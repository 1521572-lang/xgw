"""Versioned read-only overview for a local panel client on Linux."""

from __future__ import annotations

import contextlib
import json
import os
import re
import secrets
import socket
import stat
import struct
import threading
import time
from collections.abc import Callable
from pathlib import Path

from ..desync.schema import MODES
from ..local_ipc import peer_uid
from .zapret2_control import TITLES

VERSION = 1
TICKET_VERSION = 2
TICKET = re.compile(r"[A-Za-z0-9_-]{43}")
OPERATION = "zapret2.overview"
MAX_REQUEST = 256
MAX_RESPONSE = 1024
TIMEOUT = 2.0
STATUS_FIELDS = ("mode", "engine_mode", "state", "fresh", "policy_matched")
ERRORS = frozenset({"invalid_request", "unsupported_version", "unsupported_operation",
                    "request_too_large", "unauthorized", "unavailable"})


class ProtocolError(ValueError):
    pass


class StatusTickets:
    """One-use grants held only by the trusted ingress and the IPC server."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._active: dict[str, float] = {}

    @contextlib.contextmanager
    def issue(self):
        with self._lock:
            now = self._clock()
            self._active = {key: expires for key, expires in self._active.items() if expires > now}
            if len(self._active) >= 64:
                raise ProtocolError("unavailable")
            ticket = secrets.token_urlsafe(32)
            self._active[ticket] = now + 5.0
        try:
            yield ticket
        finally:
            with self._lock:
                self._active.pop(ticket, None)

    def consume(self, ticket: object) -> bool:
        if not isinstance(ticket, str) or TICKET.fullmatch(ticket) is None:
            return False
        with self._lock:
            expires = self._active.pop(ticket, None)
            return expires is not None and self._clock() < expires


def _unique_fields(pairs: list[tuple[str, object]]) -> dict:
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ProtocolError("duplicate_fields")
    return fields


def project(card: object) -> dict:
    if not isinstance(card, dict):
        raise ProtocolError("invalid_status")
    mode, engine, state = (card.get(key) for key in STATUS_FIELDS[:3])
    if (not isinstance(mode, str) or mode not in MODES
            or not isinstance(engine, str) or engine not in ("off", "auto")
            or not isinstance(state, str) or state not in TITLES
            or any(type(card.get(key)) is not bool for key in STATUS_FIELDS[3:])):
        raise ProtocolError("invalid_status")
    return {key: card[key] for key in STATUS_FIELDS}


def reply(frame: bytes, overview: Callable[[], dict | None], *,
          tickets: StatusTickets | None = None) -> dict:
    version = TICKET_VERSION if tickets is not None else VERSION

    def error(code):
        return {"version": version, "ok": False, "error": code}

    if len(frame) > MAX_REQUEST:
        return error("request_too_large")
    try:
        request = json.loads(frame.decode("utf-8"), object_pairs_hook=_unique_fields)
    except (ValueError, RecursionError):
        return error("invalid_request")
    if not isinstance(request, dict) or "version" not in request or "op" not in request:
        return error("invalid_request")
    if tickets is None and set(request) != {"version", "op"}:
        return error("invalid_request")
    if type(request["version"]) is not int or request["version"] != version:
        return error("unsupported_version")
    fields = {"version", "op", "ticket"} if tickets is not None else {"version", "op"}
    if set(request) != fields:
        return error("invalid_request")
    if request["op"] != OPERATION:
        return error("unsupported_operation")
    if tickets is not None and not tickets.consume(request["ticket"]):
        return error("unauthorized")
    try:
        overview_result = overview()
        status = project(overview_result.get("zapret2")
                         if isinstance(overview_result, dict) else None)
    except (OSError, ValueError, RecursionError):
        return error("unavailable")
    return {"version": version, "ok": True, "status": status}


def _send(connection: socket.socket, payload: bytes) -> None:
    if connection.send(payload) != len(payload):
        raise ProtocolError("short_packet")


def serve(path: Path, uid: int, gid: int, overview: Callable[[], dict | None],
          stop: threading.Event, *, tickets: StatusTickets | None = None) -> None:
    """Admit one configured UID. The group grants access to the socket path."""
    owner = os.geteuid()
    parent = path.parent.lstat()
    if (path.parent.resolve() != path.parent or not stat.S_ISDIR(parent.st_mode)
            or parent.st_uid != owner or parent.st_mode & 0o022):
        raise ValueError("trusted_socket_directory_required")
    with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as listener:
        listener.bind(str(path))
        info = path.lstat()
        try:
            os.chown(path, owner, gid)
            path.chmod(0o660)
            listener.listen(8)
            listener.settimeout(0.25)
            while not stop.is_set():
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                try:
                    with connection:
                        if peer_uid(connection) != uid:
                            continue
                        connection.settimeout(TIMEOUT)
                        frame = connection.recv(MAX_REQUEST + 1)
                        if frame:
                            payload = json.dumps(reply(frame, overview, tickets=tickets),
                                                 separators=(",", ":"))
                            _send(connection, payload.encode("ascii"))
                except (OSError, ProtocolError, struct.error):
                    continue
        finally:
            with contextlib.suppress(FileNotFoundError):
                current = path.lstat()
                if (current.st_dev, current.st_ino) == (info.st_dev, info.st_ino):
                    path.unlink()


def read_overview(path: Path, *, server_uid: int, ticket: str | None = None) -> dict:
    version = TICKET_VERSION if ticket is not None else VERSION
    request = {"version": version, "op": OPERATION}
    if ticket is not None:
        request["ticket"] = ticket
    with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as client:
        client.settimeout(TIMEOUT)
        client.connect(str(path))
        if peer_uid(client) != server_uid:
            raise ProtocolError("unexpected_server_uid")
        _send(client, json.dumps(request, separators=(",", ":")).encode("ascii"))
        frame = client.recv(MAX_RESPONSE + 1)
    if not frame or len(frame) > MAX_RESPONSE:
        raise ProtocolError("invalid_response")
    try:
        data = json.loads(frame.decode("utf-8"), object_pairs_hook=_unique_fields)
    except (ValueError, RecursionError) as exc:
        raise ProtocolError("invalid_response") from exc
    if (not isinstance(data, dict) or type(data.get("version")) is not int
            or data["version"] != version):
        raise ProtocolError("invalid_response")
    if data.get("ok") is False and set(data) == {"version", "ok", "error"}:
        error = data["error"]
        if isinstance(error, str) and error in ERRORS:
            raise ProtocolError(error)
    if (data.get("ok") is not True or set(data) != {"version", "ok", "status"}
            or not isinstance(data["status"], dict) or set(data["status"]) != set(STATUS_FIELDS)):
        raise ProtocolError("invalid_response")
    return project(data["status"])
