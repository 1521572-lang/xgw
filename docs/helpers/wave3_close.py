"""Один конечный помощник закрытия волны 3. Не устанавливает продукт или службы."""

import grp
import hashlib
import http.client
import ipaddress
import json
import os
import pwd
import signal
import socket
import ssl
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path("/run/xgw-wave3-close")
ACTIVE = ROOT / "active.json"
TARGET = ("1.1.1.1", 443)
KINDS = {"output": "цепочка output", "table": "таблица ip xgw", "rule": "правило pref 100"}
LIMITS = {"output": 10, "table": 10, "rule": 40}
USER = "xgw-singbox"


def require(ok):
    if not ok:
        raise RuntimeError("Проверка остановлена: не выполнено предусловие")


def command(argv, timeout=3, user=None):
    if user:
        argv = ["runuser", "-u", user, "--", *argv]
    try:
        p = subprocess.run(
            argv,
            cwd="/",
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "LC_ALL": "C"},
        )
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.TimeoutExpired):
        return None, b"", b""


def read(path):
    with path.open("rb") as stream:
        raw = stream.read(1048577)
    require(len(raw) <= 1048576)
    return json.loads(raw)


def save(data, path=None):
    path = path or ROOT / "state.json"
    tmp = path.with_suffix(".next")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def app():
    sys.path.insert(0, "/opt/xgw/lib")
    from xgw import config
    from xgw.net.capture import capture_for
    from xgw.paths import Paths

    paths = Paths(Path("/"))
    cfg = config.load(paths.config_file)[0]
    return cfg, paths, capture_for(cfg, paths)


def context():
    cfg, paths, capture = app()
    status = read(paths.status_file)
    pin = status.get("pin") or {}
    require(type(pin) is dict)
    private = {k: pin.get(k) for k in ("tag", "until", "expires")}
    digest = hashlib.sha256(paths.config_file.read_bytes()).hexdigest()
    panel = paths.etc / "panel.json"
    if panel.exists():
        digest += hashlib.sha256(panel.read_bytes()).hexdigest()
    mode = cfg.free_pool.mode
    return (
        cfg,
        paths,
        capture,
        (digest, mode, json.dumps(private, sort_keys=True)),
        (status.get("state") == "HEALTHY" and capture.effective_mode() == "on"),
    )


def guard(raw=None):
    if raw is None:
        rc, raw, _ = command(["nft", "-j", "-a", "list", "table", "inet", "xgw_guard"])
        require(rc == 0)
    require(len(raw) <= 65536)
    data = json.loads(raw)
    table = hook = None
    counts, terminal = {}, None
    for item in data["nftables"]:
        if "table" in item:
            row = item["table"]
            require(row["family"] == "inet" and row["name"] == "xgw_guard")
            table = row.get("handle")
        if "chain" in item and item["chain"].get("name") == "output":
            row = item["chain"]
            hook = row.get("hook") == "postrouting" and row.get("prio") == 10
        if "rule" not in item:
            continue
        row = item["rule"]
        expr = row.get("expr", [])
        counters = [e["counter"]["packets"] for e in expr if "counter" in e]
        denied = any("drop" in e or "reject" in e for e in expr)
        if counters and denied:
            require(len(counters) == 1 and type(counters[0]) is int and counters[0] >= 0)
            key = row["chain"] + ":" + str(row["handle"])
            require(key not in counts)
            counts[key] = counters[0]
            if row["chain"] == "output" and [e for e in expr if "counter" not in e] == [
                {"drop": None}
            ]:
                require(terminal is None)
                terminal = key
    require(type(table) is int and hook is True and counts and terminal in counts)
    return table, counts, terminal


def delta(before, after):
    require(before[0] == after[0] and set(before[1]) == set(after[1]) and before[2] == after[2])
    values = {key: after[1][key] - old for key, old in before[1].items()}
    require(all(v >= 0 for v in values.values()))
    return sum(values.values()), values[before[2]]


def tcp():
    try:
        with socket.create_connection(TARGET, timeout=3):
            return "соединилось"
    except TimeoutError:
        return "нет ответа за 3 с"
    except ConnectionRefusedError:
        return "сброс"
    except OSError:
        return "ошибка"


def https():
    conn = http.client.HTTPSConnection(
        TARGET[0], TARGET[1], timeout=5, context=ssl.create_default_context()
    )
    try:
        conn.request("HEAD", "/")
        return 200 <= conn.getresponse().status < 400
    except (OSError, http.client.HTTPException):
        return False
    finally:
        conn.close()


def permissions(paths):
    sb, xr = pwd.getpwnam(USER), pwd.getpwnam("xray")
    for path, gid in (
        (paths.xray_config_file, grp.getgrnam("xray").gr_gid),
        (paths.singbox_config_file, grp.getgrnam(USER).gr_gid),
    ):
        info = path.lstat()
        require(
            stat.S_ISREG(info.st_mode)
            and info.st_uid == 0
            and info.st_gid == gid
            and stat.S_IMODE(info.st_mode) == 0o640
        )
    rc, pid, _ = command(
        ["systemctl", "show", "--value", "--property=MainPID", "xgw-singbox.service"]
    )
    require(rc == 0 and pid.strip().isdigit() and int(pid) > 0)
    fields = dict(
        line.split(":", 1)
        for line in Path(f"/proc/{int(pid)}/status").read_text().splitlines()
        if ":" in line
    )
    require(int(fields["Uid"].split()[1]) == sb.pw_uid and int(fields["CapEff"].strip(), 16) == 0)
    require(xr.pw_gid not in {int(n) for n in fields["Groups"].split()})
    rc, after, _ = command(
        ["systemctl", "show", "--value", "--property=MainPID", "xgw-singbox.service"]
    )
    require(rc == 0 and after == pid)

    def marks(value):
        if isinstance(value, dict):
            require(
                "routing_mark" not in value
                or (type(value["routing_mark"]) is int and value["routing_mark"] == 0)
            )
            for child in value.values():
                marks(child)
        elif isinstance(value, list):
            for child in value:
                marks(child)

    marks(read(paths.singbox_config_file))


def loaded():
    rc, out, _ = command(
        [sys.executable, "-I", "-B", str(ROOT / "helper.py"), "_loaded"], timeout=8
    )
    return rc == 0 and out.strip() == b"yes"


def baseline():
    _, paths, _, identity, healthy = context()
    require(healthy and loaded())
    snap = guard()
    permissions(paths)
    require(https())
    state = read(ROOT / "state.json")
    state.update(baseline=True, identity=identity, count=sum(snap[1].values()))
    save(state)
    print("Исходный on: исправен; барьер POSTROUTING: есть; HTTPS: проходит; привилегии: верны")


def isolation():
    _cfg, paths, _, _, healthy = context()
    require(healthy)
    permissions(paths)
    state = read(ROOT / "state.json")
    require(state.get("baseline") and not ACTIVE.exists())
    # Fixed private one-byte tests: stdout is only a return code, never file data.
    script = """import os,socket,sys
try:
 if sys.argv[1]=='file':
  with open(sys.argv[2],'rb') as f:f.read(1)
 elif sys.argv[1]=='socket':
  with socket.socket(socket.AF_UNIX) as s:s.connect(sys.argv[2])
 else:
  fd=os.open(sys.argv[2],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  os.close(fd)
  try:os.unlink(sys.argv[2])
  except OSError:sys.exit(0)
except PermissionError:sys.exit(73)
except OSError:sys.exit(74)
sys.exit(0)
"""
    trial = paths.var / ".xgw-wave3-close-isolation"
    require(not trial.exists() and not trial.is_symlink())
    attempts = [
        (USER, "file", str(paths.xray_config_file)),
        (USER, "socket", "/run/xgw-xray/api.sock"),
        (USER, "write", str(trial)),
        ("xray", "file", str(paths.singbox_config_file)),
    ]
    results = []
    for user, what, target in attempts:
        rc, _, _ = command([sys.executable, "-I", "-c", script, what, target], user=user)
        results.append(rc == 73)
    if trial.exists() or trial.is_symlink():
        info = trial.lstat()
        require(
            stat.S_ISREG(info.st_mode)
            and info.st_uid == pwd.getpwnam(USER).pw_uid
            and info.st_nlink == 1
            and info.st_size == 0
        )
        trial.unlink()
        results[2] = False
    rc, _, err = command(["nft", "list", "tables"], user=USER)
    results.append(rc not in (None, 0) and b"Operation not permitted" in err)
    rc, raw, _ = command(["ip", "-j", "rule", "show"])
    require(rc == 0 and not any(r.get("priority") == 49 for r in json.loads(raw)))
    tail = ["from", "203.0.113.0/24", "lookup", "main", "pref", "49"]
    rc, _, err = command(["ip", "rule", "add", *tail], user=USER)
    if rc in (None, 0):
        cleanup, _, _ = command(["ip", "rule", "del", *tail])
        require(cleanup == 0 or (rc is None and cleanup == 2))
    results.append(rc not in (None, 0) and b"Operation not permitted" in err)
    state["isolation"] = sum(results)
    state["isolation_details"] = results
    state["stop"] = not all(results)
    save(state)
    print(f"Изоляция: {sum(results)} из 6 — отказ")
    require(all(results))


def restored(kind, cfg):
    if kind == "rule":
        rc, raw, _ = command(["ip", "-j", "rule", "show"])
        if rc != 0:
            return False
        rules = json.loads(raw)
        allowed = {"priority", "src", "dst", "fwmark", "fwmask", "iif", "table", "protocol"}

        def number(value):
            return int(str(value), 0)

        return any(
            set(r) <= allowed
            and r.get("priority") == 100
            and str(r.get("table")) == str(cfg.capture.route_table)
            and number(r.get("fwmark", "-1")) == cfg.capture.mark_proxy
            and number(r.get("fwmask", "0xffffffff")) == 0xFFFFFFFF
            and r.get("src", "all") == r.get("dst", "all") == "all"
            and r.get("iif") is None
            for r in rules
        )
    rc, raw, _ = command(["nft", "-j", "-t", "list", "table", "ip", "xgw"])
    if rc != 0:
        return False
    data = json.loads(raw)["nftables"]
    rules = [r["rule"] for r in data if "rule" in r and r["rule"].get("chain") == "output"]
    return bool(rules)  # full loaded/HTTPS is checked separately after structural return


def recover_window(kind, cfg, mutate, probe, snapshot, check, rescue, *, seconds=60):
    """One finite window. The timer is armed before mutation and does not need Flash."""
    before = snapshot()  # failure here must never arm a network-changing fallback
    done = threading.Event()
    fallback = {"called": False, "rc": None}

    def safety():
        if not done.wait(seconds):
            fallback["called"] = True
            fallback["rc"] = rescue()

    timer = threading.Thread(target=safety)
    timer.start()
    began = time.monotonic()
    result = {"result": "неопределённо", "rescue": False}
    try:
        rc = mutate()
        damaged = rc == 0 and not check()
        first = probe() if damaged else "не проверялось"
        still = not check()
        after = snapshot()
        restored_s = None
        while time.monotonic() - began < seconds:
            if check():
                restored_s = round(time.monotonic() - began, 2)
                done.set()
                break
            time.sleep(0.25)
        growth, host_growth = delta(before, after)
        evidence = damaged and still and first == "нет ответа за 3 с" and host_growth > 0
        result.update(
            probe=first,
            growth=growth,
            host_growth=host_growth,
            restored_s=restored_s,
            result="пройдено"
            if evidence and restored_s is not None and restored_s <= LIMITS[kind]
            else "неопределённо",
        )
    except Exception:
        result["result"] = "неопределённо"
        try:
            if check():
                done.set()
        except Exception:
            pass
    finally:
        # Never cancel fallback on an exception or unproven restoration.
        timer.join()
        result.update(rescue=fallback["called"], rescue_rc=fallback["rc"])
    return result


def cut_worker(kind):
    state = read(ROOT / "state.json")
    result = {"result": "не выполнялось", "rescue": False}
    try:
        cfg, _, _, identity, healthy = context()
        require(healthy and tuple(identity) == tuple(state["identity"]) and loaded() and https())
        require(cfg.capture.local and cfg.capture.hold_blocks and cfg.capture.fail_mode == "closed")
        require(cfg.free_pool.mode == "off" and not (kind == "rule" and cfg.capture.tun))
        require(
            not any(
                ipaddress.ip_address(TARGET[0]) in ipaddress.ip_network(n, strict=False)
                for n in cfg.capture.exclude_cidrs
            )
        )
        require(restored(kind, cfg) and tcp() == "соединилось")
        guard()
        argv = {
            "output": ["nft", "flush", "chain", "ip", "xgw", "output"],
            "table": ["nft", "delete", "table", "ip", "xgw"],
            "rule": [
                "ip",
                "rule",
                "del",
                "fwmark",
                str(cfg.capture.mark_proxy),
                "lookup",
                str(cfg.capture.route_table),
                "pref",
                "100",
            ],
        }[kind]
        result = recover_window(
            kind,
            cfg,
            lambda: command(argv)[0],
            tcp,
            guard,
            lambda: restored(kind, cfg),
            lambda: command(["sudo", "-n", "xgw", "net", "up"], timeout=15)[0],
        )
        result["after"] = loaded() and https() and context()[4]
        result["unchanged"] = tuple(context()[3]) == tuple(state["identity"])
        if not result["after"] or result["rescue"] or not result["unchanged"]:
            result["result"] = "не пройдено"
    except Exception:
        state["stop"] = True
        if result["result"] != "не выполнялось":
            result["result"] = "неопределённо"
    state["cuts"][kind] = result
    state["stop"] = state.get("stop", False) or result["result"] != "пройдено"
    save(state)


def watch_worker():
    state = read(ROOT / "state.json")
    state["watch"] = "неопределённо"
    try:
        require(context()[4] and loaded() and https())
        initial = guard()
        began = time.monotonic()
        end = began + 600
        growth = 0
        while time.monotonic() < end:
            time.sleep(min(5, max(0, end - time.monotonic())))
            growth, _ = delta(initial, guard())
            if growth:
                break
        state["watch"] = "пройдено" if growth == 0 and time.monotonic() >= end else "не пройдено"
        state["watch_growth"] = growth
        state["watch_seconds"] = round(time.monotonic() - began, 1)
        state["after"] = context()[4] and loaded() and https()
        state["unchanged"] = tuple(context()[3]) == tuple(state["identity"])
    except Exception:
        state["stop"] = True
    state["stop"] = (
        state.get("stop", False)
        or state["watch"] != "пройдено"
        or state.get("after") is not True
        or state.get("unchanged") is not True
    )
    save(state)


def launch(kind):
    state = read(ROOT / "state.json")
    require(not ACTIVE.exists() and state.get("baseline") and state.get("isolation") == 6)
    if kind != "watch":
        require(not state.get("stop") and state["cuts"][kind]["result"] == "не выполнялось")
        require("reason" not in state["cuts"][kind])
    else:
        require("watch" not in state)
    fd = os.open(ACTIVE, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump({"kind": kind, "start": time.monotonic()}, stream)
    try:
        subprocess.Popen(
            [sys.executable, "-I", "-B", str(ROOT / "helper.py"), "_work", kind],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd="/",
            start_new_session=True,
        )
    except BaseException:
        ACTIVE.unlink()
        raise


def report():
    data = read(ROOT / "state.json")
    lines = [
        "# Закрытие волны 3",
        "",
        f"Исходный on, барьер, HTTPS: {'пройдено' if data.get('baseline') else 'не выполнялось'}",
        f"Изоляция sing-box: {data.get('isolation', 0)} из 6 — отказ",
    ]
    if "isolation_details" in data:
        labels = (
            "конфиг Xray",
            "API Xray",
            "состояние XGW",
            "конфиг sing-box от Xray",
            "nftables",
            "ip rule",
        )
        lines.append(
            "; ".join(
                name + ": " + ("отказ" if value else "отказ не подтверждён")
                for name, value in zip(labels, data["isolation_details"], strict=True)
            )
        )
    for kind, label in KINDS.items():
        row = data["cuts"][kind]
        lines.append(
            f"{label}: {row['result']}; TCP: {row.get('probe', 'не проверялось')}; "
            f"счётчик: {row.get('host_growth', 'не проверялось')}; "
            f"возврат: {row.get('restored_s', 'не проверялось')} с; "
            f"резерв: {'вызван' if row.get('rescue') else 'не вызывался'}"
            + (f"; код резерва: {row.get('rescue_rc', 'не получен')}" if row.get("rescue") else "")
        )
        if row.get("reason") == "владелец отказал":
            lines.append("NOT_RUN: владелец отказал в этой правке.")
    final = (
        "пройдено"
        if data.get("after") is True
        else "не пройдено"
        if data.get("after") is False
        else "не проверено"
    )
    same = (
        "без изменений"
        if data.get("unchanged") is True
        else "изменились"
        if data.get("unchanged") is False
        else "не подтверждено"
    )
    lines += [
        f"Наблюдение {data.get('watch_seconds', 'не проверялось')} с: "
        f"{data.get('watch', 'не выполнялось')}; "
        f"прирост: {data.get('watch_growth', 'не проверялось')}",
        f"Конечный on и HTTPS: {final}",
        f"Настройки, пул и ручной выбор: {same}",
        "Проверки LAN, UDP, IPv6 и внешнего выхода пакетов: не выполнялись.",
        "Дополнительная диагностика REALITY не проводилась; прежний отказ отнесён к серверу.",
    ]
    if ACTIVE.exists():
        lines.append("Помощник ещё выполняется; итог не публиковать.")
    print("\n".join(lines[:2] + ["- " + line for line in lines[2:]]))


def wait():
    end = time.monotonic() + 50
    while ACTIVE.exists() and time.monotonic() < end:
        time.sleep(1)
    if ACTIVE.exists():
        job = read(ACTIVE)
        if time.monotonic() - job["start"] > (650 if job["kind"] == "watch" else 100):
            raise RuntimeError("Помощник не выдал итог; остановитесь")
        print("Проверка ещё выполняется. Повторите только wait")
        return 2
    report()
    return 3 if read(ROOT / "state.json").get("stop") else 0


def main():
    require(os.geteuid() == 0 and len(sys.argv) >= 2)
    action = sys.argv[1]
    if action == "prepare":
        require(not ROOT.exists() and not ROOT.is_symlink())
        ROOT.mkdir(mode=0o700)
        raw = Path(__file__).read_bytes()
        fd = os.open(
            ROOT / "helper.py", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
        save({"cuts": {k: {"result": "не выполнялось", "rescue": False} for k in KINDS}})
        print("Помощник подготовлен. Установленный XGW не изменён")
        return 0
    info = ROOT.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700)
    if action == "_loaded":
        require(app()[2].loaded() is True)
        print("yes")
    elif action == "_work":
        require(
            len(sys.argv) == 3
            and sys.argv[2] in (*KINDS, "watch")
            and read(ACTIVE)["kind"] == sys.argv[2]
        )
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        try:
            cut_worker(sys.argv[2]) if sys.argv[2] in KINDS else watch_worker()
        finally:
            ACTIVE.unlink()
    elif action == "baseline":
        require(not ACTIVE.exists())
        baseline()
    elif action == "isolation":
        isolation()
    elif action == "cut":
        require(len(sys.argv) == 4 and sys.argv[2] in KINDS and sys.argv[3] == "--approved")
        launch(sys.argv[2])
        return wait()
    elif action == "skip":
        require(not ACTIVE.exists() and len(sys.argv) >= 3)
        data = read(ROOT / "state.json")
        for kind in sys.argv[2:]:
            require(kind in KINDS and data["cuts"][kind]["result"] == "не выполнялось")
            data["cuts"][kind]["reason"] = "владелец отказал"
        save(data)
        print("Отказ владельца записан: правки не выполнялись")
    elif action == "watch":
        launch("watch")
        return wait()
    elif action == "wait":
        return wait()
    elif action == "report":
        report()
    else:
        require(False)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("Проверка остановлена. Не повторяйте правку; прочитайте report и сообщите владельцу")
        raise SystemExit(3) from None
