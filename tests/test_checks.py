"""Детектор «тишины» и классификация сканов — на локальных фейковых серверах."""

import contextlib
import shutil
import socket
import ssl
import subprocess
import threading
import time

import pytest

from xgw.watch.checks import DownloadResult, http_get_via_proxy, tcp_check, trace_location
from xgw.watch.scan import classify

BODY = 65536
HEADERS = b"HTTP/1.1 200 OK\r\nContent-Length: 65536\r\nConnection: close\r\n\r\n"
URL = "http://origin.example.com/big"


class FakeServer(threading.Thread):
    """Локальный сервер: на каждое соединение читает запрос и выполняет сценарий —
    список шагов: bytes (отправить) или float (пауза, секунды)."""

    def __init__(self, script: list):
        super().__init__(daemon=True)
        self.script = script
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
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket):
        try:
            self.requests.append(conn.recv(65536))
            for step in self.script:
                if isinstance(step, bytes):
                    conn.sendall(step)
                else:
                    time.sleep(step)
        except OSError:
            pass
        finally:
            conn.close()


@pytest.fixture()
def serve():
    servers: list[FakeServer] = []

    def factory(*script) -> FakeServer:
        server = FakeServer(list(script))
        servers.append(server)
        return server

    yield factory
    for server in servers:
        server.sock.close()


@pytest.fixture(scope="module")
def unbuffered_loopback():
    """Пропуск, если локальный HTTP-фильтр (веб-защита антивируса и т. п.) придерживает
    неполные ответы на loopback: тогда «тишину посреди тела» открытым HTTP не
    воспроизвести. Эти же сценарии поверх TLS проверяются ниже — их фильтр не видит.
    """
    server = FakeServer([HEADERS + b"x" * 1024, 2.0])
    request = b"GET http://origin.example.com/big HTTP/1.1\r\nHost: origin.example.com\r\n\r\n"
    try:
        with socket.create_connection(("127.0.0.1", server.port), timeout=2) as client:
            client.sendall(request)
            client.settimeout(1.0)
            received = 0
            try:
                while received < len(HEADERS) + 1024:
                    chunk = client.recv(65536)
                    if not chunk:
                        break
                    received += len(chunk)
            except TimeoutError:
                pass
    finally:
        server.sock.close()
    if received < len(HEADERS) + 1024:
        pytest.skip("HTTP на loopback буферизует сторонний фильтр — сценарий проверяется по TLS")


def _get(server: FakeServer, **kwargs) -> DownloadResult:
    kwargs.setdefault("timeout", 5)
    kwargs.setdefault("silence", 0.5)
    return http_get_via_proxy("127.0.0.1", server.port, URL, **kwargs)


def test_full_download_ok(serve):
    result = _get(serve(HEADERS + b"x" * BODY))
    assert result.ok and result.status == 200
    assert result.downloaded == BODY  # считаются байты тела, без заголовков
    assert not result.stalled
    assert classify(result, 1.0) == "OK"


def test_headers_split_between_packets(serve):
    """Конец заголовков может прийти в следующем пакете — это не сбой."""
    result = _get(serve(HEADERS[:-2], 0.1, HEADERS[-2:] + b"x" * BODY))
    assert result.ok and result.downloaded == BODY


def test_freeze_detected_as_stall(serve, unbuffered_loopback):
    result = _get(serve(HEADERS + b"x" * 16384, 3.0))
    assert not result.ok
    assert result.frozen  # часть тела пришла, потом тишина
    assert result.downloaded == 16384
    assert classify(result, 5.0) == "FROZEN"


def test_silence_after_headers_is_stall_before_body(serve):
    """Заголовки без единого байта тела — STALL_BEFORE_BODY, а не FROZEN."""
    result = _get(serve(HEADERS, 3.0))
    assert result.stalled and result.downloaded == 0 and not result.frozen
    assert classify(result, 5.0) == "STALL_BEFORE_BODY"


def test_silence_before_headers_is_stall_before_body(serve):
    result = _get(serve(3.0))
    assert result.stalled and not result.frozen
    assert classify(result, 5.0) == "STALL_BEFORE_BODY"


def test_truncated_body_is_not_ok(serve):
    """Соединение закрыли после 16 КиБ из 64 — загрузка не состоялась."""
    result = _get(serve(HEADERS + b"x" * 16384))
    assert not result.ok and result.kind == "truncated"
    assert result.downloaded == 16384
    assert classify(result, 0.1) == "CONNECT_FAIL"


def test_proxy_auth_failure_is_not_ok(serve):
    """Неверный пароль probe-inbound (407) не должен выглядеть как живой сервер."""
    result = _get(serve(b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n"))
    assert not result.ok and result.status == 407 and result.kind == "proxy"
    assert classify(result, 0.1) == "CONNECT_FAIL"


def test_http_error_is_not_ok(serve):
    result = _get(serve(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n"))
    assert not result.ok and result.status == 503


def test_slow_drip_hits_total_timeout(serve, unbuffered_loopback):
    """Сервер «капает» по байту чаще порога тишины — спасает общий таймаут."""
    drip: list = [HEADERS]
    for _ in range(40):
        drip += [b"x", 0.1]
    result = _get(serve(*drip), max_total=1.0)
    assert not result.ok and result.kind == "timeout"
    assert 0 < result.downloaded < 40
    assert classify(result, 1.0) == "TIMEOUT"


def test_chunked_body_ok(serve):
    head = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
    result = _get(serve(head + b"5\r\nhello\r\n0\r\n\r\n", 3.0))
    assert result.ok


def test_proxy_credentials_are_sent(serve):
    server = serve(HEADERS + b"x" * BODY)
    assert _get(server, proxy_user="xgw", proxy_pass="secret").ok
    assert b"Proxy-Authorization: Basic eGd3OnNlY3JldA==" in server.requests[0]
    assert server.requests[0].startswith(b"GET http://origin.example.com/big HTTP/1.1\r\n")


def test_connect_fail():
    result = http_get_via_proxy("127.0.0.1", 1, URL, timeout=2, silence=1.0)
    assert not result.ok
    assert classify(result, 0.1) == "CONNECT_FAIL"


def test_classify_verdicts():
    ok = DownloadResult(ok=True, downloaded=70000)
    assert classify(ok, 1.0) == "OK"
    assert classify(ok, 5.0) == "SLOW"
    frozen = DownloadResult(ok=False, downloaded=16384, stalled=True)
    assert classify(frozen, 5.0) == "FROZEN"
    stall = DownloadResult(ok=False, downloaded=0, stalled=True)
    assert classify(stall, 5.0) == "STALL_BEFORE_BODY"
    timeout = DownloadResult(ok=False, kind="timeout", error="таймаут соединения")
    assert classify(timeout, 5.0) == "TIMEOUT"


def test_tcp_check_local(serve):
    assert tcp_check("127.0.0.1", serve(HEADERS).port, timeout=2)
    assert not tcp_check("127.0.0.1", 1, timeout=0.5)


def test_trace_location_via_proxy(serve):
    body = b"fl=1f1\nip=203.0.113.5\nloc=nl\ntls=off\n"
    head = b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(body)
    via = ("127.0.0.1", serve(head + body).port)
    assert trace_location("http://trace.example.com/cdn-cgi/trace", via=via) == "NL"
    broken = ("127.0.0.1", serve(b"HTTP/1.1 502 Bad Gateway\r\n\r\n").port)
    assert trace_location("http://trace.example.com/cdn-cgi/trace", via=broken) is None


# --- https через CONNECT: так устроены probe.url и trace_url по умолчанию -------


class ConnectProxy(threading.Thread):
    """Минимальный http-inbound: отвечает на CONNECT как Xray и склеивает потоки."""

    REPLY = b"HTTP/1.1 200 Connection established\r\n\r\n"

    def __init__(self, target_port: int, reply: bytes = REPLY):
        super().__init__(daemon=True)
        self.target_port = target_port
        self.reply = reply
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
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket):
        try:
            request = b""
            while b"\r\n\r\n" not in request:
                request += conn.recv(4096)
            self.requests.append(request)
            conn.sendall(self.reply)
            if not self.reply.startswith(b"HTTP/1.1 2"):
                conn.close()
                return
            upstream = socket.create_connection(("127.0.0.1", self.target_port))
        except OSError:
            conn.close()
            return
        threading.Thread(target=self._pipe, args=(conn, upstream), daemon=True).start()
        self._pipe(upstream, conn)

    @staticmethod
    def _pipe(source: socket.socket, sink: socket.socket):
        try:
            while data := source.recv(65536):
                sink.sendall(data)
        except OSError:
            pass
        finally:
            for sock in (source, sink):
                with contextlib.suppress(OSError):
                    sock.shutdown(socket.SHUT_RDWR)


@pytest.fixture(scope="module")
def tls_files(tmp_path_factory):
    """Самоподписанный сертификат на localhost — только для этого теста."""
    openssl = shutil.which("openssl")
    if not openssl:
        pytest.skip("нет openssl — тест https через CONNECT пропущен")
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


class TlsOrigin(threading.Thread):
    def __init__(self, cert, key, script: list, delay: float = 0.0):
        super().__init__(daemon=True)
        self.delay = delay  # пауза перед рукопожатием TLS
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(str(cert), str(key))
        self.script = script
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
                elif step == "read":  # следующий запрос в том же соединении
                    self.second = tls.recv(65536)
                else:
                    time.sleep(step)
            tls.close()
        except (OSError, ssl.SSLError):
            conn.close()


def test_https_download_through_connect_tunnel(tls_files):
    cert, key = tls_files
    origin = TlsOrigin(cert, key, [HEADERS + b"x" * BODY])
    proxy = ConnectProxy(origin.port)
    result = http_get_via_proxy(
        "127.0.0.1", proxy.port, f"https://localhost:{origin.port}/big",
        timeout=5, silence=2, proxy_user="xgw", proxy_pass="secret",
        tls_context=ssl.create_default_context(cafile=str(cert)),
    )
    assert result.ok, result.error
    assert result.downloaded == BODY
    assert proxy.requests[0].startswith(f"CONNECT localhost:{origin.port} HTTP/1.1".encode())
    assert b"Proxy-Authorization: Basic eGd3OnNlY3JldA==" in proxy.requests[0]


def test_https_freeze_through_connect_tunnel(tls_files):
    cert, key = tls_files
    origin = TlsOrigin(cert, key, [HEADERS + b"x" * 16384, 3.0])
    proxy = ConnectProxy(origin.port)
    result = http_get_via_proxy(
        "127.0.0.1", proxy.port, f"https://localhost:{origin.port}/big",
        timeout=5, silence=0.5, tls_context=ssl.create_default_context(cafile=str(cert)),
    )
    assert result.frozen and result.downloaded == 16384
    assert classify(result, 1.0) == "FROZEN"


def test_https_slow_drip_hits_total_timeout(tls_files):
    cert, key = tls_files
    drip: list = [HEADERS]
    for _ in range(40):
        drip += [b"x", 0.1]
    origin = TlsOrigin(cert, key, drip)
    proxy = ConnectProxy(origin.port)
    result = http_get_via_proxy(
        "127.0.0.1", proxy.port, f"https://localhost:{origin.port}/big", timeout=5,
        silence=0.5, max_total=1.0, tls_context=ssl.create_default_context(cafile=str(cert)),
    )
    assert result.kind == "timeout" and 0 < result.downloaded < 40
    assert classify(result, 1.0) == "TIMEOUT"


def test_https_silence_after_headers_is_stall_before_body(tls_files):
    cert, key = tls_files
    origin = TlsOrigin(cert, key, [HEADERS, 3.0])
    proxy = ConnectProxy(origin.port)
    result = http_get_via_proxy(
        "127.0.0.1", proxy.port, f"https://localhost:{origin.port}/big",
        timeout=5, silence=0.5, tls_context=ssl.create_default_context(cafile=str(cert)),
    )
    assert result.stalled and result.downloaded == 0
    assert classify(result, 1.0) == "STALL_BEFORE_BODY"


def test_connect_rejected_by_proxy():
    proxy = ConnectProxy(1, reply=b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
    result = http_get_via_proxy(
        "127.0.0.1", proxy.port, "https://origin.example.com/big", timeout=5, silence=1
    )
    assert not result.ok and result.kind == "proxy" and result.status == 407
    assert classify(result, 0.1) == "CONNECT_FAIL"


def test_probe_request_carries_the_configured_user_agent(serve):
    """probe.user_agent доходит до сервера; без него — «xgw/<версия>». Сжатия проба не
    просит: тело нужно целиком, по нему считается расход трафика."""
    server = serve(HEADERS + b"x" * BODY)
    agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
    assert _get(server, user_agent=agent).ok
    assert f"User-Agent: {agent}\r\n".encode() in server.requests[0]
    assert b"Accept-Encoding" not in server.requests[0]
    assert _get(server).ok
    assert b"User-Agent: xgw/0.1\r\n" in server.requests[1]
    assert _get(server, user_agent="Bad\r\nX-Injected: 1").ok  # перевод строки не пролезет
    assert b"X-Injected" not in server.requests[2]


def test_scan_sends_probe_user_agent_and_keeps_the_failure_kind(serve):
    from xgw.config import Config
    from xgw.generator.builder import NodeInfo
    from xgw.watch import scan

    cfg = Config()
    cfg.probe.url = URL
    cfg.probe.user_agent = "ProbeAgent/9"
    server = serve(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 9\r\n\r\nForbidden")
    node = NodeInfo("aaaaaaaa", "spare-nl-aaaa", "probe-nl-aaaa", server.port, "spare")
    result = scan.scan_node(node, cfg, probe_pass="secret", silence=0.5)
    assert b"User-Agent: ProbeAgent/9\r\n" in server.requests[0]
    assert (result.verdict, result.kind, result.status, result.error) == (
        "CONNECT_FAIL", "http", 403, "HTTP 403")


# --- прерывание остановкой демона (отчёт 0.1.15, Д2) ------------------------------


def _cancel_after(seconds: float) -> threading.Event:
    cancel = threading.Event()
    timer = threading.Timer(seconds, cancel.set)
    timer.daemon = True
    timer.start()
    return cancel


@pytest.mark.parametrize(
    ("script", "url"),
    [
        ([5.0], "https://origin.example.com/"),  # прокси молчит в ответ на CONNECT
        # Туннель открыт, а сервер не отвечает на ClientHello: так на машине скан ждал 15 с.
        ([ConnectProxy.REPLY, 5.0], "https://origin.example.com/"),
        ([5.0], URL),  # нет заголовков ответа
        ([HEADERS + b"x" * 1024, 5.0], URL),  # тело остановилось
    ],
    ids=["connect", "tls", "headers", "body"],
)
def test_cancel_interrupts_every_wait(serve, script, url):
    server = serve(*script)
    started = time.monotonic()
    result = http_get_via_proxy(
        "127.0.0.1", server.port, url, timeout=4, silence=4, cancel=_cancel_after(0.3)
    )
    assert time.monotonic() - started < 2
    assert not result.ok and result.kind == "cancelled" and not result.stalled
    assert classify(result, 0.3) == "CANCELLED"


def test_cancelled_probe_does_not_even_connect(serve):
    server = serve(HEADERS + b"x" * BODY)
    cancel = threading.Event()
    cancel.set()
    result = _get(server, cancel=cancel)
    assert result.kind == "cancelled"
    time.sleep(0.2)
    assert server.requests == []


def test_cancel_that_never_comes_changes_nothing(serve):
    """Ожидание кусками не ломает детектор тишины."""
    result = _get(serve(HEADERS, 3.0), cancel=threading.Event())
    assert result.stalled and result.kind == "stall"
    assert classify(result, 5.0) == "STALL_BEFORE_BODY"


def test_https_waits_longer_than_a_slice_with_a_cancel_event(tls_files):
    """Рукопожатие TLS и тело, которые ждут дольше куска ожидания (CANCEL_SLICE),
    продолжаются с того места, где ждали данных."""
    cert, key = tls_files
    origin = TlsOrigin(cert, key, [HEADERS + b"x" * 1024, 1.2, b"x" * (BODY - 1024)], delay=1.2)
    proxy = ConnectProxy(origin.port)
    result = http_get_via_proxy(
        "127.0.0.1", proxy.port, f"https://localhost:{origin.port}/big",
        timeout=5, silence=3, tls_context=ssl.create_default_context(cafile=str(cert)),
        cancel=threading.Event(),
    )
    assert result.ok, result.error
    assert result.downloaded == BODY


def test_rtt_is_a_second_request_on_the_open_connection(tls_files):
    """0.2.0, п. 2.3: после загрузки по https тем же соединением уходит HEAD — его время и
    есть сетевая задержка (rtt_ms), без рукопожатий и файла. Сервер закрыл соединение после
    первого ответа — RTT нет, а проба всё равно удачная."""
    cert, key = tls_files
    head = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"
    keep = HEADERS.replace(b"Connection: close\r\n", b"")
    origin = TlsOrigin(cert, key, [keep + b"x" * BODY, "read", 0.05, head])
    proxy = ConnectProxy(origin.port)
    context = ssl.create_default_context(cafile=str(cert))
    result = http_get_via_proxy(
        "127.0.0.1", proxy.port, f"https://localhost:{origin.port}/big",
        timeout=5, silence=2, tls_context=context, rtt=True,
    )
    assert result.ok and result.rtt_ms is not None and 40 <= result.rtt_ms < 2000
    assert origin.second.startswith(b"HEAD /big HTTP/1.1")
    closing = TlsOrigin(cert, key, [HEADERS + b"x" * BODY])
    proxy = ConnectProxy(closing.port)
    result = http_get_via_proxy(
        "127.0.0.1", proxy.port, f"https://localhost:{closing.port}/big",
        timeout=5, silence=2, tls_context=context, rtt=True,
    )
    assert result.ok and result.rtt_ms is None


def test_own_probe_asks_a_random_part_of_a_known_file(monkeypatch):
    """Анти-ТСПУ 2.0, пробы без шаблона: файл известного размера — случайная его часть, не
    меньше RANDOM_MIN (больше двух записей TLS — «заморозка» на 16–32 КБ ловится); адрес с
    размером в параметрах и trace — целиком, как раньше."""
    from xgw.config import DEFAULT_PROBE_SIZE, DEFAULT_PROBE_URL, Config
    from xgw.generator.builder import NodeInfo
    from xgw.watch import scan as scan_module

    sizes = {scan_module.range_size(DEFAULT_PROBE_URL) for _ in range(200)}
    assert min(sizes) >= scan_module.RANDOM_MIN and max(sizes) <= DEFAULT_PROBE_SIZE
    assert len(sizes) > 50  # длина и правда меняется
    assert scan_module.range_size("https://speed.example/__down?bytes=65536") == 0
    assert scan_module.range_size("https://www.cloudflare.com/cdn-cgi/trace") == 0
    asked: list[int] = []

    def fake(*args, range_end=0, **kwargs):
        asked.append(range_end)
        return scan_module.DownloadResult(ok=True, downloaded=range_end, status=206)

    monkeypatch.setattr(scan_module, "http_get_via_proxy", fake)
    node = NodeInfo("a" * 8, "spare-nl-aaaa", "probe-nl-aaaa", 20001, "spare")
    cfg = Config()
    scan_module.scan_node(node, cfg, probe_pass="p", random_size=True)
    scan_module.scan_node(node, cfg, probe_pass="p")
    assert asked[0] >= scan_module.RANDOM_MIN and asked[1] == 0


def test_range_header_asks_part_of_the_file_and_206_is_success():
    """range_end — Range: bytes=0-…; ответ 206 с телом такой длины — удача."""
    import socket
    import threading

    body = b"x" * 1000
    seen: list[bytes] = []
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def serve():
        conn, _ = server.accept()
        request = b""
        while b"\r\n\r\n" not in request:
            request += conn.recv(4096)
        seen.append(request)
        conn.sendall(b"HTTP/1.1 206 Partial Content\r\nContent-Range: bytes 0-399/1000\r\n"
                     b"Content-Length: 400\r\n\r\n" + body[:400])
        conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    result = http_get_via_proxy("127.0.0.1", port, "http://files.example/f.woff",
                                timeout=5, range_end=400)
    thread.join(5)
    server.close()
    assert result.ok and result.status == 206 and result.downloaded == 400
    assert b"Range: bytes=0-399\r\n" in seen[0]
