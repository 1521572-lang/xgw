"""One detached, bounded qualification batch: adapters, diagnostics, fake processes."""

import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import time
import types
from dataclasses import asdict
from pathlib import Path

NOTES = Path.home() / "xgw-w3ac"
SANDBOX = NOTES / "sandbox"
BOOT = "11111111-1111-1111-1111-111111111111"
OTHER_BOOT = "22222222-2222-2222-2222-222222222222"
SOURCES = {
    "ownership.py": "2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5",
    "ownership_adapters.py": "70a1abece7e73eaeefbf1514c73dacd89602d3cd65e710f658ab4427a1d738a3",
    "ownership_diagnostics.py": "f49d8e64fda4924a2094bdc61d372459ccb24c6d13d40b33f3b06bfa3bccc32d",
    "fake_driver.py": "a287ed4d611a5a1f10d9d7c2043c83367282f89265b50d4a844f034c944fc81b",
}
SAFE_REASONS = [
    "ACK_NOT_UNKNOWN",
    "ACK_RECEIPT",
    "ADMISSION_REFUSED",
    "API",
    "ARMED",
    "BASELINE",
    "BASELINE_REFUSED",
    "BOOT_ARGUMENT",
    "BOOT_DIAGNOSTIC",
    "BOOT_MISMATCH",
    "CALLER_ASSERTION_RECORDED",
    "CAPTURE",
    "CASE_FAILED",
    "CHILD_NOT_READY",
    "CLEANUP_MASKED",
    "CLEAN_IDLE",
    "CLOCK_ARGUMENT",
    "COMMITTED",
    "COMMIT_UNCERTAIN",
    "COMPLETED",
    "COMPLETION_BLOCKED",
    "COMPLETION_UNCERTAIN",
    "COMPLETION_UNVERIFIED",
    "CONTROLLER_RC",
    "CONTROLLER_RC_OR_TIMEOUT",
    "CORE",
    "D",
    "DIAGNOSTIC_CREATED",
    "DIAGNOSTIC_RESULT",
    "DIAGNOSTIC_WROTE",
    "DIRECTORY_ARGUMENT",
    "DIRECTORY_REPLACED",
    "DORMANT_ADAPTER_DIAGNOSTIC_AND_FAKE_FILE_DRIVER",
    "DUPLICATE_JSON_KEY",
    "ERROR_NOT_PERSISTED",
    "EXPIRED_UNUSED",
    "FAILED",
    "FAKE_BASELINE_OR_DISPATCH",
    "FAKE_DRIVER_RESULT",
    "FAKE_PROTOCOL_REFUSED",
    "FAKE_PROTOCOL_STOP",
    "FAKE_READOUT",
    "FAKE_RESTORED",
    "FAULT",
    "FENCED",
    "FILES",
    "FIXTURE",
    "IDLE",
    "INITIALIZE_FAILED",
    "INJECTED",
    "INTERNAL_MODE",
    "INTERRUPTED_COMMIT",
    "INVALID_JSON",
    "INVALID_VERIFICATION",
    "JOB_ALREADY_STARTED",
    "KERNEL",
    "LEASE_ARGUMENT",
    "LEASE_CLOCK",
    "LEASE_SCHEMA",
    "LEASE_TIME",
    "LEASE_VALUES",
    "LIFECYCLE",
    "LIVE",
    "LIVE_WRITERS",
    "LOCK_BUDGET",
    "LOCK_BUDGET_ARGUMENT",
    "LOCK_BUSY",
    "LOCK_REPLACED",
    "MANUAL_REVIEW_REQUIRED",
    "MARKERS",
    "MODE",
    "NESTED_LOCK",
    "NEW",
    "NOOP",
    "NOT_COLLECTED",
    "NOT_NEEDED",
    "NO_AUTOREPAIR",
    "NO_RECORDED_RESULT",
    "OBSERVED_ONLY",
    "OPERATION_RAISED",
    "OTHER",
    "OUTCOME_RESULT",
    "OWNER_ARGUMENT",
    "OWNER_OR_MODE",
    "PANEL",
    "PEERS",
    "PEER_PATH",
    "PRIVATE_METADATA",
    "PROCESSES",
    "READ_LIMIT",
    "RECEIPT_LIMIT",
    "RECEIPT_SCHEMA",
    "RECEIPT_VALUES",
    "RECORD_LIMIT",
    "RECOVERY_",
    "RECOVERY_ARMED",
    "RECOVERY_RUNNING",
    "RECOVERY_TOKEN",
    "REFUSED",
    "REJECTION_MISSING",
    "RESTORED_ON",
    "RETIREMENT_UNVERIFIED",
    "ROLE_ARGUMENT",
    "ROLE_RESULT",
    "ROLLED_BACK",
    "ROUTES",
    "RUNNING",
    "RUNTIME_GATE",
    "SOURCE_SHA",
    "STAGE_REFUSED",
    "STAGE_UNRELATED",
    "STAGE_VALID_UNPROVEN",
    "STALE_GENERATION",
    "STALE_WRITER_TOKEN",
    "STATE_IDENTITY",
    "STATE_INTEGER",
    "STATE_SCHEMA",
    "STATE_SEQUENCE",
    "STOP_WRITER_BATCH",
    "STORE_IO",
    "STORE_IO_OR_UNSUPPORTED",
    "TERMINAL_LOST",
    "TERMINAL_SWALLOWED",
    "TUN_HOOK",
    "UNADMITTED_CALLBACK",
    "UNKNOWN",
    "UNKNOWN_RECORDED",
    "UNKNOWN_RECORD_UNCONFIRMED",
    "UNKNOWN_WRITER",
    "UNKNOWN_WRITERS",
    "UNSUPPORTED",
    "UNUSED",
    "VERIFICATION_REFUSED",
    "VERIFIER_RAISED",
    "WRITERS_IN_FLIGHT",
    "WRITER_ID",
    "WRITER_INTEGRATION_BATCH_PARTIAL",
    "WRITER_INTEGRATION_BATCH_RECORDED",
    "WRITER_INTEGRATION_BATCH_STARTED",
    "WRITER_LIMIT",
    "WRITER_SCHEMA",
    "WRITER_TOKEN",
    "WRITER_VALUES",
    "WRONG_REJECTION",
    "ZERO_WAS_UNKNOWN",
]
M = A = D = None
CHILDREN_STARTED = 0
CASE_DETAILS = None


def require(value, reason):
    if not value:
        raise ValueError(reason)


def private(path, directory=False):
    info = path.lstat()
    require(
        (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
        and (directory or info.st_nlink == 1),
        "PRIVATE_METADATA",
    )


def create(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())


def read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        private(path)
        info = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(info.st_mode)
            and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_nlink == 1,
            "PRIVATE_METADATA",
        )
        raw = stream.read(131073)
    require(len(raw) <= 131072, "READ_LIMIT")
    return json.loads(raw)


def atomic(name, value):
    create(NOTES / (name + ".part"), value)
    os.replace(NOTES / (name + ".part"), NOTES / name)


def load_sources():
    private(NOTES, True)
    for filename, digest in SOURCES.items():
        path = NOTES / filename
        private(path)
        require(
            path.stat().st_size <= 131072
            and hashlib.sha256(path.read_bytes()).hexdigest() == digest,
            "SOURCE_SHA",
        )
    package = types.ModuleType("frozen_ac")
    package.__path__ = []
    sys.modules[package.__name__] = package
    modules = []
    for name in ("ownership", "ownership_adapters", "ownership_diagnostics"):
        fullname = package.__name__ + "." + name
        spec = importlib.util.spec_from_file_location(fullname, NOTES / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[fullname] = module
        spec.loader.exec_module(module)
        modules.append(module)
    return modules


def denied(action, reason):
    try:
        action()
    except M.Refused as exc:
        require(str(exc) == reason, "WRONG_REJECTION")
    else:
        raise ValueError("REJECTION_MISSING")


def verdict(outcome="COMMITTED"):
    return A.Verification(outcome, (("FILES", True),))


def perform(registry, role, operation, verifier):
    global CASE_DETAILS
    result = A.execute(registry, role, operation, verifier)
    CASE_DETAILS = asdict(result)
    return result


def lease(reg):
    return reg.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)


def spawn(argv):
    global CHILDREN_STARTED
    child = subprocess.Popen(
        [sys.executable, "-I", "-B", *argv],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    CHILDREN_STARTED += 1
    return child


def cleanup(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=1)


def hold(root):
    require(root.parent == SANDBOX and re.fullmatch(r"case-[0-9]{2}", root.name), "PEER_PATH")
    private(SANDBOX, True)
    reg = M.Registry(root, boot_id=BOOT, expected_uid=os.getuid())
    with reg.locked():
        create(root / "hold-ready.json", {"ready": True})
        time.sleep(1.5)


def batch():
    create(NOTES / "worker-claimed.json", {"claimed": True})
    SANDBOX.mkdir(mode=0o700, exist_ok=False)
    rows = []
    started = time.monotonic()

    def case(name, action):
        global CASE_DETAILS
        CASE_DETAILS = None
        reg = M.Registry(
            SANDBOX / f"case-{len(rows) + 1:02d}",
            boot_id=BOOT,
            expected_uid=os.getuid(),
            clock_ns=lambda: 10,
        )
        reg.initialize()
        before = time.monotonic()
        try:
            details = action(reg)
            row = {"case": name, "passed": True}
            if isinstance(details, dict):
                row["details"] = details
        except Exception as exc:
            row = {
                "case": name,
                "passed": False,
                "reason": str(exc)
                if type(exc) in (ValueError, M.Refused) and str(exc) in SAFE_REASONS
                else "CASE_FAILED",
                "error_class": type(exc).__name__,
            }
        if CASE_DETAILS is not None and "details" not in row:
            row["details"] = CASE_DETAILS
        row["elapsed_ms"] = int((time.monotonic() - before) * 1000)
        rows.append(row)
        atomic("progress.json", {"final": False, "completed": len(rows), "cases": rows})

    def role(reg, name):
        calls = []
        result = perform(reg, name, lambda: calls.append(1), lambda _: verdict())
        require(
            result.status == "COMPLETED" and calls == [1] and reg.summary()["writers"] == 0,
            "ROLE_RESULT",
        )
        require(result.runtime_verifier_implemented is False, "RUNTIME_GATE")

    case("A01_CAPTURE", lambda r: role(r, "CAPTURE"))
    case("A02_PANEL", lambda r: role(r, "PANEL"))
    case("A03_PEERS", lambda r: role(r, "PEERS"))
    case("A04_CORE", lambda r: role(r, "CORE"))
    case("A05_API", lambda r: role(r, "API"))
    case("A06_TUN_HOOK", lambda r: role(r, "TUN_HOOK"))
    case("A07_LIFECYCLE", lambda r: role(r, "LIFECYCLE"))

    def admission(reg, unknown=False):
        if unknown:
            reg.unknown(reg.admit("CORE"))
        else:
            lease(reg)
        calls = []
        result = perform(reg, "CORE", lambda: calls.append(1), lambda _: verdict())
        require(
            result.status == "REFUSED" and not calls and not result.operation_entered,
            "UNADMITTED_CALLBACK",
        )

    case("A08_FENCED_NO_CALLBACK", admission)
    case("A09_UNKNOWN_NO_CALLBACK", lambda r: admission(r, True))

    def error(reg, phase):
        def fail(*args):
            raise RuntimeError("FIXTURE")

        result = perform(
            reg,
            "API",
            fail if phase == "operation" else lambda: None,
            fail if phase == "verifier" else lambda _: verdict(),
        )
        require(
            result.status == "UNKNOWN"
            and result.unknown_recorded
            and reg.summary()["unknown"] == 1,
            "ERROR_NOT_PERSISTED",
        )

    case("A10_OPERATION_ERROR", lambda r: error(r, "operation"))
    case("A11_VERIFIER_ERROR", lambda r: error(r, "verifier"))

    def rejected(reg, value):
        result = perform(reg, "API", lambda: None, lambda _: value)
        require(
            result.status == "UNKNOWN"
            and result.reason == "VERIFICATION_REFUSED"
            and reg.summary()["unknown"] == 1,
            "INVALID_VERIFICATION",
        )

    case("A12_DEFAULT_EVIDENCE", lambda r: rejected(r, A.Verification()))
    case("A13_BARE_BOOL_EVIDENCE", lambda r: rejected(r, True))
    case("A14_FALSE_CHECK", lambda r: rejected(r, A.Verification("COMMITTED", (("FILES", False),))))
    case(
        "A15_STRING_CHECK", lambda r: rejected(r, A.Verification("COMMITTED", (("FILES", "true"),)))
    )
    case(
        "A16_DUPLICATE_CHECK",
        lambda r: rejected(r, A.Verification("COMMITTED", (("FILES", True), ("FILES", True)))),
    )
    case(
        "A17_UNKNOWN_CHECK", lambda r: rejected(r, A.Verification("COMMITTED", (("OTHER", True),)))
    )
    case("A18_LIST_CHECKS", lambda r: rejected(r, A.Verification("COMMITTED", [("FILES", True)])))
    case("A19_UNKNOWN_OUTCOME", lambda r: rejected(r, A.Verification("OTHER", (("FILES", True),))))

    def outcome(reg, value):
        result = perform(reg, "PANEL", lambda: None, lambda _: verdict(value))
        require(result.status == "COMPLETED" and reg.summary()["receipts"] == 1, "OUTCOME_RESULT")

    case("A20_NOOP_RECEIPT", lambda r: outcome(r, "NOOP"))
    case("A21_ROLLBACK_RECEIPT", lambda r: outcome(r, "ROLLED_BACK"))

    def terminal(reg, exception):
        def fail():
            raise exception

        try:
            perform(reg, "CORE", fail, lambda _: verdict())
        except (KeyboardInterrupt, SystemExit) as exc:
            require(type(exc) is type(exception) and reg.summary()["unknown"] == 1, "TERMINAL_LOST")
        else:
            raise ValueError("TERMINAL_SWALLOWED")

    case("A22_KEYBOARD_INTERRUPT", lambda r: terminal(r, KeyboardInterrupt()))
    case("A23_SYSTEM_EXIT", lambda r: terminal(r, SystemExit(9)))

    def commit_error(reg, after):
        original_replace, original_fsync = M.os.replace, M.os.fsync

        def operation():
            if after:

                def fail_directory(fd):
                    if stat.S_ISDIR(os.fstat(fd).st_mode):
                        raise OSError("INJECTED")
                    original_fsync(fd)

                M.os.fsync = fail_directory
            else:

                def fail_replace(*args, **kwargs):
                    raise OSError("INJECTED")

                M.os.replace = fail_replace

        try:
            result = perform(reg, "CORE", operation, lambda _: verdict())
        finally:
            M.os.replace, M.os.fsync = original_replace, original_fsync
        require(
            result.status == "UNKNOWN" and result.reason == "COMPLETION_UNCERTAIN",
            "ACK_NOT_UNKNOWN",
        )
        if after:
            require(
                result.retained_receipt is True and reg.summary()["writers"] == 0, "ACK_RECEIPT"
            )
        else:
            denied(reg.summary, "INTERRUPTED_COMMIT")

    case("A24_PRE_REPLACE_ACK", lambda r: commit_error(r, False))
    case("A25_POST_REPLACE_ACK", lambda r: commit_error(r, True))

    def cleanup_failure(reg):
        def fail(*args):
            raise OSError("INJECTED")

        reg.unknown = fail
        result = perform(reg, "CORE", fail, lambda _: verdict())
        require(
            result.status == "UNKNOWN"
            and result.cleanup == "UNKNOWN_RECORD_UNCONFIRMED"
            and not result.unknown_recorded
            and reg.summary()["writers"] == 1,
            "CLEANUP_MASKED",
        )
        denied(lambda: lease(reg), "WRITERS_IN_FLIGHT")

    case("A26_UNKNOWN_RECORD_FAILURE", cleanup_failure)

    def nested(reg):
        def operation():
            reg.complete(reg.admit("TUN_HOOK"), outcome="NOOP", verified=True)

        result = perform(reg, "CORE", operation, lambda _: verdict())
        require(result.status == "COMPLETED" and reg.summary()["generation"] == 2, "NESTED_LOCK")

    case("A27_NESTED_ADMISSION", nested)
    case("A28_EMPTY_CHECKS", lambda r: rejected(r, A.Verification("COMMITTED", ())))

    def diagnostic(reg, expected):
        paths = list(reg.directory.iterdir())
        before = {p.name: p.read_bytes() for p in paths if p.is_file() and not p.is_symlink()}
        result = D.inspect_registry(reg)
        require(
            result.status == expected
            and result.repair_authorized is False
            and result.runtime_fence_verified is False,
            "DIAGNOSTIC_RESULT",
        )
        after = {
            p.name: p.read_bytes()
            for p in reg.directory.iterdir()
            if p.is_file() and not p.is_symlink()
        }
        require(before == after, "DIAGNOSTIC_WROTE")
        return asdict(result)

    case("B01_CLEAN_READONLY", lambda r: diagnostic(r, "CLEAN_IDLE"))

    def present(reg, unknown=False):
        token = reg.admit("API")
        if unknown:
            reg.unknown(token)
        return diagnostic(reg, "UNKNOWN_WRITERS" if unknown else "LIVE_WRITERS")

    case("B02_LIVE_READONLY", present)
    case("B03_UNKNOWN_READONLY", lambda r: present(r, True))

    def leased(reg, running=False):
        token = lease(reg)
        if running:
            reg.begin(token)
        return diagnostic(reg, "RECOVERY_RUNNING" if running else "RECOVERY_ARMED")

    case("B04_ARMED_READONLY", leased)
    case("B05_RUNNING_READONLY", lambda r: leased(r, True))

    def staged(reg, mode):
        value = read(reg.directory / "state.json")
        value["revision"] += 1
        if mode == "foreign":
            value["registry_id"] = "0" * 32
        if mode == "stale":
            value["revision"] -= 1
        create(reg.directory / "state.next", value)
        if mode == "truncated":
            (reg.directory / "state.next").write_bytes(b"{")
        if mode == "duplicate":
            (reg.directory / "state.next").write_bytes(b'{"schema":1,"schema":1}')
        expected = (
            "STAGE_REFUSED"
            if mode in ("truncated", "duplicate")
            else "STAGE_UNRELATED"
            if mode in ("foreign", "stale")
            else "STAGE_VALID_UNPROVEN"
        )
        return diagnostic(reg, expected)

    case("B06_VALID_STAGE_NOT_PROMOTED", lambda r: staged(r, "valid"))
    case("B07_TRUNCATED_STAGE", lambda r: staged(r, "truncated"))
    case("B08_FOREIGN_STAGE", lambda r: staged(r, "foreign"))
    case("B09_STALE_STAGE", lambda r: staged(r, "stale"))
    case("B10_DUPLICATE_STAGE_KEYS", lambda r: staged(r, "duplicate"))

    def old_boot(reg):
        other = M.Registry(reg.directory, boot_id=OTHER_BOOT, expected_uid=os.getuid())
        result = D.inspect_registry(other)
        require(
            result.status == "BASELINE_REFUSED"
            and result.reason == "BOOT_MISMATCH"
            and result.writers is None,
            "BOOT_DIAGNOSTIC",
        )

    case("B11_BOOT_MISMATCH", old_boot)

    def bad_mode(reg):
        (reg.directory / "state.json").chmod(0o644)
        return diagnostic(reg, "BASELINE_REFUSED")

    case("B12_BAD_MODE", bad_mode)

    def symlink_stage(reg):
        (reg.directory / "state.next").symlink_to("state.json")
        return diagnostic(reg, "STAGE_REFUSED")

    case("B13_STAGE_SYMLINK", symlink_stage)

    def bad_base(reg):
        (reg.directory / "state.json").write_bytes(b"{")
        result = diagnostic(reg, "BASELINE_REFUSED")
        require(result["writers"] is None, "ZERO_WAS_UNKNOWN")
        return result

    case("B14_CORRUPT_BASELINE_NO_ZERO_COUNTS", bad_base)

    def absent(reg):
        missing = reg.directory / "absent"
        other = M.Registry(missing, boot_id=BOOT, expected_uid=os.getuid())
        result = D.inspect_registry(other)
        require(result.status == "BASELINE_REFUSED" and not missing.exists(), "DIAGNOSTIC_CREATED")

    case("B15_ABSENT_STORE_NOT_CREATED", absent)

    def busy(reg):
        child = spawn([str(Path(__file__).resolve()), "_hold", str(reg.directory)])
        try:
            limit = time.monotonic() + 2
            while not (reg.directory / "hold-ready.json").exists() and time.monotonic() < limit:
                time.sleep(0.01)
            require((reg.directory / "hold-ready.json").exists(), "CHILD_NOT_READY")
            result = D.inspect_registry(reg)
            require(
                result.status == "BASELINE_REFUSED" and result.reason == "LOCK_BUSY", "LOCK_BUDGET"
            )
        finally:
            cleanup(child)
        return {
            "bounded_refusal": True,
            "holder_rc": child.returncode,
            "own_child_cleanup_confirmed": child.poll() is not None,
        }

    case("B16_REAL_BUSY_DIAGNOSTIC", busy)

    def fake(reg, mode, expected):
        global CASE_DETAILS
        details = {
            "controller_rc": None,
            "controller_wait_timeout": False,
            "controller_cleanup_confirmed": False,
            "driver_exit_rc": "NOT_COLLECTED",
            "expected_phase": expected,
            "observed_phase": "UNKNOWN",
            "fake_baseline": None,
            "driver_launch_observed": None,
            "fault_dispatched": None,
            "within_budget": None,
            "elapsed_ms": None,
            "timing_measured": None,
            "readout_error_class": None,
        }
        CASE_DETAILS = details
        nonce = "a" * 32
        create(reg.directory / "fake.lock", {})
        create(reg.directory / "fake-manifest.json", {"nonce": nonce, "mode": mode})
        create(
            reg.directory / "fake-state.json",
            {
                "nonce": "b" * 32 if mode == "bad_nonce" else nonce,
                "phase": "NEW",
                "value": "OTHER" if mode == "bad_baseline" else "BASELINE",
            },
        )
        child = spawn([str(NOTES / "fake_driver.py"), "_controller", str(reg.directory), mode])
        try:
            try:
                child.communicate(timeout=7)
            except subprocess.TimeoutExpired:
                details["controller_wait_timeout"] = True
        finally:
            cleanup(child)
            details["controller_rc"] = child.returncode
            details["controller_cleanup_confirmed"] = child.poll() is not None
        limit = time.monotonic() + 6
        while not (reg.directory / "fake-driver-result.json").exists() and time.monotonic() < limit:
            time.sleep(0.02)
        result = None
        # Read independent safe artifacts even after a controller error; never retry a job.
        for filename, target, key in (
            ("fake-launch.json", "driver_launch_observed", "driver_popen_returned"),
            ("fake-controller-event.json", "fault_dispatched", "fault_dispatched"),
        ):
            try:
                value = read(reg.directory / filename).get(key)
                details[target] = value if type(value) is bool else None
            except Exception as exc:
                details["readout_error_class"] = type(exc).__name__
        try:
            result = read(reg.directory / "fake-driver-result.json")
            phase = result.get("phase")
            details["observed_phase"] = (
                phase
                if phase in ("FAKE_RESTORED", "EXPIRED_UNUSED", "FAILED", "REFUSED")
                else "UNSUPPORTED"
            )
            for key in ("baseline", "within_budget", "timing_measured"):
                value = result.get(key)
                details["fake_baseline" if key == "baseline" else key] = (
                    value if type(value) is bool else None
                )
            elapsed = result.get("elapsed_ms")
            details["elapsed_ms"] = elapsed if type(elapsed) is int and elapsed >= 0 else None
        except Exception as exc:
            details["readout_error_class"] = type(exc).__name__
        expected_rc = 9 if mode == "crash" else 3 if mode.startswith("bad_") else 0
        require(
            not details["controller_wait_timeout"] and details["controller_rc"] == expected_rc,
            "CONTROLLER_RC_OR_TIMEOUT",
        )
        require(result is not None and details["readout_error_class"] is None, "FAKE_READOUT")
        measured = expected != "REFUSED"
        timing_ok = (
            (
                details["timing_measured"] is True
                and details["within_budget"] is True
                and type(details["elapsed_ms"]) is int
            )
            if measured
            else (
                details["timing_measured"] is False
                and result.get("within_budget") is None
                and result.get("elapsed_ms") is None
            )
        )
        require(
            details["observed_phase"] == expected
            and timing_ok
            and details["driver_launch_observed"] is True,
            "FAKE_DRIVER_RESULT",
        )
        baseline = expected in ("FAKE_RESTORED", "EXPIRED_UNUSED") or mode == "bad_nonce"
        require(
            details["fake_baseline"] is baseline
            and details["fault_dispatched"] is (mode in ("normal", "crash", "fail_restore")),
            "FAKE_BASELINE_OR_DISPATCH",
        )
        return details

    case("D01_CONTROLLER_EXIT_FAKE_RESTORE", lambda r: fake(r, "normal", "FAKE_RESTORED"))
    case("D02_CONTROLLER_CRASH_FAKE_RESTORE", lambda r: fake(r, "crash", "FAKE_RESTORED"))
    case("D03_UNUSED_EXPIRES", lambda r: fake(r, "none", "EXPIRED_UNUSED"))
    case("D04_LATE_DISPATCH_REFUSED", lambda r: fake(r, "late", "EXPIRED_UNUSED"))
    case("D05_EXPECTED_FAKE_RESTORE_FAILURE", lambda r: fake(r, "fail_restore", "FAILED"))
    case("D06_FOREIGN_NONCE_REFUSED", lambda r: fake(r, "bad_nonce", "REFUSED"))
    case("D07_BAD_BASELINE_REFUSED", lambda r: fake(r, "bad_baseline", "REFUSED"))
    passed = sum(row["passed"] for row in rows)
    fake_rows = [r for r in rows if r["case"].startswith("D")]
    result = {
        "marker": "WRITER_INTEGRATION_BATCH_RECORDED"
        if passed == len(rows)
        else "WRITER_INTEGRATION_BATCH_PARTIAL",
        "scope": "DORMANT_ADAPTER_DIAGNOSTIC_AND_FAKE_FILE_DRIVER",
        "total": len(rows),
        "passed": passed,
        "cases": rows,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "collector_children_started": CHILDREN_STARTED,
        "driver_launch_observations": sum(
            r.get("details", {}).get("driver_launch_observed") is True for r in fake_rows
        ),
        "real_process_cases": 8,
        "real_process_cases_passed": sum(
            r["passed"]
            for r in rows
            if r["case"].startswith("D") or r["case"] == "B16_REAL_BUSY_DIAGNOSTIC"
        ),
        "fake_positive_restorations": sum(
            r["passed"] and r.get("details", {}).get("observed_phase") == "FAKE_RESTORED"
            for r in fake_rows
        ),
        "fake_expected_failures": sum(
            r["passed"] and r.get("details", {}).get("observed_phase") == "FAILED"
            for r in fake_rows
        ),
        "fake_expected_refusals": sum(
            r["passed"] and r.get("details", {}).get("observed_phase") == "REFUSED"
            for r in fake_rows
        ),
        "fake_unused": sum(
            r["passed"] and r.get("details", {}).get("observed_phase") == "EXPIRED_UNUSED"
            for r in fake_rows
        ),
        "virtual_registry_boot_and_clock": True,
        "fake_driver_clock_measured": any(
            r.get("details", {}).get("timing_measured") is True for r in fake_rows
        ),
        "fake_driver_timings_observed": sum(
            r.get("details", {}).get("timing_measured") is True for r in fake_rows
        ),
        "installed_runtime_changed": False,
        "runtime_entrypoints_integrated": False,
        "runtime_writer_fence_installed": False,
        "runtime_recovery_implemented": False,
        "active_faults_authorized": False,
        "repair_implemented": False,
        "network_requests": 0,
        "live_gateway_operations": 0,
    }
    atomic("summary.json", result)


if __name__ == "__main__":
    try:
        require(os.geteuid() != 0 and len(sys.argv) >= 2, "OWNER_OR_MODE")
        private(NOTES, True)
        command = sys.argv[1]
        if command in ("status", "show") and len(sys.argv) == 2:
            for name in ("summary.json", "progress.json"):
                if (NOTES / name).exists():
                    print(json.dumps({"file": name, "data": read(NOTES / name)}))
                    break
            else:
                print(json.dumps({"file": None, "status": "NO_RECORDED_RESULT"}))
        else:
            M, A, D = load_sources()
            if command == "start" and len(sys.argv) == 2:
                create(NOTES / "started.json", {"started": True})
                subprocess.Popen(
                    [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "_batch"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                print("WRITER_INTEGRATION_BATCH_STARTED")
            elif command == "_batch" and len(sys.argv) == 2:
                batch()
            else:
                require(command == "_hold" and len(sys.argv) == 3, "INTERNAL_MODE")
                hold(Path(sys.argv[2]))
    except Exception as exc:
        print("STOP_WRITER_BATCH", type(exc).__name__)
        raise SystemExit(3) from None
