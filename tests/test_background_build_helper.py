"""Узкая проверка возврата двух файлов. Никаких команд машины."""

import importlib.util
import os
from pathlib import Path


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
    baseline = dict(healthy=True, on=True, https=True, daemon_active=True, signature=["private"],
                    pool="off", pin={}, pids=[1, 2], mtime=1)
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


def test_changed_settings_or_transport_refuse_acceptance():
    helper = load()
    baseline = dict(healthy=True, on=True, https=True, daemon_active=True, signature=["private"],
                    pool="off", pin={}, pids=[1, 2])
    assert helper.good(baseline, baseline)
    for key in baseline:
        changed = {**baseline, key: None}
        assert not helper.good(changed, baseline)
