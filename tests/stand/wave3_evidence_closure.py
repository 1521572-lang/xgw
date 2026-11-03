"""Close local evidence gaps in one read-only batch; no active endpoint tests."""

import importlib.util
import json
import os
import re
import selectors
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/run/xgw-w3v")
OLD = Path("/run/xgw-w3u")
U_SHA = "f3c45a1fc9ceb33f2bff012f65dbfcf875eb3906026d96f7eb8f9999b9bbff48"
spec = importlib.util.spec_from_file_location(
    "coverage_library", Path(__file__).with_name("wave3_coverage_batch.py")
)
coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage)
batch, source, single, diagnostic, bridge, reader = (
    coverage.batch,
    coverage.source,
    coverage.single,
    coverage.diagnostic,
    coverage.bridge,
    coverage.reader,
)


def write(name, value, replace=False):
    batch.ROOT = ROOT
    batch.write(name, value, replace)


def contract_gaps(sb, records):
    """Distinguish absent identity from conflicting contracts without choosing a best match."""
    counts = dict.fromkeys(
        ("default_vless", "equal", "mismatched", "missing_identity", "ambiguous_contracts"), 0
    )
    conflicting = dict.fromkeys(source.contract({}), 0)
    mismatch_fields = dict.fromkeys(conflicting, 0)
    for item in sb.get("outbounds", []):
        if item.get("type") != "vless" or not re.fullmatch(
            r"sb-out-[0-9a-f]{8}-d", str(item.get("tag", ""))
        ):
            continue
        counts["default_vless"] += 1
        actual = source.contract(item)
        matched = [
            r
            for r in records
            if all(actual[k] == r.get(k) for k in ("server", "server_port", "uuid"))
        ]
        distinct = {json.dumps(r, sort_keys=True): r for r in matched}
        if not distinct:
            counts["missing_identity"] += 1
        elif len(distinct) > 1:
            counts["ambiguous_contracts"] += 1
            for key in conflicting:
                conflicting[key] += (
                    len({json.dumps(r.get(key), sort_keys=True) for r in distinct.values()}) > 1
                )
        else:
            expected = next(iter(distinct.values()))
            differences = {k: actual[k] != expected.get(k) for k in actual}
            counts["mismatched" if any(differences.values()) else "equal"] += 1
            for key, changed in differences.items():
                mismatch_fields[key] += changed
    return {
        "counts": counts,
        "ambiguous_field_counts": conflicting,
        "mismatch_field_counts": mismatch_fields,
        "scope": "CURRENT_SUPPORTED_CACHE_ONLY_NOT_HISTORICAL_U_OR_HEALTH",
        "missing_identity_reason": "UNDETERMINED_NOT_AUTOMATIC_RUNTIME_BUG",
    }


def generation_categories(current, other):
    def index(value):
        result = {}
        for field in ("outbounds", "endpoints"):
            for item in value.get(field, []):
                if not isinstance(item, dict) or not isinstance(item.get("tag"), str):
                    raise ValueError("endpoint shape")
                if item["tag"] in result:
                    raise ValueError("duplicate endpoint tag")
                result[item["tag"]] = item
        return result

    left, right = index(current), index(other)
    categories = {
        "type": ("type",),
        "identity": ("server", "server_port", "uuid", "password"),
        "tls": ("tls",),
        "transport": ("transport",),
        "multiplex": ("multiplex",),
        "detour": ("detour",),
        "group_members": ("outbounds", "default"),
    }
    keys = {key for group in categories.values() for key in group} | {"tag"}
    fields = dict.fromkeys((*categories, "other_fields"), 0)
    roles = dict.fromkeys(("VLESS", "GROUP", "SERVICE", "OTHER"), 0)
    changed = 0
    for tag in left.keys() & right.keys():
        a, b = left[tag], right[tag]
        if a == b:
            continue
        changed += 1
        kind = a.get("type")
        role = (
            "VLESS"
            if kind == "vless"
            else "GROUP"
            if kind in ("selector", "urltest")
            else "SERVICE"
            if kind in ("direct", "block", "dns")
            else "OTHER"
        )
        roles[role] += 1
        for group, names in categories.items():
            fields[group] += any((k in a, a.get(k)) != (k in b, b.get(k)) for k in names)
        fields["other_fields"] += {k: v for k, v in a.items() if k not in keys} != {
            k: v for k, v in b.items() if k not in keys
        }
    return {
        "shared_objects_changed": changed,
        "current_type_counts": roles,
        "changed_field_group_counts_OVERLAP": fields,
        "added_in_current": len(left.keys() - right.keys()),
        "removed_in_current": len(right.keys() - left.keys()),
        "scope": "CONFIG_OBJECTS_NOT_SERVER_REFRESH_OR_WRITER_PROOF",
    }


PATTERNS = {
    "unchanged": "sing-box: изменений нет",
    "deferred": "перечитывание отложено",
    "started": "sing-box запущен",
    "reloaded": "конфиг sing-box перечитан",
    "rejected": "конфиг sing-box отклонён",
    "rollback": "откат на last-good",
    "systemd_reload_word": r"\bReload(?:ing|ed)\b",
}


def journal_counts(raw):
    lines = raw.splitlines()
    result = {
        "rows_analyzed": min(len(lines), 1000),
        "parse_errors": 0,
        "row_limit_hit": len(lines) > 1000,
        "incomplete_last_line": False,
        "literal_counts": dict.fromkeys(PATTERNS, 0),
    }
    if raw and not raw.endswith(b"\n"):
        result["incomplete_last_line"] = True
        lines = lines[:-1]
        result["rows_analyzed"] = min(len(lines), 1000)
    # journalctl returns chronological tail; keep the most recent complete rows.
    for line in lines[-1000:]:
        try:
            value = json.loads(line)
            message = value.get("MESSAGE")
            if not isinstance(message, str):
                raise ValueError("message shape")
            for name, pattern in PATTERNS.items():
                result["literal_counts"][name] += bool(re.search(pattern, message))
        except (ValueError, AttributeError, TypeError):
            result["parse_errors"] += 1
    return result


def bounded_journal():
    """One 2h query, 10s/1MiB bounds, terminate only our own journalctl child if needed."""
    now, deadline = time.time(), time.monotonic() + 10
    argv = [
        "journalctl",
        "-u",
        "xgw",
        "-u",
        "xgw-singbox",
        "--since",
        "@" + str(now - 7200),
        "--until",
        "@" + str(now),
        "-n",
        "1001",
        "-o",
        "json",
        "--output-fields=MESSAGE",
        "--no-pager",
    ]
    raw, reason, proc = bytearray(), "EOF", None
    try:
        proc = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    reason = "TIME_BUDGET"
                    break
                if not selector.select(remaining):
                    reason = "TIME_BUDGET"
                    break
                chunk = os.read(proc.stdout.fileno(), min(8192, 1048576 - len(raw)))
                if not chunk:
                    break
                raw.extend(chunk)
                if len(raw) >= 1048576:
                    reason = "BYTE_BUDGET"
                    break
        if reason == "EOF":
            try:
                proc.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                reason = "TIME_BUDGET"
    except OSError:
        reason = "CHILD_UNAVAILABLE"
    finally:
        if proc is not None:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=1)
            if proc.stdout is not None:
                proc.stdout.close()
    rc = proc.returncode if proc is not None else None
    return {
        "query_ok": reason == "EOF" and rc == 0,
        "stop_reason": reason,
        "child_rc": rc,
        "window_seconds": 7200,
        "byte_limit": 1048576,
        "raw_bytes_read": len(raw),
        **journal_counts(bytes(raw)),
        "scope": "BOUNDED_WORD_COUNTS_NOT_WRITER_OR_CAUSE_PROOF",
    }


def worker():
    write("worker-claimed.json", {"claimed": True})
    result = {
        "marker": "EVIDENCE_CLOSURE_PARTIAL",
        "network_requests": 0,
        "phases": {},
        "executor_scope": "THINKCENTRE_ONLY_CONFIRMED_BY_OWNER",
    }
    before, pin, sb_raw, xr_raw = None, None, None, None
    watched, generations, oldbase = {}, {}, {}
    began = time.monotonic()

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
        sb_raw, sb = coverage.read_config(reader.PATHS.singbox_config_file)
        xr_raw, _ = coverage.read_config(reader.PATHS.xray_config_file)

        def history():
            nonlocal oldbase
            diagnostic.checked(OLD, True)
            if (
                single.digest(diagnostic.checked(OLD / "wave3_coverage_batch.py").read_bytes())
                != U_SHA
            ):
                raise ValueError("U source")
            previous = json.loads(diagnostic.checked(OLD / "summary.json").read_bytes())
            if (
                previous.get("marker") != "COVERAGE_BATCH_RECORDED"
                or previous.get("all_context_checks_ok") is not True
            ):
                raise ValueError("U summary")
            candidate = json.loads(diagnostic.checked(OLD / "baseline-private.json").read_bytes())
            if not isinstance(candidate, dict) or not isinstance(
                candidate.get("source_digests"), dict
            ):
                raise ValueError("U baseline")
            oldbase = candidate
            return {
                "U_scope_accepted": True,
                "current_sb_matches_U": single.digest(sb_raw) == oldbase.get("sb_config_sha256"),
                "current_xray_matches_U": single.digest(xr_raw)
                == oldbase.get("xray_config_sha256"),
            }

        phase("V1_U_identity", history)

        def gaps():
            nonlocal watched
            cfg, warnings = reader.config.load(reader.PATHS.config_file)
            if warnings:
                raise ValueError("configuration warnings")
            records, watched, info = coverage.read_sources(cfg)
            info["same_cache_digests_as_U"] = (
                bool(watched)
                and {str(p): v for p, v in watched.items()} == oldbase["source_digests"]
                if oldbase
                else None
            )
            return {"source_coverage": info, "contracts": contract_gaps(sb, records)}

        phase("V2_contract_gap_classification", gaps)

        def peers():
            info = coverage.generation_summary(sb_raw, sb, {}, generations)
            for label, path in (
                ("last_good", reader.PATHS.singbox_last_good_file),
                ("pending", reader.PATHS.singbox_pending_file),
            ):
                if info[label].get("available"):
                    raw, value = coverage.read_config(path)
                    if single.digest(raw) != generations[path]:
                        raise ValueError("generation changed during read")
                    info[label]["object_categories"] = generation_categories(sb, value)
            return info

        phase("V3_generation_object_categories", peers)
        phase("V4_bounded_writer_journal", bounded_journal)
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
            xr_raw is not None and coverage.read_config(reader.PATHS.xray_config_file)[0] == xr_raw
        )
        result["cache_inputs_read"] = len(watched)
        result["cache_inputs_unchanged"] = all(
            single.digest(source.read_source(p)) == v for p, v in watched.items()
        )
        result["generation_inputs_read"] = len(generations)
        result["local_generation_files_unchanged"] = all(
            single.digest(coverage.read_config(p)[0]) == v for p, v in generations.items()
        )
        if (
            len(result["phases"]) == 4
            and all(p["collection"] == "RECORDED" for p in result["phases"].values())
            and result.get("all_context_checks_ok") is True
            and result["xray_config_unchanged"]
            and result["cache_inputs_unchanged"]
            and result["local_generation_files_unchanged"]
        ):
            result["marker"] = "EVIDENCE_CLOSURE_RECORDED"
    except Exception as exc:
        result.update(
            after_stop="AFTER_CONTEXT_OR_INPUT_CHANGED", after_error_class=type(exc).__name__
        )
    result["elapsed_seconds"] = round(time.monotonic() - began, 3)
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
                "marker": "EVIDENCE_CLOSURE_PARTIAL",
                "launch_error_class": type(exc).__name__,
                "network_requests": 0,
            },
        )
        return 3
    print("EVIDENCE_CLOSURE_STARTED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("STOP_EVIDENCE_CLOSURE", type(exc).__name__)
        raise SystemExit(3) from None
