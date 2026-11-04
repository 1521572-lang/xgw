"""Только парсер счётчиков и конечное восстановление; сеть/службы не вызываются."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

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


def fake_baseline(helper, tmp_path, monkeypatch):
    monkeypatch.setattr(helper, "ROOT", tmp_path)
    monkeypatch.setattr(helper, "ACTIVE", tmp_path / "active.json")
    initial = {"cuts": {k: {"result": "не выполнялось", "rescue": False} for k in helper.KINDS}}
    helper.save(initial)
    calls = []

    def context(*, checks=None):
        calls.append("context")
        checks.update(health=True, on=True)
        return None, SimpleNamespace(), None, ("private-config", "off", "private-pin"), True

    monkeypatch.setattr(helper, "context", context)
    monkeypatch.setattr(
        helper, "loaded_detail", lambda: calls.append("loaded") or (True, "правила соответствуют")
    )
    monkeypatch.setattr(helper, "guard", lambda: calls.append("guard") or snapshot(9))
    monkeypatch.setattr(helper, "https_detail", lambda: calls.append("https") or (True, "HTTP 200"))
    monkeypatch.setattr(helper, "permissions", lambda paths: calls.append("permissions") and None)
    monkeypatch.setattr(helper, "recover_window", lambda *args: pytest.fail("network mutation"))
    monkeypatch.setattr(
        helper.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("worker started")
    )
    return initial, calls


def test_clarification_records_failures_and_continues_independent_reads(
    helper, tmp_path, monkeypatch, capsys
):
    initial, calls = fake_baseline(helper, tmp_path, monkeypatch)
    monkeypatch.setattr(
        helper, "loaded_detail", lambda: calls.append("loaded") or (None, "таймаут loaded (8 с)")
    )

    def guard():
        calls.append("guard")
        raise helper.CheckFailed("hook или приоритет host-цепочки не совпали")

    def permissions(paths):
        calls.append("permissions")
        raise PermissionError("private-server.example")

    monkeypatch.setattr(helper, "guard", guard)
    monkeypatch.setattr(helper, "permissions", permissions)
    monkeypatch.setattr(
        helper, "https_detail", lambda: calls.append("https") or (False, "HTTP 403")
    )
    assert helper.baseline(clarification=True) == 3
    state = helper.read(tmp_path / "state.json")
    assert calls == ["context", "loaded", "guard", "https", "permissions"]
    assert state["clarification"]["completed"] is True
    assert state["clarification"]["checks"]["loaded"]["passed"] is None
    assert state["clarification"]["checks"]["guard"]["passed"] is False
    assert state["cuts"] == initial["cuts"] and state.get("baseline") is not True
    assert "identity" not in state and not helper.ACTIVE.exists()
    text = capsys.readouterr().out
    assert "таймаут loaded" in text and "HTTP 403" in text and "private-" not in text
    assert "Изоляция sing-box: 0" not in text and len(text.splitlines()) <= 15
    with pytest.raises(RuntimeError):
        helper.baseline(clarification=True)
    assert len(calls) == 5


def test_all_green_clarification_never_authorizes_old_cut(helper, tmp_path, monkeypatch):
    initial, _ = fake_baseline(helper, tmp_path, monkeypatch)
    frozen = tmp_path / "helper.py"
    frozen.write_bytes(b"old frozen helper")
    assert helper.baseline(clarification=True) == 0
    state = helper.read(tmp_path / "state.json")
    assert state.get("baseline") is not True and "identity" not in state
    assert state["cuts"] == initial["cuts"] and frozen.read_bytes() == b"old frozen helper"
    with pytest.raises(RuntimeError):
        helper.launch("output")


def test_normal_baseline_keeps_failed_check_instead_of_claiming_not_run(
    helper, tmp_path, monkeypatch, capsys
):
    fake_baseline(helper, tmp_path, monkeypatch)
    monkeypatch.setattr(helper, "https_detail", lambda: (False, "HTTP 403"))
    assert helper.baseline() == 3
    state = helper.read(tmp_path / "state.json")
    assert state["baseline"] is False and state["baseline_checks"]["completed"] is True
    out = capsys.readouterr().out
    assert "HTTPS: не пройдено; HTTP 403" in out and "Изоляция sing-box: не выполнялась" in out


@pytest.mark.parametrize(
    "mode,value,detail",
    (
        ("true", True, "правила соответствуют"),
        ("false", False, "правила не соответствуют"),
        ("unknown", None, "неизвестный результат"),
        ("timeout", None, "таймаут loaded"),
        ("oserror", None, "не удалось запустить"),
        ("rc3", None, "кодом 3"),
        ("private-server.example", None, "не распознан ответ"),
    ),
)
def test_loaded_details_keep_timeout_false_unknown_separate(
    helper, monkeypatch, mode, value, detail
):
    def run(argv, **kwargs):
        assert argv[-1] == "_loaded_result" and kwargs["timeout"] == 8
        if mode == "timeout":
            raise helper.subprocess.TimeoutExpired("private-command", 8)
        if mode == "oserror":
            raise OSError("private-path")
        return SimpleNamespace(returncode=3 if mode == "rc3" else 0, stdout=mode.encode())

    monkeypatch.setattr(helper.subprocess, "run", run)
    result, text = helper.loaded_detail()
    assert result is value and detail in text and "private-" not in text


@pytest.mark.parametrize(
    "error,value,detail",
    (
        (None, False, "HTTP 403"),
        (TimeoutError("private-host"), None, "таймаут HTTPS"),
    ),
)
def test_https_failure_has_only_safe_details(helper, monkeypatch, error, value, detail):
    class Connection:
        def request(self, *args):
            if error:
                raise error

        def getresponse(self):
            return SimpleNamespace(status=403)

        def close(self):
            pass

    monkeypatch.setattr(helper.ssl, "create_default_context", object)
    monkeypatch.setattr(helper.http.client, "HTTPSConnection", lambda *args, **kwargs: Connection())
    result, text = helper.https_detail()
    assert result is value and detail in text and "private-" not in text
