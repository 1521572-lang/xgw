"""ss:// — SIP002 (userinfo в base64) и старый формат (всё в base64).

Плагины simple-obfs/v2ray-plugin переносятся в plugin/pluginOpts.
"""

from __future__ import annotations

import binascii
from urllib.parse import parse_qs, unquote

from .common import ParseError, RawServer, b64_decode, single, split_host_port

_PLUGIN_MAP = {
    "simple-obfs": "obfs-local",
    "obfs-local": "obfs-local",
    "v2ray-plugin": "v2ray-plugin",
}


def parse(link: str) -> RawServer:
    rest = link[len("ss://") :]
    name = ""
    if "#" in rest:
        rest, _, fragment = rest.partition("#")
        name = unquote(fragment)
    query: dict[str, list[str]] = {}
    if "?" in rest:
        rest, _, query_string = rest.partition("?")
        query = parse_qs(query_string, keep_blank_values=True)

    try:
        if "@" in rest:
            userinfo, _, hostport = rest.rpartition("@")
            hostport = hostport.split("/", 1)[0]  # SIP002 допускает путь после порта
            method, password = _decode_userinfo(userinfo)
            host, port = split_host_port(hostport)
        else:
            decoded = b64_decode(rest).decode("utf-8")
            userinfo, _, hostport = decoded.rpartition("@")
            hostport = hostport.split("/", 1)[0]
            method, password = _decode_userinfo_plain(userinfo)
            host, port = split_host_port(hostport)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ParseError(f"ss: не удалось разобрать ссылку ({exc.__class__.__name__})") from exc

    if not method or not password:
        raise ParseError("ss: нет метода или пароля")
    if not name:
        name = f"{host}:{port}"

    server: dict = {
        "address": host,
        "port": port,
        "method": method,
        "password": password,
    }
    warnings: list[str] = []
    plugin = single(query, "plugin")
    transport_extra = "plain"
    if plugin:
        parts = plugin.split(";")
        base = _PLUGIN_MAP.get(parts[0].strip().lower())
        if base is None:
            warnings.append(f"ss: плагин {parts[0]} не поддерживается, игнорируется")
        else:
            server["plugin"] = base
            if len(parts) > 1:
                server["pluginOpts"] = ";".join(parts[1:])
            transport_extra = base

    outbound = {"protocol": "shadowsocks", "settings": {"servers": [server]}}
    return RawServer(
        name=name,
        protocol="shadowsocks",
        address=host,
        port=port,
        credential=password,
        transport=f"ss/{transport_extra}",
        outbound=outbound,
        warnings=warnings,
    )


def _decode_userinfo(userinfo: str) -> tuple[str, str]:
    if ":" in userinfo:
        return _decode_userinfo_plain(userinfo)
    decoded = b64_decode(userinfo).decode("utf-8")
    return _decode_userinfo_plain(decoded)


def _decode_userinfo_plain(userinfo: str) -> tuple[str, str]:
    method, _, password = unquote(userinfo).partition(":")
    return method, password
