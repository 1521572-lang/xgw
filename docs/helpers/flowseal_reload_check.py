"""Exercise list reloads in a private network namespace with interception disabled."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import stat
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

BINARY = Path("/opt/xgw/zapret2/1.0.7/nfqws2")
VERSION = re.compile(rb"^github version v?1\.0\.7 \(038c97e[0-9a-f]*\) lua_compat_ver \d+$",
                     re.MULTILINE)
BASE = b"one.example.test\ntwo.example.test\n"
UPDATE = BASE + b"three.example.test\n"
ALLOWED = set(UPDATE.splitlines())
LOCAL = b"two.example.test\n"
UPSTREAM = b"three.example.test\n"
TRUNCATED_GZIP = b"\x1f\x8b\x08\x00"
HEARTBEAT = "XGW_RELOAD_TICK"
HUP = "HUP received ! Lists will be reloaded."
WORKER_ID = 65534
TIMER = (
    'local n=0; timer_set("xgw-check",function(name) '
    'n=n+1; print("XGW_RELOAD_TICK"); if n>=40 then timer_del(name) end end, 250)'
)


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def error_label(error: Exception) -> str:
    if isinstance(error, ValueError) and re.fullmatch(r"[a-z0-9_]+", str(error)):
        return str(error)
    return type(error).__name__


def staged_write(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def check_candidate(path: Path) -> bytes:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("candidate_not_regular")
    with path.open("rb") as stream:
        value = stream.read(8193)
    domains = value.splitlines()
    if len(value) > 8192 or not domains or not set(domains) <= ALLOWED:
        raise ValueError("candidate_scope")
    return value


def fixture(path: Path, data: bytes) -> None:
    staged_write(path, data)
    os.chown(path, -1, WORKER_ID)
    path.chmod(0o640)


def allow_worker_traversal(path: Path) -> None:
    os.chown(path, -1, WORKER_ID)
    path.chmod(0o710)


class Worker:
    def __init__(self, folder: Path):
        self.folder = folder
        self.folder.mkdir(mode=0o700)
        allow_worker_traversal(folder)
        self.log = folder / "worker.log"
        self.positive = folder / "selected.txt"
        self.local = folder / "local-exclude.txt"
        self.upstream = folder / "upstream-exclude.txt"
        self.ipset = folder / "selected.ipset"
        for path, payload in ((self.positive, BASE), (self.local, LOCAL),
                              (self.upstream, UPSTREAM), (self.ipset, b"192.0.2.1/32\n")):
            fixture(path, payload)

    def argv(self, positive: Path) -> list[str]:
        return [str(BINARY), "--debug=1", "--intercept=0", "--qnum=201",
                f"--uid={WORKER_ID}:{WORKER_ID}", "--filter-tcp=443", f"--hostlist={positive}",
                f"--hostlist-exclude={self.local}", f"--hostlist-exclude={self.upstream}",
                f"--ipset={self.ipset}"]

    def __enter__(self) -> Worker:
        with self.log.open("xb") as output:
            self.proc = subprocess.Popen(
                [*self.argv(self.positive), "--lua-init=" + TIMER],
                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            )
        try:
            self.wait_log(0, lambda text: HEARTBEAT in text.splitlines(), "startup")
        except (OSError, ValueError):
            self.stop()
            raise
        return self

    def __exit__(self, *_exc) -> None:
        self.stop()

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=2)

    def wait_log(self, offset: int, done: Callable[[str], bool], phase: str) -> str:
        until = time.monotonic() + 3
        while True:
            with self.log.open("rb") as stream:
                stream.seek(offset)
                data = stream.read(65537)
            require(len(data) <= 65536, f"{phase}_log_limit")
            lines = data.decode("utf-8", errors="replace")
            if done(lines):
                return lines
            require(self.proc.poll() is None and time.monotonic() < until, phase)
            time.sleep(0.025)

    def signal_reload(self) -> int:
        require(self.proc.poll() is None, "worker_not_running")
        offset = self.log.stat().st_size
        self.proc.send_signal(signal.SIGHUP)
        return offset

    def reload(self) -> str:
        offset = self.signal_reload()
        log = self.wait_log(
            offset, lambda text: text.partition(HUP)[2].splitlines().count(HEARTBEAT) >= 2,
            "reload",
        )
        require(self.proc.poll() is None, "worker_exited_on_reload")
        return log.partition(HUP)[2]

    def publish(self, candidate: Path) -> None:
        check_candidate(candidate)
        subprocess.run([*self.argv(candidate), "--dry-run"], check=True, timeout=3,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        candidate.replace(self.positive)

    def check_loaded(self, log: str, count: int) -> None:
        for path, expected in ((self.positive, count), (self.local, 1), (self.upstream, 1)):
            require(f"Loaded {expected} hosts from {path}\n" in log, "reload_host_count")
        require(self.local.read_bytes() == LOCAL and self.upstream.read_bytes() == UPSTREAM,
                "exclusions_changed")


def valid_and_rollback(worker: Worker) -> dict:
    stage = worker.folder / "candidate"
    for content, count in ((UPDATE, 3), (UPDATE, 3), (BASE, 2)):
        fixture(stage, content)
        worker.publish(stage)
        worker.check_loaded(worker.reload(), count)
        require(worker.positive.read_bytes() == content, "revision_mismatch")
    return {"loads": [3, 3, 2], "rollback": True, "worker_survived": True}


def blocked_staging(worker: Worker) -> dict:
    candidate = worker.folder / "candidate"
    fixture(worker.folder / "interrupted", UPDATE[:-9])
    outcomes = []
    for content in (None, TRUNCATED_GZIP, b"", UPDATE[:-9], BASE + b"outside.example.test\n"):
        if content is not None:
            fixture(candidate, content)
        try:
            worker.publish(candidate)
        except FileNotFoundError:
            outcomes.append("missing")
        except ValueError as exc:
            require(str(exc) == "candidate_scope", "unexpected_rejection")
            outcomes.append("rejected")
        else:
            raise ValueError("invalid_candidate_published")
        candidate.unlink(missing_ok=True)
        require(worker.positive.read_bytes() == BASE, "active_changed")
    worker.check_loaded(worker.reload(), 2)
    return {"staging": outcomes, "loads": [2], "worker_survived": True}


def missing_active(worker: Worker) -> dict:
    saved = worker.folder / "saved"
    worker.positive.replace(saved)
    log = worker.reload()
    require(f"cannot access hostlist file '{worker.positive}'. in-memory content remains unchanged."
            in log, "missing_file_retain_marker")
    saved.replace(worker.positive)
    worker.check_loaded(worker.reload(), 2)
    return {"retained_on_missing": True, "restored": True, "worker_survived": True}


def empty_active(worker: Worker) -> dict:
    stage = worker.folder / "intentionally-empty"
    fixture(stage, b"")
    stage.replace(worker.positive)
    worker.check_loaded(worker.reload(), 0)
    return {"loaded_hosts": 0, "worker_survived": True}


def corrupt_active(worker: Worker, *, ipset: bool) -> dict:
    stage = worker.folder / "intentionally-corrupt"
    fixture(stage, TRUNCATED_GZIP)
    stage.replace(worker.ipset if ipset else worker.positive)
    offset = worker.signal_reload()
    rc = worker.proc.wait(timeout=3)
    with worker.log.open("rb") as stream:
        stream.seek(offset)
        log = stream.read(65537)
    require(len(log) <= 65536, "fatal_log_limit")
    fatal = b"ipset load failed." if ipset else b"hostlists load failed."
    require(rc == 200 and fatal in log and b"zlib decompression failed" in log, "fatal_reload")
    return {"reload_exit": rc, "fatal_reload": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--host-netns", type=int, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    out = args.out
    try:
        info = out.lstat()
        require(os.geteuid() == 0 and out.parent == Path("/run")
                and out.name.startswith("xgw-list-reload.")
                and stat.S_ISDIR(info.st_mode) and info.st_uid == 0
                and stat.S_IMODE(info.st_mode) == 0o700, "private_root_dir_required")
        devices = {line.partition(":")[0].strip() for line in
                   Path("/proc/net/dev").read_text().splitlines()[2:]}
        require(Path("/proc/self/ns/net").stat().st_ino != args.host_netns
                and devices == {"lo"}, "isolation_required")
        version = subprocess.check_output([str(BINARY), "--version"],
                                          stderr=subprocess.STDOUT, timeout=5)
        require(VERSION.search(version) is not None, "engine_mismatch")
        allow_worker_traversal(out)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print("FLOWSEAL_RELOAD_SETUP_FAILED", error_label(exc))
        return 2
    cases = (
        ("valid_repeat_rollback", valid_and_rollback),
        ("blocked_staging", blocked_staging),
        ("missing_active", missing_active),
        ("empty_active", empty_active),
        ("corrupt_active_hostlist", lambda worker: corrupt_active(worker, ipset=False)),
        ("corrupt_active_ipset", lambda worker: corrupt_active(worker, ipset=True)),
    )
    passed = 0
    for name, action in cases:
        try:
            with Worker(out / name) as worker:
                result = action(worker)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            result = {"ok": False, "error": error_label(exc)}
        else:
            result["ok"] = True
            passed += 1
        print(json.dumps({"case": name, **result}), flush=True)
    print(f"FLOWSEAL_RELOAD_CASES {passed}/{len(cases)}")
    return int(passed != len(cases))


if __name__ == "__main__":
    raise SystemExit(main())
