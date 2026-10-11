"""Маршрутизация по меткам: пакеты с меткой mark_proxy доставляются локально,
чтобы их принял TPROXY-inbound Xray (официальная инструкция TPROXY):

    ip rule add fwmark <mark_proxy> lookup <route_table> pref 100
    ip route add local 0.0.0.0/0 dev lo table <route_table>

Для IPv6 (network.ipv6 = "proxy") то же с `ip -6` и `local ::/0`; таблица
маршрутизации у семейств отдельная, номер один и тот же.

Повторное применение дубликатов не создаёт.
"""

from __future__ import annotations

import json

from .cmd import CommandError, Runner

PREF = 100
ANYWHERE = {4: "0.0.0.0/0", 6: "::/0"}


def _ip(family: int) -> list[str]:
    return ["ip", "-6"] if family == 6 else ["ip"]


def _rules(mark: int, table: int, runner: Runner, family: int = 4) -> list[dict]:
    """Правила `fwmark <mark> lookup <table>`, которые уже есть в системе."""
    try:
        listing = json.loads(runner([*_ip(family), "-j", "rule", "show"]) or "[]")
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


def _has_route(table: int, runner: Runner, family: int = 4) -> bool:
    try:
        routes = json.loads(
            runner([*_ip(family), "-j", "route", "show", "table", str(table)]) or "[]"
        )
    except (CommandError, json.JSONDecodeError):
        return False  # таблицы маршрутизации ещё нет
    return any(
        route.get("type") == "local"
        and route.get("dst") in ("default", ANYWHERE[family])
        and route.get("dev") == "lo"
        for route in routes
    )


def present(mark: int, table: int, runner: Runner, family: int = 4) -> bool:
    return bool(_rules(mark, table, runner, family)) and _has_route(table, runner, family)


def ensure(mark: int, table: int, runner: Runner, family: int = 4) -> None:
    """Правило и маршрут есть ровно в одном экземпляре."""
    ip = _ip(family)
    existing = _rules(mark, table, runner, family)
    for _extra in existing[1:]:
        runner([*ip, "rule", "del", "fwmark", str(mark), "lookup", str(table)])
    if not existing:
        runner([*ip, "rule", "add", "fwmark", str(mark), "lookup", str(table), "pref", str(PREF)])
    runner([*ip, "route", "replace", "local", ANYWHERE[family], "dev", "lo", "table", str(table)])


def remove(mark: int, table: int, runner: Runner, family: int = 4) -> None:
    """Убирает правило (все экземпляры) и маршрут; отсутствующее — не ошибка."""
    ip = _ip(family)
    for _rule in _rules(mark, table, runner, family):
        runner([*ip, "rule", "del", "fwmark", str(mark), "lookup", str(table)])
    if _has_route(table, runner, family):
        runner([*ip, "route", "del", "local", ANYWHERE[family], "dev", "lo", "table", str(table)])
