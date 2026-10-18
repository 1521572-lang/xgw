"""Основной сервер (0.1.9): демон выбирает самый быстрый из серверов в работе, закрепляет
его в ядре и держит, пока он работает; при отказе сразу передаёт трафик живому."""

import json

import pytest
from test_daemon import FakeApi, Harness, _inventory

from xgw import engine
from xgw.config import Config
from xgw.paths import Paths
from xgw.store import Store
from xgw.watch.states import State
from xgw.xraycore.api import BalancerInfo


class StickyApi(FakeApi):
    """Ядро, которое помнит закрепление (bo / bo -r), как настоящее."""

    def pin(self, balancer, tag):
        super().pin(balancer, tag)
        self.state = BalancerInfo(override=tag, selects=self.state.selects)

    def unpin(self, balancer):
        super().unpin(balancer)
        self.state = BalancerInfo(override=None, selects=self.state.selects)


def _free_inventory() -> engine.Inventory:
    """Те же серверы, но подписка безлимитная: скорость замеряется."""
    limited = _inventory()
    return engine.Inventory(limited.nodes, {}, True)


def _config() -> Config:
    cfg = Config()
    cfg.filters.max_members = 2
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []
    return cfg


def _make(paths: Paths, source=None) -> Harness:
    instance = Harness(_config(), paths)
    instance.api = StickyApi()
    instance.source = source or _free_inventory()
    return instance


@pytest.fixture()
def paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    return paths


@pytest.fixture()
def daemon(paths):
    instance = _make(paths)
    yield instance
    instance.store.close()


def _start(daemon: Harness) -> list[str]:
    """Первый шаг (конфиг собран, всё просканировано), участники живы; теги участников."""
    daemon.tick()
    daemon.set_alive()
    daemon.measured.clear()
    return daemon.tags("proxy")


def _step(daemon: Harness, seconds: float = 20.0) -> State:
    daemon.t += seconds
    return daemon.tick()


def _main_events(daemon: Harness) -> list[str]:
    return [event for event in daemon.events() if event.startswith("main:")]


def test_main_is_pinned_and_switched_to_the_fastest_after_the_first_round(daemon):
    """Сначала основной — по задержке (замеров ещё нет), после раунда замеров — самый
    быстрый; выбор по задержке держится без срока удержания."""
    first, second = _start(daemon)
    daemon.speeds = {first: 30.0, second: 90.0}
    daemon.observatory[second]["delay"] = 0.2  # по задержке лучше первый
    _step(daemon)
    assert daemon.main["tag"] == first and daemon.main["basis"] == "delay"
    assert daemon.api.state.override == first
    assert daemon.measured == [first]  # один замер за шаг
    _step(daemon)
    assert sorted(daemon.measured) == sorted([first, second])
    assert daemon.main["tag"] == second and daemon.main["basis"] == "speed"
    assert daemon.api.state.override == second
    events = _main_events(daemon)
    assert any("по задержке" in event for event in events)
    assert any("сменён" in event and "90 Мбит/с" in event and "30 Мбит/с" in event
               for event in events)
    # Дальше — ни замеров, ни смен: следующий раунд через speed.every_hours.
    for _ in range(10):
        _step(daemon)
    assert len(daemon.measured) == 2 and daemon.api.state.override == second
    assert daemon.api.calls.count(("pin", second)) == 1  # закреплено один раз


def test_main_is_not_changed_for_a_small_gain_or_before_the_hold(daemon):
    first, second = _start(daemon)
    daemon.observatory[second]["delay"] = 0.2  # по задержке лучше первый
    daemon.speeds = {first: 50.0, second: 60.0}  # быстрее на 20 % — меньше gain_pct
    for _ in range(3):
        _step(daemon)
    assert daemon.main["tag"] == first and daemon.main["basis"] == "speed"
    # Через 10 минут второй стал быстрее вдвое, но основной держится меньше hold_minutes.
    daemon.speeds = {first: 50.0, second: 100.0}
    daemon.t += 600
    daemon.request_speed()
    for _ in range(3):
        _step(daemon)
    assert daemon.main["tag"] == first
    # Через час — уже можно.
    daemon.t += 3600
    daemon.request_speed()
    for _ in range(3):
        _step(daemon)
    assert daemon.main["tag"] == second and daemon.api.state.override == second


def test_dead_main_is_replaced_at_once_and_not_taken_back(daemon):
    first, second = _start(daemon)
    daemon.observatory[second]["delay"] = 0.2  # по задержке лучше первый
    daemon.speeds = {first: 90.0, second: 30.0}
    for _ in range(3):
        _step(daemon)
    assert daemon.api.state.override == first
    daemon.set_alive(**{first.replace("-", "_"): False})
    assert _step(daemon) is State.DEGRADED
    assert daemon.main["tag"] == second and daemon.api.state.override == second
    assert any("не отвечает пробам ядра" in event for event in _main_events(daemon))
    # Ожил и он быстрее — но основной не скачет назад: держится, пока работает.
    daemon.set_alive()
    for _ in range(5):
        _step(daemon)
    assert daemon.api.state.override == second


def test_failed_download_moves_the_main_and_a_second_failure_hands_back_to_the_core(daemon):
    """Загрузка не прошла через основной — смена сразу. Не прошла и через новый — дело не в
    серверах: закрепление снимается, пока загрузка снова не пройдёт."""
    first, second = _start(daemon)
    daemon.speeds = {first: 90.0, second: 30.0}
    for _ in range(3):
        _step(daemon)
    daemon.e2e = False
    assert _step(daemon) is State.HEALTHY
    assert daemon.api.state.override == second
    _step(daemon)
    assert daemon.main is None and daemon.api.state.override is None
    assert any("дело, похоже, не в серверах" in event for event in _main_events(daemon))
    daemon.e2e = True
    _step(daemon)
    assert daemon.api.state.override is not None
    assert any("снова проходит" in event for event in _main_events(daemon))


def test_manual_pin_wins_and_the_main_returns_after_it(daemon):
    first, second = _start(daemon)
    daemon.speeds = {first: 90.0, second: 30.0}
    for _ in range(3):
        _step(daemon)
    until = daemon.t + 300
    daemon.store.set_meta("pin", json.dumps({"tag": second, "until": until}))
    daemon.api.state = BalancerInfo(override=second, selects=())
    calls = len(daemon.api.calls)
    for _ in range(3):
        _step(daemon)
    assert daemon.api.calls[calls:] == []  # ручное закрепление демон не трогает
    daemon.t = until + 1
    daemon.tick()
    assert daemon.api.state.override == first  # срок вышел — снова основной
    assert ("unpin",) in daemon.api.calls[calls:]


def test_speed_is_measured_while_a_server_is_pinned_by_hand(daemon):
    """Ручной выбор бессрочный (кнопка «Выбрать»): основной не выбирается, но участники
    замеряются по расписанию и по кнопке — иначе строки серверов остались бы без скорости."""
    first, second = _start(daemon)
    daemon.speeds = {first: 30.0, second: 90.0}
    daemon.store.set_meta("pin", json.dumps({"tag": first, "until": None}))
    daemon.api.state = BalancerInfo(override=first, selects=())
    for _ in range(3):
        _step(daemon)
    assert sorted(daemon.measured) == sorted([first, second])
    assert daemon.main is None and daemon.api.state.override == first
    assert ("pin", second) not in daemon.api.calls  # закрепление ручное, его не трогают
    daemon.request_speed()
    for _ in range(3):
        _step(daemon)
    assert len(daemon.measured) == 4 and not daemon.speed_pending
    # Выбор сняли — основной сразу по замерам, сделанным при выборе, а не по задержке.
    daemon.store.set_meta("pin", "")
    daemon.api.unpin("balancer")
    _step(daemon)
    assert daemon.main["tag"] == second and daemon.main["basis"] == "speed"
    assert daemon.api.state.override == second and len(daemon.measured) == 4


def test_round_finished_during_a_pin_moves_the_main_when_the_pin_ends(daemon):
    """Раунд прошёл при ручном выборе и другой оказался заметно быстрее — основной меняется
    на первом же шаге после снятия выбора, а не через speed.every_hours."""
    first, second = _start(daemon)
    daemon.speeds = {first: 90.0, second: 30.0}
    for _ in range(3):
        _step(daemon)
    assert daemon.main["tag"] == first
    until = daemon.t + 7200  # дольше speed.hold_minutes
    daemon.store.set_meta("pin", json.dumps({"tag": second, "until": until}))
    daemon.api.state = BalancerInfo(override=second, selects=())
    daemon.speeds = {first: 30.0, second: 90.0}
    daemon.request_speed()
    for _ in range(3):
        _step(daemon)
    assert len(daemon.measured) == 4 and not daemon.speed_pending
    assert daemon.main["tag"] == first and daemon.api.state.override == second
    daemon.t = until + 1
    daemon.tick()
    assert daemon.main["tag"] == second and daemon.api.state.override == second
    assert len(daemon.measured) == 4
    assert any("сменён" in event and "90 Мбит/с" in event for event in _main_events(daemon))


def test_x100_servers_are_not_measured_while_pinned(paths):
    """При ручном выборе цена загрузки та же: x100 не замеряются и по кнопке."""
    daemon = _make(paths, source=_inventory())
    try:
        first, _second = _start(daemon)
        prices = daemon._prices()
        daemon._prices = lambda: dict.fromkeys(prices, 100.0)
        daemon.store.set_meta("pin", json.dumps({"tag": first, "until": None}))
        daemon.api.state = BalancerInfo(override=first, selects=())
        daemon.request_speed()
        for _ in range(3):
            _step(daemon)
        assert daemon.measured == [] and not daemon.speed_pending
    finally:
        daemon.store.close()


def test_main_is_released_when_no_member_answers(daemon):
    """Без живых участников закрепление снимается: иначе трафик стоял бы на мёртвом сервере,
    а резервный выход (fallbackTag) не сработал бы — закрепление обходит здоровье."""
    first, second = _start(daemon)
    for _ in range(3):
        _step(daemon)
    assert daemon.api.state.override is not None
    daemon.set_alive(**{first.replace("-", "_"): False, second.replace("-", "_"): False})
    assert _step(daemon) is State.ALL_DEAD
    assert daemon.api.state.override is None and daemon.main is None


def test_limited_servers_are_measured(paths):
    """Лимитированные x1 замеряются, как безлимитные: основной — по скорости."""
    daemon = _make(paths, source=_inventory())  # подписка с лимитом трафика
    try:
        first, second = _start(daemon)
        daemon.speeds = {first: 30.0, second: 90.0}
        for _ in range(4):
            _step(daemon)
        assert sorted(daemon.measured) == sorted([first, second])
        assert daemon.main["tag"] == second and daemon.main["basis"] == "speed"
    finally:
        daemon.store.close()


def test_x100_servers_are_not_measured(paths):
    """x100 — серверы для LTE: замер стоил бы 100 МБ квоты, основной — по задержке."""
    daemon = _make(paths, source=_inventory())
    try:
        first, second = _start(daemon)
        prices = daemon._prices()
        daemon._prices = lambda: dict.fromkeys(prices, 100.0)
        daemon.observatory[first]["delay"] = 0.3
        for _ in range(4):
            _step(daemon)
        assert daemon.measured == []
        assert daemon.main["tag"] == second and daemon.main["basis"] == "delay"
        daemon.request_speed()
        _step(daemon)
        assert daemon.measured == [] and not daemon.speed_pending
    finally:
        daemon.store.close()


def test_speed_test_waits_while_the_channel_is_busy(daemon):
    daemon.traffic = 0
    _start(daemon)
    daemon.traffic += 10_000_000  # 10 МБ за шаг — через серверы кто-то качает
    _step(daemon)
    assert daemon.measured == [] and daemon.main is not None  # основной есть и без замера
    _step(daemon)  # канал свободен
    assert len(daemon.measured) == 1


def test_main_survives_a_daemon_restart(paths):
    daemon = _make(paths)
    first, second = _start(daemon)
    daemon.speeds = {first: 30.0, second: 90.0}
    for _ in range(3):
        _step(daemon)
    assert daemon.main["tag"] == second
    events = len(_main_events(daemon))
    daemon.store.close()

    restarted = _make(paths)  # Xray тоже перезапущен: закрепления в ядре нет
    try:
        restarted.t = daemon.t + 20
        restarted.observatory = dict(daemon.observatory)
        restarted.tick()
        assert restarted.api.state.override == second
        assert len(_main_events(restarted)) == events  # тот же основной, без нового выбора
        assert restarted.measured == []  # замеры свежие — раунд по расписанию, не сразу
    finally:
        restarted.store.close()


def test_status_shows_the_main_and_speeds(daemon):
    first, second = _start(daemon)
    daemon.speeds = {first: 30.0, second: 8.5}
    for _ in range(3):
        _step(daemon)
    status = daemon.status()
    assert status["sticky"] is True
    assert status["main"]["tag"] == first and status["main"]["mbps"] == 30.0
    by_tag = {member["tag"]: member for member in status["members"]}
    assert by_tag[first]["main"] and not by_tag[second]["main"]
    assert by_tag[second]["speed_mbps"] == 8.5
    assert status["budget"]["speed_mb"] > 0
    from xgw.watch.status import render_status

    text = render_status(status)
    assert f"Основной сервер: {first}" in text and "30 Мбит/с" in text
    assert "8,5 Мбит/с" in text and "← основной" in text


def test_failed_measurement_is_shown_and_not_repeated_until_the_round(daemon):
    first, second = _start(daemon)
    daemon.speeds = {first: None, second: 40.0}
    for _ in range(6):
        _step(daemon)
    assert daemon.measured.count(first) == 1
    assert daemon.main["tag"] == second  # у первого замер не удался
    member = next(m for m in daemon.status()["members"] if m["tag"] == first)
    assert member["speed_mbps"] is None and "тишина" in member["speed_error"]


def test_sticky_off_removes_a_leftover_main_pin(paths):
    """Основной выключили — закрепление от прошлого запуска демон снимает сам."""
    daemon = _make(paths)
    daemon.cfg.speed.sticky = False
    first, _second = _start(daemon)
    assert daemon.api.calls == []
    daemon.store.close()
    again = _make(paths)
    try:
        again.cfg.speed.sticky = False
        again.api.state = BalancerInfo(override=first, selects=())
        again.t = daemon.t + 20
        again.observatory = dict(daemon.observatory)
        again.tick()
        assert again.api.state.override is None
    finally:
        again.store.close()


def test_status_without_sticky(daemon):
    daemon.cfg.speed.sticky = False
    _start(daemon)
    _step(daemon)
    status = daemon.status()
    assert status["sticky"] is False and status["main"] is None
    assert status["budget"]["speed_mb"] == 0
    store = Store(daemon.paths.db_file)
    try:
        assert not store.get_meta("main")
    finally:
        store.close()


def test_servers_of_unknown_price_are_not_measured(daemon):
    """Подписка ещё не сопоставлена с узлами (не получена после запуска) — цена неизвестна,
    и замера нет: сервер мог бы оказаться лимитированным."""
    _start(daemon)
    daemon._prices = lambda: {}
    for _ in range(3):
        _step(daemon)
    assert daemon.measured == [] and daemon.main is not None
