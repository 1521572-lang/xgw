"""Клиент Xray API через официальный CLI `xray api` (без gRPC-зависимостей).

Синтаксис сверен с установленной версией 26.3.27: флаги подкоманды
(`-s`, `-t`, `-append`, `-b`, `-r`) обязаны идти ДО позиционных аргументов,
иначе парсер их игнорирует. Временные JSON с секретами создаются с правами
0600 и удаляются сразу после вызова. Закрепление (bo) — только вручную из
CLI, не автоматически (раздел 6.8 ТЗ).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .. import masking
from ..paths import secret_tempdir


class ApiError(Exception):
    pass


@dataclass(frozen=True)
class BalancerInfo:
    override: str | None  # закреплённый вручную узел (bo), если есть
    selects: tuple[str, ...]  # узлы, которые сейчас выбирает стратегия


_ROW_RE = re.compile(r"^\s*\d+\s+(\S+)\s*$")


def parse_balancer_info(text: str) -> BalancerInfo:
    """Разбор вывода `xray api bi` (проверено на 26.3.27):

        - Selecting Override:
            1   proxy-nl-1243
          - Selects:
            1   proxy-de-1f80

    Строка с номером без тега означает «никого»: живых узлов стратегия не видит.
    """
    override: str | None = None
    selects: list[str] = []
    section = ""
    for line in text.splitlines():
        lowered = line.lower()
        if "override" in lowered:
            section = "override"
        elif "selects" in lowered:
            section = "selects"
        else:
            match = _ROW_RE.match(line)
            if not match:
                continue
            if section == "override":
                override = match.group(1)
            elif section == "selects":
                selects.append(match.group(1))
    return BalancerInfo(override=override, selects=tuple(selects))


def server_address(listen: str) -> str:
    """api.listen конфига Xray → адрес для `xray api -s`: путь Unix-сокета — unix://путь."""
    return f"unix://{listen}" if listen.startswith("/") else listen


def applied_listen(config_file: Path) -> str:
    """api.listen из файла конфига Xray; "" — файла нет, он не читается или адреса в нём нет."""
    try:
        config = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    api = config.get("api") if isinstance(config, dict) else None
    listen = api.get("listen") if isinstance(api, dict) else None
    return listen if isinstance(listen, str) else ""



# Вывод `xray api` — список outbound'ов, статистика: больше не бывает. Ответ приходит от процесса
# ядра, и демон с правами root не копит его в памяти без меры (пятый аудит, A7).
MAX_OUTPUT = 4 * 1024 * 1024


def bounded_run(
    argv: list[str], timeout: float, limit: int = MAX_OUTPUT,
) -> tuple[int, str, str]:
    """Как subprocess.run(capture_output=True, text=True, timeout=…), но вывод больше limit —
    процесс убивается, ApiError. TimeoutExpired — как у subprocess.run."""
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    parts: dict[str, list[bytes]] = {"out": [], "err": []}
    total = [0]
    over = threading.Event()
    lock = threading.Lock()

    def pump(stream, key: str) -> None:
        while True:
            chunk = stream.read1(65536)
            if not chunk:
                return
            with lock:
                total[0] += len(chunk)
                if total[0] > limit:
                    over.set()
            if over.is_set():
                with contextlib.suppress(OSError):
                    proc.kill()
                return
            parts[key].append(chunk)

    readers = [threading.Thread(target=pump, args=(proc.stdout, "out"), daemon=True),
               threading.Thread(target=pump, args=(proc.stderr, "err"), daemon=True)]
    for reader in readers:
        reader.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise
    finally:
        for reader in readers:
            reader.join(timeout=5)
        for stream in (proc.stdout, proc.stderr):
            with contextlib.suppress(OSError):
                stream.close()
    if over.is_set():
        raise ApiError(f"ответ xray api больше {limit // (1024 * 1024)} МиБ")
    return (proc.returncode, b"".join(parts["out"]).decode("utf-8", "replace"),
            b"".join(parts["err"]).decode("utf-8", "replace"))

@dataclass(frozen=True)
class ApiClient:
    bin_path: Path
    server: str = "127.0.0.1:10085"
    timeout: float = 10.0
    # Применённый конфиг Xray: адрес берётся из его api.listen — на нём ядро и слушает. С 0.2.0
    # это сокет, а после отката на last-good прежней версии ядро может слушать и старый порт
    # (ASSUMPTIONS п. 253). Нет файла или адреса в нём — server.
    config_file: Path | None = None
    _cache: dict = field(default_factory=dict, compare=False, repr=False)

    def address(self) -> str:
        """Адрес API для `xray api -s`; файл конфига перечитывается, только когда он изменился."""
        if self.config_file is None:
            return self.server
        try:
            stat = self.config_file.stat()
        except OSError:
            return self.server
        key = (stat.st_mtime_ns, stat.st_size)
        cached = self._cache.get("listen")
        if cached is not None and cached[0] == key:
            return cached[1]
        listen = applied_listen(self.config_file)
        address = server_address(listen) if listen else self.server
        self._cache["listen"] = (key, address)
        return address

    def _run(
        self,
        command: str,
        *positionals: str,
        flags: list[str] | None = None,
        payload: dict | None = None,
    ) -> str:
        """`xray api <command> [flags…] -s <server> -t <sec> [positionals…] [file]`."""
        tmp: Path | None = None
        try:
            argv = [str(self.bin_path), "api", command]
            argv.extend(flags or [])
            argv.extend(["-s", self.address(), "-t", str(int(self.timeout))])
            argv.extend(positionals)
            if payload is not None:
                fd, name = tempfile.mkstemp(prefix="xgw-api-", suffix=".json",
                                            dir=secret_tempdir())  # в памяти: там ключи
                tmp = Path(name)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False)
                with contextlib.suppress(OSError):
                    os.chmod(tmp, 0o600)
                argv.append(str(tmp))
            try:
                returncode, stdout, stderr = bounded_run(argv, self.timeout + 5)
            except subprocess.TimeoutExpired as exc:
                raise ApiError(f"таймаут xray api {command}") from exc
            output = masking.mask_text(stdout + stderr).strip()
            if returncode != 0:
                detail = output or f"код {returncode}"
                raise ApiError(f"xray api {command}: {detail}")
            return output
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)

    # --- outbounds ------------------------------------------------------------

    def add_outbounds(self, outbounds: list[dict]) -> str:
        return self._run("ado", payload={"outbounds": outbounds})

    def remove_outbound(self, tag: str) -> str:
        return self._run("rmo", tag)

    # --- inbounds -------------------------------------------------------------

    def add_inbounds(self, inbounds: list[dict]) -> str:
        return self._run("adi", payload={"inbounds": inbounds})

    def remove_inbound(self, tag: str) -> str:
        return self._run("rmi", tag)

    # --- routing --------------------------------------------------------------

    def replace_routing(self, routing: dict, *, append: bool = False) -> str:
        """Замена правил маршрутизации вместе с балансировщиками (adrules)."""
        flags = ["-append"] if append else []
        return self._run("adrules", flags=flags, payload={"routing": routing})

    # --- наблюдение -----------------------------------------------------------

    def balancer_info(self, *balancers: str) -> str:
        """Состояние балансировщика(ов): health, strategy, selecting."""
        return self._run("bi", *balancers)

    def balancer_state(self, balancer: str) -> BalancerInfo:
        return parse_balancer_info(self.balancer_info(balancer))

    def list_outbounds(self) -> str:
        return self._run("lso")

    def list_inbounds(self) -> str:
        return self._run("lsi")

    def pin(self, balancer: str, outbound_tag: str) -> str:
        """Ручное закрепление узла (xgw pin); отключает автопереключение!"""
        return self._run("bo", outbound_tag, flags=["-b", balancer])

    def unpin(self, balancer: str) -> str:
        return self._run("bo", flags=["-b", balancer, "-r"])
