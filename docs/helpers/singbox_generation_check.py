"""Две конечные загрузки через probe-inbound Xray и один штатный singbox rotate."""

import dataclasses
import http.client
import json
import os
import socket
import sqlite3
import ssl
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path("/run/xgw-g1-fix1")
SIZE = 2 * 1024 * 1024


def save(result):
    path = ROOT / "summary.json"
    temporary = ROOT / "summary.next"
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def run(argv, timeout=180):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


def download_url(url):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    if (parts.scheme != "https" or not parts.hostname
            or parts.hostname.rstrip(".").lower() == "speed.cloudflare.com"):
        raise ValueError("для конечной загрузки нужен настроенный HTTPS адрес")
    if "bytes" not in query:
        return url  # фиксированный файл: ниже запрашивается и проверяется Range
    query["bytes"] = str(SIZE)
    return urlunsplit(parts._replace(query=urlencode(query)))


def established(port):
    output = run(["ss", "-Htn", "state", "established", "src", f"127.0.0.1:{port}"])
    return output.returncode == 0 and bool(output.stdout.strip())


def process_count():
    from xgw.apply import singbox_process as processes

    count, permissions = 0, True
    import pwd

    uid = pwd.getpwnam("xgw-singbox").pw_uid
    for slot in ("legacy", "blue", "green"):
        result = run(["systemctl", "show", processes.unit(slot), "-p", "MainPID", "--value"])
        value = result.stdout.strip()
        if not value.isdigit() or int(value) == 0:
            continue
        try:
            lines = Path(f"/proc/{int(value)}/status").read_text().splitlines()
            fields = dict(line.split(":", 1) for line in lines if ":" in line)
        except FileNotFoundError:
            continue
        count += 1
        permissions &= all(int(n) == uid for n in fields["Uid"].split())
        permissions &= int(fields["CapEff"].strip(), 16) == 0
    return count, permissions


def stream(proxy_port, password, url, agent, state):
    from xgw import fetch

    sock = None
    try:
        parts = urlsplit(url)
        sock = fetch.open_tunnel(("127.0.0.1", proxy_port), parts.hostname, parts.port or 443,
                                 user="xgw", password=password, timeout=60)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_WINDOW_CLAMP, 4096)
        sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parts.hostname)
        sock.settimeout(60)
        connection = http.client.HTTPConnection(parts.hostname)
        connection.sock = sock
        path = parts.path + ("?" + parts.query if parts.query else "")
        connection.request("GET", path, headers={
            "User-Agent": agent, "Accept-Encoding": "identity", "Connection": "close",
            "Range": f"bytes=0-{SIZE - 1}"})
        reply = connection.getresponse()
        state["http"] = reply.status
        length = reply.getheader("Content-Length")
        ranged = reply.getheader("Content-Range", "").startswith(f"bytes 0-{SIZE - 1}/")
        if (reply.status not in (200, 206) or (reply.status == 206 and not ranged)
                or (length is not None and int(length) != SIZE)):
            state["error"] = "BODY_OR_HTTP"
            return
        started = time.monotonic()
        while state["bytes"] < SIZE:
            data = reply.read(min(8192, SIZE - state["bytes"]))
            if not data:
                break
            state["bytes"] += len(data)
            state["receiving"].set()
            time.sleep(0.5)  # Backpressure, не искусственная пауза после законченного ответа.
        state["seconds"] = round(time.monotonic() - started, 1)
        state["ok"] = state["bytes"] == SIZE and not reply.read(1)
    except Exception:
        state["error"] = "STREAM_FAILED"
    finally:
        if sock:
            sock.close()
        state["done"].set()


def start_stream(port, password, url, agent):
    state = {"bytes": 0, "ok": False, "seconds": 0, "http": 0, "error": None,
             "receiving": threading.Event(), "done": threading.Event()}
    threading.Thread(target=stream, args=(port, password, url, agent, state), daemon=True).start()
    return state


def public_stream(state):
    return {key: state[key] for key in ("bytes", "ok", "seconds", "http", "error")}


def pin_value(paths):
    with sqlite3.connect(f"file:{paths.db_file}?mode=ro", uri=True) as db:
        row = db.execute("SELECT value FROM meta WHERE key='pin'").fetchone()
    value = json.loads(row[0]) if row and row[0] else None
    if isinstance(value, dict):
        value = {key: value.get(key) for key in ("tag", "since", "until")}
        value["tag"] = str(value["tag"]).partition("-")[2]
    return value


def health():
    response = run(["xgw", "status", "--json"])
    (ROOT / "health-status-private.json").write_text(response.stdout)
    try:
        status = json.loads(response.stdout)
        capture = status.get("capture") or {}
        ok = (response.returncode == 0 and status.get("daemon_down") is False
              and status.get("xray", {}).get("ok") is True
              and capture.get("mode") == "on" and capture.get("blocked") is False
              and capture.get("loaded") is True)
    except (ValueError, AttributeError):
        ok = False
    reply = run(["curl", "--silent", "--proto", "=https", "--noproxy", "*", "--max-time", "90",
                 "--output", "/dev/null", "--write-out", "%{http_code}", "https://1.1.1.1/"])
    (ROOT / "health-result.json").write_text(json.dumps({
        "status_accepted": ok, "status_rc": response.returncode, "https_rc": reply.returncode,
        "http_status": int(reply.stdout) if reply.stdout.isdigit() else 0}))
    ok &= reply.returncode == 0 and reply.stdout.isdigit() and 200 <= int(reply.stdout) < 400
    print("Рабочий on и HTTPS подтверждены" if ok else "Рабочий on или HTTPS не подтверждены")
    return 0 if ok else 3


def main():
    os.umask(0o077)
    ROOT.mkdir(mode=0o700, exist_ok=True)
    if ROOT.is_symlink() or ROOT.stat().st_uid != 0:
        raise ValueError("private output directory")
    ROOT.chmod(0o700)
    if len(sys.argv) > 1 and sys.argv[1] == "health":
        return health()
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        print((ROOT / "summary.json").read_text())
        return 0
    if (ROOT / "summary.json").exists():
        previous = json.loads((ROOT / "summary.json").read_text())
        if previous.get("stage") in {
            "before", "WAIT_FOR_PREVIOUS_GENERATION", "NO_WORKING_SINGBOX_ROUTE",
            "BASELINE_STREAM_NOT_PROVEN",
        } and previous.get("rotate_rc") is None:
            (ROOT / f"preflight-{time.time_ns()}.json").write_text(json.dumps(previous))
        else:
            print("Результат уже есть: читайте report; новую смену поколения не запускайте")
            return 3
    from xgw import config
    from xgw.apply import singbox_process as processes
    from xgw.generator import builder, singbox
    from xgw.paths import Paths
    from xgw.watch import checks
    result = {"stage": "before", "rotate_rc": None, "old_endpoint": False,
              "new_endpoint": False, "overlap": False, "max_processes": 0,
              "permissions": True, "old_retired": False, "status_gap_s": 0,
              "status_within_25": True,
              "settings_unchanged": None, "pin_unchanged": None}
    save(result)
    paths = Paths(Path("/"))
    cfg, _ = config.load(paths.config_file)
    pin_before = pin_value(paths)
    primary = len(sys.argv) > 1 and sys.argv[1] == "primary"
    url = download_url(cfg.speed.url if primary else (cfg.speed.url_fallback or cfg.speed.url))
    routed = json.loads(paths.xray_config_file.read_text())
    password, _ = builder.probe_state(routed)
    before = processes.read(paths)
    if before["draining"] or before["pending"]:
        result["stage"] = "WAIT_FOR_PREVIOUS_GENERATION"
        save(result)
        return 3
    chosen = None
    for info in builder.applied_nodes(routed):
        outbound = next((o for o in routed["outbounds"] if o.get("tag") == info.tag), {})
        if not singbox.bridge_variant(outbound):
            continue
        check = checks.http_get_via_proxy(
            "127.0.0.1", info.probe_port, cfg.probe.url, proxy_user="xgw", proxy_pass=password,
            max_total=30, min_body=config.probe_bytes(cfg.probe.url) or 1,
            user_agent=cfg.probe.user_agent)
        if check.ok:
            chosen = info, outbound["settings"]["servers"][0]["port"]
            break
    if chosen is None:
        result["stage"] = "NO_WORKING_SINGBOX_ROUTE"
        save(result)
        return 3
    info, old_port = chosen
    first = start_stream(info.probe_port, password, url, cfg.probe.user_agent)
    deadline = time.monotonic() + 180
    while not first["receiving"].is_set() and not first["done"].is_set():
        if time.monotonic() >= deadline:
            break
        time.sleep(0.2)
    result["old_endpoint"] = first["receiving"].is_set() and established(old_port)
    if not result["old_endpoint"] or first["done"].is_set():
        result.update(stage="BASELINE_STREAM_NOT_PROVEN", first=public_stream(first))
        save(result)
        return 3
    result["stage"] = "rotate"
    save(result)
    with (ROOT / "rotate-private.log").open("w") as log:
        child = subprocess.Popen(["xgw", "singbox", "rotate"], stdout=log, stderr=log)
        second, new_port = None, None
        until = time.monotonic() + 900
        old_status = paths.status_file.stat().st_mtime_ns
        while time.monotonic() < until:
            count, permissions = process_count()
            result["max_processes"] = max(result["max_processes"], count)
            result["permissions"] &= permissions
            result["rotate_rc"] = child.poll()
            if second is None and result["rotate_rc"] == 0:
                current = json.loads(paths.xray_config_file.read_text())
                outbound = next(o for o in current["outbounds"] if o.get("tag") == info.tag)
                new_port = outbound["settings"]["servers"][0]["port"]
                if new_port != old_port:
                    second = start_stream(info.probe_port, password, url, cfg.probe.user_agent)
            if second and second["receiving"].is_set() and established(new_port):
                result["new_endpoint"] = True
                result["overlap"] |= (not first["done"].is_set() and established(old_port))
            current_status = paths.status_file.stat().st_mtime_ns
            if current_status != old_status:
                result["status_within_25"] &= current_status - old_status <= 25_000_000_000
                result["status_gap_s"] = max(result["status_gap_s"],
                                              round((current_status - old_status) / 1e9, 1))
                old_status = current_status
            state = processes.read(paths)
            old_active = run([
                "systemctl", "is-active", "--quiet", processes.unit(before["active"])])
            result["old_retired"] = (not state["draining"] and old_active.returncode != 0
                                     and state["active"] != before["active"])
            result["first"] = public_stream(first)
            result["second"] = public_stream(second) if second else None
            save(result)
            if child.poll() not in (None, 0) and first["done"].is_set():
                break
            if (second and first["done"].is_set() and second["done"].is_set()
                    and result["old_retired"]):
                break
            time.sleep(1)
    result["stage"] = "complete" if result["old_retired"] else "partial"
    after_cfg, _ = config.load(paths.config_file)
    result["settings_unchanged"] = dataclasses.asdict(after_cfg) == dataclasses.asdict(cfg)
    result["pin_unchanged"] = pin_value(paths) == pin_before
    save(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if (result["rotate_rc"] == 0 and result["old_retired"]
                 and result["overlap"] and first["ok"] and second and second["ok"]
                 and first["seconds"] >= 60 and second["seconds"] >= 60
                 and result["status_within_25"] and result["settings_unchanged"]
                 and result["permissions"] and result["max_processes"] == 2) else 3


if __name__ == "__main__":
    sys.path.insert(0, "/opt/xgw/lib")
    raise SystemExit(main())
