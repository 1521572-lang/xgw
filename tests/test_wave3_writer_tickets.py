import importlib.util
from pathlib import Path

import pytest


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / "stand" / file)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture
def candidate(tmp_path):
    tmp_path.chmod(0o700)
    value = module("ticket_candidate", "wave3_writer_tickets.py")
    value.L = module("z_ledger", "wave3_writer_fence_dry.py")
    return value, value.Gate.initialize(tmp_path / "case")


def test_failed_cleanup_keeps_committing_and_disallows_recompletion(candidate, monkeypatch):
    value, gate = candidate
    token = gate.admit("CORE")
    real_save = gate.save
    calls = []

    def failing_save(fd, data):
        calls.append(1)
        if len(calls) == 2:
            raise OSError("cleanup")
        real_save(fd, data)

    monkeypatch.setattr(gate, "save", failing_save)
    with pytest.raises(OSError):
        gate.complete(token, verified=True)
    assert value.L.read(gate.root / "state.json")["generation"] == "g1"
    assert gate.read()["tickets"][0]["phase"] == "COMMITTING"
    with pytest.raises(ValueError, match="COMPLETION_UNVERIFIED"):
        gate.complete(token, verified=True)
    with pytest.raises(ValueError, match="WRITERS_IN_FLIGHT"):
        gate.lease("g1")


def test_child_style_nested_admission_has_no_pending_state(candidate):
    value, gate = candidate
    parent = gate.admit("CORE")
    with pytest.raises(ValueError, match="WRITERS_IN_FLIGHT"):
        gate.lease()
    hook = value.Gate(gate.root)
    child = hook.admit("TUN_HOOK")
    hook.complete(child, verified=True)
    gate.complete(parent, verified=True)
    assert not gate.read()["tickets"]
    gate.lease("g2")


def test_uncertain_callback_blocks_new_admission_and_recovery(candidate):
    _, gate = candidate

    def partial_mutation():
        raise OSError("side effect may already exist")

    with pytest.raises(OSError):
        gate.operate("PEERS", partial_mutation, lambda: True)
    assert gate.read()["tickets"][0]["phase"] == "UNKNOWN"
    with pytest.raises(ValueError, match="UNKNOWN_WRITER"):
        gate.admit("CAPTURE")
    with pytest.raises(ValueError, match="WRITERS_IN_FLIGHT"):
        gate.lease()
