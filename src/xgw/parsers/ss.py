"""ss:// — SIP002 (userinfo в base64) и старый формат (всё в base64).

Плагины SIP003 (simple-obfs, v2ray-plugin) Xray-core не поддерживает: у
shadowsocks-outbound нет полей для плагина, а неизвестные поля ядро молча
игнорирует. Узел с плагином пропускается с предупреждением — без обфускации
он всё равно не заработает и только займёт место в балансировщике.
"""

from __future__ import annotations

import binascii
from urllib.parse import parse_qs, unquote

from .common import ParseError, RawServer, b64_decode, single, split_host_port


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
            method, password = _split_userinfo(userinfo)
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
    supported = True
    plugin = single(query, "plugin").split(";")[0].strip()
    if plugin:
        warnings.append(f"ss: плагин {plugin} не поддерживается Xray-core")
        supported = False

    outbound = {"protocol": "shadowsocks", "settings": {"servers": [server]}}
    return RawServer(
        name=name,
        protocol="shadowsocks",
        address=host,
        port=port,
        credential=password,
        transport="ss/plain",
        outbound=outbound,
        warnings=warnings,
        supported=supported,
    )


def _decode_userinfo(userinfo: str) -> tuple[str, str]:
    """SIP002: base64url(method:password) либо percent-encoded method:password
    (так записываются шифры 2022-blake3-*)."""
    plain = unquote(userinfo)
    if ":" in plain:
        return _split_userinfo(plain)
    return _split_userinfo(b64_decode(plain).decode("utf-8"))


def _split_userinfo(userinfo: str) -> tuple[str, str]:
    method, _, password = userinfo.partition(":")
    return method, password
