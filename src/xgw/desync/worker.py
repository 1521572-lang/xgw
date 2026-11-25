"""One NFQUEUE worker slot shared by XGW's two runtime adapters."""

from __future__ import annotations

import json
import re
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
COUNTER_MAX = (1 << 32) - 1
QUEUE_SOURCE = "proc_nfnetlink_queue"
QUEUE_FRESH_SECONDS = 90
COUNTER_FIELDS = ("unit", "queue", "generation", "source", "at", "overflow", "netlink")
RUN_FIELD = "XGW_WORKER_RUN"
FATAL_MESSAGES = {
    "hostlists load failed. this is fatal.": "hostlist_reload_failed",
    "ipset load failed. this is fatal.": "ipset_reload_failed",
    "LUA PANIC: THIS IS FATAL. DYING.": "lua_panic",
}
FAULT_REASONS = frozenset((*FATAL_MESSAGES.values(), "lua_error_observed"))
JOURNAL_FILTER = r"^(hostlists load failed\.|ipset load failed\.|LUA (PANIC|ERROR):)"


@dataclass(frozen=True)
class Lease:
    generation: int
    unit: str
    queue: int


@dataclass(frozen=True)
class QueueOwner:
    socket: str
    counters: tuple[int, int, int] | None  # queue drops, netlink drops, packet sequence


class WorkerSlot:
    def __init__(self) -> None:
        self.lease: Lease | None = None
        self._generation = 0
        self._lock = threading.Lock()
        self._epoch = uuid.uuid4().hex
        self._seq = 0
        self._verified = False
        self._reserved_ns = 0
        self._startup_ms: int | None = None
        self._policy_key: str | None = None
        self._fault_checked = False
        self._queue_sample: QueueOwner | None = None
        self._queue_at = 0.0
        self._queue_series = 0
        self._events: deque[dict] = deque(maxlen=EVENT_LIMIT)

    def reserve(self, unit: str, queue: int, *, policy_key: str | None = None) -> Lease:
        with self._lock:
            if self.lease is not None:
                raise ValueError("worker_handoff_pending")
            self._generation += 1
            self.lease = Lease(self._generation, unit, queue)
            self._verified = False
            self._reserved_ns = time.monotonic_ns()
            self._startup_ms = None
            self._policy_key = policy_key
            self._fault_checked = False
            self._event("reserved", self.lease)
            return self.lease

    def observe_owner(self, lease: Lease, verified: bool, owner: QueueOwner | None = None) -> bool:
        with self._lock:
            if self.lease is not lease:
                return False
            if self._verified != verified:
                self._verified = verified
                if verified and self._startup_ms is None:
                    self._startup_ms = (time.monotonic_ns() - self._reserved_ns) // 1_000_000
                self._event("owner_verified" if verified else "owner_unverified", lease)
            previous = self._queue_sample
            self._queue_sample = None
            if not verified or owner is None or owner.counters is None:
                return verified
            self._queue_sample = owner
            self._queue_at = time.time()
            if (previous is not None and previous.socket == owner.socket
                    and previous.counters is not None
                    and all(a <= b for a, b in zip(previous.counters, owner.counters, strict=True))):
                overflow = owner.counters[0] - previous.counters[0]
                netlink = owner.counters[1] - previous.counters[1]
                if overflow or netlink:
                    self._event("queue_drops", lease, overflow_delta=overflow, netlink_delta=netlink)
            else:
                self._queue_series += 1
            return verified

    def log_property(self, lease: Lease) -> str:
        return f"LogExtraFields={self._log_field(lease)}"

    def _log_field(self, lease: Lease) -> str:
        return f"{RUN_FIELD}={self._epoch}-{lease.generation}"

    def observe_stopped(self, lease: Lease | None, runner: cmd.Runner) -> None:
        """Record advertised fault markers once after a worker disappears."""
        with self._lock:
            if lease is None or self.lease is not lease or self._fault_checked:
                return
            self._fault_checked = True
        reason = read_fault(runner, lease.unit, self._log_field(lease))
        if reason is not None:
            with self._lock:
                if self.lease is lease and not self._verified:
                    self._event("worker_fault", lease, reason=reason)

    def release(self, lease: Lease | None) -> None:
        with self._lock:
            if lease is not None and self.lease is lease:
                self._event("released", lease)
                self.lease = None
                self._queue_sample = None

    def _event(self, phase: str, lease: Lease, **details: int | str) -> None:
        self._seq += 1
        self._events.append({"seq": self._seq, "at": time.time(), "phase": phase,
                             "policy_key": self._policy_key, **asdict(lease), **details})

    def snapshot(self) -> tuple[Lease | None, dict]:
        with self._lock:
            startup = None
            if self.lease is not None and self._verified and self._startup_ms is not None:
                startup = {**asdict(self.lease), "policy_key": self._policy_key,
                           "elapsed_ms": self._startup_ms}
            counters = None
            if self.lease is not None and self._queue_sample is not None:
                overflow, netlink, packet_ids = self._queue_sample.counters
                counters = {
                    **asdict(self.lease), "source": QUEUE_SOURCE, "at": self._queue_at,
                    "overflow": overflow, "netlink": netlink, "packet_ids": packet_ids,
                }
            return self.lease, {
                "version": 1, "epoch": self._epoch, "last_seq": self._seq,
                "discarded": self._seq - len(self._events),
                "events": [dict(event) for event in self._events],
                "queue_counters": counters, "queue_series": self._queue_series, "startup": startup,
            }


def policy_revision(settings) -> str | None:
    try:
        return schema.fingerprint(schema.migrate(vars(settings)))
    except schema.PolicyError:
        return None


def read_fault(runner: cmd.Runner, unit: str, log_field: str) -> str | None:
    """Read a small journal projection for this exact worker launch."""
    try:
        rows = runner([
            "journalctl", "--boot", "--quiet", "--no-pager", "--lines=8", "--output=json",
            "--output-fields=MESSAGE", "--grep=" + JOURNAL_FILTER, "_SYSTEMD_UNIT=" + unit,
            log_field,
        ], check=False, timeout=1)
        if not isinstance(rows, str):
            return None
        lua_observed = False
        for line in rows.splitlines():
            row = json.loads(line)
            message = row.get("MESSAGE") if isinstance(row, dict) else None
            if not isinstance(message, str):
                continue
            if reason := FATAL_MESSAGES.get(message.strip()):
                return reason
            lua_observed |= message.startswith("LUA ERROR: ")
        return "lua_error_observed" if lua_observed else None
    except (cmd.CommandError, OSError, ValueError, RecursionError):
        return None


def current_queue_counters(journal: object, now: float) -> dict | None:
    """Project only a fresh sample belonging to the journal's verified owner."""
    if not isinstance(journal, dict):
        return None
    version = journal.get("version")
    if type(version) is not int or version != 1:
        return None
    value, events = journal.get("queue_counters"), journal.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= EVENT_LIMIT:
        return None
    last = events[-1]
    if (not isinstance(value, dict) or any(key not in value for key in COUNTER_FIELDS)
            or not isinstance(last, dict) or last.get("phase") not in ("owner_verified", "queue_drops")
            or any(value[key] != last.get(key) for key in ("unit", "queue", "generation"))):
        return None
    at = value["at"]
    if (value["source"] != QUEUE_SOURCE or type(at) not in (float, int)
            or not now - QUEUE_FRESH_SECONDS <= at <= now
            or value["unit"] not in (ENGINE_UNIT, SELECTED_UNIT)
            or type(value["queue"]) is not int or not 1 <= value["queue"] <= 65535
            or type(value["generation"]) is not int or not 1 <= value["generation"] < 1 << 63
            or not all(type(value[key]) is int and 0 <= value[key] <= COUNTER_MAX
                       for key in ("overflow", "netlink"))):
        return None
    return {key: value[key] for key in COUNTER_FIELDS}


def monitor_queue_sample(value: object, now: float) -> dict | None:
    if not isinstance(value, dict):
        return None
    epoch, series, at = value.get("epoch"), value.get("series"), value.get("at")
    if (not isinstance(epoch, str) or re.fullmatch("[0-9a-f]{32}", epoch) is None
            or type(series) is not int or not 1 <= series < 1 << 63
            or type(at) not in (int, float) or not 0 < at <= now
            or now - at > QUEUE_FRESH_SECONDS
            or not all(type(value.get(key)) is int and 0 <= value[key] <= COUNTER_MAX
                       for key in ("overflow", "netlink"))):
        return None
    result = {key: value[key] for key in ("epoch", "series", "at", "overflow", "netlink")}
    packet_ids = value.get("packet_ids")
    if type(packet_ids) is int and 0 <= packet_ids <= COUNTER_MAX:
        result["packet_ids"] = packet_ids
    return result


def startup_duration(journal: object, reservation: object, unit: str, queue: int | None,
                     policy_key: str) -> int | None:
    """Project a duration only for the current worker identity and revision."""
    if not isinstance(journal, dict) or not isinstance(reservation, dict):
        return None
    version, sample = journal.get("version"), journal.get("startup")
    if type(version) is not int or version != 1 or not isinstance(sample, dict):
        return None
    generation = reservation.get("generation")
    elapsed = sample.get("elapsed_ms")
    if (sample.get("policy_key") == policy_key
            and queue is not None and type(generation) is int and generation > 0
            and all(type(row.get(field)) is int for field in ("queue", "generation")
                    for row in (sample, reservation))
            and all(sample.get(field) == reservation.get(field) == expected
                    for field, expected in (("unit", unit), ("queue", queue),
                                            ("generation", generation)))
            and type(elapsed) is int and 0 <= elapsed <= 3_600_000):
        return elapsed
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


def _queue_counters(row: list[str]) -> tuple[int, int, int] | None:
    # Linux nfqnl_seq_show: queue_dropped, queue_user_dropped, id_sequence.
    # Leave unfamiliar or truncated rows usable for owner verification only.
    if len(row) == 9 and row[-1] == "1":
        overflow, netlink, sequence = row[5:8]
        if all(len(v) <= 10 and v.isascii() and v.isdecimal() and int(v) <= COUNTER_MAX
               for v in (overflow, netlink, sequence)):
            return int(overflow), int(netlink), int(sequence)
    return None


def owner_sample(runner: cmd.Runner, unit: str, queue: int) -> QueueOwner | None:
    """Match the queue's netlink port ID to a socket held by this unit's MainPID.

    NETLINK_NETFILTER port IDs identify sockets and are not necessarily PIDs.
    Missing or unreadable evidence cannot confirm ownership.
    """
    pid = runner(["systemctl", "show", unit, "-p", "MainPID", "--value"],
                 check=False, timeout=1).strip()
    if not pid.isascii() or not pid.isdecimal() or int(pid) <= 0:
        return None
    try:
        queues = [row for row in map(str.split, QUEUE_STATE.read_text().splitlines())
                  if len(row) >= 2 and row[0] == str(queue)]
        if len(queues) != 1:
            return None
        queue_row, = queues
        peer = queue_row[1]
        sockets = {f"socket:[{row[9]}]"
                   for row in map(str.split, NETLINK_STATE.read_text().splitlines())
                   if len(row) >= 10 and row[1] == "12" and row[2] == peer and row[9] != "0"}
        if not sockets:
            return None
        for fd in (PROC / pid / "fd").iterdir():
            try:
                link = str(fd.readlink())
                if link in sockets:
                    return QueueOwner(link, _queue_counters(queue_row))
            except FileNotFoundError:
                continue  # The worker closed an unrelated fd while listing.
    except OSError:
        return None
    return None


def verify_owner(runner: cmd.Runner, unit: str, queue: int) -> bool:
    return owner_sample(runner, unit, queue) is not None
