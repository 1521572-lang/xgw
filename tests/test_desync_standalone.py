from unittest.mock import Mock

import pytest

from xgw import config, engine, nfqws2, zapret2
from xgw.generator import builder
from xgw.paths import Paths


def _standalone():
    cfg = config.Config()
    cfg.zapret2.mode = "standalone"
    cfg.zapret2.strategy = "hostfakesplit_md5"
    cfg.zapret2.engine = "auto"
    return cfg


def test_build_without_servers_is_closed_until_queue_is_ready():
    cfg = _standalone()
    built = builder.build(cfg, builder.Selection(), hosts={}, ipv6=False)
    closed = built.config
    assert not nfqws2.enabled(cfg)
    assert not built.nodes and not built.pool
    assert "burstObservatory" not in closed
    assert "balancers" not in closed["routing"]
    assert {out["protocol"] for out in closed["outbounds"]} == {"dns", "blackhole", "freedom"}
    assert not zapret2.active(closed)
    dns_rule, block, default = closed["routing"]["rules"]
    assert dns_rule["outboundTag"] == "dns-out"
    assert block["domain"] == cfg.zapret2.domains and block["outboundTag"] == "block"
    assert default["outboundTag"] == zapret2.DIRECT
    active = zapret2.standalone_route(closed, enabled=True)
    assert active["routing"]["rules"][1] == {
        **block, "network": "tcp", "port": "443", "outboundTag": zapret2.OUT,
    }
    assert active["routing"]["rules"][2:] == [block, default]
    assert zapret2.standalone_route(active, enabled=False) == closed
    assert "--lua-desync=hostfakesplit:midhost=midsld:tcp_md5" in zapret2.arguments(cfg)


def test_standalone_cannot_silently_fall_through_to_engine(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[capture]\nfail_mode="open"\n[zapret2]\nmode="standalone"\n'
                    'engine="auto"\n', encoding="utf-8")
    with pytest.raises(config.ConfigError, match="runtime rejected policy"):
        config.load(path)


def test_standalone_config_loads_with_no_probe_urls(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[zapret2]\nmode="standalone"\nstrategy="hostfakesplit_md5"\n',
                    encoding="utf-8")
    cfg, _ = config.load(path)
    assert cfg.zapret2.selected_enabled and not cfg.zapret2.probe_enabled
    assert cfg.zapret2.probe_urls == []


def test_fresh_assembly_skips_subscriptions(tmp_path, monkeypatch):
    cfg = _standalone()
    cfg.subscriptions = [config.Subscription(name="offline", url="https://example.com/sub")]
    cfg.network.ipv6 = "block"
    paths = Paths(tmp_path)
    monkeypatch.setattr(engine, "containers_tun", lambda cfg: False)
    inventory = engine.collect(cfg, paths, mark=None, logger=Mock())
    assembly = engine.assemble(cfg, paths, inventory, mark=None, logger=Mock(),
                               xray_bin=None, check=False)
    assert not inventory.nodes and not assembly.selection.members
    assert zapret2.standalone(assembly.result.config) and not assembly.singbox


def test_standalone_waits_before_open_and_closes_after_worker_failure():
    cfg = _standalone()
    applied = builder.build(cfg, builder.Selection(), hosts={}, ipv6=False).config
    runtime = Mock()
    controller = zapret2.Controller(Mock(), runtime)
    controller.probe = Mock(side_effect=AssertionError("standalone must not run HTTP probes"))

    def apply(target, before):
        nonlocal applied
        assert before == applied
        if zapret2.active(target):
            runtime.gate.assert_called_with(zapret2.STANDALONE_LEASE)
        else:
            runtime.gate.assert_called_with()
            runtime.stop.assert_called_once()
        applied = target
        return True

    runtime.alive.return_value = False
    controller.step_standalone(cfg, applied, 0, apply, allowed=True)
    assert controller.view["state"] == "preparing" and not zapret2.active(applied)
    runtime.alive.return_value = True
    controller.step_standalone(cfg, applied, 1, apply, allowed=True)
    assert controller.view["without_vpn"] is True and zapret2.active(applied)
    runtime.alive.return_value = False
    controller.step_standalone(cfg, applied, 2, apply, allowed=True)
    assert not zapret2.active(applied)
    assert controller.view == {"state": "blocked", "reason": "worker_down", "gate_closed": True}
    runtime.start.assert_called_once()


def test_standalone_reports_waiting_for_vpn_without_opening_the_direct_route():
    cfg = _standalone()
    applied = builder.build(cfg, builder.Selection(), hosts={}, ipv6=False).config
    runtime, apply = Mock(), Mock()
    controller = zapret2.Controller(Mock(), runtime)

    controller.step_standalone(cfg, applied, 0, apply, allowed=False, blocked_reason="vpn_stopping")

    assert controller.view == {"state": "preparing", "reason": "vpn_stopping", "gate_closed": True}
    runtime.start.assert_not_called()
    apply.assert_not_called()
