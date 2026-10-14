"""Тесты fetch: file://, повторы, коды ответа, CONNECT-туннель, DNS (без внешней сети)."""

import socket
import struct
import threading

import pytest

from xgw import fetch
from xgw.fetch import (
    FetchError,
    FetchResult,
    ProxyError,
    ResolveError,
    _dns_query,
    _parse_a_answers,
    fetch_subscription,
    fetch_url,
    open_tunnel,
    parse_userinfo,
    plain_dns,
)


def test_fetch_file(tmp_path):
    path = tmp_path / "sub.txt"
    path.write_text("hello", encoding="utf-8")
    # В Windows это file:///C:/…, file://C:/… и file://C:\…; в POSIX все три — file:///tmp/…
    for url in {path.as_uri(), f"file://{path.as_posix()}", f"file://{path}"}:
        result = fetch_url(url)
        assert isinstance(result, FetchResult)
        assert result.status == 200
        assert result.body == b"hello"


def test_fetch_file_missing(tmp_path):
    with pytest.raises(FetchError):
        fetch_url(f"file://{tmp_path / 'nope.txt'}")


def test_parse_userinfo():
    info = parse_userinfo("upload=1234; download=5678; total=100000; expire=1798761600")
    assert info == {"upload": 1234, "download": 5678, "total": 100000, "expire": 1798761600}
    assert parse_userinfo("garbage") == {}


# --- HTTP: локальный сервер с очередью ответов ---------------------------------


class HttpServer(threading.Thread):
    """Отвечает на запросы по очереди заранее заданными ответами (последний повторяется)."""

    def __init__(self, *responses: bytes):
        super().__init__(daemon=True)
        self.responses = list(responses)
        self.requests: list[bytes] = []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.start()

    def run(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                try:
                    request = b""
                    while b"\r\n\r\n" not in request:
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        request += chunk
                    self.requests.append(request)
                    index = min(len(self.requests), len(self.responses)) - 1
                    conn.sendall(self.responses[index])
                except OSError:
                    pass

    def url(self, path: str = "/sub") -> str:
        return f"http://127.0.0.1:{self.port}{path}"


def _response(status: int, body: bytes = b"", extra: str = "") -> bytes:
    head = f"HTTP/1.1 {status} X\r\nContent-Length: {len(body)}\r\nConnection: close\r\n{extra}\r\n"
    return head.encode("ascii") + body


@pytest.fixture()
def no_sleep(monkeypatch):
    pauses: list[float] = []
    monkeypatch.setattr(fetch, "_sleep", pauses.append)
    return pauses


def test_retries_follow_spec_pauses(no_sleep):
    """Первая попытка и три повтора с паузами 2, 4 и 8 с (раздел 6.5)."""
    server = HttpServer(_response(503))
    result = fetch_url(server.url())
    assert result.status == 503
    assert len(server.requests) == 4
    assert no_sleep == [2.0, 4.0, 8.0]


def test_retry_succeeds_after_transient_error(no_sleep):
    server = HttpServer(_response(502), _response(200, b"ok"))
    result = fetch_url(server.url())
    assert (result.status, result.body) == (200, b"ok")
    assert no_sleep == [2.0]


def test_client_error_is_not_retried(no_sleep):
    server = HttpServer(_response(404, b"not found"))
    assert fetch_url(server.url()).status == 404
    assert len(server.requests) == 1 and no_sleep == []


def test_connection_error_retried_then_raises(no_sleep):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()  # порт свободен — соединение отклоняется
    with pytest.raises(FetchError):
        fetch_url(f"http://127.0.0.1:{port}/sub?token=SECRET", timeout=1, retries=1)
    assert no_sleep == [2.0]


def test_error_message_hides_url_path(no_sleep):
    with pytest.raises(FetchError) as excinfo:
        fetch_url("ftp://panel.example.com/sub/SECRETTOKEN")
    assert "SECRETTOKEN" not in str(excinfo.value)
    assert no_sleep == []  # неверная схема — повторять бессмысленно


def test_subscription_requires_http_200(no_sleep):
    """Страница ошибки панели — это сбой, а не «подписка без серверов»."""
    server = HttpServer(_response(403, b"<html>blocked</html>"))
    with pytest.raises(FetchError, match="HTTP 403"):
        fetch_subscription(server.url())


def test_subscription_headers_and_user_agent(no_sleep):
    server = HttpServer(_response(200, b"body", "Subscription-Userinfo: upload=1; total=10\r\n"))
    result = fetch_subscription(
        server.url("/sub?x=1"), user_agent="v2rayN/6.0", headers={"x-hwid": "abc"}
    )
    assert parse_userinfo(result.headers["subscription-userinfo"]) == {"upload": 1, "total": 10}
    request = server.requests[0]
    assert request.startswith(b"GET /sub?x=1 HTTP/1.1\r\n")
    assert b"User-Agent: v2rayN/6.0\r\n" in request
    assert b"x-hwid: abc\r\n" in request
    assert f"Host: 127.0.0.1:{server.port}\r\n".encode() in request


def test_redirect_followed(no_sleep):
    target = HttpServer(_response(200, b"final"))
    first = HttpServer(_response(302, extra=f"Location: {target.url('/new')}\r\n"))
    assert fetch_url(first.url()).body == b"final"
    assert target.requests[0].startswith(b"GET /new ")


def test_hostname_resolved_through_bootstrap(monkeypatch, no_sleep):
    """С bootstrap имя хоста разрешают свои резолверы, а не системный DNS
    (тот ходит через перехват и при упавшем Xray не отвечает)."""
    server = HttpServer(_response(200, b"ok"))
    asked: list[tuple] = []

    def fake_resolve(name, bootstrap, *, mark=None):
        asked.append((name, tuple(bootstrap), mark))
        return ["127.0.0.1"]

    monkeypatch.setattr(fetch, "resolve_domain", fake_resolve)
    result = fetch_url(
        f"http://panel.example.com:{server.port}/sub", bootstrap=["udp://203.0.113.53"]
    )
    assert result.body == b"ok"
    assert asked == [("panel.example.com", ("udp://203.0.113.53",), None)]
    assert f"Host: panel.example.com:{server.port}\r\n".encode() in server.requests[0]


# --- CONNECT-туннель ------------------------------------------------------------


class TunnelProxy(threading.Thread):
    def __init__(self, reply: bytes, then: bytes = b""):
        super().__init__(daemon=True)
        self.reply, self.then = reply, then
        self.requests: list[bytes] = []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.start()

    def run(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                try:
                    request = b""
                    while b"\r\n\r\n" not in request:
                        request += conn.recv(4096)
                    self.requests.append(request)
                    conn.sendall(self.reply + self.then)
                    conn.recv(1)
                except OSError:
                    pass


def test_open_tunnel_consumes_exactly_the_reply():
    """После ответа прокси сразу идут данные туннеля: ни байта лишнего не съесть
    и не оставить (иначе рвётся TLS-рукопожатие — ответ Xray кончается пустой строкой)."""
    proxy = TunnelProxy(
        b"HTTP/1.1 200 Connection established\r\nProxy-Agent: test\r\n\r\n", b"TUNNEL-DATA"
    )
    sock = open_tunnel(
        ("127.0.0.1", proxy.port), "origin.example.com", 443,
        timeout=3, user="xgw", password="secret",
    )
    try:
        received = b""
        while len(received) < len(b"TUNNEL-DATA"):
            received += sock.recv(64)
        assert received == b"TUNNEL-DATA"
    finally:
        sock.close()
    assert proxy.requests[0].startswith(b"CONNECT origin.example.com:443 HTTP/1.1\r\n")
    assert b"Proxy-Authorization: Basic eGd3OnNlY3JldA==\r\n" in proxy.requests[0]


def test_open_tunnel_rejected():
    proxy = TunnelProxy(b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
    with pytest.raises(ProxyError) as excinfo:
        open_tunnel(("127.0.0.1", proxy.port), "origin.example.com", 443, timeout=3)
    assert excinfo.value.status == 407


def test_fetch_through_proxy_uses_connect(no_sleep):
    """Подписка через http-in Xray: CONNECT, затем обычный запрос внутри туннеля."""
    proxy = TunnelProxy(b"HTTP/1.1 200 Connection established\r\n\r\n", _response(200, b"via"))
    result = fetch_url("http://panel.example.com/sub", proxy=("127.0.0.1", proxy.port))
    assert result.body == b"via"
    assert proxy.requests[0].startswith(b"CONNECT panel.example.com:80 HTTP/1.1\r\n")


# --- DNS ------------------------------------------------------------------------


def _answer(query: bytes, ip: tuple[int, int, int, int]) -> bytes:
    """Ответ: заголовок запроса с ancount=1 + имя-указатель + A-запись."""
    return (
        query[:6]
        + struct.pack(">H", 1)
        + query[8:]
        + b"\xc0\x0c"
        + struct.pack(">HHIH", 1, 1, 60, 4)
        + bytes(ip)
    )


def test_dns_wire_roundtrip():
    query = _dns_query("one.example.com")
    assert _parse_a_answers(_answer(query, (203, 0, 113, 10))) == ["203.0.113.10"]


def test_dns_wire_broken():
    with pytest.raises(ResolveError):
        _parse_a_answers(b"short")
    query = _dns_query("one.example.com")
    with pytest.raises(ResolveError):  # указатель обрезан на первом байте
        _parse_a_answers(query[:6] + struct.pack(">H", 1) + query[8:] + b"\xc0")


def test_dns_query_rejects_bad_names():
    assert _dns_query("пример.рф")[12:].startswith(b"\x0cxn--e1afmkfd\x08xn--p1ai\x00")  # IDNA
    for name in ("", "a..b", "x" * 64 + ".example.com"):
        with pytest.raises(ResolveError):
            _dns_query(name)


def test_plain_dns_ignores_mismatched_reply():
    """Датаграмма с чужим ID запроса (подделка) пропускается, ждём настоящий ответ."""
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]

    def serve():
        query, peer = server.recvfrom(4096)
        forged = bytes([query[0] ^ 0xFF, query[1]]) + query[2:]
        server.sendto(_answer(forged, (203, 0, 113, 66)), peer)
        server.sendto(_answer(query, (203, 0, 113, 10)), peer)

    threading.Thread(target=serve, daemon=True).start()
    try:
        assert plain_dns("127.0.0.1", "one.example.com", timeout=3, port=port) == ["203.0.113.10"]
    finally:
        server.close()


def test_resolve_domain_sorted_and_falls_through(monkeypatch):
    calls: list[str] = []

    def fake_doh(entry, name, *, mark=None, timeout=8.0):
        calls.append(entry)
        raise OSError("blocked")

    def fake_plain(server, name, *, mark=None, timeout=5.0, port=53):
        calls.append(server)
        return ["203.0.113.20", "203.0.113.3", "203.0.113.20"]

    monkeypatch.setattr(fetch, "doh_query", fake_doh)
    monkeypatch.setattr(fetch, "plain_dns", fake_plain)
    ips = fetch.resolve_domain("nl.example.com", ["https://1.1.1.1/dns-query", "udp://77.88.8.8"])
    assert ips == ["203.0.113.3", "203.0.113.20"]  # без дублей, порядок стабилен
    assert calls == ["https://1.1.1.1/dns-query", "77.88.8.8"]
    with pytest.raises(ResolveError):
        fetch.resolve_domain("nl.example.com", ["https://1.1.1.1/dns-query"])


def test_bootstrap_udp_with_port(monkeypatch):
    asked: list[tuple[str, int]] = []

    def fake_plain(server, name, *, mark=None, timeout=5.0, port=53):
        asked.append((server, port))
        return ["203.0.113.5"]

    monkeypatch.setattr(fetch, "plain_dns", fake_plain)
    fetch.resolve_domain("nl.example.com", ["udp://203.0.113.53:5353"])
    fetch.resolve_domain("nl.example.com", ["udp://77.88.8.8"])
    assert asked == [("203.0.113.53", 5353), ("77.88.8.8", 53)]


def test_nxdomain_is_told_apart_from_a_resolver_failure(monkeypatch):
    """«Такого имени нет» — определённый ответ: сервер с таким адресом недоступен, пока
    домен не вернут. Таймаут или SERVFAIL — сбой резолвера, по нему судить нельзя."""
    query = _dns_query("gone.example.com")
    nxdomain = query[:2] + struct.pack(">H", 0x8183) + query[4:]
    with pytest.raises(fetch.NoSuchDomain, match="NXDOMAIN"):
        _parse_a_answers(nxdomain)
    servfail = query[:2] + struct.pack(">H", 0x8182) + query[4:]
    with pytest.raises(ResolveError, match="RCODE 2") as caught:
        _parse_a_answers(servfail)
    assert not isinstance(caught.value, fetch.NoSuchDomain)
    assert _parse_a_answers(query[:2] + struct.pack(">H", 0x8180) + query[4:]) == []  # NODATA

    replies: dict[str, object] = {}

    def fake_doh(entry, name, *, mark=None, timeout=8.0):
        reply = replies[entry]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(fetch, "doh_query", fake_doh)
    first, second = "https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query"
    replies.update({first: OSError("timed out"), second: fetch.NoSuchDomain("NXDOMAIN")})
    with pytest.raises(fetch.NoSuchDomain, match="домен gone"):
        fetch.resolve_domain("gone.example.com", [first, second])
    replies[second] = []  # имя есть, адреса IPv4 нет — серверу подключаться некуда
    with pytest.raises(fetch.NoSuchDomain, match="нет адреса IPv4"):
        fetch.resolve_domain("gone.example.com", [first, second])
    replies[second] = OSError("timed out")  # не ответил никто — это не «домена нет»
    with pytest.raises(ResolveError) as caught:
        fetch.resolve_domain("gone.example.com", [first, second])
    assert not isinstance(caught.value, fetch.NoSuchDomain)
    # Один резолвер имени не знает, другой знает — имя есть.
    replies.update({first: fetch.NoSuchDomain("NXDOMAIN"), second: ["203.0.113.9"]})
    assert fetch.resolve_domain("gone.example.com", [first, second]) == ["203.0.113.9"]
