"""Генератор конфига Xray: участники, запасные, probe-inbounds, правила,
балансировщик и burstObservatory с GET-пробами (скелет — раздел 6.6 ТЗ)."""

from __future__ import annotations

import copy
import ipaddress
import re
import secrets
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from ..config import Config
from ..model import ServerNode

PROBE_USER = "xgw"
BALANCER_TAG = "auto"
_TAG_RE = re.compile(r"^(proxy|spare|probe)-([a-z]{2})-([0-9a-f]{4,8})$")


class BuildError(Exception):
    pass


@dataclass
class NodeInfo:
    fingerprint: str
    tag: str
    probe_tag: str
    probe_port: int
    role: str  # proxy | spare


@dataclass
class Selection:
    members: list[ServerNode] = field(default_factory=list)
    spares: list[ServerNode] = field(default_factory=list)
    chains: list[ServerNode] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class BuildResult:
    config: dict
    nodes: list[NodeInfo]
    chain_tags: list[str]
    fallback_tag: str


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


def select_nodes(
    nodes: Sequence[ServerNode], cfg: Config, *, prefer: Sequence[str] = ()
) -> Selection:
    """Фильтры по имени, отбрасывание служебных адресов, дедупликация,
    канонический порядок (стабилен при любом порядке входных ссылок).

    prefer — отпечатки узлов, которым место в балансировщике в первую очередь
    (лучшие первыми): текущие участники и замены из ротации. Без этого
    обновление подписки перетасовывало бы участников по сортировке отпечатков,
    а результат замены «мёртвого» участника терялся бы при следующей сборке.
    """
    warnings: list[str] = []
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
        if is_junk(node.address, node.port):
            warnings.append(
                f"узел «{node.name}» отброшен: служебный адрес {node.address}:{node.port}"
            )
            continue
        if cfg.network.ipv6 == "off" and _is_ipv6(node.address):
            warnings.append(f"узел «{node.name}» отброшен: IPv6-адрес при network.ipv6 = off")
            continue
        if include_re is not None and not include_re.search(node.name):
            continue
        if exclude_re is not None and exclude_re.search(node.name):
            continue
        if node.fingerprint in unique:
            warnings.append(f"дубль «{node.name}» схлопнут с «{unique[node.fingerprint].name}»")
            continue
        unique[node.fingerprint] = node

    limit = max(1, cfg.filters.max_members)
    members: list[ServerNode] = []
    for fingerprint in prefer:
        node = unique.get(fingerprint)
        if node is not None and node not in members and len(members) < limit:
            members.append(node)
    chosen = {node.fingerprint for node in members}
    rest = sorted(
        (node for node in unique.values() if node.fingerprint not in chosen),
        key=lambda node: (node.fingerprint, node.name),
    )
    free = limit - len(members)
    members.extend(rest[:free])
    spares = rest[free:]

    # Звенья цепочек нужны, только пока на них ссылается хоть один оставленный узел.
    kept = [*members, *spares]
    chains = _referenced_chains(kept, chains)
    return Selection(members=members, spares=spares, chains=chains, warnings=warnings)


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


def _allocate_ports(
    probe_tags: Sequence[str], previous: Mapping[str, int], cfg: Config
) -> dict[str, int]:
    """Порт закрепляется за probe-тегом: существующие сохраняются, новые
    получают первый свободный, начиная с probe_port_base."""
    reserved = {
        cfg.capture.tproxy_port,
        cfg.xray.api_port,
        cfg.xray.metrics_port,
        cfg.xray.socks_port,
        cfg.xray.http_port,
    }
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


def _apply_sockopt(outbound: dict, mark: int) -> None:
    stream = outbound.setdefault("streamSettings", {})
    sockopt = dict(stream.get("sockopt") or {})
    sockopt["mark"] = mark
    sockopt["domainStrategy"] = "UseIPv4"
    stream["sockopt"] = sockopt


def build(
    cfg: Config,
    selection: Selection,
    *,
    hosts: Mapping[str, Sequence[str]],
    probe_password: str | None = None,
    probe_ports: Mapping[str, int] | None = None,
) -> BuildResult:
    """probe_password и probe_ports — из probe_state(применённый конфиг)."""
    if not selection.members:
        raise BuildError("нет участников балансировщика: подписка пуста или всё отфильтровано")
    password = probe_password or secrets.token_urlsafe(24)

    ordered = list(selection.members) + list(selection.spares)
    suffixes = assign_suffixes(ordered)
    ports = _allocate_ports(
        [f"probe-{suffixes[node.fingerprint]}" for node in ordered], probe_ports or {}, cfg
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

    outbounds: list[dict] = []
    for info, node in zip(nodes, ordered, strict=True):
        outbound = copy.deepcopy(node.outbound)
        outbound["tag"] = info.tag
        _apply_sockopt(outbound, cfg.capture.mark_bypass)
        outbounds.append(outbound)
    for node in selection.chains:
        outbound = copy.deepcopy(node.outbound)
        outbound["tag"] = node.keep_tag
        _apply_sockopt(outbound, cfg.capture.mark_bypass)
        outbounds.append(outbound)
    outbounds.extend(
        [
            {
                "tag": "direct",
                "protocol": "freedom",
                "settings": {"domainStrategy": "UseIPv4"},
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
        for info in nodes
    ]
    inbounds: list[dict] = [
        {
            "tag": "tproxy-in",
            "protocol": "tunnel",
            "listen": "127.0.0.1",
            "port": cfg.capture.tproxy_port,
            "settings": {"allowedNetwork": "tcp,udp", "followRedirect": True},
            "streamSettings": {"sockopt": {"tproxy": "tproxy"}},
            "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
        },
        {
            "tag": "socks-in",
            "protocol": "socks",
            "listen": "127.0.0.1",
            "port": cfg.xray.socks_port,
            "settings": {"udp": True},
        },
        {"tag": "http-in", "protocol": "http", "listen": "127.0.0.1", "port": cfg.xray.http_port},
        *probe_inbounds,
    ]

    rules: list[dict] = [
        {"type": "field", "inboundTag": [info.probe_tag], "outboundTag": info.tag}
        for info in nodes
    ]
    rules.append(
        {"type": "field", "inboundTag": ["tproxy-in"], "port": "53", "outboundTag": "dns-out"}
    )
    if cfg.dns.direct_servers:
        rules.append(
            {"type": "field", "ip": list(cfg.dns.direct_servers), "outboundTag": "direct"}
        )
    rules.append({"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"})
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
    if cfg.routing.proxy_domains:
        rules.append(
            {
                "type": "field",
                "domain": list(cfg.routing.proxy_domains),
                "balancerTag": BALANCER_TAG,
            }
        )
    rules.append({"type": "field", "network": "tcp,udp", "balancerTag": BALANCER_TAG})

    fallback_tag = nodes[0].tag
    dns_servers: list[object] = []
    if cfg.dns.direct_servers and cfg.routing.direct_domains:
        for server in cfg.dns.direct_servers:
            dns_servers.append(
                {
                    "address": server,
                    "domains": list(cfg.routing.direct_domains),
                    "skipFallback": True,
                }
            )
    dns_servers.extend(cfg.dns.proxy_servers)

    config = {
        "log": {"loglevel": "warning"},
        "api": {
            "tag": "api",
            "listen": f"127.0.0.1:{cfg.xray.api_port}",
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
            "queryStrategy": "UseIPv4",
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
                }
            ],
        },
        "burstObservatory": {
            "subjectSelector": ["proxy-"],
            "pingConfig": {
                "destination": cfg.probe.url,
                "connectivity": "",
                "interval": cfg.probe.interval,
                "sampling": cfg.probe.sampling,
                "timeout": cfg.probe.timeout,
                "httpMethod": "GET",
            },
        },
    }
    return BuildResult(
        config=config,
        nodes=nodes,
        chain_tags=[node.keep_tag or "" for node in selection.chains],
        fallback_tag=fallback_tag,
    )
