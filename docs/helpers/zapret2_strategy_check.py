"""Подбор стратегии zapret2 без VPN: охват адресов YouTube, смена стратегии, замер потока.

selfcheck, listed, use и measure — от root; hosts — от пользователя браузера (тот же путь,
что у Firefox). Видеоссылки не запрашивает: ролик играет браузер, здесь только счётчики.
В вывод идут имена стратегий, общеизвестные служебные имена YouTube и числа.
"""

from __future__ import annotations

import argparse
import copy
import json
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path

_up = Path(__file__).resolve().parents  # копия для `hosts` лежит в /tmp: там src не нужен
if len(_up) > 2:
    sys.path.insert(0, str(_up[2] / "src"))

# Что открывает страница ролика и плеер. Последние два — контроль обычного прямого пути.
HOSTS = ("www.youtube.com", "redirector.googlevideo.com", "i.ytimg.com", "yt3.ggpht.com",
         "youtubei.googleapis.com", "jnn-pa.googleapis.com", "youtube.googleapis.com",
         "www.youtube-nocookie.com", "youtu.be", "www.gstatic.com", "www.google.com")
TIMEOUT = 8.0
MIB = 1024 * 1024


def loaded():
    from xgw import zapret2
    from xgw.config import load
    from xgw.paths import Paths

    paths = Paths.from_env()
    cfg, _ = load(paths.config_file)
    return zapret2, paths, cfg


def probe(host: str) -> dict:
    """TLS с проверкой сертификата и одна строка ответа на HEAD /. Тело не читается."""
    began, phase = time.monotonic(), "dns"
    try:
        address = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)[0][4]
        phase = "connect"
        with socket.create_connection(address, timeout=TIMEOUT) as raw:
            phase = "tls"
            with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as tls:
                tls.settimeout(TIMEOUT)
                phase = "http"
                tls.sendall(f"HEAD / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n"
                            "User-Agent: Mozilla/5.0\r\n\r\n".encode())
                line = tls.recv(64).split(b"\r\n", 1)[0].decode("ascii", "replace")
        status = int(line.split()[1]) if line.startswith("HTTP/") else 0
        return {"host": host, "ok": status > 0, "phase": "done" if status else "http",
                "http": status, "ms": round((time.monotonic() - began) * 1000)}
    except (OSError, ValueError, IndexError) as exc:
        kind = "timeout" if isinstance(exc, TimeoutError) else type(exc).__name__
        return {"host": host, "ok": False, "phase": phase, "error": kind,
                "ms": round((time.monotonic() - began) * 1000)}


def listed(args) -> int:
    """От root: какие из HOSTS сейчас в списке доменов zapret2 — в файл для `hosts`."""
    zapret2, _paths, cfg = loaded()
    marks = {host: zapret2.matches(host, cfg.zapret2.domains) for host in HOSTS}
    args.output.write_text(json.dumps(marks, sort_keys=True))
    args.output.chmod(0o644)
    print(f"in_list={sum(marks.values())} of {len(marks)} strategy={cfg.zapret2.strategy}")
    return 0


def hosts(args) -> int:
    """От пользователя браузера. in_list=true — адрес шёл через zapret2, false — напрямую."""
    marks = json.loads(args.listed.read_text()) if args.listed else {}
    rows = [{**probe(host), "in_list": marks.get(host)} for host in HOSTS]
    for row in rows:
        print(json.dumps(row, sort_keys=True))
    for flag, name in ((True, "zapret2"), (False, "direct")):
        part = [row for row in rows if row["in_list"] is flag]
        print(f"{name}_ok={sum(row['ok'] for row in part)} of {len(part)}")
    return 0


def selfcheck(_args) -> int:
    """Каждая стратегия — на установленном nfqws2 с --intercept=0: очередь не создаётся."""
    zapret2, _paths, cfg = loaded()
    bad = 0
    for name in zapret2.STRATEGIES:
        candidate = copy.deepcopy(cfg)
        candidate.zapret2.mode, candidate.zapret2.strategy = "standalone", name
        try:
            done = subprocess.run([*zapret2.arguments(candidate), "--intercept=0"],
                                  capture_output=True, timeout=15, check=False)
            ok = done.returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
        bad += not ok
        print(f"strategy={name} lua_check={'ok' if ok else 'FAIL'}")
    print(f"selfcheck_failed={bad}")
    return 1 if bad else 0


def status(zapret2, paths, cfg) -> dict:
    raw = json.loads(paths.status_file.read_text())
    view = raw.get("zapret2") or {}
    unit = subprocess.run(["systemctl", "show", zapret2.UNIT, "-p", "MainPID", "--value"],
                          capture_output=True, text=True, timeout=10,
                          check=False).stdout.strip()
    return {"state": view.get("state"), "reason": view.get("reason"),
            "applied": view.get("config_key") == zapret2.config_key(cfg),
            "without_vpn": bool(view.get("without_vpn")),
            "fresh": 0 <= time.time() - raw.get("updated", 0) <= 90,
            "worker_pid": int(unit) if unit.isdigit() else 0,
            "queue": zapret2.Runtime.occupied(cfg.zapret2.queue_num)}


def use(args) -> int:
    """Стратегия (и, по --domains-default, список доменов по умолчанию) — через штатное
    хранилище настроек панели; демон перечитывает их сам. Ждёт готовности обработчика."""
    from xgw import managed
    from xgw.config import Config

    zapret2, paths, cfg = loaded()
    if cfg.zapret2.mode != "standalone":
        print("STOP mode_is_not_standalone")
        return 2
    if args.strategy not in zapret2.STRATEGIES:
        print("STOP unknown_strategy")
        return 2
    settings = {"strategy": args.strategy}
    if args.domains_default:
        settings["domains"] = list(Config().zapret2.domains)
    before = status(zapret2, paths, cfg)["worker_pid"]
    changed = managed.set_zapret2(managed.path_for(paths.config_file), settings)
    deadline, state = time.monotonic() + args.wait, {}
    while time.monotonic() < deadline:
        time.sleep(2)
        try:
            zapret2, paths, cfg = loaded()
            state = status(zapret2, paths, cfg)
        except (OSError, ValueError):
            continue
        ready = (state["applied"] and state["fresh"] and state["state"] == "active"
                 and state["without_vpn"] and state["worker_pid"] > 0 and state["queue"]
                 and (not changed or state["worker_pid"] != before))
        if ready or (state["applied"] and state["state"] == "blocked"):
            break
    ok = bool(state) and state.get("state") == "active" and state.get("queue")
    print(json.dumps({"strategy": cfg.zapret2.strategy, "domains": len(cfg.zapret2.domains),
                      "changed": changed, "ready": bool(ok), **state}, sort_keys=True))
    return 0 if ok else 3


def counters(zapret2, cfg) -> tuple[int, int, int]:
    from xgw.xraycore import metrics

    rows = (metrics.fetch_metrics(cfg.xray.metrics_port).get("stats") or {}).get("outbound") or {}
    mine = rows.get(zapret2.OUT) or {}
    direct = rows.get(zapret2.DIRECT) or {}
    return int(mine.get("downlink", 0)), int(mine.get("uplink", 0)), int(direct.get("downlink", 0))


def measure(args) -> int:
    """Поток выбранных доменов за окно: байты вниз по 5-секундным отрезкам. Запускать сразу
    после старта ролика в браузере; ровный рост — ролик качается, ноль — поток стоит."""
    zapret2, paths, cfg = loaded()
    first = status(zapret2, paths, cfg)
    start = last = counters(zapret2, cfg)
    began, steps = time.monotonic(), []
    while time.monotonic() - began < args.seconds:
        time.sleep(5)
        now = counters(zapret2, cfg)
        steps.append(round((now[0] - last[0]) / 1024))
        last = now
    final = status(zapret2, paths, cfg)
    spent = time.monotonic() - began
    down = last[0] - start[0]
    print(json.dumps({
        "strategy": cfg.zapret2.strategy, "seconds": round(spent),
        "down_mib": round(down / MIB, 2), "up_kib": round((last[1] - start[1]) / 1024),
        "mbit_s": round(down * 8 / spent / 1e6, 2), "kib_per_5s": steps,
        "stalled_steps": sum(1 for step in steps if step < 16),
        "other_direct_mib": round((last[2] - start[2]) / MIB, 2),
        "worker_stable": first["worker_pid"] == final["worker_pid"] > 0,
        "state": final["state"], "queue": final["queue"],
    }, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    marks = sub.add_parser("listed")
    marks.add_argument("output", type=Path)
    marks.set_defaults(run=listed)
    check = sub.add_parser("hosts")
    check.add_argument("--listed", type=Path)
    check.set_defaults(run=hosts)
    sub.add_parser("selfcheck").set_defaults(run=selfcheck)
    one = sub.add_parser("use")
    one.add_argument("strategy")
    one.add_argument("--domains-default", action="store_true")
    one.add_argument("--wait", type=float, default=90.0)
    one.set_defaults(run=use)
    two = sub.add_parser("measure")
    two.add_argument("seconds", type=float)
    two.set_defaults(run=measure)
    args = parser.parse_args()
    return args.run(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"STOP helper_failed {type(exc).__name__}; details stay private", file=sys.stderr)
        raise SystemExit(1) from None
