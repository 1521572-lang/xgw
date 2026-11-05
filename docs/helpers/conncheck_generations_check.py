"""Значок связности и причины смены поколений sing-box на ThinkCentre. Печатает только числа.

health      — шлюз в порядке (как в ТЗ c05-scan-bytes);
conncheck   — исключение для проверки связности NetworkManager: файл адресов, правило в
              барьере, запрос, привязанный к WAN (как делает NetworkManager), и итог
              `nmcli networking connectivity check`;
generations — смены поколения sing-box за сутки и их причины (`xgw singbox status`).
"""

import json
import subprocess
import sys
from pathlib import Path

FILE = Path("/run/xgw/conncheck.json")


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


def text(argv, timeout=30):
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout.strip()


def wan_device():
    _rc, out = text(["ip", "-o", "route", "get", "1.1.1.1"])
    words = out.split()
    return words[words.index("dev") + 1] if "dev" in words else ""


def conncheck(report):
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    ips, port, host = data.get("ips") or [], int(data.get("port") or 0), data.get("host") or ""
    report.update(file=bool(data), ips=len(ips), port=port)
    _rc, guard = text(["nft", "list", "chain", "inet", "xgw_guard", "output"])
    rule = [line for line in guard.splitlines() if "skuid" in line and f"dport {port}" in line
            and all(ip in line for ip in ips[:1])]
    report["guard_rule"] = bool(rule and ips)
    device = wan_device()
    report["wan_found"] = bool(device)
    code = 0
    if host and device:
        _rc, out = text(["curl", "--silent", "--interface", device, "--max-time", "10", "-o",
                         "/dev/null", "-w", "%{http_code}", f"http://{host}/"], timeout=20)
        code = int(out) if out.isdigit() else 0
    report["bound_http"] = code
    _rc, state = text(["nmcli", "networking", "connectivity", "check"], timeout=60)
    report["nm_connectivity"] = state if state in ("full", "limited", "portal", "none",
                                                   "unknown") else "other"
    return (report["file"] and report["guard_rule"] and 200 <= code < 400
            and report["nm_connectivity"] == "full")


def generations(report):
    rc, out = text(["xgw", "singbox", "status"])
    data = json.loads(out) if rc == 0 and out else {}
    report.update({key: data.get(key) for key in (
        "active", "draining", "pending", "identity_ok", "switches_24h",
        "switch_reasons_24h", "last_switch_parts")})
    return rc == 0 and data.get("switches_24h") is not None


if __name__ == "__main__":
    record = {}
    try:
        mode = sys.argv[1:]
        if mode == ["health"]:
            passed = health()
            record["health"] = passed
        elif mode == ["conncheck"]:
            passed = conncheck(record)
        elif mode == ["generations"]:
            passed = generations(record)
        else:
            raise ValueError
    except Exception as exc:
        passed = False
        record["reason"] = type(exc).__name__
    print(json.dumps(record, ensure_ascii=False))
    sys.exit(0 if passed else 3)
