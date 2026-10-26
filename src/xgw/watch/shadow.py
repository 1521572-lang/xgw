"""Теневая проба профиля (0.2.0, ДОП-3 рекомендаций к аудиту 0.1.18).

Сервер, который блокировка загнала на тяжёлый профиль обхода (дробление ClientHello,
sing-box), раз в fragment.calm_hours (профили sing-box — раз в сутки) пробуется на базовом
профиле. До 0.2.0 проба шла на месте: рабочий выход сервера в Xray переводился на базовый
профиль, и, если блокировка ещё действовала, трафик устройств через этот сервер (свой
сервер устройства, основной) висел до следующей проверки (STALL_BEFORE_BODY).

Теперь — отдельным коротким процессом Xray: один http-inbound на 127.0.0.1 с паролем и один
выход — тот же сервер на базовом профиле Xray (с меткой mark_bypass, мимо перехвата). Проба
— обычный скан через этот inbound (watch/scan.py); процесс сразу останавливается.
Рабочий Xray и его трафик не меняются, пока проба не прошла.
"""

from __future__ import annotations

import contextlib
import copy
import json
import secrets
import socket
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..config import Config
from ..generator import builder
from .scan import ScanResult, scan_node

START_WAIT = 5.0  # столько ждать, пока теневой Xray откроет порт
STOP_WAIT = 3.0
SHADOW_USER = "xgw-shadow"


class ShadowError(Exception):
    """Теневой Xray не запустился — пробу сделать нельзя (это не вердикт о сервере)."""


@dataclass
class _Probe:
    """Что нужно scan_node от узла: тег (для журнала) и порт probe-inbound."""

    tag: str
    probe_port: int


def outbound_for(outbound: dict, cfg: Config) -> dict | None:
    """Выход сервера на базовом профиле Xray для теневого процесса; None — так нельзя:
    выход ссылается на другие (цепочка dialerProxy, proxySettings)."""
    result = copy.deepcopy(outbound)
    stream = result.get("streamSettings") or {}
    sockopt = stream.get("sockopt") or {}
    if result.get("proxySettings") or sockopt.get("dialerProxy"):
        return None
    result["tag"] = "shadow"
    builder._modernize(result)
    builder._apply_sockopt(result, cfg.capture.mark_bypass)
    return result


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_port(port: int, deadline: float, proc: subprocess.Popen) -> None:
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise ShadowError(f"теневой Xray завершился с кодом {proc.returncode}")
        with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", port), 0.2):
            return
        time.sleep(0.05)
    raise ShadowError("теневой Xray не открыл порт")


def probe(
    outbound: dict, cfg: Config, xray_bin: Path, *, url: str, run_dir: Path,
    cancel: threading.Event | None = None,
    spawn: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> ScanResult:
    """Скан сервера на базовом профиле отдельным процессом Xray. outbound — уже из
    outbound_for. ShadowError — процесс не запустился."""
    port = _free_port()
    password = secrets.token_urlsafe(16)
    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [{
            "tag": "shadow-in", "protocol": "http", "listen": "127.0.0.1", "port": port,
            "settings": {"accounts": [{"user": SHADOW_USER, "pass": password}]},
        }],
        "outbounds": [outbound],
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="shadow-", dir=run_dir) as directory:
        path = Path(directory) / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        path.chmod(0o600)
        try:
            proc = spawn(
                [str(xray_bin), "run", "-c", str(path)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise ShadowError(f"теневой Xray не запущен: {exc}") from exc
        try:
            _wait_port(port, time.monotonic() + START_WAIT, proc)
            return scan_node(
                _Probe(tag="shadow", probe_port=port), cfg,  # type: ignore[arg-type]
                probe_pass=password, probe_user=SHADOW_USER, url=url, cancel=cancel,
            )
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=STOP_WAIT)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=STOP_WAIT)
