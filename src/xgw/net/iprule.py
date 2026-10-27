"""Маршрутизация по меткам: пакеты с меткой mark_proxy попадают в Xray.

TPROXY — пакеты доставляются локально, чтобы их принял TPROXY-inbound (официальная
инструкция TPROXY). Так идёт сеть LAN и, по умолчанию, сама машина:

    ip rule add fwmark <mark_proxy> lookup <route_table> pref 100
    ip route add local 0.0.0.0/0 dev lo table <route_table>
    ip route add throw <подсеть LAN> table <route_table>

Маршрут throw для подсети LAN нужен проверке источника. Когда включён
net.ipv4.conf.all.src_valid_mark (его ставит, например, tailscaled), ядро проверяет
адрес источника входящего пакета с учётом метки: ищет обратный маршрут к клиенту LAN в
той же таблице, а там — только local 0.0.0.0/0. Источник выглядит «своим» адресом, пришедшим
не с lo, и пакет молча отбрасывается до TPROXY: устройства LAN без интернета, а машина и
контейнеры (у них другие пути) работают (ASSUMPTIONS, п. 223). throw отправляет поиск
дальше по правилам — в main, где клиент LAN за своим интерфейсом. Пакеты к самой подсети
LAN перехват не помечает (частные сети идут мимо Xray), так что прямой путь он не меняет.

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

Контейнеры Docker (capture.containers) — их пакеты, помеченные mark_containers, идут
через ту же таблицу TUN, только без `iif lo` (они приходят с мостов Docker):

    ip rule add fwmark <mark_containers> lookup <tun_route_table> pref 95

Маршрут в интерфейс — когда интерфейс есть; чёрная дыра — всегда: пока Xray не
перезапущен с inbound'ом TUN (Docker только что появился), контейнеры закрыты, а не
выходят мимо VPN.

Для IPv6 (network.ipv6 = "proxy") то же с `ip -6` и `::/0`; таблицы маршрутизации у
семейств отдельные, номера одни и те же.

Повторное применение дубликатов не создаёт.
"""

from __future__ import annotations

import json

from .cmd import CommandError, Runner

PREF = 100
PREF_TUN = 90
PREF_CONTAINERS = 95
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


def _throws(routes: list[dict]) -> set[str]:
    """Подсети маршрутов throw в таблице."""
    return {str(route.get("dst")) for route in routes if route.get("type") == "throw"}


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


def present(
    mark: int, table: int, runner: Runner, family: int = 4, throws: tuple[str, ...] = ()
) -> bool:
    """Правило, локальный маршрут и ровно те маршруты throw, что нужны (throws)."""
    routes = _routes(table, runner, family)
    return (
        bool(_rules(mark, table, runner, family))
        and any(_is_local(route, family) for route in routes)
        and _throws(routes) == set(throws)
    )


def ensure(
    mark: int, table: int, runner: Runner, family: int = 4, throws: tuple[str, ...] = ()
) -> None:
    """Правило и маршрут есть ровно в одном экземпляре; маршруты throw — ровно для
    подсетей throws (лишние убираются: подсеть LAN сменили). Сначала маршруты, правило —
    последним: без них помеченный пакет самой машины ушёл бы по main мимо VPN (третий аудит
    0.2.0)."""
    ip = _ip(family)
    runner([*ip, "route", "replace", "local", ANYWHERE[family], "dev", "lo", "table", str(table)])
    have = _throws(_routes(table, runner, family))
    for network in throws:
        if network not in have:
            runner([*ip, "route", "replace", "throw", network, "table", str(table)])
    for network in sorted(have - set(throws)):
        runner([*ip, "route", "del", "throw", network, "table", str(table)])
    existing = _rules(mark, table, runner, family)
    for _extra in existing[1:]:
        runner([*ip, "rule", "del", "fwmark", str(mark), "lookup", str(table)])
    if not existing:
        runner([*ip, "rule", "add", "fwmark", str(mark), "lookup", str(table), "pref", str(PREF)])


def remove(mark: int, table: int, runner: Runner, family: int = 4) -> None:
    """Убирает правило (все экземпляры), локальный маршрут и маршруты throw;
    отсутствующее — не ошибка."""
    ip = _ip(family)
    _del_rules(mark, table, runner, family, None)
    routes = _routes(table, runner, family)
    if any(_is_local(route, family) for route in routes):
        runner([*ip, "route", "del", "local", ANYWHERE[family], "dev", "lo", "table", str(table)])
    for network in sorted(_throws(routes)):
        runner([*ip, "route", "del", "throw", network, "table", str(table)])


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
    существовать); правило, интерфейсный маршрут и чёрная дыра — по одному экземпляру.
    Сначала таблица (чёрная дыра, затем интерфейс), правило — последним: без маршрутов в
    таблице помеченный пакет ушёл бы по main мимо VPN (третий аудит 0.2.0)."""
    ip = _ip(family)
    runner([*ip, "route", "replace", "blackhole", "default", "metric", str(BLACKHOLE_METRIC),
            "table", str(table)])
    runner([*ip, "route", "replace", "default", "dev", dev, "table", str(table)])
    existing = _rules(mark, table, runner, family, "lo")
    for _extra in existing[1:]:
        runner([*ip, "rule", "del", "fwmark", str(mark), "iif", "lo", "lookup", str(table)])
    if not existing:
        runner([*ip, "rule", "add", "fwmark", str(mark), "iif", "lo", "lookup", str(table),
                "pref", str(PREF_TUN)])


def remove_tun(
    mark: int, table: int, runner: Runner, family: int, dev: str, *, keep_routes: bool = False
) -> None:
    """Убирает правило для TUN, маршрут в интерфейс dev и чёрную дыру; чужие маршруты в
    таблице и отсутствующее не трогает. keep_routes — таблица ещё нужна контейнерам:
    убирается только правило."""
    _del_rules(mark, table, runner, family, "lo")
    if not keep_routes:
        _del_tun_routes(table, runner, family, dev)


def _del_tun_routes(table: int, runner: Runner, family: int, dev: str) -> None:
    ip = _ip(family)
    for route in _routes(table, runner, family):
        if _is_blackhole(route, family):
            runner([*ip, "route", "del", "blackhole", "default", "metric",
                    str(route.get("metric", BLACKHOLE_METRIC)), "table", str(table)])
        elif _is_tun(route, family, dev):
            runner([*ip, "route", "del", "default", "dev", dev, "table", str(table)])


# --- контейнеры Docker: по метке в TUN -------------------------------------------


def present_containers(mark: int, table: int, runner: Runner, dev: str | None) -> bool:
    """Правило для контейнеров и чёрная дыра на месте; dev — интерфейс TUN, если он есть
    (тогда нужен и маршрут в него)."""
    routes = _routes(table, runner, 4)
    return (
        bool(_rules(mark, table, runner, 4))
        and any(_is_blackhole(route, 4) for route in routes)
        and (dev is None or any(_is_tun(route, 4, dev) for route in routes))
    )


def ensure_containers(mark: int, table: int, runner: Runner, dev: str | None) -> None:
    """Пакеты контейнеров с меткой mark уходят в TUN-интерфейс dev, а пока его нет — в
    чёрную дыру. Правило — по одному экземпляру и последним, после маршрутов (как ensure_tun)."""
    runner(["ip", "route", "replace", "blackhole", "default", "metric", str(BLACKHOLE_METRIC),
            "table", str(table)])
    if dev is not None:
        runner(["ip", "route", "replace", "default", "dev", dev, "table", str(table)])
    existing = _rules(mark, table, runner, 4)
    for _extra in existing[1:]:
        runner(["ip", "rule", "del", "fwmark", str(mark), "lookup", str(table)])
    if not existing:
        runner(["ip", "rule", "add", "fwmark", str(mark), "lookup", str(table),
                "pref", str(PREF_CONTAINERS)])


def remove_containers(
    mark: int, table: int, runner: Runner, dev: str, *, keep_routes: bool = False
) -> None:
    """Убирает правило для контейнеров; маршруты таблицы — если они не нужны трафику
    самой машины (keep_routes)."""
    _del_rules(mark, table, runner, 4, None)
    if not keep_routes:
        _del_tun_routes(table, runner, 4, dev)
