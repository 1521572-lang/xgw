"""Применение конфига sing-box и слежение за ним (generator/singbox.py).

В отличие от Xray, sing-box умеет перечитывать конфиг (SIGHUP), но проверено на 1.14.3: при этом
рвутся ВСЕ его соединения. Поэтому конфиг sing-box меняется редко — только когда меняется состав
серверов (смена профиля сервера идёт через API Xray и sing-box не трогает) — и, если через
sing-box идёт трафик, откладывается до окна перезапуска (engine.assemble решает, сейчас ли).

Порядок такой же, как у Xray: проверка `sing-box check` до записи, прежний рабочий конфиг
сохраняется как last-good, не поднялся за wait_seconds — откат на него. Все операции под той же
файловой блокировкой, что и применение Xray.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import signal
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .. import log
from ..generator import singbox as singboxing
from ..paths import Paths, atomic_write_json, atomic_write_text, file_lock
from ..xraycore.service import (
    PidfileXrayService,
    SystemdXrayService,
    XrayService,
    XrayServiceError,
)

READY_SECONDS = 3.0
UNIT = "xgw-singbox.service"


class SingboxService(XrayService):
    """Служба sing-box: к start/stop/restart/is_active добавлено перечитывание конфига."""

    def reload(self) -> None:
        raise NotImplementedError


class SystemdSingboxService(SystemdXrayService, SingboxService):
    def __init__(self, unit: str = UNIT) -> None:
        super().__init__(unit)

    def reload(self) -> None:
        self._systemctl("reload")


class PidfileSingboxService(PidfileXrayService, SingboxService):
    """sing-box как обычный процесс с pid-файлом (стенд, где нет systemd-юнита)."""

    def reload(self) -> None:
        pid = self._pid()
        if not pid or not self.is_active():
            raise XrayServiceError("sing-box не запущен")
        try:
            os.kill(pid, signal.SIGHUP)
        except OSError as exc:
            raise XrayServiceError(f"sing-box не принял SIGHUP: {exc}") from exc


def make_service(paths: Paths, bin_path: Path | None) -> SingboxService:
    """systemd-юнит xgw-singbox.service; там, где юнита нет (стенд, XGW_XRAY_SERVICE=process), —
    обычный процесс с pid-файлом."""
    if os.environ.get("XGW_XRAY_SERVICE") == "process":
        return PidfileSingboxService(
            bin_path or paths.singbox_bin, paths.singbox_config_file, paths.run / "singbox.pid",
        )
    return SystemdSingboxService()


@dataclass
class SingboxOutcome:
    # unchanged | deferred | started | reloaded | removed | rejected | rollback | failed
    mode: str
    detail: str = ""


Validator = Callable[[dict], "tuple[bool | None, str]"]


class SingboxCore:
    def __init__(
        self,
        cfg,
        paths: Paths,
        service: SingboxService,
        *,
        bin_path: Path | None = None,
        validator: Validator | None = None,
        logger=None,
        wait_seconds: float = READY_SECONDS,
    ) -> None:
        self.cfg = cfg
        self.paths = paths
        self.service = service
        if validator is None:
            binary = bin_path if bin_path is not None else singboxing.find_binary(None, paths)
            validator = lambda config: singboxing.validate_config(config, binary)  # noqa: E731
        self.validator = validator
        self.log = logger or log.get_logger("singbox")
        self.wait_seconds = wait_seconds

    # --- применение ----------------------------------------------------------------

    def apply(self, config: dict | None, *, reload: bool) -> SingboxOutcome:
        """config — желаемый конфиг (None — sing-box больше не нужен); reload — применить
        сейчас, иначе отложить (конфиг ждёт в config.pending.json)."""
        with file_lock(self.paths.lock_file):
            current = self.read()
            if config is None:
                if current is None:
                    return SingboxOutcome("unchanged")
                if not reload:
                    return SingboxOutcome(
                        "deferred", "sing-box больше не нужен — остановка отложена",
                    )
                return self._remove()
            if config == current:
                self.paths.singbox_pending_file.unlink(missing_ok=True)
                return SingboxOutcome("unchanged")
            if not reload:
                atomic_write_json(self.paths.singbox_pending_file, config)
                return SingboxOutcome("deferred", "перечитывание рвёт соединения через sing-box")
            ok, output = self.validator(config)
            if ok is False:
                return SingboxOutcome("rejected", output)
            return self._install(config, first=current is None)

    def read(self) -> dict | None:
        try:
            loaded = json.loads(self.paths.singbox_config_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            self.log.error("конфиг sing-box не читается (%s) — применяю как первый запуск", exc)
            return None
        return loaded if isinstance(loaded, dict) else None

    def expected(self) -> bool:
        """Должен ли sing-box работать: конфиг применён."""
        return self.read() is not None

    def _install(self, config: dict, *, first: bool) -> SingboxOutcome:
        path = self.paths.singbox_config_file
        previous = None
        with contextlib.suppress(FileNotFoundError, OSError):
            previous = path.read_text(encoding="utf-8")
        if previous:
            atomic_write_text(self.paths.singbox_last_good_file, previous)
        self.paths.singbox_config_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, config)
        self.paths.singbox_pending_file.unlink(missing_ok=True)
        error = self._start_or_reload(config)
        if error is None:
            return SingboxOutcome("started" if first else "reloaded")
        return self._rollback(error)

    def _start_or_reload(self, config: dict) -> str | None:
        """Запускает или заставляет перечитать конфиг и ждёт порты. None — готов, иначе причина."""
        try:
            if self.service.is_active():
                self.service.reload()
            else:
                self.service.start()
        except XrayServiceError as exc:
            return f"sing-box не запустился: {exc}"
        return self._wait_ready(config)

    def _wait_ready(self, config: dict) -> str | None:
        ports = [
            inbound["listen_port"] for inbound in config.get("inbounds") or []
            if isinstance(inbound, dict) and isinstance(inbound.get("listen_port"), int)
        ]
        deadline = time.monotonic() + self.wait_seconds
        pending = set(ports)
        while pending:
            for port in sorted(pending):
                if _listening(port):
                    pending.discard(port)
            if not pending:
                break
            if time.monotonic() >= deadline:
                return (f"sing-box не открыл {len(pending)} из {len(ports)} портов за "
                        f"{self.wait_seconds:.0f} с")
            time.sleep(0.1)
        return None

    def _remove(self) -> SingboxOutcome:
        with contextlib.suppress(XrayServiceError):
            self.service.stop()
        self.paths.singbox_config_file.unlink(missing_ok=True)
        self.paths.singbox_pending_file.unlink(missing_ok=True)
        return SingboxOutcome("removed")

    def _rollback(self, reason: str) -> SingboxOutcome:
        try:
            good_text = self.paths.singbox_last_good_file.read_text(encoding="utf-8")
            good = json.loads(good_text)
        except (OSError, json.JSONDecodeError):
            self.log.error("%s; откат невозможен: last-good sing-box отсутствует", reason)
            return SingboxOutcome("failed", f"{reason}; last-good отсутствует")
        atomic_write_text(self.paths.singbox_config_file, good_text)
        with contextlib.suppress(XrayServiceError):
            self.service.restart()
        error = self._wait_ready(good) if isinstance(good, dict) else "last-good не объект"
        if error is not None:
            self.log.error("%s; откат на last-good не помог: %s", reason, error)
            return SingboxOutcome("failed", f"{reason}; после отката: {error}")
        return SingboxOutcome("rollback", reason)

    # --- слежение --------------------------------------------------------------------

    def alive(self) -> bool:
        """sing-box работает и отвечает: служба активна, Clash API отдаёт версию."""
        if not self.service.is_active():
            return False
        secret = singboxing.clash_secret(self.read())
        try:
            conn = http.client.HTTPConnection(singboxing.LOCAL, self.cfg.core.api_port, timeout=2.0)
            try:
                conn.request("GET", "/version", headers={"Authorization": f"Bearer {secret}"})
                return conn.getresponse().status == 200
            finally:
                conn.close()
        except (OSError, http.client.HTTPException):
            return False

    def restart(self) -> str | None:
        """Перезапуск службы; None — поднялся, иначе причина."""
        current = self.read()
        try:
            self.service.restart()
        except XrayServiceError as exc:
            return f"перезапуск sing-box не удался: {exc}"
        return self._wait_ready(current or {})

    def rollback(self, reason: str) -> SingboxOutcome:
        """Откат на last-good по решению watchdog. Нечего откатывать — unchanged."""
        with file_lock(self.paths.lock_file):
            try:
                good = json.loads(self.paths.singbox_last_good_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return SingboxOutcome("unchanged", "last-good отсутствует")
            if good == self.read():
                return SingboxOutcome("unchanged", "last-good совпадает с текущим конфигом")
            return self._rollback(reason)


def _listening(port: int) -> bool:
    try:
        with socket.create_connection((singboxing.LOCAL, port), timeout=0.3):
            return True
    except OSError:
        return False
