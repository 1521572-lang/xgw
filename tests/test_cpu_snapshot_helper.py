"""Формат Linux stat, маскирование трёх источников и суточные единицы бюджета."""

import importlib.util
import json
import sqlite3
import unicodedata
from pathlib import Path

HELPERS = Path(__file__).resolve().parents[1] / "docs/helpers"
SPEC = importlib.util.spec_from_file_location("cpu_snapshot", HELPERS / "cpu_snapshot.py")
cpu = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cpu)


def test_stat_parser_handles_spaces_parentheses_and_reuse_identity():
    fields = ["0"] * 22
    fields[0], fields[11], fields[12], fields[19] = "R", "50", "20", "1000"
    assert cpu.parse_stat("123 (worker (child)) " + " ".join(fields)) == (
        1000, 70, "worker (child)")
    fields[19] = "2000"
    assert cpu.parse_stat("123 (worker) " + " ".join(fields))[0] == 2000


def test_names_are_loaded_from_inventory_status_and_readonly_database(tmp_path, monkeypatch):
    var = tmp_path / "var"
    var.mkdir()
    (var / "inventory.json").write_bytes(
        b'\xef\xbb\xbf{"servers":[{"name":"InventorySecretName"}]}')
    status = tmp_path / "status.json"
    status.write_text(json.dumps({"members": [{"name": "StatusSecretName"}],
                                 "budget": {"quota_mb": {"QuotaSecretName": 123}}}))
    with sqlite3.connect(var / "state.db") as db:
        db.execute("CREATE TABLE nodes (name, source, address, tag)")
        db.execute("INSERT INTO nodes VALUES (?,?,?,?)",
                   ("DatabaseSecretName", "SubscriptionSecret", "192.0.2.8", "fake-tag"))
    monkeypatch.setattr(cpu, "VAR", var)
    monkeypatch.setattr(cpu, "STATUS", status)
    names, sources, _ = cpu.name_sources()
    assert sources == {"inventory": True, "status": True, "database": True}
    raw = "InventorySecretName StatusSecretName DatabaseSecretName QuotaSecretName"
    masked = cpu.safe_text(raw, names)
    assert all(name not in masked for name in raw.split())
    assert "InventorySecret" not in cpu.safe_text("InventorySecret", names)
    assert "192.0.2.8" not in cpu.safe_text("192.0.2.8", names)
    assert "2001:db8::1" not in cpu.safe_text("2001:db8::1", names)
    assert cpu.safe_text("python3.12", names) == "python3.12"
    assert "StatusSecretName" not in cpu.safe_text("StatusSecretName", set(), False)


def test_budget_keeps_daily_quota_and_monthly_share_without_names():
    view = cpu.budget_view({"budget": {"total_mb": 893, "all_mb": 1141.9,
        "quota_mb": {"PrivateSubscription": 17.2}, "quota_share": {"PrivateSubscription": 3.1},
        "warnings": ["PrivateSubscription: warning"]}}, {"PrivateSubscription"}, True)
    assert view["daily"]["total_mb"] == 893
    assert view["subscriptions"] == [{"subscription": 1, "quota_mb": 17.2, "quota_share": 3.1}]
    assert "30 дней" in view["quota_units"]["quota_share"]
    assert "PrivateSubscription" not in json.dumps(view)
    assert "не журнал" in view["source"]


def test_helpers_have_no_invisible_format_characters_or_bom():
    for name in ("cpu_snapshot.py", "singbox_generation_check.py"):
        raw = (HELPERS / name).read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert all(unicodedata.category(ch) != "Cf" for ch in raw.decode("utf-8"))
        assert b"\x00" not in raw


def test_cpu_units_keep_machine_and_single_core_separate(tmp_path, monkeypatch):
    (tmp_path / "uptime").write_text("100.0 0.0\n")
    clock = {"t": 0.0}
    monkeypatch.setattr(cpu, "PROC", tmp_path)
    monkeypatch.setattr(cpu.os, "sysconf", lambda key: 100)
    monkeypatch.setattr(cpu, "daemon_pid", lambda: 10)
    monkeypatch.setattr(cpu, "name_sources", lambda: (
        set(), {"inventory": True, "status": True, "database": True}, {}))
    monkeypatch.setattr(cpu, "save", lambda value: None)
    monkeypatch.setattr(cpu.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(cpu.time, "sleep", lambda span: clock.update(t=clock["t"] + span))
    monkeypatch.setattr(cpu, "system_stat", lambda: (
        1000 + clock["t"] * 200, 200 + clock["t"] * 40, 2))
    monkeypatch.setattr(cpu, "snapshot", lambda pid: {
        (10, 1): (1000 + clock["t"] * 10, "python3", "daemon"),
        (11, 2): (500 + clock["t"] * 50, "chrome", "other"),
    })
    result = cpu.measure(10)
    assert result["machine_all_cpus_mean_pct"] == 80.0
    assert result["xgw"]["daemon"]["cpu_one_core_mean_pct"] == 10.0
    assert result["top10"][0]["name"] == "chrome"
    assert result["top10"][0]["cpu_one_core_mean_pct"] == 50.0
    assert result["panel"]["separate_process_cpu_pct"] is None
