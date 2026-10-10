"""Тесты парсеров ссылок и тел подписок (все данные фейковые)."""

import base64
import json

import links
import pytest
from conftest import golden

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
    assert stream["wsSettings"] == {"path": "/ws", "headers": {"Host": "de.example.com"}}
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


def test_trojan_allow_insecure():
    raw = parse_link(links.TROJAN_INSECURE)
    assert raw.outbound["streamSettings"]["tlsSettings"]["allowInsecure"] is True


def test_ss_sip002_with_plugin():
    raw = parse_link(links.SS_SIP002)
    server = raw.outbound["settings"]["servers"][0]
    assert server["method"] == "aes-256-gcm"
    assert server["password"] == "ss-pass-123"
    assert server["plugin"] == "obfs-local"
    assert server["pluginOpts"] == "obfs=http;obfs-host=ob.example.com"


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


def test_hysteria2_skipped_with_warning():
    servers, _, warnings = parse_links_text(links.HY2, "test")
    assert servers == []
    assert any("hysteria2" in warning for warning in warnings)


def test_wireguard_skipped():
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


def test_subscription_singbox_unsupported():
    body = json.dumps({"outbounds": [{"type": "vmess", "server": "203.0.113.9", "tag": "sb"}]})
    with pytest.raises(ParseError, match="sing-box"):
        parse_body(body, "sub")


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
    chains = [server for server in servers if server.keep_tag == "chain-socks"]
    assert len(mains) == 1 and len(chains) == 1
    assert mains[0].outbound["mux"]["concurrency"] == -1  # mux сохранён как есть
    assert mains[0].outbound["streamSettings"]["sockopt"]["dialerProxy"] == "chain-socks"
    assert chains[0].outbound["protocol"] == "socks"
    assert "direct" not in [server.name for server in servers]
    assert warnings == []


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
