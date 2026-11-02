"""Only permission-helper plumbing/fixtures; no gateway, nft, service or route changes."""

import errno
import importlib.util
import os
import pwd
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest


def probe():
    path = Path(__file__).parent / "stand/wave3_permission_probe.py"
    spec = importlib.util.spec_from_file_location("permission_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def worker(tool):
    namespace = {"__name__": "fixture"}
    exec(compile(tool.WORKER, "<fixed-worker>", "exec"), namespace)
    return namespace


@pytest.mark.parametrize(
    "code,expected",
    [
        (errno.EACCES, "DENIED_PERMISSION"),
        (errno.EPERM, "DENIED_PERMISSION"),
        (errno.ENOENT, "TARGET_UNAVAILABLE"),
        (errno.ELOOP, "OTHER_OS_ERROR"),
    ],
)
def test_missing_target_or_symlink_is_not_permission_success(code, expected):
    namespace = worker(probe())

    def fail(*args):
        raise OSError(code, "PRIVATE_PATH")

    namespace["os"] = SimpleNamespace(open=fail, O_RDONLY=0, O_NOFOLLOW=0)
    result = namespace["attempt"]("open", "/private")
    assert result["outcome"] == expected
    assert "PRIVATE_PATH" not in str(result)


def test_other_nft_failure_is_not_a_denial_and_keeps_stderr_private():
    namespace = worker(probe())
    namespace["subprocess"] = SimpleNamespace(
        run=lambda *a, **kw: SimpleNamespace(returncode=1, stderr=b"PRIVATE_PARSE_ERROR"),
        DEVNULL=subprocess.DEVNULL,
        PIPE=subprocess.PIPE,
        TimeoutExpired=subprocess.TimeoutExpired,
    )
    result = namespace["attempt"]("nft", "/binary")
    assert result == {"outcome": "OTHER_COMMAND_FAILURE"}


def test_setpriv_failure_cannot_be_a_successful_denial(monkeypatch):
    tool = probe()
    monkeypatch.setattr(
        tool.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1, stdout=b"")
    )
    result = tool.child(
        {"uid": 1, "gid": 1, "groups": []},
        "open",
        "/private",
        {"setpriv": "/setpriv", "python3": "/python"},
    )
    assert result == {"outcome": "CHILD_OR_IDENTITY_ERROR", "identity_verified": False}


def test_unexpected_allow_stops_remaining_cases(monkeypatch):
    tool = probe()
    calls = []

    def allowed(*args):
        calls.append(args)
        return {"outcome": "ALLOWED", "identity_verified": True}

    monkeypatch.setattr(tool, "child", allowed)
    result = tool.run_cases(
        [
            ("first", {}, "open", "/first", "DENIED_PERMISSION"),
            ("second", {}, "open", "/second", "DENIED_PERMISSION"),
        ],
        {},
    )
    assert len(calls) == 1 and len(result) == 1 and result[0]["pass_expected"] is False


@pytest.mark.parametrize(
    "action,private,expected",
    [("open", False, "ALLOWED"), ("open", True, "DENIED_PERMISSION"), ("create", False, "ALLOWED")],
)
def test_setpriv_stdin_worker_only_on_temporary_files(action, private, expected):
    tool = probe()
    if os.geteuid() != 0 or not shutil.which("setpriv"):
        pytest.skip("requires root only for disposable child-identity fixture")
    account = pwd.getpwnam("nobody")
    tools = {"setpriv": shutil.which("setpriv"), "python3": "/usr/bin/python3"}
    identity = {"uid": account.pw_uid, "gid": account.pw_gid, "groups": []}
    with tempfile.TemporaryDirectory(prefix="xgw-w3m-helper-") as directory:
        root = Path(directory)
        root.chmod(0o777 if action == "create" else 0o755)
        target = root / "only-fixture"
        if action == "open":
            target.write_text("disposable fixture")
            target.chmod(0o600 if private else 0o644)
        result = tool.child(identity, action, target, tools)
        assert result["identity_verified"] is True and result["outcome"] == expected
        if action == "create":
            assert result["own_empty_file_removed"] is True and not target.exists()
