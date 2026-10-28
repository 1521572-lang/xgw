"""Проверки бесплатного пула в режиме наблюдения (веха М1): рабочий Xray и трафик не меняются.

Сервер Xray (VLESS, Trojan, Shadowsocks/Outline) — отдельным коротким процессом Xray, как теневая
проба (watch/shadow.py): http-inbound на 127.0.0.1 с паролем и один выход — этот сервер с меткой
mark_bypass (мимо перехвата). Через него — обычная проба проверочным файлом (скан: OK, FROZEN,
таймаут…) и, если она прошла, страна выхода по Cloudflare trace (ТЗ R15: страна — по
наблюдаемому выходу, а не по каталогу).

Сервер OpenVPN (веха М2а) — настоящим туннелем: поколение бэкенда (backend.py, agent.py) в своём
пространстве имён, затем та же проба, что у Xray, только выход временного Xray — SOCKS-работник
поколения. Трафик — по счётчикам veth (внешние байты с рукопожатием). Бэкенда нет (OpenVPN не
установлен, перехват не загружен) — как в М1: прямое TCP-соединение с адресом сервера мимо VPN,
закрыт ли адрес целиком; UDP — «не проверено».
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
from dataclasses import dataclass, replace
from pathlib import Path

from ..config import Config
from ..watch import checks, shadow
from ..watch.scan import ScanResult, scan_node
from . import agent as agenting
from . import ovpnconf
from .backend import Backend as Runtime
from .backend import BackendError
from .models import Backend, Variant
from .ovpn import OvpnProfile, OvpnRejected

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
    connect_seconds: float = 0.0  # OpenVPN: от запуска поколения до поднятого туннеля
    # OpenVPN: туннель поднимался (дальше проба могла и не пройти). Код итога этого не
    # говорит: TIMEOUT бывает и у агента (туннель не поднялся), и у пробы через туннель.
    tunnel_up: bool = False


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


def openvpn_peer(variant: Variant, profile: OvpnProfile) -> str:
    """Адрес сервера для туннеля: публичный IPv4 из каталога или из remote профиля с тем же
    портом. Имя здесь не резолвится (R45: один закреплённый адрес); нет — пусто."""
    candidates = [variant.address, variant.host,
                  *(remote.host for remote in profile.remotes if remote.port == variant.port)]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return ovpnconf.peer_address(candidate)
        except OvpnRejected:
            continue
    return ""


def check_openvpn(
    variant: Variant, profile: OvpnProfile, *, runtime: Runtime, cfg: Config, xray_bin: Path,
    run_dir: Path, auth: str = "", lan: tuple[str, ...] = (), cancel=None,
    spawn: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> Outcome:
    """Поколение бэкенда для варианта → туннель поднялся → проба и страна выхода через его
    SOCKS-работника → поколение убрано (всегда, и при сбое)."""
    peer = openvpn_peer(variant, profile)
    if not peer:
        return Outcome("UNTESTED", error="у сервера нет публичного IPv4")
    try:
        conf = ovpnconf.client_config(
            profile, remote_ip=peer, proto=variant.transport, port=variant.port,
            with_auth=bool(auth), mgmt_port=agenting.MGMT_PORT,
        )
    except OvpnRejected as exc:
        return Outcome("CONFIG_REJECTED", error=str(exc)[:160])
    started = time.monotonic()
    try:
        lease = runtime.prepare(peer=peer, proto=variant.transport, port=variant.port,
                                openvpn_conf=conf, auth=auth, lan=lan, xray_bin=xray_bin)
    except BackendError as exc:
        return Outcome(exc.code, round(time.monotonic() - started, 2), error=str(exc)[:160])
    try:
        state = runtime.wait(lease, cancel=cancel)
        if state.get("phase") != "up":
            return Outcome(
                str(state.get("reason") or "TUNNEL_FAILED"), round(time.monotonic() - started, 2),
                runtime.counters(lease), error=str(state.get("detail") or "")[:160],
            )
        connected = round(time.monotonic() - started, 2)
        outbound = {"tag": "pool", "protocol": "socks", "settings": {"servers": [{
            "address": agenting.inner_address(lease.index), "port": agenting.SOCKS_PORT,
            "users": [{"user": agenting.SOCKS_USER_NAME, "pass": lease.socks_pass}],
        }]}}
        outcome = check_xray(replace(variant, outbound=outbound), cfg, xray_bin, run_dir,
                             spawn=spawn)
        outcome.bytes_used = max(outcome.bytes_used, runtime.counters(lease))
        outcome.connect_seconds = connected
        outcome.tunnel_up = True
        return outcome
    finally:
        runtime.stop(lease)
