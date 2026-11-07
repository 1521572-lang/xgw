"""Волна 1б (п. 332): проверка адреса проб по два запроса с дедлайном — подготовка, логика на
подменённых пробах, установка с возвратом, наблюдение.

Режимы: prepare BASE | health | logic | deploy BASE | observe МИНУТ. Вывод — только числа,
слова состояний и признаки: без адресов, доменов, имён серверов, тегов и SNI.
"""
import contextlib
import hashlib
import json
import shutil
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

TREE = Path(__file__).resolve().parents[2]
STATUS = Path("/run/xgw/status.json")
# Ход цикла демона (Daemon._loop_progress): фаза tick/sleep и длительность шага step_s.
STEP = Path("/run/xgw/watchdog-step.json")
LOCK = Path("/run/xgw-diag-install")  # каталог волны 1 (/run/xgw-pacing-install) не мешает
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


def prepare(base):
    """Только чтение: ни каталогов, ни файлов. Повтор безопасен."""
    require(all(shutil.which(name) for name in ("git", "curl", "journalctl", "systemctl")),
            "tools")
    for tree in (TREE, base):
        run(["sh", "-n", str(tree / "packaging/install.sh")])
    print("OK install_scripts_parse", flush=True)
    if LOCK.exists():
        # Чужой или идущий запуск не трогаем: только сообщаем.
        state = "finished" if (LOCK / "result").exists() else "active"
        print(f"STOP lock_{state}", flush=True)
        raise ValueError("lock")
    health()
    require(match(base), "installed_is_base")
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
            while True:
                if check_health():
                    accepted = True
                    break
                if time.monotonic() - done >= RECOVER_AFTER:
                    break
                time.sleep(3)
    finally:
        if not accepted:
            print(f"recovery_started_at={time.strftime('%H:%M:%S')}", flush=True)
            rc = install(base, "rollback")
            restored = False
            if rc == 0 and match(base):
                for _ in range(6):  # до ~1 мин на подъём связи после возврата
                    restored = check_health()
                    if restored:
                        break
                    time.sleep(5)
            print("rollback_verified=" + str(restored).lower(), flush=True)
        (LOCK / "result").write_text("accepted\n" if accepted else "returned\n")
    require(accepted, "installed")


def logic():
    """Код CODE на подменённых пробах, без сети: предел 2, дедлайн, остановка."""
    sys.path.insert(0, str(TREE / "src"))
    from xgw.generator.builder import NodeInfo
    from xgw.watch import target
    from xgw.watch.scan import ScanResult

    nodes = [NodeInfo(f"f{i}", f"proxy-{i}", f"probe-{i}", 1, "proxy") for i in range(6)]
    lock, now, top = threading.Lock(), [0], [0]

    def probe(info, pause):
        with lock:
            now[0] += 1
            top[0] = max(top[0], now[0])
        time.sleep(pause)
        with lock:
            now[0] -= 1
        return ScanResult(info.tag, "TIMEOUT", 0, pause, kind="timeout")

    results, parallel = target.probe_sample(
        nodes, lambda info: probe(info, 0.05), workers=2,
        cut=target.Cutoff(None, time.monotonic() + 30))
    print(f"INFO all results={len(results)} max_parallel={parallel}", flush=True)
    require(len(results) == 6 and parallel == 2 and top[0] == 2, "two_at_a_time")
    started = time.monotonic()
    part, _parallel = target.probe_sample(
        nodes, lambda info: probe(info, 0.3), workers=2,
        cut=target.Cutoff(None, time.monotonic() + 0.5))
    print(f"INFO deadline results={len(part)} of=6 seconds={time.monotonic() - started:.1f}",
          flush=True)
    require(0 < len(part) < 6, "deadline_leaves_rest_unstarted")
    stop = threading.Event()
    stop.set()
    none, _parallel = target.probe_sample(
        nodes, lambda info: probe(info, 0.01), workers=2,
        cut=target.Cutoff(stop, time.monotonic() + 30))
    require(none == [], "stop_starts_nothing")
    incomplete = target.Diagnosis(False, complete=False)
    require(not incomplete.down and not incomplete.complete, "incomplete_is_no_verdict")
    print("OK logic", flush=True)


def snapshot():
    return json.loads(STATUS.read_text(encoding="utf-8"))


def observe(minutes):
    begin, data = time.time(), snapshot()
    pacing = data.get("scan_pacing") or {}
    require("totals" in pacing, "pacing_fields")
    first = pacing["totals"]
    print(f"INFO state={data.get('state')} scan_minutes="
          f"{(data.get('budget') or {}).get('scan_minutes')} "
          f"next_planned_in_s={pacing.get('next_planned_in_s')}", flush=True)
    config = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
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
    end = (snapshot().get("scan_pacing") or {}).get("totals") or {}
    planned = end.get("planned", 0) - first.get("planned", 0)
    outside = end.get("planned_outside", 0) - first.get("planned_outside", 0)
    urgent = end.get("urgent", 0) - first.get("urgent", 0)
    waited = end.get("urgent_waited", 0) - first.get("urgent_waited", 0)
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(begin))
    journal = run(["journalctl", "-u", "xgw", "--since", since, "-o", "cat", "--no-pager"],
                  timeout=60)
    errors = run(["journalctl", "-u", "xgw", "-p", "err", "--since", since, "-o", "cat",
                  "--no-pager"], timeout=60)
    scans = journal.count("daemon: скан ")  # строка журнала: «время INFO daemon: скан …»
    unfinished = journal.count("проверка адреса проб не закончена")
    slow = journal.count("шаг watchdog занял")
    over = sum(1 for gap in marks if gap > 25.0)
    # Статус пишется после сигналов и в конце шага, шаг начинается через interval_s ±20 % от
    # начала прошлого: разрыв до 1,2·interval_s + длительность шага — обычный долгий шаг
    # (справочно). Разрыв больше, или ни одного законченного шага рядом, — зависание (FAIL).
    hung, explained = 0, []
    for start, end in gaps:
        if end - start <= 25.0:
            continue
        near = [spent for when, spent in steps if start < when <= end + 70.0]
        if near and end - start <= 1.2 * interval + max(near) + 2.0:
            explained.append(f"{end - start:.1f}/{max(near):.1f}")
        else:
            hung += 1
    print(f"INFO window_min={(time.time() - begin) / 60:.1f} "
          f"states={sorted(map(str, states))}", flush=True)
    print(f"INFO planned_pauses={planned} min={end.get('planned_min')} "
          f"max={end.get('planned_max')} outside={outside} idle_max_s={end.get('idle_max')}")
    print(f"INFO urgent_probes={urgent} urgent_waited={waited} scan_lines={scans} "
          f"error_lines={len([line for line in errors.splitlines() if line.strip()])}")
    diag = (snapshot().get("scan_pacing") or {}).get("diagnosis") or {}
    ran = diag.get("ts") is not None and diag["ts"] >= begin
    print(f"INFO diagnosis workers={diag.get('workers')} budget_s={diag.get('budget_s')} "
          f"pending={diag.get('pending')} ran_in_window={ran} "
          f"max_parallel={diag.get('max_parallel')} complete={diag.get('complete')} "
          f"unfinished_lines={unfinished}", flush=True)
    median = statistics.median(marks) if marks else None
    print(f"INFO status_writes={len(marks)} median_s={median and round(median, 1)} "
          f"max_s={marks and round(max(marks), 1)} over25={over} slow_step_lines={slow} "
          f"long_steps={explained} hung={hung} steps_seen={len(steps)} "
          f"step_max_s={steps and round(max(spent for _w, spent in steps), 1)}",
          flush=True)
    require(hashlib.sha256(CONFIG.read_bytes()).hexdigest() == config, "config_unchanged")
    health()
    require(bool(steps), "watchdog_steps_seen")
    require(hung == 0, "status_without_hang")
    require(diag.get("workers") == 2 and diag.get("budget_s") == 16.0, "diagnosis_fields")
    require(outside == 0 and waited == 0, "pacing_regression")
    if ran:
        require((diag.get("max_parallel") or 0) <= 2, "diagnosis_two_at_a_time")
        return 0
    print("NOT_RUN diagnosis (повода — отказа всех участников — в окне не было)", flush=True)
    return 4


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "prepare":
        prepare(Path(sys.argv[2]).resolve())
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
