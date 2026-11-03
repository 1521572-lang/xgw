"""JSON-container regression and batch fixtures only; no real network or services."""

import copy
import importlib.util
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest


def tool():
    spec = importlib.util.spec_from_file_location(
        "coverage_batch", Path(__file__).parent / "stand/wave3_coverage_batch.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def node():
    return {
        "protocol": "vless",
        "settings": {
            "vnext": [{"address": "PRIVATE_HOST", "port": 443, "users": [{"id": "PRIVATE_UUID"}]}]
        },
        "streamSettings": {
            "security": "reality",
            "realitySettings": {
                "serverName": "PRIVATE_SNI",
                "publicKey": "PRIVATE_KEY",
                "shortId": "0011",
            },
        },
    }


@pytest.mark.parametrize(
    "shape", ["array_configs", "nested_arrays", "single_config", "single_outbound"]
)
def test_complete_JSON_config_containers_are_expanded_independently(shape, monkeypatch):
    m = tool()
    monkeypatch.setattr(m.source, "parse_body", lambda *a: pytest.fail("product parser forbidden"))
    n = node()
    value = {"outbounds": [n]}
    if shape == "array_configs":
        value = [value, copy.deepcopy(value)]
    elif shape == "nested_arrays":
        value = [[value]]
    elif shape == "single_outbound":
        value = n
    rows, meta = m.expanded_records(json.dumps(value).encode())
    assert len(rows) == (2 if shape == "array_configs" else 1)
    assert rows[0]["public_key"] == "PRIVATE_KEY"
    assert "PRIVATE" not in json.dumps(meta)
    if shape == "array_configs":
        assert meta["legacy_T_supported_on_same_bytes"] == 0


def test_T_cumulative_samples_are_not_added_as_total_traffic():
    m = tool()
    summary = {
        "phases": {
            "T7_passive_LAN": {
                "data": {
                    "samples": [
                        {"LAN_rx_bytes_delta": 1, "LAN_tx_bytes_delta": 10},
                        {"LAN_rx_bytes_delta": 2, "LAN_tx_bytes_delta": 20},
                        {"LAN_rx_bytes_delta": 3, "LAN_tx_bytes_delta": 30},
                    ]
                }
            }
        }
    }
    result = m.audit_T_samples(summary, reported=(6, 60))
    assert result["LAN_rx_bytes_delta"]["last_cumulative_value"] == 3
    assert result["LAN_rx_bytes_delta"]["reported_table_matches_last"] is False
    assert result["LAN_rx_bytes_delta"]["reported_table_matches_sum"] is True
    assert m.audit_T_samples({})["LAN_rx_bytes_delta"]["last_cumulative_value"] is None


def test_duplicate_JSON_keys_do_not_silently_choose_last_secret():
    m = tool()
    with pytest.raises(ValueError, match="JSON_DUPLICATE_KEYS"):
        m.expanded_records(b'{"outbounds":[],"outbounds":[]}')


def test_recursive_shape_limit_is_reported_not_presented_as_full_coverage():
    m = tool()
    value = node()
    for _ in range(12):
        value = [value]
    rows, meta = m.expanded_records(json.dumps(value).encode())
    assert rows == [] and meta["coverage_limited"] is True


def test_semantic_config_diff_is_private_and_distinguishes_auth_ports_and_endpoint():
    m = tool()
    old = {
        "inbounds": [
            {"tag": "PRIVATE_TAG", "listen_port": 1234, "users": [{"password": "OLD_SECRET"}]}
        ],
        "outbounds": [{"tag": "PRIVATE_OUT", "server": "PRIVATE_HOST"}],
    }
    current = copy.deepcopy(old)
    current["inbounds"][0]["listen_port"] = 2345
    current["inbounds"][0]["users"][0]["password"] = "NEW_SECRET"
    current["outbounds"][0]["server"] = "OTHER_PRIVATE_HOST"
    result = m.semantic_difference(current, old)
    assert (
        result["shared_bridge_ports_changed"]
        == result["shared_bridge_user_objects_changed"]
        == result["shared_endpoint_objects_changed"]
        == 1
    )
    assert "PRIVATE" not in json.dumps(result) and "SECRET" not in json.dumps(result)
    assert m.semantic_difference(old, copy.deepcopy(old))["json_values_equal"] is True


def test_keyed_scan_has_node_identity_but_does_not_invent_core_identity(tmp_path, monkeypatch):
    m = tool()
    db = tmp_path / "db"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE nodes(fingerprint TEXT,tag TEXT); "
        "CREATE TABLE scans(probe_tag TEXT,verdict TEXT,bytes INT,seconds REAL,ts REAL);"
    )
    conn.execute("INSERT INTO nodes VALUES('1234abcd','spare-de-1234')")
    conn.execute("INSERT INTO scans VALUES('probe-de-1234','OK',305,0.5,1000)")
    conn.commit()
    conn.close()
    old = db.read_bytes()
    monkeypatch.setattr(m.reader, "PATHS", SimpleNamespace(db_file=db))
    monkeypatch.setattr(m.bridge, "bridges", lambda _: [{"key": "1234abcd"}])
    result = m.keyed_health({}, "1234abcd")
    assert result["mapped_scans"] == 1 and result["reference_case"]["bytes"] == 305
    assert result["reference_case"]["scan_core_identity"] == "UNSPECIFIED_IN_SCHEMA"
    assert result["reference_case"]["fresh_active_check"] is False
    assert "1234abcd" not in json.dumps(result) and db.read_bytes() == old


def test_effective_unit_properties_are_fixed_bools_not_paths_or_accounts(monkeypatch):
    m = tool()

    def fake(argv, **kw):
        sb = argv[2] == "xgw-singbox"
        user = "xgw-singbox" if sb else "xray"
        caps = "" if sb else "cap_net_admin cap_net_bind_service"
        text = (
            f"User={user}\nGroup={user}\nAmbientCapabilities={caps}\nCapabilityBoundingSet={caps}\n"
            "NoNewPrivileges=yes\nProtectSystem=strict\nProtectHome=yes\nPrivateTmp=yes\nReadOnlyPaths=/run\n"
            "ReadWritePaths=\nRestrictSUIDSGID=yes\nRestrictRealtime=yes\nLockPersonality=yes\n"
            "RestrictAddressFamilies=AF_UNIX AF_NETLINK AF_INET AF_INET6\n"
        )
        return SimpleNamespace(returncode=0, stdout=text.encode())

    monkeypatch.setattr(m.subprocess, "run", fake)
    result = m.effective_units()
    assert result["SINGBOX"]["ambient_caps_expected"] is True
    assert result["XRAY"]["ambient_caps_expected"] is True
    assert result["SINGBOX"]["run_explicit_read_only"] is True
    assert "/run" not in json.dumps(result) and "xgw-singbox" not in json.dumps(result)


def test_missing_optional_generation_does_not_trigger_reconstruction(tmp_path, monkeypatch):
    m = tool()
    monkeypatch.setattr(
        m.reader,
        "PATHS",
        SimpleNamespace(
            singbox_last_good_file=tmp_path / "lg", singbox_pending_file=tmp_path / "pending"
        ),
    )
    result = m.generation_summary(b"{}", {}, {}, {})
    assert result["last_good"] == {"available": False, "reason": "ABSENT"}
    assert result["pending"]["available"] is False
    assert not list(tmp_path.iterdir())


def test_start_guard_never_spawns_second_worker(tmp_path, monkeypatch):
    m = tool()
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m.diagnostic, "checked", lambda p, *a: p)
    monkeypatch.setattr(m.sys, "argv", ["u", "start"])
    (tmp_path / "started.json").write_text("{}")
    monkeypatch.setattr(
        m.subprocess, "Popen", lambda *a, **kw: pytest.fail("second spawn forbidden")
    )
    with pytest.raises(ValueError, match="already started"):
        m.main()


@pytest.mark.parametrize("history", [False, True])
def test_all_eight_phases_continue_safely_after_optional_history_failure(
    tmp_path, monkeypatch, history
):
    m = tool()
    run = tmp_path / "U"
    run.mkdir()
    monkeypatch.setattr(m, "ROOT", run)
    old = tmp_path / "T"
    monkeypatch.setattr(m, "OLD", old)
    sb = tmp_path / "sb"
    xr = tmp_path / "xr"
    value = {"outbounds": []}
    sb.write_text(json.dumps(value))
    xr.write_text(json.dumps(value))
    monkeypatch.setattr(m, "read_config", lambda p: (p.read_bytes(), json.loads(p.read_bytes())))
    if history:
        old.mkdir()
        (old / "wave3_extended_batch.py").write_bytes(
            (Path(__file__).parent / "stand/wave3_extended_batch.py").read_bytes()
        )
        (old / "summary.json").write_text(
            json.dumps({"marker": "EXTENDED_BATCH_RECORDED", "all_context_checks_ok": True})
        )
        (old / "baseline-private.json").write_text(
            json.dumps({"source_digests": {}, "reference_case_key": "1234abcd"})
        )
    monkeypatch.setattr(m.diagnostic, "checked", lambda p, *a: p)
    monkeypatch.setattr(
        m.reader,
        "PATHS",
        SimpleNamespace(singbox_config_file=sb, xray_config_file=xr, config_file=tmp_path / "cfg"),
    )
    monkeypatch.setattr(m.reader.config, "load", lambda _: (None, []))
    monkeypatch.setattr(m, "read_sources", lambda _: ([], {}, {"supported_records": 0}))
    monkeypatch.setattr(m.batch, "whole_graph", lambda *a: {"fixture": True})
    monkeypatch.setattr(m, "generation_summary", lambda *a: {"fixture": True})
    monkeypatch.setattr(m, "keyed_health", lambda *a: {"query_ok": False})
    monkeypatch.setattr(m, "effective_units", lambda: {"query_ok": False})
    monkeypatch.setattr(m, "writer_journal", lambda: {"query_ok": False})
    monkeypatch.setattr(m.single, "request", lambda *a: pytest.fail("no network"))
    monkeypatch.setattr(m.bridge, "process_ready", lambda _: True)
    monkeypatch.setattr(m.bridge, "pin_token", lambda: b"same")
    monkeypatch.setattr(m.reader, "public", lambda _: {"capture": True})
    snap = {
        "singbox": {"process_identity": [42, "start"]},
        "boot_private": "boot",
        "hashes_private": [b"1", b"2", b"3"],
        "unit_private": {unit: {"MainPID": "42"} for unit in m.reader.UNITS},
    }
    monkeypatch.setattr(m.reader, "snapshot", lambda: copy.deepcopy(snap))
    m.worker()
    result = json.loads((run / "summary.json").read_text())
    assert len(result["phases"]) == 8 and result["network_requests"] == 0
    assert result["marker"] == ("COVERAGE_BATCH_RECORDED" if history else "COVERAGE_BATCH_PARTIAL")
    assert result["phases"]["U8_writer_journal_counts"]["collection"] == "RECORDED"
