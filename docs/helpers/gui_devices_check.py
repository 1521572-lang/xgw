#!/usr/bin/env python3
"""Сверка файлов окна и состояния шлюза до и после просмотра устройств."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SOURCE))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def snapshot(paths):
    from xgw.managed import path_for

    status = json.loads(paths.status_file.read_text())
    if status.get("state") != "HEALTHY" or (status.get("capture") or {}).get("mode") != "on":
        raise ValueError("health")
    cores = []
    for service in ("xgw-xray.service", "xgw-singbox.service"):
        proc = subprocess.run(
            ["systemctl", "show", service, "-p", "ActiveState", "-p", "MainPID"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        cores.append(dict(line.split("=", 1) for line in proc.stdout.splitlines()))
    if cores[0]["ActiveState"] != "active" or int(cores[0]["MainPID"]) <= 0:
        raise ValueError("xray")
    return {"config": digest(paths.config_file), "managed": digest(path_for(paths.config_file)),
            "cores": cores}


def main():
    from xgw.paths import Paths

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("before", "after"))
    parser.add_argument("--state", type=Path, required=True)
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
    for name in ("devices.py", "listing.py", "window.py"):
        if digest(paths.lib_dir / "xgw/gui" / name) != digest(SOURCE / "xgw/gui" / name):
            raise ValueError("files")
    print("CHECK healthy=1 capture_on=1 cores_same=1 settings_same=1 gui_files=3")
    print("RESULT gui_devices_ok")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print("STOP gui_devices_check_failed")
        sys.exit(2)
