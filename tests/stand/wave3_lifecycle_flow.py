"""AJ: lifecycle source regression with private files/SQLite and fake external effects."""

# ruff: noqa: E731
import contextlib
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
from types import SimpleNamespace as NS

NOTES = Path.home() / "xgw-w3aj"
SUPPORT_SHA = "9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917"
MANIFEST_SHA = "9bdbe832baebed2dd8d56deffa2948e6141b47b6a0b22e2422235f62bf2a8d3d"
VARIANTS = {
    "ENABLE": ("NO_CAPTURE", "OK", "NO_HTTP", "CAP_ERROR", "HELD_BLOCKED", "HELD_OPEN"),
    "CHECKED": ("NO_HTTP", "OK"),
    "DISABLE": ("NO_LAN", "LAN", "CAP_ERROR"),
    "NETWORK": (
        "UNCONFIG",
        "NO_LAN",
        "UNCHANGED",
        "CHANGED",
        "DHCP_ERROR",
        "CAP_ERROR",
        "BOTH_ERROR",
    ),
    "PIN": ("NO_BINARY", "BAD_TTL", "FOREVER", "NO_TAG", "API_ERROR", "OK", "DAEMON_DOWN"),
    "UNPIN": ("NO_BINARY", "API_ERROR", "STICKY", "OK"),
    "POOL_MODE": (
        "INVALID",
        "REFUSE_OFF",
        "REFUSE_ON",
        "NO_CHANGE",
        "ON_EMPTY",
        "ON_READY",
        "RETURN_OBSERVE",
        "ERROR",
    ),
    "HOUSE": ("EXISTS", "CHANGED", "UNCHANGED", "ERROR"),
    "POOL_PIN": ("AUTO", "INVALID", "AMBIGUOUS", "CHOSEN", "INACTIVE", "ERROR"),
    "CORE": ("INVALID", "NOT_FOUND", "XR_TO_SB", "SB_TO_XR", "NO_CHANGE", "CHANGED", "ERROR"),
    "INVENTORY": ("EMPTY", "ONE", "WRITE_ERROR"),
    "FINGERPRINTS": ("EMPTY", "FRESH", "EXPIRED", "WRITE_ERROR"),
    "COLLECT": ("EMPTY", "MANUAL", "REMOTE", "CANCEL", "WRITE_ERROR"),
    "PERSIST": ("EMPTY", "NODES", "CORE", "NO_EVENT", "UNAPPLIED", "SQL_ERROR"),
    "APPLY": (
        "NO_SB",
        "STARTED",
        "DEFERRED",
        "REJECTED",
        "ROLLBACK",
        "FAILED",
        "AUTO",
        "XR_ERROR",
        "SB_ERROR",
        "UNCHANGED",
    ),
}
MODES = ("LEGACY", "OWNED", "FENCED")
MATRIX = tuple(g + "_" + v for g, vs in VARIANTS.items() for v in vs)
DEPENDENCIES = ("ENABLE", "CHECKED", "DISABLE", "NETWORK", "APPLIER", "SINGBOX")
DEP_ERRORS = ("UNBOUND", "FOREIGN", "TYPE", "SHADOW")
BOUNDARY = tuple("B_" + d + "__" + e for d in DEPENDENCIES for e in DEP_ERRORS)
DEFINITIONS = (
    "N_ROWS",
    "N_ROW",
    "N_NAME",
    "N_DUP",
    "N_CLASS",
    "N_METHODS",
    "N_METHOD",
    "N_DUP_METHOD",
    "N_OPTIONAL",
    "N_PARAMETER",
    "N_ASYNC",
    "N_SIGNATURE",
)
DRIFT = (
    "D_REGISTRY",
    "D_VERIFIER",
    "D_CALL",
    "D_CLASS",
    "D_CAPTURE",
    "D_APPLIER",
    "D_SINGBOX",
    "D_NESTED_CAUGHT",
    "D_NO_VERIFIER",
    "D_TERMINAL",
)
FACTORIES = tuple(
    "F_" + d + "__" + e for d in ("API_PIN", "API_UNPIN", "SINGBOX") for e in DEP_ERRORS
)
COMPOSITES = tuple(
    "C_" + s + "__" + x
    for s in ("STARTED", "DEFERRED", "REJECTED", "FAILED")
    for x in ("RESTART", "UNCHANGED", "REJECTED", "FAILED")
)
FILES = (
    "I_FILES_OK",
    "I_FILES_BAD",
    "I_FILES_MODE",
    "I_ROLE_MISSING",
    "I_DOMAIN_UNKNOWN",
    "I_FALSE_RESULT",
    "I_EARLY_LEASE",
    "I_FENCED",
)
EXPECTED = (
    tuple(n + "__" + m for n in MATRIX for m in MODES)
    + BOUNDARY
    + DEFINITIONS
    + DRIFT
    + FACTORIES
    + COMPOSITES
    + FILES
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
DETAIL_KEYS = (
    "registry_receipts",
    "registry_generation",
    "unknown_writers",
    "stub_calls",
    "file_checked",
    "file_matched",
    "accept_entered",
    "observation_entered",
    "completion_verified",
    "rejection_observed",
    "verification_accepted",
    "outcome",
    "evidence_reason",
    "expected_return",
    "observed_return",
    "effect_equivalent",
)
REASONS = frozenset(
    (
        "NOT_OBSERVED",
        "FILES_VERIFIED",
        "VERIFIER_CONTEXT",
        "VERIFIER_DRIFT",
        "OBSERVER_DRIFT",
        "ROLE_COVERAGE",
        "DOMAIN_NOT_IMPLEMENTED",
        "RESULT_NOT_ACCEPTED",
        "VERIFIER_TAINTED",
        "OBSERVATION_TYPE",
        "FILES_NOT_VERIFIED",
        "CHECK_ERROR",
        "CHECK_INTERRUPTED",
    )
)
SUPPORT = None
M = {}
DETAILS = None
REFERENCES = {}


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
    global SUPPORT
    private(NOTES, True)
    for name, digest in (("support.py", SUPPORT_SHA), ("manifest.json", MANIFEST_SHA)):
        private(NOTES / name)
        require(hashlib.sha256((NOTES / name).read_bytes()).hexdigest() == digest, "ARTIFACT_SHA")
    spec = importlib.util.spec_from_file_location("aj_fixture_support", NOTES / "support.py")
    SUPPORT = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(SUPPORT)
    SUPPORT.NOTES, SUPPORT.MANIFEST_SHA = NOTES, MANIFEST_SHA
    return SUPPORT.verify_source()


def source():
    global M
    SUPPORT.install_audit()
    SUPPORT.load_source()
    M = SUPPORT.MODULES
    for n in (
        "actions",
        "engine",
        "ownership_entrypoints",
        "ownership_files",
        "ownership_completion",
    ):
        M[n] = importlib.import_module("frozen_ad." + n)


def enum(value):
    if value is None:
        return "NONE"
    if type(value) is bool:
        return "TRUE" if value else "FALSE"
    if isinstance(value, M["actions"].Outcome):
        return "OUTCOME_" + str(value.code)
    if isinstance(value, M["engine"].Inventory):
        return "INVENTORY"
    if type(value) is tuple and len(value) == 2:
        if all(type(x) is list for x in value):
            return "NETWORK_" + str(len(value[0])) + "_" + str(len(value[1]))
        modes = [getattr(x, "mode", "NONE") if x is not None else "NONE" for x in value]
        require(
            all(
                x
                in (
                    "NONE",
                    "restart",
                    "unchanged",
                    "rejected",
                    "failed",
                    "started",
                    "deferred",
                    "rollback",
                )
                for x in modes
            ),
            "RETURN_MODE",
        )
        return "APPLY_" + "_".join(modes)
    raise ValueError("RETURN_TYPE")


def invoke(call):
    try:
        return enum(call())
    except M["ownership_hooks"].MutationBlocked:
        return "BLOCKED"
    except M["engine"].fetch.Cancelled:
        return "CANCELLED"
    except SUPPORT.ScopeStop:
        raise
    except RuntimeError:
        return "RUNTIME_ERROR"


def fail(error, f, label):
    def operation(*args, **kwargs):
        f.event(label)
        raise error("PRIVATE_FIXTURE_ERROR")

    return operation


def prepare(f, group, variant, ownership):
    """All setup precedes the tested entrypoint; each low-level boundary is explicit."""
    a, e, managed = M["actions"], M["engine"], M["managed"]
    cfg = M["config"].Config()
    cfg.network.lan_if = ""
    cfg.capture.local, cfg.capture.lan = True, False
    cfg.speed.sticky = False
    f.paths.ensure()
    # Real private SQLite is allowed; fixed wall clock makes differential bytes stable.
    f.changes += [
        (time, "time", lambda: 100000.0),
        (e, "healthy_http_in", lambda cfg: None if variant == "NO_HTTP" else ("fixture", 1)),
    ]
    original_ensure = type(f.paths).ensure
    f.changes.append((type(f.paths), "ensure", lambda p: f.event("ENSURE") or original_ensure(p)))
    f.bad = False
    original_verifier = f.coordinator.verifier

    def verifier(roles, value):
        if f.bad:
            return M["ownership_adapters"].Verification()
        # Matrix is a source equivalence assertion, NOT a live completion policy.
        f.roles = roles
        return M["ownership_adapters"].Verification("COMMITTED", (("FILES", True),))

    f.coordinator.verifier = verifier
    f.original_verifier = original_verifier
    f.cfg = cfg
    f.capture_actor = f.applier_actor = f.singbox_actor = None
    if group in ("ENABLE", "CHECKED", "DISABLE", "NETWORK"):
        c, _ = f.capture("C_ENABLE")
        c.cfg.capture.local = (
            variant not in ("NO_CAPTURE", "UNCONFIG", "NO_LAN") or group == "DISABLE"
        )
        c.cfg.network = cfg.network
        c.held = "fixture" if variant.startswith("HELD_") else ""
        c.describe = lambda **kwargs: {"lan": False, "lan_if": "", "local": True, "bypass": []}
        if variant in (
            "LAN",
            "UNCHANGED",
            "CHANGED",
            "DHCP_ERROR",
            "CAP_ERROR",
            "BOTH_ERROR",
        ) and group in ("DISABLE", "NETWORK"):
            cfg.network.lan_if = "fixture0"
        loaded = (
            "blocked" if variant == "HELD_BLOCKED" else "off" if variant == "HELD_OPEN" else "on"
        )
        c._load = (
            fail(M["net.capture"].CaptureError, f, "LOAD_ERROR")
            if variant in ("CAP_ERROR", "BOTH_ERROR")
            else lambda mode: f.event("LOAD") or loaded
        )
        c.ownership = ownership
        f.capture_actor = c
        if group == "NETWORK":
            changed = variant in ("CHANGED", "DHCP_ERROR", "BOTH_ERROR", "CAP_ERROR")
            f.changes.append(
                (a.dnsmasq, "write_conf", lambda *args: f.event("DNSMASQ_STUB") or (changed, []))
            )
            runner = (
                fail(a.cmd.CommandError, f, "SERVICE_ERROR")
                if variant in ("DHCP_ERROR", "BOTH_ERROR")
                else f.runner
            )
            return lambda: a.apply_network(
                cfg, f.paths, c, logger=f.log, runner=runner, ownership=ownership
            )
        return lambda: getattr(
            a, {"ENABLE": "enable", "CHECKED": "enable_checked", "DISABLE": "disable"}[group]
        )(cfg, f.paths, c, ownership=ownership)
    if group in ("PIN", "UNPIN"):
        api, _ = f.api("API_PIN")
        object.__setattr__(api, "ownership", ownership)
        if variant == "API_ERROR":
            object.__setattr__(api, "_run", fail(a.ApiError, f, "API_ERROR"))
        f.api_actor = api

        def factory(*args, **kwargs):
            f.event("API_FACTORY")
            object.__setattr__(api, "ownership", kwargs.get("ownership"))
            return api

        f.changes += [
            (e, "make_api", factory),
            (
                a.validate,
                "find_xray",
                lambda *args: None if variant == "NO_BINARY" else f.work / "dummy",
            ),
            (
                a.builder,
                "applied_nodes",
                lambda *args: [] if variant == "NO_TAG" else [NS(tag="fixture", role="proxy")],
            ),
            (e, "read_json", lambda *args: {}),
            (a.status, "read_status", lambda *args: None if variant == "DAEMON_DOWN" else {}),
        ]
        cfg.speed.sticky = variant == "STICKY"
        return (
            (
                lambda: a.pin(
                    cfg,
                    f.paths,
                    "fixture",
                    "forever" if variant == "FOREVER" else "bad" if variant == "BAD_TTL" else "30s",
                    ownership=ownership,
                )
            )
            if group == "PIN"
            else lambda: a.unpin(cfg, f.paths, ownership=ownership)
        )
    if group in ("POOL_MODE", "HOUSE", "POOL_PIN", "CORE"):
        path = f.work / "panel.json"
        base, _ = managed.load(path)
        if group == "POOL_MODE":
            base["free_pool_mode"] = (
                "observe"
                if variant == "NO_CHANGE"
                else "on"
                if variant == "RETURN_OBSERVE"
                else "off"
            )
            if variant == "REFUSE_OFF":
                base["routes"] = [{"name": "fixture", "ip": "192.0.2.2", "server": "pool"}]
            mode = (
                "invalid"
                if variant == "INVALID"
                else "off"
                if variant == "REFUSE_OFF"
                else "on"
                if variant in ("REFUSE_ON", "ON_EMPTY", "ON_READY")
                else "observe"
            )
            operation = lambda: a.set_pool_mode(
                f.paths,
                path,
                mode,
                refuse_closing=variant.startswith("REFUSE"),
                ready=1 if variant == "ON_READY" else 0,
                ownership=ownership,
            )
        elif group == "HOUSE":
            base["free_pool_mode"] = "observe" if variant == "UNCHANGED" else "on"
            if variant == "EXISTS":
                f.paths.house_file.touch()
            operation = lambda: a.house_after_boot(f.paths, path, ownership=ownership)
        elif group == "POOL_PIN":
            traffic = importlib.import_module(e.__package__ + ".freepool.traffic")
            candidate = NS(node=NS(fingerprint="a" * 32, country="XX", name="fixture"))
            choices = (
                []
                if variant == "INVALID"
                else [candidate, candidate]
                if variant == "AMBIGUOUS"
                else [candidate]
            )
            f.changes += [
                (traffic, "admitted", lambda *args: choices),
                (traffic, "pool_active", lambda *args: variant != "INACTIVE"),
            ]
            operation = lambda: a.set_pool_pin(
                f.paths,
                path,
                cfg,
                "auto" if variant in ("AUTO", "INACTIVE", "ERROR") else "a" * 6,
                ownership=ownership,
            )
            if variant == "ERROR":
                base["free_pool_pin"] = "a" * 32
        else:
            capability = (
                "singbox" if variant == "SB_TO_XR" else "xray" if variant == "XR_TO_SB" else "dual"
            )
            f.changes.append(
                (
                    a,
                    "pick_server",
                    lambda *args: (
                        (None, "fixture")
                        if variant == "NOT_FOUND"
                        else ({"fingerprint": "a" * 8, "name": "fixture", "core": capability}, "")
                    ),
                )
            )
            if variant == "NO_CHANGE":
                base["core"] = {"a" * 8: "xray"}
            core = (
                "invalid"
                if variant == "INVALID"
                else "sing-box"
                if variant == "XR_TO_SB"
                else "xray"
            )
            operation = lambda: a.set_core(f.paths, path, "fixture", core, ownership=ownership)
        f.write(path, base)
        if variant == "ERROR":
            f.changes.append((managed, "atomic_write_json", fail(OSError, f, "PANEL_WRITE_ERROR")))
        return operation
    if group == "INVENTORY":
        node = NS(
            keep_tag=False,
            fingerprint="a" * 8,
            name="fixture",
            source="fixture",
            protocol="fixture",
            capability="xray",
            singbox=None,
        )
        f.changes += [
            (e, "singbox_available", lambda *args: False),
            (e.builder, "skip_reason", lambda *args, **kwargs: ""),
        ]
        inventory = e.Inventory(nodes=[] if variant == "EMPTY" else [node])
        if variant == "WRITE_ERROR":
            f.changes.append(
                (e, "atomic_write_json", fail(RuntimeError, f, "INVENTORY_WRITE_ERROR"))
            )
        return lambda: e.save_inventory(f.paths, cfg, inventory, ownership=ownership)
    if group == "FINGERPRINTS":
        known = (
            {}
            if variant == "EMPTY"
            else {"a" * 8: {"b" * 16: ["c" * 8, -3000000 if variant == "EXPIRED" else 99999]}}
        )
        if variant == "WRITE_ERROR":
            f.bad = True
            f.changes.append((e, "atomic_write_json", fail(OSError, f, "FINGERPRINT_WRITE_ERROR")))
        return lambda: e._save_fingerprints(f.paths, known, 100000, f.log, ownership=ownership)
    if group == "COLLECT":
        cfg.subscriptions = (
            [NS(url="https://fixture.invalid", name="fixture")]
            if variant in ("REMOTE", "CANCEL")
            else []
        )
        cfg.manual.links = ["fixture"] if variant == "MANUAL" else []
        f.changes += [
            (
                e,
                "_load_subscription",
                lambda *args, **kwargs: f.event("SUBSCRIPTION_STUB") or ([], {}, "fixture"),
            ),
            (e, "parse_links_text", lambda *args: ([], {}, ["fixture"])),
        ]
        if variant == "WRITE_ERROR":
            f.bad = True
            f.changes.append((e, "atomic_write_json", fail(OSError, f, "FINGERPRINT_WRITE_ERROR")))
        cancel = NS(is_set=lambda: True) if variant == "CANCEL" else None
        return lambda: e.collect(
            cfg, f.paths, mark=None, logger=f.log, cancel=cancel, ownership=ownership
        )
    if group == "PERSIST":
        node = NS(
            fingerprint="a" * 8, name="fixture", source="fixture", address="fixture.invalid", port=1
        )
        info = NS(fingerprint="a" * 8, tag="fixture", probe_tag="fixture", role="proxy")
        assembly = NS(
            result=NS(nodes=[] if variant == "EMPTY" else [info], pool=[]),
            selection=NS(members=[] if variant == "EMPTY" else [node], spares=[]),
            core={"fixture": True} if variant in ("CORE", "UNAPPLIED") else {},
        )
        f.changes.append((e, "summary", lambda *args: {"fixture": 1}))
        if variant == "SQL_ERROR":
            f.bad = True
            f.changes.append((e, "Store", fail(OSError, f, "STORE_ERROR")))
        return lambda: e.persist(
            f.paths,
            assembly,
            {},
            record_event=variant != "NO_EVENT",
            applied=variant != "UNAPPLIED",
            ownership=ownership,
        )
    require(group == "APPLY", "GROUP_UNKNOWN")
    return prepare_apply(f, variant, ownership)


def prepare_apply(f, variant, ownership, *, sb_mode=None, xr_mode=None):
    e = M["engine"]
    xr, _ = f.xray("X_APPLY")
    sb, _ = f.singbox("S_APPLY")
    xr.ownership = sb.ownership = ownership
    sm = sb_mode or {
        "DEFERRED": "deferred",
        "REJECTED": "rejected",
        "ROLLBACK": "rollback",
        "FAILED": "failed",
        "UNCHANGED": "unchanged",
    }.get(variant, "started")
    xm = xr_mode or ("unchanged" if variant == "UNCHANGED" else "restart")

    def sb_install(config, first):
        f.event("SB_INSTALL")
        e.atomic_write_json(f.paths.singbox_config_file, config)
        if variant == "SB_ERROR":
            raise RuntimeError("PRIVATE_FIXTURE")
        return M["apply.singbox"].SingboxOutcome(sm)

    sb._install = sb_install
    if sm == "rejected":
        sb.validator = lambda config: (False, "fixture")
    if sm == "unchanged":
        f.write(f.paths.singbox_config_file, {"inbounds": []})

    def xr_apply(config, **kwargs):
        f.event("XR_APPLY")
        e.atomic_write_json(f.paths.xray_config_file, config)
        if variant == "XR_ERROR":
            raise RuntimeError("PRIVATE_FIXTURE")
        return M["apply.applier"].ApplyOutcome(xm)

    xr._apply_locked = xr_apply
    if variant == "NO_SB":
        assembly_sb = None
    else:
        assembly_sb = NS(config={"inbounds": []}, reload=sm != "deferred")
    assembly = NS(result=NS(config={"inbounds": []}), singbox=assembly_sb)
    f.applier_actor, f.singbox_actor = xr, sb
    f.assembly = assembly

    def factory(*args, **kwargs):
        f.event("SB_FACTORY")
        sb.ownership = kwargs.get("ownership")
        return sb

    f.changes.append((e, "make_singbox", factory))
    return lambda: e.apply_all(
        f.cfg,
        f.paths,
        assembly,
        xr,
        force_now=True,
        singbox_core=None if variant == "AUTO" else sb,
        ownership=ownership,
    )


def matrix(f, name, mode):
    group = next(g for g in VARIANTS if name.startswith(g + "_"))
    variant = name[len(group) + 1 :]
    ownership = None if mode == "LEGACY" else f.coordinator
    call = prepare(f, group, variant, ownership)
    if mode == "FENCED":
        f.registry.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
    before = SUPPORT.digest_tree(f.work)
    with SUPPORT.patches(f.changes):
        result = invoke(call)
    after = SUPPORT.digest_tree(f.work)
    s = f.registry.summary()
    if mode == "LEGACY":
        REFERENCES[name] = (result, after, tuple(f.trace))
        DETAILS["expected_return"] = result
        require(s["receipts"] == s["writers"] == 0, "LEGACY_REGISTRY_CHANGED")
    elif mode == "OWNED":
        reference = REFERENCES.get(name)
        require(reference is not None, "LEGACY_REFERENCE_MISSING")
        equivalent = after == reference[1] and tuple(f.trace) == reference[2]
        DETAILS.update(expected_return=reference[0], effect_equivalent=equivalent)
        require(equivalent, "BODY_EFFECT_DIFFERENCE")
        execution = f.coordinator.last_execution
        require(execution is not None, "EXECUTION_MISSING")
        DETAILS["completion_verified"] = execution.status == "COMPLETED"
        if execution.status == "COMPLETED":
            require(
                result == reference[0] and s["receipts"] == 1 and s["unknown"] == 0, "OWNED_RESULT"
            )
        else:
            require(
                s["receipts"] == 0
                and s["unknown"] == 1
                and result in ("BLOCKED", "CANCELLED", "RUNTIME_ERROR"),
                "OWNED_UNKNOWN",
            )
    else:
        DETAILS.update(effect_equivalent=before == after, rejection_observed=result == "BLOCKED")
        require(
            result == "BLOCKED"
            and before == after
            and not f.trace
            and s["receipts"] == s["writers"] == 0,
            "FENCE_EFFECT",
        )
    DETAILS["observed_return"] = result


def boundary(f, name):
    dependency, error = name[2:].split("__")
    group = "APPLY" if dependency in ("APPLIER", "SINGBOX") else dependency
    call = prepare(
        f,
        group,
        "STARTED" if group == "APPLY" else "OK" if group in ("ENABLE", "CHECKED") else "NO_LAN",
        f.coordinator,
    )
    actor = (
        f.applier_actor
        if dependency == "APPLIER"
        else f.singbox_actor
        if dependency == "SINGBOX"
        else f.capture_actor
    )
    method = (
        "apply"
        if group == "APPLY"
        else "enable"
        if group in ("ENABLE", "CHECKED")
        else "disable"
        if group == "DISABLE"
        else "up"
    )
    if error == "UNBOUND":
        actor.ownership = None
    elif error == "FOREIGN":
        actor.ownership = M["ownership_hooks"].Coordinator(f.registry, f.coordinator.verifier)
    elif error == "TYPE":

        class Foreign(type(actor)):
            pass

        actor.__class__ = Foreign
    else:
        setattr(actor, method, lambda *args, **kwargs: None)
    before = SUPPORT.digest_tree(f.work)
    with SUPPORT.patches(f.changes):
        result = invoke(call)
    DETAILS.update(
        rejection_observed=result == "BLOCKED",
        effect_equivalent=SUPPORT.digest_tree(f.work) == before,
    )
    s = f.registry.summary()
    require(
        result == "BLOCKED"
        and s["writers"] == s["receipts"] == 0
        and not f.trace
        and before == SUPPORT.digest_tree(f.work),
        "DEPENDENCY_NOT_REFUSED_BEFORE_ADMIT",
    )


def definition(f, name):
    module, capture = M["ownership_entrypoints"], M["net.capture"].Capture
    deps = (("capture", capture, ("enable",), False),)
    changes = {
        "N_ROWS": [],
        "N_ROW": ((),),
        "N_NAME": ((1, capture, ("enable",), False),),
        "N_DUP": deps + deps,
        "N_CLASS": (("capture", None, ("enable",), False),),
        "N_METHODS": (("capture", capture, [], False),),
        "N_METHOD": (("capture", capture, ("missing",), False),),
        "N_DUP_METHOD": (("capture", capture, ("enable", "enable"), False),),
        "N_OPTIONAL": (("capture", capture, ("enable",), 1),),
    }

    def fn(capture, *, ownership=None):
        raise ValueError("BODY_NOT_ALLOWED")

    if name == "N_PARAMETER":

        def fn(*, ownership=None):
            return None
    elif name == "N_ASYNC":

        async def fn(capture, *, ownership=None):
            return None
    elif name == "N_SIGNATURE":

        def fn(capture, ownership=None):
            return None

    try:
        module.owned_entrypoint("LIFECYCLE", dependencies=changes.get(name, deps))(fn)
    except M["ownership_hooks"].MutationBlocked:
        DETAILS["rejection_observed"] = True
    else:
        raise ValueError("INVALID_DEFINITION_ACCEPTED")


def extra(f, name):
    if name in BOUNDARY:
        return boundary(f, name)
    if name in DEFINITIONS:
        return definition(f, name)
    ownership = f.coordinator
    call = prepare(f, "APPLY", "AUTO" if name.startswith("F_SINGBOX") else "STARTED", ownership)
    if name in FACTORIES:
        target, error = name[2:].split("__")
        if target.startswith("API"):
            call = prepare(f, "PIN" if target == "API_PIN" else "UNPIN", "OK", ownership)
            actor = f.api_actor
        else:
            actor = f.singbox_actor

        def factory(*args, **kwargs):
            f.event("FOREIGN_FACTORY")
            if error == "TYPE":
                return NS(ownership=ownership)
            object.__setattr__(
                actor,
                "ownership",
                None
                if error == "UNBOUND"
                else M["ownership_hooks"].Coordinator(f.registry, f.coordinator.verifier)
                if error == "FOREIGN"
                else ownership,
            )
            if error == "SHADOW":
                object.__setattr__(
                    actor,
                    "pin" if target == "API_PIN" else "unpin" if target == "API_UNPIN" else "apply",
                    lambda *args, **kwargs: None,
                )
            return actor

        f.changes.append(
            (M["engine"], "make_api" if target.startswith("API") else "make_singbox", factory)
        )
    elif name in COMPOSITES:
        sb, xr = name[2:].split("__")
        call = prepare_apply(f, "STARTED", ownership, sb_mode=sb.lower(), xr_mode=xr.lower())

        def strict(roles, value):
            ok = (
                type(value) is tuple
                and value[0] is not None
                and value[0].mode in ("restart", "unchanged")
                and value[1].mode == "started"
            )
            return (
                M["ownership_adapters"].Verification("COMMITTED", (("FILES", True),))
                if ok
                else M["ownership_adapters"].Verification()
            )

        f.coordinator.verifier = strict
    elif name in FILES:
        # Expected dummy config bytes only; lock files are outside the named subset.
        fm, cm = M["ownership_files"], M["ownership_completion"]
        raw = (json.dumps({"inbounds": []}, ensure_ascii=False, indent=2) + "\n").encode()
        items = tuple(
            fm.FileExpectation(
                p.relative_to(f.work).as_posix(),
                "0" * 64 if name == "I_FILES_BAD" else hashlib.sha256(raw).hexdigest(),
                mode=0o600 if name == "I_FILES_MODE" else 0o640,
            )
            for p in (f.paths.singbox_config_file, f.paths.xray_config_file)
        )
        roles = (
            frozenset({"LIFECYCLE"})
            if name == "I_ROLE_MISSING"
            else frozenset({"LIFECYCLE", "CORE"})
        )
        domains = ("FILES", "KERNEL") if name == "I_DOMAIN_UNKNOWN" else ("FILES",)
        obs = fm.PrivateFiles(f.work, expected_uid=os.getuid(), expectations=items)
        v = cm.FileCompletion(
            cm.CompletionContract(roles, domains, "COMMITTED"),
            obs,
            accept=lambda value: name != "I_FALSE_RESULT",
        )
        f.coordinator.verifier = v
        f.completion = v
        if name == "I_FENCED":
            f.registry.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
        if name == "I_EARLY_LEASE":
            original = f.applier_actor._apply_locked

            def locked(*args, **kwargs):
                try:
                    f.registry.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
                except M["ownership"].Refused:
                    f.event("EARLY_LEASE_REFUSED")
                else:
                    raise ValueError("EARLY_LEASE_ADMITTED")
                return original(*args, **kwargs)

            f.applier_actor._apply_locked = locked
    else:
        require(name in DRIFT, "EXTRA_UNKNOWN")
        if name == "D_CAPTURE":
            call = prepare(f, "ENABLE", "OK", ownership)

            def capture_load(mode):
                f.event("CAPTURE_DRIFT")
                f.capture_actor.ownership = None
                return "on"

            f.capture_actor._load = capture_load
        elif name == "D_NO_VERIFIER":
            f.coordinator.verifier = None
        elif name == "D_CALL":
            f.coordinator.call = lambda *args: None
        elif name == "D_CLASS":
            f.changes.append((M["apply.applier"].Applier, "apply", lambda *args, **kwargs: None))
        else:
            original = f.singbox_actor._install

            def drift(*args, **kwargs):
                value = original(*args, **kwargs)
                if name == "D_REGISTRY":
                    f.coordinator.registry = M["ownership"].Registry(
                        f.root / "uninitialized", boot_id=SUPPORT.BOOT, expected_uid=os.getuid()
                    )
                elif name == "D_VERIFIER":
                    f.coordinator.verifier = lambda *args: M["ownership_adapters"].Verification()
                elif name == "D_APPLIER":
                    f.applier_actor.ownership = None
                elif name == "D_SINGBOX":
                    f.singbox_actor.ownership = None
                elif name == "D_TERMINAL":
                    raise SystemExit(9)
                else:
                    with contextlib.suppress(RuntimeError):
                        f.coordinator.call("API", fail(RuntimeError, f, "NESTED_ERROR"))
                return value

            f.singbox_actor._install = drift
    try:
        with SUPPORT.patches(f.changes):
            result = invoke(call)
    except SystemExit:
        require(name == "D_TERMINAL", "UNEXPECTED_TERMINAL")
        result = "TERMINAL"
    finally:
        # Restore only fixture references so failure bookkeeping can be read, not product repair.
        f.coordinator.registry = f.registry
    s = f.registry.summary()
    positive = name in ("C_STARTED__RESTART", "C_STARTED__UNCHANGED", "I_FILES_OK", "I_EARLY_LEASE")
    pre = name in ("D_NO_VERIFIER", "D_CALL", "D_CLASS", "I_FENCED")
    DETAILS.update(
        observed_return=result,
        completion_verified=s["receipts"] == 1,
        rejection_observed=not positive,
    )
    require(s["receipts"] == (1 if positive else 0), "EXTRA_RECEIPTS")
    require(s["unknown"] == (0 if positive or pre else 1), "EXTRA_UNKNOWN")
    if name in ("D_REGISTRY", "D_VERIFIER", "D_APPLIER", "D_SINGBOX", "D_NESTED_CAUGHT"):
        require("XR_APPLY" not in f.trace, "DRIFT_DID_NOT_STOP_NEXT_STEP")
    if name in FACTORIES:
        require(
            not any(x in f.trace for x in ("API_STUB", "SB_INSTALL")), "FOREIGN_FACTORY_BODY_CALLED"
        )
    if hasattr(f, "completion"):
        d = f.completion.last
        DETAILS.update(
            file_checked=d.checked,
            file_matched=d.matched,
            accept_entered=d.accept_entered,
            observation_entered=d.observation_entered,
            evidence_reason=d.reason,
        )


def run_case(f, name):
    if name in BOUNDARY + DEFINITIONS + DRIFT + FACTORIES + COMPOSITES + FILES:
        return extra(f, name)
    variant, mode = name.rsplit("__", 1)
    return matrix(f, variant, mode)


def batch():
    global DETAILS
    SUPPORT.create(NOTES / "worker-claimed.json", {"claimed": True})
    os.umask(0o077)
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
            f = SUPPORT.Fixture(root)
            run_case(f, name)
            row = {"case": name, "passed": True}
        except Exception as exc:
            scope_stopped = isinstance(exc, (SUPPORT.ScopeStop, OSError))
            public, line = "UNKNOWN", None
            tb = exc.__traceback__
            while tb is not None:
                filename = Path(tb.tb_frame.f_code.co_filename)
                try:
                    public, line = filename.relative_to(NOTES / "source").as_posix(), tb.tb_lineno
                except ValueError:
                    mapping = {
                        "batch.py": "wave3_lifecycle_flow.py",
                        "support.py": "wave3_source_hooks.py",
                    }
                    if filename.parent == NOTES and filename.name in mapping:
                        public, line = "tests/stand/" + mapping[filename.name], tb.tb_lineno
                tb = tb.tb_next
            row = {
                "case": name,
                "passed": False,
                "reason": "LIFECYCLE_FLOW_CASE_FAILED",
                "error_class": type(exc).__name__
                if type(exc).__name__
                in (
                    "ValueError",
                    "TypeError",
                    "RuntimeError",
                    "OSError",
                    "ScopeStop",
                    "AssertionError",
                    "CompletionRefused",
                    "MutationBlocked",
                )
                else "OTHER_EXCEPTION_CLASS",
                "public_error_source": public,
                "public_error_line": line,
            }
        if f is not None:
            DETAILS["stub_calls"] = len(f.trace)
            with contextlib.suppress(Exception):
                summary = f.registry.summary()
                DETAILS.update(
                    registry_receipts=summary["receipts"],
                    registry_generation=summary["generation"],
                    unknown_writers=summary["unknown"],
                )
        row.update(details=DETAILS, elapsed_ms=int((time.monotonic() - before) * 1000))
        rows.append(row)
        SUPPORT.atomic("progress.json", {"final": False, "completed": len(rows), "cases": rows})
        if SUPPORT.AUDIT["violations"] or scope_stopped:
            break
    passed = sum(row["passed"] for row in rows)
    result = {
        "marker": "LIFECYCLE_FLOW_BATCH_RECORDED"
        if passed == len(EXPECTED)
        else "LIFECYCLE_FLOW_BATCH_PARTIAL",
        "scope": "OPTIONAL_LIFECYCLE_SOURCE_FLOW_ONLY",
        "expected": len(EXPECTED),
        "completed": len(rows),
        "passed": passed,
        "cases": rows,
        "global_scope_stop": scope_stopped or SUPPORT.AUDIT["violations"] > 0,
        "remaining_not_run": len(EXPECTED) - len(rows),
        "source_files": source_count,
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
        record = SUPPORT.read(snapshot)
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
        data = SUPPORT.read(NOTES / selected)
    require(selected in ("summary.json", "progress.json"), "REPORT_SELECTED_FILE")
    require(type(data) is dict and type(data.get("cases")) is list, "REPORT_SCHEMA")
    numeric = {
        "expected",
        "completed",
        "passed",
        "remaining_not_run",
        "source_files",
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
            and data.get("scope") == "OPTIONAL_LIFECYCLE_SOURCE_FLOW_ONLY"
            and data.get("marker")
            in ("LIFECYCLE_FLOW_BATCH_RECORDED", "LIFECYCLE_FLOW_BATCH_PARTIAL"),
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
        "# Отчёт: XGW wave3aj — lifecycle source flow",
        "",
        "Автоматические exact данные; таблицу не редактировать. worker_exit_rc=NOT_COLLECTED.",
        "Только private source fixtures/SQLite; внешние эффекты stubbed. Runtime не активировался.",
        "",
        "Delivery HEAD/tree: " + context["head"] + " / " + context["tree"],
        "Selected: " + selected,
        "Controls: `"
        + json.dumps({k: v for k, v in data.items() if k != "cases"}, sort_keys=True)
        + "`",
        "",
        "|Case|passed|exact ms|actual details|public error|",
        "|---|---|---|---|---|",
    ]
    boolkeys = {
        "file_matched",
        "accept_entered",
        "observation_entered",
        "completion_verified",
        "rejection_observed",
        "verification_accepted",
        "effect_equivalent",
    }
    intkeys = {
        "registry_receipts",
        "registry_generation",
        "unknown_writers",
        "stub_calls",
        "file_checked",
    }
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
        require(
            d["outcome"] is None or d["outcome"] in ("COMMITTED", "NOOP", "ROLLED_BACK", "UNKNOWN"),
            "DETAIL_OUTCOME",
        )
        require(d["evidence_reason"] is None or d["evidence_reason"] in REASONS, "DETAIL_REASON")
        for key in ("expected_return", "observed_return"):
            require(
                d[key] is None
                or (
                    type(d[key]) is str
                    and re.fullmatch(
                        r"(?:NONE|TRUE|FALSE|INVENTORY|BLOCKED|CANCELLED|RUNTIME_ERROR|TERMINAL|OUTCOME_[012]|NETWORK_[0-9]+_[0-9]+|APPLY_(?:NONE|restart|unchanged|rejected|failed)_(?:NONE|started|unchanged|deferred|rejected|rollback|failed))",
                        d[key],
                    )
                ),
                "RETURN_ENUM",
            )
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
                "tests/stand/wave3_lifecycle_flow.py",
                "tests/stand/wave3_source_hooks.py",
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
    print("LIFECYCLE_FLOW_REPORT_READY")


if __name__ == "__main__":
    try:
        require(os.geteuid() != 0 and len(sys.argv) == 2, "OWNER_OR_MODE")
        bootstrap()
        command = sys.argv[1]
        if command in ("status", "show"):
            for filename in ("summary.json", "progress.json"):
                if (NOTES / filename).exists():
                    print(json.dumps({"file": filename, "data": SUPPORT.read(NOTES / filename)}))
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
            print("LIFECYCLE_FLOW_BATCH_STARTED")
        else:
            require(command == "_batch", "MODE_REFUSED")
            batch()
    except Exception:
        print("LIFECYCLE_FLOW_BATCH_STOP", "LOCAL_IO_OR_SCHEMA_ERROR")
        raise SystemExit(3) from None
