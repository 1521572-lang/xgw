"""sysctl шлюза (раздел 6.2): форвардинг IPv4 включён, IPv6 — выключен.

Форвардинг нужен только для устройств в обход VPN, ICMP и режима «перехват
снят»: трафик через TPROXY доставляется локально. Значения меняются записью в
/proc/sys; постоянный файл /etc/sysctl.d/90-xgw.conf ставит `xgw install`.

Там же — disable_ipv6 карты WAN, когда IPv6 на ней нельзя выключить профилем
NetworkManager (профиль описан в netplan, см. nm.netplan_defined). Имя карты может
содержать точку (VLAN), поэтому такой ключ записан через «/» — sysctl.d это понимает.
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path

from ..paths import Paths, atomic_write_text

PROC_SYS = Path("/proc/sys")
IP_FORWARD = "net/ipv4/ip_forward"
# Алгоритм управления перегрузкой TCP (network.tcp_bbr): ставит и возвращает перехват
# (capture.Capture._congestion) — как форвардинг, по записи в /proc/sys.
TCP_CONGESTION = "net/ipv4/tcp_congestion_control"
# Проверка источника с учётом метки пакета. XGW её не ставит (её ставит, например,
# tailscaled): перехват LAN работает при любом значении (iprule.py, маршрут throw), а
# проверка пути LAN называет её в причине сбоя.
SRC_VALID_MARK = "net/ipv4/conf/all/src_valid_mark"
SETTINGS = {"net.ipv4.ip_forward": "1", "net.ipv6.conf.all.forwarding": "0"}
_WAN_IPV6 = re.compile(r"net/ipv6/conf/[A-Za-z0-9_.@-]{1,15}/disable_ipv6")


def wan_ipv6_key(device: str) -> str:
    return f"net/ipv6/conf/{device}/disable_ipv6"


def wanted(*, forwarding: bool, wan_ipv6_off: str = "") -> dict[str, str]:
    """Ключи 90-xgw.conf: форвардинг — когда есть сеть LAN; disable_ipv6 — для карты
    WAN, если IPv6 на ней выключается здесь, а не в профиле NetworkManager."""
    settings = dict(SETTINGS) if forwarding else {}
    if wan_ipv6_off:
        settings[wan_ipv6_key(wan_ipv6_off)] = "1"
    return settings


def _ours(name: str) -> bool:
    """Ключ, который XGW ставит сам: только такие возвращаются по журналу."""
    return name in SETTINGS or bool(_WAN_IPV6.fullmatch(name))


def _path(name: str) -> str:
    return name if "/" in name else name.replace(".", "/")


def file_text(settings: dict[str, str] | None = None) -> str:
    """Содержимое /etc/sysctl.d/90-xgw.conf."""
    settings = SETTINGS if settings is None else settings
    lines = ["# Создано XGW: форвардинг для устройств в обход VPN и ICMP; IPv6 на WAN."]
    lines.extend(f"{key} = {value}" for key, value in settings.items())
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


def install(
    paths: Paths, root: Path = PROC_SYS, settings: dict[str, str] | None = None
) -> dict[str, str]:
    """Ставит 90-xgw.conf (settings — по умолчанию SETTINGS) и применяет значения.
    Возвращает прежние — для журнала. Пустой settings — файл не нужен и убирается."""
    settings = SETTINGS if settings is None else settings
    previous: dict[str, str] = {}
    for name in settings:
        value = read(_path(name), root)
        if value is not None:
            previous[name] = value
    if settings:
        atomic_write_text(paths.sysctl_file, file_text(settings), mode=0o644)
    else:
        paths.sysctl_file.unlink(missing_ok=True)
    for name, value in settings.items():
        # Ключа может не быть: IPv6 выключен в ядре целиком.
        with contextlib.suppress(OSError):
            write(_path(name), value, root)
    return previous


def put_back(previous: dict[str, str], names, root: Path = PROC_SYS) -> None:
    """Возвращает прежние значения перечисленных ключей (файл не трогает)."""
    for name in names:
        if _ours(name) and name in previous:
            with contextlib.suppress(OSError):  # карты уже нет — возвращать некуда
                write(_path(name), previous[name], root)


def restore(previous: dict[str, str], paths: Paths, root: Path = PROC_SYS) -> None:
    """Убирает 90-xgw.conf и возвращает значения, которые были до установки."""
    paths.sysctl_file.unlink(missing_ok=True)
    put_back(previous, list(previous), root)
