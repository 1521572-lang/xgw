"""Замена сервера с выходом в домашнюю страну после снятия LEAK (п. 340): подготовка, установка
с возвратом, наблюдение. После установки демон не помнит такие серверы, поэтому случай из
отчёта leak-cause может повториться сам; вызывать его нельзя.

Режимы: prepare BASE | health | deploy BASE | observe МИНУТ. Вывод — только числа, слова
состояний и виды записей: текст событий (в нём тег сервера) не выводится.
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
LOCK = Path("/run/xgw-homeexit-install")
CONFIG = Path("/etc/xgw/config.toml")
DB = Path("/var/lib/xgw/state.db")
RECOVER_AFTER = 45.0  # приёмка после установки не дольше — затем сразу возврат
SWITCHED = "поколение sing-box сменено"
REFUSED = "не прошло настоящий запрос через мост"
PROMISED = "меняю его на запасной"
ROTATED = "сами выходят в"


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


def counts():
    data = json.loads(run(["xgw", "status", "--json"], timeout=10))
    return data.get("state"), len(data.get("members") or []), len(data.get("spares") or [])


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
    state, members, spares = counts()
    print(f"INFO state={state} members={members} spares={spares}", flush=True)
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


def observe(minutes):
    """Только чтение: состояния, записи LEAK и замены с начала установки."""
    begin = time.time()
    config = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    states, last = set(), None
    while time.time() < begin + minutes * 60:
        with contextlib.suppress(ValueError, OSError, subprocess.SubprocessError):
            last = counts()
            states.add(str(last[0]))
        time.sleep(15)
    try:
        start, origin = float((LOCK / "started").read_text()), "install"
    except (OSError, ValueError):
        start, origin = begin, "window"
    print("INFO from=" + origin, flush=True)
    leaks = events("leak", start)
    promised = [ts for ts, detail in leaks if PROMISED in detail]
    bypass = sum("мимо Xray" in detail for _ts, detail in leaks)
    rotations = events("rotation", start)
    home = [ts for ts, detail in rotations if ROTATED in detail]
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start))
    text = run(["journalctl", "-u", "xgw", "--since", since, "-o", "cat", "--no-pager"],
               timeout=60)
    print(f"INFO window_min={(time.time() - begin) / 60:.1f} states={sorted(states)} "
          f"last={last[1:] if last else None}", flush=True)
    print(f"INFO leak total={len(leaks)} promised={len(promised)} bypass={bypass}", flush=True)
    delay = f"{home[0] - promised[0]:.0f}" if promised and home else "none"
    print(f"INFO rotations total={len(rotations)} home={len(home)} delay_s={delay}", flush=True)
    print(f"INFO generation switched={text.count(SWITCHED)} refused={text.count(REFUSED)}",
          flush=True)
    require(hashlib.sha256(CONFIG.read_bytes()).hexdigest() == config, "config_unchanged")
    health()
    if not promised:
        print("NOT_RUN home_exit (сервера с выходом в домашнюю страну в окне не было)", flush=True)
        return 4
    if home:
        print("OK home_member_replaced", flush=True)
        return 0
    print("STOP home_member_not_replaced", flush=True)
    return 5


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
