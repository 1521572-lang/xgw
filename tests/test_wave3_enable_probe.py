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
                      "child_rc": None}


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
                                     "mismatch", "no_routes", "invalid_result"])
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
    else:
        value["loaded_reason"] = "invalid_result"
    assert tool.diagnostic_ready(value) is False
