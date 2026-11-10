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


def snapshot(*, include_comparison=False):
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
    if state not in ("off", "unknown", "preparing", "active", "fallback", "blocked", "compared"):
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
    result = {
        "state": state, "route": zapret2.active(applied), "queue": queue, "lease": bool(lease),
        "xray_pid": pid("xgw-xray.service"), "worker_pid": pid(zapret2.UNIT),
        "protected": digest, "warnings": len(warnings),
        "capture_on": (status.get("capture") or {}).get("mode") == "on",
        "zapret_bytes": total,
    }
    if include_comparison:
        result["comparison"] = view.get("probes", [])
        result["reason"] = view.get("reason", "")
        result["trace"] = view.get("trace", {})
    return result


def show(value, baseline=None):
    fields = [f"state={value['state']}", f"route={int(value['route'])}",
              f"queue={int(value['queue'])}", f"lease={int(value['lease'])}",
              f"capture_on={int(value['capture_on'])}", f"warnings={value['warnings']}"]
    fields.append(f"zapret_bytes={value['zapret_bytes']}")
    if baseline:
        fields += [f"xray_same={int(value['xray_pid'] == baseline['xray_pid'])}",
                   f"protected_same={int(value['protected'] == baseline['protected'])}"]
    print("CHECK " + " ".join(fields), flush=True)


def trace_report(value):
    fields = ("queue_packets", "hello", "send_calls", "send_ok", "applied", "lua_errors")
    trace = value.get("trace") or {}
    state = trace.get("state", "unavailable")
    if (state not in ("observed", "incomplete", "unavailable")
            or any(type(trace.get(key, -1)) is not int or trace.get(key, -1) < -1
                   for key in fields)):
        raise ValueError("invalid_trace")
    print("TRACE state=" + state + " " + " ".join(
        f"{key}={trace.get(key, -1)}" for key in fields), flush=True)


def compare_report(value):
    rows = value["comparison"]
    if not isinstance(rows, list) or len(rows) > 4:
        raise ValueError("invalid_comparison")
    kinds = {"ok", "connect", "proxy", "tls", "http", "stall", "truncated", "timeout",
             "reset", "io", "cancelled"}
    pairs = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid_comparison")
        n, path = row["probe"], row["path"]
        phase, kind, ok = row["phase"], row["kind"], row["ok"]
        http, connect, size = row["http"], row["connect_http"], row["bytes"]
        if (type(n) is not int or n not in (1, 2) or path not in ("vpn", "zapret2")
                or phase not in ("connect", "tls", "request", "headers", "body")
                or kind not in kinds or type(ok) is not bool
                or any(type(code) is not int or not 0 <= code <= 599 for code in (http, connect))
                or type(size) is not int or size < 0 or (n, path) in pairs):
            raise ValueError("invalid_comparison")
        pairs.add((n, path))
        hops, redirect = row.get("redirects", 0), row.get("redirect", "none")
        if (type(hops) is not int or not 0 <= hops <= 5
                or redirect not in ("none", "followed", "blocked", "loop", "limit",
                                    "hop_limit", "time_limit")):
            raise ValueError("invalid_redirect")
        print(f"PROBE n={n} path={path} phase={phase} kind={kind} http={http} "
              f"connect_http={connect} bytes={size} ok={int(ok)} "
              f"redirects={hops} redirect={redirect}", flush=True)
    trace_report(value)
    stopped = not (value["queue"] or value["lease"] or value["worker_pid"])
    complete = (len(pairs) == 4 and value["reason"] == "comparison_done"
                and value["state"] == "compared" and stopped)
    reason = value["reason"]
    if not complete and reason in (
        "comparison_cleanup_failed", "comparison_incomplete", "waiting_for_probe_urls",
        "dependency_missing", "worker_down", "runtime_failed", "probe_budget", "apply_failed",
        "queue_busy", "unsafe_files", "unsafe_directory", "stop_failed",
    ):
        print(f"CHECK comparison_reason={reason}", flush=True)
    print("RESULT " + ("comparison_done" if complete else "comparison_incomplete"))
    return 0 if complete else 4


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("before", "inspect", "watch", "finish", "compare",
                                          "selftest"))
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=180)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError("root_required")
    if not 1 <= args.seconds <= 600:
        raise RuntimeError("bad_duration")
    if args.action == "selftest":
        from xgw import zapret2
        from xgw.config import load
        from xgw.paths import Paths
        from xgw.zapret2_trace import SELFTEST

        cfg, warnings = load(Paths.from_env().config_file)
        if warnings or cfg.zapret2.mode != "off":
            raise RuntimeError("baseline_not_ready")
        cfg.zapret2.mode = "compare"  # только объект в памяти
        output = run([*zapret2.arguments(cfg), "--lua-init=" + SELFTEST, "--intercept=0"], 15)
        if "LUA: XGW_Z2_SELFTEST OK" not in output.splitlines():
            raise RuntimeError("selftest_failed")
        print("RESULT trace_selftest_ok", flush=True)
        return 0
    if args.action == "before":
        value = snapshot()
        if (value["route"] or value["queue"] or value["lease"] or value["worker_pid"]
                or not value["capture_on"] or not value["xray_pid"]):
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
        value = snapshot(include_comparison=args.action == "compare")
        show(value, baseline)
        if args.action == "compare":
            if (value["route"] or not value["capture_on"]
                    or value["xray_pid"] != baseline["xray_pid"]
                    or value["protected"] != baseline["protected"]):
                print("STOP comparison_guard")
                return 2
            if value["state"] in ("compared", "blocked", "fallback"):
                return compare_report(value)
        if args.action not in ("watch", "compare") or time.monotonic() >= deadline:
            break
        time.sleep(min(15, max(0, deadline - time.monotonic())))
    if args.action == "compare":
        print("RESULT comparison_incomplete")
        return 4
    if args.action == "finish":
        ok = (value["state"] == "off" and not value["route"] and not value["queue"]
              and not value["worker_pid"] and not value["lease"] and value["capture_on"]
              and value["xray_pid"] == baseline["xray_pid"]
              and value["protected"] == baseline["protected"])
        print("RESULT " + ("rollback_ok" if ok else "rollback_failed"))
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, KeyError, TypeError, ValueError, RuntimeError, subprocess.SubprocessError):
        print("STOP helper_failed", flush=True)
        sys.exit(2)
