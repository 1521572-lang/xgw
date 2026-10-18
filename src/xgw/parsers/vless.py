"""vless:// — параметры по стандарту share-link XTLS; спорные случаи как в v2rayN."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote

from .common import ParseError, RawServer, build_stream, single, split_link

KNOWN = {
    "type", "security", "encryption", "flow", "headerType", "host", "path",
    "serviceName", "mode", "authority", "sni", "fp", "alpn", "pbk", "sid", "spx",
    "allowInsecure", "insecure", "pcs", "vcn", "pks", "extra", "seed",
}


def parse(link: str) -> RawServer:
    parts, host, port = split_link(link, "vless")
    user = unquote(parts.username or "")
    if not user:
        raise ParseError("vless: нет UUID")
    if port is None:
        raise ParseError("vless: нет порта")

    query = parse_qs(parts.query, keep_blank_values=True)
    name = unquote(parts.fragment) or f"{host}:{port}"
    warnings = [f"неизвестный параметр vless: {key}" for key in query if key not in KNOWN]

    net = single(query, "type", "tcp")
    security = single(query, "security")
    if not security:
        security = "reality" if single(query, "pbk") else "none"
    stream, transport = build_stream(net, security, query, warnings)

    user_obj: dict = {"id": user, "encryption": single(query, "encryption", "none") or "none"}
    flow = single(query, "flow")
    if flow:
        user_obj["flow"] = flow
    outbound = {
        "protocol": "vless",
        "settings": {"vnext": [{"address": host, "port": port, "users": [user_obj]}]},
        "streamSettings": stream,
    }
    return RawServer(
        name=name,
        protocol="vless",
        address=host,
        port=port,
        credential=user,
        transport=transport,
        outbound=outbound,
        warnings=warnings,
    )
