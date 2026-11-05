"""Аудит противодействия ТСПУ 05.11.2026 и иконка замера на ThinkCentre. Только числа.

health      — шлюз в порядке (как в ТЗ c05-scan-bytes);
fingerprint — TLS-серверы Xray в рабочем конфиге: сколько с отпечатком ClientHello и каким;
servers     — участники живы, запасные с вердиктом OK/SLOW (сравнить до и после установки);
icon        — строки панели, где должна быть иконка замера, и один ручной замер участника
              через API панели (тот же запрос, что шлёт иконка), ожидание его итога;
generations — смены поколения sing-box за сутки, причины и изменённые поля серверов.
"""

import hashlib
import hmac
import json
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

APPLIED = Path("/etc/xgw/xray/config.json")
STATUS = Path("/run/xgw/status.json")
TOKEN = Path("/var/lib/xgw/panel-token")


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


def legs(stream, depth=0):
    found = []
    if depth >= 4 or not isinstance(stream, dict):
        return found
    for key in ("xhttpSettings", "splithttpSettings"):
        settings = stream.get(key)
        if not isinstance(settings, dict):
            continue
        for options in (settings, settings.get("extra")):
            down = options.get("downloadSettings") if isinstance(options, dict) else None
            if isinstance(down, dict):
                found.append(down)
                found.extend(legs(down, depth + 1))
    return found


def quic(stream, network):
    tls = stream.get("tlsSettings") if isinstance(stream.get("tlsSettings"), dict) else {}
    alpn = tls.get("alpn")
    alpn = alpn.split(",") if isinstance(alpn, str) else alpn if isinstance(alpn, list) else []
    return network in ("xhttp", "splithttp") and [str(a).strip() for a in alpn] == ["h3"]


def fingerprint(report):
    config = json.loads(APPLIED.read_bytes())
    values, total, missing = Counter(), 0, 0
    for item in config.get("outbounds") or []:
        if not str(item.get("tag") or "").startswith(("proxy-", "pool-", "spare-")):
            continue
        stream = item.get("streamSettings")
        if not isinstance(stream, dict):
            continue
        for leg, network in [(stream, str(stream.get("network") or "tcp")),
                             *((leg, "xhttp") for leg in legs(stream))]:
            if str(leg.get("security") or "").lower() != "tls" or quic(leg, network):
                continue
            total += 1
            tls = leg.get("tlsSettings") if isinstance(leg.get("tlsSettings"), dict) else {}
            value = str(tls.get("fingerprint") or "").strip()
            if value:
                values[value] += 1
            else:
                missing += 1
    report.update(tls_legs=total, without_fingerprint=missing, fingerprints=dict(values))
    return missing == 0


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


def icon(report):
    state = panel("/api/state")
    rows = [row for row in state.get("servers") or []
            if row.get("status") in ("member", "spare") and (row.get("multiplier") or 0) < 100]
    report.update(icon_rows=len(rows), sticky_on=(state.get("sticky") or {}).get("on"))
    members = [row for row in rows if row.get("status") == "member" and row.get("alive")]
    if not members:
        report["reason"] = "NO_LIVE_MEMBER"
        return False
    target = members[0]
    before = target.get("speed_ts")
    reply = panel("/api/speed/one", {"tag": target.get("tag")})
    report["action_ok"] = bool(reply.get("ok"))
    deadline = time.monotonic() + 180
    measured = False
    while report["action_ok"] and time.monotonic() < deadline:
        time.sleep(5)
        state = panel("/api/state")
        row = next((r for r in state.get("servers") or []
                    if r.get("fingerprint") == target.get("fingerprint")), {})
        busy = (state.get("busy") or {}).get("speed_one") or []
        if row.get("speed_ts") and row.get("speed_ts") != before and not busy:
            measured = True
            report["speed_present"] = row.get("speed_mbps") is not None
            break
    report["measured"] = measured
    return bool(report["icon_rows"] and report["action_ok"] and measured)


def generations(report):
    proc = subprocess.run(["xgw", "singbox", "status"], capture_output=True, text=True,
                          timeout=30)
    data = json.loads(proc.stdout) if proc.returncode == 0 and proc.stdout else {}
    report.update({key: data.get(key) for key in (
        "active", "draining", "identity_ok", "switches_24h", "switch_reasons_24h",
        "switch_fields_24h", "last_switch_fields")})
    return proc.returncode == 0 and data.get("switches_24h") is not None


if __name__ == "__main__":
    record = {}
    modes = {"fingerprint": fingerprint, "servers": servers, "icon": icon,
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
