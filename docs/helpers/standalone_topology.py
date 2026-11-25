"""Observe the sing-box topology during the bounded Standalone return trial."""

import argparse
import json
import subprocess
import time
from pathlib import Path

from xgw.apply import singbox_process as processes

STOPPED = ("inactive", "failed")


def project(state, marker, units):
    active = state["active"]
    return {
        "active": active, "marker": marker,
        "pending": bool(state["pending"]), "draining": bool(state["draining"]),
        "resume_managed": processes.resume_requested(state),
        "stale_resume_managed": active in processes.SLOTS and state.get("resume_managed") is True,
        "standalone_stopping": state.get("standalone_stopping") is True,
        "units": units,
    }


def ready(wanted, sample):
    if wanted == "observed":
        return True
    active, units = sample["active"], sample["units"]
    if sample["pending"] or sample["standalone_stopping"]:
        return False
    if wanted in ("legacy_resume", "paused"):
        if (active != "legacy" or sample["marker"] or not sample["resume_managed"]
                or sample["draining"]):
            return False
        if wanted == "legacy_resume":
            return units.get(processes.LEGACY) == "active"
        return all(value in STOPPED for value in units.values())
    if (active not in processes.SLOTS or not sample["marker"]
            or units.get(processes.unit(active)) != "active"):
        return False
    if wanted == "managed":
        return True
    return not sample["draining"] and all(
        name == processes.unit(active) or value in STOPPED for name, value in units.items())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wanted", choices=("observed", "legacy_resume", "paused", "managed",
                                          "stable"))
    parser.add_argument("seconds", type=int, choices=range(1, 241), metavar="1..240")
    args = parser.parse_args()
    runtime = Path("/run/xgw")
    deadline = time.monotonic() + args.seconds
    last = None
    while time.monotonic() < deadline:
        listing = subprocess.check_output(
            ["systemctl", "list-units", "--type=service", "--all", "--plain", "--no-legend",
             "--no-pager", "xgw-singbox*.service"], timeout=8, text=True,
        )
        units = {row[0]: row[2] for row in map(str.split, listing.splitlines()) if len(row) >= 3}
        state = json.loads((runtime / "singbox-generations.json").read_bytes())
        sample = project(state, (runtime / "singbox-managed").is_file(), units)
        if sample != last:
            print(json.dumps(sample, sort_keys=True), flush=True)
            last = sample
        if ready(args.wanted, sample):
            return 0
        time.sleep(2)
    raise SystemExit("topology_not_confirmed")


if __name__ == "__main__":
    raise SystemExit(main())
