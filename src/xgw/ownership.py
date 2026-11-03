"""Dormant REC-C registry foundation; no entrypoint imports or activates this module.

All I/O is explicit. Callers must supply a trusted private directory and current boot
identity. Production adapters, activation, verifier and interrupted-write repair do
not exist yet. A receipt records a caller's assertion, not network health.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import math
import os
import re
import stat
import time
import uuid
from pathlib import Path

from .ownership_identity import CodeIdentity, IdentityRefused, valid_record

MAX_BYTES = 65536
MAX_WRITERS = 32
MAX_RECEIPTS = 32
MAX_LEASE_NS = 45000000000
ROLES = frozenset({"CAPTURE", "PANEL", "PEERS", "CORE", "API", "TUN_HOOK", "LIFECYCLE"})
OUTCOMES = frozenset({"COMMITTED", "NOOP", "ROLLED_BACK"})


class Refused(Exception):
    """Only fixed public reason codes; never include paths or private state."""


def require(value, code):
    if not value:
        raise Refused(code)


def integer(value):
    return type(value) is int and 0 <= value <= 2**63 - 1


def identity(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def boot(value):
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value) is not None
    )


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


class Registry:
    """Persistent admission bookkeeping only; this class never mutates gateway state.

    expected_uid defaults to root. A nonroot owner is an explicit fixture policy for
    isolated tests; future runtime adapters must require UID0 and fixed runtime paths.
    clock_ns is injectable for tests. Real adapters must use the default monotonic clock.
    Construction does no filesystem reads, directory creation or clock calls.
    """

    def __init__(self, directory, *, boot_id, expected_uid=0, clock_ns=None, lock_budget=0.2,
                 code_identity=None):
        require(code_identity is None or type(code_identity) is CodeIdentity,
                "CODE_IDENTITY_ARGUMENT")
        try:
            record = None if code_identity is None else code_identity.record()
        except IdentityRefused:
            raise Refused("CODE_IDENTITY_ARGUMENT") from None
        self.code_identity = self._code_identity = code_identity
        self._code_record = record
        self._code_digest = None if code_identity is None else code_identity.digest()
        self._state_schema = 1 if code_identity is None else 2
        require(boot(boot_id), "BOOT_ARGUMENT")
        require(integer(expected_uid), "OWNER_ARGUMENT")
        require(
            type(lock_budget) in (int, float)
            and math.isfinite(lock_budget)
            and 0 < lock_budget <= 1,
            "LOCK_BUDGET_ARGUMENT",
        )
        self.directory = Path(directory)
        require(self.directory.is_absolute(), "DIRECTORY_ARGUMENT")
        self.boot_id = boot_id
        self.expected_uid = expected_uid
        self.clock_ns = time.monotonic_ns if clock_ns is None else clock_ns
        require(callable(self.clock_ns), "CLOCK_ARGUMENT")
        self.lock_budget = lock_budget

    def code_context(self):
        require(self.code_identity is self._code_identity, "CODE_CONTEXT_CHANGED")
        try:
            current = None if self.code_identity is None else self.code_identity.record()
        except IdentityRefused:
            raise Refused("CODE_CONTEXT_CHANGED") from None
        require(current == self._code_record, "CODE_CONTEXT_CHANGED")

    def token_fields(self, fields):
        return fields | {"code_identity_sha256"} if self._state_schema == 2 else fields

    def bind_token(self, token):
        if self._state_schema == 2:
            token["code_identity_sha256"] = self._code_digest
        return token

    def metadata(self, info, *, directory=False):
        kind = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        require(
            kind
            and info.st_uid == self.expected_uid
            and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
            and (directory or info.st_nlink == 1),
            "PRIVATE_METADATA",
        )

    def open_directory(self):
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            self.metadata(os.fstat(fd), directory=True)
            self.directory_identity(fd)
            return fd
        except BaseException:
            os.close(fd)
            raise

    def directory_identity(self, fd):
        current, path = os.fstat(fd), self.directory.lstat()
        self.metadata(path, directory=True)
        require(
            (current.st_dev, current.st_ino) == (path.st_dev, path.st_ino), "DIRECTORY_REPLACED"
        )

    def read(self, directory_fd, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        with os.fdopen(fd, "rb") as stream:
            self.metadata(os.fstat(stream.fileno()))
            raw = stream.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES, "RECORD_LIMIT")
        try:
            return json.loads(raw, object_pairs_hook=pairs)
        except (UnicodeError, ValueError, RecursionError):
            raise Refused("INVALID_JSON") from None

    def exclusive_write(self, directory_fd, name, payload):
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        require(len(raw) <= MAX_BYTES, "RECORD_LIMIT")
        fd = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd
        )
        with os.fdopen(fd, "wb") as stream:
            self.metadata(os.fstat(stream.fileno()))
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())

    def initialize(self):
        """Exclusive explicit bootstrap of a NEW store. Never repairs or reuses one."""
        self.code_context()
        try:
            self.directory.mkdir(mode=0o700, parents=False, exist_ok=False)
            directory_fd = self.open_directory()
            try:
                self.exclusive_write(directory_fd, "lock", {})
                info = os.stat("lock", dir_fd=directory_fd, follow_symlinks=False)
                state = {
                    "schema": self._state_schema,
                    "registry_id": uuid.uuid4().hex,
                    "boot_id": self.boot_id,
                    "lock_device": info.st_dev,
                    "lock_inode": info.st_ino,
                    "revision": 0,
                    "generation": 0,
                    "serial": 0,
                    "epoch": 0,
                    "writers": [],
                    "lease": None,
                    "receipts": [],
                }
                if self._state_schema == 2:
                    state["code_identity"] = dict(self._code_record)
                self.validate(state)
                self.exclusive_write(directory_fd, "state.json", state)
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            raise Refused("INITIALIZE_FAILED") from None

    def validate(self, state):
        self.code_context()
        fields = {
            "schema",
            "registry_id",
            "boot_id",
            "lock_device",
            "lock_inode",
            "revision",
            "generation",
            "serial",
            "epoch",
            "writers",
            "lease",
            "receipts",
        }
        if self._state_schema == 2:
            fields.add("code_identity")
        require(isinstance(state, dict) and set(state) == fields, "STATE_SCHEMA")
        require(type(state["schema"]) is int and state["schema"] == self._state_schema,
                "STATE_SCHEMA")
        if self._state_schema == 2:
            require(valid_record(state["code_identity"])
                    and state["code_identity"] == self._code_record, "CODE_IDENTITY_MISMATCH")
        require(identity(state["registry_id"]) and boot(state["boot_id"]), "STATE_IDENTITY")
        require(state["boot_id"] == self.boot_id, "BOOT_MISMATCH")
        require(
            all(
                integer(state[k])
                for k in ("lock_device", "lock_inode", "revision", "generation", "serial", "epoch")
            ),
            "STATE_INTEGER",
        )
        require(
            max(state["generation"], state["serial"], state["epoch"]) <= state["revision"],
            "STATE_SEQUENCE",
        )
        require(
            isinstance(state["writers"], list) and len(state["writers"]) <= MAX_WRITERS,
            "WRITER_LIMIT",
        )
        ids = set()
        for writer in state["writers"]:
            require(
                isinstance(writer, dict) and set(writer) == {"id", "role", "phase"}, "WRITER_SCHEMA"
            )
            require(
                integer(writer["id"])
                and 0 < writer["id"] <= state["serial"]
                and writer["id"] not in ids,
                "WRITER_ID",
            )
            require(
                isinstance(writer["role"], str)
                and writer["role"] in ROLES
                and writer["phase"] in ("LIVE", "UNKNOWN"),
                "WRITER_VALUES",
            )
            ids.add(writer["id"])
        lease = state["lease"]
        if lease is not None:
            require(
                isinstance(lease, dict)
                and set(lease)
                == {"run_id", "epoch", "generation", "phase", "acquired_ns", "deadline_ns"},
                "LEASE_SCHEMA",
            )
            require(
                not state["writers"]
                and identity(lease["run_id"])
                and type(lease["epoch"]) is int
                and lease["epoch"] == state["epoch"] > 0
                and type(lease["generation"]) is int
                and lease["generation"] == state["generation"]
                and lease["phase"] in ("ARMED", "RUNNING"),
                "LEASE_VALUES",
            )
            require(
                integer(lease["acquired_ns"])
                and integer(lease["deadline_ns"])
                and 0 < lease["deadline_ns"] - lease["acquired_ns"] <= MAX_LEASE_NS,
                "LEASE_CLOCK",
            )
        require(
            isinstance(state["receipts"], list) and len(state["receipts"]) <= MAX_RECEIPTS,
            "RECEIPT_LIMIT",
        )
        previous_generation = 0
        for receipt in state["receipts"]:
            require(
                isinstance(receipt, dict)
                and set(receipt) == {"id", "role", "outcome", "generation"},
                "RECEIPT_SCHEMA",
            )
            require(
                integer(receipt["id"])
                and 0 < receipt["id"] <= state["serial"]
                and receipt["id"] not in ids
                and isinstance(receipt["role"], str)
                and receipt["role"] in ROLES
                and isinstance(receipt["outcome"], str)
                and receipt["outcome"] in OUTCOMES
                and integer(receipt["generation"])
                and previous_generation < receipt["generation"] <= state["generation"],
                "RECEIPT_VALUES",
            )
            ids.add(receipt["id"])
            previous_generation = receipt["generation"]

    def lock_identity(self, directory_fd, lock_fd, state=None):
        self.directory_identity(directory_fd)
        current = os.fstat(lock_fd)
        path = os.stat("lock", dir_fd=directory_fd, follow_symlinks=False)
        self.metadata(current)
        self.metadata(path)
        require((current.st_dev, current.st_ino) == (path.st_dev, path.st_ino), "LOCK_REPLACED")
        if state is not None:
            require(
                (current.st_dev, current.st_ino) == (state["lock_device"], state["lock_inode"]),
                "LOCK_REPLACED",
            )

    @contextlib.contextmanager
    def locked(self):
        self.code_context()
        try:
            directory_fd = self.open_directory()
            try:
                fd = os.open("lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
                try:
                    self.lock_identity(directory_fd, fd)
                    deadline = time.monotonic() + self.lock_budget
                    while True:
                        try:
                            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            require(time.monotonic() < deadline, "LOCK_BUSY")
                            time.sleep(0.005)
                    try:
                        self.lock_identity(directory_fd, fd)
                        try:
                            os.stat("state.next", dir_fd=directory_fd, follow_symlinks=False)
                        except FileNotFoundError:
                            pass
                        else:
                            raise Refused("INTERRUPTED_COMMIT")
                        state = self.read(directory_fd, "state.json")
                        self.validate(state)
                        self.lock_identity(directory_fd, fd, state)
                        yield directory_fd, fd, state
                    finally:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)
            finally:
                os.close(directory_fd)
        except OSError:
            raise Refused("STORE_IO") from None

    def commit(self, directory_fd, lock_fd, state):
        state["revision"] += 1
        self.validate(state)
        self.lock_identity(directory_fd, lock_fd, state)
        try:
            self.exclusive_write(directory_fd, "state.next", state)
            self.lock_identity(directory_fd, lock_fd, state)
            os.replace("state.next", "state.json", src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            os.fsync(directory_fd)
        except OSError:
            raise Refused("COMMIT_UNCERTAIN") from None

    def writer_token(self, state, writer):
        return self.bind_token({
            "registry_id": state["registry_id"],
            "boot_id": state["boot_id"],
            "id": writer["id"],
            "role": writer["role"],
        })

    def check_writer_token(self, state, token):
        require(
            isinstance(token, dict)
            and set(token) == self.token_fields({"registry_id", "boot_id", "id", "role"})
            and (self._state_schema == 1 or token["code_identity_sha256"] == self._code_digest)
            and token["registry_id"] == state["registry_id"]
            and token["boot_id"] == self.boot_id
            and integer(token["id"])
            and token["id"] > 0
            and isinstance(token["role"], str)
            and token["role"] in ROLES,
            "WRITER_TOKEN",
        )

    def find_writer(self, state, token):
        self.check_writer_token(state, token)
        matches = [w for w in state["writers"] if self.writer_token(state, w) == token]
        require(len(matches) == 1, "STALE_WRITER_TOKEN")
        return matches[0]

    def admit(self, role):
        require(isinstance(role, str) and role in ROLES, "ROLE_ARGUMENT")
        with self.locked() as (directory_fd, fd, state):
            require(state["lease"] is None, "FENCED")
            require(all(w["phase"] == "LIVE" for w in state["writers"]), "UNKNOWN_WRITER")
            require(len(state["writers"]) < MAX_WRITERS, "WRITER_LIMIT")
            state["serial"] += 1
            writer = {"id": state["serial"], "role": role, "phase": "LIVE"}
            state["writers"].append(writer)
            self.commit(directory_fd, fd, state)
            return self.writer_token(state, writer)

    def complete(self, token, *, outcome, verified):
        require(
            isinstance(outcome, str) and outcome in OUTCOMES and verified is True,
            "COMPLETION_UNVERIFIED",
        )
        with self.locked() as (directory_fd, fd, state):
            writer = self.find_writer(state, token)
            require(writer["phase"] == "LIVE" and state["lease"] is None, "COMPLETION_BLOCKED")
            state["generation"] += 1
            receipt = {
                "id": writer["id"],
                "role": writer["role"],
                "outcome": outcome,
                "generation": state["generation"],
            }
            state["receipts"] = (state["receipts"] + [receipt])[-MAX_RECEIPTS:]
            state["writers"].remove(writer)
            # A single atomic record replaces AA's two-file completion gap.
            self.commit(directory_fd, fd, state)
            return dict(receipt)

    def unknown(self, token):
        with self.locked() as (directory_fd, fd, state):
            self.find_writer(state, token)["phase"] = "UNKNOWN"
            self.commit(directory_fd, fd, state)

    def now(self):
        value = self.clock_ns()
        require(integer(value), "CLOCK_ARGUMENT")
        return value

    def receipt(self, token):
        """Return a retained receipt, or None (never permission to retry a mutation)."""
        with self.locked() as (_, __, state):
            self.check_writer_token(state, token)
            for receipt in state["receipts"]:
                if self.writer_token(state, receipt) == token:
                    return {"outcome": receipt["outcome"], "generation": receipt["generation"]}
            return None

    def recovery_token(self, state):
        lease = state["lease"]
        return self.bind_token({
            "registry_id": state["registry_id"],
            "boot_id": state["boot_id"],
            "run_id": lease["run_id"],
            "epoch": lease["epoch"],
            "generation": lease["generation"],
        })

    def acquire(self, *, run_id, expected_generation, duration_ns):
        require(
            identity(run_id)
            and integer(expected_generation)
            and type(duration_ns) is int
            and 0 < duration_ns <= MAX_LEASE_NS,
            "LEASE_ARGUMENT",
        )
        with self.locked() as (directory_fd, fd, state):
            require(state["lease"] is None, "FENCED")
            require(not state["writers"], "WRITERS_IN_FLIGHT")
            require(state["generation"] == expected_generation, "STALE_GENERATION")
            now = self.now()
            state["epoch"] += 1
            state["lease"] = {
                "run_id": run_id,
                "epoch": state["epoch"],
                "generation": state["generation"],
                "phase": "ARMED",
                "acquired_ns": now,
                "deadline_ns": now + duration_ns,
            }
            self.commit(directory_fd, fd, state)
            return self.recovery_token(state)

    def check_recovery_token(self, state, token):
        require(
            state["lease"] is not None
            and isinstance(token, dict)
            and set(token) == self.token_fields(
                {"registry_id", "boot_id", "run_id", "epoch", "generation"})
            and type(token["epoch"]) is int
            and type(token["generation"]) is int
            and token == self.recovery_token(state),
            "RECOVERY_TOKEN",
        )

    def begin(self, token):
        with self.locked() as (directory_fd, fd, state):
            self.check_recovery_token(state, token)
            lease = state["lease"]
            require(lease["phase"] == "ARMED", "JOB_ALREADY_STARTED")
            require(lease["acquired_ns"] <= self.now() < lease["deadline_ns"], "LEASE_TIME")
            lease["phase"] = "RUNNING"
            self.commit(directory_fd, fd, state)

    def retire(self, token, *, outcome, verified=False):
        with self.locked() as (directory_fd, fd, state):
            self.check_recovery_token(state, token)
            phase = state["lease"]["phase"]
            require(
                (outcome == "UNUSED" and phase == "ARMED")
                or (outcome == "RESTORED_ON" and phase == "RUNNING" and verified is True),
                "RETIREMENT_UNVERIFIED",
            )
            if outcome == "RESTORED_ON":
                state["generation"] += 1
            state["lease"] = None
            self.commit(directory_fd, fd, state)

    def summary(self):
        """Sanitized bookkeeping. This is never a runtime recovery qualification."""
        with self.locked() as (_, __, state):
            result = {
                "writers": len(state["writers"]),
                "unknown": sum(w["phase"] == "UNKNOWN" for w in state["writers"]),
                "generation": state["generation"],
                "receipts": len(state["receipts"]),
                "phase": state["lease"]["phase"] if state["lease"] else "IDLE",
            }
            if self._state_schema == 2:
                result.update(schema=2, code_bound=True)
            return result
