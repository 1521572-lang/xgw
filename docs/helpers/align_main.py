"""Замер установленного XGW и обезличенная сводка. Установку выполняет install.sh."""

import contextlib
import cProfile
import dataclasses
import hashlib
import json
import os
import pstats
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/run/xgw-align-main")
LIB = Path("/opt/xgw/lib")
LABELS = {"before", "after", "rollback"}


def save(name, value):
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if ROOT.is_symlink() or ROOT.stat().st_uid != 0:
        raise ValueError("private directory")
    ROOT.chmod(0o700)
    path = ROOT / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False)


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def command(label, name, argv, timeout):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
        data = {"rc": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except (OSError, subprocess.TimeoutExpired):
        data = {"rc": None, "stdout": "", "stderr": "command unavailable or timed out"}
    save(f"{label}-{name}.json", data)
    return data


def status_fields(data):
    cap, xray = data.get("capture") or {}, data.get("xray") or {}
    return {
        "state": data.get("state") if data.get("state") in {"HEALTHY", "DEGRADED"} else "OTHER",
        "on": cap.get("mode") == "on" and cap.get("blocked") is False,
        "xray": xray.get("ok") is True,
        "daemon": data.get("daemon_down") is False,
        "loaded": cap.get("loaded") if type(cap.get("loaded")) is bool else None,
    }


def health(label):
    # status выполняет собственную loaded; её стоимость здесь не является порогом приёмки.
    status = command(label, "status", ["xgw", "status", "--json"], 180)
    active = command(label, "service", ["systemctl", "is-active", "xgw.service"], 60)
    http = command(label, "https", [
        "curl", "--silent", "--show-error", "--proto", "=https", "--max-time", "90",
        "--noproxy", "*", "--output", "/dev/null", "--write-out", "%{http_code}",
        "https://1.1.1.1/",
    ], 120)
    result = {"status_rc": status["rc"], "https_rc": http["rc"]}
    try:
        result.update(status_fields(json.loads(status["stdout"])))
    except (ValueError, TypeError, AttributeError):
        result.update(on=False, xray=False, daemon=False, loaded=None, state="UNKNOWN")
    code = http["stdout"].strip()
    result["https"] = http["rc"] == 0 and code.isdigit() and 200 <= int(code) < 400
    result["active"] = active["rc"] == 0 and active["stdout"].strip() == "active"
    result["working"] = status["rc"] == 0 and all(
        result[key] for key in ("on", "xray", "daemon", "active", "https")
    )
    save(f"{label}-health.json", result)
    return result["working"]


def inventory(root):
    if not root.is_dir() or root.is_symlink():
        raise ValueError("source directory")
    result = {}
    for path in root.rglob("*"):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError("source symlink")
        if path.is_file():
            result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not result:
        raise ValueError("empty inventory")
    return result


def settings():
    from xgw import config
    from xgw.paths import Paths

    paths = Paths(Path("/"))
    cfg, _ = config.load(paths.config_file)
    groups = dataclasses.asdict(cfg)
    with sqlite3.connect(f"file:{paths.db_file}?mode=ro", uri=True) as db:
        row = db.execute("SELECT value FROM meta WHERE key = ?", ("pin",)).fetchone()
    pin = json.loads(row[0]) if row and row[0] else None
    if isinstance(pin, dict):
        pin = {key: pin.get(key) for key in ("tag", "since", "until")}
        pin["tag"] = str(pin["tag"]).partition("-")[2]  # роль spare/proxy меняет демон
    groups["manual_choice"] = pin
    return {
        key: hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        for key, value in groups.items()
    }


def guard_fields(data):
    chains = [entry["chain"] for entry in data["nftables"] if "chain" in entry]
    counters = [expr["counter"] for entry in data["nftables"] if "rule" in entry
                for expr in entry["rule"].get("expr", []) if "counter" in expr]
    return {
        "postrouting": any(c.get("name") == "output" and c.get("hook") == "postrouting"
                           and c.get("prio") == 10 for c in chains),
        "counters": len(counters), "packets": sum(c["packets"] for c in counters),
        "bytes": sum(c["bytes"] for c in counters),
    }


def snapshot(label, source):
    result = {}
    for name, action in (
        ("source", lambda: all(inventory(a) == inventory(b) for a, b in (
            (source / "src/xgw", LIB / "xgw"),
            (source / "packaging", Path("/opt/xgw/packaging")),
        ))),
        ("settings", settings),
    ):
        try:
            result[name] = action()
        except Exception:
            result[name] = None
        save(f"{label}-snapshot.json", result)
    for name, argv, timeout in (
        ("diag", ["xgw", "diag", "--json"], 900),
        ("guard", ["nft", "-j", "list", "table", "inet", "xgw_guard"], 180),
    ):
        raw = command(label, name, argv, timeout)
        try:
            data = json.loads(raw["stdout"])
            result[name] = ({level: sum(c["level"] == level for c in data)
                             for level in ("OK", "WARN", "FAIL")}
                            if name == "diag" else guard_fields(data))
        except (ValueError, KeyError, TypeError):
            result[name] = None
        result[f"{name}_rc"] = raw["rc"]
        save(f"{label}-snapshot.json", result)


def loaded(profile=False):
    # Это отдельный Python-процесс. До первого loaded не вызываем rules/describe/effective_mode.
    from xgw import config
    from xgw.net.capture import capture_for
    from xgw.paths import Paths

    profiler = cProfile.Profile() if profile else None
    started = None
    result = {"loaded": None, "seconds": None, "error": False}
    try:
        paths = Paths(Path("/"))
        cfg, _ = config.load(paths.config_file)
        cap = capture_for(cfg, paths)
        started = time.perf_counter()
        if profiler:
            profiler.enable()
        result["loaded"] = cap.loaded()
    except Exception:
        result["error"] = True
    finally:
        if profiler:
            profiler.disable()
        if started is not None:
            result["seconds"] = round(time.perf_counter() - started, 1)
        if profiler and started is not None:
            stats = pstats.Stats(profiler).stats
            rows = [(key, value) for key, value in stats.items()
                    if key[0].startswith(str(LIB / "xgw") + "/")]
            result["profile"] = [
                {"file": "src/xgw/" + str(Path(key[0]).relative_to(LIB / "xgw")),
                 "line": key[1], "seconds": round(value[3], 1)}
                for key, value in sorted(rows, key=lambda row: -row[1][3])[:5]
            ]
        save("profile.json" if profile else "loaded.json", result)
    return result


def report():
    # Только этот вывод предназначен для Git. Сырые результаты и хеши настроек приватны.
    result = {}
    before = {}
    with contextlib.suppress(OSError, ValueError):
        before = read("before-snapshot.json").get("settings") or {}
    for label in sorted(LABELS):
        for kind in ("health", "snapshot"):
            try:
                value = read(f"{label}-{kind}.json")
                if kind == "snapshot":
                    current = value.pop("settings", None)
                    value["settings_unchanged"] = bool(before and current) and before == current
                result[f"{label}_{kind}"] = value
            except (OSError, ValueError):
                pass
    for name in ("loaded", "profile"):
        with contextlib.suppress(OSError, ValueError):
            result[name] = read(f"{name}.json")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    os.umask(0o077)
    sys.path.insert(0, str(LIB))
    action = sys.argv[1]
    if action == "report":
        report()
    elif action in {"loaded", "profile"}:
        print(json.dumps(loaded(action == "profile"), ensure_ascii=False))
    elif action in {"health", "snapshot"} and sys.argv[2] in LABELS:
        if action == "health":
            ok = health(sys.argv[2])
            print("Рабочий on и HTTPS подтверждены" if ok else "Рабочий on не подтверждён")
            return 0 if ok else 3
        snapshot(sys.argv[2], Path(sys.argv[3]))
        print("Сводка сохранена; отдельные неизвестные результаты не скрыты")
    else:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
