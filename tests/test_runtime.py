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
from xgw.xraycore.service import (
    PidfileXrayService,
    ProcessXrayService,
    XrayServiceError,
    pid_alive,
)

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
    owner = PidfileXrayService(sys.executable, tmp_path / "config.json", pid_file, grace=3)
    other = PidfileXrayService(sys.executable, tmp_path / "config.json", pid_file, grace=3)
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


def test_pidfile_stop_does_not_wait_for_a_zombie(tmp_path, fake_xray):
    """Xray запущен одной командой, остановлен другой: пока родитель его не снял,
    процесс остаётся в таблице (зомби), но живым считаться не должен — иначе
    остановка ждала бы весь grace."""
    pid_file = tmp_path / "xray.pid"
    owner = PidfileXrayService(sys.executable, tmp_path / "config.json", pid_file, grace=6)
    other = PidfileXrayService(sys.executable, tmp_path / "config.json", pid_file, grace=6)
    owner.start()
    pid = int(pid_file.read_text())
    started = time.monotonic()
    other.stop()
    assert time.monotonic() - started < 4
    assert not pid_alive(pid)
    deadline = time.monotonic() + 3
    while owner._proc is not None and time.monotonic() < deadline:
        assert not owner.is_active()
        time.sleep(0.05)
    assert owner._proc is None  # родитель снял свой процесс


def test_pidfile_service_reports_instant_crash(tmp_path, fake_xray):
    fake_xray["code"] = "import sys; print('failed to load config'); sys.exit(23)"
    service = PidfileXrayService(sys.executable, tmp_path / "config.json", tmp_path / "xray.pid")
    with pytest.raises(XrayServiceError, match="сразу после запуска"):
        service.start()
    assert not service.is_active()
    assert "failed to load config" in service.log_file.read_text()  # причина — в логе рядом


def test_process_service_says_why_xray_exited(tmp_path):
    # Вместо Xray — Python: на «run -c …» он сразу падает и пишет причину в stderr.
    service = ProcessXrayService(sys.executable, tmp_path / "config.json", grace=5)
    with pytest.raises(XrayServiceError, match=r"сразу после запуска: .*run") as caught:
        service.start()
    assert "\n" not in str(caught.value) and not service.is_active()


def test_status_line_tells_whether_ipv6_is_captured():
    capture = {"mode": "on", "lan_if": "lan0", "lan": True, "local": True, "bypass": [],
               "loaded": True}
    assert status.render_capture(capture) == "Перехват: включён — сеть lan0 и эта машина"
    line = status.render_capture({**capture, "ipv6": True})
    assert line == "Перехват: включён — сеть lan0 и эта машина с IPv6"
    # Строка остаётся подстрокой прежней: на неё опираются остальные проверки.
    assert "Перехват: включён — сеть lan0 и эта машина" in line
    both = status.render_capture({**capture, "ipv6": True, "tun": True})
    assert both == "Перехват: включён — сеть lan0 и эта машина через TUN с IPv6"
    assert status.render_capture({**capture, "tun": True}).endswith("эта машина через TUN")


def test_server_list_shows_priority_levels_only_when_they_are_set():
    member = {"tag": "proxy-nl-aaaa", "alive": True, "delay_ms": 80, "name": "NL-1",
              "priority": "medium"}
    spare = {"tag": "spare-de-bbbb", "verdict": None, "name": "DE-1", "priority": "medium"}
    plain = status.render_servers({"members": [member], "spares": [spare], "tier": "medium"})
    assert "уровень" not in plain and "[" not in plain
    text = status.render_servers({
        "members": [{**member, "priority": "high"}], "spares": [{**spare, "priority": "low"}],
        "tier": "high",
    })
    assert "Участники балансировщика (1), уровень приоритета «высокий»:" in text
    assert "NL-1 [высокий]" in text and "DE-1 [низкий]" in text


def test_status_line_names_the_tun_when_only_the_interface_is_not_ready():
    capture = {"mode": "on", "lan_if": "lan0", "lan": True, "local": True, "bypass": [],
               "loaded": False, "tun_problem": ""}
    assert status.render_capture(capture).endswith("ПРАВИЛА НЕ ЗАГРУЖЕНЫ (sudo xgw enable)")
    problem = "у интерфейса xgwtun0 нет адреса 169.254.10.1/32 или он не поднят"
    line = status.render_capture({**capture, "tun_problem": problem})
    assert line.endswith(f"ИНТЕРФЕЙС TUN НЕ ГОТОВ: {problem} (sudo xgw net up)")
    assert "ПРАВИЛА НЕ ЗАГРУЖЕНЫ" not in line


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
    cfg = Config()
    cfg.probe.url = "https://probe.example.net/blob?bytes=65536"
    budget = status.probe_budget(cfg, members=5, spares=0)
    assert budget.probes == 5 * 65536 * 2880 == 943_718_400
    assert budget.total == budget.probes  # сквозная проверка считается отдельно
    assert status.budget_warnings(cfg, budget, {}) == []

    with_spares = status.probe_budget(cfg, members=5, spares=60)
    assert with_spares.scans == 60 * 65536 * 24
    warnings = status.budget_warnings(cfg, with_spares, {})
    assert len(warnings) == 1 and "больше лимита 1024" in warnings[0]


def test_probe_budget_of_the_default_url_fits_the_daily_limit():
    """Файл пробы по умолчанию — 57 620 байт: 5 участников укладываются в 1024 МБ в
    сутки вместе со сканом шестидесяти пяти запасных (так было на живой машине)."""
    cfg = Config()
    budget = status.probe_budget(cfg, members=5, spares=65)
    assert budget.size == 57_620 and budget.measured is False
    assert budget.probes == 5 * 57_620 * 2880 == 829_728_000
    assert budget.scans == 65 * 57_620 * 24
    assert budget.total / status.MB < cfg.probe.max_daily_probe_mb
    assert status.budget_warnings(cfg, budget, {}) == []
    assert budget.everything == budget.probes + budget.scans + budget.e2e


def test_probe_budget_uses_the_measured_size(tmp_path):
    """Размер тела незнакомого probe.url узнаёт сквозная проверка: от него и считается
    расход. Запись относится к своему адресу — после смены probe.url она не годится."""
    store = Store(tmp_path / "state.db")
    cfg = Config()
    cfg.probe.url = "https://files.example.net/sample.bin"
    assert status.probe_budget(cfg, 5, 0).size == status.DEFAULT_PROBE_BYTES  # оценка
    status.remember_probe_size(store, cfg.probe.url, 87_533)
    size = status.measured_probe_size(store, cfg.probe.url)
    assert size == 87_533
    budget = status.probe_budget(cfg, 5, 0, size)
    assert budget.measured and budget.probes == 5 * 87_533 * 2880  # ~1260 МБ в сутки
    assert "больше лимита 1024" in status.budget_warnings(cfg, budget, {})[0]
    assert status.measured_probe_size(store, "https://other.example.net/x") is None
    status.remember_probe_size(store, cfg.probe.url, 0)  # пустое тело — не размер
    assert status.measured_probe_size(store, cfg.probe.url) == 87_533
    store.close()


def test_budget_does_not_advise_cuts_while_the_probe_size_is_a_guess():
    """probe.url не отвечает и размер его неизвестен (ни измерения, ни ?bytes=): расход
    посчитан по 64 КиБ наугад, и советовать по нему урезать проверки нельзя — на живой
    машине так получалось ~1041 МБ «больше лимита» при настоящих 57 620 байтах."""
    cfg = Config()
    cfg.probe.url = "https://127.0.0.1:9999/bad"
    budget = status.probe_budget(cfg, members=5, spares=63)
    assert budget.guessed and budget.total / status.MB > cfg.probe.max_daily_probe_mb
    assert status.budget_warnings(cfg, budget, {}) == []
    tight = {"main": {"upload": 10**9, "download": 95 * 10**9, "total": 100 * 10**9}}
    assert status.budget_warnings(cfg, budget, tight) == []
    spent = {"main": {"upload": 0, "download": 10**12, "total": 10**11}}
    assert status.budget_warnings(cfg, budget, spent) == ["квота подписки «main» исчерпана"]
    summary = status.budget_summary(cfg, budget, {}, 5, 63)
    assert summary["guessed"] is True
    text = "\n".join(status.render_budget(summary))
    assert "наугад: probe.url ещё не ответил ни разу" in text
    # Размер измерен — предупреждение снова по делу.
    measured = status.probe_budget(cfg, members=5, spares=63, size=65_536)
    assert not measured.guessed and status.budget_warnings(cfg, measured, {})


def test_budget_summary_shows_the_month_and_the_share_of_the_quota():
    cfg = Config()
    budget = status.probe_budget(cfg, members=5, spares=65)
    quotas = {"main": {"upload": 0, "download": 10**9, "total": 200 * 10**9}, "free": {}}
    summary = status.budget_summary(cfg, budget, quotas, 5, 65)
    assert summary["total_mb"] == 919.6 and summary["over"] is False
    assert summary["all_mb"] == round(budget.everything / 1e6, 1)
    assert summary["month_gb"] == round(budget.everything * 30 / 1e9, 1) == 35.1
    assert summary["quota_share"] == {"main": 17.5}  # 35,1 ГБ из 200 ГБ
    assert summary["probe_bytes"] == 57_620 and summary["interval_s"] == 30
    text = "\n".join(status.render_budget(summary))
    assert "Трафик проверок: ~920 МБ/сут" in text
    assert "~35.1 ГБ/мес" in text and "проба 57 620 Б (по оценке); участников — 5" in text
    assert "запасных — 65, скан раз в 60 мин" in text
    assert "за месяц это ~18 % квоты подписки «main»" in text
    cfg.probe.max_daily_probe_mb = 500
    over = status.budget_summary(cfg, budget, quotas, 5, 65)
    assert over["over"] is True and "больше лимита 500" in over["warnings"][0]


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
        "tag": "proxy-nl-aaaa", "fingerprint": "aaaa1111", "name": "NL-1", "source": "main",
        "alive": True,
        "delay_ms": 123, "dead_since": None, "priority": "medium",
    }
    assert snapshot["tier"] == "medium"
    assert snapshot["members"][1]["alive"] is None  # ядро по узлу ещё ничего не сообщило
    assert snapshot["spares"][0]["verdict"] == "FROZEN" and snapshot["spares"][0]["bytes"] == 16384
    assert snapshot["budget"]["total_mb"] > 0 and snapshot["pending_restart"] is False

    status.write_status(paths, snapshot)
    assert status.read_status(paths, max_age=60)["state"] == "HEALTHY"
    assert status.read_status(paths, max_age=-1) is None  # устаревший статус не показываем
    text = status.render_status(snapshot)
    assert "Состояние: HEALTHY" in text and "жив, 123 мс" in text and "нет данных" in text
    assert "FROZEN, 16384 Б" in text


def test_status_line_says_capture_waits_for_the_inbound():
    capture = {"mode": "on", "lan_if": "", "lan": False, "local": True, "bypass": [],
               "tun": True, "loaded": True,
               "inbound_missing": "в применённом конфиге Xray нет inbound tun-in для "
                                  "интерфейса xgwtun0"}
    line = status.render_capture(capture)
    assert line.startswith("Перехват: НЕ ВКЛЮЧЁН (ожидание применения inbound в Xray) — ")
    assert "tun-in" in line and "трафик идёт напрямую" in line and "xgw apply --now" in line
    # Перехват снят человеком — про inbound говорить незачем.
    assert "СНЯТ (xgw disable)" in status.render_capture({**capture, "mode": "off"})
    assert status.render_capture({**capture, "inbound_missing": ""}) == (
        "Перехват: включён — эта машина через TUN")


def test_status_shows_the_node_summary_and_the_probe_url_warning():
    assert status.render_nodes({}) == ""
    summary = {"members": 5, "spares": 65, "dropped": 4, "duplicates": 12, "excluded": 0,
               "dns": 2}
    line = status.render_nodes(summary)
    assert line.startswith(
        "Узлов: 5 активных, 65 запасных (отброшено 4 недоступных/служебных, "
        "схлопнуто 12 дублей)")
    assert "из отброшенных 2 — домен не разрешается" in line
    assert "отключено или убрано в панели: 3" in status.render_nodes({**summary, "excluded": 3})

    warning = "Внимание: пробы всех серверов падают — вероятно, недоступен сам probe.url (HTTP 403)"
    snapshot = {
        "daemon": True, "state": "PROBE_TARGET_UNREACHABLE", "action": "…", "since": None,
        "xray": {"ok": True, "version": "26.3.27"}, "members": [], "spares": [],
        "nodes": summary, "probe_target": warning,
    }
    text = status.render_status(snapshot)
    assert warning in text and "Узлов: 5 активных, 65 запасных" in text
