"""Три минуты чтения /proc и снимка бюджета; без сетевых запросов и изменения XGW."""

import argparse
import ipaddress
import json
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path

PROC = Path("/proc")
VAR = Path("/var/lib/xgw")
STATUS = Path("/run/xgw/status.json")
OUT = Path("/run/xgw-cpu-readonly")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def collect_names(value, names):
    if isinstance(value, dict):
        for key, item in value.items():
            if (key in {"name", "source", "address", "host", "hostname", "server_name", "tag"}
                    and isinstance(item, str) and item):
                names.add(item)
            if key in {"quota_mb", "quota_share", "quotas"} and isinstance(item, dict):
                names.update(item)
            collect_names(item, names)
    elif isinstance(value, list):
        for item in value:
            collect_names(item, names)


def name_sources():
    names, sources, status = set(), {}, {}
    for label, path in (("inventory", VAR / "inventory.json"), ("status", STATUS)):
        try:
            data = load_json(path)
            if not isinstance(data, dict):
                raise ValueError("expected object")
            collect_names(data, names)
            sources[label] = True
            if label == "status":
                status = data
        except (OSError, ValueError):
            sources[label] = False
    try:
        with sqlite3.connect(f"file:{VAR / 'state.db'}?mode=ro", uri=True) as db:
            for row in db.execute("SELECT name,source,address,tag FROM nodes"):
                names.update(value for value in row if isinstance(value, str) and value)
        sources["database"] = True
    except sqlite3.Error:
        sources["database"] = False
    return names, sources, status


def safe_text(text, names, complete=True):
    if not complete:
        return "имя скрыто: прочитаны не все источники"
    patterns = set(names) | {name.encode()[:15].decode(errors="ignore") for name in names}
    for name in sorted(patterns, key=len, reverse=True):
        if name:
            text = re.sub(re.escape(name), "<скрыто>", text, flags=re.IGNORECASE)
    text = re.sub(r"https?://\S+|\b(?:\d{1,3}\.){3}\d{1,3}\b", "<адрес>", text)
    text = re.sub(r"\b[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b", "<адрес>", text)
    text = re.sub(r"\b(?:[0-9a-fA-F]{2}:){3,}[0-9a-fA-F:]+\b", "<адрес>", text)
    for word in re.findall(r"[0-9a-fA-F:.]+", text):
        try:
            ipaddress.ip_address(word)
        except ValueError:
            continue
        text = text.replace(word, "<адрес>")
    return "".join(ch if ch.isprintable() and ch not in "|`" else "_" for ch in text)


def parse_stat(raw):
    left, tail = raw.rsplit(")", 1)
    fields = tail.split()
    return int(fields[19]), int(fields[11]) + int(fields[12]), left.split("(", 1)[1]


def system_stat():
    lines = (PROC / "stat").read_text().splitlines()
    ticks = [int(n) for n in lines[0].split()[1:9]]  # guest уже входит в user/nice
    cores = sum(bool(re.match(r"^cpu\d+\s", line)) for line in lines)
    return sum(ticks), ticks[3] + ticks[4], cores


def daemon_pid():
    try:
        result = subprocess.run(["systemctl", "show", "xgw.service", "-p", "MainPID", "--value"],
                                capture_output=True, text=True, timeout=15, check=False)
        return int(result.stdout.strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0


def snapshot(main_pid):
    records = {}
    for directory in PROC.iterdir():
        if not directory.name.isdigit():
            continue
        try:
            born, ticks, name = parse_stat((directory / "stat").read_text())
            role = "daemon" if int(directory.name) == main_pid else "other"
            if name.startswith(("python", "xgw")):
                # Только распознать компоненты: argv нигде не сохраняется/не публикуется.
                argv = (directory / "cmdline").read_bytes().decode(errors="replace").split("\0")
                is_xgw = any(Path(arg).name == "xgw" for arg in argv if arg)
                if is_xgw and "tray" in argv:
                    role = "tray"
                elif is_xgw and "run" in argv:
                    role = "daemon"
            records[(int(directory.name), born)] = (ticks, name, role)
        except (OSError, ValueError, IndexError):
            continue
    return records


def budget_view(status, names, complete):
    budget = status.get("budget") or {}
    accounts = sorted(set(budget.get("quota_mb", {})) | set(budget.get("quota_share", {})))
    return {
        "source": "оценка status.json, не журнал фактических байт",
        "quota_units": {"quota_mb": "МБ квоты за сутки с множителями",
                        "quota_share": "% полной квоты за 30 дней"},
        "daily": {key: budget.get(key) for key in (
            "probes_mb", "scans_mb", "total_mb", "e2e_mb", "all_mb", "limit_mb")},
        "month_gb": budget.get("month_gb"),
        "subscriptions": [{"subscription": i + 1, "quota_mb": budget.get("quota_mb", {}).get(n),
                           "quota_share": budget.get("quota_share", {}).get(n)}
                          for i, n in enumerate(accounts)],
        "warnings": ([safe_text(str(warning), names, complete)
                      for warning in budget["warnings"]] if "warnings" in budget else None),
    }


def save(data):
    temporary = OUT / "summary.next"
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUT / "summary.json")


def measure(seconds):
    names, sources, status = name_sources()
    complete = all(sources.values())
    hz = os.sysconf("SC_CLK_TCK")
    begin = last = time.monotonic()
    boot_start = float((PROC / "uptime").read_text().split()[0]) * hz
    system_before = system_last = system_stat()
    previous = snapshot(daemon_pid())
    totals = {}
    samples, machine_peak = 0, 0.0
    result = {"stage": "measuring", "mask_sources": sources}
    save(result)
    while time.monotonic() - begin < seconds:
        time.sleep(min(5, max(0.01, seconds - (time.monotonic() - begin))))
        now = time.monotonic()
        current = snapshot(daemon_pid())
        system = system_stat()
        delta_total, delta_idle = system[0] - system_last[0], system[1] - system_last[1]
        machine_peak = max(machine_peak, 100 * (delta_total - delta_idle) / max(1, delta_total))
        for key, (ticks, name, role) in current.items():
            if key not in previous and key[1] < boot_start:
                continue
            old = previous.get(key, (0, name, role))[0]
            delta = max(0, ticks - old)
            item = totals.setdefault(key, {"name": name, "role": role, "ticks": 0, "peak": 0})
            item["ticks"] += delta
            item["peak"] = max(item["peak"], 100 * delta / hz / max(0.001, now - last))
        samples += 1
        previous, last, system_last = current, now, system
        if samples % 6 == 0:
            print(f"Замер CPU: прошло {now - begin:.0f} с", flush=True)
    elapsed = time.monotonic() - begin
    end_names, end_sources, end_status = name_sources()
    names.update(end_names)
    sources = {key: value and end_sources.get(key, False) for key, value in sources.items()}
    complete = all(sources.values())
    status = end_status or status

    def row(item):
        return {"name": safe_text(item["name"], names, complete),
                "cpu_one_core_mean_pct": round(100 * item["ticks"] / hz / elapsed, 1),
                "cpu_one_core_peak_pct": round(item["peak"], 1)}

    total, idle = system_last[0] - system_before[0], system_last[1] - system_before[1]
    result.update(stage="complete", mask_sources=sources, seconds=round(elapsed, 1),
                  samples=samples,
                  logical_cpus=system_last[2],
                  machine_all_cpus_mean_pct=round(100 * (total - idle) / max(1, total), 1),
                  machine_all_cpus_peak_pct=round(machine_peak, 1),
                  top10=[row(item) for item in sorted(totals.values(),
                                                    key=lambda item: -item["ticks"])[:10]],
                  xgw={role: {"observed_processes": sum(i["role"] == role for i in totals.values()),
                              "cpu_one_core_mean_pct": round(100 * sum(i["ticks"] for i in
                                  totals.values() if i["role"] == role) / hz / elapsed, 1)}
                       for role in ("daemon", "tray")},
                  panel={"server": "потоки демона, CPU уже входит в daemon",
                         "separate_process_cpu_pct": None,
                         "browser_frontend": "смотреть отдельно в диспетчере задач браузера"},
                  budget=budget_view(status, names, complete),
                  limits=("Короткие процессы между срезами могут быть пропущены; "
                          "argv/PID не сохранены"),
                  )
    save(result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if not 120 <= args.seconds <= 300:
        parser.error("замер должен длиться от 120 до 300 секунд")
    os.umask(0o077)
    OUT.mkdir(mode=0o700, exist_ok=True)
    if OUT.is_symlink() or OUT.stat().st_uid != 0:
        raise ValueError("private output directory")
    OUT.chmod(0o700)
    data = load_json(OUT / "summary.json") if args.report else measure(args.seconds)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
