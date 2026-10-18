"""wireguard:// (и wg://) — WireGuard, сервер ведёт sing-box как endpoint.

Ссылка: wireguard://<приватный ключ>@host:port?publickey=…&address=10.0.0.2/32,fd00::2/128
&mtu=1280&reserved=1,2,3&presharedkey=…#имя. Параметры AmneziaWG (jc, jmin, jmax, s1, s2, h1…h4)
официальный sing-box не знает — такая ссылка пропускается с пояснением, а не подключается как
обычный WireGuard (сервер с обфускацией его не примет).
"""

from __future__ import annotations

import ipaddress
import re

from .common import ParseError, RawServer, UnsupportedLink
from .sblink import host_ports, single, spec, split_link

_AMNEZIA = {
    "jc", "jmin", "jmax", "s1", "s2", "s3", "s4", "h1", "h2", "h3", "h4", "i1", "i2", "i3", "i4",
    "i5",
}
_KEY_RE = re.compile(r"[A-Za-z0-9+/_-]{43}=?")


def _key(text: str, label: str) -> str:
    text = text.strip().replace("-", "+").replace("_", "/")
    if not _KEY_RE.fullmatch(text):
        raise ParseError(f"wireguard: {label} — не ключ WireGuard (44 символа base64)")
    return text if text.endswith("=") else text + "="


def parse(link: str) -> RawServer:
    userinfo, hostport, _path, query, name = split_link(link, "wireguard")
    host, port, _ranges = host_ports(hostport, "wireguard")
    if any(key in query for key in _AMNEZIA):
        raise UnsupportedLink(
            "wireguard: параметры AmneziaWG (jc, s1, h1…) официальный sing-box не поддерживает"
        )
    private_key = _key(userinfo, "приватный ключ")
    public_key = _key(
        single(query, "publickey") or single(query, "public_key") or single(query, "peer"),
        "publickey",
    )
    addresses = []
    for item in (single(query, "address") or single(query, "ip")).split(","):
        item = item.strip()
        if not item:
            continue
        try:
            addresses.append(str(ipaddress.ip_interface(item)))
        except ValueError as exc:
            raise ParseError(f"wireguard: неверный address «{item}»") from exc
    if not addresses:
        raise ParseError("wireguard: нет address (локальный адрес интерфейса)")
    peer: dict = {
        "address": host, "port": port, "public_key": public_key,
        "allowed_ips": ["0.0.0.0/0", "::/0"],
    }
    shared = single(query, "presharedkey") or single(query, "pre_shared_key")
    if shared:
        peer["pre_shared_key"] = _key(shared, "presharedkey")
    reserved_text = single(query, "reserved")
    if reserved_text:
        try:
            reserved = [int(item) for item in reserved_text.split(",")]
        except ValueError as exc:
            raise ParseError("wireguard: reserved — три числа через запятую") from exc
        if len(reserved) != 3 or not all(0 <= item < 256 for item in reserved):
            raise ParseError("wireguard: reserved — три числа 0–255")
        peer["reserved"] = reserved
    body: dict = {
        "type": "wireguard", "address": addresses, "private_key": private_key, "peers": [peer],
    }
    if single(query, "mtu").isdigit():
        body["mtu"] = int(single(query, "mtu"))
    return RawServer(
        name=name or f"{host}:{port}",
        protocol="wireguard",
        address=host,
        port=port,
        credential=private_key,
        transport="udp/wg",
        outbound={},
        warnings=[],
        singbox=spec(body, endpoint=True),
    )
