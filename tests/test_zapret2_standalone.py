"""Самостоятельный режим: маршруты без VPN, запуск без подписки, сбои и возврат."""

from types import SimpleNamespace

import pytest
import test_daemon as daemon_tests
from test_zapret2 import Runtime, Store

from xgw import config, engine, zapret2
from xgw.generator import builder
from xgw.gui import model
from xgw.net import nft
from xgw.paths import Paths, atomic_write_json
from xgw.watch import standalone, zapret2_control
from xgw.watch.states import State

daemon = daemon_tests.daemon


def configured():
    cfg = config.Config()
    cfg.zapret2.mode = "standalone"
    cfg.zapret2.probe_urls = []
    return cfg


def test_empty_subscription_build_has_no_vpn_or_automatic_probes(tmp_path):
    cfg = configured()
    assert not zapret2.validate(cfg)
    result = engine.assemble(cfg, Paths(tmp_path), engine.Inventory(), mark=None,
                             logger=None, xray_bin=None, check=False).result
    current = result.config
    assert zapret2.standalone(current)
    assert not current.get("burstObservatory")
    assert not current["routing"].get("balancers")
    assert not result.nodes and not result.pool
    assert all(o["protocol"] in ("freedom", "blackhole", "dns") for o in current["outbounds"])
    assert not any(i["tag"].startswith("probe-") for i in current["inbounds"])
    rules = current["routing"]["rules"]
    selected = next(r for r in rules if r.get("outboundTag") == zapret2.OUT)
    assert selected["domain"] == cfg.zapret2.domains
    assert selected["network"] == "tcp" and selected["port"] == "443"
    assert rules[-2]["outboundTag"] == "block"  # QUIC/HTTP выбранных доменов не обходят очередь.
    assert rules[-1]["outboundTag"] == zapret2.DIRECT
    assert current["dns"]["servers"] == cfg.dns.direct_servers


def test_standalone_ignores_vpn_device_pool_and_direct_exceptions():
    cfg = configured()
    cfg.routing.direct_domains = list(cfg.zapret2.domains)
    cfg.routing.proxy_domains = ["domain:example.test"]
    cfg.free_pool.mode = "on"
    cfg.routing.kernel_direct = True
    assert not zapret2.validate(cfg)
    selected = builder.Selection(members=daemon_tests._inventory().nodes)
    current = builder.build(cfg, selected, hosts={}, pool_all=True,
                             pool=selected.members, pool_devices=["192.168.1.2"]).config
    assert all(o["protocol"] in ("freedom", "dns", "blackhole") for o in current["outbounds"])
    assert not any("source" in r or "balancerTag" in r for r in current["routing"]["rules"])
    assert nft.kernel_direct_blocker(cfg)
    rules, _ = nft.build_rules(cfg, capture=True, time_uids=())
    assert rules.zapret2_queue == cfg.zapret2.queue_num
    assert "queue num 200" in nft.render_guard(rules)


def test_worker_failure_keeps_direct_rule_and_never_falls_back(monkeypatch):
    cfg = configured()
    applied = builder.build(cfg, builder.Selection(), hosts={}).config
    runtime = Runtime()
    ctl = zapret2.Controller(Store(), runtime)
    monkeypatch.setattr(ctl, "probe", lambda *_: pytest.fail("HTTP probe in standalone"))
    def apply(*_):
        pytest.fail("standalone must not patch to VPN")
    ctl.step(cfg, applied, 0, apply)
    assert ctl.view["state"] == "active" and ctl.view["reason"] == "worker_ready"
    runtime.up = False
    ctl.step(cfg, applied, 1, apply)
    assert ctl.view["state"] == "blocked" and ctl.view["reason"] == "worker_down"
    assert ctl.view["gate_closed"] and zapret2.active(applied)
    ctl.step(cfg, applied, 2, apply)
    assert ctl.view["state"] == "blocked"  # выдерживает retry_seconds
    ctl.step(cfg, applied, cfg.zapret2.retry_seconds + 2, apply)
    assert ctl.view["state"] == "active"
    ctl.step(cfg, applied, 400, apply, allowed=False)
    assert ctl.view["state"] == "off" and not runtime.up


def started(slow=0, exits=False):
    cfg = configured()
    applied = builder.build(cfg, builder.Selection(), hosts={}).config
    runtime = Runtime()
    runtime.slow, runtime.exits = slow, exits
    ctl = zapret2.Controller(Store(), runtime)
    return cfg, applied, runtime, ctl, lambda *_: pytest.fail("standalone must not apply")


def count(runtime, name):
    return sum(1 for event, _ in runtime.events if event == name)


def test_worker_is_not_stopped_while_queue_appears(caplog):
    """Отчёт standalone r3: nfqws2 останавливали в секунду запуска — очередь не успевала."""
    cfg, applied, runtime, ctl, apply = started(slow=2)
    with caplog.at_level("INFO", logger="xgw.zapret2"):
        for now in (0, 2):
            ctl.step(cfg, applied, now, apply)
            assert ctl.view == {"state": "preparing", "reason": "worker_starting",
                                "gate_closed": True, "probes": []}
            assert ctl.starting is not None and not ctl.ready and runtime.up
        assert runtime.events == [("gate", 0), ("start", 0)]  # ни остановки, ни разрешения
        ctl.step(cfg, applied, 4, apply)
    assert ctl.view["state"] == "active" and ctl.ready and ctl.starting is None
    assert count(runtime, "start") == 1 and count(runtime, "stop") == 0
    assert runtime.events[-1] == ("gate", cfg.zapret2.check_seconds + 60)
    assert "очередь занята через 4.0 с" in caplog.text


def test_start_deadline_stops_worker_and_waits_for_retry(caplog):
    cfg, applied, runtime, ctl, apply = started(slow=10**6)
    with caplog.at_level("INFO", logger="xgw.zapret2"):
        ctl.step(cfg, applied, 0, apply)
        ctl.step(cfg, applied, zapret2.START_WAIT - 1, apply)
        assert ctl.view["state"] == "preparing" and count(runtime, "stop") == 0
        ctl.step(cfg, applied, zapret2.START_WAIT, apply)
    assert ctl.view == {"state": "blocked", "reason": "start_timeout",
                        "gate_closed": True, "probes": []}
    assert not runtime.up and ctl.starting is None and not ctl.ready
    assert "отказ обработчика: start_timeout (ActiveState=inactive" in caplog.text
    assert "остановлен демоном: start_timeout" in caplog.text
    ctl.step(cfg, applied, zapret2.START_WAIT + 5, apply)  # до retry_seconds — без запуска
    assert count(runtime, "start") == 1 and ctl.view["reason"] == "start_timeout"
    runtime.slow = 0
    ctl.step(cfg, applied, zapret2.START_WAIT + cfg.zapret2.retry_seconds, apply)
    assert count(runtime, "start") == 2 and ctl.view["state"] == "active"


def test_worker_exit_during_start_is_not_hidden_by_the_wait():
    cfg, applied, runtime, ctl, apply = started(exits=True)
    ctl.step(cfg, applied, 0, apply)
    assert ctl.view["state"] == "blocked" and ctl.view["reason"] == "worker_exited"
    assert ctl.view["gate_closed"] and ctl.starting is None and not runtime.up
    assert all(seconds == 0 for event, seconds in runtime.events if event == "gate")


def test_switching_off_during_start_stops_worker(caplog):
    cfg, applied, runtime, ctl, apply = started(slow=10**6)
    ctl.step(cfg, applied, 0, apply)
    with caplog.at_level("INFO", logger="xgw.zapret2"):
        ctl.step(cfg, applied, 1, apply, allowed=False, gating="capture_off")
    assert ctl.view["state"] == "off" and not runtime.up and ctl.starting is None
    assert "остановлен демоном: capture_off" in caplog.text
    ctl.step(cfg, applied, 2, apply)  # перехват вернулся: новый запуск без retry_seconds
    assert count(runtime, "start") == 2 and ctl.starting is not None
    ctl.close("mode_change")  # смена режима или остановка демона посреди запуска
    assert not runtime.up and ctl.starting is None
    assert runtime.events[-2:] == [("gate", 0), ("stop", 0)]


def test_daemon_shows_starting_worker_and_steps_sooner(daemon, monkeypatch):
    prepare_daemon(daemon, monkeypatch)
    daemon._zapret2.runtime.slow = 1
    assert daemon.tick() is State.HEALTHY
    assert daemon._zapret2.view["reason"] == "worker_starting"
    assert daemon._zapret2.starting is not None  # цикл демона шагает каждые START_POLL
    assert "запускается" in daemon.action
    view = zapret2_control.card(daemon.cfg, engine.read_json(daemon.paths.status_file),
                                {"mode": "on"}, True)
    assert view["title"] == "Обработчик запускается · без VPN" and "закрыты" in view["detail"]
    daemon.tick()
    assert daemon._zapret2.view["state"] == "active" and daemon._zapret2.starting is None


def test_standalone_card_does_not_require_vpn_or_probe_urls(monkeypatch):
    import time

    cfg = config.Config()
    monkeypatch.setattr(zapret2_control.Path, "is_file", lambda _: True)
    snapshot = {"updated": time.time(), "xray": {"ok": False},
                "zapret2": {"state": "off", "config_key": zapret2.config_key(cfg)}}
    view = zapret2_control.card(cfg, snapshot, {"mode": "off"}, True)
    assert not view["blockers"]["standalone"]
    assert view["blockers"]["selective"] and view["blockers"]["compare"]
    cfg.capture.fail_mode = "open"
    assert zapret2_control.prerequisites(cfg, "standalone")


def prepare_daemon(d, monkeypatch):
    d.cfg.zapret2.mode = "standalone"
    d.cfg.zapret2.probe_urls = []
    d._zapret2.runtime = Runtime()
    capture = {"mode": "off", "loaded": True}
    d.capture = SimpleNamespace(mode=lambda: capture["mode"],
                                enable=lambda: capture.update(mode="on"),
                                tailscale_via_vpn=lambda: False)
    monkeypatch.setattr(d, "_guard_capture", lambda *_: setattr(d, "capture_info", capture))
    monkeypatch.setattr(standalone, "stop_bridges", lambda _: True)
    monkeypatch.setattr(d, "_check_provider", lambda: pytest.fail("VPN-era external check"))
    return capture


def test_daemon_cold_start_without_servers_and_xray_failure_never_restores_vpn(daemon, monkeypatch):
    d = daemon
    prepare_daemon(d, monkeypatch)
    assert d.inventory is None
    assert d.tick() is State.HEALTHY
    assert zapret2.standalone(engine.read_json(d.paths.xray_config_file))
    assert not d.collected and not d.scanned and not d.e2e_checks and not d.measured
    assert d._zapret2.view["state"] == "active"
    snapshot = engine.read_json(d.paths.status_file)
    assert snapshot["zapret2"]["without_vpn"]
    d.observatory = None
    d.tick()
    d.tick()
    d.tick()
    assert not d.applier.rollbacks
    assert zapret2.standalone(engine.read_json(d.paths.xray_config_file))
    assert d.machine.state is State.XRAY_DOWN


def test_capture_off_is_respected_after_entry(daemon, monkeypatch):
    capture = prepare_daemon(daemon, monkeypatch)
    daemon.tick()
    capture["mode"] = "off"
    daemon.tick()
    assert capture["mode"] == "off"
    assert not daemon._zapret2.runtime.up
    assert zapret2.standalone(engine.read_json(daemon.paths.xray_config_file))


def test_explicit_return_to_vpn_does_not_wait_subscription_timer(daemon, monkeypatch):
    prepare_daemon(daemon, monkeypatch)
    daemon.tick()
    daemon.cfg.zapret2.mode = "off"
    daemon.next_refresh = 100000
    for _ in range(4):
        daemon.tick()
        if not zapret2.standalone(engine.read_json(daemon.paths.xray_config_file)):
            break
    assert not zapret2.standalone(engine.read_json(daemon.paths.xray_config_file))
    assert daemon.collected and not daemon._zapret2.runtime.up


def test_bridge_stop_refuses_vpn_config_and_clears_only_after_stop(daemon, monkeypatch):
    from xgw.apply import singbox_process as processes

    current = builder.build(configured(), builder.Selection(), hosts={}).config
    atomic_write_json(daemon.paths.xray_config_file, current)
    stopped = set()
    monkeypatch.setattr(processes, "stopped", lambda slot: slot in stopped)
    monkeypatch.setattr(processes, "stop", stopped.add)
    assert standalone.stop_bridges(daemon)
    assert stopped == {*processes.SLOTS, "legacy"}
    assert processes.read(daemon.paths) == {"active": "legacy", "pending": None, "draining": None}
    daemon._standalone_bridges_stopped = False
    atomic_write_json(daemon.paths.xray_config_file, {"outbounds": []})
    assert not standalone.stop_bridges(daemon)


def test_failed_apply_does_not_claim_without_vpn(daemon, monkeypatch):
    old = builder.build(daemon.cfg, builder.Selection(
        members=daemon_tests._inventory().nodes), hosts={}).config
    atomic_write_json(daemon.paths.xray_config_file, old)
    prepare_daemon(daemon, monkeypatch)
    daemon.apply_mode = "rejected"
    daemon.tick()
    assert daemon._zapret2.view["reason"] == "apply_failed"
    assert not daemon._zapret2.runtime.up
    assert not engine.read_json(daemon.paths.status_file)["zapret2"]["without_vpn"]
    attempts = len(daemon.applied)
    for _ in range(5):
        daemon.t += 3600
        daemon.tick()
    assert len(daemon.applied) == attempts
    assert daemon.store.get_meta(standalone.FAILURE) == "rejected"


def test_failed_switch_latch_survives_new_daemon_instance(daemon, monkeypatch):
    prepare_daemon(daemon, monkeypatch)
    daemon.store.set_meta(standalone.FAILURE, "pending")
    # Нет памяти предыдущего запуска; запись в SQLite одна останавливает применение.
    daemon.tick()
    assert not daemon.applied and not daemon.collected
    assert daemon._zapret2.view["reason"] == "apply_failed"
    daemon.cfg.zapret2.mode = "off"
    daemon._stop.set()  # Сброс отметки не требует сетевой проверки/включения VPN в этом тесте.
    daemon.tick()
    assert not daemon.store.get_meta(standalone.FAILURE)


def test_gui_does_not_call_direct_mode_vpn_protection():
    state = {"updated": 1, "state": "HEALTHY", "capture": {"mode": "on"},
             "power": {"can_off": True}, "zapret2": {"mode": "standalone", "state": "active",
             "without_vpn": True, "detail": "Прямой выход"}}
    assert model.power(state, False).title == "zapret2 без VPN"
    assert model.health(state, False) == ("ok", "zapret2 без VPN")
    assert model.shield(state, False)[1] == "Прямое подключение · без VPN"


def test_invalid_standalone_config_does_not_select_vpn(daemon, monkeypatch):
    prepare_daemon(daemon, monkeypatch)
    daemon.tick()
    daemon.cfg.capture.fail_mode = "open"
    assert zapret2.validate(daemon.cfg)
    assert daemon.cfg.zapret2.mode == "standalone"
    daemon.tick()
    assert daemon._zapret2.view["reason"] == "invalid_config"
    assert zapret2.standalone(engine.read_json(daemon.paths.xray_config_file))
    assert not daemon.collected and not daemon._zapret2.runtime.up
