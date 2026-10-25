"""Контроль скорости участников (0.1.18, ТЗ R5–R8).

ТСПУ всё чаще не рвёт соединение с сервером VPN, а «придушивает» его: полоса режется до
1–5 Мбит/с. Сервер при этом жив — пробы ядра проходят, замены не будет, а интернет еле
идёт. Здесь — правила, по которым демон это замечает и уходит с такого сервера
(daemon.Daemon._guard_step).

R5. Пассивная оценка. Раз в speed.passive_seconds демон берёт счётчики байт outbound'ов из
ответа ядра (/debug/vars, те же, что у `xray api statsquery`) и считает скорость реального
трафика каждого участника — без единого лишнего байта. Не меньше speed.passive_mbps —
участник исправен, активный замер ему не нужен. Активный замер (несколько МБ) идёт только
при малом фоне, а его итог — сумма: скорость самого замера и скорость трафика клиентов через
тот же сервер за время замера. Иначе машина, которая качает игру через основной сервер,
«убила» бы здоровый сервер: замер получил бы лишь остаток полосы.

R6. «Придушен» — speed.low_count суммарных оценок подряд ниже speed.low_mbps за
speed.low_minutes. Первую низкую оценку даёт плановый замер либо пассивная оценка, когда
трафик через сервер идёт, но медленно (замер тогда — сразу), следующие — повторные короткие
замеры. Придушенному ищется замена: до speed.candidates кандидатов (живые, со свежей
проверкой, не x100, не из подписки с исчерпанной квотой, не «нестабильные по ТСПУ»),
замер строго по одному; первый не медленнее speed.switch_mbps — сразу.

R7. Гистерезис: переход только на того, кто быстрее нынешнего на speed.gain_pct и не
медленнее speed.min_mbps (с 8 на 9,5 Мбит/с — не прыгаем). Не лучше ни один — это не
сервер, а канал («глобальная просадка»: вечер, провайдер): остаёмся, событие, новых поисков
speed.cooldown_minutes. На один поиск — не больше speed.episode_mb, на все за сутки — не
больше speed.guard_daily_mb.

R8. Основной сервер переходит на кандидата (запасной сначала встаёт в работу); другой
участник выводится из работы тихо, с подстановкой кандидата; выбранный вручную — «лучший
пин»: выбор переходит на кандидата с пометкой, что он автоматический.
"""

from __future__ import annotations

import datetime
import json
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from ..config import Config

MB = 1_000_000
META_PASSIVE = "speed_passive"  # пассивные оценки участников для панели (ключ → {mbps, ts})
META_SPENT = "guard_spent"  # трафик поисков за сутки: {"day": "YYYY-MM-DD", "bytes": N}
PASSIVE_KEEP = 10  # сколько пассивных оценок помнить на сервер
# Трафик клиентов через сервер ниже этого — оценка ничего не говорит о полосе (через сервер
# просто мало качают); выше, но меньше speed.low_mbps — повод замерить сервер сразу.
ACTIVE_FLOOR_MBPS = 1.0


@dataclass(frozen=True)
class Passive:
    mbps: float
    ts: float


@dataclass
class Guard:
    cfg: Config
    wall: Callable[[], float]
    # tag → (time.time(), байт uplink + downlink с запуска Xray) на прошлой пассивной оценке
    counters: dict[str, tuple[float, int]] = field(default_factory=dict)
    next_sample: float = 0.0
    passive: dict[str, deque] = field(default_factory=dict)  # ключ сервера → оценки
    lows: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    recheck_at: dict[str, float] = field(default_factory=dict)  # ключ → когда замерить снова
    throttled: dict[str, float] = field(default_factory=dict)  # ключ → последняя оценка
    episode: dict | None = None  # идущий поиск замены (daemon._guard_step)
    cooldown_until: float = 0.0
    spent: dict = field(default_factory=dict)  # {"day", "bytes"}

    # --- R5: пассивная оценка ------------------------------------------------------

    def sample(
        self, counters: dict[str, int], own: dict[str, int], keys: dict[str, str],
    ) -> dict[str, float] | None:
        """Скорость реального трафика участников. counters — тег → байт (uplink + downlink)
        сейчас; own — тег → байт собственных проверок шлюза через этот сервер с прошлой
        оценки (замеры, пробы): их не считать трафиком клиентов; keys — тег → ключ сервера.
        None — ещё не время (оценка раз в speed.passive_seconds); иначе ключ → Мбит/с."""
        now = self.wall()
        if now < self.next_sample:
            return None
        self.next_sample = now + self.cfg.speed.passive_seconds
        result: dict[str, float] = {}
        for tag, total in counters.items():
            previous = self.counters.get(tag)
            self.counters[tag] = (now, total)
            key = keys.get(tag)
            # Счётчик меньше прежнего — Xray перезапущен: оценка с этой точки.
            if key is None or previous is None or now <= previous[0] or total < previous[1]:
                continue
            delta = max(0, total - previous[1] - own.get(tag, 0))
            mbps = round(delta * 8 / (now - previous[0]) / MB, 1)
            self.passive.setdefault(key, deque(maxlen=PASSIVE_KEEP)).append(Passive(mbps, now))
            result[key] = mbps
            if mbps >= self.cfg.speed.passive_mbps:
                self.clear(key)  # исправен: трафик клиентов сам показывает полосу
            elif ACTIVE_FLOOR_MBPS <= mbps < self.cfg.speed.low_mbps and key not in self.throttled:
                # Через сервер качают, а идёт медленно — замерить сразу, не ждать срока.
                self.recheck_at.setdefault(key, now)
        for tag in set(self.counters) - set(counters):
            del self.counters[tag]
        return result

    def latest(self, key: str) -> Passive | None:
        samples = self.passive.get(key)
        return samples[-1] if samples else None

    def healthy(self, key: str, within: float) -> float | None:
        """Мбит/с последней пассивной оценки, если она не меньше speed.passive_mbps и не
        старше within секунд: участник исправен, активный замер не нужен (R5.2)."""
        last = self.latest(key)
        if last is None or last.mbps < self.cfg.speed.passive_mbps:
            return None
        return last.mbps if self.wall() - last.ts <= within else None

    # --- R6: придушен ли сервер --------------------------------------------------------

    def note_total(self, key: str, mbps: float | None) -> bool:
        """Итог активного замера участника (замер + трафик клиентов через него). True — он
        только что признан придушенным. Неудавшийся замер (None) — не про полосу: мёртвых
        меняет замена участников."""
        if mbps is None:
            return False
        now = self.wall()
        if mbps >= self.cfg.speed.low_mbps:
            self.clear(key)
            return False
        window = self.cfg.speed.low_minutes * 60.0
        lows = [(ts, value) for ts, value in self.lows.get(key, []) if now - ts < window]
        lows.append((now, mbps))
        if len(lows) >= self.cfg.speed.low_count:
            self.lows.pop(key, None)
            self.recheck_at.pop(key, None)
            self.throttled[key] = mbps
            return True
        self.lows[key] = lows
        self.recheck_at[key] = now + window / self.cfg.speed.low_count
        return False

    def clear(self, key: str) -> None:
        self.lows.pop(key, None)
        self.recheck_at.pop(key, None)
        self.throttled.pop(key, None)

    def due(self) -> list[str]:
        """Ключи серверов, которые пора замерить снова (подозрение на придушенность)."""
        now = self.wall()
        return sorted(key for key, when in self.recheck_at.items() if when <= now)

    # --- R7: гистерезис, пауза, бюджет ----------------------------------------------

    def better(self, mbps: float | None, current: float) -> bool:
        """Кандидат стоит перехода: быстрее нынешнего на speed.gain_pct и не медленнее
        speed.min_mbps."""
        if mbps is None:
            return False
        gain = 1.0 + self.cfg.speed.gain_pct / 100.0
        return mbps >= self.cfg.speed.min_mbps and mbps >= current * gain and mbps > current

    def early(self, mbps: float | None, current: float) -> bool:
        """Ранняя остановка: кандидат не медленнее speed.switch_mbps (и стоит перехода)."""
        return mbps is not None and mbps >= self.cfg.speed.switch_mbps and self.better(
            mbps, current)

    def cooling(self) -> bool:
        return self.wall() < self.cooldown_until

    def cool_down(self) -> float:
        """«Глобальная просадка»: новых поисков speed.cooldown_minutes. Возвращает, до какого
        момента (time.time())."""
        self.cooldown_until = self.wall() + self.cfg.speed.cooldown_minutes * 60.0
        return self.cooldown_until

    def _today(self) -> str:
        return datetime.date.fromtimestamp(self.wall()).isoformat()

    def spent_today(self) -> int:
        return int(self.spent.get("bytes") or 0) if self.spent.get("day") == self._today() else 0

    def can_spend(self, nbytes: int) -> bool:
        return self.spent_today() + nbytes <= self.cfg.speed.guard_daily_mb * MB

    def spend(self, nbytes: int) -> None:
        self.spent = {"day": self._today(), "bytes": self.spent_today() + max(0, nbytes)}

    def load_spent(self, text: str | None) -> None:
        try:
            saved = json.loads(text) if text else {}
        except ValueError:
            return
        if isinstance(saved, dict) and isinstance(saved.get("bytes"), int):
            self.spent = {"day": str(saved.get("day") or ""), "bytes": saved["bytes"]}

    # --- для панели и статуса -----------------------------------------------------

    def passive_records(self) -> dict[str, dict]:
        """Последние пассивные оценки: ключ → {"mbps", "ts"} (META_PASSIVE)."""
        return {
            key: {"mbps": samples[-1].mbps, "ts": samples[-1].ts}
            for key, samples in self.passive.items() if samples
        }

    def snapshot(self) -> dict:
        episode = self.episode or {}
        return {
            "on": self.cfg.speed.guard,
            "throttled": sorted(self.throttled),
            "suspects": sorted(self.recheck_at),
            "episode": {
                key: episode.get(key) for key in ("name", "role", "mbps", "tried", "total")
            } if episode else None,
            "cooldown_until": self.cooldown_until if self.cooling() else None,
            "spent_mb": round(self.spent_today() / MB, 1),
            "daily_mb": self.cfg.speed.guard_daily_mb,
        }
