import json

import pytest

from docs.helpers.desync_playback_observation import observation
from xgw.desync import cache

VIDEO = "8plwv25NYRo"
T0 = 1_700_000_000


def trial(index, ip="a", prefix="b", host="c", outcome="pass", **overrides):
    return {
        "measurement_version": cache.MEASUREMENT_VERSION,
        "context_id": ip * 64, "prefix_context_id": prefix * 64, "host_context_id": host * 64,
        "recording_id": f"{index:064x}", "started": T0 + index * 200,
        "finished": T0 + index * 200 + 130, "outcome": outcome, "candidate": "static",
        "round": f"r{index}", **overrides,
    }


def test_lookup_expires_at_older_pass_and_rejects_changed_history_or_clock():
    first, second = trial(0), trial(1)
    now = second["finished"] + 1
    state = cache.build([first, second], "revision", now)

    assert cache.lookup(state, "revision", "a" * 64, now)["state"] == "hit"
    assert cache.lookup(state, "revision", "b" * 64, now)["state"] == "miss"
    assert cache.lookup(state, "other", "a" * 64, now)["state"] == "stale_history"
    assert cache.lookup(state, "revision", "a" * 64, now - 1)["state"] == "stale_clock"
    expired = cache.lookup(state, "revision", "a" * 64, first["finished"] + cache.TTL)
    assert expired == {"state": "miss", "candidates": [], "apply": False}
    state["snapshot"]["exact"]["a" * 64]["static"]["expires"] += 1
    assert cache.lookup(state, "revision", "a" * 64, now)["state"] == "invalid_snapshot"


def test_rebuild_uses_only_exact_ip_and_latest_independent_wins():
    first, second = trial(0), trial(1)
    failure = trial(2, outcome="playback_failed")
    assert cache.build([first, second, failure], "rev", T0 + 600)["snapshot"]["exact"] == {}
    assert cache.build([first, second | {"round": first["round"]}], "rev",
                       T0 + 600)["snapshot"]["exact"] == {}
    assert cache.build([first, second | {"started": T0 + 100}], "rev",
                       T0 + 600)["snapshot"]["exact"] == {}
    assert cache.build([first, trial(1, ip="d")], "rev", T0 + 600)["snapshot"]["exact"] == {}
    assert cache.build([first, second], "rev", T0 + 200)["snapshot"]["exact"] == {}


def test_held_out_scopes_measure_false_hits_and_do_not_look_ahead():
    a, b = trial(0), trial(1)
    fail_same_prefix = trial(2, ip="d", outcome="playback_failed")
    pass_other_prefix = trial(3, ip="e", prefix="f")
    unrelated = trial(4, ip="f", prefix="e", host="d")
    report = cache.compare([pass_other_prefix, a, unrelated, fail_same_prefix, b])

    assert report["scopes"]["exact"]["correct_hit"] == 0
    assert report["scopes"]["prefix_other_ip"]["false_hit"] == 1
    assert report["scopes"]["host_other_prefix"]["false_hit"] == 0
    assert report["scopes"]["host_other_ip"]["with_history"] == 2
    assert report["state"] == "measured" and report["apply"] is False
    assert cache.compare([a, b])["state"] == "inconclusive"


def test_rejects_a_duplicate_recording():
    with pytest.raises(ValueError, match="invalid_observation"):
        cache.validate_rows([trial(1), trial(2, recording_id=trial(1)["recording_id"])])


def test_history_excludes_pre_fix_measurements():
    old = trial(1)
    del old["measurement_version"]
    fresh = trial(2)
    assert cache.validate_rows([old, fresh]) == [fresh]


@pytest.fixture
def capture():
    metadata = {
        "hostname": "r1.googlevideo.com", "address": "8.8.8.8",
        "network": "wan-a", "protocol": "h2", "client": "chrome",
        "client_sha256": "a" * 64, "policy_sha256": "b" * 64,
        "candidate": "fake-clone-md5", "round": "run-1", "video_id": VIDEO,
        "verified_direct_single_endpoint": True,
    }
    rows = [{
        "t_s": t, "unix": T0 + t, "has_video": True, "video_id": VIDEO,
        "document_id": 1, "media_id": 1, "position": t, "playback_rate": 1,
        "ready_state": 4, "buffer_seconds": 80, "event_overflow": 0, "events": [],
        "error_code": None, "height": 720,
        **dict.fromkeys(("paused", "seeking", "hidden", "ended", "ad"), False),
    } for t in range(131)]
    return rows, metadata


def test_chrome_import_keeps_real_context_private_and_observes_quality_fall(capture):
    rows, metadata = capture
    raw = json.dumps({"rows": rows}).encode()
    row = observation(raw, metadata)
    assert row["outcome"] == "pass"
    assert "googlevideo" not in str(row) and "8.8.8.8" not in str(row)
    same_prefix = observation(raw, metadata | {"address": "8.8.8.9"})
    assert row["host_context_id"] == same_prefix["host_context_id"]
    assert row["prefix_context_id"] == same_prefix["prefix_context_id"]
    assert row["context_id"] != same_prefix["context_id"]
    other_family = observation(raw, metadata | {"address": "2001:4860:4860::8888"})
    assert row["host_context_id"] != other_family["host_context_id"]
    for sample in rows[80:]:
        sample["height"] = 480
    diagnostics = {}
    assert observation(json.dumps({"rows": rows}).encode(), metadata,
                       diagnostics=diagnostics)["outcome"] == "playback_failed"
    assert diagnostics["reason"] == "low_target_height_ratio"
    assert 0.60 < diagnostics["target_height_ratio"] < 0.65
    assert "googlevideo" not in str(diagnostics) and "8.8.8.8" not in str(diagnostics)
    with pytest.raises(ValueError, match="evidence_required"):
        observation(raw, metadata | {"verified_direct_single_endpoint": False})


def test_sample_jitter_and_a_short_ready_state_change_do_not_reduce_net_playback(capture):
    rows, metadata = capture
    for row in rows:
        if row["t_s"] % 2:
            row["position"] -= 0.2
    rows[51].update(position=rows[50]["position"], ready_state=2)
    rows[52]["position"] = 51.5
    assert observation(json.dumps({"rows": rows}).encode(), metadata)["outcome"] == "pass"


def test_confirmed_starvation_fails_and_coarse_sampling_remains_unavailable(capture):
    rows, metadata = capture
    for row in rows[90:]:
        row.update(position=89, buffer_seconds=0, ready_state=2)
    assert observation(json.dumps({"rows": rows}).encode(), metadata)[
        "outcome"] == "playback_failed"
    with pytest.raises(ValueError, match="missing_trial_coverage"):
        observation(json.dumps({"rows": rows[::15]}).encode(), metadata)
