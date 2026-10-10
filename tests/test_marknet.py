"""Сокеты с SO_MARK: метка ставится всем, кроме loopback (ASSUMPTIONS, п. 119)."""

from __future__ import annotations

import socket
import types

import pytest

from xgw import marknet


class Recording:
    """Сокет, который только запоминает, что с ним делали."""

    created: list[Recording] = []  # noqa: RUF012 — подмена на время одного теста

    def __init__(self, *_args) -> None:
        self.marks: list[int] = []
        self.connected: tuple[str, int] | None = None
        self.closed = False
        Recording.created.append(self)

    def setsockopt(self, _level, option, value) -> None:
        assert option == marknet.SO_MARK
        self.marks.append(value)

    def settimeout(self, _timeout) -> None:
        pass

    def connect(self, address) -> None:
        self.connected = address

    def close(self) -> None:
        self.closed = True


@pytest.fixture()
def recording(monkeypatch):
    Recording.created = []
    shim = types.SimpleNamespace(
        AF_INET=socket.AF_INET, SOCK_STREAM=socket.SOCK_STREAM, SOCK_DGRAM=socket.SOCK_DGRAM,
        SOL_SOCKET=socket.SOL_SOCKET, socket=Recording,
    )
    monkeypatch.setattr(marknet, "socket", shim)
    monkeypatch.setattr(marknet, "is_mark_supported", lambda: True)
    return Recording


def test_loopback_detection():
    assert marknet.is_loopback("127.0.0.1") and marknet.is_loopback("127.1.2.3")
    assert marknet.is_loopback("::1")
    for other in ("203.0.113.7", "192.168.50.1", "0.0.0.0", "example.com", ""):
        assert not marknet.is_loopback(other)


def test_marked_connection_to_internet_carries_the_mark(recording):
    marknet.connect_marked("203.0.113.7", 443, timeout=3, mark=2)
    (sock,) = recording.created
    assert sock.marks == [2] and sock.connected == ("203.0.113.7", 443)


def test_loopback_connection_goes_without_the_mark(recording):
    """Помеченный пакет к 127.0.0.0/8 правило loopback_guard отвергло бы: loopback
    не перехватывается, метка ему не нужна."""
    marknet.connect_marked("127.0.0.1", 8000, timeout=3, mark=2)
    (sock,) = recording.created
    assert sock.marks == [] and sock.connected == ("127.0.0.1", 8000)


def test_no_mark_requested_means_no_mark(recording):
    marknet.connect_marked("203.0.113.7", 443, timeout=3, mark=None)
    assert recording.created[0].marks == []


def test_mark_is_refused_outside_linux(recording, monkeypatch):
    monkeypatch.setattr(marknet, "is_mark_supported", lambda: False)
    with pytest.raises(marknet.MarkUnavailable):
        marknet.connect_marked("203.0.113.7", 443, timeout=3, mark=2)
    assert recording.created[0].closed
    marknet.connect_marked("127.0.0.1", 8000, timeout=3, mark=2)  # loopback — без метки, можно
