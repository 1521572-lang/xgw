"""Build a private shadow-cache observation from a verified real Chrome trial."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import sys
from pathlib import Path

from docs.helpers.youtube_telemetry import number, summarize
from xgw.desync import cache, experiment, shadow

MIN_PLAYBACK = 120
TARGET_HEIGHT = 720
METADATA = {"hostname", "address", "network", "protocol", "client", "client_sha256",
            "policy_sha256", "candidate", "round", "video_id", "verified_direct_single_endpoint"}


class ObservationError(ValueError):
    """A reason safe to show without private input."""


def observation(raw: bytes, metadata: object, *, diagnostics: dict | None = None) -> dict:
    if (not isinstance(metadata, dict) or set(metadata) != METADATA
            or metadata["verified_direct_single_endpoint"] is not True):
        raise ObservationError("route_and_endpoint_evidence_required")
    if any(not isinstance(metadata[k], str) for k in METADATA - {
            "verified_direct_single_endpoint"}):
        raise ObservationError("invalid_metadata")
    for key in ("network", "client", "candidate", "round"):
        if not experiment.LABEL.fullmatch(metadata[key]):
            raise ObservationError("invalid_label")
    if any(not experiment.SHA256.fullmatch(metadata[key]) for key in (
            "client_sha256", "policy_sha256")):
        raise ObservationError("invalid_revision")
    host = metadata["hostname"].lower()
    address = ipaddress.ip_address(metadata["address"])
    video = metadata["video_id"]
    if (not re.fullmatch(r"[a-z0-9.-]{1,253}\.googlevideo\.com", host)
            or not address.is_global or "%" in metadata["address"]
            or metadata["protocol"] not in ("h1", "h2", "h3")
            or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video)):
        raise ObservationError("invalid_media_endpoint")

    rows = shadow.parse_samples(raw)
    signals = shadow.evaluate(rows, video)
    if any(sample.get("has_video") is True and sample.get("video_id") == video
           and sample.get("playback_rate") != 1 for sample in rows):
        raise ObservationError("playback_rate_mismatch")
    if not all(number(rows[i].get("unix")) for i in (0, -1)):
        raise ObservationError("missing_trial_clock")
    started, finished = rows[0]["unix"], rows[-1]["unix"]
    measured = rows[-1]["t_s"] - rows[0]["t_s"]
    if measured < MIN_PLAYBACK or abs(finished - started - measured) > 2:
        raise ObservationError("insufficient_trial_clock")
    coverage = signals["phase_seconds"]
    if diagnostics is not None:
        diagnostics.update(
            samples=signals["samples"], measured_seconds=measured, phase_seconds=coverage,
            starvation_thresholds=[s["threshold_seconds"] for s in signals["signals"]],
        )
    if sum(coverage.get(phase, 0) for phase in ("missing", "gap", "no_continuous_player")) > 5:
        raise ObservationError("missing_trial_coverage")
    playback = summarize(rows, video, TARGET_HEIGHT)
    eligible = playback["eligible_seconds"]
    if diagnostics is not None:
        diagnostics.update({key: playback[key] for key in (
            "eligible_seconds", "target_height_ratio", "content_progress_seconds",
            "estimated_playing_seconds", "estimated_stall_seconds")})
    if signals["signals"]:
        outcome, reason = "playback_failed", "confirmed_starvation"
    elif eligible < MIN_PLAYBACK:
        raise ObservationError("insufficient_playback")
    elif playback["target_height_ratio"] < 0.95:
        outcome, reason = "playback_failed", "low_target_height_ratio"
    elif playback["content_progress_seconds"] < eligible * 0.98:
        # Without a confirmed starvation interval, slow progress alone is ambiguous.
        raise ObservationError("unconfirmed_playback")
    else:
        outcome, reason = "pass", "meets_playback_thresholds"

    row = {"measurement_version": cache.MEASUREMENT_VERSION,
           **experiment.context_keys(host, metadata, metadata["client_sha256"]),
           "recording_id": hashlib.sha256(raw).hexdigest(),
           "candidate": metadata["candidate"], "round": metadata["round"],
           "started": started, "finished": finished, "outcome": outcome}
    checked = cache.validate_rows([row])[0]
    if diagnostics is not None:
        diagnostics.update(outcome=outcome, reason=reason)
    return checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--diagnostics", action="store_true",
                        help="report measurement and outcome reason on stderr")
    args = parser.parse_args()
    details = {} if args.diagnostics else None
    exit_code = 0
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
        row = observation(raw, json.loads(encoded), diagnostics=details)
        print(json.dumps(row, sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError, OverflowError, RecursionError) as exc:
        print('{"state":"observation_unavailable"}')
        exit_code = 2
        if details is not None:
            details["reason"] = str(exc) if isinstance(exc, ObservationError) else "invalid_input"
    if details is not None:
        print(json.dumps(details, sort_keys=True), file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
