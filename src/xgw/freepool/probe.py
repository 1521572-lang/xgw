"""Проверки бесплатного пула в режиме наблюдения (веха М1): рабочий Xray и трафик не меняются.

Сервер Xray (VLESS, Trojan, Shadowsocks/Outline) — отдельным коротким процессом Xray, как теневая
проба (watch/shadow.py): http-inbound на 127.0.0.1 с паролем и один выход — этот сервер с меткой
mark_bypass (мимо перехвата). Через него — обычная проба проверочным файлом (скан: OK, FROZEN,
таймаут…) и, если она прошла, страна выхода по Cloudflare trace (ТЗ R15: страна — по
наблюдаемому выходу, а не по каталогу).

Сервер OpenVPN до бэкенда (веха М2) — только прямое TCP-соединение с его адресом, мимо VPN:
закрыт ли адрес целиком. Через туннель он здесь не проверяется; UDP — «не проверено».
"""

from __future__ import annotations

import contextlib
import json
import secrets
import socket
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..config import Config
from ..watch import checks, shadow
from ..watch.scan import ScanResult, scan_node
from .models import Backend, Variant

START_WAIT = 5.0
STOP_WAIT = 3.0
REACH_TIMEOUT = 4.0
TRACE_BYTES = 4096


@dataclass
class Outcome:
    """Итог проверки варианта: verdict — как у скана (OK, SLOW, FROZEN, TIMEOUT…) или
    REACHABLE / CLOSED / UNTESTED / BACKEND_PENDING для OpenVPN до вехи М2."""

    verdict: str
    seconds: float = 0.0
    bytes_used: int = 0
    egress_country: str = ""
    error: str = ""


@dataclass
class _Port:
    tag: str
    probe_port: int


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def check_xray(
    variant: Variant, cfg: Config, xray_bin: Path, run_dir: Path,
    spawn: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> Outcome:
    """Проба сервера Xray отдельным процессом: файл пробы, затем страна выхода."""
    if not variant.outbound:
        return Outcome("UNTESTED", error="нет outbound'а")
    outbound = shadow.outbound_for(variant.outbound, cfg)
    if outbound is None:
        return Outcome("UNTESTED", error="цепочка — не проверяется отдельно")
    port = _free_port()
    password = secrets.token_urlsafe(16)
    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [{
            "tag": "pool-in", "protocol": "http", "listen": "127.0.0.1", "port": port,
            "settings": {"accounts": [{"user": shadow.SHADOW_USER, "pass": password}]},
        }],
        "outbounds": [outbound],
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pool-", dir=run_dir) as directory:
        path = Path(directory) / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        path.chmod(0o600)
        try:
            proc = spawn([str(xray_bin), "run", "-c", str(path)], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            return Outcome("UNTESTED", error=f"Xray не запущен: {exc}")
        try:
            try:
                shadow._wait_port(port, time.monotonic() + START_WAIT, proc)
            except shadow.ShadowError as exc:
                return Outcome("UNTESTED", error=str(exc))
            scan: ScanResult = scan_node(
                _Port("pool", port), cfg,  # type: ignore[arg-type]
                probe_pass=password, probe_user=shadow.SHADOW_USER, random_size=True,
            )
            outcome = Outcome(scan.verdict, scan.seconds, scan.bytes_read, error=scan.error)
            if scan.verdict in ("OK", "SLOW") and cfg.probe.trace_url:
                trace = checks.http_get_via_proxy(
                    "127.0.0.1", port, cfg.probe.trace_url, timeout=10.0, keep_body=TRACE_BYTES,
                    proxy_user=shadow.SHADOW_USER, proxy_pass=password,
                    user_agent=cfg.probe.user_agent,
                )
                outcome.bytes_used += trace.downloaded
                if trace.ok:
                    outcome.egress_country = checks.parse_trace(
                        trace.body.decode("utf-8", "replace")) or ""
            return outcome
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=STOP_WAIT)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=STOP_WAIT)


def check_openvpn_reach(
    variant: Variant, mark: int | None,
    tcp_check: Callable[..., bool] = checks.tcp_check,
) -> Outcome:
    """OpenVPN до бэкенда: открывается ли TCP к адресу сервера напрямую."""
    if variant.backend != Backend.OPENVPN:
        return Outcome("UNTESTED")
    if variant.transport != "tcp":
        return Outcome("UNTESTED", error="UDP — проверка только туннелем (веха М2)")
    address = variant.address or variant.host
    if not address or mark is None:
        return Outcome("UNTESTED", error="нет адреса или метки обхода")
    started = time.monotonic()
    with contextlib.suppress(OSError):
        if tcp_check(address, variant.port, timeout=REACH_TIMEOUT, mark=mark):
            return Outcome("REACHABLE", round(time.monotonic() - started, 2))
    return Outcome("CLOSED", round(time.monotonic() - started, 2),
                   error="TCP к адресу напрямую не открывается")
