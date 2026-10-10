"""Клиент стенда — «устройство в Wi-Fi»: то, что на настоящей машине делают
curl, dig и DHCP-клиент. Обычные сокеты, только стандартная библиотека.

  lan_client.py get <url> [--dns СЕРВЕР] [--bind IP] [--mark N] [--timeout С]
  lan_client.py dns <сервер> <имя> [--tcp] [--bind IP] [--timeout С]
  lan_client.py dhcp <интерфейс> [--mac MAC] [--timeout С]

Печатает одну строку JSON; при сбое в ней есть поле "error".
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import struct
import time
from pathlib import Path
from urllib.parse import urlsplit

SO_MARK = 36
SO_BINDTODEVICE = 25
DHCP_MAGIC = b"\x63\x82\x53\x63"


def _dns_query(name: str) -> bytes:
    labels = b"".join(bytes([len(part)]) + part.encode("ascii") for part in name.split("."))
    return os.urandom(2) + struct.pack(">HHHHH", 0x0100, 1, 0, 0, 0) + labels + b"\0\0\x01\0\x01"


def _dns_addresses(reply: bytes) -> list[str]:
    """A-записи ответа (имена в ответах заглушки и Xray сжаты указателем)."""
    count = struct.unpack(">H", reply[6:8])[0]
    offset = 12
    while reply[offset]:
        offset += reply[offset] + 1
    offset += 5
    addresses = []
    for _ in range(count):
        if reply[offset] & 0xC0 == 0xC0:
            offset += 2
        else:
            while reply[offset]:
                offset += reply[offset] + 1
            offset += 1
        rtype, _cls, _ttl, size = struct.unpack(">HHIH", reply[offset : offset + 10])
        offset += 10
        if rtype == 1 and size == 4:
            addresses.append(socket.inet_ntoa(reply[offset : offset + 4]))
        offset += size
    return addresses


def resolve(server: str, name: str, *, tcp: bool = False, bind: str = "",
            timeout: float = 5.0) -> tuple[list[str], str]:
    """(адреса, от кого пришёл ответ)."""
    query = _dns_query(name)
    kind = socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM
    with socket.socket(socket.AF_INET, kind) as sock:
        if bind:
            sock.bind((bind, 0))
        sock.settimeout(timeout)
        if tcp:
            sock.connect((server, 53))
            sock.sendall(struct.pack(">H", len(query)) + query)
            size = struct.unpack(">H", sock.recv(2))[0]
            reply, peer = sock.recv(size), sock.getpeername()
        else:
            sock.sendto(query, (server, 53))
            while True:
                reply, peer = sock.recvfrom(4096)
                if reply[:2] == query[:2]:
                    break
    return _dns_addresses(reply), peer[0]


def do_dns(args) -> dict:
    addresses, peer = resolve(
        args.server, args.name, tcp=args.tcp, bind=args.bind, timeout=args.timeout
    )
    return {"answers": addresses, "from": peer}


def do_get(args) -> dict:
    url = urlsplit(args.url)
    host, port = url.hostname or "", url.port or 80
    try:
        ipaddress.ip_address(host)
        address = host
    except ValueError:
        if not args.dns:
            raise ValueError("для имени хоста нужен --dns СЕРВЕР") from None
        answers, _peer = resolve(args.dns, host, bind=args.bind, timeout=args.timeout)
        if not answers:
            raise OSError(f"DNS не дал адреса для {host}") from None
        address = answers[0]
    path = url.path or "/"
    if url.query:
        path += "?" + url.query
    with socket.socket() as sock:
        if args.mark:
            sock.setsockopt(socket.SOL_SOCKET, SO_MARK, args.mark)
        if args.bind:
            sock.bind((args.bind, 0))
        sock.settimeout(args.timeout)
        sock.connect((address, port))
        sock.sendall(
            f"GET {path} HTTP/1.1\r\nHost: {url.netloc}\r\nConnection: close\r\n\r\n".encode()
        )
        data = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
            head, sep, body = data.partition(b"\r\n\r\n")
            # Как браузер: тело целиком по Content-Length, конца потока не ждём
            # (прокси закрывает соединение на пару секунд позже сервера).
            length = next(
                (int(line.split(b":")[1]) for line in head.split(b"\r\n")
                 if line.lower().startswith(b"content-length:")), None,
            )
            if sep and length is not None and len(body) >= length:
                break
    head, _, body = data.partition(b"\r\n\r\n")
    status = head.split(b"\r\n")[0].split()
    result: dict = {
        "status": int(status[1]) if len(status) > 1 and status[1].isdigit() else 0,
        "bytes": len(body),
        "address": address,
    }
    if len(body) <= 300:
        result["body"] = body.decode("utf-8", errors="replace")
    return result


def _dhcp_options(data: bytes) -> dict[int, bytes]:
    options: dict[int, bytes] = {}
    offset = 240
    while offset < len(data) and data[offset] != 255:
        if data[offset] == 0:
            offset += 1
            continue
        size = data[offset + 1]
        options[data[offset]] = data[offset + 2 : offset + 2 + size]
        offset += 2 + size
    return options


def do_dhcp(args) -> dict:
    """DISCOVER → OFFER → REQUEST → ACK; адрес интерфейсу не назначается."""
    mac_text = args.mac or Path(f"/sys/class/net/{args.iface}/address").read_text().strip()
    mac = bytes.fromhex(mac_text.replace(":", ""))
    xid = os.urandom(4)

    def packet(kind: int, extra: bytes = b"") -> bytes:
        header = struct.pack(
            "!BBBB4sHH4s4s4s4s16s64s128s", 1, 1, 6, 0, xid, 0,
            0x8000,  # флаг broadcast: адреса у клиента ещё нет, ответ — широковещательно
            b"\0" * 4, b"\0" * 4, b"\0" * 4, b"\0" * 4, mac, b"", b"",
        )
        return header + DHCP_MAGIC + bytes([53, 1, kind]) + extra + bytes([55, 3, 1, 3, 6, 255])

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, SO_BINDTODEVICE, args.iface.encode() + b"\0")
        sock.bind(("0.0.0.0", 68))
        sock.settimeout(args.timeout)

        def exchange(request: bytes, expected: int) -> tuple[bytes, dict[int, bytes]]:
            sock.sendto(request, ("255.255.255.255", 67))
            while True:
                data, _peer = sock.recvfrom(2048)
                options = _dhcp_options(data)
                if data[4:8] == xid and options.get(53) == bytes([expected]):
                    return data, options

        offer, options = exchange(packet(1), 2)
        offered, server = offer[16:20], options[54]
        _ack, options = exchange(packet(3, bytes([50, 4]) + offered + bytes([54, 4]) + server), 5)

    def address(code: int) -> str:
        return socket.inet_ntoa(options[code][:4]) if len(options.get(code, b"")) >= 4 else ""

    return {
        "ip": socket.inet_ntoa(offered),
        "mask": address(1),
        "router": address(3),
        "dns": address(6),
        "server": socket.inet_ntoa(server),
        "lease": struct.unpack("!I", options[51])[0] if 51 in options else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    get = commands.add_parser("get")
    get.add_argument("url")
    get.add_argument("--dns", default="", help="DNS-сервер для имени хоста")
    get.add_argument("--bind", default="", help="адрес источника")
    get.add_argument("--mark", type=int, default=0, help="SO_MARK (нужен root)")
    get.add_argument("--timeout", type=float, default=6.0)
    dns = commands.add_parser("dns")
    dns.add_argument("server")
    dns.add_argument("name")
    dns.add_argument("--tcp", action="store_true")
    dns.add_argument("--bind", default="")
    dns.add_argument("--timeout", type=float, default=5.0)
    dhcp = commands.add_parser("dhcp")
    dhcp.add_argument("iface")
    dhcp.add_argument("--mac", default="")
    dhcp.add_argument("--timeout", type=float, default=6.0)
    args = parser.parse_args()

    started = time.monotonic()
    try:
        result = {"get": do_get, "dns": do_dns, "dhcp": do_dhcp}[args.command](args)
    except (OSError, ValueError, IndexError, KeyError, struct.error) as exc:
        result = {"error": f"{type(exc).__name__}: {exc}"}
    result["seconds"] = round(time.monotonic() - started, 2)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
