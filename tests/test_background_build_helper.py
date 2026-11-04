"""Узкая проверка возврата двух файлов. Никаких команд машины."""

import importlib.util
import os
import time
from pathlib import Path

import pytest


def load():
    path = Path(__file__).parents[1] / "docs/helpers/background_build.py"
    spec = importlib.util.spec_from_file_location("background_build_helper", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_partial_copy_restores_both_files(tmp_path, monkeypatch):
    helper = load()
    root, lib = tmp_path / "private", tmp_path / "installed"
    root.mkdir(mode=0o700)
    (lib / "watch").mkdir(parents=True)
    monkeypatch.setattr(helper, "ROOT", root)
    monkeypatch.setattr(helper, "LIB", lib)
    baseline = dict(state="DEGRADED", on=True, https=True, daemon_active=True,
                    signature=["private"], pool="off", pin={}, pids=[1, 2], mtime=1)
    state = dict(phase="запущен", stage="подготовка", before=baseline, changed=[],
                 metadata={}, result=None, restored=None, net_up_rc=None)
    files = {}
    for index, name in enumerate(("daemon.py", "watch/status.py")):
        old, new = f"old {index}".encode(), f"new {index}".encode()
        files[name] = (helper.sha(old), helper.sha(new))
        (lib / name).write_bytes(old)
        (root / f"old-{index}.py").write_bytes(old)
        (root / f"new-{index}.py").write_bytes(new)
        state["metadata"][name] = [0o600, os.getuid(), os.getgid()]
    monkeypatch.setattr(helper, "FILES", files)
    monkeypatch.setattr(helper, "prepared", lambda: state)
    monkeypatch.setattr(helper, "observe", lambda: baseline)
    restarted = []
    monkeypatch.setattr(helper, "restart", lambda: restarted.append(True))
    write = helper.write
    failed = False

    def fail_second(path, raw, *args):
        nonlocal failed
        if path == lib / "watch/status.py" and raw == b"new 1" and not failed:
            failed = True
            raise OSError("private failure")
        return write(path, raw, *args)

    monkeypatch.setattr(helper, "write", fail_second)
    helper.worker()
    assert failed and restarted == [True]
    assert state["phase"] == "остановлен" and state["result"] is False
    assert state["restored"] is True and state["net_up_rc"] is None
    assert (lib / "daemon.py").read_bytes() == b"old 0"
    assert (lib / "watch/status.py").read_bytes() == b"old 1"


@pytest.mark.parametrize("before_state", ["HEALTHY", "DEGRADED"])
@pytest.mark.parametrize("after_state", ["HEALTHY", "DEGRADED"])
def test_changed_settings_or_transport_refuse_acceptance(before_state, after_state):
    helper = load()
    baseline = dict(state=before_state, on=True, https=True, daemon_active=True,
                    signature=["private"], pool="off", pin={}, pids=[1, 2])
    assert helper.good({**baseline, "state": after_state}, baseline)
    for state in ("WAN_DOWN", "XRAY_DOWN", "ALL_DEAD", "LEAK", None):
        assert not helper.good({**baseline, "state": state}, baseline)
    for key in baseline:
        changed = {**baseline, key: None}
        assert not helper.good(changed, baseline)


def prepare_fixture(tmp_path, monkeypatch):
    helper = load()
    root, lib, repo = tmp_path / "prepared", tmp_path / "installed", tmp_path / "repo"
    (lib / "watch").mkdir(parents=True)
    (repo / "src/xgw/watch").mkdir(parents=True)
    monkeypatch.setattr(helper, "ROOT", root)
    monkeypatch.setattr(helper, "LIB", lib)
    files = {}
    for index, name in enumerate(("daemon.py", "watch/status.py")):
        old, new = f"# old {index}".encode(), f"# new {index}".encode()
        files[name] = (helper.sha(old), helper.sha(new))
        (lib / name).write_bytes(old)
        (repo / "src/xgw" / name).write_bytes(new)
    monkeypatch.setattr(helper, "FILES", files)
    unit = tmp_path / "xgw.service"
    unit.write_bytes(b"# unit")
    monkeypatch.setattr(helper, "UNIT", helper.sha(unit.read_bytes()))
    monkeypatch.setattr(helper, "run", lambda args: (
        0, b"" if "DropInPaths" in args else str(unit).encode()))
    baseline = dict(state="DEGRADED", on=True, https=True, daemon_active=True,
                    mtime=time.time_ns())
    monkeypatch.setattr(helper, "observe", lambda _helper=None: baseline)
    return helper, root, repo, baseline


def test_failed_baseline_leaves_no_directory_then_degraded_prepares(tmp_path, monkeypatch):
    helper, root, repo, baseline = prepare_fixture(tmp_path, monkeypatch)
    baseline["https"] = False
    with pytest.raises(ValueError):
        helper.prepare(repo)
    assert not root.exists() and not list(tmp_path.glob("xgw-build-prepare-*"))
    baseline["https"] = True
    helper.prepare(repo)
    assert helper.read(root / "state.json")["before"]["state"] == "DEGRADED"
    assert (helper.LIB / "daemon.py").read_bytes() == b"# old 0"
    saved = (root / "state.json").read_bytes()
    with pytest.raises(ValueError):
        helper.prepare(repo)
    assert (root / "state.json").read_bytes() == saved


def test_failed_prepare_copy_cleans_only_its_temporary_directory(tmp_path, monkeypatch):
    helper, root, repo, _ = prepare_fixture(tmp_path, monkeypatch)
    old = tmp_path / "xgw-background-build"
    old.mkdir()
    (old / "keep").write_bytes(b"old failed attempt")
    write = helper.write
    def fail(path, *args, **kwargs):
        if path.name == "new-1.py":
            raise OSError("private failure")
        return write(path, *args, **kwargs)
    monkeypatch.setattr(helper, "write", fail)
    with pytest.raises(OSError):
        helper.prepare(repo)
    assert not root.exists() and not list(tmp_path.glob("xgw-build-prepare-*"))
    assert (old / "keep").read_bytes() == b"old failed attempt"
    monkeypatch.setattr(helper, "write", write)
    helper.prepare(repo)
    assert (root / "state.json").is_file()
