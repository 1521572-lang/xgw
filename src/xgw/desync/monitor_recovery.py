"""Count observable returns to an active Selected route from monitor samples."""

from collections import Counter
from itertools import pairwise

from .monitor_probes import MAX_SAMPLE_GAP_SECONDS, matched_policy

_SELECTIVE_RETRY_STAGES = ("probe_inbound", "nfqueue")


def valid_status_time(value: object, sample_at: float) -> bool:
    return type(value) in (int, float) and 0 < value <= sample_at


def _retry_stage(row: dict) -> int:
    if row.get("state") == "preparing" and row.get("mode") == "selective":
        reason = row.get("reason")
        if reason in _SELECTIVE_RETRY_STAGES:
            return _SELECTIVE_RETRY_STAGES.index(reason) + 1
    return 0


def recovery_summary(rows: list[dict]) -> dict:
    from ..watch.zapret2_control import REASONS

    by_reason, by_mode = Counter(), Counter()
    comparable = widest_window = 0
    latest_at = -1
    fallback = None
    for first, last in pairwise(rows):
        at, end = first["at"], last["at"]
        ordered = at > latest_at and 0 < end - at <= MAX_SAMPLE_GAP_SECONDS
        latest_at = max(at, latest_at)
        mode, engine = first.get("mode"), first.get("engine_mode")
        if not (ordered and mode in ("selective", "standalone") and mode == last.get("mode")
                and engine in ("auto", "off") and engine == last.get("engine_mode")
                and matched_policy(first, last)):
            fallback = None
            continue
        old_status, new_status = first.get("observed_at"), last.get("observed_at")
        if not (valid_status_time(old_status, at) and valid_status_time(new_status, end)
                and new_status >= old_status):
            fallback = None
            continue
        fresh_status = new_status > at
        comparable += fresh_status
        if first.get("state") == "fallback":
            fallback = first
        if fallback is not None and end - fallback["at"] <= MAX_SAMPLE_GAP_SECONDS:
            stage, previous_stage = _retry_stage(last), _retry_stage(first)
            if stage and stage >= previous_stage and (
                    fresh_status or (stage == previous_stage and new_status == old_status)):
                # The controller can rebuild its probe inbound and start the
                # worker before publishing active. The watcher can sample both.
                continue
            if last.get("state") == "active" and fresh_status:
                reason = fallback.get("reason")
                by_reason[reason if isinstance(reason, str) and reason in REASONS
                          else "unconfirmed"] += 1
                by_mode[mode] += 1
                widest_window = max(widest_window, end - fallback["at"])
        fallback = None
    return {"comparable_sample_pairs": comparable, "observed_returns_to_active": sum(by_mode.values()),
            "by_fallback_reason": dict(by_reason), "by_selected_mode": dict(by_mode),
            "max_sampling_window_seconds": widest_window if by_mode else None}
