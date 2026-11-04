"""AM: explicit code/binding/FILES composition, private fixtures only."""

# ruff: noqa: E731
import hashlib
import importlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path
from types import FunctionType, SimpleNamespace

NOTES = Path.home() / "xgw-w3ao"
AK_SHA = "927128c0486d45eabd7c81a6416e74be9f1e7153ec6f9a0121ac8083177b9e55"
SUPPORT_SHA = "9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917"
MANIFEST_SHA = "dee99fd4c4ce43e53f0244a6e09a860e3e20f52bfa633fde14a48a25028604f3"
UNITS_SHA = "373695d50a921ef2e2fdc8398192ef62f7d6fd0414704d3822b967c8e3142bd4"
SURFACE_SHA = "8c5dd6e0362e939f2e366b3b14dde554220d8a2160122f824fb7b61a3d80adbe"
LEGACY_SHA = "2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5"
LEGACY_COMMIT = "63c9c413930eb348d46b2ff986bef46dd2e423d4"
HOOKS = (
    ("capture", "_save"),
    ("capture", "_load"),
    ("capture", "up"),
    ("capture", "enable"),
    ("capture", "disable"),
    ("capture", "open"),
    ("capture", "close"),
    ("capture", "down"),
    ("capture", "restore_tun"),
    ("capture", "tidy"),
    ("capture", "tailscale_direct"),
    ("capture", "tailscale_fallback"),
    ("peers", "_save_peers"),
    ("peers", "_nft_element"),
    ("peers", "prepare"),
    ("peers", "stop"),
    ("peers", "reconcile"),
    ("xray", "apply"),
    ("xray", "rollback"),
    ("singbox", "apply"),
    ("singbox", "rollback"),
    ("singbox", "restart"),
    ("cores", "update"),
    ("cores", "rollback"),
    ("cores", "run"),
    ("cores", "_reject"),
    ("cores", "_stage"),
    ("cores", "_save"),
    ("cores", "_event"),
    ("api", "add_outbounds"),
    ("api", "remove_outbound"),
    ("api", "add_inbounds"),
    ("api", "remove_inbound"),
    ("api", "replace_routing"),
    ("api", "pin"),
    ("api", "unpin"),
    ("panel", "update"),
    ("pool_store", "_ensure"),
    ("pool_store", "commit"),
    ("pool_store", "prune"),
    ("pool_store", "retire_openvpn"),
    ("pool_store", "save_candidates"),
    ("pool", "_prune_retired"),
    ("pool", "refresh_due"),
    ("pool", "_prune_candidates"),
    ("pool", "refresh_backend"),
    ("pool", "_note_handshake"),
    ("pool", "check_some"),
    ("pool", "_check_proxy"),
    ("pool", "_record"),
)
ACTORS = ("capture", "peers", "xray", "singbox", "cores", "api", "panel", "pool_store", "pool")
TIMES = ("PREPARE", "RUN", "BODY", "CHECKER", "FINAL")
HOOK_CASES = tuple(
    f"H_{i:02d}_{kind}_{when}" for i in range(50) for kind in ("SHADOW", "ROLE") for when in TIMES
)
ACTOR_CASES = tuple(
    "A_" + actor + "_" + kind + "_" + when
    for actor in ACTORS
    for kind in ("NONE", "FOREIGN")
    for when in TIMES
)
REFERENCE_CASES = tuple(
    "R_" + ref + "_" + kind + "_" + when
    for ref in ("API", "STORE", "BACKEND")
    for kind in ("NONE", "FOREIGN")
    for when in TIMES
)
CODE_CASES = tuple(
    "B_" + tree + "_" + kind + "_" + when
    for tree in ("SOURCE", "UNITS")
    for kind in ("HASH", "MISSING", "EXTRA", "MODE", "LINK")
    for when in TIMES[1:]
)
METHOD_TARGETS = (
    ("REGISTRY", "code_context"),
    ("REGISTRY", "admit"),
    ("REGISTRY", "unknown"),
    ("REGISTRY", "complete"),
    ("REGISTRY", "receipt"),
    ("REGISTRY", "locked"),
    ("REGISTRY", "validate"),
    ("REGISTRY", "commit"),
    ("REGISTRY", "writer_token"),
    ("REGISTRY", "check_writer_token"),
    ("REGISTRY", "read"),
    ("REGISTRY", "lock_identity"),
    ("PREFLIGHT", "observe"),
    ("PREFLIGHT", "validate"),
    ("FILES", "__call__"),
    ("FILES", "validate"),
    ("BINDING", "validate"),
    ("BINDING", "validate_steps"),
    ("BINDING", "prepare"),
    ("GATE", "validate"),
    ("GATE", "seal"),
    ("GATE", "checkpoint"),
    ("GATE", "__call__"),
)
METHOD_CASES = tuple(f"T_{i:02d}_{when}" for i in range(len(METHOD_TARGETS)) for when in TIMES)
CONTEXT_CASES = tuple(
    "C_" + n
    for n in (
        "GATE_PID",
        "GATE_THREAD",
        "REGISTRY",
        "PREFLIGHT",
        "FILES",
        "GATE_BINDING",
        "GATE_METHOD",
        "GATE_CODE",
        "REGISTRY_METHOD",
        "REGISTRY_PATH",
        "REGISTRY_UID",
        "REGISTRY_CLOCK",
        "REGISTRY_BOOT",
        "COMPOSITION_BINDING",
        "COMPOSITION_GATE",
        "COMPOSITION_PID",
        "PLAN_STEPS",
        "PLAN_ACCEPT",
        "CHECKER_CODE",
        "CHECKER_DEFAULT",
    )
)
POLICY_CASES = tuple(
    "P_" + n
    for n in (
        "REGISTRY_TYPE",
        "OLD_REGISTRY",
        "EQUAL_IDENTITY",
        "PREFLIGHT_TYPE",
        "FILES_TYPE",
        "DOMAIN",
        "UNSEALED",
        "DOUBLE_SEAL",
        "FOREIGN_BINDING",
        "BINDING_TYPE",
        "VERIFIER_TYPE",
        "ROLE_CONTRACT",
        "GATE_SUBCLASS",
        "BAD_PHASE",
        "NO_CHECKER",
        "ASYNC_CHECKER",
    )
)
PLAN_CASES = tuple(
    "D_" + n
    for n in (
        "EMPTY",
        "LIST",
        "MANY",
        "TYPE",
        "WRITER",
        "METHOD",
        "ARGS",
        "KWARGS",
        "DUPLICATE",
        "OWNERSHIP",
        "KEYTYPE",
        "ROWTYPE",
        "GENERATOR",
        "ASYNCGEN",
        "CALLABLE_OBJECT",
        "BOOL_CHECKER",
    )
)
POSITIVE_CASES = tuple(
    "I_" + n
    for n in (
        "ONE",
        "TWO",
        "THREE",
        "MAX",
        "NOOP",
        "ROLLBACK",
        "EARLY_LEASE",
        "REPLAY",
        "FENCED",
        "FULL_BUILD",
        "FULL_NOOP",
        "FULL_ROLLBACK",
    )
)
FAILURE_CASES = tuple(
    "F_" + n
    for n in (
        "CHECKER_FALSE",
        "CHECKER_BOOL",
        "CHECKER_RAISE",
        "BODY_RAISE",
        "BODY_TERMINAL",
        "FINAL_FALSE",
        "FINAL_RAISE",
        "FINAL_TERMINAL",
        "FILE_HASH",
        "FILE_MODE",
        "FILE_MISSING",
        "NESTED",
        "SWAP_BOUNDARY_FINAL",
    )
)
EXPECTED = (
    "F_CHECKER_RAISE",
    "F_BODY_RAISE",
    *(f"POSITION_{phase}_{index:02d}" for phase in ("BODY", "CHECKER") for index in range(1, 33)),
)
DETAIL_KEYS = (
    "body_calls",
    "checker_calls",
    "final_calls",
    "registry_receipts",
    "registry_generation",
    "unknown_writers",
    "writer_total",
    "observations",
    "phase",
    "build_matched",
    "source_checked",
    "units_checked",
    "surface_checked",
    "files_verified",
    "plan_used",
    "refused",
    "target_restored",
    "operation_error_observed",
    "failure_step",
    "panel_present",
)
BOOL_KEYS = {
    "build_matched",
    "files_verified",
    "plan_used",
    "refused",
    "target_restored",
    "operation_error_observed",
    "panel_present",
}
INT_KEYS = set(DETAIL_KEYS) - BOOL_KEYS - {"phase"}
PHASES = {
    "NOT_OBSERVED",
    "PRE_ADMISSION",
    "INSIDE_ADMISSION",
    "BEFORE_STEP",
    "AFTER_STEP",
    "AFTER_CHECKER",
    "VERIFY_BEFORE_FILES",
    "VERIFY_AFTER_FILES",
}
AK = SUPPORT = DETAILS = None
M = {}
UNITS = {}


class TargetRestoreStop(Exception):
    pass


def require(value, code):
    if not value:
        raise ValueError(code)


def private(path, directory=False):
    i = path.lstat()
    require(
        (stat.S_ISDIR(i.st_mode) if directory else stat.S_ISREG(i.st_mode))
        and i.st_uid == os.getuid()
        and stat.S_IMODE(i.st_mode) == (0o700 if directory else 0o600)
        and (directory or i.st_nlink == 1),
        "PRIVATE_METADATA",
    )


def bootstrap():
    global AK, SUPPORT, UNITS
    private(NOTES, True)
    private(NOTES / "ak.py")
    require(hashlib.sha256((NOTES / "ak.py").read_bytes()).hexdigest() == AK_SHA, "AK_SHA")
    spec = importlib.util.spec_from_file_location("am_pinned_ak_support", NOTES / "ak.py")
    AK = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(AK)
    AK.NOTES, AK.MANIFEST_SHA = NOTES, MANIFEST_SHA
    count = AK.bootstrap()
    SUPPORT, UNITS = AK.SUPPORT, AK.UNITS
    return count


def source():
    global M
    AK.source()
    M = AK.M
    M["ownership_binding"] = importlib.import_module("frozen_ad.ownership_binding")
    M["ownership_composition"] = importlib.import_module("frozen_ad.ownership_composition")
    require(tuple(M["ownership_binding"].FUNCTIONS) == HOOKS, "HOOK_INVENTORY")
    cm = M["ownership_composition"]
    actual = tuple(
        (key, method)
        for key, table in (
            ("REGISTRY", cm.REGISTRY_METHODS),
            ("PREFLIGHT", cm.PREFLIGHT_METHODS),
            ("FILES", cm.FILE_METHODS),
            ("BINDING", cm.BINDING_METHODS),
            ("GATE", cm.GATE_METHODS),
        )
        for method in table
    )
    require(actual == METHOD_TARGETS, "COMPOSITION_METHOD_INVENTORY")


def patch(f, obj, name, value):
    present = name in getattr(obj, "__dict__", {}) or (
        type(obj) is FunctionType and name in ("__code__", "__defaults__", "__kwdefaults__")
    )
    before = getattr(obj, name, None)
    f.undo.append((obj, name, present, before))
    object.__setattr__(obj, name, value) if not isinstance(obj, type) else setattr(obj, name, value)


def restore(f):
    for obj, name, present, value in reversed(f.undo):
        if present:
            object.__setattr__(obj, name, value) if not isinstance(obj, type) else setattr(
                obj, name, value
            )
        elif name in getattr(obj, "__dict__", {}):
            object.__delattr__(obj, name)
    f.undo.clear()
    # Global surface baseline must be restored before any later independent case.
    if not M["ownership_surface"].SurfaceCatalog(SURFACE_SHA).observe().matched:
        raise TargetRestoreStop("SURFACE_NOT_RESTORED")
    cm = M["ownership_composition"]
    if any(
        not cm.same_state(state, cm.function_state(fn)) for fn, state in cm.METHOD_STATES.items()
    ):
        raise TargetRestoreStop("METHODS_NOT_RESTORED")
    f.composition.validate()
    DETAILS["target_restored"] = True


def fixture(f, name):
    b = M["ownership_binding"]
    cm = M["ownership_composition"]
    sf = M["ownership_surface"]
    f.undo = []
    f.body_calls = f.checker_calls = f.final_calls = 0
    f.fault_at = 1
    f.trigger = lambda when: None
    f.failure = name if name in FAILURE_CASES else None
    f.noop = name in ("I_NOOP", "I_ROLLBACK", "I_FULL_NOOP", "I_FULL_ROLLBACK")
    f.panel = f.work / "panel.json"
    if name in ("I_FULL_BUILD", "I_FULL_NOOP", "I_FULL_ROLLBACK"):
        source_seal, units_seal = AK.full_seal("SOURCE"), AK.full_seal("UNITS")
    else:
        source_seal, units_seal = AK.make_seal(f, "source"), AK.make_seal(f, "units")
    identity = M["ownership_identity"].CodeIdentity(
        source_seal.manifest_digest(), units_seal.manifest_digest(), SURFACE_SHA
    )
    f.preflight = sf.CodePreflight(
        identity, source_seal, units_seal, sf.SurfaceCatalog(SURFACE_SHA)
    )
    r = M["ownership"].Registry(
        f.root / "registry",
        boot_id=SUPPORT.BOOT,
        expected_uid=os.getuid(),
        clock_ns=lambda: 10,
        code_identity=identity,
    )
    r.initialize()
    f.registry = r
    raw = (json.dumps({"value": 1}, ensure_ascii=False, indent=2) + "\n").encode()
    expectation = (
        M["ownership_files"].FileExpectation("panel.json", absent=True)
        if f.noop
        else M["ownership_files"].FileExpectation("panel.json", hashlib.sha256(raw).hexdigest())
    )

    def final_accept(value):
        f.final_calls += 1
        f.trigger("FINAL")
        if f.failure == "F_SWAP_BOUNDARY_FINAL":
            patch(f, f.gate, "_binding", b.BoundWriters(f.coordinator, f.actors))
        if f.failure == "F_FINAL_FALSE":
            return False
        if f.failure == "F_FINAL_RAISE":
            raise RuntimeError("PRIVATE_FIXTURE")
        if f.failure == "F_FINAL_TERMINAL":
            raise SystemExit(9)
        return type(value) is tuple and bool(value) and all(v is (not f.noop) for v in value)

    outcome = (
        "NOOP"
        if name in ("I_NOOP", "I_FULL_NOOP")
        else "ROLLED_BACK"
        if name in ("I_ROLLBACK", "I_FULL_ROLLBACK")
        else "COMMITTED"
    )
    files = M["ownership_files"].PrivateFiles(
        f.work, expected_uid=os.getuid(), expectations=(expectation,)
    )
    fc = M["ownership_completion"].FileCompletion(
        M["ownership_completion"].CompletionContract(
            frozenset({"LIFECYCLE", "PANEL"}), ("FILES",), outcome
        ),
        files,
        accept=final_accept,
    )
    f.files = fc
    f.gate = cm.BuildCompletion(r, f.preflight, fc)
    f.coordinator = M["ownership_hooks"].Coordinator(r, f.gate)
    f.actors = {}
    for key, (cls, _, _) in b.SPECS.items():
        obj = cls.__new__(cls)
        object.__setattr__(obj, "ownership", f.coordinator)
        f.actors[key] = obj
    f.actors["panel"] = b.PanelWriter(f.panel, f.coordinator)
    f.actors["xray"].api = f.actors["api"]
    f.actors["pool"].store = f.actors["pool_store"]
    f.actors["pool"].runtime = f.actors["peers"]
    f.binding = b.BoundWriters(f.coordinator, f.actors)
    f.composition = cm.Composition(f.binding)

    def change(data):
        f.body_calls += 1
        f.trigger("BODY")
        if f.failure == "F_BODY_RAISE" and f.body_calls == f.fault_at:
            raise RuntimeError("PRIVATE_FIXTURE")
        if f.failure == "F_BODY_TERMINAL":
            raise SystemExit(9)
        if name == "I_EARLY_LEASE":
            refuse(lambda: r.acquire(run_id="b" * 32, expected_generation=0, duration_ns=100))
        data.clear()
        data["value"] = 1
        return not f.noop

    def accept(step, value):
        f.checker_calls += 1
        f.trigger("CHECKER")
        if f.failure == "F_CHECKER_FALSE":
            return False
        if f.failure == "F_CHECKER_BOOL":
            return 1
        if f.failure == "F_CHECKER_RAISE" and f.checker_calls == f.fault_at:
            raise RuntimeError("PRIVATE_FIXTURE")
        if f.failure == "F_FILE_HASH":
            f.panel.write_bytes(b"PRIVATE_CHANGED")
        if f.failure == "F_FILE_MODE":
            f.panel.chmod(0o644)
        if f.failure == "F_FILE_MISSING":
            f.panel.unlink()
        return value is (not f.noop)

    f.accept = accept
    count = {"I_TWO": 2, "I_THREE": 3, "I_MAX": 32}.get(name, 1)
    f.steps = (b.Step("panel", "update", (change,)),) * count
    f.plan = None


def refuse(call, terminal=False, expected_runtime=False):
    try:
        call()
    except (M["ownership_hooks"].MutationBlocked, M["ownership"].Refused):
        DETAILS["refused"] = True
    except SystemExit:
        require(terminal, "UNEXPECTED_TERMINAL")
        DETAILS["refused"] = True
    except RuntimeError as exc:
        if (
            not expected_runtime
            or type(exc) is not RuntimeError
            or exc.args != ("PRIVATE_FIXTURE",)
        ):
            raise
        DETAILS["operation_error_observed"] = True
    else:
        raise ValueError("EXPECTED_REFUSAL")


def mutation(f, name):
    if name.startswith("H_"):
        _, index, kind, _ = name.split("_")
        writer, method = HOOKS[int(index)]
        if kind == "SHADOW":
            patch(f, f.actors[writer], method, lambda *a, **k: None)
        else:
            patch(f, M["ownership_binding"].FUNCTIONS[writer, method], "ownership_role", "FOREIGN")
    elif name.startswith("A_"):
        _, tail = name.split("_", 1)
        actor, kind, _ = tail.rsplit("_", 2)
        value = None if kind == "NONE" else M["ownership_hooks"].Coordinator(f.registry, f.gate)
        patch(f, f.actors[actor], "ownership", value)
    elif name.startswith("R_"):
        _, ref, kind, _ = name.split("_")
        obj, attr = {
            "API": (f.actors["xray"], "api"),
            "STORE": (f.actors["pool"], "store"),
            "BACKEND": (f.actors["pool"], "runtime"),
        }[ref]
        patch(f, obj, attr, None if kind == "NONE" else object())
    else:
        _, tree, kind, _ = name.split("_")
        seal = f.preflight.source if tree == "SOURCE" else f.preflight.units
        path = seal.root / "code.py"
        if kind == "HASH":
            path.write_bytes(b"PRIVATE_CHANGED")
        elif kind == "MISSING":
            path.unlink()
        elif kind == "EXTRA":
            (seal.root / "extra").write_bytes(b"PRIVATE")
        elif kind == "MODE":
            path.chmod(0o644)
        else:
            (f.work / "linked").hardlink_to(path)


def matrix_case(f, name):
    when = name.rsplit("_", 1)[1]
    fired = []

    def trigger(point):
        if point == when and not fired:
            fired.append(True)
            mutation(f, name)

    f.trigger = trigger
    if when == "PREPARE":
        trigger("PREPARE")
        refuse(lambda: f.composition.prepare(f.steps, accept=f.accept))
    else:
        f.plan = f.composition.prepare(f.steps, accept=f.accept)
        trigger("RUN")
        refuse(f.plan.run)
    summary = f.registry.summary()
    require(
        summary["receipts"] == 0 and summary["unknown"] == int(when not in ("PREPARE", "RUN")),
        "MATRIX_TICKET",
    )
    require(f.body_calls == int(when not in ("PREPARE", "RUN")), "MATRIX_BODY")


def context_case(f, name):
    f.plan = f.composition.prepare(f.steps, accept=f.accept)
    n = name[2:]
    choices = {
        "GATE_PID": (f.gate, "_pid", -1),
        "GATE_THREAD": (f.gate, "_thread", -1),
        "REGISTRY": (f.gate, "registry", object()),
        "PREFLIGHT": (f.gate, "preflight", object()),
        "FILES": (f.gate, "files", object()),
        "GATE_BINDING": (f.gate, "_binding", object()),
        "GATE_METHOD": (f.gate, "checkpoint", lambda phase: None),
        "GATE_CODE": (
            type(f.gate).__call__,
            "__code__",
            type(f.gate).__call__.__code__.replace(co_firstlineno=1),
        ),
        "REGISTRY_METHOD": (f.registry, "admit", lambda role: None),
        "REGISTRY_PATH": (f.registry, "directory", f.work / "foreign"),
        "REGISTRY_UID": (f.registry, "expected_uid", True),
        "REGISTRY_CLOCK": (f.registry, "clock_ns", lambda: 10),
        "REGISTRY_BOOT": (f.registry, "boot_id", "22222222-2222-2222-2222-222222222222"),
        "COMPOSITION_BINDING": (f.composition, "binding", object()),
        "COMPOSITION_GATE": (f.composition, "gate", object()),
        "COMPOSITION_PID": (f.composition, "_pid", -1),
        "PLAN_STEPS": (f.plan, "steps", tuple(list(f.steps))),
        "PLAN_ACCEPT": (f.plan, "accept", lambda s, v: True),
        "CHECKER_CODE": (f.accept, "__code__", f.accept.__code__.replace(co_firstlineno=1)),
        "CHECKER_DEFAULT": (f.accept, "__defaults__", (True,)),
    }
    patch(f, *choices[n])
    refuse(f.plan.run)


def method_case(f, name):
    _, index, when = name.split("_")
    target, method = METHOD_TARGETS[int(index)]
    obj = {
        "REGISTRY": f.registry,
        "PREFLIGHT": f.preflight,
        "FILES": f.files,
        "BINDING": f.binding,
        "GATE": f.gate,
    }[target]
    fired = []

    def shadow(*args, **kwargs):
        raise M["ownership_hooks"].MutationBlocked("FIXTURE_METHOD_DRIFT")

    def trigger(point):
        if point == when and not fired:
            fired.append(True)
            patch(f, obj, method, shadow)

    f.trigger = trigger
    if when == "PREPARE":
        trigger("PREPARE")
        refuse(lambda: f.composition.prepare(f.steps, accept=f.accept))
    else:
        f.plan = f.composition.prepare(f.steps, accept=f.accept)
        trigger("RUN")
        refuse(f.plan.run)


def policy_case(f, name):
    cm = M["ownership_composition"]
    n = name[2:]
    if n == "REGISTRY_TYPE":
        call = lambda: cm.BuildCompletion(object(), f.preflight, f.files)
    elif n == "OLD_REGISTRY":
        r = M["ownership"].Registry(
            f.work / "absent", boot_id=SUPPORT.BOOT, expected_uid=os.getuid()
        )
        call = lambda: cm.BuildCompletion(r, f.preflight, f.files)
    elif n == "EQUAL_IDENTITY":
        ident = f.preflight.identity
        peer = M["ownership"].Registry(
            f.registry.directory,
            boot_id=SUPPORT.BOOT,
            expected_uid=os.getuid(),
            code_identity=M["ownership_identity"].CodeIdentity(
                **{k: v for k, v in ident.record().items() if k != "protocol"}
            ),
        )
        call = lambda: cm.BuildCompletion(peer, f.preflight, f.files)
    elif n == "PREFLIGHT_TYPE":
        call = lambda: cm.BuildCompletion(f.registry, object(), f.files)
    elif n == "FILES_TYPE":
        call = lambda: cm.BuildCompletion(f.registry, f.preflight, object())
    elif n == "DOMAIN":
        contract = M["ownership_completion"].CompletionContract(
            frozenset({"PANEL", "LIFECYCLE"}), ("FILES", "KERNEL"), "COMMITTED"
        )
        patch(f, f.files, "contract", contract)
        patch(f, f.files, "_contract", contract)
        call = lambda: cm.BuildCompletion(f.registry, f.preflight, f.files)
    elif n == "UNSEALED":
        unsealed = cm.BuildCompletion(f.registry, f.preflight, f.files)
        require(
            not unsealed(frozenset({"PANEL", "LIFECYCLE"}), (True,)).accepted(), "UNSEALED_ACCEPTED"
        )
        return
    elif n == "DOUBLE_SEAL":
        call = lambda: f.gate.seal(f.binding)
    elif n == "FOREIGN_BINDING":
        gate = cm.BuildCompletion(f.registry, f.preflight, f.files)
        call = lambda: gate.seal(f.binding)
    elif n == "BINDING_TYPE":
        call = lambda: cm.Composition(object())
    elif n == "VERIFIER_TYPE":
        patch(f, f.binding, "verifier", f.files)
        call = lambda: cm.Composition(f.binding)
    elif n == "ROLE_CONTRACT":
        contract = M["ownership_completion"].CompletionContract(
            frozenset({"PANEL"}), ("FILES",), "COMMITTED"
        )
        patch(f, f.files, "contract", contract)
        patch(f, f.files, "_contract", contract)
        call = lambda: f.composition.prepare(f.steps, accept=f.accept)
    elif n == "GATE_SUBCLASS":

        class Foreign(cm.BuildCompletion):
            pass

        gate = Foreign.__new__(Foreign)
        patch(f, f.binding, "verifier", gate)
        call = lambda: cm.Composition(f.binding)
    elif n == "BAD_PHASE":
        call = lambda: f.gate.checkpoint("PRIVATE")
    elif n == "NO_CHECKER":
        call = lambda: f.composition.prepare(f.steps, accept=None)
    else:

        async def checker(step, value):
            return True

        call = lambda: f.composition.prepare(f.steps, accept=checker)
    refuse(call)


def plan_case(f, name):
    b = M["ownership_binding"]
    n = name[2:]
    s = f.steps[0]
    checker = f.accept
    variants = {
        "EMPTY": (),
        "LIST": [s],
        "MANY": (s,) * 33,
        "TYPE": (object(),),
        "WRITER": (b.Step("foreign", "update"),),
        "METHOD": (b.Step("panel", "foreign"),),
        "ARGS": (b.Step("panel", "update", []),),
        "KWARGS": (b.Step("panel", "update", kwargs={}),),
        "DUPLICATE": (b.Step("panel", "update", kwargs=(("x", 1), ("x", 2))),),
        "OWNERSHIP": (b.Step("panel", "update", kwargs=(("ownership", None),)),),
        "KEYTYPE": (b.Step("panel", "update", kwargs=((1, True),)),),
        "ROWTYPE": (b.Step("panel", "update", kwargs=([1, True],)),),
    }
    if n in variants:
        steps = variants[n]
    else:
        steps = f.steps

        def generator(step, value):
            yield True

        async def asyncgen(step, value):
            yield True

        checker = {
            "GENERATOR": generator,
            "ASYNCGEN": asyncgen,
            "CALLABLE_OBJECT": object(),
            "BOOL_CHECKER": True,
        }[n]
    refuse(lambda: f.composition.prepare(steps, accept=checker))


def run_case(f, name):
    position = None
    if name.startswith("POSITION_"):
        _, phase, index = name.split("_")
        position = int(index)
        name = "F_BODY_RAISE" if phase == "BODY" else "F_CHECKER_RAISE"
    fixture(f, name)
    if position is not None:
        f.fault_at = position
        f.steps = f.steps * 32
    try:
        if name in HOOK_CASES + ACTOR_CASES + REFERENCE_CASES + CODE_CASES:
            matrix_case(f, name)
        elif name in CONTEXT_CASES:
            context_case(f, name)
        elif name in METHOD_CASES:
            method_case(f, name)
        elif name in POLICY_CASES:
            policy_case(f, name)
        elif name in PLAN_CASES:
            plan_case(f, name)
        else:
            f.plan = f.composition.prepare(f.steps, accept=f.accept)
            if name == "I_FENCED":
                f.registry.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
                refuse(f.plan.run)
            elif name == "F_NESTED":
                refuse(lambda: f.coordinator.call("PANEL", f.plan.run))
            elif name in FAILURE_CASES:
                refuse(
                    f.plan.run,
                    terminal=name in ("F_BODY_TERMINAL", "F_FINAL_TERMINAL"),
                    expected_runtime=name in ("F_BODY_RAISE", "F_CHECKER_RAISE"),
                )
            else:
                value = f.plan.run()
                require(value == (not f.noop,) * len(f.steps), "RETURN")
                require(f.registry.summary()["receipts"] == 1, "POSITIVE_RECEIPT")
                if name == "I_REPLAY":
                    refuse(f.plan.run)
    finally:
        restore(f)
        summary = f.registry.summary()
        DETAILS.update(
            body_calls=f.body_calls,
            checker_calls=f.checker_calls,
            final_calls=f.final_calls,
            registry_receipts=summary["receipts"],
            registry_generation=summary["generation"],
            unknown_writers=summary["unknown"],
            writer_total=summary["writers"],
            observations=f.gate.observations,
            phase=f.gate.last.phase,
            build_matched=f.gate.last.matched,
            source_checked=f.gate.last.source_checked,
            units_checked=f.gate.last.units_checked,
            surface_checked=f.gate.last.surface_checked,
            files_verified=f.files.last.verified,
            plan_used=None if f.plan is None else f.plan.used,
            failure_step=f.fault_at,
            panel_present=f.panel.exists(),
        )
    if name in CONTEXT_CASES + POLICY_CASES + PLAN_CASES:
        require(
            f.body_calls == 0 and summary["receipts"] == summary["unknown"] == 0,
            "PREADMISSION_EFFECT",
        )
    if name in FAILURE_CASES:
        require(summary["receipts"] == 0 and summary["unknown"] == 1, "FAILED_COMPLETED")
    if name in ("F_BODY_RAISE", "F_CHECKER_RAISE"):
        body_error = name == "F_BODY_RAISE"
        require(
            DETAILS["operation_error_observed"] is True
            and f.body_calls == f.fault_at
            and f.checker_calls == f.fault_at - int(body_error)
            and f.final_calls == 0
            and summary["writers"] == summary["unknown"] == 1
            and summary["generation"] == summary["receipts"] == 0
            and f.panel.exists() is (not body_error or f.fault_at > 1),
            "FAULT_POSITION_NOT_PROVEN",
        )
    if name in METHOD_CASES:
        late = name.rsplit("_", 1)[1] not in ("PREPARE", "RUN")
        require(
            f.body_calls == int(late)
            and summary["receipts"] == summary["generation"] == 0
            and summary["writers"] == int(late)
            and summary["unknown"] in (0, int(late)),
            "METHOD_FENCE_ACTUAL",
        )
    if name in POSITIVE_CASES:
        if name == "I_FENCED":
            require(f.body_calls == summary["receipts"] == summary["unknown"] == 0, "FENCE_EFFECT")
        else:
            require(
                f.body_calls == f.checker_calls == len(f.steps)
                and summary["receipts"] == summary["generation"] == 1
                and summary["unknown"] == 0,
                "POSITIVE_ACTUAL_COUNTS",
            )


FLAGS = (
    "installed_runtime_changed",
    "runtime_actor_binding_implemented",
    "runtime_writer_fence_verified",
    "runtime_verifier_implemented",
    "runtime_recovery_implemented",
    "repair_implemented",
    "active_faults_authorized",
)


def read_record(path):
    private(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(before.st_mode)
            and before.st_uid == os.getuid()
            and stat.S_IMODE(before.st_mode) == 0o600
            and before.st_nlink == 1
            and before.st_size <= 1048576,
            "RECORD_METADATA",
        )
        raw = stream.read(1048577)
        after = os.fstat(stream.fileno())

    def fields(s):
        return (s.st_dev, s.st_ino, s.st_uid, s.st_mode, s.st_size, s.st_mtime_ns)

    require(len(raw) <= 1048576 and fields(before) == fields(after), "RECORD_CHANGED")

    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, "DUPLICATE_RECORD_KEY")
            result[k] = v
        return result

    return json.loads(raw, object_pairs_hook=pairs)


def batch():
    global DETAILS
    SUPPORT.create(NOTES / "worker-claimed.json", {"claimed": True})
    os.umask(0o077)
    SUPPORT.atomic("progress.json", {"final": False, "completed": 0, "cases": []})
    source_count = SUPPORT.verify_source()
    source()
    cases = NOTES / "cases"
    cases.mkdir(mode=0o700)
    rows = []
    scope_stopped = False
    started = time.monotonic()
    for name in EXPECTED:
        root = cases / f"case-{len(rows) + 1:03d}"
        root.mkdir(mode=0o700)
        before = time.monotonic()
        f = None
        DETAILS = dict.fromkeys(DETAIL_KEYS)
        try:
            f = SimpleNamespace(root=root, work=root)
            run_case(f, name)
            row = {"case": name, "passed": True}
        except Exception as exc:
            scope_stopped = isinstance(exc, (SUPPORT.ScopeStop, OSError, TargetRestoreStop))
            public, line = "UNKNOWN", None
            tb = exc.__traceback__
            while tb is not None:
                filename = Path(tb.tb_frame.f_code.co_filename)
                try:
                    public, line = filename.relative_to(NOTES / "source").as_posix(), tb.tb_lineno
                except ValueError:
                    mapping = {
                        "batch.py": "wave3_bound_composition.py",
                        "ak.py": "wave3_code_handshake.py",
                        "support.py": "wave3_source_hooks.py",
                        "legacy.py": (
                            "legacy@63c9c413930eb348d46b2ff986bef46dd2e423d4/src/xgw/ownership.py"
                        ),
                    }
                    if filename.parent == NOTES and filename.name in mapping:
                        public, line = "tests/stand/" + mapping[filename.name], tb.tb_lineno
                tb = tb.tb_next
            row = {
                "case": name,
                "passed": False,
                "reason": "BOUND_COMPOSITION_CASE_FAILED",
                "error_class": type(exc).__name__
                if type(exc).__name__
                in (
                    "ValueError",
                    "TypeError",
                    "RuntimeError",
                    "OSError",
                    "ScopeStop",
                    "TargetRestoreStop",
                    "Refused",
                    "IdentityRefused",
                    "SealRefused",
                    "SurfaceRefused",
                    "AssertionError",
                    "CompletionRefused",
                    "MutationBlocked",
                )
                else "OTHER_EXCEPTION_CLASS",
                "public_error_source": public,
                "public_error_line": line,
            }
        row.update(details=DETAILS, elapsed_ms=int((time.monotonic() - before) * 1000))
        rows.append(row)
        SUPPORT.atomic("progress.json", {"final": False, "completed": len(rows), "cases": rows})
        if SUPPORT.AUDIT["violations"] or scope_stopped:
            break
    passed = sum(row["passed"] for row in rows)
    result = {
        "marker": "BOUND_COMPOSITION_BATCH_RECORDED"
        if passed == len(EXPECTED)
        else "BOUND_COMPOSITION_BATCH_PARTIAL",
        "scope": "OPERATION_FAULT_POSITION_QUALIFICATION_ONLY",
        "expected": len(EXPECTED),
        "completed": len(rows),
        "passed": passed,
        "cases": rows,
        "global_scope_stop": scope_stopped or SUPPORT.AUDIT["violations"] > 0,
        "remaining_not_run": len(EXPECTED) - len(rows),
        "source_files": source_count,
        "unit_files": len(UNITS),
        "declared_surfaces": 65,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "audit_registered": SUPPORT.AUDIT["ready"],
        "unexpected_forbidden_io": SUPPORT.AUDIT["violations"],
        "workload_subprocesses": 0,
        "network_requests": 0,
        "live_gateway_operations": 0,
        "installed_runtime_changed": False,
        "runtime_actor_binding_implemented": False,
        "runtime_writer_fence_verified": False,
        "runtime_verifier_implemented": False,
        "runtime_recovery_implemented": False,
        "repair_implemented": False,
        "active_faults_authorized": False,
    }
    SUPPORT.atomic("summary.json", result)


def report():
    context = SUPPORT.read(NOTES / "source-current.json")
    require(
        type(context) is dict
        and set(context) == {"head", "tree"}
        and all(type(v) is str and re.fullmatch(r"[0-9a-f]{40}", v) for v in context.values()),
        "REPORT_SOURCE_CONTEXT",
    )
    snapshot = NOTES / "report-record.json"
    if snapshot.exists() or snapshot.is_symlink():
        record = read_record(snapshot)
        require(
            type(record) is dict
            and set(record) == {"context", "selected", "data"}
            and record["context"] == context,
            "REPORT_SNAPSHOT",
        )
        selected, data = record["selected"], record["data"]
    else:
        selected = next(
            (n for n in ("summary.json", "progress.json") if (NOTES / n).exists()), None
        )
        require(selected is not None, "NO_RECORDED_RESULT")
        data = read_record(NOTES / selected)
    require(selected in ("summary.json", "progress.json"), "REPORT_SELECTED_FILE")
    require(type(data) is dict and type(data.get("cases")) is list, "REPORT_SCHEMA")
    numeric = {
        "expected",
        "completed",
        "passed",
        "remaining_not_run",
        "source_files",
        "unit_files",
        "declared_surfaces",
        "elapsed_ms",
        "unexpected_forbidden_io",
        "workload_subprocesses",
        "network_requests",
        "live_gateway_operations",
    }
    boolean = set(FLAGS) | {"audit_registered", "global_scope_stop"}
    require(set(data) <= numeric | boolean | {"marker", "scope", "cases", "final"}, "REPORT_FIELDS")
    for key in numeric:
        val = data.get(key)
        require(val is None or (type(val) is int and 0 <= val <= 2**63 - 1), "CONTROL_TYPE")
    for key in boolean:
        require(data.get(key) is None or type(data[key]) is bool, "CONTROL_TYPE")
    if selected == "summary.json":
        require(
            "final" not in data
            and data.get("scope") == "OPERATION_FAULT_POSITION_QUALIFICATION_ONLY"
            and data.get("marker")
            in ("BOUND_COMPOSITION_BATCH_RECORDED", "BOUND_COMPOSITION_BATCH_PARTIAL"),
            "REPORT_IDENTITY",
        )
    else:
        require(
            set(data) == {"final", "completed", "cases"} and data.get("final") is False,
            "CHECKPOINT_ONLY",
        )
    rows = data["cases"]
    require(len(rows) <= len(EXPECTED) and data.get("completed") == len(rows), "REPORT_COUNT")
    manifest = SUPPORT.read(NOTES / "manifest.json")
    lines = [
        "# Отчёт: XGW wave3ao — operation exception qualification",
        "",
        "Автоматические exact данные; таблицу не редактировать. worker_exit_rc=NOT_COLLECTED.",
        "Explicit composition/private FILES; installed runtime не активировался.",
        "",
        "Delivery HEAD/tree: " + context["head"] + " / " + context["tree"],
        "Legacy public reference: " + LEGACY_COMMIT + " / " + LEGACY_SHA,
        "Selected: " + selected,
        "Controls: `"
        + json.dumps({k: v for k, v in data.items() if k != "cases"}, sort_keys=True)
        + "`",
        "",
        "|Case|passed|exact ms|actual details|public error|",
        "|---|---|---|---|---|",
    ]
    boolkeys, intkeys = BOOL_KEYS, INT_KEYS
    for i, row in enumerate(rows):
        require(
            type(row) is dict
            and set(row)
            <= {
                "case",
                "passed",
                "details",
                "elapsed_ms",
                "reason",
                "error_class",
                "public_error_source",
                "public_error_line",
            },
            "ROW_FIELDS",
        )
        require(
            row.get("case") == EXPECTED[i]
            and type(row.get("passed")) is bool
            and type(row.get("elapsed_ms")) is int
            and 0 <= row["elapsed_ms"] <= 2**63 - 1,
            "ROW_SHAPE",
        )
        d = row.get("details")
        require(type(d) is dict and set(d) == set(DETAIL_KEYS), "DETAIL_FIELDS")
        for k in intkeys:
            require(d[k] is None or (type(d[k]) is int and 0 <= d[k] <= 2**63 - 1), "DETAIL_COUNT")
        for k in boolkeys:
            require(d[k] is None or type(d[k]) is bool, "DETAIL_BOOL")
        require(d["phase"] is None or d["phase"] in PHASES, "DETAIL_PHASE")
        cls = row.get("error_class")
        require(
            cls is None
            or cls
            in (
                "ValueError",
                "TypeError",
                "RuntimeError",
                "OSError",
                "ScopeStop",
                "TargetRestoreStop",
                "Refused",
                "IdentityRefused",
                "SealRefused",
                "SurfaceRefused",
                "AssertionError",
                "CompletionRefused",
                "MutationBlocked",
                "OTHER_EXCEPTION_CLASS",
            ),
            "ERROR_CLASS",
        )
        public = row.get("public_error_source")
        require(
            public is None
            or public in manifest
            or public
            in (
                "UNKNOWN",
                "tests/stand/wave3_code_handshake.py",
                "tests/stand/wave3_bound_composition.py",
                "tests/stand/wave3_source_hooks.py",
                "tests/stand/legacy@63c9c413930eb348d46b2ff986bef46dd2e423d4/src/xgw/ownership.py",
            ),
            "ERROR_SOURCE",
        )
        line = row.get("public_error_line")
        require(line is None or (type(line) is int and 0 < line <= 200000), "ERROR_LINE")
        lines.append(
            "|"
            + "|".join(
                (
                    row["case"],
                    json.dumps(row["passed"]),
                    str(row["elapsed_ms"]),
                    json.dumps(d, sort_keys=True, separators=(",", ":")),
                    json.dumps([cls, public, line], separators=(",", ":")),
                )
            )
            + "|"
        )
    lines += [
        "",
        "Null = не собрано. Case PASS отрицательного сценария не означает завершение операции.",
        "Значения7 runtime gates приведены в Controls. Case PASS не разрешает активацию.",
        "Host не LAN proof.",
        "",
    ]
    raw = ("\n".join(lines)).encode()
    if not snapshot.exists():
        clean = {k: v for k, v in data.items() if k != "cases"}
        clean["cases"] = [{k: v for k, v in r.items() if k != "reason"} for r in rows]
        SUPPORT.create(snapshot, {"context": context, "selected": selected, "data": clean})
    target = NOTES / "report-data.md"
    if target.exists() or target.is_symlink():
        private(target)
        require(target.read_bytes() == raw, "REPORT_DATA_CHANGED")
    else:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
    print("BOUND_COMPOSITION_REPORT_READY")


if __name__ == "__main__":
    try:
        require(os.geteuid() != 0 and len(sys.argv) == 2, "OWNER_OR_MODE")
        bootstrap()
        command = sys.argv[1]
        if command in ("status", "show"):
            for filename in ("summary.json", "progress.json"):
                if (NOTES / filename).exists():
                    print(json.dumps({"file": filename, "data": read_record(NOTES / filename)}))
                    break
            else:
                print(json.dumps({"file": None, "status": "NO_RECORDED_RESULT"}))
        elif command == "report":
            report()
        elif command == "start":
            SUPPORT.create(NOTES / "started.json", {"started": True})
            subprocess.Popen(
                [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "_batch"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            print("BOUND_COMPOSITION_BATCH_STARTED")
        else:
            require(command == "_batch", "MODE_REFUSED")
            batch()
    except Exception:
        print("BOUND_COMPOSITION_BATCH_STOP", "LOCAL_IO_OR_SCHEMA_ERROR")
        raise SystemExit(3) from None
