"""Dormant AQ contracts. Session provenance is cooperative, never runtime authority."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field


class ObservationRefused(ValueError):
    pass


def require(value):
    if not value:
        raise ObservationRefused("OBSERVATION_ARGUMENT")


def integer(value, lower, upper):
    return type(value) is int and lower <= value <= upper


@dataclass(frozen=True)
class SourceSpec:
    scope_id: str
    source_id: str
    domain: str
    target: tuple
    profile: str = "AQ1"

    def __post_init__(self):
        require(type(self) is SourceSpec and self.profile == "AQ1")
        require(
            all(type(v) is str for v in (self.scope_id, self.source_id, self.domain, self.profile))
        )
        require(type(self.target) is tuple and all(type(x) is str for x in self.target))
        require((self.scope_id, self.source_id, self.domain, self.target) in SPEC_ROWS)


SPEC_ROWS = (
    ("COLLECTOR_CONTEXT", "CONTEXT", "PROCESSES", ()),
    ("UNIT_XGW", "UNIT", "PROCESSES", ("xgw.service",)),
    ("UNIT_XRAY", "UNIT", "PROCESSES", ("xgw-xray.service",)),
    ("UNIT_SINGBOX", "UNIT", "PROCESSES", ("xgw-singbox.service",)),
    ("PROCESS_XGW", "PROCESS", "PROCESSES", ("UNIT_XGW",)),
    ("PROCESS_XRAY", "PROCESS", "PROCESSES", ("UNIT_XRAY",)),
    ("PROCESS_SINGBOX", "PROCESS", "PROCESSES", ("UNIT_SINGBOX",)),
    ("NFT_IPV4", "NFT_TABLE", "KERNEL", ("ip", "xgw")),
    ("NFT_IPV6", "NFT_TABLE", "KERNEL", ("ip6", "xgw6")),
    ("NFT_GUARD", "NFT_TABLE", "KERNEL", ("inet", "xgw_guard")),
)
SPECS = tuple(SourceSpec(*row) for row in SPEC_ROWS)
SCOPES = tuple(s.scope_id for s in SPECS)
STATUSES = (
    "COMPLETE",
    "NOT_COLLECTED",
    "TIMEOUT",
    "ERROR",
    "OUTPUT_LIMIT",
    "BUDGET",
    "BLOCKED_SCOPE_REVIEW",
    "INCONSISTENT",
)
REASONS = (
    "OBSERVED",
    "SOURCE_NOT_COLLECTED",
    "QUERY_FAILED",
    "TIMEOUT",
    "OUTPUT_LIMIT",
    "BUDGET",
    "BLOCKED_SCOPE_REVIEW",
    "CLEANUP_UNCONFIRMED",
    "CONTEXT_CHANGED",
    "UNSUPPORTED_FORMAT",
    "INVALID_PAYLOAD",
    "ABSENCE_UNPROVEN",
    "EXPECTED_MISSING",
    "SCOPED_MATCH",
    "SCOPED_MISMATCH",
    "PROVENANCE_UNBOUND",
    "BINDING_CHANGED",
    "EVIDENCE_STALE",
    "CLOCK_INVALID",
    "COLLECTION_INCOMPLETE",
    "COVERAGE_INCOMPLETE",
    "PROCESS_UNBOUND",
    "PID_NOT_PRESENT",
    "PERMISSION_DENIED",
    "IMPORT_UNTRUSTED",
)
DECISIONS = ("MATCH", "MISMATCH", "UNKNOWN", "UNSUPPORTED")
PROVENANCES = ("FIXTURE", "SESSION_CAPTURED", "IMPORTED_UNTRUSTED")


@dataclass(frozen=True)
class CapturePolicy:
    child_seconds: int = 5
    total_seconds: int = 30
    stdout_bytes: int = 1048576
    stderr_bytes: int = 16384
    proc_bytes: int = 8192
    total_bytes: int = 4194304
    max_age_seconds: int = 30

    def __post_init__(self):
        require(type(self) is CapturePolicy)
        for value, ceiling in zip(
            (
                self.child_seconds,
                self.total_seconds,
                self.stdout_bytes,
                self.stderr_bytes,
                self.proc_bytes,
                self.total_bytes,
                self.max_age_seconds,
            ),
            (5, 30, 1048576, 16384, 8192, 4194304, 30),
            strict=True,
        ):
            require(integer(value, 1, ceiling))


@dataclass(frozen=True)
class SourceResult:
    collection: str = "NOT_COLLECTED"
    raw: bytes = b""
    rc: int | None = None
    reason: str = "SOURCE_NOT_COLLECTED"
    cleanup_confirmed: bool = True

    def __post_init__(self):
        require(type(self) is SourceResult)
        require(type(self.collection) is str and self.collection in STATUSES)
        require(type(self.raw) is bytes and len(self.raw) <= 1048576)
        require(self.rc is None or integer(self.rc, -255, 255))
        require(type(self.reason) is str and self.reason in REASONS)
        require(type(self.cleanup_confirmed) is bool)
        require(self.collection != "COMPLETE" or (self.rc in (None, 0) and self.raw))


@dataclass(frozen=True)
class Coverage:
    scope_id: str
    kind: str = "STRUCTURAL_SUBSET"
    domain_complete: bool = field(default=False, init=False)
    global_complete: bool = field(default=False, init=False)

    def __post_init__(self):
        require(type(self) is Coverage and type(self.scope_id) is str and self.scope_id in SCOPES)
        require(type(self.kind) is str and self.kind in ("STRUCTURAL_SUBSET", "PROCESS_SUBSET"))


@dataclass(frozen=True)
class Decoded:
    status: str
    canonical: bytes = b""
    reason: str = "UNSUPPORTED_FORMAT"

    def __post_init__(self):
        require(
            type(self) is Decoded
            and type(self.status) is str
            and self.status in ("COMPLETE", "UNSUPPORTED", "INVALID")
        )
        require(type(self.canonical) is bytes and len(self.canonical) <= 1048576)
        require(type(self.reason) is str and self.reason in REASONS)


@dataclass(frozen=True)
class ObservationEvidence:
    scope_id: str
    provenance: str
    result: SourceResult
    decoded: Decoded
    begun: float
    ended: float
    sequence: int
    coverage: Coverage

    def __post_init__(self):
        require(
            type(self) is ObservationEvidence
            and type(self.scope_id) is str
            and self.scope_id in SCOPES
        )
        require(type(self.provenance) is str and self.provenance in PROVENANCES)
        require(type(self.result) is SourceResult and type(self.decoded) is Decoded)
        require(type(self.coverage) is Coverage and self.coverage.scope_id == self.scope_id)
        require(integer(self.sequence, 1, 128))
        require(
            all(type(v) is float and math.isfinite(v) and v >= 0 for v in (self.begun, self.ended))
        )
        require(self.ended >= self.begun)


@dataclass(frozen=True)
class ObservationDecision:
    scope_id: str
    provenance: str
    collection: str
    decode: str
    decision: str
    coverage: str
    reason: str
    source_rc: int | None = None
    elapsed_ms: int | None = None
    runtime_authorized: bool = field(default=False, init=False)

    def __post_init__(self):
        require(
            type(self) is ObservationDecision
            and type(self.scope_id) is str
            and self.scope_id in SCOPES
        )
        require(type(self.provenance) is str and self.provenance in PROVENANCES)
        require(type(self.collection) is str and self.collection in STATUSES)
        require(type(self.decode) is str and self.decode in ("COMPLETE", "UNSUPPORTED", "INVALID"))
        require(type(self.decision) is str and self.decision in DECISIONS)
        require(type(self.reason) is str and self.reason in REASONS)
        require(self.coverage in ("STRUCTURAL_SUBSET", "PROCESS_SUBSET"))
        require(self.source_rc is None or integer(self.source_rc, -255, 255))
        require(self.elapsed_ms is None or integer(self.elapsed_ms, 0, 2**63 - 1))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def strict_json(raw, *, cap=1048576):
    require(type(raw) is bytes and integer(cap, 1, 1048576) and len(raw) <= cap)
    # Bound lexical nesting before invoking the recursive stdlib decoder.
    depth = tokens = 0
    quoted = escaped = False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            tokens += 1
            require(depth <= 32 and tokens <= 8192)
        elif byte in (93, 125):
            depth -= 1
            require(depth >= 0)

    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out)
            out[key] = value
        return out

    def reject(_):
        raise ObservationRefused("OBSERVATION_ARGUMENT")

    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ObservationRefused("OBSERVATION_ARGUMENT") from exc
    require(not quoted and depth == 0)

    # Overflowing JSON floats (1e999) are nonfinite without parse_constant.
    def finite(value):
        if type(value) is float:
            require(math.isfinite(value))
        elif type(value) is dict:
            for child in value.values():
                finite(child)
        elif type(value) is list:
            for child in value:
                finite(child)

    finite(result)
    return result


def project_public(decision):
    require(type(decision) is ObservationDecision)
    decision.__post_init__()
    return {
        "schema_version": 1,
        "source_id": next(s.source_id for s in SPECS if s.scope_id == decision.scope_id),
        **{
            name: getattr(decision, name)
            for name in (
                "scope_id",
                "provenance",
                "collection",
                "decode",
                "decision",
                "coverage",
                "reason",
                "source_rc",
                "elapsed_ms",
            )
        },
        "runtime_authorized": False,
    }
