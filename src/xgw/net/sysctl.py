"""sysctl шлюза (раздел 6.2): форвардинг IPv4 включён, IPv6 — выключен.

Форвардинг нужен только для устройств в обход VPN, ICMP и режима «перехват
снят»: трафик через TPROXY доставляется локально. Значения меняются записью в
/proc/sys; постоянный файл /etc/sysctl.d/90-xgw.conf ставит установка (этап 4).
"""

from __future__ import annotations

from pathlib import Path

PROC_SYS = Path("/proc/sys")
IP_FORWARD = "net/ipv4/ip_forward"
SETTINGS = {"net.ipv4.ip_forward": "1", "net.ipv6.conf.all.forwarding": "0"}


def file_text() -> str:
    """Содержимое /etc/sysctl.d/90-xgw.conf."""
    lines = ["# Создано XGW: форвардинг для устройств в обход VPN и ICMP."]
    lines.extend(f"{key} = {value}" for key, value in SETTINGS.items())
    return "\n".join(lines) + "\n"


def read(key: str, root: Path = PROC_SYS) -> str | None:
    try:
        return (root / key).read_text(encoding="ascii").strip()
    except OSError:
        return None


def write(key: str, value: str, root: Path = PROC_SYS) -> None:
    (root / key).write_text(f"{value}\n", encoding="ascii")
