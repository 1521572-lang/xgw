import json
import socket
import threading
import time
from types import SimpleNamespace

import pytest

from xgw.watch import video_browser as browser


def test_marionette_reports_eof_instead_of_waiting_for_a_frame():
    client, remote = socket.socketpair()
    errors = []
    with client, remote:
        greeting = b'{"marionetteProtocol":3}'
        remote.sendall(str(len(greeting)).encode() + b":" + greeting + b"10:{")
        remote.shutdown(socket.SHUT_WR)
        protocol = browser.Marionette(client, time.monotonic() + 2, errors.append)
        with pytest.raises(EOFError):
            protocol.call("WebDriver:ExecuteScript", {})
    assert errors == [{"method": "WebDriver:ExecuteScript", "exception": "EOFError"}]


@pytest.mark.parametrize("code,expected", [("timeout", "timeout"), ("PRIVATE", "other")])
def test_marionette_command_error_records_only_safe_fields(code, expected):
    client, remote = socket.socketpair()
    errors = []
    with client, remote:
        for value in ({"marionetteProtocol": 3},
                      [1, 1, {"error": code, "message": "PRIVATE", "stacktrace": "PRIVATE"}, None]):
            data = json.dumps(value).encode()
            remote.sendall(str(len(data)).encode() + b":" + data)
        protocol = browser.Marionette(client, time.monotonic() + 2, errors.append)
        with pytest.raises(browser.MarionetteCommandError) as failure:
            protocol.call("WebDriver:Navigate", {})
    assert errors == [{
        "method": "WebDriver:Navigate", "exception": "MarionetteCommandError", "code": expected,
    }]
    assert "PRIVATE" not in str(failure.value)


@pytest.mark.parametrize("budget,first_byte,complete,elapsed", [
    (120, 13.4, 13.4, 13.4),
    (120, 29, 31, 30),
    (10, 9, 13.4, 10),
])
def test_new_session_uses_one_deadline_and_keeps_other_reads_short(
    monkeypatch, budget, first_byte, complete, elapsed,
):
    now = [0.0]
    monkeypatch.setattr(browser.time, "monotonic", lambda: now[0])

    def frame(message):
        body = json.dumps(message).encode()
        return str(len(body)).encode() + b":" + body

    class DelayedSocket:
        def __init__(self):
            self.pending = [(0, frame({"marionetteProtocol": 3}))]
            self.seq = 0

        def settimeout(self, timeout):
            self.timeout = timeout

        def sendall(self, _data):
            self.seq += 1
            reply = frame([1, self.seq, None, {"session": "fixture"}])
            delays = (first_byte, complete) if self.seq == 1 else (9, 9)
            self.pending = [(now[0] + delays[0], reply[:1]), (now[0] + delays[1], reply[1:])]

        def recv(self, size):
            ready, data = self.pending[0]
            if ready > now[0] + self.timeout:
                now[0] += self.timeout
                raise TimeoutError
            now[0] = max(now[0], ready)
            if len(data) <= size:
                self.pending.pop(0)
            else:
                self.pending[0] = ready, data[size:]
            return data[:size]

    protocol = browser.Marionette(DelayedSocket(), budget)
    if complete <= min(budget, browser.SESSION_TIMEOUT):
        assert protocol.call("WebDriver:NewSession", {}, timeout=browser.SESSION_TIMEOUT)
        assert now[0] == pytest.approx(elapsed)
        with pytest.raises(TimeoutError):
            protocol.call("WebDriver:Navigate", {})
        assert now[0] == pytest.approx(elapsed + 8)
    else:
        with pytest.raises(TimeoutError):
            protocol.call("WebDriver:NewSession", {}, timeout=browser.SESSION_TIMEOUT)
        assert now[0] == pytest.approx(elapsed)


def test_new_session_timeout_is_recorded_before_navigation(tmp_path):
    stages = []

    class Client:
        def call(self, method, _params, *, timeout):
            assert method == "WebDriver:NewSession" and timeout == 30
            assert stages == ["session_requested"]
            raise TimeoutError

    assert browser.observe(Client(), "", [], None, tmp_path, stages.append) == (
        "", "", "browser_session_timeout", False,
    )


def test_control_port_skips_ephemeral_range_and_an_occupied_port(monkeypatch, tmp_path):
    ephemeral = tmp_path / "ip_local_port_range"
    ephemeral.write_text("1024  64999\n", encoding="ascii")
    monkeypatch.setattr(browser, "EPHEMERAL_PORTS", ephemeral)
    monkeypatch.setattr(browser.random, "sample", lambda choices, count: choices[:count])
    attempts, closed = [], []

    class Reservation:
        def bind(self, address):
            attempts.append(address)
            if len(attempts) == 1:
                raise OSError("occupied")

        def close(self):
            closed.append(self)

    monkeypatch.setattr(browser.socket, "socket", Reservation)
    reservation = browser.reserve_control_port()
    assert attempts == [("127.0.0.1", 65000), ("127.0.0.1", 65001)]
    assert len(closed) == 1 and reservation not in closed


def test_foreign_profile_is_not_navigated(tmp_path):
    calls, stages = [], []

    class Client:
        def call(self, method, _params, *, timeout):
            calls.append(method)
            return {"capabilities": {"moz:profile": str(tmp_path / "other-profile")}}

    result = browser.observe(Client(), "", [], None, tmp_path / "expected", stages.append)
    assert result == ("", "", "browser_profile_unverified", False)
    assert calls == ["WebDriver:NewSession"] and stages == ["session_requested"]


def test_navigation_response_is_recorded_before_observation(tmp_path):
    stages = []

    class Client:
        deadline = time.monotonic() + 5

        def call(self, method, _params, **_kwargs):
            if method == "WebDriver:NewSession":
                return {"capabilities": {"moz:profile": str(tmp_path)}}
            if method == "WebDriver:Navigate":
                return None
            assert method == "WebDriver:ExecuteScript"
            raise EOFError

    relay = SimpleNamespace(stopped=threading.Event())
    with pytest.raises(EOFError):
        browser.observe(Client(), "", [], relay, tmp_path, stages.append)
    assert stages == [
        "session_requested", "session_ready", "navigation_started", "navigation_returned",
        "observation_started",
    ]


def test_relay_rejects_outside_hosts_and_shares_traffic_budget(monkeypatch):
    opened = []
    upstream, remote = socket.socketpair()

    def open_tunnel(proxy, host, port, **kwargs):
        opened.append((proxy, host, port, kwargs["password"]))
        return upstream

    monkeypatch.setattr(browser.fetch, "open_tunnel", open_tunnel)
    monkeypatch.setattr(browser, "LIMIT", 8)
    with upstream, remote, browser.Relay(12345, "fixture", time.monotonic() + 5) as relay:
        thread = threading.Thread(target=relay.serve_forever, daemon=True)
        thread.start()
        try:
            with socket.create_connection(relay.server_address, timeout=2) as denied:
                denied.sendall(b"CONNECT youtube.com.outside.test:443 HTTP/1.1\r\n\r\n")
                assert denied.recv(1) == b"" and not opened
            with socket.create_connection(relay.server_address, timeout=2) as client:
                client.sendall(b"CONNECT www.youtube.com:443 HTTP/1.1\r\n\r\n")
                with client.makefile("rb") as response:
                    assert response.readline().startswith(b"HTTP/1.1 200 ")
                    assert response.readline() == b"\r\n"
                    client.sendall(b"sent")
                    remote.settimeout(2)
                    assert remote.recv(4) == b"sent"
                    remote.sendall(b"back")
                    assert response.read(4) == b"back"
                    remote.sendall(b"x")
                    assert response.read(1) == b""
            assert relay.spent == 8 and relay.stopped.is_set()
            assert opened == [(("127.0.0.1", 12345), "www.youtube.com", 443, "fixture")]
        finally:
            relay.stopped.set()
            relay.shutdown()
            thread.join(timeout=2)
