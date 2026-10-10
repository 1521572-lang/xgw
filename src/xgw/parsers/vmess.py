"""vmess:// — base64(JSON) по формату v2rayN."""

from __future__ import annotations

import json

from .common import ParseError, RawServer, build_stream


def parse(link: str) -> RawServer:
    from .common import b64_decode

    try:
        payload = b64_decode(link[len("vmess://") :]).decode("utf-8")
        data = json.loads(payload)
    except Exception as exc:
        raise ParseError(f"vmess: не удалось декодировать JSON ({exc.__class__.__name__})") from exc
    if not isinstance(data, dict) or "add" not in data or "id" not in data:
        raise ParseError("vmess: в JSON нет полей add/id")

    address = str(data.get("add", "")).lower()
    try:
        port = int(data.get("port", 0))
    except (TypeError, ValueError):
        port = 0
    if not address or port <= 0:
        raise ParseError("vmess: неверный адрес или порт")
    name = str(data.get("ps") or f"{address}:{port}")

    net = str(data.get("net") or "tcp")
    security = "tls" if str(data.get("tls") or "").lower() == "tls" else "none"
    query: dict[str, list[str]] = {}
    for target, source_key in (
        ("headerType", "type"),
        ("host", "host"),
        ("path", "path"),
        ("sni", "sni"),
        ("fp", "fp"),
        ("alpn", "alpn"),
    ):
        value = data.get(source_key)
        if value not in (None, ""):
            query[target] = [str(value)]
    if net == "grpc":
        # v2rayN хранит serviceName для grpc в поле path
        query["serviceName"] = [str(data.get("path") or "")]

    warnings: list[str] = []
    stream, transport = build_stream(net, security, query, warnings)
    try:
        alter_id = int(data.get("aid") or 0)
    except (TypeError, ValueError):
        alter_id = 0
    user = {
        "id": str(data["id"]),
        "alterId": alter_id,
        "security": str(data.get("scy") or "auto"),
    }
    outbound = {
        "protocol": "vmess",
        "settings": {"vnext": [{"address": address, "port": port, "users": [user]}]},
        "streamSettings": stream,
    }
    return RawServer(
        name=name,
        protocol="vmess",
        address=address,
        port=port,
        credential=str(data["id"]),
        transport=transport,
        outbound=outbound,
        warnings=warnings,
    )
