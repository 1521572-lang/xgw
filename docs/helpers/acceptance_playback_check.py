"""Check measured playback duration and quality; route evidence remains independent."""
from __future__ import annotations

import argparse
import json
import os
from itertools import pairwise
from pathlib import Path

from docs.helpers.playback_netlog import read_media
from docs.helpers.youtube_telemetry import eligible, number, summarize
from xgw.desync import shadow


def seek_index(rows, video, minimum_jump):
    previous = origin = None
    for index, row in enumerate(rows):
        if row.get("video_id") != video or row.get("ad") or row.get("hidden"):
            previous = origin = None
            continue
        for event in row.get("events", []):
            if (not isinstance(event, dict) or event.get("media_id") != row.get("media_id")
                    or event.get("ad") or event.get("hidden")):
                continue
            if event.get("name") == "seeking" and previous is not None and (
                    0 < row["t_s"] - previous["t_s"] <= 2.5):
                origin = previous
            if event.get("name") != "seeked":
                continue
            if minimum_jump is None:
                return index
            target = event.get("position")
            if (origin and all(origin.get(key) == row.get(key)
                               for key in ("media_id", "document_id"))
                    and number(target) and target - origin["position"] >= minimum_jump):
                ranges = origin.get("buffer_ranges")
                if (isinstance(ranges, list) and all(
                    isinstance(span, list) and len(span) == 2 and all(number(x) for x in span)
                    and 0 <= span[0] <= span[1] and not span[0] <= target <= span[1]
                    for span in ranges
                )):
                    return index
            origin = None
        if eligible(row, video):
            previous = row
    return None


def evaluate(rows, video, minimum, require_seek=False, *, minimum_jump=None, netlog=None):
    if not 120 <= minimum <= 1800 or not rows:
        raise ValueError("duration_or_samples")
    seek_found = False
    if any(not number(row.get(k)) for row in rows for k in ("unix", "t_s")):
        raise ValueError("missing_clock")
    if any(b["t_s"] <= a["t_s"] for a, b in pairwise(rows)):
        raise ValueError("non_monotonic_clock")
    if require_seek or minimum_jump is not None:
        index = seek_index(rows, video, minimum_jump)
        if index is not None:
            rows, seek_found = rows[index:], True
        require_seek = True
    elapsed = rows[-1]["t_s"] - rows[0]["t_s"]
    wall = rows[-1]["unix"] - rows[0]["unix"]
    result = summarize(rows, video, 720)
    eligible_seconds = result["eligible_seconds"]
    progress = result["content_progress_seconds"] / eligible_seconds if eligible_seconds else 0
    counters = [(r.get("network") or {}).get("encoded_bytes") for r in (rows[0], rows[-1])]
    media = (counters[1] - counters[0] if all(number(v) for v in counters)
             and counters[1] >= counters[0] else 0)
    network_source = "sample_counters" if media else "unavailable"
    if netlog is False:
        media = 0
        network_source = "netlog_unavailable"
    elif netlog is not None:
        intervals, (start, end) = netlog
        media = 0
        network_source = "netlog_incomplete"
        if start <= rows[0]["unix"] + 2 and end >= rows[-1]["unix"] - 2:
            network_source = "netlog_h2"
            media = sum(r["encoded_bytes"] for r in intervals if
                        rows[0]["unix"] <= r["start_unix"] <= r["end_unix"] <= rows[-1]["unix"])
    checks = {"duration": elapsed >= minimum, "clock": abs(elapsed - wall) <= 2,
              "eligible": eligible_seconds >= minimum, "progress": progress >= 0.98,
              "quality": (result["target_height_ratio"] or 0) >= 0.95,
              "sampling_gaps": result["sampling_gap_seconds"] <= 5,
              "events": result["lost_media_events"] == 0,
              "rate": all(r["playback_rate"] == 1 for r in rows if eligible(r, video)),
              "media_bytes": media >= 1024 * 1024,
              "seek": not require_seek or seek_found}
    failed = [name for name, passed in checks.items() if not passed]
    return {"ok": not failed, "player_ok": all(k == "media_bytes" for k in failed),
            "failed_checks": failed, "required_seconds": minimum,
            "samples": len(rows),
            "measured_seconds": elapsed, "wall_seconds": wall, "eligible_seconds": eligible_seconds,
            "progress_ratio": progress, "target_height_ratio": result["target_height_ratio"],
            "sampling_gap_seconds": result["sampling_gap_seconds"],
            "estimated_stall_seconds": result["estimated_stall_seconds"],
            "network_source": network_source, "network_media_bytes": media,
            "seek_observed": seek_found,
            "route_verdict": "UNKNOWN"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--minimum-seconds", type=int, required=True)
    parser.add_argument("--require-seek", action="store_true")
    parser.add_argument("--seek-min-forward", type=int,
                        help="Require a jump of at least this many seconds outside the last buffer")
    parser.add_argument("--netlog", type=Path)
    parser.add_argument("--media-output", type=Path, help="New private JSONL of media intervals")
    args = parser.parse_args()
    if args.media_output and not args.netlog:
        parser.error("--media-output requires --netlog")
    if args.seek_min_forward is not None and args.seek_min_forward < 1:
        parser.error("--seek-min-forward must be positive")
    netlog = None
    if args.netlog:
        try:
            netlog = read_media(args.netlog)
            if args.media_output:
                fd = os.open(args.media_output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    for row in netlog[0]:
                        stream.write(json.dumps(row, allow_nan=False) + "\n")
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            netlog = False
    try:
        result = evaluate(shadow.load_samples(args.capture), args.video,
                          args.minimum_seconds, args.require_seek,
                          minimum_jump=args.seek_min_forward, netlog=netlog)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        result = {"ok": False, "error": "invalid_or_missing_telemetry", "route_verdict": "UNKNOWN"}
    print(json.dumps(result, allow_nan=False))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

