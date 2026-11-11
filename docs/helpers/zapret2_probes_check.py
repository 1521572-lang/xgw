#!/usr/bin/env python3
"""Read-only GUI/API handoff checks. Output contains only fixed labels and counts."""

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

FILES = ("zapret2.py", "watch/zapret2_control.py", "gui/zapret2.py")
SOURCE = Path(__file__).resolve().parents[2] / "src/xgw"
TARGET = Path("/opt/xgw/lib/xgw")
STAGE = "arguments"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def files(base):
    global STAGE
    STAGE = "files"
    for name in FILES:
        source, target = base / name, TARGET / name
        if target.is_symlink() or (target.exists() and not stat.S_ISREG(target.stat().st_mode)):
            raise ValueError("file_type")
        if digest(source) != digest(target):
            raise ValueError("base_mismatch")


def snapshot():
    global STAGE
    STAGE = "status"
    path = Path("/run/xgw/status.json")
    data = json.loads(path.read_text())
    if not 0 <= time.time() - data.get("updated", 0) <= 90:
        raise ValueError("stale")
    if (data.get("capture") or {}).get("mode") != "on":
        raise ValueError("capture")
    z = data.get("zapret2") or {}
    if z.get("state") != "off":
        raise ValueError("zapret2_not_off")
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
    sys.path.insert(0, str(TARGET.parent))
    from xgw.config import ConfigError, load

    try:
        cfg, _ = load("/etc/xgw/config.toml")
    except ConfigError:
        raise ValueError("config_unreadable") from None
    if cfg.zapret2.mode != "off":
        raise ValueError("zapret2_mode")
    config = digest(Path("/etc/xgw/config.toml"))
    if not config:
        raise ValueError("missing_config")
    return {"config": config, "managed": digest(Path("/etc/xgw/panel.json")),
            "units": units, "api_versioned": bool(z.get("config_key")),
            "pin": (data.get("pin") or {}).get("tag"),
            "pool": (data.get("free_pool") or {}).get("mode")}


def main():
    global STAGE
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("before", "after"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--base", type=Path)
    args = parser.parse_args()
    data = snapshot()
    if args.action == "before":
        if args.base is None:
            raise ValueError("base_required")
        files(args.base / "src/xgw")
        STAGE = "baseline"
        fd = os.open(args.state, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
        print("OK baseline services_active=1 capture_on=1 zapret2_off=1")
        return
    STAGE = "settings_unchanged"
    before = json.loads(args.state.read_text())
    if any(before[key] != data[key] for key in ("config", "managed", "pin", "pool")):
        raise ValueError("settings_changed")
    files(SOURCE)
    STAGE = "daemon_loaded"
    if not data["api_versioned"]:
        raise ValueError("old_daemon")
    STAGE = "core_processes"
    changed = sum(a != b for a, b in zip(before["units"][1:], data["units"][1:], strict=True))
    print(f"OBS core_processes_changed={changed}")
    if changed:
        raise ValueError("core_change_requires_review")
    print("RESULT zapret2_probes_ok settings_same=1 capture_on=1 zapret2_off=1 files=3")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError, KeyError, ImportError, subprocess.SubprocessError):
        print(f"STOP zapret2_probes stage={STAGE}")
        sys.exit(2)
