#!/usr/bin/env python3
"""Read-only checks for the GUI layout handoff. Never changes services or networking."""

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "src/xgw/gui"
TARGET = Path("/opt/xgw/lib/xgw/gui")
FILES = ("pages.py", "theme.py", "widgets.py", "window.py", "mapdata.py")
STAGE = "arguments"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def snapshot():
    global STAGE
    STAGE = "status"
    path = Path("/run/xgw/status.json")
    state = json.loads(path.read_text())
    if time.time() - path.stat().st_mtime > 90:
        raise ValueError("stale")
    if (state.get("capture") or {}).get("mode") != "on":
        raise ValueError("capture")
    STAGE = "services"
    units = []
    for name in ("xgw.service", "xgw-xray.service", "xgw-singbox.service"):
        result = subprocess.run(
            ["systemctl", "show", name, "-p", "ActiveState", "-p", "MainPID"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        units.append(dict(line.split("=", 1) for line in result.stdout.splitlines()))
    if any(unit.get("ActiveState") != "active" or int(unit.get("MainPID", 0)) <= 0
           for unit in units[:2]):
        raise ValueError("inactive")
    STAGE = "settings"
    config = digest(Path("/etc/xgw/config.toml"))
    if config is None:
        raise ValueError("config")
    return {
        "config": config, "managed": digest(Path("/etc/xgw/panel.json")),
        "pin": (state.get("pin") or {}).get("tag"),
        "pool_mode": (state.get("free_pool") or {}).get("mode"), "units": units,
    }


def main():
    global STAGE
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("before", "after"))
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    data = snapshot()
    if args.action == "before":
        STAGE = "save_baseline"
        fd = os.open(args.state, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
        print("OK baseline: capture_on=1 services_active=1")
        return
    STAGE = "read_baseline"
    before = json.loads(args.state.read_text())
    STAGE = "settings_unchanged"
    if any(before[key] != data[key] for key in ("config", "managed", "pin", "pool_mode")):
        raise ValueError("changed")
    STAGE = "installed_files"
    for name in FILES:
        path = TARGET / name
        if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
            raise ValueError("file_type")
        if digest(path) != digest(SOURCE / name):
            raise ValueError("content")
    changed = sum(a != b for a, b in zip(before["units"], data["units"], strict=True))
    print(f"OBS processes_changed={changed}")
    print("OK gui_layout: capture_on=1 services_active=1 settings_same=1 files=5")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print(f"STOP gui_layout stage={STAGE}")
        sys.exit(2)
