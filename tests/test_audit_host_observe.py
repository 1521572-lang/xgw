"""The audit uses only wake timings observed inside the sampling window."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def test_watchdog_audit_counts_each_generation_and_sequence_once(monkeypatch, capsys):
    path = Path(__file__).resolve().parents[1] / "docs/helpers/audit_host_observe.py"
    spec = importlib.util.spec_from_file_location("audit_host_observe", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    moment = [100.0]

    def row(generation, sequence, received, handled):
        return {
            "generation": generation, "at": handled,
            "wake": {"sequence": sequence, "received": received, "handling_at": handled},
        }

    first = row(1, 2, {"net": 100.25}, 101.0)
    rows = iter([
        row(1, 1, {"rules": 99.0}, 100.0),
        first,
        first,
        row(2, 1, {"rules": 102.0, "private": 101.0}, 103.0),
        row(2, 1, {"rules": 102.0, "private": 101.0}, 103.0),
        row(2, 2, {"net": 106.0}, 105.0),
    ])

    def sleep(delay):
        moment[0] += delay

    clock = SimpleNamespace(monotonic=lambda: moment[0], sleep=sleep)
    snapshot = SimpleNamespace(read_bytes=lambda: json.dumps(next(rows)).encode())
    monkeypatch.setattr(helper, "time", clock)
    monkeypatch.setattr(helper, "Path", lambda _path: snapshot)
    helper.watchdog(5)
    assert json.loads(capsys.readouterr().out)["wake"] == {
        "available": True,
        "observed_batches": 2,
        "by_reason": {"net": {"count": 1, "max_s": 0.75},
                      "rules": {"count": 1, "max_s": 1.0}},
    }
