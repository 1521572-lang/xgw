"""Дневник бесплатного пула (веха М3, сутки наблюдения): сколько времени трафик шёл через пул и
сколько было закрыто, сколько раз и почему сменился ведущий сервер, средняя скорость ведущего,
замеры и пробы ядра, опоздавшие под нагрузкой, — по дням. По нему решается, нужны ли формула
рейтинга R32 и правила смены по качеству R35 (FREEPOOL-PLAN, «Что остаётся на М3»: «если
испытания покажут нужду»).

С восстановлением пула (М3) — и сколько молчащих серверов «pool» перепроверено вне очереди
(rechecked), сколько выбыло из состава (dropped) и сколько раз списки обновлялись вне расписания
из-за закрытого пула (refreshed). С проверкой YouTube (М3, watch/youtube.py) — сколько раз YouTube
проверялся через серверы «pool» (youtube_checked), сколько раз сервер его не пропускал
(youtube_blocked), тормозил (youtube_slow) или не дал замерить скорость — файлы Google через него
не скачались (youtube_unknown) — и сколько смен было из-за этого (switch_youtube).

Счётчики копит демон (Daemon._pool_step, _pool_spared, _pool_speed_step, _pool_silence,
_pool_due, _youtube_step) и пишет в meta
STATS_META не чаще раза в SAVE_EVERY; `xgw pool stats` печатает их вместе с трафиком пула и
подписки за те же дни (usage.py). Имён серверов здесь нет — только числа."""

from __future__ import annotations

import datetime
import json
import sqlite3
import time
from collections.abc import Callable

from ..usage import size
from ..watch.speed import mbps_text

STATS_META = "pool_stats"
KEEP_DAYS = 30
SAVE_EVERY = 60.0
# Шаг демона — раз в watchdog.interval_s (20 с) плюс работа шага; промежуток длиннее — сон
# машины или остановка демона, а не время работы пула.
STEP_CAP = 120.0
# Почему сменился ведущий: первый выбор (или после «закрыто»), на более быстрый по замеру,
# прежний не отвечал, прежнего нет в составе «pool», выбран вручную, через прежний плох YouTube.
REASONS = ("first", "speed", "dead", "left", "manual", "youtube")


def day_of(ts: float) -> str:
    return datetime.date.fromtimestamp(ts).isoformat()


def load(store) -> dict[str, dict[str, float]]:
    try:
        loaded = json.loads(store.get_meta(STATS_META) or "{}")
    except ValueError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {
        str(day): {str(key): float(value) for key, value in values.items()
                   if isinstance(value, (int, float)) and not isinstance(value, bool)}
        for day, values in loaded.items() if isinstance(values, dict)
    }


class Diary:
    """Счётчики пула за день; store — база демона (get_meta, set_meta)."""

    def __init__(self, store, *, clock: Callable[[], float] = time.time) -> None:
        self.store = store
        self.clock = clock
        self._days: dict[str, dict[str, float]] | None = None
        self._last: float | None = None
        self._saved_at = 0.0
        self._dirty = False

    def days(self) -> dict[str, dict[str, float]]:
        if self._days is None:
            self._days = load(self.store)
        return self._days

    def _add(self, field: str, amount: float) -> None:
        day = self.days().setdefault(day_of(self.clock()), {})
        day[field] = day.get(field, 0.0) + amount
        self._dirty = True

    def count(self, field: str, amount: float = 1.0) -> None:
        self._add(field, amount)
        self.flush()

    def tick(self, *, closed: bool, mbps: float | None) -> None:
        """Шаг пула с трафиком через него: время с прошлого шага — в «через пул», при закрытом —
        и в «закрыто», скорость ведущего (если замерен) — во взвешенную по времени среднюю."""
        now = self.clock()
        last, self._last = self._last, now
        if last is None or not 0 < now - last <= STEP_CAP:
            return
        spent = now - last
        self._add("active_s", spent)
        if closed:
            self._add("closed_s", spent)
        elif mbps is not None:
            self._add("speed_s", mbps * spent)
            self._add("speed_dt", spent)
        self.flush()

    def idle(self) -> None:
        """Через пул никто не идёт: следующий шаг с трафиком начнёт новый отрезок."""
        self._last = None

    def flush(self, *, force: bool = False) -> None:
        now = self.clock()
        if not self._dirty or (not force and now - self._saved_at < SAVE_EVERY):
            return
        oldest = day_of(now - KEEP_DAYS * 86400.0)
        self._days = {day: values for day, values in self.days().items() if day >= oldest}
        data = {day: {key: round(value, 1) for key, value in values.items()}
                for day, values in self._days.items()}
        try:
            self.store.set_meta(STATS_META, json.dumps(data, sort_keys=True))
        except sqlite3.Error:
            return  # запишется следующим разом
        self._saved_at, self._dirty = now, False


def report(store, days: int, *, clock: Callable[[], float] = time.time) -> list[dict]:
    """По строке на день за последние days дней, включая сегодня: счётчики дневника и трафик
    через пул и через подписку (usage.py)."""
    today = datetime.date.fromtimestamp(clock())
    wanted = [(today - datetime.timedelta(days=offset)).isoformat()
              for offset in range(max(1, days) - 1, -1, -1)]
    found = load(store)
    usage = store.usage_by_day(wanted[0])
    result = []
    for day in wanted:
        row: dict = {"day": day, **found.get(day, {})}
        for kind in ("pool", "sub"):
            rows = [item for item in usage if item["day"] == day and item["kind"] == kind]
            row[f"{kind}_down"] = sum(int(item["down"] or 0) for item in rows)
            row[f"{kind}_up"] = sum(int(item["up"] or 0) for item in rows)
        result.append(row)
    return result


def duration(seconds: float) -> str:
    """3 мин; 5 ч 12 мин; меньше минуты — в секундах."""
    if seconds < 60:
        return f"{int(seconds)} с"
    hours, minutes = divmod(round(seconds / 60), 60)
    return f"{hours} ч {minutes} мин" if hours else f"{minutes} мин"


def times(count: int) -> str:
    """1 раз, 2 раза, 5 раз."""
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} раза"
    return f"{count} раз"


def text(rows: list[dict]) -> str:
    lines = ["Бесплатный пул по дням (трафик через пул — весь дом или устройства):"]
    for row in rows:
        active = row.get("active_s", 0.0)
        traffic = (f"трафик через пул ↓ {size(row['pool_down'])} ↑ {size(row['pool_up'])}, через "
                   f"подписку ↓ {size(row['sub_down'])} ↑ {size(row['sub_up'])}")
        if not active:
            lines.append(f"{row['day']}: через пул никто не шёл; {traffic}")
            continue
        switches = {reason: int(row.get(f"switch_{reason}", 0)) for reason in REASONS}
        closures = int(row.get("closures", 0))
        speed = row["speed_s"] / row["speed_dt"] if row.get("speed_dt") else None
        lines.append(f"{row['day']}: через пул {duration(active)}, закрыто "
                     f"{duration(row.get('closed_s', 0.0))}"
                     + (f" ({times(closures)})" if closures else ""))
        lines.append(f"  смен сервера {sum(switches.values())}: первый выбор {switches['first']}, "
                     f"на более быстрый {switches['speed']}, прежний не отвечал "
                     f"{switches['dead']}, прежний вне состава {switches['left']}, вручную "
                     f"{switches['manual']}, через прежний плох YouTube {switches['youtube']}")
        lines.append(f"  средняя скорость ведущего "
                     f"{mbps_text(speed) if speed is not None else '— (не замерялся)'}; замеров "
                     f"{int(row.get('measured', 0))}, не удались {int(row.get('failed', 0))}; "
                     f"проба ядра опоздала под нагрузкой: {int(row.get('spared', 0))}")
        lines.append(f"  восстановление: молчащих перепроверено вне очереди "
                     f"{int(row.get('rechecked', 0))}, выбыло из состава "
                     f"{int(row.get('dropped', 0))}, списки обновлены при закрытом пуле "
                     f"{int(row.get('refreshed', 0))}")
        lines.append(f"  YouTube: проверок {int(row.get('youtube_checked', 0))}, не пропускал "
                     f"{int(row.get('youtube_blocked', 0))}, тормозил "
                     f"{int(row.get('youtube_slow', 0))}, скорость не узнать "
                     f"{int(row.get('youtube_unknown', 0))}")
        lines.append(f"  {traffic}")
    return "\n".join(lines)
