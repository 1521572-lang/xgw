"""Only mocked curl/journal and private-file fixtures; no real network or services."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def tool():
    spec = importlib.util.spec_from_file_location(
        "single_bridge", Path(__file__).parent / "stand/wave3_single_bridge.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_failed_socks_reply_is_redacted_and_does_not_invent_a_root_cause():
    m = tool()
    result = m.error_summary(b"curl: (97) Can't complete SOCKS5 connection to PRIVATE_HOST. (1)")
    assert result["socks5_reply_code"] == 1 and result["details"] == []
    assert "PRIVATE" not in json.dumps(result)
    assert m.error_summary(b"unrecognized private message")["socks5_reply_code"] is None


def test_generic_reality_or_tls_text_is_not_a_reported_handshake_failure():
    m = tool()
    assert m.error_summary(b"INFO reality TLS handshake configured")["details"] == []
    assert m.error_summary(b"REALITY verification failed PRIVATE_KEY")["details"] == [
        "reality_verification_failed"
    ]


def test_journal_message_level_is_distinct_from_journal_priority_and_domain_words():
    m = tool()
    lines = [
        {
            "MESSAGE": "INFO outbound/vless[sb-out-1234abcd-d]: TLS PRIVATE_ERROR_HOST",
            "PRIORITY": "6",
        },
        {
            "MESSAGE": "ERROR outbound/vless[sb-out-1234abcd-d]: reality verification failed",
            "PRIORITY": "6",
        },
        {"MESSAGE": "ERROR sb-out-1234abcd9-d: permission denied", "PRIORITY": "3"},
    ]
    result = m.journal_summary(b"\n".join(json.dumps(x).encode() for x in lines), "1234abcd")
    assert result["related_message_levels"]["info"] == 1
    assert result["related_message_levels"]["error"] == 1
    assert result["related_literal_details"]["permission_failure"] == 0
    assert result["related_literal_details"]["reality_verification_failed"] == 1
    assert "PRIVATE" not in json.dumps(result) and "1234abcd" not in json.dumps(result)


@pytest.mark.parametrize("changed", ["config", "N", "mapping", "summary"])
def test_missing_or_changed_historical_identity_blocks_selection(monkeypatch, changed):
    m = tool()
    monkeypatch.setattr(m.bridge, "bridges", lambda _: [{"key": "1234abcd", "protocol": "vless"}])
    raw, n_raw = b"{}", b"old"
    summary = {
        "marker": "READ_DIAGNOSTIC_RECORDED",
        "historical_summary_valid": True,
        "historical_mapping": "FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN",
    }
    mapping = {
        "mapping_basis": summary["historical_mapping"],
        "n_summary_sha256": m.digest(n_raw),
        "current_config_sha256": m.digest(raw),
        "case_keys": {"SB-1": "1234abcd"},
    }
    assert m.selected_from_mapping(mapping, summary, n_raw, raw)["key"] == "1234abcd"
    if changed == "config":
        raw = b'{"changed":true}'
    elif changed == "N":
        n_raw = b"new"
    elif changed == "mapping":
        mapping["case_keys"] = {"SB-2": "1234abcd"}
    else:
        summary["historical_mapping"] = "UNCONFIRMED"
    with pytest.raises(ValueError):
        m.selected_from_mapping(mapping, summary, n_raw, raw)


def test_curl_has_one_call_no_proxy_environment_no_secret_argv_and_only_safe_output(monkeypatch):
    m = tool()
    calls = []
    metadata = {
        "http_code": 0,
        "size_download": 0,
        "time_total": 0.5,
        "ssl_verify_result": 0,
        "num_redirects": 0,
        "url_effective": "PRIVATE_URL",
    }

    def fake(argv, **kw):
        calls.append((argv, kw))
        return SimpleNamespace(
            returncode=97,
            stdout=json.dumps(metadata).encode() + b"\n",
            stderr=b"Can't complete SOCKS5 connection to PRIVATE_HOST. (1)",
        )

    monkeypatch.setattr(m.subprocess, "run", fake)
    result = m.request(
        "/usr/bin/curl",
        {"port": 12345, "user": "xgw-d", "password": "PRIVATE_PASS"},
        "https://PRIVATE_URL/a",
    )
    assert len(calls) == 1 and result["body_ok"] is False
    argv, kw = calls[0]
    assert "PRIVATE" not in str(argv) and "PRIVATE_PASS" in kw["input"].decode()
    assert argv[1] == "-q" and argv[argv.index("--retry") + 1] == "0"
    assert argv[argv.index("--max-time") + 1] == "6" and kw["timeout"] == 8
    assert argv[argv.index("--noproxy") + 1] == "" and "--socks5-hostname" in argv
    assert set(kw["env"]) == {"PATH", "LC_ALL", "LANG"}
    assert "PRIVATE" not in json.dumps(result)
    assert result["error"]["socks5_reply_code"] == 1


@pytest.mark.parametrize(
    "rc,code,size,expected", [(0, 206, 32769, True), (0, 200, 305, False), (97, 0, 0, False)]
)
def test_small_scan_payload_or_failed_handshake_is_not_full_body_pass(
    monkeypatch, rc, code, size, expected
):
    m = tool()
    data = {
        "http_code": code,
        "size_download": size,
        "time_total": 0.4,
        "ssl_verify_result": 0,
        "num_redirects": 0,
    }
    monkeypatch.setattr(
        m.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=rc, stdout=json.dumps(data).encode() + b"\n", stderr=b""
        ),
    )
    result = m.request(
        "curl", {"port": 12345, "user": "xgw-d", "password": "secret"}, "https://example.test"
    )
    assert result["body_ok"] is expected


def test_started_marker_prevents_second_run_even_when_no_summary_exists(tmp_path, monkeypatch):
    m = tool()
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m.diagnostic, "checked", lambda p, *a: p)
    monkeypatch.setattr(m.sys, "argv", ["tool", "run"])
    (tmp_path / "started.json").write_text("{}")
    monkeypatch.setattr(m.reader, "snapshot", lambda: pytest.fail("must not read gateway"))
    with pytest.raises(ValueError, match="already started"):
        m.main()


@pytest.mark.parametrize("change", ["none", "pre_identity", "after_config"])
def test_run_saves_plan_before_only_request_and_checks_final_context(tmp_path, monkeypatch, change):
    m = tool()
    run, old, n = (tmp_path / name for name in ("P", "O", "N"))
    for directory in (run, old, n):
        directory.mkdir()
    config = tmp_path / "config.json"
    config.write_bytes(b"{}")
    raw_n = b"{}"
    (n / "summary.json").write_bytes(raw_n)
    (n / "wave3_bridge_probe.py").write_bytes(
        (Path(__file__).parent / "stand/wave3_bridge_probe.py").read_bytes()
    )
    basis = "FILE_TIME_SUPPORTED_NOT_DIGEST_PROVEN"
    (old / "summary.json").write_text(
        json.dumps(
            {
                "marker": "READ_DIAGNOSTIC_RECORDED",
                "historical_summary_valid": True,
                "historical_mapping": basis,
            }
        )
    )
    (old / "mapping-private.json").write_text(
        json.dumps(
            {
                "mapping_basis": basis,
                "n_summary_sha256": m.digest(raw_n),
                "current_config_sha256": m.digest(b"{}"),
                "case_keys": {"SB-1": "1234abcd"},
            }
        )
    )
    monkeypatch.setattr(m, "ROOT", run)
    monkeypatch.setattr(m, "OLD", old)
    monkeypatch.setattr(m.diagnostic, "OLD", n)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m.sys, "argv", ["tool", "run"])
    monkeypatch.setattr(m.diagnostic, "checked", lambda path, *a: path)
    monkeypatch.setattr(m.diagnostic, "historical", lambda value: None)
    monkeypatch.setattr(m.diagnostic, "endpoint_summary", lambda *a: {"protocol": "vless"})
    monkeypatch.setattr(
        m.bridge, "bridges", lambda _: [{"key": "1234abcd", "protocol": "vless", "port": 12345}]
    )
    monkeypatch.setattr(
        m.reader, "PATHS", SimpleNamespace(singbox_config_file=config, config_file=config)
    )
    monkeypatch.setattr(m.reader.config, "load", lambda _: (None, []))
    monkeypatch.setattr(m.bridge, "targets", lambda _: ["https://example.test"])
    monkeypatch.setattr(m.bridge, "pin_token", lambda: b"same")
    monkeypatch.setattr(m.bridge, "process_ready", lambda _: True)
    monkeypatch.setattr(m.bridge, "owns_listener", lambda *a: True)
    monkeypatch.setattr(m.reader, "enabled", lambda: True)
    monkeypatch.setattr(m.reader, "public", lambda _: {"safe": True})
    monkeypatch.setattr(m.shutil, "which", lambda _: "curl")
    monkeypatch.setattr(
        m.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=b"curl 8.5.0 test", stderr=b""),
    )
    monkeypatch.setattr(m, "journal", lambda *a: {"query_ok": False})
    snapshots = []

    def snapshot():
        snapshots.append(1)
        if len(snapshots) == 3 and change == "after_config":
            config.write_bytes(b'{"new":true}')
        return {
            "singbox": {
                "process_identity": [
                    99 if len(snapshots) == 2 and change == "pre_identity" else 42,
                    "start",
                ]
            },
            "boot_private": "boot",
            "hashes_private": [b"a", b"b", b"c"],
            "unit_private": {unit: {"MainPID": "42"} for unit in m.reader.UNITS},
        }

    monkeypatch.setattr(m.reader, "snapshot", snapshot)
    calls = []

    def request(*args):
        plan = json.loads((run / "plan-private.json").read_text())
        assert plan["config_sha256"] == m.digest(b"{}") and plan["case_key"] == "1234abcd"
        calls.append(1)
        return {"body_ok": False, "curl_rc": 97}

    monkeypatch.setattr(m, "request", request)
    rc = m.main()
    summary = json.loads((run / "summary.json").read_text())
    assert len(calls) == (0 if change == "pre_identity" else 1)
    assert summary["request_count"] == len(calls)
    assert rc == (0 if change == "none" else 3)
    assert summary["marker"] == (
        "SINGLE_PROBE_RECORDED" if change == "none" else "STOP_SINGLE_PROBE"
    )
    assert "1234abcd" not in json.dumps(summary) and "example.test" not in json.dumps(summary)
