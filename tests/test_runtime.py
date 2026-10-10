"""Мелкие части этапа 2: разбор `xray api bi`, служба с pid-файлом, события,
статус и оценка трафика проверок."""

import subprocess
import sys
import time

import pytest

from xgw.config import Config
from xgw.generator.builder import NodeInfo
from xgw.paths import Paths
from xgw.store import Store
from xgw.watch import status
from xgw.watch.notify import Notifier
from xgw.xraycore import service as service_module
from xgw.xraycore.api import BalancerInfo, parse_balancer_info
from xgw.xraycore.service import PidfileXrayService, XrayServiceError, pid_alive

# --- xray api bi ---------------------------------------------------------------

BI_SELECTED = """  - Selecting Override:
    1
  - Selects:
    1   proxy-de-7de7
"""
BI_PINNED = """  - Selecting Override:
    1   proxy-nl-4657
  - Selects:
    1   proxy-de-7de7
    2   proxy-nl-4657
"""
BI_NOBODY = "  - Selecting Override:\n    1                 \n  - Selects:\n    1\n"


def test_parse_balancer_info():
    assert parse_balancer_info(BI_SELECTED) == BalancerInfo(None, ("proxy-de-7de7",))
    assert parse_balancer_info(BI_PINNED) == BalancerInfo(
        "proxy-nl-4657", ("proxy-de-7de7", "proxy-nl-4657")
    )
    assert parse_balancer_info(BI_NOBODY) == BalancerInfo(None, ())  # живых узлов нет
    assert parse_balancer_info("") == BalancerInfo(None, ())


# --- служба с pid-файлом -------------------------------------------------------


@pytest.fixture()
def fake_xray(monkeypatch):
    """Вместо xray запускается python-процесс, который просто живёт (или сразу падает)."""
    real_popen = subprocess.Popen
    behaviour = {"code": "import time; time.sleep(120)"}

    def popen(_argv, **kwargs):
        return real_popen([sys.executable, "-c", behaviour["code"]], **kwargs)

    monkeypatch.setattr(service_module.subprocess, "Popen", popen)
    return behaviour


def test_pidfile_service_is_shared_between_processes(tmp_path, fake_xray):
    pid_file = tmp_path / "run" / "xray.pid"
    owner = PidfileXrayService("xray", tmp_path / "config.json", pid_file, grace=3)
    other = PidfileXrayService("xray", tmp_path / "config.json", pid_file, grace=3)
    assert not owner.is_active()
    owner.start()
    try:
        pid = int(pid_file.read_text())
        assert owner.is_active() and other.is_active()  # «другая команда» видит тот же процесс
        owner.start()
        assert int(pid_file.read_text()) == pid  # повторный start ничего не запускает
        other.restart()  # перезапуск чужого процесса по pid-файлу
        assert other.is_active() and int(pid_file.read_text()) != pid
        assert not pid_alive(pid)
    finally:
        other.stop()
    assert not owner.is_active() and not pid_file.exists()


def test_pidfile_service_reports_instant_crash(tmp_path, fake_xray):
    fake_xray["code"] = "import sys; print('failed to load config'); sys.exit(23)"
    service = PidfileXrayService("xray", tmp_path / "config.json", tmp_path / "xray.pid")
    with pytest.raises(XrayServiceError, match="сразу после запуска"):
        service.start()
    assert not service.is_active()
    assert "failed to load config" in service.log_file.read_text()  # причина — в логе рядом


def test_pid_alive():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        assert pid_alive(proc.pid)
    finally:
        proc.terminate()
        proc.wait(timeout=5)
    assert not pid_alive(proc.pid)
    assert not pid_alive(0)


# --- события -------------------------------------------------------------------


def test_notifier_rate_limits_per_kind(tmp_path):
    now = {"t": 1000.0}
    sent: list[tuple[str, str]] = []
    notifier = Notifier(
        tmp_path / "state.db", 10, sinks=[lambda kind, text: sent.append((kind, text))],
        clock=lambda: now["t"],
    )
    assert notifier.event("DEGRADED", "часть серверов недоступна", notify=True) is True
    assert notifier.event("DEGRADED", "снова", notify=True) is False  # не чаще раза в 10 минут
    assert notifier.event("ALL_DEAD", "живых нет", notify=True) is True  # другой тип — сразу
    assert notifier.event("apply", "применено через API") is False  # просто запись
    now["t"] += 601
    assert notifier.event("DEGRADED", "опять", notify=True) is True
    assert [kind for kind, _text in sent] == ["DEGRADED", "ALL_DEAD", "DEGRADED"]
    store = Store(tmp_path / "state.db")
    assert len(store.recent_events(10)) == 5  # в журнал событий попадает всё
    store.close()


def test_notifier_masks_secrets_and_survives_bad_sink(tmp_path):
    def broken(_kind, _text):
        raise RuntimeError("telegram недоступен")

    notifier = Notifier(tmp_path / "state.db", 0, sinks=[broken])
    uuid = "11111111-2222-3333-4455-666666666661"
    assert notifier.event("config", f"битый узел vless://{uuid}@203.0.113.1:443", notify=True)
    store = Store(tmp_path / "state.db")
    detail = store.recent_events(1)[0]["detail"]
    store.close()
    assert uuid not in detail and "vless://***" in detail


# --- оценка трафика и статус ---------------------------------------------------


def test_probe_budget_matches_spec_example():
    """Раздел 6.8: 5 участников, 64 КиБ, 30 с — около 0,94 ГБ в сутки."""
    budget = status.probe_budget(Config(), members=5, spares=0)
    assert budget.probes == 5 * 65536 * 2880 == 943_718_400
    assert budget.total == budget.probes  # сквозная проверка считается отдельно
    assert status.budget_warnings(Config(), budget, {}) == []

    with_spares = status.probe_budget(Config(), members=5, spares=60)
    assert with_spares.scans == 60 * 65536 * 24
    warnings = status.budget_warnings(Config(), with_spares, {})
    assert len(warnings) == 1 and "больше лимита 1024" in warnings[0]


def test_budget_warns_about_quota():
    budget = status.probe_budget(Config(), members=5, spares=0)  # ~944 МБ/сут
    roomy = {"main": {"upload": 0, "download": 10**9, "total": 500 * 10**9}}
    assert status.budget_warnings(Config(), budget, roomy) == []
    tight = {"main": {"upload": 10**9, "download": 95 * 10**9, "total": 100 * 10**9}}
    warnings = status.budget_warnings(Config(), budget, tight)  # остаток 4 ГБ, 10 % = 400 МБ
    assert len(warnings) == 1 and "10 % остатка квоты" in warnings[0]
    spent = {"main": {"upload": 0, "download": 10**12, "total": 10**11}}
    assert "исчерпана" in status.budget_warnings(Config(), budget, spent)[0]
    assert status.budget_warnings(Config(), budget, {"main": {"total": 0}}) == []  # безлимит


def test_collect_status_and_freshness(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    store = Store(paths.db_file)
    store.replace_nodes([
        {"fingerprint": "aaaa1111", "tag": "proxy-nl-aaaa", "role": "proxy", "name": "NL-1",
         "source": "main", "address": "203.0.113.1", "port": 443, "updated": 0},
    ])
    store.save_scan("probe-de-bbbb", "FROZEN", 16384, 5.2, "тишина 5 с после 16384 байт тела")
    store.close()
    view = [
        NodeInfo("aaaa1111", "proxy-nl-aaaa", "probe-nl-aaaa", 20001, "proxy"),
        NodeInfo("cccc3333", "proxy-fr-cccc", "probe-fr-cccc", 20003, "proxy"),
        NodeInfo("bbbb2222", "spare-de-bbbb", "probe-de-bbbb", 20002, "spare"),
    ]
    observatory = {"proxy-nl-aaaa": {"alive": True, "delay": 0.123}}
    snapshot = status.collect_status(
        Config(), paths, view, observatory=observatory, xray_ok=True,
        state="HEALTHY", action="вмешательство не требуется", since=time.time(), daemon=True,
    )
    assert snapshot["members"][0] == {
        "tag": "proxy-nl-aaaa", "name": "NL-1", "alive": True, "delay_ms": 123, "dead_since": None,
    }
    assert snapshot["members"][1]["alive"] is None  # ядро по узлу ещё ничего не сообщило
    assert snapshot["spares"][0]["verdict"] == "FROZEN" and snapshot["spares"][0]["bytes"] == 16384
    assert snapshot["budget"]["total_mb"] > 0 and snapshot["pending_restart"] is False

    status.write_status(paths, snapshot)
    assert status.read_status(paths, max_age=60)["state"] == "HEALTHY"
    assert status.read_status(paths, max_age=-1) is None  # устаревший статус не показываем
    text = status.render_status(snapshot)
    assert "Состояние: HEALTHY" in text and "жив, 123 мс" in text and "нет данных" in text
    assert "FROZEN, 16384 Б" in text
