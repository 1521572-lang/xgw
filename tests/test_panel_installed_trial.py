"""Restore an installed-panel overlay after a partial apply."""

import importlib.util
import json
import os
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "docs/helpers/panel_installed_trial.py"


@pytest.fixture()
def trial(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("panel_installed_trial", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "PACKAGE", tmp_path / "installed")
    monkeypatch.setattr(module, "UNITS", tmp_path / "units")
    monkeypatch.setattr(module, "RUNTIME", tmp_path / "ipc")
    monkeypatch.setattr(module, "RELAY", tmp_path / "relay.sock")
    monkeypatch.setattr(module, "require_idle_workers", lambda: None)
    monkeypatch.setattr(module, "reader_identity", lambda: object())
    monkeypatch.setattr(module, "trusted", lambda _: None)
    calls = []

    def systemctl(*args, **_):
        calls.append(args)
        if args[0] == "is-active":
            return "active"
        if "FragmentPath" in args:
            return str(module.UNITS / module.MAIN)
        if "LoadState" in args:
            return "not-found"
        return ""

    def atomic(path, content, mode=0o644, gid=0):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(mode)
        assert gid in (0, path.stat().st_gid)

    monkeypatch.setattr(module, "systemctl", systemctl)
    monkeypatch.setattr(module, "atomic", atomic)
    stage = tmp_path / "stage"
    for relative in module.RELATIVE:
        atomic(stage / "code" / relative, b"# candidate\n")
        if relative in ("src/xgw/cli.py", "packaging/xgw.service"):
            atomic(stage / "base" / relative, b"# original\n")
            atomic(module.target(relative), b"# original\n", mode=0o640)
    module.prepare(stage)
    manifest = json.loads((stage / "manifest.json").read_text())
    for row in manifest["files"].values():
        if row["before"] is None:
            row["gid"] = os.getegid()  # files created by the unprivileged test process
    return module, stage, manifest, calls


def test_partial_apply_restores_files_before_restarting_xgw(trial, monkeypatch):
    module, stage, manifest, calls = trial
    atomic = module.atomic

    def fail_once(path, content, mode=0o644, gid=0):
        if path == module.PACKAGE / "watch/panel.py" and content == b"# candidate\n":
            raise OSError("synthetic write failure")
        atomic(path, content, mode, gid)

    monkeypatch.setattr(module, "atomic", fail_once)
    with pytest.raises(OSError, match="synthetic write failure"):
        module.apply(stage, manifest)
    assert (module.PACKAGE / "cli.py").read_bytes() == b"# candidate\n"
    assert (module.PACKAGE / "install.py").exists()
    assert ("start", module.MAIN) not in calls
    module.rollback(stage, manifest)
    assert (module.PACKAGE / "cli.py").read_bytes() == b"# original\n"
    assert (module.PACKAGE / "cli.py").stat().st_mode & 0o777 == 0o640
    assert not (module.PACKAGE / "install.py").exists()
    assert not (stage / "started").exists()
    assert calls[-3:] == [("daemon-reload",), ("start", module.MAIN), ("is-active", module.MAIN)]
    module.rollback(stage, manifest)
    assert calls.count(("start", module.MAIN)) == 1


def test_rollback_detects_an_unexpected_edit_before_stopping_xgw(trial):
    module, stage, manifest, calls = trial
    module.apply(stage, manifest)
    cli = module.PACKAGE / "cli.py"
    cli.write_text("# third version\n", encoding="utf-8")
    before = calls.copy()
    with pytest.raises(ValueError, match="target_changed src/xgw/cli.py"):
        module.rollback(stage, manifest)
    assert calls == before and cli.read_text(encoding="utf-8") == "# third version\n"
