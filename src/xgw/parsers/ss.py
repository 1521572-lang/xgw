"""ss:// — SIP002 (userinfo в base64) и старый формат (всё в base64).

Плагины SIP003 Xray-core не поддерживает: у shadowsocks-outbound нет полей для плагина, а
неизвестные поля ядро молча игнорирует. Такой узел ведёт sing-box: obfs-local (simple-obfs) и
v2ray-plugin у него встроены, а shadow-tls записывается цепочкой shadowtls → shadowsocks. Плагин,
которого нет и у sing-box, пропускает узел с пояснением.
"""

from __future__ import annotations

import binascii
from urllib.parse import parse_qs, unquote

from .common import ParseError, RawServer, SingboxSpec, b64_decode, single, split_host_port


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
    plugin_text = single(query, "plugin").strip()
    if plugin_text:
        return _with_plugin(name, host, port, method, password, plugin_text)

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
    )


_PLUGINS = {"obfs-local": "obfs-local", "simple-obfs": "obfs-local", "obfs": "obfs-local",
            "v2ray-plugin": "v2ray-plugin"}


def _with_plugin(
    name: str, host: str, port: int, method: str, password: str, text: str,
) -> RawServer:
    """Сервер с плагином SIP003 — только для sing-box (Xray плагинов не знает)."""
    plugin, _, options = text.partition(";")
    plugin = plugin.strip().lower()
    base = dict(
        name=name, protocol="shadowsocks", address=host, port=port, credential=password,
        transport=f"ss/{plugin}", outbound={},
    )
    if plugin == "shadow-tls":
        values = dict(item.partition("=")[::2] for item in options.split(";") if item)
        try:
            version = int(values.get("version") or 3)
        except ValueError:
            version = 0
        if version not in (2, 3) or not values.get("password") or not values.get("host"):
            return RawServer(
                **base, supported=False,
                warnings=["ss: плагин shadow-tls — нужны host, password и version 2 или 3"],
            )
        tls = {"enabled": True, "server_name": values["host"],
               "utls": {"enabled": True, "fingerprint": "chrome"}}
        chain = {"tag": "shadowtls", "type": "shadowtls", "server": host, "server_port": port,
                 "version": version, "password": values["password"], "tls": tls}
        main = {
            "type": "shadowsocks", "method": method, "password": password, "detour": "shadowtls",
        }
        return RawServer(**base, singbox=SingboxSpec(main=main, extra=[chain]))
    mapped = _PLUGINS.get(plugin)
    if mapped is None:
        return RawServer(
            **base, supported=False,
            warnings=[f"ss: плагин {plugin} не поддерживается ни Xray, ни sing-box"],
        )
    main = {"type": "shadowsocks", "server": host, "server_port": port, "method": method,
            "password": password, "plugin": mapped}
    if options:
        main["plugin_opts"] = options
    return RawServer(**base, singbox=SingboxSpec(main=main))


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
