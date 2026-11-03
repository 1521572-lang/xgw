"""AG qualification of optional FreePool/PoolStore flow; fake external effects only."""

# ruff: noqa: E731
import contextlib
import hashlib
import importlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace as NS

NOTES = Path.home() / "xgw-w3ag"
SUPPORT_SHA = "9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917"
MANIFEST_SHA = "383a32d95ec55ee5a840bd32f0e9e37637fc8284d6feedfdc97ed9334a47ad2b"
STORE = (
    "ENSURE",
    "SUCCESS",
    "PARTIAL",
    "UNAVAILABLE_EMPTY",
    "UNAVAILABLE_EXISTING",
    "ROTATE",
    "PRUNE",
    "RETIRE_ALL",
    "RETIRE_NOOP",
    "SAVE_CANDIDATES",
)
POOL = (
    "PRUNE_RETIRED",
    "REFRESH_SUCCESS",
    "REFRESH_UNAVAILABLE",
    "REFRESH_PARTIAL",
    "REFRESH_TWO",
    "REFRESH_NOT_DUE",
    "PRUNE_CANDIDATES",
    "REFRESH_BACKEND",
    "NOTE_HANDSHAKE",
    "PROXY_XRAY",
    "PROXY_SINGBOX",
    "CHECK_PROXY",
    "CHECK_REACH",
    "CHECK_TUNNEL",
    "CHECK_CANCEL",
    "RECORD_PROXY",
    "RECORD_TUNNEL",
    "RECORD_LIST",
)
CONSTRUCTORS = ("EMPTY", "RETIRED", "PROVIDED")
MODES = ("LEGACY", "OWNED", "FENCED")
HOOKS = (
    "STORE_ENSURE",
    "STORE_COMMIT",
    "STORE_PRUNE",
    "STORE_RETIRE",
    "STORE_SAVE",
    "POOL_PRUNE",
    "POOL_REFRESH",
    "POOL_CANDIDATES",
    "POOL_BACKEND",
    "POOL_HANDSHAKE",
    "POOL_CHECK",
    "POOL_PROXY",
    "POOL_RECORD",
)
BASE = (
    "E_FOREIGN_NONE",
    "E_FOREIGN_OTHER",
    "E_STORE_NOIO",
    "E_BINDING_NINE",
    "E_POOL_STORE_ALIAS",
    "E_POOL_RUNTIME_ALIAS",
    "E_APPLIER_API_ALIAS",
    "E_POOL_UNBOUND",
)
ERRORS = (
    "E_PRUNE_ERROR",
    "E_RECONCILE_ERROR",
    "E_ROTATE_ERROR",
    "E_PROBE_ERROR",
    "E_STOP_ERROR",
    "E_VERIFIER_FALSE",
)
READERS = (
    "R_SUMMARY",
    "R_NEXT_CHECKS",
    "R_SPENT",
    "R_HANDSHAKES",
    "R_VARIANTS",
    "R_STORE_SNAPSHOT",
    "R_STORE_CANDIDATES",
)
INTEGRATIONS = ("I_REFRESH_CHECK", "I_SECOND_FAIL")
EXTRAS = BASE + tuple("H_" + name for name in HOOKS) + ERRORS + READERS + INTEGRATIONS
EXPECTED = (
    tuple("S_" + n + "__" + m for n in STORE for m in MODES)
    + tuple("P_" + n + "__" + m for n in POOL for m in MODES)
    + tuple("C_" + n + "__" + m for n in CONSTRUCTORS for m in MODES)
    + EXTRAS
)
SUPPORT = None
M = {}
DETAILS = None
REFERENCES = {}  # private differential fingerprints; never serialized


def require(value, code):
    if not value:
        raise ValueError(code)


def private(path, directory=False):
    info = path.lstat()
    require(
        (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
        and (directory or info.st_nlink == 1),
        "PRIVATE_METADATA",
    )


def bootstrap():
    global SUPPORT
    private(NOTES, True)
    for name, digest in (("support.py", SUPPORT_SHA), ("manifest.json", MANIFEST_SHA)):
        private(NOTES / name)
        require(hashlib.sha256((NOTES / name).read_bytes()).hexdigest() == digest, "ARTIFACT_SHA")
    spec = importlib.util.spec_from_file_location("ag_fixture_support", NOTES / "support.py")
    SUPPORT = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(SUPPORT)
    SUPPORT.NOTES, SUPPORT.MANIFEST_SHA = NOTES, MANIFEST_SHA
    return SUPPORT.verify_source()


def source():
    global M
    SUPPORT.install_audit()
    SUPPORT.load_source()
    M = SUPPORT.MODULES
    for name in (
        "config",
        "freepool.pool",
        "freepool.store",
        "freepool.models",
        "ownership_binding",
    ):
        M[name] = importlib.import_module("frozen_ad." + name)
    b = M["ownership_binding"]
    require(len(b.SPECS) == 9 and len(b.FUNCTIONS) == 50, "BOUNDARY_INVENTORY")


def reject(operation, error=None):
    error = error or M["ownership_hooks"].MutationBlocked
    try:
        operation()
    except error:
        DETAILS["rejection_observed"] = True
    else:
        raise ValueError("EXPECTED_REFUSAL_MISSING")


def result_class(value):
    if value is None:
        return "NONE"
    if type(value) is bool:
        return "TRUE" if value else "FALSE"
    if type(value) is int:
        return "ZERO" if value == 0 else "ONE" if value == 1 else "OTHER_INT"
    if type(value) is str:
        return "TEXT" if value else "EMPTY_TEXT"
    if type(value) is list:
        return "LIST"
    if type(value) is dict:
        return "DICT"
    if type(value) is tuple:
        return "TUPLE"
    if type(value) is M["freepool.pool"].FreePool:
        return "POOL"
    if type(value) is M["freepool.pool"].probing.Outcome:
        return "OUTCOME"
    return "UNSUPPORTED"


def variant(kind="xray", listed=False):
    p, models = M["freepool.pool"], M["freepool.models"]
    provider = sorted(p.providers.LIST_PROVIDERS)[0] if listed else p.providers.VPNGATE
    return models.Variant(
        provider,
        kind,
        "sstp" if kind == "sstp" else "vless",
        "fixture.invalid",
        "192.0.2.1",
        443,
        "tcp",
        "fixture",
        "DE",
    )


def retired(f, store):
    f.write(store.snapshot_path("retired"), {"variants": []})
    f.write(store.snapshot_path("retired", 1), {"variants": []})
    f.write(store.dir / "secrets.json", {"fixture": True})
    f.write(store.dir / "profiles" / "dummy.txt", {"fixture": True})
    f.write(
        store.dir / "candidates.json", {"old": {"backend": "openvpn"}, "_ledger": {"items": []}}
    )


def configure(f):
    module = M["freepool.pool"]
    cfg = M["config"].Config()
    cfg.free_pool.mode = "observe"
    cfg.free_pool.providers = [module.providers.VPNGATE]
    return cfg


def make_pool(f, owner=None):
    module = M["freepool.pool"]
    # Matrix fixture builds legacy first; constructor propagation has its own C9 cases.
    pool = module.FreePool(
        configure(f),
        f.paths,
        logger=f.log,
        clock=lambda: 100000,
        runner=f.runner,
        sleep=lambda *args: None,
    )
    pool.ownership = pool.store.ownership = pool.runtime.ownership = owner
    pool.runtime.sys_net = f.work / "sys-net"
    pool.runtime.clock = lambda: 100000
    pool.runtime._main_pid = lambda *args: 4242
    pool.runtime._wait_guarded = lambda *args: None
    pool._lan = lambda: ()
    outcome = module.probing.Outcome("OK", seconds=0.25, bytes_used=128, egress_country="DE")

    def fake_probe(*args, **kwargs):
        f.event("PROBE_STUB")
        return outcome

    def fake_tunnel(v, **kwargs):
        f.event("TUNNEL_STUB")
        runtime = kwargs["runtime"]
        lease = runtime.prepare(
            peer="192.0.2.1",
            port=443,
            host="fixture.invalid",
            user="fixture",
            password="fixture",
            lan=(),
            xray_bin=f.work / "dummy",
        )
        try:
            return module.probing.Outcome(
                "OK", seconds=0.25, bytes_used=128, egress_country="DE", tunnel_up=True
            )
        finally:
            runtime.stop(lease)

    def poll(provider, **kwargs):
        f.event("POLL_STUB")
        return M["freepool.models"].ProviderResult(
            provider, M["freepool.models"].Status.SUCCESS, [variant()], retrieved_at=100000
        )

    pool.poll = poll
    f.changes.extend(
        (
            (module, "_due", lambda seconds: seconds),
            (module.backending, "unavailable", lambda *args: ""),
            (module.probing, "server_hosts", lambda *args, **kwargs: ({}, "")),
            (module.probing, "check_xray", fake_probe),
            (module.probing, "check_singbox", fake_probe),
            (module.probing, "check_tunnel_reach", fake_probe),
            (module.probing, "tunnel_peer", lambda *args: True),
            (module.probing, "check_tunnel", fake_tunnel),
            (M["cores"].singboxing, "find_binary", lambda *args, **kwargs: f.work / "dummy"),
        )
    )
    return pool


def store_operation(f, store, name):
    models = M["freepool.models"]
    provider = M["freepool.pool"].providers.VPNGATE
    result = models.ProviderResult(
        provider, models.Status.SUCCESS, [variant()], retrieved_at=100000
    )
    if name == "ENSURE":
        store.dir.mkdir(parents=True, mode=0o755)
        store.dir.chmod(0o755)  # intentional fixture precondition; no live chmod
    elif name == "PARTIAL":
        result.status = models.Status.PARTIAL
    elif name.startswith("UNAVAILABLE"):
        result.status = models.Status.UNAVAILABLE
        if name == "UNAVAILABLE_EXISTING":
            f.write(store.snapshot_path(provider), {"variants": []})
    elif name == "ROTATE":
        for gen in range(4):
            f.write(store.snapshot_path(provider, gen), {"variants": [], "fixture": gen})
    elif name in ("PRUNE", "RETIRE_ALL"):
        retired(f, store)
    calls = {
        "ENSURE": store._ensure,
        "PRUNE": lambda: store.prune((provider,)),
        "RETIRE_ALL": store.retire_openvpn,
        "RETIRE_NOOP": store.retire_openvpn,
        "SAVE_CANDIDATES": lambda: store.save_candidates({"_ledger": {"items": [[100000, 128]]}}),
    }
    operation = calls.get(name, lambda: store.commit(result))
    expected = (
        "NONE"
        if name in ("ENSURE", "SAVE_CANDIDATES")
        else "LIST"
        if name in ("PRUNE", "RETIRE_ALL", "RETIRE_NOOP")
        else "FALSE"
        if name.startswith("UNAVAILABLE")
        else "TRUE"
    )
    return operation, expected


def pool_operation(f, pool, name):
    module, models = M["freepool.pool"], M["freepool.models"]
    v = variant(
        "sing-box"
        if name == "PROXY_SINGBOX"
        else "sstp"
        if name in ("CHECK_REACH", "CHECK_TUNNEL")
        else "xray",
        name == "RECORD_LIST",
    )
    outcome = module.probing.Outcome(
        "OK", seconds=0.25, bytes_used=128, egress_country="DE", tunnel_up=True
    )
    if name == "PRUNE_RETIRED":
        retired(f, pool.store)
    if name in ("REFRESH_UNAVAILABLE", "REFRESH_PARTIAL"):
        status = (
            models.Status.UNAVAILABLE if name == "REFRESH_UNAVAILABLE" else models.Status.PARTIAL
        )
        pool.poll = lambda provider, **kwargs: (
            f.event("POLL_STUB")
            or models.ProviderResult(
                provider,
                status,
                [] if status is models.Status.UNAVAILABLE else [v],
                retrieved_at=100000,
            )
        )
    if name == "REFRESH_TWO":
        pool.cfg.free_pool.providers += [module.providers.VPNBOOK]
    if name == "REFRESH_NOT_DUE":
        pool.next_refresh[v.provider] = 200000
    if name == "PRUNE_CANDIDATES":
        f.write(
            pool.store.dir / "candidates.json",
            {"obsolete": {"verdict": "OK"}, "_ledger": {"items": []}},
        )
    if name.startswith("CHECK_"):
        pool.next_checks = lambda *args, **kwargs: [v]
    if name == "CHECK_REACH":
        f.changes.append((module.backending, "unavailable", lambda *args: "fixture unavailable"))
    calls = {
        "PRUNE_RETIRED": pool._prune_retired,
        "PRUNE_CANDIDATES": pool._prune_candidates,
        "REFRESH_BACKEND": pool.refresh_backend,
        "NOTE_HANDSHAKE": lambda: pool._note_handshake(v.provider),
        "PROXY_XRAY": lambda: pool._check_proxy(v, mark=None, xray_bin=f.work / "dummy"),
        "PROXY_SINGBOX": lambda: pool._check_proxy(v, mark=None, xray_bin=f.work / "dummy"),
        "RECORD_PROXY": lambda: pool._record(v, outcome),
        "RECORD_TUNNEL": lambda: pool._record(v, outcome, tunnel=True),
        "RECORD_LIST": lambda: pool._record(v, outcome),
    }
    if name.startswith("CHECK_"):
        calls[name] = lambda: pool.check_some(
            mark=None,
            xray_bin=f.work / "dummy",
            cancel=NS(is_set=lambda: True) if name == "CHECK_CANCEL" else None,
        )
    operation = calls.get(name, lambda: pool.refresh_due(via=None, mark=None))
    expected = (
        "LIST"
        if name.startswith("REFRESH_") and name != "REFRESH_BACKEND"
        else "EMPTY_TEXT"
        if name == "REFRESH_BACKEND"
        else "OUTCOME"
        if name.startswith("PROXY_")
        else "ZERO"
        if name == "CHECK_CANCEL"
        else "ONE"
        if name.startswith("CHECK_")
        else "NONE"
    )
    return operation, expected


def state(pool):
    return (
        dict(pool.next_refresh),
        dict(pool.failures),
        pool._reconciled,
        pool.backend_problem,
        len(pool.runtime.leases),
    )


def matrix(f, group, name, mode):
    owner = None if mode == "LEGACY" else f.coordinator
    pool = make_pool(f, owner)
    operation, expected = (
        store_operation(f, pool.store, name) if group == "S" else pool_operation(f, pool, name)
    )
    key = group + "_" + name
    before = (SUPPORT.digest_tree(f.work), state(pool))
    DETAILS["expected_return"] = expected

    def verifier(roles, value):
        actual = (SUPPORT.digest_tree(f.work), state(pool), result_class(value), len(f.trace))
        reference = REFERENCES.get(key)
        DETAILS["legacy_equivalent"] = None if reference is None else actual == reference
        good = reference is not None and actual == reference and result_class(value) == expected
        return M["ownership_adapters"].Verification("COMMITTED", (("FILES", good),))

    f.coordinator.verifier = verifier
    if mode == "FENCED":
        f.registry.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
    with SUPPORT.patches(f.changes):
        if mode == "FENCED":
            reject(operation)
            require(
                (SUPPORT.digest_tree(f.work), state(pool)) == before and not f.trace,
                "FENCED_EFFECT",
            )
            DETAILS["fixture_unchanged"] = True
        else:
            value = operation()
            DETAILS["observed_return"] = result_class(value)
            require(result_class(value) == expected, "BUSINESS_RETURN_CHANGED")
            if mode == "LEGACY":
                REFERENCES[key] = (
                    SUPPORT.digest_tree(f.work),
                    state(pool),
                    result_class(value),
                    len(f.trace),
                )
            else:
                require(DETAILS["legacy_equivalent"] is True, "LEGACY_DIFFERENCE")
    summary = f.registry.summary()
    require(
        summary["receipts"] == (1 if mode == "OWNED" else 0) and summary["unknown"] == 0,
        "MATRIX_TICKETS",
    )
    if mode == "OWNED":
        DETAILS["completion_verified"] = True


def constructor(f, name, mode):
    module = M["freepool.pool"]
    owner = None if mode == "LEGACY" else f.coordinator
    store = M["freepool.store"].PoolStore(f.paths)
    if name == "RETIRED":
        retired(f, store)
    backend = (
        module.backending.Backend(
            f.paths, runner=f.runner, logger=f.log, sys_net=f.work / "sys-net", ownership=owner
        )
        if name == "PROVIDED"
        else None
    )
    before = SUPPORT.digest_tree(f.work)

    def verifier(roles, value):
        reference = REFERENCES.get("C_" + name)
        good = reference is not None and SUPPORT.digest_tree(f.work) == reference and value is None
        DETAILS["legacy_equivalent"] = None if reference is None else good
        return M["ownership_adapters"].Verification("COMMITTED", (("FILES", good),))

    f.coordinator.verifier = verifier
    operation = lambda: module.FreePool(
        configure(f),
        f.paths,
        clock=lambda: 100000,
        logger=f.log,
        runner=f.runner,
        runtime=backend,
        ownership=owner,
    )
    if mode == "FENCED":
        f.registry.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
        reject(operation)
        require(SUPPORT.digest_tree(f.work) == before and not f.trace, "CONSTRUCTOR_EFFECT")
        DETAILS["fixture_unchanged"] = True
    else:
        obj = operation()
        require(
            obj.ownership is obj.store.ownership is obj.runtime.ownership is owner,
            "CONSTRUCTOR_BINDING",
        )
        if backend is not None:
            require(obj.runtime is backend, "PROVIDED_BACKEND_REPLACED")
        if mode == "LEGACY":
            REFERENCES["C_" + name] = SUPPORT.digest_tree(f.work)
        else:
            require(DETAILS["legacy_equivalent"] is True, "CONSTRUCTOR_LEGACY_DIFFERENCE")
    require(
        f.registry.summary()["receipts"] == (1 if mode == "OWNED" else 0), "CONSTRUCTOR_RECEIPTS"
    )
    if mode == "OWNED":
        DETAILS["completion_verified"] = True


def actors(f, pool):
    b = M["ownership_binding"]
    result = {}
    for key, (cls, _, _) in b.SPECS.items():
        actor = cls.__new__(cls)
        object.__setattr__(actor, "ownership", f.coordinator)
        result[key] = actor
    result.update(pool=pool, pool_store=pool.store, peers=pool.runtime)
    result["xray"].api = result["api"]
    return result


def extras(f, name):
    b, p, a = M["ownership_binding"], M["freepool.pool"], M["ownership_adapters"]
    c = f.coordinator
    pool = make_pool(f, c)
    objs = actors(f, pool)
    if name in ("E_FOREIGN_NONE", "E_FOREIGN_OTHER"):
        backend = p.backending.Backend(
            f.paths,
            ownership=None
            if name == "E_FOREIGN_NONE"
            else M["ownership_hooks"].Coordinator(f.registry, f.verifier),
        )
        before = SUPPORT.digest_tree(f.work)
        reject(lambda: p.FreePool(configure(f), f.paths, runtime=backend, ownership=c))
        require(
            SUPPORT.digest_tree(f.work) == before and f.registry.summary()["writers"] == 0,
            "FOREIGN_EFFECT",
        )
    elif name == "E_STORE_NOIO":
        before = SUPPORT.digest_tree(f.work)
        store = M["freepool.store"].PoolStore(f.paths, ownership=c)
        require(
            store.ownership is c and SUPPORT.digest_tree(f.work) == before, "STORE_CONSTRUCTOR_IO"
        )
    elif name.startswith("H_"):
        names = {
            "STORE_ENSURE": ("pool_store", "_ensure"),
            "STORE_COMMIT": ("pool_store", "commit"),
            "STORE_PRUNE": ("pool_store", "prune"),
            "STORE_RETIRE": ("pool_store", "retire_openvpn"),
            "STORE_SAVE": ("pool_store", "save_candidates"),
            "POOL_PRUNE": ("pool", "_prune_retired"),
            "POOL_REFRESH": ("pool", "refresh_due"),
            "POOL_CANDIDATES": ("pool", "_prune_candidates"),
            "POOL_BACKEND": ("pool", "refresh_backend"),
            "POOL_HANDSHAKE": ("pool", "_note_handshake"),
            "POOL_CHECK": ("pool", "check_some"),
            "POOL_PROXY": ("pool", "_check_proxy"),
            "POOL_RECORD": ("pool", "_record"),
        }
        key, method = names[name[2:]]
        setattr(objs[key], method, lambda *args, **kwargs: None)
        reject(lambda: b.BoundWriters(c, objs))
    elif name in (
        "E_BINDING_NINE",
        "E_POOL_STORE_ALIAS",
        "E_POOL_RUNTIME_ALIAS",
        "E_APPLIER_API_ALIAS",
        "E_POOL_UNBOUND",
    ):
        if name == "E_POOL_STORE_ALIAS":
            pool.store = M["freepool.store"].PoolStore(f.paths, ownership=c)
        elif name == "E_POOL_RUNTIME_ALIAS":
            pool.runtime = p.backending.Backend(f.paths, ownership=c)
        elif name == "E_APPLIER_API_ALIAS":
            objs["xray"].api = object()
        elif name == "E_POOL_UNBOUND":
            pool.ownership = None
        if name == "E_BINDING_NINE":
            b.BoundWriters(c, objs).validate()
        else:
            reject(lambda: b.BoundWriters(c, objs))
    elif name in READERS:
        v = variant()
        models = M["freepool.models"]
        # Seed with ownershipNone, then restore injection before arming; no receipts from setup.
        pool.store.ownership = None
        pool.store.commit(
            models.ProviderResult(v.provider, models.Status.SUCCESS, [v], retrieved_at=100000)
        )
        pool.store.save_candidates({"_ledger": {"items": [[100000, 128]]}})
        pool.store.ownership = c
        calls = {
            "R_SUMMARY": pool.summary,
            "R_NEXT_CHECKS": lambda: pool.next_checks(None),
            "R_SPENT": pool.spent_today,
            "R_HANDSHAKES": pool.handshakes,
            "R_VARIANTS": pool.variants,
            "R_STORE_SNAPSHOT": lambda: pool.store.snapshot(v.provider),
            "R_STORE_CANDIDATES": pool.store.candidates,
        }
        before = SUPPORT.digest_tree(f.work)
        f.registry.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
        DETAILS["observed_return"] = result_class(calls[name]())
        require(SUPPORT.digest_tree(f.work) == before and not f.trace, "READER_EFFECT")
    else:
        if name == "E_PRUNE_ERROR":
            retired(f, pool.store)
            target = pool.store.snapshot_path("retired")
            path_type, original = type(target), type(target).unlink

            def fail_unlink(path, *args, **kwargs):
                if path == target:
                    raise OSError("fixture")
                return original(path, *args, **kwargs)

            f.changes.append((path_type, "unlink", fail_unlink))
            operation, expected_error = pool._prune_retired, None
        elif name == "E_RECONCILE_ERROR":

            def fail_runner(*args, **kwargs):
                f.event("RUNNER")
                raise OSError("fixture")

            pool.runtime.runner = fail_runner
            operation, expected_error = pool.refresh_backend, OSError
        elif name == "E_ROTATE_ERROR":
            operation, _ = store_operation(f, pool.store, "ROTATE")

            def denied(*args, **kwargs):
                raise OSError("fixture")

            f.changes.append((M["freepool.store"], "atomic_write_json", denied))
            expected_error = OSError
        elif name in ("E_PROBE_ERROR", "I_SECOND_FAIL"):

            def fail_probe(*args, **kwargs):
                f.event("PROBE_STUB")
                raise OSError("fixture")

            f.changes.append((p.probing, "check_xray", fail_probe))
            operation, _ = pool_operation(f, pool, "PROXY_XRAY")
            expected_error = OSError
        elif name == "E_STOP_ERROR":

            def stop_failure(argv, **kwargs):
                f.event("RUNNER")
                if argv[:3] == ["nft", "delete", "element"]:
                    raise OSError("fixture")
                return ""

            pool.runtime.runner = stop_failure
            operation, _ = pool_operation(f, pool, "CHECK_TUNNEL")
            expected_error = None
        elif name == "E_VERIFIER_FALSE":
            c.verifier = lambda *args: a.Verification()
            operation = lambda: pool.store.save_candidates({"fixture": {"verdict": "OK"}})
            expected_error = None
        elif name == "I_REFRESH_CHECK":
            operation, expected_error = None, None
        else:
            raise ValueError("UNKNOWN_EXTRA")
        if name in INTEGRATIONS:
            seen = []

            def verifier(roles, values):
                seen.append(roles)
                valid = (
                    type(values) is tuple
                    and len(values) == 2
                    and values[1] == 1
                    and pool.store.candidates().get(variant().variant_id, {}).get("verdict") == "OK"
                )
                return a.Verification("COMMITTED", (("FILES", valid),))

            c.verifier = verifier
            bound = b.BoundWriters(c, objs)
            pool.next_checks = lambda *args, **kwargs: [variant()]
            old_poll = pool.poll

            def guarded_poll(*args, **kwargs):
                require(f.registry.summary()["receipts"] == 0, "EARLY_RECEIPT")
                reject(
                    lambda: f.registry.acquire(
                        run_id="a" * 32, expected_generation=0, duration_ns=100
                    ),
                    M["ownership"].Refused,
                )
                return old_poll(*args, **kwargs)

            pool.poll = guarded_poll
            plan = bound.prepare(
                (
                    b.Step("pool", "refresh_due", kwargs=(("via", None), ("mark", None))),
                    b.Step(
                        "pool",
                        "check_some",
                        kwargs=(("mark", None), ("xray_bin", f.work / "dummy")),
                    ),
                ),
                accept=lambda step, value: (
                    type(value) is list if step.method == "refresh_due" else value == 1
                ),
            )
            operation = plan.run
        with SUPPORT.patches(f.changes):
            if name == "I_REFRESH_CHECK":
                operation()
            else:
                reject(operation, expected_error)
        summary = f.registry.summary()
        positive = name == "I_REFRESH_CHECK"
        require(
            summary["receipts"] == (1 if positive else 0)
            and summary["unknown"] == (0 if positive else 1),
            "EXTRA_TICKETS",
        )
        if positive:
            require(seen == [frozenset({"LIFECYCLE", "PEERS"})], "ROLE_UNION")
            DETAILS["completion_verified"] = True
        if name in INTEGRATIONS:
            require(
                pool.store.snapshot(variant().provider).get("variants"), "FIRST_STEP_NOT_RECORDED"
            )
    if name not in ERRORS and name not in INTEGRATIONS:
        require(
            f.registry.summary()["receipts"] == f.registry.summary()["writers"] == 0,
            "PRE_ADMISSION_TICKETS",
        )


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
        DETAILS = dict.fromkeys(
            (
                "registry_receipts",
                "registry_generation",
                "unknown_writers",
                "stub_calls",
                "expected_return",
                "observed_return",
                "legacy_equivalent",
                "fixture_unchanged",
                "rejection_observed",
                "completion_verified",
            )
        )
        try:
            f = SUPPORT.Fixture(root)
            if name in EXTRAS:
                extras(f, name)
            else:
                prefix, mode = name.rsplit("__", 1)
                if prefix.startswith("C_"):
                    constructor(f, prefix[2:], mode)
                else:
                    matrix(f, prefix[0], prefix[2:], mode)
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
                        "batch.py": "wave3_pool_flow.py",
                        "support.py": "wave3_source_hooks.py",
                    }
                    if filename.parent == NOTES and filename.name in mapping:
                        public, line = "tests/stand/" + mapping[filename.name], tb.tb_lineno
                tb = tb.tb_next
            row = {
                "case": name,
                "passed": False,
                "reason": "POOL_FLOW_CASE_FAILED",
                "error_class": type(exc).__name__,
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
        "marker": "POOL_FLOW_BATCH_RECORDED"
        if passed == len(EXPECTED)
        else "POOL_FLOW_BATCH_PARTIAL",
        "scope": "OPTIONAL_POOL_STORE_AND_DECLARED_DEPENDENCIES_ONLY",
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
        elif command == "start":
            SUPPORT.create(NOTES / "started.json", {"started": True})
            subprocess.Popen(
                [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "_batch"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            print("POOL_FLOW_BATCH_STARTED")
        else:
            require(command == "_batch", "MODE_REFUSED")
            batch()
    except Exception as exc:
        print("POOL_FLOW_BATCH_STOP", type(exc).__name__)
        raise SystemExit(3) from None
