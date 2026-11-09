"""Новое поколение sing-box через любой пригодный сервер (п. 351). Режимы: health | deploy BASE |
observe МИНУТ. Вывод — только числа и признаки; строки журнала и адреса не выводятся."""
import collections
import contextlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

TREE = Path(__file__).resolve().parents[2]
LOCK = Path("/run/xgw-bridge-any")
UNIT = "xgw.service"
RECOVER_AFTER = 45.0  # приёмка после установки не дольше — затем сразу возврат
EVENTS = (("build_started", "сборка конфига начата"),
          ("build_stale", "устаревшая сборка конфига отброшена"),
          ("build_finished", "конфиг собран в фоне"),
          ("generation_changed", "поколение sing-box сменено"),
          ("generation_failed", "подготовка поколения sing-box не выполнена"),
          ("applied_restart", "применено с перезапуском Xray"))
CHECKED = re.compile(r"новое поколение sing-box проверено: мост ([0-9]+) из ([0-9]+)"
                     r"(, не из работающих)?")
FAILED = re.compile(r"мостов проверено ([0-9]+) из ([0-9]+)(?:: ((?:[a-z_]+ [0-9]+(?:, )?)+))?")


def run(argv, *, timeout=20):
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=True).stdout


def require(ok, label):
    if not ok:
        print("STOP " + label, flush=True)
        raise ValueError(label)
    print("OK " + label, flush=True)


def health(timeout=40):
    data = json.loads(run(["xgw", "status", "--json"], timeout=timeout))
    cap = data.get("capture") or {}
    require(data.get("daemon_down") is False and data.get("xray", {}).get("ok") is True
            and cap.get("mode") == "on" and cap.get("loaded") is True
            and cap.get("blocked") is False and not cap.get("capture_failed"), "on")
    code = run(["curl", "--silent", "--noproxy", "*", "--max-time", "8", "-o", "/dev/null",
                "-w", "%{http_code}", "https://1.1.1.1/"], timeout=12)
    require(code.isdigit() and 200 <= int(code) < 400, "https")


def check_health(timeout=10):
    with contextlib.suppress(ValueError, OSError, subprocess.SubprocessError):
        health(timeout)
        return True
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


def deploy(base):
    # Приёмка строгая по времени, а исходное состояние — нет: 10 с на статус давали ложный STOP.
    require(match(base) and check_health(40), "baseline")
    LOCK.mkdir(mode=0o700)  # второй запуск при живом каталоге не начнёт вторую установку

    def install(tree, name):
        with (LOCK / (name + ".log")).open("xb") as stream:
            rc = subprocess.run(["sh", str(tree / "packaging/install.sh"), "--yes"],
                                stdout=stream, stderr=subprocess.STDOUT).returncode
        print(f"{name}_rc={rc} at={time.strftime('%H:%M:%S')}", flush=True)
        return rc

    accepted, began = False, int(time.time()) - 1
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
        (LOCK / "result").write_text(f"{began}\n" if accepted else "returned\n")
    require(accepted, "installed")


def xray_started():
    return run(["systemctl", "show", "xgw-xray", "-p", "ActiveEnterTimestampMonotonic", "--value"])


def read_journal(since):
    lines = run(["journalctl", "--no-pager", "-o", "cat", "-u", UNIT, "--since", f"@{since}"],
                timeout=60).splitlines()
    events, checked, fails = collections.Counter(), [], collections.Counter()
    for line in lines:
        event = next((label for label, text in EVENTS if text in line), None)
        if event:
            events[event] += 1
        found = CHECKED.search(line)
        if found:
            checked.append(f"{found[1]}/{found[2]}" + ("x" if found[3] else ""))
        if event == "generation_failed":
            seen = FAILED.search(line)
            fails[f"{seen[1]}/{seen[2]} " + (seen[3] or "-").replace(", ", ",")
                  if seen else "no_summary"] += 1
    return events, checked, fails


def observe(minutes):
    text = (LOCK / "result").read_text().strip() if (LOCK / "result").is_file() else ""
    require(text.isdigit(), "installed_first")
    began, deadline = xray_started(), time.monotonic() + minutes * 60
    while time.monotonic() < deadline:
        if read_journal(int(text))[0]["generation_changed"]:
            time.sleep(30)  # сборка после смены поколения успевает завершиться
            break
        time.sleep(20)
    events, checked, fails = read_journal(int(text))
    print("INFO events " + (" ".join(f"{key}={events[key]}" for key in sorted(events)) or "none"),
          flush=True)
    print(f"INFO checked (x — сервер не из работающих у Xray) {checked}", flush=True)
    print("INFO fail_kinds " + (" | ".join(f"{key} x{fails[key]}" for key in sorted(fails))
                                or "none"), flush=True)
    require(xray_started() == began, "xray_not_restarted")
    health()
    if events["generation_changed"]:
        print("OK generation_changed", flush=True)
        return 0
    if events["generation_failed"]:
        print("STOP generation_still_failing", flush=True)
        return 3
    print("NOT_RUN no_generation_needed", flush=True)
    return 4


def main():
    args = sys.argv[1:]
    if args == ["health"]:
        return health() or 0
    if len(args) == 2 and args[0] == "deploy":
        return deploy(Path(args[1]).resolve()) or 0
    if len(args) == 2 and args[0] == "observe" and args[1].isdigit():
        return observe(int(args[1]))
    print("usage", flush=True)
    return 2


if __name__ == "__main__":
    try:
        code = main()
    except ValueError:
        code = 3
    except Exception as exc:  # текст ошибки может содержать адрес
        print("STOP", type(exc).__name__, flush=True)
        code = 3
    print(f"helper_rc={code}", flush=True)
    sys.exit(code)
