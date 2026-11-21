"""Check that panel startup retries happen before using a login code."""

import errno
import http.client
from types import SimpleNamespace

import pytest

from docs.helpers import t11_panel_login_check as check


@pytest.fixture
def clock(monkeypatch):
    now = 0.0

    def sleep(seconds):
        nonlocal now
        now += seconds

    def monotonic():
        return now

    monkeypatch.setattr(check, "time", SimpleNamespace(monotonic=monotonic, sleep=sleep))
    return monotonic


def test_waits_for_guest_api_after_connection_errors(monkeypatch, clock):
    replies = iter([ConnectionRefusedError(errno.ECONNREFUSED, "private"),
                    http.client.RemoteDisconnected(), (401, {})])

    def request(port, path, *, timeout):
        assert port == 8781 and path == "/api/state" and timeout == 2
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(check, "request", request)
    assert check.wait_for_guest_api(8781) == {"attempts": 3, "seconds": 2.0}
    assert clock() == 2


def test_guest_http_contract_failure_is_immediate(monkeypatch, clock):
    monkeypatch.setattr(check, "request", lambda *args, **kwargs: (200, {}))
    with pytest.raises(check.FailedCheck, match="^guest_api$") as caught:
        check.wait_for_guest_api(8781)
    assert caught.value.details == {"attempts": 1, "http_status": 200}
    assert clock() == 0


def test_startup_wait_is_bounded_and_reports_sanitized_error(monkeypatch, clock):
    def refuse(*args, **kwargs):
        raise ConnectionRefusedError(errno.ECONNREFUSED, "private")

    monkeypatch.setattr(check, "request", refuse)
    with pytest.raises(check.FailedCheck, match="^guest_api_timeout$") as caught:
        check.wait_for_guest_api(8781, wait=3)
    assert caught.value.details == {
        "attempts": 3, "error": "ConnectionRefusedError", "errno": errno.ECONNREFUSED,
    }
    assert clock() == 3


def test_transport_error_during_code_exchange_is_not_retried(monkeypatch):
    calls = []

    def disconnect(port, path):
        calls.append(port)
        raise http.client.RemoteDisconnected("private")

    monkeypatch.setattr(check, "request", disconnect)
    with pytest.raises(check.FailedCheck, match="^new_session$") as caught:
        check.checked_request("new_session", 8781, "/?login=single-use")
    assert caught.value.details == {"error": "RemoteDisconnected", "errno": None}
    assert calls == [8781]


def test_cold_state_uses_one_bounded_request_and_records_wait(monkeypatch, clock):
    def state(port, path, *, cookie, timeout):
        assert (port, path, cookie, timeout) == (8781, "/api/state", "session", 40)
        check.time.sleep(23)
        return 200, {}

    monkeypatch.setattr(check, "request", state)
    assert check.session_state_ms("existing_session", 8781, "session", timeout=40) == 23000
    assert clock() == 23
