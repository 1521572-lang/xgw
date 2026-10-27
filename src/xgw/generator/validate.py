"""Проверка конфига установленным Xray: xray run -test.

Конфиг содержит секреты, поэтому временный файл создаётся с правами 0600
и удаляется сразу после проверки; вывод маскируется.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TypeVar

from .. import masking
from ..paths import Paths, secret_tempdir
from ..xraycore import binary

T = TypeVar("T")


def find_xray(explicit: str | Path | None = None, paths: Paths | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit))
    env_bin = os.environ.get("XGW_XRAY_BIN")
    if env_bin:
        candidates.append(Path(env_bin))
    if paths is not None:
        candidates.append(paths.xray_bin)
    found = shutil.which("xray")
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _for_test(config: dict) -> dict:
    """Конфиг для `xray run -test`. Эта проверка создаёт TUN-интерфейс из inbound `tun`
    (Xray 26.3.27 делает это и в режиме -test; 26.10.10 — уже нет), а рабочий Xray держит
    интерфейс XGW открытым — вторая попытка подключиться к нему кончилась бы отказом
    «устройство занято». Поэтому имя подменяется одноразовым; без прав root интерфейс не создать, и
    inbound убирается из проверки совсем (его принимает службный запуск от xray)."""
    inbounds = config.get("inbounds")
    if not isinstance(inbounds, list) or not any(
        isinstance(item, dict) and item.get("protocol") == "tun" for item in inbounds
    ):
        return config
    can_create = hasattr(os, "geteuid") and os.geteuid() == 0
    checked = copy.deepcopy(config)
    items = []
    for item in checked["inbounds"]:
        if isinstance(item, dict) and item.get("protocol") == "tun":
            if not can_create:
                continue
            item.setdefault("settings", {})["name"] = f"xgwchk{os.getpid() % 100000}"
        items.append(item)
    checked["inbounds"] = items
    return checked


def _run_test(config: dict, xray_bin: Path) -> tuple[bool, str]:
    verdict, output = _test_once(config, xray_bin)
    return verdict is True, output


def _test_once(config: dict, xray_bin: Path) -> tuple[bool | None, str]:
    """Вердикт `xray run -test`; None — вердикта нет (Xray не запустился или завис)."""
    # Права 0600; в /run/xgw (в памяти), а не в /tmp на диске: в конфиге — ключи серверов.
    fd, tmp_name = tempfile.mkstemp(prefix="xgw-validate-", suffix=".json", dir=secret_tempdir())
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(_for_test(config), handle, ensure_ascii=False, indent=2)
        try:
            proc = subprocess.run(
                [str(xray_bin), "run", "-test", "-c", str(tmp)],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            return None, "xray run -test: таймаут 60 с"
        except OSError as exc:
            return None, f"xray run -test не запустился: {exc}"
        secrets = masking.collect_secrets(config)
        output = masking.mask_text((proc.stdout or "") + (proc.stderr or ""), secrets)
        return proc.returncode == 0, output.strip()
    finally:
        tmp.unlink(missing_ok=True)


def validate_config(config: dict, xray_bin: Path | None) -> tuple[bool | None, str]:
    """True/False — вердикт xray run -test; None — Xray не найден (проверка пропущена).

    Xray старше минимальной версии — отказ ещё до проверки: такой бинарник
    конфиг примет, но поле httpMethod проигнорирует.
    """
    if xray_bin is None:
        return None, "xray не найден — проверка xray run -test пропущена"
    version = binary.installed_version(xray_bin)
    if version is not None and version < binary.MIN_VERSION:
        found = ".".join(map(str, version))
        return False, (
            f"установлен Xray {found}, нужен не ниже {binary.min_version_text()}: "
            "в более старых нет GET-проб (burstObservatory.pingConfig.httpMethod)"
        )
    return _run_test(config, xray_bin)


def narrow(
    items: Sequence[T], check: Callable[[list[T]], tuple[bool | None, str]],
) -> dict[int, str]:
    """Номер → вывод проверки для элементов, которых проверка не принимает поодиночке.

    Делением пополам: сначала все вместе — плохих нет, и хватило одного запуска; не прошло —
    каждая половина отдельно, и так до одного элемента. k плохих среди n — около
    2·k·log2(n/k) запусков вместо n (аудит, F-07: при 150 серверах — 150 запусков Xray на
    каждой сборке). Набор проходит, только если проходит каждый элемент (теги у всех разные),
    — так и у `xray run -test`, и у `sing-box check`. Вердикта нет (check вернул None: ядро не
    запустилось, зависло) — поиск прекращается: иначе каждый следующий запуск ждал бы того же."""
    failed: dict[int, str] = {}
    stopped = False

    def probe(lo: int, hi: int) -> None:
        nonlocal stopped
        if stopped:
            return
        verdict, output = check(list(items[lo:hi]))
        if verdict is None:
            stopped = True
            return
        if verdict:
            return
        if hi - lo == 1:
            failed[lo] = output
            return
        middle = (lo + hi) // 2
        probe(lo, middle)
        probe(middle, hi)

    if items:
        probe(0, len(items))
    return failed


# Что ядро уже отвергло: ключ — содержимое (без тега) и сам бинарник, значение — причина.
# Плохой сервер обычно так и остаётся в подписке, а она обновляется каждый час: при следующей
# сборке он отбрасывается без запуска ядра. Другой бинарник (обновление ядра) — другой ключ.
_REJECTED: dict[str, str] = {}
_REJECTED_MAX = 512


def binary_id(path: Path) -> str:
    try:
        info = path.stat()
    except OSError:
        return str(path)
    return f"{path}:{info.st_mtime_ns}:{info.st_size}"


def rejected_key(item: object, core: str) -> str:
    """core — binary_id ядра, которое проверяло."""
    if isinstance(item, dict):
        item = {key: value for key, value in item.items() if key != "tag"}
    text = json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(f"{core}\n{text}".encode()).hexdigest()


def known_rejection(key: str) -> str | None:
    return _REJECTED.get(key)


def remember_rejection(key: str, reason: str) -> None:
    if len(_REJECTED) >= _REJECTED_MAX:
        _REJECTED.clear()
    _REJECTED[key] = reason


def find_invalid_outbounds(outbounds: list[dict], xray_bin: Path) -> dict[str, str]:
    """Тег → ошибка для outbounds, которые установленный Xray не принимает.

    Нужно, чтобы один сервер с неподдерживаемым транспортом или шифром не блокировал
    обновление всей подписки: его можно отбросить и собрать конфиг без него. Отвергнутые
    раньше этим же Xray не проверяются снова, остальные — делением пополам (narrow)."""
    core = binary_id(xray_bin)
    invalid: dict[str, str] = {}
    unknown: list[tuple[dict, str]] = []
    for outbound in outbounds:
        key = rejected_key(outbound, core)
        reason = known_rejection(key)
        if reason is None:
            unknown.append((outbound, key))
        else:
            invalid[str(outbound.get("tag", ""))] = reason

    def check(chunk: list[tuple[dict, str]]) -> tuple[bool | None, str]:
        config = {"log": {"loglevel": "warning"}, "outbounds": [item for item, _key in chunk]}
        return _test_once(config, xray_bin)

    for index, output in narrow(unknown, check).items():
        outbound, key = unknown[index]
        lines = [line for line in output.splitlines() if line.strip()]
        # Xray пишет цепочку «… > infra/conf: … > причина»: нужна только причина.
        reason = lines[-1].rsplit(" > ", 1)[-1] if lines else "ошибка проверки"
        invalid[str(outbound.get("tag", ""))] = reason
        remember_rejection(key, reason)
    order = [str(outbound.get("tag", "")) for outbound in outbounds]
    return {tag: invalid[tag] for tag in order if tag in invalid}
