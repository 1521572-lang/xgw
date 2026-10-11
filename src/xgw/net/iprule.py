"""Маршрутизация по меткам: пакеты с меткой mark_proxy попадают в Xray.

TPROXY — пакеты доставляются локально, чтобы их принял TPROXY-inbound (официальная
инструкция TPROXY). Так идёт сеть LAN и, по умолчанию, сама машина:

    ip rule add fwmark <mark_proxy> lookup <route_table> pref 100
    ip route add local 0.0.0.0/0 dev lo table <route_table>

TUN (capture.method = "tun") — пакеты самой машины уходят в TUN-интерфейс, который
читает Xray. Нужна отдельная таблица: помеченные пакеты LAN по-прежнему должны
доставляться локально (TPROXY), поэтому правило для TUN выбирает только пакеты,
созданные на самой машине (`iif lo`), и стоит раньше:

    ip rule add fwmark <mark_proxy> iif lo lookup <tun_route_table> pref 90
    ip route add default dev <tun> table <tun_route_table>
    ip route add blackhole default metric 4096 table <tun_route_table>

Чёрная дыра в той же таблице — запасной маршрут: пока интерфейс есть (он постоянный,
его создаёт XGW), пакеты идут в него и без читающего Xray отбрасываются; если же
интерфейса не стало, помеченные пакеты не уходят мимо VPN, а пропадают.

Для IPv6 (network.ipv6 = "proxy") то же с `ip -6` и `::/0`; таблицы маршрутизации у
семейств отдельные, номера одни и те же.

Повторное применение дубликатов не создаёт.
"""

from __future__ import annotations

import json

from .cmd import CommandError, Runner

PREF = 100
PREF_TUN = 90
BLACKHOLE_METRIC = 4096
ANYWHERE = {4: "0.0.0.0/0", 6: "::/0"}


def _ip(family: int) -> list[str]:
    return ["ip", "-6"] if family == 6 else ["ip"]


def _rules(
    mark: int, table: int, runner: Runner, family: int = 4, iif: str | None = None
) -> list[dict]:
    """Правила `fwmark <mark> [iif <iif>] lookup <table>`, которые уже есть в системе."""
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
        if same_mark and str(rule.get("table")) == str(table) and rule.get("iif") == iif:
            found.append(rule)
    return found


def _routes(table: int, runner: Runner, family: int) -> list[dict]:
    try:
        routes = json.loads(
            runner([*_ip(family), "-j", "route", "show", "table", str(table)]) or "[]"
        )
    except (CommandError, json.JSONDecodeError):
        return []  # таблицы маршрутизации ещё нет
    return [route for route in routes if isinstance(route, dict)]


def _default(route: dict, family: int) -> bool:
    return route.get("dst") in ("default", ANYWHERE[family])


def _is_local(route: dict, family: int) -> bool:
    return route.get("type") == "local" and _default(route, family) and route.get("dev") == "lo"


def _is_blackhole(route: dict, family: int) -> bool:
    return route.get("type") == "blackhole" and _default(route, family)


def _is_tun(route: dict, family: int, dev: str) -> bool:
    return (
        route.get("type") in (None, "unicast") and _default(route, family)
        and route.get("dev") == dev
    )


def _del_rules(mark: int, table: int, runner: Runner, family: int, iif: str | None) -> None:
    ip = _ip(family)
    for _rule in _rules(mark, table, runner, family, iif):
        argv = [*ip, "rule", "del", "fwmark", str(mark)]
        if iif is not None:
            argv += ["iif", iif]
        runner([*argv, "lookup", str(table)])


def has_rule(
    mark: int, table: int, runner: Runner, family: int = 4, iif: str | None = None
) -> bool:
    """Есть ли правило `fwmark <mark> [iif <iif>] lookup <table>` (для поиска лишних)."""
    return bool(_rules(mark, table, runner, family, iif))


# --- TPROXY: локальная доставка ------------------------------------------------


def present(mark: int, table: int, runner: Runner, family: int = 4) -> bool:
    return bool(_rules(mark, table, runner, family)) and any(
        _is_local(route, family) for route in _routes(table, runner, family)
    )


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
    _del_rules(mark, table, runner, family, None)
    if any(_is_local(route, family) for route in _routes(table, runner, family)):
        runner([*ip, "route", "del", "local", ANYWHERE[family], "dev", "lo", "table", str(table)])


# --- TUN: маршрут в интерфейс --------------------------------------------------


def present_tun(mark: int, table: int, runner: Runner, family: int, dev: str) -> bool:
    routes = _routes(table, runner, family)
    return (
        bool(_rules(mark, table, runner, family, "lo"))
        and any(_is_tun(route, family, dev) for route in routes)
        and any(_is_blackhole(route, family) for route in routes)
    )


def ensure_tun(mark: int, table: int, runner: Runner, family: int, dev: str) -> None:
    """Пакеты с меткой, созданные на самой машине, уходят в интерфейс dev (он уже должен
    существовать); правило, интерфейсный маршрут и чёрная дыра — по одному экземпляру."""
    ip = _ip(family)
    existing = _rules(mark, table, runner, family, "lo")
    for _extra in existing[1:]:
        runner([*ip, "rule", "del", "fwmark", str(mark), "iif", "lo", "lookup", str(table)])
    if not existing:
        runner([*ip, "rule", "add", "fwmark", str(mark), "iif", "lo", "lookup", str(table),
                "pref", str(PREF_TUN)])
    runner([*ip, "route", "replace", "default", "dev", dev, "table", str(table)])
    runner([*ip, "route", "replace", "blackhole", "default", "metric", str(BLACKHOLE_METRIC),
            "table", str(table)])


def remove_tun(mark: int, table: int, runner: Runner, family: int, dev: str) -> None:
    """Убирает правило для TUN, маршрут в интерфейс dev и чёрную дыру; чужие маршруты в
    таблице и отсутствующее не трогает."""
    ip = _ip(family)
    _del_rules(mark, table, runner, family, "lo")
    for route in _routes(table, runner, family):
        if _is_blackhole(route, family):
            runner([*ip, "route", "del", "blackhole", "default", "metric",
                    str(route.get("metric", BLACKHOLE_METRIC)), "table", str(table)])
        elif _is_tun(route, family, dev):
            runner([*ip, "route", "del", "default", "dev", dev, "table", str(table)])
