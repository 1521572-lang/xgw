#!/usr/bin/env python3
"""Сводка приёмки zapret2. Читает состояние, не меняет конфиг, сеть или службы."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


def run(args, timeout=60):
    proc = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if proc.returncode:
        raise RuntimeError("command_failed")
    return proc.stdout


def pid(unit):
    proc = subprocess.run(["systemctl", "show", unit, "-p", "MainPID", "--value"],
                          text=True, capture_output=True, timeout=10)
    value = proc.stdout.strip()
    return int(value) if value.isdigit() else 0


def snapshot():
    from xgw import zapret2
    from xgw.config import load
    from xgw.paths import Paths
    from xgw.xraycore import metrics

    paths = Paths.from_env()
    cfg, warnings = load(paths.config_file)
    status = json.loads(run(["xgw", "status", "--json"]))
    applied = json.loads(paths.xray_config_file.read_text())
    # Только сумма защищённых разделов, их значения никуда не пишутся.
    sections = dataclasses.asdict(cfg)
    sections.pop("zapret2")
    digest = hashlib.sha256(json.dumps(sections, sort_keys=True).encode()).hexdigest()
    view = status.get("zapret2") or {}
    state = str(view.get("state", "unknown"))
    if state not in ("off", "unknown", "preparing", "active", "fallback", "blocked"):
        state = "unknown"
    queue = zapret2.Runtime.occupied(cfg.zapret2.queue_num)
    counters = (metrics.fetch_metrics(cfg.xray.metrics_port).get("stats") or {}).get(
        "outbound", {}).get(zapret2.OUT) or {}
    total = sum(v for v in counters.values() if isinstance(v, int) and not isinstance(v, bool))
    # Проверяем наличие lease по JSON, не печатаем nft-вывод.
    proc = subprocess.run(["nft", "-j", "list", "set", "inet", "xgw_guard", zapret2.LIVE],
                          text=True, capture_output=True, timeout=10)
    lease = False
    if proc.returncode == 0:
        data = json.loads(proc.stdout)
        lease = any(entry.get("set", {}).get("elem") for entry in data.get("nftables", []))
    return {
        "state": state, "route": zapret2.active(applied), "queue": queue, "lease": bool(lease),
        "xray_pid": pid("xgw-xray.service"), "worker_pid": pid(zapret2.UNIT),
        "protected": digest, "warnings": len(warnings),
        "capture_on": (status.get("capture") or {}).get("mode") == "on",
        "zapret_bytes": total,
    }


def show(value, baseline=None):
    fields = [f"state={value['state']}", f"route={int(value['route'])}",
              f"queue={int(value['queue'])}", f"lease={int(value['lease'])}",
              f"capture_on={int(value['capture_on'])}", f"warnings={value['warnings']}"]
    fields.append(f"zapret_bytes={value['zapret_bytes']}")
    if baseline:
        fields += [f"xray_same={int(value['xray_pid'] == baseline['xray_pid'])}",
                   f"protected_same={int(value['protected'] == baseline['protected'])}"]
    print("CHECK " + " ".join(fields), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("before", "inspect", "watch", "finish"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=180)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError("root_required")
    if not 1 <= args.seconds <= 600:
        raise RuntimeError("bad_duration")
    if args.action == "before":
        value = snapshot()
        if value["route"] or not value["capture_on"] or not value["xray_pid"]:
            raise RuntimeError("baseline_not_ready")
        fd = os.open(args.state, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as out:
            json.dump(value, out)
        show(value)
        print("OK baseline")
        return 0
    baseline = json.loads(args.state.read_text())
    deadline = time.monotonic() + args.seconds
    while True:
        value = snapshot()
        show(value, baseline)
        if args.action != "watch" or time.monotonic() >= deadline:
            break
        time.sleep(min(15, max(0, deadline - time.monotonic())))
    if args.action == "finish":
        ok = (not value["route"] and not value["worker_pid"] and not value["lease"]
              and value["capture_on"] and value["protected"] == baseline["protected"])
        print("RESULT " + ("rollback_ok" if ok else "rollback_failed"))
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        print("STOP helper_failed", flush=True)
        sys.exit(2)
