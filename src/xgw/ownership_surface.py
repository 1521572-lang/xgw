"""Declared 50 actor methods + 15 lifecycle functions, and explicit build preflight.

No actor construction, runtime wiring or global call-graph attestation. A local
snapshot pins wrapper code/defaults/closures, not arbitrary module globals.
"""

from __future__ import annotations

import hashlib
import inspect
import math
import os
import re
import threading
from dataclasses import dataclass
from pathlib import PosixPath, PurePosixPath, PureWindowsPath, WindowsPath
from types import FunctionType, MappingProxyType

from . import actions, engine, ownership_binding
from .ownership_binding import SPECS
from .ownership_identity import CodeIdentity, canonical
from .ownership_seal import METHODS as SEAL_METHODS
from .ownership_seal import CodeSeal, SealEvidence


class SurfaceRefused(Exception):
    pass


def require(value, reason):
    if not value:
        raise SurfaceRefused(reason)


def literal(value, depth=0):
    require(depth <= 8, "SURFACE_DEFAULT")
    if value is inspect.Parameter.empty:
        return {"kind": "REQUIRED"}
    if value is None or type(value) in (bool, int, str):
        require(not isinstance(value, str) or len(value) <= 4096, "SURFACE_DEFAULT")
        require(type(value) is not int or value.bit_length() <= 128, "SURFACE_DEFAULT")
        return {"kind": "LITERAL", "value": value}
    if type(value) is float and math.isfinite(value):
        return {"kind": "LITERAL", "value": value}
    if type(value) is tuple and len(value) <= 32:
        return {"kind": "TUPLE", "items": [literal(v, depth + 1) for v in value]}
    if type(value) is FunctionType:
        return {
            "kind": "FUNCTION",
            "module": value.__module__.split(".", 1)[-1],
            "name": value.__qualname__,
        }
    if type(value) in (PosixPath, WindowsPath, PurePosixPath, PureWindowsPath):
        return {"kind": "PATH", "value": value.as_posix()}
    raise SurfaceRefused("SURFACE_DEFAULT")


def function_state(function):
    result, seen = [], set()
    current = function
    while current is not None:
        require(
            type(current) is FunctionType and current not in seen and len(seen) < 8,
            "SURFACE_WRAPPER",
        )
        seen.add(current)
        defaults = (current.__defaults__ or (), current.__kwdefaults__ or {})
        encoded = {
            "args": [literal(v) for v in defaults[0]],
            "kwargs": {k: literal(v) for k, v in defaults[1].items()},
        }
        closure = tuple(c.cell_contents for c in current.__closure__ or ())
        refs = tuple(
            (v, v.__code__)
            for v in (*defaults[0], *defaults[1].values())
            if type(v) is FunctionType
        )
        wrapped = getattr(current, "__wrapped__", None)
        result.append(
            (
                current,
                current.__code__,
                canonical(encoded),
                closure,
                refs,
                wrapped,
                getattr(current, "__signature__", None),
            )
        )
        current = wrapped
    return tuple(result)


def same_state(before, after):
    if len(before) != len(after):
        return False
    for a, b in zip(before, after, strict=True):
        if (
            a[0] is not b[0]
            or a[1] is not b[1]
            or a[2] != b[2]
            or len(a[3]) != len(b[3])
            or any(x is not y for x, y in zip(a[3], b[3], strict=True))
            or len(a[4]) != len(b[4])
            or any(x is not u or y is not v for (x, y), (u, v) in zip(a[4], b[4], strict=True))
            or a[5] is not b[5]
            or a[6] is not b[6]
        ):
            return False
    return True


FUNCTIONS = {
    "engine": (engine, ("save_inventory", "_save_fingerprints", "collect", "persist", "apply_all")),
    "actions": (
        actions,
        (
            "enable",
            "enable_checked",
            "disable",
            "apply_network",
            "pin",
            "unpin",
            "set_pool_mode",
            "house_after_boot",
            "set_pool_pin",
            "set_core",
        ),
    ),
}
SURFACES = MappingProxyType(
    {
        **{
            actor + "." + method: (cls, method, role)
            for actor, (cls, role, methods) in SPECS.items()
            for method in methods
        },
        **{
            module + "." + method: (owner, method, "LIFECYCLE")
            for module, (owner, methods) in FUNCTIONS.items()
            for method in methods
        },
    }
)
BASE = MappingProxyType(
    {name: getattr(owner, method) for name, (owner, method, _) in SURFACES.items()}
)
STATES = MappingProxyType({name: function_state(fn) for name, fn in BASE.items()})
BINDING_SPECS = ownership_binding.SPECS
BINDING_FUNCTIONS = ownership_binding.FUNCTIONS


def surface_record():
    require(
        ownership_binding.SPECS is BINDING_SPECS
        and ownership_binding.FUNCTIONS is BINDING_FUNCTIONS,
        "SURFACE_DRIFT",
    )
    rows = []
    for name, (owner, method, role) in sorted(SURFACES.items()):
        fn = getattr(owner, method)
        require(fn is BASE[name] and same_state(STATES[name], function_state(fn)), "SURFACE_DRIFT")
        require(getattr(fn, "ownership_role", None) == role, "SURFACE_ROLE")
        parameters = inspect.signature(fn, eval_str=False).parameters.values()
        dependencies = getattr(fn, "ownership_dependencies", ())
        require(type(dependencies) is tuple, "SURFACE_DEPENDENCIES")
        declared = []
        for name_arg, cls, methods, optional in dependencies:
            require(
                type(name_arg) is str
                and isinstance(cls, type)
                and type(methods) is tuple
                and all(type(m) is str for m in methods)
                and type(optional) is bool,
                "SURFACE_DEPENDENCIES",
            )
            declared.append(
                {
                    "argument": name_arg,
                    "class": cls.__qualname__,
                    "methods": list(methods),
                    "optional": optional,
                }
            )
        rows.append(
            {
                "id": name,
                "role": role,
                "dependencies": declared,
                "parameters": [
                    {
                        "name": p.name,
                        "kind": int(p.kind),
                        "default_sha256": hashlib.sha256(canonical(literal(p.default))).hexdigest(),
                    }
                    for p in parameters
                ],
            }
        )
    return {"schema": 1, "surfaces": rows}


@dataclass(frozen=True)
class SurfaceEvidence:
    matched: bool
    checked: int
    reason: str
    runtime_fence_verified: bool = False


class SurfaceCatalog:
    def __init__(self, expected_sha256):
        require(
            type(self) is SurfaceCatalog
            and type(expected_sha256) is str
            and re.fullmatch(r"[0-9a-f]{64}", expected_sha256),
            "SURFACE_ARGUMENT",
        )
        self.expected_sha256 = self._expected_sha256 = expected_sha256
        self._pid, self._thread = os.getpid(), threading.get_ident()

    def observe(self):
        try:
            require(
                type(self) is SurfaceCatalog
                and self._pid == os.getpid()
                and self._thread == threading.get_ident()
                and self.expected_sha256 == self._expected_sha256,
                "SURFACE_CONTEXT",
            )
            record = surface_record()
            require(
                hashlib.sha256(canonical(record)).hexdigest() == self._expected_sha256,
                "SURFACE_MANIFEST_MISMATCH",
            )
            return SurfaceEvidence(True, len(record["surfaces"]), "DECLARED_SURFACES_MATCHED")
        except (SurfaceRefused, AttributeError, TypeError, ValueError):
            return SurfaceEvidence(False, 0, "SURFACE_REFUSED")


SURFACE_OBSERVE = SurfaceCatalog.observe


@dataclass(frozen=True)
class PreflightEvidence:
    matched: bool
    reason: str
    source_matched: bool | None = None
    units_matched: bool | None = None
    surface_matched: bool | None = None
    source_checked: int | None = None
    units_checked: int | None = None
    surface_checked: int | None = None
    runtime_fence_verified: bool = False


class CodePreflight:
    """Fresh observations, with provider identities pinned. Never a recovery lease."""

    def __init__(self, identity, source, units, surface):
        require(
            type(identity) is CodeIdentity
            and type(source) is CodeSeal
            and type(units) is CodeSeal
            and type(surface) is SurfaceCatalog,
            "PREFLIGHT_ARGUMENT",
        )
        self.identity, self.source, self.units, self.surface = identity, source, units, surface
        self._providers = (identity, source, units, surface)
        self._identity_record = identity.record()
        self._pid, self._thread = os.getpid(), threading.get_ident()
        self.validate()

    def validate(self):
        require(
            self._pid == os.getpid()
            and self._thread == threading.get_ident()
            and all(
                a is b
                for a, b in zip(
                    self._providers,
                    (self.identity, self.source, self.units, self.surface),
                    strict=True,
                )
            )
            and self.identity.record() == self._identity_record,
            "PREFLIGHT_CONTEXT",
        )
        for observer in (self.source, self.units):
            require(
                getattr(observer.observe, "__self__", None) is observer
                and getattr(observer.observe, "__func__", None) is SEAL_METHODS["observe"],
                "PREFLIGHT_CONTEXT",
            )
            observer.validate()
        require(
            getattr(self.surface.observe, "__self__", None) is self.surface
            and getattr(self.surface.observe, "__func__", None) is SURFACE_OBSERVE
            and self.source.manifest_digest() == self.identity.source_sha256
            and self.units.manifest_digest() == self.identity.units_sha256
            and self.surface.expected_sha256 == self.identity.surface_sha256,
            "PREFLIGHT_IDENTITY",
        )

    def observe(self):
        observed = []
        try:
            self.validate()
            for provider, cls in (
                (self.source, SealEvidence),
                (self.units, SealEvidence),
                (self.surface, SurfaceEvidence),
            ):
                self.validate()
                result = provider.observe()
                require(
                    type(result) is cls
                    and type(result.matched) is bool
                    and type(result.checked) is int
                    and result.checked >= 0,
                    "PREFLIGHT_EVIDENCE",
                )
                observed.append((result.matched, result.checked))
                self.validate()
            matched = all(v[0] for v in observed)
            return PreflightEvidence(
                matched,
                "BUILD_OBSERVED" if matched else "BUILD_REFUSED",
                *(v[0] for v in observed),
                *(v[1] for v in observed),
            )
        except Exception:
            values = observed + [(None, None)] * (3 - len(observed))
            return PreflightEvidence(
                False, "PREFLIGHT_REFUSED", *(v[0] for v in values), *(v[1] for v in values)
            )
