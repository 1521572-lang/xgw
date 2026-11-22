"""Wait for the current XGW process to publish its first completed watchdog step."""

from __future__ import annotations

import json
import os
import stat
import sys
import time
from pathlib import Path

PROGRESS = Path("/run/xgw/watchdog-step.json")
FATAL_STATES = {"invalid_snapshot", "invalid_format", "unexpected_mode"}


def progress_state(path: Path, minimum_generation: int, now: float,
                   *, require_details: bool = False, require_provider: bool = False,
                   require_scan_slot: bool = False) -> str:
    try:
        with path.open("rb") as stream:
            if stat.S_IMODE(os.fstat(stream.fileno()).st_mode) != 0o600:
                return "unexpected_mode"
            row = json.load(stream)
    except FileNotFoundError:
        return "not_written"
    except OSError:
        return "unreadable"
    except ValueError:
        return "invalid_snapshot"

    if not isinstance(row, dict):
        return "invalid_format"
    generation = row.get("generation")
    if type(generation) is not int or generation <= 0:
        return "invalid_format"
    if generation < minimum_generation:
        return "previous_generation"
    at, phase = row.get("at"), row.get("phase")
    if type(at) not in (int, float) or phase not in ("tick", "sleep"):
        return "invalid_format"
    if not 0 <= now - at <= 180:
        return "stale_snapshot"
    if "last_step" not in row or "wake" not in row:
        return "invalid_format"
    if row["wake"] is not None and not isinstance(row["wake"], dict):
        return "invalid_format"
    step = row["last_step"]
    if step is None and phase == "tick":
        return "waiting_first_step"
    if not isinstance(step, dict):
        return "invalid_format"
    sequence, started, completed = (step.get(key) for key in ("sequence", "started", "completed_at"))
    if (type(sequence) is not int or sequence <= 0 or type(started) not in (int, float)
            or type(completed) not in (int, float)
            or not generation / 1e9 <= started <= completed <= at
            or not isinstance(step.get("parts_s"), dict)):
        return "invalid_format"
    if (require_details or require_provider or require_scan_slot) and (
            not isinstance(step.get("details_s"), dict)
            or type(step.get("planned_scan_deferred")) is not bool):
        return "invalid_format"
    if require_provider or require_scan_slot:
        attempts = step.get("provider_attempts")
        if type(attempts) is not int or attempts < 0:
            return "invalid_format"
    if require_scan_slot:
        count = step.get("queue_probe_count")
        if type(count) is not int or count < 0 or type(step.get("scan_deferred_for_step")) is not bool:
            return "invalid_format"
    return "ready"


def wait_progress(path: Path, minimum_generation: int, seconds: float,
                  *, require_details: bool = False,
                  require_provider: bool = False,
                  require_scan_slot: bool = False) -> tuple[str, int, bool]:
    deadline = time.monotonic() + seconds
    attempts = 0
    saw_first_step = False
    while True:
        state = progress_state(path, minimum_generation, time.monotonic(),
                               require_details=require_details, require_provider=require_provider,
                               require_scan_slot=require_scan_slot)
        attempts += 1
        saw_first_step |= state == "waiting_first_step"
        remaining = deadline - time.monotonic()
        if state == "ready" or state in FATAL_STATES or remaining <= 0:
            return state, attempts, saw_first_step
        time.sleep(min(1.0, remaining))


if __name__ == "__main__":
    if (len(sys.argv) not in (2, 3) or (len(sys.argv) == 3
                                       and sys.argv[2] not in ("--details", "--provider", "--scan-slot"))
            or not sys.argv[1].isascii() or not sys.argv[1].isdigit()):
        raise SystemExit(2)
    minimum_generation = int(sys.argv[1]) * 1000  # systemd reports monotonic microseconds
    if minimum_generation <= 0:
        raise SystemExit(2)
    mode = sys.argv[2] if len(sys.argv) == 3 else ""
    state, attempts, saw_first_step = wait_progress(
        PROGRESS, minimum_generation, 120,
        require_details=mode == "--details", require_provider=mode == "--provider",
        require_scan_slot=mode == "--scan-slot",
    )
    print(f"WATCHDOG_TIMING_PROGRESS_CHECK result={state} polls={attempts} "
          f"waiting_first_step={str(saw_first_step).lower()}")
    raise SystemExit(0 if state == "ready" else 2)
