"""Данные о LAN из конфига: интерфейс, адрес шлюза, статические аренды, обход.

Всё, что попадает в текст правил nftables и конфиг dnsmasq, проверяется здесь:
имя интерфейса, адреса и MAC из config.toml не должны уметь испортить правила.
"""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import dataclass

from ..config import Config
from . import cmd

_IFACE_RE = re.compile(r"[A-Za-z0-9_.-]{1,15}")
_MAC_RE = re.compile(r"([0-9a-f]{2}:){5}[0-9a-f]{2}")
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}")


@dataclass(frozen=True)
class Lease:
    mac: str
    ip: str
    name: str = ""


def valid_interface(name: str) -> bool:
    """Имя сетевого интерфейса Linux: до 15 символов, без пробелов и кавычек."""
    return bool(_IFACE_RE.fullmatch(name)) and name not in (".", "..")


def normalize_mac(text: str) -> str | None:
    mac = text.strip().lower().replace("-", ":")
    return mac if _MAC_RE.fullmatch(mac) else None


def lan_interface(cfg: Config) -> str:
    """Карта к Wi-Fi-роутеру; пусто — режим «только эта машина»."""
    name = cfg.network.lan_if.strip()
    return name if name and valid_interface(name) else ""


def wan_interface(cfg: Config) -> str:
    """Явно заданный WAN; пусто — «любой интерфейс, кроме LAN»."""
    name = cfg.network.wan_if.strip()
    return name if name and valid_interface(name) else ""


def default_route_interface(runner: cmd.Runner = cmd.run) -> str:
    """Интерфейс маршрута по умолчанию; пусто — маршрута нет или `ip` недоступен."""
    try:
        routes = json.loads(runner(["ip", "-j", "route", "show", "default"]) or "[]")
    except (cmd.CommandError, json.JSONDecodeError):
        return ""
    for route in routes if isinstance(routes, list) else []:
        device = route.get("dev", "") if isinstance(route, dict) else ""
        if device and valid_interface(device):
            return device
    return ""


def effective_wan(cfg: Config, runner: cmd.Runner = cmd.run) -> str:
    """WAN: network.wan_if, а если он пуст — интерфейс маршрута по умолчанию."""
    return wan_interface(cfg) or default_route_interface(runner)


def gateway(cfg: Config) -> ipaddress.IPv4Interface | None:
    """lan_address шлюза вместе с сетью; None — значение не разобрать."""
    try:
        return ipaddress.IPv4Interface(cfg.network.lan_address.strip())
    except ValueError:
        return None


def parse_leases(cfg: Config) -> tuple[list[Lease], list[str]]:
    """static_leases: «aa:bb:cc:dd:ee:ff,192.168.50.20,имя» (имя необязательно)."""
    leases: list[Lease] = []
    warnings: list[str] = []
    seen_mac: set[str] = set()
    seen_ip: set[str] = set()
    for entry in cfg.network.static_leases:
        parts = [part.strip() for part in entry.split(",")]
        mac = normalize_mac(parts[0]) if parts else None
        try:
            address = str(ipaddress.IPv4Address(parts[1])) if len(parts) > 1 else None
        except ValueError:
            address = None
        name = parts[2] if len(parts) > 2 else ""
        if mac is None or address is None or len(parts) > 3:
            warnings.append(f"network.static_leases: «{entry}» — ожидается MAC,IP[,имя]; пропущено")
            continue
        if name and not _NAME_RE.fullmatch(name):
            warnings.append(f"network.static_leases: имя «{name}» не подходит — аренда без имени")
            name = ""
        if mac in seen_mac or address in seen_ip:
            warnings.append(f"network.static_leases: «{entry}» повторяет MAC или IP; пропущено")
            continue
        seen_mac.add(mac)
        seen_ip.add(address)
        leases.append(Lease(mac, address, name))
    return leases, warnings


def bypass_addresses(cfg: Config) -> tuple[list[str], list[str]]:
    """Адреса устройств, которые ходят мимо VPN. MAC переводится в IP через
    статические аренды: шлюз видит устройство по адресу, а адрес без аренды
    может достаться другому."""
    leases, _ = parse_leases(cfg)
    by_mac = {lease.mac: lease.ip for lease in leases}
    networks: list[ipaddress.IPv4Network] = []
    warnings: list[str] = []
    for entry in cfg.network.bypass_hosts:
        text = entry.strip()
        mac = normalize_mac(text)
        if mac is not None:
            if mac in by_mac:
                networks.append(ipaddress.IPv4Network(by_mac[mac]))
            else:
                warnings.append(
                    f"network.bypass_hosts: для {mac} нет статической аренды "
                    "(network.static_leases) — устройство пойдёт через VPN"
                )
            continue
        try:
            networks.append(ipaddress.IPv4Network(text, strict=False))
        except ValueError:
            warnings.append(f"network.bypass_hosts: «{entry}» — не IPv4-адрес и не MAC; пропущено")
    collapsed = ipaddress.collapse_addresses(networks)
    return [_plain(network) for network in collapsed], warnings


def _plain(network: ipaddress.IPv4Network) -> str:
    """Одиночный адрес — без «/32»: так его пишет и сам nft."""
    return str(network.network_address) if network.prefixlen == 32 else str(network)
