"""Focused fixtures for evidence classification and bounded journal child handling."""

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def tool():
    spec = importlib.util.spec_from_file_location(
        "evidence_closure", Path(__file__).parent / "stand/wave3_evidence_closure.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def endpoint():
    return {
        "type": "vless",
        "tag": "sb-out-1234abcd-d",
        "server": "PRIVATE_HOST",
        "server_port": 443,
        "uuid": "PRIVATE_UUID",
        "tls": {"enabled": True, "server_name": "PRIVATE_SNI"},
    }


@pytest.mark.parametrize("case", ["equal", "mismatched", "missing_identity", "ambiguous_contracts"])
def test_gap_classification_does_not_choose_best_contract_or_expose_identity(case):
    m = tool()
    node = endpoint()
    record = m.source.contract(node)
    rows = [record]
    if case == "missing_identity":
        rows = []
    elif case == "mismatched":
        record["flow"] = "PRIVATE_FLOW"
    elif case == "ambiguous_contracts":
        rows.append({**record, "flow": "PRIVATE_FLOW"})
    result = m.contract_gaps({"outbounds": [node]}, rows)
    assert result["counts"][case] == 1
    assert sum(v for k, v in result["counts"].items() if k != "default_vless") == 1
    if case == "ambiguous_contracts":
        assert result["ambiguous_field_counts"]["flow"] == 1
        assert result["counts"]["mismatched"] == 0
    assert "PRIVATE" not in json.dumps(result) and "1234abcd" not in json.dumps(result)


def test_group_membership_change_is_not_misreported_as_server_credentials_change():
    m = tool()
    old = {
        "outbounds": [
            endpoint(),
            {"type": "selector", "tag": "PRIVATE_TAG", "outbounds": ["PRIVATE_A", "PRIVATE_B"]},
        ]
    }
    new = copy.deepcopy(old)
    new["outbounds"][1]["outbounds"].reverse()
    result = m.generation_categories(new, old)
    assert result["shared_objects_changed"] == result["current_type_counts"]["GROUP"] == 1
    assert result["changed_field_group_counts_OVERLAP"]["group_members"] == 1
    assert result["changed_field_group_counts_OVERLAP"]["identity"] == 0
    assert "PRIVATE" not in json.dumps(result)
    with pytest.raises(ValueError, match="duplicate"):
        m.generation_categories({"outbounds": [endpoint(), endpoint()]}, old)


def test_journal_parser_reports_truncated_and_incomplete_rows_without_raw_messages():
    m = tool()
    row = (
        json.dumps(
            {"MESSAGE": "PRIVATE_HOST: конфиг sing-box перечитан"}, ensure_ascii=False
        ).encode()
        + b"\n"
    )
    result = m.journal_counts(row * 1001 + b'{"MESSAGE":"PRIVATE')
    assert result["row_limit_hit"] and result["incomplete_last_line"]
    assert result["rows_analyzed"] == result["literal_counts"]["reloaded"] == 1000
    assert "PRIVATE" not in json.dumps(result)
    assert m.journal_counts(b"not json\n")["parse_errors"] == 1
    assert m.journal_counts(b'{"MESSAGE":[1,2]}\n')["parse_errors"] == 1


@pytest.mark.parametrize("stop", ["EOF", "TIME_BUDGET", "BYTE_BUDGET", "BAD_RC"])
def test_bounded_journal_owns_only_one_child_and_never_retries(stop, monkeypatch):
    m = tool()
    events = []

    class Child:
        returncode = None
        stdout = SimpleNamespace(fileno=lambda: 42, close=lambda: events.append("closed"))

        def poll(self):
            return self.returncode

        def wait(self, timeout):
            self.returncode = 1 if stop == "BAD_RC" else 0

        def terminate(self):
            events.append("terminate_own_journal")

        def kill(self):
            pytest.fail("this fixture terminates normally")

    child = Child()

    class Selector:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def register(self, *args):
            pass

        def select(self, timeout):
            return [] if stop == "TIME_BUDGET" else [True]

    def spawn(argv, **kwargs):
        events.append("spawn")
        assert argv[0] == "journalctl" and argv.count("-u") == 2
        assert "1001" in argv and "--output-fields=MESSAGE" in argv
        assert kwargs["stderr"] == m.subprocess.DEVNULL
        return child

    reads = [(json.dumps({"MESSAGE": "PRIVATE: sing-box запущен"}) + "\n").encode()]

    def read(fd, size):
        assert fd == 42
        return b"a" * size if stop == "BYTE_BUDGET" else reads.pop(0) if reads else b""

    monkeypatch.setattr(m.subprocess, "Popen", spawn)
    monkeypatch.setattr(m.selectors, "DefaultSelector", Selector)
    monkeypatch.setattr(m.os, "read", read)
    result = m.bounded_journal()
    assert events.count("spawn") == 1
    assert result["query_ok"] == (stop == "EOF")
    assert result["stop_reason"] == ("EOF" if stop == "BAD_RC" else stop)
    assert result["raw_bytes_read"] <= 1048576
    assert ("terminate_own_journal" in events) == (stop in ("TIME_BUDGET", "BYTE_BUDGET"))
    assert "PRIVATE" not in json.dumps(result)


def test_start_dispatches_V_file_not_imported_U_and_second_start_is_rejected(tmp_path, monkeypatch):
    m = tool()
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m.os, "geteuid", lambda: 0)
    monkeypatch.setattr(m.diagnostic, "checked", lambda p, *a: p)
    monkeypatch.setattr(m.sys, "argv", ["v", "start"])
    launches = []
    monkeypatch.setattr(m.subprocess, "Popen", lambda argv, **kw: launches.append((argv, kw)))
    assert m.main() == 0
    assert Path(launches[0][0][-2]).name == "wave3_evidence_closure.py"
    assert launches[0][0][-1] == "_worker" and launches[0][1]["start_new_session"] is True
    with pytest.raises(ValueError, match="already started"):
        m.main()
    assert len(launches) == 1


@pytest.mark.parametrize("history", [False, True])
def test_optional_U_absent_does_not_block_other_three_phases_or_fake_acceptance(
    tmp_path, monkeypatch, history
):
    m = tool()
    run = tmp_path / "V"
    run.mkdir()
    monkeypatch.setattr(m, "ROOT", run)
    old = tmp_path / "U"
    monkeypatch.setattr(m, "OLD", old)
    if history:
        old.mkdir()
        (old / "wave3_coverage_batch.py").write_bytes(
            (Path(__file__).parent / "stand/wave3_coverage_batch.py").read_bytes()
        )
        (old / "summary.json").write_text(
            json.dumps({"marker": "COVERAGE_BATCH_RECORDED", "all_context_checks_ok": True})
        )
        (old / "baseline-private.json").write_text(json.dumps({"source_digests": {}}))
    sb, xr = tmp_path / "sb", tmp_path / "xr"
    sb.write_text('{"outbounds":[]}')
    xr.write_text("{}")
    monkeypatch.setattr(
        m.coverage, "read_config", lambda p: (p.read_bytes(), json.loads(p.read_bytes()))
    )
    monkeypatch.setattr(m.diagnostic, "checked", lambda p, *a: p)
    monkeypatch.setattr(
        m.reader,
        "PATHS",
        SimpleNamespace(
            singbox_config_file=sb,
            xray_config_file=xr,
            config_file=tmp_path / "cfg",
            singbox_last_good_file=tmp_path / "lg",
            singbox_pending_file=tmp_path / "pending",
        ),
    )
    monkeypatch.setattr(m.reader.config, "load", lambda _: (None, []))
    monkeypatch.setattr(m.coverage, "read_sources", lambda _: ([], {}, {}))
    monkeypatch.setattr(
        m.coverage, "generation_summary", lambda *a: {"last_good": {}, "pending": {}}
    )
    monkeypatch.setattr(m, "bounded_journal", lambda: {"query_ok": False})
    monkeypatch.setattr(m.bridge, "process_ready", lambda _: True)
    monkeypatch.setattr(m.bridge, "pin_token", lambda: b"same")
    monkeypatch.setattr(m.reader, "public", lambda _: {"capture": True})
    snapshot = {
        "singbox": {"process_identity": [42, "start"]},
        "boot_private": "boot",
        "hashes_private": [b"1", b"2", b"3"],
        "unit_private": {unit: {"MainPID": "42"} for unit in m.reader.UNITS},
    }
    monkeypatch.setattr(m.reader, "snapshot", lambda: copy.deepcopy(snapshot))
    m.worker()
    result = json.loads((run / "summary.json").read_text())
    assert len(result["phases"]) == 4 and result["network_requests"] == 0
    assert result["marker"] == (
        "EVIDENCE_CLOSURE_RECORDED" if history else "EVIDENCE_CLOSURE_PARTIAL"
    )
    assert result["phases"]["V1_U_identity"]["collection"] == (
        "RECORDED" if history else "UNAVAILABLE"
    )
    assert result["phases"]["V4_bounded_writer_journal"]["collection"] == "RECORDED"
