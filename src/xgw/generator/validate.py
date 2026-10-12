"""Проверка конфига установленным Xray: xray run -test.

Конфиг содержит секреты, поэтому временный файл создаётся с правами 0600
и удаляется сразу после проверки; вывод маскируется.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .. import masking
from ..net.cmd import HIDDEN
from ..paths import Paths
from ..xraycore import binary


def find_xray(explicit: str | Path | None = None, paths: Paths | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(Path(explicit))
    env_bin = os.environ.get("XGW_XRAY_BIN")
    if env_bin:
        candidates.append(Path(env_bin))
    if paths is not None:
        candidates.append(paths.xray_bin)
    for name in ("xray", "xray.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _for_test(config: dict) -> dict:
    """Конфиг для `xray run -test`. Эта проверка создаёт TUN-интерфейс из inbound `tun`
    (Xray 26.3.27 делает это и в режиме -test), а рабочий Xray держит интерфейс XGW
    открытым — вторая попытка подключиться к нему кончилась бы отказом «устройство
    занято». Поэтому имя подменяется одноразовым; без прав root интерфейс не создать, и
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
    fd, tmp_name = tempfile.mkstemp(prefix="xgw-validate-", suffix=".json")  # права 0600
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
                **HIDDEN,
            )
        except subprocess.TimeoutExpired:
            return False, "xray run -test: таймаут 60 с"
        except OSError as exc:
            return False, f"xray run -test не запустился: {exc}"
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


def find_invalid_outbounds(outbounds: list[dict], xray_bin: Path) -> dict[str, str]:
    """Тег → ошибка для outbounds, которые установленный Xray не принимает.

    Каждый outbound проверяется отдельным минимальным конфигом. Нужно, чтобы
    один сервер с неподдерживаемым транспортом или шифром не блокировал
    обновление всей подписки: его можно отбросить и собрать конфиг без него.
    """
    invalid: dict[str, str] = {}
    for outbound in outbounds:
        ok, output = _run_test({"log": {"loglevel": "warning"}, "outbounds": [outbound]}, xray_bin)
        if not ok:
            lines = [line for line in output.splitlines() if line.strip()]
            # Xray пишет цепочку «… > infra/conf: … > причина»: нужна только причина.
            reason = lines[-1].rsplit(" > ", 1)[-1] if lines else "ошибка проверки"
            invalid[str(outbound.get("tag", ""))] = reason
    return invalid
