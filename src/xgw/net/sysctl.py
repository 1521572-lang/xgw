"""sysctl шлюза (раздел 6.2): форвардинг IPv4 включён, IPv6 — выключен.

Форвардинг нужен только для устройств в обход VPN, ICMP и режима «перехват
снят»: трафик через TPROXY доставляется локально. Значения меняются записью в
/proc/sys; постоянный файл /etc/sysctl.d/90-xgw.conf ставит `xgw install`.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from ..paths import Paths, atomic_write_text

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


def ipv6_usable(root: Path = PROC_SYS) -> bool:
    """IPv6 в ядре работает: при ipv6.disable=1 нет каталога net/ipv6, а при
    disable_ipv6=1 нет ::1 на lo — Xray не открыл бы на нём TPROXY-inbound."""
    if not (root / "net" / "ipv6").is_dir():
        return False
    return all(
        read(f"net/ipv6/conf/{where}/disable_ipv6", root) != "1" for where in ("all", "lo")
    )


def install(paths: Paths, root: Path = PROC_SYS) -> dict[str, str]:
    """Ставит 90-xgw.conf и применяет значения. Возвращает прежние — для журнала."""
    previous: dict[str, str] = {}
    for name in SETTINGS:
        value = read(name.replace(".", "/"), root)
        if value is not None:
            previous[name] = value
    atomic_write_text(paths.sysctl_file, file_text(), mode=0o644)
    for name, value in SETTINGS.items():
        # Ключа может не быть: IPv6 выключен в ядре целиком.
        with contextlib.suppress(OSError):
            write(name.replace(".", "/"), value, root)
    return previous


def restore(previous: dict[str, str], paths: Paths, root: Path = PROC_SYS) -> None:
    """Убирает 90-xgw.conf и возвращает значения, которые были до установки."""
    paths.sysctl_file.unlink(missing_ok=True)
    for name, value in previous.items():
        if name in SETTINGS:
            with contextlib.suppress(OSError):
                write(name.replace(".", "/"), value, root)
