"""Приоритет серверов: высокий, средний (по умолчанию) и низкий.

Ставит его человек — в панели или командой `xgw priority`; хранится он в panel.json по
отпечатку сервера, как и отключение, и переживает обновление подписки.

С 0.2.0 (issue #2) уровень — вес в рейтинге сервера (rating.py: высокий ×1,45, средний ×1,
низкий ×0,65), а не фильтр: участники — лучшие по рейтингу из всех подписок, и сервер уровня
ниже встаёт в работу, если он заметно быстрее или если лучших не хватает. Без приоритетов
все серверы — средние.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

LEVELS = ("high", "medium", "low")  # от высокого к низкому; номер в кортеже — ранг
DEFAULT = "medium"
NAMES = {"high": "высокий", "medium": "средний", "low": "низкий"}


def level_of(levels: Mapping[str, str], fingerprint: str) -> str:
    level = levels.get(fingerprint, DEFAULT)
    return level if level in LEVELS else DEFAULT


def rank(levels: Mapping[str, str], fingerprint: str) -> int:
    """0 — высокий, 1 — средний, 2 — низкий."""
    return LEVELS.index(level_of(levels, fingerprint))


def level_name(rank_value: int) -> str:
    """Название уровня по рангу — для событий и статуса."""
    return NAMES[LEVELS[rank_value]]


def best(levels: Mapping[str, str], fingerprints: Iterable[str]) -> int | None:
    """Наивысший уровень (наименьший ранг) среди серверов; None — серверов нет."""
    ranks = [rank(levels, fingerprint) for fingerprint in fingerprints]
    return min(ranks) if ranks else None
