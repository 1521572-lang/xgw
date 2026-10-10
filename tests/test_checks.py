"""Детектор «тишины» и классификация сканов — на локальных фейковых серверах."""

import socket
import threading

import pytest

from xgw.watch.checks import DownloadResult, http_get_via_proxy, tcp_check
from xgw.watch.scan import classify

HEADERS = b"HTTP/1.1 200 OK\r\nContent-Length: 65536\r\nConnection: close\r\n\r\n"


class FakeOrigin(threading.Thread):
    """Локальный сервер-«провайдер»: ok / freeze_after / stall_before_body / refuse."""

    def __init__(self, mode: str, body: int = 65536, freeze_after: int = 16384):
        super().__init__(daemon=True)
        self.mode = mode
        self.body = body
        self.freeze_after = freeze_after
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]

    def run(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket):
        try:
            conn.recv(65536)
            if self.mode == "refuse":
                conn.close()
                return
            conn.sendall(HEADERS)
            if self.mode == "stall_before_body":
                import time

                time.sleep(3)
                conn.close()
                return
            payload = b"x" * self.body
            if self.mode == "freeze_after":
                conn.sendall(payload[: self.freeze_after])
                import time

                time.sleep(3)  # «заморозка»: соединение не закрывается, данных нет
                conn.close()
                return
            conn.sendall(payload)
            conn.close()
        except OSError:
            pass


@pytest.fixture()
def ok_origin():
    server = FakeOrigin("ok")
    server.start()
    yield server
    server.sock.close()


@pytest.fixture()
def frozen_origin():
    server = FakeOrigin("freeze_after")
    server.start()
    yield server
    server.sock.close()


def test_full_download_ok(ok_origin):
    result = http_get_via_proxy(
        "127.0.0.1", ok_origin.port, "http://origin.example.com/big",
        timeout=10, silence=1.0,
    )
    assert result.ok
    assert result.downloaded == len(HEADERS) + 65536
    assert not result.stalled


def test_freeze_detected_as_stall(frozen_origin):
    result = http_get_via_proxy(
        "127.0.0.1", frozen_origin.port, "http://origin.example.com/big",
        timeout=10, silence=0.5,
    )
    assert not result.ok
    assert result.stalled
    assert result.frozen  # часть тела пришла, потом тишина
    assert len(HEADERS) <= result.downloaded < len(HEADERS) + 65536


def test_connect_fail():
    result = http_get_via_proxy(
        "127.0.0.1", 1, "http://origin.example.com/big", timeout=2, silence=1.0
    )
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
    timeout = DownloadResult(ok=False, error="таймаут соединения")
    assert classify(timeout, 5.0) == "TIMEOUT"


def test_tcp_check_local(ok_origin):
    assert tcp_check("127.0.0.1", ok_origin.port, timeout=2)
    assert not tcp_check("127.0.0.1", 1, timeout=0.5)
