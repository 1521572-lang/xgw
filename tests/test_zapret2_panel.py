"""Batch-1 status contract; no worker, Linux command, socket, or Qt is started."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from xgw.config import Config
from xgw.desync import schema
from xgw.watch.zapret2_control import card

NOW = 1000


def fixture(*, mode="off", engine="auto", state="active", reason="", **extra):
    cfg = Config()
    cfg.zapret2.mode, cfg.zapret2.engine = mode, engine
    cfg.desync = schema.migrate(vars(cfg.zapret2))
    raw = {"state": state, "reason": reason, "profile": "hostfakesplit-md5", "queue": 200,
           **extra}
    snapshot = {"updated": NOW, "daemon": True, "capture": {"loaded": True, "nfqws2": raw},
                "zapret2": raw if mode != "off" else {"state": "off"},
                "zapret2_policy_key": schema.fingerprint(cfg.desync)}
    return cfg, snapshot


def view(cfg, snapshot, **kwargs):
    return card(cfg, snapshot, {"mode": "on"}, True, now=NOW, **kwargs)


def test_youtube_transport_is_never_reported_as_playback():
    cfg, snap = fixture(mode="selective", engine="off", reason="youtube_transport_ok",
                        valid_until=NOW + 60)
    cfg.zapret2.youtube_transport_probe = True
    cfg.desync = schema.migrate(vars(cfg.zapret2))
    snap["zapret2_policy_key"] = schema.fingerprint(cfg.desync)
    result = view(cfg, snap)
    assert result["evidence"]["transport"] == "https_reachable"
    assert result["evidence"]["playback"] == "not_tested"
    snap["zapret2"]["valid_until"] = NOW
    assert view(cfg, snap)["evidence"]["transport"] == "unknown"


@pytest.mark.parametrize(("state", "reason", "expected"), [
    ("active", "", "active"), ("off", "not_found", "absent"),
    ("fallback", "worker_down", "error"), ("fallback", "queue_busy", "error"),
    ("off", "inactive", "off"), ("preparing", "", "preparing"),
])
def test_engine_states(state, reason, expected):
    cfg, snap = fixture(state=state, reason=reason)
    result = view(cfg, snap)
    assert result["state"] == expected
    assert result["source"] == "engine"
    assert "восстановлен" not in result["title"].lower()
    assert result["state"] != "fallback"
    assert result["without_vpn"] is False
    assert result["evidence"]["playback"] == "not_tested"
    assert not result["can_off"] and not result["can_edit"]
    assert all(value is None for value in result["counters"].values())


def test_off_and_unconfirmed_stop():
    cfg, snap = fixture(engine="off", state="off")
    assert view(cfg, snap)["state"] == "off"
    snap["capture"]["nfqws2"]["state"] = "active"
    assert view(cfg, snap)["state"] == "pending"


@pytest.mark.parametrize("stamp", [None, True, NOW - 91, NOW + 1, float("nan")])
def test_stale_or_invalid_snapshot_clears_active_profile(stamp):
    cfg, snap = fixture()
    snap["updated"] = stamp
    result = view(cfg, snap)
    assert result["state"] == "unknown" and not result["fresh"]
    assert result["strategy"] is None and result["worker"]["profile"] is None


def test_changed_policy_and_legacy_snapshot():
    cfg, snap = fixture()
    snap["zapret2_policy_key"] = "previous"
    assert view(cfg, snap)["state"] == "pending"
    del snap["zapret2_policy_key"]
    assert view(cfg, snap)["reason"] == "legacy_snapshot"
    assert card(cfg, snap, {"mode": "on"}, False, now=NOW)["fresh"] is False


def test_capture_must_be_confirmed():
    cfg, snap = fixture()
    snap["capture"]["loaded"] = False
    assert view(cfg, snap)["reason"] == "capture_unconfirmed"


def test_selected_controller_has_precedence_and_checks_expiry():
    cfg, snap = fixture(mode="selective", valid_until=NOW + 60)
    assert view(cfg, snap)["source"] == "selected"
    assert view(cfg, snap)["state"] == "active"
    snap["zapret2"]["valid_until"] = NOW
    assert view(cfg, snap)["reason"] == "expired"


def test_selected_fallback_requires_gate_and_never_asserts_vpn_health():
    cfg, snap = fixture(mode="selective", state="fallback", gate_closed=True)
    assert view(cfg, snap)["state"] == "fallback"
    assert "проверяется отдельно" in view(cfg, snap)["detail"]
    snap["zapret2"]["gate_closed"] = False
    assert view(cfg, snap)["state"] == "blocked"


def test_fallback_evidence_is_policy_bound_and_keeps_the_original_probe_time():
    cfg, snap = fixture(mode="selective", state="fallback", gate_closed=True,
                        vpn_control="not_run", vpn_control_reason="no_vpn_probe_port",
                        vpn_control_at=NOW - 120)
    result = view(cfg, snap)["evidence"]
    assert result["vpn_control_reason"] == "no_vpn_probe_port"
    assert result["vpn_control_at"] == NOW - 120
    snap["zapret2"].update(vpn_control_reason="secret-token")
    assert view(cfg, snap)["evidence"]["vpn_control_reason"] is None
    snap["zapret2"].update(vpn_control="pass", vpn_control_reason="ok")
    assert view(cfg, snap)["evidence"]["vpn_control"] == "pass"
    snap["zapret2_policy_key"] = "previous"
    assert view(cfg, snap)["evidence"]["vpn_control"] == "not_run"
    assert view(cfg, snap)["evidence"]["vpn_control_at"] is None


def test_private_and_untrusted_fields_are_not_published():
    cfg, snap = fixture(reason="secret-in-error", profile="secret-profile", queue="secret")
    snap["capture"]["nfqws2"]["probes"] = [{"url": "secret-token"}]
    cfg.desync["selected"]["probe_urls"] = ["https://youtube.com/?secret-token"]
    snap["zapret2_policy_key"] = schema.fingerprint(cfg.desync)
    result = view(cfg, snap)
    assert "secret" not in json.dumps(result)
    assert result["worker"]["profile"] is None


def test_panel_state_wires_card_to_real_response(tmp_path, monkeypatch):
    from xgw.watch import panel

    cfg, snap = fixture(state="fallback", reason="worker_down")
    monkeypatch.setattr(panel.time, "time", lambda: NOW)
    p = Mock()
    p.cfg, p.paths.cache_dir = cfg, tmp_path
    p._core.return_value = snap, True, [], []
    p._capture.return_value.describe.return_value = {"mode": "on", "lan_if": ""}
    p._servers.return_value = [], []
    p._devices.return_value = []
    p._db.return_value = []
    p.daemon.speed_one_pending.return_value = []
    for field in ("refresh_pending", "scan_pending", "speed_pending", "cores_pending"):
        setattr(p.daemon, field, False)
    for method in ("_power", "_pin", "_cores_card", "_netcheck_card", "_tailscale_card",
                   "_phones_card"):
        getattr(p, method).return_value = {}
    p.recorder.state.return_value = {}
    result = panel.Panel.state(p)
    assert result["zapret2"]["state"] == "error"
    assert result["zapret2"]["source"] == "engine"
    json.dumps(result)  # response must be serializable, not a mock or private object


def test_overview_renders_new_states_and_expired_daemon():
    file = Path(__file__).parents[1] / "vpn_ui" / "xgw" / "overview.py"
    spec = importlib.util.spec_from_file_location("batch1_overview", file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        for phase, label in (("error", "Ошибка обработчика"), ("absent", "Не установлен"),
                             ("fallback", "Прямой путь отключён")):
            assert module.zapret_status({"zapret2": {"state": phase}}, False).text == label
        result = module.zapret_status({"zapret2": {"state": "active", "fresh": False}}, False)
        assert result.tone == "warn" and result.text == "Не подтверждён"
    finally:
        sys.modules.pop(spec.name, None)
