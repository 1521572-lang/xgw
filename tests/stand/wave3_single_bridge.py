"""One new SB-1 request with a persisted private identity; no gateway reconfiguration."""

import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/run/xgw-w3p")
OLD = Path("/run/xgw-w3o")
spec = importlib.util.spec_from_file_location(
    "retrospective", Path(__file__).with_name("wave3_bridge_diagnostic.py")
)
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)
bridge, reader = diagnostic.bridge, diagnostic.reader

# These are literal-message classifications, not causes. Unknown messages remain unknown.
DETAILS = {
    "reality_verification_failed": r"reality verification failed",
    "certificate_failure": r"certificate verify failed|certificate verification failed|x509:",
    "tls_alert": r"remote error: tls:|tls alert",
    "handshake_failure": r"handshake (?:failed|failure)|failed to (?:perform|complete).*handshake",
    "permission_failure": r"permission denied|operation not permitted|\beacces\b|\beperm\b",
    "dns_failure": r"no such host|name resolution.*fail|lookup.*(?:failed|timeout|timed out)",
    "timeout": r"timed out|deadline exceeded|i/o timeout",
    "refused": r"connection refused",
    "unreachable": r"network is unreachable|no route to host",
    "reset_or_eof": r"connection reset|broken pipe|unexpected eof|\beof\b",
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save(name, value):
    fd = os.open(ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def selected_from_mapping(mapping, old_summary, n_raw, config_raw):
    if (
        old_summary.get("marker") != "READ_DIAGNOSTIC_RECORDED"
        or old_summary.get("historical_summary_valid") is not True
        or old_summary.get("historical_mapping") != "FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN"
        or mapping.get("mapping_basis") != "FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN"
        or mapping.get("n_summary_sha256") != digest(n_raw)
        or mapping.get("current_config_sha256") != digest(config_raw)
    ):
        raise ValueError("historical mapping unavailable or configuration changed")
    key = mapping.get("case_keys", {}).get("SB-1")
    if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{8}", key):
        raise ValueError("case key missing")
    candidates = [x for x in bridge.bridges(json.loads(config_raw)) if x["key"] == key]
    if len(candidates) != 1 or candidates[0]["protocol"] != "vless":
        raise ValueError("not the mapped bridge")
    return candidates[0]


def error_summary(raw):
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    text = text if isinstance(text, str) else ""
    # curl 8.5.0 lib/socks.c prints the peer reply code in this specific message.
    match = re.search(r"Can't complete SOCKS5 connection to .*\. \(([1-8])\)", text)
    return {
        "message_present": bool(text.strip()),
        "socks5_reply_code": int(match[1]) if match else None,
        "socks_auth_failure_text": bool(
            re.search(r"User was rejected by the SOCKS5 server|No authentication method", text)
        ),
        "details": [key for key, pattern in DETAILS.items() if re.search(pattern, text, re.I)],
    }


def journal_summary(raw, key):
    base = diagnostic.journal_summary(raw, {"SB-1": key})
    details = {name: 0 for name in DETAILS}
    levels = {name: 0 for name in ("error", "warn", "info", "debug", "trace", "fatal", "unknown")}
    pattern = r"(?<![\w-])sb-(?:out|in)-" + re.escape(key) + r"-d(?:-[\w-]+)?(?![\w-])"
    for line in raw.splitlines()[:2000]:
        try:
            message = json.loads(line).get("MESSAGE", "")
            if not isinstance(message, str) or not re.search(pattern, message):
                continue
            # Only a leading logger level (optional ANSI/timestamp), never a word in SNI/URL.
            clean = re.sub(r"\x1b\[[0-9;]*m", "", message)
            level = re.match(
                r"^(?:\+\d{4}\s+\d{4}-\d\d-\d\d\s+\d\d:\d\d:\d\d\s+)?"
                r"(ERROR|WARN|INFO|DEBUG|TRACE|FATAL)\b",
                clean,
            )
            levels[level[1].lower() if level else "unknown"] += 1
            for name, expression in DETAILS.items():
                details[name] += bool(re.search(expression, message, re.I))
        except (ValueError, AttributeError, TypeError):
            pass  # Base parser reports coverage failures separately.
    base.update(related_literal_details=details, related_message_levels=levels)
    return base


def journal(begin, end, key):
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
        return {
            "query_ok": p.returncode == 0,
            "padding_seconds": 2,
            **(journal_summary(p.stdout, key) if p.returncode == 0 else {}),
        }
    except (OSError, subprocess.TimeoutExpired):
        return {"query_ok": False, "padding_seconds": 2}


def context(before, after, config_digest, old_pin, new_pin):
    flags = {
        "on_context_preserved": bridge.process_ready(before) and bridge.process_ready(after),
        "same_singbox_process": before["singbox"].get("process_identity") is not None
        and before["singbox"].get("process_identity") == after["singbox"].get("process_identity"),
        "same_boot": bool(before["boot_private"])
        and before["boot_private"] == after["boot_private"],
        "settings_unchanged": [
            a is not None and a == b
            for a, b in zip(before["hashes_private"], after["hashes_private"], strict=True)
        ],
        "bridge_config_unchanged": config_digest is not None
        and digest(reader.PATHS.singbox_config_file.read_bytes()) == config_digest,
        "pin_record_readable_before_after": [old_pin is not None, new_pin is not None],
        "pin_record_unchanged": old_pin is not None and new_pin is not None and old_pin == new_pin,
        "service_pid_same": {
            unit: before["unit_private"].get(unit, {}).get("MainPID")
            == after["unit_private"].get(unit, {}).get("MainPID")
            if before["unit_private"].get(unit) and after["unit_private"].get(unit)
            else None
            for unit in reader.UNITS
        },
    }
    flags["all_context_checks_ok"] = (
        all(
            flags[name] is True
            for name in (
                "on_context_preserved",
                "same_singbox_process",
                "same_boot",
                "bridge_config_unchanged",
                "pin_record_unchanged",
            )
        )
        and len(flags["settings_unchanged"]) == 3
        and all(flags["settings_unchanged"])
        and len(flags["service_pid_same"]) == 6
        and all(x is True for x in flags["service_pid_same"].values())
    )
    return flags


def request(curl, selected, url):
    # URLs and credentials stay in stdin/memory; no curlrc, direct fallback, redirect or retries.
    payload = (
        "url = "
        + bridge.quoted(url)
        + "\nproxy-user = "
        + bridge.quoted(selected["user"] + ":" + selected["password"])
        + "\n"
    )
    argv = [
        curl,
        "-q",
        "--config",
        "-",
        "--globoff",
        "--socks5-hostname",
        "127.0.0.1:" + str(selected["port"]),
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
        str(bridge.MAX_BODY),
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
        errors = error_summary(p.stderr)
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
            return {
                "outcome": "METADATA_UNKNOWN",
                "curl_rc": p.returncode,
                "body_ok": False,
                "error": errors,
            }
        identity = encoding.strip().lower() in (b"", b"identity")
        passed = (
            p.returncode == 0
            and code in (200, 206)
            and bridge.MIN_BODY <= size <= bridge.MAX_BODY
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
            "error": errors,
        }
    except subprocess.TimeoutExpired:
        return {"outcome": "WORKER_TIMEOUT", "body_ok": False}
    except (OSError, ValueError, AttributeError, TypeError):
        return {"outcome": "WORKER_OR_METADATA_ERROR", "body_ok": False}


def main():
    if os.geteuid() != 0:
        raise ValueError("root required")
    diagnostic.checked(ROOT, True)
    if sys.argv[1] == "show":
        print(diagnostic.checked(ROOT / "summary.json").read_text())
        return 0
    if sys.argv[1] != "run" or any(
        (ROOT / name).exists() or (ROOT / name).is_symlink()
        for name in ("started.json", "plan-private.json", "summary.json")
    ):
        raise ValueError("invalid or already started; never retry")
    save("started.json", {"realtime": time.time(), "monotonic": time.monotonic()})
    result = {"marker": "STOP_SINGLE_PROBE", "case": "SB-1", "request_count": 0}
    before, old_pin, config_digest = None, None, None
    try:
        before, old_pin = reader.snapshot(), bridge.pin_token()
        result["before"] = reader.public(before)
        if not bridge.process_ready(before) or old_pin is None:
            raise ValueError("working context unknown")
        diagnostic.checked(OLD, True)
        summary_raw = diagnostic.checked(OLD / "summary.json").read_bytes()
        mapping_raw = diagnostic.checked(OLD / "mapping-private.json").read_bytes()
        diagnostic.checked(diagnostic.OLD, True)
        n_raw = diagnostic.checked(diagnostic.OLD / "summary.json").read_bytes()
        if (
            digest(diagnostic.checked(diagnostic.OLD / "wave3_bridge_probe.py").read_bytes())
            != diagnostic.N_SHA
        ):
            raise ValueError("old N helper changed")
        diagnostic.historical(json.loads(n_raw))
        raw = reader.PATHS.singbox_config_file.read_bytes()
        config_digest = digest(raw)
        selected = selected_from_mapping(
            json.loads(mapping_raw), json.loads(summary_raw), n_raw, raw
        )
        if bridge.mark_keys(json.loads(raw)) != 0:
            raise ValueError("routing marks present")
        cfg, warnings = reader.config.load(reader.PATHS.config_file)
        urls = bridge.targets(cfg)
        if warnings or not urls:
            raise ValueError("no configured HTTPS target")
        curl = shutil.which("curl")
        if not curl:
            raise ValueError("no curl")
        p = subprocess.run([curl, "-q", "--version"], capture_output=True, timeout=3, check=False)
        match = re.match(rb"curl (\d+)\.(\d+)\.(\d+)", p.stdout)
        if p.returncode or not match or tuple(int(x) for x in match.groups()) < (8, 4, 0):
            raise ValueError("curl version unknown or below 8.4")
        result["curl_version"] = ".".join(x.decode() for x in match.groups())
        result["historical_mapping_basis"] = "FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN"
        result["current_config_matches_O_digest"] = True
        result["current_config"] = diagnostic.endpoint_summary(json.loads(raw), selected["key"])
        pid = before["singbox"]["process_identity"][0]
        save(
            "plan-private.json",
            {
                "case_key": selected["key"],
                "config_sha256": config_digest,
                "target_sha256": digest(urls[0].encode()),
                "target_index": 1,
                "process_identity": before["singbox"]["process_identity"],
                "service_identity": before["unit_private"],
                "boot": before["boot_private"],
                "O_summary_sha256": digest(summary_raw),
                "O_mapping_sha256": digest(mapping_raw),
                "realtime": time.time(),
                "monotonic": time.monotonic(),
            },
        )
        result["private_plan_persisted_before_request"] = True
        result["listener_owned_before"] = bridge.owns_listener(pid, selected["port"])
        pre = reader.snapshot()
        if (
            not result["listener_owned_before"]
            or reader.enabled() is not True
            or digest(reader.PATHS.singbox_config_file.read_bytes()) != config_digest
            or not bridge.process_ready(pre)
            or pre["singbox"].get("process_identity") != before["singbox"]["process_identity"]
            or pre["hashes_private"] != before["hashes_private"]
            or pre["boot_private"] != before["boot_private"]
        ):
            raise ValueError("pre-request context changed")
        # Exactly one call. No fallback target, no retry or second bridge.
        begin, mono = time.time(), time.monotonic()
        result["request_count"] = 1
        result["attempt"] = request(curl, selected, urls[0])
        end, elapsed = time.time(), time.monotonic() - mono
        result["request_window"] = {
            "begin_realtime": begin,
            "end_realtime": end,
            "elapsed_monotonic_seconds": round(elapsed, 6),
            "clock_basis_compatible": end >= begin and abs((end - begin) - elapsed) <= 1,
        }
        result["listener_owned_after"] = bridge.owns_listener(pid, selected["port"])
        result["journal"] = (
            journal(begin, end, selected["key"])
            if result["request_window"]["clock_basis_compatible"]
            else {"query_ok": False, "blocked_clock_basis": True}
        )
    except Exception as exc:
        result["collection_error_class"] = type(exc).__name__
    try:
        after, new_pin = reader.snapshot(), bridge.pin_token()
        result["after"] = reader.public(after)
        if before is not None:
            result.update(context(before, after, config_digest, old_pin, new_pin))
        complete = (
            result.get("all_context_checks_ok") is True
            and result["request_count"] == 1
            and "attempt" in result
            and result.get("listener_owned_before") is True
            and result.get("listener_owned_after") is True
            and "collection_error_class" not in result
        )
        result["marker"] = "SINGLE_PROBE_RECORDED" if complete else "STOP_SINGLE_PROBE"
    except Exception as exc:
        result["after_read_error_class"] = type(exc).__name__
    save("summary.json", result)
    print(json.dumps(result))
    return 0 if result["marker"] == "SINGLE_PROBE_RECORDED" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("STOP_SINGLE_PROBE", type(exc).__name__)
        raise SystemExit(3) from None
