"""G1 (открытые вопросы) и C06 на ThinkCentre. Печатает только числа и признаки.

health   — шлюз в порядке (как в ТЗ c05-scan-bytes);
ledger   — журнал проверок за 24 ч по назначениям (scan, speed, e2e) из status.json и SQLite:
           байты, попытки и самое длинное тело одной записи;
handover — одна штатная смена поколения sing-box (`xgw singbox rotate`) при открытом
           соединении через мост: старое соединение отвечает после смены, новое идёт через
           новый мост, оба моста одновременно держат соединения, права нового процесса.
"""

import base64
import json
import pwd
import socket
import sqlite3
import ssl
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

STATUS = Path("/run/xgw/status.json")
STATE = Path("/run/xgw/singbox-generations.json")
APPLIED = Path("/etc/xgw/xray/config.json")
DB = "file:/var/lib/xgw/state.db?mode=ro"
CRLF = chr(13) + chr(10)


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


def ledger(report):
    snap = json.loads(STATUS.read_bytes())
    actual = (snap.get("budget") or {}).get("scan_actual_24h") or {}
    now = actual.get("as_of") or time.time()
    with sqlite3.connect(DB, uri=True) as db:
        rows = db.execute("SELECT COALESCE(purpose, 'scan'), COUNT(*), SUM(bytes), MAX(bytes) "
                          "FROM scan_bodies WHERE ts > ? AND ts <= ? GROUP BY 1",
                          (now - 86400, now)).fetchall()
    report["status_by_purpose"] = actual.get("by_purpose")
    report["sql"] = {kind: {"attempts": n, "bytes": total, "max_body": top}
                     for kind, n, total, top in rows}
    report["status_matches"] = all(
        (actual.get("by_purpose") or {}).get(kind, {}).get("bytes") == value["bytes"]
        for kind, value in report["sql"].items())
    report["e2e_seen"] = "e2e" in report["sql"]
    # Замер скорости ограничен speed.max_mb; остальным — не больше 2 МБ тела (C06).
    report["max_body_within_cap"] = all((value["max_body"] or 0) <= 2_000_000
                                        for kind, value in report["sql"].items()
                                        if kind != "speed")
    return report["e2e_seen"] and report["status_matches"] and report["max_body_within_cap"]


def installed():
    sys.path.insert(0, "/opt/xgw/lib")
    from xgw import config as xconfig
    from xgw.generator import builder
    from xgw.generator import singbox as sb

    cfg, _warnings = xconfig.load(Path("/etc/xgw/config.toml"))
    return cfg, builder, sb


def bridged(builder, sb):
    """Узлы, чей выход в Xray — мост к sing-box: тег, порт probe-inbound, пароль, порт моста."""
    applied = json.loads(APPLIED.read_bytes())
    password, _ports = builder.probe_state(applied)
    outbounds = {item.get("tag"): item for item in applied.get("outbounds") or []}
    found = []
    for info in builder.applied_nodes(applied):
        outbound = outbounds.get(info.tag) or {}
        if sb.bridge_variant(outbound) and info.probe_port:
            port = outbound["settings"]["servers"][0]["port"]
            found.append((info.tag, info.probe_port, password, port, builder.PROBE_USER))
    return found


def bridge_port(sb, tag):
    applied = json.loads(APPLIED.read_bytes())
    for item in applied.get("outbounds") or []:
        if item.get("tag") == tag and sb.bridge_variant(item):
            return item["settings"]["servers"][0]["port"]
    return None


def read_head(conn, deadline):
    data = b""
    end = (CRLF + CRLF).encode()
    while end not in data:
        conn.settimeout(max(0.1, deadline - time.monotonic()))
        chunk = conn.recv(4096)
        if not chunk:
            raise OSError("closed")
        data += chunk
    line = data.split(CRLF.encode(), 1)[0].decode("latin-1").split()
    return int(line[1]) if len(line) > 1 and line[1].isdigit() else 0


def open_tunnel(probe_port, user, password, host):
    raw = socket.create_connection(("127.0.0.1", probe_port), timeout=20)
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    request = (f"CONNECT {host}:443 HTTP/1.1{CRLF}Host: {host}:443{CRLF}"
               f"Proxy-Authorization: Basic {token}{CRLF}{CRLF}")
    raw.sendall(request.encode())
    if read_head(raw, time.monotonic() + 30) != 200:
        raw.close()
        raise OSError("CONNECT refused")
    conn = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
    return conn


def head(conn, host, path):
    request = (f"HEAD {path} HTTP/1.1{CRLF}Host: {host}{CRLF}User-Agent: xgw-check{CRLF}"
               f"Connection: keep-alive{CRLF}{CRLF}")
    try:
        conn.sendall(request.encode())
        return read_head(conn, time.monotonic() + 30)
    except (OSError, ValueError):
        return 0


def established(port):
    out = subprocess.run(["ss", "-tnH", "state", "established"], capture_output=True, text=True,
                         timeout=20).stdout
    return sum(1 for line in out.splitlines() if line.split()[-1:] == [f"127.0.0.1:{port}"])


def state():
    return json.loads(STATE.read_text()) if STATE.exists() else {"active": "legacy"}


def proc_identity(slot):
    out = subprocess.run(["systemctl", "show", f"xgw-singbox-{slot}.service", "-p", "MainPID"],
                         capture_output=True, text=True, timeout=10).stdout
    pid = int(out.strip().partition("=")[2] or 0)
    if pid <= 0:
        return None
    fields = {}
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        key, _, value = line.partition(":")
        fields[key] = value.split()
    core = str(pwd.getpwnam("xgw-singbox").pw_uid)
    return {"uid_is_core": fields.get("Uid") == [core] * 4,
            "caps_zero": all(int(fields[k][0], 16) == 0 for k in ("CapPrm", "CapEff", "CapAmb")),
            "no_new_privs": fields.get("NoNewPrivs") == ["1"]}


def handover(report):
    cfg, builder, sb = installed()
    deadline = time.monotonic() + 330
    while (state().get("draining") or state().get("pending")) and time.monotonic() < deadline:
        time.sleep(5)  # прежний drain ещё идёт — rotate отказал бы
    parts = urlsplit(cfg.probe.url)
    host, path = parts.hostname, parts.path or "/"
    nodes = bridged(builder, sb)
    report["bridged_nodes"] = len(nodes)
    a = chosen = None
    for node in nodes:  # первый живой мост
        try:
            a = open_tunnel(node[1], node[4], node[2], host)
        except OSError:
            continue
        if head(a, host, path):
            chosen = node
            break
        a.close()
    if chosen is None:
        report["reason"] = "NO_LIVE_SINGBOX_BRIDGE" if nodes else "NO_SINGBOX_BRIDGE"
        return False
    tag, probe_port, password, old_port, user = chosen
    report["a_before"] = 200
    before = state()
    started = time.monotonic()
    child = subprocess.Popen(["xgw", "singbox", "rotate"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    beats, broken_at = 0, None
    while child.poll() is None and time.monotonic() - started < 400:
        time.sleep(10)  # старое соединение не простаивает, пока идёт смена
        if head(a, host, path):
            beats += 1
        elif broken_at is None:
            broken_at = round(time.monotonic() - started, 1)
    if child.poll() is None:
        child.kill()
    report["rotate_rc"] = child.wait(timeout=30)
    report["rotate_seconds"] = round(time.monotonic() - started, 1)
    report.update(a_beats_during_rotate=beats, a_broken_at_s=broken_at)
    after = state()
    new_port = bridge_port(sb, tag)
    report["slot_changed"] = after.get("active") != before.get("active")
    report["old_draining"] = (after.get("draining") or {}).get("slot") == before.get("active")
    report["port_changed"] = new_port is not None and new_port != old_port
    report["a_after"] = head(a, host, path)
    b = None
    try:
        b = open_tunnel(probe_port, user, password, host)
        report["b_after"] = head(b, host, path)
    except OSError:
        report["b_after"] = 0
    report["old_bridge_conns"] = established(old_port)
    report["new_bridge_conns"] = established(new_port) if new_port else 0
    report["overlap"] = report["old_bridge_conns"] > 0 and report["new_bridge_conns"] > 0
    for conn in (a, b):
        if conn is not None:
            conn.close()
    status = subprocess.run(["xgw", "singbox", "status"], capture_output=True, text=True,
                            timeout=30)
    try:
        report["identity_ok"] = json.loads(status.stdout).get("identity_ok")
    except ValueError:
        report["identity_ok"] = None
    report["new_process"] = proc_identity(after.get("active", "")) if after.get("active") else None
    ok = (report["rotate_rc"] == 0 and report["slot_changed"] and report["old_draining"]
          and 100 <= report["a_after"] < 600 and 100 <= report["b_after"] < 600
          and report["overlap"] and report["identity_ok"] is True)
    return bool(ok)


if __name__ == "__main__":
    record = {}
    try:
        mode = sys.argv[1:]
        if mode == ["health"]:
            passed = health()
            record["health"] = passed
        elif mode == ["ledger"]:
            passed = ledger(record)
        elif mode == ["handover"]:
            passed = handover(record)
        else:
            raise ValueError
    except Exception as exc:
        passed = False
        record["reason"] = type(exc).__name__
    print(json.dumps(record, ensure_ascii=False))
    sys.exit(0 if passed else 3)
