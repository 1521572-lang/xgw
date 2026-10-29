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

Списки GitHub (решение заказчика 28.10.2026, после отчёта М2а) — текстовые файлы со ссылками
серверов по одной в строке, строки «# …» — пояснения (как у подписок; бывает и base64 целиком).
igareck/vpn-configs-for-russia — проверенные на сервере в России «чёрные списки» (обычный
интернет): BLACK_VLESS_RUS.txt (VLESS: ws, Reality, xhttp) и BLACK_SS+All_RUS.txt (Trojan,
Hysteria2, VMess, Shadowsocks); mahdibland/V2RayAggregator — Eternity.txt (200 отобранных по
скорости: Shadowsocks, VMess, Trojan). 28.10.2026 файлы обновлялись в тот же день, размер —
десятки КБ; barry-far/V2ray-Configs отключён GitHub, у Epodonios/v2ray-configs страницы нет.
Страна — по флагу в имени (подсказка порядка проверки, R15). Списки — чужой текст: схемы только
из LIST_SCHEMES, адрес-литерал — только публичный IPv4, цепочки не принимаются; имя сервера
проверяется на публичность перед каждой пробой (probe.server_hosts).
"""

from __future__ import annotations

import base64
import binascii
import csv
import io
import ipaddress
import itertools
import json
import re
import unicodedata
from collections import Counter

from .. import fetch, masking
from . import ovpn
from .models import Access, Backend, ProviderResult, Status, Variant

VPNGATE = "vpngate"
VPNBOOK = "vpnbook"
IGARECK = "igareck"
MAHDIBLAND = "mahdibland"
LIST_PROVIDERS = (IGARECK, MAHDIBLAND)  # списки GitHub: проверки — без бюджета трафика
PROVIDERS = (VPNGATE, VPNBOOK, *LIST_PROVIDERS)

VPNGATE_URL = "https://www.vpngate.net/api/iphone/"
VPNBOOK_OPENVPN_URL = "https://www.vpnbook.com/freevpn/openvpn"
VPNBOOK_OUTLINE_URL = "https://www.vpnbook.com/freevpn/outline-vpn"
VPNBOOK_PROFILE_URL = "https://www.vpnbook.com/api/openvpn"
VPNBOOK_PROTOCOLS = ("tcp443", "tcp80", "udp53", "udp25000")
GITHUB_RAW = "raw.githubusercontent.com"
_IGARECK = f"https://{GITHUB_RAW}/igareck/vpn-configs-for-russia/main/"
LIST_URLS = {
    IGARECK: (f"{_IGARECK}BLACK_VLESS_RUS.txt", f"{_IGARECK}BLACK_SS+All_RUS.txt"),
    MAHDIBLAND: (f"https://{GITHUB_RAW}/mahdibland/V2RayAggregator/master/Eternity.txt",),
}
LIST_NAMES = {IGARECK: "igareck", MAHDIBLAND: "mahdibland"}
LIST_SCHEMES = ("vless", "vmess", "trojan", "ss", "hysteria2", "hy2", "tuic", "anytls")
MAX_LIST_LINES = 5000
MAX_LIST_VARIANTS = 2000
MAX_LINK = 8192

# Доверенные хосты каждого источника (R09): каталог, профили и перенаправления — только сюда.
ORIGINS = {
    VPNGATE: frozenset(("www.vpngate.net",)),
    VPNBOOK: frozenset(("www.vpnbook.com",)),
    IGARECK: frozenset((GITHUB_RAW,)),
    MAHDIBLAND: frozenset((GITHUB_RAW,)),
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


# --- списки GitHub ----------------------------------------------------------------------------


def flag_country(name: str) -> str:
    """Страна по флагу в имени — два символа-индикатора региона подряд («🇩🇪 Germany…» → DE);
    пусто — флага нет."""
    for first, second in itertools.pairwise(name):
        if 0x1F1E6 <= ord(first) <= 0x1F1FF and 0x1F1E6 <= ord(second) <= 0x1F1FF:
            return chr(ord("A") + ord(first) - 0x1F1E6) + chr(ord("A") + ord(second) - 0x1F1E6)
    return ""


def _clean_name(name: str) -> str:
    """Имя из ссылки — для журнала и панели: без управляющих символов, одной строкой, до 48."""
    text = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    return " ".join(text.split())[:48]


def _list_text(text: str) -> str:
    """Список целиком в base64 (так тоже публикуют) — раскодировать; иначе как есть."""
    stripped = text.lstrip("﻿").strip()
    if "://" in stripped:
        return stripped
    from ..parsers.common import b64_decode

    try:
        decoded = b64_decode(stripped).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return stripped
    return decoded if "://" in decoded else stripped


# Чего Xray 26.10.21 не принимает (xray run -test 28.10.2026; отчёт М2а.1 — «Xray завершился с
# кодом 23» у серверов списков): шифры Shadowsocks без AEAD и aes-192-gcm, ключ 2022 не той
# длины, убранные flow VLESS, транспорт HTTP/2 (h2; заменён XHTTP), shortId REALITY не из
# пар hex до 16 знаков, ключ REALITY не 43 знака base64url. Отчёт М2а.3 (проверено 29.10):
# VLESS без TLS, REALITY и VLESS-шифрования и trojan без TLS Xray принимает только к частному
# адресу («…prohibited unless the server address is a private IP or domain»), а серверы
# списков — публичные. Основная подписка такие серверы отсеивает проверкой сборки
# (generator/validate.py); у списков — здесь, с причиной.
XRAY_SS_METHODS = frozenset((
    "aes-128-gcm", "aes-256-gcm", "chacha20-poly1305", "chacha20-ietf-poly1305",
    "xchacha20-poly1305", "xchacha20-ietf-poly1305", "2022-blake3-aes-128-gcm",
    "2022-blake3-aes-256-gcm", "2022-blake3-chacha20-poly1305",
))
SS2022_KEY_BYTES = {"2022-blake3-aes-128-gcm": 16, "2022-blake3-aes-256-gcm": 32,
                    "2022-blake3-chacha20-poly1305": 32}
XRAY_FLOWS = frozenset(("", "xtls-rprx-vision", "xtls-rprx-vision-udp443"))
_SHORT_ID = re.compile(r"(?:[0-9A-Fa-f]{2}){0,8}")
_REALITY_KEY = re.compile(r"[A-Za-z0-9_-]{43}")


def _ss2022_key_ok(password: str, size: int) -> bool:
    for part in password.split(":"):
        try:
            if len(base64.b64decode(part, validate=True)) != size:
                return False
        except (binascii.Error, ValueError):
            return False
    return True


def xray_problem(outbound: dict) -> str:
    """Почему Xray не примет этот outbound (по проверенному списку выше); пусто — примет.
    Значения секретов в причину не попадают."""
    settings = outbound.get("settings") or {}
    protocol = str(outbound.get("protocol") or "")
    if protocol == "shadowsocks":
        for server in settings.get("servers") or []:
            method = str(server.get("method") or "").lower()
            if method not in XRAY_SS_METHODS:
                return f"шифр Shadowsocks {method[:32]} — Xray его не принимает"
            size = SS2022_KEY_BYTES.get(method)
            if size and not _ss2022_key_ok(str(server.get("password") or ""), size):
                return "ключ Shadowsocks 2022 не той длины"
    stream = outbound.get("streamSettings") or {}
    secured = stream.get("security") in ("tls", "reality")
    if protocol == "vless":
        for item in settings.get("vnext") or []:
            for user in item.get("users") or []:
                flow = str(user.get("flow") or "")
                if flow not in XRAY_FLOWS:
                    return f"flow VLESS {flow[:32]} — убран из Xray"
                if not secured and str(user.get("encryption") or "none") == "none":
                    return "VLESS без TLS и шифрования — Xray не пускает к публичному адресу"
    if protocol == "trojan" and not secured:
        return "trojan без TLS — Xray не пускает к публичному адресу"
    if str(stream.get("network") or "") in ("h2", "http"):
        return "транспорт HTTP/2 (h2) — убран из Xray, заменён XHTTP"
    reality = stream.get("realitySettings") if stream.get("security") == "reality" else None
    if isinstance(reality, dict):
        if not _SHORT_ID.fullmatch(str(reality.get("shortId") or "")):
            return "shortId REALITY — не пары hex до 16 знаков"
        key = str(reality.get("publicKey") or reality.get("password") or "")
        if not _REALITY_KEY.fullmatch(key):
            return "ключ REALITY — не 43 знака base64url"
    return ""


def _list_variant(provider: str, raw, url: str) -> tuple[Variant | None, str]:
    """Сервер из списка → вариант; (None, причина) — не принят."""
    address = raw.address.strip("[]").lower()
    try:
        literal = ipaddress.ip_address(address)
    except ValueError:
        literal = None
    if literal is not None:
        if literal.version != 4 or fetch.is_bogon(address):
            return None, "адрес сервера — не публичный IPv4"
        host, ipv4 = "", address
    else:
        host, ipv4 = _host(address), ""
        if not host:
            return None, "неверное имя сервера"
    if raw.outbound:
        stream = raw.outbound.get("streamSettings") or {}
        if raw.outbound.get("proxySettings") or (stream.get("sockopt") or {}).get("dialerProxy"):
            return None, "цепочка серверов"
        problem = xray_problem(raw.outbound)
        if problem:
            return None, problem
        backend, outbound, singbox = Backend.XRAY, raw.outbound, None
    elif raw.singbox is not None and not raw.singbox.endpoint:
        if raw.singbox.main.get("detour") and not raw.singbox.extra:
            return None, "цепочка серверов"
        backend, outbound = Backend.SINGBOX, None
        singbox = {"main": raw.singbox.main, "endpoint": False, "extra": raw.singbox.extra}
    else:
        return None, "сервер не умеют ни Xray, ни sing-box"
    name = _clean_name(raw.name)
    return Variant(
        provider=provider, backend=backend, protocol=raw.protocol, host=host, address=ipv4,
        port=raw.port, transport="udp" if raw.protocol in ("hysteria2", "tuic") else "tcp",
        name=f"{LIST_NAMES.get(provider, provider)} {name}".strip(),
        country_hint=flag_country(raw.name), access=Access.FREE, outbound=outbound,
        singbox=singbox, source_url=url,
    ), ""


def parse_link_list(provider: str, documents: list[tuple[str, str]], *, now: float,
                    ) -> ProviderResult:
    """Файлы списка (адрес, текст) → варианты Xray и sing-box. Ни одной ссылки —
    SCHEMA_CHANGED (прежний снимок остаётся): файл подменили или формат сменился."""
    from ..parsers.common import ParseError, parse_link

    result = ProviderResult(provider, Status.SCHEMA_CHANGED, retrieved_at=now)
    reasons: Counter[str] = Counter()
    seen: set[str] = set()
    links = 0
    for url, text in documents:
        for raw_line in _list_text(text).splitlines()[:MAX_LIST_LINES]:
            line = raw_line.strip()
            if not line or line.startswith("#") or "://" not in line:
                continue
            links += 1
            scheme = line.split("://", 1)[0].lower()
            if scheme not in LIST_SCHEMES:
                reasons[f"схема {scheme[:16]}:// не принимается"] += 1
                continue
            if len(line) > MAX_LINK:
                reasons["ссылка длиннее 8 КиБ"] += 1
                continue
            try:
                raw = parse_link(line)
            except (ParseError, ValueError) as exc:
                # Текст ошибки разбора может нести куски ссылки — маскируется и обрезается.
                reasons[masking.mask_text(str(exc))[:80]] += 1
                continue
            if not raw.supported:
                reasons["не поддерживается ни одним ядром"] += 1
                continue
            variant, why = _list_variant(provider, raw, url)
            if variant is None:
                reasons[why] += 1
                continue
            if variant.variant_id in seen:
                reasons["повтор"] += 1
                continue
            if len(result.variants) >= MAX_LIST_VARIANTS:
                reasons[f"сверх {MAX_LIST_VARIANTS} серверов"] += 1
                continue
            seen.add(variant.variant_id)
            result.variants.append(variant)
    result.rejected = sum(reasons.values())
    result.rejections = dict(reasons.most_common(20))
    if not links:
        result.detail = "в файлах списка нет ссылок серверов"
        return result
    result.complete_response = True
    result.authoritative = True  # список — весь инвентарь: пропавшей ссылки больше нет
    result.status = Status.SUCCESS
    return result
