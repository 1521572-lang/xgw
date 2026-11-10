"""Свидетельства обработки не подменяют доставку; ошибки не раскрывают журнал."""

import importlib.util
import json
from pathlib import Path

import pytest
from test_zapret2 import Harness, setup

from xgw import zapret2
from xgw.net.cmd import CommandError
from xgw.zapret2_trace import LUA, Evidence, parse

READY = "LUA: XGW_Z2_TRACE READY\n"
ROW = ("LUA: XGW_Z2_TRACE seq=1 hello=1 send_calls=3 send_ok=3 "
       "applied=1 lua_errors=0\n")


def test_only_compare_observes_and_keeps_the_strategy_arguments():
    cfg, _, _ = setup()
    args = zapret2.arguments(cfg)
    assert args[-1] == "--lua-desync=multisplit:pos=1,midsld"
    assert not any("xgw_trace" in arg for arg in args)
    cfg.zapret2.mode = "compare"
    for strategy in ("multisplit", "multidisorder"):
        cfg.zapret2.strategy = strategy
        args = zapret2.arguments(cfg)
        assert "--lua-init=" + LUA in args and "--debug=0" in args
        assert args[-1] == f"--lua-desync=xgw_trace:strategy={strategy}:pos=1,midsld"


def test_private_messages_are_not_returned_and_partial_sends_are_visible():
    failed = ROW.replace("seq=1", "seq=2").replace("send_ok=3", "send_ok=1").replace(
        "applied=1", "applied=0")
    result = parse(READY + ROW + "private packet and host detail\n" + failed)
    assert result == {"state": "observed", "hello": 2, "send_calls": 6,
                      "send_ok": 4, "applied": 1, "lua_errors": 0}
    assert "private" not in json.dumps(result)
    assert parse(READY)["hello"] == 0  # чтение журнала не является доказательством обработки


@pytest.mark.parametrize("text", [
    ROW, READY + ROW.replace("seq=1", "seq=2"), READY + ROW + ROW, READY + READY,
    READY + ROW + "LUA: XGW_Z2_TRACE LIMIT\n", READY + "LUA: XGW_Z2_TRACE bad\n",
    READY + ROW.replace("send_ok=3", "send_ok=4"),
    READY + ROW.replace("hello=1", "hello=0"),
    READY + ROW.replace("lua_errors=0", "lua_errors=1"),
])
def test_missing_truncated_or_inconsistent_journal_is_incomplete(text):
    assert parse(text)["state"] == "incomplete"


def test_scope_is_one_worker_invocation_and_queue_delta():
    counts = iter((120, 128))
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[0] == "systemctl":
            return "a" * 32
        if args[0] == "nft":
            return json.dumps({"nftables": [{"rule": {"expr": [
                {"counter": {"packets": next(counts), "bytes": 999}},
                {"queue": {"num": 200}},
            ]}}]})
        return "" if "--sync" in args else READY + ROW

    evidence = Evidence(run, zapret2.UNIT, 200)
    evidence.begin()
    evidence.sample()
    result = evidence.finish()
    assert result["state"] == "observed" and result["queue_packets"] == 8
    assert calls[-1][-1] == "_SYSTEMD_INVOCATION_ID=" + "a" * 32


def test_failed_diagnostics_never_publish_raw_errors():
    def fail(*args, **kwargs):
        raise CommandError("private data")

    evidence = Evidence(fail, zapret2.UNIT, 200)
    evidence.begin()
    evidence.sample()
    assert evidence.finish() == {"state": "unavailable", "queue_packets": -1,
                                 "hello": 0, "send_calls": 0, "send_ok": 0,
                                 "applied": 0, "lua_errors": 0}


def test_counter_reset_is_unknown_even_with_successful_lua():
    def run(args, **kwargs):
        return "" if "--sync" in args else READY + ROW

    evidence = Evidence(run, zapret2.UNIT, 200)
    evidence.invocation = "b" * 32
    evidence.before = 100
    evidence.packets = lambda: 20
    evidence.sample()
    result = evidence.finish()
    assert result["state"] == "incomplete" and result["queue_packets"] == -1


def test_helper_reports_only_allowlisted_trace_fields(capsys):
    path = Path(__file__).resolve().parents[1] / "docs/helpers/zapret2_check.py"
    spec = importlib.util.spec_from_file_location("zapret2_check", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.trace_report({"trace": {**parse(READY + ROW), "queue_packets": 8,
                                  "private": "hidden"}})
    output = capsys.readouterr().out
    assert "applied=1" in output and "hidden" not in output and "private" not in output
    with pytest.raises(ValueError, match="invalid_trace"):
        helper.trace_report({"trace": {"state": "secret"}})


def test_unavailable_trace_does_not_prevent_comparison_cleanup():
    h = Harness()
    h.cfg.zapret2.mode = "compare"
    h.controller._compare = lambda *args: [{"kind": "timeout"}] * 4
    h.runtime.finish_trace = lambda: {"state": "unavailable"}
    for now in range(3):
        h.step(now)
    assert h.controller.view["reason"] == "comparison_done"
    assert h.controller.view["trace"] == {"state": "unavailable"}
    assert not h.runtime.up and not zapret2.active(h.current)


@pytest.mark.parametrize("change", [{}, {"queue": True}, {"xray_pid": 43},
                                     {"state": "compared"}, {"worker_pid": 77}])
def test_helper_rollback_requires_off_free_queue_and_unchanged_xray(
        change, monkeypatch, tmp_path, capsys):
    path = Path(__file__).resolve().parents[1] / "docs/helpers/zapret2_check.py"
    spec = importlib.util.spec_from_file_location("zapret2_check", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    baseline = {"state": "off", "route": False, "queue": False, "lease": False,
                "capture_on": True, "xray_pid": 42, "worker_pid": 0,
                "protected": "test", "warnings": 0, "zapret_bytes": 0}
    saved = tmp_path / "before.json"
    saved.write_text(json.dumps(baseline))
    monkeypatch.setattr(helper.os, "geteuid", lambda: 0)
    monkeypatch.setattr(helper.sys, "argv", ["helper", "finish", "--state", str(saved)])
    monkeypatch.setattr(helper, "snapshot", lambda **kwargs: {**baseline, **change})
    assert helper.main() == (1 if change else 0)
    assert ("rollback_failed" if change else "rollback_ok") in capsys.readouterr().out
