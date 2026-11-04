"""Explicit source composition: build identity, nine actors and named FILES.

No existing startup calls this module. No discovery, ownership attachment, registry
creation, installation, recovery or kernel/API qualification. Legacy callers remain
outside this boundary. Sequential build checks do not eliminate filesystem TOCTOU.
"""

from __future__ import annotations

import inspect
import os
import threading
from dataclasses import dataclass
from types import FunctionType, MappingProxyType

from .ownership import Registry
from .ownership_adapters import Verification
from .ownership_binding import SPECS, BoundWriters
from .ownership_completion import FileCompletion
from .ownership_hooks import MutationBlocked
from .ownership_surface import CodePreflight, PreflightEvidence, function_state, same_state


def require(value, code):
    if not value:
        raise MutationBlocked(code)


def intact(obj, functions):
    for name, fn in functions.items():
        method = getattr(obj, name, None)
        require(
            getattr(method, "__self__", None) is obj
            and getattr(method, "__func__", None) is fn
            and same_state(METHOD_STATES[fn], function_state(fn)),
            "COMPOSITION_METHOD_DRIFT",
        )


@dataclass(frozen=True)
class GateEvidence:
    phase: str = "NOT_OBSERVED"
    matched: bool | None = None
    source_checked: int | None = None
    units_checked: int | None = None
    surface_checked: int | None = None


class BuildCompletion:
    """Unsealed verifier refuses; explicit Composition seals an existing boundary.

    Constructors/seal do no filesystem I/O. A code-bound registry must share the
    exact CodeIdentity object with the preflight. This is a cooperative contract,
    not independent attestation that a supplied digest describes executing code.
    """

    def __init__(self, registry, preflight, files):
        require(
            type(registry) is Registry
            and type(preflight) is CodePreflight
            and type(files) is FileCompletion,
            "COMPOSITION_ARGUMENT",
        )
        self.registry, self.preflight, self.files = registry, preflight, files
        self._providers = (registry, preflight, files)
        self._identity = preflight.identity
        self._registry_policy = (
            registry.directory,
            registry.boot_id,
            registry.expected_uid,
            registry.clock_ns,
            registry.lock_budget,
        )
        self._pid, self._thread = os.getpid(), threading.get_ident()
        self._binding = None
        self._sealed_binding = None
        self._active = self._tainted = False
        self.observations = 0
        self.last = GateEvidence()
        intact(self, GATE_METHODS)
        self.validate(bound=False)

    def validate(self, *, bound=True):
        intact(self, GATE_METHODS)
        require(
            self._pid == os.getpid()
            and self._thread == threading.get_ident()
            and all(
                a is b
                for a, b in zip(
                    self._providers, (self.registry, self.preflight, self.files), strict=True
                )
            ),
            "COMPOSITION_CONTEXT",
        )
        intact(self.registry, REGISTRY_METHODS)
        intact(self.preflight, PREFLIGHT_METHODS)
        intact(self.files, FILE_METHODS)
        self.registry.code_context()
        self.preflight.validate()
        self.files.validate()
        require(
            (
                self.registry.directory,
                self.registry.boot_id,
                self.registry.expected_uid,
                self.registry.clock_ns,
                self.registry.lock_budget,
            )
            == self._registry_policy
            and type(self.registry.expected_uid) is int
            and self.files.contract.domains == ("FILES",),
            "COMPOSITION_POLICY",
        )
        require(
            self.registry.code_identity is self.preflight.identity is self._identity
            and self.registry._state_schema == 2,
            "COMPOSITION_CODE_IDENTITY",
        )
        if bound:
            b = self._binding
            require(type(b) is BoundWriters and b is self._sealed_binding, "COMPOSITION_UNSEALED")
            intact(b, BINDING_METHODS)
            b.validate()
            require(
                b.registry is self.registry
                and b.verifier is self
                and b.coordinator.verifier is self,
                "COMPOSITION_BINDING",
            )

    def seal(self, binding):
        self.validate(bound=False)
        require(self._binding is None and type(binding) is BoundWriters, "COMPOSITION_SEAL")
        intact(binding, BINDING_METHODS)
        binding.validate()
        require(
            binding.registry is self.registry
            and binding.verifier is self
            and binding.coordinator.verifier is self,
            "COMPOSITION_BINDING",
        )
        self._binding = binding
        self._sealed_binding = binding
        self.validate()

    def checkpoint(self, phase):
        require(
            type(phase) is str and phase in PHASES,
            "COMPOSITION_PHASE",
        )
        self.last = GateEvidence(phase)
        intact(self, GATE_METHODS)
        self.validate()
        self.observations += 1
        evidence = self.preflight.observe()
        self.validate()
        require(type(evidence) is PreflightEvidence, "COMPOSITION_EVIDENCE")
        self.last = GateEvidence(
            phase,
            evidence.matched,
            evidence.source_checked,
            evidence.units_checked,
            evidence.surface_checked,
        )
        require(
            evidence.matched is True
            and evidence.source_matched
            is evidence.units_matched
            is evidence.surface_matched
            is True
            and evidence.source_checked == len(self.preflight.source.expectations)
            and evidence.units_checked == len(self.preflight.units.expectations)
            and evidence.surface_checked == 65
            and evidence.runtime_fence_verified is False,
            "COMPOSITION_BUILD_REFUSED",
        )

    def __call__(self, roles, value):
        if self._active:
            self._tainted = True
            raise MutationBlocked("COMPOSITION_REENTRANT")
        self._active, self._tainted = True, False
        try:
            self.checkpoint("VERIFY_BEFORE_FILES")
            result = self.files(roles, value)
            self.checkpoint("VERIFY_AFTER_FILES")
            require(not self._tainted, "COMPOSITION_TAINTED")
            require(type(result) is Verification and result.accepted(), "COMPOSITION_FILES_REFUSED")
            return result
        except Exception:
            return Verification()
        finally:
            self._active = False


class Composition:
    """Seal once; never create/repair actors, paths or ownership references."""

    def __init__(self, binding):
        require(type(binding) is BoundWriters, "COMPOSITION_ARGUMENT")
        self.binding = self._binding = binding
        self.gate = self._gate = binding.verifier
        require(type(self.gate) is BuildCompletion, "COMPOSITION_VERIFIER")
        intact(self, COMPOSITION_METHODS)
        intact(self.gate, GATE_METHODS)
        self._pid, self._thread = os.getpid(), threading.get_ident()
        self.gate.seal(binding)
        self.validate()

    def validate(self):
        intact(self, COMPOSITION_METHODS)
        require(
            self._pid == os.getpid()
            and self._thread == threading.get_ident()
            and self.binding is self._binding
            and self.gate is self._gate
            and self.gate._binding is self.binding,
            "COMPOSITION_CONTEXT",
        )
        intact(self.gate, GATE_METHODS)
        self.gate.validate()

    def prepare(self, steps, *, accept):
        self.validate()
        require(
            type(accept) is FunctionType
            and not inspect.iscoroutinefunction(accept)
            and not inspect.isgeneratorfunction(accept)
            and not inspect.isasyncgenfunction(accept),
            "COMPOSITION_CHECKER",
        )
        self.binding.validate_steps(steps, accept)
        require(
            {"LIFECYCLE", *(SPECS[s.writer][1] for s in steps)} <= self.gate.files.contract.roles,
            "COMPOSITION_ROLE_CONTRACT",
        )
        return PreparedComposition(self, steps, accept)


class PreparedComposition:
    """One process-local attempt. Not durable replay protection or a transaction."""

    def __init__(self, composition, steps, accept):
        self.composition, self.steps, self.accept = composition, steps, accept
        self._policy = (composition, steps, accept)
        self._checker = function_state(accept)
        self.used = False

    def validate(self):
        intact(self, PREPARED_METHODS)
        require(
            all(
                a is b
                for a, b in zip(
                    self._policy, (self.composition, self.steps, self.accept), strict=True
                )
            )
            and same_state(self._checker, function_state(self.accept)),
            "COMPOSITION_PLAN_DRIFT",
        )
        self.composition.validate()
        self.composition.binding.validate_steps(self.steps, self.accept)

    def run(self):
        require(not self.used, "COMPOSITION_ALREADY_USED")
        self.used = True

        def check():
            intact(self, PREPARED_METHODS)
            self.validate()

        check()
        c, g = self.composition.binding.coordinator, self.composition.gate
        require(getattr(c.local, "session", None) is None, "COMPOSITION_NESTING")
        g.checkpoint("PRE_ADMISSION")

        def operation():
            check()
            g.checkpoint("INSIDE_ADMISSION")
            values = []
            for step in self.steps:
                check()
                g.checkpoint("BEFORE_STEP")
                actor = self.composition.binding.actors[step.writer]
                value = getattr(actor, step.method)(*step.args, **dict(step.kwargs))
                check()
                g.checkpoint("AFTER_STEP")
                require(self.accept(step, value) is True, "COMPOSITION_RESULT")
                check()
                g.checkpoint("AFTER_CHECKER")
                values.append(value)
            return tuple(values)

        return c.call("LIFECYCLE", operation)


PHASES = frozenset(
    {
        "PRE_ADMISSION",
        "INSIDE_ADMISSION",
        "BEFORE_STEP",
        "AFTER_STEP",
        "AFTER_CHECKER",
        "VERIFY_BEFORE_FILES",
        "VERIFY_AFTER_FILES",
    }
)
REGISTRY_METHODS = MappingProxyType(
    {
        n: getattr(Registry, n)
        for n in (
            "code_context",
            "admit",
            "unknown",
            "complete",
            "receipt",
            "locked",
            "validate",
            "commit",
            "writer_token",
            "check_writer_token",
            "read",
            "lock_identity",
        )
    }
)
PREFLIGHT_METHODS = MappingProxyType(
    {n: getattr(CodePreflight, n) for n in ("observe", "validate")}
)
FILE_METHODS = MappingProxyType({n: getattr(FileCompletion, n) for n in ("__call__", "validate")})
BINDING_METHODS = MappingProxyType(
    {n: getattr(BoundWriters, n) for n in ("validate", "validate_steps", "prepare")}
)
GATE_METHODS = MappingProxyType(
    {n: getattr(BuildCompletion, n) for n in ("validate", "seal", "checkpoint", "__call__")}
)
COMPOSITION_METHODS = MappingProxyType(
    {n: getattr(Composition, n) for n in ("validate", "prepare")}
)
PREPARED_METHODS = MappingProxyType(
    {n: getattr(PreparedComposition, n) for n in ("validate", "run")}
)
METHOD_STATES = {
    fn: function_state(fn)
    for table in (
        REGISTRY_METHODS,
        PREFLIGHT_METHODS,
        FILE_METHODS,
        BINDING_METHODS,
        GATE_METHODS,
        COMPOSITION_METHODS,
        PREPARED_METHODS,
    )
    for fn in table.values()
}
