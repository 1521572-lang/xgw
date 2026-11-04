"""Узкая проверка возврата двух файлов. Никаких команд машины."""

import importlib.util
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

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


def timing_fixture(monkeypatch, *, now, written, polled=0):
    helper = load()
    state = dict(builds=0, max_gap_s=0, stale_s=0, poll_gap_s=0,
                 _watch=[0, 0, polled])
    snapshot = {"assembly": {"builds": 3, "build_s": 12.5,
                              "apply_s": 1.2, "outcome": "unchanged"}}
    monkeypatch.setattr(helper, "read_status", lambda _path: (snapshot, int(written * 1e9)))
    monkeypatch.setattr(helper.time, "monotonic", lambda: now)
    return helper, state


def test_late_poll_does_not_turn_a_twenty_second_write_into_twenty_six(monkeypatch):
    helper, state = timing_fixture(monkeypatch, now=25.98, written=20)
    helper.status_watch(state)
    assert state["max_gap_s"] == 20 and state["poll_gap_s"] == 25.98
    assert state["builds"] == 3 and state["build_s"] == 12.5


def test_unchanged_status_over_twenty_five_stops_and_keeps_assembly_facts(monkeypatch):
    helper, state = timing_fixture(monkeypatch, now=25.98, written=0, polled=25.8)
    with pytest.raises(helper.CheckStop, match="не изменялся"):
        helper.status_watch(state)
    assert state["stale_s"] == 25.98 and state["builds"] == 3


def test_frequently_observed_real_write_delay_is_not_relaxed(monkeypatch):
    helper, state = timing_fixture(monkeypatch, now=25.1, written=25.05, polled=24.9)
    with pytest.raises(helper.CheckStop, match="между записями"):
        helper.status_watch(state)
    assert state["max_gap_s"] == 25.05


def test_missing_observations_are_unknown_not_proven_write_delay(monkeypatch):
    helper, state = timing_fixture(monkeypatch, now=40, written=40)
    with pytest.raises(helper.CheckStop, match="не установлен"):
        helper.status_watch(state)


def test_backwards_file_clock_is_unknown(monkeypatch):
    helper, state = timing_fixture(monkeypatch, now=1, written=-1)
    with pytest.raises(helper.CheckStop, match="время записи пошло назад"):
        helper.status_watch(state)


def test_status_data_and_timestamp_belong_to_same_open_file(tmp_path, monkeypatch):
    helper = load()
    path, replacement = tmp_path / "status.json", tmp_path / "new.json"
    path.write_bytes(b'{"old": true}')
    replacement.write_bytes(b'{"new": true}')
    os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    fstat = helper.os.fstat
    def replace_then_stat(fd):
        os.replace(replacement, path)
        return fstat(fd)
    monkeypatch.setattr(helper, "os", SimpleNamespace(
        open=os.open, fdopen=os.fdopen, fstat=replace_then_stat,
        O_RDONLY=os.O_RDONLY, O_NOFOLLOW=os.O_NOFOLLOW,
    ))
    snapshot, stamp = helper.read_status(path)
    assert snapshot == {"old": True} and stamp == 1_000_000_000
    assert path.read_bytes() == b'{"new": true}'


def test_slow_read_child_keeps_watching_status():
    helper = load()
    calls = []
    rc, raw = helper.run([sys.executable, "-c", "import time; time.sleep(.45); print('done')"],
                         timeout=3, watch=lambda: calls.append(time.monotonic()))
    assert rc == 0 and raw.strip() == b"done" and len(calls) >= 3


def test_measurement_stop_reaps_its_read_child(monkeypatch):
    helper = load()
    popen, children = helper.subprocess.Popen, []
    def spawn(*args, **kwargs):
        process = popen(*args, **kwargs)
        children.append(process)
        return process
    def stop():
        raise helper.CheckStop("fixed failure")
    monkeypatch.setattr(helper.subprocess, "Popen", spawn)
    with pytest.raises(helper.CheckStop):
        helper.run([sys.executable, "-c", "import time; time.sleep(30)"], watch=stop)
    assert len(children) == 1 and children[0].poll() is not None


def test_ready_read_returns_before_the_observation_window_ends(monkeypatch, capsys):
    helper = load()
    monkeypatch.setattr(helper, "prepared", lambda: dict(phase="наблюдение", updated=time.time()))
    def no_sleep(_seconds):
        raise AssertionError("ready must not wait for the end")
    monkeypatch.setattr(helper.time, "sleep", no_sleep)
    assert helper.report(ready=True) == 2
    assert "Прогон продолжается: наблюдение" in capsys.readouterr().out


@pytest.mark.parametrize("fresh", [True, False])
def test_status_failure_keeps_current_loop_phase_but_rejects_old_attempt(monkeypatch, fresh):
    helper, state = timing_fixture(monkeypatch, now=25.98, written=0, polled=25.8)
    state["started"] = 10
    reader = helper.read_status
    def read(path):
        if path == helper.LOOP:
            return ({"phase": "tick", "started": 2, "interval_s": 20,
                     "previous_step_s": 8}, (11 if fresh else 9) * 1_000_000_000)
        return reader(path)
    monkeypatch.setattr(helper, "read_status", read)
    with pytest.raises(helper.CheckStop, match="не изменялся"):
        helper.status_watch(state)
    assert state.get("loop_phase") == ("tick" if fresh else None)
    assert state["builds"] == 3


@pytest.mark.parametrize("active", [True, False])
def test_restore_keeps_working_network_without_code_proof(tmp_path, monkeypatch, active):
    helper, root, repo, baseline = prepare_fixture(tmp_path, monkeypatch)
    helper.prepare(repo)
    state = helper.read(root / "state.json")
    baseline["assembly"] = {}  # прежний status ещё не предъявлен, но связь исправна
    baseline["daemon_active"] = active
    monkeypatch.setattr(helper, "restart", lambda: None)
    moments = iter([0, 1, 16])
    monkeypatch.setattr(helper.time, "monotonic", lambda: next(moments))
    monkeypatch.setattr(helper.time, "sleep", lambda _seconds: None)
    commands = []
    monkeypatch.setattr(helper, "run", lambda args, **_kwargs: commands.append(args) or (0, b""))
    helper.restore(state)
    assert commands == [] and state["net_up_rc"] is None
    assert state["restored"] is False and "связь исправна" in state["restore_note"]
