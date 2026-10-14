"""Данные о LAN из конфига: интерфейс, адрес шлюза, статические аренды, обход.

Всё, что попадает в текст правил nftables и конфиг dnsmasq, проверяется здесь:
имя интерфейса, адреса и MAC из config.toml не должны уметь испортить правила.
"""

from __future__ import annotations

import fnmatch
import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import Path

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


def container_links(patterns: tuple[str, ...], sys_net: Path = Path("/sys/class/net")) -> list[str]:
    """Интерфейсы контейнеров, которые уже есть в системе (имена по шаблонам вида
    «docker0», «br-*»). Пусто — Docker не установлен или ещё не создал мост."""
    try:
        names = sorted(item.name for item in sys_net.iterdir())
    except OSError:
        return []  # не Linux либо /sys недоступен
    return [name for name in names if any(fnmatch.fnmatchcase(name, p) for p in patterns)]


def valid_hostname(name: str) -> bool:
    """Имя, которое можно записать в dhcp-host."""
    return bool(_NAME_RE.fullmatch(name))


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


@dataclass(frozen=True)
class Conflict:
    """С чем пересекается подсеть LAN: интерфейс и его сеть (или адрес шлюза)."""

    interface: str
    subnet: str
    gateway: bool = False  # это адрес шлюза по умолчанию, а не сеть интерфейса


def occupied_networks(
    runner: cmd.Runner = cmd.run, *, skip: tuple[str, ...] = ()
) -> list[tuple[str, ipaddress.IPv4Network, bool]]:
    """Сети IPv4, которые уже заняты на машине: адреса интерфейсов, маршруты через них
    и шлюз по умолчанию. skip — интерфейсы, которые не в счёт (сама карта LAN и lo).

    Команды `ip` только читают состояние; если их нет или вывод не разобрать, список
    пуст — проверить нечем.
    """
    found: list[tuple[str, ipaddress.IPv4Network, bool]] = []

    def add(device: object, text: object, gateway: bool = False) -> None:
        if not isinstance(device, str) or not device or device == "lo" or device in skip:
            return
        try:
            network = ipaddress.IPv4Network(str(text), strict=False)
        except ValueError:
            return
        if network.is_loopback or network.is_link_local or network.prefixlen == 0:
            return
        if (device, network, gateway) not in found:
            found.append((device, network, gateway))

    try:
        links = json.loads(runner(["ip", "-j", "-4", "addr", "show"]) or "[]")
        routes = json.loads(runner(["ip", "-j", "-4", "route", "show"]) or "[]")
    except (cmd.CommandError, json.JSONDecodeError):
        return []
    for link in links if isinstance(links, list) else []:
        if not isinstance(link, dict):
            continue
        for address in link.get("addr_info") or []:
            if isinstance(address, dict) and address.get("family", "inet") == "inet":
                add(link.get("ifname"), f"{address.get('local')}/{address.get('prefixlen')}")
    for route in routes if isinstance(routes, list) else []:
        if not isinstance(route, dict):
            continue
        if route.get("dst") == "default":
            if route.get("gateway"):
                add(route.get("dev"), f"{route['gateway']}/32", gateway=True)
        elif route.get("type", "unicast") == "unicast":
            add(route.get("dev"), route.get("dst"))
    return found


def subnet_conflicts(cfg: Config, runner: cmd.Runner = cmd.run) -> list[Conflict]:
    """С какими сетями машины пересекается network.lan_address.

    Карта LAN с адресом из сети провайдера — это два интерфейса в одной подсети и, как
    правило, адрес, уже занятый роутером провайдера: маршрут к нему становится
    неоднозначным, и интернет пропадает и у шлюза, и у устройств за ним.
    """
    lan_if = lan_interface(cfg)
    address = gateway(cfg)
    if not lan_if or address is None:
        return []
    own = address.network
    conflicts: list[Conflict] = []
    for device, network, is_gateway in occupied_networks(runner, skip=(lan_if,)):
        if not own.overlaps(network):
            continue
        # Адрес шлюза внутри уже названной сети того же интерфейса — тот же конфликт.
        if is_gateway and any(item.interface == device and not item.gateway for item in conflicts):
            continue
        conflicts.append(Conflict(device, str(network), is_gateway))
    return conflicts


def free_lan_address(cfg: Config, runner: cmd.Runner = cmd.run) -> str:
    """Свободная подсеть для совета: первая из 192.168.60–250.0/24, не пересекающаяся ни
    с одной сетью машины. Пусто — такой не нашлось."""
    lan_if = lan_interface(cfg)
    taken = [network for _dev, network, _gw in occupied_networks(runner, skip=(lan_if,))]
    for third in range(60, 251, 10):
        candidate = ipaddress.IPv4Network(f"192.168.{third}.0/24")
        if not any(candidate.overlaps(network) for network in taken):
            return f"192.168.{third}.1/24"
    return ""


def conflict_text(cfg: Config, conflicts: list[Conflict], config_file: object,
                  suggestion: str = "") -> str:
    """Сообщение о конфликте подсетей — одно и то же в `xgw diag` и в установке."""
    first = conflicts[0]
    what = (
        f"со шлюзом по умолчанию на интерфейсе {first.interface} ({first.subnet})"
        if first.gateway else f"с интерфейсом {first.interface} ({first.subnet})"
    )
    more = "" if len(conflicts) == 1 else " и ещё с " + ", ".join(
        f"{item.interface} ({item.subnet})" for item in conflicts[1:]
    )
    example = f" (например, на {suggestion})" if suggestion else ""
    return (
        f"Конфликт подсетей: lan_address ({cfg.network.lan_address}) пересекается {what}{more}. "
        f"Измените lan_address и dhcp_range в {config_file}{example}."
    )


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
