"""Opt-in source hooks only. None preserves legacy behavior, never proves a fence.

Runtime construction/version handshake and concrete resource verifiers are absent.
No environment activation, default registry, import-time I/O or automatic repair.
"""

from __future__ import annotations

import inspect
import os
import threading
from functools import wraps

from .ownership import ROLES
from .ownership_adapters import Verification, execute


class MutationBlocked(Exception):
    """Fixed code only; the business exception remains private to its caller."""


def deferred(value):
    return inspect.isawaitable(value) or inspect.isgenerator(value) or inspect.isasyncgen(value)


class Coordinator:
    def __init__(self, registry, verifier=None):
        self.registry = registry
        self.verifier = verifier
        self.local = threading.local()
        self.last_execution = None

    @property
    def last_execution(self):
        return getattr(self.local, "execution", None)

    @last_execution.setter
    def last_execution(self, value):
        self.local.execution = value

    def call(self, role, operation):
        if type(role) is not str or role not in ROLES or not callable(operation):
            raise MutationBlocked("ARGUMENT_REFUSED")
        if not callable(self.verifier):
            raise MutationBlocked("VERIFIER_NOT_CONFIGURED")
        current = getattr(self.local, "session", None)
        if current is not None:
            if (
                current["pid"] != os.getpid()
                or current["thread"] != threading.get_ident()
                or not current["active"]
            ):
                raise MutationBlocked("INHERITED_OR_CLOSED_CONTEXT")
            current["roles"].add(role)
            try:
                value = operation()
                if deferred(value):
                    raise MutationBlocked("DEFERRED_RESULT_REFUSED")
                return value
            except BaseException:
                current["tainted"] = True
                raise
        session = {
            "pid": os.getpid(),
            "thread": threading.get_ident(),
            "active": True,
            "roles": {role},
            "tainted": False,
            "value": None,
            "exception": None,
        }
        self.local.session = session

        def invoke():
            try:
                session["value"] = operation()
                return session["value"]
            except BaseException as exc:
                session["exception"] = exc
                raise

        def verify(value):
            if session["tainted"] or deferred(value):
                return Verification()
            return self.verifier(frozenset(session["roles"]), value)

        try:
            execution = execute(self.registry, role, invoke, verify)
            self.last_execution = execution
            if session["exception"] is not None:
                raise session["exception"]
            if execution.status != "COMPLETED":
                raise MutationBlocked(execution.reason)
            return session["value"]
        finally:
            session["active"] = False
            self.local.session = None


def owned(role):
    """Wrap a synchronous instance entrypoint; explicit injected coordinator only."""
    if role not in ROLES:
        raise MutationBlocked("ROLE_REFUSED")

    def decorate(function):
        if (
            inspect.iscoroutinefunction(function)
            or inspect.isgeneratorfunction(function)
            or inspect.isasyncgenfunction(function)
        ):
            raise MutationBlocked("DEFERRED_FUNCTION_REFUSED")

        @wraps(function)
        def invoke(self, *args, **kwargs):
            coordinator = getattr(self, "ownership", None)
            if coordinator is None:
                return function(self, *args, **kwargs)
            return coordinator.call(role, lambda: function(self, *args, **kwargs))

        invoke.ownership_role = role
        return invoke

    return decorate


def call_owned(coordinator, role, operation):
    return operation() if coordinator is None else coordinator.call(role, operation)


def owned_function(role):
    """Synchronous free-function hook with explicit keyword-only ownership=None.

    Optional legacy calls remain unbound. No environment/context-global activation.
    The original signature and business result/exception are preserved by wraps.
    """
    if type(role) is not str or role not in ROLES:
        raise MutationBlocked("ROLE_REFUSED")

    def decorate(function):
        parameter = inspect.signature(function).parameters.get("ownership")
        if (
            parameter is None
            or parameter.kind is not inspect.Parameter.KEYWORD_ONLY
            or parameter.default is not None
        ):
            raise MutationBlocked("OWNERSHIP_SIGNATURE_REFUSED")
        if (
            inspect.iscoroutinefunction(function)
            or inspect.isgeneratorfunction(function)
            or inspect.isasyncgenfunction(function)
        ):
            raise MutationBlocked("DEFERRED_FUNCTION_REFUSED")

        @wraps(function)
        def invoke(*args, **kwargs):
            return call_owned(kwargs.get("ownership"), role, lambda: function(*args, **kwargs))

        invoke.ownership_role = role
        return invoke

    return decorate
