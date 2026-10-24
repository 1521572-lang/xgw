"""Контроль скорости участников (0.1.18, ТЗ R5–R8; watch/guard.py)."""

import json

import pytest
from test_daemon import Harness
from test_daemon_main import StickyApi, _free_inventory

from xgw import pin as pinning
from xgw.config import Config
from xgw.paths import Paths
from xgw.watch import guard as speedguard
from xgw.watch.guard import Guard

MB = speedguard.MB


# --- модель ---------------------------------------------------------------------------


class Clock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _guard(**speed) -> tuple[Guard, Clock]:
    cfg = Config()
    for key, value in speed.items():
        setattr(cfg.speed, key, value)
    clock = Clock()
    return Guard(cfg, clock), clock


def test_passive_estimate_counts_only_the_clients_traffic():
    """R5: скорость реального трафика по счётчикам ядра — раз в passive_seconds, без
    собственных проверок шлюза; не меньше passive_mbps — сервер исправен."""
    guard, clock = _guard()
    keys = {"proxy-de-1111": "fp-de", "proxy-nl-2222": "fp-nl"}
    assert guard.sample({"proxy-de-1111": 0, "proxy-nl-2222": 0}, {}, keys) == {}
    assert guard.sample({"proxy-de-1111": 10 * MB}, {}, keys) is None  # ещё не время
    clock.now += 90
    # 120 МБ за 90 с через DE, из них 6 МБ — свой замер; через NL — 9 МБ.
    result = guard.sample({"proxy-de-1111": 120 * MB, "proxy-nl-2222": 9 * MB},
                          {"proxy-de-1111": 6 * MB}, keys)
    assert result == {"fp-de": pytest.approx(10.1, abs=0.1), "fp-nl": 0.8}
    assert guard.healthy("fp-de", within=3600) == pytest.approx(10.1, abs=0.1)
    assert guard.healthy("fp-nl", within=3600) is None
    assert guard.recheck_at == {}  # через NL почти не качают — о полосе это не говорит
    clock.now += 90
    # Через NL качают, а идёт медленно (4 Мбит/с) — замерить сразу.
    guard.sample({"proxy-de-1111": 120 * MB, "proxy-nl-2222": 54 * MB}, {}, keys)
    assert guard.recheck_at == {"fp-nl": clock.now}
    clock.now += 90
    # Xray перезапущен — счётчик меньше прежнего: с этой точки, без отрицательных оценок.
    assert "fp-de" not in guard.sample({"proxy-de-1111": 1000}, {}, keys)
    clock.now += 4000
    assert guard.healthy("fp-de", within=3600) is None  # оценка устарела
    assert guard.passive_records()["fp-nl"]["mbps"] == 4.0


def test_three_low_totals_in_ten_minutes_mean_throttled():
    """R6.1: три суммарные оценки подряд ниже low_mbps за low_minutes — придушен; хорошая
    оценка между ними счёт обнуляет; старые низкие не считаются."""
    guard, clock = _guard()
    assert guard.note_total("k", 4.0) is False and guard.recheck_at["k"] == clock.now + 200
    clock.now += 200
    assert guard.note_total("k", 30.0) is False and "k" not in guard.recheck_at
    for _ in range(2):
        guard.note_total("k", 3.0)
        clock.now += 200
    assert guard.note_total("k", 5.0) is True and guard.throttled == {"k": 5.0}
    assert guard.note_total("k", None) is False  # неудавшийся замер — не про полосу
    guard.clear("k")
    guard.note_total("k", 2.0)
    clock.now += 700  # прошлая низкая — за пределами окна
    guard.note_total("k", 2.0)
    clock.now += 100
    assert guard.note_total("k", 2.0) is False


def test_hysteresis_cooldown_and_budget():
    """R7: переход — только на заметно более быстрый и не медленнее min_mbps; ранняя
    остановка — с switch_mbps; пауза после глобальной просадки; суточный бюджет."""
    guard, clock = _guard(guard_daily_mb=20)
    assert not guard.better(9.5, 8.0)  # +19 % — мало
    assert not guard.better(11.0, 4.0)  # быстрее, но медленнее min_mbps (12)
    assert guard.better(13.0, 4.0) and not guard.early(13.0, 4.0)
    assert guard.early(30.0, 4.0) and not guard.early(30.0, 28.0)
    assert not guard.better(None, 4.0)
    assert not guard.cooling()
    until = guard.cool_down()
    assert guard.cooling() and until == clock.now + 40 * 60
    clock.now += 40 * 60 + 1
    assert not guard.cooling()
    assert guard.can_spend(15 * MB)
    guard.spend(15 * MB)
    assert not guard.can_spend(6 * MB) and guard.snapshot()["spent_mb"] == 15.0
    clock.now += 86400  # новые сутки
    assert guard.can_spend(20 * MB)
    guard.load_spent(json.dumps({"day": "2000-01-01", "bytes": 5}))
    assert guard.spent_today() == 0


# --- демон ------------------------------------------------------------------------------


def _config() -> Config:
    cfg = Config()
    cfg.filters.max_members = 2
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []
    return cfg


@pytest.fixture()
def daemon(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    instance = Harness(_config(), paths)
    instance.api = StickyApi()
    instance.source = _free_inventory()
    instance.default_speed = 5.0
    yield instance
    instance.store.close()


def _step(daemon: Harness, seconds: float = 20.0) -> None:
    daemon.t += seconds
    daemon.tick()


def _settle(daemon: Harness) -> None:
    for _ in range(40):
        _step(daemon)
        if not daemon.speed_queue and daemon.guard.episode is None:
            return
    raise AssertionError("замеры не кончились")


def _ready(daemon: Harness) -> tuple[str, str]:
    """Основной — первый участник (60 Мбит/с), второй — 30; всё замерено."""
    daemon.tick()
    daemon.set_alive()
    first, second = daemon.tags("proxy")
    daemon.speeds = {first: 60.0, second: 30.0}
    _settle(daemon)
    assert daemon.main["tag"] == first
    daemon.measured.clear()
    return first, second


def _guard_events(daemon: Harness) -> list[str]:
    return [event for event in daemon.events() if event.startswith(("guard:", "main:", "pin:"))]


def _throttle(daemon: Harness, tag: str) -> None:
    """Сервер «придушен»: его замеры — 4 Мбит/с; первый замер — по кнопке, следующие —
    повторные короткие (каждые low_minutes / low_count)."""
    daemon.speeds[tag] = 4.0
    daemon.request_speed_one(tag)
    for _ in range(80):
        _step(daemon)
        if any("придушен" in event for event in _guard_events(daemon)):
            return
    raise AssertionError("придушенный не замечен")


def test_a_test_is_summed_with_the_clients_traffic_through_the_same_server(daemon):
    """R5.3: замер основного, через который качают, — сумма самого замера и трафика клиентов
    через него за время замера: занятый канал не «убивает» здоровый сервер."""
    first, _second = _ready(daemon)
    daemon.totals[first] = 0
    daemon.during_speed[first] = 10_000_000 + 30_000_000  # замер 10 МБ + 30 МБ клиентов
    daemon.speeds[first] = 8.0
    daemon.request_speed_one(first)
    _step(daemon)
    record = daemon._speeds()[next(i.fingerprint for i in daemon.view() if i.tag == first)]
    assert record["test_mbps"] == 8.0 and record["bg_mbps"] > 0
    assert record["mbps"] == pytest.approx(8.0 + record["bg_mbps"])
    entry = next(m for m in daemon.status()["members"] if m["tag"] == first)
    assert entry["speed_test_mbps"] == 8.0 and entry["speed_bg_mbps"] == record["bg_mbps"]


def test_busy_member_is_healthy_without_a_test(daemon):
    """R5.2: через участника клиенты качают не меньше passive_mbps — активный замер ему не
    нужен (срок замера наступил, а замера нет); оценка видна в статусе «из трафика»."""
    first, _second = _ready(daemon)
    fingerprint = next(i.fingerprint for i in daemon.view() if i.tag == first)
    daemon.guard.next_sample = 0.0
    daemon.traffic = None
    daemon.downlinks = {first: 0}
    _step(daemon)
    daemon.downlinks = {first: 30 * 90 * MB // 8}  # 30 Мбит/с за 90 с
    daemon.t += 70
    _step(daemon)
    assert daemon.guard.healthy(fingerprint, 3600) == pytest.approx(30.0, abs=1.0)
    daemon.t += 6 * 3600  # срок замера (unlimited_hours = 6) прошёл, а клиенты всё качают
    elapsed = daemon.t + 20 - daemon.guard.counters[first][0]
    daemon.downlinks = {first: daemon.downlinks[first] + int(30 * MB / 8 * elapsed)}
    daemon.guard.next_sample = 0.0
    _step(daemon)
    measured = list(daemon.measured)
    _settle(daemon)
    assert first not in measured and first not in daemon.measured
    entry = next(m for m in daemon.status()["members"] if m["tag"] == first)
    assert entry["speed_passive_mbps"] is not None


def test_throttled_main_moves_to_the_first_fast_candidate(daemon):
    """R6–R8: основной придушен — кандидаты замеряются по одному, первый не медленнее
    switch_mbps (25) и быстрее на gain_pct — сразу основной; поиск коротких замеров."""
    first, second = _ready(daemon)
    daemon.speeds[second] = 40.0
    _throttle(daemon, first)
    _settle(daemon)
    assert daemon.main["tag"] == second
    events = _guard_events(daemon)
    assert any("придушен: 3 оценки подряд ниже 10 Мбит/с" in event for event in events)
    assert any("основной теперь" in event and "40 Мбит/с" in event for event in events)
    assert daemon.guard.episode is None and True in daemon.small


def test_nothing_better_is_a_global_drop_with_a_pause(daemon):
    """R7.2: ни один кандидат не лучше — это канал, а не сервер: остаёмся, событие о
    глобальной просадке, новых поисков cooldown_minutes."""
    first, second = _ready(daemon)
    daemon.speeds[second] = 4.5
    daemon.default_speed = 4.0
    _throttle(daemon, first)
    _settle(daemon)
    assert daemon.main["tag"] == first
    assert any("глобальная просадка канала" in event for event in _guard_events(daemon))
    assert daemon.guard.cooling()
    # Пока пауза — придушенность не ведёт к новому поиску.
    daemon.guard.throttled[next(i.fingerprint for i in daemon.view() if i.tag == first)] = 3.0
    _step(daemon)
    assert daemon.guard.episode is None and daemon.guard.throttled == {}


def test_a_throttled_manual_choice_becomes_the_best_pin(daemon):
    """R8: выбранный вручную придушен — выбор переходит на лучшего кандидата с пометкой,
    что он автоматический («лучший пин»), с уведомлением."""
    first, second = _ready(daemon)
    daemon.store.set_meta(pinning.META, pinning.dumps(
        {"tag": first, "name": "Первый", "until": None, "since": daemon.t}))
    _step(daemon)
    daemon.speeds[second] = 40.0
    _throttle(daemon, first)
    _settle(daemon)
    pin = pinning.parse(daemon.store.get_meta(pinning.META))
    assert pin["tag"] == second and pin["auto"] is True and pin["was"]
    assert daemon.api.state.override == second
    assert any("«лучший пин»" in event for event in _guard_events(daemon))


def test_the_daily_budget_stops_the_search(daemon):
    daemon.cfg.speed.guard_daily_mb = 1  # меньше одного короткого замера
    first, _second = _ready(daemon)
    daemon.speeds[first] = 4.0
    fingerprint = next(i.fingerprint for i in daemon.view() if i.tag == first)
    daemon.guard.throttled[fingerprint] = 4.0
    _step(daemon)
    assert daemon.guard.episode is None
    assert any("суточный лимит трафика на поиск замены" in event
               for event in _guard_events(daemon))


def test_guard_off_changes_nothing(daemon):
    daemon.cfg.speed.guard = False
    first, _second = _ready(daemon)
    fingerprint = next(i.fingerprint for i in daemon.view() if i.tag == first)
    daemon.guard.throttled[fingerprint] = 3.0
    _step(daemon)
    assert daemon.guard.episode is None and daemon.main["tag"] == first
