"""Дневник бесплатного пула (М3): счётчики по дням, время через пул и закрытого, средняя
скорость ведущего, запись раз в минуту, `xgw pool stats` с трафиком пула и подписки."""

import datetime

import pytest

from xgw.freepool import stats
from xgw.paths import Paths
from xgw.store import Store

NOW = datetime.datetime(2026, 10, 31, 12, 0).timestamp()
DAY = stats.day_of(NOW)
YESTERDAY = stats.day_of(NOW - 86400)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    opened = Store(paths.db_file)
    yield opened
    opened.close()


def test_diary_counts_time_speed_and_switches(store):
    """Время через пул — между шагами с трафиком (разрыв длиннее STEP_CAP — сон или остановка, не
    в счёт); закрытое — отдельно; скорость ведущего — средняя по времени; в базу — не чаще раза в
    SAVE_EVERY, при остановке — сразу."""
    clock = [NOW]
    diary = stats.Diary(store, clock=lambda: clock[0])
    diary.tick(closed=False, mbps=None)
    clock[0] += 20
    diary.tick(closed=False, mbps=60.0)
    clock[0] += 20
    diary.tick(closed=False, mbps=20.0)
    diary.count("switch_speed")
    assert stats.load(store)[DAY]["active_s"] == 20.0  # первая запись — сразу, дальше раз в минуту
    clock[0] += 20
    diary.tick(closed=True, mbps=None)
    diary.count("closures")
    clock[0] += stats.STEP_CAP + 1  # демон стоял
    diary.tick(closed=False, mbps=10.0)
    diary.idle()
    clock[0] += 20
    diary.tick(closed=False, mbps=10.0)  # после простоя — новый отрезок
    diary.flush(force=True)
    saved = stats.load(store)[DAY]
    assert saved == {"active_s": 60.0, "closed_s": 20.0, "speed_s": 1600.0, "speed_dt": 40.0,
                     "switch_speed": 1.0, "closures": 1.0}


def test_diary_keeps_a_month(store):
    clock = [NOW - 40 * 86400]
    diary = stats.Diary(store, clock=lambda: clock[0])
    diary.count("measured")
    diary.flush(force=True)
    clock[0] = NOW
    diary.count("measured")
    diary.flush(force=True)
    assert list(stats.load(store)) == [DAY]


def test_stats_text_by_day_with_pool_and_subscription_traffic(store):
    clock = [NOW]
    diary = stats.Diary(store, clock=lambda: clock[0])
    diary.tick(closed=False, mbps=None)
    for _ in range(180):  # час с ведущим 54 Мбит/с
        clock[0] += 20
        diary.tick(closed=False, mbps=54.0)
    for field in ("switch_first", "switch_speed", "switch_dead", "switch_dead", "measured",
                  "measured", "failed", "spared", "closures", "rechecked", "rechecked",
                  "refreshed"):
        diary.count(field)
    diary.count("dropped", 2)
    diary.flush(force=True)
    store.add_usage(DAY, [("pool", "pool", 120_000_000, 3_200_000_000, 3_200_000_000),
                          ("sub", "aaaa1111", 5_000_000, 40_000_000, 40_000_000)])
    store.add_usage(YESTERDAY, [("sub", "aaaa1111", 1_000_000, 900_000_000, 900_000_000)])
    rows = stats.report(store, 2, clock=lambda: clock[0])
    assert [row["day"] for row in rows] == [YESTERDAY, DAY]
    assert stats.text(rows).splitlines() == [
        "Бесплатный пул по дням (трафик через пул — весь дом или устройства):",
        f"{YESTERDAY}: через пул никто не шёл; трафик через пул ↓ 0 КБ ↑ 0 КБ, через подписку "
        "↓ 900 МБ ↑ 1,0 МБ",
        f"{DAY}: через пул 1 ч 0 мин, закрыто 0 с (1 раз)",
        "  смен сервера 4: первый выбор 1, на более быстрый 1, прежний не отвечал 2, прежний вне "
        "состава 0, вручную 0",
        "  средняя скорость ведущего 54 Мбит/с; замеров 2, не удались 1; проба ядра опоздала под "
        "нагрузкой: 1",
        "  восстановление: молчащих перепроверено вне очереди 2, выбыло из состава 2, списки "
        "обновлены при закрытом пуле 1",
        "  трафик через пул ↓ 3,2 ГБ ↑ 120 МБ, через подписку ↓ 40,0 МБ ↑ 5,0 МБ",
    ]
    assert stats.times(3) == "3 раза" and stats.times(12) == "12 раз"
