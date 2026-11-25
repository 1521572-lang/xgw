"""Observe applied policy boundaries without recording their contents or actor."""

from collections import Counter

from .monitor_probes import MAX_SAMPLE_GAP_SECONDS, matched_policy


def policy_label(row: dict) -> str | None:
    selected, engine = row.get("mode"), row.get("engine_mode")
    if selected not in ("off", "selective", "standalone") or engine not in (None, "off", "auto"):
        return None
    return f"{selected}/{engine or 'unknown'}"


def policy_changes(rows: list[dict]) -> dict:
    changes, kinds = Counter(), Counter()
    confirmed = 0
    last_at = -1
    baseline = pending = None
    for row in rows:
        at = row["at"]
        if not 0 < at - last_at <= MAX_SAMPLE_GAP_SECONDS:
            baseline = pending = None
        if at <= last_at:
            continue
        last_at = at

        label, key = policy_label(row), row.get("config_key")
        if not (label and isinstance(key, str) and key and row.get("fresh") is True
                and not row.get("error") and row.get("reason") != "invalid_policy"):
            baseline = pending = None
            continue
        revision = (key, label)
        if not matched_policy(row, row):
            if (baseline is not None and at - baseline["at"] <= MAX_SAMPLE_GAP_SECONDS
                    and row.get("policy_matched") is False and row.get("state") == "pending"
                    and row.get("reason") == "policy_changed"
                    and (pending is None or pending == revision)
                    and key != baseline["config_key"]):
                pending = revision
            else:
                baseline = pending = None
            continue

        confirmed += 1
        if (baseline is not None and at - baseline["at"] <= MAX_SAMPLE_GAP_SECONDS
                and (pending is None or pending == revision) and key != baseline["config_key"]):
            changes[f"{policy_label(baseline)} → {label}"] += 1
            old_engine, engine = baseline.get("engine_mode"), row.get("engine_mode")
            engine_known = old_engine is not None and engine is not None
            if baseline.get("mode") != row.get("mode"):
                kind = ("selected_and_engine_changed" if engine_known and old_engine != engine
                        else "selected_changed")
                kinds[kind] += 1
            elif not engine_known:
                kinds["selected_unchanged_engine_unknown"] += 1
            elif old_engine != engine:
                kinds["engine_changed"] += 1
            else:
                kinds["same_modes_new_revision"] += 1
        baseline, pending = row, None
    return {"confirmed_samples": confirmed, "observed_changes": sum(changes.values()),
            "by_policy": dict(changes), "by_kind": dict(kinds)}
