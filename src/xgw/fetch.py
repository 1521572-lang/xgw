"""HTTP- и DoH-клиент XGW на сокетах с SO_MARK.

Подписки, bootstrap-DNS (DoH и DoT по IP, обычный UDP-DNS) и проверки провайдера.
Только стандартная библиотека: http.client, ssl, socket.
"""

from __future__ import annotations

import base64
import contextlib
import errno
import http.client
import io
import ipaddress
import os
import secrets
import select
import socket
import ssl
import struct
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
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
# Ожидание, которое можно прервать (wait_io), идёт кусками такой длины: столько демон самое
# большее ждёт сеть после команды остановки.
CANCEL_SLICE = 0.5

_sleep = time.sleep  # подменяется в тестах
# Резолвер bootstrap, который не ответил, пробуется последним столько секунд (0.1.18, ТЗ R4a):
# DoH-запрос к недоступному адресу ждёт таймаута, и каждый такой резолвер в начале списка
# задерживал бы разрешение имён на секунды. Память — на процесс (демон, установка, служба
# ядер); итог проверки всех резолверов демон пишет в журнал событий и diag (bootstrap.py).
RESOLVER_PAUSE = 600.0
_resolver_down: dict[str, float] = {}
_resolver_lock = threading.Lock()
# Шифрованные резолверы: ответ DoH (https://) и DoT (tls://) подписан сертификатом резолвера,
# и провайдер его не подменит. Обычный udp:// провайдер перехватывает на порту 53 и на имя
# из реестра блокировок отвечает адресом заглушки — для доменов подписок такие резолверы не
# спрашиваются вовсе (0.2.0, п. 1.1 рекомендаций к аудиту).
ENCRYPTED_SCHEMES = ("https://", "tls://")
DOT_PORT = 853
# Адреса, которых у сервера подписки в интернете быть не может: так отвечает подменённый DNS
# («0.0.0.0», «127.0.0.1», адрес из частной сети провайдера). Документационные сети
# (192.0.2.0/24 и др.) сюда не входят: заглушки ими не пользуются.
_BOGONS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
        "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/4", "240.0.0.0/4",
    )
)


def encrypted(entries: Sequence[str]) -> list[str]:
    """Только шифрованные резолверы — DoH и DoT, без udp://."""
    return [entry for entry in entries if entry.startswith(ENCRYPTED_SCHEMES)]


def is_bogon(address: str) -> bool:
    """Адрес, которым подменённый DNS отвечает вместо настоящего (_BOGONS)."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True
    return ip.version != 4 or any(ip in net for net in _BOGONS)


def resolver_order(entries: Sequence[str], now: float | None = None) -> list[str]:
    """Резолверы в порядке попыток: недавно не ответившие — в конце (порядок внутри групп
    сохраняется)."""
    now = time.monotonic() if now is None else now
    with _resolver_lock:
        down = {entry for entry, until in _resolver_down.items() if until > now}
    return [entry for entry in entries if entry not in down] + [
        entry for entry in entries if entry in down
    ]


def resolver_failed(entry: str, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    with _resolver_lock:
        _resolver_down[entry] = now + RESOLVER_PAUSE


def resolver_answered(entry: str) -> None:
    with _resolver_lock:
        _resolver_down.pop(entry, None)


class FetchError(Exception):
    pass


class Cancelled(Exception):
    """Ожидание сети прервано (cancel): демон останавливается."""


def wait_io(sock: socket.socket, op, timeout: float, cancel: threading.Event | None = None):
    """op() — одна операция с сокетом (recv, рукопожатие TLS) с таймаутом timeout, как при
    sock.settimeout(timeout). С cancel ожидание идёт кусками по CANCEL_SLICE: событие
    выставлено — Cancelled. Повторять op после таймаута можно: recv ещё ничего не забрал,
    рукопожатие TLS продолжается с того места, где ждало данных."""
    if cancel is None:
        sock.settimeout(timeout)
        return op()
    deadline = time.monotonic() + timeout
    while True:
        if cancel.is_set():
            raise Cancelled
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("timed out")
        sock.settimeout(min(left, CANCEL_SLICE))
        try:
            return op()
        except TimeoutError:
            continue


def wait_connect(
    sock: socket.socket, address: tuple[str, int], timeout: float,
    cancel: threading.Event | None = None,
) -> None:
    """sock.connect(address) с таймаутом timeout. С cancel соединение ждётся кусками по
    CANCEL_SLICE, как в wait_io: событие выставлено — Cancelled."""
    if cancel is None:
        sock.settimeout(timeout)
        sock.connect(address)
        return
    if cancel.is_set():
        raise Cancelled
    deadline = time.monotonic() + timeout
    sock.setblocking(False)
    code = sock.connect_ex(address)
    while code in (errno.EINPROGRESS, errno.EALREADY, errno.EWOULDBLOCK):
        if cancel.is_set():
            raise Cancelled
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("timed out")
        _readable, writable, _failed = select.select([], [sock], [], min(left, CANCEL_SLICE))
        if writable:
            code = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
    if code:
        raise OSError(code, os.strerror(code))
    sock.settimeout(timeout)


class ProxyError(FetchError):
    """http-inbound Xray не открыл туннель (нет связи, 407, 5xx)."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


class ResolveError(Exception):
    pass


class NoSuchDomain(ResolveError):
    """Резолвер ответил определённо: имени нет (NXDOMAIN) либо у него нет адреса IPv4.

    В отличие от сбоя резолвера (таймаут, отказ) повтор сразу ничего не даст: сервер с
    таким адресом недоступен, пока владелец домена его не вернёт.
    """


@dataclass
class FetchResult:
    status: int
    headers: dict[str, str]
    body: bytes
    url: str = ""
    # Прямой запрос к имени хоста: имя (последнего адреса после перенаправлений), IP-адрес, с
    # которым прошло рукопожатие TLS, и взят ли он из запасных (fallback), а не от резолвера.
    host: str = ""
    address: str = ""
    from_fallback: bool = False


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
    data: bytes | None = None,
    cancel: threading.Event | None = None,
    strict_dns: bool = False,
    fallback: dict[str, list[str]] | None = None,
) -> FetchResult:
    """GET (или POST, если задано тело `data`): первая попытка и до `retries`
    повторов с паузами 2, 4 и 8 с.

    Повторяются только временные сбои: сетевые ошибки и ответы 429/5xx.
    `bootstrap` — резолверы для имени хоста (сокетами с той же меткой); без них
    имя разрешает системный резолвер, то есть запрос DNS пойдёт через перехват.
    `proxy` — http-inbound Xray (127.0.0.1:<http_port>): запрос идёт CONNECT-туннелем
    через балансировщик, метка и bootstrap тогда не нужны.
    file:// читается с диска без повторов.
    `cancel` — демон останавливается: новая попытка не начинается, пауза перед ней и
    ожидание сети (разрешение имени, соединение, CONNECT, TLS, ответ) прерываются —
    Cancelled. Такой итог ничего не говорит ни о подписке, ни о сервере.
    `strict_dns` — имя спрашивается только у шифрованных резолверов (encrypted), а адреса
    служебных сетей в ответе (is_bogon) считаются подменой; так разрешаются домены
    подписок. `fallback` — имя хоста → адреса, с которыми запрос уже удавался (кэш
    store.HostCache): по ним идёт соединение, если резолверы не ответили или ни один из
    их адресов не соединился. Сертификат TLS проверяется по имени хоста и тогда.
    """
    if url.startswith("file://"):
        return _fetch_file(url)
    dns = _Dns(bootstrap, strict_dns, fallback or {})
    attempts = max(0, retries) + 1
    last_error: Exception | None = None
    result: FetchResult | None = None
    for attempt in range(attempts):
        if cancel is not None and cancel.is_set():
            raise Cancelled
        try:
            result = _request_with_redirects(
                url, headers or {}, timeout, mark, dns, proxy, data, cancel
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
            _pause(backoffs[min(attempt, len(backoffs) - 1)] if backoffs else 0.0, cancel)
    if result is not None:
        return result  # 429/5xx после всех повторов — код проверит вызывающий
    raise FetchError(f"не удалось получить {masking.mask_url(url)}: {last_error}") from last_error


def _pause(seconds: float, cancel: threading.Event | None) -> None:
    """Пауза перед повтором; остановка демона её прерывает (Cancelled)."""
    if cancel is None:
        _sleep(seconds)
    elif cancel.wait(seconds):
        raise Cancelled


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
    cancel: threading.Event | None = None,
    fallback: dict[str, list[str]] | None = None,
) -> FetchResult:
    """Подписка: таймаут 15 с, до 3 повторов. Ответ не 200 — ошибка, а не «пустая подписка».
    Имя хоста — только через шифрованные резолверы (strict_dns в fetch_url); fallback и
    cancel — см. fetch_url."""
    merged = dict(headers or {})
    if user_agent:
        merged["User-Agent"] = user_agent
    result = fetch_url(
        url, headers=merged, mark=mark, timeout=timeout, bootstrap=bootstrap, proxy=proxy,
        retries=retries, cancel=cancel, strict_dns=True, fallback=fallback,
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
    path = Path(unquote(raw))
    try:
        body = path.read_bytes()
    except OSError as exc:
        raise FetchError(f"не удалось прочитать {path}: {exc}") from exc
    return FetchResult(status=200, headers={}, body=body, url=url)


@dataclass
class _Dns:
    """Как разрешать имя хоста при прямом запросе (fetch_url): резолверы, строгий режим
    (только шифрованные, без служебных адресов) и запасные адреса по именам."""

    bootstrap: Sequence[str] | None
    strict: bool = False
    fallback: dict[str, list[str]] = field(default_factory=dict)


def _request_with_redirects(
    url: str,
    headers: dict[str, str],
    timeout: float,
    mark: int | None,
    dns: _Dns | Sequence[str] | None,
    proxy: tuple[str, int] | None = None,
    data: bytes | None = None,
    cancel: threading.Event | None = None,
) -> FetchResult:
    if not isinstance(dns, _Dns):
        dns = _Dns(dns)
    current = url
    for _ in range(5):
        result = _request_once(current, headers, timeout, mark, dns, proxy, data, cancel)
        # Тело за перенаправлением не отправляется: запрос с телом не повторяется по чужому
        # адресу.
        if data is None and result.status in (301, 302, 303, 307, 308):
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
    host: str, port: int, timeout: float, mark: int | None, dns: _Dns | Sequence[str] | None,
    cancel: threading.Event | None = None,
) -> tuple[socket.socket, bool]:
    """Соединение с host:port; второе значение — адрес взят из запасных (dns.fallback)."""
    if not isinstance(dns, _Dns):
        dns = _Dns(dns)

    def connect(sock: socket.socket, address: tuple[str, int]) -> None:
        wait_connect(sock, address, timeout, cancel)

    if not dns.bootstrap or _is_ip(host):
        sock = marknet.connect_marked(host, port, timeout=timeout, mark=mark, connect=connect)
        return sock, False
    spare = [ip for ip in dns.fallback.get(host, []) if _is_ip(ip)]
    entries = encrypted(dns.bootstrap) if dns.strict else list(dns.bootstrap)
    try:
        addresses = resolve_domain(
            host, entries, mark=mark, cancel=cancel, public_only=dns.strict,
        )
    except ResolveError:
        if not spare:
            raise
        addresses = []
    last_error: OSError | None = None
    tried: set[str] = set()
    for address in [*addresses, *spare]:
        if address in tried:
            continue
        tried.add(address)
        try:
            sock = marknet.connect_marked(
                address, port, timeout=timeout, mark=mark, connect=connect
            )
        except OSError as exc:
            last_error = exc
            continue
        return sock, address not in addresses
    raise last_error or OSError(f"нет адресов для {host}")


def open_tunnel(
    proxy: tuple[str, int],
    host: str,
    port: int,
    *,
    timeout: float,
    user: str = "",
    password: str = "",
    cancel: threading.Event | None = None,
) -> socket.socket:
    """CONNECT-туннель через http-inbound Xray к host:port.

    Ответ прокси читается ровно до пустой строки: следом идут данные туннеля
    (TLS-рукопожатие), и ни один лишний байт забрать или оставить нельзя.
    cancel — прервать ожидание ответа (Cancelled), см. wait_io.
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
            chunk = wait_io(sock, lambda: sock.recv(1), timeout, cancel)
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
    dns: _Dns | Sequence[str] | None = None,
    proxy: tuple[str, int] | None = None,
    data: bytes | None = None,
    cancel: threading.Event | None = None,
) -> FetchResult:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchError(f"неподдерживаемая схема: {parts.scheme or '(нет)'}")
    host = parts.hostname
    if not host:
        raise FetchError("в URL нет хоста")
    default_port = 443 if parts.scheme == "https" else 80
    port = parts.port or default_port
    if cancel is not None and cancel.is_set():
        raise Cancelled
    address, from_fallback = "", False
    if proxy is not None:
        sock = open_tunnel(proxy, host, port, timeout=timeout, cancel=cancel)
    else:
        sock, from_fallback = _connect(host, port, timeout, mark, dns, cancel)
        # Адрес соединения — для кэша адресов подписок (store.HostCache); подставной сокет
        # тестов getpeername может не знать — тогда адреса нет, и кэш не пишется.
        with contextlib.suppress(OSError, AttributeError):
            address = str(sock.getpeername()[0])
    try:
        if parts.scheme == "https":
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=host, do_handshake_on_connect=False)
            wait_io(sock, sock.do_handshake, timeout, cancel)
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.sock = _WaitingSocket(sock, timeout, cancel)
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
        if data is None:
            conn.request("GET", path, headers=request_headers)
        else:
            conn.request("POST", path, body=data, headers=request_headers)
        response = conn.getresponse()
        body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise FetchError(f"ответ больше {MAX_BODY // (1024 * 1024)} МиБ")
        return FetchResult(
            status=response.status,
            headers={k.lower(): v for k, v in response.getheaders()},
            body=body,
            url=url,
            host=host if address and not _is_ip(host) else "",
            address=address,
            from_fallback=from_fallback,
        )
    finally:
        with contextlib.suppress(OSError):
            sock.close()


class _WaitingSocket:
    """Сокет для http.client: ответ читается через wait_io, и остановка демона (cancel)
    прерывает ожидание заголовков и тела."""

    def __init__(self, sock: socket.socket, timeout: float, cancel: threading.Event | None):
        self._sock = sock
        self._timeout = timeout
        self._cancel = cancel

    def sendall(self, data) -> None:
        self._sock.settimeout(self._timeout)
        self._sock.sendall(data)

    def makefile(self, *_args, **_kwargs) -> io.BufferedReader:
        return io.BufferedReader(_WaitingReader(self._sock, self._timeout, self._cancel))

    def close(self) -> None:
        """Ничего не делает: http.client закрывает соединение, ещё не прочитав тело
        (Connection: close), а сокет закрывает _request_once, когда ответ прочитан."""


class _WaitingReader(io.RawIOBase):
    def __init__(self, sock: socket.socket, timeout: float, cancel: threading.Event | None):
        super().__init__()
        self._sock = sock
        self._timeout = timeout
        self._cancel = cancel

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        sock = self._sock
        return wait_io(sock, lambda: sock.recv_into(buffer), self._timeout, self._cancel)


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
    """Адреса IPv4 из ответа. Пустой список — имя есть, но A-записей у него нет."""
    if len(payload) < 12:
        raise ResolveError("битый DNS-ответ: короче заголовка")
    rcode = payload[3] & 0x0F
    if rcode == 3:
        raise NoSuchDomain("такого имени нет (NXDOMAIN)")
    if rcode:
        # SERVFAIL, REFUSED и прочее — сбой резолвера, а не сведения о домене.
        raise ResolveError(f"резолвер ответил ошибкой (RCODE {rcode})")
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
    bootstrap_url: str, name: str, *, timeout: float = 8.0, mark: int | None = None,
    cancel: threading.Event | None = None,
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
        cancel=cancel,
    )
    if result.status != 200:
        raise ResolveError(f"DoH {masking.mask_url(bootstrap_url)}: HTTP {result.status}")
    return _parse_a_answers(result.body)


def plain_dns(
    server: str, name: str, *, timeout: float = 5.0, mark: int | None = None, port: int = 53,
    cancel: threading.Event | None = None,
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
            data, peer = wait_io(sock, lambda: sock.recvfrom(4096), remaining, cancel)
            # Чужие и подложенные датаграммы пропускаем: сверяем отправителя и ID запроса.
            if peer[0] == server and data[:2] == wire[:2]:
                return _parse_a_answers(data)
    finally:
        sock.close()


def _read_exact(
    sock: socket.socket, size: int, timeout: float, cancel: threading.Event | None
) -> bytes:
    data = b""
    while len(data) < size:
        want = size - len(data)
        chunk = wait_io(sock, lambda want=want: sock.recv(want), timeout, cancel)
        if not chunk:
            raise ResolveError("резолвер закрыл соединение, не ответив")
        data += chunk
    return data


def dot_query(
    server: str, name: str, *, port: int = DOT_PORT, timeout: float = 8.0,
    mark: int | None = None, cancel: threading.Event | None = None,
) -> list[str]:
    """DNS-over-TLS (RFC 7858): запрос DNS с двухбайтовой длиной в соединении TLS к адресу
    резолвера. Сертификат проверяется по самому IP — так у Яндекса, Quad9, AdGuard,
    Cloudflare и Google (проверено 26.10.2026); чужой сертификат — ssl.SSLError."""

    def connect(sock: socket.socket, address: tuple[str, int]) -> None:
        wait_connect(sock, address, timeout, cancel)

    wire = _dns_query(name)
    raw = marknet.connect_marked(server, port, timeout=timeout, mark=mark, connect=connect)
    try:
        context = ssl.create_default_context()
        sock = context.wrap_socket(raw, server_hostname=server, do_handshake_on_connect=False)
    except BaseException:
        raw.close()
        raise
    try:
        wait_io(sock, sock.do_handshake, timeout, cancel)
        sock.settimeout(timeout)
        sock.sendall(struct.pack(">H", len(wire)) + wire)
        (length,) = struct.unpack(">H", _read_exact(sock, 2, timeout, cancel))
        payload = _read_exact(sock, length, timeout, cancel)
    finally:
        with contextlib.suppress(OSError):
            sock.close()
    if payload[:2] != wire[:2]:
        raise ResolveError("ответ DoT на чужой запрос")
    return _parse_a_answers(payload)


def _host_port(text: str, default: int) -> tuple[str, int]:
    """«адрес» или «адрес:порт» → (адрес, порт)."""
    server, sep, port = text.rpartition(":")
    if sep and port.isdigit():
        return server, int(port)
    return text, default


def resolve_domain(
    name: str, bootstrap: list[str], *, mark: int | None = None,
    cancel: threading.Event | None = None, public_only: bool = False,
) -> list[str]:
    """Разрешение домена через bootstrap-резолверы (DoH и DoT по IP, обычный UDP).

    Адреса возвращаются отсортированными: DNS-ротация не должна менять
    dns.hosts (и тем самым конфиг) от запуска к запуску.

    public_only — адреса служебных сетей (is_bogon) отбрасываются: ответ из одних таких —
    подмена, резолвер считается отказавшим, и спрашивается следующий.

    NoSuchDomain — адресов нет ни у кого, и хотя бы один резолвер ответил
    определённо (NXDOMAIN или пустой ответ); прочие сбои — ResolveError. cancel — см. fetch_url.
    """
    errors: list[str] = []
    absent = ""
    for entry in resolver_order(bootstrap):
        if cancel is not None and cancel.is_set():
            raise Cancelled
        try:
            if entry.startswith("https://"):
                ips = doh_query(entry, name, mark=mark, cancel=cancel)
            elif entry.startswith("tls://"):
                server, port = _host_port(entry[len("tls://") :].rstrip("/"), DOT_PORT)
                ips = dot_query(server, name, port=port, mark=mark, cancel=cancel)
            elif entry.startswith("udp://"):
                server, port = _host_port(entry[len("udp://") :], 53)
                ips = plain_dns(server, name, mark=mark, port=port, cancel=cancel)
            else:
                errors.append(f"неизвестный bootstrap: {entry}")
                continue
            if public_only and ips:
                public = [ip for ip in ips if not is_bogon(ip)]
                if not public:
                    resolver_failed(entry)
                    errors.append(
                        f"{masking.mask_url(entry)}: подменённый ответ ({', '.join(ips[:3])})"
                    )
                    continue
                ips = public
            resolver_answered(entry)
            if ips:
                return sorted(set(ips), key=ipaddress.ip_address)
            absent = absent or "у имени нет адреса IPv4"
            errors.append(f"{masking.mask_url(entry)}: пустой ответ")
        except NoSuchDomain as exc:
            resolver_answered(entry)  # ответил — определённо, а не сбой
            absent = str(exc)
            errors.append(f"{masking.mask_url(entry)}: {exc}")
        except Cancelled:
            raise
        except Exception as exc:
            resolver_failed(entry)
            errors.append(f"{masking.mask_url(entry)}: {exc}")
    if absent:
        raise NoSuchDomain(f"домен {name} не разрешается: {absent}")
    raise ResolveError(f"не удалось разрешить {name}: {'; '.join(errors[:3])}")
