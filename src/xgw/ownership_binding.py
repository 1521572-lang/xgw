"""Explicit, dormant binding and composite execution for cooperating source writers.

No daemon/CLI composition calls this module. This is not a runtime activation gate,
a durable replay fence, a hostile-code sandbox or a kernel/API verifier.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from . import managed
from .apply.applier import Applier
from .apply.singbox import SingboxCore
from .cores import Job
from .freepool.backend import Backend
from .net.capture import Capture
from .ownership import Registry
from .ownership_hooks import Coordinator, MutationBlocked, owned
from .xraycore.api import ApiClient


@dataclass(frozen=True)
class PanelWriter:
    path: Path
    ownership: Coordinator

    @owned("PANEL")
    def update(self, change):
        return managed._update(self.path, change, ownership=self.ownership)


# Declared source boundary only; the global runtime writer graph remains incomplete.
SPECS = MappingProxyType(
    {
        "capture": (
            Capture,
            "CAPTURE",
            (
                "_save",
                "_load",
                "up",
                "enable",
                "disable",
                "open",
                "close",
                "down",
                "restore_tun",
                "tidy",
                "tailscale_direct",
                "tailscale_fallback",
            ),
        ),
        "peers": (
            Backend,
            "PEERS",
            ("_save_peers", "_nft_element", "prepare", "stop", "reconcile"),
        ),
        "xray": (Applier, "CORE", ("apply", "rollback")),
        "singbox": (SingboxCore, "CORE", ("apply", "rollback", "restart")),
        "cores": (
            Job, "CORE", ("update", "rollback", "run", "_reject", "_stage", "_save", "_event"),
        ),
        "api": (
            ApiClient,
            "API",
            (
                "add_outbounds",
                "remove_outbound",
                "add_inbounds",
                "remove_inbound",
                "replace_routing",
                "pin",
                "unpin",
            ),
        ),
        "panel": (PanelWriter, "PANEL", ("update",)),
    }
)
FUNCTIONS = MappingProxyType(
    {
        (name, method): getattr(cls, method)
        for name, (cls, _, methods) in SPECS.items()
        for method in methods
    }
)
COORDINATOR_CALL = Coordinator.call


def require(value, code):
    if not value:
        raise MutationBlocked(code)


@dataclass(frozen=True)
class Step:
    writer: str
    method: str
    args: tuple = ()
    kwargs: tuple = ()


class BoundWriters:
    """Require all seven explicit objects, same exact coordinator and intact hooks.

    Does not attach/repair ownership, create a registry or discover actors. Revalidates
    the whole declared boundary before admission and before/after every step. Other
    references to legacy actors remain outside this boundary; None is not fenced.
    """

    def __init__(self, coordinator, actors):
        require(type(coordinator) is Coordinator, "COORDINATOR_TYPE")
        require(type(actors) is dict and set(actors) == set(SPECS), "ACTOR_SET")
        self.coordinator = coordinator
        self.actors = MappingProxyType(dict(actors))
        self.registry = coordinator.registry
        self.verifier = coordinator.verifier
        self.pid = os.getpid()
        self.thread = threading.get_ident()
        self.validate()

    def validate(self):
        require(self.pid == os.getpid() and self.thread == threading.get_ident(), "BINDING_CONTEXT")
        c = self.coordinator
        require(type(c) is Coordinator and type(c.registry) is Registry, "COORDINATOR_TYPE")
        require(c.registry is self.registry and c.verifier is self.verifier, "COORDINATOR_DRIFT")
        require(callable(self.verifier), "VERIFIER_NOT_CONFIGURED")
        require(
            getattr(c.call, "__func__", None) is COORDINATOR_CALL
            and getattr(c.call, "__self__", None) is c,
            "COORDINATOR_CALL_DRIFT",
        )
        require(set(self.actors) == set(SPECS), "ACTOR_SET")
        for name, (cls, role, methods) in SPECS.items():
            actor = self.actors[name]
            require(type(actor) is cls, "ACTOR_TYPE")
            require(getattr(actor, "ownership", None) is c, "ACTOR_UNBOUND")
            for method in methods:
                bound = getattr(actor, method, None)
                function = FUNCTIONS[name, method]
                require(
                    getattr(bound, "__self__", None) is actor
                    and getattr(bound, "__func__", None) is function
                    and getattr(function, "ownership_role", None) == role,
                    "HOOK_DRIFT",
                )

    def validate_steps(self, steps, accept):
        self.validate()
        require(callable(accept), "RESULT_CHECKER_REQUIRED")
        require(type(steps) is tuple and 1 <= len(steps) <= 32, "STEP_COUNT")
        for step in steps:
            require(type(step) is Step, "STEP_TYPE")
            require(
                type(step.writer) is str
                and type(step.method) is str
                and (step.writer, step.method) in FUNCTIONS,
                "STEP_TARGET",
            )
            require(type(step.args) is tuple and type(step.kwargs) is tuple, "STEP_ARGUMENTS")
            names = set()
            for pair in step.kwargs:
                require(
                    type(pair) is tuple
                    and len(pair) == 2
                    and type(pair[0]) is str
                    and pair[0] not in names
                    and pair[0] != "ownership",
                    "STEP_KEYWORDS",
                )
                names.add(pair[0])

    def prepare(self, steps, *, accept=None):
        self.validate_steps(steps, accept)
        return PreparedBatch(self, steps, accept)


class PreparedBatch:
    """One process-local attempt, consumed even when admission is refused.

    Not serializable authorization. No retry/rollback/repair is scheduled here. The
    pinned caller verifier sees the complete tuple and the union of nested roles.
    It must reject incomplete/failed outcomes and verify required resource domains.
    """

    def __init__(self, binding, steps, accept):
        self.binding = binding
        self.steps = steps
        self.accept = accept
        self.used = False

    def run(self):
        require(not self.used, "BATCH_ALREADY_USED")
        self.used = True
        b = self.binding
        steps, accept = self.steps, self.accept
        b.validate_steps(steps, accept)
        require(getattr(b.coordinator.local, "session", None) is None, "BATCH_NESTING_REFUSED")

        def operation():
            values = []
            for step in steps:
                b.validate()
                value = getattr(b.actors[step.writer], step.method)(*step.args, **dict(step.kwargs))
                b.validate()
                require(accept(step, value) is True, "STEP_RESULT_REFUSED")
                b.validate()
                values.append(value)
            return tuple(values)

        return b.coordinator.call("LIFECYCLE", operation)
