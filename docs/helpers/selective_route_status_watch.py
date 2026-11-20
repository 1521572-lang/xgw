"""Observe published Selective status and the applied client rule during a live test."""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter

from xgw import zapret2
from xgw.desync.route_evidence import _read_config
from xgw.paths import Paths

STATES = {"active", "pending", "preparing", "fallback", "off", "blocked", "unknown"}
REASONS = {"route_reconcile", "route_unconfirmed"}
HEALTH_PHASES = {"checks", "complete"}


def identity(path):
    info = path.stat()
    return info.st_ino, info.st_mtime_ns, info.st_size


def status_row(applied, status, status_is_newer):
    view = status.get("zapret2") or {}
    state, reason = view.get("state"), view.get("reason")
    phase = (status.get("watchdog") or {}).get("phase")
    return {
        "client_rule": zapret2.active(applied) and not zapret2.standalone(applied),
        "state": state if state in STATES else "unknown",
        "reason": reason if reason in REASONS else None,
        "phase": phase if phase in HEALTH_PHASES else None,
        "status_is_newer": status_is_newer,
    }


def observe(paths, seconds):
    config_path, status_path = paths.xray_config_file, paths.status_file
    started = time.monotonic()
    last_stamps = None
    rows = Counter()
    while time.monotonic() < started + seconds:
        try:
            stamps = identity(config_path), identity(status_path)
            if stamps != last_stamps:
                config = json.loads(_read_config(config_path))
                status = json.loads(_read_config(status_path))
                if stamps == (identity(config_path), identity(status_path)):
                    last_stamps = stamps
                    row = status_row(config, status, stamps[1][1] > stamps[0][1])
                    kind = "sample"
                    if row["status_is_newer"] and not row["client_rule"]:
                        if row["state"] == "active":
                            kind = "active_without_rule"
                        elif row["reason"] == "route_reconcile":
                            kind = "route_reconcile"
                    if row["state"] == "active" and row["client_rule"]:
                        kind = "active_with_rule"
                    rows[kind] += 1
                    print(json.dumps(dict(event=kind, elapsed_s=round(time.monotonic()-started, 3),
                                          **row)), flush=True)
        except (OSError, ValueError, AttributeError, TypeError):
            rows["unreadable"] += 1
        time.sleep(0.1)
    print(json.dumps({"event": "end", "counts": dict(rows)}), flush=True)
    return 0 if last_stamps is not None and not rows["active_without_rule"] else 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, choices=range(1, 301), metavar="1..300",
                        default=240)
    raise SystemExit(observe(Paths.from_env(), parser.parse_args().seconds))
