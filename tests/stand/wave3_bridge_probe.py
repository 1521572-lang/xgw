"""Bounded HTTPS through existing permanent sing-box bridges; no control-plane writes."""

import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path("/run/xgw-w3n")
MIN_BODY = 32769
MAX_BODY = 131072
KINDS = {
    "hysteria",
    "hysteria2",
    "tuic",
    "anytls",
    "wireguard",
    "vless",
    "vmess",
    "trojan",
    "shadowsocks",
    "shadowtls",
    "socks",
    "http",
    "ssh",
}
spec = importlib.util.spec_from_file_location(
    "on_reader", Path(__file__).with_name("wave3_on_observer.py")
)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def bridges(config):
    rules = config.get("route", {}).get("rules", [])
    if not rules or rules[-1] != {"action": "reject"}:
        raise ValueError("noncanonical route")
    for rule in rules[:-1]:
        if (
            set(rule) != {"inbound", "action", "outbound"}
            or rule["action"] != "route"
            or not isinstance(rule["inbound"], list)
            or len(rule["inbound"]) != 1
        ):
            raise ValueError("ambiguous route")
    outs = config.get("outbounds", []) + config.get("endpoints", [])
    result = []
    for item in config.get("inbounds", []):
        match = re.fullmatch(r"sb-in-([0-9a-f]{8})-d", str(item.get("tag", "")))
        if not match:
            continue
        port, users = item.get("listen_port"), item.get("users")
        if (
            item.get("type") != "socks"
            or item.get("listen") != "127.0.0.1"
            or type(port) is not int
            or not 1024 <= port <= 65535
            or not isinstance(users, list)
            or len(users) != 1
            or users[0].get("username") != "xgw-d"
            or not isinstance(users[0].get("password"), str)
            or not users[0]["password"]
        ):
            raise ValueError("bridge identity")
        outgoing = "sb-out-" + match[1] + "-d"
        links = [r for r in rules[:-1] if r["inbound"] == [item["tag"]]]
        selected = [o for o in outs if o.get("tag") == outgoing]
        if (
            len(links) != 1
            or links[0]["outbound"] != outgoing
            or len(selected) != 1
            or selected[0].get("type") not in KINDS
        ):
            raise ValueError("unconfirmed proxy route")
        result.append(
            {
                "key": match[1],
                "port": port,
                "user": "xgw-d",
                "password": users[0]["password"],
                "protocol": selected[0]["type"],
            }
        )
    if len({x["port"] for x in result}) != len(result) or len({x["key"] for x in result}) != len(
        result
    ):
        raise ValueError("duplicate bridge")
    return sorted(result, key=lambda x: x["key"])


def owns_listener(pid, port, proc=Path("/proc")):
    process = proc / str(int(pid))
    try:
        if os.readlink(proc / "self/ns/net") != os.readlink(process / "ns/net"):
            return False
        inodes = set()
        for fd in (process / "fd").iterdir():
            try:
                value = os.readlink(fd)
                if value.startswith("socket:[") and value.endswith("]"):
                    inodes.add(value[8:-1])
            except OSError:
                pass
        wanted = "0100007F:" + format(port, "04X")
        for line in (process / "net/tcp").read_text().splitlines()[1:]:
            fields = line.split()
            if (
                len(fields) >= 10
                and fields[1] == wanted
                and fields[3] == "0A"
                and fields[9] in inodes
            ):
                return True
    except (OSError, ValueError):
        return False
    return False


def quoted(value):
    if not isinstance(value, str) or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("unsafe config text")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def mark_keys(value):
    if isinstance(value, dict):
        return sum(key == "routing_mark" for key in value) + sum(
            mark_keys(x) for x in value.values()
        )
    if isinstance(value, list):
        return sum(mark_keys(x) for x in value)
    return 0


def pin_token():
    conn = None
    try:
        conn = sqlite3.connect(reader.PATHS.db_file.as_uri() + "?mode=ro", uri=True, timeout=0.5)
        row = conn.execute("SELECT value FROM meta WHERE key = ?", ("pin",)).fetchone()
        value = None if row is None else row[0]
        return hashlib.sha256(json.dumps(value).encode()).digest()
    except (OSError, sqlite3.Error, ValueError):
        return None
    finally:
        if conn is not None:
            conn.close()


def targets(cfg):
    result = []
    for url in (cfg.probe.url, *cfg.probe.urls):
        try:
            p = urlsplit(url)
            if (
                len(url) > 2048
                or p.scheme != "https"
                or not p.hostname
                or p.username is not None
                or p.password is not None
                or p.fragment
                or not 1 <= (p.port or 443) <= 65535
            ):
                continue
            quoted(url)
            if url not in result:
                result.append(url)
        except (ValueError, TypeError):
            continue
        if len(result) == 2:
            break
    return result


def request(curl, bridge, url):
    # URLs and credentials stay in stdin/memory; no curlrc, direct fallback, redirect or retries.
    payload = (
        "url = "
        + quoted(url)
        + "\nproxy-user = "
        + quoted(bridge["user"] + ":" + bridge["password"])
        + "\n"
    )
    argv = [
        curl,
        "-q",
        "--config",
        "-",
        "--globoff",
        "--socks5-hostname",
        "127.0.0.1:" + str(bridge["port"]),
        "--socks5-basic",
        "--noproxy",
        "",
        "--proto",
        "=https",
        "--http1.1",
        "--connect-timeout",
        "2",
        "--max-time",
        "6",
        "--max-filesize",
        str(MAX_BODY),
        "--range",
        "0-32768",
        "--retry",
        "0",
        "--silent",
        "--show-error",
        "--output",
        "/dev/null",
        "--header",
        "Accept-Encoding: identity",
        "--write-out",
        "%{json}\n%header{content-encoding}",
    ]
    try:
        p = subprocess.run(
            argv,
            input=payload.encode(),
            capture_output=True,
            timeout=8,
            check=False,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "LANG": "C"},
        )
        first, sep, encoding = p.stdout.partition(b"\n")
        data = json.loads(first)
        code, size, seconds, verify = (
            data.get(key)
            for key in ("http_code", "size_download", "time_total", "ssl_verify_result")
        )
        valid = (
            type(code) is int
            and type(size) is int
            and size >= 0
            and type(seconds) in (int, float)
            and math.isfinite(seconds)
            and seconds >= 0
            and type(verify) is int
            and bool(sep)
        )
        if not valid:
            return {"outcome": "METADATA_UNKNOWN", "curl_rc": p.returncode, "body_ok": False}
        identity = encoding.strip().lower() in (b"", b"identity")
        passed = (
            p.returncode == 0
            and code in (200, 206)
            and MIN_BODY <= size <= MAX_BODY
            and verify == 0
            and identity
            and data.get("num_redirects") == 0
        )
        return {
            "outcome": "BODY_OK" if passed else "PROBE_FAILED",
            "curl_rc": p.returncode,
            "http_status": code,
            "bytes": size,
            "seconds": round(seconds, 3),
            "tls_verify_result": verify,
            "content_encoding_identity": identity,
            "body_ok": passed,
        }
    except subprocess.TimeoutExpired:
        return {"outcome": "WORKER_TIMEOUT", "body_ok": False}
    except (OSError, ValueError, AttributeError, TypeError):
        return {"outcome": "WORKER_OR_METADATA_ERROR", "body_ok": False}


def save(value):
    fd = os.open(ROOT / "summary.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.write("\n")


def process_ready(value):
    sb = value["singbox"]
    return (
        reader.good(value)
        and all(
            sb.get(key) is True
            for key in (
                "account_nonprivileged",
                "uid_all_match_service",
                "gid_all_match_service",
                "forbidden_groups_absent",
                "same_process_during_read",
                "no_new_privs",
            )
        )
        and all(
            sb.get("cap_sets_zero", {}).get(key) is True
            for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
        )
    )


def main():
    if (
        os.geteuid() != 0
        or ROOT.is_symlink()
        or ROOT.stat().st_uid != 0
        or ROOT.stat().st_mode & 0o777 != 0o700
    ):
        raise ValueError("private directory")
    if sys.argv[1] == "show":
        print((ROOT / "summary.json").read_text())
        return 0
    if sys.argv[1] != "run" or (ROOT / "summary.json").exists():
        raise ValueError("already run or invalid mode")
    before = reader.snapshot()
    old_pin = pin_token()
    result = {
        "before": reader.public(before),
        "cases": [],
        "marker": "STOP_BRIDGE_PRECONDITION",
        "pin_record_readable_before": old_pin is not None,
    }
    digest = None
    try:
        if old_pin is None or not process_ready(before):
            raise ValueError("on/process context")
        curl = shutil.which("curl")
        result["curl_available"] = curl is not None
        if not curl:
            raise ValueError("curl missing")
        version = subprocess.run(
            [curl, "-q", "--version"], capture_output=True, timeout=3, check=False
        )
        match = re.match(rb"curl (\d+)\.(\d+)\.(\d+)", version.stdout)
        if version.returncode != 0 or not match:
            raise ValueError("curl version unknown")
        triplet = tuple(int(x) for x in match.groups())
        result["curl_version"] = ".".join(str(x) for x in triplet)
        result["curl_version_eligible"] = triplet >= (8, 4, 0)
        if triplet < (8, 4, 0):
            raise ValueError("curl filesize limit too old")
        raw = reader.PATHS.singbox_config_file.read_bytes()
        digest = hashlib.sha256(raw).digest()
        applied = json.loads(raw)
        result["routing_mark_key_count"] = mark_keys(applied)
        if result["routing_mark_key_count"] != 0:
            raise ValueError("permanent config still has marks")
        candidates = bridges(applied)
        result["candidates_total"] = len(candidates)
        selected = candidates[:2]
        cfg, warnings = reader.config.load(reader.PATHS.config_file)
        urls = targets(cfg)
        result.update(
            selected_count=len(selected), target_count=len(urls), configured_targets_only=True
        )
        if warnings or not selected or not urls:
            raise ValueError("no eligible bridge or HTTPS target")
        pid = before["singbox"]["process_identity"][0]
        for index, bridge in enumerate(selected, 1):
            case = {
                "case": "SB-" + str(index),
                "protocol": bridge["protocol"],
                "profile": "d",
                "attempts": [],
            }
            result["cases"].append(case)
            for target_index, url in enumerate(urls, 1):
                owner = owns_listener(pid, bridge["port"])
                if (
                    reader.enabled() is not True
                    or not owner
                    or hashlib.sha256(reader.PATHS.singbox_config_file.read_bytes()).digest()
                    != digest
                ):
                    case["context_changed_or_listener_unconfirmed"] = True
                    break
                item = request(curl, bridge, url)
                item.update(
                    target=target_index,
                    listener_owned_before=True,
                    listener_owned_after=owns_listener(pid, bridge["port"]),
                )
                case["attempts"].append(item)
                if item["body_ok"] and item["listener_owned_after"]:
                    break
            case["body_ok"] = any(
                item.get("body_ok") is True and item.get("listener_owned_after") is True
                for item in case["attempts"]
            )
            if case.get("context_changed_or_listener_unconfirmed"):
                break
    except Exception as exc:
        result["precondition_error_class"] = type(exc).__name__
    try:
        after = reader.snapshot()
        result["after"] = reader.public(after)
        result["settings_unchanged"] = [
            a is not None and a == b
            for a, b in zip(before["hashes_private"], after["hashes_private"], strict=True)
        ]
        result["bridge_config_unchanged"] = (
            digest is not None
            and hashlib.sha256(reader.PATHS.singbox_config_file.read_bytes()).digest() == digest
        )
        result["service_pid_same"] = {
            unit: before["unit_private"].get(unit, {}).get("MainPID")
            == after["unit_private"].get(unit, {}).get("MainPID")
            if before["unit_private"].get(unit) and after["unit_private"].get(unit)
            else None
            for unit in reader.UNITS
        }
        result["same_singbox_process"] = before["singbox"].get("process_identity") == after[
            "singbox"
        ].get("process_identity")
        result["on_context_preserved"] = process_ready(before) and process_ready(after)
        result["same_boot"] = before["boot_private"] == after["boot_private"]
        new_pin = pin_token()
        result["pin_record_readable_after"] = new_pin is not None
        result["pin_record_unchanged"] = (
            old_pin is not None and new_pin is not None and old_pin == new_pin
        )
        passed = (
            result.get("selected_count", 0) > 0
            and len(result["cases"]) == result["selected_count"]
            and all(
                case.get("body_ok") is True
                and not case.get("context_changed_or_listener_unconfirmed")
                for case in result["cases"]
            )
            and result["on_context_preserved"]
            and all(result["settings_unchanged"])
            and result["bridge_config_unchanged"]
            and result["same_boot"]
            and result["same_singbox_process"]
            and result["pin_record_unchanged"]
            and all(x is True for x in result["service_pid_same"].values())
        )
        result["marker"] = "BRIDGE_PROBES_PASS" if passed else "BRIDGE_PROBES_RECORDED"
    except Exception as exc:
        result["after_error_class"] = type(exc).__name__
    save(result)
    print(json.dumps(result))
    return 0 if result["marker"] == "BRIDGE_PROBES_PASS" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("STOP_BRIDGE_PROBE", type(exc).__name__)
        raise SystemExit(3) from None
