"""One current-baseline bridge request after Q established cross-run configuration drift."""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/run/xgw-w3r")
Q_ROOT = Path("/run/xgw-w3q")
O_ROOT = Path("/run/xgw-w3o")
Q_SHA = "e793106474f7a7910886cecd0d11a65f084d123f440473dba8d596f2a36f648b"
spec = importlib.util.spec_from_file_location(
    "single_reader", Path(__file__).with_name("wave3_single_bridge.py")
)
single = importlib.util.module_from_spec(spec)
spec.loader.exec_module(single)
diagnostic, bridge, reader = single.diagnostic, single.bridge, single.reader


class Stop(Exception):
    def __init__(self, code):
        self.code = code


def require(ok, code):
    if not ok:
        raise Stop(code)


def save(name, value):
    fd = os.open(ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def q_evidence(value):
    checks = value.get("current_static_checks", {})
    names = (
        "O_recorded_marker",
        "O_historical_summary_valid",
        "O_mapping_basis_supported",
        "mapping_basis_supported",
        "N_summary_digest_matches_O",
        "SB1_key_shape_valid",
        "current_route_canonical",
        "mapped_SB1_unique",
        "mapped_SB1_vless",
        "current_routing_marks_absent",
    )
    require(
        value.get("marker") == "GATE_DIAGNOSTIC_RECORDED"
        and value.get("historical_P_valid") is True
        and value.get("P_request_count") == 0
        and value.get("Q_network_requests") == 0
        and value.get("all_context_checks_ok") is True
        and value.get("current_first_unmet_gate") == "current_config_digest_matches_O"
        and checks.get("current_config_digest_matches_O") is False
        and all(checks.get(name) is True for name in names),
        "Q_EVIDENCE_MISMATCH",
    )


def current_selection(mapping, old_summary, n_raw, raw):
    # This deliberately establishes a NEW baseline. No assertion of N/O endpoint identity.
    require(
        old_summary.get("marker") == "READ_DIAGNOSTIC_RECORDED"
        and old_summary.get("historical_summary_valid") is True
        and old_summary.get("historical_mapping") == "FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN"
        and mapping.get("mapping_basis") == "FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN"
        and mapping.get("n_summary_sha256") == single.digest(n_raw),
        "REFERENCE_MAPPING_INVALID",
    )
    key = mapping.get("case_keys", {}).get("SB-1")
    require(isinstance(key, str) and re.fullmatch(r"[0-9a-f]{8}", key), "REFERENCE_KEY_INVALID")
    applied = json.loads(raw)
    selected = [item for item in bridge.bridges(applied) if item["key"] == key]
    require(
        len(selected) == 1 and selected[0]["protocol"] == "vless", "CURRENT_BRIDGE_NOT_UNIQUE_VLESS"
    )
    require(bridge.mark_keys(applied) == 0, "CURRENT_ROUTING_MARKS_PRESENT")
    return selected[0]


def main():
    require(os.geteuid() == 0, "ROOT_REQUIRED")
    diagnostic.checked(ROOT, True)
    if sys.argv[1] == "show":
        print(diagnostic.checked(ROOT / "summary.json").read_text())
        return 0
    require(
        sys.argv[1] == "run"
        and not any(
            (ROOT / name).exists() or (ROOT / name).is_symlink()
            for name in ("started.json", "plan-private.json", "summary.json")
        ),
        "ALREADY_STARTED_OR_INVALID_MODE",
    )
    save("started.json", {"realtime": time.time(), "monotonic": time.monotonic()})
    result = {
        "marker": "STOP_CURRENT_BRIDGE",
        "case": "R-CURRENT-1",
        "request_count": 0,
        "historical_endpoint_identity": "UNPROVEN",
        "stage": "BEFORE_CONTEXT",
    }
    before, old_pin, config_digest = None, None, None
    try:
        before, old_pin = reader.snapshot(), bridge.pin_token()
        result["before"] = reader.public(before)
        require(bridge.process_ready(before) and old_pin is not None, "WORKING_CONTEXT_UNCONFIRMED")
        result["stage"] = "Q_EVIDENCE"
        diagnostic.checked(Q_ROOT, True)
        require(
            single.digest(diagnostic.checked(Q_ROOT / "wave3_gate_diagnostic.py").read_bytes())
            == Q_SHA,
            "Q_SOURCE_SHA_MISMATCH",
        )
        q_raw = diagnostic.checked(Q_ROOT / "summary.json").read_bytes()
        q_evidence(json.loads(q_raw))
        result["stage"] = "REFERENCE_INPUTS"
        diagnostic.checked(O_ROOT, True)
        diagnostic.checked(diagnostic.OLD, True)
        n_raw = diagnostic.checked(diagnostic.OLD / "summary.json").read_bytes()
        require(
            single.digest(diagnostic.checked(diagnostic.OLD / "wave3_bridge_probe.py").read_bytes())
            == diagnostic.N_SHA,
            "N_SOURCE_SHA_MISMATCH",
        )
        diagnostic.historical(json.loads(n_raw))
        o_raw = diagnostic.checked(O_ROOT / "summary.json").read_bytes()
        mapping_raw = diagnostic.checked(O_ROOT / "mapping-private.json").read_bytes()
        mapping = json.loads(mapping_raw)
        result["stage"] = "CURRENT_BASELINE_SELECTION"
        raw = reader.PATHS.singbox_config_file.read_bytes()
        config_digest = single.digest(raw)
        selected = current_selection(mapping, json.loads(o_raw), n_raw, raw)
        result.update(
            selection_basis="CURRENT_UNIQUE_VLESS_AT_O_CASE_KEY",
            current_config_equals_O=single.digest(raw) == mapping.get("current_config_sha256"),
            current_config=diagnostic.endpoint_summary(json.loads(raw), selected["key"]),
        )
        result["stage"] = "CURRENT_TARGETS"
        cfg, warnings = reader.config.load(reader.PATHS.config_file)
        urls = bridge.targets(cfg)
        require(not warnings and bool(urls), "CURRENT_TARGETS_UNAVAILABLE")
        result["stage"] = "CURL_TOOL"
        curl = shutil.which("curl")
        require(bool(curl), "CURL_MISSING")
        p = subprocess.run([curl, "-q", "--version"], capture_output=True, timeout=3, check=False)
        match = re.match(rb"curl (\d+)\.(\d+)\.(\d+)", p.stdout)
        require(p.returncode == 0 and match is not None, "CURL_VERSION_UNREADABLE")
        require(tuple(int(x) for x in match.groups()) >= (8, 4, 0), "CURL_VERSION_BELOW_8_4")
        result["curl_version"] = ".".join(x.decode() for x in match.groups())
        result["stage"] = "SAVE_PRIVATE_PLAN"
        save(
            "plan-private.json",
            {
                "selection_basis": result["selection_basis"],
                "historical_endpoint_identity": "UNPROVEN",
                "case_key": selected["key"],
                "config_sha256": config_digest,
                "target_sha256": single.digest(urls[0].encode()),
                "target_index": 1,
                "process_identity": before["singbox"]["process_identity"],
                "boot": before["boot_private"],
                "service_identity": before["unit_private"],
                "Q_summary_sha256": single.digest(q_raw),
                "O_mapping_sha256": single.digest(mapping_raw),
                "realtime": time.time(),
                "monotonic": time.monotonic(),
            },
        )
        result["private_plan_persisted_before_request"] = True
        result["stage"] = "PRE_REQUEST_CONTEXT"
        pid = before["singbox"]["process_identity"][0]
        pre = reader.snapshot()
        result["listener_owned_before"] = bridge.owns_listener(pid, selected["port"])
        flags = single.context(before, pre, config_digest, old_pin, bridge.pin_token())
        require(
            flags["all_context_checks_ok"] and result["listener_owned_before"],
            "PRE_REQUEST_CONTEXT_CHANGED",
        )
        result["stage"] = "ONE_CURRENT_REQUEST"
        begin, mono = time.time(), time.monotonic()
        result["request_count"] = 1
        result["attempt"] = single.request(curl, selected, urls[0])
        end, elapsed = time.time(), time.monotonic() - mono
        result["request_window"] = {
            "begin_realtime": begin,
            "end_realtime": end,
            "elapsed_monotonic_seconds": round(elapsed, 6),
            "clock_basis_compatible": end >= begin and abs((end - begin) - elapsed) <= 1,
        }
        result["listener_owned_after"] = bridge.owns_listener(pid, selected["port"])
        result["stage"] = "NEW_REQUEST_JOURNAL"
        result["journal"] = (
            single.journal(begin, end, selected["key"])
            if result["request_window"]["clock_basis_compatible"]
            else {"query_ok": False, "blocked_clock_basis": True}
        )
        result["stage"] = "CURRENT_REQUEST_RECORDED"
    except Stop as exc:
        result["stop_code"] = exc.code
    except Exception as exc:
        result.update(stop_code="UNEXPECTED_STAGE_ERROR", error_class=type(exc).__name__)
    try:
        after, new_pin = reader.snapshot(), bridge.pin_token()
        result["after"] = reader.public(after)
        if before is not None:
            result.update(single.context(before, after, config_digest, old_pin, new_pin))
            if config_digest is None:
                result["bridge_config_unchanged"] = None
        complete = (
            result.get("all_context_checks_ok") is True
            and result["request_count"] == 1
            and "attempt" in result
            and result.get("listener_owned_before") is True
            and result.get("listener_owned_after") is True
            and "stop_code" not in result
        )
        result["marker"] = "CURRENT_BRIDGE_RECORDED" if complete else "STOP_CURRENT_BRIDGE"
        if not complete and "stop_code" not in result:
            result["stop_code"] = "AFTER_CONTEXT_OR_LISTENER_UNCONFIRMED"
    except Exception as exc:
        result.update(after_stop_code="AFTER_CONTEXT_ERROR", after_error_class=type(exc).__name__)
    save("summary.json", result)
    print(json.dumps(result))
    return 0 if result["marker"] == "CURRENT_BRIDGE_RECORDED" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Stop as exc:
        print("STOP_CURRENT_BRIDGE", exc.code)
        raise SystemExit(3) from None
    except Exception as exc:
        print("STOP_CURRENT_BRIDGE", "SETUP_ERROR", type(exc).__name__)
        raise SystemExit(3) from None
