"""Разбор ответов источников бесплатного пула (ТЗ §3, R07–R09). Здесь — только чистые функции
над текстом ответа: сеть, лимиты запросов и несущий канал — в pool.py.

Форматы сверены с настоящими ответами 28.10.2026 (очищенные образцы — tests/fixtures/freepool):

VPN Gate — официальный CSV api/iphone: строка-маркер `*vpn_servers`, заголовок `#HostName,…`,
строки, замыкающая `*`. Профиль OpenVPN — base64 в последнем столбце. Каталог частичный
(authoritative = False): пропавшая строка не значит, что сервер умер (R13).

VPNBook — сайт на Next.js: данные страницы — в `self.__next_f.push([1,"…"])` (JSON-строки).
OpenVPN: массив `"servers":[{id, name, hostname, ipAddress, countryCode, countryName}]`, общая
учётка на все серверы («Username … Password … Last updated: …»), профиль — официальная кнопка
«Download» страницы: /api/openvpn?hostname=…&protocol=…&ip=… (протоколы tcp443, tcp80, udp53,
udp25000 — из скрипта страницы). Outline: «connectionString»: ss://…@хост:443/?outline=1.
"""

from __future__ import annotations

import base64
import binascii
import csv
import io
import json
import re
from collections import Counter

from . import ovpn
from .models import Access, Backend, ProviderResult, Status, Variant

VPNGATE = "vpngate"
VPNBOOK = "vpnbook"
PROVIDERS = (VPNGATE, VPNBOOK)

VPNGATE_URL = "https://www.vpngate.net/api/iphone/"
VPNBOOK_OPENVPN_URL = "https://www.vpnbook.com/freevpn/openvpn"
VPNBOOK_OUTLINE_URL = "https://www.vpnbook.com/freevpn/outline-vpn"
VPNBOOK_PROFILE_URL = "https://www.vpnbook.com/api/openvpn"
VPNBOOK_PROTOCOLS = ("tcp443", "tcp80", "udp53", "udp25000")

# Доверенные хосты каждого источника (R09): каталог, профили и перенаправления — только сюда.
ORIGINS = {
    VPNGATE: frozenset(("www.vpngate.net",)),
    VPNBOOK: frozenset(("www.vpnbook.com",)),
}

MAX_ROWS = 2000
MAX_B64 = 400_000  # профиль до 256 КиБ в base64
VPNGATE_REQUIRED = (
    "HostName", "IP", "Score", "Ping", "Speed", "CountryShort", "NumVpnSessions", "Uptime",
    "OpenVPN_ConfigData_Base64",
)
_FLIGHT = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
_HOST = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+")
_IPV4 = re.compile(r"(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}")

def _host(value: str) -> str:
    value = (value or "").strip().lower()
    return value if _HOST.fullmatch(value) and len(value) <= 253 else ""


def _ipv4(value: str) -> str:
    value = (value or "").strip()
    return value if _IPV4.fullmatch(value) else ""


def _int(value: str) -> int:
    try:
        return int((value or "").strip())
    except ValueError:
        return 0


# --- VPN Gate ---------------------------------------------------------------------------------


def parse_vpngate(text: str, *, now: float, url: str = VPNGATE_URL) -> ProviderResult:
    """CSV VPN Gate → варианты OpenVPN. Схема не та — SCHEMA_CHANGED (прежний снимок остаётся);
    нет замыкающей `*` — PARTIAL (документ обрезан)."""
    result = ProviderResult(VPNGATE, Status.SCHEMA_CHANGED, retrieved_at=now)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines or lines[0].strip() != "*vpn_servers":
        result.detail = "нет строки-маркера *vpn_servers"
        return result
    if len(lines) < 2 or not lines[1].startswith("#"):
        result.detail = "нет заголовка #HostName,…"
        return result
    complete = lines[-1].strip() == "*"
    body = [line for line in lines[1:] if line.strip() and line.strip() != "*"]
    rows = list(csv.reader(io.StringIO("\n".join(body)[1:])))
    if not rows:
        result.detail = "пустой заголовок"
        return result
    header = rows[0]
    index = {name: position for position, name in enumerate(header)}
    missing = [name for name in VPNGATE_REQUIRED if name not in index]
    if missing:
        result.detail = "нет столбцов: " + ", ".join(missing)
        return result
    if len(rows) - 1 > MAX_ROWS:
        result.status = Status.RESOURCE_LIMIT
        result.detail = f"строк больше {MAX_ROWS}"
        return result
    reasons: Counter[str] = Counter()
    for row in rows[1:]:
        if len(row) < len(header):
            reasons["строка короче заголовка"] += 1
            continue
        field = {name: row[position] for name, position in index.items()}
        encoded = field["OpenVPN_ConfigData_Base64"].strip()
        if not encoded or len(encoded) > MAX_B64:
            reasons["нет профиля или он слишком большой"] += 1
            continue
        try:
            profile_text = base64.b64decode(encoded, validate=True).decode("utf-8")
            profile = ovpn.parse(profile_text)
        except (binascii.Error, ValueError):
            reasons["профиль не base64/UTF-8"] += 1
            continue
        except ovpn.OvpnRejected as exc:
            reasons[str(exc)] += 1
            continue
        country = field.get("CountryShort", "").strip().upper()
        speed = _int(field.get("Speed", ""))
        hints = (
            ("ping_ms", str(_int(field.get("Ping", "")))),
            ("speed_mbps", f"{speed / 1e6:.1f}"),
            ("score", str(_int(field.get("Score", "")))),
            ("sessions", str(_int(field.get("NumVpnSessions", "")))),
            ("uptime_days", str(_int(field.get("Uptime", "")) // 86_400_000)),
        )
        for remote in profile.remotes:
            address = _ipv4(remote.host) or _ipv4(field.get("IP", ""))
            result.variants.append(Variant(
                provider=VPNGATE, backend=Backend.OPENVPN, protocol="openvpn",
                host=_host(remote.host) if not _ipv4(remote.host) else "",
                address=address, port=remote.port, transport=remote.proto,
                name=f"VPN Gate {country} {field.get('HostName', '').strip()[:32]}",
                country_hint=country if re.fullmatch(r"[A-Z]{2}", country) else "",
                access=Access.FREE, hints=hints, credential_scope="",
                profile=profile, source_url=url,
            ))
    result.rejected = sum(reasons.values())
    result.rejections = dict(reasons)
    result.complete_response = complete
    result.authoritative = False
    result.status = Status.SUCCESS if complete else Status.PARTIAL
    if not complete:
        result.detail = "нет замыкающей строки «*» — документ обрезан"
    return result


# --- VPNBook ----------------------------------------------------------------------------------


def _flight(page: str) -> str:
    """Данные страницы Next.js: строки self.__next_f.push([1,"…"]) подряд."""
    parts: list[str] = []
    for chunk in _FLIGHT.findall(page):
        try:
            parts.append(json.loads('"' + chunk + '"'))
        except ValueError:
            continue
    return "".join(parts)


def _servers(flight: str) -> list[dict]:
    """Массив "servers":[…] данных страницы; пусто — не найден."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r'"servers":\[', flight):
        try:
            value, _end = decoder.raw_decode(flight, match.end() - 1)
        except ValueError:
            continue
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return value
    return []


def vpnbook_credentials(flight: str) -> dict[str, str]:
    """Общая учётка VPNBook на все серверы: {username, password, updated}; пусто — нет.
    Значения — в отрисованных элементах страницы: «Username», значение, «Password», значение,
    затем «Last updated: …»."""
    end = flight.find("Last updated: ")
    if end < 0:
        return {}
    strings = re.findall(r'"children":"([^"]{1,64})"', flight[max(0, end - 2500): end + 80])
    found: dict[str, str] = {}
    for position, value in enumerate(strings[:-1]):
        if value == "Username":
            found["username"] = strings[position + 1]
        elif value == "Password":
            found["password"] = strings[position + 1]
    updated = re.search(r"Last updated: ([A-Z][a-z]{2} \d{1,2}, \d{4})", flight[end: end + 60])
    if updated:
        found["updated"] = updated.group(1)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", found.get("username", "")) or not re.fullmatch(
            r"[A-Za-z0-9._!@#$%^&*-]{1,64}", found.get("password", "")):
        return {}
    return found


def parse_vpnbook_openvpn(page: str, *, now: float) -> ProviderResult:
    """Страница OpenVPN VPNBook → серверы (вариантов пока без профиля: профиль качается
    отдельно для отобранных, needs="profile") и общая учётка."""
    result = ProviderResult(VPNBOOK, Status.SCHEMA_CHANGED, retrieved_at=now)
    flight = _flight(page)
    servers = _servers(flight)
    if not servers:
        result.detail = 'нет массива "servers" в данных страницы'
        return result
    credentials = vpnbook_credentials(flight)
    if credentials:
        result.credentials["vpnbook"] = credentials
    for item in servers:
        host = _host(str(item.get("hostname") or ""))
        server_id = str(item.get("id") or "")
        country = str(item.get("countryCode") or "").upper()
        if not host or not re.fullmatch(r"[a-z]{2}\d{1,4}", server_id):
            result.rejected += 1
            continue
        for protocol in VPNBOOK_PROTOCOLS:
            transport, port = protocol[:3], int(protocol[3:])
            result.variants.append(Variant(
                provider=VPNBOOK, backend=Backend.OPENVPN, protocol="openvpn", host=host,
                address=_ipv4(str(item.get("ipAddress") or "")), port=port, transport=transport,
                name=f"VPNBook {item.get('name') or server_id} {protocol}",
                country_hint=country if re.fullmatch(r"[A-Z]{2}", country) else "",
                access=Access.FREE, needs="profile", credential_scope="vpnbook",
                source_url=VPNBOOK_OPENVPN_URL,
                extra=(("server_id", server_id), ("protocol", protocol)),
            ))
    result.complete_response = True
    result.authoritative = True  # страница перечисляет все свои бесплатные серверы
    result.status = Status.SUCCESS
    if not credentials:
        result.detail = "учётка на странице не найдена — профили без неё не подключатся"
    return result


def vpnbook_profile_query(variant: Variant) -> dict[str, str]:
    """Параметры официальной кнопки «Download» для профиля этого варианта."""
    extra = dict(variant.extra)
    query = {"hostname": variant.host, "protocol": extra.get("protocol", "")}
    if variant.address:
        query["ip"] = variant.address
    return query


def parse_vpnbook_outline(page: str, *, now: float) -> ProviderResult:
    """Страница Outline VPNBook → варианты Xray (Shadowsocks) по ключам ss://."""
    from ..parsers.common import ParseError, parse_link

    result = ProviderResult(VPNBOOK, Status.SCHEMA_CHANGED, retrieved_at=now)
    flight = _flight(page)
    decoder = json.JSONDecoder()
    found = 0
    for match in re.finditer(r'"connectionString":"', flight):
        start = flight.rfind("{", 0, match.start())
        try:
            item, _end = decoder.raw_decode(flight, start)
        except ValueError:
            continue
        link = str(item.get("connectionString") or "")
        if not link.startswith("ss://"):
            continue
        found += 1
        try:
            raw = parse_link(link)
        except ParseError as exc:
            result.rejected += 1
            result.rejections[str(exc)] = result.rejections.get(str(exc), 0) + 1
            continue
        country = str(item.get("countryCode") or "").upper()
        result.variants.append(Variant(
            provider=VPNBOOK, backend=Backend.XRAY, protocol="shadowsocks",
            host=_host(raw.address), address=_ipv4(raw.address), port=raw.port, transport="tcp",
            name=f"VPNBook Outline {item.get('name') or raw.address}",
            country_hint=country if re.fullmatch(r"[A-Z]{2}", country) else "",
            access=Access.FREE, outbound=raw.outbound, source_url=VPNBOOK_OUTLINE_URL,
        ))
    if not found:
        result.detail = "ключей ss:// в данных страницы нет"
        return result
    result.complete_response = True
    result.authoritative = True
    result.status = Status.SUCCESS
    return result
