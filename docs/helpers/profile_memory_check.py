"""Волна 2 (п. 336): память профилей — подготовка (стоит одна из двух BASE), логика на
минимальных данных, установка с возвратом, наблюдение.

Режимы: prepare BASE1 BASE2 | health | logic | deploy BASE | observe МИНУТ. Вывод — только
числа, слова состояний и признаки: без адресов, доменов, имён серверов, тегов и SNI.
"""
import contextlib
import hashlib
import json
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time
from pathlib import Path

TREE = Path(__file__).resolve().parents[2]
STATUS = Path("/run/xgw/status.json")
# Ход цикла демона (Daemon._loop_progress): фаза tick/sleep и длительность шага step_s.
STEP = Path("/run/xgw/watchdog-step.json")
LOCK = Path("/run/xgw-memory-install")  # каталоги прошлых волн не мешают
DB = Path("/var/lib/xgw/state.db")
CONFIG = Path("/etc/xgw/config.toml")
RECOVER_AFTER = 45.0  # приёмка после установки не дольше — затем сразу возврат (предел 60 с)


def run(argv, *, timeout=20):
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=True).stdout


def require(ok, label):
    if not ok:
        print("STOP " + label, flush=True)
        raise ValueError(label)
    print("OK " + label, flush=True)


def health():
    data = json.loads(run(["xgw", "status", "--json"], timeout=10))
    cap = data.get("capture") or {}
    require(data.get("daemon_down") is False and data.get("xray", {}).get("ok") is True
            and cap.get("mode") == "on" and cap.get("loaded") is True
            and cap.get("blocked") is False and not cap.get("capture_failed"), "on")
    code = run(["curl", "--silent", "--noproxy", "*", "--max-time", "8", "-o", "/dev/null",
                "-w", "%{http_code}", "https://1.1.1.1/"], timeout=12)
    require(code.isdigit() and 200 <= int(code) < 400, "https")


def check_health():
    try:
        health()
        return True
    except (ValueError, OSError, subprocess.SubprocessError):
        return False


def match(tree):
    files = run(["git", "-c", f"safe.directory={tree}", "-C", str(tree), "ls-files", "-z",
                 "src/xgw", "packaging"]).rstrip("\0").split("\0")
    if not files or not all(files):
        return False
    for name in files:
        dest = Path("/opt/xgw") / ("lib/" + name[4:] if name.startswith("src/") else name)
        if not dest.is_file() or dest.read_bytes() != (tree / name).read_bytes():
            return False
    return True


def memory_counts():
    """Сколько записей в памяти профилей (meta profile_trials) — только числа, только чтение."""
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = 'profile_trials'").fetchone()
    saved = json.loads(row[0]) if row and row[0] else {}
    keys = ("trials", "switched", "escalated", "closed", "unstable", "worked", "failed")
    return {key: len(saved.get(key) or {}) for key in keys}


def prepare(bases):
    """Только чтение: ни каталогов, ни файлов. Повтор безопасен. На машине должна стоять одна
    из двух BASE (окно до или после ТЗ gui-s3b) — какая, сказано в installed_is."""
    require(all(shutil.which(name) for name in ("git", "curl", "journalctl", "systemctl")),
            "tools")
    for tree in (TREE, *bases):
        run(["sh", "-n", str(tree / "packaging/install.sh")])
    print("OK install_scripts_parse", flush=True)
    if LOCK.exists():
        # Чужой или идущий запуск не трогаем: только сообщаем.
        state = "finished" if (LOCK / "result").exists() else "active"
        print(f"STOP lock_{state}", flush=True)
        raise ValueError("lock")
    health()
    found = [tree for tree in bases if match(tree)]
    require(len(found) == 1, "installed_is_one_base")
    sha = run(["git", "-c", f"safe.directory={found[0]}", "-C", str(found[0]), "rev-parse",
               "--short", "HEAD"]).strip()
    print(f"installed_is={sha} dir={found[0].name}", flush=True)
    print("INFO memory " + json.dumps(memory_counts(), sort_keys=True), flush=True)
    print("config_sha=" + hashlib.sha256(CONFIG.read_bytes()).hexdigest()[:16], flush=True)
    print("OK prepare", flush=True)


def deploy(base):
    LOCK.mkdir(mode=0o700)  # второй запуск при живом каталоге не начнёт вторую установку
    try:
        ready = match(base) and check_health()
    except (OSError, subprocess.SubprocessError):
        ready = False
    if not ready:
        LOCK.rmdir()  # ничего не начато — каталог не оставляем
        print("STOP baseline", flush=True)
        raise ValueError("baseline")
    print("OK baseline", flush=True)

    def install(tree, name):
        with (LOCK / (name + ".log")).open("xb") as stream:
            try:
                rc = subprocess.run(["sh", str(tree / "packaging/install.sh"), "--yes"],
                                    stdout=stream, stderr=subprocess.STDOUT).returncode
            except OSError:
                rc = 127
        print(f"{name}_rc={rc} at={time.strftime('%H:%M:%S')}", flush=True)
        return rc

    accepted = False
    try:
        if install(TREE, "install") == 0 and match(TREE):
            done = time.monotonic()
            while not accepted and time.monotonic() - done < RECOVER_AFTER:
                accepted = check_health()
                if not accepted:
                    time.sleep(3)
    finally:
        if not accepted:
            print(f"recovery_started_at={time.strftime('%H:%M:%S')}", flush=True)
            rc = install(base, "rollback")
            restored, tries = False, 6 if rc == 0 and match(base) else 0
            while not restored and tries:  # до ~1 мин на подъём связи после возврата
                restored, tries = check_health(), tries - 1
                if not restored:
                    time.sleep(5)
            print("rollback_verified=" + str(restored).lower(), flush=True)
        (LOCK / "result").write_text("accepted\n" if accepted else "returned\n")
    require(accepted, "installed")


def logic():
    """Код CODE на минимальных данных, без сети: порядок лестницы по памяти, сроки, ключ."""
    sys.path.insert(0, str(TREE / "src"))
    from xgw.generator import profiles

    ladder = profiles.ladder("FROZEN", profiles.XRAY_DEFAULT, profiles.XRAY_DEFAULT,
                             list(profiles.ALL))
    worked = {"profile": profiles.SB_FRAGMENT, "ts": 1000.0, "key": "k"}
    failed = {"key": "k", "steps": {profiles.XRAY_FRAGMENT: 1000.0}}
    order = profiles.remembered(ladder, key="k", now=2000.0, worked=worked, failed=failed)
    before = ladder.index(profiles.SB_FRAGMENT) + 1
    after = order.index(profiles.SB_FRAGMENT) + 1
    print(f"INFO attempts_before={before} attempts_after={after} "
          f"failed_last={order[-1] == profiles.XRAY_FRAGMENT}", flush=True)
    require(before == 4 and after == 1 and order[-1] == profiles.XRAY_FRAGMENT, "memory_order")
    require(profiles.remembered(ladder, key="new", now=2000.0, worked=worked,
                                failed=failed) == ladder, "new_params_no_false_success")
    late = 1000.0 + profiles.FAILED_KEEP + 1
    require(profiles.remembered(ladder, key="k", now=late, failed=failed) == ladder,
            "expired_failure_allowed")
    require(profiles.remembered(ladder, key="k", now=500.0, worked=worked,
                                failed=failed) == ladder, "clock_back_no_ban")
    print(f"INFO keep worked_h={profiles.WORKED_KEEP / 3600:.0f} "
          f"failed_h={profiles.FAILED_KEEP / 3600:.0f}", flush=True)
    print("OK logic", flush=True)


def snapshot():
    return json.loads(STATUS.read_text(encoding="utf-8"))


def classify_gaps(gaps, steps, interval):
    """Разрывы записи статуса > 25 с: (зависаний, «разрыв/шаг»). До 1,2·interval_s + шаг —
    обычный долгий шаг (справочно); больше или без шага рядом — зависание (FAIL)."""
    hung, explained = 0, []
    for gap_from, gap_to in gaps:
        length = gap_to - gap_from
        if length <= 25.0:
            continue
        near = [spent for when, spent in steps if gap_from < when <= gap_to + 70.0]
        if near and length <= 1.2 * interval + max(near) + 2.0:
            explained.append(f"{length:.1f}/{max(near):.1f}")
        else:
            hung += 1
    return hung, explained


def observe(minutes):
    begin, data = time.time(), snapshot()
    pacing = data.get("scan_pacing") or {}
    require("totals" in pacing, "pacing_fields")
    first = pacing["totals"]
    print(f"INFO state={data.get('state')} scan_minutes="
          f"{(data.get('budget') or {}).get('scan_minutes')} "
          f"next_planned_in_s={pacing.get('next_planned_in_s')}", flush=True)
    config = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    memory_before = memory_counts()
    marks, last, states = [], STATUS.stat().st_mtime, set()
    gaps, steps, seen = [], [], None  # разрывы (начало, конец); шаги (когда замечен, step_s)
    interval = float(data.get("interval_s") or 20)
    while time.time() < begin + minutes * 60:
        time.sleep(1)
        with contextlib.suppress(OSError, ValueError):
            step = json.loads(STEP.read_text(encoding="utf-8"))
            key = (step.get("phase"), step.get("started"))
            if key != seen:
                seen = key
                interval = float(step.get("interval_s") or interval)
                if step.get("phase") == "sleep" and isinstance(step.get("step_s"), (int, float)):
                    steps.append((time.time(), float(step["step_s"])))
        try:
            moment = STATUS.stat().st_mtime
        except OSError:
            continue
        if moment == last:
            continue
        marks.append(moment - last)
        gaps.append((last, moment))
        last = moment
        with contextlib.suppress(OSError, ValueError):
            states.add(snapshot().get("state"))
    totals = (snapshot().get("scan_pacing") or {}).get("totals") or {}
    planned = totals.get("planned", 0) - first.get("planned", 0)
    outside = totals.get("planned_outside", 0) - first.get("planned_outside", 0)
    urgent = totals.get("urgent", 0) - first.get("urgent", 0)
    waited = totals.get("urgent_waited", 0) - first.get("urgent_waited", 0)
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(begin))
    journal = run(["journalctl", "-u", "xgw", "--since", since, "-o", "cat", "--no-pager"],
                  timeout=60)
    errors = run(["journalctl", "-u", "xgw", "-p", "err", "--since", since, "-o", "cat",
                  "--no-pager"], timeout=60).strip().splitlines()
    scans = journal.count("daemon: скан ")  # строка журнала: «время INFO daemon: скан …»
    unparsed = journal.count("не разобран")  # «записи о пробах профилей … не разобраны»
    ladders = journal.count("пробую «")  # строки лестницы: «… — пробую «профиль»»
    memory_after, slow = memory_counts(), journal.count("шаг watchdog занял")
    over = sum(1 for gap in marks if gap > 25.0)
    hung, explained = classify_gaps(gaps, steps, interval)
    print(f"INFO window_min={(time.time() - begin) / 60:.1f} states={sorted(map(str, states))}")
    print(f"INFO planned_pauses={planned} min={totals.get('planned_min')} "
          f"max={totals.get('planned_max')} outside={outside}")
    print(f"INFO urgent_probes={urgent} urgent_waited={waited} scan_lines={scans} "
          f"error_lines={len(errors)}")
    diag = (snapshot().get("scan_pacing") or {}).get("diagnosis") or {}
    print(f"INFO diagnosis workers={diag.get('workers')} budget_s={diag.get('budget_s')} "
          f"pending={diag.get('pending')}", flush=True)
    median = statistics.median(marks) if marks else None
    print(f"INFO status_writes={len(marks)} median_s={median and round(median, 1)} "
          f"max_s={marks and round(max(marks), 1)} over25={over} slow_step_lines={slow} "
          f"long_steps={explained} hung={hung} steps_seen={len(steps)} "
          f"step_max_s={steps and round(max(spent for _w, spent in steps), 1)}",
          flush=True)
    print(f"INFO memory_before={json.dumps(memory_before, sort_keys=True)} memory_after="
          f"{json.dumps(memory_after, sort_keys=True)} unparsed_lines={unparsed} "
          f"ladder_lines={ladders}", flush=True)
    require(hashlib.sha256(CONFIG.read_bytes()).hexdigest() == config, "config_unchanged")
    health()
    require(bool(steps), "watchdog_steps_seen")
    require(hung == 0, "status_without_hang")
    require(diag.get("workers") == 2 and diag.get("budget_s") == 16.0, "diagnosis_fields")
    require(outside == 0 and waited == 0, "pacing_regression")
    require(unparsed == 0, "memory_records_parsed")
    used = any(memory_after[key] != memory_before[key] for key in ("worked", "failed"))
    if used or ladders:
        print("OK memory_used_in_window", flush=True)
        return 0
    print("NOT_RUN memory (лестницы профилей в окне не было — повода не было)", flush=True)
    return 4


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "prepare":
        prepare([Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()])
    elif sys.argv[1:] == ["health"]:
        health()
    elif sys.argv[1:] == ["logic"]:
        logic()
    elif len(sys.argv) == 3 and sys.argv[1] == "deploy":
        deploy(Path(sys.argv[2]).resolve())
    elif len(sys.argv) == 3 and sys.argv[1] == "observe" and sys.argv[2].isdigit():
        return observe(int(sys.argv[2]))
    else:
        return 2
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:
        # Не выводим тексты системных команд, адреса и конфиги. Последний OK указывает этап.
        print("STOP", type(exc).__name__, flush=True)
        code = 3
    print(f"helper_rc={code}", flush=True)
    sys.exit(code)
