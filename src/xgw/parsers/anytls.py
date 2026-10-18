"""anytls:// — AnyTLS, сервер ведёт sing-box (в Xray 26.10.10 AnyTLS нет: «unknown config id»)."""

from __future__ import annotations

from .common import ParseError, RawServer
from .sblink import host_ports, spec, split_link, tls_block


def parse(link: str) -> RawServer:
    userinfo, hostport, _path, query, name = split_link(link, "anytls")
    host, port, _ranges = host_ports(hostport, "anytls", default_port=443)
    if not userinfo:
        raise ParseError("anytls: нет пароля")
    warnings: list[str] = []
    body: dict = {
        "type": "anytls", "server": host, "server_port": port, "password": userinfo,
        "tls": tls_block(host, query, warnings, "anytls", utls=True),
    }
    return RawServer(
        name=name or f"{host}:{port}",
        protocol="anytls",
        address=host,
        port=port,
        credential=userinfo,
        transport="tcp/tls",
        outbound={},
        warnings=warnings,
        singbox=spec(body),
    )
