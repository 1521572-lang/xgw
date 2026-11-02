"""Compare parsed local source views with the applied REALITY contract; no network/tools."""

import base64
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
from pathlib import Path

ROOT = Path("/run/xgw-w3s")
OLD = Path("/run/xgw-w3r")
R_SHA = "38b40524dad5aa76742100cea46b07853b9c9d06940ffc17da3094384bdd59f4"
MAX_SOURCE = 2 * 1024 * 1024
MAX_TOTAL = 8 * 1024 * 1024
spec = importlib.util.spec_from_file_location(
    "single_library", Path(__file__).with_name("wave3_single_bridge.py")
)
single = importlib.util.module_from_spec(spec)
spec.loader.exec_module(single)
diagnostic, bridge, reader = single.diagnostic, single.bridge, single.reader
parsers = importlib.import_module("xgw.parsers.common")
parse_body, parse_links_text = parsers.parse_body, parsers.parse_links_text


def save(name, value):
    fd = os.open(ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def contract(body):
    tls = body.get("tls") or {}
    reality, utls = tls.get("reality") or {}, tls.get("utls") or {}
    return {
        "server": body.get("server"),
        "server_port": body.get("server_port"),
        "uuid": body.get("uuid"),
        "flow": body.get("flow") or "",
        "server_name": tls.get("server_name") or "",
        "tls_enabled": tls.get("enabled") is True,
        "reality_enabled": reality.get("enabled") is True,
        "public_key": reality.get("public_key") or "",
        "short_id": reality.get("short_id") or "",
        "utls_enabled": utls.get("enabled") is True,
        "fingerprint": utls.get("fingerprint") or "",
        "transport": body.get("transport") or {},
    }


def syntax_flags(value):
    key, sid = value["public_key"], value["short_id"]
    key_valid = False
    if isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_-]{43}", key):
        with contextlib.suppress(ValueError):
            key_valid = len(base64.b64decode(key + "=", altchars=b"-_", validate=True)) == 32
    return {
        "public_key_base64url_32_bytes": key_valid,
        "short_id_even_hex_at_most_8_bytes": isinstance(sid, str)
        and len(sid) <= 16
        and len(sid) % 2 == 0
        and re.fullmatch(r"[0-9a-fA-F]*", sid) is not None,
        "server_name_present": isinstance(value["server_name"], str) and bool(value["server_name"]),
        "tls_enabled": value["tls_enabled"],
        "reality_enabled": value["reality_enabled"],
        "utls_enabled": value["utls_enabled"],
    }


def compare_sources(applied, raws):
    actual = contract(applied)
    matches, views = 0, {}
    for item in raws:
        if (
            item.protocol != "vless"
            or item.address != actual["server"]
            or item.port != actual["server_port"]
            or item.credential != actual["uuid"]
        ):
            continue
        matches += 1
        if item.singbox is not None and item.singbox.main.get("type") == "vless":
            view = contract(item.singbox.main)
            views[json.dumps(view, sort_keys=True)] = view
    result = {
        "matching_parsed_source_rows": matches,
        "distinct_parsed_contracts": len(views),
        "source_boundary": "AFTER_PRODUCT_PARSER_NOT_ORIGINAL_WIRE",
        "comparison": "NO_UNIQUE_PARSED_CONTRACT",
    }
    if len(views) == 1:
        expected = next(iter(views.values()))
        equal = {name: actual[name] == expected[name] for name in actual}
        result.update(
            comparison="PARSED_CONTRACT_COMPARED",
            fields_equal=equal,
            all_compared_fields_equal=all(equal.values()),
        )
    return result


def read_source(path):
    # Read private cache bodies without invoking a downloader/Store/cache write method.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o777 != 0o600:
            raise ValueError("private cache metadata")
        if info.st_size > MAX_SOURCE:
            raise ValueError("source limit")
        data = stream.read(MAX_SOURCE + 1)
        if len(data) > MAX_SOURCE:
            raise ValueError("source limit")
    return data


def cached_sources(cfg):
    raws, watched = [], {}
    counters = {
        "configured_sources": len(cfg.subscriptions),
        "sources_read": 0,
        "sources_missing_or_unreadable": 0,
        "sources_parse_errors": 0,
        "sources_with_parser_warnings": 0,
        "coverage_limited": False,
        "manual_links_parsed": False,
    }
    total = 0
    for source in cfg.subscriptions[:32]:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", source.name).strip("._") or "sub"
        stem = safe[:40] + "-" + hashlib.sha256(source.name.encode()).hexdigest()[:8]
        path = reader.PATHS.cache_dir / (stem + ".body")
        try:
            data = read_source(path)
            total += len(data)
            if total > MAX_TOTAL:
                counters["coverage_limited"] = True
                break
            watched[path] = single.digest(data)
            parsed, _, warnings = parse_body(data, source.name)
            counters["sources_read"] += 1
            counters["sources_with_parser_warnings"] += bool(warnings)
            raws.extend(parsed)
        except (OSError, ValueError):
            counters["sources_missing_or_unreadable"] += 1
        except Exception:
            counters["sources_parse_errors"] += 1
        if len(raws) > 5000:
            counters["coverage_limited"] = True
            break
    if len(cfg.subscriptions) > 32:
        counters["coverage_limited"] = True
    manual = "\n".join(cfg.manual.links)
    if manual:
        if len(manual.encode()) <= MAX_SOURCE and len(raws) <= 5000:
            parsed, _, warnings = parse_links_text(manual, "manual")
            raws.extend(parsed)
            counters["manual_links_parsed"] = True
            counters["sources_with_parser_warnings"] += bool(warnings)
        else:
            counters["coverage_limited"] = True
    return raws, watched, counters


def main():
    if os.geteuid() != 0:
        raise ValueError("root required")
    diagnostic.checked(ROOT, True)
    if sys.argv[1] == "show":
        print(diagnostic.checked(ROOT / "summary.json").read_text())
        return 0
    if sys.argv[1] != "run" or any(
        (ROOT / name).exists() or (ROOT / name).is_symlink()
        for name in ("started.json", "summary.json")
    ):
        raise ValueError("already started")
    save("started.json", {"began": True})
    result = {"marker": "STOP_REALITY_CONTRACT", "stage": "BEFORE_CONTEXT", "network_requests": 0}
    before, old_pin, config_digest, watched = None, None, None, {}
    try:
        before, old_pin = reader.snapshot(), bridge.pin_token()
        result["before"] = reader.public(before)
        if not bridge.process_ready(before) or old_pin is None:
            raise ValueError("working context")
        result["stage"] = "R_EVIDENCE"
        diagnostic.checked(OLD, True)
        if single.digest(diagnostic.checked(OLD / "wave3_current_bridge.py").read_bytes()) != R_SHA:
            raise ValueError("R source")
        previous = json.loads(diagnostic.checked(OLD / "summary.json").read_bytes())
        plan = json.loads(diagnostic.checked(OLD / "plan-private.json").read_bytes())
        attempt = previous.get("attempt", {})
        if (
            previous.get("marker") != "CURRENT_BRIDGE_RECORDED"
            or previous.get("request_count") != 1
            or previous.get("all_context_checks_ok") is not True
            or attempt.get("curl_rc") != 97
            or attempt.get("http_status") != 0
            or attempt.get("bytes") != 0
            or previous.get("journal", {})
            .get("related_literal_details", {})
            .get("reality_verification_failed")
            != 1
        ):
            raise ValueError("R shape")
        key = plan.get("case_key")
        if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{8}", key):
            raise ValueError("R key")
        if not isinstance(plan.get("config_sha256"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", plan["config_sha256"]
        ):
            raise ValueError("R config digest")
        result["stage"] = "CURRENT_APPLIED_CONTRACT"
        raw = reader.PATHS.singbox_config_file.read_bytes()
        config_digest = single.digest(raw)
        result["current_config_matches_R_plan"] = config_digest == plan.get("config_sha256")
        result["contract_relation_to_R"] = (
            "CONFIG_DIGEST_MATCHES_R_PLAN"
            if result["current_config_matches_R_plan"]
            else "CURRENT_ONLY_NOT_R_CONTRACT"
        )
        applied = json.loads(raw)
        bridge.bridges(applied)
        bodies = [x for x in applied.get("outbounds", []) if x.get("tag") == "sb-out-" + key + "-d"]
        if len(bodies) != 1 or bodies[0].get("type") != "vless":
            raise ValueError("current candidate")
        result["syntax_flags"] = syntax_flags(contract(bodies[0]))
        result["stage"] = "LOCAL_PARSED_SOURCES"
        cfg, warnings = reader.config.load(reader.PATHS.config_file)
        if warnings:
            raise ValueError("current config warnings")
        raws, watched, counters = cached_sources(cfg)
        result["source_coverage"] = counters
        result["source_comparison"] = compare_sources(bodies[0], raws)
        result["stage"] = "STATIC_CONTRACT_RECORDED"
    except Exception as exc:
        result.update(stop_code="READ_OR_SCHEMA_ERROR", error_class=type(exc).__name__)
    try:
        after, new_pin = reader.snapshot(), bridge.pin_token()
        result["after"] = reader.public(after)
        if before is not None:
            result.update(single.context(before, after, config_digest, old_pin, new_pin))
            if config_digest is None:
                result["bridge_config_unchanged"] = None
        result["cache_inputs_unchanged"] = all(
            single.digest(read_source(path)) == value for path, value in watched.items()
        )
        if not result["cache_inputs_unchanged"]:
            result["stop_code"] = "CACHE_INPUTS_CHANGED"
        elif result.get("all_context_checks_ok") is not True and "stop_code" not in result:
            result["stop_code"] = "AFTER_CONTEXT_UNCONFIRMED"
        if (
            result.get("all_context_checks_ok") is True
            and result["cache_inputs_unchanged"]
            and result.get("stage") == "STATIC_CONTRACT_RECORDED"
            and "stop_code" not in result
        ):
            result["marker"] = "REALITY_CONTRACT_RECORDED"
    except Exception as exc:
        result.update(after_stop_code="AFTER_READ_ERROR", after_error_class=type(exc).__name__)
    save("summary.json", result)
    print(json.dumps(result))
    return 0 if result["marker"] == "REALITY_CONTRACT_RECORDED" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("STOP_REALITY_CONTRACT", "SETUP_ERROR", type(exc).__name__)
        raise SystemExit(3) from None
