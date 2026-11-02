"""Synthetic historical files and mocked context only; no live gateway or tools."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def tool():
    spec = importlib.util.spec_from_file_location(
        "gate_diagnostic", Path(__file__).parent / "stand/wave3_gate_diagnostic.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def p_summary():
    return {
        "marker": "STOP_SINGLE_PROBE",
        "request_count": 0,
        "collection_error_class": "ValueError",
        "all_context_checks_ok": True,
        "bridge_config_unchanged": True,
        "before": {"realtime": 1000.0, "monotonic": 100.0},
        "after": {"realtime": 1002.0, "monotonic": 102.0},
    }


def mapping_fixture(m):
    basis = "FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN"
    old = {
        "marker": "READ_DIAGNOSTIC_RECORDED",
        "historical_summary_valid": True,
        "historical_mapping": basis,
    }
    mapping = {
        "mapping_basis": basis,
        "case_keys": {"SB-1": "1234abcd"},
        "n_summary_sha256": m.digest(b"N"),
        "current_config_sha256": m.digest(b"{}"),
    }
    return mapping, old


def test_historical_report_only_supports_stage_range_not_exact_exception_site():
    m = tool()
    result, begin, mono = m.p_evidence(p_summary())
    assert (begin, mono) == (1000.0, 100.0)
    assert (
        result["P_source_derived_stage_range"] == "AFTER_CONFIG_DIGEST_BEFORE_CURL_VERSION_EMISSION"
    )
    assert result["P_exception_site"] == "UNRECORDED"
    assert result["P_plan_persisted_flag_true"] is False


@pytest.mark.parametrize("changed", ["request_count", "all_context_checks_ok", "clock"])
def test_other_or_incomplete_historical_P_is_not_the_reported_run(changed):
    m, value = tool(), p_summary()
    if changed == "clock":
        value["after"]["realtime"] += 50
    else:
        value[changed] = 1 if changed == "request_count" else False
    with pytest.raises(m.GateStop):
        m.p_evidence(value)


def test_changed_config_is_specific_current_gate_without_leaking_hash_or_key(monkeypatch):
    m = tool()
    mapping, old = mapping_fixture(m)
    monkeypatch.setattr(m.bridge, "bridges", lambda _: [{"key": "1234abcd", "protocol": "vless"}])
    result = m.mapping_checks(mapping, old, b"N", b'{"changed":true}')
    assert result["current_first_unmet_gate"] == "current_config_digest_matches_O"
    assert result["current_static_checks"]["mapped_SB1_unique"] is True
    assert result["current_all_mapping_and_route_gates_ok"] is False
    assert "1234abcd" not in json.dumps(result) and m.digest(b"{}") not in json.dumps(result)


@pytest.mark.parametrize(
    "kind,gate",
    [
        ("N", "N_summary_digest_matches_O"),
        ("key", "SB1_key_shape_valid"),
        ("route", "current_route_canonical"),
    ],
)
def test_independent_read_gates_report_the_first_failure(monkeypatch, kind, gate):
    m = tool()
    mapping, old = mapping_fixture(m)

    def bridges(_):
        if kind == "route":
            raise ValueError("PRIVATE_URI")
        return [{"key": "1234abcd", "protocol": "vless"}]

    monkeypatch.setattr(m.bridge, "bridges", bridges)
    if kind == "key":
        mapping["case_keys"] = []
    result = m.mapping_checks(mapping, old, b"OTHER" if kind == "N" else b"N", b"{}")
    assert result["current_first_unmet_gate"] == gate
    assert "PRIVATE" not in json.dumps(result)


def test_file_times_are_supporting_only_and_a_new_file_is_not_historical_proof():
    m = tool()
    info = SimpleNamespace(st_mtime=900.0, st_ctime=901.0)
    result = m.time_support(1000.0, 100.0, info, now=1100.0, current_mono=200.0)
    assert result["current_config_relation_to_P"] == "FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN"
    info.st_ctime = 1050.0
    assert (
        m.time_support(1000.0, 100.0, info, now=1100.0, current_mono=200.0)[
            "current_config_relation_to_P"
        ]
        == "UNCONFIRMED"
    )
    info.st_ctime = 901.0
    assert (
        m.time_support(1000.0, 100.0, info, now=1100.0, current_mono=5.0)[
            "current_config_relation_to_P"
        ]
        == "UNCONFIRMED"
    )


def test_private_failures_are_fixed_codes_never_raw_exceptions(tmp_path, monkeypatch):
    m = tool()

    def unsafe(*args):
        raise ValueError("PRIVATE_PASSWORD_OR_URI")

    monkeypatch.setattr(m.diagnostic, "checked", unsafe)
    with pytest.raises(m.GateStop) as caught:
        m.read_json(tmp_path / "x", "O_MAPPING")
    assert caught.value.stage == "O_MAPPING"
    assert caught.value.status == "OWNER_MODE_OR_KIND_INVALID"
    assert "PRIVATE" not in str(caught.value)


def test_started_file_prevents_new_diagnostic_run(tmp_path, monkeypatch):
    m = tool()
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m.diagnostic, "checked", lambda path, *a: path)
    monkeypatch.setattr(m.sys, "argv", ["q", "run"])
    (tmp_path / "started.json").write_text("{}")
    monkeypatch.setattr(m.reader, "snapshot", lambda: pytest.fail("no gateway reads expected"))
    with pytest.raises(m.GateStop) as caught:
        m.main()
    assert caught.value.status == "ALREADY_STARTED_OR_INVALID_MODE"


@pytest.mark.parametrize("missing", [False, True])
def test_main_records_changed_config_without_probe_or_blocks_missing_evidence(
    tmp_path, monkeypatch, missing
):
    m = tool()
    q, p, o, n = [tmp_path / name for name in ("Q", "P", "O", "N")]
    for directory in (q, p, o, n):
        directory.mkdir()
    stand = Path(__file__).parent / "stand"
    (p / "wave3_single_bridge.py").write_bytes((stand / "wave3_single_bridge.py").read_bytes())
    (p / "summary.json").write_text(json.dumps(p_summary()))
    (n / "wave3_bridge_probe.py").write_bytes((stand / "wave3_bridge_probe.py").read_bytes())
    n_value = {"dummy": True}
    n_raw = json.dumps(n_value).encode()
    (n / "summary.json").write_bytes(n_raw)
    mapping, old = mapping_fixture(m)
    mapping["n_summary_sha256"] = m.digest(n_raw)
    (o / "summary.json").write_text(json.dumps(old))
    if not missing:
        (o / "mapping-private.json").write_text(json.dumps(mapping))
    config = tmp_path / "config.json"
    config.write_bytes(b'{"changed":true}')
    for name, value in (("ROOT", q), ("P_ROOT", p), ("O_ROOT", o), ("N_ROOT", n)):
        monkeypatch.setattr(m, name, value)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m.sys, "argv", ["q", "run"])
    monkeypatch.setattr(
        m.diagnostic,
        "checked",
        lambda path, *a: path if path.exists() else (_ for _ in ()).throw(FileNotFoundError()),
    )
    monkeypatch.setattr(m.diagnostic, "historical", lambda value: None)
    monkeypatch.setattr(m.bridge, "bridges", lambda _: [{"key": "1234abcd", "protocol": "vless"}])
    monkeypatch.setattr(m.bridge, "targets", lambda _: ["https://example.test"])
    monkeypatch.setattr(m.bridge, "process_ready", lambda _: True)
    monkeypatch.setattr(m.bridge, "pin_token", lambda: b"same")
    monkeypatch.setattr(
        m.reader, "PATHS", SimpleNamespace(singbox_config_file=config, config_file=config)
    )
    monkeypatch.setattr(m.reader.config, "load", lambda _: (None, []))
    monkeypatch.setattr(m.reader, "public", lambda _: {"capture": True})
    monkeypatch.setattr(m.shutil, "which", lambda _: "/usr/bin/curl")
    before = {
        "singbox": {"process_identity": [42, "start"]},
        "boot_private": "same",
        "hashes_private": [b"1", b"2", b"3"],
        "unit_private": {unit: {"MainPID": "42"} for unit in m.reader.UNITS},
    }
    monkeypatch.setattr(m.reader, "snapshot", lambda: before)
    monkeypatch.setattr(m.bridge, "request", lambda *a: pytest.fail("no network probes allowed"))
    rc = m.main()
    result = json.loads((q / "summary.json").read_text())
    assert result["Q_network_requests"] == 0
    assert result["P_exception_site"] == "UNRECORDED"
    if missing:
        assert rc == 3 and result["stop_code"] == "MISSING" and result["stage"] == "O_MAPPING"
        assert result["bridge_config_unchanged"] is None
    else:
        assert rc == 0 and result["marker"] == "GATE_DIAGNOSTIC_RECORDED"
        assert result["current_first_unmet_gate"] == "current_config_digest_matches_O"
        assert result["all_context_checks_ok"] is True
    assert "1234abcd" not in json.dumps(result) and "example.test" not in json.dumps(result)
