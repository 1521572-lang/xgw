"""Набор «как Happ» для подписок (п. 345): подготовка, установка с возвратом, наблюдение.

Набор включает владелец мышью; помощник только смотрит, что получилось.
Режимы: prepare BASE | health | deploy BASE | observe МИНУТ. Вывод — только числа, номера
подписок и виды причин: имена, адреса и текст причин не выводятся.
"""
import contextlib
import hashlib
import json
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

TREE = Path(__file__).resolve().parents[2]
LOCK = Path("/run/xgw-happ-install")
PANEL = Path("/etc/xgw/panel.json")
CONFIG = Path("/etc/xgw/config.toml")
STATUS = Path("/run/xgw/status.json")
RECOVER_AFTER = 45.0  # приёмка после установки не дольше — затем сразу возврат
STATUS_LIMIT = 25.0  # предел задания: запись status.json
AGE_SLACK = 90.0  # set_age_s считается при записи статуса, не в момент чтения
KINDS = (("expired", "срок подписки истёк"), ("html", "страница HTML"), ("empty", "пустой ответ"),
         ("junk", "служебные адреса"), ("no_servers", "нет серверов"))


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


def kind_of(reason):
    if not reason:
        return "none"
    return next((key for key, phrase in KINDS if phrase in reason), "other")


def classify(entry, start):
    """fresh — обновилась после установки; cached — опрос оставил прежний набор; stale —
    причины нет, а обновления с установки ещё не было."""
    if entry.get("cache_reason"):
        return "cached"
    return "fresh" if (entry.get("last_ok_ts") or 0) >= start else "stale"


def presets():
    """Имя подписки из панели → (User-Agent как у Happ, её x-hwid). Значения не выводятся."""
    found = {}
    with contextlib.suppress(OSError, ValueError):
        for item in json.loads(PANEL.read_text(encoding="utf-8")).get("subscriptions") or []:
            headers = item.get("headers") or {}
            found[item.get("name")] = (str(item.get("user_agent") or "").startswith("Happ/"),
                                       str(headers.get("x-hwid") or ""))
    return found


def observe(minutes):
    """Только чтение: поля подписок в статусе с начала установки."""
    begin = time.time()
    config = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    states, entries, oldest = {}, [], 0.0  # states: сколько 15-секундных замеров в состоянии
    while time.time() < begin + minutes * 60:
        with contextlib.suppress(ValueError, OSError, subprocess.SubprocessError):
            data = status()
            states[str(data.get("state"))] = states.get(str(data.get("state")), 0) + 1
            entries = data.get("subscriptions") or entries
            oldest = max(oldest, time.time() - STATUS.stat().st_mtime)
        time.sleep(15)
    try:
        start, origin = float((LOCK / "started").read_text()), "install"
    except (OSError, ValueError):
        start, origin = begin, "window"
    print("INFO from=" + origin, flush=True)
    print(f"INFO window_min={(time.time() - begin) / 60:.1f} states={sorted(states.items())} "
          f"status_age_max_s={oldest:.0f}", flush=True)
    require(bool(entries) and all("last_ok_ts" in item and "set_age_s" in item
                                  and "cache_reason" in item for item in entries), "fields")
    now, seen, managed = time.time(), [], presets()
    for number, item in enumerate(entries, 1):
        state = classify(item, start)
        seen.append(state)
        agent, hwid = managed.get(item.get("name"), (False, ""))
        print(f"INFO sub {number} state={state} set_age_s={item.get('set_age_s')} "
              f"reason={kind_of(item.get('cache_reason'))} happ={'yes' if agent else 'no'} "
              f"hwid={'yes' if hwid else 'no'}", flush=True)
    require(all(item.get("last_ok_ts") is None or abs(now - item["last_ok_ts"]
                                                      - item["set_age_s"]) <= AGE_SLACK
                for item in entries), "age_consistent")
    if "cached" in seen:
        require("не обновилась" in run(["xgw", "status"], timeout=10), "status_line")
    subs = tomllib.loads(CONFIG.read_text(encoding="utf-8")).get("subscriptions") or []
    urls = [sub.get("url") for sub in subs if isinstance(sub, dict) and sub.get("url")]
    text = STATUS.read_text(encoding="utf-8")
    print(f"INFO urls_checked={len(urls)}", flush=True)
    require(not any(url in text for url in urls), "no_urls_in_status")
    ids = [hwid for _agent, hwid in managed.values() if hwid]
    require(not any(hwid in text for hwid in ids), "no_hwid_in_status")
    print(f"INFO happ_subs={len(ids)} same_hwid={len(set(ids)) <= 1}", flush=True)
    require(hashlib.sha256(CONFIG.read_bytes()).hexdigest() == config, "config_unchanged")
    health()
    if oldest > STATUS_LIMIT:
        print("WARN status_age", flush=True)
    if "stale" in seen:
        print("NOT_RUN fetch (подписка с установки не опрашивалась)", flush=True)
        return 4
    if not ids:
        print("NOT_RUN happ (набор не включён)", flush=True)
        return 4
    print("OK subscriptions_reported", flush=True)
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
