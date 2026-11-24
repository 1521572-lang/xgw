"""Accounting evidence distinguishes archived status from observed new charges."""

import json

import pytest

from xgw.desync.monitor_budget import budget_summary
from xgw.zapret2 import PROBE_CHARGE, PROBE_DAY_SECONDS

DAY = PROBE_DAY_SECONDS
CHARGE = PROBE_CHARGE


def sample(at, units, *, limit_units=4, **extras):
    spent, limit = units * CHARGE, limit_units * CHARGE
    budget = {"spent_bytes": spent, "limit_bytes": limit,
              "remaining_bytes": max(0, limit - spent), "resets_at": (at // DAY + 1) * DAY}
    return {"at": at, "mode": "off", "engine_mode": "off", "fresh": True, "policy_matched": True,
            "config_key": "private-revision", "budget": budget} | extras


def test_monitor_budget_confirms_rollover_and_separate_daily_charges():
    result = budget_summary([
        sample(DAY - 60, 2), sample(DAY - 30, 3), sample(DAY + 30, 0),
        sample(DAY + 60, 1), sample(DAY + 90, 1),
    ])
    assert result == {
        "trusted_samples": 5, "unavailable_samples": 0, "confirmed_utc_rollovers": 1,
        "days": [
            {"utc_day": "1970-01-01", "samples": 2, "max_spent_bytes": 3 * CHARGE,
             "min_remaining_bytes": CHARGE, "over_limit_samples": 0, "comparable_intervals": 1,
             "charged_intervals": 1, "observed_charge_bytes": CHARGE},
            {"utc_day": "1970-01-02", "samples": 3, "max_spent_bytes": CHARGE,
             "min_remaining_bytes": 3 * CHARGE, "over_limit_samples": 0, "comparable_intervals": 2,
             "charged_intervals": 1, "observed_charge_bytes": CHARGE},
        ],
    }
    assert "private" not in json.dumps(result)


def test_monitor_budget_distinguishes_zero_charge_from_unavailable_snapshots():
    rows = [sample(30, 1), sample(60, 1), {"at": 90, "budget": {"resets_at": DAY}}]
    result = budget_summary(rows)
    assert result["days"][0]["comparable_intervals"] == 1
    assert result["days"][0]["observed_charge_bytes"] == 0
    assert result["unavailable_samples"] == 1
    assert budget_summary(rows[2:]) == {
        "trusted_samples": 0, "unavailable_samples": 1,
        "confirmed_utc_rollovers": 0, "days": [],
    }


@pytest.mark.parametrize("changes", [
    {"spent_bytes": False}, {"remaining_bytes": 0}, {"limit_bytes": 0},
    {"resets_at": 2 * DAY}, {"resets_at": DAY + 1}, {"day": True}, {"day": 1},
    {"spent_bytes": "0"}, {"limit_bytes": 1 << 31},
])
def test_monitor_budget_rejects_inconsistent_or_non_integer_counters(changes):
    row = sample(30, 1)
    row["budget"].update(changes)
    result = budget_summary([row])
    assert result["unavailable_samples"] == 1
    assert result["days"] == []


@pytest.mark.parametrize("first,last", [
    (sample(30, 0), sample(631, 1)),
    (sample(30, 0), sample(60, 1, fresh=False)),
    (sample(30, 0), sample(60, 1, policy_matched=False)),
    (sample(30, 0), sample(60, 1, error="api_unavailable")),
    (sample(30, 0), sample(60, 1, config_key="private-new-revision")),
    (sample(30, 0), sample(60, 1, mode="selective")),
    (sample(30, 0), sample(60, 1, engine_mode="auto")),
    (sample(30, 0), sample(60, 1, limit_units=8)),
    (sample(DAY - 30, 2), sample(DAY + 30, 0, mode="standalone")),
    (sample(DAY - 601, 2), sample(DAY + 30, 0)),
])
def test_monitor_budget_does_not_bridge_gaps_or_policy_and_limit_changes(first, last):
    result = budget_summary([first, last])
    assert result["confirmed_utc_rollovers"] == 0
    assert all(day["comparable_intervals"] == 0 for day in result["days"])
    assert all(day["observed_charge_bytes"] == 0 for day in result["days"])


def test_monitor_budget_does_not_bridge_errors_or_recount_clock_and_counter_backtracks():
    rows = [
        sample(30, 0), sample(60, 1),
        sample(45, 0), sample(60, 0), sample(90, 1),
        {"at": 120, "error": "api_unavailable"}, sample(150, 2),
        sample(180, 1), sample(210, 2), sample(240, 3),
    ]
    result = budget_summary(rows)
    assert result["unavailable_samples"] == 3
    assert result["days"][0]["comparable_intervals"] == 2
    assert result["days"][0]["observed_charge_bytes"] == 2 * CHARGE


def test_monitor_budget_keeps_over_limit_observation_after_limit_reduction():
    result = budget_summary([sample(30, 3), sample(60, 3, limit_units=2),
                             sample(90, 3, limit_units=2)])
    assert result["days"][0] == {
        "utc_day": "1970-01-01", "samples": 3, "max_spent_bytes": 3 * CHARGE,
        "min_remaining_bytes": 0, "over_limit_samples": 2, "comparable_intervals": 1,
        "charged_intervals": 0, "observed_charge_bytes": 0,
    }
