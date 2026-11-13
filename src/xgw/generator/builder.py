"""Генератор конфига Xray: участники, запасные, probe-inbounds, правила,
балансировщик и burstObservatory с GET-пробами (скелет — раздел 6.6 ТЗ)."""

from __future__ import annotations

import copy
import ipaddress
import re
import secrets
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .. import nfqws2, priority, rating, zapret2
from ..config import Config, service_ports
from ..model import ServerNode
from ..net import sysctl
from ..net.tun import MTU as tun_mtu
from . import fragment as fragmenting
from . import profiles as profiling
from . import singbox as singboxing

PROBE_USER = "xgw"
BALANCER_TAG = "auto"
# Бесплатный пул (веха М2б.1): устройства с «Бесплатные серверы» в панели — балансировщиком
# «pool» из допущенных серверов пула (freepool/traffic.py). Все они мертвы или их нет —
# выход «block»: у такого устройства закрыто, а не подписка и не прямой WAN (R05).
POOL_BALANCER = "pool"
YOUTUBE_BALANCER = "youtube"  # выход для видео (п. 348); есть, только пока есть план
POOL_PREFIX = "pool-"
# API Xray — Unix-сокет в каталоге службы xgw-xray (RuntimeDirectory), а не порт на 127.0.0.1:
# к порту мог подключиться любой процесс машины (ASSUMPTIONS п. 253). Стенд и тесты под
# XGW_ROOT передают свой путь (engine.assemble — paths.xray_api_socket).
API_SOCKET = "/run/xgw-xray/api.sock"
# Устройство со своим сервером (Ф4): правило по адресу источника прямо на выход этого сервера.
# С 0.2.0 без балансировщика «dev-<адрес>», loopback-выхода to-main и пробы сервера в
# burstObservatory: их появление требовало перезапуска Xray (отчёт f6b — три перезапуска за
# минуту). Жив ли сервер, проверяет демон (Daemon._device_step), и мёртвого он убирает из
# правил (devices_down) — через API ядра, как любое изменение routing.
TS_NET = "domain:ts.net"  # Tailscale Funnel и MagicDNS — мимо VPN-серверов
# Управление, DERP и журнал Tailscale (controlplane, derpN, log): весь дом через пул (М2б.2) их
# в бесплатные серверы не пускает — удалённый доступ к шлюзу держится на tailscaled.
TS_CONTROL = ("domain:tailscale.com", "domain:tailscale.io")
_TAG_RE = re.compile(r"^(proxy|spare|probe)-([a-z]{2})-([0-9a-f]{4,8})$")
_POOL_TAG_RE = re.compile(r"^pool-([a-z]{2})-([0-9a-f]{4,8})$")
TAG_RE = _TAG_RE  # тег узла: роль, страна, начало отпечатка (для команд CLI)


class BuildError(Exception):
    pass


@dataclass
class NodeInfo:
    fingerprint: str
    tag: str
    probe_tag: str
    probe_port: int
    role: str  # proxy | spare | pool
    fragment: bool = False  # соединение идёт через дробление ClientHello (fragment.py)
    # Профиль обхода (profiles.py): каким ядром и как ведётся сервер.
    profile: str = profiling.XRAY_DEFAULT


@dataclass
class Selection:
    members: list[ServerNode] = field(default_factory=list)
    spares: list[ServerNode] = field(default_factory=list)
    chains: list[ServerNode] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Сводка разбора: сколько серверов пришло и почему часть из них в конфиг не попала
    # (junk — служебные адреса, ipv6, filter — фильтр имён, dns — домен не разрешается,
    # excluded — отключены или убраны в панели, duplicates — схлопнутые дубли).
    stats: dict[str, int] = field(default_factory=dict)
    # Резервный выход балансировщика (fallbackTag): лимитированный запасной. Через него
    # трафик идёт, только когда все участники мертвы; observatory его не пробует. None —
    # лимитированных запасных нет, fallbackTag — первый участник.
    reserve: ServerNode | None = None
    # Рейтинг серверов (rating.py), по которому отобраны участники: отпечаток → число.
    scores: dict[str, float] = field(default_factory=dict)


@dataclass
class BuildResult:
    config: dict
    nodes: list[NodeInfo]
    chain_tags: list[str]
    fallback_tag: str
    # Серверы бесплатного пула (балансировщик «pool», роль pool): отдельно от участников и
    # запасных подписки — их счёт, замены и замеры демона пул не задевает.
    pool: list[NodeInfo] = field(default_factory=list)


def is_junk(address: str, port: int) -> bool:
    if not 0 < port < 65536:
        return True
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_unspecified or ip.is_loopback


def _is_ipv6(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).version == 6
    except ValueError:
        return False


def skip_reason(
    node: ServerNode, cfg: Config, include_re=None, exclude_re=None,
    dead: Collection[str] = (), served: Collection[str] | None = None,
) -> str:
    """Почему сервер не попадёт в конфиг Xray; пусто — попадёт.

    excluded — отключён или убран в панели; junk — служебный адрес; ipv6 —
    IPv6-адрес при network.ipv6 = off; filter — отсеян фильтрами по имени; dns —
    домен сервера не разрешается (dead — такие домены, их ведёт engine); core — сервер
    умеет только sing-box, а он не ведёт этот сервер (отключён `core.mode = "xray"` или
    сервер закреплён за Xray, нет sing-box, а при served — сервера нет среди тех, что
    sing-box сейчас ведёт).
    """
    if node.fingerprint in cfg.managed.disabled or node.fingerprint in cfg.managed.removed:
        return "excluded"
    if node.capability == "singbox" and (
        cfg.core.mode == "xray" or cfg.managed.core.get(node.fingerprint) == "xray"
        or (served is not None and node.fingerprint not in served)
    ):
        return "core"
    if is_junk(node.address, node.port):
        return "junk"
    if not cfg.network.ipv6_proxy and _is_ipv6(node.address):
        return "ipv6"
    if node.address in dead:
        return "dns"
    if include_re is None and cfg.filters.include_regex:
        include_re = re.compile(cfg.filters.include_regex)
    if exclude_re is None and cfg.filters.exclude_regex:
        exclude_re = re.compile(cfg.filters.exclude_regex)
    if include_re is not None and not include_re.search(node.name):
        return "filter"
    if exclude_re is not None and exclude_re.search(node.name):
        return "filter"
    return ""


def reserve_price(price: float, floor: float) -> bool:
    """Годится ли сервер такой стоимости в резервный выход при самом дешёвом участнике floor:
    лимитированный и дороже floor — резервный «хуже» участников и в работу без нужды не
    встаёт."""
    return price > 0 and price > floor


def select_nodes(
    nodes: Sequence[ServerNode], cfg: Config, *, prefer: Sequence[str] = (),
    dead: Collection[str] = (), scores: Mapping[str, float] | None = None,
    costs: Mapping[str, float] | None = None, reserve: str | None = None,
    served: Collection[str] | None = None, quota_low: Collection[str] = (),
) -> Selection:
    """Фильтры по имени, отбрасывание служебных адресов, дедупликация,
    канонический порядок (стабилен при любом порядке входных ссылок).

    prefer — отпечатки узлов, которым место в балансировщике в первую очередь
    (лучшие первыми): текущие участники и замены из ротации. Без этого
    обновление подписки перетасовывало бы участников по сортировке отпечатков,
    а результат замены «мёртвого» участника терялся бы при следующей сборке.

    dead — домены, которых нет в DNS: серверы с такими адресами в конфиг не попадают
    и пробы на них не тратятся, пока домен не появится снова (см. engine).

    scores — рейтинг серверов (rating.py, считает демон по замерам); у сервера без него —
    рейтинг по одним приоритету и стоимости (rating.static). Участники — лучшие по рейтингу
    из всех подписок, до max_members (0.2.0, issue #2): приоритет и стоимость — веса, а не
    фильтр. Сервер с рейтингом 0 (x100, квота подписки на исходе — quota_low: отпечатки) в
    участники не попадает. prefer сохраняет нынешних участников и замены из ротации, если
    они годны.

    costs — стоимость серверов по отпечаткам (cost.costs); без неё все безлимитные.

    reserve — отпечаток запасного, которому быть резервным выходом (его выбирает демон
    по дешёвой проверке). Годится лимитированный запасной дороже самого дешёвого участника
    (reserve_price): при безлимитных участниках — любой лимитированный, а когда в работе одни
    x1, резервного нет, как и до 0.2.0. Без reserve резервный — самый дешёвый из годных,
    при равной цене — с лучшим рейтингом.

    served — отпечатки серверов, которые sing-box сейчас ведёт; без него (None) серверы,
    которые умеет только sing-box, отсеиваются лишь по настройкам (skip_reason).
    """
    warnings: list[str] = []
    stats = dict.fromkeys(
        ("total", "junk", "ipv6", "filter", "dns", "excluded", "duplicates", "core"), 0,
    )
    include_re = re.compile(cfg.filters.include_regex) if cfg.filters.include_regex else None
    exclude_re = re.compile(cfg.filters.exclude_regex) if cfg.filters.exclude_regex else None

    chains: list[ServerNode] = []
    chain_tags: set[str] = set()
    unique: dict[str, ServerNode] = {}
    for node in nodes:
        if node.keep_tag:
            if node.keep_tag not in chain_tags:
                chain_tags.add(node.keep_tag)
                chains.append(node)
            continue
        stats["total"] += 1
        reason = skip_reason(node, cfg, include_re, exclude_re, dead, served)
        if reason == "junk":
            warnings.append(
                f"узел «{node.name}» отброшен: служебный адрес {node.address}:{node.port}"
            )
        elif reason == "ipv6":
            warnings.append(f"узел «{node.name}» отброшен: IPv6-адрес при network.ipv6 = off")
        elif reason == "dns":
            warnings.append(
                f"узел «{node.name}» отложен: домен {node.address} не разрешается"
            )
        if reason:
            stats[reason] += 1
            continue
        if node.fingerprint in unique:
            warnings.append(f"дубль «{node.name}» схлопнут с «{unique[node.fingerprint].name}»")
            stats["duplicates"] += 1
            continue
        unique[node.fingerprint] = node

    levels = cfg.managed.priority
    prices = costs if costs is not None else dict.fromkeys(unique, 0.0)
    low = set(quota_low)
    rated: dict[str, float] = {}
    for fingerprint in unique:
        price = prices.get(fingerprint, 1.0)
        if scores is not None and fingerprint in scores:
            value = float(scores[fingerprint])
            if rating.cost_factor(price, fingerprint in low) == 0:
                value = 0.0  # квота кончилась после замера — всё равно не в работу
        else:
            value = rating.static(
                priority.level_of(levels, fingerprint), price, fingerprint in low)
        rated[fingerprint] = value
    limit = max(1, cfg.filters.max_members)
    members: list[ServerNode] = []
    for fingerprint in prefer:
        node = unique.get(fingerprint)
        if (
            node is not None and node not in members and len(members) < limit
            and rated[fingerprint] > 0
        ):
            members.append(node)
    chosen = {node.fingerprint for node in members}
    # Запасные — в каноническом порядке (по отпечатку): рейтинг меняется с каждым замером, и
    # порядок по нему пересобирал бы конфиг без всякой перемены состава.
    rest = sorted(
        (node for node in unique.values() if node.fingerprint not in chosen),
        key=lambda node: (node.fingerprint, node.name),
    )
    free = limit - len(members)
    best = sorted(
        (node for node in rest if rated[node.fingerprint] > 0),
        key=lambda node: (-rated[node.fingerprint], node.fingerprint, node.name),
    )[:free]
    members.extend(best)
    taken = {node.fingerprint for node in best}
    spares = [node for node in rest if node.fingerprint not in taken]
    floor = min((prices.get(node.fingerprint, 1.0) for node in members), default=0.0)
    limited = sorted(
        (node for node in spares if reserve_price(prices.get(node.fingerprint, 1.0), floor)),
        key=lambda node: (
            node.fingerprint in low, prices.get(node.fingerprint, 1.0),
            -rated[node.fingerprint], node.fingerprint, node.name,
        ),
    )
    backup = next((node for node in limited if node.fingerprint == reserve), None)
    if backup is None and limited:
        backup = limited[0]

    # Звенья цепочек нужны, только пока на них ссылается хоть один оставленный узел.
    kept = [*members, *spares]
    chains = _referenced_chains(kept, chains)
    return Selection(
        members=members, spares=spares, chains=chains, warnings=warnings, stats=stats,
        reserve=backup, scores=rated,
    )


def _dialer(outbound: dict) -> str | None:
    stream = outbound.get("streamSettings")
    sockopt = stream.get("sockopt") if isinstance(stream, dict) else None
    tag = sockopt.get("dialerProxy") if isinstance(sockopt, dict) else None
    return str(tag) if tag else None


def _referenced_chains(nodes: Sequence[ServerNode], chains: list[ServerNode]) -> list[ServerNode]:
    by_tag = {node.keep_tag: node for node in chains}
    needed: set[str] = set()
    queue = [tag for tag in (_dialer(node.outbound) for node in nodes) if tag]
    while queue:
        tag = queue.pop()
        if tag in needed or tag not in by_tag:
            continue
        needed.add(tag)
        nested = _dialer(by_tag[tag].outbound)
        if nested:
            queue.append(nested)
    return [node for node in chains if node.keep_tag in needed]


@dataclass(frozen=True)
class MediaPlan:
    """Куда вести видео: теги серверов и домены (config.Media)."""

    outbound_tags: tuple[str, ...]
    domains: tuple[str, ...]


def applied_media(config: Mapping | None) -> tuple[str, ...]:
    """Теги выхода видео в применённом конфиге; пусто — правила нет."""
    routing = config.get("routing") if isinstance(config, Mapping) else None
    balancers = routing.get("balancers") if isinstance(routing, Mapping) else None
    for balancer in balancers if isinstance(balancers, list) else []:
        if isinstance(balancer, Mapping) and balancer.get("tag") == YOUTUBE_BALANCER:
            selector = balancer.get("selector")
            return tuple(str(tag) for tag in selector) if isinstance(selector, list) else ()
    return ()


def applied_media_domains(config: Mapping | None) -> tuple[str, ...]:
    """Домены правила видео в применённом конфиге; пусто — правила нет."""
    routing = config.get("routing") if isinstance(config, Mapping) else None
    rules = routing.get("rules") if isinstance(routing, Mapping) else None
    for rule in rules if isinstance(rules, list) else []:
        if isinstance(rule, Mapping) and rule.get("balancerTag") == YOUTUBE_BALANCER:
            domain = rule.get("domain")
            return tuple(str(item) for item in domain) if isinstance(domain, list) else ()
    return ()


def media_problems(config: Mapping | None) -> list[str]:
    """Что не так с правилом видео в применённом конфиге (`xgw diag`). Пусто — всё согласовано
    либо правила нет."""
    routing = config.get("routing") if isinstance(config, Mapping) else None
    if not isinstance(routing, Mapping):
        return []
    rules = [rule for rule in routing.get("rules") or [] if isinstance(rule, Mapping)]
    at = [index for index, rule in enumerate(rules) if rule.get("balancerTag") == YOUTUBE_BALANCER]
    balancer = next((item for item in routing.get("balancers") or [] if isinstance(item, Mapping)
                     and item.get("tag") == YOUTUBE_BALANCER), None)
    if not at and balancer is None:
        return []
    if not at or balancer is None:
        return ["правило видео и его балансировщик не согласованы"]
    tags = {str(item.get("tag")) for item in config.get("outbounds") or []
            if isinstance(item, Mapping)}
    selector = [str(tag) for tag in balancer.get("selector") or []]
    problems = []
    if not selector or not all(tag in tags and tag.startswith("proxy-") for tag in selector):
        problems.append("в выходе видео сервер, которого нет в конфиге")
    if any(other != tag and other.startswith(tag) for tag in selector for other in tags):
        problems.append("выход видео захватывает посторонний сервер: тег — начало другого")
    if str(balancer.get("fallbackTag")) not in selector:
        problems.append("запасной выход видео — не его сервер")
    if applied_whole(config):
        problems.append("правило видео при режиме «весь дом через пул»")
    wanted_first = [index for index, rule in enumerate(rules) if rule.get("source")
                    or rule.get("outboundTag") == "direct"]
    if wanted_first and at[0] < max(wanted_first):
        problems.append("правило видео стоит раньше прямых адресов или правил устройств")
    if at[0] >= len(rules) - 1:
        problems.append("правило видео стоит после общего правила")
    return problems


def assign_suffixes(nodes: Sequence[ServerNode]) -> dict[str, str]:
    """Отпечаток → «<страна>-<fp>»: 4 hex, при коллизии — 6, затем 8.

    Суффикс общий для тегов proxy-/spare-/probe- одного узла, поэтому коллизию
    считаем по суффиксу, а не по полному тегу: участник и запасной с одинаковыми
    4 hex иначе получили бы один и тот же probe-тег. Длину выбираем для всей
    группы совпавших узлов сразу — результат не зависит от порядка обхода.
    """
    result: dict[str, str] = {}
    pending = list(nodes)
    for size in (4, 6, 8):
        groups: dict[str, list[ServerNode]] = defaultdict(list)
        for node in pending:
            groups[f"{node.country}-{node.fingerprint[:size]}"].append(node)
        pending = []
        for suffix, group in groups.items():
            if len(group) == 1:
                result[group[0].fingerprint] = suffix
            else:
                pending.extend(group)
        if not pending:
            return result
    names = ", ".join(f"«{node.name}»" for node in pending)
    raise BuildError(f"не удалось построить уникальные теги для узлов {names}")


def probe_state(config: Mapping | None) -> tuple[str | None, dict[str, int]]:
    """Пароль и порты probe-inbounds из применённого конфига.

    Новая сборка обязана их переиспользовать: работающий Xray держит inbounds с
    этими портами и паролем, и расхождение сломало бы сканы запасных, а смена
    порта у существующего тега означала бы лишние rmi/adi на каждом обновлении.
    """
    password: str | None = None
    ports: dict[str, int] = {}
    if not isinstance(config, Mapping):
        return password, ports
    for inbound in config.get("inbounds") or []:
        if not isinstance(inbound, Mapping):
            continue
        tag = str(inbound.get("tag") or "")
        port = inbound.get("port")
        if not tag.startswith("probe-") or not isinstance(port, int):
            continue
        ports[tag] = port
        accounts = (inbound.get("settings") or {}).get("accounts") or []
        if password is None and accounts and isinstance(accounts[0], Mapping):
            candidate = accounts[0].get("pass")
            if isinstance(candidate, str) and candidate:
                password = candidate
    return password, ports


def member_fingerprints(config: Mapping | None, nodes: Sequence[ServerNode]) -> list[str]:
    """Отпечатки текущих участников балансировщика в порядке применённого
    конфига — для select_nodes(prefer=…). Узел опознаётся по суффиксу тега."""
    if not isinstance(config, Mapping):
        return []
    result: list[str] = []
    for outbound in config.get("outbounds") or []:
        if not isinstance(outbound, Mapping):
            continue
        match = _TAG_RE.match(str(outbound.get("tag") or ""))
        if not match or match.group(1) != "proxy":
            continue
        country, prefix = match.group(2), match.group(3)
        found = [
            node.fingerprint
            for node in nodes
            if not node.keep_tag and node.country == country and node.fingerprint.startswith(prefix)
        ]
        if len(set(found)) == 1 and found[0] not in result:
            result.append(found[0])
    return result


def reserve_tag(config: Mapping | None) -> str:
    """Тег резервного выхода из применённого конфига: fallbackTag балансировщика, если
    это запасной (spare-*); пусто — резервного нет, fallbackTag — участник."""
    if not isinstance(config, Mapping):
        return ""
    routing = config.get("routing")
    balancers = routing.get("balancers") if isinstance(routing, Mapping) else None
    for balancer in balancers if isinstance(balancers, list) else []:
        if isinstance(balancer, Mapping) and balancer.get("tag") == BALANCER_TAG:
            tag = str(balancer.get("fallbackTag") or "")
            match = _TAG_RE.match(tag)
            return tag if match and match.group(1) == "spare" else ""
    return ""


def reserve_fingerprint(config: Mapping | None, nodes: Sequence[ServerNode]) -> str | None:
    """Отпечаток резервного выхода применённого конфига — для select_nodes(reserve=…)."""
    match = _TAG_RE.match(reserve_tag(config))
    if not match:
        return None
    country, prefix = match.group(2), match.group(3)
    found = {
        node.fingerprint
        for node in nodes
        if not node.keep_tag and node.country == country and node.fingerprint.startswith(prefix)
    }
    return found.pop() if len(found) == 1 else None


def _allocate_ports(
    probe_tags: Sequence[str], previous: Mapping[str, int], cfg: Config,
    avoid: Collection[int] = (),
) -> dict[str, int]:
    """Порт закрепляется за probe-тегом: существующие сохраняются, новые
    получают первый свободный, начиная с probe_port_base. Мимо служебных портов XGW и
    ядер (config.service_ports) и avoid — входов sing-box (аудит, F-04)."""
    reserved = set(service_ports(cfg).values()) | set(avoid)
    ports: dict[str, int] = {}
    used: set[int] = set()
    for tag in probe_tags:
        port = previous.get(tag)
        if isinstance(port, int) and 0 < port < 65536 and port not in reserved | used:
            ports[tag] = port
            used.add(port)
    candidate = cfg.xray.probe_port_base
    for tag in probe_tags:
        if tag in ports:
            continue
        while candidate in reserved or candidate in used:
            candidate += 1
        if candidate > 65535:
            raise BuildError("закончились порты для probe-inbounds — уменьшите probe_port_base")
        ports[tag] = candidate
        used.add(candidate)
    return ports


def applied_pool(config: Mapping | None, nodes: Sequence[ServerNode] = ()) -> list[NodeInfo]:
    """Серверы бесплатного пула в работающем ядре (теги pool-*): как applied_nodes, но для
    балансировщика «pool». fingerprint — полный, если сервер однозначно нашёлся среди nodes,
    иначе hex-часть тега."""
    _password, ports = probe_state(config)
    result: list[NodeInfo] = []
    if not isinstance(config, Mapping):
        return result
    for outbound in config.get("outbounds") or []:
        if not isinstance(outbound, Mapping):
            continue
        match = _POOL_TAG_RE.match(str(outbound.get("tag") or ""))
        if not match:
            continue
        country, prefix = match.groups()
        found = {node.fingerprint for node in nodes
                 if node.country == country and node.fingerprint.startswith(prefix)}
        result.append(NodeInfo(
            fingerprint=found.pop() if len(found) == 1 else prefix,
            tag=f"pool-{country}-{prefix}", probe_tag=f"probe-{country}-{prefix}",
            probe_port=ports.get(f"probe-{country}-{prefix}", 0), role="pool",
            fragment=fragmenting.used(outbound), profile=outbound_profile(outbound),
        ))
    return result


def applied_whole(config: Mapping | None) -> bool:
    """Весь дом через пул в работающем ядре (М2б.2): есть правило несущего канала — входы демона
    http-in и socks-in в балансировщик подписки. Оно собирается только при pool_all."""
    routing = config.get("routing") if isinstance(config, Mapping) else None
    rules = routing.get("rules") if isinstance(routing, Mapping) else None
    return any(isinstance(rule, Mapping) and "http-in" in (rule.get("inboundTag") or [])
               and rule.get("balancerTag") == BALANCER_TAG for rule in rules or [])


def applied_nodes(config: Mapping | None, nodes: Sequence[ServerNode] = ()) -> list[NodeInfo]:
    """Участники и запасные так, как они заведены в работающем ядре: теги, роли
    и порты проб из применённого конфига. Нужны демону и CLI — следить за
    ядром можно и тогда, когда подписку получить не удалось.

    fingerprint — полный отпечаток, если узел однозначно нашёлся среди nodes,
    иначе только hex-часть тега (для замены участников такого узла недостаточно).
    """
    _password, ports = probe_state(config)
    result: list[NodeInfo] = []
    if not isinstance(config, Mapping):
        return result
    for outbound in config.get("outbounds") or []:
        if not isinstance(outbound, Mapping):
            continue
        match = _TAG_RE.match(str(outbound.get("tag") or ""))
        if not match or match.group(1) not in ("proxy", "spare"):
            continue
        role, country, prefix = match.groups()
        probe_tag = f"probe-{country}-{prefix}"
        found = {
            node.fingerprint
            for node in nodes
            if not node.keep_tag and node.country == country and node.fingerprint.startswith(prefix)
        }
        result.append(
            NodeInfo(
                fingerprint=found.pop() if len(found) == 1 else prefix,
                tag=f"{role}-{country}-{prefix}",
                probe_tag=probe_tag,
                probe_port=ports.get(probe_tag, 0),
                role=role,
                fragment=fragmenting.used(outbound),
                profile=outbound_profile(outbound),
            )
        )
    return result


def outbound_profile(outbound: Mapping) -> str:
    """Профиль обхода (profiles.py), в котором сервер заведён в Xray: мост к sing-box,
    дробление ClientHello или обычное соединение."""
    letter = singboxing.bridge_variant(outbound)
    if letter:
        return profiling.PROFILE_OF_LETTER[letter]
    dialer = fragmenting.dialer(outbound)
    for profile in profiling.NFQ_PROFILES:
        if dialer == profiling.nfq_tag(profile):
            return profile
    if fragmenting.split_used(outbound):
        return profiling.XRAY_SPLIT
    return profiling.XRAY_FRAGMENT if fragmenting.used(outbound) else profiling.XRAY_DEFAULT


def applied_profiles(config: Mapping | None, nodes: Sequence[ServerNode]) -> dict[str, str]:
    """Отпечаток → профиль сервера в применённом конфиге Xray."""
    known = {node.fingerprint for node in nodes}
    return {
        info.fingerprint: info.profile for info in applied_nodes(config, nodes)
        if info.fingerprint in known
    }


def fragmented_fingerprints(config: Mapping | None, nodes: Sequence[ServerNode]) -> set[str]:
    """Отпечатки серверов, у которых в применённом конфиге включено дробление ClientHello
    (fragment.py), — для build(fragment=…): режим переживает обновление подписки."""
    known = {node.fingerprint for node in nodes}
    return {
        info.fingerprint for info in applied_nodes(config, nodes)
        if info.fragment and info.fingerprint in known
    }


def device_routes(
    cfg: Config, nodes: Sequence[NodeInfo], down: Collection[str] = (),
) -> list[tuple[str, str]]:
    """(адрес устройства, тег его сервера) для устройств со своим сервером
    (cfg.managed.routes, Ф4). Сервера нет в конфиге (отключён, убран, отсеян) или демон счёл
    его мёртвым (down — адреса устройств) — устройство идёт через основной, как все."""
    tags = {info.fingerprint: info.tag for info in nodes}
    return [
        (ip, tags[fingerprint])
        for ip, fingerprint in sorted(cfg.managed.routes.items())
        if fingerprint in tags and ip not in down
    ]


def _dns_server(entry: str) -> tuple[str, int | None]:
    """«1.1.1.1» или «1.1.1.1:5353» → (адрес, порт). Порт не 53 Xray принимает
    только объектом {"address", "port"}. Адрес DoH («https://77.88.8.8/dns-query») — как
    есть: порт в нём самом."""
    if "://" in entry:
        return entry, None
    address, sep, port = entry.rpartition(":")
    if sep and port.isdigit() and address.count(".") == 3:
        return address, int(port)
    return entry, None


def dns_server_ip(entry: str) -> str:
    """IP сервера DNS из записи dns.*_servers («77.88.8.8», «77.88.8.8:5353»,
    «https://77.88.8.8/dns-query»); пусто — записан именем."""
    address = _dns_server(entry)[0]
    if "://" in address:
        address = urlsplit(address).hostname or ""
    try:
        ipaddress.ip_address(address)
    except ValueError:
        return ""
    return address


# Отпечаток ClientHello (uTLS) для TLS-серверов Xray, у которых его нет в ссылке (аудит
# противодействия ТСПУ 05.11.2026, P0): без него Xray подключается стеком Go, и JA3/JA4 не
# похож ни на один браузер. chrome — как у sing-box (parsers/convert.DEFAULT_FINGERPRINT) и у
# большинства клиентов. Отпечаток из ссылки главнее; он постоянен для сервера, не меняется
# от соединения к соединению. REALITY задаёт отпечаток сам; XHTTP по HTTP/3 — QUIC.
DEFAULT_TLS_FINGERPRINT = "chrome"


def _default_fingerprint(stream: dict, network: str | None = None) -> None:
    if str(stream.get("security") or "").lower() != "tls":
        return
    if fragmenting.xhttp_h3(stream, network):
        return
    tls = stream.get("tlsSettings")
    tls = dict(tls) if isinstance(tls, dict) else {}
    if str(tls.get("fingerprint") or "").strip():
        return
    tls["fingerprint"] = DEFAULT_TLS_FINGERPRINT
    stream["tlsSettings"] = tls


def _modernize(outbound: dict) -> None:
    """Записывает outbound так, как этого ждёт Xray 26.3.27.

    Имя хоста транспортов WebSocket и HTTPUpgrade — отдельное поле `host`. Прежняя
    запись `headers.Host` (она приходит из JSON-подписок: их streamSettings переносятся
    как есть) у WebSocket объявлена устаревшей — Xray пишет в журнал «"host" in
    "headers" is deprecated, will be removed soon», — а у HTTPUpgrade уже отклоняется
    («"headers" can't contain "host"»), и сервер выпадал из конфига. Проверено на
    Xray 26.3.27. Явно заданный `host` не трогаем — он главнее.

    Поле `tlsSettings.allowInsecure` Xray 26.10.10 убрал и конфиг с ним не принимает
    (проверено): из JSON-подписки оно не переносится — сервер проверяется по
    сертификату, а не выпадает из конфига.
    """
    stream = outbound.get("streamSettings")
    if not isinstance(stream, dict):
        return
    tls = stream.get("tlsSettings")
    # allowInsecure Xray не принимает, xgwSingboxPin — поле XGW для sing-box (parsers/common.py).
    if isinstance(tls, dict) and ("allowInsecure" in tls or "xgwSingboxPin" in tls):
        dropped = ("allowInsecure", "xgwSingboxPin")
        stream["tlsSettings"] = {key: value for key, value in tls.items() if key not in dropped}
    _default_fingerprint(stream)
    for leg in fragmenting.download_legs(stream):
        _default_fingerprint(leg, "xhttp")
    for key in ("wsSettings", "httpupgradeSettings"):
        settings = stream.get(key)
        headers = settings.get("headers") if isinstance(settings, dict) else None
        if not isinstance(headers, dict):
            continue
        names = [name for name in headers if isinstance(name, str) and name.lower() == "host"]
        if not names:
            continue
        rest = {name: value for name, value in headers.items() if name not in names}
        value = headers[names[0]]
        if isinstance(value, list):  # так записывают заголовки у tcp/http-обфускации
            value = value[0] if value else ""
        updated = {k: v for k, v in settings.items() if k != "headers"}
        if isinstance(value, str) and value and not updated.get("host"):
            updated["host"] = value
        if rest:
            updated["headers"] = rest
        stream[key] = updated


def _apply_sockopt(outbound: dict, mark: int) -> None:
    stream = outbound.setdefault("streamSettings", {})
    for leg in [stream, *fragmenting.download_legs(stream)]:
        if leg is not stream and fragmenting.loopback_address(leg.get("address")):
            continue  # мост к своему 127.0.0.1 метку не получает (loopback_guard)
        current = leg.get("sockopt")
        sockopt = dict(current) if isinstance(current, dict) else {}
        sockopt["mark"] = mark
        sockopt["domainStrategy"] = "UseIPv4"
        leg["sockopt"] = sockopt


def _media_tags(
    media: MediaPlan, nodes: Sequence[NodeInfo], outbounds: Sequence[Mapping],
) -> list[str]:
    """Теги плана, которые в этой сборке есть среди участников. selector у Xray — начало тега
    (проверено на 26.10.21: proxy-de-aaaa выбирает и proxy-de-aaaa11), поэтому тег, который
    начинает другой, не берётся: в группу попал бы посторонний сервер."""
    return _usable_media(media.outbound_tags, {info.tag for info in nodes if info.role == "proxy"},
                         {str(item.get("tag")) for item in outbounds})


def _usable_media(tags: Sequence[str], members: set[str], every: set[str]) -> list[str]:
    return [tag for tag in tags if tag in members
            and not any(other != tag and other.startswith(tag) for other in every)]


def _media_rule(domains: Sequence[str]) -> dict:
    return {"type": "field", "domain": list(domains), "balancerTag": YOUTUBE_BALANCER}


def _media_balancer(tags: list[str]) -> dict:
    return {"tag": YOUTUBE_BALANCER, "selector": tags, "strategy": {"type": "leastPing"},
            "fallbackTag": tags[0]}


def with_media(
    config: Mapping, media: MediaPlan, proxy_domains: Sequence[str],
) -> dict | None:
    """Рабочий конфиг с другим правилом видео (п. 350): меняется только routing, результат —
    как у полной сборки с этим планом. None — общего правила в конце нет, вставить некуда."""
    result = copy.deepcopy(dict(config))
    routing = result.get("routing")
    if not isinstance(routing, dict):
        return None
    rules = [rule for rule in routing.get("rules") or []
             if rule.get("balancerTag") != YOUTUBE_BALANCER]
    balancers = [item for item in routing.get("balancers") or []
                 if item.get("tag") != YOUTUBE_BALANCER]
    every = {str(item.get("tag")) for item in result.get("outbounds") or []}
    tags = _usable_media(media.outbound_tags, {tag for tag in every if tag.startswith("proxy-")},
                         every)
    if tags:
        if not rules or rules[-1].get("network") != "tcp,udp":
            return None
        at = len(rules) - 1
        if proxy_domains and at > 0 and rules[at - 1].get("domain") == list(proxy_domains):
            at -= 1
        rules.insert(at, _media_rule(media.domains))
        balancers.append(_media_balancer(tags))
    routing["rules"], routing["balancers"] = rules, balancers
    return result


def build(
    cfg: Config,
    selection: Selection,
    *,
    hosts: Mapping[str, Sequence[str]],
    probe_password: str | None = None,
    probe_ports: Mapping[str, int] | None = None,
    ipv6: bool | None = None,
    probe_url: str | None = None,
    containers_tun: bool = False,
    fragment: Collection[str] = (),
    profile_of: Mapping[str, str] | None = None,
    bridge: singboxing.Plan | None = None,
    devices_down: Collection[str] = (),
    avoid_ports: Collection[int] = (),
    api_listen: str = API_SOCKET,
    pool: Sequence[ServerNode] = (),
    pool_devices: Sequence[str] = (),
    pool_all: bool = False,
    media: MediaPlan | None = None,
) -> BuildResult:
    """probe_password и probe_ports — из probe_state(применённый конфиг).

    devices_down — адреса устройств, чей свой сервер (Ф4) сейчас не отвечает: их правила в
    конфиг не попадают, и устройство идёт через основной (device_routes).

    avoid_ports — порты, которых не занимать проверкам Xray (входы новой сборки sing-box,
    если её перезапуск отложен); входы bridge обходятся и так.

    api_listen — где слушает API Xray: путь сокета (API_SOCKET) или «адрес:порт».

    pool — допущенные серверы бесплатного пула (freepool/traffic.py), pool_devices — адреса
    устройств, которые идут через них (веха М2б.1): балансировщик «pool», правило по адресу
    после прямых доменов; pool пуст — правило в «block» (закрыто, R05).

    pool_all — весь дом через пул (free_pool.mode = on, веха М2б.2): весь трафик перехвата и
    запросы DNS самого Xray — в «pool» (пуст — в block, кроме прямых доменов и адресов), а
    «auto» из серверов подписки — только входам демона http-in и socks-in: несущий канал для
    списков пула, подписок и обновлений. Свои серверы устройств (Ф4) тогда не действуют.

    media — выход для видео (п. 348): балансировщик и правило по доменам, только если его
    серверы — участники этой сборки. Нет таких — правила нет, видео идёт общим маршрутом.

    fragment — отпечатки серверов, чьё соединение идёт через дробление ClientHello
    (fragment.py; при fragment.mode = "always" — все, кому оно подходит, при "off" — никто).

    profile_of — профиль каждого сервера (profiles.py; отпечаток → профиль), уже выбранный
    engine.assemble; у серверов, которых в нём нет, профиль — по fragment и настройкам.
    bridge — желаемое состояние sing-box (singbox.Plan): порты и пароль мостов для серверов,
    которых ведёт он.

    probe_url — адрес проб ядра (burstObservatory), если не probe.url: пока probe.url не
    отвечает, ядро пробует серверы по запасному адресу (watch/target.py).

    containers_tun — нужен inbound TUN для контейнеров Docker (engine.containers_tun):
    их трафик идёт в TUN-интерфейс при любом способе перехвата самой машины.

    ipv6 — открыть TPROXY-inbound для IPv6 самой машины; по умолчанию — если так
    настроено (network.ipv6 = proxy, capture.local) и IPv6 в ядре работает."""
    if ipv6 is None:
        ipv6 = cfg.network.ipv6_proxy and sysctl.ipv6_usable()
    ipv6 = ipv6 and cfg.capture.local
    if not selection.members:
        raise BuildError("нет участников балансировщика: подписка пуста или всё отфильтровано")
    password = probe_password or secrets.token_urlsafe(24)

    ordered = list(selection.members) + list(selection.spares)
    taken = {node.fingerprint for node in ordered}
    pooled = [node for node in pool if node.fingerprint not in taken]
    suffixes = assign_suffixes([*ordered, *pooled])
    ports = _allocate_ports(
        [f"probe-{suffixes[node.fingerprint]}" for node in [*ordered, *pooled]],
        probe_ports or {}, cfg,
        avoid={*avoid_ports, *(bridge.ports.values() if bridge is not None else ())},
    )

    nodes: list[NodeInfo] = []
    for index, node in enumerate(ordered):
        role = "proxy" if index < len(selection.members) else "spare"
        suffix = suffixes[node.fingerprint]
        nodes.append(
            NodeInfo(
                fingerprint=node.fingerprint,
                tag=f"{role}-{suffix}",
                probe_tag=f"probe-{suffix}",
                probe_port=ports[f"probe-{suffix}"],
                role=role,
            )
        )

    pool_infos = [
        NodeInfo(
            fingerprint=node.fingerprint,
            tag=f"{POOL_PREFIX}{suffixes[node.fingerprint]}",
            probe_tag=f"probe-{suffixes[node.fingerprint]}",
            probe_port=ports[f"probe-{suffixes[node.fingerprint]}"],
            role="pool",
        )
        for node in pooled
    ]
    every = [*nodes, *pool_infos]

    outbounds: list[dict] = []
    mode = cfg.fragment.mode
    for info, node in zip(every, [*ordered, *pooled], strict=True):
        profile = (profile_of or {}).get(node.fingerprint)
        if profile is None:
            wanted = mode == "always" or (mode != "off" and node.fingerprint in fragment)
            profile = profiling.XRAY_FRAGMENT if wanted else profiling.XRAY_DEFAULT
        letter = profiling.LETTERS.get(profile, "")
        if letter:
            port = bridge.ports.get((node.fingerprint, letter)) if bridge is not None else None
            if port is not None:
                outbound = singboxing.bridge_outbound(port, letter, bridge.password)  # type: ignore[union-attr]
                outbound["tag"] = info.tag
                info.profile = profile
                outbounds.append(outbound)
                continue
            if not node.outbound:
                raise BuildError(f"для «{node.name}» нет входа sing-box — сервер ведёт только он")
            profile = profiling.XRAY_DEFAULT
        if not node.outbound:
            raise BuildError(f"«{node.name}» умеет только sing-box, а профиль {profile} — Xray")
        outbound = copy.deepcopy(node.outbound)
        outbound["tag"] = info.tag
        _modernize(outbound)
        _apply_sockopt(outbound, cfg.capture.mark_bypass)
        if profile == profiling.XRAY_FRAGMENT and fragmenting.eligible(outbound):
            fragmenting.enable(outbound)
            info.fragment = True
            info.profile = profiling.XRAY_FRAGMENT
        elif profile == profiling.XRAY_SPLIT and fragmenting.eligible(outbound):
            fragmenting.enable(outbound, fragmenting.SPLIT_TAG)
            info.profile = profiling.XRAY_SPLIT
        elif profile in profiling.NFQ_PROFILES and fragmenting.dialer(outbound) in (
            "", fragmenting.TAG, fragmenting.SPLIT_TAG
        ):
            fragmenting.enable(outbound, profiling.nfq_tag(profile))
            info.profile = profile
        outbounds.append(outbound)
    for node in selection.chains:
        outbound = copy.deepcopy(node.outbound)
        outbound["tag"] = node.keep_tag
        _modernize(outbound)
        _apply_sockopt(outbound, cfg.capture.mark_bypass)
        outbounds.append(outbound)
    if any(info.fragment for info in every):
        outbounds.append(fragmenting.outbound(cfg))
    if any(info.profile == profiling.XRAY_SPLIT for info in every):
        outbounds.append(fragmenting.split_outbound(cfg))
    for profile in profiling.NFQ_PROFILES:
        if any(info.profile == profile for info in every):
            outbounds.append(fragmenting.nfq_outbound(cfg, profiling.nfq_tag(profile)))
    if cfg.network.effective_quic_mode == "noise":
        outbounds.append(fragmenting.noise_outbound(cfg))
    outbounds.extend(
        [
            {
                "tag": "direct",
                "protocol": "freedom",
                "settings": {"domainStrategy": "UseIP" if ipv6 else "UseIPv4"},
                "streamSettings": {"sockopt": {"mark": cfg.capture.mark_bypass}},
            },
            {"tag": "block", "protocol": "blackhole"},
            {
                "tag": "dns-out",
                "protocol": "dns",
                "streamSettings": {"sockopt": {"mark": cfg.capture.mark_bypass}},
            },
        ]
    )

    probe_inbounds = [
        {
            "tag": info.probe_tag,
            "protocol": "http",
            "listen": "127.0.0.1",
            "port": info.probe_port,
            "settings": {"accounts": [{"user": PROBE_USER, "pass": password}]},
        }
        for info in every
    ]
    # Перехват выключен целиком (capture.lan = capture.local = false) — XGW только
    # управляет Xray: TPROXY-inbound не нужен, а без root он и не откроется.
    capture = cfg.capture.lan or cfg.capture.local
    # TUN (capture.method = "tun") — только для трафика самой машины, сеть LAN остаётся на
    # TPROXY; IPv6 машины тогда идёт через тот же TUN, и отдельный inbound на ::1 не нужен.
    tun_local = cfg.capture.tun and cfg.capture.local
    tun = tun_local or containers_tun
    tproxy_tags = []
    if cfg.capture.lan or (cfg.capture.local and not tun_local):
        tproxy_tags.append("tproxy-in")
    if ipv6 and not tun_local:
        tproxy_tags.append("tproxy-in6")
    capture_tags = [*tproxy_tags, *(["tun-in"] if tun else [])]
    sniffing = {"enabled": True, "destOverride": ["http", "tls", "quic"]}
    inbounds: list[dict] = []
    if capture:
        if tun:
            inbounds.append(
                {
                    "tag": "tun-in",
                    "protocol": "tun",
                    # Интерфейс создаёт XGW (постоянный), Xray подключается к нему по имени.
                    "settings": {"name": cfg.capture.tun_name, "mtu": tun_mtu},
                    "sniffing": sniffing,
                }
            )
        for tag, listen in (("tproxy-in", "127.0.0.1"), ("tproxy-in6", "::1")):
            if tag not in tproxy_tags:
                continue
            inbounds.append(
                {
                    "tag": tag,
                    "protocol": "tunnel",
                    "listen": listen,
                    "port": cfg.capture.tproxy_port,
                    # UDP включает поле network: Xray 26.3.27 поля allowedNetwork не
                    # знает и молча его игнорирует — без network перехватывался бы
                    # только TCP. allowedNetwork оставлено для версий, где поле
                    # переименовано.
                    "settings": {
                        "network": "tcp,udp",
                        "allowedNetwork": "tcp,udp",
                        "followRedirect": True,
                    },
                    "streamSettings": {"sockopt": {"tproxy": "tproxy"}},
                    "sniffing": sniffing,
                }
            )
    inbounds.extend(
        [
            {
                "tag": "socks-in",
                "protocol": "socks",
                "listen": "127.0.0.1",
                "port": cfg.xray.socks_port,
                "settings": {"udp": True},
            },
            {
                "tag": "http-in",
                "protocol": "http",
                "listen": "127.0.0.1",
                "port": cfg.xray.http_port,
            },
            *probe_inbounds,
        ]
    )

    direct_dns = [_dns_server(server) for server in cfg.dns.direct_servers]
    rules: list[dict] = [
        {"type": "field", "inboundTag": [info.probe_tag], "outboundTag": info.tag}
        for info in every
    ]
    if capture:
        rules.append(
            {"type": "field", "inboundTag": capture_tags, "port": "53", "outboundTag": "dns-out"}
        )
    # Запросы к прямым серверам DNS (и DoH к ним) — выходом direct, мимо VPN.
    direct_ips = [ip for ip in map(dns_server_ip, cfg.dns.direct_servers) if ip]
    if direct_ips:
        rules.append({"type": "field", "ip": direct_ips, "outboundTag": "direct"})
    rules.append({"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"})
    # Адреса Tailscale Funnel (*.ts.net) — напрямую: через VPN-сервер Funnel не открывается
    # (испытания А1 и А3), а телефон в домашнем Wi-Fi ходит к API приложения на самом шлюзе
    # именно по публичному адресу Funnel (ASSUMPTIONS п. 229).
    rules.append({"type": "field", "domain": [TS_NET], "outboundTag": "direct"})
    if cfg.routing.direct_domains:
        rules.append(
            {
                "type": "field",
                "domain": list(cfg.routing.direct_domains),
                "outboundTag": "direct",
            }
        )
    if cfg.routing.direct_ips:
        rules.append({"type": "field", "ip": list(cfg.routing.direct_ips), "outboundTag": "direct"})
    # Свой сервер устройства — после DNS, частных сетей и direct_*: российские сайты у
    # устройства по-прежнему напрямую. TPROXY сохраняет адрес источника. Весь дом через пул —
    # свои серверы из подписки не действуют.
    if not pool_all:
        rules.extend(
            {"type": "field", "source": [ip], "outboundTag": tag}
            for ip, tag in device_routes(cfg, nodes, devices_down)
        )
    # Серверов пула нет — закрыто: через подписку трафик пула не идёт (R05, решение заказчика
    # 29.10.2026).
    to_pool = {"balancerTag": POOL_BALANCER} if pool_infos else {"outboundTag": "block"}
    # Устройства через бесплатный пул (М2б.1) — тоже после прямых доменов.
    if pool_devices and not pool_all:
        rules.append({"type": "field", "source": list(pool_devices), **to_pool})
    if pool_all:
        # Несущий канал (М2б.2): серверы подписки — только входам демона и Tailscale. Через
        # бесплатные серверы tailscaled (tailscale.route = "vpn" или DERP напрямую не отвечает —
        # тогда он идёт через Xray) терял управление и DERP, а с ними удалённый доступ к шлюзу —
        # до перезагрузки (отчёт m2b2fix, дефект 1). Имена — по сниффингу (TLS, HTTP).
        rules.append({"type": "field", "inboundTag": ["http-in", "socks-in"],
                      "balancerTag": BALANCER_TAG})
        rules.append({"type": "field", "domain": list(TS_CONTROL), "balancerTag": BALANCER_TAG})
    rest = to_pool if pool_all else {"balancerTag": BALANCER_TAG}
    if cfg.routing.cloudflare_tcp_ports:
        rules.append({
            "type": "field", "network": "tcp",
            "port": ",".join(cfg.routing.cloudflare_tcp_ports), **rest,
        })
    if cfg.network.effective_quic_mode == "noise":
        udp_ports = ["443", *cfg.routing.discord_udp_ports, *nfqws2.stun_ports(cfg)]
        rules.append({
            "type": "field", "network": "udp", "port": ",".join(dict.fromkeys(udp_ports)),
            "outboundTag": "direct-noise",
        })
    media_tags = [] if pool_all or media is None else _media_tags(media, nodes, outbounds)
    if media_tags:
        # После прямых адресов и правил устройств: они главнее выхода для видео.
        rules.append(_media_rule(media.domains))  # type: ignore[union-attr]
    if cfg.routing.proxy_domains:
        rules.append({"type": "field", "domain": list(cfg.routing.proxy_domains), **rest})
    rules.append({"type": "field", "network": "tcp,udp", **rest})

    # Резервный выход — дешёвый лимитированный запасной: через него трафик идёт, только
    # когда observatory считает мёртвыми всех участников. В subjectSelector он не входит,
    # поэтому ядро его не пробует. Нет резервного — первый участник.
    fallback_tag = nodes[0].tag
    if selection.reserve is not None:
        fallback_tag = next(
            info.tag for info in nodes if info.fingerprint == selection.reserve.fingerprint
        )
    dns_servers: list[object] = []
    # Весь дом через пул: имена Tailscale — прямыми серверами DNS, как прямые домены, а не через
    # бесплатные серверы: без них tailscaled не находит управление и DERP (отчёт m2b2fix).
    direct_names = [*cfg.routing.direct_domains, *(TS_CONTROL if pool_all else ())]
    if direct_names:
        for address, port in direct_dns:
            entry: dict = {
                "address": address,
                "domains": direct_names,
                "skipFallback": True,
            }
            if port is not None:
                entry["port"] = port
            dns_servers.append(entry)
    for address, port in map(_dns_server, cfg.dns.proxy_servers):
        if pool_all and "://" not in address:
            # Весь дом через пул (М2б.2): DNS — по TCP («tcp://», DNS-over-TCP через маршрутизацию
            # Xray, app/dns/nameserver.go). Проверки пула меряют только TCP, а бесплатный сервер
            # может не пропускать UDP — у всего дома тогда не разрешались бы имена.
            address = f"tcp://{address}"
        dns_servers.append(address if port is None else {"address": address, "port": port})

    query_strategy = cfg.dns.query_strategy
    if query_strategy == "auto":
        query_strategy = "PreferIPv4" if ipv6 else "UseIPv4"
    config = {
        "log": {"loglevel": "warning"},
        "api": {
            "tag": "api",
            "listen": api_listen,
            "services": ["HandlerService", "RoutingService", "StatsService"],
        },
        "metrics": {"tag": "metrics", "listen": f"127.0.0.1:{cfg.xray.metrics_port}"},
        "stats": {},
        "policy": {
            "levels": {"0": {"connIdle": cfg.routing.conn_idle_s}},
            "system": {"statsOutboundUplink": True, "statsOutboundDownlink": True},
        },
        "dns": {
            "hosts": {host: list(ips) for host, ips in sorted(hosts.items())},
            "servers": dns_servers,
            # auto: AAAA предпочитается только при проксировании IPv6; явная стратегия
            # позволяет выбрать UseIPv4, PreferIPv4 или AsIs независимо от перехвата.
            "queryStrategy": query_strategy,
        },
        "inbounds": inbounds,
        "outbounds": outbounds,
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": rules,
            "balancers": [
                {
                    "tag": BALANCER_TAG,
                    "selector": ["proxy-"],
                    "strategy": {"type": "leastPing"},
                    "fallbackTag": fallback_tag,
                },
                *([{
                    "tag": POOL_BALANCER,
                    "selector": [POOL_PREFIX],
                    "strategy": {"type": "leastPing"},
                    "fallbackTag": "block",
                }] if pool_infos else []),
                # Отдельный балансировщик, чтобы не трогать burstObservatory (его смена — это
                # перезапуск Xray): пробы участников уже идут. Стратегия при одном сервере не
                # влияет на выбор, а fallbackTag держит правило, пока проба не ответила.
                *([_media_balancer(media_tags)] if media_tags else []),
            ],
        },
        "burstObservatory": {
            # Пробы ядра для пула — по наличию устройств через него (или всего дома), а не
            # серверов: секция burstObservatory меняется только перезапуском Xray, и пропадание
            # серверов пула не должно рвать соединения всего дома.
            "subjectSelector": ["proxy-", *([POOL_PREFIX] if pool_devices or pool_all else [])],
            "pingConfig": {
                "destination": probe_url or cfg.probe.url,
                "connectivity": "",
                "interval": cfg.probe.interval,
                "sampling": cfg.probe.sampling,
                "timeout": cfg.probe.timeout,
                "httpMethod": "GET",
            },
        },
    }
    if cfg.zapret2.mode == "selective":
        config = zapret2.patch(config, cfg)
    return BuildResult(
        config=config,
        nodes=nodes,
        chain_tags=[node.keep_tag or "" for node in selection.chains],
        fallback_tag=fallback_tag,
        pool=pool_infos,
    )
