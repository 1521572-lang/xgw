"""Plan and replay the T09 six-cell YouTube strategy experiment."""

from __future__ import annotations

import argparse
import json
import math
import os
from itertools import pairwise
from pathlib import Path

from ..paths import LockTimeout, atomic_write_json, file_lock
from . import cache, experiment

TRIAL_SECONDS = 300
DEFAULT_BUDGET = 3600
PROFILES = {
    "multisplit": ("split", "none"),
    "multidisorder": ("disorder", "none"),
    "fake_md5_split": ("split", "md5"),
    "fake_seq": ("disorder", "seq"),
    "fake_seq_split": ("split", "seq"),
    "fake_md5": ("disorder", "md5"),
}
ORDER = tuple(PROFILES)
ROUNDS = ("t09-1", "t09-2")
SLOTS = tuple((name, strategy)
              for name, sequence in zip(ROUNDS, (ORDER, reversed(ORDER)), strict=True)
              for strategy in sequence)
FIELDS = {"round", "candidate", "elapsed_seconds", "observation"}


def validate_ledger(value: object) -> list[dict]:
    if not isinstance(value, list) or len(value) > len(SLOTS):
        raise ValueError("ledger_size")
    observations = []
    for row, (round_id, candidate) in zip(value, SLOTS, strict=False):
        if (not isinstance(row, dict) or set(row) != FIELDS
                or (row["round"], row["candidate"]) != (round_id, candidate)):
            raise ValueError("unexpected_trial")
        elapsed = row["elapsed_seconds"]
        if type(elapsed) not in (int, float) or not 0 < elapsed <= 86400:
            raise ValueError("invalid_elapsed")
        observation = row["observation"]
        if observation is None:
            continue
        if (not isinstance(observation, dict)
                or elapsed > TRIAL_SECONDS
                or observation.get("round") != round_id
                or observation.get("candidate") != candidate):
            raise ValueError("observation_mismatch")
        observations.append(observation)
    if len(cache.validate_rows(observations)) != len(observations):
        raise ValueError("obsolete_measurement")
    for older, newer in pairwise(observations):
        if older["finished"] > newer["started"]:
            raise ValueError("overlapping_observations")
    return value


def next_trial(ledger: list[dict], budget: int, cancelled: bool) -> dict:
    remaining = max(0, budget - sum(row["elapsed_seconds"] for row in ledger))
    if cancelled:
        state = "cancelled"
    elif len(ledger) == len(SLOTS):
        state = "complete"
    elif remaining < TRIAL_SECONDS:
        state = "budget"
    else:
        state = "ready"
    trial = None
    if state == "ready":
        round_id, candidate = SLOTS[len(ledger)]
        trial = {"round": round_id, "candidate": candidate, "limit_seconds": TRIAL_SECONDS}
    return {"state": state, "done": len(ledger), "total": len(SLOTS),
            "remaining_seconds": math.floor(remaining), "trial": trial, "apply": False}


def _score(order: tuple, rows: dict, winners: set) -> dict:
    elapsed, first = 0.0, None
    for candidate in order:
        elapsed += rows[candidate]["elapsed_seconds"]
        if first is None and candidate in winners:
            first = round(elapsed, 3)
    return {"order": list(order), "attempts": len(order), "seconds": round(elapsed, 3),
            "first_pass_seconds": first, "winners": sorted(winners.intersection(order))}


def _replay(rows: list[dict]) -> dict:
    by_candidate = {row["candidate"]: row for row in rows if row["observation"] is not None}
    contexts = {row["observation"]["context_id"] for row in by_candidate.values()}
    if len(by_candidate) != len(ORDER) or len(contexts) != 1:
        state = "mixed_context" if len(contexts) > 1 else "incomplete"
        return {"state": state, "accepted": len(by_candidate),
                "contexts": len(contexts), "missing": sorted(set(ORDER) - by_candidate.keys())}
    winners = {name for name, row in by_candidate.items()
               if row["observation"]["outcome"] == "pass"}
    bases = ORDER[:2]
    promising = {PROFILES[name][0] for name in bases if name in winners}
    # If neither unmodified geometry passed, the policy falls back to the entire grid.
    keep = tuple(name for name in ORDER if name in bases or not promising
                 or PROFILES[name][0] in promising)
    full, pruned = _score(ORDER, by_candidate, winners), _score(keep, by_candidate, winners)
    return {"state": "compared", "accepted": len(ORDER), "full": full, "pruned": pruned,
            "estimated_seconds_saved": round(full["seconds"] - pruned["seconds"], 3),
            "missed_winners": sorted(winners.difference(keep))}


def summarize(ledger: list[dict]) -> dict:
    windows = {round_id: _replay([row for row in ledger if row["round"] == round_id])
               for round_id in ROUNDS}
    compared = [window for window in windows.values() if window["state"] == "compared"]
    contexts = {row["observation"]["context_id"] for row in ledger if row["observation"]}
    repeated = None
    if len(compared) == len(ROUNDS) and len(contexts) == 1:
        first, second = compared
        repeated = sorted(set(first["full"]["winners"]) & set(second["full"]["winners"]))
    return {"windows": windows, "observed_attempt_seconds": round(
                sum(row["elapsed_seconds"] for row in ledger), 3),
            "repeatable_winners": repeated, "apply": False}


def _load(path: Path) -> object:
    experiment.private_path(path)
    with path.open("rb") as source:
        raw = source.read(32769)
    if len(raw) > 32768:
        raise ValueError("input_size")
    return json.loads(raw)


def _record(path: Path, row_path: Path) -> list[dict]:
    with file_lock(path.with_name(f".{path.name}.lock"), timeout=3, mode=0o600):
        ledger = validate_ledger(_load(path))
        updated = validate_ledger([*ledger, _load(row_path)])
        atomic_write_json(path, updated, mode=0o600)
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "next", "record", "report"):
        action = sub.add_parser(name)
        if name != "plan":
            action.add_argument("--ledger", required=True, type=Path)
        if name in ("next", "record"):
            action.add_argument("--budget-seconds", type=int, default=DEFAULT_BUDGET)
            action.add_argument("--cancel-file", type=Path)
        if name == "record":
            action.add_argument("--row", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            output = [
                {"round": round_id, "candidate": candidate, "geometry": PROFILES[candidate][0],
                 "fooling": PROFILES[candidate][1]} for round_id, candidate in SLOTS
            ]
        else:
            if os.name != "posix":
                raise ValueError("real_linux_required")
            if args.command == "report":
                output = summarize(validate_ledger(_load(args.ledger)))
            else:
                if args.budget_seconds <= 0:
                    raise ValueError("invalid_budget")
                if args.command == "record":
                    experiment.private_path(args.ledger.parent, directory=True)
                    ledger = _record(args.ledger, args.row)
                else:
                    ledger = validate_ledger(_load(args.ledger))
                cancelled = args.cancel_file is not None and args.cancel_file.exists()
                output = next_trial(ledger, args.budget_seconds, cancelled)
        print(json.dumps(output, indent=2))
        return 0
    except (OSError, ValueError, LockTimeout, RecursionError):
        print('{"state":"invalid_tournament_input","apply":false}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
