"""DHCP на LAN-интерфейсе (раздел 6.4): свой экземпляр dnsmasq — служба xgw-dhcp.

DNS в dnsmasq выключен (`port=0`): запросы устройств перехватывает и обслуживает
Xray, а с systemd-resolved на 127.0.0.53 не возникает конфликта.

Конфиг — /etc/xgw/dnsmasq.conf, и служба читает только его (--conf-file). До 0.1.4 XGW
клал файл в /etc/dnsmasq.d, который читает штатная служба dnsmasq.service, — и этот
каталог делят все пакеты: пакет ubuntu-fan (ставится вместе с docker.io) кладёт туда
bind-interfaces, с которым наш bind-dynamic несовместим, и dnsmasq после перезагрузки не
запускался вовсе (`cannot set --bind-interfaces and --bind-dynamic`). Программа — из
пакета dnsmasq-base (без своей службы; он же нужен NetworkManager). Старая установка
переводится сама: файл из /etc/dnsmasq.d убирается, штатная служба возвращается в
состояние до XGW (restore_system), аренды переезжают (migrate_leases).
"""

from __future__ import annotations

import ipaddress
import re
import shutil
from pathlib import Path

from ..config import Config
from ..paths import Paths, atomic_write_text
from . import cmd, lan

UNIT = "xgw-dhcp.service"  # своя служба DHCP (packaging/xgw-dhcp.service)
SYSTEM_UNIT = "dnsmasq.service"  # штатная служба пакета dnsmasq — её XGW больше не трогает
PACKAGE = "dnsmasq-base"  # программа /usr/sbin/dnsmasq без своей службы
LEASES = "/var/lib/xgw/dhcp.leases"
PIDFILE = "/run/xgw-dhcp/dnsmasq.pid"  # каталог создаёт служба (RuntimeDirectory)

_LEASE_TIME_RE = re.compile(r"\d+[smhdw]?|infinite")


def conf_path(paths: Paths) -> Path:
    return paths.etc / "dnsmasq.conf"


def legacy_conf_path(paths: Paths) -> Path:
    """Где конфиг лежал до 0.1.4 — в каталоге штатной службы dnsmasq."""
    return paths.root / "etc" / "dnsmasq.d" / "xgw.conf"


def leases_path(paths: Paths) -> Path:
    return paths.var / "dhcp.leases"


def legacy_leases_path(paths: Paths) -> Path:
    """Файл аренд штатной службы dnsmasq в Debian и Ubuntu (до 0.1.4)."""
    return paths.root / "var" / "lib" / "misc" / "dnsmasq.leases"


def write_conf(cfg: Config, paths: Paths) -> tuple[bool, list[str]]:
    """Записывает dnsmasq.conf, если он изменился. Возвращает (изменился ли, предупреждения).

    Пустой конфиг (LAN не настроен или dhcp_range не разобрать) файл убирает:
    иначе dnsmasq продолжал бы раздавать адреса по старым настройкам.
    """
    text, warnings = render(cfg, leasefile=str(leases_path(paths)))
    path = conf_path(paths)
    try:
        current = path.read_text(encoding="utf-8")
    except OSError:
        current = ""
    if text == current:
        return False, warnings
    if text:
        atomic_write_text(path, text, mode=0o644)
    else:
        path.unlink(missing_ok=True)
    return True, warnings


def migrate_leases(paths: Paths) -> bool:
    """Аренды штатной службы — в файл своей: устройства сохранят свои адреса. True —
    перенесены."""
    source, target = legacy_leases_path(paths), leases_path(paths)
    if target.exists() or not source.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return True


def restore_system(paths: Paths, record: dict | None, runner: cmd.Runner) -> str:
    """Убирает конфиг XGW из /etc/dnsmasq.d и возвращает штатную службу dnsmasq.service
    в состояние до XGW (record — запись журнала установки до 0.1.4). Что сделано."""
    conf = legacy_conf_path(paths)
    conf.unlink(missing_ok=True)
    if record is None:
        return f"{conf} удалён"
    if record.get("active"):
        # Работала и до XGW — пусть работает дальше, уже без нашего файла.
        runner(["systemctl", "restart", SYSTEM_UNIT], timeout=60.0, check=False)
        return f"{SYSTEM_UNIT} перезапущен без настроек XGW"
    runner(["systemctl", "stop", SYSTEM_UNIT], timeout=60.0, check=False)
    if not record.get("enabled"):
        runner(["systemctl", "disable", SYSTEM_UNIT], timeout=60.0, check=False)
    return f"{SYSTEM_UNIT} остановлен, его конфиг XGW удалён"


def read_leases(paths: Paths) -> list[dict]:
    """Устройства из аренд dnsmasq: «срок MAC IP имя идентификатор» в каждой строке."""
    try:
        text = leases_path(paths).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    devices: list[dict] = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 4 or not fields[0].isdigit() or lan.normalize_mac(fields[1]) is None:
            continue  # строка «duid …» и всё, что не аренда IPv4
        devices.append(
            {
                "expires": int(fields[0]),
                "mac": fields[1].lower(),
                "ip": fields[2],
                "name": "" if fields[3] == "*" else fields[3],
            }
        )
    return sorted(devices, key=_ip_order)


def _ip_order(device: dict) -> int:
    try:
        return int(ipaddress.IPv4Address(device["ip"]))
    except ValueError:
        return 0


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


def render(cfg: Config, *, leasefile: str = LEASES) -> tuple[str, list[str]]:
    """Текст dnsmasq.conf и предупреждения. Пусто — LAN не настроен, dnsmasq не нужен."""
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
        "# Его читает только служба xgw-dhcp (dnsmasq --conf-file): файлы /etc/dnsmasq.d",
        "# и /etc/dnsmasq.conf к ней не относятся.",
        "# DNS выключен: запросы устройств перехватывает и обслуживает Xray.",
        "port=0",
        "user=dnsmasq",  # пользователь из пакета dnsmasq-base
        f"pid-file={PIDFILE}",
        f"dhcp-leasefile={leasefile}",
        f"interface={lan_if}",
        # Не bind-interfaces: с ним dnsmasq завершается («unknown interface»), если
        # при старте у карты ещё нет адреса — роутер выключен или кабель не вставлен.
        "bind-dynamic",
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
