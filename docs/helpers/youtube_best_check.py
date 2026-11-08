"""Отдельный выход для видео YouTube (п. 348): установка с возвратом, включение, наблюдение.

Режимы: prepare BASE | health | deploy BASE | enable | observe МИНУТ | disable. Вывод — только
числа и признаки: теги, имена и адреса серверов не выводятся. enable и disable — только с согласия
владельца: это единственная правка config.toml, и disable возвращает файл байт в байт.
"""
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

TREE = Path(__file__).resolve().parents[2]
LOCK = Path("/run/xgw-youtube-install")
CONFIG = Path("/etc/xgw/config.toml")
RECOVER_AFTER = 45.0  # приёмка после установки не дольше — затем сразу возврат
SWITCH_WAIT = 180  # столько секунд демон может перечитывать настройки
DEGRADED_LIMIT = 8  # замеров подряд по 15 с: дольше сборки и применения
SECTION = '\n[media]\nyoutube_mode = "best"\n'


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


def config_sum():
    return hashlib.sha256(CONFIG.read_bytes()).hexdigest()


def has_section(text):
    return re.search(r"^\[media\]", text, re.M) is not None


def prepare(base):
    """Только чтение: ни каталогов, ни файлов. Повтор безопасен."""
    require(all(shutil.which(name) for name in ("git", "curl", "journalctl", "systemctl")), "tools")
    for tree in (TREE, base):
        run(["sh", "-n", str(tree / "packaging/install.sh")])
    print("OK install_scripts_parse", flush=True)
    if LOCK.exists():
        print(f"STOP lock_{'finished' if (LOCK / 'result').exists() else 'active'}", flush=True)
        raise ValueError("lock")
    health()
    require(match(base), "installed_is_base")
    require(not has_section(CONFIG.read_text(encoding="utf-8")), "no_media_section")
    data = status()
    print(f"INFO state={data.get('state')} members={len(data.get('members') or [])} "
          f"spares={len(data.get('spares') or [])}", flush=True)
    print("config_sha=" + config_sum()[:16], flush=True)
    print("OK prepare", flush=True)


def deploy(base):
    LOCK.mkdir(mode=0o700)  # второй запуск при живом каталоге не начнёт вторую установку
    (LOCK / "started").write_text(f"{time.time():.0f}\n")
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


def media_state():
    with contextlib.suppress(ValueError, OSError, subprocess.SubprocessError):
        return (status().get("media") or {}).get("state")
    return None


def wait_state(check):
    end = time.monotonic() + SWITCH_WAIT
    while time.monotonic() < end:
        state = media_state()
        if check(state):
            return state
        time.sleep(5)
    return media_state()


def enable():
    require((LOCK / "result").is_file()
            and (LOCK / "result").read_text().strip() == "accepted", "installed_first")
    backup = LOCK / "config.before"
    require(not backup.exists(), "enable_once")
    text = CONFIG.read_text(encoding="utf-8")
    require(not has_section(text), "no_media_section")
    shutil.copy2(CONFIG, backup)
    info = CONFIG.stat()
    temporary = CONFIG.with_name(".xgw-youtube.tmp")
    temporary.write_text(text.rstrip("\n") + "\n" + SECTION, encoding="utf-8")
    os.chmod(temporary, info.st_mode & 0o777)
    os.chown(temporary, info.st_uid, info.st_gid)
    os.replace(temporary, CONFIG)
    state = wait_state(lambda value: value not in (None, "off"))
    print(f"INFO media_state={state}", flush=True)
    require(state not in (None, "off"), "enabled")
    health()


def disable():
    backup = LOCK / "config.before"
    require(backup.is_file(), "backup_found")
    wanted = hashlib.sha256(backup.read_bytes()).hexdigest()
    os.replace(backup, CONFIG)
    require(config_sum() == wanted, "config_restored")
    state = wait_state(lambda value: value == "off")
    print(f"INFO media_state={state}", flush=True)
    require(state == "off", "disabled")
    health()


def xray_started():
    return run(["systemctl", "show", "xgw-xray", "-p", "ActiveEnterTimestampMonotonic", "--value"])


def diag_lines():
    out = subprocess.run(["xgw", "diag", "--no-net"], text=True, capture_output=True, timeout=180,
                         check=False).stdout
    return [line for line in out.splitlines() if "YouTube" in line]


def observe(minutes):
    """Только чтение. Выход показан числом смен, сами серверы не выводятся."""
    begin = time.time()
    config = config_sum()
    restarted_from = xray_started()
    states, rows, oldest, changes, streak, worst = {}, [], 0.0, 0, 0, 0
    before = None
    while time.time() < begin + minutes * 60:
        with contextlib.suppress(ValueError, OSError, subprocess.SubprocessError):
            view = status().get("media") or {}
            state = str(view.get("state"))
            states[state] = states.get(state, 0) + 1
            streak = streak + 1 if state == "degraded" else 0
            worst = max(worst, streak)
            tags = tuple(view.get("tags") or ())
            if before is not None and tags != before:
                changes += 1
            before = tags
            rows = view.get("samples") or rows
            oldest = max(oldest, *(item.get("age_s") or 0 for item in rows), 0)
        time.sleep(15)
    print(f"INFO window_min={(time.time() - begin) / 60:.1f} states={sorted(states.items())} "
          f"exit_changes={changes} sample_age_max_s={oldest:.0f}", flush=True)
    print("INFO exit_mbps=" + ",".join(str(item.get("mbps")) for item in rows), flush=True)
    lines = diag_lines()
    print(f"INFO diag_youtube_lines={len(lines)} diag_warn={sum('WARN' in x for x in lines)}",
          flush=True)
    require(not any("WARN" in line or "FAIL" in line for line in lines), "diag_youtube")
    require(xray_started() == restarted_from, "xray_not_restarted")
    require(worst < DEGRADED_LIMIT, "not_degraded")
    require(config_sum() == config, "config_unchanged")
    health()
    if not states.get("best"):
        print("NOT_RUN best (свежих замеров не было)", flush=True)
        return 4
    print("OK best_applied", flush=True)
    return 0


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "prepare":
        prepare(Path(args[1]).resolve())
    elif args == ["health"]:
        health()
    elif len(args) == 2 and args[0] == "deploy":
        deploy(Path(args[1]).resolve())
    elif args == ["enable"]:
        enable()
    elif args == ["disable"]:
        disable()
    elif len(args) == 2 and args[0] == "observe" and args[1].isdigit():
        return observe(int(args[1]))
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
