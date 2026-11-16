"""Persist verified direct playback observations for T07/T08 shadow decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

from ..paths import LockTimeout, atomic_write_json, file_lock
from .experiment import LABEL, SHA256, TTL, digest, private_path

SCHEMA = 2
MEASUREMENT_VERSION = 2
LIMIT = 512
MAX_BYTES = 512 * 1024
SCOPES = ("context_id", "prefix_context_id", "host_context_id")
HASH_FIELDS = (*SCOPES, "recording_id")
LABEL_FIELDS = ("candidate", "round")
FIELDS = {*HASH_FIELDS, *LABEL_FIELDS, "started", "finished", "outcome"}
TMP_NAME = re.compile(r"\.playback-shadow\.json\.\d+\.\d+\.tmp")


def _timestamp(value: object) -> bool:
    return type(value) in (int, float) and 0 < value < 1e11


def validate_rows(rows: object) -> list[dict]:
    if not isinstance(rows, list) or len(rows) > LIMIT:
        raise ValueError("history_size")
    seen = set()
    current = []
    for row in rows:
        if not isinstance(row, dict) or set(row) not in (FIELDS, FIELDS | {"measurement_version"}):
            raise ValueError("invalid_observation")
        version = row.get("measurement_version", 1)
        if (type(version) is not int or version not in (1, MEASUREMENT_VERSION)
                or ("measurement_version" in row and version != MEASUREMENT_VERSION)
                or any(not isinstance(row[k], str) or not SHA256.fullmatch(row[k])
                       for k in HASH_FIELDS)
                or any(not isinstance(row[k], str) or not LABEL.fullmatch(row[k])
                       for k in LABEL_FIELDS)
                or not _timestamp(row["started"]) or not _timestamp(row["finished"])
                or not 0 < row["finished"] - row["started"] <= 3600
                or row["outcome"] not in ("pass", "playback_failed")):
            raise ValueError("invalid_observation")
        if version == MEASUREMENT_VERSION:
            if row["recording_id"] in seen:
                raise ValueError("invalid_observation")
            seen.add(row["recording_id"])
            current.append(row)
    return current


def _read(path: Path) -> bytes:
    private_path(path)
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("file_size")
    return raw


def read_history(path: Path) -> tuple[list[dict], str]:
    raw = _read(path)
    return validate_rows(json.loads(raw)), hashlib.sha256(raw).hexdigest()


def _recent(rows: list[dict], now: float) -> list[dict]:
    return [row for row in rows if now - TTL < row["finished"] <= now]


def _window(rows: list[dict]) -> dict | None:
    recent = sorted(rows, key=lambda r: r["finished"], reverse=True)[:2]
    if len(recent) != 2:
        return None
    newest, older = recent
    if (newest["finished"] == older["finished"] or newest["started"] <= older["finished"]
            or newest["round"] == older["round"]
            or (newest["outcome"], older["outcome"]) != ("pass", "pass")):
        return None
    return {"last_success": newest["finished"], "expires": older["finished"] + TTL}


def build(rows: list[dict], revision: str, now: float) -> dict:
    groups = defaultdict(list)
    for row in _recent(rows, now):
        groups[row["context_id"], row["candidate"]].append(row)
    exact = {}
    for (context, candidate), group in sorted(groups.items()):
        window = _window(group)
        if window:
            exact.setdefault(context, {})[candidate] = window
    payload = {"schema": SCHEMA, "revision": revision, "built": now, "exact": exact}
    return {"snapshot": payload, "sha256": digest(payload)}


def lookup(snapshot: dict, revision: str, context: str, now: float) -> dict:
    result = {"candidates": [], "apply": False}
    payload = snapshot.get("snapshot") if isinstance(snapshot, dict) else None
    if (not isinstance(payload, dict) or payload.get("schema") != SCHEMA
            or digest(payload) != snapshot.get("sha256")):
        return {"state": "invalid_snapshot", **result}
    built = payload.get("built")
    if payload.get("revision") != revision:
        return {"state": "stale_history", **result}
    if not _timestamp(built) or not built <= now < built + TTL:
        return {"state": "stale_clock", **result}
    exact = payload.get("exact")
    group = exact.get(context, {}) if isinstance(exact, dict) else None
    if not isinstance(group, dict) or len(group) > LIMIT // 2:
        return {"state": "invalid_snapshot", **result}
    for candidate, window in sorted(group.items()):
        if not LABEL.fullmatch(candidate) or not isinstance(window, dict):
            return {"state": "invalid_snapshot", "candidates": [], "apply": False}
        seen, expires = window.get("last_success"), window.get("expires")
        if (not _timestamp(seen) or not _timestamp(expires)
                or not seen <= built < expires <= seen + TTL):
            return {"state": "invalid_snapshot", "candidates": [], "apply": False}
        if now < expires:
            result["candidates"].append({"candidate": candidate, "expires": expires})
    return {"state": "hit" if result["candidates"] else "miss", **result}


def compare(rows: list[dict]) -> dict:
    """Score earlier, independent rounds against held-out addresses and outcomes."""
    counts = {scope: Counter(dict.fromkeys(
        ("with_history", "correct_hit", "false_hit", "abstained_pass", "abstained_fail"), 0))
        for scope in ("exact", "prefix_other_ip", "host_other_ip", "host_other_prefix")}
    by_host = defaultdict(list)
    for row in rows:
        by_host[row["host_context_id"], row["candidate"]].append(row)
    for held in rows:
        history = by_host[held["host_context_id"], held["candidate"]]
        past = [row for row in _recent(history, held["started"])
                if row["finished"] < held["started"] and row["round"] != held["round"]]
        exact = [row for row in past if row["context_id"] == held["context_id"]]
        other = [row for row in past if row["context_id"] != held["context_id"]]
        prefix = [row for row in other if row["prefix_context_id"] == held["prefix_context_id"]]
        other_prefix = [row for row in other
                        if row["prefix_context_id"] != held["prefix_context_id"]]
        for scope, prior in (("exact", exact), ("prefix_other_ip", prefix),
                             ("host_other_ip", other), ("host_other_prefix", other_prefix)):
            counter = counts[scope]
            if prior:
                counter["with_history"] += 1
            if _window(prior):
                counter["correct_hit" if held["outcome"] == "pass" else "false_hit"] += 1
            else:
                counter["abstained_pass" if held["outcome"] == "pass" else "abstained_fail"] += 1
    return {
        "observations": len(rows), "endpoints": len({r["context_id"] for r in rows}),
        "prefixes": len({r["prefix_context_id"] for r in rows}), "scopes": counts,
        "state": "measured" if any(c["correct_hit"] or c["false_hit"]
                                   for k, c in counts.items() if k != "exact") else "inconclusive",
        "apply": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("rebuild", "lookup", "compare"):
        action = sub.add_parser(command)
        action.add_argument("--history", type=Path, required=True)
        if command != "compare":
            action.add_argument("--state-dir", type=Path, required=True)
        if command == "lookup":
            action.add_argument("--context", required=True)
    args = parser.parse_args()
    try:
        if os.name != "posix":
            raise ValueError("real_linux_required")
        if args.command == "compare":
            rows, _ = read_history(args.history)
            report = compare(rows)
        else:
            private_path(args.state_dir, directory=True)
            snapshot = args.state_dir / "playback-shadow.json"
            if args.command == "rebuild":
                with file_lock(args.state_dir / ".playback-shadow.lock", timeout=3, mode=0o600):
                    rows, revision = read_history(args.history)
                    state = build(rows, revision, time.time())
                    for entry in args.state_dir.glob(".playback-shadow.json.*.tmp"):
                        if TMP_NAME.fullmatch(entry.name):
                            entry.unlink()
                    atomic_write_json(snapshot, state, mode=0o600)
                report = {"state": "rebuilt", "contexts": len(state["snapshot"]["exact"]),
                          "apply": False}
            else:
                if not SHA256.fullmatch(args.context):
                    raise ValueError("context")
                _, revision = read_history(args.history)
                try:
                    state = json.loads(_read(snapshot))
                except FileNotFoundError:
                    state = build([], revision, time.time())
                report = lookup(state, revision, args.context, time.time())
        print(json.dumps(report, sort_keys=True))
        return 0
    except (OSError, ValueError, LockTimeout, RecursionError):
        print('{"state":"input_or_storage_error","apply":false,"candidates":[]}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
