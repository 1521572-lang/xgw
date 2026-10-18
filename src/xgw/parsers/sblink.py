"""Общее для ссылок серверов, которые ведёт только sing-box: hysteria2://, tuic://, anytls://,
wireguard://. Серверы с такими ссылками Xray не умеет (generator/singbox.py ведёт их вторым ядром).

Проверка сертификата здесь не отключается никогда: `insecure`/`allow_insecure` из ссылки в
sing-box не переносятся, а закрепление сертификата в виде pinSHA256 (хеш всего сертификата) у
sing-box записать нечем — у него хеш открытого ключа. Сервер с самоподписанным сертификатом
поэтому не заработает, а причину покажет предупреждение.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import parse_qs, unquote

from .common import ParseError, SingboxSpec, normalize_pin, single

_RANGE_RE = re.compile(r"(\d{1,5})(?:-(\d{1,5}))?")
DEFAULT_FINGERPRINT = "chrome"


def truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def split_link(link: str, label: str) -> tuple[str, str, str, dict[str, list[str]], str]:
    """(userinfo, адрес и порты, путь, параметры, имя) — без разбора портов: у hysteria2 их
    бывает несколько («443,20000-30000»), и urlsplit с таким адресом справиться не может."""
    rest = link.partition("://")[2]
    rest, _, fragment = rest.partition("#")
    rest, _, query_text = rest.partition("?")
    authority, _, path = rest.partition("/")
    userinfo, at, hostport = authority.rpartition("@")
    if not at:
        userinfo, hostport = "", authority
    if not hostport:
        raise ParseError(f"{label}: нет адреса")
    query = parse_qs(query_text, keep_blank_values=True)
    return unquote(userinfo), hostport, path, query, unquote(fragment)


def host_ports(
    hostport: str, label: str, default_port: int | None = None,
) -> tuple[str, int, list[str]]:
    """Адрес, основной порт и диапазоны портов в записи sing-box («20000:30000»).

    «host:443», «host:443,20000-30000» (порт и диапазон для смены портов), «[::1]:443»."""
    if hostport.startswith("["):
        host, _, rest = hostport[1:].partition("]")
        ports_text = rest[1:] if rest.startswith(":") else ""
    else:
        host, sep, ports_text = hostport.rpartition(":")
        if not sep:
            host, ports_text = hostport, ""
    host = host.strip().lower()
    if not host:
        raise ParseError(f"{label}: нет адреса")
    if not ports_text:
        if default_port is None:
            raise ParseError(f"{label}: нет порта")
        return host, default_port, []
    port: int | None = None
    ranges: list[str] = []
    for part in ports_text.split(","):
        match = _RANGE_RE.fullmatch(part.strip())
        if not match:
            raise ParseError(f"{label}: неверный порт «{part}»")
        low = int(match.group(1))
        high = int(match.group(2) or low)
        if not (0 < low <= high < 65536):
            raise ParseError(f"{label}: порт вне диапазона «{part}»")
        if port is None:
            port = low
        if high != low:
            ranges.append(f"{low}:{high}")
    assert port is not None
    return host, port, ranges


def port_ranges(text: str, label: str) -> list[str]:
    """Диапазоны из параметра mport: «20000-30000» или «443,20000-30000»."""
    result: list[str] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        match = _RANGE_RE.fullmatch(part)
        if not match:
            raise ParseError(f"{label}: неверный mport «{part}»")
        low, high = int(match.group(1)), int(match.group(2) or match.group(1))
        if not (0 < low <= high < 65536):
            raise ParseError(f"{label}: mport вне диапазона «{part}»")
        if high != low:
            result.append(f"{low}:{high}")
    return result


def is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def tls_block(
    host: str, query: dict[str, list[str]], warnings: list[str], label: str,
    *, alpn: tuple[str, ...] = (), utls: bool = False,
) -> dict:
    """tls-часть outbound'а sing-box: имя сервера, ALPN, при utls — отпечаток uTLS."""
    tls: dict = {"enabled": True}
    sni = single(query, "sni") or single(query, "peer") or single(query, "serverName")
    if sni:
        tls["server_name"] = sni
    elif not is_ip(host):
        tls["server_name"] = host
    wanted = [item for item in single(query, "alpn").split(",") if item] or list(alpn)
    if wanted:
        tls["alpn"] = wanted
    if utls:
        tls["utls"] = {"enabled": True, "fingerprint": single(query, "fp") or DEFAULT_FINGERPRINT}
    insecure = (
        truthy(single(query, "insecure")) or truthy(single(query, "allowInsecure"))
        or truthy(single(query, "allow_insecure")) or truthy(single(query, "skip-cert-verify"))
    )
    if insecure:
        warnings.append(
            f"{label}: insecure не поддерживается — сертификат сервера проверяется; сервер с "
            "самоподписанным сертификатом не подключится"
        )
    pin = normalize_pin(single(query, "pks"))
    if pin:
        tls["certificate_public_key_sha256"] = [pin]
    elif single(query, "pks"):
        warnings.append(f"{label}: pks — не SHA-256 открытого ключа (hex или base64): пропущен")
    if single(query, "pinSHA256") and not pin:
        warnings.append(
            f"{label}: pinSHA256 (хеш сертификата) в sing-box записать нечем — параметр "
            "пропущен, сертификат проверяется обычным порядком; закрепить свой сертификат "
            "можно параметром pks (SHA-256 открытого ключа, base64)"
        )
    return tls


def spec(main: dict, *, endpoint: bool = False, extra: list[dict] | None = None) -> SingboxSpec:
    return SingboxSpec(main=main, endpoint=endpoint, extra=extra or [])


def mbps(text: str) -> int | None:
    """«100», «100 mbps» → 100; пусто или не число — None."""
    match = re.match(r"\s*(\d+)", text or "")
    return int(match.group(1)) if match else None
