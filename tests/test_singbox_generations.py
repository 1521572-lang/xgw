"""Ровно путь G1: без VM-сети и запуска процессов, с настоящим API-планировщиком."""

import copy
import os
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

NL = chr(10)
REAL_BRIDGE_CHECK = g.bridge_check
REAL_START = p.start
REAL_STOPPED = p.stopped


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    paths, cfg = Paths(tmp_path), Config()
    paths.singbox_config_dir.mkdir(parents=True)
    if os.geteuid() != 0:
        # Тесты от владельца без sudo (ТЗ на машине, отчёт bridge-order): chown файла
        # поколения на root запрещён — владелец файлов здесь не проверяется.
        monkeypatch.setattr(os, "chown", lambda *args, **kwargs: None)
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
                assert not p.marker_path(paths).exists()
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
    monkeypatch.setattr(p, "identity", lambda core, slot: "")
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
    assert p.marker_path(w.paths).is_file()
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


@pytest.mark.parametrize("side", ["old", "new"])
def test_identity_bound_endpoint_is_refused_before_launch(gateway, side):
    w = gateway
    config = copy.deepcopy(w.old)
    if side == "old":
        w.old["endpoints"] = [{"type": "wireguard", "private_key": "fake"}]
        atomic_write_json(w.paths.singbox_config_file, w.old)
    else:
        config["endpoints"] = [{"type": "wireguard", "private_key": "fake"}]
    with pytest.raises(ValueError, match="WireGuard"):
        g.prepare(w.core, config, w.xray)
    assert w.alive == {p.LEGACY} and not w.api.calls
    assert p.read(w.paths)["pending"] is None


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


def _three_bridges(w):
    config, xray = copy.deepcopy(w.old), copy.deepcopy(w.xray)
    for fp, port in (("bbcc2233", 22002), ("ccdd3344", 22003)):
        inbound = copy.deepcopy(config["inbounds"][0])
        inbound.update(tag=f"sb-in-{fp}-d", listen_port=port)
        config["inbounds"].append(inbound)
        outbound = sb.bridge_outbound(port, "d", "fake")
        outbound["tag"] = f"spare-test-{fp}"
        xray["outbounds"].append(outbound)
    return config, xray


def test_daemon_ranks_members_first_then_by_failures(tmp_path, monkeypatch):
    from test_daemon import Harness, _started

    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []
    daemon = Harness(cfg, paths)
    try:
        _started(daemon)
        rank = daemon._bridge_rank()
        members = [fp for fp, place in rank.items() if place < 0]
        assert members and all(rank[fp] < g.UNKNOWN_RANK for fp in members)
        hour = str(int(daemon.wall() // 3600))
        daemon._healths()["ffff0000"] = {hour: [1, 3]}  # 3 сбоя из 4 — после неизвестных
        assert daemon._bridge_rank()["ffff0000"] == 0.75
    finally:
        daemon.store.close()


def test_bridges_of_working_servers_are_checked_first(gateway, monkeypatch):
    """Отчёт sub-remove: мёртвые первые мосты съедали срок, поколение не менялось. Порядок —
    по rank (участники, затем доля сбоев), на мост не больше BRIDGE_EACH."""
    w = gateway
    config, xray = _three_bridges(w)
    captured = []

    def reply(*args, **kwargs):
        captured.append((args[1], kwargs["max_total"]))
        return DownloadResult(ok=args[1] == 22003, kind="" if args[1] == 22003 else "stall")

    monkeypatch.setattr(g.checks, "http_get_via_proxy", reply)
    checked = REAL_BRIDGE_CHECK(w.core, config, xray, {"ccdd3344": -2.0, "aabb1122": 0.9})
    assert checked and [port for port, _cap in captured] == [22003]
    assert all(cap <= g.BRIDGE_EACH for _port, cap in captured)
    captured.clear()
    # Без порядка — как в конфиге; неизвестный (0.5) раньше частых сбоев (0.9).
    REAL_BRIDGE_CHECK(w.core, config, xray, {"aabb1122": 0.9})
    assert [port for port, _cap in captured] == [22002, 22003]


def test_no_bridge_in_use_is_not_a_refusal(gateway, monkeypatch):
    """Отчёт bridge-order: все серверы на Xray, sing-box держит заготовленные варианты —
    «мостов проверено 0 из 0» отклоняло всю сборку. Теперь поколение меняется."""
    w = gateway
    config, _xray = _three_bridges(w)
    xray = copy.deepcopy(w.xray)
    xray["outbounds"] = [{"protocol": "freedom", "tag": "direct"}]
    atomic_write_json(w.paths.xray_config_file, xray)  # и действующий Xray без мостов
    monkeypatch.setattr(g, "bridge_check", REAL_BRIDGE_CHECK)
    monkeypatch.setattr(g.checks, "http_get_via_proxy",
                        lambda *a, **kw: pytest.fail("мостов в работе нет — запросов нет"))
    checked = REAL_BRIDGE_CHECK(w.core, config, xray, {})
    assert checked and checked.summary == "мостов в работе нет"
    prepared = g.prepare(w.core, config, xray, rank={})
    assert g.finish(w.core, w.applier, prepared).mode in ("api", "unchanged")


def _spare_bridges_and_free_server(w):
    """Все мосты Xray запасные, в sing-box есть ещё безлимитный сервер вне работы Xray."""
    config, xray = _three_bridges(w)
    for outbound in xray["outbounds"]:
        if sb.bridge_variant(outbound):
            outbound["tag"] = "spare-test-" + str(outbound["settings"]["servers"][0]["port"])
    for letter, port in (("d", 22004), ("f", 22005)):
        inbound = copy.deepcopy(config["inbounds"][0])
        inbound.update(tag=f"sb-in-ddee4455-{letter}", listen_port=port)
        config["inbounds"].append(inbound)
    return config, xray


def test_silent_spares_do_not_stop_a_generation_when_a_usable_server_answers(gateway, monkeypatch):
    """Отчёт bridges-cause: 5 молчащих запасных hysteria2 остановили все сборки (п. 351)."""
    w = gateway
    config, xray = _spare_bridges_and_free_server(w)
    tried = []

    def reply(*args, **kwargs):
        tried.append(args[1])
        return DownloadResult(ok=args[1] == 22004, kind="" if args[1] == 22004 else "tls")

    monkeypatch.setattr(g.checks, "http_get_via_proxy", reply)
    checked = REAL_BRIDGE_CHECK(w.core, config, xray, {"ddee4455": -2.0}, {"ddee4455": 0.0})
    assert checked and tried == [22004] and "не из работающих" in checked.summary
    tried.clear()
    # Живой сервер не первый — запасные пробуются раньше него; вариант f не проверяется.
    checked = REAL_BRIDGE_CHECK(w.core, config, xray, {"ddee4455": 0.9}, {"ddee4455": 0.0})
    assert checked and tried == [22001, 22002, 22003, 22004]
    tried.clear()
    # Лимитный (надбавка 1.0) — после запасных, хотя по доле сбоев был бы первым (п. 352).
    checked = REAL_BRIDGE_CHECK(w.core, config, xray, {"ddee4455": 0.0}, {"ddee4455": 1.0})
    assert checked and tried == [22001, 22002, 22003, 22004]


def test_server_outside_the_usable_list_is_not_asked(gateway, monkeypatch):
    """Сервера нет в списке пригодных — запроса через него нет."""
    w = gateway
    config, xray = _spare_bridges_and_free_server(w)
    tried = []

    def reply(*args, **kwargs):
        tried.append(args[1])
        return DownloadResult(ok=False, kind="tls")

    monkeypatch.setattr(g.checks, "http_get_via_proxy", reply)
    checked = REAL_BRIDGE_CHECK(w.core, config, xray, {}, {})
    assert not checked and sorted(tried) == [22001, 22002, 22003]
    assert "мостов проверено 3 из 3: tls 3" in checked.summary


def test_bridge_that_carries_traffic_is_not_replaced_by_another_server(gateway, monkeypatch):
    """Мост участника молчит — поколение отклоняется, как раньше: другой сервер не довод."""
    w = gateway
    config, xray = _spare_bridges_and_free_server(w)
    first = next(item for item in xray["outbounds"] if sb.bridge_variant(item))
    first["tag"] = "proxy-test-aabb1122"
    tried = []

    def reply(*args, **kwargs):
        tried.append(args[1])
        return DownloadResult(ok=False, kind="tls")

    monkeypatch.setattr(g.checks, "http_get_via_proxy", reply)
    checked = REAL_BRIDGE_CHECK(w.core, config, xray, {"ddee4455": -2.0}, {"ddee4455": 0.0})
    assert not checked and 22004 not in tried


def test_daemon_offers_unlimited_and_limited_servers_with_normal_speed(tmp_path, monkeypatch):
    from test_daemon import Harness, _started

    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []
    daemon = Harness(cfg, paths)
    try:
        _started(daemon)
        nodes = [node.fingerprint for node in daemon.inventory.nodes]
        monkeypatch.setattr(daemon, "_mbps", lambda info: None)
        monkeypatch.setattr(daemon, "_prices", lambda: {})
        assert daemon._bridge_usable() == {}  # стоимость неизвестна, замера нет
        monkeypatch.setattr(daemon, "_prices", lambda: dict.fromkeys(nodes, 0.0))
        free = daemon._bridge_usable()
        assert free and set(free) <= set(nodes) and set(free.values()) == {0.0}
        monkeypatch.setattr(daemon, "_prices", lambda: dict.fromkeys(nodes, 2.0))
        assert daemon._bridge_usable() == {}  # лимитный без замера
        monkeypatch.setattr(daemon, "_mbps", lambda info: cfg.speed.min_mbps - 0.5)
        assert daemon._bridge_usable() == {}  # медленный лимитный
        monkeypatch.setattr(daemon, "_mbps", lambda info: float(cfg.speed.min_mbps))
        limited = daemon._bridge_usable()
        assert set(limited) == set(free) and set(limited.values()) == {1.0}
    finally:
        daemon.store.close()


def test_failed_bridges_are_counted_in_the_refusal(gateway, monkeypatch):
    w = gateway
    config, xray = _three_bridges(w)
    monkeypatch.setattr(g, "bridge_check", REAL_BRIDGE_CHECK)
    monkeypatch.setattr(g.checks, "http_get_via_proxy",
                        lambda *a, **kw: DownloadResult(ok=False, kind="stall"))
    with pytest.raises(ValueError, match=r"мостов проверено 3 из 3: stall 3"):
        g.prepare(w.core, config, xray, rank={})
    assert w.alive == {p.LEGACY} and p.read(w.paths)["pending"] is None


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



def test_boot_condition_is_checked_by_pid1_without_cli_config_access():
    text = (Path(__file__).resolve().parents[1] / "packaging/xgw-singbox.service").read_text()
    unit, service = text.split("[Service]", 1)
    assert "ConditionPathExists=!/run/xgw/singbox-managed" in unit
    assert "ExecCondition=" not in service
    assert "User=xgw-singbox" in service and "CapabilityBoundingSet=\n" in service
    assert "AmbientCapabilities=\n" in service and "NoNewPrivileges=true" in service


def test_unused_marker_is_cleared_after_legacy_recovery(gateway):
    w = gateway
    w.paths.run.mkdir(parents=True)
    p.marker_path(w.paths).write_text("managed\n")
    p.reap(w.core)
    assert not p.marker_path(w.paths).exists()


def test_marker_precedes_canonical_config_during_promotion(gateway, monkeypatch):
    w = gateway
    prepared = g.prepare(w.core, w.old, w.xray)
    original = g.atomic_write_json
    observed = []

    def write(path, value, **kwargs):
        if path == w.paths.singbox_config_file:
            observed.append(p.marker_path(w.paths).exists())
        return original(path, value, **kwargs)

    monkeypatch.setattr(g, "atomic_write_json", write)
    assert g.finish(w.core, w.applier, prepared).mode == "api"
    assert observed == [True]
    g.legacy(w.core, w.applier)
    assert not p.marker_path(w.paths).exists()


def _fake_proc(tmp_path, *, uid=990, gid=991, caps="0000000000000000", nnp="1",
               argv0="/opt/xgw/sing-box/sing-box", born=("777", "777")):
    base = tmp_path / "proc" / "4242"
    base.mkdir(parents=True)
    stat = "4242 (sing-box) S " + " ".join(["0"] * 18)
    reads = iter(born)
    status = NL.join(["Name:\tsing-box", f"Uid:\t{uid}\t{uid}\t{uid}\t{uid}",
                      f"Gid:\t{gid}\t{gid}\t{gid}\t{gid}",
                      *[f"{key}:\t{caps}" for key in p._CAPS], f"NoNewPrivs:\t{nnp}"])
    (base / "status").write_text(status)
    (base / "cmdline").write_bytes(argv0.encode() + bytes(1) + b"run" + bytes(1))
    return base, stat, reads


@pytest.mark.parametrize(("change", "reason"), [
    ({}, ""),
    ({"uid": 0}, "не от xgw-singbox"),
    ({"caps": "0000000000003000"}, "capabilities"),
    ({"nnp": "0"}, "NoNewPrivileges"),
    ({"argv0": "/usr/bin/other"}, "не бинарник"),
    ({"born": ("777", "778")}, "сменился"),
])
def test_new_generation_identity_is_checked_before_switch(tmp_path, monkeypatch, change, reason):
    """G1: UID/GID, capabilities, NoNewPrivileges и образ работающего процесса поколения;
    время рождения до и после чтения — тот же процесс."""
    base, stat, reads = _fake_proc(tmp_path, **change)
    real_read = Path.read_text

    def read_text(path, *args, **kwargs):
        if path == base / "stat":
            return stat + " " + next(reads)
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(p, "main_pid", lambda slot: 4242)
    monkeypatch.setattr(p.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=990))
    monkeypatch.setattr(p.grp, "getgrnam", lambda name: SimpleNamespace(gr_gid=991))
    monkeypatch.setattr(p.sb, "find_binary", lambda cfg, paths: Path("/opt/xgw/sing-box/sing-box"))
    core = SimpleNamespace(paths=None)
    problem = p.identity(core, "blue", proc=tmp_path / "proc")
    assert (reason in problem) if reason else problem == ""


def test_failed_identity_aborts_candidate_and_marks_checked_generation(gateway, monkeypatch):
    w = gateway
    monkeypatch.setattr(p, "identity", lambda core, slot: "работает не от xgw-singbox")
    with pytest.raises(ValueError, match="не от xgw-singbox"):
        g.prepare(w.core, w.old, w.xray)
    assert w.alive == {p.LEGACY} and w.api.calls == [] and p.read(w.paths)["pending"] is None
    monkeypatch.setattr(p, "identity", lambda core, slot: "")
    prepared = g.prepare(w.core, w.old, w.xray)
    assert g.finish(w.core, w.applier, prepared).mode == "api"
    assert p.summary(w.paths)["identity_ok"] is True


def test_generation_switch_reasons_are_counted():
    """«Карусель» из отчёта g1-c06: что изменилось в конфиге sing-box, ради чего новое
    поколение, — в состоянии поколений и в `xgw singbox status` за сутки."""
    old = {"inbounds": [{"tag": "a"}], "outbounds": [{"tag": "o", "server": "x"}],
           "dns": {"servers": [1]}, "route": {"rules": [1]}}
    assert g.changed_parts(old, copy.deepcopy(old)) == ()
    dns = copy.deepcopy(old)
    dns["dns"] = {"servers": [2]}
    assert g.changed_parts(old, dns) == ("dns_hosts",)
    settings = copy.deepcopy(old)
    settings["outbounds"][0]["server"] = "y"
    assert g.changed_parts(old, settings) == ("server_settings",)
    more = copy.deepcopy(old)
    more["inbounds"].append({"tag": "b"})
    assert g.changed_parts(old, more) == ("servers",)


def test_switch_history_in_summary(gateway):
    w = gateway
    changed = copy.deepcopy(w.old)
    changed["dns"] = {"servers": [{"type": "hosts", "predefined": {"h": ["192.0.2.9"]}}]}
    prepared = g.prepare(w.core, changed, w.xray)
    assert prepared.parts == ("dns_hosts",)
    assert g.finish(w.core, w.applier, prepared).mode == "api"
    summary = p.summary(w.paths)
    assert summary["switches_24h"] == 1
    assert summary["switch_reasons_24h"] == {"dns_hosts": 1}
    assert summary["last_switch_parts"] == ["dns_hosts"]
    assert summary["switch_fields_24h"] == {} and summary["last_switch_fields"] == []


def test_changed_server_fields_are_named_without_values():
    old = {"outbounds": [
        {"tag": "a", "server": "x", "tls": {"reality": {"short_id": "11"}, "sni": "s"}},
        {"tag": "b", "server": "y", "transport": {"path": "/p"}},
        {"tag": "c", "server": "z"}]}
    new = copy.deepcopy(old)
    new["outbounds"][0]["tls"]["reality"]["short_id"] = "22"
    new["outbounds"][1]["transport"]["path"] = "/q"
    new["outbounds"][1]["server_port"] = 8443
    fields = g.changed_fields(old, new)
    assert fields == ("server_port", "tls.reality.short_id", "transport.path", "servers=2")
    assert "22" not in repr(fields) and "/q" not in repr(fields)
    assert g.changed_fields(old, copy.deepcopy(old)) == ()


def test_composition_tells_where_servers_came_from_and_went():
    """Отчёт reality-pin-r3: смены состава (servers, route) — по строке журнала видно, откуда
    добавленные и куда делись убранные серверы sing-box; только числа."""
    def config(*tags):
        return {"inbounds": [{"tag": f"sb-in-{fp * 8}-{letter}"} for fp, letter in tags]}

    old = config(("a", "d"), ("b", "d"), ("c", "d"), ("c", "f"), ("f", "d"), ("1", "d"))
    new = config(("a", "d"), ("c", "d"), ("d", "d"), ("e", "d"), ("2", "d"))
    counts = g.composition(
        old, new, inventory={"a" * 8, "b" * 8, "c" * 8, "d" * 8, "e" * 8},
        before={"a" * 8, "b" * 8, "c" * 8, "e" * 8}, pool={"1" * 8, "2" * 8})
    assert counts == {"new": 1, "back": 0, "again": 1, "gone": 1, "dropped": 1, "pool_in": 1,
                      "pool_out": 1, "variants": 1}
    line = g.describe_composition(counts)
    assert line.startswith("состав sing-box: +3 −3 (подписка: новые +1, вернулись +0, снова "
                           "отобраны +1")
    back = g.composition(
        old, new, inventory={"a" * 8, "c" * 8, "d" * 8, "e" * 8},
        before={"a" * 8, "b" * 8, "c" * 8, "e" * 8}, pool={"1" * 8, "2" * 8},
        history={"d" * 8})
    assert (back["new"], back["back"], back["gone"]) == (0, 1, 2)
    first = g.composition(old, new, inventory=set(), before=None, pool=set())
    assert (first["new"], first["again"], first["gone"]) == (3, 0, 3)
    assert not any(g.composition(old, old, inventory=set(), before=None, pool=set()).values())
