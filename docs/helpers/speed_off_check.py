"""Замеры скорости при выключенном основном сервере (ASSUMPTIONS п. 325). Только числа.

health — шлюз в порядке (как в ТЗ tspu-audit);
speed  — переключатель основного сервера, есть ли плановые замеры, сколько строк серверов
         подписки (без x100) замерено за последние 6 и 30 часов, возраст самого старого
         замера в часах, строки с прежней надписью «основной сервер выключен», закреплён ли
         основной;
pool   — режим бесплатного пула и сводка наблюдения: найдено, проверено, живых, живых со
         списков GitHub, состояние источников списков (без адресов и имён).
"""

import hashlib
import hmac
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

TOKEN = Path("/var/lib/xgw/panel-token")
OLD_NOTE = "основной сервер выключен"
LISTS = ("igareck", "mahdibland")


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


def panel(path):
    sys.path.insert(0, "/opt/xgw/lib")
    from xgw import config as xconfig

    cfg, _warnings = xconfig.load(Path("/etc/xgw/config.toml"))
    token = TOKEN.read_text(encoding="ascii").strip()
    cookie = hmac.new(token.encode(), b"xgw-panel", hashlib.sha256).hexdigest()
    headers = {"Cookie": f"xgw_panel={cookie}", "X-XGW-Panel": "1"}
    request = urllib.request.Request(f"http://127.0.0.1:{cfg.panel.port}{path}",
                                     headers=headers)
    with urllib.request.urlopen(request, timeout=30) as reply:
        return json.loads(reply.read())


def speed(report):
    state = panel("/api/state")
    sticky = state.get("sticky") or {}
    rows = [row for row in state.get("servers") or []
            if row.get("status") in ("member", "spare") and (row.get("multiplier") or 0) < 100]
    now = time.time()
    stamps = [float(row["speed_ts"]) for row in rows
              if isinstance(row.get("speed_ts"), (int, float))]
    report.update(
        sticky_on=sticky.get("on"), unlimited_hours=sticky.get("unlimited_hours"),
        limited_hours=sticky.get("limited_hours"), spare_hours=sticky.get("spare_hours"),
        rows=len(rows), members=sum(1 for row in rows if row.get("status") == "member"),
        measured=len(stamps),
        measured_6h=sum(1 for ts in stamps if now - ts < 6 * 3600),
        measured_30h=sum(1 for ts in stamps if now - ts < 30 * 3600),
        oldest_hours=round((now - min(stamps)) / 3600, 1) if stamps else None,
        old_note_rows=sum(1 for row in rows if OLD_NOTE in (row.get("speed_note") or "")),
        main_set=bool(state.get("main")),
        state=state.get("state"))
    return bool(rows)


def pool(report):
    state = panel("/api/state")
    found = state.get("free_pool") or {}
    summary = found.get("summary") or {}
    ready = summary.get("ready_by_source") or {}
    sources = {item.get("id"): item for item in summary.get("sources") or []
               if isinstance(item, dict)}
    now = time.time()
    report.update(
        mode=found.get("mode"), region=summary.get("region"),
        region_policy=summary.get("region_policy"), found=summary.get("found"),
        lists=summary.get("lists"), checked=summary.get("checked"),
        ready=summary.get("ready"),
        ready_lists=sum(int(ready.get(name) or 0) for name in LISTS))
    for name in LISTS:
        item = sources.get(name) or {}
        got = item.get("retrieved_at")
        report[f"{name}_status"] = item.get("status")
        report[f"{name}_variants"] = item.get("variants")
        report[f"{name}_age_hours"] = (round((now - float(got)) / 3600, 1)
                                       if isinstance(got, (int, float)) else None)
    return True


if __name__ == "__main__":
    record = {}
    modes = {"speed": speed, "pool": pool}
    try:
        mode = sys.argv[1:]
        if mode == ["health"]:
            passed = health()
            record["health"] = passed
        elif len(mode) == 1 and mode[0] in modes:
            passed = modes[mode[0]](record)
        else:
            raise ValueError
    except Exception as exc:
        passed = False
        record["reason"] = type(exc).__name__
    print(json.dumps(record, ensure_ascii=False))
    sys.exit(0 if passed else 3)
