"""Match private mpv TCP endpoints to accepted routes in the existing Xray journal."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from uuid import UUID

from docs.helpers.selective_media_evidence import (
    MAX_LOG_ROWS,
    MIN_MEDIA_BYTES,
    number,
    read_intervals,
    read_log,
    read_rows,
)
from docs.helpers.xray_access import endpoint, parse_accepted
from xgw.desync import route_evidence
from xgw.net.capture import CAPTURE_TAGS
from xgw.zapret2 import OUT

XRAY_UNIT = "xgw-xray.service"
MAX_CAPTURE_SECONDS = 180


def media_flows(player, start, end):
    eligible = [row for row in player if row.get("eligible_phase") is True]
    intervals = read_intervals(eligible, start, end)
    flows = {key for key, spans in intervals.items()
             if sum(count for _, _, count in spans) >= MIN_MEDIA_BYTES}
    endpoints = defaultdict(set)
    first_seen = {}
    for row in player:
        observed = row.get("socket_unix")
        if not number(observed) or not start <= observed <= end:
            continue
        for sample in row.get("sockets", []):
            key = sample["peer_ip"], sample["socket"]
            if key not in flows:
                continue
            local = sample.get("local_endpoint")
            endpoints[key].add(endpoint(local) if local else None)
            first_seen[key] = min(first_seen.get(key, observed), observed)
    return flows, endpoints, first_seen


def access_records(journal, snapshot, start, end):
    boot, pid, _ = snapshot["xray_epoch"].split(":")
    boot = UUID(boot).hex
    records = defaultdict(list)
    for row in journal:
        if ((row.get("_SYSTEMD_UNIT"), row.get("_BOOT_ID"), row.get("_PID"))
                != (XRAY_UNIT, boot, pid)):
            continue
        when = int(row.get("__REALTIME_TIMESTAMP", "0")) / 1_000_000
        message = row.get("MESSAGE")
        if not start <= when <= end or not isinstance(message, str):
            continue
        accepted = parse_accepted(message)
        if accepted is None or accepted.inbound not in CAPTURE_TAGS:
            continue
        try:
            source, target = endpoint(accepted.source), endpoint(accepted.target)
        except ValueError:
            continue
        group = snapshot["tags"].get(accepted.outbound, {}).get("group")
        records[source, target].append(
            (when, group if group in route_evidence.GROUPS else "other")
        )
    return records


def _match_flows(player, journal, before, after, *, include_record_counts=False):
    start = player[0].get("capture_started_unix") if player else None
    begin = before["unix"]
    end = after["unix"]
    if not number(start) or not begin <= start < end <= begin + MAX_CAPTURE_SECONDS:
        return {"state": "inconclusive", "reason": "capture_window"}
    flows, endpoints, first_seen = media_flows(player, start, end)
    records = access_records(journal, before, start, end)
    grouped = Counter()
    unmatched = Counter()
    flow_keys = {}
    for key in sorted(flows):
        sources = endpoints[key]
        if len(sources) != 1 or None in sources:
            unmatched["local_endpoint_unconfirmed"] += 1
            continue
        (source,) = sources
        flow_keys[key] = source, (key[0], 443)
    uses = Counter(flow_keys.values())
    for key, endpoints_key in flow_keys.items():
        candidates = records.get(endpoints_key, ())
        if uses[endpoints_key] > 1 or len(candidates) > 1:
            unmatched["ambiguous"] += 1
        elif not candidates or candidates[0][0] > first_seen[key] + 2.5:
            unmatched["no_access_record"] += 1
        else:
            grouped[candidates[0][1]] += 1
    result = {
        "state": "observed" if grouped else "inconclusive",
        "qualified_flows": len(flows),
        "groups": dict(grouped),
        "unmatched": dict(unmatched),
        "client_zapret2_rule": before["client_zapret2_rule"],
    }
    if include_record_counts:
        result["capture_accept_records"] = dict(Counter(
            group for entries in records.values() for _, group in entries
        ))
    return result


def analyze(player, journal, before, after, *, observe_applied_change=False):
    if len(journal) >= MAX_LOG_ROWS:
        return {"state": "inconclusive", "reason": "journal_limit"}
    try:
        route_evidence.deltas(before, after)
    except route_evidence.EvidenceError as exc:
        result = {"state": "inconclusive", "reason": "snapshots_incomparable",
                  "snapshot_reason": str(exc), **exc.details()}
        if (observe_applied_change and exc.details().get("field") == "applied_config"
                and type(before["monotonic_ns"]) is int and type(after["monotonic_ns"]) is int
                and 0 < before["monotonic_ns"] < after["monotonic_ns"]
                and all(snap["tags"].get(OUT, {}).get("group") == "zapret2"
                        for snap in (before, after))):
            # The reserved tag is meaningful within one Xray epoch. A changed
            # window can't establish which VPN endpoint was behind other tags.
            # Keep the primary window verdict and expose only exact journal matches.
            selected = {**before, "tags": {OUT: {"group": "zapret2"}}}
            matches = _match_flows(player, journal, selected, after, include_record_counts=True)
            if "qualified_flows" in matches:
                total = matches["qualified_flows"]
                accepted = matches["groups"].get("zapret2", 0)
                result["logged_zapret2"] = {
                    "accepted_flows": accepted, "unconfirmed_flows": total - accepted,
                    "qualified_flows": total,
                    "accepted_other_outbound_flows": matches["groups"].get("other", 0),
                    "unmatched": matches["unmatched"],
                    "capture_accept_records": matches["capture_accept_records"],
                }
        return result
    return _match_flows(player, journal, before, after, include_record_counts=observe_applied_change)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--player", type=Path, required=True)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--observe-applied-change", action="store_true",
                        help="Report exact zapret2 journal matches in an otherwise inconclusive window")
    args = parser.parse_args()
    try:
        result = analyze(read_log(args.player), read_rows(sys.stdin.buffer),
                         route_evidence._read_snapshot(args.before),
                         route_evidence._read_snapshot(args.after),
                         observe_applied_change=args.observe_applied_change)
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        print(json.dumps({"state": "inconclusive", "reason": "invalid_evidence"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
