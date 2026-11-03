import contextlib
import importlib.util
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "mode,expected,baseline", [("none", "EXPIRED_UNUSED", True), ("fail_restore", "FAILED", False)]
)
def test_fake_driver_distinguishes_unused_from_failed_restore(
    monkeypatch, mode, expected, baseline
):
    path = Path(__file__).parent / "stand/wave3_fake_recovery.py"
    spec = importlib.util.spec_from_file_location("fake_driver_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    nonce = "a" * 32
    manifest = {"nonce": nonce, "mode": mode}
    state = {"nonce": nonce, "phase": "NEW", "value": "BASELINE"}
    results = []
    state_reads = []

    def read(file):
        if file.name == "fake-manifest.json":
            return manifest
        state_reads.append(1)
        if len(state_reads) > 1 and mode == "fail_restore":
            return {**state, "phase": "RUNNING", "value": "FAULT"}
        return dict(state)

    def save(root, value):
        state.update(value)

    ticks = iter([10, 2000000000, 2000000001])
    monkeypatch.setattr(module.time, "monotonic_ns", lambda: next(ticks))
    monkeypatch.setattr(module, "read", read)
    monkeypatch.setattr(module, "save", save)
    monkeypatch.setattr(module, "locked", lambda _: contextlib.nullcontext())
    monkeypatch.setattr(module, "create", lambda path, value: results.append(value))
    module.driver(Path("/unused-fixture"))
    assert results[0]["phase"] == expected
    assert results[0]["baseline"] is baseline
    assert results[0]["within_budget"] is True


def test_refused_fake_arm_has_no_invented_duration(monkeypatch):
    path = Path(__file__).parent / "stand/wave3_fake_recovery.py"
    spec = importlib.util.spec_from_file_location("fake_refusal_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results = []

    def read(file):
        if file.name == "fake-manifest.json":
            return {"nonce": "a" * 32, "mode": "bad_baseline"}
        return {"nonce": "a" * 32, "phase": "NEW", "value": "OTHER"}

    def no_clock():
        raise AssertionError("refusal must precede clock arming")

    monkeypatch.setattr(module, "read", read)
    monkeypatch.setattr(module, "save", lambda *args: None)
    monkeypatch.setattr(module, "locked", lambda _: contextlib.nullcontext())
    monkeypatch.setattr(module, "create", lambda path, value: results.append(value))
    monkeypatch.setattr(module.time, "monotonic_ns", no_clock)
    module.driver(Path("/unused-fixture"))
    assert results[0]["phase"] == "REFUSED"
    assert results[0]["timing_measured"] is False
    assert results[0]["elapsed_ms"] is None and results[0]["within_budget"] is None
