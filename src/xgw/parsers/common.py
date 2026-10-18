"""Общий код парсеров: ошибки, base64, адреса, построение streamSettings,
разбор тел подписок (base64/plain/JSON) и метаданных «#key: value»."""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass, field
from urllib.parse import SplitResult, unquote, urlsplit


class ParseError(Exception):
    """Понятная ошибка разбора ссылки или подписки."""


class UnsupportedLink(ParseError):
    """Схема или формат не поддерживается (пропускается с предупреждением)."""


@dataclass
class SingboxSpec:
    """Сервер так, как его описывает sing-box (generator/singbox.py).

    main — outbound без тега: type, server, server_port и остальные поля sing-box. У WireGuard
    это endpoint (endpoint = True), а не outbound. extra — вспомогательные звенья цепочки
    (shadowtls для Shadowsocks), у каждого локальный «tag»; main["detour"] ссылается на него.
    """

    main: dict
    endpoint: bool = False
    extra: list[dict] = field(default_factory=list)


@dataclass
class RawServer:
    name: str
    protocol: str
    address: str
    port: int
    credential: str
    transport: str
    # Описание для Xray; пустое — сервер умеет только sing-box (hysteria2, TUIC, AnyTLS…).
    outbound: dict
    warnings: list[str] = field(default_factory=list)
    # False — узел распознан, но не включается в конфиг (например, ссылка без поддержки
    # ни в Xray, ни в sing-box).
    supported: bool = True
    keep_tag: str | None = None
    # Описание для sing-box; None — сервер умеет только Xray (xhttp, цепочки dialerProxy…).
    singbox: SingboxSpec | None = None


def b64_decode(data: str) -> bytes:
    """base64 обычный и URL-safe, с добивкой «=»."""
    compact = re.sub(r"\s+", "", data)
    try:
        compact.encode("ascii")
    except UnicodeEncodeError as exc:
        raise binascii.Error("не base64: не-ASCII символы") from exc
    standard = compact.replace("-", "+").replace("_", "/")
    padded = standard + "=" * (-len(standard) % 4)
    return base64.b64decode(padded, validate=True)


def split_host_port(text: str) -> tuple[str, int]:
    if text.startswith("["):
        host, _, rest = text[1:].partition("]")
        if not host or not rest.startswith(":") or not rest[1:].isdigit():
            raise ParseError(f"неверный адрес: {text}")
        return host.lower(), int(rest[1:])
    host, _, port_s = text.rpartition(":")
    if not host or not port_s.isdigit():
        raise ParseError(f"неверный адрес: {text}")
    return host.lower(), int(port_s)


def split_link(link: str, label: str) -> tuple[SplitResult, str, int | None]:
    """urlsplit с понятными ошибками: (части, адрес, порт или None).

    Текст исключения urlsplit в сообщение не попадает: в нём бывает netloc
    целиком, то есть UUID или пароль.
    """
    try:
        parts = urlsplit(link)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError as exc:
        raise ParseError(f"{label}: битая ссылка (неверный адрес или порт)") from exc
    if not host:
        raise ParseError(f"{label}: нет адреса")
    return parts, host, port


def normalize_pin(text: str) -> str:
    """SHA-256 открытого ключа сервера (параметр pks) в записи sing-box — base64; пусто, если
    это не хеш. Принимается hex (64 символа) и base64 (обычный или URL-safe, с «=» или без).
    «+» из base64, не закодированный в ссылке как %2B, разбор запроса превращает в пробел —
    внутри значения пробел возвращается в «+»."""
    text = text.replace(" ", "+").strip()
    if re.fullmatch(r"[0-9a-fA-F]{64}", text):
        return base64.b64encode(bytes.fromhex(text)).decode("ascii")
    try:
        raw = b64_decode(text)
    except (binascii.Error, ValueError):
        return ""
    return base64.b64encode(raw).decode("ascii") if len(raw) == 32 else ""


def single(query: dict[str, list[str]], key: str, default: str = "") -> str:
    values = query.get(key)
    if not values:
        return default
    return values[0]


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes")


# --- построение streamSettings (vless / trojan / vmess) ------------------------

_NETWORKS = {
    "tcp": "tcp",
    "raw": "tcp",
    "ws": "ws",
    "grpc": "grpc",
    "xhttp": "xhttp",
    "splithttp": "xhttp",
    "httpupgrade": "httpupgrade",
    "kcp": "kcp",
    "mkcp": "kcp",
    "h2": "h2",
    "http": "h2",
}


def build_stream(
    net: str, security: str, query: dict[str, list[str]], warnings: list[str]
) -> tuple[dict, str]:
    """Собирает streamSettings из параметров ссылки. Спорные случаи — как в v2rayN."""
    requested = (net or "tcp").lower()
    net = _NETWORKS.get(requested)
    if net is None:
        warnings.append(f"неизвестный транспорт {requested!r}, используется tcp")
        net = "tcp"
    stream: dict = {"network": net}

    if net == "tcp":
        if single(query, "headerType").lower() == "http":
            host = single(query, "host")
            stream["tcpSettings"] = {
                "header": {
                    "type": "http",
                    "request": {
                        "version": "1.1",
                        "method": "GET",
                        "path": [single(query, "path", "/")],
                        "headers": {"Host": [host] if host else []},
                    },
                }
            }
    elif net == "ws":
        ws: dict = {"path": single(query, "path", "/") or "/"}
        host = single(query, "host")
        if host:
            # Отдельное поле host: запись headers.Host Xray объявил устаревшей
            # («will be removed soon»), а версия по умолчанию — latest.
            ws["host"] = host
        stream["wsSettings"] = ws
    elif net == "grpc":
        grpc: dict = {"serviceName": single(query, "serviceName")}
        if single(query, "mode") == "multi":
            grpc["multiMode"] = True
        if single(query, "authority"):
            grpc["authority"] = single(query, "authority")
        stream["grpcSettings"] = grpc
    elif net == "xhttp":
        xhttp: dict = {}
        if single(query, "path"):
            xhttp["path"] = single(query, "path")
        if single(query, "host"):
            xhttp["host"] = single(query, "host")
        if single(query, "mode"):
            xhttp["mode"] = single(query, "mode")
        extra = single(query, "extra")
        if extra:
            try:
                xhttp["extra"] = json.loads(extra)
            except json.JSONDecodeError:
                warnings.append("xhttp: параметр extra не JSON — пропущен")
        stream["xhttpSettings"] = xhttp
    elif net == "httpupgrade":
        upgrade: dict = {"path": single(query, "path", "/") or "/"}
        if single(query, "host"):
            upgrade["host"] = single(query, "host")
        stream["httpupgradeSettings"] = upgrade
    elif net == "kcp":
        kcp: dict = {"header": {"type": single(query, "headerType", "none") or "none"}}
        seed = single(query, "seed") or single(query, "path")
        if seed:
            kcp["seed"] = seed
        stream["kcpSettings"] = kcp
    elif net == "h2":
        h2: dict = {}
        if single(query, "path"):
            h2["path"] = single(query, "path")
        if single(query, "host"):
            h2["host"] = [single(query, "host")]
        stream["httpSettings"] = h2

    security = (security or "none").lower()
    if security == "tls":
        tls: dict = {}
        # Как в v2rayN: без sni именем сервера становится host транспорта —
        # иначе узел «IP-адрес + CDN-домен в host» не пройдёт проверку сертификата.
        sni = single(query, "sni") or single(query, "host").split(",")[0].strip()
        if sni:
            tls["serverName"] = sni
        if single(query, "fp"):
            tls["fingerprint"] = single(query, "fp")
        if single(query, "alpn"):
            tls["alpn"] = [item for item in single(query, "alpn").split(",") if item]
        # Xray 26.10.10 убрал allowInsecure: конфиг с ним он не принимает, и сервер выпал бы.
        # Замена — закрепить сертификат сервера (pcs, SHA-256 сертификата) или сверять его
        # с другим именем (vcn). Без них сертификат проверяется обычным порядком.
        if single(query, "pcs"):
            tls["pinnedPeerCertSha256"] = single(query, "pcs")
        if single(query, "vcn"):
            tls["verifyPeerCertByName"] = single(query, "vcn")
        # pks — SHA-256 открытого ключа сервера для sing-box (у Xray закрепляется хеш всего
        # сертификата, pcs; друг в друга они не переводятся). Xray поле не видит: builder
        # убирает его из конфига; без pks сервер с pcs остаётся только у Xray (convert.py).
        if single(query, "pks"):
            pin = normalize_pin(single(query, "pks"))
            if pin:
                tls["xgwSingboxPin"] = pin
            else:
                warnings.append("pks — не SHA-256 (hex или base64): параметр пропущен")
        insecure = _truthy(single(query, "allowInsecure")) or _truthy(single(query, "insecure"))
        if insecure and not single(query, "pcs"):
            warnings.append(
                "allowInsecure не поддерживается Xray 26.10.10: сертификат сервера проверяется "
                "(закрепить свой — параметр pcs)"
            )
        stream["security"] = "tls"
        stream["tlsSettings"] = tls
    elif security == "reality":
        reality: dict = {}
        if single(query, "sni"):
            reality["serverName"] = single(query, "sni")
        if single(query, "fp"):
            reality["fingerprint"] = single(query, "fp")
        if single(query, "pbk"):
            reality["publicKey"] = single(query, "pbk")
        if single(query, "sid"):
            reality["shortId"] = single(query, "sid")
        if single(query, "spx"):
            reality["spiderX"] = single(query, "spx")
        stream["security"] = "reality"
        stream["realitySettings"] = reality
    elif security not in ("", "none"):
        warnings.append(f"неизвестный security={security!r}, используется none")
        security = "none"
    return stream, f"{net}/{security}"


# --- разбор ссылок -------------------------------------------------------------


def parse_link(link: str) -> RawServer:
    scheme, sep, _ = link.partition("://")
    if not sep:
        raise ParseError("строка не похожа на ссылку сервера")
    scheme = scheme.lower()
    if scheme == "vless":
        from .vless import parse
    elif scheme == "vmess":
        from .vmess import parse
    elif scheme == "trojan":
        from .trojan import parse
    elif scheme == "ss":
        from .ss import parse
    elif scheme in ("hysteria2", "hy2"):
        from .hysteria2 import parse
    elif scheme == "tuic":
        from .tuic import parse
    elif scheme == "anytls":
        from .anytls import parse
    elif scheme in ("wireguard", "wg"):
        from .wireguard import parse
    elif scheme == "socks":
        parse = _parse_socks
    else:
        raise UnsupportedLink(f"схема {scheme}:// не поддерживается")
    raw = parse(link)
    if raw.singbox is None and raw.outbound:
        # Сервер, который умеют оба ядра, получает и описание для sing-box (convert.py).
        from . import convert

        raw.singbox = convert.to_singbox(raw.outbound)
    return raw


def _parse_socks(link: str) -> RawServer:
    parts, host, port = split_link(link, "socks")
    if port is None:
        raise ParseError("socks: нет порта")
    name = unquote(parts.fragment) or f"{host}:{port}"
    users: list[dict] = []
    userinfo = unquote(parts.username or "")
    if parts.password is not None:
        userinfo += f":{unquote(parts.password)}"
    if userinfo:
        try:
            decoded = b64_decode(userinfo).decode("utf-8")
            user, _, password = decoded.partition(":")
        except (binascii.Error, UnicodeDecodeError):
            user, _, password = userinfo.partition(":")
        users.append({"user": user, "pass": password})
    outbound = {
        "protocol": "socks",
        "settings": {"servers": [{"address": host, "port": port, "users": users}]},
    }
    credential = users[0]["user"] if users else ""
    return RawServer(name, "socks", host, port, credential, "tcp/none", outbound)


# --- разбор тел подписок -------------------------------------------------------


_META_RE = re.compile(r"^#\s*([A-Za-z0-9_-]+)\s*:\s*(.*)$")


def parse_body(raw: bytes | str, source: str = "manual") -> tuple[list[RawServer], dict, list[str]]:
    """base64 (обычный/URL-safe), plain-текст или JSON полных конфигов Xray."""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    text = text.lstrip("\ufeff").strip()
    if not text:
        return [], {}, [f"{source}: пустой ответ подписки"]
    if text[0] in "{[":
        return _parse_json_body(text, source)
    if re.search(r"(?m)^\s*(proxies|proxy-groups)\s*:", text):
        raise ParseError(f"{source}: формат Clash не поддерживается")
    decoded = _try_b64_text(text)
    if decoded is not None:
        text = decoded
    return parse_links_text(text, source)


def _try_b64_text(text: str) -> str | None:
    if "://" in text:
        return None
    try:
        decoded = b64_decode(text).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
    return decoded if "://" in decoded else None


def parse_links_text(text: str, source: str = "manual") -> tuple[list[RawServer], dict, list[str]]:
    servers: list[RawServer] = []
    warnings: list[str] = []
    meta: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = _META_RE.match(line)
        if match:
            meta[match.group(1).lower()] = match.group(2).strip()
            continue
        if "://" not in line:
            continue
        try:
            raw = parse_link(line)
        except UnsupportedLink as exc:
            warnings.append(f"{source}: пропуск ({exc})")
            continue
        except (ParseError, ValueError) as exc:
            warnings.append(f"{source}: {exc}")
            continue
        if not raw.supported:
            reason = raw.warnings[-1] if raw.warnings else "не поддерживается"
            warnings.append(f"{source}: узел «{raw.name}» пропущен: {reason}")
            continue
        servers.append(raw)
        warnings.extend(f"{source}/{raw.name}: {warning}" for warning in raw.warnings)
    if not servers and not meta:
        warnings.append(f"{source}: ссылок не найдено")
    return servers, meta, warnings


def _parse_json_body(text: str, source: str) -> tuple[list[RawServer], dict, list[str]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(f"{source}: битый JSON ({exc})") from exc
    configs = data if isinstance(data, list) else [data]
    if not all(isinstance(item, dict) for item in configs):
        raise ParseError(f"{source}: неожиданная структура JSON-подписки")
    servers: list[RawServer] = []
    warnings: list[str] = []
    for config in configs:
        from . import sbjson, xray_json

        if sbjson.looks_like_singbox(config) or (
            "outbounds" not in config and sbjson.is_singbox_item(config)
        ):
            got, got_warnings = sbjson.parse_config(config, source)
            servers.extend(got)
            warnings.extend(got_warnings)
            continue
        outbounds = config.get("outbounds")
        if not isinstance(outbounds, list):
            raise ParseError(
                f"{source}: JSON без outbounds — не похоже на конфиг Xray или sing-box"
            )
        remarks = config.get("remarks")
        got, got_warnings = xray_json.parse_outbounds(
            outbounds, source, remarks=remarks if isinstance(remarks, str) else ""
        )
        servers.extend(got)
        warnings.extend(got_warnings)
    return servers, {}, warnings
