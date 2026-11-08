"""Причина LEAK после установки bridge-order-r2 и пересборки демона — только чтение.

Режим: report ЧАСОВ. Без сети, без записи. Вывод — виды причин, числа и время: текст событий
не выводится (в нём тег сервера). Причины LEAK (Daemon._handle_leak): own_exit — сервер сам
выходит в домашнюю страну и меняется запасным; pinned — так выходит выбранный вручную;
bypass — проверка через Xray не показала домашнюю страну: трафик мимо Xray или проверка
через Xray в этот момент не удалась (одной записью эти случаи не различить).
"""
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

DB = Path("/var/lib/xgw/state.db")
STARTED = Path("/run/xgw-bridge2-install/started")
INSTALL_LOG = Path("/run/xgw-bridge2-install/install.log")
AROUND_BEFORE, AROUND_AFTER = 60.0, 900.0  # что считать «при установке»
SWITCHED = "поколение sing-box сменено"
REFUSED = "не прошло настоящий запрос через мост"
INSTALL_SWITCH = "новое поколение выбрано через API"
INSTALL_REFUSE = "конфиг sing-box отклонён"
SUMMARY = re.compile(r"мостов проверено [0-9]+ из [0-9]+(: [a-z]+ [0-9]+(, [a-z]+ [0-9]+)*)?")


def run(argv, *, timeout=60):
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=True).stdout


def clock(moment):
    return time.strftime("%H:%M:%S", time.localtime(moment))


def classify(detail):
    if "выбранный вручную" in detail:
        return "pinned"
    if "мимо Xray" in detail:
        return "bypass"
    if "сам выходит" in detail:
        return "own_exit"
    return "other"


def events(kind, since):
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5) as conn:
        return conn.execute("SELECT ts, detail FROM events WHERE kind = ? AND ts >= ? ORDER BY ts",
                            (kind, since)).fetchall()


def started():
    try:
        return float(STARTED.read_text())
    except (OSError, ValueError):
        return None


def unit_start(unit):
    text = run(["systemctl", "show", "--timestamp=unix", "-p", "ActiveEnterTimestamp", "--value",
                unit], timeout=10).strip()
    return float(text[1:]) if text.startswith("@") else None


def verdict(rows, install):
    """Итог по записям LEAK рядом с установкой; install None — установка неизвестна."""
    if install is None:
        return "unknown_install"
    near = [classify(detail) for ts, detail in rows
            if install - AROUND_BEFORE <= ts <= install + AROUND_AFTER]
    if not near:
        return "none_near_install"
    return near[0] if len(set(near)) == 1 else "mixed"


def report(hours):
    since, install = time.time() - hours * 3600, started()
    state = json.loads(run(["xgw", "status", "--json"], timeout=10)).get("state")
    print(f"INFO window_h={hours} state={state} install_start="
          f"{clock(install) if install else 'none'}", flush=True)
    for unit in ("xgw", "xgw-xray"):
        moment = unit_start(unit)
        print(f"INFO unit_start {unit}={clock(moment) if moment else 'none'}", flush=True)
    rows = events("leak", since)
    totals = dict.fromkeys(("own_exit", "pinned", "bypass", "other"), 0)
    for _ts, detail in rows:
        totals[classify(detail)] += 1
    print("INFO leak_totals " + json.dumps(totals, sort_keys=True), flush=True)
    for ts, detail in rows[-12:]:
        offset = f" after_install_s={ts - install:.0f}" if install else ""
        print(f"INFO leak at={clock(ts)} cause={classify(detail)}{offset}", flush=True)
    if install is not None:
        rotations = [ts for ts, _d in events("rotation", install)
                     if ts <= install + AROUND_AFTER]
        print(f"INFO rotations_after_install={len(rotations)}", flush=True)
    frame = install if install is not None else since
    text = run(["journalctl", "-u", "xgw", "--since", f"@{frame:.0f}", "-o", "short-unix",
                "--no-pager"])
    switched, refused, found = [], 0, []
    for line in text.splitlines():
        stamp = line.split(" ", 1)[0]
        if SWITCHED in line and stamp.replace(".", "").isdigit():
            switched.append(clock(float(stamp)))
        if REFUSED in line:
            refused += 1
            found.extend(match.group(0) for match in SUMMARY.finditer(line))
    print(f"INFO daemon_generation switched={len(switched)} times={switched[-5:]} "
          f"refused={refused}", flush=True)
    for summary in found[-5:]:
        print("INFO refusal " + summary, flush=True)
    try:
        log = INSTALL_LOG.read_text(encoding="utf-8", errors="replace")
        print(f"INFO install_log switched={log.count(INSTALL_SWITCH)} "
              f"refused={log.count(INSTALL_REFUSE)}", flush=True)
    except OSError:
        print("INFO install_log none", flush=True)
    print("RESULT " + verdict(rows, install), flush=True)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "report" and sys.argv[2].isdigit():
        report(int(sys.argv[2]))
        return 0
    return 2


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        # Не выводим тексты системных команд и записи базы.
        print("STOP", type(exc).__name__, flush=True)
        code = 3
    print(f"helper_rc={code}", flush=True)
    sys.exit(code)
