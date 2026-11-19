"""Check measured playback duration and quality; route evidence remains independent."""
from __future__ import annotations

import argparse
import json
from itertools import pairwise
from pathlib import Path

from docs.helpers.youtube_telemetry import number, summarize
from xgw.desync import shadow


def evaluate(rows, video, minimum, require_seek=False):
    if not 120 <= minimum <= 1800 or not rows:
        raise ValueError("duration_or_samples")
    seek_found = False
    if require_seek:
        for index, row in enumerate(rows):
            if row.get("video_id") == video and not row.get("ad") and any(
                isinstance(e, dict) and e.get("name") == "seeked"
                and e.get("media_id") == row.get("media_id") and not e.get("ad")
                for e in row.get("events", [])
            ):
                rows, seek_found = rows[index:], True
                break
    if any(not number(row.get(k)) for row in rows for k in ("unix", "t_s")):
        raise ValueError("missing_clock")
    if any(b["t_s"] <= a["t_s"] for a, b in pairwise(rows)):
        raise ValueError("non_monotonic_clock")
    elapsed = rows[-1]["t_s"] - rows[0]["t_s"]
    wall = rows[-1]["unix"] - rows[0]["unix"]
    result = summarize(rows, video, 720)
    eligible = result["eligible_seconds"]
    progress = result["content_progress_seconds"] / eligible if eligible else 0
    counters = [(r.get("network") or {}).get("encoded_bytes") for r in (rows[0], rows[-1])]
    media = (counters[1] - counters[0] if all(number(v) for v in counters)
             and counters[1] >= counters[0] else 0)
    checks = {"duration": elapsed >= minimum, "clock": abs(elapsed - wall) <= 2,
              "eligible": eligible >= minimum, "progress": progress >= 0.98,
              "quality": (result["target_height_ratio"] or 0) >= 0.95,
              "sampling_gaps": result["sampling_gap_seconds"] <= 5,
              "events": result["lost_media_events"] == 0, "media_bytes": media >= 1024 * 1024,
              "seek": not require_seek or seek_found}
    failed = [name for name, passed in checks.items() if not passed]
    return {"ok": not failed, "failed_checks": failed, "required_seconds": minimum,
            "samples": len(rows),
            "measured_seconds": elapsed, "wall_seconds": wall, "eligible_seconds": eligible,
            "progress_ratio": progress, "target_height_ratio": result["target_height_ratio"],
            "sampling_gap_seconds": result["sampling_gap_seconds"],
            "estimated_stall_seconds": result["estimated_stall_seconds"],
            "network_media_bytes": media, "seek_observed": seek_found,
            "route_verdict": "UNKNOWN"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--minimum-seconds", type=int, required=True)
    parser.add_argument("--require-seek", action="store_true")
    args = parser.parse_args()
    try:
        result = evaluate(shadow.load_samples(args.capture), args.video,
                          args.minimum_seconds, args.require_seek)
    except (OSError, ValueError, TypeError, KeyError):
        result = {"ok": False, "error": "invalid_or_missing_telemetry", "route_verdict": "UNKNOWN"}
    print(json.dumps(result, allow_nan=False))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

