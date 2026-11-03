"""REC-C candidate: cooperative synthetic writers in a private user sandbox only.

No XGW, kernel networking, daemon, service or recovery integration is present.
"""

import contextlib
import fcntl
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path

NOTES = Path.home() / "xgw-w3z"
SANDBOX = NOTES / "sandbox"
MAX_RECORD = 16384
CHILDREN_STARTED = 0


class Refuse(Exception):
    pass


def require(value, code):
    if not value:
        raise Refuse(code)


def object_pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "DUPLICATE_KEY")
        result[key] = value
    return result


def directory(path):
    info = path.lstat()
    require(
        stat.S_ISDIR(info.st_mode)
        and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == 0o700,
        "SANDBOX_METADATA",
    )


def metadata(info):
    require(
        stat.S_ISREG(info.st_mode)
        and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == 0o600
        and info.st_nlink == 1,
        "RECORD_METADATA",
    )


def read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        metadata(os.fstat(stream.fileno()))
        raw = stream.read(MAX_RECORD + 1)
    require(len(raw) <= MAX_RECORD, "RECORD_LIMIT")
    return json.loads(raw, object_pairs_hook=object_pairs)


def create(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())


def atom(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is not None


def validate(state):
    require(
        isinstance(state, dict)
        and set(state)
        == {"version", "epoch", "generation", "phase", "owner", "acquired_ns", "deadline_ns"},
        "STATE_SCHEMA",
    )
    require(
        type(state["version"]) is int
        and state["version"] == 1
        and type(state["epoch"]) is int
        and state["epoch"] >= 0
        and atom(state["generation"]),
        "STATE_VALUES",
    )
    require(state["phase"] in ("IDLE", "ARMED", "RUNNING"), "STATE_PHASE")
    if state["phase"] == "IDLE":
        require(
            state["owner"] is None
            and state["deadline_ns"] is None
            and state["acquired_ns"] is None,
            "IDLE_STATE",
        )
    else:
        require(
            atom(state["owner"])
            and type(state["acquired_ns"]) is int
            and state["acquired_ns"] >= 0
            and type(state["deadline_ns"]) is int
            and 0 < state["deadline_ns"] - state["acquired_ns"] <= 45000000000
            and state["epoch"] > 0,
            "ACTIVE_STATE",
        )


class Store:
    def __init__(self, root):
        self.root = Path(root)
        directory(self.root)
        self.identity = read(self.root / "identity.json")
        require(
            isinstance(self.identity, list)
            and len(self.identity) == 2
            and all(type(v) is int for v in self.identity),
            "LOCK_IDENTITY_SCHEMA",
        )

    @classmethod
    def initialize(cls, root):
        root.mkdir(mode=0o700, exist_ok=False)
        create(root / "lock", {})
        info = (root / "lock").stat()
        create(root / "identity.json", [info.st_dev, info.st_ino])
        create(
            root / "state.json",
            {
                "version": 1,
                "epoch": 0,
                "generation": "g0",
                "phase": "IDLE",
                "owner": None,
                "acquired_ns": None,
                "deadline_ns": None,
            },
        )
        return cls(root)

    def lock_identity(self, fd):
        directory(self.root)
        current, path = os.fstat(fd), (self.root / "lock").lstat()
        metadata(current)
        metadata(path)
        require(
            [current.st_dev, current.st_ino] == self.identity
            and [path.st_dev, path.st_ino] == self.identity,
            "LOCK_INODE_CHANGED",
        )

    @contextlib.contextmanager
    def guard(self):
        fd = os.open(self.root / "lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            self.lock_identity(fd)
            deadline = time.monotonic() + 0.15
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    require(time.monotonic() < deadline, "LOCK_BUSY")
                    time.sleep(0.005)
            self.lock_identity(fd)
            state = read(self.root / "state.json")
            validate(state)
            yield fd, state
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def commit(self, fd, state):
        validate(state)
        self.lock_identity(fd)
        create(self.root / "state.part", state)
        self.lock_identity(fd)
        os.replace(self.root / "state.part", self.root / "state.json")
        directory_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def writer(self, expected, new):
        require(atom(expected) and atom(new) and expected != new, "GENERATION_ARGUMENT")
        with self.guard() as (fd, state):
            require(state["phase"] == "IDLE", "FENCED")
            require(state["generation"] == expected, "STALE_GENERATION")
            state["generation"] = new
            self.commit(fd, state)

    def acquire(self, owner, expected, now_ns, duration_ns=15000000000):
        require(atom(owner) and atom(expected), "OWNER_ARGUMENT")
        require(
            type(now_ns) is int
            and now_ns >= 0
            and type(duration_ns) is int
            and 0 < duration_ns <= 45000000000,
            "LEASE_BUDGET",
        )
        with self.guard() as (fd, state):
            require(state["phase"] == "IDLE", "FENCED")
            require(state["generation"] == expected, "STALE_GENERATION")
            state.update(
                epoch=state["epoch"] + 1,
                owner=owner,
                phase="ARMED",
                acquired_ns=now_ns,
                deadline_ns=now_ns + duration_ns,
            )
            self.commit(fd, state)
            return {"epoch": state["epoch"], "owner": owner, "generation": expected}

    def token(self, state, token):
        require(
            isinstance(token, dict)
            and set(token) == {"epoch", "owner", "generation"}
            and type(token["epoch"]) is int
            and token["epoch"] == state["epoch"]
            and token["owner"] == state["owner"]
            and token["generation"] == state["generation"]
            and state["phase"] != "IDLE",
            "STALE_OR_FOREIGN_TOKEN",
        )

    def begin_job(self, token, now_ns):
        require(type(now_ns) is int and now_ns >= 0, "CLOCK_ARGUMENT")
        with self.guard() as (fd, state):
            self.token(state, token)
            require(state["phase"] == "ARMED", "JOB_ALREADY_STARTED")
            require(now_ns >= state["acquired_ns"], "CLOCK_BEFORE_LEASE")
            require(now_ns < state["deadline_ns"], "LEASE_EXPIRED")
            state["phase"] = "RUNNING"
            self.commit(fd, state)

    def retire(self, token, *, reason, verified=False, observed_generation=None):
        with self.guard() as (fd, state):
            self.token(state, token)
            if reason == "UNUSED":
                require(state["phase"] == "ARMED", "JOB_WAS_DISPATCHED")
            else:
                require(
                    reason == "RESTORED_ON"
                    and state["phase"] == "RUNNING"
                    and verified is True
                    and observed_generation == state["generation"],
                    "RECOVERY_UNVERIFIED",
                )
            state.update(phase="IDLE", owner=None, acquired_ns=None, deadline_ns=None)
            self.commit(fd, state)


def peer(root, mode):
    # Internal protocol: fixed sandbox path and synthetic operations only.
    require(root.parent == SANDBOX and root.name.startswith("case-"), "PEER_SANDBOX")
    directory(NOTES)
    directory(SANDBOX)
    store = Store(root)
    if mode == "lease":
        store.acquire("ownerA", "g0", time.monotonic_ns())
        print("LEASE_SET")
        return
    if mode == "writer":
        try:
            store.writer("g0", "g1")
            print("COMMITTED")
        except Refuse as exc:
            require(str(exc) in ("FENCED", "STALE_GENERATION", "LOCK_BUSY"), "PEER_RESULT")
            print(str(exc))
        return
    require(mode == "hold", "PEER_MODE")
    with store.guard():
        create(root / "ready.json", {"ready": True})
        deadline = time.monotonic() + 3
        while not (root / "release.json").exists() and time.monotonic() < deadline:
            time.sleep(0.01)


def spawn_peer(root, mode):
    global CHILDREN_STARTED
    child = subprocess.Popen(
        [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "_peer", str(root), mode],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    CHILDREN_STARTED += 1
    return child


def stop_child(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=1)
    if child.stdout is not None:
        child.stdout.close()


def batch():
    directory(NOTES)
    require(not SANDBOX.exists() and not SANDBOX.is_symlink(), "SANDBOX_ALREADY_USED")
    create(NOTES / "fence-started.json", {"started": True})
    SANDBOX.mkdir(mode=0o700)
    results = []

    def test(name, action):
        root = SANDBOX / ("case-" + str(len(results) + 1).zfill(2))
        row = {"case": name, "passed": False}
        try:
            details = action(Store.initialize(root))
            row["passed"] = True
            if isinstance(details, dict):
                row["details"] = details
        except Exception as exc:
            row["error_class"] = type(exc).__name__
            if isinstance(exc, Refuse):
                row["reason"] = str(exc)
            if hasattr(exc, "safe_details"):
                row["details"] = exc.safe_details
        results.append(row)
        create(
            NOTES / "fence-progress.part",
            {
                "final": False,
                "completed": len(results),
                "cases": results,
                "scope": "SANDBOX_CHECKPOINT_NOT_FINAL",
            },
        )
        os.replace(NOTES / "fence-progress.part", NOTES / "fence-progress.json")

    def denied(fn, code):
        try:
            fn()
        except Refuse as exc:
            require(str(exc) == code, "WRONG_REJECTION")
            return
        raise Refuse("UNEXPECTED_ADMISSION")

    def read_state(store):
        return read(store.root / "state.json")

    test(
        "WRITER_COMMIT",
        lambda s: (
            s.writer("g0", "g1"),
            require(read_state(s)["generation"] == "g1", "WRITER_NOT_COMMITTED"),
        ),
    )
    test("STALE_WRITER", lambda s: denied(lambda: s.writer("old", "g1"), "STALE_GENERATION"))

    def fenced(s):
        s.acquire("ownerA", "g0", 1)
        denied(lambda: s.writer("g0", "g1"), "FENCED")

    test("WRITER_BLOCKED_DURING_LEASE", fenced)

    def double_owner(s):
        s.acquire("ownerA", "g0", 1)
        denied(lambda: s.acquire("ownerB", "g0", 1), "FENCED")

    test("SECOND_OWNER_BLOCKED", double_owner)

    def expired(s):
        token = s.acquire("ownerA", "g0", 1, duration_ns=10)
        denied(lambda: s.begin_job(token, 11), "LEASE_EXPIRED")
        denied(lambda: s.writer("g0", "g1"), "FENCED")

    test("EXPIRY_NEVER_UNFENCES_WRITER_OR_STARTS_JOB", expired)

    def foreign(s):
        token = s.acquire("ownerA", "g0", 1)
        token["owner"] = "ownerB"
        denied(lambda: s.begin_job(token, 2), "STALE_OR_FOREIGN_TOKEN")

    test("FOREIGN_TOKEN", foreign)

    def retired(s):
        token = s.acquire("ownerA", "g0", 1)
        s.retire(token, reason="UNUSED")
        denied(lambda: s.begin_job(token, 2), "STALE_OR_FOREIGN_TOKEN")

    test("LATE_JOB_AFTER_RETIRE", retired)

    def epoch(s):
        old = s.acquire("ownerA", "g0", 1)
        s.retire(old, reason="UNUSED")
        new = s.acquire("ownerA", "g0", 2)
        require(new["epoch"] > old["epoch"], "EPOCH_NOT_INCREMENTED")
        denied(lambda: s.begin_job(old, 3), "STALE_OR_FOREIGN_TOKEN")

    test("REACQUIRE_INVALIDATES_OLD_EPOCH", epoch)

    def started(s):
        token = s.acquire("ownerA", "g0", 1)
        s.begin_job(token, 2)
        denied(lambda: s.begin_job(token, 3), "JOB_ALREADY_STARTED")
        denied(lambda: s.retire(token, reason="UNUSED"), "JOB_WAS_DISPATCHED")

    test("NO_DUPLICATE_JOB_OR_UNUSED_AFTER_DISPATCH", started)

    def unverified(s):
        token = s.acquire("ownerA", "g0", 1)
        s.begin_job(token, 2)
        denied(lambda: s.retire(token, reason="RESTORED_ON"), "RECOVERY_UNVERIFIED")
        denied(lambda: s.writer("g0", "g1"), "FENCED")

    test("UNVERIFIED_RECOVERY_KEEPS_FENCE", unverified)

    def restored(s):
        token = s.acquire("ownerA", "g0", 1)
        s.begin_job(token, 2)
        s.retire(token, reason="RESTORED_ON", verified=True, observed_generation="g0")
        s.writer("g0", "g1")

    test("SYNTHETIC_VERIFIED_RETIRE_THEN_WRITER", restored)
    test(
        "INVALID_DURATION",
        lambda s: denied(lambda: s.acquire("a", "g0", 1, 45000000001), "LEASE_BUDGET"),
    )
    test(
        "BOOLEAN_CLOCK_REJECTED",
        lambda s: denied(lambda: s.acquire("a", "g0", True), "LEASE_BUDGET"),
    )

    def metadata_case(s):
        (s.root / "state.json").chmod(0o666)
        denied(lambda: s.writer("g0", "g1"), "RECORD_METADATA")

    test("WRITABLE_STATE_REJECTED", metadata_case)

    def replacement(s):
        with s.guard() as (fd, state):
            os.replace(s.root / "lock", s.root / "old-synthetic-lock")
            create(s.root / "lock", {})
            denied(lambda: s.commit(fd, state), "LOCK_INODE_CHANGED")

    test("LOCK_INODE_REPLACEMENT_REJECTED", replacement)

    def concurrent(s):
        children = [spawn_peer(s.root, "writer"), spawn_peer(s.root, "writer")]
        try:
            outputs = [p.communicate(timeout=4)[0].decode().strip() for p in children]
            details = {
                "committed": outputs.count("COMMITTED"),
                "stale": outputs.count("STALE_GENERATION"),
                "busy": outputs.count("LOCK_BUSY"),
                "fenced": outputs.count("FENCED"),
                "other": sum(
                    o not in ("COMMITTED", "STALE_GENERATION", "LOCK_BUSY", "FENCED")
                    for o in outputs
                ),
                "child_rc": [p.returncode for p in children],
            }
            if not all(p.returncode == 0 for p in children) or sorted(outputs) != [
                "COMMITTED",
                "STALE_GENERATION",
            ]:
                exc = Refuse("CONCURRENT_RESULT")
                exc.safe_details = details
                raise exc
            require(read_state(s)["generation"] == "g1", "LOST_UPDATE")
            return details
        finally:
            for child in children:
                stop_child(child)

    test("TWO_REAL_PROCESSES_ONE_COMMIT", concurrent)

    def dead_holder(s):
        child = spawn_peer(s.root, "hold")
        try:
            deadline = time.monotonic() + 2
            while not (s.root / "ready.json").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            require((s.root / "ready.json").exists(), "PEER_NOT_READY")
            denied(lambda: s.writer("g0", "g1"), "LOCK_BUSY")
            stop_child(child)
            s.writer("g0", "g1")
            require(read_state(s)["generation"] == "g1", "LOCK_NOT_RELEASED")
        finally:
            stop_child(child)

    test("OWN_CHILD_EXIT_RELEASES_OS_LOCK", dead_holder)

    def departed_owner(s):
        child = spawn_peer(s.root, "lease")
        try:
            output = child.communicate(timeout=4)[0].decode().strip()
            require(child.returncode == 0 and output == "LEASE_SET", "LEASE_PEER_EXIT")
            denied(lambda: s.writer("g0", "g1"), "FENCED")
        finally:
            stop_child(child)

    test("LEASE_PERSISTS_AFTER_OWNER_PROCESS_EXIT", departed_owner)

    def backward(s):
        token = s.acquire("ownerA", "g0", 10)
        denied(lambda: s.begin_job(token, 9), "CLOCK_BEFORE_LEASE")

    test("CLOCK_BEFORE_LEASE_REJECTED", backward)

    passed = sum(row["passed"] for row in results)
    value = {
        "marker": "WRITER_FENCE_DRY_RECORDED"
        if passed == len(results)
        else "WRITER_FENCE_DRY_PARTIAL",
        "total": len(results),
        "passed": passed,
        "cases": results,
        "scope": "COOPERATIVE_SYNTHETIC_WRITERS_USER_SANDBOX",
        "runtime_writer_fence_installed": False,
        "runtime_recovery_implemented": False,
        "active_faults_authorized": False,
        "network_requests": 0,
        "live_gateway_operations": 0,
        "real_process_cases": 3,
        "real_process_cases_passed": sum(
            row["passed"]
            for row in results
            if row["case"]
            in (
                "TWO_REAL_PROCESSES_ONE_COMMIT",
                "OWN_CHILD_EXIT_RELEASES_OS_LOCK",
                "LEASE_PERSISTS_AFTER_OWNER_PROCESS_EXIT",
            )
        ),
        "children_started": CHILDREN_STARTED,
        "virtual_lease_boundaries": True,
    }
    create(NOTES / "fence-result.json", value)
    print(json.dumps(value))
    return 0 if passed == len(results) else 3


if __name__ == "__main__":
    try:
        require(os.geteuid() != 0, "ORDINARY_OWNER_REQUIRED")
        if sys.argv[1:] == ["batch"]:
            raise SystemExit(batch())
        require(len(sys.argv) == 4 and sys.argv[1] == "_peer", "MODE_NOT_ALLOWED")
        peer(Path(sys.argv[2]), sys.argv[3])
    except Exception as exc:
        print("STOP_FENCE_DRY", str(exc) if isinstance(exc, Refuse) else type(exc).__name__)
        raise SystemExit(3) from None
