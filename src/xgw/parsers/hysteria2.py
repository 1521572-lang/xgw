"""hysteria2:// и hy2:// — сервер, который ведёт sing-box.

В Xray 26.10.10 hysteria2-outbound'а нет (проверено: «unknown config id: hysteria2»), поэтому узел
описывается только для sing-box (generator/singbox.py). Поддержаны obfs salamander, смена портов
(`mport` и «443,20000-30000» в адресе), ограничения скорости upmbps/downmbps.
"""

from __future__ import annotations

from .common import ParseError, RawServer
from .sblink import host_ports, mbps, port_ranges, single, spec, split_link, tls_block


def parse(link: str) -> RawServer:
    userinfo, hostport, _path, query, name = split_link(link, "hysteria2")
    host, port, ranges = host_ports(hostport, "hysteria2", default_port=443)
    password = userinfo
    if not password:
        raise ParseError("hysteria2: нет пароля")
    warnings: list[str] = []
    if single(query, "mport"):
        ranges = [*ranges, *port_ranges(single(query, "mport"), "hysteria2")]
    body: dict = {
        "type": "hysteria2", "server": host, "server_port": port, "password": password,
        "tls": tls_block(host, query, warnings, "hysteria2", alpn=("h3",)),
    }
    if ranges:
        body["server_ports"] = list(dict.fromkeys(ranges))
    obfs = single(query, "obfs")
    if obfs:
        if obfs.lower() != "salamander":
            raise ParseError(f"hysteria2: obfs={obfs} не поддерживается (нужен salamander)")
        body["obfs"] = {"type": "salamander", "password": single(query, "obfs-password")}
        if not body["obfs"]["password"]:
            raise ParseError("hysteria2: obfs=salamander без obfs-password")
    up = mbps(single(query, "upmbps") or single(query, "up"))
    down = mbps(single(query, "downmbps") or single(query, "down"))
    if up:
        body["up_mbps"] = up
    if down:
        body["down_mbps"] = down
    return RawServer(
        name=name or f"{host}:{port}",
        protocol="hysteria2",
        address=host,
        port=port,
        credential=password,
        transport="udp/none",
        outbound={},
        warnings=warnings,
        singbox=spec(body),
    )
