"""Dormant callback coordinator. No existing runtime entrypoint uses it.

Verification is supplied by the caller. Named checks are assertions, not implemented
kernel/API verifiers. This module cannot qualify or authorize a live recovery.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from .ownership import OUTCOMES, Refused

CHECKS = frozenset({"FILES", "KERNEL", "API", "PROCESSES", "MODE", "ROUTES", "MARKERS"})


@dataclass(frozen=True)
class Verification:
    outcome: str = "UNKNOWN"
    checks: tuple = ()

    def accepted(self):
        if type(self.outcome) is not str or self.outcome not in OUTCOMES:
            return False
        if type(self.checks) is not tuple or not 0 < len(self.checks) <= len(CHECKS):
            return False
        names = set()
        for row in self.checks:
            if (
                type(row) is not tuple
                or len(row) != 2
                or type(row[0]) is not str
                or row[0] not in CHECKS
                or row[0] in names
                or row[1] is not True
            ):
                return False
            names.add(row[0])
        return True


@dataclass(frozen=True)
class Execution:
    status: str
    reason: str
    operation_entered: bool = False
    verification_entered: bool = False
    completion_attempted: bool = False
    unknown_recorded: bool = False
    retained_receipt: bool | None = None
    cleanup: str = "NOT_NEEDED"
    runtime_verifier_implemented: bool = False


def record_unknown(registry, token):
    """Keep best-effort bookkeeping separate from the operation's original failure."""
    try:
        registry.unknown(token)
        return True, "UNKNOWN_RECORDED"
    except Exception:
        return False, "UNKNOWN_RECORD_UNCONFIRMED"


def execute(registry, role, operation, verifier):
    """Admit before callback; never hold the registry flock across a domain operation.

    An unsuccessful acknowledgement never authorizes mutation retry. Terminal signals
    preserve a blocking ticket best-effort and are re-raised. Product outcome mapping,
    concrete resource verifiers and entrypoint integration remain separate work.
    """
    try:
        token = registry.admit(role)
    except Refused:
        return Execution("REFUSED", "ADMISSION_REFUSED")
    verification_entered = False
    completion_attempted = False
    phase = "OPERATION_RAISED"
    try:
        value = operation()
        verification_entered = True
        phase = "VERIFIER_RAISED"
        decision = verifier(value)
        if type(decision) is not Verification or not decision.accepted():
            recorded, cleanup = record_unknown(registry, token)
            return Execution(
                "UNKNOWN",
                "VERIFICATION_REFUSED",
                True,
                True,
                unknown_recorded=recorded,
                cleanup=cleanup,
            )
        completion_attempted = True
        phase = "COMPLETION_UNCERTAIN"
        registry.complete(token, outcome=decision.outcome, verified=True)
        return Execution(
            "COMPLETED", "CALLER_ASSERTION_RECORDED", True, True, True, retained_receipt=True
        )
    except BaseException as exc:
        recorded, cleanup = record_unknown(registry, token)
        if not isinstance(exc, Exception):
            raise
        receipt = None
        if completion_attempted:
            with contextlib.suppress(Exception):
                receipt = registry.receipt(token) is not None
        return Execution(
            "UNKNOWN",
            phase,
            True,
            verification_entered,
            completion_attempted,
            recorded,
            receipt,
            cleanup,
        )
