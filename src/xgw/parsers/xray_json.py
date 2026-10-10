"""JSON-подписки: полные конфиги Xray (объект или массив).

proxy-outbounds берутся с streamSettings и mux без изменений;
freedom/blackhole/dns/loopback отбрасываются. Цепочки sockopt.dialerProxy
переносятся целиком, включая freedom-звено с fragment/noises.

Звенья цепочек получают собственные теги chain-<хеш содержимого>, а ссылки
dialerProxy переписываются на них. Исходные теги сохранять нельзя: у разных
конфигов подписки они совпадают при разном содержимом, а тег вида «proxy-…»
попал бы под селектор балансировщика, и трафик пошёл бы через промежуточный узел.
"""

from __future__ import annotations

import copy
import hashlib
import json

from .common import ParseError, RawServer

DROP_PROTOCOLS = {"freedom", "blackhole", "dns", "loopback"}
# freedom в роли звена цепочки допустим (fragment/noises); остальные служебные — нет.
_CHAIN_FORBIDDEN = DROP_PROTOCOLS - {"freedom"}
CHAIN_PREFIX = "chain-"


def looks_like_singbox(outbounds: list) -> bool:
    """У sing-box outbounds описываются полем type вместо protocol."""
    return any(
        isinstance(item, dict) and "type" in item and "protocol" not in item
        for item in outbounds
    )


def parse_outbounds(
    outbounds: list, source: str, remarks: str = ""
) -> tuple[list[RawServer], list[str]]:
    """Серверы одного конфига Xray. remarks — имя конфига в подписке: у таких
    подписок основной outbound обычно зовётся просто «proxy»."""
    if looks_like_singbox(outbounds):
        raise ParseError(f"{source}: формат sing-box не поддерживается")
    warnings: list[str] = []
    items = [item for item in outbounds if isinstance(item, dict)]
    by_tag = {str(item["tag"]): item for item in items if item.get("tag")}
    dialer_targets = {tag for tag in map(_dialer_tag, items) if tag}

    chains: dict[str, RawServer] = {}  # новый тег → звено
    resolved: dict[str, str | None] = {}  # исходный тег → новый тег (None — недоступно)

    def resolve_chain(tag: str, trail: tuple[str, ...]) -> str | None:
        if tag in resolved:
            return resolved[tag]
        item = by_tag.get(tag)
        new_tag: str | None = None
        if item is None:
            warnings.append(f"{source}: dialerProxy «{tag}» не найден в подписке")
        elif tag in trail:
            warnings.append(f"{source}: цепочка dialerProxy зациклена на «{tag}»")
        elif str(item.get("protocol") or "") in _CHAIN_FORBIDDEN or not item.get("protocol"):
            warnings.append(f"{source}: звено «{tag}» — служебный outbound, цепочка недоступна")
        else:
            outbound = _strip_tag(item)
            nested = _dialer_tag(item)
            nested_tag = resolve_chain(nested, (*trail, tag)) if nested else None
            if nested and nested_tag is None:
                warnings.append(f"{source}: звено «{tag}» отброшено вместе с цепочкой")
            else:
                if nested_tag:
                    outbound["streamSettings"]["sockopt"]["dialerProxy"] = nested_tag
                new_tag = CHAIN_PREFIX + _content_hash(outbound)
                address, port, credential = _endpoint(item)
                chains.setdefault(
                    new_tag,
                    RawServer(
                        name=tag,
                        protocol=str(item.get("protocol") or ""),
                        address=address,
                        port=port,
                        credential=credential,
                        transport="chain",
                        outbound=outbound,
                        keep_tag=new_tag,
                    ),
                )
        resolved[tag] = new_tag
        return new_tag

    mains: list[tuple[str, RawServer]] = []
    for item in items:
        protocol = str(item.get("protocol") or "")
        tag = str(item.get("tag") or "")
        if protocol in DROP_PROTOCOLS or not protocol:
            continue
        if tag and tag in dialer_targets:
            continue  # звено цепочки: переносится вместе с тем, кто на него ссылается
        if protocol == "hysteria2":
            warnings.append(f"{source}: outbound «{tag}» пропущен (hysteria2 не подтверждён)")
            continue
        address, port, credential = _endpoint(item)
        if not address or not port:
            warnings.append(f"{source}: outbound «{tag}» без адреса/порта пропущен")
            continue
        stream = item.get("streamSettings")
        if not isinstance(stream, dict):
            stream = {}
        transport = f"{stream.get('network', 'tcp')}/{stream.get('security', 'none')}"
        outbound = _strip_tag(item)
        dialer = _dialer_tag(item)
        if dialer:
            chain_tag = resolve_chain(dialer, (tag,))
            if chain_tag is None:
                warnings.append(f"{source}: outbound «{tag}» пропущен: его цепочка недоступна")
                continue
            outbound["streamSettings"]["sockopt"]["dialerProxy"] = chain_tag
            transport += f"+{chain_tag}"
        mains.append(
            (
                tag,
                RawServer(
                    name=tag or f"{address}:{port}",
                    protocol=protocol,
                    address=address,
                    port=port,
                    credential=credential,
                    transport=transport,
                    outbound=outbound,
                ),
            )
        )

    if remarks:
        for tag, server in mains:
            server.name = remarks if len(mains) == 1 else f"{remarks} {tag}".strip()

    used = _reachable_chains([server for _tag, server in mains], chains)
    return [server for _tag, server in mains] + used, warnings


def _reachable_chains(mains: list[RawServer], chains: dict[str, RawServer]) -> list[RawServer]:
    """Звенья, на которые действительно ссылаются оставленные узлы (с вложенными)."""
    result: list[RawServer] = []
    seen: set[str] = set()
    queue = [tag for tag in (_dialer_tag(server.outbound) for server in mains) if tag]
    while queue:
        tag = queue.pop(0)
        if tag in seen or tag not in chains:
            continue
        seen.add(tag)
        result.append(chains[tag])
        nested = _dialer_tag(chains[tag].outbound)
        if nested:
            queue.append(nested)
    return result


def _strip_tag(item: dict) -> dict:
    return copy.deepcopy({key: value for key, value in item.items() if key != "tag"})


def _content_hash(outbound: dict) -> str:
    canonical = json.dumps(outbound, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]


def _dialer_tag(item: dict) -> str | None:
    stream = item.get("streamSettings")
    sockopt = stream.get("sockopt") if isinstance(stream, dict) else None
    tag = sockopt.get("dialerProxy") if isinstance(sockopt, dict) else None
    return str(tag) if tag else None


def _endpoint(item: dict) -> tuple[str, int, str]:
    """Адрес, порт и учётные данные: классический vnext/servers либо плоская
    запись settings.address/port (её принимают новые версии Xray)."""
    settings = item.get("settings")
    if not isinstance(settings, dict):
        return "", 0, ""
    entries = settings.get("vnext") or settings.get("servers") or []
    first = entries[0] if isinstance(entries, list) and entries else None
    if not isinstance(first, dict):
        first = settings if settings.get("address") else None
    if first is None:
        return "", 0, ""
    address = str(first.get("address") or "").lower()
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
        credential = str(first.get("id") or first.get("password") or first.get("user") or "")
    return address, port, credential
