"""Local, read-only cursor protocol for the zapret2 worker journal."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import signal
import socket
import stat
import struct
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import worker

VERSION = 1
MAX_CLIENTS = 8
REQUESTS_PER_SECOND = 16
DEADLINE_SECONDS = 2
MAX_REQUEST = 512
MAX_RESPONSE = 24 * 1024
MAX_STATUS = 4 * 1024 * 1024
MAX_SEQUENCE = (1 << 63) - 1
FRESH_SECONDS = 90
EPOCH = re.compile(r"[0-9a-f]{32}")
POLICY_KEY = re.compile(r"[0-9a-f]{64}")
PHASES = ("reserved", "owner_verified", "owner_unverified", "released")
UNITS = (worker.ENGINE_UNIT, worker.SELECTED_UNIT)
EVENT_FIELDS = ("seq", "at", "phase", "unit", "queue", "generation", "policy_key")
UCRED = struct.Struct("iII")


def _integer(value: object, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _epoch(value: object) -> bool:
    return isinstance(value, str) and EPOCH.fullmatch(value) is not None


def parse_request(frame: bytes) -> tuple[str | None, int]:
    if len(frame) > MAX_REQUEST or not frame.endswith(b"\n") or frame.count(b"\n") != 1:
        raise ValueError("invalid_frame")
    data = json.loads(frame.decode("utf-8"))
    if (not isinstance(data, dict) or set(data) != {"version", "epoch", "after"}
            or not _integer(data["version"], VERSION, VERSION)
            or not _integer(data["after"], 0, MAX_SEQUENCE)
            or not (_epoch(data["epoch"]) or (data["epoch"] is None and data["after"] == 0))):
        raise ValueError("invalid_cursor")
    return data["epoch"], data["after"]


def _response(state: str, **fields) -> dict:
    return {"version": VERSION, "state": state, "events": [], **fields}


def _valid_event(event: object, seq: int) -> bool:
    if not isinstance(event, dict) or any(key not in event for key in EVENT_FIELDS):
        return False
    revision = event["policy_key"]
    valid_revision = revision is None or (
        isinstance(revision, str) and POLICY_KEY.fullmatch(revision) is not None)
    return (_integer(event["seq"], seq, seq) and type(event["at"]) in (float, int)
            and 0 <= event["at"] < 1e11 and event["phase"] in PHASES
            and event["unit"] in UNITS and _integer(event["queue"], 1, 65535)
            and _integer(event["generation"], 1, MAX_SEQUENCE)
            and valid_revision)


def cursor_response(snapshot: object, epoch: str | None, after: int, now: float) -> dict:
    if not isinstance(snapshot, dict) or snapshot.get("daemon") is not True:
        return _response("unavailable")
    updated = snapshot.get("updated")
    if not (type(updated) in (int, float) and now - FRESH_SECONDS <= updated <= now):
        return _response("unavailable")
    journal = snapshot.get("zapret2_worker_events")
    if not isinstance(journal, dict) or not _integer(journal.get("version"), VERSION, VERSION):
        return _response("unavailable")
    current, last = journal.get("epoch"), journal.get("last_seq")
    discarded, events = journal.get("discarded"), journal.get("events")
    if (not _epoch(current) or not _integer(last, 0, MAX_SEQUENCE)
            or not isinstance(events, list) or not _integer(discarded, 0, last)
            or len(events) != min(last, worker.EVENT_LIMIT) or discarded + len(events) != last
            or any(not _valid_event(e, i) for i, e in enumerate(events, discarded + 1))):
        return _response("unavailable")
    positions = {"epoch": current, "last_seq": last, "discarded": discarded}
    if epoch is not None and epoch == current and after > last:
        return _response("invalid_cursor", **positions)
    if epoch != current:
        state, after = ("snapshot" if epoch is None else "reset"), 0
    else:
        state = "gap" if after < discarded else "ok"
    return _response(state, **positions, events=[{key: e[key] for key in EVENT_FIELDS}
                                                for e in events if e["seq"] > after])


def read_status(path: Path) -> object:
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("invalid_status")
        raw = source.read(MAX_STATUS + 1)
    if len(raw) > MAX_STATUS:
        raise ValueError("status_too_large")
    return json.loads(raw)


def _peer_uid(connection: socket.socket) -> int:
    credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, UCRED.size)
    return UCRED.unpack(credentials)[1]


def _set_deadline(connection: socket.socket, deadline: float) -> None:
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError
    connection.settimeout(left)


def _read_frame(connection: socket.socket, deadline: float, limit: int) -> bytes:
    data = bytearray()
    while len(data) < limit:
        _set_deadline(connection, deadline)
        segment = connection.recv(limit - len(data))
        if not segment:
            break
        data.extend(segment)
        if b"\n" in segment:
            if not data.endswith(b"\n") or data.count(b"\n") != 1:
                raise ValueError("trailing_data")
            return bytes(data)
    raise ValueError("incomplete_frame")


def _handle(connection: socket.socket, deadline: float, path: Path,
            slots: threading.BoundedSemaphore) -> None:
    try:
        with connection:
            try:
                epoch, after = parse_request(_read_frame(connection, deadline, MAX_REQUEST))
            except (ValueError, RecursionError):
                reply = _response("invalid_request")
            else:
                try:
                    reply = cursor_response(read_status(path), epoch, after, time.time())
                except (OSError, ValueError, RecursionError):
                    reply = _response("unavailable")
            frame = json.dumps(reply, separators=(",", ":"), allow_nan=False).encode() + b"\n"
            if len(frame) > MAX_RESPONSE:
                return
            _set_deadline(connection, deadline)
            connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
            connection.sendall(frame)
    except OSError:
        pass
    finally:
        slots.release()


def _dispatch(listener: socket.socket, status: Path, stop: threading.Event) -> None:
    slots = threading.BoundedSemaphore(MAX_CLIENTS)
    admitted: deque[float] = deque(maxlen=REQUESTS_PER_SECOND)
    uid = os.geteuid()
    with ThreadPoolExecutor(max_workers=MAX_CLIENTS) as pool:
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                continue
            try:
                authorized = _peer_uid(connection) == uid
            except (OSError, struct.error):
                authorized = False
            now = time.monotonic()
            saturated = len(admitted) == REQUESTS_PER_SECOND and now - admitted[0] < 1
            if not authorized or saturated or not slots.acquire(blocking=False):
                connection.close()
                continue
            admitted.append(now)
            try:
                pool.submit(_handle, connection, now + DEADLINE_SECONDS, status, slots)
            except RuntimeError:
                connection.close()
                slots.release()
                raise


def serve(path: Path, status: Path, stop: threading.Event) -> None:
    parent = path.parent.lstat()
    if (path.parent.resolve() != path.parent or not stat.S_ISDIR(parent.st_mode)
            or stat.S_IMODE(parent.st_mode) != 0o700 or parent.st_uid != os.geteuid()):
        raise ValueError("private_socket_directory_required")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(path))  # Never replace an existing path.
        info = path.lstat()
        try:
            path.chmod(0o600)
            listener.listen(MAX_CLIENTS)
            listener.settimeout(0.25)
            _dispatch(listener, status, stop)
        finally:
            with contextlib.suppress(FileNotFoundError):
                current = path.lstat()
                if (info.st_dev, info.st_ino) == (current.st_dev, current.st_ino):
                    path.unlink()


def request(path: Path, frame: bytes) -> dict:
    deadline = time.monotonic() + DEADLINE_SECONDS
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        _set_deadline(client, deadline)
        client.connect(str(path))
        if _peer_uid(client) != os.geteuid():
            raise ValueError("unauthorized_server")
        _set_deadline(client, deadline)
        client.sendall(frame)
        return json.loads(_read_frame(client, deadline, MAX_RESPONSE))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    service = sub.add_parser("serve", help="serve events through a private local socket")
    service.add_argument("--socket", type=Path, required=True)
    service.add_argument("--status", type=Path, default=Path("/run/xgw/status.json"))
    client = sub.add_parser("read", help="read after a cursor (omit it for the retained snapshot)")
    client.add_argument("--socket", type=Path, required=True)
    client.add_argument("--epoch")
    client.add_argument("--after", type=int, default=0)
    args = parser.parse_args()
    try:
        if not sys.platform.startswith("linux"):
            raise ValueError("linux_required")
        if args.command == "serve":
            stop = threading.Event()
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, lambda *_: stop.set())
            serve(args.socket.absolute(), args.status, stop)
        else:
            frame = json.dumps({"version": VERSION, "epoch": args.epoch,
                                "after": args.after}).encode() + b"\n"
            parse_request(frame)
            print(json.dumps(request(args.socket, frame), sort_keys=True))
        return 0
    except (OSError, ValueError, RecursionError, struct.error):
        print('{"state":"event_socket_error"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
