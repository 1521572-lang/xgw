"""Подписки, ссылки, устройства и Tailscale, добавленные из панели: /etc/xgw/panel.json.

config.toml пишет человек — с комментариями и в своём порядке; программа его не
переписывает. То, что добавлено кнопкой в панели, лежит отдельным файлом рядом
(права 0600: в адресах подписок токены) и при чтении конфига дополняет его:
подписки, ссылки и устройства из обоих файлов складываются.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar
from urllib.parse import urlsplit

from . import priority as priority_levels
from .parsers.common import parse_links_text
from .paths import LockTimeout, atomic_write_json, file_lock

T = TypeVar("T")

FILE_NAME = "panel.json"
LOCK_TIMEOUT = 10.0  # правка panel.json — доли секунды; дольше — что-то зависло
MAX_SUBSCRIPTIONS = 16
MAX_LINKS = 200
MAX_SERVERS = 2000  # сколько отключённых и убранных серверов помнить
MAX_DEVICES = 256
MAX_URL = 2048
MAX_NAME = 40
DEFAULT_REFRESH = 60
SERVER_MODES = ("enabled", "disabled", "removed")
# Ядро, закреплённое за сервером вручную (`xgw core`, переключатель в панели); «auto» не хранится.
CORE_PINS = ("xray", "sing-box")
_FINGERPRINT_RE = re.compile(r"[0-9a-f]{8}")
_MAC_RE = re.compile(r"([0-9a-f]{2}:){5}[0-9a-f]{2}")
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}")
# Имя шлюза в tailnet (Self.DNSName без точки): «gw.tail1234.ts.net».
_TS_LABEL = r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
_TS_NAME_RE = re.compile(rf"(?=.{{1,253}}$){_TS_LABEL}(\.{_TS_LABEL})+")
TS_ROUTES = ("direct", "vpn")
_TAILNET = ipaddress.IPv4Network("100.64.0.0/10")


class ManagedError(Exception):
    """Добавить или убрать не удалось; текст — для пользователя панели."""


def path_for(config_path: Path) -> Path:
    return Path(config_path).with_name(FILE_NAME)


def lock_path(path: Path) -> Path:
    """Файл блокировки рядом с panel.json. Сам panel.json для неё не годится: атомарная
    запись подменяет файл, и блокировка осталась бы на прежнем."""
    path = Path(path)
    return path.with_name(f".{path.name}.lock")


def _update(path: Path, change: Callable[[dict], T]) -> T:
    """load → change → save под блокировкой. У panel.json несколько писателей: панель
    (поток демона) и команды `xgw priority`, `xgw core`; без блокировки правка, сделанная
    между чтением и записью другого писателя, терялась.

    change правит data на месте и возвращает итог; ложный итог — ничего не изменилось,
    файл не переписывается."""
    path = Path(path)
    try:
        with file_lock(lock_path(path), timeout=LOCK_TIMEOUT, poll=0.02, mode=0o600):
            data, error = load(path)
            if error:
                raise ManagedError(error)
            result = change(data)
            if result:
                save(path, data)
            return result
    except LockTimeout as exc:
        raise ManagedError(f"{exc}: настройки меняет другой процесс XGW — повторите") from exc


def load(path: Path) -> tuple[dict, str]:
    """Содержимое panel.json и текст ошибки (пустой, если файла нет или он цел).

    Возвращается только проверенное: подписки с именем и адресом, ссылки — строки,
    отключённые и убранные серверы — отпечатки, устройства мимо VPN — MAC и IPv4,
    приоритеты — отпечаток → "high" или "low" (средний не хранится).
    """
    empty: dict = {
        "subscriptions": [], "links": [], "disabled": [], "removed": [], "devices": [],
        "routes": [], "priority": {}, "sticky": None, "kernel_direct": None,
        "kernel_devices": [], "core": {},
        "tailscale": {"serve": "", "route": None, "funnel": "", "direct": []},
        "free_pool_mode": None, "free_pool_links": [],
    }
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty, ""
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return empty, f"{path} не читается ({exc}) — добавленное из панели не загружено"
    if not isinstance(raw, dict):
        return empty, f"{path}: ожидается объект JSON — добавленное из панели не загружено"
    subscriptions = []
    for item in raw.get("subscriptions") or []:
        if not isinstance(item, dict):
            continue
        name, url = item.get("name"), item.get("url")
        if not isinstance(name, str) or not isinstance(url, str) or not name or not url:
            continue
        agent, refresh = item.get("user_agent"), item.get("refresh_minutes")
        headers = item.get("headers")
        if not isinstance(headers, dict):
            headers = {}
        else:
            headers = {
                str(k): str(v) for k, v in headers.items()
                if isinstance(k, (str, int, float)) and isinstance(v, (str, int, float))
            }
        subscriptions.append({
            "name": name,
            "url": url,
            "user_agent": agent if isinstance(agent, str) else "",
            "headers": headers,
            "refresh_minutes": refresh
            if isinstance(refresh, int) and not isinstance(refresh, bool) and refresh > 0
            else DEFAULT_REFRESH,
        })
    links = [link for link in raw.get("links") or [] if isinstance(link, str) and link]
    removed = _fingerprints(raw.get("removed"))
    disabled = [item for item in _fingerprints(raw.get("disabled")) if item not in removed]
    return {
        "subscriptions": subscriptions, "links": links, "disabled": disabled, "removed": removed,
        "devices": _devices(raw.get("devices")),
        "routes": _routes(raw.get("routes")),
        "priority": _priority(raw.get("priority")),
        "core": _core(raw.get("core")),
        # Основной сервер (speed.sticky) включён или выключен переключателем в панели.
        "sticky": raw["sticky"] if isinstance(raw.get("sticky"), bool) else None,
        # Российские адреса мимо Xray: у самой машины и контейнеров (routing.kernel_direct) и
        # у устройств сети ({mac, ip, name}, адрес закрепляется арендой) — переключатели в панели.
        "kernel_direct": raw["kernel_direct"] if isinstance(raw.get("kernel_direct"), bool)
        else None,
        "kernel_devices": _devices(raw.get("kernel_devices")),
        "tailscale": _tailscale(raw.get("tailscale")),
        # Бесплатный пул (docs/FREEPOOL-PLAN.md): режим из панели и выданные источником ссылки
        # (VPNJantit выдаёт учётку формой сайта — заказчик вставляет ссылку в панель).
        "free_pool_mode": raw["free_pool_mode"]
        if raw.get("free_pool_mode") in FREE_POOL_MODES else None,
        "free_pool_links": _pool_links(raw.get("free_pool_links")),
    }, ""


FREE_POOL_MODES = ("off", "observe", "on")
POOL_LINK_SCHEMES = ("vless://", "trojan://", "ss://", "vmess://")
MAX_POOL_LINKS = 50


def _pool_links(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    links = [item.strip() for item in value if isinstance(item, str)]
    links = [item for item in links if item.startswith(POOL_LINK_SCHEMES) and len(item) < 4096]
    return list(dict.fromkeys(links))[:MAX_POOL_LINKS]


def set_free_pool_mode(path: Path, mode: str | None) -> bool:
    """Режим бесплатного пула из панели (None — как в config.toml); True — изменилось."""
    if mode is not None and mode not in FREE_POOL_MODES:
        raise ManagedError("ожидается off, observe или on")

    def change(data: dict) -> bool:
        if data["free_pool_mode"] == mode:
            return False
        data["free_pool_mode"] = mode
        return True

    return _update(path, change)


def add_pool_links(path: Path, text: str) -> int:
    """Добавить выданные источником ссылки (по одной в строке); сколько добавлено."""
    candidates = _pool_links([line for line in str(text).splitlines() if line.strip()])

    def change(data: dict) -> int:
        before = list(data["free_pool_links"])
        merged = _pool_links([*before, *candidates])
        data["free_pool_links"] = merged
        return len(merged) - len(before)

    return _update(path, change)


def remove_pool_link(path: Path, index: int) -> bool:
    def change(data: dict) -> bool:
        links = list(data["free_pool_links"])
        if not 0 <= index < len(links):
            return False
        del links[index]
        data["free_pool_links"] = links
        return True

    return _update(path, change)


def _tailscale(value: object) -> dict:
    """Tailscale из панели: serve — имя шлюза в tailnet, для которого XGW включил Serve
    (панель по tailnet; пусто — не включал); route — маршрут tailscaled, None — как в
    config.toml; funnel — имя, для которого XGW включил Funnel (API приложения); direct —
    устройства tailnet, что выходят в интернет через шлюз напрямую, мимо Xray ({ip, name})."""
    serve, route, funnel = "", None, ""
    direct = _tailnet_devices(value.get("direct") if isinstance(value, dict) else None)
    if isinstance(value, dict):
        name, way, public = value.get("serve"), value.get("route"), value.get("funnel")
        if isinstance(name, str) and _TS_NAME_RE.fullmatch(name):
            serve = name
        if way in TS_ROUTES:
            route = way
        if isinstance(public, str) and _TS_NAME_RE.fullmatch(public):
            funnel = public
    return {"serve": serve, "route": route, "funnel": funnel, "direct": direct}


def tailnet_address(text: object) -> str | None:
    """Адрес IPv4 устройства tailnet (100.64.0.0/10) или None."""
    try:
        address = ipaddress.IPv4Address(str(text).strip())
    except ValueError:
        return None
    return str(address) if address in _TAILNET else None


def _tailnet_devices(value: object) -> list[dict]:
    result: list[dict] = []
    for item in value if isinstance(value, list) else ():
        if not isinstance(item, dict):
            continue
        address = tailnet_address(item.get("ip"))
        name = item.get("name")
        if address and all(known["ip"] != address for known in result):
            result.append({"ip": address, "name": name[:63] if isinstance(name, str) else ""})
    return result[:MAX_DEVICES]


def set_tailscale_direct(path: Path, ip: str, name: str, *, direct: bool) -> bool:
    """Устройство tailnet выходит через шлюз напрямую (direct) или снова через Xray."""
    address = tailnet_address(ip)
    if address is None:
        raise ManagedError("ожидается адрес устройства tailnet 100.64.0.0/10")

    def change(data: dict) -> bool:
        listed = [item for item in data["tailscale"]["direct"] if item["ip"] != address]
        if direct:
            listed.append({"ip": address, "name": name[:63]})
        if listed == data["tailscale"]["direct"]:
            return False
        data["tailscale"] = {**data["tailscale"], "direct": listed}
        return True

    return _update(path, change)


def replace_tailscale_direct(path: Path, devices: list[dict]) -> None:
    """Вернуть прежний список (сеть не приняла изменение)."""

    def change(data: dict) -> bool:
        data["tailscale"] = {**data["tailscale"], "direct": _tailnet_devices(devices)}
        return True

    _update(path, change)


def _priority(value: object) -> dict[str, str]:
    result: dict[str, str] = {}
    for fingerprint, level in (value.items() if isinstance(value, dict) else ()):
        if (
            isinstance(fingerprint, str) and _FINGERPRINT_RE.fullmatch(fingerprint)
            and level in priority_levels.LEVELS and level != priority_levels.DEFAULT
        ):
            result[fingerprint] = level
    return dict(list(result.items())[-MAX_SERVERS:])


def _core(value: object) -> dict[str, str]:
    result: dict[str, str] = {}
    for fingerprint, core in (value.items() if isinstance(value, dict) else ()):
        if (
            isinstance(fingerprint, str) and _FINGERPRINT_RE.fullmatch(fingerprint)
            and core in CORE_PINS
        ):
            result[fingerprint] = core
    return dict(list(result.items())[-MAX_SERVERS:])


def _fingerprints(value: object) -> list[str]:
    result: list[str] = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, str) and _FINGERPRINT_RE.fullmatch(item) and item not in result:
            result.append(item)
    return result


def normalize_mac(text: object) -> str | None:
    if not isinstance(text, str):
        return None
    mac = text.strip().lower().replace("-", ":")
    return mac if _MAC_RE.fullmatch(mac) else None


def _devices(value: object) -> list[dict]:
    """Устройства, которые ходят мимо VPN: {"mac", "ip", "name"}; повторы отбрасываются."""
    result: list[dict] = []
    seen_mac: set[str] = set()
    seen_ip: set[str] = set()
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        mac, address, name = normalize_mac(item.get("mac")), item.get("ip"), item.get("name")
        try:
            ip = str(ipaddress.IPv4Address(address)) if isinstance(address, str) else ""
        except ValueError:
            ip = ""
        if mac is None or not ip or mac in seen_mac or ip in seen_ip:
            continue
        seen_mac.add(mac)
        seen_ip.add(ip)
        result.append({
            "mac": mac, "ip": ip,
            "name": name if isinstance(name, str) and _NAME_RE.fullmatch(name) else "",
        })
    return result[:MAX_DEVICES]


def set_device(path: Path, mac: str, ip: str, name: str = "", *, bypass: bool) -> bool:
    """Ставит устройство «мимо VPN» (bypass) либо возвращает его в VPN; True — что-то
    изменилось. Адрес запоминается: шлюз узнаёт устройство по адресу, поэтому запись
    превращается в статическую аренду DHCP — иначе адрес достался бы другому."""
    mac_ok = normalize_mac(mac)
    if mac_ok is None:
        raise ManagedError("неверный MAC устройства")

    def change(data: dict) -> bool:
        devices = [item for item in data["devices"] if item["mac"] != mac_ok]
        if bypass:
            if any(item["mac"] == mac_ok for item in data["routes"]):
                raise ManagedError("у устройства выбран свой сервер — сначала поставьте «авто»")
            try:
                address = str(ipaddress.IPv4Address(ip))
            except ValueError as exc:
                raise ManagedError("неверный адрес устройства") from exc
            if any(item["ip"] == address for item in devices):
                raise ManagedError("этот адрес уже закреплён за другим устройством")
            if len(devices) >= MAX_DEVICES:
                raise ManagedError(f"устройств мимо VPN уже {MAX_DEVICES} — больше нельзя")
            clean = name if _NAME_RE.fullmatch(name) else ""
            devices.append({"mac": mac_ok, "ip": address, "name": clean})
        if devices == data["devices"]:
            return False
        data["devices"] = devices
        return True

    return _update(path, change)


def replace_devices(
    path: Path, devices: list[dict], routes: list[dict] | None = None,
    kernel: list[dict] | None = None,
) -> None:
    """Возвращает прежние списки устройств (мимо VPN, со своим сервером и с российскими
    адресами мимо Xray) — откат, если сеть изменение не приняла."""

    def change(data: dict) -> bool:
        data["devices"] = _devices(devices)
        if routes is not None:
            data["routes"] = _routes(routes)
        if kernel is not None:
            data["kernel_devices"] = _devices(kernel)
        return True

    _update(path, change)


def set_kernel_device(path: Path, mac: str, ip: str, name: str = "", *, on: bool) -> bool:
    """Российские адреса устройства — ядром мимо Xray (on) либо снова через Xray; True —
    что-то изменилось. Правило ядра узнаёт устройство по адресу: он закрепляется арендой."""
    mac_ok = normalize_mac(mac)
    if mac_ok is None:
        raise ManagedError("неверный MAC устройства")

    def change(data: dict) -> bool:
        kernel = [item for item in data["kernel_devices"] if item["mac"] != mac_ok]
        if on:
            try:
                address = str(ipaddress.IPv4Address(ip))
            except ValueError as exc:
                raise ManagedError("неверный адрес устройства") from exc
            others = [*kernel, *data["devices"], *data["routes"]]
            if any(item["ip"] == address and item["mac"] != mac_ok for item in others):
                raise ManagedError("этот адрес уже закреплён за другим устройством")
            if len(kernel) >= MAX_DEVICES:
                raise ManagedError(f"устройств с российскими адресами мимо Xray уже {MAX_DEVICES}")
            clean = name if _NAME_RE.fullmatch(name) else ""
            kernel.append({"mac": mac_ok, "ip": address, "name": clean})
        if kernel == data["kernel_devices"]:
            return False
        data["kernel_devices"] = kernel
        return True

    return _update(path, change)


def split_kernel_direct(path: Path, online: list[dict]) -> bool:
    """До разгрузки по устройствам переключатель «российские адреса мимо Xray» был один на
    всю сеть. Включённый в panel.json, он остаётся переключателем самой машины, а устройства,
    что сейчас в сети (online: {mac, ip, name}), получают свой — разгрузка, которую оставили
    включённой, не пропадает. Один раз: потом в panel.json есть kernel_devices. True —
    файл переписан."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(raw, dict) or "kernel_devices" in raw or raw.get("kernel_direct") is not True:
        return False

    def change(data: dict) -> bool:
        # Адрес, закреплённый за другим устройством, не берётся: аренды разошлись бы.
        taken = {item["ip"]: item["mac"] for item in [*data["devices"], *data["routes"]]}
        data["kernel_devices"] = _devices([
            item for item in online
            if taken.get(item.get("ip")) in (None, normalize_mac(item.get("mac")))
        ])
        return True

    return _update(path, change)


def _routes(value: object) -> list[dict]:
    """Устройства со своим сервером (Ф4): {"mac", "ip", "name", "server"} — server — отпечаток
    сервера; адрес закрепляется статической арендой, как у устройств мимо VPN."""
    servers: dict[str, str] = {}
    for entry in value if isinstance(value, list) else []:
        server = entry.get("server") if isinstance(entry, dict) else None
        mac = normalize_mac(entry.get("mac")) if isinstance(entry, dict) else None
        if mac and isinstance(server, str) and _FINGERPRINT_RE.fullmatch(server):
            servers.setdefault(mac, server)
    return [{**item, "server": servers[item["mac"]]} for item in _devices(value)
            if item["mac"] in servers]


def set_route(path: Path, mac: str, ip: str, name: str, server: str) -> bool:
    """Свой сервер устройства (отпечаток) либо «авто» (server пуст); True — что-то изменилось.
    Устройство мимо VPN своего сервера иметь не может: в Xray его трафик не попадает."""
    mac_ok = normalize_mac(mac)
    if mac_ok is None:
        raise ManagedError("неверный MAC устройства")
    if server and not _FINGERPRINT_RE.fullmatch(server):
        raise ManagedError("неверный сервер")

    def change(data: dict) -> bool:
        routes = [item for item in data["routes"] if item["mac"] != mac_ok]
        if server:
            if any(item["mac"] == mac_ok for item in data["devices"]):
                raise ManagedError("устройство идёт мимо VPN — сначала верните его в VPN")
            try:
                address = str(ipaddress.IPv4Address(ip))
            except ValueError as exc:
                raise ManagedError("неверный адрес устройства") from exc
            if any(item["ip"] == address for item in [*routes, *data["devices"]]):
                raise ManagedError("этот адрес уже закреплён за другим устройством")
            if len(routes) >= MAX_DEVICES:
                raise ManagedError(f"устройств со своим сервером уже {MAX_DEVICES} — больше нельзя")
            clean = name if _NAME_RE.fullmatch(name) else ""
            routes.append({"mac": mac_ok, "ip": address, "name": clean, "server": server})
        if routes == data["routes"]:
            return False
        data["routes"] = routes
        return True

    return _update(path, change)


def set_servers(path: Path, fingerprints: list[str], mode: str) -> bool:
    """Включает, отключает или убирает серверы; True — что-то изменилось.

    Сервер опознаётся по отпечатку (протокол, адрес, порт, ключ, транспорт):
    запись переживает обновление подписки и смену имени сервера. Если владелец
    подписки сменит адрес или ключ, это будет уже другой сервер.
    """
    if mode not in SERVER_MODES or not fingerprints or not all(
        isinstance(item, str) and _FINGERPRINT_RE.fullmatch(item) for item in fingerprints
    ):
        raise ManagedError("неизвестный сервер или действие")
    chosen = list(dict.fromkeys(fingerprints))

    def change(data: dict) -> bool:
        before = (set(data["disabled"]), set(data["removed"]))
        for key in ("disabled", "removed"):
            data[key] = [item for item in data[key] if item not in chosen]
        if mode != "enabled":
            # Самые старые записи вытесняются: серверы, которых давно нет в подписке.
            data[mode] = [*data[mode], *chosen][-MAX_SERVERS:]
        return (set(data["disabled"]), set(data["removed"])) != before

    return _update(path, change)


def set_priority(path: Path, fingerprints: list[str], level: str) -> bool:
    """Ставит серверам приоритет: high, medium или low; True — что-то изменилось.
    Средний — уровень по умолчанию, поэтому он не хранится: запись просто убирается."""
    if level not in priority_levels.LEVELS or not fingerprints or not all(
        isinstance(item, str) and _FINGERPRINT_RE.fullmatch(item) for item in fingerprints
    ):
        raise ManagedError("неизвестный сервер или уровень приоритета")

    def change(data: dict) -> bool:
        before = dict(data["priority"])
        levels = {key: value for key, value in before.items() if key not in fingerprints}
        if level != priority_levels.DEFAULT:
            levels.update(dict.fromkeys(fingerprints, level))
        if levels == before:
            return False
        # Самые старые записи вытесняются: серверы, которых давно нет в подписке.
        data["priority"] = dict(list(levels.items())[-MAX_SERVERS:])
        return True

    return _update(path, change)


def set_core(path: Path, fingerprints: list[str], core: str) -> bool:
    """Закрепляет за серверами ядро: xray, sing-box или auto (выбор шлюза — не хранится);
    True — что-то изменилось. Запись — по отпечатку, как у приоритета."""
    if (core != "auto" and core not in CORE_PINS) or not fingerprints or not all(
        isinstance(item, str) and _FINGERPRINT_RE.fullmatch(item) for item in fingerprints
    ):
        raise ManagedError("неизвестный сервер или ядро")

    def change(data: dict) -> bool:
        before = dict(data["core"])
        cores = {key: value for key, value in before.items() if key not in fingerprints}
        if core != "auto":
            cores.update(dict.fromkeys(fingerprints, core))
        if cores == before:
            return False
        data["core"] = dict(list(cores.items())[-MAX_SERVERS:])
        return True

    return _update(path, change)


def set_sticky(path: Path, value: bool) -> bool:
    """Основной сервер (speed.sticky) включён или выключен; True — что-то изменилось."""
    if not isinstance(value, bool):
        raise ManagedError("ожидается true или false")

    def change(data: dict) -> bool:
        if data["sticky"] is value:
            return False
        data["sticky"] = value
        return True

    return _update(path, change)


def set_kernel_direct(path: Path, value: bool | None) -> bool:
    """Российские адреса самой машины и контейнеров мимо Xray (routing.kernel_direct)
    включены, выключены или (None) — как в config.toml; True — что-то изменилось."""
    if value is not None and not isinstance(value, bool):
        raise ManagedError("ожидается true или false")

    def change(data: dict) -> bool:
        if data["kernel_direct"] is value:
            return False
        data["kernel_direct"] = value
        return True

    return _update(path, change)


def set_tailscale_serve(path: Path, name: str) -> bool:
    """Запоминает, что XGW включил Serve для этого имени в tailnet; пусто — выключил.
    True — что-то изменилось."""
    name = name.strip().lower().rstrip(".")
    if name and not _TS_NAME_RE.fullmatch(name):
        raise ManagedError("неверное имя шлюза в tailnet")

    def change(data: dict) -> bool:
        if data["tailscale"]["serve"] == name:
            return False
        data["tailscale"] = {**data["tailscale"], "serve": name}
        return True

    return _update(path, change)


def set_tailscale_funnel(path: Path, name: str) -> bool:
    """Запоминает, что XGW включил Funnel для этого имени (API приложения); пусто —
    выключил. True — что-то изменилось."""
    name = name.strip().lower().rstrip(".")
    if name and not _TS_NAME_RE.fullmatch(name):
        raise ManagedError("неверное имя шлюза в tailnet")

    def change(data: dict) -> bool:
        if data["tailscale"]["funnel"] == name:
            return False
        data["tailscale"] = {**data["tailscale"], "funnel": name}
        return True

    return _update(path, change)


def set_tailscale_route(path: Path, route: str) -> bool:
    """Маршрут tailscaled: direct или vpn (как tailscale.route в config.toml)."""
    if route not in TS_ROUTES:
        raise ManagedError("маршрут Tailscale: direct или vpn")

    def change(data: dict) -> bool:
        if data["tailscale"]["route"] == route:
            return False
        data["tailscale"] = {**data["tailscale"], "route": route}
        return True

    return _update(path, change)


def drop_telegram(path: Path) -> bool:
    """Прежние версии хранили в panel.json бота Telegram (токен и чат). Telegram в XGW больше
    нет — токен, секрет, не должен лежать на диске: файл переписывается без него. True —
    было что убрать."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(raw, dict) or "telegram" not in raw:
        return False
    return _update(path, lambda data: True)  # load() поля telegram уже не знает


def save(path: Path, data: dict) -> None:
    atomic_write_json(Path(path), data, mode=0o600)


def link_id(link: str) -> str:
    """Короткий идентификатор ссылки: саму ссылку (в ней ключ) панель наружу не отдаёт."""
    return hashlib.sha256(link.encode("utf-8")).hexdigest()[:12]


def check_url(url: str) -> str:
    """Адрес подписки, пригодный для запроса; иначе ManagedError."""
    url = url.strip()
    if not url or len(url) > MAX_URL or re.search(r"[\s\x00-\x1f]", url):
        raise ManagedError("адрес подписки пуст, слишком длинный или содержит пробелы")
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError as exc:
        raise ManagedError("адрес подписки не разобрать") from exc
    # Только http и https: file:// заставил бы демон читать файлы машины от root.
    if parts.scheme not in ("http", "https") or not host:
        raise ManagedError("адрес подписки должен начинаться с https:// или http://")
    return url


def _clean_name(name: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f]+", " ", name).strip()[:MAX_NAME].strip()


def _clean_header_value(value: str) -> str:
    value = str(value).strip()
    # Убираем управляющие символы и обрезаем до разумного размера.
    value = re.sub(r"[\x00-\x1f\x7f]+", "", value)
    return value[:512]


def _clean_headers(headers: dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    if not isinstance(headers, dict):
        return result
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        # Заголовки с управляющими символами (в т. ч. переносом строки) недопустимы в HTTP.
        if re.search(r"[\x00-\x1f\x7f]", key) or re.search(r"[\x00-\x1f\x7f]", value):
            continue
        key = key.strip()[:128]
        value = value.strip()[:2048]
        if key and value:
            result[key] = value
    return result


def _free_name(wanted: str, taken: set[str]) -> str:
    if wanted not in taken:
        return wanted
    for number in range(2, 1000):
        suffix = f"-{number}"
        candidate = wanted[: MAX_NAME - len(suffix)] + suffix
        if candidate not in taken:
            return candidate
    raise ManagedError("не удалось подобрать имя подписки")


def add_subscription(
    path: Path,
    url: str,
    name: str = "",
    *,
    taken: set[str],
    user_agent: str = "",
    headers: dict[str, str] | None = None,
) -> str:
    """Добавляет подписку и возвращает её имя. taken — имена, занятые в config.toml."""
    url = check_url(url)
    wanted = _clean_name(name)

    def change(data: dict) -> str:
        if len(data["subscriptions"]) >= MAX_SUBSCRIPTIONS:
            raise ManagedError(f"подписок из панели уже {MAX_SUBSCRIPTIONS} — больше нельзя")
        if any(item["url"] == url for item in data["subscriptions"]):
            raise ManagedError("такая подписка уже добавлена")
        used = set(taken) | {item["name"] for item in data["subscriptions"]}
        if wanted and wanted in used:
            raise ManagedError(f"подписка с именем «{wanted}» уже есть")
        chosen = wanted or _free_name((urlsplit(url).hostname or "sub")[:MAX_NAME], used)
        data["subscriptions"].append(
            {
                "name": chosen,
                "url": url,
                "user_agent": _clean_header_value(user_agent),
                "headers": _clean_headers(headers or {}),
                "refresh_minutes": DEFAULT_REFRESH,
            }
        )
        return chosen

    return _update(path, change)


def update_subscription(
    path: Path,
    name: str,
    *,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
) -> bool:
    """Обновляет User-Agent и заголовки управляемой подписки. False — нет такой подписки."""

    def change(data: dict) -> bool:
        for item in data["subscriptions"]:
            if item["name"] == name:
                if user_agent is not None:
                    item["user_agent"] = _clean_header_value(user_agent)
                if headers is not None:
                    item["headers"] = _clean_headers(headers)
                return True
        return False

    return _update(path, change)


def remove_subscription(path: Path, name: str) -> bool:
    def change(data: dict) -> bool:
        kept = [item for item in data["subscriptions"] if item["name"] != name]
        if len(kept) == len(data["subscriptions"]):
            return False
        data["subscriptions"] = kept
        return True

    return _update(path, change)


def split_links(text: str) -> list[str]:
    """Ссылки серверов из вставленного текста — по одной на строку."""
    return [line.strip() for line in text.splitlines() if "://" in line]


def add_links(path: Path, text: str, *, taken: set[str]) -> int:
    """Добавляет ссылки серверов (vless://, vmess://, trojan://, ss://); возвращает,
    сколько добавлено. Ссылка, которую XGW не разбирает, не принимается."""

    def change(data: dict) -> int:
        known = set(taken) | set(data["links"])
        added = 0
        for link in split_links(text):
            if link in known:
                continue
            raws, _meta, warnings = parse_links_text(link, "manual")
            if not raws:
                reason = warnings[0] if warnings else "формат не распознан"
                raise ManagedError(f"ссылку сервера разобрать не удалось: {reason}")
            if len(data["links"]) >= MAX_LINKS:
                raise ManagedError(f"ссылок из панели уже {MAX_LINKS} — больше нельзя")
            data["links"].append(link)
            known.add(link)
            added += 1
        return added

    return _update(path, change)


def remove_link(path: Path, identifier: str) -> bool:
    def change(data: dict) -> bool:
        kept = [link for link in data["links"] if link_id(link) != identifier]
        if len(kept) == len(data["links"]):
            return False
        data["links"] = kept
        return True

    return _update(path, change)
