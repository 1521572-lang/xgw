"""One NFQUEUE worker slot shared by XGW's two runtime adapters."""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

from ..net import cmd
from . import schema

QUEUE_STATE = Path("/proc/net/netfilter/nfnetlink_queue")
NETLINK_STATE = Path("/proc/net/netlink")
PROC = Path("/proc")
ENGINE_UNIT = "xgw-nfqws2.service"
SELECTED_UNIT = "xgw-zapret2.service"
STOPPED = {"inactive", "failed", "unknown"}
EVENT_LIMIT = 64


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
        self._epoch = uuid.uuid4().hex
        self._seq = 0
        self._verified = False
        self._policy_key: str | None = None
        self._events: deque[dict] = deque(maxlen=EVENT_LIMIT)

    def reserve(self, unit: str, queue: int, *, policy_key: str | None = None) -> Lease:
        with self._lock:
            if self.lease is not None:
                raise ValueError("worker_handoff_pending")
            self._generation += 1
            self.lease = Lease(self._generation, unit, queue)
            self._verified = False
            self._policy_key = policy_key
            self._event("reserved", self.lease)
            return self.lease

    def observe_owner(self, lease: Lease, verified: bool) -> bool:
        with self._lock:
            if self.lease is not lease:
                return False
            if self._verified != verified:
                self._verified = verified
                self._event("owner_verified" if verified else "owner_unverified", lease)
            return verified

    def release(self, lease: Lease | None) -> None:
        with self._lock:
            if lease is not None and self.lease is lease:
                self._event("released", lease)
                self.lease = None

    def _event(self, phase: str, lease: Lease) -> None:
        self._seq += 1
        self._events.append({"seq": self._seq, "at": time.time(), "phase": phase,
                             "policy_key": self._policy_key, **asdict(lease)})

    def snapshot(self) -> tuple[Lease | None, dict]:
        with self._lock:
            return self.lease, {
                "version": 1, "epoch": self._epoch, "last_seq": self._seq,
                "discarded": self._seq - len(self._events),
                "events": [dict(event) for event in self._events],
            }


def policy_revision(settings) -> str | None:
    try:
        return schema.fingerprint(schema.migrate(vars(settings)))
    except schema.PolicyError:
        return None


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
