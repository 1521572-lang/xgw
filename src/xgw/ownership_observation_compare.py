"""Session-local AQ comparisons. Scoped evidence never authorizes runtime completion."""

from __future__ import annotations

import math
import os
import threading
import time
from dataclasses import dataclass
from types import FunctionType

from . import ownership_observation_sources as sources
from . import ownership_observations as types
from .ownership_adapters import Verification


@dataclass(frozen=True)
class ExpectedState:
    scope_id: str
    canonical: bytes
    profile: str = "AQ1"
    origin: str = "FIXTURE"

    def __post_init__(self):
        types.require(type(self) is ExpectedState and self.scope_id in types.SCOPES)
        types.require(type(self.canonical) is bytes and 0 < len(self.canonical) <= 1048576)
        types.require(self.profile == "AQ1" and self.origin in ("FIXTURE", "DECLARED"))
        # Input must already be deterministic JSON; no learning baseline from collect.
        types.require(types.canonical(types.strict_json(self.canonical)) == self.canonical)


def methods():
    """Cooperative method/code/default identity pin, not a full globals/deep-state seal."""
    result = []
    for cls in (
        ReadonlyObservationSession,
        sources.FixtureBackend,
        sources.LinuxReadonlyBackend,
        ExpectedState,
        types.CapturePolicy,
        types.SourceResult,
        types.Decoded,
        types.ObservationEvidence,
        types.ObservationDecision,
        types.Coverage,
    ):
        for name, value in vars(cls).items():
            if type(value) is FunctionType:
                result.append(
                    (cls, name, value, value.__code__, value.__defaults__, value.__kwdefaults__)
                )
    for module in (types, sources):
        for name, value in vars(module).items():
            if type(value) is FunctionType and value.__module__ == module.__name__:
                result.append(
                    (module, name, value, value.__code__, value.__defaults__, value.__kwdefaults__)
                )
    return tuple(result)


class ReadonlyObservationSession:
    def __init__(self, policy, backend, *, clock_values=None, expected_states=()):
        types.require(
            type(self) is ReadonlyObservationSession and type(policy) is types.CapturePolicy
        )
        types.require(type(backend) in (sources.FixtureBackend, sources.LinuxReadonlyBackend))
        policy.__post_init__()
        if type(backend) is sources.FixtureBackend:
            backend.__post_init__()
        else:
            types.require(backend.policy is policy)
        types.require(
            clock_values is None
            or (
                type(clock_values) is tuple
                and 2 <= len(clock_values) <= 256
                and all(type(v) is float and math.isfinite(v) and v >= 0 for v in clock_values)
            )
        )
        types.require(type(expected_states) is tuple and len(expected_states) <= 10)
        types.require(all(type(e) is ExpectedState for e in expected_states))
        types.require(len({e.scope_id for e in expected_states}) == len(expected_states))
        for e in expected_states:
            e.__post_init__()
        self.policy, self.backend = policy, backend
        self.clock_values = clock_values
        self._clock_index = 0
        self._pid, self._thread = os.getpid(), threading.get_ident()
        self._ledger = []
        self._busy = self._finalized = False
        self._last_clock = None
        self._used = 0
        self._begin = None
        self._contexts = {}
        self._context_valid = None
        self._terminal = False
        self._latest = {}
        self._snapshots = {}
        self._expected = tuple((e, tuple(vars(e).items())) for e in expected_states)
        self._config = (
            policy,
            backend,
            clock_values,
            backend.entries if type(backend) is sources.FixtureBackend else policy,
        )
        self._pins = methods()
        self._clock_provider = time.monotonic
        self._policy_values = tuple(vars(policy).items())
        self._backend_rows = (
            tuple(
                (scope, phase, result, tuple(vars(result).items()))
                for scope, phase, result in backend.entries
            )
            if type(backend) is sources.FixtureBackend
            else ()
        )

    def _validate(self):
        types.require(type(self) is ReadonlyObservationSession)
        types.require((os.getpid(), threading.get_ident()) == (self._pid, self._thread))
        types.require(not self._terminal)
        types.require(self.policy is self._config[0] and self.backend is self._config[1])
        types.require(self.clock_values is self._config[2])
        types.require(tuple(vars(self.policy).items()) == self._policy_values)
        types.require(time.monotonic is self._clock_provider)
        types.require(
            not (set(vars(self)) & {name for cls, name, *_ in self._pins if cls is type(self)})
        )
        for owner, name, fn, code, defaults, kwdefaults in self._pins:
            types.require(getattr(owner, name) is fn and fn.__code__ is code)
            types.require(fn.__defaults__ is defaults and fn.__kwdefaults__ is kwdefaults)
        if type(self.backend) is sources.FixtureBackend:
            types.require(
                self.backend.entries is self._config[3]
                and not set(vars(self.backend)) - {"entries"}
            )
            for scope, phase, result, values in self._backend_rows:
                types.require(
                    any(
                        s == scope and p == phase and r is result
                        for s, p, r in self.backend.entries
                    )
                )
                types.require(tuple(vars(result).items()) == values)
        else:
            types.require(
                self.backend.policy is self.policy and set(vars(self.backend)) == {"policy"}
            )

    def _now(self):
        if self.clock_values is None:
            value = self._clock_provider()
        else:
            types.require(self._clock_index < len(self.clock_values))
            value = self.clock_values[self._clock_index]
            self._clock_index += 1
        types.require(type(value) is float and math.isfinite(value) and value >= 0)
        types.require(self._last_clock is None or value >= self._last_clock)
        self._last_clock = value
        return value

    def collect_once(self, scope_id, phase="SINGLE"):
        # Invoke the pinned class validator, not an instance-shadowable self.validate.
        _VALIDATE(self)
        spec = sources.spec_for(scope_id)
        types.require(type(phase) is str and phase in sources.PHASES)
        types.require(not self._busy and not self._finalized and len(self._ledger) < 32)
        types.require((scope_id, phase) not in self._contexts)
        self._busy = True
        try:
            begun = self._now()
            if self._begin is None:
                self._begin = begun
            if (
                begun - self._begin >= self.policy.total_seconds
                or self._used >= self.policy.total_bytes
            ):
                result = types.SourceResult(collection="BUDGET", reason="BUDGET")
            else:
                result = self.backend.capture(scope_id, phase)
                types.require(type(result) is types.SourceResult)
                result.__post_init__()
                self._used += len(result.raw)
                cap = (
                    self.policy.stdout_bytes
                    if spec.source_id == "NFT_TABLE"
                    else self.policy.proc_bytes
                )
                if len(result.raw) > cap or self._used > self.policy.total_bytes:
                    result = types.SourceResult(collection="OUTPUT_LIMIT", reason="OUTPUT_LIMIT")
            ended = self._now()
            if ended - self._begin > self.policy.total_seconds:
                result = types.SourceResult(collection="BUDGET", reason="BUDGET")
            if not result.cleanup_confirmed:
                self._terminal = True
            decoded = sources.decode(spec, result)
            coverage = types.Coverage(
                scope_id, "STRUCTURAL_SUBSET" if spec.source_id == "NFT_TABLE" else "PROCESS_SUBSET"
            )
            evidence = types.ObservationEvidence(
                scope_id,
                "FIXTURE" if type(self.backend) is sources.FixtureBackend else "IMPORTED_UNTRUSTED",
                result,
                decoded,
                begun,
                ended,
                len(self._ledger) + 1,
                coverage,
            )
            self._ledger.append((evidence, result, decoded, coverage, phase))
            self._snapshots[id(evidence)] = (
                scope_id,
                evidence.provenance,
                begun,
                ended,
                evidence.sequence,
                tuple(vars(result).items()),
                tuple(vars(decoded).items()),
                tuple(vars(coverage).items()),
            )
            self._contexts[(scope_id, phase)] = evidence
            self._latest[scope_id] = evidence
            return evidence
        except BaseException:
            self._terminal = True
            raise
        finally:
            self._busy = False

    def finalize(self):
        _VALIDATE(self)
        types.require(not self._busy and not self._finalized)
        self._finalized = True
        pair = tuple(self._contexts.get(("COLLECTOR_CONTEXT", p)) for p in ("BEFORE", "AFTER"))
        self._context_valid = all(e is not None and e.decoded.status == "COMPLETE" for e in pair)
        if self._context_valid:
            self._context_valid = pair[0].decoded.canonical == pair[1].decoded.canonical
        for spec in types.SPECS:
            if spec.source_id not in ("UNIT", "PROCESS"):
                continue
            before, after = (self._contexts.get((spec.scope_id, p)) for p in ("BEFORE", "AFTER"))
            if before is not None or after is not None:
                # Any partial bookend invalidates binding, not the raw collection fact.
                equal = (
                    before is not None
                    and after is not None
                    and all(e.decoded.status == "COMPLETE" for e in (before, after))
                    and before.decoded.canonical == after.decoded.canonical
                )
                if not equal:
                    self._context_valid = False
            if spec.source_id == "PROCESS" and before is not None and after is not None:
                unit_pair = tuple(
                    self._contexts.get((spec.target[0], p)) for p in ("BEFORE", "AFTER")
                )
                if any(u is None or u.decoded.status != "COMPLETE" for u in unit_pair):
                    self._context_valid = False
                elif before.decoded.status == after.decoded.status == "COMPLETE":
                    pids = [types.strict_json(u.decoded.canonical)["MainPID"] for u in unit_pair]
                    observed = [
                        types.strict_json(p.decoded.canonical)["pid"] for p in (before, after)
                    ]
                    if pids[0] == 0 or pids != observed:
                        self._context_valid = False
        return self._context_valid

    def compare_scoped(self, evidence, expected=None):
        _VALIDATE(self)
        types.require(type(evidence) is types.ObservationEvidence)
        evidence.__post_init__()
        status, reason = "UNKNOWN", "PROVENANCE_UNBOUND"
        owned = next((row for row in self._ledger if row[0] is evidence), None)
        now = self._now()
        snapshot = (
            evidence.scope_id,
            evidence.provenance,
            evidence.begun,
            evidence.ended,
            evidence.sequence,
            tuple(vars(evidence.result).items()),
            tuple(vars(evidence.decoded).items()),
            tuple(vars(evidence.coverage).items()),
        )
        if (
            owned
            and snapshot == self._snapshots[id(evidence)]
            and evidence.result is owned[1]
            and evidence.decoded is owned[2]
            and evidence.coverage is owned[3]
        ):
            if self._latest[evidence.scope_id] is not evidence:
                reason = "BINDING_CHANGED"
            elif now - evidence.ended > self.policy.max_age_seconds:
                reason = "EVIDENCE_STALE"
            elif evidence.result.collection != "COMPLETE":
                reason = evidence.result.reason
            elif not self._finalized or not self._context_valid:
                reason = "CONTEXT_CHANGED"
            elif evidence.decoded.status != "COMPLETE":
                status, reason = "UNSUPPORTED", evidence.decoded.reason
            elif expected is None:
                reason = "EXPECTED_MISSING"
            else:
                types.require(type(expected) is ExpectedState)
                expected.__post_init__()
                pinned = next((values for e, values in self._expected if e is expected), None)
                if (
                    pinned is None
                    or tuple(vars(expected).items()) != pinned
                    or expected.scope_id != evidence.scope_id
                ):
                    reason = "BINDING_CHANGED"
                elif evidence.provenance != "FIXTURE" or expected.origin != "FIXTURE":
                    status, reason = "UNSUPPORTED", "PROVENANCE_UNBOUND"
                else:
                    status = (
                        "MATCH" if expected.canonical == evidence.decoded.canonical else "MISMATCH"
                    )
                    reason = "SCOPED_MATCH" if status == "MATCH" else "SCOPED_MISMATCH"
        return types.ObservationDecision(
            evidence.scope_id,
            evidence.provenance,
            evidence.result.collection,
            evidence.decoded.status,
            status,
            evidence.coverage.kind,
            reason,
            evidence.result.rc,
            int((evidence.ended - evidence.begun) * 1000),
        )

    def runtime_verification(self):
        return Verification()


_VALIDATE = ReadonlyObservationSession._validate


def imported_evidence(raw):
    """Decode only a public projection. Imported JSON can never reconstruct a handle."""
    row = types.strict_json(raw, cap=8192)
    expected_keys = {
        "schema_version",
        "scope_id",
        "source_id",
        "provenance",
        "collection",
        "decode",
        "decision",
        "coverage",
        "reason",
        "source_rc",
        "elapsed_ms",
        "runtime_authorized",
    }
    types.require(type(row) is dict and set(row) == expected_keys)
    types.require(type(row["schema_version"]) is int and row["schema_version"] == 1)
    types.require(row["runtime_authorized"] is False)
    spec = sources.spec_for(row["scope_id"])
    types.require(row["source_id"] == spec.source_id)
    # Validate supplied enum/type fields, then discard asserted provenance/decision.
    types.ObservationDecision(
        **{
            k: v
            for k, v in row.items()
            if k not in ("schema_version", "source_id", "runtime_authorized")
        }
    )
    return types.ObservationDecision(
        spec.scope_id,
        "IMPORTED_UNTRUSTED",
        "NOT_COLLECTED",
        "INVALID",
        "UNKNOWN",
        "STRUCTURAL_SUBSET" if spec.source_id == "NFT_TABLE" else "PROCESS_SUBSET",
        "IMPORT_UNTRUSTED",
    )


def aggregate_scoped(decisions):
    types.require(type(decisions) is tuple and len(decisions) <= 32)
    types.require(all(type(d) is types.ObservationDecision for d in decisions))
    types.require(len({d.scope_id for d in decisions}) == len(decisions))
    for d in decisions:
        d.__post_init__()
    # No AQ source has domain/global completeness. Never promote scoped matches.
    return "UNKNOWN", "COVERAGE_INCOMPLETE", decisions
