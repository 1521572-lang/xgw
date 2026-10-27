"""Рейтинг сервера (0.2.0, issue #2, раздел 3 рекомендаций к аудиту 0.1.18).

До 0.2.0 серверы делились на жёсткие классы «приоритет × стоимость», и в балансировщике
работал один класс: мёртвого участника меняли только запасным того же класса, и при четырёх
«высоких × x10» в работе DEGRADED висел часами при 74 живых «средних» (разбор Р1, 24.10.2026).
Теперь приоритет и стоимость — веса в одном числе, и участники — лучшие по нему из всех
подписок:

    score = V · L · H · C · P

V — скорость: (min(Мбит/с, 100) / 100) ** 0.6; у живого сервера без свежего замера —
    априорные 35 Мбит/с (иначе 69 незамеренных запасных получили бы ноль и не выбирались бы
    никогда). Степень 0.6, а не логарифм: 80 Мбит/с против 25 — в 2 раза, а не на 35 %.
L — задержка: 200 / (200 + max(0, RTT − 50)); до 50 мс разницы нет. RTT — сетевой, по
    короткому запросу в открытом соединении (checks.DownloadResult.rtt_ms); без замера —
    150 мс.
H — стабильность: max(0.1, 1 − 0.6 · доля сбоев за 24 ч − 0.25 · штраф ТСПУ), штраф 1 —
    «нестабилен по ТСПУ», 0.5 — отвечает только на профиле обхода (дробление, sing-box).
C — стоимость: безлимит 1.00, x1 0.95, x10 0.75 (между ними — по логарифму множителя),
    x100 и дороже, а также подписка с исчерпанной квотой (меньше QUOTA_LOW остатка) — 0:
    такой сервер в работу не ставится.
P — приоритет владельца: высокий 1.45, средний 1.00, низкий 0.65.

Баланс весов: «высокий × x10» (1.45 · 0.75 = 1.09) опережает «средний × безлимит» (1.00),
«средний» обгоняет «высокого» той же стоимости, только если быстрее в 1.45 ** (1 / 0.6) ≈ 1.86
раза, а сервер x10 уступает безлимитному того же уровня, пока не быстрее в 0.75 ** (−1 / 0.6)
≈ 1.6 раза — квоту зря не тратит. Живость в число не входит: участник, которого ядро считает
мёртвым, и запасной, не прошедший скан, кандидатами не бывают вовсе (daemon).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import priority

PRIORITY_WEIGHT = {"high": 1.45, "medium": 1.00, "low": 0.65}
PRIOR_MBPS = 35.0  # живой сервер без свежего замера
SPEED_CAP = 100.0
SPEED_POWER = 0.6
RTT_FREE = 50.0  # мс: задержка до этого не штрафуется
RTT_SCALE = 200.0
PRIOR_RTT = 150.0  # мс: задержка не замерялась
FAIL_WEIGHT = 0.6
TSPU_WEIGHT = 0.25
HEALTH_FLOOR = 0.1
COST_FREE = 1.00
COST_X1 = 0.95
COST_X10 = 0.75
COST_SKIP = 100.0  # x100 и дороже — только для LTE: в работу не ставятся
QUOTA_LOW = 0.05  # остаток квоты подписки меньше этой доли — её серверы в работу не ставятся


@dataclass(frozen=True)
class Facts:
    """Что известно о сервере для рейтинга."""

    level: str = priority.DEFAULT  # приоритет: high | medium | low
    price: float = 0.0  # стоимость (cost.py): 0 — безлимит, иначе множитель
    mbps: float | None = None  # свежий замер скорости; None — нет
    rtt_ms: float | None = None  # сетевая задержка; None — не замерялась
    fail_rate: float = 0.0  # доля неудачных проверок за 24 ч
    tspu: float = 0.0  # штраф ТСПУ: 1 — нестабилен, 0.5 — только с обходом
    quota_low: bool = False  # квота подписки на исходе


def speed_factor(mbps: float | None) -> float:
    value = PRIOR_MBPS if mbps is None else max(0.0, float(mbps))
    return (min(value, SPEED_CAP) / SPEED_CAP) ** SPEED_POWER


def latency_factor(rtt_ms: float | None) -> float:
    value = PRIOR_RTT if rtt_ms is None else max(0.0, float(rtt_ms))
    return RTT_SCALE / (RTT_SCALE + max(0.0, value - RTT_FREE))


def health_factor(fail_rate: float, tspu: float) -> float:
    return max(HEALTH_FLOOR, 1.0 - FAIL_WEIGHT * fail_rate - TSPU_WEIGHT * tspu)


def cost_factor(price: float, quota_low: bool = False) -> float:
    """Вес стоимости: безлимит 1, x1 0.95, x10 0.75, x100 — 0 (между — по log10)."""
    if quota_low and price > 0:
        return 0.0
    if price <= 0:
        return COST_FREE
    if price >= COST_SKIP:
        return 0.0
    if price <= 1:
        return COST_X1
    if price <= 10:
        return COST_X1 - (COST_X1 - COST_X10) * math.log10(price)
    return max(0.0, COST_X10 * (1.0 - math.log10(price / 10.0)))


def priority_factor(level: str) -> float:
    return PRIORITY_WEIGHT.get(level, PRIORITY_WEIGHT[priority.DEFAULT])


def score(facts: Facts) -> float:
    """Рейтинг сервера; 0 — в работу не ставится (x100, квота на исходе)."""
    value = (
        speed_factor(facts.mbps) * latency_factor(facts.rtt_ms)
        * health_factor(facts.fail_rate, facts.tspu)
        * cost_factor(facts.price, facts.quota_low) * priority_factor(facts.level)
    )
    return round(value, 4)


def static(level: str, price: float, quota_low: bool = False) -> float:
    """Рейтинг без сведений о сервере (первая сборка, `xgw generate`): только приоритет и
    стоимость, скорость и задержка — априорные."""
    return score(Facts(level=level, price=price, quota_low=quota_low))


def quota_low(quota: object) -> bool:
    """Квота подписки на исходе: остаток меньше QUOTA_LOW от полной (subscription-userinfo)."""
    if not isinstance(quota, dict):
        return False
    total = quota.get("total", 0)
    if not isinstance(total, (int, float)) or total <= 0:
        return False
    used = float(quota.get("upload", 0) or 0) + float(quota.get("download", 0) or 0)
    return total - used < total * QUOTA_LOW
