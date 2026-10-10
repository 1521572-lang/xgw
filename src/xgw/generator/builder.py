"""Генератор конфига Xray: участники, запасные, probe-inbounds, правила,
балансировщик и burstObservatory с GET-пробами (скелет — раздел 6.6 ТЗ)."""

from __future__ import annotations

import copy
import ipaddress
import re
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from ..config import Config
from ..model import ServerNode

PROBE_USER = "xgw"


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
    if port <= 0:
        return True
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_unspecified or ip.is_loopback


def select_nodes(nodes: Sequence[ServerNode], cfg: Config) -> Selection:
    """Фильтры по имени, отбрасывание служебных адресов, дедупликация,
    канонический порядок (стабилен при любом порядке входных ссылок)."""
    warnings: list[str] = []
    include_re = re.compile(cfg.filters.include_regex) if cfg.filters.include_regex else None
    exclude_re = re.compile(cfg.filters.exclude_regex) if cfg.filters.exclude_regex else None

    chains: list[ServerNode] = []
    chain_tags: set[str] = set()
    unique: dict[str, ServerNode] = {}
    ordered: list[ServerNode] = []
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
        if include_re is not None and not include_re.search(node.name):
            continue
        if exclude_re is not None and exclude_re.search(node.name):
            continue
        if node.fingerprint in unique:
            warnings.append(f"дубль «{node.name}» схлопнут с «{unique[node.fingerprint].name}»")
            continue
        unique[node.fingerprint] = node
        ordered.append(node)
        warnings.extend(f"{node.name}: {warning}" for warning in node.warnings)

    ordered.sort(key=lambda node: (node.fingerprint, node.name))
    members = ordered[: cfg.filters.max_members]
    spares = ordered[cfg.filters.max_members :]
    return Selection(members=members, spares=spares, chains=chains, warnings=warnings)


def _unique_tag(role: str, node: ServerNode, taken: set[str]) -> str:
    for size in (4, 6, 8):
        tag = f"{role}-{node.country}-{node.fingerprint[:size]}"
        if tag not in taken:
            taken.add(tag)
            return tag
    raise BuildError(f"не удалось построить уникальный тег для узла «{node.name}»")


def _probe_tag(tag: str) -> str:
    return "probe-" + tag.split("-", 1)[1]


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
) -> BuildResult:
    if not selection.members:
        raise BuildError("нет участников балансировщика: подписка пуста или всё отфильтровано")
    password = probe_password or secrets.token_urlsafe(24)

    ordered = list(selection.members) + list(selection.spares)
    taken: set[str] = set()
    for node in selection.chains:
        if node.keep_tag:
            taken.add(node.keep_tag)

    nodes: list[NodeInfo] = []
    for index, node in enumerate(ordered):
        role = "proxy" if index < len(selection.members) else "spare"
        tag = _unique_tag(role, node, taken)
        nodes.append(
            NodeInfo(
                fingerprint=node.fingerprint,
                tag=tag,
                probe_tag=_probe_tag(tag),
                probe_port=cfg.xray.probe_port_base + index,
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
            {"type": "field", "domain": list(cfg.routing.proxy_domains), "balancerTag": "auto"}
        )
    rules.append({"type": "field", "network": "tcp,udp", "balancerTag": "auto"})

    fallback_tag = nodes[0].tag
    dns_servers: list[object] = []
    if cfg.dns.direct_servers:
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
            "hosts": {host: list(ips) for host, ips in hosts.items()},
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
                    "tag": "auto",
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
