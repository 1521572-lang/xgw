"""Страна адреса сервера из применённых конфигов, без DNS и запросов наружу."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .. import engine, geodat
from ..generator import singbox
from ..paths import Paths


def _country(index: geodat.Countries, addresses: list[str], hosts: dict) -> str:
    """Если у адреса несколько IP, все должны указывать на одну страну."""
    countries = set()
    for address in addresses:
        known = hosts.get(address.lower(), address)
        for ip in known if isinstance(known, list) else [known]:
            countries.add(index.lookup(ip) if isinstance(ip, str) else "")
    return countries.pop() if len(countries) == 1 else ""


def _xray_endpoints(outbound: dict) -> list[dict]:
    settings = outbound.get("settings") or {}
    entries = settings.get("vnext") or settings.get("servers")
    return entries if isinstance(entries, list) else [settings]


def _singbox_peers(
    config: dict, hosts: dict, index: geodat.Countries,
) -> dict[tuple[int, str], str]:
    by_tag = {item["tag"]: item for kind in ("outbounds", "endpoints")
              for item in config.get(kind) or [] if item.get("tag")}
    result = {}
    for (fingerprint, letter), port in singbox.bridge_ports(config).items():
        item = by_tag.get(singbox.tag_out(fingerprint, letter), {})
        if item.get("detour"):
            # У ShadowTLS адрес соединения в звене detour, а не у Shadowsocks.
            item = by_tag.get(item["detour"], {})
        addresses = ([peer.get("address", "") for peer in item.get("peers") or []]
                     if item.get("type") == "wireguard" else [item.get("server", "")])
        result[port, letter] = _country(index, addresses, hosts)
    return result


def _config(path: Path) -> dict:
    try:
        info = path.stat()
    except OSError:
        return {}
    return _read_config(path, (info.st_ino, info.st_mtime_ns, info.st_size))


@lru_cache(maxsize=4)
def _read_config(path: Path, _stamp: tuple[int, int, int]) -> dict:
    return engine.read_json(path) or {}


def applied_countries(paths: Paths, tags: set[str]) -> dict[str, str]:
    """Код страны по тегу, включая локальный мост sing-box и его удалённого партнёра."""
    if not tags or paths.api_dirty_file.exists():
        return {}
    path = geodat.ui_asset(paths.xray_dir)
    if not path.is_file():
        return {}
    xray = _config(paths.xray_config_file)
    if not xray:
        return {}
    index = geodat.countries(path)
    hosts = (xray.get("dns") or {}).get("hosts") or {}
    result = {}
    peers = None
    for outbound in xray.get("outbounds") or []:
        tag = outbound.get("tag")
        if tag not in tags:
            continue
        endpoints = _xray_endpoints(outbound)
        letter = singbox.bridge_variant(outbound)
        if letter:
            if peers is None:
                box = _config(paths.singbox_config_file)
                box_hosts = next((server.get("predefined") or {}
                                  for server in (box.get("dns") or {}).get("servers") or []
                                  if server.get("tag") == "hosts"), {})
                peers = _singbox_peers(box, box_hosts, index)
            result[tag] = peers.get((endpoints[0].get("port"), letter), "")
        else:
            result[tag] = _country(index, [item.get("address") or "" for item in endpoints], hosts)
    return result
