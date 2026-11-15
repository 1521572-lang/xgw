#!/usr/bin/env python3
"""Ubuntu-only, bounded file overlay for batch 1. Does not change network configuration.

Run prepare, arm the independent rollback timer from NEXT_STEP, then apply.
Only root-owned immutable payloads are accepted. Unknown installed versions are refused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

BACKEND = ("config.py", "managed.py", "daemon.py", "watch/panel.py",
           "watch/zapret2_control.py", "desync/__init__.py", "desync/schema.py")
GUI = ("vpn_ui/xgw/overview.py", "src/xgw/gui/zapret2.py")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def trusted(path):
    """Reject symlinks and writable parents, including for not-yet-existing targets."""
    require(path.is_absolute(), "absolute path required")
    for part in [*reversed(path.parents), path]:
        require(not part.is_symlink(), f"symlink: {part}")
        if part.exists():
            info = part.stat()
            require(info.st_uid == 0 and not info.st_mode & 0o022, f"untrusted: {part}")
            require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode),
                    f"special file: {part}")


def bounded(value, root):
    # Validate Ubuntu lexical paths independently of the development OS.
    pure = PurePosixPath(value)
    require(pure.is_absolute() and ".." not in pure.parts and "\\" not in value,
            "invalid target path")
    require(pure.is_relative_to(root) and str(pure) != root, "target outside allowed root")
    path = Path(str(pure))
    trusted(path)
    return path


def atomic(path, data, mode=0o644, gid=0):
    trusted(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    fd, name = tempfile.mkstemp(prefix=".batch1-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchown(stream.fileno(), 0, gid)
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def service(action, name="xgw.service"):
    return subprocess.run(["systemctl", action, name], check=True, capture_output=True,
                          text=True, timeout=120).stdout.strip()


def prepare(args, backup):
    require(not (backup / "manifest.json").exists(), "backup already prepared")
    payload = bounded(args.payload, "/opt/xgw")
    package = bounded(args.package, "/opt/xgw")
    require(package.name == "xgw" and package.is_dir(), "expected installed xgw package")
    require(service("is-active") == "active", "daemon must initially be active")
    for unit in ("xgw-nfqws2.service", "xgw-zapret2.service"):
        probe = subprocess.run(["systemctl", "is-active", unit], capture_output=True,
                               text=True, timeout=10)
        require(probe.stdout.strip() in ("inactive", "failed", "unknown"),
                "active/transitioning worker: stop and report, do not disable it")
    pairs = [(payload / "code/src/xgw" / rel, package / rel,
              payload / "base/src/xgw" / rel) for rel in BACKEND]
    if args.gui:
        gui = bounded(args.gui, "/opt/xgw")
        pairs.extend((payload / "code" / rel, gui / rel, payload / "gui_base" / rel)
                     for rel in GUI)
    rows = []
    for index, (source, target, baseline) in enumerate(pairs):
        for path in (source, target, baseline):
            trusted(path)
        new = source.read_bytes()
        compile(new, str(source), "exec")
        old = target.read_bytes() if target.exists() else None
        if baseline.exists():
            require(old == baseline.read_bytes(), f"installed baseline differs: {target}")
        else:
            require(old is None, f"unexpected pre-existing file: {target}")
        row = {"target": str(target), "old_sha": sha(old) if old is not None else None,
               "mode": stat.S_IMODE(target.stat().st_mode) if old is not None else 0o644,
               "gid": target.stat().st_gid if old is not None else 0,
               "new_sha": sha(new), "old": f"{index}.old", "new": f"{index}.new"}
        if old is not None:
            atomic(backup / row["old"], old, 0o600)
        atomic(backup / row["new"], new, 0o600)
        rows.append(row)
    atomic(backup / "manifest.json", (json.dumps(rows, indent=2) + "\n").encode(), 0o600)


def records(backup):
    trusted(backup / "manifest.json")
    rows = json.loads((backup / "manifest.json").read_text())
    require(isinstance(rows, list) and 7 <= len(rows) <= 9, "invalid manifest")
    seen = set()
    for row in rows:
        bounded(row["target"], "/opt/xgw")
        require(row["target"] not in seen, "duplicate target")
        seen.add(row["target"])
        for kind in ("new", "old"):
            if kind == "old" and row["old_sha"] is None:
                continue
            require(Path(row[kind]).name == row[kind], "invalid backup filename")
            path = backup / row[kind]
            trusted(path)
            require(sha(path.read_bytes()) == row[kind + "_sha"], "backup hash mismatch")
    return rows


def restore(backup, rows):
    for row in rows:
        target = Path(row["target"])
        trusted(target)
        if row["old_sha"] is None:
            target.unlink(missing_ok=True)
        else:
            atomic(target, (backup / row["old"]).read_bytes(), row["mode"], row["gid"])


def apply(backup, rows):
    require(service("is-active", "xgw-desync-b1-rollback.timer") == "active",
            "arm independent rollback timer before apply")
    for row in rows:
        target = Path(row["target"])
        actual = sha(target.read_bytes()) if target.exists() else None
        require(actual == row["old_sha"], "installed files changed after prepare")
    service("stop")
    try:
        for row in rows:
            atomic(Path(row["target"]), (backup / row["new"]).read_bytes(),
                   row["mode"], row["gid"])
        service("start")
    except BaseException:
        service("stop")
        restore(backup, rows)
        service("start")
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "apply", "rollback"))
    parser.add_argument("--backup", required=True)
    parser.add_argument("--payload")
    parser.add_argument("--package")
    parser.add_argument("--gui")
    args = parser.parse_args()
    require(sys.platform.startswith("linux") and os.geteuid() == 0, "Ubuntu root required")
    import fcntl

    backup = bounded(args.backup, "/var/lib/xgw/handoff")
    backup.mkdir(parents=True, exist_ok=True, mode=0o700)
    trusted(backup / "operation.lock")
    with (backup / "operation.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # timer and apply may not race
        if args.action == "prepare":
            require(bool(args.payload and args.package), "prepare needs payload and package")
            prepare(args, backup)
        else:
            rows = records(backup)
            if args.action == "apply":
                apply(backup, rows)
            else:
                service("stop")
                restore(backup, rows)
                service("start")
    print(args.action + ": complete")


if __name__ == "__main__":
    main()
