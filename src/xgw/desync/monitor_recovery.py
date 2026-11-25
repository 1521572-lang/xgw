"""Count observable returns to an active Selected route from monitor samples."""

from collections import Counter
from itertools import pairwise

from .monitor_probes import MAX_SAMPLE_GAP_SECONDS, matched_policy


def valid_status_time(value: object, sample_at: float) -> bool:
    return type(value) in (int, float) and 0 < value <= sample_at


def recovery_summary(rows: list[dict]) -> dict:
    from ..watch.zapret2_control import REASONS

    by_reason, by_mode = Counter(), Counter()
    comparable = widest_window = 0
    latest_at = -1
    for first, last in pairwise(rows):
        at, end = first["at"], last["at"]
        ordered = at > latest_at and 0 < end - at <= MAX_SAMPLE_GAP_SECONDS
        latest_at = max(at, latest_at)
        mode, engine = first.get("mode"), first.get("engine_mode")
        if not (ordered and mode in ("selective", "standalone") and mode == last.get("mode")
                and engine in ("auto", "off") and engine == last.get("engine_mode")
                and matched_policy(first, last)):
            continue
        old_status, new_status = first.get("observed_at"), last.get("observed_at")
        # A cached daemon status or a snapshot published before the first sample
        # cannot establish a return to active within this interval.
        if not (valid_status_time(old_status, at) and valid_status_time(new_status, end)
                and new_status > at):
            continue
        comparable += 1
        if first.get("state") != "fallback" or last.get("state") != "active":
            continue
        reason = first.get("reason")
        by_reason[reason if isinstance(reason, str) and reason in REASONS else "unconfirmed"] += 1
        by_mode[mode] += 1
        widest_window = max(widest_window, end - at)
    return {"comparable_sample_pairs": comparable, "observed_returns_to_active": sum(by_mode.values()),
            "by_fallback_reason": dict(by_reason), "by_selected_mode": dict(by_mode),
            "max_sampling_window_seconds": widest_window if by_mode else None}
