"""Verify listener loss and one-slot NFQUEUE overflow in an isolated network namespace."""

from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
import re
import socket
import stat
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

QUEUE = 201
PORT = 31085
PACKETS = 8
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


@contextmanager
def overflow_samples(sample):
    """Read a known one-slot backlog before and after a fixed loopback-only batch."""
    try:
        library = ctypes.CDLL("libnetfilter_queue.so.1")
    except OSError as exc:
        raise ValueError("libnetfilter_queue_unavailable") from exc
    ptr = ctypes.c_void_p
    callback_type = ctypes.CFUNCTYPE(ctypes.c_int, ptr, ptr, ptr, ptr)
    for name, result, args in (
        ("nfq_open", ptr, []), ("nfq_close", ctypes.c_int, [ptr]),
        ("nfq_create_queue", ptr, [ptr, ctypes.c_uint16, callback_type, ptr]),
        ("nfq_set_mode", ctypes.c_int, [ptr, ctypes.c_uint8, ctypes.c_uint32]),
        ("nfq_set_queue_maxlen", ctypes.c_int, [ptr, ctypes.c_uint32]),
        ("nfq_destroy_queue", ctypes.c_int, [ptr]),
    ):
        function = getattr(library, name)
        function.restype, function.argtypes = result, args
    handle = library.nfq_open()
    require(bool(handle), "overflow_nfq_open")
    queue = None
    rule_added = False
    callback = callback_type(lambda *_: 0)
    nft = "/usr/sbin/nft"
    try:
        queue = library.nfq_create_queue(handle, QUEUE, callback, None)
        require(bool(queue), "overflow_queue_create")
        require(library.nfq_set_mode(queue, 1, 0) >= 0, "overflow_copy_meta")
        require(library.nfq_set_queue_maxlen(queue, 1) >= 0, "overflow_queue_length")
        before = sample()
        require(before is not None and before.counters == (0, 0, 0), "overflow_baseline")

        subprocess.run(["/usr/sbin/ip", "link", "set", "lo", "up"], check=True, timeout=3)
        rule = (
            "table inet xgw_queue_trial {\n"
            "  chain trial {\n"
            "    type filter hook output priority filter; policy accept;\n"
            f"    ip daddr 127.0.0.1 udp dport {PORT} queue num {QUEUE}\n"
            "  }\n"
            "}\n"
        )
        subprocess.run([nft, "-f", "-"], input=rule, text=True, check=True, timeout=3)
        rule_added = True
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.settimeout(0.5)
            for _ in range(PACKETS):
                try:
                    sender.sendto(b"xgw-test", ("127.0.0.1", PORT))
                except OSError as exc:
                    if exc.errno not in (errno.EPERM, errno.ENOBUFS):
                        raise
        after = sample()
        require(after is not None and after.counters is not None
                and after.socket == before.socket, "overflow_same_owner")
        require(after.counters[:2] == (PACKETS - 1, 0), "overflow_expected_counters")
        yield before, after
    finally:
        if queue:
            library.nfq_destroy_queue(queue)
        library.nfq_close(handle)
        if rule_added:
            subprocess.run([nft, "delete", "table", "inet", "xgw_queue_trial"],
                           check=True, timeout=3)


def run(folder):
    sys.path.insert(0, str(folder / "src"))
    from xgw.config import Config
    from xgw.desync import event_socket, worker
    from xgw.watch.zapret2_control import card

    status = folder / "status.json"
    endpoint = folder / "events.sock"
    ending = threading.Event()
    service = threading.Thread(target=event_socket.serve, args=(endpoint, status, ending),
                               daemon=True)
    service.start()
    frame = b'{"version":1,"epoch":null,"after":0}\n'
    slot = worker.WorkerSlot()
    selected = Config()
    selected.zapret2.mode = "selective"
    selected.zapret2.queue_num = QUEUE
    selected_key = worker.policy_revision(selected.zapret2)

    def start_ms(lease):
        now = time.time()
        snapshot = {
            "daemon": True, "updated": now, "zapret2_policy_key": selected_key,
            "zapret2_reservation": asdict(lease), "zapret2_worker_events": slot.snapshot()[1],
            "capture": {"loaded": True},
            "zapret2": {"state": "active", "valid_until": now + 10},
        }
        return card(selected, snapshot, {"mode": "on"}, True, now=now)["evidence"][
            "worker_start_ms"
        ]

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
            lease = slot.reserve(worker.SELECTED_UNIT, QUEUE, policy_key=selected_key)
            require(start_ms(lease) is None, "startup_before_listener")
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
                elapsed = start_ms(lease)
                require(type(elapsed) is int and 0 <= elapsed <= 6_000, "startup_proof")
                slot.observe_owner(lease, True, sample)
                require(start_ms(lease) == elapsed, "startup_moved_after_repeat")
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
            require(start_ms(lease) is None, "startup_after_listener_loss")
            lost = read()
            require(lost["state"] == "snapshot" and lost["queue_counters"] is None
                    and lost["events"][-1]["phase"] == "owner_unverified"
                    and all(e["phase"] != "queue_drops" for e in lost["events"]),
                    "socket_listener_loss")
            slot.release(lease)
            print(json.dumps({"generation": count, "kernel_counters": [0, 0],
                              "event_socket": "ok", "worker_start_ms": elapsed,
                              "after_listener_loss": None}), flush=True)
        cfg = Config()
        cfg.zapret2.engine = "auto"
        key = worker.policy_revision(cfg.zapret2)
        lease = slot.reserve(worker.ENGINE_UNIT, QUEUE, policy_key=key)
        with overflow_samples(
            lambda: worker.owner_sample(lambda *_a, **_kw: str(os.getpid()), lease.unit, QUEUE),
        ) as (before, after):
            slot.observe_owner(lease, True, before)
            slot.observe_owner(lease, True, after)
            reply = read()
            event = reply["events"][-1]
            require(event["phase"] == "queue_drops" and event["generation"] == lease.generation
                    and event["overflow_delta"] == PACKETS - 1 and event["netlink_delta"] == 0,
                    "overflow_event")
            snapshot = {
                "daemon": True, "updated": time.time(), "zapret2_policy_key": key,
                "zapret2_reservation": asdict(lease), "zapret2_worker_events": slot.snapshot()[1],
                "capture": {"loaded": True, "nfqws2": {
                    "state": "active", "profile": "seqovl", "queue": QUEUE,
                }},
            }
            losses = card(cfg, snapshot, {"mode": "on"}, True)["counters"]
            require(losses["queue_overflow"] == PACKETS - 1 and losses["queue_netlink_dropped"] == 0
                    and losses["queue_dropped"] == PACKETS - 1, "overflow_panel_projection")
        require(not worker.occupied(QUEUE), "overflow_listener_still_present")
        slot.observe_owner(lease, False)
        snapshot["zapret2_worker_events"] = slot.snapshot()[1]
        require(read()["queue_counters"] is None and
                card(cfg, snapshot, {"mode": "on"}, True)["counters"]["queue_dropped"] is None,
                "overflow_cleared_after_close")
        slot.release(lease)
        print(json.dumps({"generation": lease.generation, "sent_attempts": PACKETS,
                          "overflow_delta": PACKETS - 1, "netlink_delta": 0,
                          "panel_projection": "ok", "after_listener_loss": None}), flush=True)
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
