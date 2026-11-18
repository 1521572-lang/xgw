"""Switch the installed Qt home view using the pinned before/after files in the handoff."""

import argparse
import fcntl
import os
import stat
import sys
from pathlib import Path

# The assignment installs both helpers into the same root-owned payload before sudo -I.
sys.path.insert(0, str(Path(__file__).parent))
from gui_catalog_install import atomic, trusted

BASE = "7c20f59023ec39e5c5ce4606767ea915c3b91f64"
RELEASE = Path("/opt/xgw/gui/releases") / BASE
DISPATCHER = Path("/opt/xgw/lib/xgw/gui/app.py")
FILES = ("vpn_ui/main_xgw.py", "vpn_ui/views/map_canvas_view.py", "vpn_ui/xgw/panels.py",
         "vpn_ui/xgw/sidebar.py", "vpn_ui/xgw/window.py")


def delivery(payload):
    rows = []
    for name in FILES:
        before, after = (payload / kind / name for kind in ("before", "after"))
        trusted(before)
        trusted(after)
        rows.append((RELEASE / name, before.read_bytes(), after.read_bytes()))
    saved = Path("/var/lib/xgw/gui-install") / BASE / "patched.py"
    trusted(saved)
    old = saved.read_bytes()
    line = b"        '--theme', 'light', '--native-titlebar',"
    if old.count(line) != 1 or str(RELEASE / "vpn_ui/main_xgw.py").encode() not in old:
        raise ValueError("unexpected dispatcher in installation backup")
    rows.append((DISPATCHER, old, old.replace(line, b"")))
    return rows


def switch(rows, action):
    changes = []
    for target, before, after in rows:
        trusted(target)
        current = target.read_bytes()
        if current not in (before, after):
            raise ValueError(f"unexpected installed file: {target}")
        wanted = before if action == "rollback" else after
        compile(wanted, str(target), "exec")
        if current != wanted:
            info = target.stat()
            changes.append((target, current, wanted, stat.S_IMODE(info.st_mode), info.st_gid))
    if action == "check":
        print("READY", "changed files:", len(changes))
        return
    applied = []
    try:
        for row in changes:
            target, current, wanted, mode, gid = row
            if target.read_bytes() != current:
                raise ValueError(f"changed since preflight: {target}")
            atomic(target, wanted, mode, gid)
            applied.append(row)
        for target, before, after in rows:
            if target.read_bytes() != (before if action == "rollback" else after):
                raise ValueError(f"verification failed: {target}")
    except BaseException:
        for target, current, wanted, mode, gid in reversed(applied):
            if target.read_bytes() == wanted:
                atomic(target, current, mode, gid)
        raise
    print("RESTORED" if action == "rollback" else "INSTALLED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "apply", "rollback"))
    args = parser.parse_args()
    payload = Path(__file__).parent
    trusted(payload)
    if os.geteuid() or not payload.is_relative_to("/var/lib/xgw/handoff"):
        parser.error("install the pinned payload under /var/lib/xgw/handoff and run as root")
    # Lock the common release, including when another session uses a different payload directory.
    trusted(RELEASE)
    fd = os.open(RELEASE, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        switch(delivery(payload), args.action)
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
