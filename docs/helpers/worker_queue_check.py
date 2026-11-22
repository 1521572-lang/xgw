"""Read counters from a disposable nfqws2 listener in an isolated network namespace."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

QUEUE = 201
BINARY = Path("/opt/xgw/zapret2/1.0.7/nfqws2")
VERSION = re.compile(rb"^github version v?1\.0\.7 \(038c97e[0-9a-f]*\) lua_compat_ver \d+$",
                     re.MULTILINE)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def stop(proc):
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


def run(folder):
    sys.path.insert(0, str(folder / "src"))
    from xgw.desync import event_socket, worker

    status = folder / "status.json"
    endpoint = folder / "events.sock"
    ending = threading.Event()
    service = threading.Thread(target=event_socket.serve, args=(endpoint, status, ending),
                               daemon=True)
    service.start()
    frame = b'{"version":1,"epoch":null,"after":0}\n'
    slot = worker.WorkerSlot()

    def read():
        snapshot = {"daemon": True, "updated": time.time(),
                    "zapret2_worker_events": slot.snapshot()[1]}
        status.write_text(json.dumps(snapshot), encoding="utf-8")
        deadline = time.monotonic() + 3
        while True:
            try:
                return event_socket.request(endpoint, frame)
            except (FileNotFoundError, ConnectionRefusedError):
                require(time.monotonic() < deadline, "socket_unavailable")
                time.sleep(0.025)

    try:
        for count in (1, 2):
            lease = slot.reserve(worker.ENGINE_UNIT, QUEUE)
            with (folder / f"worker-{count}.log").open("xb") as log:
                proc = subprocess.Popen(
                    [str(BINARY), "--intercept=1", f"--qnum={QUEUE}", "--uid=65534:65534",
                     "--filter-tcp=443"],
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                )
            try:
                deadline = time.monotonic() + 5
                while True:
                    sample = worker.owner_sample(lambda *_a, **_kw: str(proc.pid),
                                                 lease.unit, QUEUE)
                    if sample is not None:
                        break
                    require(proc.poll() is None and time.monotonic() < deadline, "listener_start")
                    time.sleep(0.05)
                require(sample.counters == (0, 0, 0), "kernel_counter_layout")
                slot.observe_owner(lease, True, sample)
                initial = read()
                counters = initial.get("queue_counters")
                require(initial["state"] == "snapshot" and isinstance(counters, dict)
                        and counters["generation"] == count and counters["overflow"] == 0
                        and counters["netlink"] == 0 and counters["source"] == worker.QUEUE_SOURCE,
                        "socket_counters")
            finally:
                stop(proc)
            absent = worker.owner_sample(lambda *_a, **_kw: str(proc.pid), lease.unit, QUEUE)
            require(absent is None and not worker.occupied(QUEUE), "listener_still_present")
            slot.observe_owner(lease, False)
            lost = read()
            require(lost["state"] == "snapshot" and lost["queue_counters"] is None
                    and lost["events"][-1]["phase"] == "owner_unverified"
                    and all(e["phase"] != "queue_drops" for e in lost["events"]),
                    "socket_listener_loss")
            slot.release(lease)
            print(json.dumps({"generation": count, "kernel_counters": [0, 0],
                              "event_socket": "ok", "after_listener_loss": None}), flush=True)
    finally:
        ending.set()
        service.join(timeout=3)
    require(not service.is_alive(), "socket_shutdown")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--host-netns", type=int, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        folder = args.out
        info = folder.lstat()
        require(os.geteuid() == 0 and folder.parent == Path("/run")
                and folder.name.startswith("xgw-worker-diag.")
                and stat.S_ISDIR(info.st_mode) and info.st_uid == 0
                and stat.S_IMODE(info.st_mode) == 0o700, "private_root_dir_required")
        devices = {line.partition(":")[0].strip() for line in
                   Path("/proc/net/dev").read_text().splitlines()[2:]}
        require(Path("/proc/self/ns/net").stat().st_ino != args.host_netns
                and devices == {"lo"}, "isolation_required")
        require(VERSION.search(subprocess.check_output([str(BINARY), "--version"],
                                                       stderr=subprocess.STDOUT, timeout=5))
                is not None, "engine_mismatch")
        run(folder)
    except (ImportError, OSError, ValueError, subprocess.SubprocessError) as exc:
        reason = str(exc) if isinstance(exc, ValueError) and re.fullmatch(
            r"[a-z0-9_]+", str(exc)
        ) else type(exc).__name__
        print("WORKER_QUEUE_LAB_FAILED", reason)
        return 2
    print("WORKER_QUEUE_LAB_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
