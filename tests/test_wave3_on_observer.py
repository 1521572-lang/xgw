"""Narrow observer failures/privacy checks; no service or network operations."""

import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


def observer():
    path = Path(__file__).parent / "stand/wave3_on_observer.py"
    spec = importlib.util.spec_from_file_location("on_observer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_private_process_and_interface_identifiers_are_not_exported():
    tool = observer()
    value = {
        "hashes_private": ["secret_hash"],
        "unit_private": {"secret_unit": 123},
        "boot_private": "secret_boot",
        "interface_private": {"LAN": "secret_nic"},
        "singbox": {"process_identity": [999, "secret_start"], "no_new_privs": True},
        "capture_after": True,
    }
    exported = tool.public(value)
    assert exported == {"singbox": {"no_new_privs": True}, "capture_after": True}
    assert value["singbox"]["process_identity"] == [999, "secret_start"]


def test_service_account_alias_to_root_is_reported_as_privileged(monkeypatch):
    tool = observer()
    monkeypatch.setattr(
        tool.pwd,
        "getpwnam",
        lambda name: SimpleNamespace(pw_uid=0 if name == "xgw-singbox" else 123, pw_gid=0),
    )
    monkeypatch.setattr(
        tool.grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=0 if name == "root" else 123)
    )
    result = tool.caps(os.getpid())
    assert result["account_nonprivileged"] is False


@pytest.mark.parametrize("raw", [b"not json", b'{"nftables":{}}', b'{"nftables":[7]}'])
def test_unreadable_guard_never_becomes_a_confirmed_layout(monkeypatch, raw):
    tool = observer()
    monkeypatch.setattr(tool, "query", lambda argv: (0, raw))
    assert tool.guard()["query"] == "parse_or_schema_error"


def test_query_timeout_is_not_an_empty_successful_journal(monkeypatch):
    tool = observer()

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("read-only", 3)

    monkeypatch.setattr(tool.subprocess, "run", timeout)
    assert tool.query(["journalctl"]) == (None, b"")
    assert tool.logs(0) == {"query_ok": False, "limit": 2000}


def test_journal_limit_preserves_incomplete_coverage_and_no_messages(monkeypatch):
    tool = observer()
    row = json.dumps({"MESSAGE": "fatal permission denied PRIVATE_URI", "PRIORITY": "3"}).encode()
    monkeypatch.setattr(tool, "query", lambda argv: (0, b"\n".join([row] * 2001)))
    result = tool.logs(0)
    assert result["rows"] == 2001 and result["truncated"] is True
    assert (
        result["fatal_rows"] == result["permission_rows"] == result["error_priority_rows"] == 2000
    )
    assert "PRIVATE_URI" not in json.dumps(result)


def test_off_baseline_does_not_start_a_watch_or_change_network(tmp_path, monkeypatch, capsys):
    tool = observer()
    tmp_path.chmod(0o700)
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    monkeypatch.setattr(tool.sys, "argv", ["observer.py", "start"])
    monkeypatch.setattr(
        tool,
        "snapshot",
        lambda: {"capture_before": False, "capture_after": False, "guard": {}, "singbox": {}},
    )
    monkeypatch.setattr(tool.subprocess, "run", lambda *a, **kw: pytest.fail("no command allowed"))
    assert tool.main() == 3
    assert "STOP_BASELINE_READ" in capsys.readouterr().out
    assert (tmp_path / "start-summary.json").exists()


def test_end_before_observation_interval_cannot_take_another_snapshot(tmp_path, monkeypatch):
    tool = observer()
    tmp_path.chmod(0o700)
    start = {
        "boot_private": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "monotonic": tool.time.monotonic(),
    }
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    monkeypatch.setattr(tool.sys, "argv", ["observer.py", "end"])
    monkeypatch.setattr(tool, "load", lambda name: start)
    monkeypatch.setattr(tool, "good", lambda value: True)
    monkeypatch.setattr(tool, "snapshot", lambda: pytest.fail("too early to sample end"))
    monkeypatch.setattr(tool.subprocess, "run", lambda *a, **kw: pytest.fail("no command allowed"))
    with pytest.raises(ValueError, match="too early"):
        tool.main()
    assert not (tmp_path / "end-summary.json").exists()
