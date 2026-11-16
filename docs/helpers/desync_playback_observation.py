"""Build a private shadow-cache observation from a verified real Chrome trial."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
from pathlib import Path

from docs.helpers.youtube_telemetry import number, summarize
from xgw.desync import cache, experiment, shadow

MIN_PLAYBACK = 120
TARGET_HEIGHT = 720
METADATA = {"hostname", "address", "network", "protocol", "client", "client_sha256",
            "policy_sha256", "candidate", "round", "video_id", "verified_direct_single_endpoint"}


def observation(raw: bytes, metadata: object) -> dict:
    if (not isinstance(metadata, dict) or set(metadata) != METADATA
            or metadata["verified_direct_single_endpoint"] is not True):
        raise ValueError("route_and_endpoint_evidence_required")
    if any(not isinstance(metadata[k], str) for k in METADATA - {
            "verified_direct_single_endpoint"}):
        raise ValueError("invalid_metadata")
    for key in ("network", "client", "candidate", "round"):
        if not experiment.LABEL.fullmatch(metadata[key]):
            raise ValueError("invalid_label")
    if any(not experiment.SHA256.fullmatch(metadata[key]) for key in (
            "client_sha256", "policy_sha256")):
        raise ValueError("invalid_revision")
    host = metadata["hostname"].lower()
    address = ipaddress.ip_address(metadata["address"])
    video = metadata["video_id"]
    if (not re.fullmatch(r"[a-z0-9.-]{1,253}\.googlevideo\.com", host)
            or not address.is_global or "%" in metadata["address"]
            or metadata["protocol"] not in ("h1", "h2", "h3")
            or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video)):
        raise ValueError("invalid_media_endpoint")

    rows = shadow.parse_samples(raw)
    signals = shadow.evaluate(rows, video)
    if not all(number(rows[i].get("unix")) for i in (0, -1)):
        raise ValueError("missing_trial_clock")
    started, finished = rows[0]["unix"], rows[-1]["unix"]
    measured = rows[-1]["t_s"] - rows[0]["t_s"]
    if measured < MIN_PLAYBACK or abs(finished - started - measured) > 2:
        raise ValueError("insufficient_trial_clock")
    coverage = signals["phase_seconds"]
    if sum(coverage.get(phase, 0) for phase in ("missing", "gap", "no_continuous_player")) > 5:
        raise ValueError("missing_trial_coverage")
    playback = summarize(rows, video, TARGET_HEIGHT)
    if signals["signals"]:
        outcome = "playback_failed"
    elif playback["eligible_seconds"] >= MIN_PLAYBACK:
        outcome = ("pass" if playback["target_height_ratio"] >= 0.95
                   and playback["estimated_playing_seconds"] >= playback["eligible_seconds"] * 0.98
                   and playback["estimated_stall_seconds"] < 1
                   else "playback_failed")
    else:
        raise ValueError("insufficient_playback")

    row = {**experiment.context_keys(host, metadata, metadata["client_sha256"]),
           "recording_id": hashlib.sha256(raw).hexdigest(),
           "candidate": metadata["candidate"], "round": metadata["round"],
           "started": started, "finished": finished, "outcome": outcome}
    return cache.validate_rows([row])[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    args = parser.parse_args()
    try:
        if os.name != "posix":
            raise ValueError("real_linux_required")
        experiment.private_path(args.capture)
        experiment.private_path(args.metadata)
        with args.capture.open("rb") as capture, args.metadata.open("rb") as context:
            raw = capture.read(shadow.MAX_BYTES + 1)
            encoded = context.read(8193)
        if len(encoded) > 8192:
            raise ValueError("metadata_size")
        print(json.dumps(observation(raw, json.loads(encoded)), sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, OverflowError, RecursionError):
        print('{"state":"observation_unavailable"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
