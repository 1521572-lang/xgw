"""Synthetic contract/source fixtures only, no subscriptions, tools or network."""

import base64
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def tool():
    spec = importlib.util.spec_from_file_location(
        "reality_contract", Path(__file__).parent / "stand/wave3_reality_contract.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def body():
    return {
        "type": "vless",
        "server": "PRIVATE_HOST",
        "server_port": 443,
        "uuid": "PRIVATE_UUID",
        "flow": "xtls-rprx-vision",
        "tls": {
            "enabled": True,
            "server_name": "PRIVATE_SNI",
            "utls": {"enabled": True, "fingerprint": "chrome"},
            "reality": {
                "enabled": True,
                "public_key": base64.urlsafe_b64encode(b"x" * 32).decode().rstrip("="),
                "short_id": "0011",
            },
        },
    }


def parsed(value):
    return SimpleNamespace(
        protocol="vless",
        address=value["server"],
        port=value["server_port"],
        credential=value["uuid"],
        singbox=SimpleNamespace(main=value),
    )


def test_equal_parsed_contract_does_not_export_secrets_or_claim_original_source_correctness():
    m, applied = tool(), body()
    result = m.compare_sources(applied, [parsed(copy.deepcopy(applied))])
    assert result["all_compared_fields_equal"] is True
    assert result["source_boundary"] == "AFTER_PRODUCT_PARSER_NOT_ORIGINAL_WIRE"
    assert "PRIVATE" not in json.dumps(result)
    assert applied["tls"]["reality"]["public_key"] not in json.dumps(result)


def test_public_key_drift_is_per_field_failure_not_an_upstream_cause():
    m, applied = tool(), body()
    expected = copy.deepcopy(applied)
    expected["tls"]["reality"]["public_key"] = "PRIVATE_OTHER_KEY"
    result = m.compare_sources(applied, [parsed(expected)])
    assert result["all_compared_fields_equal"] is False
    assert (
        result["fields_equal"]["public_key"] is False and result["fields_equal"]["short_id"] is True
    )
    assert "PRIVATE" not in json.dumps(result)


def test_multiple_distinct_contracts_are_ambiguous_never_best_match_selected():
    m, applied = tool(), body()
    other = copy.deepcopy(applied)
    other["tls"]["server_name"] = "PRIVATE_OTHER_SNI"
    result = m.compare_sources(applied, [parsed(applied), parsed(other)])
    assert result["distinct_parsed_contracts"] == 2
    assert result["comparison"] == "NO_UNIQUE_PARSED_CONTRACT" and "fields_equal" not in result


def test_exact_duplicate_parsed_rows_share_one_contract():
    m, applied = tool(), body()
    result = m.compare_sources(applied, [parsed(applied), parsed(copy.deepcopy(applied))])
    assert result["matching_parsed_source_rows"] == 2 and result["distinct_parsed_contracts"] == 1


@pytest.mark.parametrize(
    "sid,valid", [("", True), ("0011", True), ("a", False), ("zz", False), ("00" * 9, False)]
)
def test_short_id_syntax_allows_empty_and_checks_even_hex_without_values(sid, valid):
    m, applied = tool(), body()
    applied["tls"]["reality"]["short_id"] = sid
    flags = m.syntax_flags(m.contract(applied))
    assert flags["short_id_even_hex_at_most_8_bytes"] is valid
    assert flags["public_key_base64url_32_bytes"] is True


def test_invalid_public_key_is_detected_without_downgrading_verification():
    m, applied = tool(), body()
    applied["tls"]["reality"]["public_key"] = "bad"
    assert m.syntax_flags(m.contract(applied))["public_key_base64url_32_bytes"] is False
    assert "insecure" not in applied["tls"]


def test_cache_reader_never_follows_symlink_or_accepts_public_file(tmp_path, monkeypatch):
    m = tool()
    real = tmp_path / "body"
    real.write_bytes(b"PRIVATE_SOURCE")
    real.chmod(0o644)
    with pytest.raises(ValueError):
        m.read_source(real)
    link = tmp_path / "link"
    link.symlink_to(real)
    with pytest.raises(OSError):
        m.read_source(link)


def test_started_file_blocks_repeat_before_gateway_reads(tmp_path, monkeypatch):
    m = tool()
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m.diagnostic, "checked", lambda path, *a: path)
    monkeypatch.setattr(m.sys, "argv", ["s", "run"])
    (tmp_path / "started.json").write_text("{}")
    monkeypatch.setattr(m.reader, "snapshot", lambda: pytest.fail("must not touch gateway"))
    with pytest.raises(ValueError, match="already started"):
        m.main()


@pytest.mark.parametrize("drift", [False, True])
def test_main_parses_only_local_manual_fixture_and_preserves_R_lineage_limit(
    tmp_path, monkeypatch, drift
):
    m = tool()
    s, r = tmp_path / "S", tmp_path / "R"
    s.mkdir()
    r.mkdir()
    key = base64.urlsafe_b64encode(b"x" * 32).decode().rstrip("=")
    link = (
        "vless://00000000-0000-0000-0000-000000000001@node.example.test:443"
        "?security=reality&sni=cover.example.test&fp=chrome&sid=0011&pbk=" + key
    )
    raws, _, _ = m.parse_links_text(link, "manual")
    applied = copy.deepcopy(raws[0].singbox.main)
    applied["tag"] = "sb-out-1234abcd-d"
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"outbounds": [applied]}))
    (r / "wave3_current_bridge.py").write_bytes(
        (Path(__file__).parent / "stand/wave3_current_bridge.py").read_bytes()
    )
    (r / "summary.json").write_text(
        json.dumps(
            {
                "marker": "CURRENT_BRIDGE_RECORDED",
                "request_count": 1,
                "all_context_checks_ok": True,
                "attempt": {"curl_rc": 97, "http_status": 0, "bytes": 0},
                "journal": {"related_literal_details": {"reality_verification_failed": 1}},
            }
        )
    )
    (r / "plan-private.json").write_text(
        json.dumps(
            {
                "case_key": "1234abcd",
                "config_sha256": "f" * 64 if drift else m.single.digest(config.read_bytes()),
            }
        )
    )
    monkeypatch.setattr(m, "ROOT", s)
    monkeypatch.setattr(m, "OLD", r)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m.sys, "argv", ["s", "run"])
    monkeypatch.setattr(m.diagnostic, "checked", lambda path, *a: path)
    monkeypatch.setattr(m.bridge, "bridges", lambda _: [])
    monkeypatch.setattr(m.bridge, "process_ready", lambda _: True)
    monkeypatch.setattr(m.bridge, "pin_token", lambda: b"same")
    monkeypatch.setattr(m.single, "request", lambda *a: pytest.fail("no network"))
    monkeypatch.setattr(m.single, "journal", lambda *a: pytest.fail("no journal"))
    monkeypatch.setattr(
        m.reader, "PATHS", SimpleNamespace(singbox_config_file=config, config_file=config)
    )
    cfg = SimpleNamespace(subscriptions=[], manual=SimpleNamespace(links=[link]))
    monkeypatch.setattr(m.reader.config, "load", lambda _: (cfg, []))
    monkeypatch.setattr(m.reader, "public", lambda _: {"capture": True})
    before = {
        "singbox": {"process_identity": [42, "start"]},
        "boot_private": "same",
        "hashes_private": [b"1", b"2", b"3"],
        "unit_private": {unit: {"MainPID": "42"} for unit in m.reader.UNITS},
    }
    monkeypatch.setattr(m.reader, "snapshot", lambda: before)
    assert m.main() == 0
    result = json.loads((s / "summary.json").read_text())
    assert result["marker"] == "REALITY_CONTRACT_RECORDED" and result["network_requests"] == 0
    assert result["contract_relation_to_R"] == (
        "CURRENT_ONLY_NOT_R_CONTRACT" if drift else "CONFIG_DIGEST_MATCHES_R_PLAN"
    )
    assert result["source_comparison"]["all_compared_fields_equal"] is True
    assert result["source_coverage"]["manual_links_parsed"] is True
    assert "node.example.test" not in json.dumps(result) and key not in json.dumps(result)
