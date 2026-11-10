#!/usr/bin/env python3
"""Сверка файлов окна и состояния шлюза до и после просмотра раздела."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SOURCE))
FILES = {
    "devices": ("devices.py", "listing.py", "window.py"),
    "traffic": ("client.py", "listing.py", "traffic.py", "window.py"),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def snapshot(paths):
    from xgw.managed import path_for

    status = json.loads(paths.status_file.read_text())
    if status.get("state") != "HEALTHY" or (status.get("capture") or {}).get("mode") != "on":
        raise ValueError("health")
    units = []
    for service in ("xgw.service", "xgw-xray.service", "xgw-singbox.service"):
        proc = subprocess.run(
            ["systemctl", "show", service, "-p", "ActiveState", "-p", "MainPID"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        units.append(dict(line.split("=", 1) for line in proc.stdout.splitlines()))
    if any(unit["ActiveState"] != "active" or int(unit["MainPID"]) <= 0 for unit in units[:2]):
        raise ValueError("service")
    return {"config": digest(paths.config_file), "managed": digest(path_for(paths.config_file)),
            "units": units}


def main():
    from xgw.paths import Paths

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("before", "after"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--section", choices=FILES, default="devices")
    args = parser.parse_args()
    paths = Paths.from_env()
    data = snapshot(paths)
    if args.action == "before":
        fd = os.open(args.state, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
        print("RESULT baseline_ok")
        return
    if data != json.loads(args.state.read_text()):
        raise ValueError("state")
    for name in FILES[args.section]:
        expected = digest(SOURCE / "xgw/gui" / name)
        if expected is None or digest(paths.lib_dir / "xgw/gui" / name) != expected:
            raise ValueError("files")
    print("CHECK healthy=1 capture_on=1 daemon_same=1 cores_same=1 settings_same=1 "
          f"gui_files={len(FILES[args.section])}")
    print(f"RESULT gui_{args.section}_ok")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print("STOP gui_check_failed")
        sys.exit(2)
