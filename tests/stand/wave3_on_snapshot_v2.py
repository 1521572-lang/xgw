"""REC-B private snapshot and nft --check only. No arm, replay or live recovery mode."""

import copy
import hashlib
import json
import math
import os
import selectors
import stat
import subprocess
import sys
import time
import tomllib
from pathlib import Path

ROOT = Path("/run/xgw-w3y")
UNITS = ("xgw", "xgw-net", "xgw-xray", "xgw-singbox", "xgw-dhcp", "tailscaled")
INPUTS = {
    "config": Path("/etc/xgw/config.toml"),
    "panel": Path("/etc/xgw/panel.json"),
    "capture": Path("/var/lib/xgw/capture.json"),
    "xray": Path("/etc/xgw/xray/config.json"),
    "singbox": Path("/etc/xgw/sing-box/config.json"),
}
MARKERS = tuple(
    Path("/run/xgw") / name for name in ("capture-open", "tailscale-direct", "tailscale-via-vpn")
)
NFT_CAPTURE = ("nft", "-n", "-y", "-j", "list", "table", "ip", "xgw")
NFT_GUARD = ("nft", "-n", "-y", "-j", "list", "table", "inet", "xgw_guard")
RULES = ("ip", "-j", "rule", "show")
UNIT_QUERY = (
    "systemctl",
    "show",
    *(u + ".service" for u in UNITS),
    "--property=Id,ActiveState,SubState,MainPID,NRestarts",
    "--no-pager",
)
CHECK = ("nft", "-c", "-j", "-f", "-")


class Refuse(Exception):
    pass


def require(value, code):
    if not value:
        raise Refuse(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def decode(raw):
    def bad_constant(_):
        raise Refuse("NONFINITE_JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)


def secure_directory(path):
    info = path.lstat()
    require(
        stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700,
        "PRIVATE_DIRECTORY_METADATA",
    )


def read_file(path, limit=2 * 1024 * 1024, private=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(before.st_mode) and before.st_uid == 0 and not before.st_mode & 0o022,
            "INPUT_METADATA",
        )
        require(not private or stat.S_IMODE(before.st_mode) == 0o600, "PRIVATE_FILE_METADATA")
        require(before.st_size <= limit, "INPUT_SIZE_LIMIT")
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        require(len(raw) <= limit, "INPUT_SIZE_LIMIT")
        require(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            "INPUT_READ_RACE",
        )
    require(not path.is_symlink() and path.stat().st_ino == before.st_ino, "INPUT_REPLACED")
    return raw


def save(name, value, replace=False, raw=False):
    require(Path(name).name == name, "OUTPUT_NAME")
    target = ROOT / (name + ".part" if replace else name)
    payload = value if raw else (json.dumps(value, sort_keys=True) + "\n").encode()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    if replace:
        os.replace(target, ROOT / name)


def permitted(argv):
    fixed = (NFT_CAPTURE, NFT_GUARD, RULES, UNIT_QUERY, CHECK)
    route = False
    # The only variable argument is a validated non-reserved numeric XGW routing table.
    if len(argv) == 6 and tuple(argv[:5]) == ("ip", "-j", "route", "show", "table"):
        try:
            number = int(argv[5])
            route = (
                str(number) == argv[5]
                and 1 <= number <= 0x7FFFFFFF
                and number not in (253, 254, 255)
            )
        except (ValueError, TypeError):
            route = False
    return tuple(argv) in fixed or route


def query(argv, data=None):
    argv = tuple(argv)
    require(permitted(argv), "COMMAND_NOT_ALLOWED")
    require((argv == CHECK) == (data is not None), "COMMAND_STDIN_SCOPE")
    if data is not None:
        validate_transaction(decode(data))
    output, proc, deadline = bytearray(), None, time.monotonic() + 5
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            sent = 0
            if data is not None:
                os.set_blocking(proc.stdin.fileno(), False)
                selector.register(proc.stdin, selectors.EVENT_WRITE)
            reading = True
            while reading:
                left = deadline - time.monotonic()
                require(left > 0, "COMMAND_TIME_LIMIT")
                events = selector.select(left)
                require(events, "COMMAND_TIME_LIMIT")
                for key, _ in events:
                    if key.fileobj is proc.stdin:
                        count = os.write(proc.stdin.fileno(), data[sent : sent + 8192])
                        sent += count
                        if sent == len(data):
                            selector.unregister(proc.stdin)
                            proc.stdin.close()
                    else:
                        chunk = os.read(
                            proc.stdout.fileno(), min(8192, 8 * 1024 * 1024 - len(output))
                        )
                        if not chunk:
                            reading = False
                            break
                        output.extend(chunk)
                        require(len(output) < 8 * 1024 * 1024, "COMMAND_BYTE_LIMIT")
        proc.wait(timeout=max(0.01, deadline - time.monotonic()))
        require(proc.returncode == 0, "COMMAND_NONZERO")
        return bytes(output)
    except Exception as exc:
        exc.command_role = {
            NFT_CAPTURE: "NFT_CAPTURE_JSON",
            NFT_GUARD: "NFT_GUARD_JSON",
            RULES: "IPV4_RULES",
            UNIT_QUERY: "UNIT_PROPERTIES",
            CHECK: "NFT_CHECK_ONLY",
        }.get(argv, "IPV4_ROUTES")
        exc.command_rc = proc.returncode if proc is not None else None
        raise
    finally:
        if proc is not None:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=1)
            for stream in (proc.stdin, proc.stdout):
                if stream is not None and not stream.closed:
                    stream.close()


def normalize(value):
    if isinstance(value, dict):
        require("expires" not in value, "DYNAMIC_EXPIRATION_UNSUPPORTED")
        result = {}
        for key, child in value.items():
            if key == "counter" and isinstance(child, dict):
                child = {k: v for k, v in child.items() if k not in ("packets", "bytes")}
                child = child or None
            result[key] = normalize(child)
        return result
    if isinstance(value, list):
        return [normalize(child) for child in value]
    return value


def nft_objects(value, family, table):
    require(
        isinstance(value, dict)
        and set(value) == {"nftables"}
        and isinstance(value["nftables"], list),
        "NFT_SCHEMA",
    )
    result, tables = [], 0
    for entry in value["nftables"]:
        require(isinstance(entry, dict) and len(entry) == 1, "NFT_ENTRY_SCHEMA")
        kind, body = next(iter(entry.items()))
        if kind == "metainfo":
            continue
        require(
            kind in ("table", "chain", "set", "map", "rule", "element") and isinstance(body, dict),
            "NFT_OBJECT_UNSUPPORTED",
        )
        require(body.get("family") == family, "FOREIGN_NFT_FAMILY")
        require(body.get("name" if kind == "table" else "table") == table, "FOREIGN_NFT_TABLE")
        require(kind != "table" or not body.get("flags"), "NFT_TABLE_FLAGS_UNSUPPORTED")
        tables += kind == "table"
        result.append({kind: normalize({k: v for k, v in body.items() if k != "handle"})})
    require(tables == 1 and result and "table" in result[0], "NFT_TABLE_COUNT_OR_ORDER")
    return result


def make_transaction(objects):
    nft_objects({"nftables": objects}, "ip", "xgw")
    table = {"family": "ip", "name": "xgw"}
    value = {
        "nftables": [
            {"add": {"table": table}},
            {"delete": {"table": table}},
            *({"add": entry} for entry in objects),
        ]
    }
    validate_transaction(value)
    return value


def validate_transaction(value):
    require(isinstance(value, dict) and set(value) == {"nftables"}, "TRANSACTION_SCHEMA")
    entries = value["nftables"]
    target = {"table": {"family": "ip", "name": "xgw"}}
    require(
        isinstance(entries, list)
        and len(entries) >= 3
        and entries[:2] == [{"add": target}, {"delete": target}],
        "TRANSACTION_PREFIX",
    )
    objects = []
    for entry in entries[2:]:
        require(isinstance(entry, dict) and set(entry) == {"add"}, "TRANSACTION_OPERATION")
        objects.append(entry["add"])
    nft_objects({"nftables": objects}, "ip", "xgw")
    return True


def settings(raw):
    cfg = tomllib.loads(raw.decode("utf-8"))
    cap = cfg.get("capture", {})
    require(
        isinstance(cap, dict) and str(cap.get("method", "tproxy")).strip().lower() == "tproxy",
        "UNSUPPORTED_CAPTURE_METHOD",
    )
    table, mark = cap.get("route_table", 100), cap.get("mark_proxy", 1)
    require(
        type(table) is int and 1 <= table <= 0x7FFFFFFF and table not in (253, 254, 255),
        "UNSAFE_ROUTE_TABLE",
    )
    require(type(mark) is int and 1 <= mark <= 0xFFFFFFFF, "UNSAFE_PROXY_MARK")
    return table, mark


def status_gate(value, now):
    updated = value.get("updated")
    require(
        type(updated) in (int, float) and math.isfinite(updated) and -5 <= now - updated <= 120,
        "STALE_CACHED_STATUS",
    )
    cap = value.get("capture") or {}
    require(
        value.get("daemon") is True
        and value.get("state") == "HEALTHY"
        and cap.get("mode") == "on"
        and cap.get("loaded") is True
        and cap.get("blocked") is False
        and not cap.get("inbound_missing")
        and cap.get("tun") is False,
        "WORKING_ON_UNCONFIRMED",
    )
    return True


def guard_observation(objects):
    chains = {entry["chain"].get("name"): entry["chain"] for entry in objects if "chain" in entry}
    host, forward = chains.get("output", {}), chains.get("forward", {})
    expressions = [
        expr
        for entry in objects
        if "rule" in entry and entry["rule"].get("chain") == "output"
        for expr in entry["rule"].get("expr", [])
    ]
    return {
        "host_chain_present": bool(host),
        "forward_chain_present": bool(forward),
        "host_hook_expected": host.get("hook") == "postrouting",
        "host_priority_expected": host.get("prio") == 10,
        "forward_hook_expected": forward.get("hook") == "forward",
        "forward_priority_expected": forward.get("prio") == 10,
        "host_drop_rules": sum(isinstance(x, dict) and "drop" in x for x in expressions),
        "host_reject_rules": sum(isinstance(x, dict) and "reject" in x for x in expressions),
    }


def guard_gate(objects):
    observation = guard_observation(objects)
    layout = all(
        observation[key]
        for key in (
            "host_chain_present",
            "forward_chain_present",
            "host_hook_expected",
            "host_priority_expected",
            "forward_hook_expected",
            "forward_priority_expected",
        )
    )
    verdict = observation["host_drop_rules"] > 0 and observation["host_reject_rules"] == 0
    if not layout or not verdict:
        exc = Refuse("GUARD_LAYOUT" if not layout else "GUARD_VERDICT")
        exc.safe_details = {"guard_observation": observation}
        raise exc
    return observation


def unit_pid(name, values):
    require(
        values.get("ActiveState") == "active" and values.get("MainPID", "").isdigit(),
        "UNIT_NOT_ACTIVE",
    )
    pid = int(values["MainPID"])
    require(
        pid > 0 or (name == "xgw-net" and pid == 0 and values.get("SubState") == "exited"),
        "UNIT_PID_MISSING",
    )
    return pid


def has_tproxy(value):
    if isinstance(value, dict):
        return "tproxy" in value or any(has_tproxy(child) for child in value.values())
    return isinstance(value, list) and any(has_tproxy(child) for child in value)


def collect():
    raw, missing = {}, []
    for name, path in INPUTS.items():
        try:
            raw[name] = read_file(path)
        except FileNotFoundError:
            require(name == "panel", "REQUIRED_INPUT_MISSING")
            missing.append(name)
    table, mark = settings(raw["config"])
    require(decode(raw["capture"]).get("enabled") is True, "CAPTURE_CHOICE_NOT_ON")
    for name in ("xray", "singbox"):
        require(isinstance(decode(raw[name]), dict), "CORE_CONFIG_SHAPE")
    if "panel" in raw:
        require(isinstance(decode(raw["panel"]), dict), "PANEL_CONFIG_SHAPE")
    status = decode(read_file(Path("/run/xgw/status.json")))
    status_gate(status, time.time())
    raw["cached_status"] = (json.dumps(status) + "\n").encode()
    marker_values = []
    for path in MARKERS:
        require(not path.is_symlink(), "MARKER_SYMLINK")
        marker_values.append(path.exists())
    require(not marker_values[0], "CAPTURE_OPEN_MARKER")
    capture = nft_objects(decode(query(NFT_CAPTURE)), "ip", "xgw")
    require(
        any("rule" in entry and has_tproxy(entry["rule"].get("expr", [])) for entry in capture),
        "CAPTURE_TPROXY_UNCONFIRMED",
    )
    guard = nft_objects(decode(query(NFT_GUARD)), "inet", "xgw_guard")
    guard_gate(guard)
    rules = decode(query(RULES))
    routes = decode(query(("ip", "-j", "route", "show", "table", str(table))))
    require(isinstance(rules, list) and isinstance(routes, list), "ROUTING_SCHEMA")
    matched = [
        row
        for row in rules
        if str(row.get("table")) == str(table)
        and row.get("priority") == 100
        and str(row.get("fwmark")) in (str(mark), hex(mark))
        and set(row) <= {"priority", "src", "dst", "fwmark", "fwmask", "iif", "table", "protocol"}
        and row.get("src") in (None, "all")
        and row.get("dst") in (None, "all")
        and row.get("iif") is None
        and str(row.get("fwmask", "0xffffffff")) in ("0xffffffff", "4294967295")
    ]
    require(len(matched) == 1, "REQUIRED_PROXY_RULE_UNCONFIRMED")
    require(
        any(
            row.get("type") == "local"
            and row.get("dev") == "lo"
            and row.get("dst") in ("default", "0.0.0.0/0")
            for row in routes
        ),
        "REQUIRED_LOCAL_ROUTE_UNCONFIRMED",
    )
    units = {}
    for block in query(UNIT_QUERY).decode().strip().split("\n\n"):
        values = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        name = values.get("Id", "").removesuffix(".service")
        if name in UNITS:
            pid = unit_pid(name, values)
            started = (
                (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()[19]
                if pid
                else None
            )
            units[name] = [pid, started, values.get("NRestarts")]
    require(set(units) == set(UNITS), "UNIT_SET_INCOMPLETE")
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    require(boot and len(boot) < 64, "BOOT_ID_UNAVAILABLE")
    require(sum(map(len, raw.values())) <= 16 * 1024 * 1024, "INPUT_TOTAL_LIMIT")
    return {
        "raw": raw,
        "missing": missing,
        "capture": capture,
        "guard": guard,
        "rules": rules,
        "routes": routes,
        "units": units,
        "boot": boot,
        "markers": marker_values,
        "table": table,
    }


def stability(before, after):
    keys = set(before["raw"]) - {"cached_status"}
    return {
        "inputs_unchanged": keys == set(after["raw"]) - {"cached_status"}
        and all(before["raw"][k] == after["raw"][k] for k in keys),
        "optional_absence_unchanged": before["missing"] == after["missing"],
        **{
            name + "_unchanged": before[name] == after[name]
            for name in ("capture", "guard", "rules", "routes", "units", "boot", "markers")
        },
    }


def manifest_check(value, payload):
    require(
        value.get("version") == 1
        and value.get("scope") == "CAPTURE_TABLE_ONLY_IPV4"
        and value.get("status") == "PLANNED_NOT_ARMED",
        "MANIFEST_SCOPE",
    )
    require(set(value.get("files", {})) == set(payload), "MANIFEST_MEMBERS")
    for name, raw in payload.items():
        require(
            Path(name).name == name
            and value["files"][name] == {"sha256": digest(raw), "size": len(raw)},
            "MANIFEST_DIGEST",
        )
    require(
        value.get("writer_fence_verified") is False
        and value.get("runtime_recovery_implemented") is False
        and value.get("active_faults_authorized") is False,
        "MANIFEST_UNSAFE_GATE",
    )
    return True


def synthetic_guard():
    # Product render_guard uses priority 10 for both chains; 5 is an observed drop count.
    return [
        {"table": {"family": "inet", "name": "xgw_guard"}},
        {
            "chain": {
                "family": "inet",
                "table": "xgw_guard",
                "name": "output",
                "hook": "postrouting",
                "prio": 10,
            }
        },
        {
            "chain": {
                "family": "inet",
                "table": "xgw_guard",
                "name": "forward",
                "hook": "forward",
                "prio": 10,
            }
        },
        *(
            {
                "rule": {
                    "family": "inet",
                    "table": "xgw_guard",
                    "chain": "output",
                    "expr": [{"drop": None}],
                }
            }
            for _ in range(5)
        ),
    ]


def fixtures():
    results = []

    def check(name, objects, reject=False):
        try:
            guard_gate(objects)
            ok = not reject
        except Refuse:
            ok = reject
        except Exception:
            ok = False
        results.append({"case": name, "passed": ok})

    good = synthetic_guard()
    check("GUARD_PRODUCT_PRIORITY_TEN_ACCEPTED", good)
    bad = copy.deepcopy(good)
    bad[2]["chain"]["prio"] = 5
    check("GUARD_FORWARD_PRIORITY_FIVE_REJECTED", bad, True)
    bad = copy.deepcopy(good)
    bad[1]["chain"]["prio"] = 5
    check("GUARD_WRONG_HOST_PRIORITY_REJECTED", bad, True)
    bad = copy.deepcopy(good)
    bad[2]["chain"]["hook"] = "output"
    check("GUARD_WRONG_FORWARD_HOOK_REJECTED", bad, True)
    bad = copy.deepcopy(good)
    bad.append(
        {
            "rule": {
                "family": "inet",
                "table": "xgw_guard",
                "chain": "output",
                "expr": [{"reject": None}],
            }
        }
    )
    check("GUARD_HOST_REJECT_REJECTED", bad, True)
    check("GUARD_MISSING_FORWARD_REJECTED", good[:2] + good[3:], True)
    return {
        "total": len(results),
        "passed": sum(row["passed"] for row in results),
        "cases": results,
        "scope": "SIX_NEW_GUARD_CONTRACT_CASES_ONLY",
        "historical_X_validation_cases": "26_ACCEPTED_IN_REPORT_NOT_REEXECUTED",
    }


def worker():
    save("worker-claimed.json", {"claimed": True})
    result = {
        "marker": "ON_SNAPSHOT_V2_PARTIAL",
        "phases": {},
        "network_requests": 0,
        "writer_fence_verified": False,
        "runtime_recovery_implemented": False,
        "active_faults_authorized": False,
    }
    began = time.monotonic()
    before, transaction, payload = None, None, {}

    def phase(name, fn):
        save("progress.json", {"stage": name, "completed": list(result["phases"])}, True)
        try:
            result["phases"][name] = {"collection": "RECORDED", "data": fn()}
        except Exception as exc:
            result["phases"][name] = {
                "collection": "UNAVAILABLE",
                "error_class": type(exc).__name__,
            }
            if isinstance(exc, Refuse):
                result["phases"][name]["reason"] = str(exc)
            if hasattr(exc, "safe_details"):
                result["phases"][name]["safe_details"] = exc.safe_details
            if hasattr(exc, "command_role"):
                result["phases"][name]["command_role"] = exc.command_role
                result["phases"][name]["command_rc"] = exc.command_rc
        save("partial.json", result, True)

    phase("Y1_guard_regression_fixtures", fixtures)

    def snapshot():
        nonlocal before, transaction, payload
        before = collect()
        transaction = make_transaction(before["capture"])
        payload = {name + ".private": raw for name, raw in before["raw"].items()}
        payload["kernel.private"] = json.dumps(
            {k: v for k, v in before.items() if k != "raw"}
        ).encode()
        payload["draft-check-only.private"] = json.dumps(transaction).encode()
        require(sum(map(len, payload.values())) <= 32 * 1024 * 1024, "SNAPSHOT_TOTAL_LIMIT")
        for name, raw in payload.items():
            save(name, raw, raw=True)
        return {
            "private_files": len(payload),
            "capture_objects": len(before["capture"]),
            "guard_objects": len(before["guard"]),
            "rules": len(before["rules"]),
            "routes": len(before["routes"]),
            "units_active": len(before["units"]),
            "cached_on_status_fresh": True,
            "guard_basic_layout_expected": True,
            "guard_observation": guard_observation(before["guard"]),
            "scope": "IPV4_CAPTURE_TABLE_ONLY_NOT_FULL_REPLAY_READINESS",
        }

    phase("Y2_private_snapshot", snapshot)

    def syntax_check():
        require(transaction is not None and bool(payload), "NO_COMPLETE_SNAPSHOT")
        query(CHECK, json.dumps(transaction).encode())
        return {
            "nft_check_rc": 0,
            "changes_applied": False,
            "scope": "CHECK_ONLY_CURRENT_PRESENT_TABLE_NOT_RECOVERY_OR_ABSENT_TABLE_PROOF",
        }

    phase("Y3_nft_check_only", syntax_check)

    def after():
        require(before is not None, "NO_BEFORE_SNAPSHOT")
        value = stability(before, collect())
        value["all_observed_inputs_stable"] = all(value.values())
        return value

    phase("Y4_after_stability", after)
    try:
        done = result["phases"]
        require(all(v["collection"] == "RECORDED" for v in done.values()), "INCOMPLETE_COLLECTION")
        require(done["Y1_guard_regression_fixtures"]["data"]["passed"] == 6, "FIXTURE_FAILURE")
        require(done["Y4_after_stability"]["data"]["all_observed_inputs_stable"], "STALE_SNAPSHOT")
        manifest = {
            "version": 1,
            "scope": "CAPTURE_TABLE_ONLY_IPV4",
            "status": "PLANNED_NOT_ARMED",
            "files": {
                name: {"sha256": digest(raw), "size": len(raw)} for name, raw in payload.items()
            },
            "writer_fence_verified": False,
            "runtime_recovery_implemented": False,
            "active_faults_authorized": False,
        }
        manifest_check(manifest, payload)
        persisted = {
            name: read_file(ROOT / name, limit=32 * 1024 * 1024, private=True) for name in payload
        }
        manifest_check(manifest, persisted)
        save("manifest-private.json", manifest)
        manifest_check(decode(read_file(ROOT / "manifest-private.json", private=True)), persisted)
        result.update(
            marker="ON_SNAPSHOT_V2_PLAN_RECORDED",
            plan_status="PLANNED_NOT_ARMED",
            private_manifest_written=True,
        )
    except Exception as exc:
        result["qualification_error_class"] = type(exc).__name__
        if isinstance(exc, Refuse):
            result["qualification_reason"] = str(exc)
    result["elapsed_seconds"] = round(time.monotonic() - began, 3)
    save("summary.json", result)
    save("progress.json", {"stage": "FINISHED", "marker": result["marker"]}, True)


def main():
    require(os.geteuid() == 0, "ROOT_REQUIRED")
    secure_directory(ROOT)
    mode = sys.argv[1] if len(sys.argv) == 2 else "INVALID"
    if mode in ("show", "status"):
        names = (
            ("summary.json", "partial.json", "progress.json")
            if mode == "show"
            else ("summary.json", "progress.json")
        )
        for name in names:
            if (ROOT / name).exists():
                print(
                    json.dumps({"file": name, "data": decode(read_file(ROOT / name, private=True))})
                )
                return 0
        print("SNAPSHOT_STATUS_UNAVAILABLE")
        return 3
    if mode == "_worker":
        read_file(ROOT / "started.json", private=True)
        worker()
        return 0
    require(
        mode == "start"
        and not any(
            (ROOT / name).exists() or (ROOT / name).is_symlink()
            for name in ("started.json", "worker-claimed.json", "summary.json")
        ),
        "ALREADY_STARTED_OR_MODE",
    )
    save("started.json", {"started": True})
    save("progress.json", {"stage": "LAUNCHING"}, True)
    try:
        subprocess.Popen(
            [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "_worker"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        save("summary.json", {"marker": "ON_SNAPSHOT_V2_PARTIAL", "launch_failed": True})
        return 3
    print("ON_SNAPSHOT_V2_STARTED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("STOP_ON_SNAPSHOT_V2", str(exc) if isinstance(exc, Refuse) else type(exc).__name__)
        raise SystemExit(3) from None
