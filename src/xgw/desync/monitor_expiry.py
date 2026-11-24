"""Visibility of signed CDN deadline crossings in status samples."""

from collections import Counter

from ..zapret2 import CDN_EXPIRED
from .monitor_budget import MAX_TIME
from .monitor_probes import MAX_SAMPLE_GAP_SECONDS, matched_policy


def valid_cdn_deadline(value: object) -> bool:
    return type(value) is int and 0 < value < MAX_TIME


def cdn_expiry_summary(rows: list[dict]) -> dict:
    """Summarize sampled deadlines and daemon responses without exposing identifiers."""
    from ..watch.zapret2_control import REASONS, TITLES

    samples = crossings = post_statuses = 0
    states, reasons, reactions = Counter(), Counter(), Counter()
    latest_at = -1
    previous = None
    waiting = False
    last_status_at = 0
    for row in rows:
        at, deadline = row.get("at"), row.get("cdn_expires_at")
        ordered = type(at) in (int, float) and 0 <= at < MAX_TIME and at > latest_at
        if ordered:
            latest_at = at
        if (not ordered or row.get("mode") != "selective" or not valid_cdn_deadline(deadline)
                or not matched_policy(row, row)):
            previous, waiting = None, False
            continue
        samples += 1
        continuous = (previous is not None and at - previous["at"] <= MAX_SAMPLE_GAP_SECONDS
                      and previous["cdn_expires_at"] == deadline and matched_policy(previous, row)
                      and previous.get("engine_mode") == row.get("engine_mode"))
        if not continuous:
            waiting = False
        elif previous["at"] < deadline <= at:
            crossings += 1
            waiting, last_status_at = True, 0
        previous = row
        observed_at = row.get("observed_at")
        if (not waiting or type(observed_at) not in (int, float)
                or not (deadline <= observed_at <= at and observed_at > last_status_at)):
            continue

        state, reason = row.get("state"), row.get("reason")
        if not last_status_at:
            post_statuses += 1
            states[state if isinstance(state, str) and state in TITLES else "unknown"] += 1
            reasons[reason if isinstance(reason, str) and reason in REASONS else "unconfirmed"] += 1
        last_status_at = observed_at
        if reason == CDN_EXPIRED and state in ("fallback", "blocked"):
            reactions[state] += 1
            waiting = False
    return {"samples_with_deadline": samples, "observed_crossings": crossings,
            "crossings_with_post_expiry_status": post_statuses, "post_expiry_states": dict(states),
            "post_expiry_reasons": dict(reasons), "confirmed_expiry_reactions": dict(reactions)}
