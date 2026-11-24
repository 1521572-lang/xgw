"""Conservative accounting evidence from the bounded observation journal."""

from datetime import date, timedelta

from ..zapret2 import PROBE_DAY_SECONDS, ProbeBudget
from .monitor_probes import MAX_SAMPLE_GAP_SECONDS, matched_policy
from .schema import MODES

EPOCH = date(1970, 1, 1)
MAX_TIME = ((date.max - EPOCH).days + 1) * PROBE_DAY_SECONDS
MAX_BUDGET_BYTES = 1024 ** 3


def _snapshot(row: dict, at: float) -> ProbeBudget | None:
    value = row.get("budget")
    if ("error" in row or not matched_policy(row, row) or not isinstance(value, dict)
            or row.get("mode") not in (None, *MODES)
            or row.get("engine_mode") not in (None, "off", "auto")):
        return None
    day = int(at // PROBE_DAY_SECONDS)
    recorded_day = value.get("day", day)
    spent, limit = value.get("spent_bytes"), value.get("limit_bytes")
    remaining, resets = value.get("remaining_bytes"), value.get("resets_at")
    if (any(type(item) is not int for item in (recorded_day, spent, limit, remaining, resets))
            or recorded_day != day or resets != (day + 1) * PROBE_DAY_SECONDS
            or not 0 <= spent <= MAX_BUDGET_BYTES or not 0 < limit <= MAX_BUDGET_BYTES):
        return None
    budget = ProbeBudget(day, spent, limit)
    return budget if remaining == budget.remaining_bytes else None


def _comparable(first: dict, last: dict, before: ProbeBudget, after: ProbeBudget) -> bool:
    return (last["at"] - first["at"] <= MAX_SAMPLE_GAP_SECONDS
            and before.limit_bytes == after.limit_bytes and matched_policy(first, last)
            and first.get("mode") == last.get("mode")
            and first.get("engine_mode") == last.get("engine_mode"))


def budget_summary(rows: list[dict]) -> dict:
    """Count observed budget increments, never infer traffic volume from reservations."""
    days = {}
    trusted_samples = rollovers = 0
    last_seen = -1
    previous_row, previous = {}, None
    for row in rows:
        at = row.get("at")
        if type(at) not in (int, float) or not (0 <= at < MAX_TIME and at > last_seen):
            previous = None
            continue
        last_seen = at
        current = _snapshot(row, at)
        if current is None:
            previous = None
            continue
        trusted_samples += 1
        day = days.setdefault(current.day, {
            "utc_day": (EPOCH + timedelta(days=current.day)).isoformat(),
            "samples": 0,
            "max_spent_bytes": current.spent_bytes,
            "min_remaining_bytes": current.remaining_bytes,
            "over_limit_samples": 0,
            "comparable_intervals": 0,
            "charged_intervals": 0,
            "observed_charge_bytes": 0,
        })
        prior_max = day["max_spent_bytes"]
        day["samples"] += 1
        day["max_spent_bytes"] = max(prior_max, current.spent_bytes)
        day["min_remaining_bytes"] = min(day["min_remaining_bytes"], current.remaining_bytes)
        day["over_limit_samples"] += current.spent_bytes > current.limit_bytes
        if previous is not None and _comparable(previous_row, row, previous, current):
            if current.day == previous.day + 1:
                rollovers += 1
            elif (current.day == previous.day and previous.spent_bytes == prior_max
                  and current.spent_bytes >= prior_max):
                # A counter rollback must not charge the climb back to the old value twice.
                change = current.spent_bytes - prior_max
                day["comparable_intervals"] += 1
                day["charged_intervals"] += change > 0
                day["observed_charge_bytes"] += change
        previous_row, previous = row, current
    return {"trusted_samples": trusted_samples, "unavailable_samples": len(rows) - trusted_samples,
            "confirmed_utc_rollovers": rollovers, "days": list(days.values())}
