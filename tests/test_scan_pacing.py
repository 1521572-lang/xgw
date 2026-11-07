"""Волна 1 (ASSUMPTIONS п. 330): плановые сканы запасных — с паузой внутри бюджета шага,
срочные и ручные — без паузы, очередь без дубликатов и потерь."""

import pytest
from test_daemon import Harness, _started

from xgw import engine
from xgw.config import Config
from xgw.daemon import SCAN_BUDGET, SCAN_GAP
from xgw.paths import Paths
from xgw.watch.states import State


@pytest.fixture()
def daemon(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.filters.max_members = 2
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []
    cfg.speed.sticky = False
    cfg.speed.unlimited_hours = cfg.speed.limited_hours = 0
    instance = Harness(cfg, paths)
    yield instance
    instance.store.close()


def _spares(daemon) -> list[str]:
    return [info.probe_tag for info in daemon.view() if info.role == "spare"]


def _fresh_pace(daemon) -> None:
    """Счётчики темпа — с нуля: первый шаг _started тоже сканировал."""
    daemon._scan_pace.clear()
    daemon._pace_stats.update(planned=0, planned_min=None, planned_max=None,
                              planned_outside=0, idle_max=None, urgent=0, urgent_waited=0)


def _step(daemon) -> None:
    daemon._scan_step(daemon.view(), engine.read_json(daemon.paths.xray_config_file))


def test_planned_spares_are_spaced_inside_the_budget(daemon):
    _started(daemon)
    _fresh_pace(daemon)
    gaps = []

    def gap(seconds):
        gaps.append(seconds)
        daemon.t += seconds  # пауза идёт по часам демона и входит в SCAN_BUDGET
        return False

    daemon._scan_gap = gap
    daemon.next_scan = 0.0
    assert daemon.tick() is State.HEALTHY
    assert len(daemon.scanned) == 3 and len(gaps) == 2  # перед первой пробой шага паузы нет
    assert all(SCAN_GAP[0] <= item <= SCAN_GAP[1] for item in gaps)
    pacing = daemon.status()["scan_pacing"]
    # Демон округляет измеренную паузу (разность часов), тест — заданную: на границе сотых
    # они расходятся на 0,01 (отчёт diag-limit: 3 из 18 прогонов) — сравнение с допуском.
    assert pacing["planned_gaps_s"] == pytest.approx(gaps, abs=0.011)
    assert pacing["totals"]["planned"] == 2 and pacing["totals"]["planned_outside"] == 0
    assert pacing["next_planned_in_s"] > 0


def test_urgent_manual_and_degraded_scans_wait_for_nothing(daemon):
    _started(daemon)
    _fresh_pace(daemon)
    daemon.gaps = []
    for tag in _spares(daemon):
        daemon._queue_first(tag, urgent=True)
    daemon._queue_first(_spares(daemon)[0], urgent=True)  # повтор — без дубликата
    assert len(daemon.scan_queue) == 3
    daemon.tick()
    assert len(daemon.scanned) == 3 and daemon.gaps == [] and not daemon._scan_urgent
    totals = daemon._pacing()["totals"]
    assert totals["urgent"] >= 2 and totals["urgent_waited"] == 0
    for state, manual in ((State.HEALTHY, True), (State.DEGRADED, False)):
        daemon.machine.state, daemon._manual_scan = state, manual
        daemon.scan_queue.extend(_spares(daemon))
        _step(daemon)
        assert daemon.gaps == [] and not daemon.scan_queue


def test_no_new_probe_after_the_budget_and_stop_keeps_the_queue(daemon):
    _started(daemon)
    original = daemon._scan
    started = []

    def slow(info, password, url=None):
        started.append(daemon.t)
        daemon.t += 3.0
        return original(info, password, url)

    daemon._scan = slow
    daemon._scan_gap = lambda seconds: (setattr(daemon, "t", daemon.t + seconds), False)[1]
    daemon.next_scan = 0.0
    daemon.tick()
    assert started and all(moment - started[0] < SCAN_BUDGET for moment in started)
    assert len(daemon.scan_queue) == 3 - len(started)  # не начатые ждут следующего шага
    daemon.scan_queue.clear()
    daemon.scan_queue.extend(_spares(daemon))
    daemon._scan_gap = lambda seconds: True  # остановка во время паузы
    _step(daemon)
    assert list(daemon.scan_queue) == _spares(daemon)[1:]  # первая прошла, остальные ждут


def test_emergency_requeue_raises_priority_and_drops_vanished_tags(daemon):
    _started(daemon)
    first, second, third = _spares(daemon)
    daemon.scan_queue.extend([first, second])
    daemon.machine.state = State.ALL_DEAD
    daemon._queue_scan(daemon.view(), daemon.t)
    queue = list(daemon.scan_queue)
    assert sorted(queue) == sorted([first, second, third]) and len(queue) == len(set(queue))
    daemon.scan_queue.appendleft("probe-gone-0000")  # сервера уже нет в конфиге
    _step(daemon)
    assert "probe-gone-0000" not in daemon.scan_queue and len(daemon.scanned) == 3


def test_equal_priority_order_is_shuffled_but_ranked_order_kept(daemon):
    _started(daemon)
    orders = set()
    for _ in range(12):
        daemon.scan_queue.clear()
        daemon._queue_scan(daemon.view(), daemon.t)
        scores = [daemon._score(info) for info in daemon.view() if info.role == "spare"]
        orders.add(tuple(daemon.scan_queue))
        ranked = {info.probe_tag: daemon._score(info) for info in daemon.view()}
        values = [ranked[tag] for tag in daemon.scan_queue]
        assert values == sorted(values, reverse=True)  # рейтинг по-прежнему главнее
    if len(set(scores)) == 1:
        assert len(orders) > 1  # равный рейтинг — порядок меняется от круга к кругу
