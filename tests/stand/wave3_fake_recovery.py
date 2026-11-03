"""Finite fake-file-only recovery experiment. No systemd, network or XGW access."""

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

NOTES = Path.home() / "xgw-w3ac"
SANDBOX = NOTES / "sandbox"
MODES = {"normal", "crash", "none", "late", "fail_restore", "bad_nonce", "bad_baseline"}


def require(value):
    if not value:
        raise ValueError("FAKE_PROTOCOL_REFUSED")


def private(path, directory=False):
    info = path.lstat()
    require(
        (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
        and (directory or info.st_nlink == 1)
    )


def read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        private(path)
        info = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(info.st_mode)
            and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_nlink == 1
        )
        raw = stream.read(65537)
    require(len(raw) <= 65536)
    return json.loads(raw)


def create(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())


def save(root, value):
    create(root / "fake-state.next", value)
    os.replace(root / "fake-state.next", root / "fake-state.json")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextlib.contextmanager
def locked(root):
    fd = os.open(root / "fake.lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        private(root / "fake.lock")
        limit = time.monotonic() + 0.1
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(time.monotonic() < limit)
                time.sleep(0.005)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def driver(root):
    manifest = read(root / "fake-manifest.json")
    require(
        set(manifest) == {"nonce", "mode"}
        and manifest["mode"] in MODES
        and re.fullmatch(r"[0-9a-f]{32}", manifest["nonce"])
    )
    with locked(root):
        state = read(root / "fake-state.json")
        if (
            state["phase"] != "NEW"
            or state["nonce"] != manifest["nonce"]
            or state["value"] != "BASELINE"
        ):
            state["phase"] = "REFUSED"
            save(root, state)
            create(
                root / "fake-driver-result.json",
                {
                    "phase": "REFUSED",
                    "elapsed_ms": None,
                    "within_budget": None,
                    "timing_measured": False,
                    "baseline": state["value"] == "BASELINE",
                },
            )
            return
        now = time.monotonic_ns()
        state.update(
            phase="ARMED",
            armed_ns=now,
            dispatch_by=now + 1000000000,
            restore_at=now + 1500000000,
            hard_deadline=now + 4000000000,
        )
        save(root, state)
    while time.monotonic_ns() < state["restore_at"]:
        time.sleep(0.01)
    with locked(root):
        current = read(root / "fake-state.json")
        require(current["nonce"] == manifest["nonce"])
        if current["phase"] == "RUNNING":
            if manifest["mode"] == "fail_restore":
                current["phase"] = "FAILED"
            else:
                current.update(phase="FAKE_RESTORED", value="BASELINE")
        else:
            require(current["phase"] == "ARMED")
            current["phase"] = "EXPIRED_UNUSED"
        save(root, current)
        ended = time.monotonic_ns()
        create(
            root / "fake-driver-result.json",
            {
                "phase": current["phase"],
                "elapsed_ms": (ended - current["armed_ns"]) // 1000000,
                "within_budget": ended <= current["hard_deadline"],
                "timing_measured": True,
                "baseline": current["value"] == "BASELINE",
            },
        )


def controller(root, mode):
    child = subprocess.Popen(
        [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "_driver", str(root)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    create(root / "fake-launch.json", {"driver_popen_returned": child.pid > 0})
    limit = time.monotonic() + 3
    while True:
        with locked(root):
            state = read(root / "fake-state.json")
        if state["phase"] == "REFUSED":
            create(root / "fake-controller-event.json", {"fault_dispatched": False})
            return 3
        if state["phase"] == "ARMED":
            break
        require(time.monotonic() < limit)
        time.sleep(0.01)
    if mode == "late":
        time.sleep(2)
    dispatched = False
    if mode != "none":
        with locked(root):
            state = read(root / "fake-state.json")
            if state["phase"] == "ARMED" and time.monotonic_ns() < state["dispatch_by"]:
                state.update(phase="RUNNING", value="FAULT")
                save(root, state)
                dispatched = True
    create(root / "fake-controller-event.json", {"fault_dispatched": dispatched})
    if mode == "crash":
        os._exit(9)
    return 0


if __name__ == "__main__":
    try:
        require(os.geteuid() != 0 and len(sys.argv) in (3, 4))
        root = Path(sys.argv[2])
        require(root.parent == SANDBOX and re.fullmatch(r"case-[0-9]{2}", root.name))
        private(NOTES, True)
        private(SANDBOX, True)
        private(root, True)
        if sys.argv[1] == "_driver" and len(sys.argv) == 3:
            driver(root)
        else:
            require(sys.argv[1] == "_controller" and len(sys.argv) == 4 and sys.argv[3] in MODES)
            raise SystemExit(controller(root, sys.argv[3]))
    except Exception as exc:
        print("FAKE_PROTOCOL_STOP", type(exc).__name__)
        raise SystemExit(3) from None
