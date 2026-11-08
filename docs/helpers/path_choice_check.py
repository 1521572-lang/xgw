"""Разные пути при замене сервера (п. 341): подготовка, установка с возвратом, наблюдение.

Настоящую замену вызвать нельзя: если её в окне не было — NOT_RUN по этой части.
Режимы: prepare BASE | health | deploy BASE | observe МИНУТ. Вывод — только числа, слова
состояний и виды причин: текст событий (в нём теги серверов) и адреса не выводятся.
"""
import contextlib
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

TREE = Path(__file__).resolve().parents[2]
LOCK = Path("/run/xgw-pathchoice-install")
CONFIG = Path("/etc/xgw/config.toml")
DB = Path("/var/lib/xgw/state.db")
STATUS = Path("/run/xgw/status.json")
RECOVER_AFTER = 45.0  # приёмка после установки не дольше — затем сразу возврат
STATUS_LIMIT = 25.0  # предел задания: запись status.json
SWITCHED = "поколение sing-box сменено"
REFUSED = "не прошло настоящий запрос через мост"
KINDS = (("both", "другой адрес и другой путь"), ("address", "другой адрес, тот же путь"),
         ("transport", "тот же адрес, другой путь"), ("same", "тот же адрес и путь"),
         ("unknown", "путь не известен"))


def run(argv, *, timeout=20):
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=True).stdout


def require(ok, label):
    if not ok:
        print("STOP " + label, flush=True)
        raise ValueError(label)
    print("OK " + label, flush=True)


def status():
    return json.loads(run(["xgw", "status", "--json"], timeout=10))


def health():
    data = status()
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


def events(kind, since):
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5) as conn:
        return conn.execute("SELECT ts, detail FROM events WHERE kind = ? AND ts >= ? ORDER BY ts",
                            (kind, since)).fetchall()


def prepare(base):
    """Только чтение: ни каталогов, ни файлов. Повтор безопасен."""
    require(all(shutil.which(name) for name in ("git", "curl", "journalctl", "systemctl")),
            "tools")
    for tree in (TREE, base):
        run(["sh", "-n", str(tree / "packaging/install.sh")])
    print("OK install_scripts_parse", flush=True)
    if LOCK.exists():
        state = "finished" if (LOCK / "result").exists() else "active"
        print(f"STOP lock_{state}", flush=True)
        raise ValueError("lock")
    health()
    require(match(base), "installed_is_base")
    data = status()
    print(f"INFO state={data.get('state')} members={len(data.get('members') or [])} "
          f"spares={len(data.get('spares') or [])}", flush=True)
    print("config_sha=" + hashlib.sha256(CONFIG.read_bytes()).hexdigest()[:16], flush=True)
    print("OK prepare", flush=True)


def deploy(base):
    LOCK.mkdir(mode=0o700)  # второй запуск при живом каталоге не начнёт вторую установку
    (LOCK / "started").write_text(f"{time.time():.0f}\n")  # начало отсчёта для observe
    try:
        ready = match(base) and check_health()
    except (OSError, subprocess.SubprocessError):
        ready = False
    if not ready:
        (LOCK / "started").unlink()
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


def kinds_of(rows):
    """Сколько замен с каждым видом причины; одна запись может содержать несколько."""
    return {key: sum(phrase in detail for _ts, detail in rows) for key, phrase in KINDS}


def observe(minutes):
    """Только чтение: сводка запаса, возраст status.json, причины замен с начала установки."""
    begin = time.time()
    config = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    states, seen, oldest = set(), [], 0.0
    while time.time() < begin + minutes * 60:
        with contextlib.suppress(ValueError, OSError, subprocess.SubprocessError):
            data = status()
            states.add(str(data.get("state")))
            seen.append(data.get("selection"))
            oldest = max(oldest, time.time() - STATUS.stat().st_mtime)
        time.sleep(15)
    try:
        start, origin = float((LOCK / "started").read_text()), "install"
    except (OSError, ValueError):
        start, origin = begin, "window"
    print("INFO from=" + origin, flush=True)
    last = next((item for item in reversed(seen) if isinstance(item, dict)), None)
    print(f"INFO window_min={(time.time() - begin) / 60:.1f} states={sorted(states)} "
          f"status_age_max_s={oldest:.0f}", flush=True)
    require(last is not None, "selection_present")
    good, paths = last.get("spares_ok", -1), last.get("paths", -1)
    other = last.get("other_paths", -1)
    print(f"INFO selection spares_ok={good} paths={paths} other_paths={other} "
          f"note={last.get('note') or 'нет'}", flush=True)
    require(0 <= other <= paths <= good, "selection_counts")
    rotations = events("rotation", start)
    kinds = kinds_of(rotations)
    print(f"INFO rotations total={len(rotations)} reasons={json.dumps(kinds, sort_keys=True)}",
          flush=True)
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start))
    text = run(["journalctl", "-u", "xgw", "--since", since, "-o", "cat", "--no-pager"],
               timeout=60)
    print(f"INFO generation switched={text.count(SWITCHED)} refused={text.count(REFUSED)}",
          flush=True)
    require("Запас:" in run(["xgw", "status"], timeout=10), "status_line")
    require(hashlib.sha256(CONFIG.read_bytes()).hexdigest() == config, "config_unchanged")
    health()
    if oldest > STATUS_LIMIT:
        print("WARN status_age", flush=True)
    if sum(kinds.values()):
        print("OK reason_recorded", flush=True)
        return 0
    print("NOT_RUN replacement (замены с причиной в окне не было)", flush=True)
    return 4


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
