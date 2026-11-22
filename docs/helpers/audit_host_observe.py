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

STEP_PARTS = (
    "первая сборка конфига", "сигналы ядра", "белый список", "списки бесплатного пула",
    "перехват и конфиг", "устройства и сервер пула", "подписка и сборка конфига", "сканы и замены",
    "основной сервер и замеры подписки", "замер пула и YouTube", "ядра и сеть", "запись состояния",
)
STEP_DETAILS = (
    "core_metrics", "core_api", "provider_check", "end_to_end", "leak_probe", "probe_target",
    "provider_resolve", "provider_connect", "e2e_primary", "e2e_fallback", "e2e_reserve",
    "scan_queue", "rotation", "rebalance", "reserve_selection", "profile_checks",
)


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


def step_timings(raw, names, duration):
    timings = {}
    if isinstance(raw, dict):
        for name in names:
            value = raw.get(name)
            if type(value) in (int, float) and 0 <= value <= duration:
                timings[name] = value
    return timings


def completed_step(row, begin, measured_at):
    generation = row.get("generation")
    if type(generation) is int and isinstance(step := row.get("last_step"), dict):
        sequence, started, ended = (step.get(key) for key in ("sequence", "started", "completed_at"))
        if (type(sequence) is not int or sequence < 1 or type(started) not in (int, float)
                or type(ended) not in (int, float) or not math.isfinite(started) or started > ended
                or not begin <= ended <= measured_at):
            return None
        duration = ended - started
        parts = step_timings(step.get("parts_s"), STEP_PARTS, duration)
        return (generation, sequence), duration, parts
    started, duration = row.get("started"), row.get("step_s")
    if (row.get("phase") == "sleep" and type(started) in (int, float)
            and type(duration) in (int, float) and duration >= 0
            and begin <= started + duration <= measured_at):
        return (generation if type(generation) is int else None, started), duration, {}
    return None


def watchdog(seconds):
    begin = time.monotonic()
    deadline = begin + seconds
    steps = {}
    step_sequences = {}
    part_max = {}
    detail_times = {}
    scan_deferrals = {}
    scan_slot_deferrals = {}
    queue_probes = {}
    provider_attempts = {}
    intervals = set()
    wakes = {}
    wake_overlaps = {}
    checks = {}
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
            interval = row.get("interval_s")
            if type(interval) is int and interval >= 0:
                intervals.add(interval)
            if sample := completed_step(row, begin, recorded_at):
                key, duration, parts = sample
                steps[key] = duration
                if type(key[0]) is int and isinstance(row.get("last_step"), dict):
                    generation, sequence = key
                    step_sequences.setdefault(generation, set()).add(sequence)
                    step = row["last_step"]
                    deferred = step.get("planned_scan_deferred")
                    if type(deferred) is bool:
                        scan_deferrals[key] = deferred
                    deferred_for_step = step.get("scan_deferred_for_step")
                    if type(deferred_for_step) is bool:
                        scan_slot_deferrals[key] = deferred_for_step
                    count = step.get("queue_probe_count")
                    if type(count) is int and count >= 0:
                        queue_probes[key] = count
                    attempts = step.get("provider_attempts")
                    if type(attempts) is int and attempts >= 0:
                        provider_attempts[key] = attempts
                    details = step_timings(step.get("details_s"), STEP_DETAILS, duration)
                    for name, value in details.items():
                        detail_times.setdefault(name, {})[key] = value
                for name, value in parts.items():
                    part_max[name] = max(part_max.get(name, 0), value)
            wake_available |= type(row.get("generation")) is int and "wake" in row
            if sample := wake_sample(row, begin, recorded_at):
                key, delays = sample
                wakes[key] = delays
                wake = row["wake"]
                overlap = wake.get("last_step_overlap_s")
                if isinstance(overlap, dict):
                    wake_overlaps[key] = {}
                    for reason, delay in delays.items():
                        span = overlap.get(reason)
                        if type(span) in (int, float) and 0 <= span <= delay:
                            wake_overlaps[key][reason] = span
                check = wake.get("rules_check_s")
                if ("rules" in delays and type(check) in (int, float)
                        and 0 <= check <= recorded_at - wake["handling_at"]):
                    checks[key] = check
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
            overlaps = [sample[reason] for sample in wake_overlaps.values() if reason in sample]
            if overlaps:
                by_reason[reason]["last_step_overlap"] = {
                    "count": len(overlaps), "max_s": round(max(overlaps), 4),
                }
    wake_details = {}
    if checks:
        wake_details["rules_check"] = {"count": len(checks), "max_s": round(max(checks.values()), 4)}
    if wake_available:
        wake_state = "observed" if wakes else "not_observed"
    else:
        wake_state = "not_instrumented" if samples else "unavailable"
    skipped = sum(max(seq) - min(seq) + 1 - len(seq) for seq in step_sequences.values())
    step_details = {}
    for name, timings in detail_times.items():
        durations = sorted(timings.values())
        step_details[name] = {
            "steps": len(durations), "max_s": round(durations[-1], 4),
            "p50_s": round(durations[math.ceil(len(durations) / 2) - 1], 4),
            "p95_s": round(durations[math.ceil(len(durations) * .95) - 1], 4),
        }
    print(json.dumps({"seconds": seconds, "samples": samples, "missing": misses,
                      "configured_intervals_s": sorted(intervals),
                      "distinct_completed_steps": len(values),
                      "unseen_steps_between_samples": skipped if step_sequences else None,
                      "max_record_age_s": round(max_age, 2) if max_age is not None else None,
                      "step_max_s": values[-1] if values else None,
                      "step_p95_s": values[math.ceil(len(values) * .95) - 1] if values else None,
                      "step_part_max_s": {name: round(value, 4) for name, value in part_max.items()},
                      "step_details": step_details,
                      "planned_scan_deferred_steps": sum(scan_deferrals.values())
                      if scan_deferrals else None,
                      "scan_deferred_for_step": sum(scan_slot_deferrals.values())
                      if scan_slot_deferrals else None,
                      "queue_probes": {
                          "steps": len(queue_probes), "steps_with_probes": sum(
                              count > 0 for count in queue_probes.values()),
                          "total": sum(queue_probes.values()),
                      } if queue_probes else None,
                      "provider_attempts": {
                          "steps": len(provider_attempts), "total": sum(provider_attempts.values()),
                          "max": max(provider_attempts.values()),
                      } if provider_attempts else None,
                      "wake": {"available": wake_available, "state": wake_state,
                               "observed_batches": len(wakes),
                               "by_reason": by_reason, **wake_details}}, ensure_ascii=False))


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
