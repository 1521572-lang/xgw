"""Narrow new AQ paths only; full offline batch is delegated to ThinkCentre."""

import importlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def helper(monkeypatch):
    path = Path(__file__).parent / "stand/wave3_observation_batch.py"
    spec = importlib.util.spec_from_file_location("aq_narrow", path)
    h = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(h)
    names = (
        "ownership_observations",
        "ownership_observation_sources",
        "ownership_observation_compare",
    )
    monkeypatch.setattr(h, "M", {n: importlib.import_module("xgw." + n) for n in names})
    monkeypatch.setattr(h, "DETAILS", dict.fromkeys(h.DETAIL_KEYS))
    return h


@pytest.mark.parametrize(
    "case",
    (
        "J_OVERFLOW",
        "J_DEPTH",
        "U_INACTIVE",
        "U_DUP",
        "P_COMM",
        "P_START_OVERFLOW",
        "N_RULE",
        "N_COUNTER",
        "N_ORDER",
        "N_EXPR",
        "N_BOOL_HANDLE",
        "S_MATCH",
        "S_PROCESS_BOUND",
        "S_PROCESS_UNBOUND",
        "S_VALIDATOR",
        "S_EVIDENCE_MUTATE",
        "S_EXPECTED_CLONE",
        "S_STALE",
        "S_CONTEXT_DRIFT",
        "B_OUTPUT",
        "B_CLEANUP",
        "B_HOST",
        "I_IMPORT",
        "I_RUNTIME",
        "I_CONSTRUCTOR",
        "I_PROPOSED_PROC",
        "I_PID_ZERO",
        "I_PID_MISMATCH",
        "I_PROFILE_CLEANUP",
    ),
)
def test_new_observation_paths(helper, tmp_path, case):
    helper.run_case(SimpleNamespace(root=tmp_path), case)


def test_policy_mutation_and_nested_result_are_fenced(helper):
    t, _, _ = helper.modules()
    session, expected = helper.session_fixture()
    ev = helper.collect_fixture(session)
    object.__setattr__(session.policy, "max_age_seconds", True)
    with pytest.raises(t.ObservationRefused):
        session.compare_scoped(ev, expected)


def test_blocked_host_constructor_and_capture_have_no_io(helper, monkeypatch):
    t, s, _ = helper.modules()

    def forbidden(*args, **kwargs):
        pytest.fail("host boundary performed IO")

    monkeypatch.setattr(s.os, "lstat", forbidden)
    monkeypatch.setattr(s.subprocess, "Popen", forbidden)
    monkeypatch.setattr(s.os, "readlink", forbidden)
    backend = s.LinuxReadonlyBackend(t.CapturePolicy())
    assert all(
        backend.capture(scope, "SINGLE").collection == "BLOCKED_SCOPE_REVIEW" for scope in t.SCOPES
    )


@pytest.mark.parametrize("mode", ("cap", "timeout", "rc1", "cleanup"))
def test_candidate_transport_uses_caps_and_only_owned_child(helper, monkeypatch, mode):
    t, s, _ = helper.modules()
    events = []

    class Stream:
        def fileno(self):
            return 999

        def close(self):
            events.append("close")

    class Child:
        stdout, stderr = Stream(), Stream()

        def poll(self):
            return None

        def kill(self):
            events.append("own_child_kill")

        def wait(self, timeout):
            if mode == "cleanup":
                raise s.subprocess.TimeoutExpired("private", timeout)
            return 1 if mode == "rc1" else -9 if mode in ("cap", "timeout") else 0

    class Selector:
        def __init__(self):
            self.entries = {}

        def register(self, stream, event, name):
            self.entries[stream] = name

        def get_map(self):
            return self.entries

        def select(self, timeout):
            stream = next(iter(self.entries))
            return [(SimpleNamespace(fileobj=stream, data=self.entries[stream]), 1)]

        def unregister(self, stream):
            del self.entries[stream]

        def close(self):
            pass

    chunks = iter([b"x" * 9] if mode == "cap" else [b"{}", b"", b""])
    times = iter([0.0, 10.0] if mode == "timeout" else [0.0] * 20)
    with monkeypatch.context() as patch:
        patch.setattr(s.os, "lstat", lambda path: SimpleNamespace(st_mode=0o100755, st_uid=0))
        patch.setattr(s.os, "set_blocking", lambda *args: None)
        patch.setattr(s.os, "read", lambda *args: next(chunks))
        patch.setattr(s.time, "monotonic", lambda: next(times))
        patch.setattr(s.selectors, "DefaultSelector", Selector)

        def spawn(argv, **kwargs):
            assert argv == ("/usr/sbin/nft", "-j", "-t", "list", "table", "ip", "xgw")
            assert kwargs["shell"] is False and kwargs["stdin"] == s.subprocess.DEVNULL
            events.append("fake_spawn")
            return Child()

        patch.setattr(s.subprocess, "Popen", spawn)
        transport = s.ProposedTransport(t.CapturePolicy(stdout_bytes=8))
        result = transport.query(s.spec_for("NFT_IPV4"), "/usr/sbin/nft")
        if mode == "cleanup":
            assert result.reason == "CLEANUP_UNCONFIRMED" and not result.cleanup_confirmed
            with pytest.raises(t.ObservationRefused):
                transport.query(s.spec_for("NFT_IPV4"), "/usr/sbin/nft")
        else:
            assert (
                result.collection
                == {"cap": "OUTPUT_LIMIT", "timeout": "TIMEOUT", "rc1": "ERROR"}[mode]
            )
    assert events.count("fake_spawn") == 1 and events.count("own_child_kill") == 1


def test_candidate_proc_assembly_zero_size_stream_and_unit_binding(helper, monkeypatch):
    t, s, _ = helper.modules()
    paths, opened = [], {}
    contents = {
        "/proc/sys/kernel/random/boot_id": b"11111111-1111-1111-1111-111111111111\n",
        "/proc/123/stat": helper.stat_raw(),
    }

    def fake_open(path, flags):
        assert path in contents and flags & s.os.O_NOFOLLOW and flags & s.os.O_NONBLOCK
        fd = 1000 + len(paths)
        paths.append(path)
        opened[fd] = contents[path]
        return fd

    def fake_read(fd, size):
        data = opened[fd][:size]
        opened[fd] = opened[fd][size:]
        return data

    with monkeypatch.context() as patch:
        patch.setattr(s.os, "open", fake_open)
        patch.setattr(s.os, "read", fake_read)
        patch.setattr(s.os, "fstat", lambda fd: SimpleNamespace(st_mode=0o100444, st_size=0))
        patch.setattr(s.os, "close", lambda fd: None)
        patch.setattr(
            s.os, "readlink", lambda path: "net:[1]" if path.endswith("net") else "mnt:[2]"
        )
        patch.setattr(s.time, "monotonic", lambda: 0.0)
        transport = s.ProposedTransport(t.CapturePolicy())
        context = transport.proc_context()
        process = transport.proc_process(s.spec_for("UNIT_XGW"), helper.complete(helper.unit_raw()))
    assert context.collection == process.collection == "COMPLETE"
    assert s.decode(s.spec_for("PROCESS_XGW"), process).status == "COMPLETE"
    assert paths == ["/proc/sys/kernel/random/boot_id", "/proc/123/stat"]


def test_candidate_zero_pid_does_not_read_proc(helper, monkeypatch):
    t, s, _ = helper.modules()

    def forbidden(*args):
        pytest.fail("PID0 caused proc read")

    monkeypatch.setattr(s.os, "open", forbidden)
    result = s.ProposedTransport(t.CapturePolicy()).proc_process(
        s.spec_for("UNIT_XGW"), helper.complete(helper.unit_raw(MainPID="0"))
    )
    assert result.reason == "PID_NOT_PRESENT"


def test_candidate_wrong_pid_is_not_bound(helper, monkeypatch):
    t, s, _ = helper.modules()
    monkeypatch.setattr(s.ProposedTransport, "_proc_stream", lambda *args: helper.stat_raw(pid=124))
    monkeypatch.setattr(s.ProposedTransport, "_namespace", lambda *args: "net:[1]")
    result = s.ProposedTransport(t.CapturePolicy()).proc_process(
        s.spec_for("UNIT_XGW"), helper.complete(helper.unit_raw())
    )
    assert result.collection == "ERROR" and result.reason == "INVALID_PAYLOAD"


def test_candidate_profile_stops_after_unconfirmed_cleanup(helper, monkeypatch):
    t, s, _ = helper.modules()
    calls = []
    monkeypatch.setattr(
        s.ProposedTransport, "proc_context", lambda self: helper.complete(helper.context_raw())
    )

    def query(self, spec, executable):
        calls.append(spec.scope_id)
        self.cleanup_confirmed = False
        return t.SourceResult(
            collection="ERROR", reason="CLEANUP_UNCONFIRMED", cleanup_confirmed=False
        )

    monkeypatch.setattr(s.ProposedTransport, "query", query)
    rows = s.proposed_profile(s.ProposedTransport(t.CapturePolicy()))
    assert calls == ["UNIT_XGW"] and len(rows) == 2
