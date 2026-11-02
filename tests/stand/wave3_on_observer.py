"""Bookend-only observation of an existing on gateway; no network/service writes."""

import grp
import hashlib
import json
import os
import pwd
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/xgw/lib")
from xgw import config, managed
from xgw.net import cmd, lan
from xgw.paths import Paths

ROOT = Path("/run/xgw-w3l")
PATHS = Paths(Path("/"))
UNITS = ("xgw", "xgw-net", "xgw-xray", "xgw-singbox", "xgw-dhcp", "tailscaled")
WATCHED = (
    PATHS.config_file,
    managed.path_for(PATHS.config_file),
    PATHS.opt / "lib/xgw/net/nft.py",
)


def save(name, value):
    fd = os.open(
        ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.write("\n")


def load(name):
    return json.loads((ROOT / name).read_text())


def query(argv):
    try:
        p = subprocess.run(argv, capture_output=True, timeout=3, check=False)
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired:
        return None, b""
    except OSError:
        return -1, b""


def enabled():
    try:
        value = json.loads((PATHS.var / "capture.json").read_text()).get("enabled")
        return value if type(value) is bool else None
    except (OSError, ValueError):
        return None


def hashes():
    result = []
    for path in WATCHED:
        try:
            result.append(hashlib.sha256(path.read_bytes()).hexdigest())
        except OSError:
            result.append(None)
    return result


def guard_layout(items):
    """Фактические hook/drop, без правил, адресов и имён чужих объектов."""
    result = {
        "query": "ok",
        "host_hook": None,
        "host_priority": None,
        "forward_hook": None,
        "host_drop_rules": 0,
        "host_reject_rules": 0,
    }
    for item in items:
        chain = item.get("chain", {})
        if chain.get("table") == "xgw_guard":
            if chain.get("name") == "output":
                hook = chain.get("hook")
                result["host_hook"] = (
                    hook if hook in ("output", "postrouting") else "other"
                )
                priority = chain.get("prio")
                result["host_priority"] = priority if type(priority) is int else None
            elif chain.get("name") == "forward":
                result["forward_hook"] = (
                    "forward" if chain.get("hook") == "forward" else "other"
                )
        rule = item.get("rule", {})
        if rule.get("table") == "xgw_guard" and rule.get("chain") == "output":
            result["host_drop_rules"] += any(
                "drop" in expr for expr in rule.get("expr", [])
            )
            result["host_reject_rules"] += any(
                "reject" in expr for expr in rule.get("expr", [])
            )
    return result


def guard():
    rc, raw = query(["nft", "-n", "-y", "-j", "list", "table", "inet", "xgw_guard"])
    try:
        if rc != 0:
            return {"query": "timeout" if rc is None else "nonzero", "rc": rc}
        items = json.loads(raw)["nftables"]
        if not isinstance(items, list) or not all(
            isinstance(item, dict) for item in items
        ):
            raise ValueError("shape")
        return guard_layout(items)
    except (ValueError, KeyError, TypeError, AttributeError):
        return {"query": "parse_or_schema_error", "rc": rc}


def services():
    rc, raw = query(
        [
            "systemctl",
            "show",
            *(unit + ".service" for unit in UNITS),
            "--property=Id,ActiveState,MainPID,NRestarts",
        ]
    )
    result = {}
    if rc == 0:
        for block in raw.decode(errors="replace").strip().split("\n\n"):
            fields = dict(
                line.split("=", 1) for line in block.splitlines() if "=" in line
            )
            name = fields.get("Id", "").removesuffix(".service")
            if name in UNITS:
                result[name] = fields
    return result


def caps(pid):
    try:
        proc = Path("/proc") / str(int(pid))
        before = (proc / "stat").read_text().rsplit(")", 1)[1].split()[19]
        fields = dict(
            line.split(":", 1)
            for line in (proc / "status").read_text().splitlines()
            if ":" in line
        )
        after = (proc / "stat").read_text().rsplit(")", 1)[1].split()[19]
        account = pwd.getpwnam("xgw-singbox")
        forbidden = {grp.getgrnam("root").gr_gid, grp.getgrnam("xray").gr_gid}
        groups = {int(value) for value in fields["Groups"].split()}
        return {
            "process_identity": [int(pid), before],
            "same_process_during_read": before == after,
            "account_nonprivileged": account.pw_uid
            not in (0, pwd.getpwnam("xray").pw_uid)
            and account.pw_gid not in forbidden,
            "uid_all_match_service": [int(x) for x in fields["Uid"].split()]
            == [account.pw_uid] * 4,
            "gid_all_match_service": [int(x) for x in fields["Gid"].split()]
            == [account.pw_gid] * 4,
            "forbidden_groups_absent": not bool(groups & forbidden),
            "cap_sets_zero": {
                key: int(fields[key], 16) == 0
                for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
            },
            "no_new_privs": fields.get("NoNewPrivs", "").strip() == "1",
        }
    except (OSError, ValueError, KeyError, IndexError):
        return {"read": "UNKNOWN"}


def metadata():
    result = {}
    for role, directory, group in [
        ("xray", PATHS.xray_config_dir, "xray"),
        ("singbox", PATHS.singbox_config_dir, "xgw-singbox"),
    ]:
        try:
            d, f = directory.stat(), (directory / "config.json").stat()
            gid = grp.getgrnam(group).gr_gid
            result[role] = {
                "directory_dac_expected": d.st_uid == 0
                and d.st_gid == gid
                and d.st_mode & 0o7777 == 0o2750,
                "file_dac_expected": f.st_uid == 0
                and f.st_gid == gid
                and f.st_mode & 0o7777 == 0o640,
            }
        except (OSError, KeyError):
            result[role] = {"read": "UNKNOWN"}
    return result


def interface(name):
    result = {}
    for key, file in [
        ("rx_bytes", "statistics/rx_bytes"),
        ("tx_bytes", "statistics/tx_bytes"),
        ("carrier", "carrier"),
    ]:
        try:
            result[key] = (
                int((Path("/sys/class/net") / name / file).read_text())
                if name
                else None
            )
        except (OSError, ValueError):
            result[key] = None
    return result


def snapshot():
    began = time.monotonic()
    before, old_hashes = enabled(), hashes()
    cfg, warnings = config.load(PATHS.config_file)
    if warnings:
        raise ValueError("configuration warnings")
    wan = lan.effective_wan(cfg, lambda argv: cmd.run(argv, timeout=3))
    units = services()
    sb = units.get("xgw-singbox", {})
    result = {
        "monotonic": began,
        "realtime": time.time(),
        "capture_before": before,
        "pool_mode": cfg.free_pool.mode,
        "router_mode": cfg.network.router_mode,
        "tailscale_route": cfg.tailscale.route,
        "derp_fallback_configured": cfg.tailscale.derp_fallback,
        "interfaces_distinct": bool(
            wan and cfg.network.lan_if and wan != cfg.network.lan_if
        ),
        "interfaces": {"WAN": interface(wan), "LAN": interface(cfg.network.lan_if)},
        "interface_private": {"WAN": wan, "LAN": cfg.network.lan_if},
        "service_active": {
            unit: (
                units[unit]["ActiveState"] == "active"
                if units.get(unit, {}).get("ActiveState")
                in (
                    "active",
                    "inactive",
                    "failed",
                    "activating",
                    "deactivating",
                    "reloading",
                )
                else None
            )
            for unit in UNITS
        },
        "unit_private": units,
        "singbox": caps(sb.get("MainPID", "0")),
        "config_dac": metadata(),
        "guard": guard(),
        "hashes_private": old_hashes,
        "boot_private": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
    }
    result["files_unchanged_during_read"] = [
        old is not None and old == now
        for old, now in zip(old_hashes, hashes(), strict=True)
    ]
    result["capture_after"] = enabled()
    result["sample_seconds"] = round(time.monotonic() - began, 3)
    return result


def public(value):
    result = {
        key: item
        for key, item in value.items()
        if key
        not in ("hashes_private", "unit_private", "boot_private", "interface_private")
    }
    result["singbox"] = {
        key: item for key, item in value["singbox"].items() if key != "process_identity"
    }
    return result


def good(value):
    g = value["guard"]
    return (
        value["capture_before"] is True
        and value["capture_after"] is True
        and all(value["files_unchanged_during_read"])
        and all(value["service_active"].get(unit) for unit in UNITS[:-1])
        and g.get("query") == "ok"
        and g.get("host_hook") == "postrouting"
        and g.get("host_priority") == 10
        and g.get("forward_hook") == "forward"
        and g.get("host_drop_rules", 0) >= 1
        and g.get("host_reject_rules") == 0
    )


def logs(since):
    rc, raw = query(
        [
            "journalctl",
            "-u",
            "xgw",
            "-u",
            "xgw-singbox",
            "--since",
            "@" + str(since),
            "-n",
            "2001",
            "-o",
            "json",
            "--no-pager",
        ]
    )
    result = {"query_ok": rc == 0, "limit": 2000}
    if rc == 0:
        rows = raw.splitlines()
        result.update(
            rows=len(rows),
            truncated=len(rows) > 2000,
            error_priority_rows=0,
            traceback_rows=0,
            permission_rows=0,
            fatal_rows=0,
            parse_errors=0,
        )
        for row in rows[:2000]:
            try:
                value = json.loads(row)
                text = value.get("MESSAGE", "")
                text = text.lower() if isinstance(text, str) else ""
                priority = str(value.get("PRIORITY", ""))
                result["error_priority_rows"] += (
                    priority.isdigit() and int(priority) <= 3
                )
                result["traceback_rows"] += "traceback" in text
                result["permission_rows"] += (
                    "permission denied" in text or "operation not permitted" in text
                )
                result["fatal_rows"] += "fatal" in text
            except (ValueError, AttributeError):
                result["parse_errors"] += 1
    return result


def main():
    if (
        os.geteuid() != 0
        or ROOT.is_symlink()
        or ROOT.stat().st_uid != 0
        or ROOT.stat().st_mode & 0o777 != 0o700
    ):
        raise ValueError("private directory")
    mode = sys.argv[1]
    if mode == "start":
        if (ROOT / "start-private.json").exists():
            raise ValueError("already started")
        value = snapshot()
        save("start-private.json", value)
        safe = public(value)
        safe["marker"] = (
            "ON_OBSERVATION_STARTED" if good(value) else "STOP_BASELINE_READ"
        )
        save("start-summary.json", safe)
        print(json.dumps(safe, ensure_ascii=False))
        return 0 if good(value) else 3
    start = load("start-private.json")
    if mode == "show":
        for name in ("start-summary.json", "end-summary.json"):
            if (ROOT / name).exists():
                print(name, json.dumps(load(name), ensure_ascii=False))
        return 0
    if mode not in ("wait", "end") or not good(start):
        raise ValueError("invalid stage")
    if (
        start["boot_private"]
        != Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    ):
        raise ValueError("boot changed")
    elapsed = time.monotonic() - start["monotonic"]
    if mode == "wait":
        time.sleep(max(0, min(45, 600 - elapsed)))
        elapsed = time.monotonic() - start["monotonic"]
        print(
            json.dumps(
                {
                    "marker": "READY_FOR_END" if elapsed >= 600 else "WAIT_MORE",
                    "elapsed_seconds": round(elapsed, 3),
                }
            )
        )
        return 0
    if elapsed < 600 or (ROOT / "end-summary.json").exists():
        raise ValueError("too early or already ended")
    end = snapshot()
    interval = end["monotonic"] - start["monotonic"]
    result = {
        "start": public(start),
        "end": public(end),
        "elapsed_seconds": round(interval, 3),
        "bookends_on": good(start) and good(end),
        "settings_unchanged": [
            a is not None and a == b
            for a, b in zip(start["hashes_private"], end["hashes_private"], strict=True)
        ],
        "pool_mode_unchanged": start["pool_mode"] == end["pool_mode"],
        "clock_step_suspected": abs((end["realtime"] - start["realtime"]) - interval)
        > 2,
        "journals": logs(start["realtime"]),
        "service_pid_same": {},
        "restart_count_delta": {},
        "interface_byte_deltas": {},
        "interface_roles_same": start["interface_private"] == end["interface_private"],
    }
    for unit in UNITS:
        a, b = start["unit_private"].get(unit, {}), end["unit_private"].get(unit, {})
        result["service_pid_same"][unit] = (
            a.get("MainPID") == b.get("MainPID") if a and b else None
        )
        try:
            result["restart_count_delta"][unit] = int(b["NRestarts"]) - int(
                a["NRestarts"]
            )
        except (ValueError, KeyError):
            result["restart_count_delta"][unit] = None
    a, b = (
        start["singbox"].get("process_identity"),
        end["singbox"].get("process_identity"),
    )
    result["same_singbox_process_bookends"] = (
        a == b if a is not None and b is not None else None
    )
    for role in ("WAN", "LAN"):
        delta = {}
        for key in ("rx_bytes", "tx_bytes"):
            a, b = start["interfaces"][role][key], end["interfaces"][role][key]
            same = start["interface_private"][role] == end["interface_private"][role]
            delta[key] = (
                b - a if same and a is not None and b is not None and b >= a else None
            )
        result["interface_byte_deltas"][role] = delta
    result["marker"] = (
        "ON_OBSERVATION_RECORDED"
        if result["bookends_on"]
        and all(result["settings_unchanged"])
        and result["pool_mode_unchanged"]
        else "STOP_STATE_CHANGED"
    )
    save("end-summary.json", result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["marker"] == "ON_OBSERVATION_RECORDED" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("STOP_OBSERVER_READ", type(exc).__name__)
        raise SystemExit(3) from None
