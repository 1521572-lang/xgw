"""New bound-composition/file-observer cases only. Frozen AD fixture support, fake I/O."""

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
import threading
import time
from pathlib import Path

NOTES = Path.home() / "xgw-w3ae"
SUPPORT_SHA = "9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917"
MANIFEST_SHA = "d38f369bc1f45e636b92c35635b261c3cba6eb33f3f42ea737cca09ad43275a0"
WRITERS = ("capture", "peers", "xray", "singbox", "cores", "api", "panel")
METHODS = (
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
    ("api", "add_outbounds"),
    ("api", "remove_outbound"),
    ("api", "add_inbounds"),
    ("api", "remove_inbound"),
    ("api", "replace_routing"),
    ("api", "pin"),
    ("api", "unpin"),
    ("panel", "update"),
)
BINDING = (
    "B_INCOMPLETE",
    "B_EXTRA",
    "B_WRONG_TYPE",
    "B_NO_VERIFIER",
    "B_WRONG_COORDINATOR",
    "B_WRONG_REGISTRY",
    "B_REGISTRY_DRIFT",
    "B_VERIFIER_DRIFT",
    "B_CALL_DRIFT",
    "B_FOREIGN_PID",
    "B_FOREIGN_THREAD",
    "B_NESTED",
)
PLANS = (
    "P_EMPTY",
    "P_LIST",
    "P_TOO_MANY",
    "P_WRONG_STEP",
    "P_UNKNOWN_WRITER",
    "P_UNKNOWN_METHOD",
    "P_ARGS_LIST",
    "P_KWARGS_DICT",
    "P_DUP_KEY",
    "P_OWNER_KEY",
    "P_USED",
    "P_FENCED",
    "P_NO_CHECKER",
)
COMPOSITES = (
    "C_SB_XRAY",
    "C_SB_XRAY_API",
    "C_PANEL_PEERS",
    "C_FAILED_RESULT",
    "C_VERIFIER_EXCEPTION",
    "C_FALSE_VERIFIER",
    "C_STEP_EXCEPTION",
    "C_AFTER_UNBIND",
    "C_AFTER_HOOK_DRIFT",
    "C_AFTER_VERIFIER_DRIFT",
    "C_AFTER_REGISTRY_DRIFT",
    "C_NO_EARLY_LEASE",
    "C_CHECKER_FALSE",
    "C_CHECKER_EXCEPTION",
    "C_FILE_MISMATCH",
    "C_SECOND_REJECT",
    "C_SECOND_TERMINAL",
)
FILES = (
    "F_PRESENT",
    "F_ABSENT",
    "F_TWO",
    "F_DIGEST_MISMATCH",
    "F_MODE",
    "F_OWNER",
    "F_HARDLINK",
    "F_SYMLINK",
    "F_PARENT_SYMLINK",
    "F_ROOT_SYMLINK",
    "F_FIFO",
    "F_OVERSIZE",
    "F_MISSING",
    "F_ABSENT_PRESENT",
    "F_ABSENT_SYMLINK",
    "F_ABSENT_MISSING_PARENT",
    "F_DIRECTORY_MODE",
    "F_ROOT_MODE",
    "F_DUPLICATE",
    "F_TRAVERSAL",
    "F_BAD_DIGEST",
    "F_BOOL_OWNER",
    "F_BOOL_MODE",
    "F_EMPTY",
)
EXPECTED = (
    tuple("H_" + writer.upper() + "__" + method.upper() for writer, method in METHODS)
    + tuple("M_" + writer.upper() for writer in WRITERS)
    + tuple("O_" + writer.upper() for writer in WRITERS)
    + BINDING
    + PLANS
    + COMPOSITES
    + FILES
)
SUPPORT = None
M = {}
DETAILS = None


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
    global SUPPORT, M
    private(NOTES, True)
    for name, digest in (("support.py", SUPPORT_SHA), ("manifest.json", MANIFEST_SHA)):
        private(NOTES / name)
        require(hashlib.sha256((NOTES / name).read_bytes()).hexdigest() == digest, "ARTIFACT_SHA")
    spec = importlib.util.spec_from_file_location("ae_fixture_support", NOTES / "support.py")
    SUPPORT = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(SUPPORT)
    SUPPORT.NOTES = NOTES
    SUPPORT.MANIFEST_SHA = MANIFEST_SHA
    return SUPPORT.verify_source()


def source():
    global M
    SUPPORT.install_audit()
    SUPPORT.load_source()
    M = SUPPORT.MODULES
    for name in ("ownership_binding", "ownership_files"):
        M[name] = importlib.import_module("frozen_ad." + name)
    b = M["ownership_binding"]
    require(tuple(b.SPECS) == WRITERS and tuple(b.FUNCTIONS) == METHODS, "BOUNDARY_INVENTORY")


def actors(f):
    b = M["ownership_binding"]
    result = {}
    for name, (cls, _, _) in b.SPECS.items():
        actor = cls.__new__(cls)
        object.__setattr__(actor, "ownership", f.coordinator)
        result[name] = actor
    result["panel"] = b.PanelWriter(f.work / "panel.json", f.coordinator)
    return result


def refused(operation, error=None):
    error = error or M["ownership_hooks"].MutationBlocked
    try:
        operation()
    except error:
        DETAILS["rejection_observed"] = True
    else:
        raise ValueError("EXPECTED_REFUSAL_MISSING")


def quiet(f, before):
    summary = f.registry.summary()
    require(
        not f.trace
        and summary["writers"] == summary["receipts"] == 0
        and SUPPORT.digest_tree(f.work) == before,
        "EFFECT_BEFORE_ADMISSION",
    )


def binding_case(f, name):
    b = M["ownership_binding"]
    c = f.coordinator
    objs = actors(f)
    before = SUPPORT.digest_tree(f.work)
    if name.startswith("H_"):
        writer, method = METHODS[EXPECTED.index(name)]
        object.__setattr__(objs[writer], method, lambda *args, **kwargs: f.event("FORBIDDEN"))
        refused(lambda: b.BoundWriters(c, objs))
    elif name.startswith(("M_", "O_")):
        writer = name[2:].lower()
        value = (
            None
            if name.startswith("M_")
            else M["ownership_hooks"].Coordinator(f.registry, f.verifier)
        )
        object.__setattr__(objs[writer], "ownership", value)
        refused(lambda: b.BoundWriters(c, objs))
    elif name == "B_INCOMPLETE":
        objs.pop("capture")
        refused(lambda: b.BoundWriters(c, objs))
    elif name == "B_EXTRA":
        objs["other"] = object()
        refused(lambda: b.BoundWriters(c, objs))
    elif name == "B_WRONG_TYPE":
        objs["capture"] = object()
        refused(lambda: b.BoundWriters(c, objs))
    elif name == "B_NO_VERIFIER":
        c.verifier = None
        refused(lambda: b.BoundWriters(c, objs))
    elif name == "B_WRONG_COORDINATOR":
        refused(lambda: b.BoundWriters(object(), objs))
    elif name == "B_WRONG_REGISTRY":
        c.registry = object()
        refused(lambda: b.BoundWriters(c, objs))
    else:
        bound = b.BoundWriters(c, objs)
        if name == "B_REGISTRY_DRIFT":
            c.registry = M["ownership"].Registry(
                f.root / "unused", boot_id=SUPPORT.BOOT, expected_uid=os.getuid()
            )
        elif name == "B_VERIFIER_DRIFT":
            c.verifier = lambda *args: M["ownership_adapters"].Verification()
        elif name == "B_CALL_DRIFT":
            c.call = lambda *args: f.event("FORBIDDEN")
        elif name == "B_FOREIGN_PID":
            bound.pid = -1
        elif name == "B_FOREIGN_THREAD":
            errors = []

            def other():
                try:
                    bound.validate()
                except M["ownership_hooks"].MutationBlocked:
                    errors.append(True)

            thread = threading.Thread(target=other)
            thread.start()
            thread.join(3)
            if thread.is_alive():
                raise SUPPORT.ScopeStop("THREAD_UNCONFIRMED")
            require(errors == [True], "FOREIGN_THREAD_ACCEPTED")
            DETAILS["rejection_observed"] = True
        elif name == "B_NESTED":
            plan = bound.prepare(
                (b.Step("panel", "update", (lambda data: False,)),), accept=lambda step, value: True
            )
            c.local.session = {"active": True}
            try:
                refused(plan.run)
            finally:
                c.local.session = None
        if name not in ("B_FOREIGN_THREAD", "B_NESTED"):
            refused(bound.validate)
    quiet(f, before)


def plan_case(f, name):
    b = M["ownership_binding"]
    objs = actors(f)
    bound = b.BoundWriters(f.coordinator, objs)
    s = b.Step("panel", "update", (lambda data: False,))
    candidates = {
        "P_EMPTY": (),
        "P_LIST": [s],
        "P_TOO_MANY": (s,) * 33,
        "P_WRONG_STEP": (object(),),
        "P_UNKNOWN_WRITER": (b.Step("other", "update"),),
        "P_UNKNOWN_METHOD": (b.Step("panel", "_update_locked"),),
        "P_ARGS_LIST": (b.Step("panel", "update", []),),
        "P_KWARGS_DICT": (b.Step("panel", "update", kwargs={}),),
        "P_DUP_KEY": (b.Step("panel", "update", kwargs=(("x", 1), ("x", 2))),),
        "P_OWNER_KEY": (b.Step("panel", "update", kwargs=(("ownership", None),)),),
    }
    before = SUPPORT.digest_tree(f.work)
    if name in candidates:
        refused(lambda: bound.prepare(candidates[name], accept=lambda step, value: True))
        quiet(f, before)
    elif name == "P_NO_CHECKER":
        refused(lambda: bound.prepare((s,)))
        quiet(f, before)
    else:
        plan = bound.prepare((s,), accept=lambda step, value: True)
        if name == "P_FENCED":
            f.registry.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
            refused(plan.run)
            quiet(f, before)
        else:
            require(plan.run() == (False,), "BUSINESS_RESULT")
        refused(plan.run)
        require(f.registry.summary()["receipts"] == (0 if name == "P_FENCED" else 1), "REPLAY")


def file_observer(f, specs):
    module = M["ownership_files"]
    rows = tuple(
        module.FileExpectation(
            path.relative_to(f.work).as_posix(), hashlib.sha256(payload).hexdigest(), mode
        )
        for path, payload, mode in specs
    )
    return module.PrivateFiles(f.work, expected_uid=os.getuid(), expectations=rows)


def composite_case(f, name):
    b, a = M["ownership_binding"], M["ownership_adapters"]
    objs = actors(f)
    seen = []
    config = {"inbounds": []}
    payload = (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode()
    objs["singbox"], _ = f.singbox("S_APPLY")
    objs["xray"], _ = f.xray("X_APPLY")
    objs["api"], _ = f.api("API_PIN")
    objs["peers"], _ = f.backend("B_RECONCILE")
    for obj in objs.values():
        object.__setattr__(obj, "ownership", f.coordinator)
    steps = (
        b.Step("singbox", "apply", (config,), (("reload", True),)),
        b.Step("xray", "apply", (config,)),
    )
    expected_modes = ("started", "restart")
    specs = (
        (f.paths.singbox_config_file, payload, 0o640),
        (f.paths.xray_config_file, payload, 0o640),
    )
    if name == "C_SB_XRAY_API":
        steps += (b.Step("api", "pin", ("fixture", "fixture")),)
        expected_modes += ("EMPTY",)
    elif name == "C_PANEL_PEERS":
        steps = (
            b.Step("panel", "update", (lambda data: False,)),
            b.Step("peers", "_save_peers"),
        )
        expected_modes = ("FALSE", "NONE")
        specs = ((M["freepool.backend"].peers_file(f.paths), b'{\n  "peers": []\n}\n', 0o600),)
    observer = file_observer(f, specs)
    if name == "C_FILE_MISMATCH":
        observer = file_observer(f, ((f.paths.singbox_config_file, b"different", 0o640),))

    def verifier(roles, values):
        seen.append(roles)
        evidence = observer.observe()
        DETAILS["file_checked"] = evidence.checked
        DETAILS["file_matched"] = evidence.matched
        if name == "C_VERIFIER_EXCEPTION":
            raise ValueError("fixture")
        if name == "C_FALSE_VERIFIER":
            return a.Verification()
        require(type(values) is tuple and len(values) == len(steps), "INCOMPLETE_RESULT")
        return a.Verification("COMMITTED", (("FILES", evidence.matched),))

    f.coordinator.verifier = verifier
    bound = b.BoundWriters(f.coordinator, objs)

    def accept(step, value):
        require(f.registry.summary()["receipts"] == 0, "EARLY_RECEIPT")
        if name == "C_NO_EARLY_LEASE":
            try:
                f.registry.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
            except M["ownership"].Refused:
                DETAILS["rejection_observed"] = True
            else:
                raise ValueError("LEASE_DURING_COMPOSITE")
        if step is steps[0] and name == "C_CHECKER_FALSE":
            return 1  # strict True required, not truthiness
        if step is steps[0] and name == "C_CHECKER_EXCEPTION":
            raise ValueError("fixture")
        mode = getattr(
            value,
            "mode",
            "EMPTY"
            if value == ""
            else "FALSE"
            if value is False
            else "NONE"
            if value is None
            else "UNSUPPORTED",
        )
        return mode == expected_modes[steps.index(step)]

    if name == "C_FAILED_RESULT":
        objs["singbox"].validator = lambda value: (False, "fixture")
    elif name == "C_SECOND_REJECT":
        objs["xray"].validator = lambda value: (False, "fixture")
    elif name == "C_SECOND_TERMINAL":
        objs["xray"].validator = lambda value: (_ for _ in ()).throw(SystemExit("fixture"))
    elif name == "C_STEP_EXCEPTION":
        objs["singbox"].validator = lambda value: (_ for _ in ()).throw(ValueError("fixture"))
    elif name.startswith("C_AFTER_"):

        def start_or_reload(value):
            f.event("SERVICE")
            if name == "C_AFTER_UNBIND":
                objs["api"].__dict__["ownership"] = None
            elif name == "C_AFTER_HOOK_DRIFT":
                objs["capture"].down = lambda: None
            elif name == "C_AFTER_VERIFIER_DRIFT":
                f.coordinator.verifier = lambda *args: a.Verification(
                    "COMMITTED", (("FILES", True),)
                )
            else:
                f.coordinator.registry = M["ownership"].Registry(
                    f.root / "unused", boot_id=SUPPORT.BOOT, expected_uid=os.getuid()
                )
            return None

        objs["singbox"]._start_or_reload = start_or_reload
    plan = bound.prepare(steps, accept=accept)
    positive = name in ("C_SB_XRAY", "C_SB_XRAY_API", "C_PANEL_PEERS", "C_NO_EARLY_LEASE")
    with SUPPORT.patches(f.changes):
        if positive:
            values = plan.run()
            require(len(values) == len(steps), "RETURN_COUNT")
        else:
            error = (
                SystemExit
                if name == "C_SECOND_TERMINAL"
                else ValueError
                if name in ("C_STEP_EXCEPTION", "C_CHECKER_EXCEPTION")
                else None
            )
            refused(plan.run, error)
    summary = f.registry.summary()
    require(summary["receipts"] == (1 if positive else 0), "COMPOSITE_RECEIPTS")
    require(summary["generation"] == (1 if positive else 0), "COMPOSITE_GENERATION")
    require(summary["unknown"] == (0 if positive else 1), "COMPOSITE_UNKNOWN")
    if positive:
        expected_roles = (
            {"LIFECYCLE", "PANEL", "PEERS"} if name == "C_PANEL_PEERS" else {"LIFECYCLE", "CORE"}
        )
        if name == "C_SB_XRAY_API":
            expected_roles.add("API")
        require(seen == [frozenset(expected_roles)], "ROLE_UNION")
        require(DETAILS["file_matched"] is True, "FILE_POSTCONDITION")
        DETAILS["completion_verified"] = True
    elif name not in ("C_VERIFIER_EXCEPTION", "C_FALSE_VERIFIER", "C_FILE_MISMATCH"):
        require(not seen and not f.paths.xray_config_file.exists(), "CONTINUED_AFTER_FAILURE")
        if name in ("C_SECOND_REJECT", "C_SECOND_TERMINAL"):
            require(f.paths.singbox_config_file.exists(), "PARTIAL_EFFECT_NOT_OBSERVED")


def file_case(f, name):
    module = M["ownership_files"]
    root = f.work / "observed"
    root.mkdir(mode=0o700)
    file = root / "file"
    file.write_bytes(b"fixture")
    file.chmod(0o600)
    item = module.FileExpectation("file", hashlib.sha256(b"fixture").hexdigest())
    items = (item,)
    uid = os.getuid()
    argument_refusal = name in {
        "F_DUPLICATE",
        "F_TRAVERSAL",
        "F_BAD_DIGEST",
        "F_BOOL_OWNER",
        "F_BOOL_MODE",
        "F_EMPTY",
    }
    if name == "F_ABSENT":
        items = (module.FileExpectation("missing", absent=True),)
    elif name == "F_TWO":
        items += (module.FileExpectation("missing", absent=True),)
    elif name == "F_DIGEST_MISMATCH":
        file.write_bytes(b"changed")
    elif name == "F_MODE":
        file.chmod(0o640)
    elif name == "F_OWNER":
        uid += 1  # refusal at root policy; no chown and no root-DAC proof
    elif name == "F_HARDLINK":
        os.link(file, root / "hardlink")
    elif name in ("F_SYMLINK", "F_FIFO"):
        file.unlink()
        if name == "F_SYMLINK":
            file.symlink_to(root / "missing")
        else:
            os.mkfifo(file, 0o600)
    elif name in ("F_PARENT_SYMLINK", "F_DIRECTORY_MODE"):
        directory = root / "directory"
        directory.mkdir(mode=0o700)
        file.rename(directory / "file")
        if name == "F_PARENT_SYMLINK":
            (root / "alias").symlink_to(directory, target_is_directory=True)
            relative = "alias/file"
        else:
            directory.chmod(0o755)
            relative = "directory/file"
        items = (module.FileExpectation(relative, item.digest),)
    elif name == "F_ROOT_SYMLINK":
        alias = f.work / "alias"
        alias.symlink_to(root, target_is_directory=True)
        root = alias
    elif name == "F_ROOT_MODE":
        root.chmod(0o755)
    elif name == "F_OVERSIZE":
        with file.open("wb") as stream:
            stream.truncate(module.MAX_FILE + 1)
    elif name == "F_MISSING":
        file.unlink()
    elif name in ("F_ABSENT_PRESENT", "F_ABSENT_SYMLINK", "F_ABSENT_MISSING_PARENT"):
        if name == "F_ABSENT_SYMLINK":
            file.unlink()
            file.symlink_to(root / "missing")
        relative = "missing/file" if name == "F_ABSENT_MISSING_PARENT" else "file"
        items = (module.FileExpectation(relative, absent=True),)
    elif name == "F_DUPLICATE":
        items = (item, item)
    elif name == "F_TRAVERSAL":
        items = (module.FileExpectation("../file", item.digest),)
    elif name == "F_BAD_DIGEST":
        items = (module.FileExpectation("file", "invalid"),)
    elif name == "F_BOOL_OWNER":
        uid = True
    elif name == "F_BOOL_MODE":
        items = (module.FileExpectation("file", item.digest, True),)
    elif name == "F_EMPTY":
        items = ()
    before = SUPPORT.digest_tree(f.work)
    make = lambda: module.PrivateFiles(root, expected_uid=uid, expectations=items)
    if argument_refusal:
        refused(make, module.ObservationRefused)
    else:
        evidence = make().observe()
        DETAILS["file_checked"] = evidence.checked
        DETAILS["file_matched"] = evidence.matched
        require(evidence.matched is (name in ("F_PRESENT", "F_ABSENT", "F_TWO")), "FILE_DECISION")
    require(SUPPORT.digest_tree(f.work) == before, "OBSERVER_MUTATED_TREE")


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
                "file_checked",
                "file_matched",
                "rejection_observed",
                "completion_verified",
            )
        )
        try:
            f = SUPPORT.Fixture(root)
            if name in FILES:
                file_case(f, name)
            elif name in COMPOSITES:
                composite_case(f, name)
            elif name in PLANS:
                plan_case(f, name)
            else:
                binding_case(f, name)
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
                        "batch.py": "wave3_bound_batch.py",
                        "support.py": "wave3_source_hooks.py",
                    }
                    if filename.parent == NOTES and filename.name in mapping:
                        public, line = "tests/stand/" + mapping[filename.name], tb.tb_lineno
                tb = tb.tb_next
            row = {
                "case": name,
                "passed": False,
                "reason": "BOUND_CASE_FAILED",
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
        "marker": "BOUND_COMPOSITE_BATCH_RECORDED"
        if passed == len(EXPECTED)
        else "BOUND_COMPOSITE_BATCH_PARTIAL",
        "scope": "EXPLICIT_BOUND_SOURCE_AND_PRIVATE_FILES_ONLY",
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
            print("BOUND_COMPOSITE_BATCH_STARTED")
        else:
            require(command == "_batch", "MODE_REFUSED")
            batch()
    except Exception as exc:
        print("BOUND_COMPOSITE_BATCH_STOP", type(exc).__name__)
        raise SystemExit(3) from None
