"""Локальная страховка только для согласованного повторного теста wave3c.

Не устанавливается как часть XGW. Исходное состояние обязательно off. Доверенная
копия и snapshot готовятся до опасных действий; watchdog запускается отдельным
systemd unit и не зависит от модели, сети и устанавливаемого Python-пакета.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LEASE_SECONDS = 25.0
MAX_SECONDS = 1800.0
JOB = "xgw-w3c-job.service"
SAFETY = "xgw-w3c-safety.service"


def atomic(path: Path, data: bytes) -> None:
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save(path: Path, value: object) -> None:
    atomic(path, json.dumps(value).encode("utf-8"))


def call(argv: list[str], timeout: float, *, data: bytes | None = None) -> int:
    """Каждая команда ограничена, её вывод остаётся локально и не раскрывает адреса."""
    try:
        return subprocess.run(argv, input=data, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=timeout, check=False).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 124


def prepare(directory: Path) -> None:
    # Импорт установленного XGW только до установки; restore/watch используют stdlib.
    sys.path.insert(0, "/opt/xgw/lib")
    from xgw import config
    from xgw.net import cmd, lan, nft
    from xgw.net.capture import Capture
    from xgw.paths import Paths

    paths = Paths.from_env()
    cfg, _ = config.load(paths.config_file)
    capture = Capture(cfg, paths)
    if capture.mode() != "off" or capture.choice() is not False or cfg.free_pool.mode != "off":
        raise SystemExit("STOP: страховка допустима только из явного VPN off и pool off")
    if capture.loaded() is not True:
        raise SystemExit("STOP: исходная off-политика не проверена")
    rules = capture.rules("off")
    text = nft.render(rules) or "table ip xgw\ndelete table ip xgw\n"
    if capture.ipv6_usable():
        text += nft.render6(rules) or "table ip6 xgw6\ndelete table ip6 xgw6\n"
    text += "table inet xgw_guard\ndelete table inet xgw_guard\n"
    data = text.encode("utf-8")
    if call(["nft", "-c", "-f", "-"], 8, data=data) != 0:
        raise SystemExit("STOP: подготовленные off-правила не приняты nft")
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    atomic(directory / "off.nft", data)
    atomic(directory / "capture.json", paths.var.joinpath("capture.json").read_bytes())
    save(directory / "snapshot.json", {
        "capture_state": str(paths.var / "capture.json"),
        "open_marker": str(paths.run / "capture-open"),
        "off_sha256": hashlib.sha256(data).hexdigest(),
        "state_sha256": hashlib.sha256((directory / "capture.json").read_bytes()).hexdigest(),
        "boot": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "status_file": str(paths.status_file),
        "interfaces": {"WAN": lan.effective_wan(cfg, cmd.run), "LAN": cfg.network.lan_if},
        "bypass_mark": cfg.capture.mark_bypass,
    })
    save(directory / "status.json", {"state": "prepared"})
    print("PREPARED: исходный off сохранён; страховка ещё не запущена")


def restore(directory: Path) -> None:
    began = time.monotonic()
    try:
        last_pulse = float(json.loads((directory / "lease.json").read_text()))
    except (OSError, ValueError, TypeError):
        last_pulse = None
    save(directory / "status.json", {"state": "restoring"})
    snapshot = json.loads((directory / "snapshot.json").read_text())
    rules = (directory / "off.nft").read_bytes()
    state = (directory / "capture.json").read_bytes()
    if hashlib.sha256(rules).hexdigest() != snapshot["off_sha256"] or (
            hashlib.sha256(state).hexdigest() != snapshot["state_sha256"]):
        save(directory / "status.json", {"state": "FAILED_SNAPSHOT"})
        return
    # Не ждём net.lock либо зависший install: прекращаем единственных разрешённых
    # писателей этого теста. Остановка демона не снимает его правила и не рвёт Xray.
    stopped = call(["systemctl", "stop", "--no-block", JOB,
                    "xgw.service", "xgw-net.service"], 1)
    killed = call(["systemctl", "kill", "--kill-whom=all", "--signal=KILL",
                   JOB, "xgw.service", "xgw-net.service"], 1)
    applied = call(["nft", "-f", "-"], 3, data=rules)
    if applied == 0:
        atomic(Path(snapshot["capture_state"]), state)
        Path(snapshot["open_marker"]).unlink(missing_ok=True)
    # Прерванный job не должен вечно выглядеть выполняющимся. Прочее восстановление
    # не зависит от наличия/читаемости необязательного артефакта результата.
    try:
        result = json.loads((directory / "job-result.json").read_text())
        if isinstance(result, dict) and result.get("state") == "running":
            result.update(state="aborted_by_safety", rc=None)
            save(directory / "job-result.json", result)
    except (OSError, ValueError):
        pass
    ended = time.monotonic()
    save(directory / "status.json", {
        "state": "RESTORED_OFF" if applied == 0 else "FAILED_RESTORE",
        "nft_rc": applied, "stop_rc": stopped, "kill_rc": killed,
        "daemon": "left_stopped_for_review", "monotonic": ended,
        "recovery_seconds": round(ended - began, 3),
        "seconds_since_last_pulse": (round(ended - last_pulse, 3)
                                     if last_pulse is not None else None),
    })


def watch(directory: Path, dry: bool = False) -> None:
    if not dry:
        snapshot = json.loads((directory / "snapshot.json").read_text())
        if snapshot["boot"] != Path("/proc/sys/kernel/random/boot_id").read_text().strip():
            raise SystemExit("STOP: snapshot от другой загрузки")
    began = time.monotonic()
    save(directory / "lease.json", began)
    save(directory / "status.json", {"state": "armed", "dry": dry})
    while True:
        now = time.monotonic()
        try:
            lease = float(json.loads((directory / "lease.json").read_text()))
            disarmed = (directory / "disarm").exists()
        except (OSError, ValueError, TypeError):
            lease, disarmed = began - LEASE_SECONDS, False
        # Просроченный lease нельзя продлить или отменить после потери связи.
        if now - lease >= LEASE_SECONDS or now - began >= MAX_SECONDS or lease > now + 1:
            if dry:
                save(directory / "status.json", {"state": "DRY_EXPIRED"})
            else:
                restore(directory)
            return
        if disarmed:
            save(directory / "status.json", {"state": "disarmed"})
            return
        time.sleep(0.25)


def pulse(directory: Path, disarm: bool = False) -> None:
    status = json.loads((directory / "status.json").read_text())
    lease = float(json.loads((directory / "lease.json").read_text()))
    gap = time.monotonic() - lease
    if status.get("state") != "armed" or gap >= LEASE_SECONDS:
        raise SystemExit("STOP: страховка не armed или lease истёк; новый опыт запрещён")
    if disarm:
        atomic(directory / "disarm", b"confirmed\n")
    else:
        save(directory / "lease.json", time.monotonic())
    print("DISARM_REQUESTED" if disarm else "LEASE_OK")
    print(json.dumps({"previous_gap_seconds": round(gap, 3), "lease_seconds": LEASE_SECONDS}))


def job(directory: Path, action: str, repo: Path) -> None:
    if json.loads((directory / "status.json").read_text()).get("dry") is not False:
        raise SystemExit("STOP: dry-калибровка не разрешает install/enable")
    pulse(directory)
    # Повторный install в том же опыте не должен выглядеть завершённым по rc старого enable.
    save(directory / "job-result.json", {"action": action, "state": "running", "rc": None})
    command = (["/bin/sh", str(repo / "packaging/install.sh"), "--yes"]
               if action == "install" else ["/usr/local/bin/xgw", "enable"])
    with (directory / "job.log").open("wb") as stream:
        result = subprocess.run(command, cwd=repo, stdout=stream,
                                stderr=subprocess.STDOUT, check=False)
    save(directory / "job-result.json", {
        "action": action, "state": "finished", "rc": result.returncode,
    })


def observe(directory: Path) -> None:
    snapshot = json.loads((directory / "snapshot.json").read_text())
    state = json.loads(Path(snapshot["capture_state"]).read_text())
    result = {"capture_enabled": state.get("enabled"),
              "baseline_present": bool(state.get("baseline")),
              "mismatch_present": bool(state.get("mismatch")), "links": {}}
    for label, interface in snapshot["interfaces"].items():
        if not interface:
            result["links"][label] = "not_configured"
            continue
        link = Path("/sys/class/net") / interface
        try:
            result["links"][label] = {
                "operstate": (link / "operstate").read_text().strip(),
                "carrier": (link / "carrier").read_text().strip(),
            }
        except OSError:
            result["links"][label] = "unknown"
    print(json.dumps(result))


def probe(directory: Path) -> None:
    # Только новые TCP handshakes к той же публичной цели, что в предыдущем ТЗ.
    result = {}
    snapshot = json.loads((directory / "snapshot.json").read_text())
    for label, mark in (("plain", None), ("marked", snapshot["bypass_mark"])):
        with socket.socket() as sock:
            sock.settimeout(2)
            try:
                if mark is not None:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, mark)
                sock.connect(("1.1.1.1", 443))
                result[label] = "connected"
            except OSError as exc:
                result[label] = type(exc).__name__
    print(json.dumps(result))


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("нужен sudo")
    mode, directory = sys.argv[1], Path(sys.argv[2]).resolve()
    if mode == "prepare":
        prepare(directory)
        return
    if directory.stat().st_uid != 0 or directory.stat().st_mode & 0o077:
        raise SystemExit("STOP: каталог страховки должен быть root:root 0700")
    if mode in ("pulse", "disarm", "job") and call(
            ["systemctl", "is-active", "--quiet", SAFETY], 2) != 0:
        raise SystemExit("STOP: независимая служба страховки не работает")
    if mode == "watch-dry":
        watch(directory, dry=True)
    elif mode == "watch":
        watch(directory)
    elif mode in ("pulse", "disarm"):
        pulse(directory, disarm=mode == "disarm")
        # Один короткий операторский цикл: продление и результат job в одной команде.
        result = directory / "job-result.json"
        if result.exists():
            print(result.read_text())
    elif mode == "status":
        print((directory / "status.json").read_text())
        result = directory / "job-result.json"
        if result.exists():
            print(result.read_text())
    elif mode == "observe":
        observe(directory)
    elif mode == "probe":
        probe(directory)
    elif mode == "job" and sys.argv[3] in ("install", "enable"):
        job(directory, sys.argv[3], Path(sys.argv[4]).resolve())
    else:
        raise SystemExit("prepare|watch-dry|watch|pulse|disarm|status|job")


if __name__ == "__main__":
    main()
