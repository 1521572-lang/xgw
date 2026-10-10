"""Конфиг dnsmasq: только DHCP на LAN-интерфейсе (раздел 6.4).

DNS в dnsmasq выключен (`port=0`): запросы устройств перехватывает и обслуживает
Xray, а с systemd-resolved на 127.0.0.53 не возникает конфликта. Файл —
/etc/dnsmasq.d/xgw.conf; ставит его и перезапускает службу установка (этап 4).
"""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path

from ..config import Config
from ..paths import Paths
from . import lan

_LEASE_TIME_RE = re.compile(r"\d+[smhdw]?|infinite")


def conf_path(paths: Paths) -> Path:
    return paths.root / "etc" / "dnsmasq.d" / "xgw.conf"


def _range(cfg: Config, network: ipaddress.IPv4Network) -> tuple[str, str, str] | None:
    """dhcp_range «начало,конец[,срок]» → (начало, конец, срок); None — не разобрать."""
    parts = [part.strip() for part in cfg.network.dhcp_range.split(",")]
    if len(parts) not in (2, 3):
        return None
    try:
        start, end = ipaddress.IPv4Address(parts[0]), ipaddress.IPv4Address(parts[1])
    except ValueError:
        return None
    lease = parts[2] if len(parts) == 3 else "12h"
    if start not in network or end not in network or start > end:
        return None
    if not _LEASE_TIME_RE.fullmatch(lease):
        return None
    return str(start), str(end), lease


def render(cfg: Config) -> tuple[str, list[str]]:
    """Текст xgw.conf и предупреждения. Пусто — LAN не настроен, dnsmasq не нужен."""
    lan_if = lan.lan_interface(cfg)
    if not lan_if:
        return "", []
    warnings: list[str] = []
    gateway = lan.gateway(cfg)
    if gateway is None:
        return "", [f"network.lan_address={cfg.network.lan_address}: ожидается адрес/префикс"]
    dhcp = _range(cfg, gateway.network)
    if dhcp is None:
        return "", [
            f"network.dhcp_range={cfg.network.dhcp_range}: ожидается «начало,конец,срок» "
            f"внутри сети {gateway.network} — DHCP не настроен"
        ]
    start, end, lease = dhcp
    leases, lease_warnings = lan.parse_leases(cfg)
    warnings.extend(lease_warnings)
    for item in leases:
        if ipaddress.IPv4Address(item.ip) not in gateway.network:
            warnings.append(f"network.static_leases: {item.ip} вне сети {gateway.network}")

    lines = [
        "# Создано XGW — не редактируйте: файл перезаписывается.",
        "# DNS выключен: запросы устройств перехватывает и обслуживает Xray.",
        "port=0",
        f"interface={lan_if}",
        "bind-interfaces",
    ]
    router_mac = lan.normalize_mac(cfg.network.router_mac)
    if cfg.network.router_mode == "router" and router_mac:
        # Кабель в WAN-порту роутера: адрес получает только он.
        lines.append(f"dhcp-range={start},static,{lease}")
        lines.append(f"dhcp-host={router_mac},{start},router")
    else:
        if cfg.network.router_mode == "router":
            warnings.append(
                'network.router_mode = "router", но router_mac не задан — '
                "адреса выдаются всем устройствам"
            )
        lines.append(f"dhcp-range={start},{end},{lease}")
    lines += [
        f"dhcp-option=option:router,{gateway.ip}",
        f"dhcp-option=option:dns-server,{gateway.ip}",
        "dhcp-authoritative",
    ]
    for item in leases:
        suffix = f",{item.name}" if item.name else ""
        lines.append(f"dhcp-host={item.mac},{item.ip}{suffix}")
    return "\n".join(lines) + "\n", warnings
