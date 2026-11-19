"""Read-only observations for the Ubuntu gateway audit. Emit aggregates only."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
import tomllib
from pathlib import Path


def read_command(*argv):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=8)
    return p.stdout if p.returncode == 0 else None


def unit(name):
    props = "LoadState,ActiveState,MainPID,InvocationID,CapabilityBoundingSet"
    data = read_command("systemctl", "show", name, "--property=" + props)
    if data is None:
        return {"load": "unknown"}
    values = dict(line.split("=", 1) for line in data.splitlines() if "=" in line)
    row = {"load": values.get("LoadState"), "active": values.get("ActiveState"),
           "pid": int(values.get("MainPID") or 0), "invocation": values.get("InvocationID")}
    caps = values.get("CapabilityBoundingSet", "").lower().split()
    row["bounded_net_admin"] = "cap_net_admin" in caps
    row["bounded_net_raw"] = "cap_net_raw" in caps
    if row["pid"]:
        try:
            fields = dict(line.split(":", 1) for line in
                          Path(f"/proc/{row['pid']}/status").read_text().splitlines())
            row["euid"] = int(fields["Uid"].split()[1])
            row["effective_caps_hex"] = fields["CapEff"].strip()
        except (OSError, KeyError, ValueError):
            row["effective_caps_hex"] = None
    return row


def snapshot():
    with Path("/etc/xgw/config.toml").open("rb") as stream:
        cfg = tomllib.load(stream)
    cap = cfg.get("capture", {})
    proxy, bypass = (int(cap.get(k, v)) for k, v in (("mark_proxy", 1), ("mark_bypass", 2)))
    services = {name: unit(name + ".service") for name in
                ("xgw", "xgw-xray", "xgw-singbox", "xgw-nfqws2", "xgw-zapret2")}
    listeners = {}
    for role, port in (("panel", cfg.get("panel", {}).get("port", 8781)),
                       ("status", 8780)):
        text = read_command("ss", "-Hlnpt", "sport", "=", f":{int(port)}")
        pid = services["xgw"].get("pid")
        listeners[role] = {"listening": bool(text) if text is not None else None,
                           "daemon_owns": (f"pid={pid}," in text if text and pid else None)}
    net = cfg.get("network", {})
    devs = {str(net.get("wan_if") or "__wan"): "wan",
            str(cap.get("tun_name") or "xgwtun0"): "tun", "lo": "lo"}
    routes = {}
    for label, mark in (("proxy", proxy), ("bypass", bypass),
                        ("proxy_extra", proxy | 0x20000000), ("selected", 0x10000000)):
        # FIB lookups only. Do not open a socket or publish the selected source address.
        result = read_command("ip", "-4", "-j", "route", "get", "1.1.1.1", "mark", hex(mark))
        if result:
            row = json.loads(result)[0]
            routes[label] = {"dev_class": devs.get(row.get("dev"), "other"),
                             "table": row.get("table", "main"), "type": row.get("type", "unicast")}
        else:
            routes[label] = None
    rules = read_command("ip", "-4", "-j", "rule", "show")
    earlier = None if rules is None else [
        {"pref": int(r["priority"]), "selectors": sorted(r.keys())}
        for r in json.loads(rules) if 0 < int(r.get("priority", 0)) < 100
    ]
    print(json.dumps({"units": services, "listeners": listeners, "fib": routes,
                      "before_100_including_own": earlier}, sort_keys=True))


def watchdog(seconds):
    deadline = time.monotonic() + seconds
    steps = {}
    misses = 0
    max_age = None
    samples = 0
    while True:
        try:
            row = json.loads(Path("/run/xgw/watchdog-step.json").read_bytes())
            now = time.monotonic()
            age = now - float(row["at"])
            if not math.isfinite(age) or age < 0:
                raise ValueError("clock")
            max_age = max(max_age or 0, age)
            samples += 1
            if row.get("phase") == "sleep" and isinstance(row.get("step_s"), (int, float)):
                steps[row["started"]] = row["step_s"]
        except (OSError, KeyError, ValueError, TypeError):
            misses += 1
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(1, remaining))
    values = sorted(steps.values())
    print(json.dumps({"seconds": seconds, "samples": samples, "missing": misses,
                      "distinct_completed_steps": len(values),
                      "max_record_age_s": round(max_age, 2) if max_age is not None else None,
                      "step_max_s": values[-1] if values else None,
                      "step_p95_s": values[math.ceil(len(values) * .95) - 1] if values else None}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snapshot", "watchdog"))
    parser.add_argument("--seconds", type=int, choices=range(5, 301), default=180,
                        metavar="5..300")
    args = parser.parse_args()
    if args.action == "snapshot":
        snapshot()
    else:
        watchdog(args.seconds)
