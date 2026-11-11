"""Действия окна через настоящий HTTP API, без запуска обработчика или изменения сети."""

import copy
import json
import time
from types import SimpleNamespace

import pytest
import test_panel as panel_tests
from test_panel import _snapshot

from xgw import config, managed, zapret2
from xgw.watch import status, zapret2_control

rig, user = panel_tests.rig, panel_tests.user


@pytest.fixture()
def ready(rig, monkeypatch):
    directory = rig.paths.root / "zapret2"
    directory.mkdir()
    for name in ("nfqws2", "zapret-lib.lua", "zapret-antidpi.lua"):
        (directory / name).write_text("fixture")
    with rig.config_path.open("a") as stream:
        stream.write(f'\n[zapret2]\nbinary="{directory}/nfqws2"\nlua_dir="{directory}"\n'
                     'probe_urls=["https://youtube.com/watch?v=PRIVATE_SENTINEL",'
                     '"https://cdn.googlevideo.com/video?token=PRIVATE_SENTINEL"]\n')
    rig.panel.cfg = config.load(rig.config_path)[0]
    monkeypatch.setattr(rig.panel, "_capture", lambda: SimpleNamespace(
        describe=lambda **_: {"mode": "on", "lan_if": ""}))

    def publish(state="off", **values):
        cfg = config.load(rig.config_path)[0]
        snapshot = _snapshot()
        snapshot["zapret2"] = {"config_key": zapret2.config_key(cfg), "state": state,
                               "reason": "off", **values}
        status.write_status(rig.paths, snapshot)
        return snapshot

    publish()
    return publish


def test_modes_are_persisted_but_pending_is_not_active(rig, user, ready):
    view = user.state()["zapret2"]
    assert view["state"] == "off" and view["can_edit"] and not view["blockers"]["selective"]
    assert "PRIVATE_SENTINEL" not in json.dumps(view)
    before = rig.config_path.read_bytes()
    assert user.act("zapret2/mode", {"mode": "selective", "expected": view["config_key"]})["ok"]
    assert rig.config_path.read_bytes() == before
    assert config.load(rig.config_path)[0].zapret2.mode == "selective"
    assert rig.daemon.poke.is_set()
    assert user.state()["zapret2"]["state"] == "pending"
    ready("active", reason="probes_ok", valid_until=time.time() + 120)
    assert user.state()["zapret2"]["state"] == "active"
    ready("active", reason="probes_ok", valid_until=time.time() - 1)
    assert user.state()["zapret2"]["state"] == "unknown"
    assert user.act("zapret2/mode", {"mode": "off"})["ok"]
    assert user.state()["zapret2"]["state"] == "pending"
    ready()
    assert user.state()["zapret2"]["state"] == "off"
    assert not rig.system_calls and not rig.kernel.calls


def test_settings_are_private_validated_and_do_not_enable(rig, user, ready):
    key = user.state()["zapret2"]["config_key"]
    settings = {"strategy": "multidisorder", "probe_urls": []}
    assert user.act("zapret2/settings", {"expected": key, "settings": settings})["ok"]
    cfg = config.load(rig.config_path)[0]
    assert cfg.zapret2.mode == "off" and cfg.zapret2.strategy == "multidisorder"
    ready()
    key = user.state()["zapret2"]["config_key"]
    assert not user.act("zapret2/mode", {"expected": key, "mode": "selective"})["ok"]
    before = rig.store_path.read_bytes()
    for settings in ({"binary": "/bin/sh"}, {"mode": "selective"}, {"domains": []},
                     {"probe_urls": ["https://outside.test/PRIVATE_SENTINEL"]},
                     {"strategy": []}, {"probe_urls": "https://youtube.com/"}):
        result = user.act("zapret2/settings", {"expected": key, "settings": settings})
        assert not result["ok"] and "PRIVATE_SENTINEL" not in json.dumps(result)
        assert rig.store_path.read_bytes() == before
    assert not user.act("zapret2/settings", {"expected": "old", "settings": {}})["ok"]
    assert rig.store_path.stat().st_mode & 0o077 == 0


def test_capture_pool_stale_and_bad_config_block_activation(rig, user, ready):
    snapshot = ready()
    cfg = rig.panel.cfg
    for capture, change in (({"mode": "off"}, {}), ({"mode": "on"}, {"updated": 1})):
        view = zapret2_control.card(cfg, {**snapshot, **change}, capture, True)
        assert view["blockers"]["selective"] and view["blockers"]["compare"]
    cfg = copy.deepcopy(cfg)
    cfg.free_pool.mode = "on"
    assert zapret2_control.card(cfg, snapshot, {"mode": "on"}, True)["blockers"]["selective"]
    cfg.zapret2.probe_urls = ["https://[bad"]
    assert zapret2_control.prerequisites(cfg, "selective")
    snapshot["updated"] = 1
    status.write_status(rig.paths, snapshot)
    key = user.state()["zapret2"]["config_key"]
    assert not user.act("zapret2/mode", {"mode": "selective", "expected": key})["ok"]
    assert user.act("zapret2/mode", {"mode": "off"})["ok"]


def test_comparison_and_failed_return_are_distinct(rig, user, ready):
    view = user.state()["zapret2"]
    assert user.act("zapret2/mode", {"mode": "compare", "expected": view["config_key"]})["ok"]
    ready("compared", reason="comparison_done", probes=[
        {"probe": 1, "path": "zapret2", "http": 302, "ok": False, "bytes": 0,
         "url": "PRIVATE_SENTINEL"}])
    view = user.state()["zapret2"]
    assert view["state"] == "compared" and not view["probes"][0]["ok"]
    assert "PRIVATE_SENTINEL" not in json.dumps(view)
    assert view["blockers"]["compare"] and not view["can_edit"]
    ready("blocked", reason="comparison_cleanup_failed")
    assert user.state()["zapret2"]["state"] == "blocked"


def test_selective_evidence_and_expiry_are_private(rig, user, ready):
    managed.set_zapret2(rig.store_path, {"probe_urls": [
        "https://youtube.com/watch?v=PRIVATE", "https://cdn.googlevideo.com/v?expire=1&token=PRIVATE"]})
    rig.panel._wake()
    ready("fallback", reason="probe_failed", probes=[
        {"probe": 1, "path": "zapret2", "http": 200, "bytes": 25, "ok": False,
         "verdict": "short_body", "checked_at": 123, "error": "PRIVATE"},
        {"probe": 2, "path": "zapret2", "ok": False, "verdict": "not_run"}])
    view = user.state()["zapret2"]
    assert view["probe_expiry"] == [{"probe": 1, "expires_at": None}, {"probe": 2, "expires_at": 1}]
    assert "16 КиБ" in view["probes"][0]["detail"]
    assert view["probes"][1]["verdict"] == "not_run"
    assert "PRIVATE" not in json.dumps(view)


def test_managed_override_survives_unrelated_writes_and_corruption_disables(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[zapret2]\nmode="selective"\n')
    store = managed.path_for(path)
    managed.set_zapret2(store, {"mode": "off", "strategy": "multidisorder"})
    managed.set_sticky(store, False)
    cfg = config.load(path)[0]
    assert cfg.zapret2.mode == "off" and cfg.zapret2.strategy == "multidisorder"
    store.write_text('{"zapret2":{"domains":42}}')
    assert config.load(path)[0].zapret2.mode == "off"
