import pytest

from xgw import zapret2
from xgw.config import Config
from xgw.desync import cache, schema, tournament


def results(winners=()):
    rows = []
    for i, (round_id, candidate) in enumerate(tournament.SLOTS, 1):
        start = 1_700_000_000 + i * 280
        observation = {
            "context_id": "a" * 64, "prefix_context_id": "b" * 64, "host_context_id": "c" * 64,
            "recording_id": f"{i:064x}", "candidate": candidate, "round": round_id,
            "started": start, "finished": start + 150,
            "outcome": "pass" if candidate in winners else "playback_failed",
            "measurement_version": cache.MEASUREMENT_VERSION,
        }
        rows.append({"round": round_id, "candidate": candidate, "observation": observation,
                     "elapsed_seconds": 220})
    return rows


def test_matrix_adds_only_matching_geometry_to_existing_fakes():
    cfg = Config()
    cfg.zapret2.mode = "standalone"
    for old in ("fake_md5", "fake_seq"):
        cfg.zapret2.strategy = old
        before = zapret2.arguments(cfg)
        cfg.zapret2.strategy = old + "_split"
        after = zapret2.arguments(cfg)
        assert before[:-1] == after[:-1]
        assert before[-1] == "--lua-desync=multidisorder:pos=1,midsld"
        assert after[-1] == "--lua-desync=multisplit:pos=1,midsld"
        policy = schema.migrate(vars(cfg.zapret2))
        assert schema.project(policy)["strategy"] == cfg.zapret2.strategy
        with pytest.raises(schema.PolicyError, match="T09"):
            schema.project(policy, target="freepool")


def test_stops_on_cancel_and_budget_and_mirrors_the_window_order():
    assert tournament.SLOTS[6:] == tuple(("t09-2", name)
                                         for name in reversed(tournament.ORDER))
    rows = results()[:1]
    assert tournament.next_trial(rows, 500, False)["state"] == "budget"
    assert tournament.next_trial(rows, 600, True)["state"] == "cancelled"
    assert tournament.next_trial(rows, 600, False)["trial"]["candidate"] == "multidisorder"
    assert tournament.next_trial(results(), 3600, False)["state"] == "complete"


def test_replay_detects_a_hidden_winner_and_displays_true_saved_cost():
    rows = results(("multisplit", "fake_md5"))
    report = tournament.summarize(tournament.validate_ledger(rows))
    window = report["windows"]["t09-1"]
    assert window["full"]["attempts"] == 6
    assert window["pruned"]["attempts"] == 4
    assert window["full"]["seconds"] - window["pruned"]["seconds"] == 440
    assert window["missed_winners"] == ["fake_md5"]
    assert report["repeatable_winners"] == ["fake_md5", "multisplit"]
    assert report["apply"] is False


def test_failed_bases_fall_back_to_full_and_missing_or_changed_context_stays_unknown():
    rows = results(("fake_md5",))
    report = tournament.summarize(rows)
    assert report["windows"]["t09-1"]["pruned"] == report["windows"]["t09-1"]["full"]
    rows[2]["observation"]["context_id"] = "d" * 64
    rows[6]["observation"] = None
    report = tournament.summarize(rows)
    assert report["windows"]["t09-1"]["state"] == "mixed_context"
    assert report["windows"]["t09-2"]["state"] == "incomplete"
    assert report["repeatable_winners"] is None


def test_rejects_invalid_trial_order_duplicate_recording_and_overlap():
    rows = results()
    with pytest.raises(ValueError, match="unexpected_trial"):
        tournament.validate_ledger(rows[1:])
    rows[1]["observation"]["started"] = rows[0]["observation"]["finished"] - 1
    with pytest.raises(ValueError, match="overlapping_observations"):
        tournament.validate_ledger(rows)
    rows[1]["observation"]["recording_id"] = rows[0]["observation"]["recording_id"]
    with pytest.raises(ValueError, match="invalid_observation"):
        tournament.validate_ledger(rows)
