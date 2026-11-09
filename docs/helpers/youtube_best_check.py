"""Отдельный выход для видео YouTube (п. 348): включение, наблюдение, проверка маршрута.

Режимы: health | enable | observe МИНУТ | route | disable. Установка — помощником коммита 30e4068.
Вывод — только числа и признаки: теги, имена и адреса серверов не выводятся. enable и disable —
только с согласия владельца: это единственная правка config.toml, disable возвращает её байт в байт.
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
import tomllib
from pathlib import Path

LOCK = Path("/run/xgw-youtube-install")
CONFIG = Path("/etc/xgw/config.toml")
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


def config_sum():
    return hashlib.sha256(CONFIG.read_bytes()).hexdigest()


def has_section(text):
    return re.search(r"^\[media\]", text, re.M) is not None


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
    # Раздел status «media» есть только у кода 30e4068 и новее, off — режим выключен.
    require((status().get("media") or {}).get("state") == "off", "installed_first")
    LOCK.mkdir(mode=0o700, exist_ok=True)
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


def outbound_bytes(tags, port):
    text = run(["curl", "--silent", "--noproxy", "*", "--max-time", "5",
                f"http://127.0.0.1:{port}/debug/vars"], timeout=8)
    stats = json.loads(text)["stats"]["outbound"]
    return sum(value for tag in tags for value in stats[tag].values())


def route_verdict(video, control, need):
    """Чужой трафик только прибавляет байты: мало при запросах к видеосети — правило не сработало,
    столько же при контроле — выход совпал с обычным или мешает чужой трафик: неизвестно."""
    seen = sorted(video)[len(video) // 2]
    if seen < need:
        return "missing"
    return "proven" if seen - sorted(control)[len(control) // 2] >= need else "unclear"


def route_not_run(why):
    print("NOT_RUN route " + why, flush=True)
    return 4


def route():
    """Малые запросы с самого шлюза: идёт ли видеосеть через выбранный выход. Повтор безопасен."""
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
    print(f"INFO route_video={sorted(video)} route_control={sorted(control)} need={need}",
          flush=True)
    same = (status().get("media") or {}).get("tags") == tags
    verdict = route_verdict(video, control, need) if same else "changed"
    require(verdict != "missing", "route_video_seen")
    if verdict != "proven":
        return route_not_run(verdict)
    print("OK route_video", flush=True)
    return 0


def main():
    args = sys.argv[1:]
    if args == ["health"]:
        health()
    elif args == ["route"]:
        return route()
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
