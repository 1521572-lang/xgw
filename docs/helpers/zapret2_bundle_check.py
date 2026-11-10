#!/usr/bin/env python3
"""Приёмка комплекта без запуска очереди и изменения конфигурации шлюза."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


def run(args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError("command_failed")
    return result.stdout


def snapshot():
    from xgw.config import load
    from xgw.paths import Paths
    from xgw.zapret2 import UNIT, Runtime, active

    paths = Paths.from_env()
    cfg, warnings = load(paths.config_file)
    status = json.loads(run(["xgw", "status", "--json"]))
    applied = json.loads(paths.xray_config_file.read_text())
    state = (status.get("zapret2") or {}).get("state")
    proc = subprocess.run(["systemctl", "show", UNIT, "-p", "MainPID", "--value"],
                          text=True, capture_output=True, timeout=10)
    worker = proc.stdout.strip()  # transient unit после off может уже отсутствовать
    if proc.returncode not in (0, 1):
        raise ValueError("worker_state_unavailable")
    if (cfg.zapret2.mode != "off" or state != "off" or warnings or active(applied)
            or Runtime.occupied(cfg.zapret2.queue_num) or worker not in ("", "0")
            or (status.get("capture") or {}).get("mode") != "on"):
        raise ValueError("baseline_not_ready")
    pids = [run(["systemctl", "show", unit, "-p", "MainPID", "--value"]).strip()
            for unit in ("xgw-xray.service", "xgw-singbox.service")]
    if any(not pid.isdigit() or int(pid) == 0 for pid in pids):
        raise ValueError("core_not_running")
    return {"config": hashlib.sha256(paths.config_file.read_bytes()).hexdigest(), "pids": pids}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("before", "check", "finish"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise ValueError("root_required")
    if args.action == "check":
        from xgw.zapret2_bundle import validate

        if args.bundle is None:
            raise ValueError("bundle_required")
        data = validate(args.bundle)
        binary = args.bundle / "nfqws2"
        lua = args.bundle / "lua"
        run([str(binary), "--version"])
        run([str(binary), "--intercept=0", "--lua-init=@" + str(lua / "zapret-lib.lua"),
             "--lua-init=@" + str(lua / "zapret-antidpi.lua")])
        print(f"CHECK files={len(data['files'])} hashes_ok=1 lua_ok=1")
        print("RESULT bundle_ok")
        return
    current = snapshot()
    if args.action == "before":
        fd = os.open(args.state, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(current, stream)
        print("RESULT baseline_ok")
    else:
        if current != json.loads(args.state.read_text()):
            raise ValueError("state_changed")
        print("CHECK config_same=1 cores_same=1 capture_on=1 mode_off=1")
        print("RESULT rollback_ok")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        print("STOP bundle_check_failed")
        sys.exit(2)
