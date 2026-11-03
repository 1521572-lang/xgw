"""Dormant bounded read-only registry diagnostics. No repair or pruning actions."""

from __future__ import annotations

import fcntl
import os
import time
from dataclasses import dataclass

from .ownership import Refused

REASONS = frozenset(
    {
        "PRIVATE_METADATA",
        "DIRECTORY_REPLACED",
        "LOCK_REPLACED",
        "LOCK_BUSY",
        "RECORD_LIMIT",
        "DUPLICATE_JSON_KEY",
        "INVALID_JSON",
        "STATE_SCHEMA",
        "STATE_IDENTITY",
        "BOOT_MISMATCH",
        "STATE_INTEGER",
        "STATE_SEQUENCE",
        "WRITER_LIMIT",
        "WRITER_SCHEMA",
        "WRITER_ID",
        "WRITER_VALUES",
        "LEASE_SCHEMA",
        "LEASE_VALUES",
        "LEASE_CLOCK",
        "RECEIPT_LIMIT",
        "RECEIPT_SCHEMA",
        "RECEIPT_VALUES",
        "CODE_IDENTITY_MISMATCH",
        "CODE_CONTEXT_CHANGED",
    }
)


@dataclass(frozen=True)
class Diagnostic:
    status: str
    reason: str
    stage_present: bool | None = None
    baseline_valid: bool = False
    stage_valid: bool | None = None
    writers: int | None = None
    unknown: int | None = None
    receipts: int | None = None
    phase: str = "UNKNOWN"
    repair_authorized: bool = False
    runtime_fence_verified: bool = False


def reason(exc):
    return str(exc) if type(exc) is Refused and str(exc) in REASONS else "STORE_IO_OR_UNSUPPORTED"


def inspect_registry(registry):
    """Read current/staged records under a bounded lock without writing any file.

    A valid stage is only structurally related to the baseline, not an authorized
    state transition. This function never promotes, deletes, repairs or releases it.
    """
    stage_present = None
    try:
        directory_fd = registry.open_directory()
        try:
            fd = os.open("lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
            try:
                registry.lock_identity(directory_fd, fd)
                deadline = time.monotonic() + registry.lock_budget
                while True:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise Refused("LOCK_BUSY") from None
                        time.sleep(0.005)
                try:
                    registry.lock_identity(directory_fd, fd)
                    try:
                        os.stat("state.next", dir_fd=directory_fd, follow_symlinks=False)
                        stage_present = True
                    except FileNotFoundError:
                        stage_present = False
                    state = registry.read(directory_fd, "state.json")
                    registry.validate(state)
                    registry.lock_identity(directory_fd, fd, state)
                    counts = {
                        "writers": len(state["writers"]),
                        "unknown": sum(w["phase"] == "UNKNOWN" for w in state["writers"]),
                        "receipts": len(state["receipts"]),
                        "phase": state["lease"]["phase"] if state["lease"] else "IDLE",
                    }
                    if stage_present:
                        try:
                            staged = registry.read(directory_fd, "state.next")
                            registry.validate(staged)
                            related = all(
                                staged[k] == state[k]
                                for k in ("registry_id", "boot_id", "lock_device", "lock_inode")
                            )
                            related = related and staged["revision"] == state["revision"] + 1
                            if not related:
                                return Diagnostic(
                                    "STAGE_UNRELATED",
                                    "MANUAL_REVIEW_REQUIRED",
                                    True,
                                    True,
                                    False,
                                    **counts,
                                )
                        except (OSError, Refused) as exc:
                            return Diagnostic(
                                "STAGE_REFUSED", reason(exc), True, True, False, **counts
                            )
                        return Diagnostic(
                            "STAGE_VALID_UNPROVEN", "NO_AUTOREPAIR", True, True, True, **counts
                        )
                    status = "CLEAN_IDLE"
                    if counts["unknown"]:
                        status = "UNKNOWN_WRITERS"
                    elif counts["writers"]:
                        status = "LIVE_WRITERS"
                    elif state["lease"]:
                        status = "RECOVERY_" + counts["phase"]
                    return Diagnostic(status, "OBSERVED_ONLY", False, True, None, **counts)
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        finally:
            os.close(directory_fd)
    except (OSError, Refused) as exc:
        return Diagnostic("BASELINE_REFUSED", reason(exc), stage_present)
