"""Почему мосты sing-box не отвечают и с каких пор падают общие сборки: только чтение.

Выводятся числа и короткие метки. Адреса, домены, теги, отпечатки, пароли и строки журнала не
выводятся. Настройки и службы не меняются. На каждый мост — один малый запрос через него и одно
TCP-соединение с сервером от пользователя sing-box, без передачи данных.
"""
import collections
import errno
import json
import os
import pwd
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

XRAY, SB_DIR = Path("/etc/xgw/xray/config.json"), Path("/etc/xgw/sing-box")
STATE, DIRTY = Path("/run/xgw/singbox-generations.json"), Path("/run/xgw/api-dirty")
UNIT, SB_USER = "xgw.service", "xgw-singbox"
SLOTS, DAYS, MAX_BRIDGES = ("blue", "green"), 14, 8
QUIC = ("hysteria2", "hysteria", "tuic")
USER = re.compile(r"^xgw-([dfm])$")
WORD = re.compile(r"^[A-Za-z0-9_]{1,20}$")
IP_TEXT = re.compile(r"^[0-9.]+$|:")
PARTS = ("server_settings", "dns_hosts", "endpoints", "servers", "route")
EVENTS = (("build_started", "сборка конфига начата"),
          ("build_stale", "устаревшая сборка конфига отброшена"),
          ("build_finished", "конфиг собран в фоне"),
          ("generation_changed", "поколение sing-box сменено"),
          ("generation_failed", "подготовка поколения sing-box не выполнена"))
BRIDGES = re.compile(r"мостов проверено ([0-9]+) из ([0-9]+)(?:: ((?:[a-z_]+ [0-9]+(?:, )?)+))?")
STAMP = re.compile(r"^[0-9]{4}-([0-9]{2}-[0-9]{2})T([0-9]{2}:[0-9]{2})")
PX_REPLY = re.compile(r"[(]([0-9]{1,3})[)]")
PX_MARKS = (("user_rejected", "rejected"), ("no_auth_method", "no authentication method"),
            ("auth_read_failed", "sub-negotiation"), ("greeting_failed", "initial socks5"),
            ("connect_read_failed", "connect request ack"), ("timeout", "timed out"),
            ("connect_refused", "connection refused"), ("connect_failed", "failed to connect"))
# Первое совпадение определяет вид строки журнала sing-box.
LOG_KINDS = (("timeout", ("i/o timeout", "deadline exceeded", "timed out")),
             ("refused", ("connection refused",)), ("reset", ("connection reset", "broken pipe")),
             ("unreachable", ("no route to host", "network is unreachable")),
             ("no_host", ("no such host", "lookup ")),
             ("perm", ("operation not permitted", "permission denied")), ("reality", ("reality",)),
             ("auth", ("authenticat", "user not found", "invalid user", "unauthorized")),
             ("tls", ("tls:", "certificate", "handshake")), ("eof", ("eof",)),
             ("reject", ("reject",)))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def word(value):
    text = str(value or "")
    return text if WORD.fullmatch(text) else ("-" if not text else "?")


def unit_of(slot):
    return "xgw-singbox.service" if slot == "legacy" else f"xgw-singbox-{slot}.service"


def path_of(slot):
    return SB_DIR / ("config.json" if slot == "legacy" else f"generation-{slot}.json")


def by_tag(config, key):
    return {str(item.get("tag")): item for item in config.get(key) or [] if isinstance(item, dict)}


def compare(old, new):
    """Чем файл несостоявшегося поколения отличается от работающего: только части и числа."""
    old_in, new_in = by_tag(old, "inbounds"), by_tag(new, "inbounds")
    old_out, new_out = by_tag(old, "outbounds"), by_tag(new, "outbounds")
    parts = ["servers"] if set(old_in) != set(new_in) or set(old_out) != set(new_out) else []
    changed = sum(old_out[tag] != new_out[tag] for tag in set(old_out) & set(new_out))
    parts += ["server_settings"] if changed else []
    parts += [key for key in ("dns", "endpoints", "route") if old.get(key) != new.get(key)]
    return parts, changed, len(set(new_in) - set(old_in)), len(set(old_in) - set(new_in))


def generation():
    try:
        state = read_json(STATE)
    except FileNotFoundError:
        state = {"active": "legacy"}
    slot = state.get("active")
    if slot not in (*SLOTS, "legacy"):
        raise ValueError("state")
    active, now = read_json(path_of(slot)), time.time()
    history = [item for item in state.get("history") or [] if isinstance(item, dict)]
    stamps = [float(item.get("ts") or 0) for item in history]
    age = round((now - max(stamps)) / 3600, 1) if stamps else "-"
    last_parts = [part for part in history[-1].get("parts") or [] if part in PARTS] if history else []
    main_file = SB_DIR / "config.json"
    same = int(main_file.exists() and read_json(main_file) == active)
    print(f"INFO generation active={slot} pending={int(bool(state.get('pending')))} "
          f"draining={int(bool(state.get('draining')))} api_dirty={int(DIRTY.exists())} "
          f"switches_24h={sum(now - stamp < 86400 for stamp in stamps)} last_switch_age_h={age} "
          f"last_parts={last_parts} config_same={same}", flush=True)
    other = next((item for item in SLOTS if item != slot), None)
    if other is None or not path_of(other).exists():
        print("INFO candidate present=0", flush=True)
        return slot, active, other
    body = read_json(path_of(other))
    parts, changed, added, removed = compare(active, body)
    print(f"INFO candidate present=1 age_min={round((now - path_of(other).stat().st_mtime) / 60)} "
          f"inbounds_active={len(active.get('inbounds') or [])} "
          f"inbounds_candidate={len(body.get('inbounds') or [])} added={added} removed={removed} "
          f"changed_servers={changed} parts={parts}", flush=True)
    return slot, active, other


def connect_label(host, port):
    began = time.monotonic()
    try:
        with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET) as sock:
            sock.settimeout(6)
            sock.connect((host, port))
        return f"ok:{round((time.monotonic() - began) * 1000)}ms"
    except OSError as exc:
        names = {errno.ECONNREFUSED: "refused", errno.ENETUNREACH: "unreachable",
                 errno.EHOSTUNREACH: "unreachable", errno.EPERM: "perm", errno.EACCES: "perm"}
        return "timeout" if isinstance(exc, TimeoutError) else names.get(exc.errno, "error")


def tcp_as_user(host, port):
    """Соединение от того же пользователя, что и sing-box: те же правила и маршруты."""
    info = pwd.getpwnam(SB_USER)
    reader, writer = os.pipe()
    child = os.fork()
    if child == 0:
        try:
            os.setgroups([])
            os.setgid(info.pw_gid)
            os.setuid(info.pw_uid)
            os.write(writer, connect_label(host, port).encode())
        finally:
            os._exit(0)
    os.close(writer)
    label = os.read(reader, 64).decode()  # соединение ограничено 6 секундами
    os.close(reader)
    os.waitpid(child, 0)
    return label or "error"


def upstream(config, tag):
    """Описание сервера моста и (адрес, порт) для TCP; адрес наружу не выводится."""
    rules = (config.get("route") or {}).get("rules") or []
    target = next((rule.get("outbound") for rule in rules if tag in (rule.get("inbound") or [])),
                  None)
    out = {**by_tag(config, "endpoints"), **by_tag(config, "outbounds")}.get(target) or {}
    kind, net, tls = out.get("type"), (out.get("transport") or {}).get("type") or "tcp", \
        out.get("tls") or {}
    secure = ("reality" if (tls.get("reality") or {}).get("enabled") else
              "tls" if tls.get("enabled") else "none")
    server, port = str(out.get("server") or ""), out.get("server_port")
    servers = (config.get("dns") or {}).get("servers") or [{}]
    known = (servers[0].get("predefined") or {}).get(server) or []
    address, label = (server, "ip") if IP_TEXT.search(server) else (
        (known[0], "host") if known else (None, "no_host"))
    text = (f"type={word(kind)} net={word(net)} sec={secure} detour={int(bool(out.get('detour')))} "
            f"mux={int(bool((out.get('multiplex') or {}).get('enabled')))} addr={label}")
    dial = None if kind in QUIC or net == "quic" or not port or not address else (address, port)
    return text, dial


def px_label(message):
    """Текст ошибки curl — в метку: сам текст содержит адрес проверки и наружу не идёт."""
    if not message:
        return "-"
    low, reply = message.lower(), PX_REPLY.search(message)
    if "socks" in low and "connection to" in low and reply:
        return "reply_" + reply[1]
    return next((label for label, mark in PX_MARKS if mark in low), "other")


def curl_bridge(server, user, url):
    ask = (f'proxy = "socks5h://127.0.0.1:{server["port"]}"\n'
           f'proxy-user = "{user["user"]}:{user["pass"]}"\n')  # пароль не в аргументах
    done = subprocess.run(
        ["curl", "-K", "-", "--silent", "--max-time", "20", "-o", "/dev/null",
         "-w", "%{time_total}|%{errormsg}", url],
        input=ask, text=True, capture_output=True, timeout=25, check=False)
    spent, _, message = done.stdout.strip().partition("|")
    return done.returncode, px_label(message), spent[:5] or "-"


def singbox_log(unit, since):
    return subprocess.run(
        ["timeout", "60", "journalctl", "--no-pager", "-o", "cat", "-u", unit, "--since", since],
        capture_output=True, encoding="utf-8", errors="replace", timeout=70,
        check=False).stdout.splitlines()


def counted(lines):
    found = collections.Counter(
        next((label for label, marks in LOG_KINDS if any(m in line.lower() for m in marks)), "other")
        for line in lines if line.strip())
    return " ".join(f"{key}={found[key]}" for key in sorted(found)) or "none"


def check_bridges(slot, active, other):
    xray = read_json(XRAY)
    inbounds = {item.get("listen_port"): item for item in active.get("inbounds") or []}
    url, found = xray["burstObservatory"]["pingConfig"]["destination"], []
    for item in xray.get("outbounds") or []:
        servers = (item.get("settings") or {}).get("servers") or [{}]
        users = servers[0].get("users") or [{}]
        match = USER.match(str(users[0].get("user") or ""))
        if item.get("protocol") == "socks" and servers[0].get("address") == "127.0.0.1" and match:
            found.append((item, servers[0], users[0], match[1]))
    began, names = int(time.time()) - 1, []
    print(f"INFO bridges total={len(found)} tested={min(len(found), MAX_BRIDGES)} "
          f"inbounds_active={len(inbounds)}", flush=True)
    for number, (item, server, user, letter) in enumerate(found[:MAX_BRIDGES], 1):
        tag = str(item.get("tag") or "")
        role = "main" if tag.startswith("proxy-") else "spare" if tag.startswith("spare-") else "other"
        inbound = inbounds.get(server["port"]) or {}
        name, owner = str(inbound.get("tag") or ""), (inbound.get("users") or [{}])[0]
        same = int(owner.get("username") == user["user"] and owner.get("password") == user["pass"])
        text, dial = upstream(active, name)
        code, error, seconds = curl_bridge(server, user, url)
        tcp = tcp_as_user(*dial) if dial else "skip"
        names.append((number, name))
        print(f"B{number} role={role} letter={letter} found={int(bool(inbound))} "
              f"in={word(inbound.get('type'))} cred={same} {text} "
              f"curl={code} px={error} t={seconds} tcp={tcp}", flush=True)
    time.sleep(1)  # журнал должен успеть получить последние строки
    window = singbox_log(unit_of(slot), f"@{began}")
    for number, name in names:
        mine = [line for line in window
                if name and (name in line or name.replace("sb-in-", "sb-out-", 1) in line)]
        print(f"LOG B{number} {counted(mine)}", flush=True)
    print(f"LOG test_window_all {counted(window)}", flush=True)
    print(f"LOG active_24h {counted(singbox_log(unit_of(slot), '-24h'))}", flush=True)
    if other:
        print(f"LOG candidate_24h {counted(singbox_log(unit_of(other), '-24h'))}", flush=True)


def read_daemon_journal():
    days, kinds, moments = collections.defaultdict(collections.Counter), collections.Counter(), {}
    lines, first, last, streak = 0, "-", "-", {"count": 0, "first": "-", "last": "-", "built": 0}
    with subprocess.Popen(["timeout", "240", "journalctl", "--no-pager", "-o", "short-iso", "-u",
                           UNIT, "--since", f"-{DAYS}d"], stdout=subprocess.PIPE,
                          encoding="utf-8", errors="replace") as stream:
        for line in stream.stdout:
            found = STAMP.match(line)
            if not found:
                continue
            lines, moment = lines + 1, f"{found[1]}_{found[2]}"
            first, last = moment if first == "-" else first, moment
            event = next((label for label, text in EVENTS if text in line), None)
            if event is None:
                continue
            days[found[1]][event] += 1
            moments[event] = moment
            if event == "generation_failed":
                streak.update(count=streak["count"] + 1, last=moment,
                              first=moment if streak["first"] == "-" else streak["first"])
                seen = BRIDGES.search(line)
                kinds[f"{seen[1]}/{seen[2]} " + (seen[3] or "-").replace(", ", ",")
                      if seen else "no_bridge_summary"] += 1
            elif event == "generation_changed":
                streak = {"count": 0, "first": "-", "last": "-", "built": 0}
            elif event == "build_finished" and streak["count"]:
                streak["built"] += 1
    if stream.returncode == 124:
        raise TimeoutError("journal")
    print(f"INFO journal_lines={lines} first={first} last={last}", flush=True)
    for day in sorted(days):
        print(f"DAY {day} " + " ".join(f"{key}={days[day][key]}" for key in sorted(days[day])),
              flush=True)
    print("INFO fail_kinds " + (" | ".join(f"{key} x{kinds[key]}" for key in sorted(kinds))
                                or "none"), flush=True)
    print("INFO last " + " ".join(f"{key}={moments[key]}" for key in sorted(moments)), flush=True)
    print(f"INFO streak count={streak['count']} first={streak['first']} last={streak['last']} "
          f"finished_inside={streak['built']}", flush=True)


def main():
    print("INFO now=" + time.strftime("%m-%d_%H:%M"), flush=True)
    check_bridges(*generation())
    read_daemon_journal()
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:  # noqa: BLE001 — текст ошибки может содержать адрес
        print("STOP", type(exc).__name__, flush=True)
        code = 3
    print(f"helper_rc={code}", flush=True)
    sys.exit(code)
