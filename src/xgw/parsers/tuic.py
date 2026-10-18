"""tuic:// — TUIC v5, сервер ведёт sing-box.

В Xray 26.10.10 TUIC нет: «unknown config id: tuic» (проверено).
"""

from __future__ import annotations

from urllib.parse import unquote

from .common import ParseError, RawServer
from .sblink import host_ports, single, spec, split_link, tls_block, truthy

CONGESTION = ("bbr", "cubic", "new_reno")
RELAY_MODES = ("native", "quic")


def parse(link: str) -> RawServer:
    userinfo, hostport, _path, query, name = split_link(link, "tuic")
    host, port, _ranges = host_ports(hostport, "tuic")
    uuid, _, password = userinfo.partition(":")
    uuid, password = unquote(uuid), unquote(password)
    if not uuid:
        raise ParseError("tuic: нет UUID")
    warnings: list[str] = []
    body: dict = {
        "type": "tuic", "server": host, "server_port": port, "uuid": uuid,
        "tls": tls_block(host, query, warnings, "tuic", alpn=("h3",)),
    }
    if password:
        body["password"] = password
    congestion = (
        single(query, "congestion_control") or single(query, "congestion-control")
    ).lower()
    if congestion:
        if congestion not in CONGESTION:
            warnings.append(f"tuic: congestion_control={congestion} неизвестен — пропущен")
        else:
            body["congestion_control"] = congestion
    relay = (single(query, "udp_relay_mode") or single(query, "udp-relay-mode")).lower()
    if relay:
        if relay not in RELAY_MODES:
            warnings.append(f"tuic: udp_relay_mode={relay} неизвестен — пропущен")
        else:
            body["udp_relay_mode"] = relay
    if truthy(single(query, "reduce_rtt") or single(query, "zero_rtt_handshake")):
        body["zero_rtt_handshake"] = True
    return RawServer(
        name=name or f"{host}:{port}",
        protocol="tuic",
        address=host,
        port=port,
        credential=uuid,
        transport="udp/tls",
        outbound={},
        warnings=warnings,
        singbox=spec(body),
    )
