"""Match private mpv TCP endpoints to accepted routes in the existing Xray journal."""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
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
from xgw.desync import route_evidence
from xgw.net.capture import CAPTURE_TAGS

XRAY_UNIT = "xgw-xray.service"
MAX_CAPTURE_SECONDS = 180
ACCESS = re.compile(
    r"(?:^|\s)from (?:tcp:)?(\S+) accepted tcp:(\S+) \[(\S+) (?:->|>>|==>) (\S+?)\]"
)


def endpoint(value):
    host, separator, port = value.rpartition(":")
    if not separator or not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError("invalid_endpoint")
    address = ipaddress.ip_address(host.removeprefix("[").removesuffix("]"))
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return str(address), int(port)


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
        match = ACCESS.search(message)
        if not match or match[3] not in CAPTURE_TAGS:
            continue
        try:
            source, target = endpoint(match[1]), endpoint(match[2])
        except ValueError:
            continue
        group = snapshot["tags"].get(match[4], {}).get("group")
        records[source, target].append(
            (when, group if group in route_evidence.GROUPS else "other")
        )
    return records


def analyze(player, journal, before, after):
    if len(journal) >= MAX_LOG_ROWS:
        return {"state": "inconclusive", "reason": "journal_limit"}
    try:
        route_evidence.deltas(before, after)
    except route_evidence.EvidenceError as exc:
        return {"state": "inconclusive", "reason": "snapshots_incomparable",
                "snapshot_reason": str(exc), **exc.details()}
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
    return {
        "state": "observed" if grouped else "inconclusive",
        "qualified_flows": len(flows),
        "groups": dict(grouped),
        "unmatched": dict(unmatched),
        "client_zapret2_rule": before["client_zapret2_rule"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--player", type=Path, required=True)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = analyze(read_log(args.player), read_rows(sys.stdin.buffer),
                         route_evidence._read_snapshot(args.before),
                         route_evidence._read_snapshot(args.after))
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        print(json.dumps({"state": "inconclusive", "reason": "invalid_evidence"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
