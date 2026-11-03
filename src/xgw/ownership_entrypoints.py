"""Explicit lifecycle entrypoints. No default activation or runtime construction.

An outer ticket spans cooperating synchronous writers. This declared dependency
check does not inventory other callers, paths, threads or services.
"""

from __future__ import annotations

import inspect
import os
import threading
from functools import wraps

from .ownership import Registry
from .ownership_hooks import Coordinator, MutationBlocked, owned_function

COORDINATOR_CALL = Coordinator.call


def require(value, reason):
    if not value:
        raise MutationBlocked(reason)


def actor_check(coordinator, actor, cls, methods):
    require(
        type(actor) is cls and getattr(actor, "ownership", None) is coordinator,
        "ENTRY_ACTOR_BINDING",
    )
    for name, function, role in methods:
        bound = getattr(actor, name, None)
        require(
            getattr(bound, "__self__", None) is actor
            and getattr(bound, "__func__", None) is function
            and getattr(function, "ownership_role", None) == role,
            "ENTRY_HOOK_DRIFT",
        )


def pin_actor(cls, methods):
    require(
        isinstance(cls, type) and type(methods) is tuple and bool(methods), "ENTRY_DEPENDENCIES"
    )
    require(
        all(type(m) is str and callable(getattr(cls, m, None)) for m in methods)
        and len(set(methods)) == len(methods),
        "ENTRY_DEPENDENCIES",
    )
    functions = tuple(
        (m, getattr(cls, m), getattr(getattr(cls, m), "ownership_role", None)) for m in methods
    )
    require(all(type(r) is str for _, _, r in functions), "ENTRY_HOOK_DECLARATION")
    return cls, functions


def require_bound_actor(coordinator, actor, pinned):
    """Check a newly constructed dependency before its first business call.

    None is the historical compatibility path, never an attested runtime fence.
    Source class methods are already pinned by the entrypoint's declaration when
    supplied as arguments; this helper checks a fresh factory result only.
    """
    if coordinator is not None:
        require(type(coordinator) is Coordinator, "ENTRY_COORDINATOR_TYPE")
        cls, functions = pinned
        actor_check(coordinator, actor, cls, functions)
    return actor


class EntryBoundary:
    """Process-local pinned checks only; no filesystem I/O or registry creation."""

    def __init__(self, coordinator, actors=()):
        self.coordinator = coordinator
        self.actors = actors
        self.pid, self.thread = os.getpid(), threading.get_ident()
        if coordinator is not None:
            require(
                type(coordinator) is Coordinator
                and type(coordinator.registry) is Registry
                and callable(coordinator.verifier),
                "ENTRY_COORDINATOR_TYPE",
            )
            self.registry, self.verifier = coordinator.registry, coordinator.verifier
        self.validate()

    def validate(self):
        c = self.coordinator
        if c is None:
            return
        require(self.pid == os.getpid() and self.thread == threading.get_ident(), "ENTRY_CONTEXT")
        require(
            c.registry is self.registry
            and c.verifier is self.verifier
            and getattr(c.call, "__self__", None) is c
            and getattr(c.call, "__func__", None) is COORDINATOR_CALL,
            "ENTRY_COORDINATOR_DRIFT",
        )
        session = getattr(c.local, "session", None)
        require(session is None or not session["tainted"], "ENTRY_TAINTED")
        for actor, cls, functions, optional in self.actors:
            if actor is not None or not optional:
                actor_check(c, actor, cls, functions)


def owned_entrypoint(role, *, dependencies=()):
    """Optional keyword-only ownership=None, exact declared actor dependencies.

    Refuse a foreign/unbound dependency before admission. Revalidate the same
    coordinator/registry/verifier and declared hooks inside admission and after
    the synchronous body. No lock is held across body/domain/service waits.
    """
    require(type(dependencies) is tuple, "ENTRY_DEPENDENCIES")
    pinned = []
    names = set()
    for row in dependencies:
        require(type(row) is tuple and len(row) == 4, "ENTRY_DEPENDENCIES")
        name, cls, methods, optional = row
        require(
            type(name) is str
            and name not in names
            and isinstance(cls, type)
            and type(methods) is tuple
            and bool(methods)
            and type(optional) is bool,
            "ENTRY_DEPENDENCIES",
        )
        names.add(name)
        _, functions = pin_actor(cls, methods)
        pinned.append((name, cls, functions, optional))
    pinned = tuple(pinned)

    def decorate(function):
        # Reuse the accepted synchronous/ownership signature validation only.
        declared = owned_function(role)(function)
        signature = inspect.signature(function)
        require(all(n in signature.parameters for n in names), "ENTRY_PARAMETER")

        @wraps(declared)
        def invoke(*args, **kwargs):
            coordinator = kwargs.get("ownership")
            if coordinator is None:
                return function(*args, **kwargs)
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            actors = tuple(
                (bound.arguments[name], cls, functions, optional)
                for name, cls, functions, optional in pinned
            )

            boundary = EntryBoundary(coordinator, actors)

            def operation():
                boundary.validate()
                result = function(*args, **kwargs)
                boundary.validate()
                return result

            return coordinator.call(role, operation)

        invoke.ownership_dependencies = dependencies
        return invoke

    return decorate
