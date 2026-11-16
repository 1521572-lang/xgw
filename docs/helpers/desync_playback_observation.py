"""Build a private cache or tournament observation from a verified Chrome trial."""

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
from xgw.desync import cache, experiment, shadow, tournament

MIN_PLAYBACK = 120
TARGET_HEIGHT = 720
SHARED = {"network", "client", "client_sha256", "policy_sha256", "candidate", "round", "video_id"}
ENDPOINT_FIELDS = {"hostname", "address", "protocol"}
SINGLE_PROOF = "verified_direct_single_endpoint"
TOURNAMENT_PROOF = "verified_direct_all_endpoints"


class ObservationError(ValueError):
    """A reason safe to show without private input."""


def _endpoint(value: object) -> tuple[str, str, str]:
    if (not isinstance(value, dict) or set(value) != ENDPOINT_FIELDS
            or any(not isinstance(value[key], str) for key in ENDPOINT_FIELDS)):
        raise ObservationError("invalid_media_endpoint")
    host, address, protocol = value["hostname"].lower(), value["address"], value["protocol"]
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        raise ObservationError("invalid_media_endpoint") from None
    if (not re.fullmatch(r"[a-z0-9.-]{1,253}\.googlevideo\.com", host)
            or not ip.is_global or "%" in address or protocol not in ("h1", "h2", "h3")):
        raise ObservationError("invalid_media_endpoint")
    return host, str(ip), protocol


def _context(metadata: object, for_tournament: bool) -> dict:
    proof = TOURNAMENT_PROOF if for_tournament else SINGLE_PROOF
    fields = {"endpoints"} if for_tournament else ENDPOINT_FIELDS
    if (not isinstance(metadata, dict) or set(metadata) != SHARED | fields | {proof}
            or metadata[proof] is not True):
        raise ObservationError("route_and_endpoint_evidence_required")
    if any(not isinstance(metadata[k], str) for k in SHARED):
        raise ObservationError("invalid_metadata")
    for key in ("network", "client", "candidate", "round"):
        if not experiment.LABEL.fullmatch(metadata[key]):
            raise ObservationError("invalid_label")
    if any(not experiment.SHA256.fullmatch(metadata[key]) for key in (
            "client_sha256", "policy_sha256")):
        raise ObservationError("invalid_revision")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", metadata["video_id"]):
        raise ObservationError("invalid_video_id")

    if not for_tournament:
        host, _, _ = _endpoint({key: metadata[key] for key in ENDPOINT_FIELDS})
        return experiment.context_keys(host, metadata, metadata["client_sha256"])

    values = metadata["endpoints"]
    if not isinstance(values, list) or not 1 <= len(values) <= tournament.MAX_ENDPOINTS:
        raise ObservationError("invalid_endpoint_count")
    endpoints = sorted({_endpoint(value) for value in values})
    if len(endpoints) != len(values):
        raise ObservationError("duplicate_media_endpoint")
    shared = {k: metadata[k] for k in SHARED - {"candidate", "round"}}
    protocols = sorted({entry[2] for entry in endpoints})
    playback_context = experiment.digest(["t09-playback", shared, protocols])
    return {"playback_context_id": playback_context, "endpoint_count": len(endpoints),
            "context_id": experiment.digest([playback_context, endpoints])}


def observation(raw: bytes, metadata: object, *, diagnostics: dict | None = None,
                for_tournament: bool = False) -> dict:
    context = _context(metadata, for_tournament)
    video = metadata["video_id"]

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
           **context,
           "recording_id": hashlib.sha256(raw).hexdigest(),
           "candidate": metadata["candidate"], "round": metadata["round"],
           "started": started, "finished": finished, "outcome": outcome}
    if for_tournament:
        tournament.validate_observation(row)
    else:
        cache.validate_rows([row])
    if diagnostics is not None:
        diagnostics.update(outcome=outcome, reason=reason)
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--diagnostics", action="store_true",
                        help="report measurement and outcome reason on stderr")
    parser.add_argument("--tournament", action="store_true",
                        help="accept a verified CDN endpoint set for T09, outside shadow cache")
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
        row = observation(raw, json.loads(encoded), diagnostics=details,
                          for_tournament=args.tournament)
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
