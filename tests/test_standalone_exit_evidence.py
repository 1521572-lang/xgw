import json

from docs.helpers import standalone_exit_evidence as exit_evidence
from xgw import zapret2
from xgw.desync import worker


def test_off_snapshot_separates_worker_stop_from_pending_vpn_config():
    status = {"daemon": True, "updated": 95, "zapret2": {"state": "blocked", "reason": "stop_failed"},
              "zapret2_reservation": {"unit": worker.SELECTED_UNIT, "generation": 22}}
    config = {"outbounds": [{"tag": zapret2.DIRECT, "settings": {"secret": "private"}}]}
    summary = exit_evidence.project(status, config, now=100, api_dirty=False)
    assert summary == {"daemon_snapshot_fresh": True, "selected_state": "blocked",
                       "selected_reason": "stop_failed", "reservation": "selected",
                       "standalone_config_applied": True, "api_dirty": False}

    status["zapret2"] = {"state": "preparing", "reason": "vpn_requested"}
    status["zapret2_reservation"] = None
    summary = exit_evidence.project(status, config, now=100, api_dirty=True)
    assert summary["selected_reason"] == "vpn_requested" and summary["reservation"] == "none"
    assert summary["standalone_config_applied"] is True and summary["api_dirty"] is True
    assert "private" not in json.dumps(summary)


def test_off_snapshot_handles_stale_legacy_and_unrecognized_fields():
    status = {"daemon": True, "updated": 1, "zapret2": {"state": "private", "reason": "private"}}
    summary = exit_evidence.project(status, {"outbounds": None}, now=100, api_dirty=False)
    assert summary == {"daemon_snapshot_fresh": False, "selected_state": "unknown",
                       "selected_reason": "unknown", "reservation": "unknown",
                       "standalone_config_applied": None, "api_dirty": False}
