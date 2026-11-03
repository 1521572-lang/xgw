"""Expanded local source coverage and configuration-generation diagnosis; no network changes."""

import base64
import importlib.util
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/run/xgw-w3u")
OLD = Path("/run/xgw-w3t")
T_SHA = "9e467188bf5f7d6e7161184324a81b5028f10572cd2b8ace06510d28ad3716fb"
spec = importlib.util.spec_from_file_location(
    "previous_batch", Path(__file__).with_name("wave3_extended_batch.py")
)
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)
source, single, diagnostic, bridge, reader = (
    batch.source,
    batch.single,
    batch.diagnostic,
    batch.bridge,
    batch.reader,
)


def write(name, value, replace=False):
    batch.ROOT = ROOT
    batch.write(name, value, replace)


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("JSON_DUPLICATE_KEYS")
        result[name] = value
    return result


def expanded_records(data):
    text = data.decode("utf-8-sig").strip()
    carrier = "PLAIN"
    if not text.startswith(("{", "[")) and "://" not in text:
        compact = "".join(text.split()).replace("-", "+").replace("_", "/")
        text = (
            base64.b64decode(compact + "=" * (-len(compact) % 4), validate=True)
            .decode("utf-8-sig")
            .strip()
        )
        carrier = "BASE64"
    meta = {
        "carrier": carrier,
        "config_containers": 0,
        "visited_items": 0,
        "candidate_records": 0,
        "ignored_non_vless_or_service": 0,
        "unknown_containers": 0,
        "coverage_limited": False,
        "unsupported_reason_counts": {},
    }
    leaves = []

    def walk(value, depth=0):
        if depth > 6 or meta["visited_items"] >= 20000 or len(leaves) >= 5000:
            meta["coverage_limited"] = True
            return
        meta["visited_items"] += 1
        if isinstance(value, list):
            for child in value:
                walk(child, depth + 1)
        elif isinstance(value, dict):
            if "outbounds" in value or "endpoints" in value:
                meta["config_containers"] += 1
                for key in ("outbounds", "endpoints"):
                    if key in value:
                        if isinstance(value[key], list):
                            walk(value[key], depth + 1)
                        else:
                            meta["unknown_containers"] += 1
            elif "protocol" in value or "type" in value:
                leaves.append(value)
            else:
                meta["unknown_containers"] += 1
        elif isinstance(value, str):
            leaves.append(value)
        else:
            meta["unknown_containers"] += 1

    if text.startswith(("{", "[")):
        meta["carrier"] += "_JSON"
        walk(json.loads(text, object_pairs_hook=unique_object))
    else:
        meta["carrier"] += "_LINKS"
        walk(
            [
                line.strip()
                for line in text.splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
        )
    records = []
    reasons = {
        "duplicate query keys": "DUPLICATE_QUERY_KEYS",
        "unsupported transport": "UNSUPPORTED_URI_TRANSPORT",
        "unsupported credential": "UNSUPPORTED_URI_CREDENTIAL",
        "unsupported security": "UNSUPPORTED_URI_SECURITY",
        "missing identity": "MISSING_URI_IDENTITY",
        "unsupported native transport or chain": "UNSUPPORTED_SB_TRANSPORT_OR_CHAIN",
        "unsupported Xray transport or chain": "UNSUPPORTED_XRAY_TRANSPORT_OR_CHAIN",
        "unsupported Xray header": "UNSUPPORTED_XRAY_HEADER",
        "multiple servers": "MULTIPLE_SERVERS",
        "multiple users": "MULTIPLE_USERS",
        "unsupported Xray security": "UNSUPPORTED_XRAY_SECURITY",
        "unsupported extra verification": "UNSUPPORTED_EXTRA_VERIFICATION",
    }
    for leaf in leaves:
        meta["candidate_records"] += 1
        try:
            record = batch.independent_record(leaf)
            if record is None:
                meta["ignored_non_vless_or_service"] += 1
            else:
                records.append(record)
        except Exception as exc:
            code = reasons.get(str(exc), "SCHEMA_OR_URL_PARSE_ERROR")
            meta["unsupported_reason_counts"][code] = (
                meta["unsupported_reason_counts"].get(code, 0) + 1
            )
    meta["supported_records"] = len(records)
    try:
        legacy, _ = batch.source_records(data)
        meta["legacy_T_supported_on_same_bytes"] = len(legacy)
    except Exception:
        meta["legacy_T_supported_on_same_bytes"] = None
    return records, meta


def read_sources(cfg):
    rows, watched, reports, total = [], {}, [], 0
    for sub in cfg.subscriptions[:32]:
        name = re.sub(r"[^A-Za-z0-9_.-]+", "_", sub.name).strip("._") or "sub"
        stem = name[:40] + "-" + source.hashlib.sha256(sub.name.encode()).hexdigest()[:8]
        path = reader.PATHS.cache_dir / (stem + ".body")
        try:
            data = source.read_source(path)
            total += len(data)
            if total > source.MAX_TOTAL:
                reports.append({"outcome": "TOTAL_LIMIT"})
                break
            watched[path] = single.digest(data)
            found, meta = expanded_records(data)
            rows.extend(found)
            reports.append({"outcome": "READ", **meta})
        except Exception as exc:
            reports.append(
                {"outcome": "UNAVAILABLE_OR_UNSUPPORTED", "error_class": type(exc).__name__}
            )
    manual = "\n".join(cfg.manual.links).encode()
    if manual:
        try:
            if len(manual) > source.MAX_SOURCE:
                raise ValueError("manual limit")
            found, meta = expanded_records(manual)
            rows.extend(found)
            reports.append({"outcome": "MANUAL", **meta})
        except Exception as exc:
            reports.append({"outcome": "MANUAL_UNSUPPORTED", "error_class": type(exc).__name__})
    return (
        rows,
        watched,
        {
            "configured_sources": len(cfg.subscriptions),
            "source_limit_hit": len(cfg.subscriptions) > 32,
            "anonymous_source_reports": reports,
            "supported_records": len(rows),
            "parser_boundary": (
                "INDEPENDENT_CONTAINER_WALK_AND_TCP_VLESS_EXTRACTION_NO_PRODUCT_PARSER"
            ),
            "default_fp_convention": "ABSENT_FP_USES_PRODUCT_CHROME_CONVENTION",
        },
    )


def audit_T_samples(value, reported=(35774669, 924284684)):
    samples = value.get("phases", {}).get("T7_passive_LAN", {}).get("data", {}).get("samples", [])
    result = {
        "sample_count": len(samples),
        "scope": "CUMULATIVE_FROM_T_START_DO_NOT_SUM_AS_TRAFFIC",
    }
    for field, stated in zip(("LAN_rx_bytes_delta", "LAN_tx_bytes_delta"), reported, strict=True):
        values = [s.get(field) for s in samples]
        last = values[-1] if values and type(values[-1]) is int else None
        total = sum(values) if values and all(type(x) is int for x in values) else None
        result[field] = {
            "last_cumulative_value": last,
            "sum_of_cumulative_values_NOT_total_traffic": total,
            "reported_table_matches_last": stated == last if last is not None else None,
            "reported_table_matches_sum": stated == total if total is not None else None,
        }
    return result


def semantic_difference(current, other):
    def indexed(value, field):
        return {
            item.get("tag"): item
            for item in value.get(field, [])
            if isinstance(item, dict) and isinstance(item.get("tag"), str)
        }

    left, right = {}, {}
    for field in ("outbounds", "endpoints"):
        left.update(indexed(current, field))
        right.update(indexed(other, field))
    shared = left.keys() & right.keys()
    lin, rin = indexed(current, "inbounds"), indexed(other, "inbounds")
    both = lin.keys() & rin.keys()
    return {
        "json_values_equal": current == other,
        "endpoint_tags_added_in_current": len(left.keys() - right.keys()),
        "endpoint_tags_removed_in_current": len(right.keys() - left.keys()),
        "shared_endpoint_objects_changed": sum(left[k] != right[k] for k in shared),
        "inbound_tags_added_in_current": len(lin.keys() - rin.keys()),
        "inbound_tags_removed_in_current": len(rin.keys() - lin.keys()),
        "shared_bridge_ports_changed": sum(
            lin[k].get("listen_port") != rin[k].get("listen_port") for k in both
        ),
        "shared_bridge_user_objects_changed": sum(
            lin[k].get("users") != rin[k].get("users") for k in both
        ),
        "dns_changed": current.get("dns") != other.get("dns"),
        "route_changed": current.get("route") != other.get("route"),
        "experimental_changed": current.get("experimental") != other.get("experimental"),
        "log_changed": current.get("log") != other.get("log"),
    }


def read_config(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not source.stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_mode & 0o007
            or info.st_size > 8 * 1024 * 1024
        ):
            raise ValueError("config metadata")
        raw = stream.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError("config size")
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError("config shape")
    return raw, value


def generation_summary(current_raw, current, oldbase, watched):
    result = {
        "current_matches_T_digest": single.digest(current_raw) == oldbase.get("sb_config_sha256")
        if oldbase
        else None,
        "writer_identity": "NOT_ATTRIBUTED_BY_FILE_METADATA",
    }
    for label, path in (
        ("last_good", reader.PATHS.singbox_last_good_file),
        ("pending", reader.PATHS.singbox_pending_file),
    ):
        try:
            raw, value = read_config(path)
            watched[path] = single.digest(raw)
            result[label] = {
                "available": True,
                "matches_T_digest": single.digest(raw) == oldbase.get("sb_config_sha256")
                if oldbase
                else None,
                "bytes_equal_current": raw == current_raw,
                "difference_current_vs_file": semantic_difference(current, value),
            }
        except FileNotFoundError:
            result[label] = {"available": False, "reason": "ABSENT"}
        except Exception as exc:
            result[label] = {
                "available": False,
                "reason": "UNREADABLE_OR_INVALID",
                "error_class": type(exc).__name__,
            }
    return result


def keyed_health(sb, reference):
    conn = None
    try:
        candidates = bridge.bridges(sb)
        conn = sqlite3.connect(reader.PATHS.db_file.as_uri() + "?mode=ro", uri=True, timeout=0.5)
        rows = conn.execute(
            "SELECT n.fingerprint,n.tag,s.verdict,s.bytes,s.seconds,s.ts "
            "FROM nodes n LEFT JOIN scans s "
            "ON s.probe_tag=('probe'||substr(n.tag,instr(n.tag,'-'))) LIMIT 5001"
        ).fetchall()
        result = {
            "query_ok": True,
            "rows": len(rows),
            "truncated": len(rows) > 5000,
            "default_bridges": len(candidates),
            "unique_current_node_rows": 0,
            "missing_or_ambiguous_nodes": 0,
            "mapped_scans": 0,
            "missing_or_unconfirmed_scans": 0,
            "scan_core_identity": "UNSPECIFIED_IN_SCHEMA",
            "reference_case": {"outcome": "NOT_AVAILABLE"},
        }
        now = time.time()
        for item in candidates:
            found = [row for row in rows[:5000] if row[0] == item["key"]]
            if len(found) != 1:
                result["missing_or_ambiguous_nodes"] += 1
                continue
            result["unique_current_node_rows"] += 1
            fp, tag, verdict, size, seconds, stamp = found[0]
            match = re.fullmatch(r"(?:proxy|spare|probe)-[a-z]{2}-([0-9a-f]{4,8})", tag or "")
            if not match or not fp.startswith(match[1]) or verdict is None:
                result["missing_or_unconfirmed_scans"] += 1
                continue
            result["mapped_scans"] += 1
            if item["key"] == reference:
                result["reference_case"] = {
                    "outcome": "PERSISTED_SCAN_MAPPED_TO_CURRENT_NODE",
                    "verdict": verdict if verdict in diagnostic.VERDICTS else "OTHER",
                    "bytes": size if type(size) is int and size >= 0 else None,
                    "seconds": seconds
                    if type(seconds) in (int, float) and math.isfinite(seconds) and seconds >= 0
                    else None,
                    "age_seconds": round(now - stamp, 3)
                    if type(stamp) in (int, float) and math.isfinite(stamp)
                    else None,
                    "scan_core_identity": "UNSPECIFIED_IN_SCHEMA",
                    "fresh_active_check": False,
                }
        return result
    except Exception as exc:
        return {"query_ok": False, "error_class": type(exc).__name__}
    finally:
        if conn is not None:
            conn.close()


def effective_units():
    result = {}
    fields = (
        "User",
        "Group",
        "AmbientCapabilities",
        "CapabilityBoundingSet",
        "NoNewPrivileges",
        "ProtectSystem",
        "ProtectHome",
        "PrivateTmp",
        "ReadOnlyPaths",
        "ReadWritePaths",
        "RestrictSUIDSGID",
        "RestrictRealtime",
        "LockPersonality",
        "RestrictAddressFamilies",
    )
    for unit, role, user in (
        ("xgw-singbox", "SINGBOX", "xgw-singbox"),
        ("xgw-xray", "XRAY", "xray"),
    ):
        try:
            p = subprocess.run(
                ["systemctl", "show", unit, "--no-pager", *["--property=" + f for f in fields]],
                capture_output=True,
                timeout=3,
                check=False,
            )
            if p.returncode:
                result[role] = {"query_ok": False}
                continue
            values = dict(
                line.split("=", 1)
                for line in p.stdout.decode(errors="replace").splitlines()
                if "=" in line
            )
            caps = set() if role == "SINGBOX" else {"cap_net_admin", "cap_net_bind_service"}
            result[role] = {
                "query_ok": True,
                "properties_seen": len(set(values) & set(fields)),
                "user_expected": values.get("User") == user,
                "group_expected": values.get("Group") == user,
                "ambient_caps_expected": set(
                    values.get("AmbientCapabilities", "MISSING").lower().split()
                )
                == caps,
                "bounding_caps_expected": set(
                    values.get("CapabilityBoundingSet", "MISSING").lower().split()
                )
                == caps,
                "no_new_privileges": values.get("NoNewPrivileges") == "yes",
                "protect_system_strict": values.get("ProtectSystem") == "strict",
                "protect_home": values.get("ProtectHome") in ("yes", "true"),
                "private_tmp": values.get("PrivateTmp") in ("yes", "true"),
                "run_explicit_read_only": "/run" in values.get("ReadOnlyPaths", "").split(),
                "read_write_paths_empty": values.get("ReadWritePaths") == "",
                "restrict_suid_sgid": values.get("RestrictSUIDSGID") == "yes",
                "restrict_realtime": values.get("RestrictRealtime") == "yes",
                "lock_personality": values.get("LockPersonality") == "yes",
                "address_families_expected": set(
                    values.get("RestrictAddressFamilies", "").upper().split()
                )
                == {"AF_UNIX", "AF_NETLINK", "AF_INET", "AF_INET6"},
            }
        except Exception as exc:
            result[role] = {"query_ok": False, "error_class": type(exc).__name__}
    return result


def writer_journal():
    patterns = {
        "unchanged": "sing-box: изменений нет",
        "deferred": "перечитывание отложено",
        "started": "sing-box запущен",
        "reloaded": "конфиг sing-box перечитан",
        "rejected": "конфиг sing-box отклонён",
        "rollback": "откат на last-good",
        "systemd_reload_word": r"\bReload(?:ing|ed)\b",
    }
    now = time.time()
    try:
        p = subprocess.run(
            [
                "journalctl",
                "-u",
                "xgw",
                "-u",
                "xgw-singbox",
                "--since",
                "@" + str(now - 86400),
                "--until",
                "@" + str(now),
                "-n",
                "3001",
                "-o",
                "json",
                "--no-pager",
            ],
            capture_output=True,
            timeout=3,
            check=False,
        )
        if p.returncode:
            return {"query_ok": False}
        lines = p.stdout.splitlines()
        result = {
            "query_ok": True,
            "rows": len(lines),
            "truncated": len(lines) > 3000,
            "parse_errors": 0,
            "window_seconds": 86400,
            "literal_counts": dict.fromkeys(patterns, 0),
            "scope": "WORD_COUNTS_NOT_WRITER_OR_CAUSE_PROOF",
        }
        for line in lines[:3000]:
            try:
                message = json.loads(line).get("MESSAGE")
                if not isinstance(message, str):
                    raise ValueError
                for name, pattern in patterns.items():
                    result["literal_counts"][name] += bool(re.search(pattern, message))
            except Exception:
                result["parse_errors"] += 1
        return result
    except Exception as exc:
        return {"query_ok": False, "error_class": type(exc).__name__}


def worker():
    write("worker-claimed.json", {"claimed": True})
    result = {
        "marker": "COVERAGE_BATCH_PARTIAL",
        "network_requests": 0,
        "phases": {},
        "executor_scope": "THINKCENTRE_ONLY_CONFIRMED_BY_OWNER",
        "not_run": [
            "active_health",
            "client_LAN_UDP_IPv6_DNS",
            "performance",
            "faults",
            "D1_on_install",
            "E4_packet_attribution",
            "all_Tailscale_paths",
        ],
    }
    before, pin, sb_raw, xr_raw, watched, generations, oldbase, reference = (
        None,
        None,
        None,
        None,
        {},
        {},
        {},
        None,
    )
    start = time.monotonic()

    def phase(name, fn):
        write("progress.json", {"stage": name, "completed": list(result["phases"])}, True)
        try:
            result["phases"][name] = {"collection": "RECORDED", "data": fn()}
        except Exception as exc:
            result["phases"][name] = {
                "collection": "UNAVAILABLE",
                "error_class": type(exc).__name__,
            }
        write("partial.json", result, True)

    try:
        before, pin = reader.snapshot(), bridge.pin_token()
        result["before"] = reader.public(before)
        if not bridge.process_ready(before) or pin is None:
            raise ValueError("working context")
        sb_raw, sb = read_config(reader.PATHS.singbox_config_file)
        xr_raw, xr = read_config(reader.PATHS.xray_config_file)

        def history():
            nonlocal oldbase, reference
            diagnostic.checked(OLD, True)
            if (
                single.digest(diagnostic.checked(OLD / "wave3_extended_batch.py").read_bytes())
                != T_SHA
            ):
                raise ValueError("T source")
            previous = json.loads(diagnostic.checked(OLD / "summary.json").read_bytes())
            if (
                previous.get("marker") != "EXTENDED_BATCH_RECORDED"
                or previous.get("all_context_checks_ok") is not True
            ):
                raise ValueError("T shape")
            candidate = json.loads(diagnostic.checked(OLD / "baseline-private.json").read_bytes())
            if not isinstance(candidate, dict) or not isinstance(
                candidate.get("source_digests"), dict
            ):
                raise ValueError("T baseline shape")
            oldbase = candidate
            key = oldbase.get("reference_case_key")
            reference = key if isinstance(key, str) and re.fullmatch(r"[0-9a-f]{8}", key) else None
            return {
                "T_scope_accepted": True,
                "T_counter_aggregation_audit": audit_T_samples(previous),
                "current_sb_matches_T": single.digest(sb_raw) == oldbase.get("sb_config_sha256"),
                "current_xray_matches_T": single.digest(xr_raw)
                == oldbase.get("xray_config_sha256"),
                "reference_key_available": reference is not None,
            }

        phase("U1_T_evidence", history)
        records = []

        def sources():
            nonlocal records, watched
            cfg, warnings = reader.config.load(reader.PATHS.config_file)
            if warnings:
                raise ValueError("configuration warnings")
            records, watched, info = read_sources(cfg)
            previous = oldbase.get("source_digests", {})
            info["same_cache_digests_as_T"] = (
                bool(watched) and {str(p): v for p, v in watched.items()} == previous
                if oldbase
                else None
            )
            return info

        phase("U2_expanded_independent_sources", sources)
        write(
            "baseline-private.json",
            {
                "sb_config_sha256": single.digest(sb_raw),
                "xray_config_sha256": single.digest(xr_raw),
                "source_digests": {str(p): v for p, v in watched.items()},
                "reference_case_key": reference,
                "boot": before["boot_private"],
                "process_identity": before["singbox"].get("process_identity"),
            },
        )

        def contracts():
            counts = {"default_vless": 0, "equal": 0, "mismatched": 0, "no_unique_record": 0}
            case = {"outcome": "REFERENCE_UNAVAILABLE"}
            for item in sb.get("outbounds", []):
                if item.get("type") != "vless" or not re.fullmatch(
                    r"sb-out-[0-9a-f]{8}-d", str(item.get("tag", ""))
                ):
                    continue
                counts["default_vless"] += 1
                row = batch.compare_record(source.contract(item), records)
                counts[
                    "no_unique_record"
                    if row["outcome"] != "COMPARED"
                    else "equal"
                    if row["all_fields_equal"]
                    else "mismatched"
                ] += 1
                if reference and item["tag"] == "sb-out-" + reference + "-d":
                    case = row
            return {
                "counts": counts,
                "reference_case": case,
                "scope": "SUPPORTED_CURRENT_SOURCE_RECORDS_NOT_HEALTH",
            }

        phase("U3_all_default_contracts", contracts)
        phase("U4_current_all_profile_graph", lambda: batch.whole_graph(sb, xr))
        phase(
            "U5_local_config_generations",
            lambda: generation_summary(sb_raw, sb, oldbase, generations),
        )
        phase("U6_keyed_persisted_health", lambda: keyed_health(sb, reference))
        phase("U7_effective_unit_properties", effective_units)
        phase("U8_writer_journal_counts", writer_journal)
    except Exception as exc:
        result.update(global_stop="BASELINE_UNAVAILABLE", error_class=type(exc).__name__)
    try:
        after, newpin = reader.snapshot(), bridge.pin_token()
        result["after"] = reader.public(after)
        if before is not None:
            result.update(
                single.context(
                    before, after, single.digest(sb_raw) if sb_raw else None, pin, newpin
                )
            )
            if sb_raw is None:
                result["bridge_config_unchanged"] = None
        result["xray_config_unchanged"] = (
            xr_raw is not None and read_config(reader.PATHS.xray_config_file)[0] == xr_raw
        )
        result["cache_inputs_unchanged"] = all(
            single.digest(source.read_source(p)) == v for p, v in watched.items()
        )
        result["local_generation_files_unchanged"] = all(
            single.digest(read_config(p)[0]) == v for p, v in generations.items()
        )
        if (
            len(result["phases"]) == 8
            and all(v["collection"] == "RECORDED" for v in result["phases"].values())
            and result.get("all_context_checks_ok") is True
            and result["xray_config_unchanged"]
            and result["cache_inputs_unchanged"]
            and result["local_generation_files_unchanged"]
        ):
            result["marker"] = "COVERAGE_BATCH_RECORDED"
    except Exception as exc:
        result.update(
            after_stop="AFTER_CONTEXT_OR_INPUT_CHANGED", after_error_class=type(exc).__name__
        )
    result["elapsed_seconds"] = round(time.monotonic() - start, 3)
    write("summary.json", result)
    write(
        "progress.json",
        {"stage": "FINISHED", "marker": result["marker"], "summary_available": True},
        True,
    )


def main():
    if os.geteuid() != 0:
        raise ValueError("root required")
    diagnostic.checked(ROOT, True)
    mode = sys.argv[1]
    if mode in ("status", "show"):
        names = (
            ("summary.json", "partial.json", "progress.json")
            if mode == "show"
            else ("summary.json", "progress.json")
        )
        for name in names:
            if (ROOT / name).exists():
                print(
                    json.dumps(
                        {
                            "file": name,
                            "data": json.loads(diagnostic.checked(ROOT / name).read_text()),
                        }
                    )
                )
                return 0
        print("BATCH_STATUS_NOT_AVAILABLE")
        return 3
    if mode == "_worker":
        diagnostic.checked(ROOT / "started.json")
        worker()
        return 0
    if mode != "start" or any(
        (ROOT / n).exists() or (ROOT / n).is_symlink()
        for n in ("started.json", "worker-claimed.json", "summary.json")
    ):
        raise ValueError("already started or invalid mode")
    write("started.json", {"start_realtime": time.time()})
    write("progress.json", {"stage": "LAUNCHING", "summary_available": False}, True)
    try:
        subprocess.Popen(
            [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "_worker"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        write(
            "summary.json",
            {
                "marker": "COVERAGE_BATCH_PARTIAL",
                "launch_error_class": type(exc).__name__,
                "network_requests": 0,
            },
        )
        return 3
    print("COVERAGE_BATCH_STARTED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("STOP_COVERAGE_BATCH", type(exc).__name__)
        raise SystemExit(3) from None
