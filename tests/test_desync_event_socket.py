import json

import pytest

from xgw.desync import event_socket as transport
from xgw.desync import worker

NOW = 1_700_000_000


def journal(rounds):
    slot = worker.WorkerSlot()
    for _ in range(rounds):
        lease = slot.reserve(worker.ENGINE_UNIT, 201, policy_key="a" * 64)
        slot.observe_owner(lease, True)
        slot.release(lease)
    return {"daemon": True, "updated": NOW, "zapret2_worker_events": slot.snapshot()[1]}


def test_cursor_replay_gap_restart_and_future_cursor_are_distinct():
    snapshot = journal(30)
    first = transport.cursor_response(snapshot, None, 0, NOW)
    assert first["state"] == "snapshot" and first["last_seq"] == 90
    assert first["discarded"] == 26
    assert [event["seq"] for event in first["events"]] == list(range(27, 91))
    assert len(json.dumps(first)) < transport.MAX_RESPONSE
    epoch = first["epoch"]

    gap = transport.cursor_response(snapshot, epoch, 20, NOW)
    assert gap["state"] == "gap" and gap["events"] == first["events"]
    replay = transport.cursor_response(snapshot, epoch, 89, NOW)
    assert replay["state"] == "ok" and replay["events"] == first["events"][-1:]
    assert transport.cursor_response(snapshot, epoch, 89, NOW) == replay
    assert transport.cursor_response(snapshot, epoch, 90, NOW)["events"] == []
    assert transport.cursor_response(snapshot, epoch, 91, NOW)["state"] == "invalid_cursor"

    reset = transport.cursor_response(journal(0), epoch, 90, NOW)
    assert reset["state"] == "reset"
    assert reset["epoch"] != epoch and reset["last_seq"] == 0


def test_transport_filters_unknown_fields_and_rejects_stale_and_corrupt_journals():
    snapshot = journal(1)
    recorded = snapshot["zapret2_worker_events"]["events"][0]
    recorded["hostname"] = "hidden.example.invalid"
    report = transport.cursor_response(snapshot, None, 0, NOW)
    assert set(report["events"][0]) == set(transport.EVENT_FIELDS)
    assert transport.cursor_response(snapshot, None, 0, NOW + 91)["state"] == "unavailable"
    assert transport.cursor_response(snapshot, None, 0, NOW - 1)["state"] == "unavailable"
    recorded["seq"] = 42
    assert transport.cursor_response(snapshot, None, 0, NOW)["state"] == "unavailable"


def test_queue_drop_events_and_sampling_remain_bounded_and_backward_compatible(monkeypatch):
    monkeypatch.setattr(worker.time, "time", lambda: NOW)
    slot = worker.WorkerSlot()
    lease = slot.reserve(worker.SELECTED_UNIT, 201)
    slot.observe_owner(lease, True, worker.QueueOwner("socket:[100]", (0, 0, 2)))
    slot.observe_owner(lease, True, worker.QueueOwner("socket:[100]", (2, 1, 3)))
    status = {"daemon": True, "updated": NOW, "zapret2_worker_events": slot.snapshot()[1]}
    log = status["zapret2_worker_events"]
    log["events"][-1]["private_socket"] = "socket:[100]"
    reply = transport.cursor_response(status, None, 0, NOW)
    assert reply["state"] == "snapshot"
    assert reply["queue_counters"] == dict(unit=worker.SELECTED_UNIT, queue=201,
                                          generation=lease.generation, source=worker.QUEUE_SOURCE,
                                          at=NOW, overflow=2, netlink=1)
    assert reply["events"][-1]["overflow_delta"] == 2 and reply["events"][-1]["netlink_delta"] == 1
    assert "socket:[" not in json.dumps(reply)
    log["queue_counters"]["at"] = NOW - 100
    assert transport.cursor_response(status, None, 0, NOW)["queue_counters"] is None
    log["queue_counters"]["at"] = NOW
    log["queue_counters"]["generation"] += 1
    assert transport.cursor_response(status, None, 0, NOW)["queue_counters"] is None
    log.pop("queue_counters")
    assert "queue_counters" not in transport.cursor_response(status, None, 0, NOW)
    log["events"][-1]["overflow_delta"] = True
    assert transport.cursor_response(status, None, 0, NOW)["state"] == "unavailable"


def test_worker_fault_exports_only_allowlisted_reason():
    slot = worker.WorkerSlot()
    lease = slot.reserve(worker.ENGINE_UNIT, 201)
    slot.observe_stopped(lease, lambda *_a, **_kw: '{"MESSAGE":"LUA ERROR: abc-private"}')
    status = {"daemon": True, "updated": NOW, "zapret2_worker_events": slot.snapshot()[1]}
    item = transport.cursor_response(status, None, 0, NOW)["events"][-1]
    assert item["phase"] == "worker_fault" and item["reason"] == "lua_error_observed"
    assert "abc-private" not in json.dumps(item)
    status["zapret2_worker_events"]["events"][-1]["reason"] = ["unknown"]
    assert transport.cursor_response(status, None, 0, NOW)["state"] == "unavailable"


@pytest.mark.parametrize("frame", [
    b'{"version":true,"epoch":null,"after":0}\n',
    b'{"version":1,"epoch":null,"after":1}\n',
    b'{"version":1,"epoch":null,"after":0,"action":"pin"}\n',
    b'{"version":1,"epoch":null,"after":0}\n{}\n',
    b" " * transport.MAX_REQUEST + b"\n",
    b"{}",
])
def test_bad_requests_never_return_a_cursor(frame):
    with pytest.raises(ValueError):
        transport.parse_request(frame)
    assert transport.parse_request(b'{"version":1,"epoch":null,"after":0}\n') == (None, 0)
