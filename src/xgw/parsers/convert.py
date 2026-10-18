"""Перевод сервера из описания Xray в описание sing-box и обратно.

Нужен, чтобы один и тот же сервер можно было вести любым из двух ядер (generator/singbox.py,
generator/profiles.py). Переводится общее подмножество — то, что проверено на живых Xray 26.10.10
и sing-box 1.14.3 (tests/test_convert_live.py):

    протоколы   vless, vmess, trojan, shadowsocks, socks
    транспорты  tcp (без маскировки под HTTP), ws, grpc (не multiMode), httpupgrade
    защита      tls (с uTLS-отпечатком), reality

Всё остальное — xhttp, mKCP, HTTP/2, цепочки dialerProxy, mux в самом описании сервера, закрепление
сертификата (у Xray — хеш сертификата, у sing-box — хеш открытого ключа: друг в друга не
переводятся) — остаётся только у того ядра, которое это умеет: перевод возвращает None.

Проверка сертификата не отключается ни в одном из ядер: `insecure` не переносится.
"""

from __future__ import annotations

import copy
import re

from .common import SingboxSpec

# Отпечаток uTLS, если в ссылке его нет: Xray 26.10.10 без fp отправляет ClientHello как
# Chrome (проверено), а sing-box без uTLS — как Go (по нему легко узнать клиента).
DEFAULT_FINGERPRINT = "chrome"


class Unsupported(Exception):
    """Сервер так не записать."""


# --- Xray → sing-box -------------------------------------------------------------


def to_singbox(outbound: dict) -> SingboxSpec | None:
    """Описание сервера для sing-box; None — сервер умеет только Xray."""
    if not outbound:
        return None
    try:
        return SingboxSpec(main=_xray_to_singbox(outbound))
    except Unsupported:
        return None


def _entry(settings: dict) -> tuple[dict, dict]:
    """Сервер и пользователь из settings: классический vnext/servers либо плоская запись."""
    entries = settings.get("vnext") or settings.get("servers") or []
    first = entries[0] if isinstance(entries, list) and entries else None
    if not isinstance(first, dict):
        if not settings.get("address"):
            raise Unsupported("нет адреса")
        first = settings
    users = first.get("users")
    user = users[0] if isinstance(users, list) and users and isinstance(users[0], dict) else {}
    return first, user


def _xray_to_singbox(outbound: dict) -> dict:
    protocol = str(outbound.get("protocol") or "")
    settings = outbound.get("settings") if isinstance(outbound.get("settings"), dict) else {}
    stream = outbound.get("streamSettings")
    stream = stream if isinstance(stream, dict) else {}
    mux = outbound.get("mux")
    if isinstance(mux, dict) and mux.get("enabled"):
        raise Unsupported("mux в описании сервера")
    sockopt = stream.get("sockopt")
    if isinstance(sockopt, dict) and sockopt.get("dialerProxy"):
        raise Unsupported("цепочка dialerProxy")

    entry, user = _entry(settings)
    try:
        port = int(entry.get("port") or 0)
    except (TypeError, ValueError):
        port = 0
    address = str(entry.get("address") or "")
    if not address or not 0 < port < 65536:
        raise Unsupported("нет адреса или порта")
    body: dict = {"type": "", "server": address, "server_port": port}

    if protocol == "vless":
        encryption = str(user.get("encryption") or entry.get("encryption") or "none")
        if encryption not in ("", "none"):
            raise Unsupported("шифрование VLESS")
        uuid = user.get("id") or entry.get("id")
        if not uuid:
            raise Unsupported("нет UUID")
        body.update(type="vless", uuid=str(uuid), packet_encoding="xudp")
        flow = user.get("flow") or entry.get("flow")
        if flow:
            body["flow"] = str(flow)
    elif protocol == "vmess":
        uuid = user.get("id") or entry.get("id")
        if not uuid:
            raise Unsupported("нет UUID")
        body.update(
            type="vmess", uuid=str(uuid), security=str(user.get("security") or "auto"),
            alter_id=int(user.get("alterId") or 0), packet_encoding="xudp",
        )
    elif protocol == "trojan":
        password = entry.get("password") or user.get("password")
        if not password:
            raise Unsupported("нет пароля")
        body.update(type="trojan", password=str(password))
    elif protocol == "shadowsocks":
        method, password = entry.get("method"), entry.get("password")
        if not method or not password:
            raise Unsupported("нет метода или пароля")
        body.update(type="shadowsocks", method=str(method), password=str(password))
    elif protocol == "socks":
        body.update(type="socks", version="5")
        if user.get("user"):
            body.update(username=str(user["user"]), password=str(user.get("pass") or ""))
    else:
        raise Unsupported(f"протокол {protocol}")

    transport = _transport_to_singbox(stream)
    if transport:
        body["transport"] = transport
    tls = _security_to_singbox(stream, protocol, body.get("flow", ""))
    if tls:
        body["tls"] = tls
    elif protocol == "trojan":
        pass  # trojan без TLS допустим в sing-box, но так его почти не используют
    return body


def _transport_to_singbox(stream: dict) -> dict | None:
    network = str(stream.get("network") or "tcp").lower()
    if network in ("tcp", "raw"):
        settings = stream.get("tcpSettings")
        header = settings.get("header") if isinstance(settings, dict) else None
        if isinstance(header, dict) and str(header.get("type") or "none").lower() != "none":
            raise Unsupported("маскировка tcp под HTTP")
        return None
    if network == "ws":
        ws = stream.get("wsSettings") if isinstance(stream.get("wsSettings"), dict) else {}
        path = str(ws.get("path") or "/")
        result: dict = {"type": "ws"}
        # Ранние данные Xray задаёт параметром ed в пути; sing-box — отдельными полями.
        path, early = _split_early_data(path)
        if early:
            result["max_early_data"] = early
            result["early_data_header_name"] = "Sec-WebSocket-Protocol"
        result["path"] = path or "/"
        headers = {}
        host = ws.get("host")
        raw_headers = ws.get("headers")
        if isinstance(raw_headers, dict):
            headers = {str(k): str(v) for k, v in raw_headers.items() if isinstance(v, (str, int))}
        if host:
            headers["Host"] = str(host)
        if headers:
            result["headers"] = headers
        return result
    if network == "grpc":
        grpc = stream.get("grpcSettings") if isinstance(stream.get("grpcSettings"), dict) else {}
        if grpc.get("multiMode"):
            raise Unsupported("grpc multiMode")
        if grpc.get("authority"):
            raise Unsupported("grpc authority")
        return {"type": "grpc", "service_name": str(grpc.get("serviceName") or "")}
    if network == "httpupgrade":
        up = (stream.get("httpupgradeSettings")
              if isinstance(stream.get("httpupgradeSettings"), dict) else {})
        result = {"type": "httpupgrade", "path": str(up.get("path") or "/")}
        if up.get("host"):
            result["host"] = str(up["host"])
        return result
    raise Unsupported(f"транспорт {network}")


def _split_early_data(path: str) -> tuple[str, int]:
    """Путь без параметра ed и размер ранних данных (0 — параметра нет)."""
    found = re.search(r"[?&]ed=(\d+)", path)
    if not found:
        return path, 0
    cleaned = path[: found.start()] + path[found.end():]
    if found.group(0).startswith("?") and cleaned[found.start():found.start() + 1] == "&":
        cleaned = cleaned[: found.start()] + "?" + cleaned[found.start() + 1:]
    return cleaned or "/", int(found.group(1))


def _security_to_singbox(stream: dict, protocol: str, flow: str) -> dict | None:
    security = str(stream.get("security") or "none").lower()
    if security == "none":
        return None
    if security == "tls":
        tls_in = stream.get("tlsSettings") if isinstance(stream.get("tlsSettings"), dict) else {}
        pin = tls_in.get("xgwSingboxPin")
        # Хеш сертификата Xray (pcs) и проверка по другому имени (vcn) у sing-box записать
        # нечем; закрепление по открытому ключу (pks) — есть.
        if tls_in.get("verifyPeerCertByName") or (tls_in.get("pinnedPeerCertSha256") and not pin):
            raise Unsupported("закрепление сертификата")
        tls: dict = {"enabled": True}
        if pin:
            tls["certificate_public_key_sha256"] = [str(pin)]
        if tls_in.get("serverName"):
            tls["server_name"] = str(tls_in["serverName"])
        alpn = tls_in.get("alpn")
        if isinstance(alpn, list) and alpn:
            tls["alpn"] = [str(item) for item in alpn]
        tls["utls"] = {
            "enabled": True,
            "fingerprint": str(tls_in.get("fingerprint") or DEFAULT_FINGERPRINT),
        }
        return tls
    if security == "reality":
        reality_in = (stream.get("realitySettings")
                      if isinstance(stream.get("realitySettings"), dict) else {})
        if reality_in.get("mldsa65Verify"):
            raise Unsupported("mldsa65")
        spider = str(reality_in.get("spiderX") or "")
        if flow and spider not in ("", "/"):
            raise Unsupported("spiderX вместе с flow")
        public_key = reality_in.get("publicKey")
        if not public_key:
            raise Unsupported("нет публичного ключа REALITY")
        reality: dict = {"enabled": True, "public_key": str(public_key)}
        if reality_in.get("shortId"):
            reality["short_id"] = str(reality_in["shortId"])
        tls = {"enabled": True, "reality": reality}
        if reality_in.get("serverName"):
            tls["server_name"] = str(reality_in["serverName"])
        tls["utls"] = {
            "enabled": True,
            "fingerprint": str(reality_in.get("fingerprint") or DEFAULT_FINGERPRINT),
        }
        return tls
    raise Unsupported(f"защита {security}")


# --- sing-box → Xray -------------------------------------------------------------


def to_xray(spec: SingboxSpec) -> dict:
    """Описание сервера для Xray; пустое — сервер умеет только sing-box."""
    if spec.endpoint or spec.extra:
        return {}
    try:
        return _singbox_to_xray(spec.main)
    except Unsupported:
        return {}


def _singbox_to_xray(body: dict) -> dict:
    kind = str(body.get("type") or "")
    if body.get("detour") or body.get("multiplex") or body.get("bind_interface"):
        raise Unsupported("цепочка или multiplex")
    for key in ("udp_over_tcp", "domain_resolver", "network"):
        if body.get(key):
            raise Unsupported(f"поле {key}")
    address, port = str(body.get("server") or ""), body.get("server_port")
    if not address or not isinstance(port, int) or not 0 < port < 65536:
        raise Unsupported("нет адреса или порта")

    if kind == "vless":
        user: dict = {"id": str(body.get("uuid") or ""), "encryption": "none"}
        if body.get("flow"):
            user["flow"] = str(body["flow"])
        _no_unknown_encoding(body)
        outbound: dict = {
            "protocol": "vless",
            "settings": {"vnext": [{"address": address, "port": port, "users": [user]}]},
        }
    elif kind == "vmess":
        _no_unknown_encoding(body)
        user = {
            "id": str(body.get("uuid") or ""), "alterId": int(body.get("alter_id") or 0),
            "security": str(body.get("security") or "auto"),
        }
        outbound = {
            "protocol": "vmess",
            "settings": {"vnext": [{"address": address, "port": port, "users": [user]}]},
        }
    elif kind == "trojan":
        outbound = {
            "protocol": "trojan",
            "settings": {"servers": [{
                "address": address, "port": port, "password": str(body.get("password") or ""),
            }]},
        }
    elif kind == "shadowsocks":
        if body.get("plugin"):
            raise Unsupported("плагин shadowsocks")
        outbound = {
            "protocol": "shadowsocks",
            "settings": {"servers": [{
                "address": address, "port": port, "method": str(body.get("method") or ""),
                "password": str(body.get("password") or ""),
            }]},
        }
    elif kind == "socks":
        server: dict = {"address": address, "port": port, "users": []}
        if body.get("username"):
            server["users"] = [{
                "user": str(body["username"]), "pass": str(body.get("password") or ""),
            }]
        outbound = {"protocol": "socks", "settings": {"servers": [server]}}
    else:
        raise Unsupported(f"тип {kind}")

    stream = _transport_to_xray(body.get("transport"))
    _security_to_xray(body.get("tls"), stream)
    outbound["streamSettings"] = stream
    # Без идентификатора, пароля и т. п. сервера нет.
    if kind in ("vless", "vmess") and not user["id"]:
        raise Unsupported("нет UUID")
    return outbound


def _no_unknown_encoding(body: dict) -> None:
    if str(body.get("packet_encoding") or "xudp") not in ("xudp", ""):
        raise Unsupported("packet_encoding")


def _transport_to_xray(transport: object) -> dict:
    if not transport:
        return {"network": "tcp"}
    if not isinstance(transport, dict):
        raise Unsupported("транспорт")
    kind = str(transport.get("type") or "")
    if kind == "ws":
        path = str(transport.get("path") or "/")
        early = transport.get("max_early_data")
        if early:
            if transport.get("early_data_header_name") not in (None, "", "Sec-WebSocket-Protocol"):
                raise Unsupported("имя заголовка ранних данных")
            path += ("&" if "?" in path else "?") + f"ed={int(early)}"
        ws: dict = {"path": path}
        headers = transport.get("headers")
        if isinstance(headers, dict):
            rest = {k: v for k, v in headers.items() if str(k).lower() != "host"}
            host = next((v for k, v in headers.items() if str(k).lower() == "host"), None)
            if isinstance(host, list):
                host = host[0] if host else None
            if host:
                ws["host"] = str(host)
            if rest:
                ws["headers"] = {str(k): str(v) for k, v in rest.items()}
        return {"network": "ws", "wsSettings": ws}
    if kind == "grpc":
        return {"network": "grpc",
                "grpcSettings": {"serviceName": str(transport.get("service_name") or "")}}
    if kind == "httpupgrade":
        up: dict = {"path": str(transport.get("path") or "/")}
        if transport.get("host"):
            up["host"] = str(transport["host"])
        return {"network": "httpupgrade", "httpupgradeSettings": up}
    raise Unsupported(f"транспорт {kind}")


def _security_to_xray(tls: object, stream: dict) -> None:
    if not tls:
        return
    if not isinstance(tls, dict):
        raise Unsupported("tls")
    if not tls.get("enabled"):
        return
    for key in ("fragment", "record_fragment", "ech", "certificate", "certificate_path",
                "certificate_public_key_sha256", "min_version", "max_version", "cipher_suites",
                "curve_preferences", "client_certificate", "client_key", "disable_sni"):
        if tls.get(key):
            raise Unsupported(f"tls.{key}")
    utls = tls.get("utls")
    fingerprint = ""
    if isinstance(utls, dict) and utls.get("enabled"):
        fingerprint = str(utls.get("fingerprint") or DEFAULT_FINGERPRINT)
    reality = tls.get("reality")
    if isinstance(reality, dict) and reality.get("enabled"):
        settings: dict = {"publicKey": str(reality.get("public_key") or "")}
        if reality.get("short_id"):
            settings["shortId"] = str(reality["short_id"])
        if tls.get("server_name"):
            settings["serverName"] = str(tls["server_name"])
        if fingerprint:
            settings["fingerprint"] = fingerprint
        if not settings["publicKey"]:
            raise Unsupported("нет публичного ключа REALITY")
        stream["security"] = "reality"
        stream["realitySettings"] = settings
        return
    settings = {}
    if tls.get("server_name"):
        settings["serverName"] = str(tls["server_name"])
    if tls.get("alpn"):
        settings["alpn"] = [str(item) for item in tls["alpn"]]
    if fingerprint:
        settings["fingerprint"] = fingerprint
    stream["security"] = "tls"
    stream["tlsSettings"] = settings


def copy_spec(spec: SingboxSpec) -> SingboxSpec:
    return SingboxSpec(
        main=copy.deepcopy(spec.main), endpoint=spec.endpoint, extra=copy.deepcopy(spec.extra),
    )
