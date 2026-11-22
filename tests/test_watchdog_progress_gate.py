"""The installer waits for a completed step from the current process."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture()
def gate():
    path = Path(__file__).resolve().parents[1] / "docs/helpers/watchdog_progress_gate.py"
    spec = importlib.util.spec_from_file_location("watchdog_progress_gate", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


def write_progress(path, generation, *, at, step=None, phase="tick"):
    path.write_text(json.dumps({
        "phase": phase, "generation": generation, "at": at, "wake": None, "last_step": step,
    }), encoding="utf-8")
    path.chmod(0o600)


def test_wait_progress_ignores_old_step_and_waits_for_new_completion(gate, tmp_path, monkeypatch):
    path = tmp_path / "watchdog-step.json"
    now = [10.0]
    step = {"sequence": 1, "started": 4.0, "completed_at": 5.0, "parts_s": {}}
    write_progress(path, 3_000_000_000, at=9.0, step=step, phase="sleep")

    def advance(seconds):
        now[0] += seconds
        if now[0] == 11.0:
            write_progress(path, 10_000_000_000, at=now[0])
        elif now[0] == 12.0:
            step["started"], step["completed_at"] = 10.75, 11.75
            # The reader can miss sleep if the next tick writes immediately.
            write_progress(path, 10_000_000_000, at=now[0], step=step)

    clock = SimpleNamespace(monotonic=lambda: now[0], sleep=advance)
    monkeypatch.setattr(gate, "time", clock)
    assert gate.wait_progress(path, 10_000_000_000, 5) == ("ready", 3, True)
    assert now[0] == 12.0
    assert gate.progress_state(path, 10_000_000_000, 12.0, require_details=True) == "invalid_format"
    step.update(details_s={}, planned_scan_deferred=False)
    write_progress(path, 10_000_000_000, at=now[0], step=step)
    assert gate.progress_state(path, 10_000_000_000, 12.0, require_details=True) == "ready"
    assert gate.progress_state(path, 10_000_000_000, 12.0, require_provider=True) == "invalid_format"
    step["provider_attempts"] = 0
    write_progress(path, 10_000_000_000, at=now[0], step=step)
    assert gate.progress_state(path, 10_000_000_000, 12.0, require_provider=True) == "ready"
    assert gate.progress_state(path, 10_000_000_000, 12.0, require_scan_slot=True) == "invalid_format"
    step.update(queue_probe_count=0, scan_deferred_for_step=True)
    write_progress(path, 10_000_000_000, at=now[0], step=step)
    assert gate.progress_state(path, 10_000_000_000, 12.0, require_scan_slot=True) == "ready"
    assert gate.progress_state(path, 10_000_000_000, 12.0, require_wan_dns=True) == "invalid_format"
    step.update(provider_dns_refresh_started=False, provider_dns_refresh_used=False)
    write_progress(path, 10_000_000_000, at=now[0], step=step)
    assert gate.progress_state(path, 10_000_000_000, 12.0, require_wan_dns=True) == "ready"


def test_wait_progress_stops_at_deadline_when_first_step_is_busy(gate, tmp_path, monkeypatch):
    path = tmp_path / "watchdog-step.json"
    now = [10.0]
    write_progress(path, 10_000_000_000, at=now[0])

    def advance(seconds):
        now[0] += seconds

    monkeypatch.setattr(gate, "time", SimpleNamespace(monotonic=lambda: now[0], sleep=advance))
    assert gate.wait_progress(path, 10_000_000_000, 2) == ("waiting_first_step", 3, True)
    assert now[0] == 12.0


@pytest.mark.parametrize(("step", "phase", "mode", "result"), [
    (None, "sleep", 0o600, "invalid_format"),
    ({"sequence": 1, "started": 10.0, "completed_at": 12.0, "parts_s": {}},
     "tick", 0o600, "invalid_format"),
    (None, "tick", 0o644, "unexpected_mode"),
])
def test_progress_gate_rejects_bad_current_snapshot(gate, tmp_path, step, phase, mode, result):
    path = tmp_path / "watchdog-step.json"
    write_progress(path, 10_000_000_000, at=11.0, step=step, phase=phase)
    path.chmod(mode)
    assert gate.progress_state(path, 10_000_000_000, 11.0) == result
