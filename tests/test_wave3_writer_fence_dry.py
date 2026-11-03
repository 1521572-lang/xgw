"""Narrow failure-atomicity and bounded-lock checks; no peer batch or real XGW access."""

import importlib.util
from pathlib import Path

import pytest


def tool():
    spec = importlib.util.spec_from_file_location(
        "fence_dry", Path(__file__).parent / "stand/wave3_writer_fence_dry.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_interrupted_atomic_replace_keeps_old_generation_and_stable_lock(tmp_path, monkeypatch):
    m = tool()
    store = m.Store.initialize(tmp_path / "fixture")
    old_identity = (store.root / "lock").stat().st_ino
    replace = m.os.replace

    def fail(source, target):
        if Path(target) == store.root / "state.json":
            raise OSError("synthetic write interruption")
        return replace(source, target)

    monkeypatch.setattr(m.os, "replace", fail)
    with pytest.raises(OSError):
        store.writer("g0", "g1")
    assert m.read(store.root / "state.json")["generation"] == "g0"
    assert (store.root / "lock").stat().st_ino == old_identity
    assert (store.root / "state.part").exists()
    with pytest.raises(FileExistsError):
        store.writer("g0", "g1")
    assert m.read(store.root / "state.json")["generation"] == "g0"


def test_lock_deadline_never_breaks_or_replaces_other_open_description(tmp_path, monkeypatch):
    m = tool()
    store = m.Store.initialize(tmp_path / "fixture")
    inode = (store.root / "lock").stat().st_ino
    times = iter((0, 1))
    calls = []

    def busy(fd, operation):
        calls.append(operation)
        if operation & m.fcntl.LOCK_NB:
            raise BlockingIOError

    monkeypatch.setattr(m.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(m.fcntl, "flock", busy)
    with pytest.raises(m.Refuse, match="LOCK_BUSY"):
        store.writer("g0", "g1")
    assert calls == [m.fcntl.LOCK_EX | m.fcntl.LOCK_NB, m.fcntl.LOCK_UN]
    assert (store.root / "lock").stat().st_ino == inode
    assert m.read(store.root / "state.json")["generation"] == "g0"


def test_false_verification_does_not_retire_running_lease(tmp_path):
    m = tool()
    store = m.Store.initialize(tmp_path / "fixture")
    token = store.acquire("ownerA", "g0", 1)
    store.begin_job(token, 2)
    with pytest.raises(m.Refuse, match="RECOVERY_UNVERIFIED"):
        store.retire(token, reason="RESTORED_ON", verified="true", observed_generation="g0")
    assert m.read(store.root / "state.json")["phase"] == "RUNNING"
    with pytest.raises(m.Refuse, match="FENCED"):
        store.writer("g0", "g1")
