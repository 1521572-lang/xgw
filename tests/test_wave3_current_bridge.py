"""New-baseline orchestration fixtures; never uses live tools, requests or services."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def tool():
    spec = importlib.util.spec_from_file_location(
        "current_bridge", Path(__file__).parent / "stand/wave3_current_bridge.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def q_value():
    names = (
        "O_recorded_marker O_historical_summary_valid O_mapping_basis_supported "
        "mapping_basis_supported N_summary_digest_matches_O SB1_key_shape_valid "
        "current_route_canonical mapped_SB1_unique mapped_SB1_vless "
        "current_routing_marks_absent"
    ).split()
    checks = dict.fromkeys(names, True)
    checks["current_config_digest_matches_O"] = False
    return {
        "marker": "GATE_DIAGNOSTIC_RECORDED",
        "historical_P_valid": True,
        "P_request_count": 0,
        "Q_network_requests": 0,
        "all_context_checks_ok": True,
        "current_first_unmet_gate": "current_config_digest_matches_O",
        "current_static_checks": checks,
    }


def references(m):
    basis = "FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN"
    old = {
        "marker": "READ_DIAGNOSTIC_RECORDED",
        "historical_summary_valid": True,
        "historical_mapping": basis,
    }
    mapping = {
        "mapping_basis": basis,
        "n_summary_sha256": m.single.digest(b"{}"),
        "case_keys": {"SB-1": "1234abcd"},
        "current_config_sha256": "OLD_PRIVATE_HASH",
    }
    return mapping, old


def test_new_baseline_allows_cross_run_drift_but_selects_only_the_reference_key(monkeypatch):
    m = tool()
    mapping, old = references(m)
    monkeypatch.setattr(
        m.bridge,
        "bridges",
        lambda _: [
            {"key": "00000000", "protocol": "vless"},
            {"key": "1234abcd", "protocol": "vless"},
        ],
    )
    selected = m.current_selection(mapping, old, b"{}", b'{"new":true}')
    assert selected["key"] == "1234abcd"  # Never the first/new healthy alternative.


@pytest.mark.parametrize("change", ["bad_N", "absent_key", "wrong_protocol"])
def test_invalid_reference_or_current_selection_stays_blocked(monkeypatch, change):
    m = tool()
    mapping, old = references(m)
    monkeypatch.setattr(
        m.bridge,
        "bridges",
        lambda _: (
            []
            if change == "absent_key"
            else [
                {"key": "1234abcd", "protocol": "trojan" if change == "wrong_protocol" else "vless"}
            ]
        ),
    )
    with pytest.raises(m.Stop):
        m.current_selection(mapping, old, b"other" if change == "bad_N" else b"{}", b"{}")


def test_Q_must_be_the_reported_drift_case_not_a_generic_success():
    m = tool()
    value = q_value()
    m.q_evidence(value)
    value["current_static_checks"]["mapped_SB1_unique"] = False
    with pytest.raises(m.Stop) as caught:
        m.q_evidence(value)
    assert caught.value.code == "Q_EVIDENCE_MISMATCH"


def test_exclusive_started_prevents_retry_without_touching_gateway(tmp_path, monkeypatch):
    m = tool()
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m.diagnostic, "checked", lambda path, *a: path)
    monkeypatch.setattr(m.sys, "argv", ["r", "run"])
    (tmp_path / "started.json").write_text("{}")
    monkeypatch.setattr(m.reader, "snapshot", lambda: pytest.fail("no gateway reads"))
    with pytest.raises(m.Stop) as caught:
        m.main()
    assert caught.value.code == "ALREADY_STARTED_OR_INVALID_MODE"


@pytest.mark.parametrize("change", ["none", "pre_change", "after_change", "bad_Q"])
def test_single_request_has_private_plan_beforehand_and_fail_closed_context(
    tmp_path, monkeypatch, change
):
    m = tool()
    r, q, o, n = [tmp_path / name for name in ("R", "Q", "O", "N")]
    for directory in (r, q, o, n):
        directory.mkdir()
    stand = Path(__file__).parent / "stand"
    (q / "wave3_gate_diagnostic.py").write_bytes((stand / "wave3_gate_diagnostic.py").read_bytes())
    value = q_value()
    if change == "bad_Q":
        value["P_request_count"] = 1
    (q / "summary.json").write_text(json.dumps(value))
    (n / "summary.json").write_bytes(b"{}")
    (n / "wave3_bridge_probe.py").write_bytes((stand / "wave3_bridge_probe.py").read_bytes())
    mapping, old = references(m)
    (o / "summary.json").write_text(json.dumps(old))
    (o / "mapping-private.json").write_text(json.dumps(mapping))
    config = tmp_path / "config.json"
    config.write_bytes(b"{}")
    for name, val in (("ROOT", r), ("Q_ROOT", q), ("O_ROOT", o)):
        monkeypatch.setattr(m, name, val)
    monkeypatch.setattr(m.diagnostic, "OLD", n)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m.sys, "argv", ["r", "run"])
    monkeypatch.setattr(m.diagnostic, "checked", lambda path, *a: path)
    monkeypatch.setattr(m.diagnostic, "historical", lambda _: None)
    monkeypatch.setattr(m.diagnostic, "endpoint_summary", lambda *a: {"protocol": "vless"})
    monkeypatch.setattr(
        m.bridge, "bridges", lambda _: [{"key": "1234abcd", "protocol": "vless", "port": 12345}]
    )
    monkeypatch.setattr(m.bridge, "targets", lambda _: ["https://example.test"])
    monkeypatch.setattr(m.bridge, "process_ready", lambda _: True)
    monkeypatch.setattr(m.bridge, "owns_listener", lambda *a: True)
    monkeypatch.setattr(m.bridge, "pin_token", lambda: b"same")
    monkeypatch.setattr(
        m.reader, "PATHS", SimpleNamespace(singbox_config_file=config, config_file=config)
    )
    monkeypatch.setattr(m.reader.config, "load", lambda _: (None, []))
    monkeypatch.setattr(m.reader, "public", lambda _: {"capture": True})
    monkeypatch.setattr(m.shutil, "which", lambda _: "curl")
    monkeypatch.setattr(
        m.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=b"curl 8.5.0")
    )
    snapshots = []

    def snapshot():
        snapshots.append(1)
        if (len(snapshots) == 2 and change == "pre_change") or (
            len(snapshots) == 3 and change == "after_change"
        ):
            config.write_bytes(b'{"changed":true}')
        return {
            "singbox": {"process_identity": [42, "start"]},
            "boot_private": "boot",
            "hashes_private": [b"a", b"b", b"c"],
            "unit_private": {unit: {"MainPID": "42"} for unit in m.reader.UNITS},
        }

    monkeypatch.setattr(m.reader, "snapshot", snapshot)
    calls = []

    def request(*args):
        plan = json.loads((r / "plan-private.json").read_text())
        assert plan["config_sha256"] == m.single.digest(b"{}")
        assert plan["historical_endpoint_identity"] == "UNPROVEN"
        calls.append(1)
        return {"body_ok": False, "curl_rc": 97}

    monkeypatch.setattr(m.single, "request", request)
    monkeypatch.setattr(m.single, "journal", lambda *a: {"query_ok": False})
    rc = m.main()
    result = json.loads((r / "summary.json").read_text())
    assert len(calls) == (1 if change in ("none", "after_change") else 0)
    assert result["request_count"] == len(calls)
    assert rc == (0 if change == "none" else 3)
    assert result["marker"] == (
        "CURRENT_BRIDGE_RECORDED" if change == "none" else "STOP_CURRENT_BRIDGE"
    )
    assert "1234abcd" not in json.dumps(result) and "example.test" not in json.dumps(result)
    if change == "pre_change":
        assert result["stop_code"] == "PRE_REQUEST_CONTEXT_CHANGED"
    if change == "bad_Q":
        assert result["stage"] == "Q_EVIDENCE" and result["stop_code"] == "Q_EVIDENCE_MISMATCH"
        assert result["bridge_config_unchanged"] is None
    if change == "after_change":
        assert result["stop_code"] == "AFTER_CONTEXT_OR_LISTENER_UNCONFIRMED"
