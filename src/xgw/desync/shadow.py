"""T07 playback watchdog over recorded browser telemetry."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable
from itertools import pairwise
from pathlib import Path

THRESHOLDS = (15, 30, 60)
MAX_BYTES = 16 * 1024 * 1024
MAX_SAMPLES = 4000
MAX_GAP_SECONDS = 2.5
STARTUP_SECONDS = 4
MAX_BUFFER_SECONDS = 1
TRANSITIONS = ("pause", "play", "seeking", "seeked", "ended", "error", "emptied", "loadedmetadata")


def _number(value: object) -> bool:
    return type(value) is int or (type(value) is float and math.isfinite(value))


def load_samples(path: Path) -> list[dict]:
    """Read the ordinary Chrome export or the CDP collector's JSONL."""
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("recording too large")
    if path.suffix == ".jsonl":
        lines = raw.splitlines()
        if len(lines) > MAX_SAMPLES:
            raise ValueError("too many samples")
        return [json.loads(line) for line in lines]
    document = json.loads(raw)
    if not isinstance(document, dict) or not isinstance(document.get("rows"), list):
        raise ValueError("expected a Chrome export with rows")
    if len(document["rows"]) > MAX_SAMPLES:
        raise ValueError("too many samples")
    return document["rows"]


def _context(row: dict, video_id: str) -> tuple | None:
    keys = row.get("document_id"), row.get("media_id")
    if (row.get("has_video") is True and row.get("video_id") == video_id
            and all(_number(key) and key > 0 for key in keys)):
        return keys
    return None


def _state(previous: dict, current: dict, dt: float) -> str:
    events = current.get("events")
    lost = current.get("event_overflow")
    if (not isinstance(events, list) or type(lost) is not int
            or lost != previous.get("event_overflow")
            or any(not isinstance(event, dict) for event in events)):
        return "missing"
    for key in ("ended", "paused", "seeking", "ad", "hidden"):
        if any(type(row.get(key)) is not bool for row in (previous, current)):
            return "missing"
        if previous[key] or current[key]:
            return key
    if "error_code" not in previous or "error_code" not in current:
        return "missing"
    if previous["error_code"] is not None or current["error_code"] is not None:
        return "player_error"
    if any(event.get("name") in TRANSITIONS for event in events):
        return "transition"
    for row in (previous, current):
        if (not _number(row.get("position")) or not 0 <= row["position"] <= 1e8
                or not _number(row.get("playback_rate")) or not 0 < row["playback_rate"] <= 16
                or type(row.get("ready_state")) is not int or not 0 <= row["ready_state"] <= 4
                or not _number(row.get("buffer_seconds")) or row["buffer_seconds"] < 0):
            return "missing"
    delta = current["position"] - previous["position"]
    if delta < 0 or delta > dt * previous["playback_rate"] + 0.5:
        return "discontinuity"
    if delta > 0:
        return "advancing"
    if max(previous["buffer_seconds"], current["buffer_seconds"]) > MAX_BUFFER_SECONDS:
        return "buffered"
    if min(previous["ready_state"], current["ready_state"]) >= 3:
        return "ready"
    if max(previous["ready_state"], current["ready_state"]) >= 3:
        return "transition"
    return "starved"


def _pending(previous: dict, current: dict) -> str:
    rows = (previous.get("network"), current.get("network"))
    if any(not isinstance(row, dict) or type(row.get("inflight")) is not int
           or type(row.get("data_bytes")) is not int or row["data_bytes"] < 0
           or row["inflight"] < 0 for row in rows):
        return "unavailable"
    before, after = rows
    if after["data_bytes"] < before["data_bytes"]:
        return "unavailable"
    if before["data_bytes"] == after["data_bytes"] and before["inflight"] and after["inflight"]:
        return "pending_without_data"
    return "not_continuous"


def evaluate(samples: Iterable[dict], video_id: str) -> dict:
    """Measure post-start starvation. A signal describes playback, with unknown cause."""
    phases: dict[str, float] = defaultdict(float)
    signals = []
    context = stall_start = None
    playing = 0.0
    pending = set()
    reached = 0
    count = 0
    last = -1.0

    def checked():
        nonlocal count, last
        for count, row in enumerate(samples, 1):
            if count > MAX_SAMPLES:
                raise ValueError("too many samples")
            t = row.get("t_s") if isinstance(row, dict) else None
            if not _number(t) or not 0 <= t <= 86400 or t <= last:
                raise ValueError("sample clock must be finite, nonnegative and increasing")
            last = t
            yield row

    for previous, current in pairwise(checked()):
        dt = current["t_s"] - previous["t_s"]
        prior, present = _context(previous, video_id), _context(current, video_id)
        if context != present:
            playing = 0.0
            context = present
        if dt > MAX_GAP_SECONDS:
            phase = "gap"
        elif present is None or present != prior:
            phase = "no_continuous_player"
        else:
            phase = _state(previous, current, dt)
        if phase == "advancing":
            playing += min(dt, (current["position"] - previous["position"])
                           / previous["playback_rate"])
        if phase == "starved" and playing < STARTUP_SECONDS:
            phase = "startup"
        phases[phase] += dt
        if phase != "starved":
            stall_start = None
            continue
        if stall_start is None:
            stall_start = previous["t_s"]
            pending.clear()
            reached = 0
        pending.add(_pending(previous, current))
        duration = current["t_s"] - stall_start
        if reached < len(THRESHOLDS) and duration >= THRESHOLDS[reached]:
            signals.append({"threshold_seconds": THRESHOLDS[reached],
                            "start_s": round(stall_start, 3),
                            "observed_s": round(current["t_s"], 3), "cause": "unknown",
                            "media_network": next(iter(pending)) if len(pending) == 1 else "mixed"})
            reached += 1
    if count < 2:
        raise ValueError("at least two samples are required")
    return {
        "samples": count,
        "phase_seconds": {key: round(value, 3) for key, value in sorted(phases.items())},
        "signals": signals,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path, help="private player.json or samples.jsonl")
    parser.add_argument("--video", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", args.video):
        parser.error("invalid public video ID")
    try:
        report = evaluate(load_samples(args.recording), args.video)
    except (OSError, ValueError):
        parser.error("unreadable recording, malformed rows or invalid sample clock")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
