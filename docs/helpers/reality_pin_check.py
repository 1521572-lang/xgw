"""Закрепление SNI и short_id REALITY (отчёт tspu-audit) на ThinkCentre. Только числа.

health      — шлюз в порядке (как в ТЗ tspu-audit);
servers     — участники живы, запасные с вердиктом OK/SLOW (сравнить до и после установки);
reality     — файл пар REALITY: есть ли, права 0600, сколько серверов в нём;
refresh     — внеочередное обновление подписок через API панели (кнопка «Обновить»), затем
              ожидание сборки: сколько серверов сохранили прежнюю пару, сменилось ли поколение
              sing-box и из-за чего (имена частей и полей, без значений);
generations — смены поколения sing-box с запуска службы xgw: число, причины, поля, и
              сколько раз обновление подписки оставило прежние пары.
"""

import hashlib
import hmac
import json
import os
import stat
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

STATUS = Path("/run/xgw/status.json")
TOKEN = Path("/var/lib/xgw/panel-token")
PAIRS = Path("/var/lib/xgw/reality.json")
SWITCH = "поколение sing-box сменено: изменились "
HELD = "REALITY: у "
REFRESHED = "обновление подписки: опрос"


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


def servers(report):
    snap = json.loads(STATUS.read_bytes())
    members = snap.get("members") or []
    spares = snap.get("spares") or []
    report.update(
        members=len(members), members_alive=sum(1 for m in members if m.get("alive") is True),
        spares=len(spares),
        spares_usable=sum(1 for s in spares if s.get("verdict") in ("OK", "SLOW")),
        state=snap.get("state"))
    return True


def reality(report):
    if not PAIRS.exists():
        report.update(file=False)
        return False
    mode = stat.S_IMODE(os.stat(PAIRS).st_mode)
    known = (json.loads(PAIRS.read_bytes()).get("known") or {})
    now = time.time()
    report.update(file=True, mode=oct(mode), records=len(known),
                  with_fingerprint=sum(1 for e in known.values() if e.get("fp")),
                  older_than_1h=sum(1 for e in known.values()
                                    if now - float(e.get("since") or now) >= 3600))
    return mode == 0o600 and len(known) > 0


def journal(since):
    proc = subprocess.run(["journalctl", "-u", "xgw", "--since", since, "-o", "cat",
                           "--no-pager"], capture_output=True, text=True, timeout=120)
    return proc.stdout.splitlines()


def summarize(lines, report):
    switches, parts, fields, held = 0, Counter(), Counter(), []
    for line in lines:
        if SWITCH in line:
            switches += 1
            rest = line.split(SWITCH, 1)[1]
            head, _sep, tail = rest.partition(" (поля: ")
            for part in head.split(", "):
                parts[part.strip()] += 1
            for name in tail.rstrip(")").split(", ") if tail else []:
                fields["servers=N" if name.startswith("servers=") else name.strip()] += 1
        elif HELD in line:
            number = line.split(HELD, 1)[1].split(" ", 1)[0]
            if number.isdigit():
                held.append(int(number))
    report.update(switches=switches, switch_parts=dict(parts), switch_fields=dict(fields),
                  refreshes=sum(1 for line in lines if REFRESHED in line),
                  held_times=len(held), held_max=max(held, default=0))


def panel(path, body=None):
    sys.path.insert(0, "/opt/xgw/lib")
    from xgw import config as xconfig

    cfg, _warnings = xconfig.load(Path("/etc/xgw/config.toml"))
    token = TOKEN.read_text(encoding="ascii").strip()
    cookie = hmac.new(token.encode(), b"xgw-panel", hashlib.sha256).hexdigest()
    headers = {"Cookie": f"xgw_panel={cookie}", "X-XGW-Panel": "1"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"http://127.0.0.1:{cfg.panel.port}{path}", data=data,
                                     headers=headers, method="POST" if data else "GET")
    with urllib.request.urlopen(request, timeout=30) as reply:
        return json.loads(reply.read())


def refresh(report):
    since = f"@{int(time.time()) - 1}"
    reply = panel("/api/refresh", {})
    report["action_ok"] = bool(reply.get("ok"))
    deadline = time.monotonic() + 600
    done = False
    while report["action_ok"] and time.monotonic() < deadline:
        time.sleep(10)
        busy = (panel("/api/state").get("busy") or {}).get("refresh")
        if not busy and any(REFRESHED in line for line in journal(since)):
            done = True
            break
    report["refreshed"] = done
    if done:
        time.sleep(240)  # сборка запрошена отдельно, подготовка поколения — в фоне
    summarize(journal(since), report)
    return report["action_ok"] and done


def generations(report):
    started = subprocess.run(["systemctl", "show", "xgw", "-p", "ActiveEnterTimestamp",
                              "--value"], capture_output=True, text=True, timeout=30)
    value = started.stdout.strip()
    if not value:
        report["reason"] = "NO_START_TIME"
        return False
    summarize(journal(value), report)
    proc = subprocess.run(["xgw", "singbox", "status"], capture_output=True, text=True,
                          timeout=30)
    data = json.loads(proc.stdout) if proc.returncode == 0 and proc.stdout else {}
    report.update({key: data.get(key) for key in (
        "active", "draining", "identity_ok", "switches_24h", "switch_reasons_24h",
        "switch_fields_24h")})
    report["hours_since_start"] = round(
        (time.time() - float(subprocess.run(
            ["date", "-d", value, "+%s"], capture_output=True, text=True,
            timeout=10).stdout.strip() or time.time())) / 3600, 1)
    return proc.returncode == 0


if __name__ == "__main__":
    record = {}
    modes = {"servers": servers, "reality": reality, "refresh": refresh,
             "generations": generations}
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
