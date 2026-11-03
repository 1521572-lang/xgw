"""Explicit named-file completion verifier. Dormant; no live runtime wiring.

Only FILES observations are implemented. A contract requiring any other domain
returns UNKNOWN. This cannot qualify a gateway lifecycle or network recovery.
"""

from __future__ import annotations

import inspect
import os
import threading
from dataclasses import dataclass
from types import MappingProxyType

from .ownership import OUTCOMES, ROLES
from .ownership_adapters import CHECKS, Verification
from .ownership_files import FileEvidence, ObservationRefused, PrivateFiles


class CompletionRefused(Exception):
    """Fixed public reason only, no paths or operation values."""


def require(value, reason):
    if not value:
        raise CompletionRefused(reason)


@dataclass(frozen=True)
class CompletionContract:
    # No inferred roles, domains, outcomes or resource expectations.
    roles: frozenset
    domains: tuple
    outcome: str


@dataclass(frozen=True)
class CompletionEvidence:
    reason: str = "NOT_OBSERVED"
    accept_entered: bool = False
    observation_entered: bool = False
    matched: bool | None = None
    checked: int | None = None
    verified: bool = False


OBSERVER_METHODS = MappingProxyType(
    {
        name: getattr(PrivateFiles, name)
        for name in ("observe", "open_root", "directory", "observe_one")
    }
)


class FileCompletion:
    """Check the result, then freshly observe all named files before completion.

    Exact process/thread and observer configuration are pinned at construction.
    Read-only result checkers must explicitly return True. Exceptions, drift,
    incomplete observations and unsupported domains never yield accepted evidence.
    No I/O at construction, cached PASS, retry, compensation or automatic activation.
    A configured FILES-only contract does not prove other operation effects.
    """

    def __init__(self, contract, files, *, accept):
        require(type(contract) is CompletionContract, "CONTRACT_TYPE")
        require(
            type(contract.roles) is frozenset
            and bool(contract.roles)
            and all(type(r) is str and r in ROLES for r in contract.roles),
            "CONTRACT_ROLES",
        )
        require(
            type(contract.domains) is tuple
            and 1 <= len(contract.domains) <= len(CHECKS)
            and all(type(d) is str and d in CHECKS for d in contract.domains)
            and len(set(contract.domains)) == len(contract.domains)
            and "FILES" in contract.domains,
            "CONTRACT_DOMAINS",
        )
        require(type(contract.outcome) is str and contract.outcome in OUTCOMES, "CONTRACT_OUTCOME")
        require(type(files) is PrivateFiles, "OBSERVER_TYPE")
        # Revalidate arguments without I/O: a valid observer may have been changed
        # before it was supplied here (for example to an empty expectation tuple).
        try:
            PrivateFiles(
                files.root, expected_uid=files.expected_uid, expectations=files.expectations
            )
        except ObservationRefused:
            raise CompletionRefused("OBSERVER_POLICY") from None
        require(
            callable(accept)
            and not inspect.iscoroutinefunction(accept)
            and not inspect.isgeneratorfunction(accept)
            and not inspect.isasyncgenfunction(accept),
            "RESULT_CHECKER",
        )
        self.contract = contract
        self.files = files
        self.accept = accept
        self._contract = contract
        self._files = files
        self._accept = accept
        self._file_policy = (files.root, files.expected_uid, files.expectations)
        self._pid = os.getpid()
        self._thread = threading.get_ident()
        self._active = False
        self._tainted = False
        self.last = CompletionEvidence()
        self.validate()

    def validate(self):
        require(
            self._pid == os.getpid() and self._thread == threading.get_ident(), "VERIFIER_CONTEXT"
        )
        require(
            self.contract is self._contract
            and self.files is self._files
            and self.accept is self._accept,
            "VERIFIER_DRIFT",
        )
        files = self.files
        require(
            type(files) is PrivateFiles
            and (files.root, files.expected_uid, files.expectations) == self._file_policy
            and type(files.expected_uid) is int,
            "OBSERVER_DRIFT",
        )
        for name, function in OBSERVER_METHODS.items():
            method = getattr(files, name, None)
            require(
                getattr(method, "__self__", None) is files
                and getattr(method, "__func__", None) is function,
                "OBSERVER_DRIFT",
            )

    def __call__(self, roles, value):
        # Recursion is refused without modifying the outer invocation's diagnostic.
        if self._active:
            self._tainted = True
            raise CompletionRefused("VERIFIER_REENTRANT")
        self.last = CompletionEvidence()
        accepted = observed = False
        matched = checked = None
        self._active = True
        self._tainted = False
        try:
            self.validate()
            require(
                type(roles) is frozenset
                and bool(roles)
                and all(type(r) is str and r in ROLES for r in roles)
                and roles == self.contract.roles,
                "ROLE_COVERAGE",
            )
            require(self.contract.domains == ("FILES",), "DOMAIN_NOT_IMPLEMENTED")
            accepted = True
            require(self.accept(value) is True, "RESULT_NOT_ACCEPTED")
            self.validate()
            require(not self._tainted, "VERIFIER_TAINTED")
            observed = True
            evidence = self.files.observe()
            self.validate()
            require(not self._tainted, "VERIFIER_TAINTED")
            require(type(evidence) is FileEvidence, "OBSERVATION_TYPE")
            matched = evidence.matched if type(evidence.matched) is bool else None
            checked = evidence.checked if type(evidence.checked) is int else None
            require(
                matched is True
                and checked == len(self.files.expectations)
                and evidence.reason == "EXACT_NAMED_FILES_OBSERVED",
                "FILES_NOT_VERIFIED",
            )
            self.last = CompletionEvidence("FILES_VERIFIED", True, True, matched, checked, True)
            return Verification(self.contract.outcome, (("FILES", True),))
        except CompletionRefused as exc:
            self.last = CompletionEvidence(str(exc), accepted, observed, matched, checked)
            return Verification()
        except Exception:
            self.last = CompletionEvidence("CHECK_ERROR", accepted, observed, matched, checked)
            return Verification()
        except BaseException:
            self.last = CompletionEvidence(
                "CHECK_INTERRUPTED", accepted, observed, matched, checked
            )
            raise
        finally:
            self._active = False
