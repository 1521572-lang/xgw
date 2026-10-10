"""HTTP- и DoH-клиент XGW на сокетах с SO_MARK.

Подписки, bootstrap-DNS (DoH по IP и обычный UDP-DNS) и проверки провайдера.
Только стандартная библиотека: http.client, ssl, socket.
"""

from __future__ import annotations

import base64
import contextlib
import http.client
import ipaddress
import re
import secrets
import socket
import ssl
import struct
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from . import marknet, masking

DEFAULT_TIMEOUT = 15.0
RETRY_DELAYS = (2.0, 4.0, 8.0)
DEFAULT_UA = "xgw/0.1"
MAX_BODY = 128 * 1024 * 1024  # потолок ответа: архив Xray ~30 МиБ, подписки — килобайты
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
CRLF = "\r\n"
HEAD_END = b"\r\n\r\n"  # конец заголовков HTTP

_sleep = time.sleep  # подменяется в тестах


class FetchError(Exception):
    pass


class ProxyError(FetchError):
    """http-inbound Xray не открыл туннель (нет связи, 407, 5xx)."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


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
    bootstrap: Sequence[str] | None = None,
    proxy: tuple[str, int] | None = None,
) -> FetchResult:
    """GET: первая попытка и до `retries` повторов с паузами 2, 4 и 8 с.

    Повторяются только временные сбои: сетевые ошибки и ответы 429/5xx.
    `bootstrap` — резолверы для имени хоста (сокетами с той же меткой); без них
    имя разрешает системный резолвер, то есть запрос DNS пойдёт через перехват.
    `proxy` — http-inbound Xray (127.0.0.1:<http_port>): запрос идёт CONNECT-туннелем
    через балансировщик, метка и bootstrap тогда не нужны.
    file:// читается с диска без повторов.
    """
    if url.startswith("file://"):
        return _fetch_file(url)
    attempts = max(0, retries) + 1
    last_error: Exception | None = None
    result: FetchResult | None = None
    for attempt in range(attempts):
        try:
            result = _request_with_redirects(
                url, headers or {}, timeout, mark, bootstrap, proxy
            )
        except (
            FetchError,
            marknet.MarkUnavailable,
            ssl.SSLCertVerificationError,
            ValueError,  # в т. ч. UnicodeError: URL или имя хоста не разобрать
        ) as exc:
            # Повтор не поможет: неверный URL, нет SO_MARK, недоверенный сертификат.
            raise FetchError(f"не удалось получить {masking.mask_url(url)}: {exc}") from exc
        except (OSError, http.client.HTTPException, ResolveError) as exc:
            last_error = exc
            result = None
        else:
            if result.status not in _RETRY_STATUSES:
                return result
        if attempt < attempts - 1:
            _sleep(backoffs[min(attempt, len(backoffs) - 1)] if backoffs else 0.0)
    if result is not None:
        return result  # 429/5xx после всех повторов — код проверит вызывающий
    raise FetchError(f"не удалось получить {masking.mask_url(url)}: {last_error}") from last_error


def fetch_subscription(
    url: str,
    *,
    user_agent: str = "",
    headers: dict[str, str] | None = None,
    mark: int | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    bootstrap: Sequence[str] | None = None,
    proxy: tuple[str, int] | None = None,
    retries: int = 3,
) -> FetchResult:
    """Подписка: таймаут 15 с, до 3 повторов. Ответ не 200 — ошибка, а не «пустая подписка»."""
    merged = dict(headers or {})
    if user_agent:
        merged["User-Agent"] = user_agent
    result = fetch_url(
        url, headers=merged, mark=mark, timeout=timeout, bootstrap=bootstrap, proxy=proxy,
        retries=retries,
    )
    if result.status != 200:
        raise FetchError(f"{masking.mask_url(url)}: HTTP {result.status}")
    return result


def parse_userinfo(header: str) -> dict[str, int]:
    """subscription-userinfo: upload=…; download=…; total=…; expire=…"""
    result: dict[str, int] = {}
    for part in header.split(";"):
        key, sep, value = part.partition("=")
        key = key.strip().lower()
        if sep and key in ("upload", "download", "total", "expire"):
            try:
                result[key] = int(float(value.strip()))
            except ValueError:
                continue
    return result


# --- низкий уровень -----------------------------------------------------------


def _fetch_file(url: str) -> FetchResult:
    raw = url[len("file://") :]
    raw = raw.split("?", 1)[0].split("#", 1)[0]
    raw = unquote(raw)
    if re.match(r"^/[A-Za-z]:[/\\]", raw):  # file:///C:/… → C:/…
        raw = raw[1:]
    path = Path(raw)
    try:
        body = path.read_bytes()
    except OSError as exc:
        raise FetchError(f"не удалось прочитать {path}: {exc}") from exc
    return FetchResult(status=200, headers={}, body=body, url=url)


def _request_with_redirects(
    url: str,
    headers: dict[str, str],
    timeout: float,
    mark: int | None,
    bootstrap: Sequence[str] | None,
    proxy: tuple[str, int] | None = None,
) -> FetchResult:
    current = url
    for _ in range(5):
        result = _request_once(current, headers, timeout, mark, bootstrap, proxy)
        if result.status in (301, 302, 303, 307, 308):
            location = result.headers.get("location", "")
            if not location:
                return result
            current = urljoin(current, location)
            continue
        return result
    raise FetchError(f"слишком много перенаправлений: {masking.mask_url(url)}")


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _connect(
    host: str, port: int, timeout: float, mark: int | None, bootstrap: Sequence[str] | None
) -> socket.socket:
    if not bootstrap or _is_ip(host):
        return marknet.connect_marked(host, port, timeout=timeout, mark=mark)
    last_error: OSError | None = None
    for address in resolve_domain(host, list(bootstrap), mark=mark):
        try:
            return marknet.connect_marked(address, port, timeout=timeout, mark=mark)
        except OSError as exc:
            last_error = exc
    raise last_error or OSError(f"нет адресов для {host}")


def open_tunnel(
    proxy: tuple[str, int],
    host: str,
    port: int,
    *,
    timeout: float,
    user: str = "",
    password: str = "",
) -> socket.socket:
    """CONNECT-туннель через http-inbound Xray к host:port.

    Ответ прокси читается ровно до пустой строки: следом идут данные туннеля
    (TLS-рукопожатие), и ни один лишний байт забрать или оставить нельзя.
    """
    try:
        host = host if ":" in host else host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ProxyError(f"недопустимое имя хоста: {host}") from exc
    sock = socket.create_connection(proxy, timeout=timeout)
    try:
        target = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
        lines = [f"CONNECT {target} HTTP/1.1", f"Host: {target}"]
        if user:
            token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
            lines.append(f"Proxy-Authorization: Basic {token}")
        sock.sendall((CRLF.join(lines) + CRLF * 2).encode("ascii"))
        head = b""
        while not head.endswith(HEAD_END):
            chunk = sock.recv(1)
            if not chunk:
                raise ProxyError("прокси закрыл соединение, не ответив на CONNECT")
            head += chunk
            if len(head) > 16384:
                raise ProxyError("слишком длинный ответ прокси на CONNECT")
        status_line = head.split(CRLF.encode("ascii"), 1)[0].decode("latin-1")
        fields = status_line.split()
        if len(fields) < 2 or not fields[0].startswith("HTTP/1.") or not fields[1].isdigit():
            raise ProxyError("прокси ответил на CONNECT не по HTTP")
        if not fields[1].startswith("2"):
            raise ProxyError(f"CONNECT отклонён: {status_line}", status=int(fields[1]))
    except BaseException:
        sock.close()
        raise
    return sock


def _request_once(
    url: str,
    headers: dict[str, str],
    timeout: float,
    mark: int | None,
    bootstrap: Sequence[str] | None = None,
    proxy: tuple[str, int] | None = None,
) -> FetchResult:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchError(f"неподдерживаемая схема: {parts.scheme or '(нет)'}")
    host = parts.hostname
    if not host:
        raise FetchError("в URL нет хоста")
    default_port = 443 if parts.scheme == "https" else 80
    port = parts.port or default_port
    if proxy is not None:
        sock = open_tunnel(proxy, host, port, timeout=timeout)
    else:
        sock = _connect(host, port, timeout, mark, bootstrap)
    try:
        if parts.scheme == "https":
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host)
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.sock = sock
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        host_header = f"[{host}]" if ":" in host else host
        if port != default_port:
            host_header = f"{host_header}:{port}"
        request_headers = {
            "Host": host_header,
            "User-Agent": DEFAULT_UA,
            "Accept": "*/*",
            "Connection": "close",
            **headers,
        }
        conn.request("GET", path, headers=request_headers)
        response = conn.getresponse()
        body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise FetchError(f"ответ больше {MAX_BODY // (1024 * 1024)} МиБ")
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
    try:
        ascii_name = name.rstrip(".").encode("idna")
    except UnicodeError as exc:
        raise ResolveError(f"недопустимое имя: {name}") from exc
    labels = ascii_name.split(b".")
    if not ascii_name or any(not label or len(label) > 63 for label in labels):
        raise ResolveError(f"недопустимое имя: {name}")
    qname = b"".join(bytes([len(label)]) + label for label in labels) + b"\x00"
    return header + qname + struct.pack(">HH", qtype, 1)


def _skip_name(payload: bytes, offset: int) -> int:
    end: int | None = None
    jumps = 0
    while True:
        if offset >= len(payload):
            raise ResolveError("битый DNS-ответ: обрезано имя")
        length = payload[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(payload):
                raise ResolveError("битый DNS-ответ: обрезан указатель")
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
        if rtype == 1 and rdlength == 4 and len(rdata) == 4:
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
        retries=0,
    )
    if result.status != 200:
        raise ResolveError(f"DoH {masking.mask_url(bootstrap_url)}: HTTP {result.status}")
    return _parse_a_answers(result.body)


def plain_dns(
    server: str, name: str, *, timeout: float = 5.0, mark: int | None = None, port: int = 53
) -> list[str]:
    wire = _dns_query(name)
    sock = marknet.marked_udp(mark)
    try:
        deadline = time.monotonic() + timeout
        sock.sendto(wire, (server, port))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("нет ответа DNS")
            sock.settimeout(remaining)
            data, peer = sock.recvfrom(4096)
            # Чужие и подложенные датаграммы пропускаем: сверяем отправителя и ID запроса.
            if peer[0] == server and data[:2] == wire[:2]:
                return _parse_a_answers(data)
    finally:
        sock.close()


def resolve_domain(name: str, bootstrap: list[str], *, mark: int | None = None) -> list[str]:
    """Разрешение домена через bootstrap-резолверы (DoH по IP, затем UDP).

    Адреса возвращаются отсортированными: DNS-ротация не должна менять
    dns.hosts (и тем самым конфиг) от запуска к запуску.
    """
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
                return sorted(set(ips), key=ipaddress.ip_address)
            errors.append(f"{masking.mask_url(entry)}: пустой ответ")
        except Exception as exc:
            errors.append(f"{masking.mask_url(entry)}: {exc}")
    raise ResolveError(f"не удалось разрешить {name}: {'; '.join(errors[:3])}")
