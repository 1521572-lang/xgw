"""Волна 1 (п. 330): паузы плановых проб — подготовка, установка с возвратом, наблюдение.

Режимы: prepare BASE | health | deploy BASE | observe МИНУТ. Вывод — только числа, слова
состояний и признаки: без адресов, доменов, имён серверов, тегов и SNI.
"""
import contextlib
import hashlib
import json
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

TREE = Path(__file__).resolve().parents[2]
STATUS = Path("/run/xgw/status.json")
LOCK = Path("/run/xgw-pacing-install")
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
    while time.time() < begin + minutes * 60:
        time.sleep(2)
        try:
            moment = STATUS.stat().st_mtime
        except OSError:
            continue
        if moment == last:
            continue
        marks.append(moment - last)
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
    scans = sum(1 for line in journal.splitlines() if line.startswith("скан "))
    slow = journal.count("шаг watchdog занял")
    over = sum(1 for gap in marks if gap > 25.0)
    print(f"INFO window_min={(time.time() - begin) / 60:.1f} "
          f"states={sorted(map(str, states))}", flush=True)
    print(f"INFO planned_pauses={planned} min={end.get('planned_min')} "
          f"max={end.get('planned_max')} outside={outside} idle_max_s={end.get('idle_max')}")
    print(f"INFO urgent_probes={urgent} urgent_waited={waited} scan_lines={scans} "
          f"error_lines={len([line for line in errors.splitlines() if line.strip()])}")
    median = statistics.median(marks) if marks else None
    print(f"INFO status_writes={len(marks)} median_s={median and round(median, 1)} "
          f"max_s={marks and round(max(marks), 1)} over25={over} slow_step_lines={slow}",
          flush=True)
    require(hashlib.sha256(CONFIG.read_bytes()).hexdigest() == config, "config_unchanged")
    health()
    require(over == 0, "status_every_25s")
    if planned == 0:
        print("NOT_RUN planned_pauses (плановый круг в окне не шёл)", flush=True)
        return 4
    require(outside == 0 and waited == 0, "pacing")
    return 0


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "prepare":
        prepare(Path(sys.argv[2]).resolve())
    elif sys.argv[1:] == ["health"]:
        health()
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
