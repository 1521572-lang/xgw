"""Последний повтор G1: реальные форматы HTTP, без сети, ядер и служб."""

import http.client
import importlib.util
import io
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def helper():
    path = Path(__file__).resolve().parents[1] / "docs/helpers/singbox_generation_check.py"
    spec = importlib.util.spec_from_file_location("g1_stream_helper", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def response(status, headers, body=b""):
    wire = f"HTTP/1.1 {status} Test\r\n{headers}\r\n".encode() + body
    fake_socket = SimpleNamespace(makefile=lambda *args: io.BytesIO(wire))
    reply = http.client.HTTPResponse(fake_socket)
    reply.begin()
    return reply


@pytest.mark.parametrize(("headers", "error", "span", "length"), [
    ("Content-Range: bytes 0-2097151/9020119\r\nContent-Length: 2097152\r\n",
     None, [0, 2097151, 9020119], 2097152),
    ("Content-Range: BYTES 0-2097151/*\r\nTransfer-Encoding: chunked\r\n",
     None, [0, 2097151, None], None),
    ("Content-Range: bytes 0-1048575/9020119\r\nContent-Length: 1048576\r\n",
     "RANGE_MISMATCH", [0, 1048575, 9020119], 1048576),
    ("Content-Range: bytes 10-2097161/9020119\r\n",
     "RANGE_MISMATCH", [10, 2097161, 9020119], None),
    ("Content-Range: bytes 0-2097151/1000\r\n",
     "RANGE_MISMATCH", [0, 2097151, 1000], None),
    ("Content-Range: not-a-range\r\n", "RANGE_MISMATCH", None, None),
    ("Content-Range: bytes 0-2097151/9020119\r\nContent-Length: 1024\r\n",
     "LENGTH_MISMATCH", [0, 2097151, 9020119], 1024),
    ("Content-Encoding: gzip\r\n", "ENCODED_BODY", None, None),
])
def test_206_preserves_numeric_reason_without_header_text(helper, headers, error, span, length):
    # 206/BODY_OR_HTTP/0 Б — формат отчёта fix1. Его неизвестные заголовки не выдумываем.
    state = {}
    assert helper.response_error(response(206, headers), state) == error
    assert state["range"] == span
    assert state["length"] == length


def test_full_200_and_status_rejection(helper):
    assert helper.response_error(response(200, "Content-Length: 2097152\r\n"), {}) is None
    assert helper.response_error(response(200, "Content-Length: 9020119\r\n"), {}) == (
        "LENGTH_MISMATCH")
    assert helper.response_error(response(503, ""), {}) == "HTTP_STATUS"


@pytest.mark.parametrize("body,ok", [(b"abcd", True), (b"abc", False), (b"abcde", False)])
def test_single_connection_body_accounting_and_cleanup(helper, monkeypatch, body, ok):
    from xgw import fetch

    monkeypatch.setattr(helper, "SIZE", 4)
    monkeypatch.setattr(helper.time, "sleep", lambda seconds: None)
    sock = SimpleNamespace(setsockopt=lambda *a: None, settimeout=lambda *a: None,
                           close=lambda: closed.append(True))
    monkeypatch.setattr(fetch, "open_tunnel", lambda *a, **kw: sock)
    monkeypatch.setattr(helper.ssl, "create_default_context", lambda: SimpleNamespace(
        wrap_socket=lambda *a, **kw: sock))
    reply = response(206, "Content-Range: bytes 0-3/20\r\n", body)
    requests, closed = [], []
    connection = SimpleNamespace(request=lambda *a, **kw: requests.append(kw),
                                 getresponse=lambda: reply)
    monkeypatch.setattr(helper.http.client, "HTTPConnection", lambda *a: connection)
    state = {"bytes": 0, "ok": False, "seconds": 0,
             "receiving": threading.Event(), "done": threading.Event()}
    helper.stream(1234, "private", "https://example.invalid/file", "agent", state)
    assert state["done"].is_set() and closed == [True]
    assert state["ok"] is ok and state["bytes"] == min(4, len(body))
    assert state["error"] == (None if ok else "BODY_SIZE")
    assert len(requests) == 1  # Ни повторного CONNECT, ни второго GET для докачивания.
    assert requests[0]["headers"]["Cache-Control"] == "no-cache"
    assert reply.isclosed()
    state["url"] = "private-url-must-not-escape"
    assert "private-url" not in json.dumps(helper.public_stream(state))


def test_existing_alternative_and_no_retry_after_summary(helper, monkeypatch, tmp_path):
    from xgw import config
    from xgw.apply import singbox_process
    from xgw.generator import builder, singbox
    from xgw.paths import Paths
    from xgw.watch import checks

    monkeypatch.setattr(helper, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["helper"])
    monkeypatch.setattr(helper, "process_count", lambda: (1, True))
    monkeypatch.setattr(helper, "pin_value", lambda paths: None)
    cfg = SimpleNamespace(speed=SimpleNamespace(
        url_fallback="https://example.invalid/fallback", url="",
        youtube_speed_url="https://example.invalid/youtube"),
        probe=SimpleNamespace(url="https://example.invalid/probe", user_agent="test"))
    monkeypatch.setattr(config, "load", lambda path: (cfg, []))
    monkeypatch.setattr(Paths, "xray_config_file", property(lambda self: tmp_path / "xray.json"))
    (tmp_path / "xray.json").write_text(json.dumps({"outbounds": [
        {"tag": "private", "settings": {"servers": [{"port": 1234}]}}]}))
    monkeypatch.setattr(singbox_process, "read", lambda paths: {
        "active": "blue", "draining": None, "pending": None})
    monkeypatch.setattr(builder, "probe_state", lambda routed: ("secret", {}))
    monkeypatch.setattr(builder, "applied_nodes", lambda routed: [
        SimpleNamespace(tag="private", probe_port=1235)])
    monkeypatch.setattr(singbox, "bridge_variant", lambda outbound: True)
    monkeypatch.setattr(checks, "http_get_via_proxy", lambda *a, **kw: SimpleNamespace(ok=True))
    monkeypatch.setattr(helper, "established", lambda port: True)
    urls = []

    def start(port, password, url, agent):
        urls.append(url)
        receiving, done = threading.Event(), threading.Event()
        (done if len(urls) == 1 else receiving).set()
        return {"bytes": 0 if len(urls) == 1 else 8192, "ok": False, "seconds": 0,
                "http": 206, "error": "RANGE_MISMATCH" if len(urls) == 1 else None,
                "receiving": receiving, "done": done}

    class BeforeRealRotate(Exception):
        pass

    def refuse_process(*args, **kwargs):
        raise BeforeRealRotate

    monkeypatch.setattr(helper, "start_stream", start)
    monkeypatch.setattr(helper.subprocess, "Popen", refuse_process)
    with pytest.raises(BeforeRealRotate):
        helper.main()
    result = json.loads((tmp_path / "summary.json").read_text())
    assert urls == [cfg.speed.url_fallback, cfg.speed.youtube_speed_url]
    assert result["source"] == "youtube" and result["stage"] == "rotate"
    assert [row["source"] for row in result["attempts"]] == ["fallback", "youtube"]
    assert "example.invalid" not in json.dumps(result) and "secret" not in json.dumps(result)
    assert helper.main() == 3  # Даже оборванный start не разрешает третий повтор.
