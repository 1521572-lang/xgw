"""Только новые границы диагностики enable: без служб и сетевых запросов."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def sampler():
    path = Path(__file__).parent / "stand/wave3_enable_probe.py"
    spec = importlib.util.spec_from_file_location("enable_sampler", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("error", [TimeoutError, ConnectionResetError])
def test_failed_body_keeps_bytes_from_previous_reads(error):
    tool = sampler()
    result = {"bytes": 0}

    class Stream:
        def settimeout(self, value):
            pass

    class Response:
        reads = 0

        def read1(self, size):
            self.reads += 1
            if self.reads == 1:
                return b"x" * 8192
            raise error()

    with pytest.raises(error):
        tool.consume(Response(), Stream(), tool.time.monotonic() + 3, result)
    assert result == {"bytes": 8192, "phase": "body"}


@pytest.mark.parametrize("failure", ["not_ready", "stale", "changed_sampler"])
def test_invalid_baseline_cannot_reach_enable(tmp_path, monkeypatch, failure):
    tool = sampler()
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    tool.guard.save(tmp_path / "snapshot.json", {"boot": boot})
    tool.guard.save(tmp_path / "baseline.json", {
        "ready": failure != "not_ready",
        "monotonic": tool.time.monotonic() - (301 if failure == "stale" else 0),
        "sampler_sha256": ("bad" if failure == "changed_sampler"
                           else tool.hashlib.sha256(tool.HERE.read_bytes()).hexdigest()),
    })
    monkeypatch.setattr(tool.subprocess, "run", lambda *a, **kw: pytest.fail("must not enable"))
    with pytest.raises(SystemExit, match="off-базы"):
        tool.run(tmp_path)


def test_manual_sampler_run_outside_tracked_job_cannot_enable(tmp_path, monkeypatch):
    tool = sampler()
    monkeypatch.setattr(tool, "permit", lambda directory: {"target": 0})
    monkeypatch.setattr(tool, "in_job", lambda: False)
    monkeypatch.setattr(tool.subprocess, "run", lambda *a, **kw: pytest.fail("must not enable"))
    with pytest.raises(SystemExit, match="job-unit"):
        tool.run(tmp_path)


@pytest.mark.parametrize("payload", [{}, {"schema": 1}, {"schema": 1, "loaded": "yes"}])
def test_missing_or_untyped_loaded_is_explicit_unknown(tmp_path, monkeypatch, payload):
    tool = sampler()

    def child(*args, **kwargs):
        tool.guard.save(tmp_path / "kernel-diagnostic.json", payload)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(tool.subprocess, "run", child)
    result = tool.loaded(tmp_path)
    assert result["loaded"] is None
    assert result["loaded_reason"] == "invalid_result"


def test_loaded_deadline_keeps_fast_facts_without_claiming_false(tmp_path, monkeypatch):
    tool = sampler()

    def child(*args, **kwargs):
        tool.guard.save(tmp_path / "kernel-diagnostic.json", {
            "schema": 1, "loaded": None, "loaded_reason": "pending_loaded",
            "effective_mode": "blocked", "inbound_problem_present": True,
        })
        raise tool.subprocess.TimeoutExpired(args[0], 4)

    monkeypatch.setattr(tool.subprocess, "run", child)
    result = tool.loaded(tmp_path)
    assert result == {"schema": 1, "loaded": None, "loaded_reason": "child_deadline",
                      "effective_mode": "blocked", "inbound_problem_present": True,
                      "child_rc": None, "context": "off", "child_budget_seconds": 4}


def test_route_summary_classifies_proxy_loopback_without_addresses():
    tool = sampler()
    result = tool.route_summary({"type": "local", "dev": "lo", "table": 100,
                                 "dst": "198.51.100.12", "prefsrc": "192.0.2.1"},
                                {"WAN": "enp1s0", "LAN": "enp2s0"}, "xgwtun0",
                                {"tproxy": 100, "tun": 101})
    assert result == {"device_role": "loopback", "route_type": "local",
                      "table_role": "tproxy"}


@pytest.mark.parametrize("state,expected", [("0A", True), ("01", False)])
def test_only_listen_state_at_exact_tproxy_port_is_listener(tmp_path, state, expected):
    tool = sampler()
    (tmp_path / "tcp").write_text(
        f"header\n0: 0100007F:3039 00000000:0000 {state} other\n"
        "1: 00000000:303A 00000000:0000 0A other\n")
    (tmp_path / "tcp6").write_text("header\n")
    result = tool.listener_summary(12345, tmp_path)
    assert result["ipv4_loopback"] is expected
    assert result["ipv4_any"] is False
    assert result["tcp_read"] is True


@pytest.mark.parametrize("failure", ["no_listener", "missing_inbound", "local_disabled",
                                     "mismatch", "no_routes", "invalid_result",
                                     "readonly_violation"])
def test_off_diagnostic_prevents_ready_before_known_bad_enable(failure):
    tool = sampler()
    value = {"schema": 1, "requested_mode": "off", "effective_mode": "off",
             "configured_local": True, "inbound_problem_present": False,
             "loaded": None, "capture_method": "tproxy",
             "mismatch_present": False, "loaded_reason": "child_deadline",
             "routes": {"unmarked": {"route_type": "unicast"}},
             "listener": {"tcp_read": True, "ipv4_loopback": True}}
    assert tool.diagnostic_ready(value) is True
    if failure == "no_listener":
        value["listener"]["ipv4_loopback"] = False
    elif failure == "missing_inbound":
        value["inbound_problem_present"] = True
    elif failure == "local_disabled":
        value["configured_local"] = False
    elif failure == "mismatch":
        value["mismatch_present"] = True
    elif failure == "no_routes":
        value["routes"] = {}
    elif failure == "readonly_violation":
        value["read_trace"] = {"readonly_violation": True}
    else:
        value["loaded_reason"] = "invalid_result"
    assert tool.diagnostic_ready(value) is False


@pytest.mark.parametrize("hook", ["output", "postrouting"])
def test_guard_layout_reports_actual_hook_without_exposing_rules(hook):
    tool = sampler()
    value = tool.guard_layout([
        {"chain": {"family": "inet", "table": "xgw_guard", "name": "output",
                   "hook": hook, "prio": 10}},
        {"chain": {"table": "xgw_guard", "name": "forward", "hook": "forward"}},
        {"rule": {"table": "xgw_guard", "chain": "output", "expr": [
            {"match": {"right": "192.0.2.1"}}, {"counter": {"packets": 2}}, {"drop": None}]}},
        {"rule": {"table": "foreign", "chain": "output", "expr": [{"reject": None}]}},
    ])
    assert value == {"query": "ok", "host_hook": hook, "host_priority": 10,
                     "forward_hook": "forward", "host_drop_rules": 1, "host_reject_rules": 0}


def test_guard_layout_does_not_invent_missing_chain_metadata():
    tool = sampler()
    value = tool.guard_layout([{"metainfo": {"version": "1.0.9"}}])
    assert value["host_hook"] is None
    assert value["forward_hook"] is None


@pytest.mark.parametrize("context,budget", [("off", 4), ("on", 8)])
def test_diagnostic_budget_and_context_are_explicit_without_extending_guard(
        tmp_path, monkeypatch, context, budget):
    tool = sampler()

    def child(argv, **kwargs):
        assert argv[-1] == context
        assert kwargs["timeout"] == budget
        tool.guard.save(tmp_path / "kernel-diagnostic.json", {
            "schema": 1, "loaded": True, "loaded_reason": "measured"})
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(tool.subprocess, "run", child)
    result = tool.loaded(tmp_path, context)
    assert result["child_budget_seconds"] == budget
    assert result["context"] == context


def test_guard_and_routes_saved_before_slow_inbound_policy_build(tmp_path, monkeypatch):
    from xgw import config
    from xgw.net import capture
    from xgw.paths import Paths

    tool = sampler()
    state_path = tmp_path / "live-state.json"
    tool.guard.save(state_path, {"enabled": True})
    tool.guard.save(tmp_path / "snapshot.json", {
        "capture_state": str(state_path), "interfaces": {"WAN": "wan0", "LAN": "lan0"}})
    tool.guard.save(tmp_path / "probe-plan.json", [{"address": ["198.51.100.1", 443], "port": 443}])
    tool.guard.save(tmp_path / "baseline.json", {"target": 0})
    cfg = config.Config()

    class SlowCapture:
        def mode(self):
            return "on"

        def _state(self):
            return {"enabled": True}

        def inbound_problem(self):
            raise RuntimeError("slow_inbound")

    def command(argv, **kwargs):
        if argv[0] == "nft":
            value = {"nftables": [{"chain": {"table": "xgw_guard", "name": "output",
                                            "hook": "postrouting", "prio": 10}},
                                  {"chain": {"table": "xgw_guard", "name": "forward",
                                             "hook": "forward"}}]}
        else:
            value = [{"type": "local", "dev": "lo", "table": 100}]
        return SimpleNamespace(returncode=0, stdout=tool.json.dumps(value).encode(), stderr=b"")

    monkeypatch.setattr(tool.subprocess, "run", command)
    monkeypatch.setattr(config, "load", lambda path: (cfg, []))
    monkeypatch.setattr(capture, "capture_for", lambda *args: SlowCapture())
    monkeypatch.setattr(Paths, "from_env", lambda: SimpleNamespace(config_file=tmp_path / "cfg"))
    monkeypatch.setattr(tool, "listener_summary", lambda port: {"ipv4_loopback": True})
    layout = tool.guard_query(tmp_path, "on")
    assert layout["host_hook"] == "postrouting"
    with pytest.raises(RuntimeError, match="slow_inbound"):
        tool.kernel(tmp_path, "on")
    checkpoint = tool.read_json(tmp_path / "kernel-diagnostic.json")
    assert tool.read_json(tmp_path / "on-guard.json")["host_hook"] == "postrouting"
    assert checkpoint["capture_enabled_now"] is True
    assert checkpoint["listener"]["ipv4_loopback"] is True
    assert set(checkpoint["routes"]) == {"unmarked", "proxy", "bypass"}
    assert checkpoint["phase"] == "inbound_check"
    assert checkpoint["loaded"] is None


NATIVE_GUARD = '''table inet xgw_guard {
    chain output {
        type filter hook postrouting priority 10; policy accept;
        meta iif != 0 return
        counter packets 0 bytes 0 drop
    }
    chain forward {
        type filter hook forward priority 10; policy accept;
        return
    }
}
'''


def test_native_fallback_reports_only_guard_metadata():
    tool = sampler()
    assert tool.native_guard_layout(NATIVE_GUARD) == {
        "query": "ok", "host_hook": "postrouting", "host_priority": 10,
        "forward_hook": "forward", "host_drop_rules": 1, "host_reject_rules": 0}


@pytest.mark.parametrize("failure,expected", [("timeout", "timeout"), ("rc", "nonzero"),
                                             ("json", "parse_or_schema_error"),
                                             ("schema", "parse_or_schema_error")])
def test_guard_query_distinguishes_failure_and_uses_readonly_native_fallback(
        tmp_path, monkeypatch, failure, expected):
    tool = sampler()
    state = tmp_path / "capture.json"
    tool.guard.save(state, {"enabled": True})
    tool.guard.save(tmp_path / "snapshot.json", {"capture_state": str(state)})

    def command(argv, **kwargs):
        assert kwargs["timeout"] == 3
        assert "list" in argv and "-n" in argv and "-y" in argv
        if "-j" in argv:
            if failure == "timeout":
                raise tool.subprocess.TimeoutExpired(argv, 3)
            return SimpleNamespace(returncode=1 if failure == "rc" else 0,
                                   stdout=b"bad json" if failure == "json" else b'[]', stderr=b"")
        return SimpleNamespace(returncode=0, stdout=NATIVE_GUARD.encode(), stderr=b"")

    monkeypatch.setattr(tool.subprocess, "run", command)
    result = tool.guard_query(tmp_path, "on")
    assert result["attempts"][0]["state"] == expected
    assert result["attempts"][1]["state"] == "ok"
    assert result["source"] == "text"
    assert result["capture_enabled_before"] is True
    assert result["host_hook"] == "postrouting"


@pytest.mark.parametrize("argv,expected", [
    (["ip", "-d", "-j", "link", "show", "dev", "private"], "ip_link_read"),
    (["nft", "list", "table", "inet", "xgw_guard; flush ruleset"], None),
])
def test_read_trace_refuses_writers_without_logging_interface_names(argv, expected):
    assert sampler().read_command_label(argv) == expected


def test_method_trace_preserves_exception_and_records_active_boundary(tmp_path):
    tool = sampler()

    class Capture:
        def rules(self):
            raise ValueError("private details")

    value = {}
    capture = Capture()
    tool.trace_capture(capture, tmp_path / "trace.json", value)
    with pytest.raises(ValueError, match="private details"):
        capture.rules()
    saved = tool.read_json(tmp_path / "trace.json")
    assert saved["read_trace"]["active"] == []
    record = saved["read_trace"]["calls"][0]
    assert record["state"] == "exception" and record["error_class"] == "ValueError"
    assert "private details" not in tool.json.dumps(saved)
