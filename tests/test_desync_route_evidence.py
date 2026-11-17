import pytest

from xgw.desync import route_evidence
from xgw.generator import singbox


def snapshot(ns, zapret, xray, sb):
    applied = {"outbounds": [
        {"tag": "xgw-zapret2", "protocol": "freedom"},
        {"tag": "proxy-x", "protocol": "vless"},
        {"tag": "proxy-sb", **singbox.bridge_outbound(12345, "d", "secret")},
        {"tag": "proxy-idle", "protocol": "vless"},
        {"tag": "probe-foo", "protocol": "vless"},
    ]}
    totals = {"stats": {"outbound": {
        "xgw-zapret2": {"downlink": zapret, "uplink": 7},
        "proxy-x": {"downlink": xray, "uplink": 11},
        "proxy-sb": {"downlink": sb, "uplink": 13},
        "probe-foo": {"downlink": 99999999, "uplink": 99999999},
    }}}
    return {"monotonic_ns": ns, "xray_epoch": "same", "config_sha256": "same",
            "client_zapret2_rule": True, "tags": route_evidence.counters(applied, totals)}


def test_delta_separates_direct_and_both_vpn_cores_and_does_not_assume_missing_zero():
    before = snapshot(1_000_000_000, 100, 200, 300)
    after = snapshot(3_000_000_000, 1100, 210, 900)
    result = route_evidence.deltas(before, after)
    assert result["seconds"] == 2
    groups = result["groups"]
    assert [groups[group]["downlink"] for group in route_evidence.GROUPS] == [1000, 10, 600]
    assert groups["xray"]["tags_with_unknown_counters"] == 1
    for snap in (before, after):
        del snap["tags"]["proxy-sb"]
    groups = route_evidence.deltas(before, after)["groups"]
    assert groups["sing-box"]["downlink"] is None
    assert "secret" not in str(before)


def test_rejects_restart_config_change_and_counter_reset():
    before = snapshot(1, 10, 10, 10)
    after = snapshot(2, 20, 20, 20)
    for modification in ({"xray_epoch": "new"}, {"config_sha256": "changed"}):
        with pytest.raises(ValueError, match="incomparable_snapshots"):
            route_evidence.deltas(before, after | modification)
    with pytest.raises(ValueError, match="counter_reset_or_invalid"):
        route_evidence.deltas(before, snapshot(2, 9, 20, 20))
