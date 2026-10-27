"""Стоимость серверов: безлимитные и лимитированные подписки, множители расхода.

Лимит подписки — поле total заголовка subscription-userinfo (engine.Inventory.quotas):
total больше нуля — подписка с лимитом трафика; заголовка нет или total = 0 —
безлимитная. Ручные ссылки — тоже безлимитные: о них ничего не известно.

Множитель расхода есть только в имени сервера: «x10 🛜 Германия», «🇳🇱 x10📶 Нидерланды».
Шаблон — filters.multiplier_regex (первая группа — число); без отметки — x1. У сервера
безлимитной подписки стоимость 0 при любом множителе: квоту он не тратит. У сервера
подписки с лимитом стоимость — его множитель: столько байт квоты уходит на байт трафика.

С 0.2.0 стоимость — вес в рейтинге сервера (rating.py: безлимит 1, x1 0,95, x10 0,75, x100 —
не в работу), а не класс-фильтр (issue #2). Класс (ранг приоритета, стоимость) остался для
текстов статуса (status.class_warning). Запасной выход балансировщика (fallbackTag) —
лимитированный сервер дороже самого дешёвого участника: через него трафик идёт, только когда
все участники мертвы, и observatory его не пробует (builder.select_nodes,
daemon.Daemon._reserve_step).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import NamedTuple

from . import priority

# Латинская x, кириллическая х или знак × перед числом (допустимы дроби: x0.5, x1,5);
# слева и справа от отметки — не буква и не цифра, чтобы не ловить «box1» или «x2ray».
DEFAULT_MULTIPLIER_REGEX = r"(?i)(?<![0-9a-zа-яё])[xх×]\s?(\d+(?:[.,]\d+)?)(?![0-9a-zа-яё])"
MANUAL = "manual"  # источник ручных ссылок (engine.collect)


class Klass(NamedTuple):
    """Класс сервера: меньше — лучше."""

    rank: int  # ранг приоритета: 0 — высокий, 1 — средний, 2 — низкий
    cost: float  # 0 — квоту не тратит; иначе множитель расхода


def multiplier(name: str, pattern: str | re.Pattern | None) -> float:
    """Множитель расхода из имени сервера; без отметки (или без шаблона) — 1."""
    if not pattern:
        return 1.0
    compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
    match = compiled.search(name or "")
    if not match:
        return 1.0
    text = match.group(1) if match.groups() else match.group(0)
    try:
        value = float(str(text).replace(",", "."))
    except ValueError:
        return 1.0
    return value if value >= 0 else 1.0


def limited_sources(quotas: Mapping[str, object]) -> set[str]:
    """Подписки с лимитом трафика: total в subscription-userinfo больше нуля."""
    result: set[str] = set()
    for name, quota in quotas.items():
        total = quota.get("total", 0) if isinstance(quota, Mapping) else 0
        if isinstance(total, int | float) and total > 0:
            result.add(name)
    return result


def cost_of(name: str, source: str, limited: Iterable[str], pattern) -> float:
    """Стоимость сервера: 0 — безлимитный, иначе его множитель."""
    if source not in set(limited):
        return 0.0
    return multiplier(name, pattern)


def costs(nodes: Iterable, quotas: Mapping[str, object], pattern) -> dict[str, float]:
    """Отпечаток → стоимость для серверов (ServerNode: fingerprint, name, source)."""
    limited = limited_sources(quotas)
    compiled = re.compile(pattern) if isinstance(pattern, str) and pattern else pattern
    result: dict[str, float] = {}
    for node in nodes:
        if getattr(node, "keep_tag", None):
            continue  # звенья цепочек — не самостоятельные серверы
        value = multiplier(node.name, compiled) if node.source in limited else 0.0
        # Дубль из другой подписки: берётся дешёвый — тот же сервер, а квоту тратить незачем.
        result[node.fingerprint] = min(value, result.get(node.fingerprint, value))
    return result


def klass(levels: Mapping[str, str], prices: Mapping[str, float], fingerprint: str) -> Klass:
    """Класс сервера. Сервер, стоимость которого не известна, считается x1."""
    return Klass(priority.rank(levels, fingerprint), prices.get(fingerprint, 1.0))


def best(
    levels: Mapping[str, str], prices: Mapping[str, float], fingerprints: Iterable[str]
) -> Klass | None:
    """Лучший класс среди серверов; None — серверов нет."""
    found = [klass(levels, prices, fingerprint) for fingerprint in fingerprints]
    return min(found) if found else None


def label(value: float) -> str:
    """«x1», «x10», «x0.5»."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"x{text}"


def describe(value: float) -> str:
    """Как назвать стоимость сервера человеку: «безлимит» или множитель."""
    return "безлимит" if value == 0 else label(value)


def class_name(value: Klass, ranked: bool) -> str:
    """Название класса для событий: «безлимитные серверы», «лимитированные серверы x10»;
    ranked — у классов разный приоритет, и уровень тоже назван."""
    text = "безлимитные серверы" if value.cost == 0 else (
        f"лимитированные серверы {label(value.cost)}"
    )
    if ranked:
        text += f" уровня «{priority.level_name(value.rank)}»"
    return text
