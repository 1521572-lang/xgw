"""Wire contract and local Unix-socket lifecycle for the panel overview."""

import json
import os
import socket
import stat
import threading
import time

import pytest

from xgw.watch import panel_ipc

STATUS = {"mode": "off", "engine_mode": "off", "state": "off", "fresh": True,
          "policy_matched": True}
QUERY = b'{"version":1,"op":"zapret2.overview"}'


@pytest.mark.parametrize(("frame", "expected"), [
    (b'{"version":2,"op":"zapret2.overview"}', "unsupported_version"),
    (b'{"version":true,"op":"zapret2.overview"}', "unsupported_version"),
    (b'{"version":1,"op":"zapret2.mode"}', "unsupported_operation"),
    (b'{"version":1,"op":"zapret2.overview","path":"/etc"}', "invalid_request"),
    (b'{"version":2,"version":1,"op":"zapret2.overview"}', "invalid_request"),
    (b" " * (panel_ipc.MAX_REQUEST + 1), "request_too_large"),
])
def test_bad_request_does_not_reach_the_backend(frame, expected):
    def read():
        pytest.fail("unexpected backend read")

    assert panel_ipc.reply(frame, read) == {"version": 1, "ok": False, "error": expected}


def test_overview_projects_the_public_fields_and_validates_values():
    def read():
        return {"zapret2": {**STATUS, "probe": "private"}, "journal": {"secret": "private"}}

    assert panel_ipc.reply(QUERY, read) == {"version": 1, "ok": True, "status": STATUS}
    for read in (lambda: None, lambda: {"zapret2": {**STATUS, "fresh": 1}}):
        assert panel_ipc.reply(QUERY, read) == {"version": 1, "ok": False, "error": "unavailable"}


def test_scoped_ipc_consumes_valid_tickets_and_denies_legacy_requests():
    calls = []
    tickets = panel_ipc.StatusTickets()

    def overview():
        calls.append(True)
        return {"zapret2": STATUS}

    def reply(ticket, operation=panel_ipc.OPERATION):
        frame = json.dumps({"version": 2, "op": operation, "ticket": ticket}).encode()
        return panel_ipc.reply(frame, overview, tickets=tickets)

    assert panel_ipc.reply(QUERY, overview, tickets=tickets)["error"] == "unsupported_version"
    with tickets.issue() as ticket:
        assert reply(ticket, "zapret2.mode")["error"] == "unsupported_operation"
        assert reply(ticket) == {"version": 2, "ok": True, "status": STATUS}
        assert reply(ticket)["error"] == "unauthorized"
    assert calls == [True]


def test_scoped_tickets_expire_and_are_revoked_when_request_finishes():
    now = 0.0
    tickets = panel_ipc.StatusTickets(clock=lambda: now)
    with tickets.issue() as expired:
        now = 5.0
        assert not tickets.consume(expired)
    with tickets.issue() as revoked:
        assert revoked != expired
    assert not tickets.consume(revoked)


@pytest.mark.skipif(not hasattr(socket, "SO_PEERCRED"), reason="requires Linux Unix sockets")
def test_local_peer_and_shutdown(tmp_path):
    path = tmp_path / "panel.sock"
    stop = threading.Event()
    calls = []
    uid = os.geteuid()

    def overview():
        calls.append(True)
        return {"zapret2": STATUS}

    thread = threading.Thread(target=panel_ipc.serve,
                              args=(path, uid, os.getegid(), overview, stop), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if path.is_socket() and stat.S_IMODE(path.stat().st_mode) == 0o660:
                with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as client:
                    try:
                        client.connect(str(path))
                    except ConnectionRefusedError:
                        pass
                    else:
                        break
            time.sleep(0.01)
        else:
            pytest.fail("IPC listener did not start")
        with pytest.raises(panel_ipc.ProtocolError, match="unexpected_server_uid"):
            panel_ipc.read_overview(path, server_uid=uid + 1)
        assert panel_ipc.read_overview(path, server_uid=uid) == STATUS
        assert calls == [True]
    finally:
        stop.set()
        thread.join(timeout=3)
    assert not thread.is_alive() and not path.exists()
