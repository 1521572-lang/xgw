"""Narrow mocked child-containment and collector-finalization checks, no real commands."""

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def tool():
    spec = importlib.util.spec_from_file_location(
        "snapshot_plan", Path(__file__).parent / "stand/wave3_on_snapshot.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def table():
    return [
        {"table": {"family": "ip", "name": "xgw"}},
        {"rule": {"family": "ip", "table": "xgw", "chain": "output", "expr": [{"accept": None}]}},
    ]


def test_mutating_command_or_check_without_stdin_never_starts_child(monkeypatch):
    m = tool()
    monkeypatch.setattr(m.subprocess, "Popen", lambda *a, **k: pytest.fail("child forbidden"))
    with pytest.raises(m.Refuse, match="COMMAND_NOT_ALLOWED"):
        m.query(("nft", "-f", "-"))
    with pytest.raises(m.Refuse, match="COMMAND_STDIN_SCOPE"):
        m.query(m.CHECK)


@pytest.mark.parametrize("timeout", [False, True])
def test_one_bounded_check_child_gets_scoped_JSON_and_cleanup_is_local(timeout, monkeypatch):
    m = tool()
    operations, sent = [], bytearray()

    class Stream:
        closed = False

        def __init__(self, fd):
            self.fd = fd

        def fileno(self):
            return self.fd

        def close(self):
            self.closed = True

    class Child:
        returncode = None
        stdin, stdout = Stream(10), Stream(20)
        waits = 0

        def poll(self):
            return self.returncode

        def wait(self, timeout):
            self.waits += 1
            if timeout_fixture and self.waits == 1:
                raise m.subprocess.TimeoutExpired("owned-child", timeout)
            self.returncode = -9 if timeout_fixture else 0

        def terminate(self):
            operations.append("terminate_own_child")

        def kill(self):
            operations.append("kill_own_child")

    timeout_fixture, child = timeout, Child()

    class Selector:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def register(self, *a):
            pass

        def unregister(self, *a):
            pass

        def select(self, remaining):
            if timeout_fixture:
                return []
            return [
                (SimpleNamespace(fileobj=child.stdout if child.stdin.closed else child.stdin), 1)
            ]

    def spawn(argv, **kwargs):
        assert tuple(argv) == m.CHECK and "-c" in argv
        assert kwargs["stderr"] == m.subprocess.DEVNULL
        operations.append("spawn")
        return child

    def write(fd, data):
        assert fd == 10
        sent.extend(data)
        return len(data)

    monkeypatch.setattr(m.subprocess, "Popen", spawn)
    monkeypatch.setattr(m.selectors, "DefaultSelector", Selector)
    monkeypatch.setattr(m.os, "set_blocking", lambda *a: None)
    monkeypatch.setattr(m.os, "read", lambda *a: b"")
    monkeypatch.setattr(m.os, "write", write)
    raw = json.dumps(m.make_transaction(table())).encode()
    if timeout:
        with pytest.raises(m.Refuse, match="COMMAND_TIME_LIMIT"):
            m.query(m.CHECK, raw)
        assert operations == ["spawn", "terminate_own_child", "kill_own_child"]
    else:
        assert m.query(m.CHECK, raw) == b""
        assert sent == raw and operations == ["spawn"]
    assert child.stdin.closed and child.stdout.closed


@pytest.mark.parametrize("baseline", [False, True])
def test_worker_partial_or_manifest_preserves_separation_from_live_recovery(
    baseline, tmp_path, monkeypatch
):
    m = tool()
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m, "fixtures", lambda: {"passed": 26, "total": 26})
    bundle = {
        "raw": {"config": b"PRIVATE_HOST", "cached_status": b"PRIVATE_STATUS"},
        "missing": [],
        "capture": table(),
        "guard": [],
        "rules": [],
        "routes": [],
        "units": {"PRIVATE_UNIT": [123, "PRIVATE_START"]},
        "boot": "PRIVATE_BOOT",
        "markers": [],
        "table": 100,
    }

    def collect():
        if not baseline:
            raise m.Refuse("WORKING_ON_UNCONFIRMED")
        return copy.deepcopy(bundle)

    calls = []

    def query(argv, data=None):
        calls.append(tuple(argv))
        assert tuple(argv) == m.CHECK and m.validate_transaction(m.decode(data))
        return b""

    monkeypatch.setattr(m, "collect", collect)
    monkeypatch.setattr(m, "query", query)
    m.worker()
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert len(summary["phases"]) == 4 and summary["network_requests"] == 0
    assert summary["writer_fence_verified"] is summary["runtime_recovery_implemented"] is False
    assert summary["active_faults_authorized"] is False and "PRIVATE" not in json.dumps(summary)
    assert summary["marker"] == ("ON_SNAPSHOT_PLAN_RECORDED" if baseline else "ON_SNAPSHOT_PARTIAL")
    assert len(calls) == int(baseline)
    assert (tmp_path / "manifest-private.json").exists() == baseline
    if baseline:
        manifest = json.loads((tmp_path / "manifest-private.json").read_text())
        assert manifest["status"] == "PLANNED_NOT_ARMED"
        payload = {n: (tmp_path / n).read_bytes() for n in manifest["files"]}
        assert m.manifest_check(manifest, payload)
    else:
        assert summary["phases"]["X2_private_snapshot"]["reason"] == "WORKING_ON_UNCONFIRMED"
