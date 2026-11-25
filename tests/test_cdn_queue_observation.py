import json
from dataclasses import asdict

import pytest

from docs.helpers import cdn_queue_observation as queue
from xgw.desync import worker

REQUEST = {"started_monotonic_ns": 102 * 10**9, "finished_monotonic_ns": 111 * 10**9}


def boundary(at, **changes):
    return {"state": "observed", "monotonic_ns": int(at * 10**9),
            "epoch": "private", "generation": 1, "queue": 200, "policy_key": "private",
            "socket": "private", "last_seq": 5, "owner_change": 2,
            "overflow": 7, "netlink": 12, "packet_ids": 32} | changes


def test_only_counters_bracketing_the_direct_probe_are_reported():
    before = boundary(100)
    after = boundary(112, last_seq=6, overflow=9, netlink=16, packet_ids=48)
    result = queue.summarize(before, after, REQUEST)
    assert result == {"state": "observed", "seconds": 12, "overflow_delta": 2,
                      "netlink_delta": 4, "assigned_ids": 16, "netlink_loss_fraction": 0.25}
    assert "private" not in json.dumps(result)
    result = queue.summarize(before, boundary(112), REQUEST)
    assert result["assigned_ids"] == 0 and result["netlink_loss_fraction"] is None


@pytest.mark.parametrize(("after", "expected"), [
    (boundary(110), "probe_window_unconfirmed"),
    (boundary(120), "probe_window_unconfirmed"),
    (boundary(112, monotonic_ns=10), "probe_window_unconfirmed"),
    (boundary(112, epoch="restart"), "queue_owner_changed"),
    (boundary(112, socket="different"), "queue_owner_changed"),
    (boundary(112, policy_key="different"), "queue_owner_changed"),
    (boundary(112, generation=2), "queue_owner_changed"),
    (boundary(112, owner_change=6, last_seq=6), "queue_owner_changed"),
    (boundary(112, netlink=11), "queue_counters_reset"),
    (boundary(112, netlink=13), "queue_counters_reset"),
    (boundary(112, overflow=True), "queue_counters_unavailable"),
    ({}, "queue_counters_unavailable"),
])
def test_queue_snapshot_rejects_ambiguous_windows(after, expected):
    result = queue.summarize(boundary(100), after, REQUEST)
    assert result == {"state": expected}


def test_snapshot_checks_selected_owner_against_daemon_journal(tmp_path, monkeypatch):
    monkeypatch.setattr(queue.time, "time", lambda: 100.0)
    policy_key = "a" * 64
    slot = worker.WorkerSlot()
    lease = slot.reserve(worker.SELECTED_UNIT, 200, policy_key=policy_key)
    owner = worker.QueueOwner("socket:[12]", (2, 3, 14))
    slot.observe_owner(lease, True, owner)
    status = {"daemon": True, "updated": 100.0, "zapret2_policy_key": policy_key,
              "zapret2": {"state": "active", "valid_until": 110.0},
              "zapret2_reservation": asdict(lease), "zapret2_worker_events": slot.snapshot()[1]}
    path = tmp_path / "status.json"
    path.write_text(json.dumps(status), encoding="utf-8")
    runner = object()

    def read_owner(selected_runner, unit, queue_id):
        assert selected_runner is runner
        assert (unit, queue_id) == (worker.SELECTED_UNIT, 200)
        return owner

    monkeypatch.setattr(worker, "owner_sample", read_owner)
    result = queue.snapshot(path, runner=runner)
    assert result["state"] == "observed" and result["packet_ids"] == 14
    status["zapret2_policy_key"] = "b" * 64
    path.write_text(json.dumps(status), encoding="utf-8")
    assert queue.snapshot(path, runner=runner) == {"state": "queue_counters_unavailable"}
