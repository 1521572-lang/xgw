"""trojan:// — пароль в userinfo, остальные параметры как у vless."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlsplit

from .common import ParseError, RawServer, build_stream, single

KNOWN = {
    "type", "security", "sni", "fp", "alpn", "allowInsecure", "insecure",
    "host", "path", "serviceName", "mode", "pbk", "sid", "headerType", "flow",
}


def parse(link: str) -> RawServer:
    try:
        parts = urlsplit(link)
    except ValueError as exc:
        raise ParseError(f"trojan: битая ссылка ({exc})") from exc
    password = unquote(parts.username or "")
    if not password:
        raise ParseError("trojan: нет пароля")
    host = (parts.hostname or "").lower()
    if not host:
        raise ParseError("trojan: нет адреса")
    if parts.port is None:
        raise ParseError("trojan: нет порта")
    port = parts.port

    query = parse_qs(parts.query, keep_blank_values=True)
    name = unquote(parts.fragment) or f"{host}:{port}"
    warnings = [f"неизвестный параметр trojan: {key}" for key in query if key not in KNOWN]
    if single(query, "flow"):
        warnings.append("trojan: параметр flow игнорируется (у trojan-outbound нет flow)")

    net = single(query, "type", "tcp")
    security = single(query, "security")
    if not security:
        # trojan почти всегда работает поверх TLS
        security = "reality" if single(query, "pbk") else "tls"
    stream, transport = build_stream(net, security, query, warnings)
    outbound = {
        "protocol": "trojan",
        "settings": {"servers": [{"address": host, "port": port, "password": password}]},
        "streamSettings": stream,
    }
    return RawServer(
        name=name,
        protocol="trojan",
        address=host,
        port=port,
        credential=password,
        transport=transport,
        outbound=outbound,
        warnings=warnings,
    )
