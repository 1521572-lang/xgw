"""Bounded read-only exact inventory of an explicit artifact tree.

No execution, import, installation, chmod, repair or authorization. Observations
are sequential and do not make a mutable filesystem an atomic snapshot.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .ownership_identity import canonical

MAX_FILE = 2097152
MAX_TOTAL = 16777216
MAX_FILES = 256
REASONS = frozenset(
    {
        "SEAL_TYPE",
        "SEAL_CONTEXT",
        "DIRECTORY_METADATA",
        "FILE_METADATA",
        "FILE_LIMIT",
        "TOTAL_LIMIT",
        "FILE_CHANGED",
        "CONTENT_MISMATCH",
        "INVENTORY_MISMATCH",
        "DIRECTORY_CHANGED",
        "ROOT_CHANGED",
    }
)


class SealRefused(Exception):
    pass


def require(value, code):
    if not value:
        raise SealRefused(code)


@dataclass(frozen=True)
class CodeFile:
    relative: str
    sha256: str
    mode: int = 0o600


@dataclass(frozen=True)
class SealEvidence:
    matched: bool
    checked: int
    reason: str


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


def tree(expectations):
    root = {}
    for item in expectations:
        parts = item.relative.split("/")
        node = root
        for name in parts[:-1]:
            require(name not in node or type(node[name]) is dict, "MANIFEST_COLLISION")
            node = node.setdefault(name, {})
        require(parts[-1] not in node, "MANIFEST_COLLISION")
        node[parts[-1]] = item
    return root


def methods_intact(observer):
    require(type(observer) is CodeSeal, "SEAL_TYPE")
    for name, function in METHODS.items():
        method = getattr(observer, name, None)
        require(
            getattr(method, "__self__", None) is observer
            and getattr(method, "__func__", None) is function,
            "SEAL_CONTEXT",
        )


class CodeSeal:
    """No constructor I/O. Explicit owner and exact files/modes, no defaults to live paths.

    Root/descendant directories must be owner700/750/755, never group/other writable.
    Ancestors are traversed with NOFOLLOW, without claiming a complete ancestor DAC
    or mount policy. A production startup must separately protect its fixed roots.
    """

    def __init__(self, root, *, expected_uid, expectations):
        require(type(self) is CodeSeal, "SEAL_TYPE")
        self.root = Path(root)
        require(
            self.root.is_absolute()
            and self.root != Path(self.root.anchor)
            and ".." not in self.root.parts
            and len(self.root.parts) <= 64,
            "ROOT_ARGUMENT",
        )
        require(type(expected_uid) is int and expected_uid >= 0, "OWNER_ARGUMENT")
        require(type(expectations) is tuple and 1 <= len(expectations) <= MAX_FILES, "FILE_COUNT")
        names = set()
        for item in expectations:
            require(
                type(item) is CodeFile
                and type(item.relative) is str
                and len(item.relative) <= 512
                and len(item.relative.split("/")) <= 16
                and re.fullmatch(r"[A-Za-z0-9_.@-]+(?:/[A-Za-z0-9_.@-]+)*", item.relative)
                and all(p not in (".", "..") for p in item.relative.split("/"))
                and item.relative not in names,
                "FILE_ARGUMENT",
            )
            require(
                type(item.sha256) is str and re.fullmatch(r"[0-9a-f]{64}", item.sha256),
                "DIGEST_ARGUMENT",
            )
            require(
                type(item.mode) is int and item.mode in (0o600, 0o640, 0o644, 0o700, 0o750, 0o755),
                "MODE_ARGUMENT",
            )
            names.add(item.relative)
        tree(expectations)
        self.expected_uid, self.expectations = expected_uid, expectations
        self._policy = (self.root, expected_uid, expectations)
        self._pid, self._thread = os.getpid(), threading.get_ident()
        methods_intact(self)
        self._digest = self.manifest_digest()

    def manifest_digest(self):
        return hashlib.sha256(
            canonical(
                {
                    "schema": 1,
                    "files": [
                        {"path": f.relative, "sha256": f.sha256, "mode": f.mode}
                        for f in sorted(self.expectations, key=lambda f: f.relative)
                    ],
                }
            )
        ).hexdigest()

    def validate(self):
        methods_intact(self)
        require(
            self._pid == os.getpid()
            and self._thread == threading.get_ident()
            and (self.root, self.expected_uid, self.expectations) == self._policy
            and type(self.expected_uid) is int
            and self.manifest_digest() == self._digest,
            "SEAL_CONTEXT",
        )

    def directory(self, fd):
        info = os.fstat(fd)
        require(
            stat.S_ISDIR(info.st_mode)
            and info.st_uid == self.expected_uid
            and stat.S_IMODE(info.st_mode) in (0o700, 0o750, 0o755),
            "DIRECTORY_METADATA",
        )
        return info

    def open_root(self):
        fd = os.open(self.root.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in self.root.parts[1:]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            self.directory(fd)
            return fd
        except BaseException:
            os.close(fd)
            raise

    def read_file(self, parent, name, item, budget):
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        require(
            stat.S_ISREG(before.st_mode)
            and before.st_uid == self.expected_uid
            and before.st_nlink == 1
            and stat.S_IMODE(before.st_mode) == item.mode,
            "FILE_METADATA",
        )
        require(before.st_size <= MAX_FILE, "FILE_LIMIT")
        require(before.st_size <= budget, "TOTAL_LIMIT")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, "rb") as stream:
            require(stamp(os.fstat(stream.fileno())) == stamp(before), "FILE_CHANGED")
            raw = stream.read(min(MAX_FILE, budget) + 1)
            after = os.fstat(stream.fileno())
        final = os.stat(name, dir_fd=parent, follow_symlinks=False)
        require(
            len(raw) <= min(MAX_FILE, budget) and stamp(before) == stamp(after) == stamp(final),
            "FILE_CHANGED",
        )
        require(hashlib.sha256(raw).hexdigest() == item.sha256, "CONTENT_MISMATCH")
        return len(raw)

    def walk(self, fd, expected, counter):
        before = self.directory(fd)
        names = set()
        with os.scandir(fd) as entries:
            for entry in entries:
                require(entry.name in expected and entry.name not in names, "INVENTORY_MISMATCH")
                names.add(entry.name)
        require(names == set(expected), "INVENTORY_MISMATCH")
        for name in sorted(expected):
            item = expected[name]
            if type(item) is dict:
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    initial = self.directory(child)
                    self.walk(child, item, counter)
                    current = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    require(stamp(current) == stamp(initial), "DIRECTORY_CHANGED")
                finally:
                    os.close(child)
            else:
                counter[1] += self.read_file(fd, name, item, MAX_TOTAL - counter[1])
                counter[0] += 1
        require(stamp(before) == stamp(self.directory(fd)), "DIRECTORY_CHANGED")

    def observe(self):
        counter = [0, 0]
        root_fd = None
        try:
            methods_intact(self)
            self.validate()
            root_fd = self.open_root()
            initial = self.directory(root_fd)
            self.walk(root_fd, tree(self.expectations), counter)
            self.validate()
            check = self.open_root()
            try:
                require(stamp(initial) == stamp(self.directory(check)), "ROOT_CHANGED")
            finally:
                os.close(check)
            require(counter[0] == len(self.expectations), "INVENTORY_MISMATCH")
            return SealEvidence(True, counter[0], "EXACT_CODE_INVENTORY")
        except SealRefused as exc:
            reason = exc.args[0] if type(exc) is SealRefused and len(exc.args) == 1 else None
            reason = reason if type(reason) is str and reason in REASONS else "READ_REFUSED"
            return SealEvidence(False, counter[0], reason)
        except (OSError, ValueError):
            return SealEvidence(False, counter[0], "READ_REFUSED")
        finally:
            if root_fd is not None:
                os.close(root_fd)


METHODS = MappingProxyType(
    {
        n: getattr(CodeSeal, n)
        for n in (
            "manifest_digest",
            "validate",
            "directory",
            "open_root",
            "read_file",
            "walk",
            "observe",
        )
    }
)
