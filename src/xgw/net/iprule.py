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

Таблицы маршрутизации XGW (route_table, tun_route_table) — свои: в них ровно те маршруты,
что выше, а лишний (кто-то добавил, например, сеть через WAN) проверка видит, и загрузка его
убирает — иначе помеченные пакеты к этой сети ушли бы мимо VPN (кросс-аудит 4cc96b9, N04).
Чужие правила `ip rule` не трогаются никогда — даже с той же меткой и таблицей, но с другими
условиями (N03).
"""

from __future__ import annotations

import json

from .cmd import CommandError, Runner

PREF = 100
PREF_TUN = 90
PREF_CONTAINERS = 95
BLACKHOLE_METRIC = 4096
ANYWHERE = {4: "0.0.0.0/0", 6: "::/0"}
# Чтение таблицы, в которой ещё не было маршрутов: `ip route show table N` завершается с кодом 2 и
# этим текстом ядра (проверено: ядро 6.18, iproute2 6.19; язык системы на него не влияет).
NO_TABLE = "FIB table does not exist"
# Ключи `ip -j rule show`, при которых правило — ровно правило XGW (кросс-аудит 4cc96b9, N03).
# Любой другой (uidrange, ipproto, sport, dport, oif, l3mdev, not, suppress_prefixlength, tos,
# goto…) сужает или меняет правило: помеченный трафик, которому оно не подходит, ушёл бы по
# main мимо VPN, а проверка считала бы правило на месте.
RULE_KEYS = frozenset({"priority", "src", "dst", "fwmark", "fwmask", "iif", "table", "protocol"})


def _ip(family: int) -> list[str]:
    return ["ip", "-6"] if family == 6 else ["ip"]


def _number(value: object) -> int | None:
    """Метка или маска из `ip -j rule show`: «0x1» и «1» — одно и то же число."""
    text = str(value).strip()
    for base in (0, 16):
        try:
            return int(text, base)
        except ValueError:
            continue
    return None


def _listing(runner: Runner, family: int) -> list[dict]:
    try:
        listing = json.loads(runner([*_ip(family), "-j", "rule", "show"]) or "[]")
    except json.JSONDecodeError as exc:
        raise CommandError(f"ip -j rule show: непонятный ответ ({exc})") from exc
    return [rule for rule in listing if isinstance(rule, dict)]


def _rules(
    mark: int, table: int, runner: Runner, family: int = 4, iif: str | None = None
) -> list[dict]:
    """Правила `fwmark <mark> [iif <iif>] lookup <table>`, которые уже есть в системе (и
    чужие с теми же меткой и таблицей — их отличает _plain)."""
    return [
        rule for rule in _listing(runner, family)
        if _number(rule.get("fwmark", "")) == mark and str(rule.get("table")) == str(table)
        and rule.get("iif") == iif
    ]


def _routes(table: int, runner: Runner, family: int) -> list[dict]:
    """Маршруты таблицы. Пусто — только если таблица действительно пуста или её ещё нет; любой
    другой сбой — CommandError: «не удалось узнать» не значит «маршрутов нет» (п. 347, A-04)."""
    try:
        text = runner([*_ip(family), "-j", "route", "show", "table", str(table)])
    except CommandError as exc:
        if NO_TABLE in str(exc):
            return []
        raise
    try:
        routes = json.loads(text or "[]")
    except json.JSONDecodeError as exc:
        raise CommandError(f"ip -j route show: непонятный ответ ({exc})") from exc
    if not isinstance(routes, list):
        raise CommandError("ip -j route show: ответ не список")
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


def _unexpected(routes: list[dict], allowed) -> list[dict]:
    """Маршруты таблицы XGW, которых в ней быть не должно (allowed — что должно)."""
    return [route for route in routes if not allowed(route)]


def _del_route(route: dict, table: int, runner: Runner, family: int) -> None:
    """Убирает маршрут таблицы XGW таким, каким его показал `ip -j route show`."""
    kind = route.get("type")
    argv = [*_ip(family), "route", "del", *([str(kind)] if kind and kind != "unicast" else []),
            str(route.get("dst") or "default")]
    if route.get("gateway"):
        argv += ["via", str(route["gateway"])]
    if route.get("dev"):
        argv += ["dev", str(route["dev"])]
    if isinstance(route.get("metric"), int):
        argv += ["metric", str(route["metric"])]
    runner([*argv, "table", str(table)])


def _del_rules(mark: int, table: int, runner: Runner, family: int, iif: str | None) -> None:
    """Убирает свои правила — без лишних условий (_plain), каждое по его приоритету: чужое
    правило с той же меткой и таблицей, но с другими условиями остаётся (N03)."""
    ip = _ip(family)
    for rule in _rules(mark, table, runner, family, iif):
        if not (_plain(rule) and isinstance(rule.get("priority"), int)):
            continue
        argv = [*ip, "rule", "del", "fwmark", str(mark)]
        if iif is not None:
            argv += ["iif", iif]
        runner([*argv, "lookup", str(table), "pref", str(rule["priority"])])


def _plain(rule: dict) -> bool:
    """Без лишних условий: только ключи RULE_KEYS, полная маска метки, «from all», без адреса
    назначения."""
    return (
        set(rule) <= RULE_KEYS
        and _number(rule.get("fwmask", 0xFFFFFFFF)) == 0xFFFFFFFF
        and rule.get("src", "all") == "all"
        and rule.get("dst", "all") == "all"
    )


def _exact(rule: dict, pref: int) -> bool:
    """Правило XGW как есть: его приоритет и без лишних условий. Правило с той же меткой и
    таблицей, но другим приоритетом (например, после main — 32767) помеченный трафик в
    таблицу не ведёт: main выбирается раньше (пятый аудит)."""
    return rule.get("priority") == pref and _plain(rule)


def _ensure_rule(
    mark: int, table: int, runner: Runner, family: int, iif: str | None, pref: int
) -> None:
    """Ровно одно правило `fwmark <mark> [iif <iif>] lookup <table> pref <pref>`. Своё с другим
    приоритетом (сдвинутое) убирается — после того, как нужное на месте: иначе на миг
    помеченный трафик ушёл бы по main мимо VPN. Чужие правила с другими условиями (src, маска)
    не трогаются."""
    ip = _ip(family)
    selector = ["fwmark", str(mark), *(["iif", iif] if iif is not None else []),
                "lookup", str(table)]
    existing = _rules(mark, table, runner, family, iif)
    exact = [rule for rule in existing if _exact(rule, pref)]
    if not exact:
        runner([*ip, "rule", "add", *selector, "pref", str(pref)])
    for rule in existing:
        if exact and rule is exact[0]:
            continue
        if _plain(rule) and isinstance(rule.get("priority"), int):
            runner([*ip, "rule", "del", *selector, "pref", str(rule["priority"])])


def _has_exact(
    mark: int, table: int, runner: Runner, family: int, iif: str | None, pref: int
) -> bool:
    return any(_exact(rule, pref) for rule in _rules(mark, table, runner, family, iif))


def has_rule(
    mark: int, table: int, runner: Runner, family: int = 4, iif: str | None = None
) -> bool:
    """Есть ли своё правило `fwmark <mark> [iif <iif>] lookup <table>` (для поиска лишних).
    Чужое с другими условиями не в счёт: убрать его XGW не вправе (_del_rules), и проверка
    иначе загружала бы правила по кругу."""
    return any(_plain(rule) for rule in _rules(mark, table, runner, family, iif))


def early(runner: Runner, family: int, tables: tuple[int, ...], before: int = PREF) -> list[int]:
    """Приоритеты чужих правил `ip rule` раньше правил XGW (кросс-аудит 4cc96b9, N03): такое
    правило может увести помеченный трафик мимо таблиц XGW, по main мимо VPN. Не в счёт
    обычное «from all lookup local» (pref 0), правила в таблицы XGW (tables) и правила без
    lookup (unreachable, prohibit — они трафик не выпускают). Ничего не меняет: чужие правила
    XGW не трогает, о них говорит `xgw diag`. Сбой чтения — CommandError: пустой список значит
    только «таких правил нет» (п. 347, A-05)."""
    listing = _listing(runner, family)
    own = {str(table) for table in tables}
    found = set()
    for rule in listing:
        priority = rule.get("priority")
        target = rule.get("table")
        if not isinstance(priority, int) or priority >= before or target is None:
            continue
        if str(target) in own or (priority == 0 and str(target) == "local" and _plain(rule)):
            continue
        found.add(priority)
    return sorted(found)


# --- TPROXY: локальная доставка ------------------------------------------------


def _tproxy_route(family: int):
    """Что может быть в таблице TPROXY: локальная доставка и маршруты throw (их набор
    сверяется отдельно)."""
    return lambda route: _is_local(route, family) or route.get("type") == "throw"


def present(
    mark: int, table: int, runner: Runner, family: int = 4, throws: tuple[str, ...] = ()
) -> bool:
    """Правило, локальный маршрут и ровно те маршруты throw, что нужны (throws), — и ничего
    лишнего в таблице (N04)."""
    routes = _routes(table, runner, family)
    return (
        _has_exact(mark, table, runner, family, None, PREF)
        and any(_is_local(route, family) for route in routes)
        and _throws(routes) == set(throws)
        and not _unexpected(routes, _tproxy_route(family))
    )


def ensure(
    mark: int, table: int, runner: Runner, family: int = 4, throws: tuple[str, ...] = ()
) -> None:
    """Правило и маршрут есть ровно в одном экземпляре; маршруты throw — ровно для
    подсетей throws (лишние убираются: подсеть LAN сменили). Сначала маршруты, правило —
    последним: без них помеченный пакет самой машины ушёл бы по main мимо VPN (третий аудит
    0.2.0). Лишние маршруты таблицы убираются уже после правила (N04): не убрался — правило
    и нужные маршруты всё равно на месте."""
    ip = _ip(family)
    runner([*ip, "route", "replace", "local", ANYWHERE[family], "dev", "lo", "table", str(table)])
    have = _throws(_routes(table, runner, family))
    for network in throws:
        if network not in have:
            runner([*ip, "route", "replace", "throw", network, "table", str(table)])
    for network in sorted(have - set(throws)):
        runner([*ip, "route", "del", "throw", network, "table", str(table)])
    _ensure_rule(mark, table, runner, family, None, PREF)
    for route in _unexpected(_routes(table, runner, family), _tproxy_route(family)):
        _del_route(route, table, runner, family)


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


def _tun_route(family: int, dev: str | None):
    """Что может быть в таблице TUN (её делят машина и контейнеры): чёрная дыра и маршрут в
    интерфейс dev, если он есть."""
    return lambda route: _is_blackhole(route, family) or (
        dev is not None and _is_tun(route, family, dev))


def _drop_unexpected(table: int, runner: Runner, family: int, dev: str | None) -> None:
    for route in _unexpected(_routes(table, runner, family), _tun_route(family, dev)):
        _del_route(route, table, runner, family)


def present_tun(mark: int, table: int, runner: Runner, family: int, dev: str) -> bool:
    routes = _routes(table, runner, family)
    return (
        _has_exact(mark, table, runner, family, "lo", PREF_TUN)
        and any(_is_tun(route, family, dev) for route in routes)
        and any(_is_blackhole(route, family) for route in routes)
        and not _unexpected(routes, _tun_route(family, dev))
    )


def ensure_tun(mark: int, table: int, runner: Runner, family: int, dev: str) -> None:
    """Пакеты с меткой, созданные на самой машине, уходят в интерфейс dev (он уже должен
    существовать); правило, интерфейсный маршрут и чёрная дыра — по одному экземпляру.
    Сначала таблица (чёрная дыра, затем интерфейс), правило — последним: без маршрутов в
    таблице помеченный пакет ушёл бы по main мимо VPN (третий аудит 0.2.0). Лишние маршруты
    таблицы — после правила (N04)."""
    ip = _ip(family)
    runner([*ip, "route", "replace", "blackhole", "default", "metric", str(BLACKHOLE_METRIC),
            "table", str(table)])
    runner([*ip, "route", "replace", "default", "dev", dev, "table", str(table)])
    _ensure_rule(mark, table, runner, family, "lo", PREF_TUN)
    _drop_unexpected(table, runner, family, dev)


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
        _has_exact(mark, table, runner, 4, None, PREF_CONTAINERS)
        and any(_is_blackhole(route, 4) for route in routes)
        and (dev is None or any(_is_tun(route, 4, dev) for route in routes))
        and not _unexpected(routes, _tun_route(4, dev))
    )


def ensure_containers(mark: int, table: int, runner: Runner, dev: str | None) -> None:
    """Пакеты контейнеров с меткой mark уходят в TUN-интерфейс dev, а пока его нет — в
    чёрную дыру. Правило — по одному экземпляру и последним, после маршрутов (как ensure_tun);
    лишние маршруты таблицы — после правила (N04)."""
    runner(["ip", "route", "replace", "blackhole", "default", "metric", str(BLACKHOLE_METRIC),
            "table", str(table)])
    if dev is not None:
        runner(["ip", "route", "replace", "default", "dev", dev, "table", str(table)])
    _ensure_rule(mark, table, runner, 4, None, PREF_CONTAINERS)
    _drop_unexpected(table, runner, 4, dev)


def remove_containers(
    mark: int, table: int, runner: Runner, dev: str, *, keep_routes: bool = False
) -> None:
    """Убирает правило для контейнеров; маршруты таблицы — если они не нужны трафику
    самой машины (keep_routes)."""
    _del_rules(mark, table, runner, 4, None)
    if not keep_routes:
        _del_tun_routes(table, runner, 4, dev)
