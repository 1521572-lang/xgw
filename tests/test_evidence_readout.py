import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def reader():
    stand = Path(__file__).parents[1] / "tests/stand"
    spec = importlib.util.spec_from_file_location(
        "ah_reader_narrow", stand / "wave3_evidence_readout.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    profile = copy.deepcopy(
        json.loads((stand / "wave3_evidence_contract.json").read_bytes())["profiles"][0]
    )
    case = "S_UNAVAILABLE_EMPTY__LEGACY"
    profile.update(
        count=1,
        ids=[case],
        rules={case: profile["rules"][case]},
        reported_rows={case: profile["reported_rows"][case]},
    )
    details = dict.fromkeys(profile["details"])
    details.update(
        expected_return="FALSE",
        observed_return="FALSE",
        registry_receipts=0,
        registry_generation=0,
        unknown_writers=0,
        stub_calls=0,
    )
    row = {"case": case, "passed": True, "details": details, "elapsed_ms": 117}
    data = {
        "marker": "POOL_FLOW_BATCH_RECORDED",
        "scope": profile["scope"],
        "expected": 1,
        "completed": 1,
        "passed": 1,
        "remaining_not_run": 0,
        "source_files": 116,
        "elapsed_ms": 122,
        "unexpected_forbidden_io": 0,
        "workload_subprocesses": 0,
        "network_requests": 0,
        "live_gateway_operations": 0,
        "audit_registered": True,
        "global_scope_stop": False,
        "cases": [row],
        **dict.fromkeys(module.FLAGS, False),
    }
    return module, profile, data


def test_actual_false_is_kept_and_report_true_detected(reader):
    module, profile, data = reader
    result = module.normalize(profile, data, True, set())
    assert result["all_case_checks_passed"] is True
    row = result["rows"][0]
    assert row["actual"]["expected_return"] == row["actual"]["observed_return"] == "FALSE"
    assert "REPORTED_EXPECTED_DIFFERS" in row["report_differences"]
    assert "REPORTED_TIME_APPROXIMATE" in row["report_differences"]
    assert row["elapsed_ms"] == 117


def test_boolean_is_not_accepted_as_numeric_counter(reader):
    module, profile, data = reader
    data["cases"][0]["details"]["registry_receipts"] = False
    with pytest.raises(module.Refused, match="DETAIL_TYPE_REFUSED"):
        module.normalize(profile, data, True, set())


def test_unexpected_private_field_is_refused(reader):
    module, profile, data = reader
    data["cases"][0]["details"]["private_config"] = "do-not-publish"
    with pytest.raises(module.Refused, match="DETAIL_SCHEMA_REFUSED"):
        module.normalize(profile, data, True, set())


def test_failed_checkpoint_keeps_nulls_and_never_becomes_pass(reader):
    module, profile, data = reader
    row = data["cases"][0]
    row.update(passed=False, details=dict.fromkeys(profile["details"]))
    checkpoint = {"final": False, "completed": 1, "cases": [row]}
    result = module.normalize(profile, checkpoint, False, set())
    assert result["all_case_checks_passed"] is False
    assert result["rows"][0]["actual"]["expected_return"] is None
    assert result["rows"][0]["actual"]["registry_receipts"] is None
    assert result["controls"]["network_requests"] is None


def test_unknown_exception_and_private_path_do_not_leak(reader):
    module, profile, data = reader
    row = data["cases"][0]
    row.update(
        passed=False,
        error_class="private-token",
        public_error_source="/home/private/config",
        public_error_line=7,
        reason="private-exception-text",
    )
    result = module.normalize(profile, data, True, set())
    output = json.dumps(result)
    assert "private-token" not in output and "/home/private" not in output
    assert "private-exception-text" not in output
    assert result["rows"][0]["error_class"] == "OTHER_EXCEPTION_CLASS"


def test_partial_marker_cannot_support_all_pass(reader):
    module, profile, data = reader
    data["marker"] = "POOL_FLOW_BATCH_PARTIAL"
    result = module.normalize(profile, data, True, set())
    assert result["all_case_checks_passed"] is False
    assert "MARKER_COUNTS_MISMATCH" in result["control_issues"]


def test_read_refuses_symlink_and_wrong_mode(reader, tmp_path):
    module, _, _ = reader
    target = tmp_path / "data.json"
    target.write_bytes(b"{}")
    target.chmod(0o600)
    link = tmp_path / "alias.json"
    link.symlink_to(target)
    with pytest.raises(module.Refused, match="METADATA_REFUSED"):
        module.read(link)
    target.chmod(0o644)
    with pytest.raises(module.Refused, match="METADATA_REFUSED"):
        module.read(target)


def test_duplicate_json_does_not_pass(reader):
    module, _, _ = reader
    with pytest.raises(module.Refused, match="DUPLICATE_JSON_KEY"):
        module.decode(b'{"cases":[],"cases":[]}')


def test_generated_report_roundtrip_and_edit_detection(reader, tmp_path, monkeypatch):
    module, profile, data = reader
    tmp_path.chmod(0o700)
    monkeypatch.setattr(module, "NOTES", tmp_path)
    observed = module.normalize(profile, data, True, set())
    observed["reference_tested_head"] = profile["tested_head"]
    observed["reference_identity"] = {"helper_sha256": profile["helper_sha256"]}
    result = {"schema": 1, "head": "a" * 40, "tree": "b" * 40, "profiles": [observed]}
    raw, preview = module.json_bytes(result), module.render(result)
    module.create("readout.json", raw)
    module.create("report-data.md", preview)
    module.create(
        "receipt.json",
        module.json_bytes(
            {
                "readout_sha256": hashlib.sha256(raw).hexdigest(),
                "report_data_sha256": hashlib.sha256(preview).hexdigest(),
            }
        ),
    )
    assert module.load_result() == result
    assert b"117" in preview and b"~110" not in preview
    (tmp_path / "report-data.md").write_bytes(preview + b"edited")
    with pytest.raises(module.Refused, match="REPORT_DATA_CHANGED"):
        module.load_result()
