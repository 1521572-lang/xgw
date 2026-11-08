"""Правки внешнего аудита (п. 347): подготовка, установка с возвратом, наблюдение.

Отказы не вызываются: на машине проверяется, что обычный путь не сломан и состояние известно.
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
LOCK = Path("/run/xgw-auditfix-install")
CONFIG = Path("/etc/xgw/config.toml")
STATUS = Path("/run/xgw/status.json")
RECOVER_AFTER = 45.0  # приёмка после установки не дольше — затем сразу возврат
STATUS_LIMIT = 25.0  # предел задания: запись status.json
AGE_SLACK = 90.0  # set_age_s считается при записи статуса, не в момент чтения
KINDS = (("html", "страница HTML"), ("empty", "пустой ответ"), ("junk", "служебные адреса"),
         ("no_servers", "нет серверов"), ("target", "служебная сеть"),
         ("no_resolvers", "шифрованных резолверов"))
NO_TABLE = "FIB table does not exist"
ABSENT_TABLE = "54321"  # только чтение: номер, которого нет ни в XGW, ни в обычной системе
UNKNOWN = ("правила ip rule не прочитаны", "маршруты XGW не прочитаны", "Снятие правил")


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


def absent_table():
    """Как эта система отвечает о таблице, которой нет: от этого зависит п. 347, A-04."""
    good = True
    for flags in ([], ["-6"]):
        proc = subprocess.run(["ip", *flags, "-j", "route", "show", "table", ABSENT_TABLE],
                              text=True, capture_output=True, timeout=15, check=False)
        known = NO_TABLE in proc.stderr
        print(f"INFO absent_table family={'6' if flags else '4'} rc={proc.returncode} "
              f"known_text={known}", flush=True)
        good = good and (known or proc.returncode == 0)
    require(good, "absent_table")


def journal(start):
    return run(["journalctl", "-u", "xgw", "--since", f"@{int(start)}", "--no-pager", "-o", "cat"],
               timeout=60).splitlines()


def state_known():
    out = subprocess.run(["xgw", "diag", "--no-net"], text=True, capture_output=True, timeout=180,
                         check=False).stdout
    lines = [line for line in out.splitlines() if any(mark in line for mark in UNKNOWN)]
    print(f"INFO unknown_lines={len(lines)}", flush=True)
    require(not lines, "state_known")


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
    absent_table()
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


def observe(minutes):
    """Только чтение: поля подписок в статусе с начала установки."""
    begin = time.time()
    config = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    states, entries, oldest = set(), [], 0.0
    while time.time() < begin + minutes * 60:
        with contextlib.suppress(ValueError, OSError, subprocess.SubprocessError):
            data = status()
            states.add(str(data.get("state")))
            entries = data.get("subscriptions") or entries
            oldest = max(oldest, time.time() - STATUS.stat().st_mtime)
        time.sleep(15)
    try:
        start, origin = float((LOCK / "started").read_text()), "install"
    except (OSError, ValueError):
        start, origin = begin, "window"
    print("INFO from=" + origin, flush=True)
    print(f"INFO window_min={(time.time() - begin) / 60:.1f} states={sorted(states)} "
          f"status_age_max_s={oldest:.0f}", flush=True)
    require(bool(entries) and all("last_ok_ts" in item and "set_age_s" in item
                                  and "cache_reason" in item for item in entries), "fields")
    now, seen = time.time(), []
    for number, item in enumerate(entries, 1):
        state = classify(item, start)
        seen.append(state)
        print(f"INFO sub {number} state={state} set_age_s={item.get('set_age_s')} "
              f"reason={kind_of(item.get('cache_reason'))}", flush=True)
    require(all(item.get("last_ok_ts") is None or abs(now - item["last_ok_ts"]
                                                      - item["set_age_s"]) <= AGE_SLACK
                for item in entries), "age_consistent")
    kinds = [kind_of(item.get("cache_reason")) for item in entries]
    require(not {"target", "no_resolvers"} & set(kinds), "subscription_path")
    if "cached" in seen:
        require("не обновилась" in run(["xgw", "status"], timeout=10), "status_line")
    lines = journal(start)
    print(f"INFO via_xray_errors={sum('запрос через Xray' in line for line in lines)} "
          f"target_refused={sum('служебная сеть' in line for line in lines)} "
          f"unconfirmed={sum('устранение не подтверждено' in line for line in lines)} "
          f"tracebacks={sum('Traceback' in line for line in lines)}", flush=True)
    require(not any("Traceback" in line for line in lines), "no_tracebacks")
    state_known()
    subs = tomllib.loads(CONFIG.read_text(encoding="utf-8")).get("subscriptions") or []
    urls = [sub.get("url") for sub in subs if isinstance(sub, dict) and sub.get("url")]
    text = STATUS.read_text(encoding="utf-8")
    print(f"INFO urls_checked={len(urls)}", flush=True)
    require(not any(url in text for url in urls), "no_urls_in_status")
    require(hashlib.sha256(CONFIG.read_bytes()).hexdigest() == config, "config_unchanged")
    health()
    if oldest > STATUS_LIMIT:
        print("WARN status_age", flush=True)
    if "stale" in seen:
        print("NOT_RUN fetch (подписка с установки не опрашивалась)", flush=True)
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
