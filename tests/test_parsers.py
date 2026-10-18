"""Тесты парсеров ссылок и тел подписок (все данные фейковые)."""

import base64
import json
import re

import links
import pytest
from conftest import golden

from xgw.config import Config
from xgw.generator.builder import build, select_nodes
from xgw.model import raw_to_node
from xgw.parsers.common import (
    ParseError,
    b64_decode,
    parse_body,
    parse_link,
    parse_links_text,
)
from xgw.parsers.xray_json import parse_outbounds


def test_vless_reality_tcp():
    raw = parse_link(links.VLESS_REALITY)
    assert raw.protocol == "vless"
    assert raw.transport == "tcp/reality"
    assert raw.outbound == golden("vless_reality.outbound.json", raw.outbound)
    assert raw_to_node(raw, "test").country == "nl"


def test_vless_ws_tls():
    raw = parse_link(links.VLESS_WS)
    stream = raw.outbound["streamSettings"]
    assert stream["network"] == "ws"
    assert stream["security"] == "tls"
    assert stream["tlsSettings"]["alpn"] == ["h2", "http/1.1"]
    assert stream["wsSettings"] == {"path": "/ws", "host": "de.example.com"}
    assert raw_to_node(raw, "test").country == "de"


def test_vless_grpc():
    raw = parse_link(links.VLESS_GRPC)
    assert raw.outbound["streamSettings"]["grpcSettings"] == {"serviceName": "grpc-svc"}
    assert "multiMode" not in raw.outbound["streamSettings"]["grpcSettings"]


def test_vless_xhttp():
    raw = parse_link(links.VLESS_XHTTP)
    settings = raw.outbound["streamSettings"]["xhttpSettings"]
    assert settings["path"] == "/xh"
    assert settings["mode"] == "auto"
    assert settings["extra"] == {"scMaxEachPostBytes": 1000000}


def test_vless_kcp():
    raw = parse_link(links.VLESS_KCP)
    kcp = raw.outbound["streamSettings"]["kcpSettings"]
    assert kcp["header"]["type"] == "srtp"
    assert kcp["seed"] == "kcp-seed"


def test_vless_httpupgrade():
    raw = parse_link(links.VLESS_HTTPUPGRADE)
    assert raw.outbound["streamSettings"]["httpupgradeSettings"] == {
        "path": "/hu",
        "host": "hu.example.com",
    }


def test_vless_tcp_http_header():
    raw = parse_link(links.VLESS_TCP_HTTP)
    request = raw.outbound["streamSettings"]["tcpSettings"]["header"]["request"]
    assert request["path"] == ["/hpd"]
    assert request["headers"]["Host"] == ["h.example.com"]


def test_vless_unknown_param_warning():
    raw = parse_link(links.VLESS_WS.replace("#", "&wat=42#"))
    assert any("wat" in warning for warning in raw.warnings)


def test_vless_broken_no_uuid():
    with pytest.raises(ParseError):
        parse_link("vless://203.0.113.10:443?security=tls#broken")


def test_vmess_ws():
    raw = parse_link(links.VMESS)
    vnext = raw.outbound["settings"]["vnext"][0]
    assert vnext["address"] == "fr.example.com"
    assert vnext["users"][0]["id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert vnext["users"][0]["security"] == "auto"
    assert vnext["users"][0]["alterId"] == 0
    assert raw.outbound["streamSettings"]["wsSettings"]["path"] == "/vmess"
    assert raw.transport == "ws/tls"


def test_vmess_broken():
    with pytest.raises(ParseError):
        parse_link("vmess://" + base64.b64encode(b"not json").decode())



def test_trojan():
    raw = parse_link(links.TROJAN)
    server = raw.outbound["settings"]["servers"][0]
    assert server == {"address": "203.0.113.20", "port": 443, "password": "tr0jan-pass"}
    assert raw.outbound["streamSettings"]["security"] == "tls"
    assert raw.outbound["streamSettings"]["tlsSettings"]["serverName"] == "nl2.example.org"


def test_trojan_allow_insecure_is_dropped_for_xray_26_10_10():
    """Xray 26.10.10 конфиг с allowInsecure не принимает (поле убрано, замена — pcs и
    vcn; проверено): сервер проверяется по сертификату, а не выпадает из конфига."""
    raw = parse_link(links.TROJAN_INSECURE)
    tls = raw.outbound["streamSettings"]["tlsSettings"]
    assert "allowInsecure" not in tls
    assert any("allowInsecure не поддерживается" in warning for warning in raw.warnings)


def test_pinned_certificate_and_verify_name_from_the_link():
    pin = "495b481f261d899a504576d5ffbfc8f58a6ce3d8dd757a980ca2a81a6fb55dbb"
    raw = parse_link(
        f"vless://11111111-2222-3333-4455-666666666661@203.0.113.30:443?security=tls"
        f"&sni=nl.example.org&allowInsecure=1&pcs={pin}&vcn=cdn.example.org#pinned"
    )
    tls = raw.outbound["streamSettings"]["tlsSettings"]
    assert tls["pinnedPeerCertSha256"] == pin
    assert tls["verifyPeerCertByName"] == "cdn.example.org"
    assert "allowInsecure" not in tls
    assert raw.warnings == []


def test_ss_sip002():
    raw = parse_link(links.SS_SIP002.split("/?plugin=")[0] + "#SS-1")
    assert raw.supported and raw.name == "SS-1"
    assert raw.outbound["settings"]["servers"][0] == {
        "address": "203.0.113.40",
        "port": 8388,
        "method": "aes-256-gcm",
        "password": "ss-pass-123",
    }


def test_ss_plugin_goes_to_singbox_not_to_xray():
    """У shadowsocks-outbound Xray нет плагинов: узел с obfs не попадает в конфиг Xray с
    полями, которые ядро молча проигнорирует, а описан для sing-box (у него obfs встроен)."""
    raw = parse_link(links.SS_SIP002)
    assert raw.supported and raw.outbound == {}
    assert raw.singbox is not None
    assert raw.singbox.main["plugin"] == "obfs-local"
    assert raw.singbox.main["plugin_opts"].startswith("obfs=")
    servers, _, warnings = parse_links_text(links.SS_SIP002, "test")
    assert len(servers) == 1 and not warnings


def test_ss_2022_percent_encoded_userinfo():
    raw = parse_link(
        "ss://2022-blake3-aes-256-gcm%3AYWFhYWFhYWFhYWFhYWFhYQ%3D%3D@203.0.113.43:8390#SS-2022"
    )
    server = raw.outbound["settings"]["servers"][0]
    assert server["method"] == "2022-blake3-aes-256-gcm"
    assert server["password"] == "YWFhYWFhYWFhYWFhYWFhYQ=="


def test_ss_plain_userinfo():
    raw = parse_link(links.SS_PLAIN)
    server = raw.outbound["settings"]["servers"][0]
    assert server["method"] == "aes-128-gcm"
    assert server["password"] == "pw123"
    assert server["port"] == 8388


def test_ss_old_format():
    raw = parse_link(links.SS_OLD)
    server = raw.outbound["settings"]["servers"][0]
    assert server == {
        "address": "203.0.113.42",
        "port": 8389,
        "method": "chacha20-ietf-poly1305",
        "password": "old-pass",
    }


def test_socks():
    raw = parse_link(links.SOCKS)
    server = raw.outbound["settings"]["servers"][0]
    assert server["users"] == [{"user": "user", "pass": "pass"}]
    assert server["address"] == "203.0.113.30"


def test_hysteria2_is_a_singbox_only_server():
    servers, _, _warnings = parse_links_text(links.HY2, "test")
    assert len(servers) == 1 and servers[0].outbound == {}
    body = servers[0].singbox.main
    assert body["type"] == "hysteria2" and body["server_port"] == 443
    assert body["tls"]["enabled"] and "insecure" not in body["tls"]


def test_wireguard_with_a_broken_key_is_skipped_with_a_reason():
    servers, _, warnings = parse_links_text(
        "wireguard://eyJhIjoxfQ@203.0.113.60:51820#wg", "test"
    )
    assert servers == []
    assert any("wireguard" in warning for warning in warnings)


def test_b64_variants():
    import binascii

    assert b64_decode("dGVzdA") == b"test"  # URL-safe без добивки
    assert b64_decode("dGVzdA==") == b"test"  # обычный с добивкой
    with pytest.raises(binascii.Error):
        b64_decode("!!!")


def test_subscription_base64_std():
    text = "# expire: 2027-01-01\n" + "\n".join(links.FULL_LINKS)
    servers, meta, _warnings = parse_body(base64.b64encode(text.encode()), "sub")
    assert len(servers) == 4
    assert meta.get("expire") == "2027-01-01"


def test_subscription_base64_urlsafe():
    text = "\n".join(links.FULL_LINKS)
    encoded = base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")
    servers, _meta, _warnings = parse_body(encoded, "sub")
    assert len(servers) == 4


def test_subscription_plain():
    servers, meta, warnings = parse_body("# expire: soon\nнет ссылок тут", "sub")
    assert servers == []
    assert "ссылок не найдено" not in " ".join(warnings)  # meta был — не «пусто»
    assert meta.get("expire") == "soon"


def test_subscription_clash_unsupported():
    with pytest.raises(ParseError, match="Clash"):
        parse_body("proxies:\n  - name: x\n    type: ss", "sub")


def test_subscription_in_singbox_format_is_parsed():
    uuid = "2dd61d93-75d8-4da4-ac0e-6aece7eac365"
    body = json.dumps({"outbounds": [
        {"type": "direct", "tag": "direct"},
        {"type": "vmess", "server": "203.0.113.9", "server_port": 443, "uuid": uuid, "tag": "sb"},
    ]})
    servers, _, warnings = parse_body(body, "sub")
    assert [server.name for server in servers] == ["sb"] and not warnings
    assert servers[0].outbound["protocol"] == "vmess" and servers[0].singbox is not None


def test_broken_link_does_not_stop_parsing():
    servers, _, warnings = parse_links_text("vless://broken\n" + links.VLESS_WS, "sub")
    assert len(servers) == 1
    assert any("vless" in warning for warning in warnings)


def test_xray_json_subscription_with_chain():
    chain = {
        "tag": "chain-socks",
        "protocol": "socks",
        "settings": {"servers": [{"address": "203.0.113.70", "port": 1080}]},
    }
    proxy = {
        "tag": "vless-main",
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": "203.0.113.71",
                    "port": 443,
                    "users": [{"id": "11111111-2222-3333-4455-666666666672", "encryption": "none"}],
                }
            ]
        },
        "streamSettings": {
            "network": "tcp",
            "security": "tls",
            "sockopt": {"dialerProxy": "chain-socks"},
        },
        "mux": {"enabled": False, "concurrency": -1},
    }
    config = {"outbounds": [proxy, chain, {"tag": "direct", "protocol": "freedom"}]}
    servers, _meta, warnings = parse_body(json.dumps(config), "sub")
    assert len(servers) == 2
    mains = [server for server in servers if server.keep_tag is None]
    chains = [server for server in servers if server.keep_tag is not None]
    assert len(mains) == 1 and len(chains) == 1
    assert mains[0].outbound["mux"]["concurrency"] == -1  # mux сохранён как есть
    # звено получает собственный тег, ссылка dialerProxy переписана на него
    chain_tag = chains[0].keep_tag
    assert re.fullmatch(r"chain-[0-9a-f]{8}", chain_tag)
    assert mains[0].outbound["streamSettings"]["sockopt"]["dialerProxy"] == chain_tag
    assert chains[0].outbound["protocol"] == "socks"
    assert "direct" not in [server.name for server in servers]
    assert warnings == []


def _vless_json(tag: str, address: str, dialer: str | None = None) -> dict:
    stream: dict = {"network": "tcp", "security": "tls"}
    if dialer:
        stream["sockopt"] = {"dialerProxy": dialer}
    return {
        "tag": tag,
        "protocol": "vless",
        "settings": {"vnext": [{"address": address, "port": 443, "users": [
            {"id": "11111111-2222-3333-4455-666666666673", "encryption": "none"}]}]},
        "streamSettings": stream,
    }


def test_xray_json_chain_tags_do_not_collide_or_leak_into_balancer():
    """У двух конфигов подписки звено называется одинаково («proxy-hop»), а
    содержимое разное. Теги звеньев не должны ни слиться, ни начаться с «proxy-»:
    иначе промежуточный узел попал бы под селектор балансировщика."""
    def config(remarks: str, address: str, hop: str) -> dict:
        hop_outbound = {"tag": "proxy-hop", "protocol": "socks",
                        "settings": {"servers": [{"address": hop, "port": 1080}]}}
        return {"remarks": remarks, "outbounds": [
            _vless_json("proxy", address, dialer="proxy-hop"), hop_outbound,
            {"tag": "direct", "protocol": "freedom"},
        ]}

    body = json.dumps([
        config("🇳🇱 NL chain", "203.0.113.81", "203.0.113.91"),
        config("🇩🇪 DE chain", "203.0.113.82", "203.0.113.92"),
    ])
    servers, _meta, warnings = parse_body(body, "sub")
    assert warnings == []
    mains = [server for server in servers if server.keep_tag is None]
    chains = [server for server in servers if server.keep_tag is not None]
    assert sorted(server.name for server in mains) == ["🇩🇪 DE chain", "🇳🇱 NL chain"]
    assert len({server.keep_tag for server in chains}) == 2

    nodes = [raw_to_node(server, "sub") for server in servers]
    cfg = Config()
    result = build(cfg, select_nodes(nodes, cfg), hosts={}, probe_password="P" * 32)
    by_tag = {outbound["tag"]: outbound for outbound in result.config["outbounds"]}
    members = [tag for tag in by_tag if tag.startswith("proxy-")]
    assert sorted(members) == sorted(info.tag for info in result.nodes)  # звеньев среди них нет
    for tag in members:
        hop = by_tag[by_tag[tag]["streamSettings"]["sockopt"]["dialerProxy"]]
        expected = "203.0.113.91" if "-nl-" in tag else "203.0.113.92"
        assert hop["settings"]["servers"][0]["address"] == expected
        assert hop["streamSettings"]["sockopt"]["mark"] == cfg.capture.mark_bypass


def test_xray_json_fragment_chain_is_kept():
    """freedom с fragment в роли dialerProxy — часть цепочки, а не служебный outbound."""
    fragment = {"tag": "fragment", "protocol": "freedom",
                "settings": {"fragment": {"packets": "tlshello", "length": "100-200"}}}
    body = json.dumps({"outbounds": [
        _vless_json("main", "203.0.113.83", dialer="fragment"), fragment,
        {"tag": "direct", "protocol": "freedom"},
    ]})
    servers, _meta, warnings = parse_body(body, "sub")
    assert warnings == []
    chains = [server for server in servers if server.keep_tag]
    assert len(chains) == 1 and chains[0].outbound["settings"]["fragment"]["packets"] == "tlshello"


def test_xray_json_missing_chain_drops_server():
    """Ссылка dialerProxy в никуда: узел пропускается, а не едет в конфиг сломанным."""
    body = json.dumps({"outbounds": [
        _vless_json("broken", "203.0.113.84", dialer="nowhere"),
        _vless_json("fine", "203.0.113.85"),
    ]})
    servers, _meta, warnings = parse_body(body, "sub")
    assert [server.name for server in servers] == ["fine"]
    assert any("nowhere" in warning for warning in warnings)


def test_xray_json_flat_settings():
    body = json.dumps({"outbounds": [{
        "tag": "flat", "protocol": "vless",
        "settings": {"address": "203.0.113.86", "port": 443,
                     "id": "11111111-2222-3333-4455-666666666674", "encryption": "none"},
        "streamSettings": {"network": "tcp", "security": "tls"},
    }]})
    servers, _meta, _warnings = parse_body(body, "sub")
    assert [(s.address, s.port, s.credential) for s in servers] == [
        ("203.0.113.86", 443, "11111111-2222-3333-4455-666666666674")
    ]


def test_tls_server_name_falls_back_to_host():
    """Как в v2rayN: адрес — IP, домен только в host → он же имя сервера TLS."""
    raw = parse_link(
        "vless://11111111-2222-3333-4455-666666666675@203.0.113.87:443?"
        "security=tls&type=ws&host=cdn.example.com&path=%2Fws#CDN"
    )
    assert raw.outbound["streamSettings"]["tlsSettings"]["serverName"] == "cdn.example.com"


def test_unknown_transport_warning_names_it():
    raw = parse_link(links.VLESS_WS.replace("type=ws", "type=quantum"))
    assert any("'quantum'" in warning for warning in raw.warnings)


def test_broken_port_is_parse_error_without_secrets():
    with pytest.raises(ParseError) as excinfo:
        parse_link("trojan://sup3r-secret@203.0.113.88:notaport?security=tls#x")
    assert "sup3r-secret" not in str(excinfo.value)


def test_subscription_with_bom():
    servers, _meta, _warnings = parse_body("﻿\n" + links.VLESS_WS, "sub")
    assert len(servers) == 1


def test_xray_json_array_of_configs():
    one = {"outbounds": [
        {"tag": "a", "protocol": "trojan",
         "settings": {"servers": [{"address": "203.0.113.72", "port": 443, "password": "p1"}]}}
    ]}
    two = {"outbounds": [
        {"tag": "b", "protocol": "trojan",
         "settings": {"servers": [{"address": "203.0.113.73", "port": 443, "password": "p2"}]}}
    ]}
    servers, _meta, _warnings = parse_body(json.dumps([one, two]), "sub")
    assert sorted(server.name for server in servers) == ["a", "b"]


def test_xray_json_hysteria2_skipped():
    config = {
        "outbounds": [
            {
                "tag": "hy",
                "protocol": "hysteria2",
                "settings": {"servers": [{"address": "h.example.com"}]},
            }
        ]
    }
    servers, warnings = parse_outbounds(config["outbounds"], "sub")
    assert servers == []
    assert any("hysteria2" in warning for warning in warnings)
