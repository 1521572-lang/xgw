"""Tailscale рядом с XGW (Т1 `TAILSCALE_MINIAPP_PLAN.md`): что о нём знать правилам и diag.

XGW Tailscale не ставит и не настраивает — он работает с уже установленным `tailscaled`.
Как тот устроен на Linux (исходники Tailscale, проверено снимком Т0 на 1.104.1):

- свои сокеты (WireGuard, DERP, STUN, управление) он помечает меткой MARK в маске
  MARK_MASK, а правило `ip rule` 5210 ведёт их в таблицу main — мимо таблицы 52;
- адреса tailnet (100.64.0.0/10, fd7a:115c:a1e0::/48) и MagicDNS (100.100.100.100)
  маршрутизируются в интерфейс INTERFACE.

Без исключений в правилах XGW метку затирает «meta mark set 1», и Tailscale уходит в
Xray (К1); DNS к MagicDNS перехватывается (К2), blocked и v6_guard его отбивают (К3, К4).

Формат `tailscale status --json` Tailscale не обещает сохранять: поля читаются осторожно,
нет поля — «неизвестно», а не сбой.
"""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .net import cmd, lan
from .paths import Paths

INTERFACE = "tailscale0"
MARK = 0x80000
MARK_MASK = 0xFF0000
CGNAT = ipaddress.IPv4Network("100.64.0.0/10")
TAILNET6 = ipaddress.IPv6Network("fd7a:115c:a1e0::/48")
MAGIC_DNS = "100.100.100.100"
SOCKET = Path("run/tailscale/tailscaled.sock")  # от корня машины (paths.root)
ROUTES = ("direct", "vpn")


def socket_path(paths: Paths) -> Path:
    return paths.root / SOCKET


def present(paths: Paths, sys_net: Path | None = None) -> bool:
    """tailscaled работает: есть его интерфейс или сокет управления. Без подпроцесса —
    правила собираются на каждом шаге демона. Сокет лежит в RuntimeDirectory службы и
    исчезает с её остановкой, интерфейс убирает `tailscaled --cleanup`."""
    try:
        if ((sys_net or lan.SYS_NET) / INTERFACE).exists():
            return True
        return socket_path(paths).exists()
    except OSError:
        return False


@dataclass(frozen=True)
class Status:
    """Нужное из `tailscale status --json`; пусто — поля нет."""

    backend: str = ""  # BackendState: Running, NeedsLogin, Stopped, Starting…
    auth_url: str = ""
    dns_name: str = ""  # Self.DNSName без точки в конце
    addresses: tuple[str, ...] = ()  # Self.TailscaleIPs
    magic_dns: bool | None = None  # CurrentTailnet.MagicDNSEnabled


def parse_status(text: str) -> Status | None:
    """Вывод `tailscale status --json`; None — не JSON-объект."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    me = data.get("Self") if isinstance(data.get("Self"), dict) else {}
    tailnet = data.get("CurrentTailnet") if isinstance(data.get("CurrentTailnet"), dict) else {}
    addresses = me.get("TailscaleIPs")
    magic = tailnet.get("MagicDNSEnabled")
    return Status(
        backend=str(data.get("BackendState") or ""),
        auth_url=str(data.get("AuthURL") or ""),
        dns_name=str(me.get("DNSName") or "").rstrip("."),
        addresses=tuple(str(item) for item in addresses) if isinstance(addresses, list) else (),
        magic_dns=magic if isinstance(magic, bool) else None,
    )


def status(runner: cmd.Runner = cmd.run) -> Status | None:
    """`tailscale status --json`; None — CLI нет или он не ответил. Код возврата у CLI
    ненулевой и при NeedsLogin, а JSON он печатает всё равно."""
    try:
        return parse_status(runner(["tailscale", "status", "--json"], timeout=10.0, check=False))
    except cmd.CommandError:
        return None


@dataclass(frozen=True)
class Netcheck:
    udp: bool | None = None
    derp: str = ""  # «Nearest DERP»
    latency_ms: float | None = None  # задержка до него


_ITEM = re.compile(r"^\s*\*\s*([^:]+):\s*(.*?)\s*$")
_LATENCY = re.compile(r"^\s*-\s*\S+:\s*([\d.]+)\s*ms\s*\((.+)\)\s*$")


def parse_netcheck(text: str) -> Netcheck:
    """Отчёт `tailscale netcheck` (текст: строки «* UDP: true», «* Nearest DERP: …» и
    задержки «- fra: 88.6ms (Frankfurt)»). Строки portmap в начале пропускаются."""
    items: dict[str, str] = {}
    latency: dict[str, float] = {}
    for line in text.splitlines():
        match = _ITEM.match(line)
        if match:
            items[match.group(1).strip()] = match.group(2)
            continue
        match = _LATENCY.match(line)
        if match:
            latency.setdefault(match.group(2).strip(), float(match.group(1)))
    udp = items.get("UDP", "").lower()
    derp = items.get("Nearest DERP", "")
    return Netcheck(
        udp=True if udp == "true" else False if udp == "false" else None,
        derp=derp,
        latency_ms=latency.get(derp),
    )


def netcheck(runner: cmd.Runner = cmd.run) -> Netcheck | None:
    try:
        return parse_netcheck(runner(["tailscale", "netcheck"], timeout=30.0))
    except cmd.CommandError:
        return None


def default_route_dns(text: str) -> bool | None:
    """`resolvectl status tailscale0`: стоит ли у интерфейса DefaultRoute (Override local
    DNS в консоли tailnet — тогда через него идут все имена машины). None — не понять."""
    match = re.search(r"([+-])DefaultRoute\b", text)
    return None if match is None else match.group(1) == "+"


def cgnat(addresses: list[str] | tuple[str, ...]) -> list[str]:
    """Те из адресов IPv4, что попадают в 100.64.0.0/10."""
    found = []
    for item in addresses:
        try:
            address = ipaddress.ip_interface(item.strip()).ip
        except ValueError:
            continue
        if address.version == 4 and address in CGNAT:
            found.append(str(address))
    return found
