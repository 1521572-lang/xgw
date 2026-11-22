"""The audit uses only wake timings observed inside the sampling window."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture()
def observer():
    path = Path(__file__).resolve().parents[1] / "docs/helpers/audit_host_observe.py"
    spec = importlib.util.spec_from_file_location("audit_host_observe", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


def test_watchdog_audit_counts_each_generation_and_sequence_once(observer, monkeypatch, capsys):
    moment = [100.0]

    def row(generation, sequence, received, handled, *, started, duration):
        return {
            "generation": generation, "at": handled,
            "phase": "sleep", "started": started, "step_s": duration,
            "wake": {"sequence": sequence, "received": received, "handling_at": handled},
        }

    first = row(1, 2, {"net": 100.25}, 101.0, started=100.0, duration=0.5)
    second = row(2, 1, {"rules": 102.0, "private": 101.0}, 103.0, started=100.0, duration=2.5)
    rows = iter([
        row(1, 1, {"rules": 99.0}, 100.0, started=98.0, duration=1.5),
        first,
        first,
        second,
        second,
        row(2, 2, {"net": 106.0}, 105.0, started=103.0, duration=2.5),
    ])

    def sleep(delay):
        moment[0] += delay

    clock = SimpleNamespace(monotonic=lambda: moment[0], sleep=sleep)
    snapshot = SimpleNamespace(read_bytes=lambda: json.dumps(next(rows)).encode())
    monkeypatch.setattr(observer, "time", clock)
    monkeypatch.setattr(observer, "Path", lambda _path: snapshot)
    observer.watchdog(5)
    result = json.loads(capsys.readouterr().out)
    assert result["distinct_completed_steps"] == 2
    assert result["step_max_s"] == 2.5
    assert result["wake"] == {
        "available": True,
        "state": "observed",
        "observed_batches": 2,
        "by_reason": {"net": {"count": 1, "max_s": 0.75},
                      "rules": {"count": 1, "max_s": 1.0}},
    }


@pytest.mark.parametrize(("row", "state"), [
    ({"at": 104.0}, "not_instrumented"),
    ({"at": 104.0, "generation": 1, "wake": None}, "not_observed"),
    (None, "unavailable"),
])
def test_watchdog_audit_distinguishes_absent_wake_data(observer, monkeypatch, capsys, row, state):
    moment = iter([100.0, 105.0, 105.0])
    monkeypatch.setattr(observer, "time", SimpleNamespace(monotonic=lambda: next(moment)))
    snapshot = SimpleNamespace(read_bytes=lambda: json.dumps(row).encode())
    monkeypatch.setattr(observer, "Path", lambda _path: snapshot)

    observer.watchdog(5)
    result = json.loads(capsys.readouterr().out)
    assert result["wake"]["state"] == state
    assert result["wake"]["observed_batches"] == 0


def test_watchdog_audit_counts_completions_from_tick_records(observer, monkeypatch, capsys):
    moment = [100.0]
    wake = {
        "sequence": 2, "handling_at": 101.0, "received": {"rules": 100.0},
        "last_step_overlap_s": {"rules": 0.75}, "rules_check_s": 0.2,
    }
    first = {
        "generation": 1, "at": 101.25, "phase": "tick", "started": 101.25, "interval_s": 20,
        "last_step": {"sequence": 3, "started": 99.75, "completed_at": 100.75,
                      "parts_s": {"сигналы ядра": 0.75, "private value": 1.0},
                      "details_s": {"end_to_end": 0.5, "provider_resolve": 0.01,
                                    "private": 0.2, "scan_queue": 2.0},
                      "planned_scan_deferred": True, "provider_attempts": 2,
                      "provider_dns_refresh_started": False, "provider_dns_refresh_used": True,
                      "scan_deferred_for_step": True, "queue_probe_count": 1},
        "wake": wake,
    }
    second = {
        **first, "at": 103.0, "started": 103.0,
        "last_step": {"sequence": 5, "started": 102.0, "completed_at": 103.0, "parts_s": {}},
    }
    rows = iter([first, first, first, second, second, second])

    def sleep(delay):
        moment[0] += delay

    clock = SimpleNamespace(monotonic=lambda: moment[0], sleep=sleep)
    snapshot = SimpleNamespace(read_bytes=lambda: json.dumps(next(rows)).encode())
    monkeypatch.setattr(observer, "time", clock)
    monkeypatch.setattr(observer, "Path", lambda _path: snapshot)
    observer.watchdog(5)
    result = json.loads(capsys.readouterr().out)
    assert result["configured_intervals_s"] == [20]
    assert result["distinct_completed_steps"] == 2
    assert result["unseen_steps_between_samples"] == 1
    assert result["step_part_max_s"] == {"сигналы ядра": 0.75}
    assert result["step_details"] == {
        "end_to_end": {"steps": 1, "max_s": 0.5, "p50_s": 0.5, "p95_s": 0.5},
        "provider_resolve": {"steps": 1, "max_s": 0.01, "p50_s": 0.01, "p95_s": 0.01},
    }
    assert result["planned_scan_deferred_steps"] == 1
    assert result["scan_deferred_for_step"] == 1
    assert result["queue_probes"] == {"steps": 1, "steps_with_probes": 1, "total": 1}
    assert result["provider_attempts"] == {"steps": 1, "total": 2, "max": 2}
    assert result["provider_dns_refresh"] == {
        "steps": 1, "started": 0, "used": 1, "max_resolve_s_when_used": 0.01,
    }
    assert result["wake"]["rules_check"] == {"count": 1, "max_s": 0.2}
    assert result["wake"]["by_reason"]["rules"]["last_step_overlap"] == {
        "count": 1, "max_s": 0.75,
    }
