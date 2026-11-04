"""Только парсер счётчиков и конечное восстановление; сеть/службы не вызываются."""

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def helper():
    path = Path(__file__).parents[1] / "docs/helpers/wave3_close.py"
    spec = importlib.util.spec_from_file_location("wave3_close_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(packets=0, generation=1):
    return generation, {"output:3": packets}, "output:3"


def test_guard_requires_postrouting_and_counts_only_denials(helper):
    data = {
        "nftables": [
            {"table": {"family": "inet", "name": "xgw_guard", "handle": 1}},
            {"chain": {"name": "output", "hook": "postrouting", "prio": 10}},
            {
                "rule": {
                    "chain": "output",
                    "handle": 3,
                    "expr": [{"counter": {"packets": 9}}, {"drop": None}],
                }
            },
            {
                "rule": {
                    "chain": "output",
                    "handle": 4,
                    "expr": [{"counter": {"packets": 100}}, {"accept": None}],
                }
            },
        ]
    }
    assert helper.guard(json.dumps(data).encode()) == snapshot(9)
    data["nftables"][1]["chain"]["hook"] = "output"
    with pytest.raises(RuntimeError):
        helper.guard(json.dumps(data).encode())


@pytest.mark.parametrize("after", (snapshot(1, 2), snapshot(1)))
def test_reset_is_not_reported_as_zero_growth(helper, after):
    with pytest.raises(RuntimeError):
        helper.delta(snapshot(2), after)


def test_timeout_and_counter_growth_prove_only_local_barrier(helper):
    checks = iter((False, False, True))
    snaps = iter((snapshot(), snapshot(2)))
    calls = []
    row = helper.recover_window(
        "output",
        None,
        lambda: calls.append("mutate") or 0,
        lambda: "нет ответа за 3 с",
        lambda: next(snaps),
        lambda: next(checks),
        lambda: calls.append("rescue"),
        seconds=0.2,
    )
    assert row["result"] == "пройдено" and row["host_growth"] == 2
    assert calls == ["mutate"] and row["rescue"] is False


def test_reset_is_not_a_postrouting_drop_proof(helper):
    checks = iter((False, False, True))
    snaps = iter((snapshot(), snapshot(2)))
    row = helper.recover_window(
        "table",
        None,
        lambda: 0,
        lambda: "сброс",
        lambda: next(snaps),
        lambda: next(checks),
        lambda: pytest.fail("unexpected rescue"),
        seconds=0.2,
    )
    assert row["result"] == "неопределённо" and not row["rescue"]


def test_fallback_runs_without_another_model_command(helper):
    calls = []
    row = helper.recover_window(
        "rule",
        None,
        lambda: 0,
        lambda: "нет ответа за 3 с",
        lambda: snapshot(),
        lambda: False,
        lambda: calls.append("sudo xgw net up") or 0,
        seconds=0.01,
    )
    assert calls == ["sudo xgw net up"] and row["rescue"] and row["rescue_rc"] == 0


def test_counter_read_failure_keeps_fallback_and_its_actual_result(helper):
    count = 0

    def read():
        nonlocal count
        count += 1
        if count > 1:
            raise OSError("synthetic")
        return snapshot()

    row = helper.recover_window(
        "output",
        None,
        lambda: 0,
        lambda: "нет ответа за 3 с",
        read,
        lambda: False,
        lambda: 7,
        seconds=0.01,
    )
    assert row["rescue"] and row["rescue_rc"] == 7 and row["result"] == "неопределённо"


def test_preparation_failure_never_arms_rescue_or_mutation(helper):
    def fail():
        raise OSError("synthetic")

    with pytest.raises(OSError):
        helper.recover_window(
            "output",
            None,
            lambda: pytest.fail("mutation"),
            lambda: "",
            fail,
            lambda: False,
            lambda: pytest.fail("rescue"),
            seconds=0.01,
        )


def test_no_raw_identity_in_report(helper, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(helper, "ROOT", tmp_path)
    monkeypatch.setattr(helper, "ACTIVE", tmp_path / "active.json")
    data = {
        "identity": ["private-configuration", "private-pin"],
        "baseline": True,
        "cuts": {
            k: {"result": "не выполнялось", "rescue": False, "reason": "владелец отказал"}
            for k in helper.KINDS
        },
    }
    (tmp_path / "state.json").write_text(json.dumps(data))
    helper.report()
    out = capsys.readouterr().out
    assert "private-" not in out and "NOT_RUN" in out and len(out.splitlines()) <= 18
