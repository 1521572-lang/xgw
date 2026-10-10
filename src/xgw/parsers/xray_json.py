"""JSON-подписки: полные конфиги Xray (объект или массив).

proxy-outbounds берутся с streamSettings и mux без изменений;
freedom/blackhole/dns/loopback отбрасываются; цепочки sockopt.dialerProxy
переносятся целиком — с исходными тегами, иначе ссылка dialerProxy порвётся.
"""

from __future__ import annotations

import copy

from .common import ParseError, RawServer

DROP_PROTOCOLS = {"freedom", "blackhole", "dns", "loopback"}


def looks_like_singbox(outbounds: list) -> bool:
    """У sing-box outbounds описываются полем type вместо protocol."""
    return any(
        isinstance(item, dict) and "type" in item and "protocol" not in item
        for item in outbounds
    )


def parse_outbounds(outbounds: list, source: str) -> tuple[list[RawServer], list[str]]:
    if looks_like_singbox(outbounds):
        raise ParseError(f"{source}: формат sing-box не поддерживается")
    warnings: list[str] = []
    servers: list[RawServer] = []
    by_tag = {
        item.get("tag"): item
        for item in outbounds
        if isinstance(item, dict) and item.get("tag")
    }
    # Outbound, на который ссылается чей-то dialerProxy, — часть цепочки:
    # он переносится один раз и с исходным тегом.
    dialer_tags = {
        tag for tag in (_dialer_tag(item) for item in outbounds if isinstance(item, dict)) if tag
    }

    chain_queue: list[str] = []
    for item in outbounds:
        if not isinstance(item, dict):
            continue
        protocol = str(item.get("protocol") or "")
        tag = str(item.get("tag") or "")
        if protocol in DROP_PROTOCOLS or not protocol:
            continue
        if tag and tag in dialer_tags:
            chain_queue.append(tag)
            continue
        if protocol == "hysteria2":
            warnings.append(f"{source}: outbound «{tag}» пропущен (hysteria2 не подтверждён)")
            continue
        address, port, credential = _endpoint(item)
        if not address or not port:
            warnings.append(f"{source}: outbound «{tag}» без адреса/порта пропущен")
            continue
        stream = item.get("streamSettings") or {}
        transport = f"{stream.get('network', 'tcp')}/{stream.get('security', 'none')}"
        outbound = copy.deepcopy({key: value for key, value in item.items() if key != "tag"})
        servers.append(
            RawServer(
                name=tag or f"{address}:{port}",
                protocol=protocol,
                address=address,
                port=port,
                credential=credential,
                transport=transport,
                outbound=outbound,
            )
        )
        dialer = _dialer_tag(item)
        if dialer:
            chain_queue.append(dialer)

    used: set[str] = set()
    while chain_queue:
        tag = chain_queue.pop(0)
        if tag in used:
            continue
        used.add(tag)
        item = by_tag.get(tag)
        if item is None:
            warnings.append(f"{source}: dialerProxy «{tag}» не найден в подписке")
            continue
        if str(item.get("protocol") or "") in DROP_PROTOCOLS:
            warnings.append(f"{source}: цепочка через «{tag}» отброшена (служебный протокол)")
            continue
        address, port, credential = _endpoint(item)
        outbound = copy.deepcopy({key: value for key, value in item.items() if key != "tag"})
        servers.append(
            RawServer(
                name=tag,
                protocol=str(item.get("protocol") or ""),
                address=address,
                port=port,
                credential=credential,
                transport="chain",
                outbound=outbound,
                keep_tag=tag,
            )
        )
        dialer = _dialer_tag(item)
        if dialer:
            chain_queue.append(dialer)
    return servers, warnings


def _dialer_tag(item: dict) -> str | None:
    sockopt = (item.get("streamSettings") or {}).get("sockopt") or {}
    tag = sockopt.get("dialerProxy")
    return str(tag) if tag else None


def _endpoint(item: dict) -> tuple[str, int, str]:
    settings = item.get("settings") or {}
    entries = settings.get("vnext") or settings.get("servers") or []
    if entries and isinstance(entries, list) and isinstance(entries[0], dict):
        first = entries[0]
        address = str(first.get("address") or "")
        try:
            port = int(first.get("port") or 0)
        except (TypeError, ValueError):
            port = 0
        credential = ""
        users = first.get("users")
        if isinstance(users, list) and users and isinstance(users[0], dict):
            credential = str(
                users[0].get("id") or users[0].get("password") or users[0].get("user") or ""
            )
        if not credential:
            credential = str(first.get("password") or "")
        return address, port, credential
    return "", 0, ""
