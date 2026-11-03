"""REC-C admission lifetime candidate. User sandbox, no product integration."""

import contextlib
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

NOTES = Path.home() / "xgw-w3aa"
SANDBOX = NOTES / "sandbox"
LEDGER_SHA = "be2f1558bae1882ae5bbf2d52de937aa2133ddfa66417e59f27fd37479e2f36b"
ROLES = {"CAPTURE", "PANEL", "PEERS", "CORE", "API", "TUN_HOOK", "LIFECYCLE"}
SAFE_REASONS = {
    "UNKNOWN_WRITER",
    "STALE_TICKET",
    "STATE_CONFLICT",
    "ORDINARY_OWNER_REQUIRED",
    "COMPLETION_UNVERIFIED",
    "LEDGER_SIZE",
    "LOCK_BUSY",
    "LEDGER_SHA",
    "PEER_RC",
    "SUCCESS_STATE",
    "TICKET_LIMIT",
    "TICKET_ID",
    "TICKET_SERIAL",
    "PARTIAL_LOST",
    "RECORD_LIMIT",
    "LEASE_ARGUMENT",
    "FENCED",
    "STALE_GENERATION",
    "UNADMITTED_CALLBACK",
    "GENERATION_NOT_PUBLISHED",
    "WRONG_REJECTION",
    "PEER_OUTPUT",
    "TICKET_ITEM",
    "LEDGER_OWNER",
    "LOCK_INODE_CHANGED",
    "MODE_REJECTED",
    "LEDGER_MODE",
    "CALLBACK_UNVERIFIED",
    "TOKEN_SCHEMA",
    "ROLE_REJECTED",
    "TICKET_SCHEMA",
    "DUPLICATE_KEY",
    "TICKET_PHASE",
    "PEER_PATH",
    "STATE_SCHEMA",
    "ABANDONED_TICKET_LOST",
    "WRITERS_IN_FLIGHT",
    "TICKET_IDENTITY",
    "GENERATION_SCHEMA",
    "TICKET_LOST",
    "RECORD_METADATA",
    "TICKET_VERSION",
}
L = None
CHILDREN_STARTED = 0


def require(value, reason):
    if not value:
        raise ValueError(reason)


def load_ledger():
    path = NOTES / "ledger.py"
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid(), "LEDGER_OWNER")
    require(info.st_mode & 0o7777 == 0o600 and info.st_nlink == 1, "LEDGER_MODE")
    require(info.st_size <= 1048576, "LEDGER_SIZE")
    require(hashlib.sha256(path.read_bytes()).hexdigest() == LEDGER_SHA, "LEDGER_SHA")
    spec = importlib.util.spec_from_file_location("frozen_z_ledger", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Gate:
    def __init__(self, root):
        self.root = Path(root)
        self.store = L.Store(root)

    @classmethod
    def initialize(cls, root):
        L.Store.initialize(root)
        L.create(root / "tickets.json", {"version": 1, "serial": 0, "tickets": []})
        return cls(root)

    def read(self):
        data = L.read(self.root / "tickets.json")
        require(
            isinstance(data, dict) and set(data) == {"version", "serial", "tickets"},
            "TICKET_SCHEMA",
        )
        require(type(data["version"]) is int and data["version"] == 1, "TICKET_VERSION")
        require(type(data["serial"]) is int and data["serial"] >= 0, "TICKET_SERIAL")
        require(isinstance(data["tickets"], list) and len(data["tickets"]) <= 32, "TICKET_LIMIT")
        ids = set()
        for item in data["tickets"]:
            require(isinstance(item, dict) and set(item) == {"id", "role", "phase"}, "TICKET_ITEM")
            require(type(item["id"]) is int and 0 < item["id"] <= data["serial"], "TICKET_ID")
            require(item["id"] not in ids and item["role"] in ROLES, "TICKET_IDENTITY")
            require(item["phase"] in ("LIVE", "COMMITTING", "UNKNOWN"), "TICKET_PHASE")
            ids.add(item["id"])
        return data

    def save(self, fd, data):
        self.store.lock_identity(fd)
        L.create(self.root / "tickets.part", data)
        self.store.lock_identity(fd)
        os.replace(self.root / "tickets.part", self.root / "tickets.json")
        directory_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def admit(self, role):
        require(role in ROLES, "ROLE_REJECTED")
        with self.store.guard() as (fd, state):
            require(state["phase"] == "IDLE", "FENCED")
            data = self.read()
            require(all(t["phase"] == "LIVE" for t in data["tickets"]), "UNKNOWN_WRITER")
            require(len(data["tickets"]) < 32, "TICKET_LIMIT")
            data["serial"] += 1
            token = {"id": data["serial"], "role": role}
            data["tickets"].append({**token, "phase": "LIVE"})
            self.save(fd, data)
            return token

    def find(self, data, token):
        require(isinstance(token, dict) and set(token) == {"id", "role"}, "TOKEN_SCHEMA")
        require(type(token["id"]) is int and token["role"] in ROLES, "TOKEN_SCHEMA")
        matches = [
            t for t in data["tickets"] if t["id"] == token["id"] and t["role"] == token["role"]
        ]
        require(len(matches) == 1, "STALE_TICKET")
        return matches[0]

    def complete(self, token, *, verified):
        with self.store.guard() as (fd, state):
            require(state["phase"] == "IDLE", "STATE_CONFLICT")
            data = self.read()
            ticket = self.find(data, token)
            require(ticket["phase"] == "LIVE" and verified is True, "COMPLETION_UNVERIFIED")
            require(re.fullmatch(r"g[0-9]+", state["generation"]) is not None, "GENERATION_SCHEMA")
            ticket["phase"] = "COMMITTING"
            self.save(fd, data)
            # Publish BEFORE removal. A crash or failed cleanup leaves a blocking ticket.
            state["generation"] = "g" + str(int(state["generation"][1:]) + 1)
            self.store.commit(fd, state)
            data["tickets"].remove(ticket)
            self.save(fd, data)

    def unknown(self, token):
        with self.store.guard() as (fd, state):
            require(state["phase"] == "IDLE", "STATE_CONFLICT")
            data = self.read()
            self.find(data, token)["phase"] = "UNKNOWN"
            self.save(fd, data)

    def lease(self, expected="g0", now_ns=10):
        require(type(now_ns) is int and now_ns >= 0 and L.atom(expected), "LEASE_ARGUMENT")
        with self.store.guard() as (fd, state):
            require(state["phase"] == "IDLE", "FENCED")
            data = self.read()
            require(not data["tickets"], "WRITERS_IN_FLIGHT")
            require(state["generation"] == expected, "STALE_GENERATION")
            state.update(
                phase="ARMED",
                epoch=state["epoch"] + 1,
                owner="dryOwner",
                acquired_ns=now_ns,
                deadline_ns=now_ns + 15000000000,
            )
            self.store.commit(fd, state)
            return {"epoch": state["epoch"], "owner": state["owner"], "generation": expected}

    def operate(self, role, mutation, verifier):
        token = self.admit(role)
        try:
            mutation()
            require(verifier() is True, "CALLBACK_UNVERIFIED")
            self.complete(token, verified=True)
        except Exception:
            # Best effort only; the previously persisted LIVE ticket also blocks a lease.
            with contextlib.suppress(Exception):
                self.unknown(token)
            raise


def denied(action, reason):
    try:
        action()
    except (ValueError, L.Refuse) as exc:
        require(str(exc) == reason, "WRONG_REJECTION")
    else:
        raise ValueError("REJECTION_MISSING")


def atomic_note(name, value):
    temporary = NOTES / (name + ".part")
    L.create(temporary, value)
    os.replace(temporary, NOTES / name)


def peer(root, mode):
    require(root.parent == SANDBOX and re.fullmatch(r"case-[0-9]{2}", root.name), "PEER_PATH")
    L.directory(NOTES)
    L.directory(SANDBOX)
    gate = Gate(root)
    if mode == "hook":
        token = gate.admit("TUN_HOOK")
        gate.complete(token, verified=True)
        print("HOOK_COMPLETED")
    elif mode == "lease":
        denied(lambda: gate.lease(), "WRITERS_IN_FLIGHT")
        print("LEASE_REFUSED")
    elif mode == "abandon":
        gate.admit("CORE")
        print("TICKET_PERSISTED")
    else:
        raise ValueError("PEER_MODE")


def run_peer(gate, mode):
    global CHILDREN_STARTED
    child = subprocess.Popen(
        [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "_peer", str(gate.root), mode],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    CHILDREN_STARTED += 1
    try:
        output = child.communicate(timeout=4)[0]
        require(child.returncode == 0, "PEER_RC")
        expected = {
            "hook": b"HOOK_COMPLETED",
            "lease": b"LEASE_REFUSED",
            "abandon": b"TICKET_PERSISTED",
        }[mode]
        require(output.strip() == expected, "PEER_OUTPUT")
        return {"child_rc": child.returncode, "fixed_output_matched": True}
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=1)


def batch():
    L.directory(NOTES)
    L.create(NOTES / "tickets-started.json", {"started": True})
    SANDBOX.mkdir(mode=0o700, exist_ok=False)
    results = []

    def test(name, action):
        gate = Gate.initialize(SANDBOX / f"case-{len(results) + 1:02d}")
        try:
            details = action(gate)
            row = {"case": name, "passed": True}
            if isinstance(details, dict):
                row["details"] = details
        except Exception as exc:
            row = {
                "case": name,
                "passed": False,
                "error_class": type(exc).__name__,
                "reason": str(exc)
                if type(exc) in (ValueError, L.Refuse) and str(exc) in SAFE_REASONS
                else "CASE_FAILED",
            }
        results.append(row)
        atomic_note(
            "tickets-progress.json", {"final": False, "completed": len(results), "cases": results}
        )

    def success(g):
        called = []
        g.operate("CAPTURE", lambda: called.append(1), lambda: True)
        require(called == [1] and not g.read()["tickets"], "SUCCESS_STATE")
        g.lease("g1")

    test("SUCCESS_PUBLISHES_BEFORE_DRAIN", success)

    def callback_lease(g):
        g.operate("CAPTURE", lambda: denied(lambda: g.lease(), "WRITERS_IN_FLIGHT"), lambda: True)

    test("LEASE_REFUSED_INSIDE_CALLBACK", callback_lease)

    def hook(g):
        parent = g.admit("CORE")
        details = run_peer(g, "hook")
        denied(lambda: g.lease("g1"), "WRITERS_IN_FLIGHT")
        g.complete(parent, verified=True)
        g.lease("g2")
        return details

    test("REAL_CHILD_HOOK_ADMITTED_WITH_PARENT_TICKET", hook)

    def competing(g):
        details = []
        g.operate("PEERS", lambda: details.append(run_peer(g, "lease")), lambda: True)
        g.lease("g1")
        return details[0]

    test("REAL_CHILD_LEASE_REFUSED_DURING_CALLBACK", competing)

    def abandoned(g):
        details = run_peer(g, "abandon")
        denied(lambda: g.lease(), "WRITERS_IN_FLIGHT")
        require(len(g.read()["tickets"]) == 1, "ABANDONED_TICKET_LOST")
        return details

    test("REAL_OWNER_EXIT_DOES_NOT_DRAIN_TICKET", abandoned)

    def armed(g):
        g.lease()
        called = []
        denied(lambda: g.operate("CAPTURE", lambda: called.append(1), lambda: True), "FENCED")
        require(not called, "UNADMITTED_CALLBACK")

    test("ARMED_PREVENTS_CALLBACK_ENTRY", armed)

    def preadmitted(g):
        token = g.admit("PANEL")
        denied(lambda: g.lease(), "WRITERS_IN_FLIGHT")
        g.complete(token, verified=True)
        g.lease("g1")

    test("DRAIN_REQUIRED_BEFORE_ARM", preadmitted)

    def no_pending(g):
        first = g.admit("CORE")
        denied(lambda: g.lease(), "WRITERS_IN_FLIGHT")
        second = g.admit("TUN_HOOK")
        g.complete(second, verified=True)
        g.complete(first, verified=True)
        g.lease("g2")

    test("FAILED_ACQUIRE_NEVER_SETS_PENDING_BARRIER", no_pending)

    def mutation_error(g):
        touched = []

        def mutate():
            touched.append(1)
            raise ValueError("INJECTED")

        denied(lambda: g.operate("PEERS", mutate, lambda: True), "INJECTED")
        require(touched == [1] and g.read()["tickets"][0]["phase"] == "UNKNOWN", "PARTIAL_LOST")
        denied(lambda: g.lease(), "WRITERS_IN_FLIGHT")
        denied(lambda: g.admit("PANEL"), "UNKNOWN_WRITER")

    test("PARTIAL_CALLBACK_ERROR_RETAINS_UNKNOWN", mutation_error)

    def bad_verify(g, result):
        denied(lambda: g.operate("API", lambda: None, lambda: result), "CALLBACK_UNVERIFIED")
        denied(lambda: g.lease(), "WRITERS_IN_FLIGHT")

    test("FALSE_VERIFIER_NEVER_DRAINS", lambda g: bad_verify(g, False))
    test("STRING_VERIFIER_NEVER_DRAINS", lambda g: bad_verify(g, "true"))

    def verify_error(g):
        def verifier():
            raise ValueError("VERIFY_INJECTED")

        denied(lambda: g.operate("API", lambda: None, verifier), "VERIFY_INJECTED")
        denied(lambda: g.lease(), "WRITERS_IN_FLIGHT")

    test("VERIFIER_ERROR_RETAINS_TICKET", verify_error)

    def duplicate(g):
        token = g.admit("CAPTURE")
        g.complete(token, verified=True)
        denied(lambda: g.complete(token, verified=True), "STALE_TICKET")

    test("DUPLICATE_COMPLETION_REJECTED", duplicate)

    def wrong_role(g):
        token = g.admit("CORE")
        denied(lambda: g.complete({**token, "role": "API"}, verified=True), "STALE_TICKET")
        denied(lambda: g.lease(), "WRITERS_IN_FLIGHT")

    test("CROSS_ROLE_TOKEN_REJECTED", wrong_role)

    def unknown(g):
        token = g.admit("CORE")
        g.unknown(token)
        denied(lambda: g.complete(token, verified=True), "COMPLETION_UNVERIFIED")
        denied(lambda: g.admit("CAPTURE"), "UNKNOWN_WRITER")

    test("UNKNOWN_HAS_NO_AUTOMATIC_RETIREMENT", unknown)

    def generations(g):
        a, b = g.admit("PANEL"), g.admit("API")
        g.complete(b, verified=True)
        g.complete(a, verified=True)
        denied(lambda: g.lease("g0"), "STALE_GENERATION")
        g.lease("g2")

    test("OUT_OF_ORDER_COMPLETIONS_ADVANCE_GENERATION", generations)

    def role_limit(g):
        denied(lambda: g.admit("OTHER"), "ROLE_REJECTED")
        for _ in range(32):
            g.admit("CORE")
        denied(lambda: g.admit("CORE"), "TICKET_LIMIT")
        denied(lambda: g.lease(), "WRITERS_IN_FLIGHT")

    test("ROLE_AND_INFLIGHT_LIMITS_REJECTED", role_limit)

    def malformed(g):
        L.create(g.root / "bad.json", {"version": 1, "serial": True, "tickets": []})
        os.replace(g.root / "bad.json", g.root / "tickets.json")
        denied(lambda: g.admit("CORE"), "TICKET_SERIAL")
        denied(lambda: g.lease(), "TICKET_SERIAL")

    test("MALFORMED_REGISTRY_BLOCKS_ADMISSION_AND_LEASE", malformed)

    def expired(g):
        g.lease()
        with g.store.guard() as (fd, state):
            state.update(acquired_ns=0, deadline_ns=1)
            g.store.commit(fd, state)
        denied(lambda: g.admit("CORE"), "FENCED")

    test("EXPIRED_LOGICAL_LEASE_STILL_BLOCKS_WRITERS", expired)

    def failed_publish(g):
        token = g.admit("PEERS")
        L.create(g.root / "state.part", {"interrupted": True})
        try:
            g.complete(token, verified=True)
        except FileExistsError:
            pass
        else:
            raise ValueError("PUBLICATION_SHOULD_FAIL")
        denied(lambda: g.lease(), "WRITERS_IN_FLIGHT")
        require(len(g.read()["tickets"]) == 1, "TICKET_LOST")

    test("FAILED_GENERATION_PUBLICATION_NEVER_DRAINS", failed_publish)

    def failed_cleanup(g):
        token = g.admit("CORE")
        save = g.save
        calls = []

        def fail_second(fd, data):
            calls.append(1)
            if len(calls) == 2:
                raise OSError("INJECTED_CLEANUP")
            save(fd, data)

        g.save = fail_second
        try:
            g.complete(token, verified=True)
        except OSError:
            pass
        else:
            raise ValueError("CLEANUP_SHOULD_FAIL")
        require(L.read(g.root / "state.json")["generation"] == "g1", "GENERATION_NOT_PUBLISHED")
        denied(lambda: g.lease("g1"), "WRITERS_IN_FLIGHT")
        denied(lambda: g.complete(token, verified=True), "COMPLETION_UNVERIFIED")

    test("PUBLISHED_GENERATION_WITH_FAILED_CLEANUP_STAYS_BLOCKED", failed_cleanup)

    def restart(g):
        g.admit("LIFECYCLE")
        other = Gate(g.root)
        denied(lambda: other.lease(), "WRITERS_IN_FLIGHT")

    test("REOPEN_NEVER_PRUNES_ORPHAN_TICKET", restart)
    passed = sum(row["passed"] for row in results)
    process_ids = {
        "REAL_CHILD_HOOK_ADMITTED_WITH_PARENT_TICKET",
        "REAL_CHILD_LEASE_REFUSED_DURING_CALLBACK",
        "REAL_OWNER_EXIT_DOES_NOT_DRAIN_TICKET",
    }
    value = {
        "marker": "WRITER_TICKETS_DRY_RECORDED"
        if passed == len(results)
        else "WRITER_TICKETS_DRY_PARTIAL",
        "scope": "COOPERATIVE_ADMISSION_LIFETIME_USER_SANDBOX",
        "total": len(results),
        "passed": passed,
        "cases": results,
        "real_process_cases": 3,
        "real_process_cases_passed": sum(
            row["passed"] for row in results if row["case"] in process_ids
        ),
        "children_started": CHILDREN_STARTED,
        "virtual_lease_boundaries": True,
        "runtime_writer_fence_installed": False,
        "runtime_recovery_implemented": False,
        "active_faults_authorized": False,
        "network_requests": 0,
        "live_gateway_operations": 0,
    }
    L.create(NOTES / "tickets-result.json", value)
    print(json.dumps(value))
    return 0 if passed == len(results) else 3


if __name__ == "__main__":
    try:
        require(os.geteuid() != 0, "ORDINARY_OWNER_REQUIRED")
        L = load_ledger()
        if sys.argv[1:] == ["batch"]:
            raise SystemExit(batch())
        require(len(sys.argv) == 4 and sys.argv[1] == "_peer", "MODE_REJECTED")
        peer(Path(sys.argv[2]), sys.argv[3])
    except Exception as exc:
        print("STOP_TICKETS_DRY", type(exc).__name__)
        raise SystemExit(3) from None
