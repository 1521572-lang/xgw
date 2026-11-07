"""Подписки из config.toml убираются кнопкой (п. 337): подготовка, логика на временных
файлах, установка с возвратом, счёт источников до и после кнопок окна.

Режимы: prepare BASE | health | logic | deploy BASE | sources. Вывод — только числа, слова
состояний и признаки: без имён подписок, адресов, доменов, серверов и тегов.
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TREE = Path(__file__).resolve().parents[2]
LOCK = Path("/run/xgw-subremove-install")  # каталоги прошлых волн не мешают
CONFIG = Path("/etc/xgw/config.toml")
PANEL = Path("/etc/xgw/panel.json")
RECOVER_AFTER = 45.0  # приёмка после установки не дольше — затем сразу возврат (предел 60 с)


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


def digest(path):
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except FileNotFoundError:
        return "none"


def sources():
    """Только чтение: сколько подписок в config.toml и panel.json, убранных и ссылок.
    live_allowed=yes — подписка одна и ссылок нет: без неё ядро остаётся на прежних
    серверах (daemon: «подписок и ссылок нет вовсе»), ручной выбор не снимается."""
    sys.path.insert(0, str(TREE / "src"))
    from xgw import config, managed

    cfg, _warnings = config.load(CONFIG)
    _data, error = managed.load(PANEL)
    own = set(cfg.managed.subscriptions)
    counts = {"config_subs": sum(1 for sub in cfg.subscriptions if sub.name not in own),
              "panel_subs": len(own), "hidden": len(cfg.managed.hidden),
              "links": len(cfg.manual.links), "panel_error": bool(error)}
    total = counts["config_subs"] + counts["panel_subs"] + counts["hidden"]
    print("INFO sources " + json.dumps(counts, sort_keys=True), flush=True)
    print("live_allowed=" + ("yes" if total == 1 and not counts["links"] else "no"), flush=True)
    print(f"config_sha={digest(CONFIG)} panel_sha={digest(PANEL)}", flush=True)


def prepare(base):
    """Только чтение: ни каталогов, ни файлов. Повтор безопасен."""
    require(all(shutil.which(name) for name in ("git", "curl", "journalctl", "systemctl")),
            "tools")
    for tree in (TREE, base):
        run(["sh", "-n", str(tree / "packaging/install.sh")])
    print("OK install_scripts_parse", flush=True)
    if LOCK.exists():
        # Чужой или идущий запуск не трогаем: только сообщаем.
        state = "finished" if (LOCK / "result").exists() else "active"
        print(f"STOP lock_{state}", flush=True)
        raise ValueError("lock")
    health()
    require(match(base), "installed_is_base")
    sources()
    print("OK prepare", flush=True)


def deploy(base):
    LOCK.mkdir(mode=0o700)  # второй запуск при живом каталоге не начнёт вторую установку
    try:
        ready = match(base) and check_health()
    except (OSError, subprocess.SubprocessError):
        ready = False
    if not ready:
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


def logic():
    """Код CODE на временных файлах, без сети и без /etc/xgw: убрать, имя занято, вернуть."""
    sys.path.insert(0, str(TREE / "src"))
    from xgw import config, managed

    with tempfile.TemporaryDirectory() as tmp:
        conf = Path(tmp) / "config.toml"
        conf.write_text("""[[subscriptions]]
name = "main"
url = "https://sub.example.net/s"
""", encoding="utf-8")
        before, panel = conf.read_bytes(), managed.path_for(conf)
        require(managed.hide_subscription(panel, "main", True), "hide_written")
        cfg, warnings = config.load(conf)
        require(cfg.subscriptions == [] and list(cfg.managed.hidden) == ["main"]
                and not warnings, "hidden_skipped")
        require(conf.read_bytes() == before, "config_untouched")
        require(not managed.hide_subscription(panel, "main", True), "hide_idempotent")
        try:
            managed.add_subscription(panel, "https://other.example.org/x", "main",
                                     taken=set(cfg.managed.hidden))
            taken = False
        except managed.ManagedError:
            taken = True
        require(taken, "name_stays_taken")
        require(managed.hide_subscription(panel, "main", False), "restore_written")
        cfg, _warnings = config.load(conf)
        require([sub.name for sub in cfg.subscriptions] == ["main"] and not cfg.managed.hidden,
                "restored")
    print("OK logic", flush=True)


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "prepare":
        prepare(Path(sys.argv[2]).resolve())
    elif sys.argv[1:] == ["health"]:
        health()
    elif sys.argv[1:] == ["logic"]:
        logic()
    elif len(sys.argv) == 3 and sys.argv[1] == "deploy":
        deploy(Path(sys.argv[2]).resolve())
    elif sys.argv[1:] == ["sources"]:
        sources()
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
