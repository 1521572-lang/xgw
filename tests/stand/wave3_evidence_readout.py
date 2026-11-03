"""AH: bounded read-only reconciliation of existing AG/AF/AE artifacts. No test execution."""

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

NOTES = Path.home() / "xgw-w3ah"
CONTRACT_SHA = "4a1af46f22d444e0f1a352f43d5a596ab904e167cd667e1cce80c43a060a9eec"
FLAGS = (
    "installed_runtime_changed",
    "runtime_actor_binding_implemented",
    "runtime_writer_fence_verified",
    "runtime_verifier_implemented",
    "runtime_recovery_implemented",
    "repair_implemented",
    "active_faults_authorized",
)
ENUMS = frozenset(
    (
        "NONE",
        "TRUE",
        "FALSE",
        "ZERO",
        "ONE",
        "OTHER_INT",
        "TEXT",
        "EMPTY_TEXT",
        "LIST",
        "DICT",
        "TUPLE",
        "POOL",
        "OUTCOME",
        "UNSUPPORTED",
    )
)
INT_DETAILS = frozenset(
    ("registry_receipts", "registry_generation", "unknown_writers", "stub_calls", "file_checked")
)
BOOL_DETAILS = frozenset(
    (
        "legacy_equivalent",
        "fixture_unchanged",
        "rejection_observed",
        "completion_verified",
        "file_matched",
    )
)
ERRORS = frozenset(
    (
        "OSError",
        "PermissionError",
        "FileExistsError",
        "FileNotFoundError",
        "ValueError",
        "TypeError",
        "AttributeError",
        "AssertionError",
        "RuntimeError",
        "ScopeStop",
        "MutationBlocked",
        "Refused",
        "JSONDecodeError",
    )
)
SUMMARY_KEYS = frozenset(
    (
        "marker",
        "scope",
        "expected",
        "completed",
        "passed",
        "cases",
        "global_scope_stop",
        "remaining_not_run",
        "source_files",
        "elapsed_ms",
        "audit_registered",
        "unexpected_forbidden_io",
        "workload_subprocesses",
        "network_requests",
        "live_gateway_operations",
        *FLAGS,
    )
)


class Refused(Exception):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def count(value):
    return type(value) is int and 0 <= value <= 2**63 - 1


def private(path, directory=False):
    info = path.lstat()
    require(
        (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
        and (directory or info.st_nlink == 1),
        "METADATA_REFUSED",
    )
    return info


def stamp(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def read(path, limit=262144):
    before = private(path)
    require(before.st_size <= limit, "SIZE_REFUSED")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        require(stamp(os.fstat(stream.fileno())) == stamp(before), "FILE_CHANGED")
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    require(
        len(raw) <= limit and stamp(before) == stamp(after) == stamp(private(path)), "FILE_CHANGED"
    )
    return raw


def pairs(items):
    data = {}
    for key, value in items:
        require(key not in data, "DUPLICATE_JSON_KEY")
        data[key] = value
    return data


def decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, UnicodeError, RecursionError):
        raise Refused("JSON_REFUSED") from None


def create(name, raw):
    private(NOTES, True)
    fd = os.open(NOTES / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()


def verify_frozen(profile):
    label = profile["label"]
    require(
        label in ("AG", "AF", "AE") and profile["notes"] == "xgw-w3" + label.lower(),
        "PROFILE_REFUSED",
    )
    root = Path.home() / profile["notes"]
    private(root, True)
    for name, digest in (
        ("batch.py", profile["helper_sha256"]),
        ("support.py", profile["support_sha256"]),
        ("manifest.json", profile["manifest_sha256"]),
    ):
        require(hashlib.sha256(read(root / name)).hexdigest() == digest, "FROZEN_HASH_MISMATCH")
    manifest = decode(read(root / "manifest.json"))
    require(
        type(manifest) is dict and len(manifest) == profile["source_files"] == 116,
        "SOURCE_COUNT_REFUSED",
    )
    private(root / "source", True)
    inventory, total = set(), 0
    for path in (root / "source").rglob("*"):
        if stat.S_ISDIR(path.lstat().st_mode):
            private(path, True)
        else:
            private(path)
            inventory.add(path.relative_to(root / "source").as_posix())
    require(inventory == set(manifest), "SOURCE_INVENTORY_MISMATCH")
    for relative, digest in manifest.items():
        require(
            type(relative) is str
            and re.fullmatch(r"src/xgw/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\.py", relative)
            and type(digest) is str
            and re.fullmatch(r"[0-9a-f]{64}", digest),
            "SOURCE_PATH_REFUSED",
        )
        raw = read(root / "source" / relative, 2097152)
        total += len(raw)
        require(
            total <= 16777216 and hashlib.sha256(raw).hexdigest() == digest, "SOURCE_HASH_MISMATCH"
        )
    for filename, key in (("started.json", "started"), ("worker-claimed.json", "claimed")):
        marker = decode(read(root / filename))
        require(
            type(marker) is dict and set(marker) == {key} and marker[key] is True,
            "RUN_MARKER_REFUSED",
        )
    return root, set(manifest)


def normalize(profile, data, final, public_paths):
    require(type(data) is dict, "RECORD_SCHEMA_REFUSED")
    allowed = SUMMARY_KEYS if final else {"final", "completed", "cases"}
    require(set(data) <= allowed and type(data.get("cases")) is list, "RECORD_SCHEMA_REFUSED")
    if not final:
        require(data.get("final") is False, "CHECKPOINT_REFUSED")
    raw_rows = data["cases"]
    require(len(raw_rows) <= profile["count"], "CASE_COUNT_REFUSED")
    rows = []
    allowed_row = {
        "case",
        "passed",
        "details",
        "elapsed_ms",
        "reason",
        "error_class",
        "public_error_source",
        "public_error_line",
    }
    for index, raw in enumerate(raw_rows):
        require(
            type(raw) is dict
            and set(raw) <= allowed_row
            and raw.get("case") == profile["ids"][index]
            and type(raw.get("passed")) is bool
            and count(raw.get("elapsed_ms")),
            "CASE_SCHEMA_REFUSED",
        )
        details = raw.get("details")
        require(
            type(details) is dict and set(details) <= set(profile["details"]),
            "DETAIL_SCHEMA_REFUSED",
        )
        actual = {}
        for key in profile["details"]:
            value = details.get(key)
            if key in INT_DETAILS:
                require(value is None or count(value), "DETAIL_TYPE_REFUSED")
            elif key in BOOL_DETAILS:
                require(value is None or type(value) is bool, "DETAIL_TYPE_REFUSED")
            else:
                require(
                    value is None or (type(value) is str and value in ENUMS), "DETAIL_ENUM_REFUSED"
                )
            actual[key] = value
        checks = profile["rules"][raw["case"]]
        issues = [] if raw["passed"] else ["CASE_FAILED"]
        if set(details) != set(profile["details"]):
            issues.append("DETAIL_FIELDS_MISSING")
        if raw["passed"]:
            for key, expected in checks["checks"].items():
                if type(actual.get(key)) is not type(expected) or actual.get(key) != expected:
                    issues.append("CASE_CONTRACT_MISMATCH:" + key)
        reported = profile["reported_rows"][raw["case"]]
        differences = []
        if reported["passed"] != raw["passed"]:
            differences.append("REPORTED_PASS_DIFFERS")
        if reported["expected_return"] is not None:
            if reported["expected_return"] != actual.get("expected_return"):
                differences.append("REPORTED_EXPECTED_DIFFERS")
            if reported["observed_return"] != actual.get("observed_return"):
                differences.append("REPORTED_OBSERVED_DIFFERS")
        if reported["elapsed_approximate"]:
            differences.append("REPORTED_TIME_APPROXIMATE")
        elif reported["elapsed_ms"] is not None and reported["elapsed_ms"] != raw["elapsed_ms"]:
            differences.append("REPORTED_TIME_DIFFERS")
        if reported["stub_calls"] is not None and reported["stub_calls"] != actual.get(
            "stub_calls"
        ):
            differences.append("REPORTED_STUB_COUNT_DIFFERS")
        error = raw.get("error_class")
        safe_error = (
            error
            if type(error) is str and error in ERRORS
            else "OTHER_EXCEPTION_CLASS"
            if error is not None
            else None
        )
        public = raw.get("public_error_source")
        allowed_paths = public_paths | {
            profile["helper_public"],
            "tests/stand/wave3_source_hooks.py",
        }
        public = (
            public
            if type(public) is str and public in allowed_paths
            else "UNKNOWN"
            if public is not None
            else None
        )
        line = raw.get("public_error_line")
        line = line if count(line) and 0 < line <= 200000 else None
        rows.append(
            {
                "case": raw["case"],
                "passed": raw["passed"],
                "elapsed_ms": raw["elapsed_ms"],
                "actual": actual,
                "source_expected_return": checks["source_expected_return"],
                "issues": issues,
                "report_differences": differences,
                "reported": reported,
                "error_class": safe_error,
                "public_error_source": public,
                "public_error_line": line,
            }
        )
    controls = {}
    for key in (
        "expected",
        "completed",
        "passed",
        "remaining_not_run",
        "source_files",
        "elapsed_ms",
        "unexpected_forbidden_io",
        "workload_subprocesses",
        "network_requests",
        "live_gateway_operations",
    ):
        value = data.get(key)
        controls[key] = value if count(value) else None
    for key in (*FLAGS, "audit_registered", "global_scope_stop"):
        value = data.get(key)
        controls[key] = value if type(value) is bool else None
    control_issues = []
    if controls["completed"] != len(rows):
        control_issues.append("COMPLETED_COUNT_MISMATCH")
    if final:
        require(
            data.get("marker")
            in (
                profile["marker_prefix"] + "_BATCH_RECORDED",
                profile["marker_prefix"] + "_BATCH_PARTIAL",
            ),
            "MARKER_REFUSED",
        )
        if data.get("scope") != profile["scope"]:
            control_issues.append("SCOPE_MISMATCH")
        if controls["expected"] != profile["count"] or controls["passed"] != sum(
            r["passed"] for r in rows
        ):
            control_issues.append("TOTAL_COUNTS_MISMATCH")
        if controls["remaining_not_run"] != profile["count"] - len(rows):
            control_issues.append("REMAINING_COUNT_MISMATCH")
        if controls["source_files"] != 116:
            control_issues.append("SOURCE_COUNT_MISMATCH")
        if any(controls[key] is not False for key in FLAGS):
            control_issues.append("RUNTIME_FLAG_NOT_FALSE")
        if controls["audit_registered"] is not True or controls["global_scope_stop"] is not False:
            control_issues.append("AUDIT_OR_SCOPE_NOT_CONFIRMED")
        if any(
            controls[key] != 0
            for key in (
                "unexpected_forbidden_io",
                "workload_subprocesses",
                "network_requests",
                "live_gateway_operations",
            )
        ):
            control_issues.append("ZERO_IO_NOT_CONFIRMED")
        if controls["elapsed_ms"] is None:
            control_issues.append("BATCH_TIME_NOT_COLLECTED")
    if final:
        expected_marker = profile["marker_prefix"] + (
            "_BATCH_RECORDED"
            if len(rows) == profile["count"] and all(r["passed"] for r in rows)
            else "_BATCH_PARTIAL"
        )
        if data.get("marker") != expected_marker:
            control_issues.append("MARKER_COUNTS_MISMATCH")
    complete = final and len(rows) == profile["count"]
    consistent = (
        complete and not control_issues and all(r["passed"] and not r["issues"] for r in rows)
    )
    return {
        "label": profile["label"],
        "state": "FINAL_RECORDED" if final else "CHECKPOINT_ONLY",
        "frozen_identity_verified": True,
        "selected_file": "summary.json" if final else "progress.json",
        "complete": complete,
        "all_case_checks_passed": consistent,
        "controls": controls,
        "control_issues": control_issues,
        "rows_collected": len(rows),
        "expected_rows": profile["count"],
        "remaining_not_collected": profile["count"] - len(rows),
        "rows": rows,
        "report_difference_rows": sum(bool(r["report_differences"]) for r in rows),
        "contract_mismatch_rows": sum(bool(r["issues"]) for r in rows),
    }


def collect_profile(profile):
    identity_verified = False
    try:
        root, paths = verify_frozen(profile)
        identity_verified = True
        for name in ("summary.json", "progress.json"):
            if (root / name).exists() or (root / name).is_symlink():
                return normalize(profile, decode(read(root / name)), name == "summary.json", paths)
        raise Refused("NO_RECORDED_RESULT")
    except Refused as exc:
        return {
            "label": profile["label"],
            "state": "READ_REFUSED",
            "reason": str(exc),
            "rows": [],
            "rows_collected": 0,
            "expected_rows": profile["count"],
            "remaining_not_collected": profile["count"],
            "all_case_checks_passed": False,
            "frozen_identity_verified": identity_verified,
        }
    except OSError:
        return {
            "label": profile["label"],
            "state": "READ_UNAVAILABLE",
            "reason": "SOURCE_NOT_READABLE",
            "rows": [],
            "rows_collected": 0,
            "expected_rows": profile["count"],
            "remaining_not_collected": profile["count"],
            "all_case_checks_passed": False,
            "frozen_identity_verified": identity_verified,
        }


def cell(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def render(result):
    lines = [
        "# Отчёт: XGW wave3ah — точное чтение сохранённых AG/AF/AE результатов",
        "",
        "Автоматические таблицы. Старые workers не запускались; src/сеть/службы не менялись.",
        "Readback не является повторным PASS или подтверждением происхождения owner files.",
        "AG остаётся на сверке архитектора. worker_exit_rc=NOT_COLLECTED.",
        "",
        "Delivery HEAD/tree: " + result["head"] + " / " + result["tree"],
        "",
    ]
    for profile in result["profiles"]:
        lines += [
            "## " + profile["label"],
            "",
            "State: " + profile["state"],
            "Rows: " + str(profile["rows_collected"]) + "/" + str(profile["expected_rows"]),
            "All source-contract checks passed: " + cell(profile["all_case_checks_passed"]),
            "Frozen identity verified: " + cell(profile["frozen_identity_verified"]),
            "",
        ]
        lines += [
            "Reference tested HEAD: " + profile["reference_tested_head"],
            "Reference helper/manifest/source: `" + cell(profile["reference_identity"]) + "`",
            "",
        ]
        if "reason" in profile:
            lines += ["Read reason: " + profile["reason"], ""]
        if "controls" in profile:
            lines += [
                "Controls: `" + cell(profile["controls"]) + "`",
                "Control issues: `" + cell(profile["control_issues"]) + "`",
                "Report difference rows: " + str(profile["report_difference_rows"]),
                "Contract mismatch rows: " + str(profile["contract_mismatch_rows"]),
                "",
            ]
        lines += [
            "|Case|actual passed|source expectation|actual expected|actual observed|"
            "receipt/gen/unknown/stubs|other actual fields|exact ms|"
            "issues/report differences|error source|",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for row in profile["rows"]:
            d = row["actual"]
            counts = [
                d.get(k)
                for k in (
                    "registry_receipts",
                    "registry_generation",
                    "unknown_writers",
                    "stub_calls",
                )
            ]
            other = {
                k: v
                for k, v in d.items()
                if k not in INT_DETAILS and k not in ("expected_return", "observed_return")
            }
            if "file_checked" in d:
                other["file_checked"] = d["file_checked"]
            error = [row["error_class"], row["public_error_source"], row["public_error_line"]]
            fields = [
                row["case"],
                cell(row["passed"]),
                cell(row["source_expected_return"]),
                cell(d.get("expected_return")),
                cell(d.get("observed_return")),
                cell(counts),
                cell(other),
                str(row["elapsed_ms"]),
                cell(row["issues"] + row["report_differences"]),
                cell(error),
            ]
            lines.append("|" + "|".join(fields) + "|")
        lines += [
            "",
            "Null не заменён ожиданием. Приблизительные времена из старых таблиц не копировались.",
            "",
        ]
    lines += [
        "## Исполнение AH и конечный режим — заполняет исполнитель",
        "",
        "Добавить фактические MSK/NNP/sudo/command rc/status/pool/connection/owner actions.",
        "Таблицы не редактировать. При unavailable/mismatch старые batches не запускать.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def load_result():
    raw = read(NOTES / "readout.json", 2097152)
    receipt = decode(read(NOTES / "receipt.json"))
    require(
        type(receipt) is dict
        and set(receipt) == {"readout_sha256", "report_data_sha256"}
        and hashlib.sha256(raw).hexdigest() == receipt["readout_sha256"],
        "READOUT_CHANGED",
    )
    preview = read(NOTES / "report-data.md", 2097152)
    require(
        hashlib.sha256(preview).hexdigest() == receipt["report_data_sha256"], "REPORT_DATA_CHANGED"
    )
    result = decode(raw)
    require(
        type(result) is dict
        and set(result) == {"schema", "head", "tree", "profiles"}
        and result["schema"] == 1
        and render(result) == preview,
        "READOUT_CHANGED",
    )
    return result


def main(command):
    require(os.geteuid() != 0, "OWNER_REQUIRED")
    private(NOTES, True)
    if command == "collect":
        create("collection-started.json", json_bytes({"started": True}))
        raw = read(NOTES / "contract.json", 1048576)
        require(hashlib.sha256(raw).hexdigest() == CONTRACT_SHA, "CONTRACT_HASH_MISMATCH")
        contract = decode(raw)
        require(
            type(contract) is dict
            and contract.get("schema") == 1
            and [p.get("label") for p in contract["profiles"]] == ["AG", "AF", "AE"],
            "CONTRACT_REFUSED",
        )
        identity = decode(read(NOTES / "source-current.json"))
        require(
            type(identity) is dict
            and set(identity) == {"head", "tree"}
            and all(type(v) is str and re.fullmatch(r"[0-9a-f]{40}", v) for v in identity.values()),
            "DELIVERY_IDENTITY_REFUSED",
        )
        profiles = []
        for profile in contract["profiles"]:
            observed = collect_profile(profile)
            observed["reference_tested_head"] = profile["tested_head"]
            observed["reference_identity"] = {
                "helper_sha256": profile["helper_sha256"],
                "manifest_sha256": profile["manifest_sha256"],
                "support_sha256": profile["support_sha256"],
                "source_files": profile["source_files"],
            }
            profiles.append(observed)
        result = {
            "schema": 1,
            **identity,
            "profiles": profiles,
        }
        payload = json_bytes(result)
        preview = render(result)
        create("readout.json", payload)
        create("report-data.md", preview)
        create(
            "receipt.json",
            json_bytes(
                {
                    "readout_sha256": hashlib.sha256(payload).hexdigest(),
                    "report_data_sha256": hashlib.sha256(preview).hexdigest(),
                }
            ),
        )
        print("EVIDENCE_READBACK_RECORDED")
    elif command == "show":
        result = load_result()
        print(
            json.dumps(
                [
                    {
                        "label": p["label"],
                        "state": p["state"],
                        "rows": p["rows_collected"],
                        "expected": p["expected_rows"],
                        "source_contract_consistent": p["all_case_checks_passed"],
                        "report_difference_rows": p.get("report_difference_rows"),
                    }
                    for p in result["profiles"]
                ]
            )
        )
    else:
        raise Refused("COMMAND_REFUSED")


if __name__ == "__main__":
    try:
        require(len(sys.argv) == 2, "COMMAND_REFUSED")
        main(sys.argv[1])
    except Refused as exc:
        print("EVIDENCE_READBACK_STOP", str(exc))
        raise SystemExit(3) from None
    except Exception:
        print("EVIDENCE_READBACK_STOP", "LOCAL_IO_OR_SCHEMA_ERROR")
        raise SystemExit(3) from None
