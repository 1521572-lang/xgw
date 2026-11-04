"""Проверки бесплатного пула в режиме наблюдения (веха М1): рабочий Xray и трафик не меняются.

Сервер Xray (VLESS, VMess, Trojan, Shadowsocks/Outline) — отдельным коротким процессом Xray, как
теневая проба (watch/shadow.py): http-inbound на 127.0.0.1 с паролем и один выход — этот сервер с
меткой mark_bypass (мимо перехвата). Через него — обычная проба проверочным файлом (скан: OK,
FROZEN, таймаут…) и, если она прошла, страна выхода по Cloudflare trace (ТЗ R15: страна — по
наблюдаемому выходу, а не по каталогу).

Сервер, которого Xray не умеет (Hysteria2, TUIC, AnyTLS из списков GitHub), — так же, только
процессом sing-box: http-inbound на 127.0.0.1 с паролем и выход с routing_mark = mark_bypass —
те же поля, что у моста sing-box основного конфига (generator/singbox.py).

Адрес сервера из каталога или списка — только публичный (server_hosts): имя разрешается
резолверами шлюза (fetch.resolve_domain, public_only) и закрепляется во временном процессе
(dns.hosts у Xray, hosts-сервер DNS у sing-box — как в основном конфиге). Список с GitHub — чужой
текст: без этого он мог бы направить пробу на адрес LAN или самого шлюза.

Сервер SSTP (VPN Gate; веха М2в, до неё — OpenVPN с М2а) — настоящим туннелем: поколение
бэкенда (backend.py, agent.py) в своём пространстве имён, затем та же проба, что у Xray, только
выход временного Xray — SOCKS-работник поколения. Трафик — по счётчикам veth (внешние байты с
рукопожатием); что видел агент изнутри (TCP и DNS через туннель, пакеты из туннеля) —
diagnosis. Бэкенда нет (sstp-client не установлен, перехват не загружен) — как в М1: прямое
TCP-соединение с адресом сервера мимо VPN, закрыт ли адрес целиком.
"""

from __future__ import annotations

import contextlib
import copy
import ipaddress
import json
import secrets
import socket
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from .. import fetch, masking
from ..config import Config
from ..watch import checks, shadow
from ..watch.scan import ScanResult, scan_node
from . import agent as agenting
from .backend import Backend as Runtime
from .backend import BackendError
from .models import Backend, Variant

START_WAIT = 5.0
STOP_WAIT = 3.0
REACH_TIMEOUT = 4.0
TRACE_BYTES = 4096
DIAGNOSIS_MAX = 400  # вид изнутри, fpt0, канал к серверу, охрана

Resolver = Callable[..., list[str]]


@dataclass
class Outcome:
    """Итог проверки варианта: verdict — как у скана (OK, SLOW, FROZEN, TIMEOUT…), код отказа
    туннеля (agent.py) или REACHABLE / CLOSED / UNTESTED для туннеля без бэкенда."""

    verdict: str
    seconds: float = 0.0
    bytes_used: int = 0
    egress_country: str = ""
    error: str = ""
    connect_seconds: float = 0.0  # туннель: от запуска поколения до поднятого туннеля
    # Туннель поднимался (дальше проба могла и не пройти). Код итога этого не говорит:
    # TIMEOUT бывает и у агента (туннель не поднялся), и у пробы через туннель.
    tunnel_up: bool = False
    # Туннель: что агент увидел изнутри (TCP и DNS через туннель, пакеты из туннеля) — без
    # адресов. Отчёт М2а: проба через туннель не прошла ни разу, а почему — не узнать.
    diagnosis: str = ""


@dataclass
class _Port:
    tag: str
    probe_port: int


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _server_names(variant: Variant) -> list[str]:
    """Адреса, к которым подключится временный процесс: сервер и звенья sing-box (shadowtls)."""
    names = [variant.host or variant.address]
    if variant.singbox:
        for item in [variant.singbox.get("main") or {}, *(variant.singbox.get("extra") or [])]:
            if isinstance(item, dict) and item.get("server"):
                names.append(str(item["server"]))
    return [name.strip("[]").lower() for name in dict.fromkeys(names) if name]


def server_hosts(variant: Variant, cfg: Config, mark: int | None, *,
                 resolve: Resolver = fetch.resolve_domain) -> tuple[dict[str, list[str]], str]:
    """Закрепление адреса сервера: ({имя: [адреса IPv4]}, "") либо ({}, почему проверять
    нельзя). Адрес — только публичный IPv4 (fetch.is_bogon: не LAN, не loopback, не сеть
    операторов); имя — резолверами шлюза, только публичные ответы."""
    hosts: dict[str, list[str]] = {}
    names = _server_names(variant)
    if not names:
        return {}, "нет адреса сервера"
    for name in names:
        try:
            ipaddress.ip_address(name)
        except ValueError:
            pass
        else:
            if fetch.is_bogon(name):
                return {}, "адрес сервера — не публичный IPv4"
            continue
        try:
            ips = resolve(name, cfg.dns.resolvers, mark=mark, public_only=True)
        except fetch.NoSuchDomain:
            return {}, "имени сервера нет в DNS"
        except (fetch.ResolveError, fetch.Cancelled, OSError) as exc:
            return {}, f"имя сервера не разрешилось: {type(exc).__name__}"
        ips = [ip for ip in ips if not fetch.is_bogon(ip)]
        if not ips:
            return {}, "у имени сервера нет публичного IPv4"
        hosts[name] = sorted(ips)
    return hosts, ""


def _probe(port: int, password: str, cfg: Config) -> Outcome:
    """Проба через http-inbound временного процесса: файл пробы, затем страна выхода."""
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


def _run_probe(argv_of: Callable[[Path], list[str]], config: dict, port: int, password: str,
               cfg: Config, run_dir: Path, spawn: Callable[..., subprocess.Popen],
               what: str) -> Outcome:
    """Временный процесс с конфигом config (0600, во временном каталоге run_dir), проба через
    его порт port, остановка — всегда. Вывод процесса — в файл того же каталога: не
    запустился — в причину идёт его строка отказа без секретов (отчёт М2а.1: «Xray завершился
    с кодом 23» ×4, а почему — не узнать)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pool-", dir=run_dir) as directory:
        path = Path(directory) / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        path.chmod(0o600)
        log_path = Path(directory) / "core.log"
        with open(log_path, "wb") as log:
            try:
                proc = spawn(argv_of(path), stdin=subprocess.DEVNULL, stdout=log,
                             stderr=subprocess.STDOUT)
            except OSError as exc:
                return Outcome("UNTESTED", error=f"{what} не запущен: {exc}")
        try:
            try:
                shadow._wait_port(port, time.monotonic() + START_WAIT, proc)
            except shadow.ShadowError as exc:
                error = str(exc).replace("теневой Xray", what)
                why = core_failure(log_path, config)
                return Outcome("UNTESTED", error=f"{error}: {why}" if why else error)
            return _probe(port, password, cfg)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=STOP_WAIT)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=STOP_WAIT)


def core_failure(log_path: Path, config: dict) -> str:
    """Строка отказа временного процесса из его вывода (agent.core_reason): секреты конфига,
    адреса и имена скрыты. Пусто — вывода нет или в нём нет ошибки."""
    try:
        with open(log_path, "rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - 16384))
            text = handle.read().decode("utf-8", "replace")
    except OSError:
        return ""
    return agenting.core_reason(text.splitlines(), masking.collect_secrets(config))


def check_xray(
    variant: Variant, cfg: Config, xray_bin: Path, run_dir: Path,
    spawn: Callable[..., subprocess.Popen] = subprocess.Popen, *,
    hosts: dict[str, list[str]] | None = None,
) -> Outcome:
    """Проба сервера Xray отдельным процессом: файл пробы, затем страна выхода. hosts —
    закреплённые адреса сервера (server_hosts) в dns.hosts, как в основном конфиге."""
    if not variant.outbound:
        return Outcome("UNTESTED", error="нет outbound'а")
    outbound = shadow.outbound_for(variant.outbound, cfg)
    if outbound is None:
        return Outcome("UNTESTED", error="цепочка — не проверяется отдельно")
    port = _free_port()
    password = secrets.token_urlsafe(16)
    config: dict = {
        "log": {"loglevel": "warning"},
        "inbounds": [{
            "tag": "pool-in", "protocol": "http", "listen": "127.0.0.1", "port": port,
            "settings": {"accounts": [{"user": shadow.SHADOW_USER, "pass": password}]},
        }],
        "outbounds": [outbound],
    }
    if hosts:
        config["dns"] = {"hosts": hosts, "queryStrategy": "UseIPv4"}
    return _run_probe(lambda path: [str(xray_bin), "run", "-c", str(path)], config, port,
                      password, cfg, run_dir, spawn, "Xray")


def singbox_config(variant: Variant, cfg: Config, port: int, password: str,
                   hosts: dict[str, list[str]]) -> dict | None:
    """Конфиг временного sing-box: http-inbound с паролем → сервер варианта (и его звенья) с
    routing_mark = mark_bypass; имена — из hosts. None — так не проверить (WireGuard)."""
    spec = variant.singbox or {}
    if spec.get("endpoint") or not isinstance(spec.get("main"), dict):
        return None
    main = copy.deepcopy(spec["main"])
    extras = [copy.deepcopy(item) for item in spec.get("extra") or [] if isinstance(item, dict)]
    main["tag"] = "pool"
    renames = {str(item.get("tag")): f"pool-{item.get('tag')}" for item in extras}
    for item in extras:
        item["tag"] = renames[str(item.get("tag"))]
    if main.get("detour") in renames:
        main["detour"] = renames[main["detour"]]
    for body in (main, *extras):
        body["routing_mark"] = cfg.capture.mark_bypass
    return {
        "log": {"level": "warn"},
        "dns": {"servers": [{"type": "hosts", "tag": "hosts", "predefined": hosts}]},
        "inbounds": [{
            "type": "http", "tag": "pool-in", "listen": "127.0.0.1", "listen_port": port,
            "users": [{"username": shadow.SHADOW_USER, "password": password}],
        }],
        "outbounds": [main, *extras],
        "route": {
            "rules": [{"inbound": ["pool-in"], "action": "route", "outbound": "pool"}],
            "default_domain_resolver": "hosts",
        },
    }


def check_singbox(
    variant: Variant, cfg: Config, singbox_bin: Path, run_dir: Path,
    spawn: Callable[..., subprocess.Popen] = subprocess.Popen, *,
    hosts: dict[str, list[str]] | None = None,
) -> Outcome:
    """Проба сервера, которого умеет только sing-box (Hysteria2, TUIC, AnyTLS), отдельным
    процессом sing-box; дальше — как у Xray."""
    port = _free_port()
    password = secrets.token_urlsafe(16)
    config = singbox_config(variant, cfg, port, password, hosts or {})
    if config is None:
        return Outcome("UNTESTED", error="WireGuard — не проверяется")
    return _run_probe(lambda path: [str(singbox_bin), "run", "-c", str(path)], config, port,
                      password, cfg, run_dir, spawn, "sing-box")


def check_tunnel_reach(
    variant: Variant, mark: int | None,
    tcp_check: Callable[..., bool] = checks.tcp_check,
) -> Outcome:
    """Туннель без бэкенда: открывается ли TCP к адресу сервера напрямую."""
    if variant.backend != Backend.SSTP:
        return Outcome("UNTESTED")
    address = tunnel_peer(variant)
    if not address or mark is None:
        return Outcome("UNTESTED", error="нет публичного адреса или метки обхода")
    started = time.monotonic()
    with contextlib.suppress(OSError):
        if tcp_check(address, variant.port, timeout=REACH_TIMEOUT, mark=mark):
            return Outcome("REACHABLE", round(time.monotonic() - started, 2))
    return Outcome("CLOSED", round(time.monotonic() - started, 2),
                   error="TCP к адресу напрямую не открывается")


def tunnel_peer(variant: Variant) -> str:
    """Адрес сервера для туннеля: публичный IPv4 из каталога (R45: один закреплённый адрес;
    имя здесь не резолвится); нет — пусто."""
    try:
        return agenting.peer_address(variant.address) if variant.address else ""
    except ValueError:
        return ""


def tunnel_diagnosis(at_up: dict, after: dict) -> str:
    """Что видел агент: проверка изнутри (при подъёме), счётчики fpt0 и отбитое охраной после
    подъёма — на момент после пробы или отказа. Без адресов — это строка журнала демона и
    записи кандидата."""
    inner = agenting.inner_text(after.get("inner") or at_up.get("inner"))
    traffic = agenting.tunnel_text(after.get("tun") or at_up.get("tun"))
    link = agenting.link_text(after.get("link_after_up") or at_up.get("link_after_up"))
    refused = after.get("refused_after_up") or {}
    guard = ""
    if isinstance(refused, dict) and any(
            refused.get(name) for name in (agenting.REFUSED_VPN, agenting.REFUSED_SOCKS)):
        guard = "охрана после подъёма: " + agenting.guard_text(refused)
    return "; ".join(part for part in (inner, traffic, link and f"канал к серверу: {link}",
                                       guard) if part)[:DIAGNOSIS_MAX]


def check_tunnel(
    variant: Variant, *, runtime: Runtime, cfg: Config, xray_bin: Path, run_dir: Path,
    user: str, password: str, lan: tuple[str, ...] = (), cancel=None,
    spawn: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> Outcome:
    """Поколение бэкенда для варианта SSTP → туннель поднялся → проба и страна выхода через его
    SOCKS-работника → поколение убрано (всегда, и при сбое)."""
    peer = tunnel_peer(variant)
    if not peer:
        return Outcome("UNTESTED", error="у сервера нет публичного IPv4")
    started = time.monotonic()
    try:
        lease = runtime.prepare(peer=peer, port=variant.port, host=variant.host, user=user,
                                password=password, lan=lan, xray_bin=xray_bin)
    except BackendError as exc:
        return Outcome(exc.code, round(time.monotonic() - started, 2), error=str(exc)[:160])
    try:
        state = runtime.wait(lease, cancel=cancel)
        if state.get("phase") != "up":
            # Туннель мог подняться, а отказать — работник (отчёт М2а.1: SOCKS_FAILED у всех
            # четырёх, а в записях — ни «туннель поднимался», ни что видно изнутри).
            was_up = bool(state.get("tunnel_at"))
            return Outcome(
                str(state.get("reason") or "TUNNEL_FAILED"), round(time.monotonic() - started, 2),
                runtime.counters(lease), error=str(state.get("detail") or "")[:160],
                tunnel_up=was_up, diagnosis=tunnel_diagnosis(state, state) if was_up else "",
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
        outcome.diagnosis = tunnel_diagnosis(state, runtime.state(lease))
        return outcome
    finally:
        runtime.stop(lease)
