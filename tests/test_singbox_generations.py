"""Ровно путь G1: без VM-сети и запуска процессов, с настоящим API-планировщиком."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from xgw.apply import singbox_generation as g
from xgw.apply import singbox_process as p
from xgw.apply.applier import Applier
from xgw.apply.singbox import SingboxCore
from xgw.config import Config
from xgw.generator import singbox as sb
from xgw.paths import Paths, atomic_write_json
from xgw.watch.checks import DownloadResult
from xgw.xraycore.api import ApiError

REAL_BRIDGE_CHECK = g.bridge_check
REAL_START = p.start
REAL_STOPPED = p.stopped


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    paths, cfg = Paths(tmp_path), Config()
    paths.singbox_config_dir.mkdir(parents=True)
    alive = {p.LEGACY}

    class Service:
        def __init__(self, unit):
            self.unit = unit

        def is_active(self):
            return self.unit in alive

        def stop(self):
            alive.discard(self.unit)

        def restart(self):
            if self.unit == p.LEGACY:
                assert p.read(paths)["active"] == "legacy"  # ExecCondition
            alive.add(self.unit)

    old = {
        "inbounds": [{"tag": "sb-in-aabb1122-d", "type": "mixed", "listen": sb.LOCAL,
                      "listen_port": 22001, "users": [{"username": "xgw-d", "password": "fake"}]}],
        "outbounds": [], "route": {},
        "experimental": {"clash_api": {"external_controller": "127.0.0.1:10087", "secret": "fake"}},
    }
    bridge = sb.bridge_outbound(22001, "d", "fake")
    bridge["tag"] = "proxy-test-aabb1122"
    xray = {"outbounds": [bridge], "inbounds": [], "routing": {},
            "burstObservatory": {"subjectSelector": ["proxy-"]}}
    atomic_write_json(paths.singbox_config_file, old)
    atomic_write_json(paths.xray_config_file, xray)

    class API:
        def __init__(self):
            self.items = {bridge["tag"]: copy.deepcopy(bridge)}
            self.calls = []
            self.fail_adds = 0

        def remove_outbound(self, tag):
            self.calls.append("remove")
            self.items.pop(tag, None)

        def add_outbounds(self, items):
            self.calls.append("add")
            if self.fail_adds:
                self.fail_adds -= 1
                raise ApiError("fake API failure")
            self.items.update({i["tag"]: copy.deepcopy(i) for i in items})

    api = API()
    core = SingboxCore(cfg, paths, Service(p.LEGACY), validator=lambda config: (True, ""))
    monkeypatch.setattr(core, "_wait_ready", lambda config: None)
    monkeypatch.setattr(core, "sync_generation", lambda: setattr(
        core, "service", Service(p.unit(p.read(paths)["active"]))))
    monkeypatch.setattr(g, "SystemdXrayService", Service)
    monkeypatch.setattr(p, "start", lambda core, slot, config: alive.add(p.unit(slot)))
    monkeypatch.setattr(p, "stop", lambda slot: alive.discard(p.unit(slot)))
    monkeypatch.setattr(p, "stopped", lambda slot: p.unit(slot) not in alive)
    monkeypatch.setattr(g, "bridge_check", lambda *args: True)
    applier = Applier(cfg, paths, api, Service("xray-never-restart"),
                      validator=lambda config: (True, ""))
    monkeypatch.setattr(applier, "_restart", lambda *args, **kwargs: pytest.fail("Xray restart"))
    return SimpleNamespace(core=core, applier=applier, old=old, xray=xray, api=api,
                           paths=paths, alive=alive, service=Service)


def test_prepare_api_switch_drain_and_next_generation(gateway, monkeypatch):
    w = gateway
    prepared = g.prepare(w.core, w.old, w.xray)
    assert w.api.calls == [] and w.core.read() == w.old
    assert not p.ports(prepared.config).intersection(p.ports(w.old))
    assert len(w.alive) == 2
    outcome = g.finish(w.core, w.applier, prepared)
    assert outcome.mode == "api"
    assert w.api.items == {i["tag"]: i for i in prepared.xray["outbounds"]}
    assert prepared.xray["burstObservatory"] == w.xray["burstObservatory"]
    assert p.xray_ports(prepared.xray).isdisjoint(p.ports(w.old))
    assert w.core.read() == prepared.config and p.LEGACY in w.alive
    with pytest.raises(ValueError):
        g.prepare(w.core, prepared.config, prepared.xray)
    state = p.read(w.paths)
    with monkeypatch.context() as patch:
        patch.setattr(p.time, "monotonic", lambda: state["draining"]["until"] + 1)
        p.reap(w.core)
    assert w.alive == {p.unit(prepared.slot)}
    second = g.prepare(w.core, prepared.config, prepared.xray)
    assert second.slot != prepared.slot and len(w.alive) == 2
    g.abort(w.core, second)


def test_failed_bridge_leaves_old_without_api(gateway, monkeypatch):
    w = gateway
    monkeypatch.setattr(g, "bridge_check", lambda *args: False)
    with pytest.raises(ValueError, match="настоящий запрос"):
        g.prepare(w.core, w.old, w.xray)
    assert w.alive == {p.LEGACY} and w.api.calls == []
    assert w.core.read() == w.old and p.read(w.paths)["pending"] is None


def test_new_server_composition_gets_disjoint_bridges(gateway):
    w = gateway
    config, xray = copy.deepcopy(w.old), copy.deepcopy(w.xray)
    inbound = copy.deepcopy(config["inbounds"][0])
    inbound.update(tag="sb-in-bbcc2233-d", listen_port=22002)
    config["inbounds"].append(inbound)
    outbound = sb.bridge_outbound(22002, "d", "fake")
    outbound["tag"] = "spare-test-bbcc2233"
    xray["outbounds"].append(outbound)
    prepared = g.prepare(w.core, config, xray)
    assert g.finish(w.core, w.applier, prepared).mode == "api"
    assert len(w.api.items) == 2 and len(w.alive) == 2
    assert p.xray_ports(prepared.xray) == p.ports(prepared.config)
    assert p.xray_ports(prepared.xray).isdisjoint(p.ports(w.old))


def test_changed_inputs_discard_prepared_without_api(gateway):
    w = gateway
    prepared = g.prepare(w.core, w.old, w.xray)
    changed = copy.deepcopy(w.old)
    changed["route"]["changed"] = True
    atomic_write_json(w.paths.singbox_config_file, changed)
    assert g.finish(w.core, w.applier, prepared).mode == "rejected"
    assert w.alive == {p.LEGACY} and not w.api.calls


@pytest.mark.parametrize("failures,expected", [(1, "rejected"), (2, "failed")])
def test_api_failure_restores_old_or_keeps_both_when_uncertain(gateway, failures, expected):
    w = gateway
    prepared = g.prepare(w.core, w.old, w.xray)
    w.api.fail_adds = failures
    assert g.finish(w.core, w.applier, prepared).mode == expected
    assert w.core.read() == w.old
    if expected == "rejected":
        assert not w.paths.api_dirty_file.exists()
        assert w.alive == {p.LEGACY}
        assert list(w.api.items.values()) == w.xray["outbounds"]
    else:
        assert w.paths.api_dirty_file.exists() and len(w.alive) == 2
        assert p.read(w.paths)["pending"]["phase"] == "uncertain"
        with pytest.raises(ValueError):
            g.prepare(w.core, w.old, w.xray)
        w.applier._restart_and_wait = lambda: w.paths.api_dirty_file.unlink()
        g.legacy(w.core, w.applier)
        assert w.alive == {p.LEGACY} and not p.state_path(w.paths).exists()


def test_crash_after_api_commit_is_finished_on_next_step(gateway, monkeypatch):
    w = gateway
    prepared = g.prepare(w.core, w.old, w.xray)
    with monkeypatch.context() as patch:
        patch.setattr(g, "_promote", lambda *args: (_ for _ in ()).throw(OSError()))
        with pytest.raises(OSError):
            g.finish(w.core, w.applier, prepared)
    assert not w.paths.api_dirty_file.exists()
    g.recover(w.core)
    assert w.core.read() == prepared.config
    assert p.read(w.paths)["active"] == prepared.slot and len(w.alive) == 2


def test_candidate_cannot_require_xray_restart(gateway):
    w = gateway
    changed = copy.deepcopy(w.xray)
    changed["burstObservatory"] = {"subjectSelector": ["other-"]}
    with pytest.raises(ValueError, match="перезапуска Xray"):
        g.prepare(w.core, w.old, changed)
    assert w.alive == {p.LEGACY} and not w.api.calls


def test_ready_process_dies_before_api_old_remains(gateway):
    w = gateway
    prepared = g.prepare(w.core, w.old, w.xray)
    w.alive.discard(p.unit(prepared.slot))
    assert g.finish(w.core, w.applier, prepared).mode == "rejected"
    assert w.alive == {p.LEGACY} and not w.api.calls


@pytest.mark.parametrize("pid,state,expected", [(42, "deactivating", False), (0, "inactive", True)])
def test_deactivating_process_keeps_its_slot(monkeypatch, pid, state, expected):
    monkeypatch.setattr(p.cmd, "run", lambda *a, **kw:
                        f"LoadState=loaded\nMainPID={pid}\nActiveState={state}\n")
    assert REAL_STOPPED("blue") is expected


def test_body_check_uses_only_new_routed_bridge(gateway, monkeypatch):
    w = gateway
    captured = []
    monkeypatch.setattr(g.checks, "http_get_via_proxy", lambda *a, **kw: (
        captured.append((a, kw)) or DownloadResult(ok=True, downloaded=200000)))
    assert REAL_BRIDGE_CHECK(w.core, w.old, w.xray)
    assert captured[0][0][1] == 22001 and captured[0][1]["proxy_user"] == "xgw-d"
    assert captured[0][1]["min_body"] > 0


def test_transient_unit_keeps_installed_sandbox(gateway, monkeypatch):
    w = gateway
    # Restore actual start, whose only external operation is captured cmd.run.
    source = Path(__file__).resolve().parents[1] / "packaging/xgw-singbox.service"
    w.paths.systemd_dir.mkdir(parents=True)
    (w.paths.systemd_dir / p.LEGACY).write_bytes(source.read_bytes())
    captured = []
    monkeypatch.setattr(p.sb, "find_binary", lambda *args: w.paths.singbox_bin)
    monkeypatch.setattr(p.cmd, "run", lambda argv, **kw: captured.extend(argv))
    REAL_START(w.core, "blue", w.old)
    assert "User=xgw-singbox" in captured and "Group=xgw-singbox" in captured
    assert "CapabilityBoundingSet=" in captured and "AmbientCapabilities=" in captured
    assert "NoNewPrivileges=true" in captured and "ReadOnlyPaths=/run" in captured
    assert "ProtectSystem=strict" in captured and "Type=exec" in captured
    assert not any("SIGHUP" in part for part in captured)


def test_real_machine_helper_keeps_query_and_public_types(tmp_path):
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "docs/helpers/singbox_generation_check.py"
    spec = importlib.util.spec_from_file_location("g1_helper", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    assert helper.download_url("https://example.invalid/down?bytes=10000000&kind=test") == (
        "https://example.invalid/down?bytes=2097152&kind=test")
    with pytest.raises(ValueError):
        helper.download_url("http://example.invalid/no-size")
    state = {"bytes": 2097152, "ok": True, "seconds": 128.0, "http": 200,
             "error": None, "receiving": object(), "done": object()}
    assert json.loads(json.dumps(helper.public_stream(state)))["bytes"] == 2097152
    helper.ROOT = tmp_path
    status = {"state": "DEGRADED", "daemon_down": False, "xray": {"ok": True},
              "capture": {"mode": "on", "blocked": False, "loaded": True}}
    helper.run = lambda argv: SimpleNamespace(returncode=0, stdout=(
        json.dumps(status) if argv[0] == "xgw" else "301"))
    assert helper.health() == 0
    status["capture"]["loaded"] = False
    assert helper.health() == 3
