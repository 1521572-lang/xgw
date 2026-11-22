"""The incident summary retains order and exports only fixed event labels."""

import importlib.util
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "docs/helpers/leak_cause_check.py"


@pytest.fixture()
def helper(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("leak_cause_check", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "DB", tmp_path / "state.db")
    return module


def test_incident_keeps_legacy_uncertainty_and_redacts_details(helper, capsys):
    start = "2026-11-22T02:20:00+03:00"
    end = "2026-11-22T02:45:00+03:00"
    ts = datetime.fromisoformat(start).timestamp()
    rows = [
        (ts - 15, "leak", "предыдущий выход"),
        (ts + 10, "pin", "«private-server» выбран вручную"),
        (ts + 11, "leak", "выбранный вручную сервер private-server сам выходит в RU"),
        (ts + 12, "pin", "автовыбор: ручной выбор сервера снят"),
        (ts + 13, "leak", "выход в RU мимо Xray при включённом перехвате"),
        (ts + 14, "leak", "контроль через Xray не подтвердился"),
        (ts + 15, "HEALTHY", "private route"),
        (ts + 1500, "LEAK", "after interval"),
    ]
    with sqlite3.connect(helper.DB) as conn:
        conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, ts REAL, kind TEXT, detail TEXT)")
        conn.executemany("INSERT INTO events (ts, kind, detail) VALUES (?, ?, ?)", rows)
    assert helper.incident(start, end) == 0
    assert capsys.readouterr().out.splitlines() == [
        "INCIDENT_EVENT offset_s=10 kind=pin_set",
        "INCIDENT_EVENT offset_s=11 kind=pinned",
        "INCIDENT_EVENT offset_s=12 kind=pin_released",
        "INCIDENT_EVENT offset_s=13 kind=legacy_ambiguous",
        "INCIDENT_EVENT offset_s=14 kind=xray_probe_failed",
        "INCIDENT_EVENT offset_s=15 kind=healthy",
        "INCIDENT_COMPLETE events=6",
    ]


def test_incident_requires_explicit_offsets_before_opening_database(helper):
    with pytest.raises(ValueError, match="timezone_required"):
        helper.incident("2026-11-22T02:20:00", "2026-11-22T02:45:00")
    assert not helper.DB.exists()
