"""Qualify dormant ownership.py through frozen user-sandbox fixtures only."""

import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

NOTES = Path.home() / "xgw-w3ab"
SANDBOX = NOTES / "sandbox"
BOOT = "11111111-1111-1111-1111-111111111111"
OTHER_BOOT = "22222222-2222-2222-2222-222222222222"
RUN = "a" * 32
LIBRARY_SHA = "2a04974052ff99ee27bbf8392e75db13d31a4551fc7163ccf54c1f9618da67a5"
SAFE_REASONS = [
    "ADMITTED",
    "API",
    "ARMED",
    "ARMED_BLOCKS_WRITER",
    "BACKWARD_CLOCK_REFUSED",
    "BOOLEAN_CLOCK_REFUSED",
    "BOOLEAN_EXPECTED_GENERATION_REFUSED",
    "BOOT_ARGUMENT",
    "BOOT_MISMATCH",
    "CAPTURE",
    "CASE_FAILED",
    "CHILD_RESULT",
    "CLOCK_ARGUMENT",
    "COHERENT_RECEIPT",
    "COMMITTED",
    "COMMIT_UNCERTAIN",
    "COMPLETED",
    "COMPLETION_BLOCKED",
    "COMPLETION_UNVERIFIED",
    "CONCURRENT_ADMISSION",
    "CORE",
    "DIRECTORY_ARGUMENT",
    "DIRECTORY_REPLACED",
    "DISPATCHED_JOB_CANNOT_BE_UNUSED_OR_DISPATCHED_TWICE",
    "DORMANT_PRODUCT_REGISTRY_USER_SANDBOX",
    "DUPLICATE_COMPLETION_CANNOT_PUBLISH_TWICE",
    "DUPLICATE_GENERATION",
    "DUPLICATE_JSON_KEY",
    "DUPLICATE_JSON_KEYS_REFUSED",
    "EXPIRED_LEASE_NEVER_UNFENCES",
    "FALSE_COMPLETION_REFUSED",
    "FENCED",
    "FOREIGN_REGISTRY_TOKEN_REFUSED",
    "IDLE",
    "INITIALIZE_FAILED",
    "INJECTED",
    "INTERRUPTED_COMMIT",
    "INTERRUPTED_STAGE_BLOCKS_WITHOUT_AUTOREPAIR",
    "INVALID_JSON",
    "JOB_ALREADY_STARTED",
    "LEASE_ARGUMENT",
    "LEASE_CLOCK",
    "LEASE_SCHEMA",
    "LEASE_TIME",
    "LEASE_VALUES",
    "LIFECYCLE",
    "LIVE",
    "LOCK_BUDGET_ARGUMENT",
    "LOCK_BUSY",
    "LOCK_REPLACED",
    "METADATA",
    "MODE_ARGUMENT",
    "NOOP",
    "NO_PENDING_BARRIER_BEFORE_DRAIN",
    "OLD_BOOT_REFUSES_READ_AND_ADMISSION",
    "OLD_RECORD",
    "ORDINARY_OWNER_REQUIRED",
    "OUTCOME_RECEIPTS_ALL_INVALIDATE_OLD_GENERATION",
    "OVERSIZED_RECORD_REFUSED",
    "OWNER_ARGUMENT",
    "OWNER_POLICY_MISMATCH_REFUSED",
    "PANEL",
    "PEERS",
    "PEER_MODE",
    "PEER_PATH",
    "POST_REPLACE_ACK_ERROR_HAS_COHERENT_RECEIPT",
    "PRE_REPLACE_FAILURE_PRESERVES_OLD_RECORD_AND_STAGE",
    "PRIVATE_METADATA",
    "REAL_",
    "REAL_CHILD_HOOK_FINISHES_WITH_PARENT_TICKET",
    "REAL_OWNER_EXIT_DOES_NOT_PRUNE_DURABLE_TICKET",
    "REAL_PROCESSES_HAVE_DISTINCT_DURABLE_TICKETS",
    "RECEIPTS",
    "RECEIPT_BOUND",
    "RECEIPT_HISTORY_IS_BOUNDED",
    "RECEIPT_LIMIT",
    "RECEIPT_SCHEMA",
    "RECEIPT_VALUES",
    "RECORD_LIMIT",
    "RECOVERY_TOKEN",
    "REGISTRY_FOUNDATION_PARTIAL",
    "REGISTRY_FOUNDATION_RECORDED",
    "REJECTION_MISSING",
    "REOPEN",
    "REPLACED_STABLE_LOCK_REFUSED",
    "RESTORED_ON",
    "RESTORED_RECORD",
    "RETIREMENT_UNVERIFIED",
    "ROLE_ARGUMENT",
    "ROLLED_BACK",
    "ROUNDTRIP",
    "RUNNING",
    "SAME_BOOT_REOPEN_RETAINS_WRITER",
    "SOURCE_SHA",
    "STALE_GENERATION",
    "STALE_WRITER_TOKEN",
    "STATE_IDENTITY",
    "STATE_INTEGER",
    "STATE_PERMISSIONS_REFUSED",
    "STATE_SCHEMA",
    "STATE_SEQUENCE",
    "STATE_SYMLINK_REFUSED",
    "STOP_REGISTRY_BATCH",
    "STORE_IO",
    "STRING_COMPLETION_REFUSED",
    "SYNTHETIC_RESTORED_RECEIPT_ADVANCES_GENERATION",
    "TUN_HOOK",
    "UNIFIED_RECORD_COMPLETION",
    "UNKNOWN",
    "UNKNOWN_REQUIRES_FUTURE_REPAIR",
    "UNKNOWN_WRITER",
    "UNUSED",
    "UNUSED_RETIRE_INVALIDATES_OLD_EPOCH",
    "UNVERIFIED_DRAIN",
    "WRITERS_IN_FLIGHT",
    "WRITER_CAP_NEVER_EVICTS_LIVE_TICKET",
    "WRITER_ID",
    "WRITER_LIMIT",
    "WRITER_SCHEMA",
    "WRITER_TOKEN",
    "WRITER_VALUES",
    "WRONG_REJECTION",
]
M = None
CHILDREN_STARTED = 0


def require(value, code):
    if not value:
        raise ValueError(code)


def private(path, directory=False):
    info = path.lstat()
    kind = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    require(
        kind
        and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
        and (directory or info.st_nlink == 1),
        "METADATA",
    )


def create(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())


def load_library():
    private(NOTES, True)
    path = NOTES / "registry.py"
    private(path)
    require(
        path.stat().st_size <= 131072
        and hashlib.sha256(path.read_bytes()).hexdigest() == LIBRARY_SHA,
        "SOURCE_SHA",
    )
    spec = importlib.util.spec_from_file_location("frozen_ownership_candidate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def denied(action, code):
    try:
        action()
    except M.Refused as exc:
        require(str(exc) == code, "WRONG_REJECTION")
    else:
        raise ValueError("REJECTION_MISSING")


def acquire(reg, generation=0):
    return reg.acquire(run_id=RUN, expected_generation=generation, duration_ns=100)


def raw_state(reg):
    # Internal assertions only; never emit this identity-bearing object.
    return json.loads((reg.directory / "state.json").read_bytes())


def peer(root, mode):
    require(root.parent == SANDBOX and re.fullmatch(r"case-[0-9]{2}", root.name), "PEER_PATH")
    private(SANDBOX, True)
    reg = M.Registry(root, boot_id=BOOT, expected_uid=os.getuid())
    if mode == "admit":
        reg.admit("CORE")
        print("ADMITTED")
    elif mode == "hook":
        token = reg.admit("TUN_HOOK")
        reg.complete(token, outcome="COMMITTED", verified=True)
        print("COMPLETED")
    else:
        raise ValueError("PEER_MODE")


def spawn(root, mode):
    global CHILDREN_STARTED
    result = subprocess.Popen(
        [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "_peer", str(root), mode],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    CHILDREN_STARTED += 1
    return result


def cleanup(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=1)


def read_child(child, expected):
    output = child.communicate(timeout=4)[0]
    require(child.returncode == 0 and output.strip() == expected, "CHILD_RESULT")
    return {"child_rc": child.returncode, "fixed_output_matched": True}


def batch():
    private(NOTES, True)
    create(NOTES / "registry-started.json", {"started": True})
    SANDBOX.mkdir(mode=0o700, exist_ok=False)
    rows = []

    def test(name, action):
        reg = M.Registry(
            SANDBOX / f"case-{len(rows) + 1:02d}",
            boot_id=BOOT,
            expected_uid=os.getuid(),
            clock_ns=lambda: reg.fixture_clock[0],
        )
        reg.fixture_clock = [10]
        reg.initialize()
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
        rows.append(row)
        create(NOTES / "progress.part", {"final": False, "completed": len(rows), "cases": rows})
        os.replace(NOTES / "progress.part", NOTES / "registry-progress.json")

    def roundtrip(r):
        token = r.admit("CAPTURE")
        r.complete(token, outcome="COMMITTED", verified=True)
        require(r.summary()["generation"] == 1 and r.summary()["writers"] == 0, "ROUNDTRIP")

    test("UNIFIED_RECORD_COMPLETION", roundtrip)

    def reopen(r):
        r.admit("CORE")
        other = M.Registry(r.directory, boot_id=BOOT, expected_uid=os.getuid())
        require(other.summary()["writers"] == 1, "REOPEN")
        denied(lambda: acquire(other), "WRITERS_IN_FLIGHT")

    test("SAME_BOOT_REOPEN_RETAINS_WRITER", reopen)

    def other_boot(r):
        other = M.Registry(r.directory, boot_id=OTHER_BOOT, expected_uid=os.getuid())
        denied(other.summary, "BOOT_MISMATCH")
        denied(lambda: other.admit("CORE"), "BOOT_MISMATCH")

    test("OLD_BOOT_REFUSES_READ_AND_ADMISSION", other_boot)

    def foreign(r):
        token = r.admit("CORE")
        denied(
            lambda: r.complete(
                {**token, "registry_id": "0" * 32}, outcome="COMMITTED", verified=True
            ),
            "WRITER_TOKEN",
        )

    test("FOREIGN_REGISTRY_TOKEN_REFUSED", foreign)

    def duplicate(r):
        token = r.admit("CORE")
        r.complete(token, outcome="COMMITTED", verified=True)
        denied(lambda: r.complete(token, outcome="COMMITTED", verified=True), "STALE_WRITER_TOKEN")
        require(r.summary()["generation"] == 1, "DUPLICATE_GENERATION")
        require(r.receipt(token) == {"outcome": "COMMITTED", "generation": 1}, "RECEIPT_LOOKUP")

    test("DUPLICATE_COMPLETION_CANNOT_PUBLISH_TWICE", duplicate)

    def unknown(r):
        token = r.admit("PEERS")
        r.unknown(token)
        denied(lambda: r.admit("CORE"), "UNKNOWN_WRITER")
        denied(lambda: acquire(r), "WRITERS_IN_FLIGHT")
        denied(
            lambda: r.complete(token, outcome="ROLLED_BACK", verified=True), "COMPLETION_BLOCKED"
        )

    test("UNKNOWN_REQUIRES_FUTURE_REPAIR", unknown)

    def unverified(r, value):
        token = r.admit("API")
        denied(
            lambda: r.complete(token, outcome="COMMITTED", verified=value), "COMPLETION_UNVERIFIED"
        )
        require(r.summary()["writers"] == 1 and r.summary()["generation"] == 0, "UNVERIFIED_DRAIN")

    test("FALSE_COMPLETION_REFUSED", lambda r: unverified(r, False))
    test("STRING_COMPLETION_REFUSED", lambda r: unverified(r, "true"))

    def outcomes(r):
        for mode in ("COMMITTED", "NOOP", "ROLLED_BACK"):
            r.complete(r.admit("PANEL"), outcome=mode, verified=True)
        require(r.summary()["generation"] == 3 and r.summary()["receipts"] == 3, "RECEIPTS")

    test("OUTCOME_RECEIPTS_ALL_INVALIDATE_OLD_GENERATION", outcomes)

    def drain(r):
        token = r.admit("CORE")
        denied(lambda: acquire(r), "WRITERS_IN_FLIGHT")
        nested = r.admit("TUN_HOOK")
        r.complete(nested, outcome="NOOP", verified=True)
        r.complete(token, outcome="COMMITTED", verified=True)
        acquire(r, 2)

    test("NO_PENDING_BARRIER_BEFORE_DRAIN", drain)

    def armed(r):
        acquire(r)
        denied(lambda: r.admit("CORE"), "FENCED")

    test("ARMED_BLOCKS_WRITER", armed)

    def expiry(r):
        token = acquire(r)
        r.fixture_clock[0] = 110
        denied(lambda: r.begin(token), "LEASE_TIME")
        denied(lambda: r.admit("CORE"), "FENCED")

    test("EXPIRED_LEASE_NEVER_UNFENCES", expiry)

    def duplicate_job(r):
        token = acquire(r)
        r.begin(token)
        denied(lambda: r.begin(token), "JOB_ALREADY_STARTED")
        denied(lambda: r.retire(token, outcome="UNUSED"), "RETIREMENT_UNVERIFIED")

    test("DISPATCHED_JOB_CANNOT_BE_UNUSED_OR_DISPATCHED_TWICE", duplicate_job)

    def unused(r):
        token = acquire(r)
        r.retire(token, outcome="UNUSED")
        acquire(r)
        denied(lambda: r.begin(token), "RECOVERY_TOKEN")

    test("UNUSED_RETIRE_INVALIDATES_OLD_EPOCH", unused)

    def restored(r):
        token = acquire(r)
        r.begin(token)
        denied(
            lambda: r.retire(token, outcome="RESTORED_ON", verified="true"), "RETIREMENT_UNVERIFIED"
        )
        r.retire(token, outcome="RESTORED_ON", verified=True)
        require(
            r.summary()["generation"] == 1 and r.summary()["phase"] == "IDLE", "RESTORED_RECORD"
        )
        denied(lambda: acquire(r, 0), "STALE_GENERATION")

    test("SYNTHETIC_RESTORED_RECEIPT_ADVANCES_GENERATION", restored)
    test(
        "BOOLEAN_EXPECTED_GENERATION_REFUSED",
        lambda r: denied(lambda: acquire(r, True), "LEASE_ARGUMENT"),
    )

    def bad_clock(r):
        r.clock_ns = lambda: True
        denied(lambda: acquire(r), "CLOCK_ARGUMENT")

    test("BOOLEAN_CLOCK_REFUSED", bad_clock)

    def backward(r):
        token = acquire(r)
        r.fixture_clock[0] = 9
        denied(lambda: r.begin(token), "LEASE_TIME")

    test("BACKWARD_CLOCK_REFUSED", backward)

    def bad_mode(r):
        (r.directory / "state.json").chmod(0o644)
        denied(r.summary, "PRIVATE_METADATA")

    test("STATE_PERMISSIONS_REFUSED", bad_mode)

    def symlink(r):
        (r.directory / "state.json").rename(r.directory / "kept.json")
        (r.directory / "state.json").symlink_to("kept.json")
        denied(r.summary, "STORE_IO")

    test("STATE_SYMLINK_REFUSED", symlink)

    def replaced(r):
        create(r.directory / "newlock", {})
        os.replace(r.directory / "newlock", r.directory / "lock")
        denied(r.summary, "LOCK_REPLACED")

    test("REPLACED_STABLE_LOCK_REFUSED", replaced)

    def duplicate_json(r):
        (r.directory / "state.json").write_bytes(b'{"schema":1,"schema":1}')
        denied(r.summary, "DUPLICATE_JSON_KEY")

    test("DUPLICATE_JSON_KEYS_REFUSED", duplicate_json)

    def size(r):
        (r.directory / "state.json").write_bytes(b" " * (M.MAX_BYTES + 1))
        denied(r.summary, "RECORD_LIMIT")

    test("OVERSIZED_RECORD_REFUSED", size)

    def staged(r):
        create(r.directory / "state.next", {"interrupted": True})
        denied(r.summary, "INTERRUPTED_COMMIT")
        denied(lambda: r.admit("CORE"), "INTERRUPTED_COMMIT")

    test("INTERRUPTED_STAGE_BLOCKS_WITHOUT_AUTOREPAIR", staged)

    def pre_replace(r):
        token = r.admit("CORE")
        original = M.os.replace

        def fail(*args, **kwargs):
            raise OSError("INJECTED")

        M.os.replace = fail
        try:
            denied(
                lambda: r.complete(token, outcome="COMMITTED", verified=True), "COMMIT_UNCERTAIN"
            )
        finally:
            M.os.replace = original
        require(len(raw_state(r)["writers"]) == 1 and raw_state(r)["generation"] == 0, "OLD_RECORD")
        denied(r.summary, "INTERRUPTED_COMMIT")

    test("PRE_REPLACE_FAILURE_PRESERVES_OLD_RECORD_AND_STAGE", pre_replace)

    def post_replace(r):
        token = r.admit("CORE")
        original = M.os.fsync

        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("INJECTED")
            original(fd)

        M.os.fsync = fail_directory
        try:
            denied(
                lambda: r.complete(token, outcome="COMMITTED", verified=True), "COMMIT_UNCERTAIN"
            )
        finally:
            M.os.fsync = original
        value = r.summary()
        require(
            value["writers"] == 0 and value["generation"] == 1 and value["receipts"] == 1,
            "COHERENT_RECEIPT",
        )
        denied(lambda: r.complete(token, outcome="COMMITTED", verified=True), "STALE_WRITER_TOKEN")

    test("POST_REPLACE_ACK_ERROR_HAS_COHERENT_RECEIPT", post_replace)

    def bounds(r):
        for _ in range(34):
            r.complete(r.admit("API"), outcome="NOOP", verified=True)
        require(r.summary()["receipts"] == 32 and r.summary()["generation"] == 34, "RECEIPT_BOUND")

    test("RECEIPT_HISTORY_IS_BOUNDED", bounds)

    def limits(r):
        for _ in range(32):
            r.admit("CORE")
        denied(lambda: r.admit("CORE"), "WRITER_LIMIT")
        denied(lambda: acquire(r), "WRITERS_IN_FLIGHT")

    test("WRITER_CAP_NEVER_EVICTS_LIVE_TICKET", limits)

    def concurrent(r):
        children = []
        try:
            children.append(spawn(r.directory, "admit"))
            children.append(spawn(r.directory, "admit"))
            details = [read_child(child, b"ADMITTED") for child in children]
            state = raw_state(r)
            require(
                len(state["writers"]) == 2 and len({w["id"] for w in state["writers"]}) == 2,
                "CONCURRENT_ADMISSION",
            )
            return {"child_rc": [d["child_rc"] for d in details], "fixed_output_matched": True}
        finally:
            for child in children:
                cleanup(child)

    test("REAL_PROCESSES_HAVE_DISTINCT_DURABLE_TICKETS", concurrent)

    def child_hook(r):
        parent = r.admit("CORE")
        child = spawn(r.directory, "hook")
        try:
            details = read_child(child, b"COMPLETED")
            denied(lambda: acquire(r, 1), "WRITERS_IN_FLIGHT")
            r.complete(parent, outcome="COMMITTED", verified=True)
            acquire(r, 2)
            return details
        finally:
            cleanup(child)

    test("REAL_CHILD_HOOK_FINISHES_WITH_PARENT_TICKET", child_hook)

    def child_exit(r):
        child = spawn(r.directory, "admit")
        try:
            details = read_child(child, b"ADMITTED")
            denied(lambda: acquire(r), "WRITERS_IN_FLIGHT")
            return details
        finally:
            cleanup(child)

    test("REAL_OWNER_EXIT_DOES_NOT_PRUNE_DURABLE_TICKET", child_exit)

    def wrong_owner(r):
        other = M.Registry(r.directory, boot_id=BOOT, expected_uid=os.getuid() + 1)
        denied(other.summary, "PRIVATE_METADATA")

    test("OWNER_POLICY_MISMATCH_REFUSED", wrong_owner)
    passed = sum(row["passed"] for row in rows)
    value = {
        "marker": "REGISTRY_FOUNDATION_RECORDED"
        if passed == len(rows)
        else "REGISTRY_FOUNDATION_PARTIAL",
        "scope": "DORMANT_PRODUCT_REGISTRY_USER_SANDBOX",
        "total": len(rows),
        "passed": passed,
        "cases": rows,
        "real_process_cases": 3,
        "real_process_cases_passed": sum(
            row["passed"] for row in rows if row["case"].startswith("REAL_")
        ),
        "children_started": CHILDREN_STARTED,
        "virtual_boot_and_clock": True,
        "installed_runtime_changed": False,
        "runtime_writer_fence_installed": False,
        "runtime_recovery_implemented": False,
        "active_faults_authorized": False,
        "network_requests": 0,
        "live_gateway_operations": 0,
    }
    create(NOTES / "registry-result.json", value)
    print(json.dumps(value))
    return 0 if passed == len(rows) else 3


if __name__ == "__main__":
    try:
        require(os.geteuid() != 0, "ORDINARY_OWNER_REQUIRED")
        M = load_library()
        if sys.argv[1:] == ["batch"]:
            raise SystemExit(batch())
        require(len(sys.argv) == 4 and sys.argv[1] == "_peer", "MODE_ARGUMENT")
        peer(Path(sys.argv[2]), sys.argv[3])
    except Exception as exc:
        print("STOP_REGISTRY_BATCH", type(exc).__name__)
        raise SystemExit(3) from None
