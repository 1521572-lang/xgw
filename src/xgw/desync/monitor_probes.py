"""Aggregate the probe evidence actually seen by the status sampler."""

from collections import Counter

from ..zapret2 import PROBE_BYTES

MAX_SAMPLE_GAP_SECONDS = 600


def matched_policy(first, last):
    key = first.get("config_key")
    return (isinstance(key, str) and bool(key) and key == last.get("config_key")
            and all(row.get("fresh") is True and row.get("policy_matched") is True
                    and not row.get("error") for row in (first, last)))


def _timestamp(value, sample_at):
    return type(value) in (int, float) and 0 < value <= sample_at


def _probe_outcome(row, ok):
    fields = {"ok": ok}
    verified = row.get("range_verified")
    if type(verified) is bool:
        http, length = row.get("http"), row.get("bytes")
        fields["range_verified"] = (verified and ok and row.get("phase") == "body"
                                    and type(http) is int and http == 206
                                    and type(length) is int and length == PROBE_BYTES)
    return fields


def _vpn_records(attempts, target, sample_at):
    if not isinstance(attempts, list):
        return []
    recorded = []
    for attempt in attempts[:2]:
        if not isinstance(attempt, dict):
            break
        stamp, verdict = attempt.get("at"), attempt.get("verdict")
        if not _timestamp(stamp, sample_at) or verdict not in ("pass", "fail"):
            break
        if recorded and (recorded[0]["verdict"] != "fail" or stamp <= recorded[0]["at"]
                         or target != "cdn"):
            break
        row = {"at": stamp, "verdict": verdict}
        if target == "cdn":
            outcome = _probe_outcome(attempt, verdict == "pass")
            if "range_verified" in outcome:
                row["range_verified"] = outcome["range_verified"]
                if outcome["range_verified"]:
                    row.update(phase="body", http=206, bytes=PROBE_BYTES)
        recorded.append(row)
    return recorded


def vpn_probe_attempts(evidence, sample_at):
    target = evidence.get("vpn_control_target")
    if target not in ("page", "cdn"):
        return {}
    recorded = _vpn_records(evidence.get("vpn_control_attempts"), target, sample_at)
    return {target: recorded} if recorded else {}


def _record(counts, outcome, *, first, target):
    phase = "first" if first else "retry"
    verdict = "pass" if outcome["ok"] else "fail"
    counts[f"{phase}_{verdict}"] += 1
    if target == "cdn":
        range_result = {True: "verified", False: "unverified", None: "unavailable"}
        counts[f"range_{range_result[outcome.get('range_verified')]}"] += 1


def probe_summary(rows):
    """Each attempt is counted once even if the daemon publishes it repeatedly."""
    counts = {f"{path}_{target}": Counter() for path in ("direct", "vpn")
              for target in ("page", "cdn")}
    seen = set()
    for row in rows:
        if not matched_policy(row, row):
            continue
        direct, vpn = row.get("probes"), row.get("vpn_probe_attempts")
        for target in ("page", "cdn"):
            probe = direct.get(target) if isinstance(direct, dict) else None
            if isinstance(probe, dict) and type(probe.get("ok")) is bool:
                stamp, retry_ms = probe.get("started_at"), probe.get("first_tls_timeout_ms")
                event = ("direct", target, stamp) if _timestamp(stamp, row["at"]) else None
                if event is not None and event not in seen:
                    seen.add(event)
                    elapsed = probe.get("elapsed_ms")
                    retry = (target == "cdn" and type(retry_ms) is int and type(elapsed) is int
                             and 0 <= retry_ms <= elapsed <= 60_000)
                    summary = counts[f"direct_{target}"]
                    if retry:
                        _record(summary, {"ok": False}, first=True, target=target)
                    _record(summary, _probe_outcome(probe, probe["ok"]),
                            first=not retry, target=target)
            attempts = vpn.get(target) if isinstance(vpn, dict) else None
            for i, attempt in enumerate(_vpn_records(attempts, target, row["at"])):
                event = ("vpn", target, attempt["at"])
                if event not in seen:
                    seen.add(event)
                    outcome = _probe_outcome(attempt, attempt["verdict"] == "pass")
                    _record(counts[f"vpn_{target}"], outcome, first=i == 0, target=target)
    return {name: dict(summary) for name, summary in counts.items()}
