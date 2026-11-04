"""Разбор ответов источников бесплатного пула (ТЗ §3, R07–R09). Здесь — только чистые функции
над текстом ответа: сеть, лимиты запросов и несущий канал — в pool.py.

Форматы сверены с настоящими ответами 28.10.2026 (очищенные образцы — tests/fixtures/freepool):

VPN Gate (веха М2в, 29.10.2026: OpenVPN убран из XGW — решение заказчика) — страница списка
серверов www.vpngate.net/en/ (сверена с настоящей 29.10.2026, ~210 КБ, 100 серверов): таблица с
заголовком «DDNS hostname», строки — по 10 ячеек `<td class='vg_table_row_…'>`, заголовок
повторяется через каждые десять. Ячейки: флаг страны (`images/flags/JP.png`), имя DDNS
(*.opengw.net) и IPv4, сессии и время работы, скорость и задержка, SSL-VPN, L2TP/IPsec,
OpenVPN, MS-SSTP («SSTP Hostname : имя[:порт]», порт 443 не пишется), оператор, счёт. Берутся
только серверы с SSTP (TLS по TCP; у OpenVPN и L2TP в CSV-каталоге и на странице — нет: ТСПУ
распознаёт их по протоколу). Вход — общий «vpn»/«vpn» (страница howto_sstp.aspx). Каталог
частичный (authoritative = False): VPN Gate показывает каждому свою часть списка, пропавшая
строка не значит, что сервер умер (R13).

VPNBook — сайт на Next.js: данные страницы — в `self.__next_f.push([1,"…"])` (JSON-строки).
Берутся только ключи Outline: «connectionString»: ss://…@хост:443/?outline=1 (страница OpenVPN
и её общая учётка — не нужны с М2в).

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
import html
import ipaddress
import itertools
import json
import re
import unicodedata
from collections import Counter

from .. import fetch, masking
from .models import Access, Backend, ProviderResult, Status, Variant

VPNGATE = "vpngate"
VPNBOOK = "vpnbook"
IGARECK = "igareck"
MAHDIBLAND = "mahdibland"
LIST_PROVIDERS = (IGARECK, MAHDIBLAND)  # списки GitHub: проверки — без бюджета трафика
PROVIDERS = (VPNGATE, VPNBOOK, *LIST_PROVIDERS)

VPNGATE_URL = "https://www.vpngate.net/en/"
# Общий вход SSTP у всех серверов VPN Gate (www.vpngate.net/en/howto_sstp.aspx) — не секрет.
VPNGATE_USER = VPNGATE_PASSWORD = "vpn"
VPNBOOK_OUTLINE_URL = "https://www.vpnbook.com/freevpn/outline-vpn"
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

# Доверенные хосты каждого источника (R09): каталог и перенаправления — только сюда.
ORIGINS = {
    VPNGATE: frozenset(("www.vpngate.net",)),
    VPNBOOK: frozenset(("www.vpnbook.com",)),
    IGARECK: frozenset((GITHUB_RAW,)),
    MAHDIBLAND: frozenset((GITHUB_RAW,)),
}

MAX_ROWS = 2000
# Заголовок таблицы серверов: у таблицы сессий на той же странице (с тем же id) его нет.
_VG_MARKER = "DDNS hostname"
_VG_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
_VG_CELL = re.compile(r"<td\b[^>]*>(.*?)</td>", re.S | re.I)
_VG_FLAG = re.compile(r"flags/([A-Z]{2})\.png")
_VG_BREAK = re.compile(r"<br\s*/?>|</?p\b[^>]*>|</span>|</a>", re.I)
_VG_TAG = re.compile(r"<[^>]*>")
_VG_SSTP = "SSTP Hostname"
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


def _cell_lines(cell: str) -> list[str]:
    """Ячейка таблицы → строки текста: разрывы (<br>, абзац, конец span и ссылки) — новые строки,
    теги убраны, сущности HTML раскрыты, пустые — выброшены."""
    text = _VG_TAG.sub("", _VG_BREAK.sub("\n", cell))
    return [line for line in (" ".join(html.unescape(raw).split()) for raw in text.split("\n"))
            if line]


def _number(text: str) -> float:
    """Первое число строки («1,171,661.52 GB», «158.22 Mbps», «Ping: 12 ms»); 0 — нет."""
    match = re.search(r"\d[\d,]*(?:\.\d+)?", text or "")
    return float(match.group(0).replace(",", "")) if match else 0.0


def _sstp_endpoint(cell: str, host: str) -> tuple[int, str]:
    """Ячейка MS-SSTP → (порт, ""), или (0, почему не годится). Имя SSTP — то же, что имя DDNS
    сервера: иное — не доверять строке."""
    lines = _cell_lines(cell)
    for position, line in enumerate(lines):
        if line.startswith(_VG_SSTP):
            value = line.split(":", 1)[1].strip() if ":" in line else ""
            if not value and position + 1 < len(lines):
                value = lines[position + 1]
            name, _colon, port_text = value.lower().partition(":")
            if name != host:
                return 0, "имя SSTP не совпадает с именем сервера"
            port = int(port_text) if port_text.isdigit() else (443 if not port_text else 0)
            if not 0 < port < 65536:
                return 0, "неверный порт SSTP"
            return port, ""
    return 0, "нет SSTP"


def parse_vpngate(text: str, *, now: float, url: str = VPNGATE_URL) -> ProviderResult:
    """Страница списка VPN Gate → варианты SSTP. Таблицы серверов нет — SCHEMA_CHANGED (прежний
    снимок остаётся); нет её конца — PARTIAL (документ обрезан)."""
    result = ProviderResult(VPNGATE, Status.SCHEMA_CHANGED, retrieved_at=now)
    marker = text.find(_VG_MARKER)
    start = text.rfind("<table", 0, marker) if marker >= 0 else -1
    if start < 0:
        result.detail = "нет таблицы серверов («DDNS hostname»)"
        return result
    end = text.find("</table>", marker)
    complete = end >= 0
    table = text[start: end if complete else len(text)]
    rows = [row for row in _VG_ROW.findall(table) if "vg_table_row" in row]
    if not rows:
        result.detail = "в таблице нет строк серверов"
        return result
    if len(rows) > MAX_ROWS:
        result.status = Status.RESOURCE_LIMIT
        result.detail = f"строк больше {MAX_ROWS}"
        return result
    reasons: Counter[str] = Counter()
    seen: set[tuple[str, int]] = set()
    for row in rows:
        cells = _VG_CELL.findall(row)
        if len(cells) != 10:
            reasons["строка не из 10 ячеек"] += 1
            continue
        flag = _VG_FLAG.search(cells[0])
        country = flag.group(1) if flag else ""
        names = _cell_lines(cells[1])
        host = _host(names[0]) if names else ""
        address = _ipv4(names[1]) if len(names) > 1 else ""
        if not host or "." not in host or not address:
            reasons["нет имени или адреса сервера"] += 1
            continue
        port, why = _sstp_endpoint(cells[7], host)
        if why:
            reasons[why] += 1
            continue
        if (host, port) in seen:
            reasons["повтор"] += 1
            continue
        seen.add((host, port))
        sessions, quality = _cell_lines(cells[2]), _cell_lines(cells[3])
        speed = _number(quality[0]) if quality else 0.0
        ping = next((_number(line) for line in quality if line.startswith("Ping")), 0.0)
        hints = (
            ("ping_ms", str(int(ping))),
            ("speed_mbps", f"{speed:.1f}"),
            ("score", str(int(_number(" ".join(_cell_lines(cells[9])))))),
            ("sessions", str(int(_number(sessions[0])) if sessions else 0)),
            ("uptime_days", str(int(_number(sessions[1])) if len(sessions) > 1
                                and "day" in sessions[1] else 0)),
        )
        result.variants.append(Variant(
            provider=VPNGATE, backend=Backend.SSTP, protocol="sstp", host=host,
            address=address, port=port, transport="tcp",
            name=f"VPN Gate {country} {host.split('.', 1)[0][:32]}",
            country_hint=country, access=Access.FREE, hints=hints, source_url=url,
        ))
    result.rejected = sum(reasons.values())
    result.rejections = dict(reasons)
    result.complete_response = complete
    result.authoritative = False
    result.status = Status.SUCCESS if complete else Status.PARTIAL
    if not complete:
        result.detail = "нет конца таблицы серверов — документ обрезан"
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
