"""Дополнительные проверки выхода для видео (п. 353). Режимы: health | deploy BASE | enable |
observe МИНУТ | disable. Вывод — только числа и признаки; строк журнала и адресов нет."""
import contextlib
import hashlib
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

TREE = Path(__file__).resolve().parents[2]
LOCK = Path("/run/xgw-youtube-media")
CONFIG = Path("/etc/xgw/config.toml")
UNIT = "xgw.service"
RECOVER_AFTER = 120.0  # приёмка после установки не дольше — затем сразу возврат
STATUS_WAIT = 30
SWITCH_WAIT = 180  # столько секунд демон может перечитывать настройки
DEGRADED_LIMIT = 8  # замеров подряд по 20 с: дольше сборки и применения
MIN_GAP = 100.0  # обычный промежуток YOUTUBE_GAP — 120 с, шаг демона может сдвинуть замер журнала
SECTION = '\n[media]\nyoutube_mode = "best"\n'
EXTRA = "(дополнительно для видео)"
ANY_CHECK = "YouTube через "


def run(argv, *, timeout=20):
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=True).stdout


def require(ok, label):
    if not ok:
        print("STOP " + label, flush=True)
        raise ValueError(label)
    print("OK " + label, flush=True)


def status(timeout=40):
    return json.loads(run(["xgw", "status", "--json"], timeout=timeout))


def is_on(data):
    cap = data.get("capture") or {}
    return (data.get("daemon_down") is False and data.get("xray", {}).get("ok") is True
            and cap.get("mode") == "on" and cap.get("loaded") is True
            and cap.get("blocked") is False and not cap.get("capture_failed"))


def https_code():
    return run(["curl", "--silent", "--noproxy", "*", "--max-time", "8", "-o", "/dev/null",
                "-w", "%{http_code}", "https://1.1.1.1/"], timeout=12)


def code_ok(code):
    return code.isdigit() and 200 <= int(code) < 400


def health():
    require(is_on(status()), "on")
    require(code_ok(https_code()), "https")


def check_health():
    with contextlib.suppress(ValueError, OSError, subprocess.SubprocessError):
        health()
        return True
    return False


def outcome(call):
    """Итог команды: (метка, вывод). Метка — только вид неудачи, без текста ошибки."""
    try:
        return "ok", call()
    except subprocess.TimeoutExpired:
        return "timeout", ""
    except subprocess.CalledProcessError as exc:
        return f"rc_{exc.returncode}", ""
    except (OSError, ValueError):
        return "error", ""


def attempt(number):
    began = time.monotonic()
    state, text = outcome(lambda: run(["xgw", "status", "--json"], timeout=STATUS_WAIT))
    running = False
    if state == "ok":
        try:
            running = bool(is_on(json.loads(text)))
        except (ValueError, AttributeError):
            state = "bad_json"
    spent = round(time.monotonic() - began, 1)
    web, code = outcome(https_code)
    print(f"ATTEMPT {number} at={time.strftime('%H:%M:%S')} status={state} status_s={spent} "
          f"on={int(running)} https={web}:{code if code.isdigit() else '-'}", flush=True)
    return running and web == "ok" and code_ok(code)


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


def deploy(base):
    require(match(base) and check_health(), "baseline")
    LOCK.mkdir(mode=0o700)  # второй запуск при живом каталоге не начнёт вторую установку

    def install(tree, name):
        with (LOCK / (name + ".log")).open("xb") as stream:
            rc = subprocess.run(["sh", str(tree / "packaging/install.sh"), "--yes"],
                                stdout=stream, stderr=subprocess.STDOUT).returncode
        print(f"{name}_rc={rc} at={time.strftime('%H:%M:%S')}", flush=True)
        return rc

    accepted, number = False, 0
    try:
        if install(TREE, "install") == 0 and match(TREE):
            done = time.monotonic()
            while not accepted and time.monotonic() - done < RECOVER_AFTER:
                number += 1
                accepted = attempt(number)
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


def pin_info(data):
    pin = data.get("pin")
    print(f"INFO pin_active={bool(pin) and not pin.get('down')}", flush=True)


def wait_state(check):
    end, state = time.monotonic() + SWITCH_WAIT, None
    while True:
        with contextlib.suppress(ValueError, OSError, subprocess.SubprocessError):
            state = (status().get("media") or {}).get("state")
        if check(state) or time.monotonic() >= end:
            return state
        time.sleep(5)


def place_config(write):
    info = CONFIG.stat()
    temporary = CONFIG.with_name(".xgw-youtube.tmp")
    write(temporary)
    os.chmod(temporary, info.st_mode & 0o777)
    os.chown(temporary, info.st_uid, info.st_gid)
    os.replace(temporary, CONFIG)


def enable():
    require((LOCK / "result").is_file()
            and (LOCK / "result").read_text().strip() == "accepted", "installed_first")
    pin_info(status())
    backup = LOCK / "config.before"
    require(not backup.exists(), "enable_once")
    text = CONFIG.read_text(encoding="utf-8")
    require(re.search(r"^\[media\]", text, re.M) is None, "no_media_section")
    shutil.copy2(CONFIG, backup)
    place_config(lambda path: path.write_text(text.rstrip("\n") + "\n" + SECTION, encoding="utf-8"))
    state = wait_state(lambda value: value not in (None, "off"))
    print(f"INFO media_state={state}", flush=True)
    require(state not in (None, "off"), "enabled")
    health()


def disable():
    backup = LOCK / "config.before"
    require(backup.is_file(), "backup_found")
    wanted = hashlib.sha256(backup.read_bytes()).hexdigest()
    place_config(lambda path: shutil.copyfile(backup, path))  # снимок на /run, файл на /etc
    require(config_sum() == wanted, "config_restored")
    backup.unlink()
    state = wait_state(lambda value: value == "off")
    print(f"INFO media_state={state}", flush=True)
    require(state == "off", "disabled")
    pin_info(status())
    health()


def xray_started():
    return run(["systemctl", "show", "xgw-xray", "-p", "ActiveEnterTimestampMonotonic", "--value"])


def read_checks(since):
    """Сколько проверок YouTube в журнале и наименьший промежуток между дополнительными."""
    lines = run(["journalctl", "--no-pager", "-o", "short-unix", "-u", UNIT,
                 "--since", f"@{since}"], timeout=60).splitlines()
    stamps, total, broken = [], 0, 0
    for line in lines:
        broken += "Traceback" in line or "шаг watchdog завершился ошибкой" in line
        if ANY_CHECK not in line:
            continue
        total += 1
        if EXTRA in line:
            stamps.append(float(line.split(None, 1)[0]))
    gaps = [later - earlier for earlier, later in itertools.pairwise(stamps)]
    return len(stamps), total, min(gaps) if gaps else None, broken


def observe(minutes):
    begin = int(time.time())
    config = config_sum()
    restarted_from = xray_started()
    states, changes, streak, worst, before, spent, limit = {}, 0, 0, 0, None, 0.0, None
    while time.time() < begin + minutes * 60:
        with contextlib.suppress(ValueError, OSError, subprocess.SubprocessError):
            view = status().get("media") or {}
            state = str(view.get("state"))
            states[state] = states.get(state, 0) + 1
            streak = streak + 1 if state == "degraded" else 0
            worst = max(worst, streak)
            tags = tuple(view.get("tags") or ())
            changes += before is not None and tags != before
            before = tags
            spent = max(spent, float(view.get("probe_mb") or 0))
            limit = view.get("probe_limit_mb", limit)
        time.sleep(20)
    extra, total, gap, broken = read_checks(begin)
    print(f"INFO window_min={(time.time() - begin) / 60:.1f} states={sorted(states.items())} "
          f"exit_changes={changes}", flush=True)
    print(f"INFO extra_checks={extra} all_checks={total} min_gap_s="
          f"{'-' if gap is None else round(gap)} probe_mb={spent} probe_limit_mb={limit} "
          f"errors={broken}", flush=True)
    require(xray_started() == restarted_from, "xray_not_restarted")
    require(worst < DEGRADED_LIMIT, "not_degraded")
    require(config_sum() == config, "config_unchanged")
    require(limit is not None and spent <= limit, "budget")
    health()
    if not states.get("best"):
        print("NOT_RUN best (причина — в states выше)", flush=True)
        return 4
    print("OK best_applied", flush=True)
    if not extra:
        print("NOT_RUN extra_checks", flush=True)
        return 4
    print("OK extra_checks", flush=True)
    require(gap is None or gap >= MIN_GAP, "gap")
    return 0


def main():
    args, simple = sys.argv[1:], {"health": health, "enable": enable, "disable": disable}
    if len(args) == 1 and args[0] in simple:
        return simple[args[0]]() or 0
    if len(args) == 2 and args[0] == "deploy":
        return deploy(Path(args[1]).resolve()) or 0
    if len(args) == 2 and args[0] == "observe" and args[1].isdigit():
        return observe(int(args[1]))
    return 2


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:  # текст ошибки может содержать адрес
        print("STOP", type(exc).__name__, flush=True)
        code = 3
    print(f"helper_rc={code}", flush=True)
    sys.exit(code)
