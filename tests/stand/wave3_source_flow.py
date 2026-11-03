"""AF: free-function writer flow and factories; frozen source, fake external I/O."""

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

NOTES = Path.home() / "xgw-w3af"
SUPPORT_SHA = "9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917"
MANIFEST_SHA = "ff4929792a5e51cd76b38870c0352941238cd3194484697f9aa192147846cd82"
PANEL = (
    "set_free_pool_mode",
    "set_free_pool_pin",
    "set_tailscale_direct",
    "replace_tailscale_direct",
    "set_device",
    "replace_devices",
    "set_kernel_device",
    "split_kernel_direct",
    "set_route",
    "set_servers",
    "set_priority",
    "set_core",
    "set_sticky",
    "set_kernel_direct",
    "set_tailscale_serve",
    "set_tailscale_funnel",
    "set_tailscale_route",
    "drop_telegram",
    "add_subscription",
    "update_subscription",
    "remove_subscription",
    "add_links",
    "remove_link",
    "save",
    "_update_locked",
    "_update",
)
CORE = (
    "SAVE_STATE",
    "FORGET",
    "START",
    "TAKE_BAD",
    "TAKE_VALID",
    "CHECK",
    "RUN_REQUEST",
    "RUN_REQUEST_EMPTY",
    "JOB_RUN",
    "JOB_RUN_ROLLBACK",
    "JOB_REJECT",
    "JOB_STAGE",
    "JOB_SAVE",
    "JOB_EVENT",
)
FACTORIES = ("API", "APPLIER", "SINGBOX")
MODES = ("LEGACY", "OWNED", "FENCED")
EXTRAS = (
    "H_SIGNATURE",
    "H_DEFERRED",
    "H_NO_VERIFIER",
    "H_NESTED_ERROR",
    "H_NESTED_RETURN",
    "K_RUN_FAILED",
    "K_RUN_INVALID",
    "K_REQUEST_FOREIGN",
    "K_REQUEST_NO_JOB",
    "K_SWALLOWED_SAVE",
    "I_PANEL_CORE",
    "B_RUN_SHADOW",
    "B_REJECT_SHADOW",
    "B_STAGE_SHADOW",
    "B_SAVE_SHADOW",
    "B_EVENT_SHADOW",
)
EXPECTED = (
    tuple("P_" + name.upper() + "__" + mode for name in PANEL for mode in MODES)
    + tuple("K_" + name + "__" + mode for name in CORE for mode in MODES)
    + tuple("F_" + name + "__" + mode for name in FACTORIES for mode in MODES)
    + EXTRAS
)
SUPPORT = None
M = {}
DETAILS = None
REFERENCES = {}  # private differential fingerprints, never serialized


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
    spec = importlib.util.spec_from_file_location("af_fixture_support", NOTES / "support.py")
    SUPPORT = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(SUPPORT)
    SUPPORT.NOTES, SUPPORT.MANIFEST_SHA = NOTES, MANIFEST_SHA
    return SUPPORT.verify_source()


def source():
    global M
    SUPPORT.install_audit()
    SUPPORT.load_source()
    M = SUPPORT.MODULES
    for name in ("engine", "ownership_binding"):
        M[name] = importlib.import_module("frozen_ad." + name)
    require(len(M["ownership_binding"].FUNCTIONS) == 37, "BOUNDARY_COUNT")


def result_class(value):
    if value is None:
        return "NONE"
    if type(value) is bool:
        return "TRUE" if value else "FALSE"
    if type(value) is int:
        return "ZERO" if value == 0 else "ONE" if value == 1 else "OTHER_INT"
    if type(value) is str:
        return "TEXT" if value else "EMPTY_TEXT"
    if type(value) is dict:
        return "DICT"
    if type(value) is tuple:
        return "TUPLE"
    return "UNSUPPORTED"


def reject(operation, error=None):
    error = error or M["ownership_hooks"].MutationBlocked
    try:
        operation()
    except error:
        DETAILS["rejection_observed"] = True
    else:
        raise ValueError("EXPECTED_REFUSAL_MISSING")


def panel(f, name, owner):
    module = M["managed"]
    path = f.work / "panel.json"
    mac, ip, tail = "02:00:00:00:00:01", "192.0.2.1", "100.64.0.1"
    device = {"mac": mac, "ip": ip, "name": "fixture"}
    link = (
        "vless://11111111-1111-1111-1111-111111111111@192.0.2.1:443?security=none&type=tcp#fixture"
    )
    seed, _ = module.load(path)
    if name in ("remove_subscription", "update_subscription"):
        seed["subscriptions"] = [{"name": "fixture", "url": "https://fixture.invalid/list"}]
    if name == "remove_link":
        seed["links"] = [link]
    if name == "replace_devices":
        seed["devices"] = [device]
    if name == "drop_telegram":
        seed["telegram"] = {"fixture": True}
    if name == "split_kernel_direct":
        seed.pop("kernel_devices")
        seed["kernel_direct"] = True
    f.write(path, seed)

    def changed(data):
        data["sticky"] = True
        return True

    calls = {
        "set_free_pool_mode": (("observe",), {}),
        "set_free_pool_pin": (("b" * 32,), {}),
        "set_tailscale_direct": ((tail, "fixture"), {"direct": True}),
        "replace_tailscale_direct": (([{"ip": tail, "name": "fixture"}],), {}),
        "set_device": ((mac, ip, "fixture"), {"bypass": True}),
        "replace_devices": (([],), {}),
        "set_kernel_device": ((mac, ip, "fixture"), {"on": True}),
        "split_kernel_direct": (([device],), {}),
        "set_route": ((mac, ip, "fixture", "1234abcd"), {}),
        "set_servers": ((["1234abcd"], "disabled"), {}),
        "set_priority": ((["1234abcd"], "high"), {}),
        "set_core": ((["1234abcd"], "xray"), {}),
        "set_sticky": ((True,), {}),
        "set_kernel_direct": ((True,), {}),
        "set_tailscale_serve": (("fixture.ts.net",), {}),
        "set_tailscale_funnel": (("fixture.ts.net",), {}),
        "set_tailscale_route": (("direct",), {}),
        "drop_telegram": ((), {}),
        "add_subscription": (("https://fixture.invalid/list", "fixture"), {"taken": set()}),
        "update_subscription": (("fixture",), {"user_agent": "fixture"}),
        "remove_subscription": (("fixture",), {}),
        "add_links": ((link,), {"taken": set()}),
        "remove_link": ((module.link_id(link),), {}),
        "save": (({**seed, "sticky": True},), {}),
        "_update_locked": ((changed,), {}),
        "_update": ((changed,), {}),
    }
    args, kwargs = calls[name]
    expected = (
        "NONE"
        if name in ("save", "replace_devices", "replace_tailscale_direct")
        else "TEXT"
        if name == "add_subscription"
        else "ONE"
        if name == "add_links"
        else "TRUE"
    )
    return lambda: getattr(module, name)(path, *args, **kwargs, ownership=owner), expected


def job(f, owner, rollback=False):
    module = M["cores"]
    obj, _ = f.core("K_ROLLBACK" if rollback else "K_UPDATE")
    obj.ownership, obj.now = owner, lambda: 10

    class Store:
        def __init__(self, path):
            f.event("STORE_OPEN")

        def add_event(self, *args):
            f.event("STORE_EVENT")

        def close(self):
            f.event("STORE_CLOSE")

    f.changes.append((module, "Store", Store))
    return obj


def core(f, name, owner):
    module, p = M["cores"], f.paths
    obj = job(f, owner, name == "JOB_RUN_ROLLBACK")
    request = {"core": "xray", "action": "update", "version": "1.0.0", "reason": "fixture"}
    if name in ("RUN_REQUEST", "JOB_RUN", "JOB_RUN_ROLLBACK", "TAKE_VALID"):
        f.write(p.cores_request_file, request)
    if name == "TAKE_BAD":
        p.cores_request_file.write_text("{invalid")
    if name == "FORGET":
        f.write(p.cores_state_file, {"xray": {"accepted": "1.0.0"}})
        prev = module.prev_dir(p, "xray")
        prev.mkdir(mode=0o700)
        (prev / "xray").write_text("dummy")
    if name == "JOB_STAGE":
        f.write(p.cores_state_file, {"job": {"state": "running"}})
    if name == "CHECK":
        f.changes.extend(
            (
                (module, "routes", lambda *args: [{}]),
                (
                    module,
                    "fetch_releases",
                    lambda *args: f.event("RELEASE_STUB") or [{"tag_name": "v1.0.0"}],
                ),
            )
        )
    calls = {
        "SAVE_STATE": lambda: module.save_state(p, {"fixture": True}, ownership=owner),
        "FORGET": lambda: module.forget(p, "xray", ownership=owner),
        "START": lambda: module.start(
            p, "xray", "update", version="1.0.0", runner=f.runner, now=lambda: 10, ownership=owner
        ),
        "TAKE_BAD": lambda: module.take_request(p, ownership=owner),
        "TAKE_VALID": lambda: module.take_request(p, ownership=owner),
        "CHECK": lambda: module.check(
            NS(),
            p,
            {"xray": (1, 0, 0)},
            platform=("linux", "amd64"),
            now=lambda: 10,
            ownership=owner,
        ),
        "RUN_REQUEST": lambda: module.run_request(
            NS(), p, logger=f.log, out=lambda *args: None, job=obj, ownership=owner
        ),
        "RUN_REQUEST_EMPTY": lambda: module.run_request(
            NS(), p, job=obj, out=lambda *args: None, ownership=owner
        ),
        "JOB_RUN": lambda: obj.run("xray", "update", "1.0.0", "fixture"),
        "JOB_RUN_ROLLBACK": lambda: obj.run("xray", "rollback", "", "fixture"),
        "JOB_REJECT": lambda: obj._reject("xray", "2.0.0", "fixture"),
        "JOB_STAGE": lambda: obj._stage("fixture"),
        "JOB_SAVE": lambda: obj._save({"fixture": True}),
        "JOB_EVENT": lambda: obj._event("fixture"),
    }
    expected = (
        "DICT"
        if name in ("TAKE_BAD", "TAKE_VALID")
        else "TUPLE"
        if name == "CHECK"
        else "EMPTY_TEXT"
        if name == "START"
        else "ZERO"
        if name in ("RUN_REQUEST", "RUN_REQUEST_EMPTY", "JOB_RUN", "JOB_RUN_ROLLBACK")
        else "NONE"
    )
    return calls[name], expected


def matrix(f, group, variant, mode):
    key = group + "_" + variant
    owner = None if mode == "LEGACY" else f.coordinator
    operation, expected = (
        panel(f, variant.lower(), owner) if group == "P" else core(f, variant, owner)
    )
    DETAILS["expected_return"] = expected
    before = SUPPORT.digest_tree(f.work)

    def verifier(roles, value):
        reference = REFERENCES.get(key)
        actual = (SUPPORT.digest_tree(f.work), result_class(value), len(f.trace))
        DETAILS["legacy_equivalent"] = None if reference is None else actual == reference
        if reference is None or actual != reference or result_class(value) != expected:
            return M["ownership_adapters"].Verification()
        outcome = "NOOP" if actual[0] == before and not f.trace else "COMMITTED"
        return M["ownership_adapters"].Verification(outcome, (("FILES", True),))

    f.coordinator.verifier = verifier
    if mode == "FENCED":
        f.registry.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
    with SUPPORT.patches(f.changes):
        if mode == "FENCED":
            reject(operation)
            require(
                SUPPORT.digest_tree(f.work) == before and not f.trace, "EFFECT_BEFORE_ADMISSION"
            )
            DETAILS["fixture_unchanged"] = True
        else:
            value = operation()
            DETAILS["observed_return"] = result_class(value)
            require(result_class(value) == expected, "BUSINESS_RETURN_CHANGED")
            actual = (SUPPORT.digest_tree(f.work), result_class(value), len(f.trace))
            if mode == "LEGACY":
                REFERENCES[key] = actual
            else:
                require(DETAILS["legacy_equivalent"] is True, "LEGACY_DIFFERENCE")
    summary = f.registry.summary()
    require(summary["receipts"] == (1 if mode == "OWNED" else 0), "RECEIPT_COUNT")
    require(summary["unknown"] == summary["writers"] == 0, "TICKET_LEAK")
    if mode == "OWNED":
        DETAILS["completion_verified"] = True


def factory(f, variant, mode):
    e = M["engine"]
    sb = M["apply.singbox"]
    owner = None if mode == "LEGACY" else f.coordinator
    service = NS(restart=lambda: f.event("SERVICE"))
    changes = [
        (e, "make_service", lambda *args: service),
        (sb, "make_service", lambda *args: service),
        (e.singboxing, "find_binary", lambda *args: f.work / "dummy"),
    ]
    before = SUPPORT.digest_tree(f.work)
    with SUPPORT.patches(changes):
        if variant == "API":
            actor = e.make_api(f.paths, f.work / "dummy", ownership=owner)
            operation = lambda: actor.pin("fixture", "fixture")
        elif variant == "APPLIER":
            actor = e.make_applier(NS(), f.paths, f.work / "dummy", ownership=owner)
            require(actor.api.ownership is owner, "NESTED_API_UNBOUND")
            operation = lambda: actor.apply({"inbounds": []})
        else:
            actor = e.make_singbox(NS(), f.paths, ownership=owner)
            operation = lambda: actor.apply({"inbounds": []}, reload=True)
        require(actor.ownership is owner, "FACTORY_LOST_BINDING")
        if mode == "FENCED":
            f.registry.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
            reject(operation)
    require(SUPPORT.digest_tree(f.work) == before and not f.trace, "FACTORY_EFFECT")
    require(f.registry.summary()["receipts"] == 0, "FACTORY_RECEIPT")
    DETAILS["fixture_unchanged"] = True


def extras(f, name):
    h, a, k = M["ownership_hooks"], M["ownership_adapters"], M["cores"]
    c, b = f.coordinator, M["ownership_binding"]
    if name in ("H_SIGNATURE", "H_DEFERRED"):

        def invalid(ownership=None):
            f.event("FORBIDDEN")

        def deferred(*, ownership=None):
            yield 1

        reject(lambda: h.owned_function("PANEL")(invalid if name == "H_SIGNATURE" else deferred))
    elif name == "H_NO_VERIFIER":
        operation, _ = panel(f, "set_sticky", c)
        before = SUPPORT.digest_tree(f.work)
        c.verifier = None
        reject(operation)
        require(SUPPORT.digest_tree(f.work) == before, "UNCONFIGURED_EFFECT")
    elif name in ("H_NESTED_ERROR", "H_NESTED_RETURN"):

        @h.owned_function("PANEL")
        def nested(*, ownership=None):
            if name == "H_NESTED_ERROR":
                raise ValueError("fixture")
            return value

        def values():
            yield 1

        value = values()

        def outer():
            try:
                nested(ownership=c)
            except (ValueError, h.MutationBlocked):
                return None

        try:
            reject(lambda: c.call("CORE", outer))
        finally:
            value.close()
    elif name.startswith("B_"):
        objs = {}
        for key, (cls, _, _) in b.SPECS.items():
            obj = cls.__new__(cls)
            object.__setattr__(obj, "ownership", c)
            objs[key] = obj
        method = {
            "B_RUN_SHADOW": "run",
            "B_REJECT_SHADOW": "_reject",
            "B_STAGE_SHADOW": "_stage",
            "B_SAVE_SHADOW": "_save",
            "B_EVENT_SHADOW": "_event",
        }[name]
        setattr(objs["cores"], method, lambda *args: None)
        reject(lambda: b.BoundWriters(c, objs))
    else:
        obj = job(f, c)
        request = {"core": "xray", "action": "update", "version": "1.0.0", "reason": "fixture"}
        f.write(f.paths.cores_request_file, request)
        if name == "K_RUN_FAILED":
            obj.cores["xray"].precheck = lambda *args: "fixture failure"
            operation = lambda: obj.run("xray", "update", "2.0.0", "fixture")
        elif name == "K_RUN_INVALID":
            c.verifier = lambda roles, value: (
                a.Verification() if value != 0 else a.Verification("NOOP", (("FILES", True),))
            )
            operation = lambda: obj.run("invalid", "update")
        elif name == "K_REQUEST_FOREIGN":
            obj.ownership = None
            operation = lambda: k.run_request(NS(), f.paths, job=obj, ownership=c)
        elif name == "K_SWALLOWED_SAVE":

            def denied(*args, **kwargs):
                raise OSError("fixture")

            f.changes.append((k, "atomic_write_json", denied))
            operation = lambda: obj._save({"fixture": True})
        elif name == "K_REQUEST_NO_JOB":
            created_jobs = []
            real_job = k.Job

            def record_job(*args, **kwargs):
                created = real_job(*args, **kwargs)
                created_jobs.append(created)
                return created

            f.changes.append((k, "adapters", lambda *args: obj.cores))
            f.changes.append((k, "Job", record_job))
            operation = lambda: k.run_request(NS(), f.paths, out=lambda *args: None, ownership=c)
        elif name == "I_PANEL_CORE":
            seen = []
            path = f.work / "panel.json"

            def verify(roles, value):
                seen.append(roles)
                good = (
                    value == (True, 0)
                    and M["managed"].load(path)[0]["sticky"] is True
                    and k.load_state(f.paths).get("job", {}).get("state") == "ok"
                )
                return a.Verification("COMMITTED", (("FILES", good),))

            c.verifier = verify

            def compound():
                first = M["managed"].set_sticky(path, True, ownership=c)
                require(f.registry.summary()["receipts"] == 0, "EARLY_RECEIPT")
                reject(
                    lambda: f.registry.acquire(
                        run_id="a" * 32, expected_generation=0, duration_ns=100
                    ),
                    M["ownership"].Refused,
                )
                return first, obj.run("xray", "update", "1.0.0", "fixture")

            operation = lambda: c.call("LIFECYCLE", compound)
        else:
            raise ValueError("CASE_UNSUPPORTED")
        before = SUPPORT.digest_tree(f.work)
        positive = name in ("K_REQUEST_NO_JOB", "I_PANEL_CORE")
        with SUPPORT.patches(f.changes):
            if positive:
                operation()
            else:
                reject(operation)
        summary = f.registry.summary()
        require(summary["receipts"] == (1 if positive else 0), "EXTRA_RECEIPTS")
        require(summary["unknown"] == (0 if positive else 1), "EXTRA_UNKNOWN")
        if name in ("K_REQUEST_FOREIGN", "K_RUN_INVALID", "K_SWALLOWED_SAVE"):
            require(SUPPORT.digest_tree(f.work) == before, "UNEXPECTED_PARTIAL_EFFECT")
        if name == "K_RUN_FAILED":
            require(k.load_state(f.paths).get("job", {}).get("state") == "failed", "FAILED_STATE")
        if name == "K_REQUEST_NO_JOB":
            require(
                len(created_jobs) == 1
                and type(created_jobs[0]) is real_job
                and created_jobs[0].ownership is c,
                "JOB_FACTORY_LOST_BINDING",
            )
            require(
                k.load_state(f.paths).get("job", {}).get("state") == "ok"
                and not f.paths.cores_request_file.exists(),
                "JOB_FACTORY_NO_COMPLETION",
            )
        if name == "I_PANEL_CORE":
            require(seen == [frozenset({"LIFECYCLE", "CORE", "PANEL"})], "ROLE_UNION")
        if positive:
            DETAILS["completion_verified"] = True
    if name.startswith(("H_NESTED_",)):
        require(f.registry.summary()["unknown"] == 1, "NESTED_TAINT_LOST")
    if name in ("H_SIGNATURE", "H_DEFERRED", "H_NO_VERIFIER") or name.startswith("B_"):
        require(
            f.registry.summary()["writers"] == f.registry.summary()["receipts"] == 0
            and not f.trace,
            "DEFINITION_OR_BINDING_EFFECT",
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
                if prefix.startswith("F_"):
                    factory(f, prefix[2:], mode)
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
                        "batch.py": "wave3_source_flow.py",
                        "support.py": "wave3_source_hooks.py",
                    }
                    if filename.parent == NOTES and filename.name in mapping:
                        public, line = "tests/stand/" + mapping[filename.name], tb.tb_lineno
                tb = tb.tb_next
            row = {
                "case": name,
                "passed": False,
                "reason": "SOURCE_FLOW_CASE_FAILED",
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
        "marker": "SOURCE_FLOW_BATCH_RECORDED"
        if passed == len(EXPECTED)
        else "SOURCE_FLOW_BATCH_PARTIAL",
        "scope": "OPTIONAL_SOURCE_FLOW_AND_FACTORY_PROPAGATION_ONLY",
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
            print("SOURCE_FLOW_BATCH_STARTED")
        else:
            require(command == "_batch", "MODE_REFUSED")
            batch()
    except Exception as exc:
        print("SOURCE_FLOW_BATCH_STOP", type(exc).__name__)
        raise SystemExit(3) from None
