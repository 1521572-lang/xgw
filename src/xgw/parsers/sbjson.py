"""JSON-подписки в формате sing-box: конфиг (объект или массив) с outbounds/endpoints либо один
outbound.

Берутся прокси-серверы; служебные outbound'ы (direct, block, dns, selector, urltest…) отбрасываются.
Цепочка через `detour` переносится только для shadowtls (Shadowsocks поверх ShadowTLS): другие
цепочки XGW не строит, такой сервер пропускается с пояснением.

Из серверов убираются поля, которыми sing-box привязывается к машине автора конфига: метка
(`routing_mark`), интерфейс, адрес источника, `domain_resolver`. XGW задаёт свои. Проверка
сертификата не отключается: `tls.insecure` отбрасывается с предупреждением.

Сервер, который умеют оба ядра, получает и описание для Xray (parsers/convert.py): тогда он
участвует в обоих профилях, а отпечаток у него такой же, как у того же сервера из ссылки.
"""

from __future__ import annotations

import copy

from . import convert
from .common import ParseError, RawServer, SingboxSpec

SERVICE_TYPES = {"direct", "block", "dns", "selector", "urltest", "loadbalance", "fallback"}
PROXY_TYPES = {
    "vless", "vmess", "trojan", "shadowsocks", "socks", "hysteria2", "hysteria", "tuic", "anytls",
}
ENDPOINT_TYPES = {"wireguard"}
# Поля, которыми конфиг привязан к машине автора; XGW задаёт свои (generator/singbox.py).
STRIP = (
    "tag", "routing_mark", "bind_interface", "inet4_bind_address", "inet6_bind_address",
    "domain_resolver", "netns", "connect_timeout", "tcp_fast_open", "tcp_multi_path",
    "udp_fragment",
)
_TRANSPORT = {
    "vless": "sb/vless", "vmess": "sb/vmess", "trojan": "sb/trojan", "shadowsocks": "ss/plain",
    "socks": "tcp/none", "hysteria2": "udp/none", "hysteria": "udp/hysteria", "tuic": "udp/tls",
    "anytls": "tcp/tls", "wireguard": "udp/wg",
}


def is_singbox_item(item: object) -> bool:
    return isinstance(item, dict) and "type" in item and "protocol" not in item


def looks_like_singbox(config: dict) -> bool:
    outbounds = config.get("outbounds")
    if isinstance(outbounds, list) and any(is_singbox_item(item) for item in outbounds):
        return True
    endpoints = config.get("endpoints")
    return isinstance(endpoints, list) and any(is_singbox_item(item) for item in endpoints)


def parse_config(config: dict, source: str) -> tuple[list[RawServer], list[str]]:
    """Серверы одного конфига sing-box (или одного outbound'а, если это он)."""
    if "outbounds" not in config and "endpoints" not in config and is_singbox_item(config):
        config = {"outbounds": [config]}
    outbounds = config.get("outbounds")
    endpoints = config.get("endpoints")
    items = [
        item for item in (outbounds if isinstance(outbounds, list) else [])
        if isinstance(item, dict)
    ]
    items += [
        item for item in (endpoints if isinstance(endpoints, list) else [])
        if isinstance(item, dict)
    ]
    by_tag = {str(item["tag"]): item for item in items if item.get("tag")}
    warnings: list[str] = []
    servers: list[RawServer] = []
    for item in items:
        kind = str(item.get("type") or "")
        tag = str(item.get("tag") or "")
        if kind in SERVICE_TYPES or kind == "shadowtls":
            continue
        if kind not in PROXY_TYPES and kind not in ENDPOINT_TYPES:
            warnings.append(
                f"{source}: «{tag or kind}» пропущен (тип {kind or '?'} не поддерживается)"
            )
            continue
        try:
            servers.append(_server(item, by_tag, source, warnings))
        except ParseError as exc:
            warnings.append(f"{source}: «{tag or kind}» пропущен ({exc})")
    return servers, warnings


def _server(item: dict, by_tag: dict[str, dict], source: str, warnings: list[str]) -> RawServer:
    kind = str(item["type"])
    tag = str(item.get("tag") or "")
    body = copy.deepcopy({key: value for key, value in item.items() if key not in STRIP})
    extra: list[dict] = []
    detour = body.pop("detour", None) if kind != "shadowtls" else None
    if detour:
        target = by_tag.get(str(detour))
        if not target or str(target.get("type")) != "shadowtls" or target.get("detour"):
            raise ParseError("цепочка через detour (кроме shadowtls) не поддерживается")
        link = copy.deepcopy({key: value for key, value in target.items() if key not in STRIP})
        link["tag"] = "shadowtls"
        _drop_insecure(link, tag, warnings, source)
        extra.append(link)
        body["detour"] = "shadowtls"
    _drop_insecure(body, tag, warnings, source)
    endpoint = kind in ENDPOINT_TYPES
    if endpoint:
        peers = body.get("peers")
        peer = peers[0] if isinstance(peers, list) and peers and isinstance(peers[0], dict) else {}
        address, port = str(peer.get("address") or ""), peer.get("port")
        credential = str(body.get("private_key") or "")
    else:
        address, port = str(body.get("server") or ""), body.get("server_port")
        if (not port) and isinstance(body.get("server_ports"), list) and body["server_ports"]:
            port = int(str(body["server_ports"][0]).partition(":")[0])
        credential = str(
            body.get("uuid") or body.get("password") or body.get("username")
            or body.get("auth_str") or ""
        )
    if not extra and not address:
        raise ParseError("нет адреса")
    if extra:
        address, port = str(extra[0].get("server") or ""), extra[0].get("server_port")
    address = address.lower()
    if not isinstance(port, int) or not 0 < port < 65536:
        raise ParseError("нет порта")
    spec = SingboxSpec(main=body, endpoint=endpoint, extra=extra)
    outbound = convert.to_xray(spec)
    stream = outbound.get("streamSettings") if outbound else None
    if outbound and isinstance(stream, dict):
        security = str(stream.get("security") or "none")
        network = stream.get("network", "tcp")
        transport = "ss/plain" if kind == "shadowsocks" else f"{network}/{security}"
    else:
        transport = _TRANSPORT.get(kind, f"sb/{kind}")
    return RawServer(
        name=tag or f"{address}:{port}",
        protocol=kind if kind != "wireguard" else "wireguard",
        address=address,
        port=port,
        credential=credential,
        transport=transport,
        outbound=outbound or {},
        singbox=spec,
    )


def _drop_insecure(body: dict, tag: str, warnings: list[str], source: str) -> None:
    tls = body.get("tls")
    if isinstance(tls, dict) and tls.get("insecure"):
        tls.pop("insecure", None)
        warnings.append(
            f"{source}/{tag or body.get('type')}: tls.insecure не поддерживается — сертификат "
            "сервера проверяется"
        )
    elif isinstance(tls, dict):
        tls.pop("insecure", None)
