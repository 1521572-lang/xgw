"""HTTP- и DoH-клиент XGW на сокетах с SO_MARK.

Подписки, bootstrap-DNS (DoH по IP и обычный UDP-DNS) и проверки провайдера.
Только стандартная библиотека: http.client, ssl, socket.
"""

from __future__ import annotations

import base64
import contextlib
import http.client
import secrets
import socket
import ssl
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from . import marknet, masking

DEFAULT_TIMEOUT = 15.0
RETRY_DELAYS = (2.0, 4.0, 8.0)
DEFAULT_UA = "xgw/0.1"


class FetchError(Exception):
    pass


class ResolveError(Exception):
    pass


@dataclass
class FetchResult:
    status: int
    headers: dict[str, str]
    body: bytes
    url: str = ""


def fetch_url(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    mark: int | None = None,
    retries: int = 3,
    backoffs: tuple[float, ...] = RETRY_DELAYS,
) -> FetchResult:
    """GET с повторами (пауза 2/4/8 c). file:// читается с диска без повторов."""
    if url.startswith("file://"):
        return _fetch_file(url)
    last_error: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            return _request_with_redirects(url, headers or {}, timeout, mark)
        except Exception as exc:
            last_error = exc
            if attempt < retries - 1:
                delay = backoffs[min(attempt, len(backoffs) - 1)]
                time.sleep(delay)
    raise FetchError(f"не удалось получить {masking.mask_url(url)}: {last_error}") from last_error


def fetch_subscription(
    url: str,
    *,
    user_agent: str = "",
    headers: dict[str, str] | None = None,
    mark: int | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> FetchResult:
    merged = dict(headers or {})
    if user_agent:
        merged["User-Agent"] = user_agent
    return fetch_url(url, headers=merged, mark=mark, timeout=timeout)


def parse_userinfo(header: str) -> dict[str, int]:
    """subscription-userinfo: upload=…; download=…; total=…; expire=…"""
    result: dict[str, int] = {}
    for part in header.split(";"):
        key, sep, value = part.partition("=")
        key = key.strip()
        if sep and key in ("upload", "download", "total", "expire"):
            try:
                result[key] = int(value.strip())
            except ValueError:
                continue
    return result


# --- низкий уровень -----------------------------------------------------------


def _fetch_file(url: str) -> FetchResult:
    raw = url[len("file://") :]
    raw = raw.split("?", 1)[0].split("#", 1)[0]
    path = Path(unquote(raw))
    try:
        body = path.read_bytes()
    except OSError as exc:
        raise FetchError(f"не удалось прочитать {path}: {exc}") from exc
    return FetchResult(status=200, headers={}, body=body, url=url)


def _request_with_redirects(
    url: str, headers: dict[str, str], timeout: float, mark: int | None
) -> FetchResult:
    current = url
    for _ in range(4):
        result = _request_once(current, headers, timeout, mark)
        if result.status in (301, 302, 303, 307, 308):
            location = result.headers.get("location", "")
            if not location:
                return result
            current = urljoin(current, location)
            continue
        return result
    raise FetchError(f"слишком много перенаправлений: {masking.mask_url(url)}")


def _request_once(
    url: str, headers: dict[str, str], timeout: float, mark: int | None
) -> FetchResult:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchError(f"неподдерживаемая схема: {parts.scheme}")
    host = parts.hostname
    if not host:
        raise FetchError("в URL нет хоста")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    sock = marknet.connect_marked(host, port, timeout=timeout, mark=mark)
    try:
        if parts.scheme == "https":
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.sock = sock
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        request_headers = {"User-Agent": DEFAULT_UA, "Accept": "*/*", **headers}
        conn.request("GET", path, headers=request_headers)
        response = conn.getresponse()
        body = response.read()
        return FetchResult(
            status=response.status,
            headers={k.lower(): v for k, v in response.getheaders()},
            body=body,
            url=url,
        )
    finally:
        with contextlib.suppress(OSError):
            sock.close()


# --- DNS: wire-формат, DoH и обычный UDP --------------------------------------


def _dns_query(name: str, qtype: int = 1) -> bytes:
    qid = secrets.randbits(16)
    header = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    qname = b"".join(bytes([len(label)]) + label.encode("ascii") for label in name.split("."))
    qname += b"\x00"
    return header + qname + struct.pack(">HH", qtype, 1)


def _skip_name(payload: bytes, offset: int) -> int:
    end: int | None = None
    jumps = 0
    while True:
        if offset >= len(payload):
            raise ResolveError("битый DNS-ответ: обрезано имя")
        length = payload[offset]
        if length & 0xC0 == 0xC0:
            if end is None:
                end = offset + 2
            offset = ((length & 0x3F) << 8) | payload[offset + 1]
            jumps += 1
            if jumps > 8:
                raise ResolveError("битый DNS-ответ: зацикленное имя")
            continue
        offset += 1
        if length == 0:
            return end if end is not None else offset
        offset += length


def _parse_a_answers(payload: bytes) -> list[str]:
    if len(payload) < 12:
        raise ResolveError("битый DNS-ответ: короче заголовка")
    qdcount, ancount = struct.unpack(">HH", payload[4:8])
    offset = 12
    for _ in range(qdcount):
        offset = _skip_name(payload, offset) + 4
    ips: list[str] = []
    for _ in range(ancount):
        offset = _skip_name(payload, offset)
        if offset + 10 > len(payload):
            raise ResolveError("битый DNS-ответ: обрезана запись")
        rtype, _rclass, _ttl, rdlength = struct.unpack(">HHIH", payload[offset : offset + 10])
        offset += 10
        rdata = payload[offset : offset + rdlength]
        offset += rdlength
        if rtype == 1 and rdlength == 4:
            ips.append(socket.inet_ntoa(rdata))
    return ips


def doh_query(
    bootstrap_url: str, name: str, *, timeout: float = 8.0, mark: int | None = None
) -> list[str]:
    parts = urlsplit(bootstrap_url)
    path = parts.path or "/dns-query"
    wire = _dns_query(name)
    encoded = base64.urlsafe_b64encode(wire).rstrip(b"=").decode("ascii")
    url = f"{parts.scheme}://{parts.netloc}{path}?dns={encoded}"
    result = fetch_url(
        url,
        headers={"Accept": "application/dns-message"},
        timeout=timeout,
        mark=mark,
        retries=1,
    )
    if result.status != 200:
        raise ResolveError(f"DoH {masking.mask_url(bootstrap_url)}: HTTP {result.status}")
    return _parse_a_answers(result.body)


def plain_dns(
    server: str, name: str, *, timeout: float = 5.0, mark: int | None = None
) -> list[str]:
    wire = _dns_query(name)
    sock = marknet.marked_udp(mark)
    try:
        sock.settimeout(timeout)
        sock.sendto(wire, (server, 53))
        data, _ = sock.recvfrom(4096)
    finally:
        sock.close()
    return _parse_a_answers(data)


def resolve_domain(name: str, bootstrap: list[str], *, mark: int | None = None) -> list[str]:
    """Разрешение домена сервера через bootstrap-резолверы (DoH по IP, затем UDP)."""
    errors: list[str] = []
    for entry in bootstrap:
        try:
            if entry.startswith("https://"):
                ips = doh_query(entry, name, mark=mark)
            elif entry.startswith("udp://"):
                ips = plain_dns(entry[len("udp://") :], name, mark=mark)
            else:
                errors.append(f"неизвестный bootstrap: {entry}")
                continue
            if ips:
                return ips
            errors.append(f"{masking.mask_url(entry)}: пустой ответ")
        except Exception as exc:
            errors.append(f"{masking.mask_url(entry)}: {exc}")
    raise ResolveError(f"не удалось разрешить {name}: {'; '.join(errors[:3])}")
