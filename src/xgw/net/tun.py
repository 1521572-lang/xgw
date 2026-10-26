"""TUN-интерфейс для capture.method = "tun".

Интерфейс создаёт XGW, а не Xray, и он **постоянный**: Xray при запуске подключается к
готовому интерфейсу, а при остановке оставляет его (состояние NO-CARRIER). Поэтому
маршрут помеченных пакетов в интерфейс не пропадает вместе с Xray — пока Xray не
работает, пакеты отбрасываются (fail-closed), а не уходят напрямую. Проверено на
Xray 26.3.27: inbound `tun` подключается к существующему интерфейсу и переживает
его перезапуски.

Адрес на интерфейсе — один IPv4 /32 из link-local диапазона (как Xray берёт по
умолчанию на macOS). Он нужен не для маршрутов — их это не создаёт, — а чтобы ядро не
отбрасывало ответы Xray: ответы приходят с интерфейса, которого нет в обратном маршруте
до их отправителя, и обратная проверка пути (rp_filter, на Ubuntu по умолчанию «мягкая»,
2) пропускает такой пакет, только если на интерфейсе есть IPv4-адрес. Проверено на
стенде: без адреса ядро считает `TcpExtIPReversePathFilter` и соединение не
устанавливается. Строгий rp_filter (1) ответы отбросил бы и с адресом. Ядро берёт
наибольшее из общего значения (conf.all) и значения интерфейса, поэтому XGW ставит самому
интерфейсу мягкую проверку (2): тогда она мягкая и при строгом conf.all (0.2.0; до того
интерфейсу ставился 0, и решало общее значение).
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

from . import sysctl
from .cmd import CommandError, Runner

MTU = 1500
ADDRESS = "169.254.10.1/32"
LOOSE = "2"  # rp_filter интерфейса: мягкая проверка обратного пути


def inbound_name(config: dict) -> str | None:
    """Имя интерфейса из inbound `tun` конфига Xray; None — такого inbound нет."""
    for inbound in config.get("inbounds") or []:
        if isinstance(inbound, dict) and inbound.get("protocol") == "tun":
            settings = inbound.get("settings")
            name = settings.get("name") if isinstance(settings, dict) else None
            if isinstance(name, str) and name:
                return name
    return None


def info(name: str, runner: Runner) -> dict | None:
    """Описание интерфейса из `ip -d -j link show`; None — такого интерфейса нет."""
    try:
        listing = runner(["ip", "-d", "-j", "link", "show", "dev", name])
    except CommandError as exc:
        text = str(exc)
        if "does not exist" in text or "Cannot find device" in text:
            return None
        raise
    try:
        items = json.loads(listing or "[]")
    except json.JSONDecodeError as exc:
        raise CommandError(f"ip -j link show {name}: непонятный ответ ({exc})") from exc
    return items[0] if items and isinstance(items[0], dict) else None


def is_tun(item: dict) -> bool:
    linkinfo = item.get("linkinfo")
    return isinstance(linkinfo, dict) and linkinfo.get("info_kind") == "tun"


def present(name: str, runner: Runner) -> bool:
    """Интерфейс есть и это TUN."""
    item = info(name, runner)
    return item is not None and is_tun(item)


def ready(name: str, runner: Runner) -> bool:
    """Интерфейс поднят и на нём адрес XGW. Интерфейс, который создал сам Xray (например,
    после перезагрузки, раньше XGW), адреса не имеет — и ответы Xray ядро отбрасывает."""
    try:
        listing = runner(["ip", "-j", "addr", "show", "dev", name])
    except CommandError as exc:
        text = str(exc)
        if "does not exist" in text or "Cannot find device" in text:
            return False
        raise
    try:
        items = json.loads(listing or "[]")
    except json.JSONDecodeError as exc:
        raise CommandError(f"ip -j addr show {name}: непонятный ответ ({exc})") from exc
    item = items[0] if items and isinstance(items[0], dict) else None
    if item is None or "UP" not in (item.get("flags") or []):
        return False
    local, _, prefix = ADDRESS.partition("/")
    return any(
        isinstance(addr, dict) and addr.get("family") == "inet"
        and addr.get("local") == local and str(addr.get("prefixlen")) == prefix
        for addr in item.get("addr_info") or []
    )


def ensure(name: str, runner: Runner, proc_sys: Path = sysctl.PROC_SYS) -> bool:
    """Постоянный TUN-интерфейс есть и поднят. True — создан сейчас."""
    item = info(name, runner)
    created = item is None
    if item is not None and not is_tun(item):
        raise CommandError(f"интерфейс {name} уже есть и это не TUN — выберите capture.tun_name")
    if created:
        runner(["ip", "tuntap", "add", "dev", name, "mode", "tun"])
    runner(["ip", "link", "set", "dev", name, "mtu", str(MTU), "up"])
    runner(["ip", "addr", "replace", ADDRESS, "dev", name])
    with contextlib.suppress(OSError):  # каталога интерфейса нет в подставном /proc
        sysctl.write(f"net/ipv4/conf/{name}/rp_filter", LOOSE, proc_sys)
    return created


def remove(name: str, runner: Runner) -> None:
    """Убирает интерфейс XGW; чужой интерфейс с таким именем и отсутствующий не трогает."""
    item = info(name, runner)
    if item is not None and is_tun(item):
        runner(["ip", "link", "del", "dev", name])
