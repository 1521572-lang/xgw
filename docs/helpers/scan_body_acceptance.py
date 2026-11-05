"""Одна проба CLI и сверка опубликованного окна с SQLite на ThinkCentre."""

import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

STATUS = Path("/run/xgw/status.json")
DB = "file:/var/lib/xgw/state.db?mode=ro"


def health():
    proc = subprocess.run(["xgw", "status", "--json"], capture_output=True, timeout=180)
    data = json.loads(proc.stdout)
    cap = data.get("capture") or {}
    https = subprocess.run(["curl", "--silent", "--noproxy", "*", "--max-time", "60",
                            "-o", "/dev/null", "-w", "%{http_code}", "https://1.1.1.1/"],
                           capture_output=True, timeout=70)
    return (proc.returncode == 0 and data.get("daemon_down") is False
            and data.get("xray", {}).get("ok") is True and cap.get("mode") == "on"
            and cap.get("blocked") is False and cap.get("loaded") is True
            and https.returncode == 0 and https.stdout.isdigit() and 200 <= int(https.stdout) < 400)


def verify(report):
    snap = json.loads(STATUS.read_bytes())
    members = [n for n in snap["members"] if n.get("tag") and n.get("alive") is not False]
    if not members:
        report["reason"] = "NO_MEMBER"
        return False
    node = min(members, key=lambda n: n.get("cost") or 0)
    start = time.time()
    probe = subprocess.run(["xgw", "probe", node["tag"]], text=True,
                           capture_output=True, timeout=180)
    end = time.time()
    match = re.search(r"^" + re.escape(node["tag"]) + r"\s+\S+\s+(\d+) Б за ", probe.stdout, re.M)
    size = int(match[1]) if match else None
    report.update(probe_rc=probe.returncode, cli_bytes=size)
    with sqlite3.connect(DB, uri=True) as db:
        rows = db.execute("SELECT bytes FROM scan_bodies WHERE origin='cli' AND ts BETWEEN ? AND ?",
                          (start, end)).fetchall()
        report["cli_matches"] = rows == [(size,)] and size is not None
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            snap = json.loads(STATUS.read_bytes())
            actual = snap["budget"].get("scan_actual_24h") or {}
            now = actual.get("as_of", 0)
            if now >= end:
                rows = db.execute("SELECT bytes,source,quota_bytes,origin,ts FROM scan_bodies "
                                  "WHERE ts>? AND ts<=?", (now - 86400, now)).fetchall()
                quota = {}
                for _, source, billed, _, _ in rows:
                    if billed is not None and source:
                        quota[source] = quota.get(source, 0) + billed
                report.update(window_bytes=sum(r[0] for r in rows), attempts=len(rows),
                              limited_sources=len(quota), weighted_bytes=sum(quota.values()),
                              daemon_seen=any(r[3] == "daemon" and r[4] >= start for r in rows))
                report["window_matches"] = (actual["bytes"] == report["window_bytes"]
                                            and actual["attempts"] == len(rows)
                                            and actual["quota_bytes"] == quota)
                if report["window_matches"] and report["daemon_seen"]:
                    break
            time.sleep(2)
    return bool(report["cli_matches"] and size and report.get("window_matches")
                and report.get("daemon_seen"))


if __name__ == "__main__":
    record = {}
    try:
        if sys.argv[1:] == ["health"]:
            passed = health()
            record["health"] = passed
        elif sys.argv[1:] == ["verify"]:
            passed = verify(record)
        else:
            raise ValueError
    except Exception as exc:
        passed = False
        record["reason"] = type(exc).__name__
    print(json.dumps(record))
    sys.exit(0 if passed else 3)
