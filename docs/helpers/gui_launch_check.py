"""Ярлык и значок открывают окно XGW (п. 344): подготовка, установка с возвратом, запуск.

Режимы: prepare BASE | health | deploy BASE | launch | observe МИНУТ (launch — от владельца,
в его графическом сеансе; остальные — sudo). Вывод — только числа и признаки.
"""
import contextlib
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

TREE = Path(__file__).resolve().parents[2]
LOCK = Path("/run/xgw-guilaunch-install")
DESKTOP = Path("/usr/local/share/applications/xgw-panel.desktop")
CONFIG = Path("/etc/xgw/config.toml")
STATUS = Path("/run/xgw/status.json")
RECOVER_AFTER = 45.0  # приёмка после установки не дольше — затем сразу возврат
STATUS_LIMIT = 25.0  # предел задания: запись status.json


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
          f"spares={len(data.get('spares') or [])} "
          f"subscriptions={len(data.get('subscriptions') or [])}", flush=True)
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


def gui_pids():
    """Процессы `xgw gui` этого человека."""
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        with contextlib.suppress(OSError):
            if entry.stat().st_uid != os.getuid():
                continue
            words = [word.decode("utf-8", "replace")
                     for word in (entry / "cmdline").read_bytes().split(bytes(1)) if word]
            if "gui" in words and "tray" not in words and any(
                    Path(word).name == "xgw" for word in words):
                found.append(int(entry.name))
    return found


def wait_for(check, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.25)
    return check()


def launch():
    """От владельца: ярлык как он есть. Окно, открытое до проверки, остаётся; своё закрывается."""
    require(os.getuid() != 0, "not_root")
    require(bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")), "graphic_session")
    lines = [line[5:] for line in DESKTOP.read_text(encoding="utf-8").splitlines()
             if line.startswith("Exec=")]
    require(bool(lines) and " tray --window " in lines[0], "shortcut_opens_window")
    command = lines[0].split()
    url = command[-1]
    require(any(line.endswith(" tray --open " + url) for line in lines), "shortcut_browser_action")
    require(any(line.endswith(" panel --login") for line in lines), "shortcut_login_action")
    code = "none"
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        code = run(["curl", "--silent", "--noproxy", "*", "--max-time", "5", "-o", "/dev/null",
                    "-w", "%{http_code}", url], timeout=8)
    browser = ""
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        browser = run(["xdg-settings", "get", "default-web-browser"], timeout=8).strip()
    print(f"INFO panel_http={code} xdg_open={'yes' if shutil.which('xdg-open') else 'no'} "
          f"default_browser={'set' if browser else 'empty'}", flush=True)
    before = gui_pids()
    print(f"INFO windows_before={len(before)}", flush=True)
    quiet = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
             "stderr": subprocess.DEVNULL}
    clicks = [subprocess.Popen(command, **quiet) for _ in range(1 if before else 2)]
    require(all(click.wait(timeout=20) == 0 for click in clicks), "launch_rc")
    require(wait_for(lambda: len(gui_pids()) >= 1, 10), "window_started")
    require(wait_for(lambda: len(gui_pids()) == 1, 8), "one_window")
    time.sleep(3)
    require(len(gui_pids()) == 1, "one_window_after_pause")
    require(subprocess.run(command, timeout=20, **quiet).returncode == 0, "second_launch_rc")
    time.sleep(3)
    require(len(gui_pids()) == 1, "still_one_window")
    if not before:
        for pid in gui_pids():
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGTERM)
        require(wait_for(lambda: not gui_pids(), 8), "own_window_closed")
    print("OK launch", flush=True)


def observe(minutes):
    """Только чтение: состояния и запись статуса после установки."""
    begin = time.time()
    config = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    states, oldest = {}, 0.0
    while time.time() < begin + minutes * 60:
        with contextlib.suppress(ValueError, OSError, subprocess.SubprocessError):
            state = str(status().get("state"))
            states[state] = states.get(state, 0) + 1
            oldest = max(oldest, time.time() - STATUS.stat().st_mtime)
        time.sleep(15)
    print(f"INFO window_min={(time.time() - begin) / 60:.1f} states={sorted(states.items())} "
          f"status_age_max_s={oldest:.0f}", flush=True)
    require(hashlib.sha256(CONFIG.read_bytes()).hexdigest() == config, "config_unchanged")
    health()
    if oldest > STATUS_LIMIT:
        print("WARN status_age", flush=True)
    print("OK observe", flush=True)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "prepare":
        prepare(Path(sys.argv[2]).resolve())
    elif sys.argv[1:] == ["health"]:
        health()
    elif len(sys.argv) == 3 and sys.argv[1] == "deploy":
        deploy(Path(sys.argv[2]).resolve())
    elif sys.argv[1:] == ["launch"]:
        launch()
    elif len(sys.argv) == 3 and sys.argv[1] == "observe" and sys.argv[2].isdigit():
        observe(int(sys.argv[2]))
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
