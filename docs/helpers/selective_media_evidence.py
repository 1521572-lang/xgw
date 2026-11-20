"""Correlate bounded mpv, Xray socket and gateway observations."""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from itertools import pairwise
from pathlib import Path

MAX_LOG_BYTES = 8 * 1024**2
MAX_LOG_ROWS = 5000
MIN_MEDIA_BYTES = 32 * 1024
OUTBOUND_GROUPS = ("zapret2", "xray", "sing-box")
MAX_DIAGNOSTIC_WINDOWS = 5


def number(value):
    return type(value) in (float, int) and math.isfinite(value)


def read_log(path):
    with path.open("rb") as stream:
        return read_rows(stream)


def read_rows(stream):
    raw = stream.read(MAX_LOG_BYTES + 1)
    if len(raw) > MAX_LOG_BYTES:
        raise ValueError("log_size")
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if len(rows) > MAX_LOG_ROWS or any(not isinstance(row, dict) for row in rows):
        raise ValueError("log_rows")
    return rows


def read_intervals(rows, start, end, *, owner=None):
    """Only use socket reads fully inside the independently observed interval."""
    flows = {}
    for before, after in pairwise(rows):
        if owner is not None and any(row.get("state") != "read" for row in (before, after)):
            continue
        t0 = before.get("socket_start_unix")
        t1 = after.get("socket_unix")
        if (not number(t0) or not number(t1) or not start <= t0 < t1 <= end
                or t1 - t0 > 2.5):
            continue
        old = {row["socket"]: row for row in before.get("sockets", [])}
        for row in after.get("sockets", []):
            first = old.get(row["socket"])
            if not first or first["peer_ip"] != row["peer_ip"]:
                continue
            if owner is not None and any(owner not in r.get("owner_pids", [])
                                         for r in (first, row)):
                continue
            a, b = first["bytes_received"], row["bytes_received"]
            if type(a) is int and type(b) is int and 0 <= a < b:
                flows.setdefault((row["peer_ip"], row["socket"]), []).append((t0, t1, b - a))
    return flows


def correlated(player, gateway):
    exact = 0
    for (peer, _), received in player.items():
        candidates = [intervals for (address, _), intervals in gateway.items() if address == peer]
        if len(candidates) != 1:
            continue
        # Count only bytes with overlapping transfer times on the two legs.
        upstream = candidates[0]
        if (sum(b for start, end, b in received
                if any(start < right and left < end for left, right, _ in upstream))
                >= MIN_MEDIA_BYTES
                and sum(b for start, end, b in upstream
                        if any(start < right and left < end for left, right, _ in received))
                >= MIN_MEDIA_BYTES):
            exact += 1
    return exact == 1


def rates(pair):
    duration = pair["end_unix"] - pair["start_unix"]
    down = pair["groups"]["zapret2"]["downlink"]
    # Rates use the spans of the corresponding counter reads, not merely their overlap.
    seconds = pair.get("seconds") or duration
    queue_seconds = pair.get("queue_seconds") or duration
    return (down / seconds if type(down) is int else None,
            pair["nft_packets"] / queue_seconds, pair["queue_sequence_delta"] / queue_seconds)


def unmatched_outbound_reason(rate, background):
    if rate is None:
        return "counter_unavailable"
    if rate == 0:
        return "no_growth"
    if background is None:
        return "background_unavailable"
    return "at_or_below_background"


def analyze(player, sockets, gateway):
    counters = Counter()
    probe_windows = set()
    for row in gateway:
        for probe in row.get("probes", {}).values():
            start, elapsed = probe.get("started_at"), probe.get("elapsed_ms")
            if number(start) and number(elapsed) and elapsed >= 0:
                probe_windows.add((start, start + elapsed / 1000))
    windows = []
    for before, after in pairwise(gateway):
        pair = after.get("media_pair") or {}
        if pair.get("state") != "accepted":
            counters["rejected_pairs"] += 1
            continue
        start, end = pair["start_unix"], pair["end_unix"]
        if (not number(pair.get("probe_before"))
                or pair["probe_before"] != pair.get("probe_after")
                or any(left <= end and start <= right for left, right in probe_windows)):
            counters["probe_overlap_or_unconfirmed"] += 1
            continue
        pid = after["route"]["xray_epoch"].split(":")[1]
        trusted = all(row.get("queue_owner_confirmed") is True for row in (before, after))
        if not trusted or not pid.isascii() or not pid.isdecimal() or int(pid) <= 0:
            counters["owner_unconfirmed"] += 1
            continue
        last_read = max(after["route"]["unix"], after["queue_end_unix"], end)
        windows.append((start, end, last_read, int(pid), rates(pair), pair["groups"]))

    started = player[0].get("capture_started_unix", player[0]["unix"]) if player else None
    background = [values for _, _, last, _, values, _ in windows
                  if started is not None and last < started]
    baseline = [max((row[i] for row in background if row[i] is not None), default=None)
                for i in range(3)]
    playback = [row for row in player if row.get("eligible_phase") is True]
    unmatched_reasons = Counter()
    unmatched_windows = []
    for start, end, _, pid, values, groups in windows:
        if started is None or end <= started:
            continue
        counters["comparable_windows"] += 1
        client_flows = read_intervals(playback, max(start, started), end)
        marked_flows = read_intervals(sockets, max(start, started), end, owner=pid)
        if not correlated(client_flows, marked_flows):
            continue
        counters["socket_matches"] += 1
        increases = [actual is not None and base is not None and actual > base
                     for actual, base in zip(values, baseline, strict=True)]
        counters["outbound_matches"] += increases[0]
        queue_increase = all(increases[1:])
        counters["queue_matches"] += queue_increase
        counters["full_matches"] += all(increases)
        if not increases[0]:
            reason = unmatched_outbound_reason(values[0], baseline[0])
            unmatched_reasons[reason] += 1
            downlink = {}
            for group in OUTBOUND_GROUPS:
                value = groups.get(group, {}).get("downlink")
                downlink[group] = value if type(value) is int and value >= 0 else None
            unmatched_windows.append({
                "offset_seconds": round(start - started, 3),
                "overlap_seconds": round(end - start, 3),
                "downlink_bytes": downlink,
                "zapret2_bytes_per_second": values[0],
                "queue_above_background": queue_increase,
                "reason": reason,
            })
    unmatched_windows.sort(
        key=lambda window: max(value or 0 for value in window["downlink_bytes"].values()),
        reverse=True,
    )
    return {"counts": dict(counters), "background_windows": len(background),
            "media_path": ("SUPPORTED" if counters["outbound_matches"]
                           else "PARTIAL" if counters["socket_matches"] else "UNKNOWN"),
            "nfqueue": "OBSERVED" if counters["queue_matches"] else "UNCONFIRMED",
            "outbound_diagnostics": {
                "zapret2_background_peak_bytes_per_second": baseline[0],
                "unmatched_reasons": dict(unmatched_reasons),
                "top_unmatched_windows": unmatched_windows[:MAX_DIAGNOSTIC_WINDOWS],
            }}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--player", type=Path, required=True)
    parser.add_argument("--marked", type=Path, required=True)
    parser.add_argument("--gateway", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = analyze(read_log(args.player), read_log(args.marked), read_log(args.gateway))
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        print(json.dumps({"error": "invalid_or_missing_evidence"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
