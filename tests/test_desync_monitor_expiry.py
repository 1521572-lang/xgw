import json

import pytest

from xgw.desync.monitor_expiry import cdn_expiry_summary


def sample(at, **fields):
    return {
        "at": at, "observed_at": at, "mode": "selective", "engine_mode": "off",
        "config_key": "private-revision", "fresh": True, "policy_matched": True,
        "cdn_expires_at": 120, "state": "active", "reason": "youtube_transport_ok",
    } | fields


def test_monitor_cdn_expiry_waits_for_daemon_reaction_without_double_counting():
    expired = {"state": "fallback", "reason": "youtube_cdn_expired"}
    result = cdn_expiry_summary([
        sample(110),
        sample(120, observed_at=110),
        sample(125, observed_at=122),
        sample(130, observed_at=122, **expired),
        sample(135, observed_at=132, **expired),
        sample(140, observed_at=132, **expired),
    ])
    assert result == {
        "samples_with_deadline": 6,
        "observed_crossings": 1,
        "crossings_with_post_expiry_status": 1,
        "post_expiry_states": {"active": 1},
        "post_expiry_reasons": {"youtube_transport_ok": 1},
        "confirmed_expiry_reactions": {"fallback": 1},
    }


@pytest.mark.parametrize("first,last", [
    (sample(110), sample(130, cdn_expires_at=160)),
    (sample(110), sample(130, config_key="rotated")),
    (sample(110), sample(130, engine_mode="auto")),
    (sample(110), sample(130, mode="off")),
    (sample(110), sample(130, fresh=False)),
    (sample(110), sample(130, policy_matched=False)),
    (sample(110), sample(130, error="api_unavailable")),
    (sample(110), sample(711)),
    (sample(119), sample(100)),
])
def test_monitor_cdn_expiry_requires_bounded_matching_adjacent_samples(first, last):
    result = cdn_expiry_summary([first, last])
    assert result["observed_crossings"] == 0
    assert result["crossings_with_post_expiry_status"] == 0
    assert result["confirmed_expiry_reactions"] == {}


@pytest.mark.parametrize("observed", [None, "120", True, float("nan"), float("inf"), 119.9, 130.1])
def test_monitor_cdn_expiry_distinguishes_boundary_from_fresh_daemon_status(observed):
    result = cdn_expiry_summary([
        sample(110),
        sample(130, observed_at=observed, state="blocked", reason="youtube_cdn_expired"),
    ])
    assert result["observed_crossings"] == 1
    assert result["crossings_with_post_expiry_status"] == 0
    assert result["confirmed_expiry_reactions"] == {}


def test_monitor_cdn_expiry_stops_waiting_after_an_api_gap():
    result = cdn_expiry_summary([
        sample(110),
        sample(120, observed_at=110),
        {"at": 130, "error": "api_unavailable"},
        sample(140, state="blocked", reason="youtube_cdn_expired"),
    ])
    assert result["observed_crossings"] == 1
    assert result["crossings_with_post_expiry_status"] == 0
    assert result["confirmed_expiry_reactions"] == {}


def test_monitor_cdn_expiry_distinguishes_blocked_and_unknown_reactions():
    result = cdn_expiry_summary([
        sample(110),
        sample(120, state="private-state", reason="private-reason"),
        sample(130, state="blocked", reason="youtube_cdn_expired"),
    ])
    assert result["post_expiry_states"] == {"unknown": 1}
    assert result["post_expiry_reasons"] == {"unconfirmed": 1}
    assert result["confirmed_expiry_reactions"] == {"blocked": 1}
    assert "private" not in json.dumps(result)


def test_monitor_cdn_expiry_uses_high_water_mark_after_clock_rewind():
    result = cdn_expiry_summary([
        sample(110), sample(120), sample(110), sample(120), sample(130),
    ])
    assert result["samples_with_deadline"] == 3
    assert result["observed_crossings"] == 1


@pytest.mark.parametrize("deadline", [None, False, "120", 120.0, 0, 253402300800])
def test_monitor_cdn_expiry_ignores_legacy_or_invalid_deadline(deadline):
    result = cdn_expiry_summary([
        sample(110, cdn_expires_at=deadline), sample(130, cdn_expires_at=deadline),
    ])
    assert result["samples_with_deadline"] == 0
    assert result["observed_crossings"] == 0
