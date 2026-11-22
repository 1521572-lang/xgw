"""Read-only observations for the Ubuntu gateway audit. Emit aggregates only."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
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


def wake_sample(row, begin, measured_at):
    generation, wake = row.get("generation"), row.get("wake")
    if type(generation) is not int or not isinstance(wake, dict):
        return None
    sequence, handled, received = (wake.get(key) for key in
                                   ("sequence", "handling_at", "received"))
    if (type(sequence) is not int or sequence < 1 or not isinstance(received, dict)
            or type(handled) not in (int, float) or not begin <= handled <= measured_at):
        return None
    delays = {}
    for reason in ("net", "sleep", "rules"):
        at = received.get(reason)
        if type(at) in (int, float) and begin <= at <= handled:
            delays[reason] = handled - at
    return ((generation, sequence), delays) if delays else None


def watchdog(seconds):
    begin = time.monotonic()
    deadline = begin + seconds
    steps = {}
    wakes = {}
    wake_available = False
    misses = 0
    max_age = None
    samples = 0
    while True:
        try:
            row = json.loads(Path("/run/xgw/watchdog-step.json").read_bytes())
            if not isinstance(row, dict):
                raise ValueError("format")
            now = time.monotonic()
            age = now - float(row["at"])
            if not math.isfinite(age) or age < 0:
                raise ValueError("clock")
            max_age = max(max_age or 0, age)
            samples += 1
            recorded_at = float(row["at"])
            generation = row.get("generation")
            started, duration = row.get("started"), row.get("step_s")
            if (row.get("phase") == "sleep" and type(started) in (int, float)
                    and type(duration) in (int, float) and duration >= 0
                    and begin <= started + duration <= recorded_at):
                key = (generation if type(generation) is int else None, started)
                steps[key] = duration
            wake_available |= type(row.get("generation")) is int and "wake" in row
            if sample := wake_sample(row, begin, recorded_at):
                key, delays = sample
                wakes[key] = delays
        except (OSError, KeyError, ValueError, TypeError):
            misses += 1
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(1, remaining))
    values = sorted(steps.values())
    by_reason = {}
    for reason in ("net", "sleep", "rules"):
        delays = [sample[reason] for sample in wakes.values() if reason in sample]
        if delays:
            by_reason[reason] = {"count": len(delays), "max_s": round(max(delays), 4)}
    if wake_available:
        wake_state = "observed" if wakes else "not_observed"
    else:
        wake_state = "not_instrumented" if samples else "unavailable"
    print(json.dumps({"seconds": seconds, "samples": samples, "missing": misses,
                      "distinct_completed_steps": len(values),
                      "max_record_age_s": round(max_age, 2) if max_age is not None else None,
                      "step_max_s": values[-1] if values else None,
                      "step_p95_s": values[math.ceil(len(values) * .95) - 1] if values else None,
                      "wake": {"available": wake_available, "state": wake_state,
                               "observed_batches": len(wakes),
                               "by_reason": by_reason}}))


def desync():
    sys.path.insert(0, "/opt/xgw/lib")
    from xgw import config, zapret2
    from xgw.desync import worker
    from xgw.net import cmd, nft
    from xgw.paths import Paths
    from xgw.watch import status, zapret2_control

    started = time.time()
    paths = Paths.from_env({})
    cfg, _ = config.load(paths.config_file)
    snap = status.read_status(paths, float("inf")) or {}
    policy = worker.policy_revision(cfg.zapret2)
    age = started - snap.get("updated", 0)
    units = {name: unit(name) for name in (worker.SELECTED_UNIT, worker.ENGINE_UNIT)}
    try:
        queues = [row.split() for row in worker.QUEUE_STATE.read_text().splitlines()]
    except OSError:
        queues = None
    for name, number in ((worker.SELECTED_UNIT, cfg.zapret2.queue_num),
                         (worker.ENGINE_UNIT, cfg.zapret2.engine_queue)):
        row = next((r for r in queues or [] if r and r[0] == str(number)), None)
        units[name].update(queue=number, listed=row is not None if queues is not None else None,
                           seq=int(row[7]) if row and len(row) > 7 else None,
                           owner_verified=worker.verify_owner(cmd.run, name, number))
    raw = read_command("nft", "-a", "-j", "list", "table", "inet", nft.GUARD)
    gate_size = None
    counters = {}
    if raw is not None:
        for entry in json.loads(raw)["nftables"]:
            for kind in ("set", "element"):
                group = entry.get(kind, {})
                if group.get("name") == zapret2.LIVE:
                    gate_size = len(group.get("elem", []))
            rule = entry.get("rule", {})
            expr = rule.get("expr", [])
            if any("queue" in e for e in expr):
                key = f"{rule['chain']}.{rule['handle']}"
                packets = (e["counter"]["packets"] for e in expr if "counter" in e)
                counters[key] = next(packets, None)
    lease = snap.get("zapret2_reservation") or {}
    print(json.dumps({"at": started, "span_s": round(time.time() - started, 2),
                      "mode": cfg.zapret2.mode, "engine": cfg.zapret2.engine,
                      "daemon": unit("xgw.service"), "status_at": snap.get("updated"),
                      "policy_key": policy,
                      "policy_match": bool(policy and snap.get("zapret2_policy_key") == policy),
                      "fresh": 0 <= age <= zapret2_control.FRESH_SECONDS,
                      "reservation": lease.get("unit"), "units": units,
                      "guard_read": raw is not None, "gate_elements": gate_size,
                      "queue_counters": counters}, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snapshot", "watchdog", "desync"))
    parser.add_argument("--seconds", type=int, choices=range(5, 601), default=180,
                        metavar="5..600")
    args = parser.parse_args()
    if args.action == "snapshot":
        snapshot()
    elif args.action == "desync":
        desync()
    else:
        watchdog(args.seconds)
