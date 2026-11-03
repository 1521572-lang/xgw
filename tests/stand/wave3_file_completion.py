"""New FILES completion policy cases. Private dummy files; no live activation."""

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
import threading
import time
from pathlib import Path

NOTES = Path.home() / "xgw-w3ai"
SUPPORT_SHA = "9a03913dd77b11366573e3e6e8f7a90424b5fbc282ae88ddd4eed265752d5917"
MANIFEST_SHA = "c575672fc7727f30a75d01d40727aab67a8f971608f44b598754b228d9c7f249"
CONTRACTS = (
    "T_TYPE",
    "T_ROLES_EMPTY",
    "T_ROLES_LIST",
    "T_ROLES_UNKNOWN",
    "T_ROLES_STRING",
    "T_DOMAINS_LIST",
    "T_DOMAINS_EMPTY",
    "T_DOMAINS_DUPLICATE",
    "T_DOMAINS_UNKNOWN",
    "T_DOMAINS_NO_FILES",
    "T_OUTCOME",
    "T_OBSERVER",
    "T_EMPTY_OBSERVER_POLICY",
    "T_BOOL_OBSERVER_POLICY",
    "T_CHECKER",
    "T_ASYNC",
    "T_GENERATOR",
)
ROLE_POSITIVE = tuple(
    "R_" + r
    for r in (
        "CAPTURE",
        "PANEL",
        "PEERS",
        "CORE",
        "API",
        "TUN_HOOK",
        "LIFECYCLE",
        "UNION",
    )
)
ROLE_NEGATIVE = ("R_EMPTY", "R_SET", "R_LIST", "R_OTHER", "R_EXTRA", "R_MISSING")
DOMAINS = tuple("U_" + d for d in ("KERNEL", "API", "PROCESSES", "MODE", "ROUTES", "MARKERS"))
FILES = (
    "F_PRESENT",
    "F_ABSENT",
    "F_TWO",
    "F_NOOP",
    "F_ROLLBACK",
    "F_CHANGED",
    "F_MISSING",
    "F_MODE",
    "F_LINK",
    "F_ROOT_MODE",
    "F_MISSING_PARENT",
    "F_ABSENCE_PRESENT",
)
DRIFTS = (
    "D_OBSERVER",
    "D_CONTRACT",
    "D_ACCEPT",
    "D_ROOT",
    "D_UID",
    "D_EXPECTATIONS",
    "D_OBSERVE",
    "D_OPEN_ROOT",
    "D_DIRECTORY",
    "D_OBSERVE_ONE",
    "D_PID",
    "D_THREAD",
)
CHECKERS = (
    "K_FALSE",
    "K_ONE",
    "K_TEXT",
    "K_EXCEPTION",
    "K_TERMINAL",
    "K_REENTER",
    "K_DRIFT_DURING_CHECK",
    "K_FILECHANGE_DURING_CHECK",
    "K_FRESH_SECOND",
)
INTEGRATIONS = (
    "I_COMMITTED",
    "I_NOOP",
    "I_ROLLBACK",
    "I_FILES_MISMATCH",
    "I_ROLE_MISMATCH",
    "I_DOMAIN_UNKNOWN",
    "I_RESULT_REJECT",
    "I_FENCED",
)
EXPECTED = (
    CONTRACTS + ROLE_POSITIVE + ROLE_NEGATIVE + DOMAINS + FILES + DRIFTS + CHECKERS + INTEGRATIONS
)
SUPPORT = None
M = {}
DETAILS = None
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
    spec = importlib.util.spec_from_file_location("ai_fixture_support", NOTES / "support.py")
    SUPPORT = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(SUPPORT)
    SUPPORT.NOTES, SUPPORT.MANIFEST_SHA = NOTES, MANIFEST_SHA
    return SUPPORT.verify_source()


def source():
    global M
    SUPPORT.install_audit()
    SUPPORT.load_source()
    M = SUPPORT.MODULES
    for name in ("ownership_binding", "ownership_files", "ownership_completion"):
        M[name] = importlib.import_module("frozen_ad." + name)
    require(len(M["ownership_binding"].SPECS) == 9, "BOUNDARY_INVENTORY")


def write(path, raw=b"BASELINE\n", mode=0o600):
    path.write_bytes(raw)
    path.chmod(mode)


def setup(f, *, roles=None, domains=("FILES",), outcome="COMMITTED", accept=None, items=None):
    c, fm = M["ownership_completion"], M["ownership_files"]
    target = f.work / "result.txt"
    write(target)
    if items is None:
        items = (fm.FileExpectation("result.txt", hashlib.sha256(b"BASELINE\n").hexdigest()),)
    observer = fm.PrivateFiles(f.work, expected_uid=os.getuid(), expectations=items)
    contract = c.CompletionContract(
        frozenset({"PANEL"}) if roles is None else roles, domains, outcome
    )
    verifier = c.FileCompletion(
        contract, observer, accept=(lambda value: value is True) if accept is None else accept
    )
    return verifier, target


def record(v, decision=None):
    d = v.last
    DETAILS.update(
        file_checked=d.checked,
        file_matched=d.matched,
        accept_entered=d.accept_entered,
        observation_entered=d.observation_entered,
        completion_verified=d.verified,
        evidence_reason=d.reason,
    )
    if decision is not None:
        DETAILS.update(verification_accepted=decision.accepted(), outcome=decision.outcome)


def decision(v, roles=frozenset({"PANEL"}), *, passed=False, reason=None):
    result = v(roles, True)
    record(v, result)
    require(result.accepted() is passed, "VERIFICATION_DECISION")
    require(v.last.verified is passed, "EVIDENCE_DECISION")
    if reason is not None:
        require(v.last.reason == reason, "EVIDENCE_REASON")
    if passed:
        require(result.checks == (("FILES", True),), "CHECK_DOMAINS")
    else:
        require(result.outcome == "UNKNOWN" and result.checks == (), "FAIL_CLOSED")


def contract_case(f, name):
    c = M["ownership_completion"]
    v, _ = setup(f)
    roles, domains, outcome, files, accept = (
        v.contract.roles,
        v.contract.domains,
        "COMMITTED",
        v.files,
        v.accept,
    )
    replacements = {
        "T_ROLES_EMPTY": frozenset(),
        "T_ROLES_LIST": ["PANEL"],
        "T_ROLES_UNKNOWN": frozenset({"UNKNOWN"}),
        "T_ROLES_STRING": "PANEL",
    }
    roles = replacements.get(name, roles)
    replacements = {
        "T_DOMAINS_LIST": ["FILES"],
        "T_DOMAINS_EMPTY": (),
        "T_DOMAINS_DUPLICATE": ("FILES", "FILES"),
        "T_DOMAINS_UNKNOWN": ("FILES", "UNKNOWN"),
        "T_DOMAINS_NO_FILES": ("API",),
    }
    domains = replacements.get(name, domains)
    if name == "T_OUTCOME":
        outcome = "UNKNOWN"
    if name == "T_OBSERVER":
        files = object()
    if name == "T_EMPTY_OBSERVER_POLICY":
        files.expectations = ()
    if name == "T_BOOL_OBSERVER_POLICY":
        files.expected_uid = True
    if name == "T_CHECKER":
        accept = True
    if name == "T_ASYNC":

        async def accept(value):
            return True

    if name == "T_GENERATOR":

        def accept(value):
            yield True

    contract = object() if name == "T_TYPE" else c.CompletionContract(roles, domains, outcome)
    before = SUPPORT.digest_tree(f.work)
    try:
        c.FileCompletion(contract, files, accept=accept)
    except c.CompletionRefused:
        DETAILS["rejection_observed"] = True
    else:
        raise ValueError("CONSTRUCTOR_NOT_REFUSED")
    require(before == SUPPORT.digest_tree(f.work), "CONSTRUCTOR_WROTE_FILES")


def role_case(f, name):
    required = frozenset({"PANEL"})
    actual = required
    domains = ("FILES",)
    if name in ROLE_POSITIVE:
        actual = frozenset({"PANEL", "LIFECYCLE"}) if name == "R_UNION" else frozenset({name[2:]})
        required = actual
    elif name.startswith("U_"):
        domains = ("FILES", name[2:])
    elif name == "R_EMPTY":
        actual = frozenset()
    elif name == "R_SET":
        actual = {"PANEL"}
    elif name == "R_LIST":
        actual = ["PANEL"]
    elif name == "R_OTHER":
        actual = frozenset({"API"})
    elif name == "R_EXTRA":
        actual = frozenset({"PANEL", "API"})
    elif name == "R_MISSING":
        required = frozenset({"PANEL", "API"})
    v, _ = setup(f, roles=required, domains=domains)
    decision(
        v,
        actual,
        passed=name in ROLE_POSITIVE,
        reason=None
        if name in ROLE_POSITIVE
        else "DOMAIN_NOT_IMPLEMENTED"
        if name in DOMAINS
        else "ROLE_COVERAGE",
    )
    if name not in ROLE_POSITIVE:
        require(not v.last.accept_entered and not v.last.observation_entered, "EARLY_REFUSAL")


def file_case(f, name):
    fm = M["ownership_files"]
    items = None
    if name == "F_ABSENT":
        items = (fm.FileExpectation("absent.txt", absent=True),)
    elif name == "F_TWO":
        items = (
            fm.FileExpectation("result.txt", hashlib.sha256(b"BASELINE\n").hexdigest()),
            fm.FileExpectation("absent.txt", absent=True),
        )
    elif name == "F_MISSING_PARENT":
        items = (fm.FileExpectation("missing/absent.txt", absent=True),)
    elif name == "F_ABSENCE_PRESENT":
        items = (fm.FileExpectation("result.txt", absent=True),)
    outcome = "NOOP" if name == "F_NOOP" else "ROLLED_BACK" if name == "F_ROLLBACK" else "COMMITTED"
    v, target = setup(f, items=items, outcome=outcome)
    if name == "F_CHANGED":
        write(target, b"CHANGED\n")
    elif name == "F_MISSING":
        target.unlink()
    elif name == "F_MODE":
        target.chmod(0o644)
    elif name == "F_LINK":
        (f.work / "alias.txt").hardlink_to(target)
    elif name == "F_ROOT_MODE":
        f.work.chmod(0o755)
    before = SUPPORT.digest_tree(f.work)
    positive = name in ("F_PRESENT", "F_ABSENT", "F_TWO", "F_NOOP", "F_ROLLBACK")
    decision(v, passed=positive, reason="FILES_VERIFIED" if positive else "FILES_NOT_VERIFIED")
    require(before == SUPPORT.digest_tree(f.work), "VERIFIER_MUTATED_FILES")


def drift_case(f, name):
    c = M["ownership_completion"]
    v, _ = setup(f)
    if name == "D_OBSERVER":
        v.files = object()
    elif name == "D_CONTRACT":
        v.contract = c.CompletionContract(frozenset({"PANEL"}), ("FILES",), "NOOP")
    elif name == "D_ACCEPT":
        v.accept = lambda value: True
    elif name == "D_ROOT":
        v.files.root = f.work / "other"
    elif name == "D_UID":
        v.files.expected_uid = True
    elif name == "D_EXPECTATIONS":
        v.files.expectations = ()
    elif name in ("D_OBSERVE", "D_OPEN_ROOT", "D_DIRECTORY", "D_OBSERVE_ONE"):
        setattr(v.files, name[2:].lower(), lambda *args: True)
    elif name == "D_PID":
        v._pid = -1
    if name == "D_THREAD":
        answers = []

        def foreign():
            answers.append(v(frozenset({"PANEL"}), True).accepted())

        worker = threading.Thread(target=foreign)
        worker.start()
        worker.join(2)
        if worker.is_alive():
            raise SUPPORT.ScopeStop("UNFINISHED_THREAD")
        require(answers == [False], "FOREIGN_THREAD_ACCEPTED")
        record(v)
    else:
        reason = (
            "VERIFIER_CONTEXT"
            if name == "D_PID"
            else "VERIFIER_DRIFT"
            if name in ("D_OBSERVER", "D_CONTRACT", "D_ACCEPT")
            else "OBSERVER_DRIFT"
        )
        decision(v, reason=reason)
    require(not v.last.accept_entered and not v.last.observation_entered, "DRIFT_NOT_EARLY")


def checker_case(f, name):
    c = M["ownership_completion"]
    holder = {}

    def check(value):
        v = holder["v"]
        if name == "K_FALSE":
            return False
        if name == "K_ONE":
            return 1
        if name == "K_TEXT":
            return "true"
        if name == "K_EXCEPTION":
            raise RuntimeError("PRIVATE_FIXTURE_TEXT")
        if name == "K_TERMINAL":
            raise KeyboardInterrupt()
        if name == "K_REENTER":
            with contextlib.suppress(c.CompletionRefused):
                v(frozenset({"PANEL"}), value)
        if name == "K_DRIFT_DURING_CHECK":
            v.files.expectations = ()
        if name == "K_FILECHANGE_DURING_CHECK":
            write(f.work / "result.txt", b"CHANGED\n")
        return True

    v, target = setup(f, accept=check)
    holder["v"] = v
    if name == "K_TERMINAL":
        try:
            v(frozenset({"PANEL"}), True)
        except KeyboardInterrupt:
            DETAILS["rejection_observed"] = True
        else:
            raise ValueError("TERMINAL_NOT_RERAISED")
        record(v)
        require(v.last.reason == "CHECK_INTERRUPTED" and not v._active, "TERMINAL_CLEANUP")
    elif name == "K_FRESH_SECOND":
        decision(v, passed=True)
        write(target, b"CHANGED\n")
        decision(v, reason="FILES_NOT_VERIFIED")
        require(v.last.observation_entered, "CACHED_SUCCESS")
    else:
        reason = {
            "K_EXCEPTION": "CHECK_ERROR",
            "K_REENTER": "VERIFIER_TAINTED",
            "K_DRIFT_DURING_CHECK": "OBSERVER_DRIFT",
            "K_FILECHANGE_DURING_CHECK": "FILES_NOT_VERIFIED",
        }.get(name, "RESULT_NOT_ACCEPTED")
        decision(v, reason=reason)


def integration_case(f, name):
    b, fm, c = M["ownership_binding"], M["ownership_files"], M["ownership_completion"]
    target = f.work / "panel.json"
    base, error = M["managed"].load(target)
    require(not error, "PANEL_BASELINE")
    raw = lambda data: (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
    write(target, raw(base))
    # Existing panel load has its own stable serialization order. Pin that
    # baseline before computing the expected final bytes; do not infer from a
    # missing-file default dict whose key order differs.
    base, error = M["managed"].load(target)
    require(not error, "PANEL_EXISTING_BASELINE")
    write(target, raw(base))
    final = dict(base)
    if name not in ("I_NOOP", "I_ROLLBACK"):
        final["free_pool_pin"] = "b" * 32
    digest = hashlib.sha256(raw(final)).hexdigest()
    if name == "I_FILES_MISMATCH":
        digest = "0" * 64
    observer = fm.PrivateFiles(
        f.work, expected_uid=os.getuid(), expectations=(fm.FileExpectation("panel.json", digest),)
    )
    roles = frozenset({"LIFECYCLE", "PANEL"}) if name != "I_ROLE_MISMATCH" else frozenset({"PANEL"})
    domains = ("FILES", "KERNEL") if name == "I_DOMAIN_UNKNOWN" else ("FILES",)
    outcome = "NOOP" if name == "I_NOOP" else "ROLLED_BACK" if name == "I_ROLLBACK" else "COMMITTED"
    v = c.FileCompletion(
        c.CompletionContract(roles, domains, outcome),
        observer,
        accept=lambda values: (
            type(values) is tuple
            and len(values) == 2
            and all(type(x) is bool for x in values)
            and name != "I_RESULT_REJECT"
        ),
    )
    f.coordinator.verifier = v
    actors = {}
    for actor_name, (cls, _, _) in b.SPECS.items():
        actor = cls.__new__(cls)
        object.__setattr__(actor, "ownership", f.coordinator)
        actors[actor_name] = actor
    actors["panel"] = b.PanelWriter(target, f.coordinator)
    object.__setattr__(actors["xray"], "api", actors["api"])
    actors["pool"].store, actors["pool"].runtime = actors["pool_store"], actors["peers"]

    def change(pin):
        def apply(data):
            f.trace.append("PANEL_BODY")
            if name == "I_NOOP":
                return False
            data["free_pool_pin"] = pin
            return True

        return apply

    lastpin = "" if name == "I_ROLLBACK" else "b" * 32
    plan = b.BoundWriters(f.coordinator, actors).prepare(
        (
            b.Step("panel", "update", (change("a" * 32),)),
            b.Step("panel", "update", (change(lastpin),)),
        ),
        accept=lambda step, value: type(value) is bool,
    )
    if name == "I_FENCED":
        f.registry.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
    positive = name in ("I_COMMITTED", "I_NOOP", "I_ROLLBACK")
    try:
        values = plan.run()
    except M["ownership_hooks"].MutationBlocked:
        require(not positive, "POSITIVE_REFUSED")
        DETAILS["rejection_observed"] = True
    else:
        require(
            positive and values == ((False, False) if name == "I_NOOP" else (True, True)),
            "COMPOSITE_RESULT",
        )
    record(v)
    s = f.registry.summary()
    require(s["receipts"] == (1 if positive else 0), "RECEIPT_COUNT")
    require(s["generation"] == (1 if positive else 0), "GENERATION_COUNT")
    require(s["unknown"] == (0 if positive or name == "I_FENCED" else 1), "UNKNOWN_COUNT")
    require(len(f.trace) == (0 if name == "I_FENCED" else 2), "PANEL_BODY_COUNT")
    require(v.last.verified is positive, "FINAL_VERIFIER_DECISION")
    if name == "I_FENCED":
        require(v.last.reason == "NOT_OBSERVED", "FENCED_CALLED_VERIFIER")
    elif positive:
        require(target.read_bytes() == raw(final), "FINAL_FILE_CONTENT")


def run_case(f, name):
    if name in CONTRACTS:
        contract_case(f, name)
    elif name in ROLE_POSITIVE + ROLE_NEGATIVE + DOMAINS:
        role_case(f, name)
    elif name in FILES:
        file_case(f, name)
    elif name in DRIFTS:
        drift_case(f, name)
    elif name in CHECKERS:
        checker_case(f, name)
    else:
        require(name in INTEGRATIONS, "CASE_UNKNOWN")
        integration_case(f, name)


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
                        "batch.py": "wave3_file_completion.py",
                        "support.py": "wave3_source_hooks.py",
                    }
                    if filename.parent == NOTES and filename.name in mapping:
                        public, line = "tests/stand/" + mapping[filename.name], tb.tb_lineno
                tb = tb.tb_next
            row = {
                "case": name,
                "passed": False,
                "reason": "FILE_COMPLETION_CASE_FAILED",
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
        "marker": "FILE_COMPLETION_BATCH_RECORDED"
        if passed == len(EXPECTED)
        else "FILE_COMPLETION_BATCH_PARTIAL",
        "scope": "EXPLICIT_PRIVATE_FILES_COMPLETION_ONLY",
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
            and data.get("scope") == "EXPLICIT_PRIVATE_FILES_COMPLETION_ONLY"
            and data.get("marker")
            in ("FILE_COMPLETION_BATCH_RECORDED", "FILE_COMPLETION_BATCH_PARTIAL"),
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
        "# Отчёт: XGW wave3ai — explicit FILES completion",
        "",
        "Автоматические exact данные; таблицу не редактировать. worker_exit_rc=NOT_COLLECTED.",
        "Только private fixture FILES. Runtime/source activation, сеть и службы не изменялись.",
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
                "tests/stand/wave3_file_completion.py",
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
    print("FILE_COMPLETION_REPORT_READY")


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
            print("FILE_COMPLETION_BATCH_STARTED")
        else:
            require(command == "_batch", "MODE_REFUSED")
            batch()
    except Exception:
        print("FILE_COMPLETION_BATCH_STOP", "LOCAL_IO_OR_SCHEMA_ERROR")
        raise SystemExit(3) from None
