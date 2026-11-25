import json

import pytest

from xgw.desync.client import analyze


def sample(at, state, **fields):
    return {
        "at": at, "state": state, "observed_at": at - 1, "fresh": True,
        "policy_matched": True, "mode": "selective", "engine_mode": "off",
        "config_key": "private-revision", "reason": "youtube_cdn_probe_failed",
    } | fields


def summarize(tmp_path, *rows):
    path = tmp_path / "watch.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    return analyze(path)["selected_recovery"]


def test_monitor_counts_sampled_returns_once_and_aggregates_allowlisted_fields(tmp_path):
    stats = summarize(
        tmp_path, sample(100, "fallback"), sample(120, "active"),
        sample(140, "active", observed_at=119),
        sample(160, "fallback", mode="standalone", reason="private-reason"),
        sample(190, "active", mode="standalone"),
    )
    assert stats == {
        "comparable_sample_pairs": 2, "observed_returns_to_active": 2,
        "by_fallback_reason": {"youtube_cdn_probe_failed": 1, "unconfirmed": 1},
        "by_selected_mode": {"selective": 1, "standalone": 1},
        "max_sampling_window_seconds": 30,
    }
    assert "private" not in json.dumps(stats)


@pytest.mark.parametrize("changes", [
    {"at": 701}, {"at": 90}, {"at": 100}, {"observed_at": 99}, {"observed_at": 100},
    {"observed_at": 121}, {"observed_at": None}, {"observed_at": "119"},
    {"observed_at": True}, {"observed_at": float("nan")}, {"observed_at": float("inf")},
    {"mode": "standalone"}, {"engine_mode": "auto"}, {"engine_mode": None},
    {"config_key": "changed"}, {"fresh": False}, {"policy_matched": False},
    {"error": "api_unavailable"}, {"state": "blocked"}, {"state": "preparing"},
])
def test_monitor_requires_a_new_matching_daemon_status_in_a_bounded_window(tmp_path, changes):
    stats = summarize(tmp_path, sample(100, "fallback"), sample(120, "active") | changes)
    assert stats["observed_returns_to_active"] == 0
    assert stats["max_sampling_window_seconds"] is None


@pytest.mark.parametrize("middle", [
    {"at": 120, "error": "api_unavailable"}, sample(120, "blocked"), sample(120, "preparing"),
    sample(120, "off", mode="off"), sample(120, "fallback", fresh=False),
])
def test_monitor_does_not_infer_a_transition_across_an_intervening_sample(tmp_path, middle):
    stats = summarize(tmp_path, sample(100, "fallback"), middle, sample(140, "active"))
    assert stats["observed_returns_to_active"] == 0


def test_monitor_keeps_legacy_or_rewound_samples_out_of_recovery_count(tmp_path):
    old_sample = sample(100, "fallback")
    del old_sample["observed_at"]
    stats = summarize(
        tmp_path, old_sample, sample(120, "active"), sample(100, "fallback"),
        sample(120, "fallback"), sample(140, "active"),
    )
    assert stats["comparable_sample_pairs"] == stats["observed_returns_to_active"] == 0
