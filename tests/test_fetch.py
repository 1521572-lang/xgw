"""Тесты fetch: file://, повторы, коды ответа, CONNECT-туннель, DNS (без внешней сети)."""

import shutil
import socket
import ssl
import struct
import subprocess
import threading
import time

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
    result = fetch_url(path.as_uri())
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

    def fake_resolve(name, bootstrap, *, mark=None, cancel=None, public_only=False):
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

    def fake_doh(entry, name, *, mark=None, timeout=8.0, cancel=None):
        calls.append(entry)
        raise OSError("blocked")

    def fake_plain(server, name, *, mark=None, timeout=5.0, port=53, cancel=None):
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

    def fake_plain(server, name, *, mark=None, timeout=5.0, port=53, cancel=None):
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

    def fake_doh(entry, name, *, mark=None, timeout=8.0, cancel=None):
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


# --- прерывание остановкой демона (наблюдение Н1 отчёта о Д1/Д2) ------------------


def _cancel_after(seconds: float) -> threading.Event:
    cancel = threading.Event()
    timer = threading.Timer(seconds, cancel.set)
    timer.daemon = True
    timer.start()
    return cancel


class SilentServer(threading.Thread):
    """Принимает соединение, читает запрос, отдаёт `prefix` и замолкает, не закрывая его."""

    def __init__(self, prefix: bytes = b""):
        super().__init__(daemon=True)
        self.prefix = prefix
        self.conns: list[socket.socket] = []
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.start()

    def run(self):
        while True:
            try:
                conn, _ = self.sock.accept()
                self.conns.append(conn)
                conn.recv(65536)
                conn.sendall(self.prefix)
            except OSError:
                return


@pytest.mark.parametrize(
    ("prefix", "via_proxy"),
    [
        (b"", True),  # http-in Xray не отвечает на CONNECT
        (b"", False),  # нет заголовков ответа
        (b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n" + b"x" * 10, False),  # тело встало
    ],
    ids=["connect", "headers", "body"],
)
def test_cancel_interrupts_the_wait_for_the_network(prefix, via_proxy):
    """Остановка демона прерывает ожидание сети за доли секунды, а не по таймауту (15 с
    на каждую из до 4 попыток) — systemd ждёт остановки не дольше 90 с."""
    server = SilentServer(prefix)
    url = "http://panel.example.com/sub" if via_proxy else f"http://127.0.0.1:{server.port}/s"
    started = time.monotonic()
    with pytest.raises(fetch.Cancelled):
        fetch_url(
            url, timeout=5, proxy=("127.0.0.1", server.port) if via_proxy else None,
            cancel=_cancel_after(0.3),
        )
    assert time.monotonic() - started < 2
    assert len(server.conns) == 1  # и повторов после остановки нет


def test_cancel_interrupts_a_hanging_connect():
    """Соединение, на которое никто не отвечает (очередь слушателя занята — SYN теряется,
    как у недоступного сервера при прямом запросе), тоже прерывается."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(0)
    port = listener.getsockname()[1]
    filler = socket.create_connection(("127.0.0.1", port), timeout=3)  # занял очередь
    try:
        started = time.monotonic()
        with pytest.raises(fetch.Cancelled):
            fetch_url(f"http://127.0.0.1:{port}/sub", timeout=5, cancel=_cancel_after(0.3))
        assert time.monotonic() - started < 2
    finally:
        filler.close()
        listener.close()


def test_cancel_interrupts_the_pause_before_a_retry():
    """Паузы между попытками (2, 4, 8 с) остановка тоже прерывает, а новой попытки нет."""
    server = HttpServer(_response(503))
    started = time.monotonic()
    with pytest.raises(fetch.Cancelled):
        fetch_subscription(server.url(), cancel=_cancel_after(0.3))
    assert time.monotonic() - started < 1.5  # первая пауза — 2 с
    assert len(server.requests) == 1


def test_cancelled_fetch_does_not_even_connect():
    server = HttpServer(_response(200, b"ok"))
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(fetch.Cancelled):
        fetch_url(server.url(), cancel=cancel)
    time.sleep(0.2)
    assert server.requests == []


def test_cancel_that_never_comes_changes_nothing():
    """С событием, которое не выставлено, запрос — как прежде: повтор после 503,
    перенаправление, тело целиком."""
    target = HttpServer(_response(200, b"x" * 300_000))
    redirect = _response(302, extra=f"Location: {target.url('/new')}\r\n")
    server = HttpServer(_response(503), redirect)
    result = fetch_url(server.url(), backoffs=(0.1,), cancel=threading.Event())
    assert result.status == 200 and result.body == b"x" * 300_000
    assert len(server.requests) == 2


@pytest.fixture(scope="module")
def tls_files(tmp_path_factory):
    """Самоподписанный сертификат на localhost — только для этих тестов."""
    openssl = shutil.which("openssl")
    if not openssl:
        pytest.skip("нет openssl — тесты https пропущены")
    directory = tmp_path_factory.mktemp("tls")
    cert, key = directory / "cert.pem", directory / "key.pem"
    proc = subprocess.run(
        [openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
         "-keyout", str(key), "-out", str(cert), "-subj", "/CN=localhost",
         "-addext", "subjectAltName=DNS:localhost"],
        capture_output=True, timeout=60,
    )
    if proc.returncode != 0:
        pytest.skip("openssl не выпустил тестовый сертификат")
    return cert, key


class TlsServer(threading.Thread):
    """https на localhost: пауза перед рукопожатием, затем ответ по шагам (байты или паузы)."""

    def __init__(self, cert, key, script: list, delay: float = 0.0):
        super().__init__(daemon=True)
        self.delay = delay
        self.script = script
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(str(cert), str(key))
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
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket):
        try:
            time.sleep(self.delay)
            tls = self.context.wrap_socket(conn, server_side=True)
            tls.recv(65536)
            for step in self.script:
                if isinstance(step, bytes):
                    tls.sendall(step)
                else:
                    time.sleep(step)
            tls.close()
        except (OSError, ssl.SSLError):
            conn.close()


@pytest.fixture()
def trust(tls_files, monkeypatch):
    """Подписка по https доверяет тестовому сертификату."""
    cert, _key = tls_files
    create = ssl.create_default_context
    monkeypatch.setattr(fetch.ssl, "create_default_context", lambda: create(cafile=str(cert)))
    return tls_files


@pytest.mark.parametrize("cancel", [None, threading.Event()], ids=["without", "with"])
def test_https_waits_longer_than_a_slice(trust, cancel):
    """Рукопожатие и тело, которые ждут дольше куска ожидания (CANCEL_SLICE), продолжаются
    с того места, где ждали данных."""
    body = b"x" * 200_000
    head = f"HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\n\r\n".encode()
    server = TlsServer(*trust, [head + body[:1000], 1.2, body[1000:]], delay=1.2)
    result = fetch_url(f"https://localhost:{server.port}/sub", timeout=5, cancel=cancel)
    assert result.status == 200 and result.body == body


def test_cancel_interrupts_the_tls_handshake(trust):
    server = TlsServer(*trust, [_response(200, b"ok")], delay=5.0)
    started = time.monotonic()
    with pytest.raises(fetch.Cancelled):
        fetch_url(f"https://localhost:{server.port}/sub", timeout=5, cancel=_cancel_after(0.3))
    assert time.monotonic() - started < 2


def test_cancel_interrupts_dns_and_is_not_a_resolver_failure(monkeypatch):
    """Ожидание ответа DNS прерывается, а прерванный опрос резолвера не превращается в
    «резолвер не ответил» и не переходит к следующему."""
    silent = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    silent.bind(("127.0.0.1", 0))
    try:
        port = silent.getsockname()[1]
        started = time.monotonic()
        with pytest.raises(fetch.Cancelled):
            plain_dns("127.0.0.1", "nl.example.com", timeout=5, port=port,
                      cancel=_cancel_after(0.3))
        assert time.monotonic() - started < 2
    finally:
        silent.close()

    asked: list[str] = []

    def fake_doh(entry, name, *, mark=None, timeout=8.0, cancel=None):
        asked.append(entry)
        raise fetch.Cancelled

    monkeypatch.setattr(fetch, "doh_query", fake_doh)
    with pytest.raises(fetch.Cancelled):
        fetch.resolve_domain(
            "nl.example.com", ["https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query"],
            cancel=threading.Event(),
        )
    assert asked == ["https://1.1.1.1/dns-query"]


# --- 0.2.0: DoT, подменённые ответы, запасные адреса подписки -----------------------------


def test_dot_resolver_entry_and_encrypted_only(monkeypatch):
    """tls://адрес[:порт] — DNS-over-TLS (порт 853 по умолчанию); для доменов подписок
    спрашиваются только шифрованные резолверы."""
    asked: list[tuple] = []

    def fake_dot(server, name, *, port=853, timeout=8.0, mark=None, cancel=None):
        asked.append((server, port))
        return ["203.0.113.7"]

    monkeypatch.setattr(fetch, "dot_query", fake_dot)
    assert fetch.resolve_domain("sub.example.com", ["tls://77.88.8.8"]) == ["203.0.113.7"]
    assert fetch.resolve_domain("sub.example.com", ["tls://9.9.9.11:8853"]) == ["203.0.113.7"]
    assert asked == [("77.88.8.8", 853), ("9.9.9.11", 8853)]
    entries = ["https://1.1.1.1/dns-query", "udp://77.88.8.8", "tls://77.88.8.8"]
    assert fetch.encrypted(entries) == ["https://1.1.1.1/dns-query", "tls://77.88.8.8"]


def test_spoofed_answer_is_skipped_for_subscription_hosts(monkeypatch):
    """Ответ из одних служебных адресов (заглушка провайдера) — подмена: резолвер считается
    отказавшим, адрес даёт следующий. Без public_only ответ берётся как есть."""
    fetch._resolver_down.clear()
    replies = {"udp://203.0.113.53": ["127.0.0.1"], "https://1.1.1.1/dns-query": ["203.0.113.8"]}

    def fake_plain(server, name, *, timeout=5.0, mark=None, port=53, cancel=None):
        return replies[f"udp://{server}"]

    def fake_doh(url, name, *, timeout=8.0, mark=None, cancel=None):
        return replies[url]

    monkeypatch.setattr(fetch, "plain_dns", fake_plain)
    monkeypatch.setattr(fetch, "doh_query", fake_doh)
    entries = ["udp://203.0.113.53", "https://1.1.1.1/dns-query"]
    assert fetch.resolve_domain("sub.example.com", entries) == ["127.0.0.1"]
    assert fetch.resolve_domain("sub.example.com", entries, public_only=True) == ["203.0.113.8"]
    assert fetch.is_bogon("10.1.2.3") and fetch.is_bogon("0.0.0.0") and fetch.is_bogon("x")
    assert not fetch.is_bogon("77.88.55.242")
    fetch._resolver_down.clear()


def test_subscription_falls_back_to_the_known_address(monkeypatch, no_sleep):
    """Резолверы не ответили — подписка идёт по адресу из кэша (fallback); удачный запрос
    сообщает имя и адрес, с которым соединился. udp:// для подписки не спрашивается."""
    server = HttpServer(_response(200, b"vless://x"))
    asked: list[tuple] = []

    def no_dns(name, bootstrap, *, mark=None, cancel=None, public_only=False):
        asked.append((tuple(bootstrap), public_only))
        raise fetch.ResolveError("резолверы молчат")

    monkeypatch.setattr(fetch, "resolve_domain", no_dns)
    url = f"http://sub.example.com:{server.port}/s"
    with pytest.raises(FetchError):
        fetch_subscription(url, bootstrap=["udp://203.0.113.53"], retries=0)
    result = fetch_subscription(
        url, bootstrap=["udp://203.0.113.53", "tls://77.88.8.8"], retries=0,
        fallback={"sub.example.com": ["127.0.0.1"]},
    )
    assert result.body == b"vless://x"
    assert (result.host, result.address, result.from_fallback) == (
        "sub.example.com", "127.0.0.1", True)
    assert asked[-1] == (("tls://77.88.8.8",), True)


def test_redirect_keeps_credentials_on_the_same_origin_only():
    """Четвёртый аудит 0.2.0: Authorization и Cookie не уходят на другой адрес (как у curl и
    requests), остальные заголовки подписки — уходят; с https на http — отказ."""
    sent = {"Authorization": "Bearer t", "Cookie": "a=b", "X-Hwid": "h1"}
    home = "https://sub.example.net/a"
    assert fetch.redirect_headers(home, "https://sub.example.net:443/b", sent) == sent
    assert fetch.redirect_headers(home, "https://cdn.example.org/b", sent) == {"X-Hwid": "h1"}
    port = fetch.redirect_headers(home, "https://sub.example.net:8443/", sent)
    assert "Authorization" not in port
    with pytest.raises(fetch.FetchError, match="с https на http"):
        fetch.redirect_headers(home, "http://sub.example.net/a", sent)
    # http → https того же хоста — уже другой адрес (порт и схема): без учётных заголовков.
    assert fetch.redirect_headers("http://a.example.net/", "https://a.example.net/", sent) == {
        "X-Hwid": "h1"}
