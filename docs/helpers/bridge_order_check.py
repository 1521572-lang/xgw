"""Проверка нового поколения sing-box: живые мосты первыми (п. 338), без мостов в работе — не
отказ (п. 339) — подготовка, порядок мостов без сети, установка с возвратом, наблюдение за
сменой поколения (журнал — с начала установки: первая пересборка идёт сразу после неё).

Режимы: prepare BASE | health | logic | deploy BASE | observe МИНУТ. Вывод — только числа,
слова состояний и виды отказов: без адресов, доменов, имён серверов, тегов и SNI.
"""
import contextlib
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

TREE = Path(__file__).resolve().parents[2]
LOCK = Path("/run/xgw-bridge2-install")  # каталоги прошлых проверок не мешают
CONFIG = Path("/etc/xgw/config.toml")
RECOVER_AFTER = 45.0  # приёмка после установки не дольше — затем сразу возврат (предел 60 с)
SWITCHED = "поколение sing-box сменено"
REFUSED = "не прошло настоящий запрос через мост"
# Сводка отказа из п. 338: «мостов проверено N из M: вид число, …» — только числа и слова.
SUMMARY = re.compile(r"мостов проверено \d+ из \d+(: [a-z]+ \d+(, [a-z]+ \d+)*)?")


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
    assembly = data.get("assembly") or {}
    return (data.get("state"), len(data.get("members") or []), len(data.get("spares") or []),
            assembly.get("state"))


def journal(since):
    return run(["journalctl", "-u", "xgw", "--since", since, "-o", "cat", "--no-pager"],
               timeout=60)


def tally(text):
    found = [match.group(0) for match in SUMMARY.finditer(text)]
    return text.count(SWITCHED), text.count(REFUSED), found


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
    state, members, spares, assembly = counts()
    print(f"INFO state={state} members={members} spares={spares} assembly={assembly}",
          flush=True)
    switched, refused, _found = tally(journal("-3h"))
    print(f"INFO last_3h switched={switched} refused={refused}", flush=True)
    print("config_sha=" + hashlib.sha256(CONFIG.read_bytes()).hexdigest()[:16], flush=True)
    print("OK prepare", flush=True)


def deploy(base):
    LOCK.mkdir(mode=0o700)  # второй запуск при живом каталоге не начнёт вторую установку
    (LOCK / "started").write_text(f"{time.time():.0f}\n")  # начало журнала для observe
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


def logic():
    """Код CODE без сети: порядок мостов по rank, срок на мост, сводка отказа."""
    sys.path.insert(0, str(TREE / "src"))
    from xgw.apply import singbox_generation as g
    from xgw.config import Config
    from xgw.generator import singbox as sb
    from xgw.watch.checks import DownloadResult

    config, routed = {"inbounds": []}, {"outbounds": []}
    for fp, port in (("aabb1122", 22001), ("bbcc2233", 22002), ("ccdd3344", 22003)):
        config["inbounds"].append({"tag": f"sb-in-{fp}-d", "listen_port": port,
                                   "users": [{"username": "u", "password": "p"}]})
        routed["outbounds"].append(sb.bridge_outbound(port, "d", "p"))
    core, calls = SimpleNamespace(cfg=Config()), []

    def reply(_host, port, _url, **kwargs):
        calls.append((port, kwargs["max_total"]))
        return DownloadResult(ok=port == 22003, kind="" if port == 22003 else "stall")

    g.checks.http_get_via_proxy = reply
    checked = g.bridge_check(core, config, routed, {"ccdd3344": -2.0, "aabb1122": 0.9})
    print(f"INFO order={[port - 22000 for port, _cap in calls]} each_s={g.BRIDGE_EACH}",
          flush=True)
    require(bool(checked) and [port for port, _cap in calls] == [22003], "member_first")
    require(all(cap <= g.BRIDGE_EACH <= 20 for _port, cap in calls), "bridge_cap")
    calls.clear()
    g.bridge_check(core, config, routed, {"aabb1122": 0.9})
    require([port for port, _cap in calls] == [22002, 22003], "unknown_before_failing")
    g.checks.http_get_via_proxy = lambda *a, **kw: DownloadResult(ok=False, kind="stall")
    refused = g.bridge_check(core, config, routed, {})
    print(f"INFO refusal={refused.summary}", flush=True)
    require(not refused and SUMMARY.fullmatch(refused.summary) is not None, "refusal_summary")
    idle = g.bridge_check(core, config, {"outbounds": [{"protocol": "freedom"}]}, {})
    print(f"INFO no_bridge={idle.summary}", flush=True)
    require(bool(idle) and idle.summary == "мостов в работе нет", "no_bridge_in_use")
    print("OK logic", flush=True)


def observe(minutes):
    """Только чтение: смена поколения sing-box и число запасных за окно."""
    begin = time.time()
    config = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    seen, states = [], set()
    while time.time() < begin + minutes * 60:
        with contextlib.suppress(ValueError, OSError, subprocess.SubprocessError):
            state, members, spares, _assembly = counts()
            seen.append((members, spares))
            states.add(str(state))
        time.sleep(15)
    # С начала установки (каталог LOCK создан до неё): первая пересборка идёт сразу после
    # перезапуска демона, раньше окна (отчёт bridge-order: отказ за секунды до окна не попал).
    try:
        start, origin = float((LOCK / "started").read_text()), "install"
    except (OSError, ValueError):
        start, origin = begin, "window"
    print("INFO journal_from=" + origin, flush=True)
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(min(start, begin)))
    text = journal(since)
    switched, refused, found = tally(text)
    errors = run(["journalctl", "-u", "xgw", "-p", "err", "--since", since, "-o", "cat",
                  "--no-pager"], timeout=60).strip().splitlines()
    spares = [spare for _members, spare in seen]
    print(f"INFO window_min={(time.time() - begin) / 60:.1f} states={sorted(states)} "
          f"spares_first={spares[:1]} spares_last={spares[-1:]} spares_max={max(spares or [0])} "
          f"members_last={[members for members, _s in seen][-1:]}", flush=True)
    print(f"INFO switched={switched} refused={refused} error_lines={len(errors)}", flush=True)
    for summary in found[:5]:
        print("INFO refusal " + summary, flush=True)
    require(hashlib.sha256(CONFIG.read_bytes()).hexdigest() == config, "config_unchanged")
    health()
    if switched:
        print("OK generation_switched", flush=True)
        return 0
    if refused:
        print("STOP generation_refused (виды отказов — строки refusal)", flush=True)
        return 5
    print("NOT_RUN generation (пересборки sing-box в окне не было)", flush=True)
    return 4


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "prepare":
        prepare(Path(sys.argv[2]).resolve())
    elif sys.argv[1:] == ["health"]:
        health()
    elif sys.argv[1:] == ["logic"]:
        logic()
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
