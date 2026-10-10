"""Тесты fetch: file://, subscription-userinfo, DNS wire-формат (без сети)."""

import struct

import pytest

from xgw.fetch import (
    FetchResult,
    _dns_query,
    _parse_a_answers,
    fetch_url,
    parse_userinfo,
)


def test_fetch_file(tmp_path):
    path = tmp_path / "sub.txt"
    path.write_text("hello", encoding="utf-8")
    result = fetch_url(path.as_uri().replace("file:///", "file://"))
    assert isinstance(result, FetchResult)
    assert result.status == 200
    assert result.body == b"hello"


def test_fetch_file_missing(tmp_path):
    from xgw.fetch import FetchError

    with pytest.raises(FetchError):
        fetch_url(f"file://{tmp_path / 'nope.txt'}")


def test_parse_userinfo():
    info = parse_userinfo("upload=1234; download=5678; total=100000; expire=1798761600")
    assert info == {"upload": 1234, "download": 5678, "total": 100000, "expire": 1798761600}
    assert parse_userinfo("garbage") == {}


def test_dns_wire_roundtrip():
    query = _dns_query("one.example.com")
    # Ответ: заголовок запроса с ancount=1 + имя-указатель + A-запись
    answer = (
        query[:6]
        + struct.pack(">H", 1)
        + query[8:]
        + b"\xc0\x0c"
        + struct.pack(">HHIH", 1, 1, 60, 4)
        + bytes([203, 0, 113, 10])
    )
    assert _parse_a_answers(answer) == ["203.0.113.10"]


def test_dns_wire_broken():
    from xgw.fetch import ResolveError

    with pytest.raises(ResolveError):
        _parse_a_answers(b"short")
