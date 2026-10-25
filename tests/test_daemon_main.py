"""Основной сервер (0.1.9): демон выбирает самый быстрый из серверов в работе, закрепляет
его в ядре и держит, пока он работает; при отказе сразу передаёт трафик живому."""

import json
import threading

import pytest
from test_daemon import FakeApi, Harness, _inventory

from xgw import engine
from xgw.config import Config
from xgw.paths import Paths
from xgw.store import Store
from xgw.watch.speed import SpeedResult
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
    # Расписание issue #1 (все живые — раз в час): эти тесты — про него. Реже, как с 0.1.18 по
    # умолчанию, и контроль скорости — в своих тестах.
    cfg.speed.unlimited_hours = 1
    cfg.speed.spare_hours = 0
    cfg.speed.guard = False
    return cfg


def _make(paths: Paths, source=None) -> Harness:
    instance = Harness(_config(), paths)
    instance.api = StickyApi()
    instance.source = source or _free_inventory()
    # Запасные (и участники без своей цифры) медленные: основной выбирается из участников.
    # Перевод быстрого запасного в работу — в своих тестах.
    instance.default_speed = 5.0
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


def _settle(daemon: Harness, seconds: float = 20.0) -> None:
    """Шаги, пока очередь замеров не опустеет: фоновый замер — один сервер за шаг."""
    for _ in range(30):
        _step(daemon, seconds)
        if not daemon.speed_queue:
            return
    raise AssertionError(f"очередь замеров не опустела: {list(daemon.speed_queue)}")


def _main_events(daemon: Harness) -> list[str]:
    return [event for event in daemon.events() if event.startswith("main:")]


def test_main_is_the_fastest_and_every_live_server_is_measured_hourly(daemon):
    """Issue #1: замеряются все живые серверы — участники и запасные, каждый раз в
    speed.unlimited_hours, а не раунд по участникам раз в 6 часов. Основной — самый быстрый
    по замеру, сразу; между замерами смен нет."""
    first, second = _start(daemon)
    daemon.speeds = {first: 30.0, second: 90.0}
    daemon.observatory[second]["delay"] = 0.2  # по задержке лучше первый
    _step(daemon)
    # Фоновый замер — один сервер за шаг (шаг watchdog не затягивается), участники первыми.
    # Пока второй не замерен, выбор основного предварительный.
    assert daemon.measured == [first]
    assert daemon.main["tag"] == first and daemon.main["basis"] == "delay"
    _step(daemon)
    assert daemon.measured == [first, second]
    assert daemon.main["tag"] == second and daemon.main["basis"] == "speed"
    assert daemon.api.state.override == second
    _settle(daemon)
    spares = daemon.tags("spare")
    assert spares and set(spares) <= set(daemon.measured)  # и запасные
    assert any("остальные ещё замеряются" in event for event in _main_events(daemon))
    measured = len(daemon.measured)
    for _ in range(10):
        _step(daemon)
    assert len(daemon.measured) == measured  # замеры свежие — до срока не повторяются
    daemon.t += 3600
    _settle(daemon)
    assert {first, second, *spares} <= set(daemon.measured[measured:])
    assert daemon.api.calls.count(("pin", second)) == 1  # закреплено один раз


def test_main_is_not_changed_for_a_small_gain_or_before_the_hold(daemon):
    first, second = _start(daemon)
    daemon.speeds = {first: 60.0, second: 50.0}
    _settle(daemon)
    assert daemon.main["tag"] == first and daemon.main["basis"] == "speed"
    # Через 10 минут второй быстрее на 17 % — меньше gain_pct.
    daemon.speeds = {first: 60.0, second: 70.0}
    daemon.t += 600
    daemon.request_speed()
    _step(daemon)
    assert daemon.main["tag"] == first
    # Второй стал быстрее вдвое, но основной держится меньше hold_minutes.
    daemon.speeds = {first: 60.0, second: 120.0}
    daemon.request_speed()
    _step(daemon)
    assert daemon.main["tag"] == first
    # Через час — уже можно (замер по расписанию, без кнопки).
    daemon.t += 3600
    _settle(daemon)
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
    """Ручной выбор бессрочный (кнопка «Выбрать»): основной не выбирается, но серверы
    замеряются по расписанию и по кнопке — иначе строки серверов остались бы без скорости."""
    first, second = _start(daemon)
    daemon.speeds = {first: 30.0, second: 90.0}
    daemon.store.set_meta("pin", json.dumps({"tag": first, "until": None}))
    daemon.api.state = BalancerInfo(override=first, selects=())
    for _ in range(3):
        _step(daemon)
    assert {first, second} <= set(daemon.measured)
    assert daemon.main is None and daemon.api.state.override == first
    assert ("pin", second) not in daemon.api.calls  # закрепление ручное, его не трогают
    measured = len(daemon.measured)
    daemon.request_speed()
    _step(daemon)
    assert {first, second} <= set(daemon.measured[measured:]) and not daemon.speed_pending
    measured = len(daemon.measured)
    # Выбор сняли — основной сразу по замерам, сделанным при выборе, а не по задержке.
    daemon.store.set_meta("pin", "")
    daemon.api.unpin("balancer")
    _step(daemon)
    assert daemon.main["tag"] == second and daemon.main["basis"] == "speed"
    assert daemon.api.state.override == second and len(daemon.measured) == measured


def test_round_finished_during_a_pin_moves_the_main_when_the_pin_ends(daemon):
    """Замеры прошли при ручном выборе и другой оказался заметно быстрее — основной
    меняется на первом же шаге после снятия выбора."""
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
    _step(daemon)
    assert not daemon.speed_pending
    assert daemon.main["tag"] == first and daemon.api.state.override == second
    daemon.t = until + 1
    daemon.tick()
    assert daemon.main["tag"] == second and daemon.api.state.override == second
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
    """Лимитированные x1 замеряются, как безлимитные, но раз в speed.limited_hours."""
    daemon = _make(paths, source=_inventory())  # подписка с лимитом трафика
    try:
        first, second = _start(daemon)
        daemon.speeds = {first: 30.0, second: 90.0}
        _settle(daemon)
        assert {first, second} <= set(daemon.measured)
        assert daemon.main["tag"] == second and daemon.main["basis"] == "speed"
        measured = len(daemon.measured)
        daemon.t += 3600 * 2  # безлимитных было бы пора замерить, лимитированных — нет
        _step(daemon)
        _step(daemon)
        assert len(daemon.measured) == measured
        daemon.t += 3600 * 4
        _settle(daemon)
        assert {first, second} <= set(daemon.measured[measured:])
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


def _busy_step(daemon: Harness, seconds: float = 20.0) -> None:
    """Шаг, за который через серверы прошло ~1 МБ/с чужого трафика: канал занят."""
    daemon.traffic += int(seconds * 1_000_000)
    _step(daemon, seconds)


def test_speed_test_waits_while_the_channel_is_busy_but_not_for_ever(daemon):
    """Issue #1: на домашнем шлюзе канал занят почти всегда, и замеры не проходили вовсе.
    Фоновый замер ждёт свободного канала не дольше SPEED_FORCE_AFTER (час), а потом
    проходит с пометкой «канал был занят»."""
    daemon.traffic = 0
    first, second = _start(daemon)
    _busy_step(daemon)
    assert daemon.measured == [] and daemon.main is not None  # основной есть и без замера
    for _ in range(10):
        _busy_step(daemon, 300)  # 50 минут занятого канала
    assert daemon.measured == []
    assert daemon.status()["speed"]["deferred"] is True
    member = next(m for m in daemon.status()["members"] if m["tag"] == first)
    assert member["speed_note"] == "замер отложен: канал занят"
    _busy_step(daemon, 900)
    for _ in range(5):  # по одному серверу за шаг; шаг скана запасных замер пропускает
        if {first, second} <= set(daemon.measured):
            break
        _busy_step(daemon)
    assert {first, second} <= set(daemon.measured)
    record = daemon._speeds()[next(i.fingerprint for i in daemon.view() if i.tag == first)]
    assert record["busy"] is True


def test_speed_button_does_not_wait_for_the_channel(daemon):
    """Замер по кнопке — сразу, и при занятом канале; прогресс «N из M» виден в статусе."""
    daemon.traffic = 0
    first, second = _start(daemon)
    _busy_step(daemon)
    assert daemon.measured == []
    daemon.request_speed()
    _busy_step(daemon)
    everyone = {first, second, *daemon.tags("spare")}
    assert everyone <= set(daemon.measured) and not daemon.speed_pending


def test_free_channel_is_measured_at_once(daemon):
    daemon.traffic = 0
    first, _second = _start(daemon)
    _step(daemon)  # канал свободен
    assert daemon.measured[0] == first


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


def test_measurement_cut_by_a_stop_is_not_recorded(daemon):
    """Отчёт 0.1.15, Д2: остановка демона прерывает замер скорости. Прерванный замер — не
    неудача сервера: в базу он не попадает, сервер снова в очереди."""
    first, _second = _start(daemon)
    stop = threading.Event()
    before = json.loads(daemon.store.get_meta("speed") or "{}")

    def cut(info, password, *, small=False):
        daemon.measured.append(info.tag)
        stop.set()
        return SpeedResult(None, 4096, 0.4, "проверка прервана: демон останавливается")

    daemon._speed = cut
    daemon.t += 20
    daemon.run(stop)
    daemon.store = Store(daemon.paths.db_file)
    assert daemon.measured == [first]
    assert json.loads(daemon.store.get_meta("speed") or "{}") == before
    assert next(i.probe_tag for i in daemon.view() if i.tag == first) in daemon.speed_queue


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


def test_faster_spare_is_promoted_and_becomes_the_main(daemon):
    """Самый живой сервер может лежать в запасных (issue #1): запасной быстрее основного на
    gain_pct — после hold_minutes он встаёт в работу вместо слабейшего участника (не
    основного) и, проверенный ядром, становится основным."""
    first, second = _start(daemon)
    fast = daemon.tags("spare")[0]
    fingerprint = next(i.fingerprint for i in daemon.view() if i.tag == fast)
    daemon.speeds = {first: 60.0, second: 30.0, fast: 200.0}
    _settle(daemon)
    assert daemon.main["tag"] == first  # основной держится hold_minutes
    daemon.t += 3600
    for _ in range(30):
        _step(daemon)
        if fingerprint in {i.fingerprint for i in daemon.view() if i.role == "proxy"}:
            break
    members = {i.fingerprint: i.tag for i in daemon.view() if i.role == "proxy"}
    assert fingerprint in members and second not in daemon.tags("proxy")
    assert daemon.main["tag"] == first  # ядро новый участник ещё не проверило
    assert any("встаёт в работу вместо" in event for event in _main_events(daemon))
    daemon.set_alive()
    daemon.speeds[members[fingerprint]] = 200.0
    _step(daemon)
    assert daemon.main["tag"] == members[fingerprint]
    assert daemon.api.state.override == members[fingerprint]
    assert any("из запасных быстрее" in event for event in _main_events(daemon))


def test_main_is_replaced_by_the_same_country(daemon):
    """Основной отказал: замена ищется той же страны (страна и подписка отказавшего — в
    записи об основном), и событие это называет."""
    first, second = _start(daemon)
    daemon.speeds = {first: 90.0, second: 30.0}
    _step(daemon)
    assert daemon.main["tag"] == first
    country = daemon._node(next(i for i in daemon.view() if i.tag == second)).country
    assert country
    daemon._set_main(daemon._candidate(next(i for i in daemon.view() if i.tag == first), {}))
    daemon.main = {**daemon.main, "country": country, "source": "другая"}
    daemon.set_alive(**{first.replace("-", "_"): False})
    _step(daemon)
    assert daemon.main["tag"] == second
    assert any("той же страны" in event for event in _main_events(daemon))


def test_one_server_is_measured_by_its_own_button(daemon):
    """Пожелание заказчика (отчёт cores 24.10.2026): иконка у скорости сервера замеряет только
    его — сразу, и при занятом канале, без общего замера всех: фоновые замеры по-прежнему
    ждут свободного канала."""
    daemon.traffic = 0
    _first, second = _start(daemon)
    _busy_step(daemon)
    assert daemon.measured == []  # фоновый замер ждёт свободного канала
    spare = daemon.tags("spare")[0]
    spare_fp = next(info.fingerprint for info in daemon.view() if info.tag == spare)
    daemon.request_speed_one(spare_fp)
    assert daemon.speed_one_pending() == [spare_fp]
    _busy_step(daemon)
    assert daemon.measured == [spare]
    assert daemon.speed_one_pending() == []
    assert spare_fp in daemon._speeds()
    # По тегу участника — тоже он один (шаг со сканом запасных замер пропускает).
    daemon.request_speed_one(second)
    for _ in range(3):
        _busy_step(daemon)
        if second in daemon.measured:
            break
    assert daemon.measured == [spare, second]


def _scan_every_step(daemon: Harness, spare: str) -> None:
    """Шаг со сканом — как непрерывные пробы профилей у запасных на шлюзе 25.10.2026."""
    daemon.scan_queue.append(spare.replace("spare-", "probe-"))
    _step(daemon)


def test_the_button_works_while_every_step_scans(daemon):
    """Отчёт 0.1.18, дефект 2: сканы шли на каждом шаге, а замер ждал шага без скана —
    кнопка ↻ «крутилась, но не обновляла». Заказанный замер идёт и в шаге со сканом, один."""
    _start(daemon)
    _settle(daemon)
    first, second = daemon.tags("spare")[:2]
    daemon.measured.clear()
    daemon.request_speed_one(first)
    daemon.request_speed_one(second)
    _scan_every_step(daemon, second)
    assert len(daemon.measured) == 1  # в шаге со сканом — один
    _scan_every_step(daemon, first)
    assert sorted(daemon.measured) == sorted([first, second])
    assert daemon.speed_one_pending() == []


def test_background_waits_for_a_scan_free_step_but_not_for_ever(daemon):
    """Фоновый замер ждёт шага без скана не дольше SPEED_SCAN_WAIT, потом идёт — по одному."""
    from xgw.daemon import SPEED_SCAN_WAIT

    _start(daemon)
    _settle(daemon)
    spare = daemon.tags("spare")[0]
    daemon.speed_queue.append(spare.replace("spare-", "probe-"))  # фоновый замер подошёл
    daemon.measured.clear()
    steps = int(SPEED_SCAN_WAIT // 20)
    for _ in range(steps - 1):
        _scan_every_step(daemon, spare)
    assert daemon.measured == []
    for _ in range(3):
        _scan_every_step(daemon, spare)
    assert daemon.measured == [spare]


def test_the_button_measures_a_server_the_background_would_skip(daemon):
    """Запасной не прошёл последний скан, участник не отвечает ядру — фоновый замер их не
    берёт, а кнопку человек нажал нарочно: замер идёт (и честно записывает неудачу)."""
    first, _second = _start(daemon)
    _settle(daemon)
    measured = len(daemon.measured)
    spare = daemon.tags("spare")[0]
    probe = spare.replace("spare-", "probe-")
    daemon.store.save_scan(probe, "FROZEN", 16384, 5.0, "заморозка", ts=daemon.t)
    daemon.speeds[spare] = None
    daemon.request_speed_one(spare)
    _step(daemon)
    assert daemon.measured[measured:] == [spare]
    record = daemon._speeds()[next(i.fingerprint for i in daemon.view() if i.tag == spare)]
    assert record["mbps"] is None and "тишина" in record["error"]
    daemon.set_alive(**{first.replace("-", "_"): False})
    daemon.request_speed_one(first)
    _step(daemon)
    assert daemon.measured[-1] == first
    # Сервера уже нет в конфиге — запрос снимается, ничего не замеряется.
    daemon.request_speed_one("spare-zz-0000")
    _step(daemon)
    assert daemon.measured[-1] == first and daemon.speed_one_pending() == []
