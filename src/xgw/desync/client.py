"""Local authenticated control and bounded acceptance monitoring; never opens a WAN port."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import time
from collections import Counter
from itertools import pairwise
from pathlib import Path

from .jobs import ACTIVE, CANDIDATES, WAIT_STAGES


class _HTTPFailure(ValueError):
    def __init__(self, status: int) -> None:
        super().__init__("local_api_unavailable_or_login_expired")
        self.status = status


class Client:
    def __init__(self):
        from ..gui.model import load_session, session_file

        self.session = load_session(session_file())
        if self.session is None:
            raise ValueError("Сначала войдите в панель через XGW от пользователя рабочего стола.")

    def request(self, path, body=None):
        if path not in ("/api/state", "/api/zapret2/overview") and not path.startswith(
            "/api/zapret2/"
        ):
            raise ValueError("local_api_path")
        connection = http.client.HTTPConnection("127.0.0.1", self.session.port, timeout=10)
        headers = {"Cookie": "xgw_panel=" + self.session.cookie}
        data = None
        if body is not None:
            headers.update({"X-XGW-Panel": "1", "Content-Type": "application/json"})
            data = json.dumps(body).encode()
        try:
            connection.request("GET" if body is None else "POST", path, data, headers)
            response = connection.getresponse()
            raw = response.read(1024 * 1024 + 1)
            if response.status != 200:
                raise _HTTPFailure(response.status)
            if len(raw) > 1024 * 1024:
                raise ValueError("local_api_unavailable_or_login_expired")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("local_api_schema")
            return result
        finally:
            connection.close()


def observation(state):
    """Whitelist only aggregate metrics: no servers, URLs, cookies, IPs or device IDs."""
    card = state.get("zapret2") or {}
    budget = card.get("probe_budget") or {}
    evidence = card.get("evidence") or {}
    pool = state.get("free_pool") or {}
    summary = pool.get("summary") or {}
    traffic = summary.get("traffic") or {}
    return {
        "at": time.time(), "utc_day": time.strftime("%Y-%m-%d", time.gmtime()),
        "health": state.get("state"), "updated": state.get("updated"),
        "mode": card.get("mode"), "engine_mode": card.get("engine_mode"),
        "state": card.get("state"),
        "reason": card.get("reason"), "fresh": card.get("fresh"),
        "policy_matched": card.get("policy_matched"),
        "config_key": card.get("config_key"),
        "transport": evidence.get("transport"),
        "vpn_control": evidence.get("vpn_control"),
        "budget": {k: budget[k] for k in ("day", "spent_bytes", "remaining_bytes",
                                         "limit_bytes", "resets_at") if k in budget},
        "job_state": (card.get("job") or {}).get("state"),
        "pool_mode": pool.get("mode"), "pool_closed": traffic.get("closed"),
        "probes": {name: {k: row[k] for k in ("ok", "phase", "kind", "elapsed_ms",
                                             "http", "bytes") if k in row}
                   for name, row in (evidence.get("transport_probes") or {}).items()
                   if name in ("page", "cdn") and isinstance(row, dict)},
    }


def monitor(client, output, seconds, interval):
    if not 60 <= seconds <= 90000 or not 15 <= interval <= 300:
        raise ValueError("monitor_bounds_60_90000s_interval_15_300s")
    deadline = time.monotonic() + seconds
    counts = Counter()
    size = samples = 0
    fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        while True:
            try:
                row = observation(client.request("/api/state"))
                counts[str(row["state"])] += 1
            except (OSError, ValueError, http.client.HTTPException):
                row = {"at": time.time(), "error": "api_unavailable"}
                counts["api_unavailable"] += 1
            line = json.dumps(row, ensure_ascii=False) + "\n"
            size += len(line.encode())
            if size > 16 * 1024 * 1024:
                raise ValueError("monitor_size_limit")
            stream.write(line)
            stream.flush()
            samples += 1
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval, remaining))
    return {"samples": samples, "states": dict(counts), "bytes": size,
            "seconds": seconds, "output": str(output)}


def _policy_label(row):
    selected, engine = row.get("mode"), row.get("engine_mode")
    if selected not in ("off", "selective", "standalone") or engine not in (None, "off", "auto"):
        return None
    # Older journals stored the Selected mode but omitted the Engine setting.
    return f"{selected}/{engine or 'unknown'}"


def analyze(path):
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("monitor_size_limit")
    rows = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if not isinstance(row, dict) or type(row.get("at")) not in (int, float):
                raise ValueError("monitor_schema")
            rows.append(row)
            if len(rows) > 6002:
                raise ValueError("monitor_sample_limit")
    durations, policies = Counter(), Counter()
    boundaries = gaps = 0
    for first, last in pairwise(rows):
        elapsed = last["at"] - first["at"]
        if not 0 < elapsed <= 600:
            gaps += 1
            continue
        key = first.get("config_key")
        matched = (isinstance(key, str) and bool(key) and key == last.get("config_key")
                   and all(row.get("fresh") is True and row.get("policy_matched") is True
                           for row in (first, last)))
        state, mode = first.get("state"), _policy_label(first)
        same_state = matched and isinstance(state, str) and state and state == last.get("state")
        durations[state if same_state else "unconfirmed"] += elapsed
        same_mode = matched and mode and mode == _policy_label(last)
        policies[mode if same_mode else "unconfirmed"] += elapsed
        a, b = first.get("budget") or {}, last.get("budget") or {}
        if (isinstance(a.get("resets_at"), int) and isinstance(b.get("resets_at"), int)
                and b["resets_at"] - a["resets_at"] == 86400):
            boundaries += 1
    return {"samples": len(rows), "elapsed_seconds": (
        rows[-1]["at"] - rows[0]["at"] if rows else 0),
        "confirmed_interval_seconds": dict(durations), "policy_interval_seconds": dict(policies),
        "large_or_backward_gaps": gaps,
        "utc_boundary_sample_pairs": boundaries,
        "api_errors": sum(bool(r.get("error")) for r in rows),
        "note": "Status intervals do not prove playback or a free-pool recovery."}


def matrix_report(path):
    """Recount the ordered results from a single saved job or client status."""
    from ..watch.zapret2_control import REASONS, transport_probes

    with path.open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("matrix_size")
    view = json.loads(raw)
    if not isinstance(view, dict):
        raise ValueError("matrix_object")
    job = view.get("job", view)
    if (not isinstance(job, dict) or not isinstance(job.get("id"), str)
            or not re.fullmatch("[0-9a-f]{32}", job["id"])):
        raise ValueError("matrix_job")
    profiles, rounds, rows = job.get("candidates"), job.get("rounds"), job.get("results")
    if (not isinstance(profiles, list) or not 1 <= len(profiles) <= len(CANDIDATES)
            or any(not isinstance(p, str) or p not in CANDIDATES for p in profiles)
            or len(set(profiles)) != len(profiles)
            or type(rounds) is not int or rounds not in (1, 2) or not isinstance(rows, list)):
        raise ValueError("matrix_schedule")
    schedule = [(n + 1, p) for n in range(rounds) for p in profiles[::1 if n == 0 else -1]]
    if len(rows) > len(schedule):
        raise ValueError("extra_rows")
    counts = Counter()
    results = {p: [] for p in profiles}
    now = time.time()
    for row, (n, profile) in zip(rows, schedule, strict=False):
        if (not isinstance(row, dict) or type(row.get("round")) is not int
                or (row["round"], row.get("candidate")) != (n, profile)
                or row.get("state") not in ("active", "fallback", "blocked", "timeout", "error")):
            raise ValueError("matrix_row_or_order")
        state = row["state"]
        counts[state] += 1
        reason = row.get("reason")
        if not isinstance(reason, str) or (reason not in REASONS and reason != "trial_timeout"):
            reason = "unconfirmed"
        outcome = {
            "round": n, "state": state, "reason": reason,
            "https_ok": state == "active" and row.get("transport") == "https_reachable",
            "probes": transport_probes(row.get("probes"), now=now),
        }
        stage = row.get("wait_stage")
        if state == "timeout" and stage in WAIT_STAGES:
            outcome["wait_stage"] = stage
        elapsed = row.get("elapsed_ms")
        if type(elapsed) is int and 0 <= elapsed <= 3_600_000:
            outcome["elapsed_ms"] = elapsed
        results[profile].append(outcome)
    complete = (len(rows) == len(schedule) and job.get("state") == "complete"
                and job.get("restore") == "pass")
    passed_twice = [p for p, runs in results.items()
                    if len(runs) == 2 and all(run["https_ok"] for run in runs)]
    return {"ok": complete, "job_id": job["id"], "expected_rows": len(schedule),
            "observed_rows": len(rows), "states": dict(counts), "profiles": results,
            "full_matrix": complete and rounds == 2 and len(profiles) == len(CANDIDATES),
            "two_https_pass": passed_twice, "playback": "NOT_MEASURED"}


def _matrix_outcome(row: dict) -> str:
    from ..zapret2 import CDN_EXPIRED

    reason = row["reason"]
    if row["https_ok"]:
        return "https_pass"
    if reason == CDN_EXPIRED:
        return "expired_cdn_url"
    if row["state"] == "timeout":
        if row.get("wait_stage") in ("status_stale", "policy_pending", "matched_other", "no_sample"):
            return "control_wait_timeout"
        return "trial_timeout"
    target = {"youtube_page_probe_failed": "page", "youtube_cdn_probe_failed": "cdn"}.get(reason)
    probe = row["probes"].get(target)
    if not probe or probe["ok"]:
        return "probe_details_unavailable" if target else "other_unconfirmed"
    phase, kind = probe["phase"], probe["kind"]
    if phase == "tls":
        return "tls_timeout" if kind == "timeout" else "tls_failure"
    if phase == "body" and kind in ("stall", "timeout", "truncated", "reset"):
        return "body_stall" if kind in ("stall", "timeout") else "body_interrupted"
    if kind in ("http", "proxy"):
        return "http_or_proxy_failure"
    if kind == "cancelled":
        return "probe_cancelled"
    return "probe_failure_other"


def _prefix_score(order: list[str], holdout: dict) -> dict:
    """Measure a hypothetical first-success stop using only held-out costs and outcomes."""
    hits = [i for i, candidate in enumerate(order, 1) if holdout[candidate]["https_ok"]]
    first = hits[0] if hits else None
    prefix = order[:first]

    def total(candidates: list[str]) -> int | None:
        costs = [holdout[name].get("elapsed_ms") for name in candidates]
        return None if None in costs else sum(costs)

    body_sizes = [[probe["bytes"] for probe in holdout[name]["probes"].values()
                   if probe["bytes"] is not None] for name in prefix]
    return {
        "order": order, "full_attempt_ms": total(order),
        "first_pass_attempt": first, "first_pass_ms": total(prefix) if first else None,
        "attempts_if_stop_after_pass": len(prefix),
        "attempt_ms_if_stop_after_pass": total(prefix),
        "observed_probe_bytes_if_stop_after_pass": sum(sum(sizes) for sizes in body_sizes)
        if any(body_sizes) else None,
        "attempts_with_byte_samples": sum(bool(sizes) for sizes in body_sizes),
        "untried_https_passes": [order[i - 1] for i in hits[1:]],
    }


def matrix_replay(report: dict) -> dict:
    """Compare a prior-round order on recorded HTTPS trials. No change to gateway policy."""
    profiles = report["profiles"]
    outcomes: dict[int, Counter] = {1: Counter(), 2: Counter()}
    for runs in profiles.values():
        for sample in runs:
            outcomes[sample["round"]][_matrix_outcome(sample)] += 1
    result = {
        "ok": report["ok"], "expected_rows": report["expected_rows"],
        "observed_rows": report["observed_rows"], "full_matrix": report["full_matrix"],
        "outcomes_by_round": {n: dict(counts) for n, counts in outcomes.items()},
        "replay": {"state": "two_complete_rounds_required"},
        "endpoint_context": "NOT_VERIFIED", "playback": "NOT_MEASURED", "apply": False,
    }
    if not report["ok"] or not all(len(runs) == 2 for runs in profiles.values()):
        return result
    baseline = list(reversed(profiles))
    training = {name: runs[0] for name, runs in profiles.items()}
    holdout = {name: runs[1] for name, runs in profiles.items()}

    def rank(name: str) -> tuple[bool, float]:
        prior = training[name]
        # Unknown or unsuccessful trials stay in the original relative order.
        if prior["https_ok"]:
            return False, prior.get("elapsed_ms", float("inf"))
        return True, float("inf")

    proposed = sorted(baseline, key=rank)
    result["replay"] = {
        "state": "descriptive", "training_round": 1, "held_out_round": 2,
        "training_https_passes": sum(row["https_ok"] for row in training.values()),
        "recorded": _prefix_score(baseline, holdout),
        "prior_round_order": _prefix_score(proposed, holdout),
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    status = sub.add_parser("status")
    status.add_argument("--summary", action="store_true",
                        help="Пять полей статуса через изолированную службу чтения")
    start = sub.add_parser("start")
    start.add_argument("--candidates", nargs="+", choices=CANDIDATES, default=list(CANDIDATES))
    start.add_argument("--rounds", type=int, choices=(1, 2), default=2)
    start.add_argument("--seconds", type=int, default=3600)
    for name in ("cancel", "reset", "probe-persistent", "import-flowseal"):
        sub.add_parser(name)
    pin = sub.add_parser("pin")
    pin.add_argument("candidate", choices=CANDIDATES)
    watch = sub.add_parser("monitor")
    watch.add_argument("--output", type=Path, required=True)
    watch.add_argument("--seconds", type=int, default=86400)
    watch.add_argument("--interval", type=int, default=60)
    review = sub.add_parser("analyze")
    review.add_argument("input", type=Path)
    matrix = sub.add_parser("matrix", help="Summarize one saved job without contacting the gateway")
    matrix.add_argument("input", type=Path)
    matrix.add_argument("--replay", action="store_true", help="Compare a prior-round order offline")
    args = parser.parse_args()
    try:
        client = None if args.action in ("analyze", "matrix") else Client()
        if args.action == "matrix":
            result = matrix_report(args.input)
            if args.replay:
                result = matrix_replay(result)
        elif args.action == "analyze":
            result = analyze(args.input)
        elif args.action == "monitor":
            result = monitor(client, args.output, args.seconds, args.interval)
        elif args.action == "status" and args.summary:
            from ..watch.panel_ipc import project

            result = project(client.request("/api/zapret2/status").get("zapret2"))
        else:
            view = client.request("/api/zapret2/overview")["zapret2"]
            job = view.get("job") or {}
            body = {"expected": view["config_key"]}
            if args.action == "status":
                result = view
            else:
                if args.action in ("cancel", "reset", "pin"):
                    if not job.get("id"):
                        raise ValueError("no_job")
                    body["id"] = job["id"]
                if args.action == "cancel":
                    body.pop("expected")
                    if job.get("state") not in ACTIVE:
                        raise ValueError("no_active_job")
                if args.action == "pin":
                    body["candidate"] = args.candidate
                if args.action == "start":
                    body.update(candidates=args.candidates, rounds=args.rounds,
                                budget_seconds=args.seconds)
                if args.action == "probe-persistent":
                    action, body["probe"] = "probe", "persistent"
                elif args.action == "import-flowseal":
                    action, body["import"] = "import", "flowseal_alt9"
                else:
                    action = "job/" + args.action
                result = client.request("/api/zapret2/" + action, body)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok", True) else 2
    except (OSError, ValueError, KeyError, RecursionError, http.client.HTTPException) as exc:
        if args.action == "matrix":
            print(json.dumps({"ok": False, "error": "invalid_or_missing_job_snapshot"}))
            return 2
        if (args.action == "status" and args.summary and isinstance(exc, _HTTPFailure)
                and exc.status in (404, 503)):
            print(json.dumps({"ok": False, "error": "isolated_status_unavailable",
                              "http_status": exc.status,
                              "text": "Изолированная служба статуса недоступна."},
                             ensure_ascii=False))
            return 2
        print(json.dumps({"ok": False, "error": "local_api_or_parameters",
                          "text": "Проверьте вход в панель и параметры команды."},
                         ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

