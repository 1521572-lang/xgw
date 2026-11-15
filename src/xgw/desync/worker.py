"""One NFQUEUE worker slot shared by XGW's two runtime adapters."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from ..net import cmd

QUEUE_STATE = Path("/proc/net/netfilter/nfnetlink_queue")
NETLINK_STATE = Path("/proc/net/netlink")
PROC = Path("/proc")
ENGINE_UNIT = "xgw-nfqws2.service"
SELECTED_UNIT = "xgw-zapret2.service"
STOPPED = {"inactive", "failed", "unknown"}


@dataclass(frozen=True)
class Lease:
    generation: int
    unit: str
    queue: int


class WorkerSlot:
    def __init__(self) -> None:
        self.lease: Lease | None = None
        self._generation = 0
        self._lock = threading.Lock()

    def reserve(self, unit: str, queue: int) -> Lease:
        with self._lock:
            if self.lease is not None:
                raise ValueError("worker_handoff_pending")
            self._generation += 1
            self.lease = Lease(self._generation, unit, queue)
            return self.lease

    def release(self, lease: Lease | None) -> None:
        with self._lock:
            if self.lease is lease:
                self.lease = None


def occupied(queue: int, path: Path = QUEUE_STATE) -> bool:
    try:
        return any(fields and fields[0] == str(queue)
                   for fields in map(str.split, path.read_text().splitlines()))
    except FileNotFoundError:
        # The kernel creates this file when NFQUEUE is available.
        return False


def require_stopped(runner: cmd.Runner, unit: str) -> None:
    state = runner(["systemctl", "is-active", unit], check=False, timeout=5).strip()
    if state not in STOPPED:
        raise ValueError("worker_unit_busy")


def verify_owner(runner: cmd.Runner, unit: str, queue: int) -> bool:
    """Match the queue's netlink port ID to a socket held by this unit's MainPID.

    NETLINK_NETFILTER port IDs identify sockets and are not necessarily PIDs.
    Missing or unreadable evidence cannot confirm ownership.
    """
    pid = runner(["systemctl", "show", unit, "-p", "MainPID", "--value"],
                 check=False, timeout=1).strip()
    if not pid.isascii() or not pid.isdecimal() or int(pid) <= 0:
        return False
    try:
        peers = {row[1] for row in map(str.split, QUEUE_STATE.read_text().splitlines())
                 if len(row) >= 2 and row[0] == str(queue)}
        if len(peers) != 1:
            return False
        sockets = {f"socket:[{row[9]}]"
                   for row in map(str.split, NETLINK_STATE.read_text().splitlines())
                   if len(row) >= 10 and row[1] == "12" and row[2] in peers and row[9] != "0"}
        if not sockets:
            return False
        for fd in (PROC / pid / "fd").iterdir():
            try:
                if str(fd.readlink()) in sockets:
                    return True
            except FileNotFoundError:
                continue  # The worker closed an unrelated fd while listing.
    except OSError:
        return False
    return False
