"""Read-only diagnosis of P's pre-request stop; never executes a probe or a tool check."""

import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path("/run/xgw-w3q")
P_ROOT = Path("/run/xgw-w3p")
O_ROOT = Path("/run/xgw-w3o")
N_ROOT = Path("/run/xgw-w3n")
P_SHA = "66128ddaf8bea6dc73ad1b1138714a468cafb5219168335c035052b167282a93"
spec = importlib.util.spec_from_file_location(
    "old_diagnostic", Path(__file__).with_name("wave3_bridge_diagnostic.py")
)
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)
bridge, reader = diagnostic.bridge, diagnostic.reader


class GateStop(Exception):
    """Only fixed stage/status codes reach public output."""

    def __init__(self, stage, status):
        self.stage, self.status = stage, status


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save(name, value):
    fd = os.open(ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def private(path, stage, directory=False):
    try:
        return diagnostic.checked(path, directory)
    except FileNotFoundError:
        raise GateStop(stage, "MISSING") from None
    except OSError:
        raise GateStop(stage, "READ_ERROR") from None
    except ValueError:
        raise GateStop(stage, "OWNER_MODE_OR_KIND_INVALID") from None


def read_json(path, stage):
    try:
        raw = private(path, stage).read_bytes()
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise GateStop(stage, "JSON_OBJECT_REQUIRED")
        return raw, value
    except (ValueError, UnicodeError):
        raise GateStop(stage, "JSON_INVALID") from None
    except OSError:
        raise GateStop(stage, "READ_ERROR") from None


def p_evidence(value):
    if (
        value.get("marker") != "STOP_SINGLE_PROBE"
        or value.get("request_count") != 0
        or value.get("collection_error_class") != "ValueError"
        or value.get("all_context_checks_ok") is not True
    ):
        raise GateStop("P_SUMMARY", "REPORTED_P_SHAPE_MISMATCH")
    try:
        b, a = value["before"], value["after"]
        times = [b["realtime"], b["monotonic"], a["realtime"], a["monotonic"]]
        duration = a["monotonic"] - b["monotonic"]
        if (
            not all(type(x) in (int, float) and math.isfinite(x) and x > 0 for x in times)
            or not 0 < duration < 120
            or abs((a["realtime"] - b["realtime"]) - duration) > 2
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise GateStop("P_SUMMARY", "TIME_BASIS_INVALID") from None
    # This is a source-derived interval, never a recovered exact exception site.
    stage = (
        "AFTER_CONFIG_DIGEST_BEFORE_CURL_VERSION_EMISSION"
        if value.get("bridge_config_unchanged") is True and "curl_version" not in value
        else "EXACT_SITE_UNRECORDED"
    )
    return (
        {
            "historical_P_valid": True,
            "P_request_count": 0,
            "P_source_derived_stage_range": stage,
            "P_plan_persisted_flag_present": "private_plan_persisted_before_request" in value,
            "P_plan_persisted_flag_true": value.get("private_plan_persisted_before_request")
            is True,
            "P_curl_version_field_present": "curl_version" in value,
            "P_O_digest_flag_present": "current_config_matches_O_digest" in value,
            "P_exception_site": "UNRECORDED",
        },
        b["realtime"],
        b["monotonic"],
    )


def mapping_checks(mapping, old_summary, n_raw, raw):
    if not isinstance(mapping, dict) or not isinstance(old_summary, dict):
        raise GateStop("O_MAPPING", "JSON_OBJECT_REQUIRED")
    key = mapping.get("case_keys", {})
    key = key.get("SB-1") if isinstance(key, dict) else None
    checks = {
        "O_recorded_marker": old_summary.get("marker") == "READ_DIAGNOSTIC_RECORDED",
        "O_historical_summary_valid": old_summary.get("historical_summary_valid") is True,
        "O_mapping_basis_supported": old_summary.get("historical_mapping")
        == "FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN",
        "mapping_basis_supported": mapping.get("mapping_basis")
        == "FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN",
        "N_summary_digest_matches_O": mapping.get("n_summary_sha256") == digest(n_raw),
        "current_config_digest_matches_O": mapping.get("current_config_sha256") == digest(raw),
        "SB1_key_shape_valid": isinstance(key, str)
        and re.fullmatch(r"[0-9a-f]{8}", key) is not None,
    }
    try:
        applied = json.loads(raw)
        candidates = bridge.bridges(applied)
        matched = [x for x in candidates if checks["SB1_key_shape_valid"] and x["key"] == key]
        checks.update(
            current_route_canonical=True,
            mapped_SB1_unique=len(matched) == 1,
            mapped_SB1_vless=len(matched) == 1 and matched[0]["protocol"] == "vless",
            current_routing_marks_absent=bridge.mark_keys(applied) == 0,
        )
    except (ValueError, AttributeError, TypeError, KeyError, UnicodeError):
        checks.update(
            current_route_canonical=False,
            mapped_SB1_unique=None,
            mapped_SB1_vless=None,
            current_routing_marks_absent=None,
        )
    first = next((name for name, ok in checks.items() if ok is not True), None)
    return {
        "current_static_checks": checks,
        "current_first_unmet_gate": first,
        "current_all_mapping_and_route_gates_ok": first is None,
    }


def time_support(begin, mono, info, now=None, current_mono=None):
    now = time.time() if now is None else now
    current_mono = time.monotonic() if current_mono is None else current_mono
    compatible = abs((now - begin) - (current_mono - mono)) <= 5
    predates = info.st_mtime <= begin and info.st_ctime <= begin
    return {
        "clock_basis_compatible_with_P": compatible,
        "config_file_times_predate_P": predates,
        "current_config_relation_to_P": "FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN"
        if compatible and predates
        else "UNCONFIRMED",
    }


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
        "bridge_config_unchanged": digest(reader.PATHS.singbox_config_file.read_bytes())
        == config_digest
        if config_digest is not None
        else None,
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


def main():
    if os.geteuid() != 0:
        raise GateStop("Q_RUN", "ROOT_REQUIRED")
    private(ROOT, "Q_DIRECTORY", True)
    if sys.argv[1] == "show":
        print(private(ROOT / "summary.json", "Q_SUMMARY").read_text())
        return 0
    if sys.argv[1] != "run" or any(
        (ROOT / name).exists() or (ROOT / name).is_symlink()
        for name in ("started.json", "summary.json")
    ):
        raise GateStop("Q_RUN", "ALREADY_STARTED_OR_INVALID_MODE")
    save("started.json", {"realtime": time.time()})
    result = {
        "marker": "STOP_GATE_DIAGNOSTIC",
        "Q_network_requests": 0,
        "P_exception_site": "UNRECORDED",
        "stage": "Q_BEFORE_CONTEXT",
    }
    before, old_pin, config_digest = None, None, None
    try:
        before, old_pin = reader.snapshot(), bridge.pin_token()
        result["before"] = reader.public(before)
        if not bridge.process_ready(before) or old_pin is None:
            raise GateStop("Q_BEFORE_CONTEXT", "WORKING_CONTEXT_UNCONFIRMED")
        for directory, stage in (
            (P_ROOT, "P_DIRECTORY"),
            (O_ROOT, "O_DIRECTORY"),
            (N_ROOT, "N_DIRECTORY"),
        ):
            private(directory, stage, True)
        result["stage"] = "P_SOURCE"
        if digest(private(P_ROOT / "wave3_single_bridge.py", "P_SOURCE").read_bytes()) != P_SHA:
            raise GateStop("P_SOURCE", "SHA_MISMATCH")
        _, previous = read_json(P_ROOT / "summary.json", "P_SUMMARY")
        facts, begin, mono = p_evidence(previous)
        result.update(facts)
        plan = P_ROOT / "plan-private.json"
        result["P_plan_file_present_now"] = plan.exists() or plan.is_symlink()
        if result["P_plan_file_present_now"]:
            private(plan, "P_PLAN")  # Metadata only; no need to read its private values.
        result["stage"] = "N_INPUTS"
        if (
            digest(private(N_ROOT / "wave3_bridge_probe.py", "N_SOURCE").read_bytes())
            != diagnostic.N_SHA
        ):
            raise GateStop("N_SOURCE", "SHA_MISMATCH")
        n_raw, n_value = read_json(N_ROOT / "summary.json", "N_SUMMARY")
        try:
            diagnostic.historical(n_value)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise GateStop("N_SUMMARY", "HISTORICAL_SHAPE_INVALID") from None
        _, old_summary = read_json(O_ROOT / "summary.json", "O_SUMMARY")
        _, mapping = read_json(O_ROOT / "mapping-private.json", "O_MAPPING")
        result["stage"] = "CURRENT_CONFIG"
        path = reader.PATHS.singbox_config_file
        raw, info = path.read_bytes(), path.stat()
        config_digest = digest(raw)
        result.update(mapping_checks(mapping, old_summary, n_raw, raw))
        result.update(time_support(begin, mono, info))
        result["stage"] = "CURRENT_CONFIG_PROBE_TARGETS"
        cfg, warnings = reader.config.load(reader.PATHS.config_file)
        result["current_config_warnings_present"] = bool(warnings)
        result["current_valid_configured_HTTPS_target_count"] = len(bridge.targets(cfg))
        result["current_curl_path_available"] = shutil.which("curl") is not None
        result["curl_version_rechecked"] = False  # No subprocess, even --version.
        result["current_diagnostic_complete"] = True
        result["stage"] = "CURRENT_STATIC_READS_COMPLETE"
    except GateStop as exc:
        result.update(stage=exc.stage, stop_code=exc.status)
    except Exception as exc:
        result.update(stop_code="UNEXPECTED_READ_OR_SCHEMA_ERROR", error_class=type(exc).__name__)
    try:
        after, new_pin = reader.snapshot(), bridge.pin_token()
        result["after"] = reader.public(after)
        if before is not None:
            result.update(context(before, after, config_digest, old_pin, new_pin))
        if result.get("current_diagnostic_complete") and result.get("all_context_checks_ok"):
            result["marker"] = "GATE_DIAGNOSTIC_RECORDED"
    except Exception as exc:
        result.update(
            after_stop_code="AFTER_CONTEXT_READ_ERROR", after_error_class=type(exc).__name__
        )
    save("summary.json", result)
    print(json.dumps(result))
    return 0 if result["marker"] == "GATE_DIAGNOSTIC_RECORDED" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateStop as exc:
        print("STOP_GATE_DIAGNOSTIC", exc.stage, exc.status)
        raise SystemExit(3) from None
    except Exception as exc:
        print("STOP_GATE_DIAGNOSTIC", "UNEXPECTED_SETUP_ERROR", type(exc).__name__)
        raise SystemExit(3) from None
