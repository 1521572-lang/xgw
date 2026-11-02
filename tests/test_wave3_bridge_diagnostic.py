"""Retrospective classifiers/SQLite fixtures only; no live logs, probes or gateway."""

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest


def tool():
    spec = importlib.util.spec_from_file_location(
        "bridge_diagnostic", Path(__file__).parent / "stand/wave3_bridge_diagnostic.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def historical():
    return {
        "marker": "BRIDGE_PROBES_RECORDED",
        "candidates_total": 71,
        "selected_count": 2,
        "target_count": 2,
        "cases": [
            {
                "case": "SB-1",
                "protocol": "vless",
                "body_ok": False,
                "attempts": [
                    {"target": index, "curl_rc": 97, "http_status": 0, "bytes": 0, "body_ok": False}
                    for index in (1, 2)
                ],
            },
            {
                "case": "SB-2",
                "protocol": "vless",
                "body_ok": True,
                "attempts": [{"http_status": 206, "bytes": 32769, "body_ok": True}],
            },
        ],
        "before": {"realtime": 1000.0, "monotonic": 100.0},
        "after": {"realtime": 1004.0, "monotonic": 104.0},
    }


@pytest.mark.parametrize("change", ["wrong_failure", "clock_jump", "wrong_count"])
def test_other_run_or_ambiguous_time_is_not_historical_evidence(change):
    module = tool()
    data = historical()
    assert module.historical(data) == (1000.0, 1004.0, 100.0)
    if change == "wrong_failure":
        data["cases"][0]["attempts"][0]["curl_rc"] = 0
    elif change == "clock_jump":
        data["after"]["realtime"] = 1014.0
    else:
        data["candidates_total"] = 70
    with pytest.raises(ValueError):
        module.historical(data)


def test_related_tags_do_not_match_other_fingerprints_and_raw_messages_stay_private():
    module = tool()
    lines = [
        {
            "MESSAGE": (
                "outbound/vless[sb-out-1234abcd-d]: PRIVATE_IP permission denied TLS handshake"
            ),
            "PRIORITY": "3",
        },
        {"MESSAGE": "sb-out-1234abcd9-d: PRIVATE_IP connection refused", "PRIORITY": "3"},
    ]
    result = module.journal_summary(
        b"\n".join(json.dumps(x).encode() for x in lines), {"SB-1": "1234abcd"}
    )
    assert result["related"]["SB-1"]["matched_rows"] == 1
    assert result["related"]["SB-1"]["categories"]["permission"] == 1
    assert result["related"]["SB-1"]["categories"]["tls_auth_or_handshake"] == 1
    assert result["global_categories"]["refused"] == 1
    assert "PRIVATE" not in json.dumps(result) and "1234abcd" not in json.dumps(result)


def test_limited_or_unreadable_log_is_not_zero_error_coverage():
    module = tool()
    result = module.journal_summary(b"not-json\n" + b"{}\n" * 2000, {})
    assert result["truncated"] is True and result["parse_errors"] == 1 and result["rows"] == 2001


def test_current_endpoint_attributes_never_export_addresses_or_credentials():
    module = tool()
    cfg = {
        "outbounds": [
            {
                "tag": "sb-out-1234abcd-d",
                "type": "vless",
                "server": "10.0.0.9",
                "server_port": 23456,
                "uuid": "PRIVATE_UUID",
                "bind_interface": "PRIVATE_NIC",
                "tls": {
                    "enabled": True,
                    "server_name": "PRIVATE_SNI",
                    "reality": {"enabled": True},
                },
            }
        ]
    }
    result = module.endpoint_summary(cfg, "1234abcd")
    assert (
        result["server_kind"] == "non_global_literal" and result["bind_interface_present"] is True
    )
    assert result["reality_enabled"] is True and result["tls_server_name_present"] is True
    public = json.dumps(result)
    assert all(value not in public for value in ("PRIVATE", "10.0.0.9", "23456", "1234abcd"))


@pytest.mark.parametrize(
    "stamp,relation", [(900.0, "before"), (1002.0, "during"), (1100.0, "after")]
)
def test_latest_scan_after_N_cannot_be_called_a_preexisting_failure(tmp_path, stamp, relation):
    module = tool()
    database = tmp_path / "state.db"
    conn = sqlite3.connect(database)
    conn.executescript(
        "CREATE TABLE nodes(fingerprint TEXT,tag TEXT); "
        "CREATE TABLE scans(probe_tag TEXT,verdict TEXT,bytes INT,seconds REAL,ts REAL);"
    )
    conn.execute("INSERT INTO nodes VALUES (?,?)", ("1234abcdPRIVATE", "spare-de-1234"))
    conn.execute(
        "INSERT INTO scans VALUES (?,?,?,?,?)", ("probe-de-1234", "CONNECT_FAIL", 0, 1.0, stamp)
    )
    conn.commit()
    conn.close()
    old = database.read_bytes()
    result = module.scan_summary(database, "1234abcd", 1000.0, 1004.0)
    assert result["relation_to_N"] == relation and result["verdict"] == "CONNECT_FAIL"
    assert "PRIVATE" not in json.dumps(result) and "spare-de" not in json.dumps(result)
    assert database.read_bytes() == old


def test_missing_database_is_unknown_and_not_created(tmp_path):
    module = tool()
    database = tmp_path / "absent.db"
    assert module.scan_summary(database, "1234abcd", 1000, 1004) == {"query_ok": False}
    assert not database.exists()
