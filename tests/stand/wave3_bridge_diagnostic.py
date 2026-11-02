"""Retrospective reads for N's partial result. Never replays requests or changes the gateway."""

import hashlib
import importlib.util
import ipaddress
import json
import math
import os
import re
import sqlite3
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/run/xgw-w3o")
OLD = Path("/run/xgw-w3n")
N_SHA = "2f02303299db7dbccb7dc5edfa971dbce595063ad0a88eff59ba8e8054c85fef"
spec = importlib.util.spec_from_file_location(
    "bridge_reader", Path(__file__).with_name("wave3_bridge_probe.py")
)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
reader = bridge.reader
CATEGORIES = {
    "permission": r"permission denied|operation not permitted|\beacces\b|\beperm\b",
    "name_resolution": r"no such host|name resolution|\blookup\b|\bdns\b",
    "timeout": r"timed out|timeout|deadline exceeded",
    "refused": r"connection refused|\beconnrefused\b",
    "unreachable": r"network is unreachable|no route to host|network unreachable",
    "tls_auth_or_handshake": r"\btls\b|certificate|handshake|reality|authentication|invalid user",
    "reset_or_eof": r"connection reset|broken pipe|unexpected eof|closed pipe|\beof\b",
}
VERDICTS = {
    "OK",
    "SLOW",
    "FROZEN",
    "BODY_RESET",
    "STALL_BEFORE_BODY",
    "CONNECT_FAIL",
    "TIMEOUT",
    "CANCELLED",
}


def checked(path, directory=False):
    st = path.lstat()
    mode = 0o700 if directory else 0o600
    kind = stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode)
    if path.is_symlink() or not kind or st.st_uid != 0 or st.st_mode & 0o777 != mode:
        raise ValueError("private input identity")
    return path


def save(name, value):
    fd = os.open(ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.write("\n")


def historical(value):
    cases = value.get("cases", [])
    if (
        value.get("marker") != "BRIDGE_PROBES_RECORDED"
        or value.get("candidates_total") != 71
        or value.get("selected_count") != 2
        or value.get("target_count") != 2
        or len(cases) != 2
    ):
        raise ValueError("not the reported N run")
    first, second = cases
    if (
        first.get("case") != "SB-1"
        or first.get("body_ok") is not False
        or first.get("protocol") != "vless"
        or second.get("case") != "SB-2"
        or second.get("protocol") != "vless"
        or second.get("body_ok") is not True
    ):
        raise ValueError("unexpected N cases")
    attempts = first.get("attempts", [])
    if (
        len(attempts) != 2
        or [x.get("target") for x in attempts] != [1, 2]
        or not all(
            x.get("curl_rc") == 97
            and x.get("http_status") == 0
            and x.get("bytes") == 0
            and x.get("body_ok") is False
            for x in attempts
        )
    ):
        raise ValueError("unexpected negative evidence")
    positive = second.get("attempts", [])
    if (
        len(positive) != 1
        or positive[0].get("http_status") != 206
        or positive[0].get("bytes") != 32769
        or positive[0].get("body_ok") is not True
    ):
        raise ValueError("unexpected positive evidence")
    b, a = value["before"], value["after"]
    times = [b["realtime"], a["realtime"], b["monotonic"], a["monotonic"]]
    if not all(type(x) in (int, float) and math.isfinite(x) and x > 0 for x in times):
        raise ValueError("missing N time basis")
    duration = a["monotonic"] - b["monotonic"]
    if not 0 < duration < 120 or abs((a["realtime"] - b["realtime"]) - duration) > 2:
        raise ValueError("ambiguous N interval")
    return b["realtime"], a["realtime"], b["monotonic"]


def classification(message):
    return [key for key, pattern in CATEGORIES.items() if re.search(pattern, message, re.I)]


def journal_summary(raw, tags):
    lines = raw.splitlines()
    result = {
        "rows": len(lines),
        "limit": 2000,
        "truncated": len(lines) > 2000,
        "parse_errors": 0,
        "error_priority_rows": 0,
        "global_categories": {key: 0 for key in CATEGORIES},
        "related": {
            label: {
                "matched_rows": 0,
                "categories": {key: 0 for key in CATEGORIES},
                "uncategorized_rows": 0,
            }
            for label in tags
        },
    }
    for line in lines[:2000]:
        try:
            entry = json.loads(line)
            message = entry.get("MESSAGE", "")
            if not isinstance(message, str):
                raise ValueError("nontext log")
            priority = str(entry.get("PRIORITY", ""))
            result["error_priority_rows"] += priority.isdigit() and int(priority) <= 3
            categories = classification(message)
            for key in categories:
                result["global_categories"][key] += 1
            for label, key in tags.items():
                # Include related detour tags, not an arbitrary substring or another fingerprint.
                pattern = r"(?<![\w-])sb-(?:out|in)-" + re.escape(key) + r"-d(?:-[\w-]+)?(?![\w-])"
                if re.search(pattern, message):
                    row = result["related"][label]
                    row["matched_rows"] += 1
                    row["uncategorized_rows"] += not categories
                    for category in categories:
                        row["categories"][category] += 1
        except (ValueError, AttributeError, TypeError):
            result["parse_errors"] += 1
    return result


def endpoint_summary(applied, key):
    tag = "sb-out-" + key + "-d"
    item = next(
        x
        for x in applied.get("outbounds", []) + applied.get("endpoints", [])
        if x.get("tag") == tag
    )
    address = item.get("server")
    try:
        parsed = ipaddress.ip_address(address)
        kind = (
            ("ipv" + str(parsed.version) + "_global") if parsed.is_global else "non_global_literal"
        )
    except ValueError:
        kind = "hostname" if isinstance(address, str) and address else "absent"
    tls, transport = item.get("tls") or {}, item.get("transport") or {}
    flow = item.get("flow") or ""
    transport_kind = transport.get("type") or "tcp_or_default"
    host_entries = []
    for server in applied.get("dns", {}).get("servers", []):
        if server.get("type") == "hosts":
            host_entries.extend(server.get("predefined", {}).get(address, []))
    global_entries = []
    for value in host_entries:
        try:
            global_entries.append(ipaddress.ip_address(value).is_global)
        except ValueError:
            global_entries.append(False)
    return {
        "protocol": item["type"],
        "server_kind": kind,
        "remote_port_class": "443" if item.get("server_port") == 443 else "other_or_absent",
        "tls_enabled": tls.get("enabled") is True,
        "tls_server_name_present": bool(tls.get("server_name")),
        "tls_insecure_configured": tls.get("insecure") is True,
        "reality_enabled": (tls.get("reality") or {}).get("enabled") is True,
        "utls_enabled": (tls.get("utls") or {}).get("enabled") is True,
        "flow": flow if flow in ("", "xtls-rprx-vision") else "OTHER",
        "transport": transport_kind
        if transport_kind in ("tcp_or_default", "ws", "grpc", "http", "httpupgrade", "quic")
        else "OTHER",
        "multiplex_enabled": (item.get("multiplex") or {}).get("enabled") is True,
        "detour_present": bool(item.get("detour")),
        "bind_interface_present": bool(item.get("bind_interface")),
        "bind_address_present": bool(
            item.get("inet4_bind_address") or item.get("inet6_bind_address")
        ),
        "static_host_entries_count": len(host_entries),
        "static_host_entries_all_global": all(global_entries) if host_entries else None,
    }


def scan_summary(database, key, begin, end):
    conn = None
    try:
        conn = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=0.5)
        rows = conn.execute(
            "SELECT fingerprint, tag FROM nodes WHERE fingerprint LIKE ?", (key + "%",)
        ).fetchall()
        result = {"query_ok": True, "matching_nodes": len(rows)}
        if len(rows) != 1:
            return result
        fp, tag = rows[0]
        match = re.fullmatch(r"(?:proxy|spare|probe)-([a-z]{2})-([0-9a-f]{4,8})", tag or "")
        if not match or not fp.startswith(match[2]):
            return {**result, "probe_tag_derived": False}
        row = conn.execute(
            "SELECT verdict, bytes, seconds, ts FROM scans WHERE probe_tag = ?",
            ("probe-" + match[1] + "-" + match[2],),
        ).fetchone()
        result.update(probe_tag_derived=True, scan_present=row is not None)
        if row:
            verdict, size, seconds, stamp = row
            valid = type(stamp) in (int, float) and math.isfinite(stamp)
            result.update(
                verdict=verdict if verdict in VERDICTS else "OTHER",
                bytes=size if type(size) is int and size >= 0 else None,
                seconds=seconds
                if type(seconds) in (int, float) and math.isfinite(seconds) and seconds >= 0
                else None,
                relation_to_N=("before" if stamp < begin else "during" if stamp <= end else "after")
                if valid
                else "UNKNOWN",
                age_at_N_start_seconds=round(begin - stamp, 3) if valid else None,
            )
        return result
    except (OSError, sqlite3.Error, ValueError, TypeError, AttributeError):
        return {"query_ok": False}
    finally:
        if conn is not None:
            conn.close()


def main():
    if os.geteuid() != 0:
        raise ValueError("root required")
    checked(ROOT, True)
    if sys.argv[1] == "show":
        print(checked(ROOT / "summary.json").read_text())
        return 0
    if sys.argv[1] != "run" or (ROOT / "summary.json").exists():
        raise ValueError("invalid or already run")
    before, old_pin = reader.snapshot(), bridge.pin_token()
    config_digest = None
    result = {"before": reader.public(before), "marker": "STOP_READ_DIAGNOSTIC", "cases": {}}
    try:
        if not bridge.process_ready(before):
            raise ValueError("working context unknown")
        checked(OLD, True)
        source = checked(OLD / "wave3_bridge_probe.py").read_bytes()
        if hashlib.sha256(source).hexdigest() != N_SHA:
            raise ValueError("historical helper changed")
        raw_summary = checked(OLD / "summary.json").read_bytes()
        previous = json.loads(raw_summary)
        begin, end, mono = historical(previous)
        result.update(
            historical_summary_valid=True,
            historical_interval_seconds=round(end - begin, 3),
            clock_basis_compatible=abs((time.time() - begin) - (time.monotonic() - mono)) <= 5,
        )
        path = reader.PATHS.singbox_config_file
        raw, info = path.read_bytes(), path.stat()
        config_digest = hashlib.sha256(raw).digest()
        applied = json.loads(raw)
        candidates = bridge.bridges(applied)
        supported = (
            result["clock_basis_compatible"]
            and info.st_mtime <= begin
            and info.st_ctime <= begin
            and len(candidates) == previous["candidates_total"]
            and len(candidates) >= 2
            and all(x["protocol"] == "vless" for x in candidates[:2])
        )
        result.update(
            current_candidate_count=len(candidates),
            config_file_times_predate_N=info.st_mtime <= begin and info.st_ctime <= begin,
            historical_mapping="FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN"
            if supported
            else "UNCONFIRMED",
        )
        tags = (
            {"SB-" + str(index): item["key"] for index, item in enumerate(candidates[:2], 1)}
            if supported
            else {}
        )
        if tags:
            save(
                "mapping-private.json",
                {
                    "n_summary_sha256": hashlib.sha256(raw_summary).hexdigest(),
                    "current_config_sha256": hashlib.sha256(raw).hexdigest(),
                    "case_keys": tags,
                    "mapping_basis": result["historical_mapping"],
                },
            )
            for label, key in tags.items():
                result["cases"][label] = {
                    "current_config": endpoint_summary(applied, key),
                    "latest_persisted_scan": scan_summary(reader.PATHS.db_file, key, begin, end),
                }
        try:
            p = subprocess.run(
                [
                    "journalctl",
                    "-u",
                    "xgw-singbox",
                    "--since",
                    "@" + str(begin - 2),
                    "--until",
                    "@" + str(end + 2),
                    "-n",
                    "2001",
                    "-o",
                    "json",
                    "--no-pager",
                ],
                capture_output=True,
                timeout=3,
                check=False,
            )
            result["journal"] = {"query_ok": p.returncode == 0, "padding_seconds": 2}
            if p.returncode == 0:
                result["journal"].update(journal_summary(p.stdout, tags))
        except (OSError, subprocess.TimeoutExpired):
            result["journal"] = {"query_ok": False, "padding_seconds": 2}
    except Exception as exc:
        result["read_error_class"] = type(exc).__name__
    try:
        after, new_pin = reader.snapshot(), bridge.pin_token()
        result["after"] = reader.public(after)
        result["current_bridge_config_unchanged"] = (
            config_digest is not None
            and hashlib.sha256(reader.PATHS.singbox_config_file.read_bytes()).digest()
            == config_digest
        )
        result["same_singbox_process"] = before["singbox"].get(
            "process_identity"
        ) is not None and before["singbox"].get("process_identity") == after["singbox"].get(
            "process_identity"
        )
        result["same_boot"] = before["boot_private"] == after["boot_private"]
        result["settings_unchanged"] = [
            a is not None and a == b
            for a, b in zip(before["hashes_private"], after["hashes_private"], strict=True)
        ]
        result["on_context_preserved"] = bridge.process_ready(before) and bridge.process_ready(
            after
        )
        result["pin_record_readable_before_after"] = [old_pin is not None, new_pin is not None]
        result["pin_record_unchanged"] = (
            old_pin is not None and new_pin is not None and old_pin == new_pin
        )
        result["service_pid_same"] = {
            unit: before["unit_private"].get(unit, {}).get("MainPID")
            == after["unit_private"].get(unit, {}).get("MainPID")
            if before["unit_private"].get(unit) and after["unit_private"].get(unit)
            else None
            for unit in reader.UNITS
        }
        result["marker"] = (
            "READ_DIAGNOSTIC_RECORDED"
            if result.get("historical_summary_valid") and result["on_context_preserved"]
            else "STOP_READ_DIAGNOSTIC"
        )
    except Exception as exc:
        result["after_read_error_class"] = type(exc).__name__
    save("summary.json", result)
    print(json.dumps(result))
    return 0 if result["marker"] == "READ_DIAGNOSTIC_RECORDED" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("STOP_READ_DIAGNOSTIC", type(exc).__name__)
        raise SystemExit(3) from None
