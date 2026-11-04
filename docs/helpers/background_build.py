#!/usr/bin/env python3
"""Один конечный прогон обновления двух файлов; сеть штатно не меняет."""

import hashlib
import http.client
import json
import os
import ssl
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path("/run/xgw-background-build-3")
LIB = Path("/opt/xgw/lib/xgw")
STATUS = Path("/run/xgw/status.json")
FILES = {
    "daemon.py": (
        "3fb8d542c26f2eaafa0710dd19f0e1d715628bf6b212868cb30d009ee1a42989",
        "684b1aca24874654e7da0f43f477863c193821f4d7936a0f5ac7f8694bfcf0b3",
    ),
    "watch/status.py": (
        "32f04d54b06392e82bd0ff120cfb4f445098560fa8d530f361d9cc1a72a1283a",
        "9a029938806c2a6638cc5bf1da9ea0e707fa5e0119e57c4b32728a6a894aa853",
    ),
}
UNIT = "c80a578528b96f7549811f27328902351715a44fa4d859eca605717446aa2b21"
PHASES = {"готов", "запущен", "наблюдение", "завершён", "возврат", "остановлен"}
WORKING_STATES = {"HEALTHY", "DEGRADED"}
STAGE = "чтение команды"


class CheckStop(Exception):
    """Только фиксированная безопасная причина остановки измерения."""


def require(ok):
    if not ok:
        raise ValueError("проверка")


def run(args, timeout=8, watch=None):
    if watch is None:
        result = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
        require(len(result.stdout) <= 8 * 1024 * 1024)
        return result.returncode, result.stdout
    # HTTPS/импорт приложения не останавливают частое чтение статуса в родителе.
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        deadline = time.monotonic() + timeout
        try:
            while True:
                watch()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(args, timeout)
                try:
                    out, _ = process.communicate(timeout=min(0.2, remaining))
                    require(len(out) <= 8 * 1024 * 1024)
                    return process.returncode, out
                except subprocess.TimeoutExpired:
                    pass
        except BaseException:
            process.kill()
            process.communicate()
            raise


def regular(path):
    require(not path.is_symlink())
    for parent in path.parents:
        require(not parent.is_symlink())
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
    require(info.st_size <= 2 * 1024 * 1024)
    return path.read_bytes(), info


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    raw, _ = regular(path)
    return json.loads(raw)


def read_status(path=STATUS):
    # Данные и время записи берём из одного открытого файла, даже при atomic replace.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        raw = stream.read(1048577)
        info = os.fstat(stream.fileno())
    require(stat.S_ISREG(info.st_mode) and len(raw) <= 1048576)
    snapshot = json.loads(raw)
    require(type(snapshot) is dict)
    return snapshot, info.st_mtime_ns


def status_watch(state):
    snapshot, mtime = read_status(STATUS)
    now = time.monotonic()
    assembly = snapshot.get("assembly") or {}
    require(type(assembly.get("builds")) is int)
    # Сохраняем факты ДО возможного отказа порога, а не теряем последнюю строку.
    state["builds"] = max(state["builds"], assembly["builds"])
    state["build_s"], state["apply_s"] = assembly.get("build_s"), assembly.get("apply_s")
    state["apply_result"] = assembly.get("outcome")
    previous = state.get("_watch")
    if previous is None:
        state["_watch"] = [mtime, now, now]
        return
    last_mtime, seen, polled = previous
    poll_gap = now - polled
    state["poll_gap_s"] = max(state["poll_gap_s"], poll_gap)
    if mtime != last_mtime:
        gap = (mtime - last_mtime) / 1e9
        state["_watch"] = [mtime, now, now]
        if gap < 0:
            raise CheckStop("время записи пошло назад; результат измерения неизвестен")
        state["max_gap_s"] = max(state["max_gap_s"], gap)
        if gap > 25:
            if poll_gap > 1:
                raise CheckStop("пропуск частого чтения; интервал записи не установлен")
            raise CheckStop("интервал между записями статуса больше 25 с")
    else:
        state["_watch"] = [mtime, seen, now]
        stale = now - seen
        state["stale_s"] = max(state["stale_s"], stale)
        if stale > 25:
            raise CheckStop("статус не изменялся больше 25 с")


def wait_status(state, seconds):
    deadline = time.monotonic() + seconds
    while True:
        status_watch(state)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.2, remaining))


def write(path, raw, mode=0o600, uid=0, gid=0):
    temporary = path.with_name(path.name + ".background-next")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as stream:
        os.fchown(stream.fileno(), uid, gid)
        os.fchmod(stream.fileno(), mode)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def save(state, directory=None):
    state["updated"] = time.time()
    write((directory or ROOT) / "state.json", json.dumps(state, ensure_ascii=False).encode())


def sample():
    """Приватный дочерний процесс: ни адреса, ни имена не выходят в отчёт."""
    sys.path.insert(0, "/opt/xgw/lib")
    from xgw import config
    from xgw.net.capture import capture_for
    from xgw.paths import Paths

    paths = Paths(Path("/"))
    cfg = config.load(paths.config_file)[0]
    snapshot, mtime = read_status(paths.status_file)
    signature = []
    for path in (paths.config_file, paths.etc / "panel.json"):
        signature.append(sha(regular(path)[0]) if path.exists() else None)
    pin = snapshot.get("pin") or {}
    require(type(pin) is dict)
    rc, pids = run(["systemctl", "show", "-p", "MainPID", "--value",
                    "xgw-xray.service", "xgw-singbox.service"])
    require(rc == 0)
    pids = pids.split()
    require(len(pids) == 2 and all(p.isdigit() and int(p) > 0 for p in pids))
    daemon_active = run(["systemctl", "is-active", "--quiet", "xgw.service"])[0] == 0
    connection = http.client.HTTPSConnection("1.1.1.1", timeout=3,
                                            context=ssl.create_default_context())
    try:
        connection.request("HEAD", "/")
        https = 200 <= connection.getresponse().status < 400
    except (OSError, http.client.HTTPException):
        https = False
    finally:
        connection.close()
    return {
        "state": snapshot.get("state"), "daemon_active": daemon_active,
        "on": capture_for(cfg, paths).effective_mode() == "on", "https": https,
        "signature": signature, "pool": cfg.free_pool.mode,
        "pin": {key: pin.get(key) for key in ("tag", "until", "expires")},
        "pids": [int(p) for p in pids], "mtime": mtime,
        "assembly": snapshot.get("assembly"),
    }


def observe(helper=None, watch=None):
    args = [sys.executable, "-I", "-B", str(helper or ROOT / "helper.py"), "_sample"]
    rc, raw = run(args) if watch is None else run(args, watch=watch)
    require(rc == 0)
    return json.loads(raw)


def good(current, before):
    return (current.get("state") in WORKING_STATES
            and all(current.get(key) is True for key in ("on", "https", "daemon_active"))
            and all(current.get(key) == before.get(key)
                    for key in ("signature", "pool", "pin", "pids")))


def prepared():
    info = ROOT.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0
            and stat.S_IMODE(info.st_mode) == 0o700)
    state = read(ROOT / "state.json")
    require(state.get("phase") in PHASES)
    return state


def prepare(repo):
    global STAGE
    STAGE = "каталог нового прогона"
    require(not ROOT.exists())
    source = repo / "src/xgw"
    originals, replacements, metadata = {}, {}, {}
    for name, (old, new) in FILES.items():
        STAGE = "чтение файлов " + name
        originals[name], info = regular(LIB / name)
        replacements[name], _ = regular(source / name)
        STAGE = "права установленного файла " + name
        require(info.st_uid == 0 and not info.st_mode & 0o022)
        STAGE = "сумма установленного файла " + name
        require(sha(originals[name]) == old)
        STAGE = "сумма нового файла " + name
        require(sha(replacements[name]) == new)
        compile(replacements[name], name, "exec")
        metadata[name] = [stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid]
    STAGE = "неизменность unit xgw.service"
    rc, unit_path = run(["systemctl", "show", "--value", "-p", "FragmentPath", "xgw.service"])
    require(rc == 0)
    unit, _ = regular(Path(unit_path.decode().strip()))
    require(sha(unit) == UNIT)
    rc, dropins = run(["systemctl", "show", "--value", "-p", "DropInPaths", "xgw.service"])
    require(rc == 0 and not dropins.strip())
    STAGE = "исходное состояние: дочерняя проверка до 8 с"
    baseline = observe(Path(__file__).resolve())
    STAGE = "исходное состояние HEALTHY или DEGRADED"
    require(baseline.get("state") in WORKING_STATES)
    for field, label in (("on", "on"), ("https", "HTTPS"), ("daemon_active", "служба xgw")):
        STAGE = "исходная проверка " + label
        require(baseline[field] is True)
    STAGE = "свежесть исходного статуса до 120 с"
    require(time.time() - baseline["mtime"] / 1e9 <= 120)
    STAGE = "приватная копия для возврата"
    # Каталог готового прогона появляется только после всех проверок и записей.
    # Неудачная подготовка удаляет только свою временную копию, не старые прогоны.
    with tempfile.TemporaryDirectory(prefix="xgw-build-prepare-", dir=ROOT.parent) as temporary:
        directory = Path(temporary)
        write(directory / "helper.py", regular(Path(__file__).resolve())[0])
        write(directory / "unit.backup", unit)
        for index, name in enumerate(FILES):
            write(directory / f"old-{index}.py", originals[name])
            write(directory / f"new-{index}.py", replacements[name])
        save({"phase": "готов", "stage": "подготовка", "before": baseline,
              "metadata": metadata, "changed": [], "samples": 0, "max_gap_s": 0,
              "builds": 0, "build_s": None, "apply_s": None, "slow_steps": None,
              "https_failures": 0, "restored": None, "net_up_rc": None, "result": None,
              "failed_stage": None, "failure_kind": None,
              "gateway_state": None, "on": None, "https": None, "apply_result": None,
              "poll_gap_s": 0, "stale_s": 0,
              "states": {name: 0 for name in sorted(WORKING_STATES)}}, directory)
        os.rename(directory, ROOT)
    print("Подготовлено. Установленный XGW не изменён")


def restart():
    rc, _ = run(["systemctl", "--no-block", "restart", "xgw.service"])
    require(rc == 0)


def restore(state):
    state["phase"], state["stage"] = "возврат", "возврат прежнего кода"
    save(state)
    # Не восстанавливаем настройки владельца, конфиги ядер или сетевые профили.
    for index, name in enumerate(FILES):
        old, _ = regular(ROOT / f"old-{index}.py")
        require(sha(old) == FILES[name][0])
        write(LIB / name, old, *state["metadata"][name])
    restart()
    until = time.monotonic() + 15
    while time.monotonic() < until:
        try:
            current = observe()
            if good(current, state["before"]) and current.get("assembly") is None:
                state["restored"] = True
                return
        except Exception:
            pass
        time.sleep(1)
    # Только аварийный возврат on, явно включённый в согласие шага запуска.
    state["net_up_rc"], _ = run(["/usr/local/bin/xgw", "net", "up"], timeout=20)
    current = observe()
    state["restored"] = good(current, state["before"]) and current.get("assembly") is None


def worker():
    state = prepared()
    require(state["phase"] == "запущен")
    rollback = False
    state["started"] = time.time()
    try:
        require(good(observe(), state["before"]))
        for index, name in enumerate(FILES):
            state["stage"] = "замена файла " + name
            require(sha(regular(LIB / name)[0]) == FILES[name][0])
            new, _ = regular(ROOT / f"new-{index}.py")
            require(sha(new) == FILES[name][1])
            # Флаг до замены: даже ошибка второй записи возвращает оба файла.
            rollback = True
            write(LIB / name, new, *state["metadata"][name])
            state["changed"].append(name)
            save(state)
        state["stage"] = "запуск демона"
        save(state)
        restart()
        deadline = time.monotonic() + 35
        while True:
            current = observe()
            if (current.get("assembly") is not None
                    and current["mtime"] > state["before"]["mtime"]
                    and good(current, state["before"])):
                break
            require(current["https"] and current["on"] and time.monotonic() < deadline)
            time.sleep(1)
        state["phase"], state["stage"] = "наблюдение", "десять минут"
        status_watch(state)
        save(state)  # report --ready выпускает исполнителя к кнопке без ожидания 45 с.
        deadline = time.monotonic() + 600
        failures = 0
        while time.monotonic() < deadline:
            current = observe(watch=lambda: status_watch(state))
            state["samples"] += 1
            state["gateway_state"], state["on"], state["https"] = (
                current["state"], current["on"], current["https"])
            if current["state"] in WORKING_STATES:
                state["states"][current["state"]] += 1
            state["https_failures"] += int(not current["https"])
            failures = failures + 1 if not good(current, state["before"]) else 0
            if failures >= 2:
                raise CheckStop("дважды не прошли on/HTTPS/службы или сохранность настроек")
            save(state)
            wait_status(state, 2)
        state["stage"] = "итог"
        rc, raw = run(["journalctl", "-u", "xgw.service", "--since", f"@{state['started']:.6f}",
                       "--no-pager", "-o", "json"], timeout=10)
        require(rc == 0)
        messages = [json.loads(line).get("MESSAGE", "") for line in raw.splitlines()]
        state["slow_steps"] = sum(isinstance(m, str) and m.startswith("шаг watchdog занял ")
                                  for m in messages)
        current = observe()
        require(good(current, state["before"]) and state["slow_steps"] == 0
                and state["builds"] > 0 and state["build_s"] is not None
                and state["build_s"] > 0 and state["https_failures"] == 0
                and state["apply_result"] in ("api", "restart", "unchanged")
                and (current.get("assembly") or {}).get("state") == "idle")
        state["result"] = True
        rollback = False
    except Exception as exc:
        state["failed_stage"] = state["stage"]
        state["failure_kind"] = (str(exc) if isinstance(exc, CheckStop) else
                                 "тайм-аут дочерней команды"
                                 if isinstance(exc, subprocess.TimeoutExpired) else
                                 "ошибка чтения или записи" if isinstance(exc, OSError) else
                                 "несовпадение ожидания или ошибка формата")
        state["result"] = False
    finally:
        if rollback:
            try:
                restore(state)
            except Exception:
                state["restored"] = False
        state["phase"] = "завершён" if state["result"] else "остановлен"
        save(state)


def start(approved):
    require(approved)
    state = prepared()
    require(state["phase"] == "готов")
    # O_EXCL: один запуск даже при повторном нажатии/обрыве терминала.
    fd = os.open(ROOT / "started", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    state["phase"], state["stage"] = "запущен", "проверка перед обновлением"
    save(state)
    try:
        with open(os.devnull, "wb") as null:
            subprocess.Popen([sys.executable, "-I", "-B", str(ROOT / "helper.py"), "_worker"],
                             stdin=subprocess.DEVNULL, stdout=null, stderr=null,
                             start_new_session=True, close_fds=True)
    except Exception:
        state["phase"], state["result"] = "остановлен", False
        save(state)
        raise
    print("Прогон запущен. Помощник сам завершит проверку или вернёт прежний код")


def report(wait=False, ready=False):
    deadline = time.monotonic() + (45 if wait or ready else 0)
    state = prepared()
    while state["phase"] in ("запущен", "наблюдение", "возврат") and time.monotonic() < deadline:
        if ready and state["phase"] == "наблюдение":
            break
        time.sleep(1)
        state = prepared()
    if state["phase"] not in ("завершён", "остановлен"):
        require(time.time() - state["updated"] <= 60)
        print("Прогон продолжается: " + state["phase"])
        return 2
    print("# Проверка фоновой сборки конфига\n")
    for label, value in (
        ("Итог", "прошло" if state["result"] else "не прошло"),
        ("Последний этап", state["stage"]), ("Наблюдений", state["samples"]),
        ("Этап неудачи", state["failed_stage"]),
        ("Класс неудачи", state["failure_kind"]),
        ("Последнее состояние демона", state["gateway_state"]),
        ("Последнее on / HTTPS", (state["on"], state["https"])),
        ("Наблюдений HEALTHY / DEGRADED",
         (state["states"]["HEALTHY"], state["states"]["DEGRADED"])),
        ("Наибольший интервал между прочитанными записями статуса, с", state["max_gap_s"]),
        ("Наибольшее подтверждённое время без изменения статуса, с", state["stale_s"]),
        ("Наибольшая пауза частого чтения статуса, с", state["poll_gap_s"]),
        ("Начатых сборок", state["builds"]), ("Последняя сборка, с", state["build_s"]),
        ("Последнее применение, с", state["apply_s"]), ("Шагов от 60 с", state["slow_steps"]),
        ("Результат применения", state["apply_result"]),
        ("Неудачных HTTPS-проб", state["https_failures"]),
        ("Прежний код возвращён и on проверен", state["restored"]),
        ("Код аварийного xgw net up", state["net_up_rc"]),
    ):
        print(f"- {label}: {value if value is not None else 'НЕ ВЫПОЛНЯЛОСЬ'}")
    print("\nСтатус читается отдельно от HTTPS, обычно каждые 0,2 с; "
          "время записи — из того же файла. "
          "Пропуск чтения и превышение порога записи различаются. "
          "Это наблюдение ThinkCentre, а не проверка устройств за роутером.\n"
          "Сбор данных: завершён")
    return 0


def main():
    require(os.geteuid() == 0)
    command = sys.argv[1]
    if command == "prepare":
        prepare(Path(sys.argv[2]).resolve())
    elif command == "start":
        start(sys.argv[2:] == ["--owner-approved"])
    elif command == "_sample":
        print(json.dumps(sample()))
    elif command == "_worker":
        worker()
    elif command == "report":
        require(sys.argv[2:] in ([], ["--wait"], ["--ready"]))
        return report(wait=sys.argv[2:] == ["--wait"], ready=sys.argv[2:] == ["--ready"])
    else:
        raise ValueError("команда")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("Проверка остановлена: " + STAGE
              + ". Не повторяйте prepare/start; сообщите этот этап и код 3")
        raise SystemExit(3) from None
