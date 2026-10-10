"""Маршрутизация по меткам: пакеты с меткой mark_proxy доставляются локально,
чтобы их принял TPROXY-inbound Xray (официальная инструкция TPROXY):

    ip rule add fwmark <mark_proxy> lookup <route_table> pref 100
    ip route add local 0.0.0.0/0 dev lo table <route_table>

Повторное применение дубликатов не создаёт.
"""

from __future__ import annotations

import json

from .cmd import CommandError, Runner

PREF = 100


def _rules(mark: int, table: int, runner: Runner) -> list[dict]:
    """Правила `fwmark <mark> lookup <table>`, которые уже есть в системе."""
    try:
        listing = json.loads(runner(["ip", "-j", "rule", "show"]) or "[]")
    except json.JSONDecodeError as exc:
        raise CommandError(f"ip -j rule show: непонятный ответ ({exc})") from exc
    found = []
    for rule in listing:
        try:
            same_mark = int(str(rule.get("fwmark", "")), 16) == mark
        except ValueError:
            same_mark = False
        if same_mark and str(rule.get("table")) == str(table):
            found.append(rule)
    return found


def _has_route(table: int, runner: Runner) -> bool:
    try:
        routes = json.loads(runner(["ip", "-j", "route", "show", "table", str(table)]) or "[]")
    except (CommandError, json.JSONDecodeError):
        return False  # таблицы маршрутизации ещё нет
    return any(
        route.get("type") == "local" and route.get("dst") == "default" and route.get("dev") == "lo"
        for route in routes
    )


def present(mark: int, table: int, runner: Runner) -> bool:
    return bool(_rules(mark, table, runner)) and _has_route(table, runner)


def ensure(mark: int, table: int, runner: Runner) -> None:
    """Правило и маршрут есть ровно в одном экземпляре."""
    existing = _rules(mark, table, runner)
    for _extra in existing[1:]:
        runner(["ip", "rule", "del", "fwmark", str(mark), "lookup", str(table)])
    if not existing:
        runner(
            ["ip", "rule", "add", "fwmark", str(mark), "lookup", str(table), "pref", str(PREF)]
        )
    runner(["ip", "route", "replace", "local", "0.0.0.0/0", "dev", "lo", "table", str(table)])


def remove(mark: int, table: int, runner: Runner) -> None:
    """Убирает правило (все экземпляры) и маршрут; отсутствующее — не ошибка."""
    for _rule in _rules(mark, table, runner):
        runner(["ip", "rule", "del", "fwmark", str(mark), "lookup", str(table)])
    if _has_route(table, runner):
        runner(["ip", "route", "del", "local", "0.0.0.0/0", "dev", "lo", "table", str(table)])
