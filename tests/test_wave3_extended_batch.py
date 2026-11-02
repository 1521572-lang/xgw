"""Only local synthetic records and mocked batch orchestration; no real waiting/network."""

import base64
import copy
import importlib.util
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest


def tool():
    spec = importlib.util.spec_from_file_location(
        "extended", Path(__file__).parent / "stand/wave3_extended_batch.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LINK = "vless://00000000-0000-0000-0000-000000000001@node.example.test:443?security=reality&sni=cover.example.test&fp=chrome&sid=0011&pbk=PRIVATE_KEY"


@pytest.mark.parametrize("carrier", ["plain", "base64", "native_json", "xray_json"])
def test_independent_source_carriers_do_not_call_product_parsers(monkeypatch, carrier):
    m = tool()
    monkeypatch.setattr(m.source, "parse_body", lambda *a: pytest.fail("product parser forbidden"))
    expected = m.independent_record(LINK)
    if carrier == "native_json":
        item = {
            "type": "vless",
            "server": expected["server"],
            "server_port": 443,
            "uuid": expected["uuid"],
            "tls": {
                "enabled": True,
                "server_name": expected["server_name"],
                "reality": {"enabled": True, "public_key": "PRIVATE_KEY", "short_id": "0011"},
                "utls": {"enabled": True, "fingerprint": "chrome"},
            },
        }
        data = json.dumps({"outbounds": [item]}).encode()
    elif carrier == "xray_json":
        item = {
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": expected["server"],
                        "port": 443,
                        "users": [{"id": expected["uuid"]}],
                    }
                ]
            },
            "streamSettings": {
                "security": "reality",
                "realitySettings": {
                    "serverName": expected["server_name"],
                    "publicKey": "PRIVATE_KEY",
                    "shortId": "0011",
                    "fingerprint": "chrome",
                },
            },
        }
        data = json.dumps([item]).encode()
    else:
        data = LINK.encode() if carrier == "plain" else base64.b64encode(LINK.encode())
    rows, report = m.source_records(data)
    assert rows == [expected] and report["supported_records"] == 1


@pytest.mark.parametrize("suffix", ["&pbk=OTHER", "&type=ws", "&encryption=other"])
def test_ambiguous_or_unsupported_record_is_counted_never_silently_selected(suffix):
    m = tool()
    rows, report = m.source_records((LINK + suffix).encode())
    assert rows == [] and report["unsupported_or_ambiguous"] == 1


def test_independent_comparison_redacts_values_and_preserves_source_ambiguity():
    m = tool()
    expected = m.independent_record(LINK)
    other = {**expected, "public_key": "OTHER_SECRET"}
    result = m.compare_record(expected, [expected, other])
    assert result["outcome"] == "NO_UNIQUE_SUPPORTED_RECORD"
    assert "PRIVATE" not in json.dumps(result) and "OTHER_SECRET" not in json.dumps(result)
    result = m.compare_record(expected, [other])
    assert result["fields_equal"]["public_key"] is False


def graph_fixture():
    sb = {
        "inbounds": [
            {
                "tag": "sb-in-1234abcd-d",
                "type": "socks",
                "listen": "127.0.0.1",
                "listen_port": 23456,
                "users": [{"username": "xgw-d", "password": "PRIVATE_PASSWORD"}],
            }
        ],
        "outbounds": [{"tag": "sb-out-1234abcd-d", "type": "vless"}],
        "route": {
            "rules": [
                {
                    "inbound": ["sb-in-1234abcd-d"],
                    "action": "route",
                    "outbound": "sb-out-1234abcd-d",
                },
                {"action": "reject"},
            ]
        },
    }
    xr = {
        "outbounds": [
            {
                "protocol": "socks",
                "settings": {
                    "servers": [
                        {
                            "address": "127.0.0.1",
                            "port": 23456,
                            "users": [{"user": "xgw-d", "pass": "PRIVATE_PASSWORD"}],
                        }
                    ]
                },
            }
        ]
    }
    return sb, xr


def test_whole_graph_detects_password_drift_and_orphan_local_reference_privately():
    m = tool()
    sb, xr = graph_fixture()
    good = m.whole_graph(sb, xr)
    assert good["noncanonical_bridges"] == good["bad_xray_references"] == 0
    xr["outbounds"][0]["settings"]["servers"][0]["users"][0]["pass"] = "OTHER_SECRET"
    xr["outbounds"].append(
        {"protocol": "socks", "settings": {"servers": [{"address": "127.0.0.1", "port": 23457}]}}
    )
    result = m.whole_graph(sb, xr)
    assert result["bad_xray_references"] == 1 and result["unmatched_local_socks_references"] == 1
    assert "PRIVATE" not in json.dumps(result) and "23456" not in json.dumps(result)


def test_scan_summary_is_read_only_and_short_OK_is_not_full_body(tmp_path):
    m = tool()
    path = tmp_path / "db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE scans(verdict TEXT,bytes INT,seconds REAL,ts REAL)")
    conn.execute("INSERT INTO scans VALUES ('OK',305,0.5,1000)")
    conn.commit()
    conn.close()
    old = path.read_bytes()
    result = m.health_summary(path, 1500)
    assert result["OK_bodies_under_32769"] == result["age_over_300_seconds"] == 1
    assert result["core_identity"] == "UNSPECIFIED_IN_SCAN_SCHEMA"
    assert path.read_bytes() == old


def test_missing_scan_database_is_unknown_and_not_created(tmp_path):
    m = tool()
    assert m.health_summary(tmp_path / "absent", 1500)["query_ok"] is False
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize("history_present", [False, True])
def test_worker_continues_optional_history_failure_and_finishes_all_safe_phases(
    tmp_path, monkeypatch, history_present
):
    m = tool()
    run = tmp_path / "T"
    run.mkdir()
    monkeypatch.setattr(m, "ROOT", run)
    monkeypatch.setattr(m, "S_ROOT", tmp_path / "absent_history")
    monkeypatch.setattr(m, "SAMPLES", 2)
    monkeypatch.setattr(m, "INTERVAL", 0)
    monkeypatch.setattr(m.time, "sleep", lambda _: None)
    monkeypatch.setattr(m.diagnostic, "checked", lambda path, *a: path)
    sb, xr = graph_fixture()
    sbpath, xrpath = tmp_path / "sb.json", tmp_path / "xr.json"
    sbpath.write_text(json.dumps(sb))
    xrpath.write_text(json.dumps(xr))
    if history_present:
        old_s, old_r = tmp_path / "oldS", tmp_path / "oldR"
        old_s.mkdir()
        old_r.mkdir()
        monkeypatch.setattr(m, "S_ROOT", old_s)
        monkeypatch.setattr(m, "R_ROOT", old_r)
        (old_s / "wave3_reality_contract.py").write_bytes(
            (Path(__file__).parent / "stand/wave3_reality_contract.py").read_bytes()
        )
        (old_s / "summary.json").write_text(
            json.dumps(
                {
                    "marker": "REALITY_CONTRACT_RECORDED",
                    "source_comparison": {"all_compared_fields_equal": True},
                    "all_context_checks_ok": True,
                }
            )
        )
        (old_r / "plan-private.json").write_text(
            json.dumps(
                {"case_key": "1234abcd", "config_sha256": m.single.digest(sbpath.read_bytes())}
            )
        )
    monkeypatch.setattr(
        m.reader,
        "PATHS",
        SimpleNamespace(
            singbox_config_file=sbpath,
            xray_config_file=xrpath,
            config_file=tmp_path / "conf",
            db_file=tmp_path / "absentdb",
        ),
    )
    cfg = SimpleNamespace(subscriptions=[], manual=SimpleNamespace(links=[LINK]))
    monkeypatch.setattr(m.reader.config, "load", lambda _: (cfg, []))
    monkeypatch.setattr(m, "journals", lambda _: {"query_ok": False})
    monkeypatch.setattr(m.bridge, "process_ready", lambda _: True)
    monkeypatch.setattr(m.bridge, "pin_token", lambda: b"same")
    monkeypatch.setattr(m.single, "request", lambda *a: pytest.fail("no requests"))
    monkeypatch.setattr(m.reader, "public", lambda _: {"capture": True})
    before = {
        "singbox": {"process_identity": [42, "start"]},
        "boot_private": "boot",
        "hashes_private": [b"1", b"2", b"3"],
        "interface_private": {"LAN": "fixture"},
        "interfaces": {"LAN": {"rx_bytes": 100, "tx_bytes": 200, "carrier": 1}},
        "unit_private": {unit: {"MainPID": "42"} for unit in m.reader.UNITS},
    }
    monkeypatch.setattr(m.reader, "snapshot", lambda: copy.deepcopy(before))
    m.worker()
    result = json.loads((run / "summary.json").read_text())
    assert result["marker"] == (
        "EXTENDED_BATCH_RECORDED" if history_present else "EXTENDED_BATCH_PARTIAL"
    )
    assert len(result["phases"]) == 7
    assert result["phases"]["T1_history"]["collection"] == (
        "RECORDED" if history_present else "UNAVAILABLE"
    )
    assert result["phases"]["T7_passive_LAN"]["data"]["stop"] == "PLANNED_OBSERVATION_COMPLETE"
    assert result["network_requests"] == 0 and "PRIVATE_PASSWORD" not in json.dumps(result)


def test_start_guard_prevents_second_worker_without_any_gateway_read(tmp_path, monkeypatch):
    m = tool()
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m.diagnostic, "checked", lambda path, *a: path)
    monkeypatch.setattr(m.sys, "argv", ["t", "start"])
    (tmp_path / "started.json").write_text("{}")
    monkeypatch.setattr(m.subprocess, "Popen", lambda *a, **kw: pytest.fail("must not spawn"))
    with pytest.raises(ValueError, match="already started"):
        m.main()


def test_successful_start_detaches_only_own_read_only_worker_and_does_not_claim_completion(
    tmp_path, monkeypatch
):
    m = tool()
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m.diagnostic, "checked", lambda path, *a: path)
    monkeypatch.setattr(m.sys, "argv", ["t", "start"])
    calls = []
    monkeypatch.setattr(m.subprocess, "Popen", lambda argv, **kw: calls.append((argv, kw)))
    assert m.main() == 0
    argv, kw = calls[0]
    assert argv[1:3] == ["-I", "-B"] and argv[-1] == "_worker"
    assert (
        kw["start_new_session"] is True
        and kw["stdin"] == kw["stdout"] == kw["stderr"] == m.subprocess.DEVNULL
    )
    assert (tmp_path / "started.json").exists() and not (tmp_path / "summary.json").exists()


def test_graph_does_not_accept_direct_outbound_or_extra_ambiguous_route_rule():
    m = tool()
    sb, xr = graph_fixture()
    sb["outbounds"][0]["type"] = "direct"
    sb["route"]["rules"].insert(0, {"action": "route", "outbound": "direct"})
    result = m.whole_graph(sb, xr)
    assert result["noncanonical_bridges"] == 1 and result["route_rule_schema_violations"] == 1


def test_disabled_security_does_not_compare_unused_URI_tls_values():
    m = tool()
    value = m.independent_record(LINK.replace("security=reality", "security=none"))
    assert value["tls_enabled"] is False
    assert (
        value["server_name"]
        == value["public_key"]
        == value["short_id"]
        == value["fingerprint"]
        == ""
    )
