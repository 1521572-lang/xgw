"""Приватные снимки маршрута и байтов. Не делает запросов к YouTube или VPN."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))


def pid(unit):
    result = subprocess.run(["systemctl", "show", unit, "-p", "MainPID", "--value"],
                            capture_output=True, text=True, timeout=10)
    return int(result.stdout.strip()) if result.stdout.strip().isdigit() else 0


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def snapshot():
    from xgw import zapret2
    from xgw.config import load
    from xgw.paths import Paths
    from xgw.xraycore import metrics

    paths = Paths.from_env()
    cfg, warnings = load(paths.config_file)
    current = json.loads(paths.xray_config_file.read_text())
    status = json.loads(paths.status_file.read_text())
    raw = status.get("zapret2") or {}
    capture = status.get("capture") or {}
    data = metrics.fetch_metrics(cfg.xray.metrics_port)
    counters = (data.get("stats") or {}).get("outbound") or {}
    count = counters.get(zapret2.OUT) or {}
    safe_tags = {"direct", "block", "dns-out", "api", "metrics", zapret2.OUT, zapret2.DIRECT}
    vpn_bytes = sum(int(row.get("uplink", 0)) + int(row.get("downlink", 0))
                    for tag, row in counters.items() if tag not in safe_tags)
    no_vpn = (zapret2.standalone(current) and not current.get("burstObservatory")
              and not current.get("routing", {}).get("balancers")
              and all(o.get("protocol") in ("freedom", "blackhole", "dns")
                      and o.get("tag") in safe_tags for o in current["outbounds"]))
    result = subprocess.run(["nft", "-j", "list", "set", "inet", "xgw_guard", zapret2.LIVE],
                            capture_output=True, text=True, timeout=10)
    lease = False
    if result.returncode == 0:
        lease = any(row.get("set", {}).get("elem")
                    for row in json.loads(result.stdout).get("nftables", []))
    bridges = sum(pid(unit) > 0 for unit in (
        "xgw-singbox.service", "xgw-singbox-blue.service", "xgw-singbox-green.service"))
    worker = pid(zapret2.UNIT)
    fresh = (0 <= time.time() - status.get("updated", 0) <= 90
             and raw.get("config_key") == zapret2.config_key(cfg))
    ready = (no_vpn and cfg.zapret2.mode == "standalone" and fresh
             and raw.get("without_vpn") and raw.get("state") == "active"
             and capture.get("mode") == "on" and capture.get("loaded") is True
             and not capture.get("capture_failed") and not capture.get("inbound_missing")
             and lease and worker > 0 and bridges == 0
             and zapret2.Runtime.occupied(cfg.zapret2.queue_num))
    return {
        "utc": datetime.now(UTC).isoformat(), "mode": cfg.zapret2.mode,
        "strategy": cfg.zapret2.strategy, "fresh": fresh, "ready": bool(ready),
        "without_vpn_config": no_vpn, "vpn_bridges": bridges, "lease": bool(lease),
        "queue": zapret2.Runtime.occupied(cfg.zapret2.queue_num),
        "worker_pid": worker, "xray_pid": pid("xgw-xray.service"),
        "config_digest": digest(current), "warnings": len(warnings),
        "upload": int(count.get("uplink", 0)), "download": int(count.get("downlink", 0)),
        "vpn_bytes": vpn_bytes, "capture_on": capture.get("mode") == "on",
    }


def delta(before, after):
    up, down = after["upload"] - before["upload"], after["download"] - before["download"]
    stable = all(before[key] == after[key] for key in (
        "config_digest", "worker_pid", "xray_pid", "strategy"))
    direct = (before["ready"] and after["ready"] and stable and up > 0
              and down >= 2 * 1024 * 1024 and after["vpn_bytes"] == before["vpn_bytes"] == 0)
    return {"utc": after["utc"], "stable": stable, "upload_delta": up,
            "download_delta": down, "vpn_delta": after["vpn_bytes"] - before["vpn_bytes"],
            "direct_data_confirmed": direct,
            "playback": "requires_visual_observation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    one = sub.add_parser("snapshot")
    one.add_argument("output", type=Path)
    pair = sub.add_parser("delta")
    pair.add_argument("before", type=Path)
    pair.add_argument("after", type=Path)
    args = parser.parse_args()
    if args.action == "snapshot":
        value = snapshot()
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, sort_keys=True)
    else:
        value = delta(json.loads(args.before.read_text()), json.loads(args.after.read_text()))
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        print("STOP snapshot_failed; details stay private", file=sys.stderr)
        raise SystemExit(1) from None
