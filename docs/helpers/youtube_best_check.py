"""Выход для видео (п. 348–350). Режимы: health | deploy BASE | enable | observe МИНУТ | route |
bridges | disable. Вывод — только числа и признаки. enable и disable — с согласия владельца."""
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

TREE = Path(__file__).resolve().parents[2]
LOCK = Path("/run/xgw-youtube-direct")
CONFIG = Path("/etc/xgw/config.toml")
XRAY = Path("/etc/xgw/xray/config.json")
RECOVER_AFTER = 45.0  # приёмка после установки не дольше — затем сразу возврат
SWITCH_WAIT = 180  # столько секунд демон может перечитывать настройки
DEGRADED_LIMIT = 8  # замеров подряд по 15 с: дольше сборки и применения
SECTION = '\n[media]\nyoutube_mode = "best"\n'
ROUTE_URLS = ("https://redirector.googlevideo.com/generate_204",  # попадает под правило видео
              "https://www.youtube.com/generate_204")  # не попадает: контроль
ROUTE_ROUNDS, ROUTE_REQUESTS, ROUTE_MIN_BYTES = 3, 6, 2000  # байт на запрос — оценка снизу


def run(argv, *, timeout=20):
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=True).stdout


def require(ok, label):
    if not ok:
        print("STOP " + label, flush=True)
        raise ValueError(label)
    print("OK " + label, flush=True)


def status(timeout=40):  # 10 с не хватало (отчёты); при приёмке установки — 10, важнее скорость
    return json.loads(run(["xgw", "status", "--json"], timeout=timeout))


def health(timeout=40):
    data = status(timeout)
    cap = data.get("capture") or {}
    require(data.get("daemon_down") is False and data.get("xray", {}).get("ok") is True
            and cap.get("mode") == "on" and cap.get("loaded") is True
            and cap.get("blocked") is False and not cap.get("capture_failed"), "on")
    code = run(["curl", "--silent", "--noproxy", "*", "--max-time", "8", "-o", "/dev/null",
                "-w", "%{http_code}", "https://1.1.1.1/"], timeout=12)
    require(code.isdigit() and 200 <= int(code) < 400, "https")


def check_health():
    with contextlib.suppress(ValueError, OSError, subprocess.SubprocessError):
        health(10)
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


def enable():
    require((LOCK / "result").is_file()
            and (LOCK / "result").read_text().strip() == "accepted", "installed_first")
    pin_info(status())
    backup = LOCK / "config.before"
    require(not backup.exists(), "enable_once")
    text = CONFIG.read_text(encoding="utf-8")
    require(re.search(r"^\[media\]", text, re.M) is None, "no_media_section")
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
    info = CONFIG.stat()
    temporary = CONFIG.with_name(".xgw-youtube.tmp")
    shutil.copyfile(backup, temporary)  # снимок на /run, файл на /etc: переносить нельзя
    os.chmod(temporary, info.st_mode & 0o777)
    os.chown(temporary, info.st_uid, info.st_gid)
    os.replace(temporary, CONFIG)
    require(config_sum() == wanted, "config_restored")
    backup.unlink()
    state = wait_state(lambda value: value == "off")
    print(f"INFO media_state={state}", flush=True)
    require(state == "off", "disabled")
    pin_info(status())
    health()


def xray_started():
    return run(["systemctl", "show", "xgw-xray", "-p", "ActiveEnterTimestampMonotonic", "--value"])


def diag_lines():
    out = subprocess.run(["xgw", "diag", "--no-net"], text=True, capture_output=True, timeout=180,
                         check=False).stdout
    return [line for line in out.splitlines() if "YouTube" in line]


def observe(minutes):
    begin = time.time()
    config = config_sum()
    restarted_from = xray_started()
    states, rows, oldest, changes, streak, worst, before = {}, [], 0.0, 0, 0, 0, None
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
        print("NOT_RUN best (причина — в states выше)", flush=True)
        return 4
    print("OK best_applied", flush=True)
    return 0


def outbound_bytes(tags, port):
    text = run(["curl", "--silent", "--noproxy", "*", "--max-time", "5",
                f"http://127.0.0.1:{port}/debug/vars"], timeout=8)
    stats = json.loads(text)["stats"]["outbound"]
    return sum(value for tag in tags for value in stats[tag].values())


def route_verdict(video, control, need):
    """Мало байт — правило не сработало; столько же при контроле — неизвестно."""
    seen = sorted(video)[len(video) // 2]
    if seen < need:
        return "missing"
    return "proven" if seen - sorted(control)[len(control) // 2] >= need else "unclear"


def route_not_run(why):
    print("NOT_RUN route " + why, flush=True)
    return 4


def route():
    view = status().get("media") or {}
    tags, began, video, control = view.get("tags") or [], xray_started(), [], []
    if view.get("state") != "best" or not tags:
        return route_not_run("state")
    cfg = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    port = (cfg.get("xray") or {}).get("metrics_port", 10086)
    try:
        for _ in range(ROUTE_ROUNDS):
            for url, into in zip(ROUTE_URLS, (video, control), strict=True):
                before = outbound_bytes(tags, port)
                for _attempt in range(ROUTE_REQUESTS):
                    run(["curl", "--silent", "--fail", "--noproxy", "*", "--max-time", "8",
                         "-o", "/dev/null", url], timeout=12)
                time.sleep(1)  # счётчик должен успеть увидеть последний ответ
                into.append(outbound_bytes(tags, port) - before)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        return route_not_run(type(exc).__name__)
    require(xray_started() == began, "xray_not_restarted")
    need = ROUTE_REQUESTS * ROUTE_MIN_BYTES
    print(f"INFO route_video={video} route_control={control} need={need}", flush=True)
    same = (status().get("media") or {}).get("tags") == tags
    verdict = route_verdict(video, control, need) if same else "changed"
    require(verdict != "missing", "route_video_seen")
    if verdict != "proven":
        return route_not_run(verdict)
    print("OK route_video", flush=True)
    return 0


def bridges():
    """Запрос через мосты работающего поколения sing-box: выводятся только коды curl."""
    applied = json.loads(XRAY.read_text(encoding="utf-8"))
    found = [item for item in applied["outbounds"] if item.get("protocol") == "socks"
             and item["settings"]["servers"][0].get("address") == "127.0.0.1"]
    codes, url = [], applied["burstObservatory"]["pingConfig"]["destination"]
    for item in found[:8]:
        server = item["settings"]["servers"][0]
        user = server["users"][0]
        ask = (f'proxy = "socks5h://127.0.0.1:{server["port"]}"\n'
               f'proxy-user = "{user["user"]}:{user["pass"]}"\n')  # пароль не в аргументах
        codes.append(subprocess.run(
            ["curl", "-K", "-", "--silent", "--max-time", "20", "-o", "/dev/null", url], input=ask,
            text=True, capture_output=True, timeout=25, check=False).returncode)
    members = sum(item["tag"].startswith("proxy-") for item in found)
    print(f"INFO bridges total={len(found)} members={members} curl_rc={codes}", flush=True)


def main():
    args, simple = sys.argv[1:], {"health": health, "route": route, "bridges": bridges,
                                  "enable": enable, "disable": disable}
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
    except Exception as exc:  # без текстов команд и адресов; последний OK указывает этап
        print("STOP", type(exc).__name__, flush=True)
        code = 3
    print(f"helper_rc={code}", flush=True)
    sys.exit(code)
