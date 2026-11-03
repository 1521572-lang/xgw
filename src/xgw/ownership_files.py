"""Bounded exact file observations in an explicit private tree. No mutation/repair.

Evidence covers named files only, not an atomic snapshot, whole-directory inventory,
kernel/API/service state, network health or permission to activate recovery.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

MAX_FILE = 2097152


@dataclass(frozen=True)
class FileExpectation:
    relative: str
    digest: str | None = None
    mode: int = 0o600
    absent: bool = False


@dataclass(frozen=True)
class FileEvidence:
    matched: bool
    checked: int
    reason: str


class ObservationRefused(Exception):
    pass


def require(value, code):
    if not value:
        raise ObservationRefused(code)


def stamp(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


class PrivateFiles:
    """Exact bytes/hash/mode/owner/nlink or exact absence, no symlink ancestors.

    Root and descendants used as directories must be owner0700. Production protected
    path policies are not wired; UID is supplied explicitly, no default runtime root.
    Constructor validates arguments only. observe reads without creating anything.
    """

    def __init__(self, root, *, expected_uid, expectations):
        self.root = Path(root)
        require(self.root.is_absolute() and ".." not in self.root.parts, "ROOT_ARGUMENT")
        require(type(expected_uid) is int and expected_uid >= 0, "OWNER_ARGUMENT")
        require(type(expectations) is tuple and 1 <= len(expectations) <= 32, "FILE_COUNT")
        names = set()
        for item in expectations:
            require(type(item) is FileExpectation, "FILE_TYPE")
            require(
                type(item.relative) is str
                and len(item.relative) <= 512
                and re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", item.relative)
                and all(part not in (".", "..") for part in item.relative.split("/"))
                and item.relative not in names,
                "FILE_PATH",
            )
            names.add(item.relative)
            require(type(item.absent) is bool, "ABSENCE_ARGUMENT")
            require(type(item.mode) is int and 0 <= item.mode <= 0o777, "MODE_ARGUMENT")
            require(
                (item.absent and item.digest is None)
                or (
                    not item.absent
                    and type(item.digest) is str
                    and re.fullmatch(r"[0-9a-f]{64}", item.digest)
                ),
                "DIGEST_ARGUMENT",
            )
        self.expected_uid = expected_uid
        self.expectations = expectations

    def directory(self, fd):
        info = os.fstat(fd)
        require(
            stat.S_ISDIR(info.st_mode)
            and info.st_uid == self.expected_uid
            and stat.S_IMODE(info.st_mode) == 0o700,
            "DIRECTORY_METADATA",
        )
        return info

    def open_root(self):
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(self.root.anchor, flags)
        try:
            for part in self.root.parts[1:]:
                next_fd = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            self.directory(fd)
            return fd
        except BaseException:
            os.close(fd)
            raise

    def observe_one(self, root_fd, item):
        parent = os.dup(root_fd)
        opened = []
        try:
            parts = item.relative.split("/")
            for part in parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                try:
                    info = self.directory(child)
                except BaseException:
                    os.close(child)
                    raise
                opened.append((os.dup(parent), part, info.st_dev, info.st_ino))
                os.close(parent)
                parent = child
            if item.absent:
                try:
                    os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise ObservationRefused("EXPECTED_ABSENCE")
            else:
                fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                with os.fdopen(fd, "rb") as stream:
                    before = os.fstat(stream.fileno())
                    require(
                        stat.S_ISREG(before.st_mode)
                        and before.st_uid == self.expected_uid
                        and before.st_nlink == 1
                        and stat.S_IMODE(before.st_mode) == item.mode
                        and before.st_size <= MAX_FILE,
                        "FILE_METADATA",
                    )
                    raw = stream.read(MAX_FILE + 1)
                    require(len(raw) <= MAX_FILE, "FILE_LIMIT")
                    after = os.fstat(stream.fileno())
                final = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
                require(stamp(before) == stamp(after) == stamp(final), "FILE_CHANGED")
                require(hashlib.sha256(raw).hexdigest() == item.digest, "CONTENT_MISMATCH")
            self.directory(parent)
            for parent_fd, part, dev, ino in opened:
                current = os.stat(part, dir_fd=parent_fd, follow_symlinks=False)
                require((current.st_dev, current.st_ino) == (dev, ino), "DIRECTORY_CHANGED")
                require(
                    stat.S_ISDIR(current.st_mode)
                    and current.st_uid == self.expected_uid
                    and stat.S_IMODE(current.st_mode) == 0o700,
                    "DIRECTORY_METADATA",
                )
        finally:
            os.close(parent)
            for parent_fd, *_ in opened:
                os.close(parent_fd)

    def observe(self):
        checked = 0
        root_fd = None
        try:
            root_fd = self.open_root()
            initial = self.directory(root_fd)
            for item in self.expectations:
                self.observe_one(root_fd, item)
                checked += 1
            final_fd = self.open_root()
            try:
                final = self.directory(final_fd)
                require(
                    (initial.st_dev, initial.st_ino) == (final.st_dev, final.st_ino), "ROOT_CHANGED"
                )
            finally:
                os.close(final_fd)
            self.directory(root_fd)
            return FileEvidence(True, checked, "EXACT_NAMED_FILES_OBSERVED")
        except ObservationRefused as exc:
            return FileEvidence(False, checked, str(exc))
        except (OSError, ValueError):
            return FileEvidence(False, checked, "READ_REFUSED")
        finally:
            if root_fd is not None:
                os.close(root_fd)
