"""One unattended, read-only batch: source records, whole bridge graph, history and LAN counters."""

import base64
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

ROOT = Path("/run/xgw-w3t")
S_ROOT = Path("/run/xgw-w3s")
R_ROOT = Path("/run/xgw-w3r")
S_SHA = "3fbc8fddbb298ed95c9584ec01657a27eba915897b151ccbb657d6c025f1875c"
INTERVAL = 30
SAMPLES = 12
spec = importlib.util.spec_from_file_location(
    "source_library", Path(__file__).with_name("wave3_reality_contract.py")
)
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)
single, diagnostic, bridge, reader = source.single, source.diagnostic, source.bridge, source.reader


def write(name, value, replace=False):
    target = ROOT / (name + ".part" if replace else name)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    if replace:
        os.replace(target, ROOT / name)


def independent_record(item):
    """Only explicitly supported TCP VLESS records; never calls XGW parsers/converters."""
    if isinstance(item, str):
        p = urlsplit(item)
        if p.scheme != "vless":
            return None
        pairs = parse_qsl(p.query, keep_blank_values=True)
        keys = [name for name, _ in pairs]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate query keys")
        q = dict(pairs)
        if q.get("type", "tcp") not in ("tcp", "raw") or q.get("headerType", "none") != "none":
            raise ValueError("unsupported transport")
        if q.get("encryption", "none") not in ("", "none") or p.password is not None:
            raise ValueError("unsupported credential")
        sec = q.get("security") or ("reality" if q.get("pbk") else "none")
        if sec not in ("none", "tls", "reality"):
            raise ValueError("unsupported security")
        host, port, user = p.hostname, p.port, unquote(p.username or "")
        if not host or not port or not user:
            raise ValueError("missing identity")
        enabled = sec in ("tls", "reality")
        return {
            "server": host,
            "server_port": port,
            "uuid": user,
            "flow": q.get("flow", ""),
            "server_name": q.get("sni", "") if enabled else "",
            "tls_enabled": enabled,
            "reality_enabled": sec == "reality",
            "public_key": q.get("pbk", "") if sec == "reality" else "",
            "short_id": q.get("sid", "") if sec == "reality" else "",
            "utls_enabled": enabled,
            "fingerprint": (q.get("fp") or "chrome") if enabled else "",
            "transport": {},
        }
    if not isinstance(item, dict):
        return None
    if item.get("type") == "vless":
        if item.get("transport") or item.get("detour"):
            raise ValueError("unsupported native transport or chain")
        return source.contract(item)
    if item.get("protocol") != "vless":
        return None
    stream = item.get("streamSettings") or {}
    if stream.get("network", "tcp") not in ("tcp", "raw") or (stream.get("sockopt") or {}).get(
        "dialerProxy"
    ):
        raise ValueError("unsupported Xray transport or chain")
    header = (stream.get("tcpSettings") or {}).get("header") or {}
    if header.get("type", "none") != "none":
        raise ValueError("unsupported Xray header")
    settings = item.get("settings") or {}
    servers = settings.get("vnext") or settings.get("servers") or [settings]
    if len(servers) != 1:
        raise ValueError("multiple servers")
    server = servers[0]
    users = server.get("users") or [server]
    if len(users) != 1:
        raise ValueError("multiple users")
    user = users[0]
    sec = stream.get("security", "none")
    if sec not in ("none", "tls", "reality"):
        raise ValueError("unsupported Xray security")
    tls = stream.get("realitySettings" if sec == "reality" else "tlsSettings") or {}
    if tls.get("mldsa65Verify"):
        raise ValueError("unsupported extra verification")
    enabled = sec in ("tls", "reality")
    return {
        "server": server.get("address"),
        "server_port": int(server.get("port", 0)),
        "uuid": user.get("id"),
        "flow": user.get("flow") or "",
        "server_name": tls.get("serverName") or "",
        "tls_enabled": enabled,
        "reality_enabled": sec == "reality",
        "public_key": tls.get("publicKey") or "",
        "short_id": tls.get("shortId") or "",
        "utls_enabled": enabled,
        "fingerprint": tls.get("fingerprint") or ("chrome" if enabled else ""),
        "transport": {},
    }


def source_records(data):
    text = data.decode("utf-8-sig").strip()
    carrier = "PLAIN"
    if not text.startswith(("{", "[")) and "://" not in text:
        compact = "".join(text.split()).replace("-", "+").replace("_", "/")
        text = base64.b64decode(compact + "=" * (-len(compact) % 4), validate=True).decode(
            "utf-8-sig"
        )
        carrier = "BASE64"
    if text.lstrip().startswith(("{", "[")):
        root = json.loads(text)
        items = root if isinstance(root, list) else root.get("outbounds", [root])
        carrier += "_JSON"
    else:
        items = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        carrier += "_LINKS"
    if not isinstance(items, list):
        raise ValueError("unsupported container")
    records, rejected = [], 0
    for item in items[:5000]:
        try:
            row = independent_record(item)
            if row is not None:
                records.append(row)
        except (ValueError, TypeError, KeyError, AttributeError):
            rejected += 1
    return records, {
        "carrier": carrier,
        "supported_records": len(records),
        "unsupported_or_ambiguous": rejected,
        "record_limit_hit": len(items) > 5000,
    }


def compare_record(actual, records):
    matched = [
        row
        for row in records
        if all(row.get(k) == actual.get(k) for k in ("server", "server_port", "uuid"))
    ]
    unique = {json.dumps(row, sort_keys=True): row for row in matched}
    result = {
        "matching_records": len(matched),
        "distinct_contracts": len(unique),
        "outcome": "NO_UNIQUE_SUPPORTED_RECORD",
    }
    if len(unique) == 1:
        expected = next(iter(unique.values()))
        equal = {name: actual[name] == expected.get(name) for name in actual}
        result.update(outcome="COMPARED", fields_equal=equal, all_fields_equal=all(equal.values()))
    return result


def read_records(cfg):
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
            found, report = source_records(data)
            rows.extend(found)
            reports.append({"outcome": "READ", **report})
        except Exception as exc:
            reports.append(
                {"outcome": "UNAVAILABLE_OR_UNSUPPORTED", "error_class": type(exc).__name__}
            )
    manual = "\n".join(cfg.manual.links).encode()
    if manual:
        if len(manual) <= source.MAX_SOURCE:
            try:
                found, report = source_records(manual)
                rows.extend(found)
                reports.append({"outcome": "MANUAL", **report})
            except Exception as exc:
                reports.append({"outcome": "MANUAL_UNSUPPORTED", "error_class": type(exc).__name__})
        else:
            reports.append({"outcome": "MANUAL_LIMIT"})
    return (
        rows,
        watched,
        {
            "configured_cache_sources": len(cfg.subscriptions),
            "cache_source_limit_hit": len(cfg.subscriptions) > 32,
            "reports_anonymous": reports,
            "independent_supported_records": len(rows),
            "default_convention": "ABSENT_FP_USES_PRODUCT_CHROME_CONVENTION_NOT_SOURCE_EXPLICIT",
        },
    )


def whole_graph(sb, xray):
    inbounds = [
        x
        for x in sb.get("inbounds", [])
        if re.fullmatch(r"sb-in-[0-9a-f]{8}-[dfm]", str(x.get("tag", "")))
    ]
    outs = sb.get("outbounds", []) + sb.get("endpoints", [])
    rules = sb.get("route", {}).get("rules", [])
    result = {
        "bridge_count": len(inbounds),
        "profiles": dict.fromkeys("dfm", 0),
        "noncanonical_bridges": 0,
        "duplicate_listener_ports": 0,
        "xray_bridge_references": 0,
        "bad_xray_references": 0,
        "unmatched_local_socks_references": 0,
        "reality_outbounds": 0,
        "reality_invalid_key_form": 0,
        "reality_invalid_short_id_form": 0,
        "routing_mark_key_count": bridge.mark_keys(sb),
        "route_rule_schema_violations": sum(
            set(r) != {"inbound", "action", "outbound"}
            or r.get("action") != "route"
            or not isinstance(r.get("inbound"), list)
            or len(r["inbound"]) != 1
            for r in rules[:-1]
        ),
    }
    ports = {}
    for item in inbounds:
        letter = item["tag"][-1]
        result["profiles"][letter] += 1
        port, users = item.get("listen_port"), item.get("users") or []
        linked = [
            r for r in rules if r.get("inbound") == [item["tag"]] and r.get("action") == "route"
        ]
        target = "sb-out-" + item["tag"][6:]
        targets = [o for o in outs if o.get("tag") == target]
        result["noncanonical_bridges"] += not (
            item.get("type") == "socks"
            and item.get("listen") == "127.0.0.1"
            and type(port) is int
            and 1024 <= port <= 65535
            and len(users) == 1
            and users[0].get("username") == "xgw-" + letter
            and bool(users[0].get("password"))
            and len(linked) == 1
            and linked[0].get("outbound") == target
            and len(targets) == 1
            and targets[0].get("type") in bridge.KINDS
        )
        if type(port) is int:
            result["duplicate_listener_ports"] += port in ports
            ports[port] = (letter, users)
    for item in xray.get("outbounds", []):
        if item.get("protocol") != "socks":
            continue
        for server in (item.get("settings") or {}).get("servers", []):
            if server.get("address") != "127.0.0.1":
                continue
            if server.get("port") not in ports:
                result["unmatched_local_socks_references"] += 1
                continue
            result["xray_bridge_references"] += 1
            letter, users = ports[server["port"]]
            xusers = server.get("users") or []
            result["bad_xray_references"] += not (
                len(users) == len(xusers) == 1
                and xusers[0].get("user") == "xgw-" + letter
                and xusers[0].get("pass") == users[0].get("password")
                and not (item.get("streamSettings") or {}).get("sockopt", {}).get("mark")
            )
    for item in outs:
        if ((item.get("tls") or {}).get("reality") or {}).get("enabled"):
            flags = source.syntax_flags(source.contract(item))
            result["reality_outbounds"] += 1
            result["reality_invalid_key_form"] += not flags["public_key_base64url_32_bytes"]
            result["reality_invalid_short_id_form"] += not flags[
                "short_id_even_hex_at_most_8_bytes"
            ]
    result["final_reject"] = bool(rules) and rules[-1] == {"action": "reject"}
    return result


def health_summary(path, now):
    conn = None
    try:
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.5)
        rows = conn.execute("SELECT verdict, bytes, seconds, ts FROM scans LIMIT 5001").fetchall()
        result = {
            "query_ok": True,
            "rows": len(rows),
            "truncated": len(rows) > 5000,
            "verdict_counts": {},
            "age_under_300_seconds": 0,
            "age_over_300_seconds": 0,
            "future_or_invalid_time": 0,
            "OK_bodies_under_32769": 0,
            "core_identity": "UNSPECIFIED_IN_SCAN_SCHEMA",
        }
        for verdict, size, _, stamp in rows[:5000]:
            v = verdict if verdict in diagnostic.VERDICTS else "OTHER"
            result["verdict_counts"][v] = result["verdict_counts"].get(v, 0) + 1
            result["OK_bodies_under_32769"] += (
                verdict == "OK" and type(size) is int and size < 32769
            )
            if type(stamp) not in (int, float) or not -5 <= now - stamp < 10**10:
                result["future_or_invalid_time"] += 1
            else:
                result[
                    "age_under_300_seconds" if now - stamp <= 300 else "age_over_300_seconds"
                ] += 1
        return result
    except Exception as exc:
        return {"query_ok": False, "error_class": type(exc).__name__}
    finally:
        if conn is not None:
            conn.close()


def journals(begin):
    result = {}
    for unit in ("xgw", "xgw-singbox"):
        try:
            p = subprocess.run(
                [
                    "journalctl",
                    "-u",
                    unit,
                    "--since",
                    "@" + str(begin - 600),
                    "--until",
                    "@" + str(begin),
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
            result[unit] = {
                "query_ok": p.returncode == 0,
                **(diagnostic.journal_summary(p.stdout, {}) if p.returncode == 0 else {}),
            }
        except Exception as exc:
            result[unit] = {"query_ok": False, "error_class": type(exc).__name__}
    return result


def worker():
    write("worker-claimed.json", {"claimed": True})
    result = {
        "marker": "EXTENDED_BATCH_PARTIAL",
        "network_requests": 0,
        "phases": {},
        "not_run": [
            "active_health",
            "speed_ping_benchmarks",
            "faults",
            "D1_on_install",
            "E4_packet_attribution",
            "LAN_UDP_IPv6_DNS_end_to_end",
            "all_Tailscale_paths",
        ],
    }
    started = time.monotonic()
    before, old_pin, sb_raw, xr_raw, watched, target_key = None, None, None, None, {}, None

    def phase(name, fn):
        write(
            "progress.json",
            {
                "stage": name,
                "elapsed_seconds": round(time.monotonic() - started),
                "completed": list(result["phases"]),
            },
            True,
        )
        try:
            result["phases"][name] = {"collection": "RECORDED", "data": fn()}
        except Exception as exc:
            result["phases"][name] = {
                "collection": "UNAVAILABLE",
                "error_class": type(exc).__name__,
            }
        write("partial.json", result, True)

    try:
        before, old_pin = reader.snapshot(), bridge.pin_token()
        result["before"] = reader.public(before)
        if not bridge.process_ready(before) or old_pin is None:
            raise ValueError("working context unconfirmed")
        sb_raw, xr_raw = (
            reader.PATHS.singbox_config_file.read_bytes(),
            reader.PATHS.xray_config_file.read_bytes(),
        )
        sb, xr = json.loads(sb_raw), json.loads(xr_raw)

        def historical():
            nonlocal target_key
            diagnostic.checked(S_ROOT, True)
            if (
                single.digest(diagnostic.checked(S_ROOT / "wave3_reality_contract.py").read_bytes())
                != S_SHA
            ):
                raise ValueError("S source mismatch")
            previous = json.loads(diagnostic.checked(S_ROOT / "summary.json").read_bytes())
            if (
                previous.get("marker") != "REALITY_CONTRACT_RECORDED"
                or previous.get("source_comparison", {}).get("all_compared_fields_equal")
                is not True
                or previous.get("all_context_checks_ok") is not True
            ):
                raise ValueError("S evidence shape")
            diagnostic.checked(R_ROOT, True)
            plan = json.loads(diagnostic.checked(R_ROOT / "plan-private.json").read_bytes())
            target_key = plan.get("case_key")
            if not isinstance(target_key, str) or not re.fullmatch(r"[0-9a-f]{8}", target_key):
                target_key = None
                raise ValueError("reference key")
            return {
                "S_accepted_source_consistency": True,
                "current_config_matches_R_plan": single.digest(sb_raw) == plan.get("config_sha256"),
                "old_endpoint_identity": "UNPROVEN",
                "current_sources_lineage": "NOT_ESTABLISHED",
            }

        phase("T1_history", historical)
        records = []

        def sources():
            nonlocal records, watched
            cfg, warnings = reader.config.load(reader.PATHS.config_file)
            if warnings:
                raise ValueError("config warnings")
            records, watched, report = read_records(cfg)
            return report

        phase("T2_independent_sources", sources)
        write(
            "baseline-private.json",
            {
                "sb_config_sha256": single.digest(sb_raw),
                "xray_config_sha256": single.digest(xr_raw),
                "reference_case_key": target_key,
                "source_digests": {str(path): value for path, value in watched.items()},
                "boot": before["boot_private"],
                "process_identity": before["singbox"].get("process_identity"),
            },
        )

        def all_contracts():
            counts = {
                "default_vless_outbounds": 0,
                "equal_supported_contracts": 0,
                "mismatched_supported_contracts": 0,
                "no_unique_supported_record": 0,
            }
            reference = {"outcome": "REFERENCE_NOT_AVAILABLE"}
            for item in sb.get("outbounds", []):
                if item.get("type") != "vless" or not re.fullmatch(
                    r"sb-out-[0-9a-f]{8}-d", str(item.get("tag", ""))
                ):
                    continue
                counts["default_vless_outbounds"] += 1
                row = compare_record(source.contract(item), records)
                if row["outcome"] != "COMPARED":
                    counts["no_unique_supported_record"] += 1
                else:
                    counts[
                        "equal_supported_contracts"
                        if row["all_fields_equal"]
                        else "mismatched_supported_contracts"
                    ] += 1
                if target_key and item["tag"] == "sb-out-" + target_key + "-d":
                    reference = row
            return {
                "counts": counts,
                "reference_case": reference,
                "scope": "INDEPENDENT_SUPPORTED_TCP_RECORDS_ONLY",
            }

        phase("T3_all_default_vless_contracts", all_contracts)
        phase("T4_all_profile_graph", lambda: whole_graph(sb, xr))
        phase("T5_persisted_health", lambda: health_summary(reader.PATHS.db_file, time.time()))
        phase("T6_recent_journal_counts", lambda: journals(time.time()))

        def passive():
            samples = []
            base = before["interfaces"]["LAN"]
            for _ in range(SAMPLES):
                if time.monotonic() - started >= 600:
                    return {"samples": samples, "stop": "BATCH_TIME_BUDGET"}
                time.sleep(INTERVAL)
                value = reader.snapshot()
                lan = value["interfaces"]["LAN"]
                same_lan = value["interface_private"]["LAN"] == before["interface_private"]["LAN"]
                sample = {
                    "elapsed_seconds": round(time.monotonic() - started),
                    "LAN_identity_same": same_lan,
                    "LAN_carrier": lan.get("carrier"),
                    "context_ok": bridge.process_ready(value),
                    "settings_same": value["hashes_private"] == before["hashes_private"],
                    "singbox_process_same": value["singbox"].get("process_identity")
                    == before["singbox"].get("process_identity"),
                }
                for field in ("rx_bytes", "tx_bytes"):
                    a, b = base.get(field), lan.get(field)
                    sample["LAN_" + field + "_delta"] = (
                        b - a if same_lan and type(a) is int and type(b) is int and b >= a else None
                    )
                samples.append(sample)
                write(
                    "progress.json",
                    {
                        "stage": "T7_passive_LAN",
                        "completed_samples": len(samples),
                        "planned_samples": SAMPLES,
                        "last_sample": sample,
                    },
                    True,
                )
                if not (
                    sample["context_ok"]
                    and sample["settings_same"]
                    and sample["singbox_process_same"]
                    and same_lan
                ):
                    return {"samples": samples, "stop": "CONTEXT_CHANGED_STOP_OBSERVATION_ONLY"}
            return {
                "samples": samples,
                "stop": "PLANNED_OBSERVATION_COMPLETE",
                "scope": "COUNTERS_NOT_CLIENT_OR_VPN_PACKET_ATTRIBUTION",
            }

        phase("T7_passive_LAN", passive)
    except Exception as exc:
        result.update(global_stop="BASELINE_OR_CONFIG_UNAVAILABLE", error_class=type(exc).__name__)
    try:
        after, new_pin = reader.snapshot(), bridge.pin_token()
        result["after"] = reader.public(after)
        if before is not None:
            result.update(
                single.context(
                    before, after, single.digest(sb_raw) if sb_raw else None, old_pin, new_pin
                )
            )
        result["xray_config_unchanged"] = (
            xr_raw is not None and reader.PATHS.xray_config_file.read_bytes() == xr_raw
        )
        result["cache_inputs_unchanged"] = all(
            single.digest(source.read_source(path)) == value for path, value in watched.items()
        )
        if (
            len(result["phases"]) == 7
            and all(x["collection"] == "RECORDED" for x in result["phases"].values())
            and result.get("all_context_checks_ok") is True
            and result["xray_config_unchanged"]
            and result["cache_inputs_unchanged"]
            and result["phases"]["T7_passive_LAN"]["data"].get("stop")
            == "PLANNED_OBSERVATION_COMPLETE"
        ):
            result["marker"] = "EXTENDED_BATCH_RECORDED"
    except Exception as exc:
        result.update(after_stop="AFTER_CONTEXT_UNAVAILABLE", after_error_class=type(exc).__name__)
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
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
        (ROOT / name).exists() or (ROOT / name).is_symlink()
        for name in ("started.json", "worker-claimed.json", "summary.json")
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
                "marker": "EXTENDED_BATCH_PARTIAL",
                "launch_error_class": type(exc).__name__,
                "network_requests": 0,
            },
        )
        return 3
    print("EXTENDED_BATCH_STARTED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("STOP_EXTENDED_BATCH", type(exc).__name__)
        raise SystemExit(3) from None
