"""Форматы продукта и замер без прежнего отсечения loaded через восемь секунд."""

import importlib.util
import json
from pathlib import Path

import pytest

from xgw import config
from xgw.net import capture

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("align_main", REPO / "docs/helpers/align_main.py")
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


@pytest.fixture
def saved(monkeypatch):
    records = {}
    monkeypatch.setattr(helper, "save", lambda name, value: records.update({name: value.copy()}))
    monkeypatch.setattr(helper, "read", records.__getitem__)
    return records


@pytest.mark.parametrize("state", ["HEALTHY", "DEGRADED"])
def test_health_uses_product_json_not_state_name(monkeypatch, saved, state):
    # Поля capture.describe / cli._snapshot; HTTP 301 из фактического wave3-close-readonly.
    prior = (REPO / "docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3-close-readonly-2026-11-04.md")
    assert "HTTP 301" in prior.read_text(encoding="utf-8")
    status = {"state": state, "daemon_down": False, "xray": {"ok": True},
              "capture": {"mode": "on", "blocked": False, "loaded": True}}

    def command(label, name, argv, timeout):
        assert timeout >= 60
        return {"rc": 0, "stderr": "", "stdout": {
            "status": json.dumps(status), "service": "active\n", "https": "301",
        }[name]}

    monkeypatch.setattr(helper, "command", command)
    assert helper.health("before") is True
    assert saved["before-health.json"]["state"] == state
    status["capture"]["blocked"] = True
    assert helper.health("after") is False


def test_guard_product_nft_format_and_previous_public_counts():
    prior = (REPO / "docs/TEST-REPORT-REAL-MACHINE-0.2.0-wave3-close-readonly-2026-11-04.md")
    assert "счётчиков 7; пакетов 5994" in prior.read_text(encoding="utf-8")
    data = {"nftables": [
        {"chain": {"name": "output", "hook": "postrouting", "prio": 10}},
        *[{"rule": {"expr": [{"counter": {"packets": p, "bytes": p * 60}},
                              {"drop": None}]}} for p in (5994, 0, 0, 0, 0, 0, 0)],
    ]}
    assert helper.guard_fields(data) == {
        "postrouting": True, "counters": 7, "packets": 5994, "bytes": 359640,
    }


def test_source_inventory_rejects_extra_installed_file(tmp_path):
    source, installed = tmp_path / "source", tmp_path / "installed"
    for root in (source, installed):
        root.mkdir()
        (root / "code.py").write_text("pass\n")
        (root / "__pycache__").mkdir()
        (root / "__pycache__/code.pyc").write_bytes(b"ignored")
    assert helper.inventory(source) == helper.inventory(installed)
    (installed / "old.py").write_text("pass\n")
    assert helper.inventory(source) != helper.inventory(installed)


def test_loaded_records_nine_seconds_without_rejecting(monkeypatch, saved):
    calls = []
    monkeypatch.setattr(config, "load", lambda path: (object(), []))

    class Capture:
        def loaded(self):
            calls.append("first loaded")
            return True

    monkeypatch.setattr(capture, "capture_for", lambda cfg, paths: Capture())
    clock = iter([10.0, 19.2])
    monkeypatch.setattr(helper.time, "perf_counter", lambda: next(clock))
    assert helper.loaded() == {"loaded": True, "seconds": 9.2, "error": False}
    assert calls == ["first loaded"]
    assert saved["loaded.json"]["seconds"] == 9.2


def test_snapshot_keeps_guard_when_diag_json_is_invalid(monkeypatch, saved, tmp_path):
    monkeypatch.setattr(helper, "inventory", lambda path: {"code.py": "digest"})
    monkeypatch.setattr(helper, "settings", lambda: {"network": "private digest"})

    def command(label, name, argv, timeout):
        return {"rc": 1 if name == "diag" else 0, "stderr": "", "stdout":
                "invalid" if name == "diag" else '{"nftables":[]}'}

    monkeypatch.setattr(helper, "command", command)
    helper.snapshot("after", tmp_path)
    result = saved["after-snapshot.json"]
    assert result["diag"] is None
    assert result["diag_rc"] == 1
    assert result["guard"]["counters"] == 0
    assert result["source"] is True


def test_report_removes_settings_hashes(monkeypatch, capsys):
    records = {"before-snapshot.json": {"settings": {"network": "private hash"}},
               "after-snapshot.json": {"settings": {"network": "private hash"}}}

    def read(name):
        if name not in records:
            raise FileNotFoundError
        return records[name].copy()

    monkeypatch.setattr(helper, "read", read)
    helper.report()
    output = capsys.readouterr().out
    assert "private hash" not in output
    assert json.loads(output)["after_snapshot"]["settings_unchanged"] is True
