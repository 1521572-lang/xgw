import socket
import threading
import time

import pytest

from xgw.watch import video_browser as browser


def test_marionette_reports_eof_instead_of_waiting_for_a_frame():
    client, remote = socket.socketpair()
    with client, remote:
        greeting = b'{"marionetteProtocol":3}'
        remote.sendall(str(len(greeting)).encode() + b":" + greeting + b"10:{")
        remote.shutdown(socket.SHUT_WR)
        protocol = browser.Marionette(client, time.monotonic() + 2)
        with pytest.raises(EOFError):
            protocol.read()


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
        def call(self, method, _params):
            calls.append(method)
            return {"capabilities": {"moz:profile": str(tmp_path / "other-profile")}}

    result = browser.observe(Client(), "", [], None, tmp_path / "expected", stages.append)
    assert result == ("", "", "browser_profile_unverified", False)
    assert calls == ["WebDriver:NewSession"] and not stages


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
