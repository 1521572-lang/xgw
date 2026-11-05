"""Проверка связности NetworkManager мимо барьера (значок «ограниченное подключение»).

NetworkManager раз в несколько минут спрашивает свой адрес проверки (в Ubuntu — HTTP к
connectivity-check.ubuntu.com) сокетом, привязанным к интерфейсу WAN. Такой сокет уходит
мимо перехвата, а барьер `inet xgw_guard` (nft.render_guard) молча отбрасывает всё, что
ушло с машины мимо Xray, — с 02.11.2026 значок шлюза показывал «ограниченное подключение»
при работающем интернете (отчёт g1-c06). Исключение узкое: только root, только TCP на порт
адреса проверки и только к его IPv4-адресам. Наружу мимо VPN уходит тот же открытый запрос,
что делает любая Ubuntu, без пользовательских данных.

Демон узнаёт адрес у NetworkManager (busctl), разрешает его своими резолверами мимо
перехвата и пишет /run/xgw/conncheck.json; правила (Capture.rules) читают файл. Сменились
адреса — меняется желаемый барьер, и сверка правил загружает их заново.
"""

from __future__ import annotations

import ipaddress
import json
from pathlib import Path
from urllib.parse import urlsplit

from ..paths import Paths, atomic_write_json
from . import cmd

FILE = "conncheck.json"
REFRESH = 6 * 3600.0
_NM = ("busctl", "--system", "get-property", "org.freedesktop.NetworkManager",
       "/org/freedesktop/NetworkManager", "org.freedesktop.NetworkManager")


def path(paths: Paths) -> Path:
    return paths.run / FILE


def parse_uri(text: str) -> tuple[str, int] | None:
    """`s "http://host./"` (вывод busctl) или сам адрес → (хост, порт); None — нет адреса."""
    value = text.strip()
    if value.startswith("s "):
        value = value[2:].strip().strip('"')
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        return None
    return parts.hostname.rstrip("."), port


def nm_target(run=cmd.run) -> tuple[str, int] | None:
    """Адрес проверки связности NetworkManager; None — NetworkManager нет, проверка
    выключена или адреса нет."""
    try:
        enabled = run([*_NM, "ConnectivityCheckEnabled"], timeout=10).strip()
        uri = run([*_NM, "ConnectivityCheckUri"], timeout=10)
    except cmd.CommandError:
        return None
    if enabled != "b true":
        return None
    return parse_uri(uri)


def _public4(values) -> list[str]:
    found = []
    for value in values:
        try:
            address = ipaddress.ip_address(str(value))
        except ValueError:
            continue
        if address.version == 4 and address.is_global:
            found.append(str(address))
    return sorted(set(found))


def read(paths: Paths) -> tuple[tuple[str, ...], int]:
    """Адреса и порт исключения для правил; пусто — исключения нет."""
    try:
        data = json.loads(path(paths).read_text(encoding="utf-8"))
        port = int(data.get("port") or 0)
        ips = tuple(_public4(data.get("ips") or []))
    except (OSError, ValueError, TypeError, AttributeError):
        return (), 80
    if not ips or not 1 <= port <= 65535:
        return (), 80
    return ips, port


def lookup(resolve, run=cmd.run):
    """Адрес проверки у NetworkManager, разрешённый resolve(host): словарь для store; None —
    проверки нет (исключение убрать); False — адрес не разрешился (оставить прежний). Сеть и
    busctl — здесь, в фоновом потоке демона; файл и правила меняет основной поток (store)."""
    target = nm_target(run)
    if target is None:
        return None
    host, port = target
    ips = _public4(resolve(host))
    if not ips:
        return False
    return {"host": host, "port": port, "ips": ips}


def refresh(paths: Paths, resolve, run=cmd.run) -> bool:
    """lookup и store разом. True — файл изменился."""
    found = lookup(resolve, run)
    return False if found is False else store(paths, found)


def store(paths: Paths, wanted: dict | None) -> bool:
    """Записать адреса (None — удалить файл). True — файл изменился: правила барьера надо
    загрузить заново сразу, иначе сверка до следующего шага видит «правила не загружены»."""
    file = path(paths)
    if wanted is None:
        existed = file.exists()
        file.unlink(missing_ok=True)
        return existed
    try:
        current = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        current = None
    if current == wanted:
        return False
    atomic_write_json(file, wanted, mode=0o644)
    return True
