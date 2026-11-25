import json

import pytest

from xgw.desync.client import analyze


def sample(at, key, **fields):
    return {"at": at, "config_key": key, "mode": "off", "engine_mode": "off",
            "fresh": True, "policy_matched": True, "state": "off"} | fields


def pending(at, key, **fields):
    return sample(at, key, policy_matched=False, state="pending", reason="policy_changed") | fields


def run(tmp_path, *rows):
    path = tmp_path / "policy.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    return analyze(path)["policy_changes"]


def test_counts_applied_policy_changes_without_exposing_fingerprints(tmp_path):
    before, after = "private-before", "private-after"
    stats = run(
        tmp_path, sample(10, before),
        pending(20, after, mode="selective"), pending(30, after, mode="selective"),
        sample(40, after, mode="selective", state="active"),
        sample(50, after, mode="selective", state="fallback"),
        sample(60, "third", mode="selective"),
        sample(70, "fourth", mode="selective", engine_mode="auto"),
        sample(80, "fifth", mode="standalone", engine_mode="off"),
    )
    assert stats == {
        "confirmed_samples": 6, "observed_changes": 4,
        "by_policy": {"off/off → selective/off": 1, "selective/off → selective/off": 1,
                      "selective/off → selective/auto": 1, "selective/auto → standalone/off": 1},
        "by_kind": {"selected_changed": 1, "same_modes_new_revision": 1, "engine_changed": 1,
                    "selected_and_engine_changed": 1},
    }
    assert "private" not in json.dumps(stats)


def test_legacy_engine_setting_remains_unknown(tmp_path):
    stats = run(
        tmp_path, sample(10, "a", engine_mode=None), sample(20, "b", engine_mode=None),
        sample(30, "c", mode="standalone", engine_mode=None),
    )
    assert stats["by_policy"] == {"off/unknown → off/unknown": 1, "off/unknown → standalone/unknown": 1}
    assert stats["by_kind"] == {"selected_unchanged_engine_unknown": 1, "selected_changed": 1}


@pytest.mark.parametrize("middle", [
    {"at": 20, "error": "api_unavailable"}, sample(20, "a", fresh=False),
    sample(20, "a", reason="invalid_policy"), pending(20, "c"), pending(20, "b", reason="stopping"),
    pending(20, "b", engine_mode="auto"), pending(10, "b"), pending(9, "b"),
    pending(620, "b"),
])
def test_clears_policy_chain_on_gap_or_inconsistent_confirmation(tmp_path, middle):
    after = max(middle["at"] + 10, 30)
    stats = run(tmp_path, sample(10, "a"), middle, sample(after, "b"))
    assert stats["observed_changes"] == 0
    assert stats["by_policy"] == {}


def test_conflicting_pending_revisions_and_overlong_pending_interval_are_not_counted(tmp_path):
    stats = run(
        tmp_path, sample(10, "a"), pending(20, "b"), pending(30, "c"), sample(40, "c"),
        pending(400, "d"), pending(630, "d"), sample(660, "d"),
    )
    assert stats["observed_changes"] == 0
