"""Части стенда сами по себе — без Xray и без root: реле, origin, DNS-заглушка."""

from __future__ import annotations

import contextlib
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest
from origin import dns_answer
from stand import free_port

from xgw.fetch import _dns_query, _parse_a_answers, plain_dns

HERE = Path(__file__).resolve().parent
PAYLOAD = bytes(range(256)) * 256  # 64 КиБ, не похоже на HTTP


def _spawn(script: str, *args: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, str(HERE / script), *args],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    assert proc.stdout is not None and proc.stdout.readline().strip() == "READY"
    return proc


@pytest.fixture()
def upstream():
    """«Сервер»: на любое соединение сразу отдаёт 64 КиБ и ждёт закрытия."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(8)

    def handle(conn: socket.socket) -> None:
        with contextlib.suppress(OSError), conn:
            conn.sendall(PAYLOAD)
            while conn.recv(4096):  # дочитываем до закрытия: иначе close() даст RST
                pass

    def serve() -> None:
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return
            threading.Thread(target=handle, args=(conn,), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    yield server.getsockname()[1]
    server.close()


@pytest.fixture()
def relay(upstream, tmp_path):
    mode_file = tmp_path / "mode"
    mode_file.write_text("pass", encoding="ascii")
    port = free_port()
    proc = _spawn(
        "freeze_relay.py", "--listen", f"127.0.0.1:{port}",
        "--upstream", f"127.0.0.1:{upstream}", "--mode-file", str(mode_file),
    )

    def set_mode(mode: str) -> None:
        mode_file.write_text(mode, encoding="ascii")
        time.sleep(0.3)

    yield port, set_mode
    proc.terminate()
    proc.wait(timeout=5)


def _read(port: int, silence: float = 1.0) -> tuple[int, str]:
    """(сколько байт пришло, чем кончилось: closed | silence | reset)."""
    received = 0
    with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
        client.settimeout(silence)
        try:
            client.sendall(b"hello")  # при сбросе соединения ошибка может прийти уже здесь
            while received < len(PAYLOAD):
                chunk = client.recv(65536)
                if not chunk:
                    return received, "closed"
                received += len(chunk)
        except TimeoutError:
            return received, "silence"
        except ConnectionError:
            return received, "reset"
    return received, "complete"


def test_relay_pass(relay):
    port, _set_mode = relay
    assert _read(port) == (len(PAYLOAD), "complete")


def test_relay_freeze_after_keeps_connection_open(relay):
    """После N байт данные перестают идти, но соединение не закрывается."""
    port, set_mode = relay
    set_mode("freeze_after=16384")
    assert _read(port) == (16384, "silence")
    assert _read(port) == (16384, "silence")  # счётчик — на каждое соединение отдельно
    set_mode("pass")
    assert _read(port) == (len(PAYLOAD), "complete")


def test_relay_small_response_passes_under_freeze(relay):
    """Ответ короче порога проходит целиком — поэтому HEAD-проверка «заморозку» не видит."""
    port, set_mode = relay
    set_mode("freeze_after=100000")
    assert _read(port) == (len(PAYLOAD), "complete")


def test_relay_drop_and_blackhole(relay):
    port, set_mode = relay
    set_mode("drop")
    received, ending = _read(port)
    assert received == 0 and ending in ("closed", "reset")
    set_mode("blackhole")
    assert _read(port) == (0, "silence")


def test_relay_latency(relay):
    port, set_mode = relay
    set_mode("pass;latency=400")
    started = time.monotonic()
    assert _read(port, silence=3.0) == (len(PAYLOAD), "complete")
    assert time.monotonic() - started >= 0.4


def test_origin_http_and_dns():
    port, dns_port = free_port(), free_port()
    proc = _spawn("origin.py", "--port", str(port), "--dns-port", str(dns_port),
                  "--answer", "203.0.113.7", "--country", "NL")
    try:
        base = f"http://127.0.0.1:{port}"
        with urllib.request.urlopen(f"{base}/64k", timeout=5) as response:
            assert len(response.read()) == 65536
        with urllib.request.urlopen(f"{base}/trace", timeout=5) as response:
            assert b"loc=NL" in response.read()
        head = urllib.request.Request(f"{base}/64k", method="HEAD")
        with urllib.request.urlopen(head, timeout=5) as response:
            assert response.headers["Content-Length"] == "65536" and response.read() == b""
        started = time.monotonic()
        with urllib.request.urlopen(f"{base}/slow?bytes=40960&seconds=1", timeout=10) as response:
            assert len(response.read()) == 40960
        assert time.monotonic() - started >= 0.8
        # DNS-заглушка отвечает тем же клиентом, которым XGW резолвит домены серверов
        assert plain_dns("127.0.0.1", "nl.stand.test", timeout=3, port=dns_port) == ["203.0.113.7"]
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_dns_answer_shapes():
    query = _dns_query("any.example.com")
    assert _parse_a_answers(dns_answer(query, "203.0.113.9")) == ["203.0.113.9"]
    aaaa = _dns_query("any.example.com", qtype=28)
    assert _parse_a_answers(dns_answer(aaaa, "203.0.113.9")) == []  # на AAAA — пустой ответ
    assert dns_answer(b"short", "203.0.113.9") is None
