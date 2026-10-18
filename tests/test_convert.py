"""Один сервер — два ядра (0.1.12): перевод Xray ↔ sing-box и ссылки серверов, которые умеет только
sing-box. Ссылки и ключи — фейковые (tests/links.py)."""

import base64
import json

import links
import pytest

from xgw.model import raw_to_node
from xgw.parsers import convert
from xgw.parsers.common import ParseError, UnsupportedLink, normalize_pin, parse_body, parse_link

UUID = "2dd61d93-75d8-4da4-ac0e-6aece7eac365"
KEY = "yAnz5TF%2BlXXJte14tji3zlMNq%2Bhd2rYUIgJBgB3fBmk%3D"
PUB = "xTIBA5rboUvnH4htodjb6e697QjLERt1NAB4mZqp8Dg%3D"
PIN = base64.b64encode(bytes(range(32))).decode()


def _capability(link: str) -> str:
    return raw_to_node(parse_link(link), "t").capability


# --- Xray → sing-box -------------------------------------------------------------------


def test_vless_with_websocket_and_tls_is_translated():
    raw = parse_link(links.VLESS_WS)
    body = raw.singbox.main
    assert body["type"] == "vless" and body["server"] == "de.example.com"
    assert body["uuid"] == "11111111-2222-3333-4455-666666666662"
    assert body["transport"] == {
        "type": "ws", "path": "/ws", "headers": {"Host": "de.example.com"},
    }
    assert body["tls"]["server_name"] == "de.example.com" and body["tls"]["alpn"] == [
        "h2", "http/1.1"]
    # Отпечаток uTLS задан явно, а без него был бы «Chrome»: у Go-клиента ClientHello другой.
    assert body["tls"]["utls"] == {"enabled": True, "fingerprint": "chrome"}
    assert body["packet_encoding"] == "xudp"


def test_reality_with_vision_keeps_flow_and_keys():
    body = parse_link(links.VLESS_REALITY).singbox.main
    assert body["flow"] == "xtls-rprx-vision"
    assert body["tls"]["reality"] == {
        "enabled": True, "public_key": links.FAKE_PBK, "short_id": "abcd1234",
    }
    assert body["tls"]["server_name"] == "www.example.org"


def test_default_fingerprint_is_chrome_like_in_xray():
    link = links.VLESS_GRPC  # fp в ссылке нет
    body = parse_link(link).singbox.main
    assert body["tls"]["utls"]["fingerprint"] == "chrome"
    assert body["transport"] == {"type": "grpc", "service_name": "grpc-svc"}


@pytest.mark.parametrize("link", [
    links.VLESS_XHTTP, links.VLESS_KCP, links.VLESS_TCP_HTTP,
])
def test_transports_that_sing_box_lacks_stay_with_xray(link):
    assert _capability(link) == "xray"


def test_certificate_pin_of_xray_cannot_be_moved_without_a_public_key_pin():
    base = (f"vless://{UUID}@203.0.113.9:443?security=tls&sni=a.example&type=tcp"
            f"&pcs={'ab' * 32}")
    assert _capability(base) == "xray"
    pinned = parse_link(base + f"&pks={PIN}")
    assert raw_to_node(pinned, "t").capability == "dual"
    assert pinned.singbox.main["tls"]["certificate_public_key_sha256"] == [PIN]
    # Поле XGW живёт в описании сервера, но в конфиг Xray не попадает (builder._modernize).
    assert pinned.outbound["streamSettings"]["tlsSettings"]["xgwSingboxPin"] == PIN


def test_pin_accepts_hex_and_base64_and_rejects_the_rest():
    assert normalize_pin(PIN) == PIN
    assert normalize_pin(bytes(range(32)).hex()) == PIN
    assert normalize_pin(PIN.replace("+", "-").replace("/", "_").rstrip("=")) == PIN
    assert normalize_pin("deadbeef") == "" and normalize_pin("не хеш") == ""


def test_pin_with_an_unencoded_plus_in_the_link_is_still_a_pin():
    """Разбор запроса превращает «+» в пробел; в base64 пробела нет, значит это был «+»."""
    pin = base64.b64encode(bytes([0xFB]) * 32).decode()
    assert "+" in pin
    base = (f"vless://{UUID}@203.0.113.9:443?security=tls&sni=a.example&type=tcp"
            f"&pcs={'ab' * 32}")
    node = parse_link(base + f"&pks={pin}")
    assert not node.warnings and node.singbox.main["tls"]["certificate_public_key_sha256"] == [pin]
    assert normalize_pin(pin.replace("+", " ")) == pin


def test_spider_x_with_flow_and_chains_stay_with_xray():
    outbound = parse_link(links.VLESS_REALITY).outbound
    outbound["streamSettings"]["realitySettings"]["spiderX"] = "/crawl"
    assert convert.to_singbox(outbound) is None
    outbound["streamSettings"]["realitySettings"]["spiderX"] = "/"
    assert convert.to_singbox(outbound) is not None  # путь по умолчанию на соединение не влияет
    chained = parse_link(links.VLESS_WS).outbound
    chained["streamSettings"]["sockopt"] = {"dialerProxy": "chain-x"}
    assert convert.to_singbox(chained) is None
    muxed = parse_link(links.VLESS_WS).outbound
    muxed["mux"] = {"enabled": True}
    assert convert.to_singbox(muxed) is None


def test_websocket_early_data_moves_from_the_path_to_fields():
    outbound = parse_link(links.VLESS_WS).outbound
    outbound["streamSettings"]["wsSettings"]["path"] = "/ws?a=1&ed=2048"
    transport = convert.to_singbox(outbound).main["transport"]
    assert transport["path"] == "/ws?a=1" and transport["max_early_data"] == 2048
    assert transport["early_data_header_name"] == "Sec-WebSocket-Protocol"
    back = convert.to_xray(convert.to_singbox(outbound))
    assert back["streamSettings"]["wsSettings"]["path"] == "/ws?a=1&ed=2048"


@pytest.mark.parametrize("link", [
    links.VLESS_REALITY, links.VLESS_WS, links.VLESS_GRPC, links.VLESS_HTTPUPGRADE,
    links.TROJAN, links.VMESS, links.SS_PLAIN, links.SOCKS,
])
def test_round_trip_keeps_the_server(link):
    raw = parse_link(link)
    assert raw.singbox is not None, raw.name
    back = convert.to_xray(raw.singbox)
    assert back, raw.name
    # Тот же сервер: протокол, транспорт и защита.
    assert back["protocol"] == raw.outbound["protocol"]
    before = raw.outbound.get("streamSettings", {})
    after = back.get("streamSettings", {})
    assert after.get("network", "tcp") == before.get("network", "tcp")
    assert after.get("security", "none") == before.get("security", "none")


def test_no_converted_server_ever_disables_certificate_checks():
    for link in (links.VLESS_WS, links.TROJAN_INSECURE, links.VLESS_GRPC):
        text = json.dumps(parse_link(link).singbox.main)
        assert "insecure" not in text and "allowInsecure" not in text


# --- sing-box → Xray -------------------------------------------------------------------


def test_features_only_singbox_has_do_not_go_to_xray():
    base = {"type": "vless", "server": "203.0.113.5", "server_port": 443, "uuid": UUID}
    from xgw.parsers.common import SingboxSpec

    assert convert.to_xray(SingboxSpec(main=base))["protocol"] == "vless"
    for extra in (
        {"multiplex": {"enabled": True}}, {"detour": "x"}, {"udp_over_tcp": True},
        {"tls": {"enabled": True, "fragment": True}},
        {"tls": {"enabled": True, "certificate_public_key_sha256": [PIN]}},
        {"transport": {"type": "quic"}}, {"packet_encoding": "packetaddr"},
    ):
        assert convert.to_xray(SingboxSpec(main={**base, **extra})) == {}, extra
    assert convert.to_xray(SingboxSpec(main=base, endpoint=True)) == {}


# --- ссылки серверов, которые умеет только sing-box -------------------------------------


def test_hysteria2_link_with_obfs_ports_and_speed():
    link = ("hysteria2://s3cret@hy.example.com:443,20000-30000/?sni=sni.example&obfs=salamander"
            "&obfs-password=ob&mport=40000-41000&upmbps=50&downmbps=100#HY")
    raw = parse_link(link)
    assert raw.outbound == {} and raw_to_node(raw, "t").capability == "singbox"
    body = raw.singbox.main
    assert body["server_port"] == 443
    assert body["server_ports"] == ["20000:30000", "40000:41000"]
    assert body["obfs"] == {"type": "salamander", "password": "ob"}
    assert body["up_mbps"] == 50 and body["down_mbps"] == 100
    assert body["tls"] == {"enabled": True, "server_name": "sni.example", "alpn": ["h3"]}


def test_insecure_and_pin_sha256_are_not_carried_into_sing_box():
    raw = parse_link("hysteria2://pw@hy.example.com/?insecure=1&pinSHA256=" + "ab" * 32)
    assert "insecure" not in raw.singbox.main["tls"]
    assert "certificate_public_key_sha256" not in raw.singbox.main["tls"]
    assert any("insecure" in warning for warning in raw.warnings)
    assert any("pks" in warning for warning in raw.warnings)  # подсказка, чем закрепить
    pinned = parse_link(f"hysteria2://pw@hy.example.com/?pks={PIN}")
    assert pinned.singbox.main["tls"]["certificate_public_key_sha256"] == [PIN]


def test_tuic_link():
    raw = parse_link(f"tuic://{UUID}:pw@tuic.example:8443?congestion_control=bbr"
                     "&udp_relay_mode=native&alpn=h3&sni=t.example#T")
    body = raw.singbox.main
    assert body["uuid"] == UUID and body["password"] == "pw"
    assert body["congestion_control"] == "bbr" and body["udp_relay_mode"] == "native"
    assert body["tls"]["server_name"] == "t.example" and body["server_port"] == 8443
    assert raw_to_node(raw, "t").capability == "singbox"


def test_anytls_link_uses_an_utls_fingerprint():
    body = parse_link("anytls://pw@any.example:443?sni=a.example&fp=firefox#A").singbox.main
    assert body["password"] == "pw"
    assert body["tls"]["utls"] == {"enabled": True, "fingerprint": "firefox"}


def test_wireguard_link_becomes_an_endpoint():
    raw = parse_link(f"wireguard://{KEY}@203.0.113.7:51820?publickey={PUB}"
                     "&address=10.0.0.2%2F32&reserved=1,2,3&mtu=1280#WG")
    assert raw.singbox.endpoint and raw.singbox.main["type"] == "wireguard"
    peer = raw.singbox.main["peers"][0]
    assert peer["address"] == "203.0.113.7" and peer["reserved"] == [1, 2, 3]
    assert raw.singbox.main["address"] == ["10.0.0.2/32"] and raw.singbox.main["mtu"] == 1280
    assert raw.address == "203.0.113.7" and raw.port == 51820


def test_wireguard_with_amnezia_parameters_is_refused_with_a_reason():
    with pytest.raises(UnsupportedLink, match="AmneziaWG"):
        parse_link(f"wireguard://{KEY}@203.0.113.7:51820?publickey={PUB}"
                   "&address=10.0.0.2%2F32&jc=4&jmin=40#WG")


@pytest.mark.parametrize("bad", [
    "wireguard://short@203.0.113.7:51820?publickey=x&address=10.0.0.2/32",
    f"wireguard://{KEY}@203.0.113.7:51820?publickey={PUB}",
    f"wireguard://{KEY}@203.0.113.7:51820?publickey={PUB}&address=bad",
    f"wireguard://{KEY}@203.0.113.7:51820?publickey={PUB}&address=10.0.0.2/32&reserved=1,2",
])
def test_broken_wireguard_links_are_refused(bad):
    with pytest.raises(ParseError):
        parse_link(bad)


def test_shadowsocks_plugins():
    obfs = parse_link(links.SS_SIP002)
    assert obfs.outbound == {} and obfs.singbox.main["plugin"] == "obfs-local"
    assert obfs.singbox.main["plugin_opts"] == "obfs=http;obfs-host=ob.example.com"
    v2ray = parse_link("ss://YWVzLTEyOC1nY206cGFzcw@203.0.113.5:443?plugin=v2ray-plugin"
                       "%3Btls%3Bhost%3Dv.example#V")
    assert v2ray.singbox.main["plugin"] == "v2ray-plugin"
    assert v2ray.singbox.main["plugin_opts"] == "tls;host=v.example"
    stls = parse_link("ss://YWVzLTEyOC1nY206cGFzcw@203.0.113.5:443?plugin=shadow-tls"
                      "%3Bhost%3Dx.example%3Bpassword%3Dpp%3Bversion%3D3#S")
    assert stls.singbox.main["detour"] == "shadowtls"
    assert stls.singbox.extra[0]["type"] == "shadowtls" and stls.singbox.extra[0]["version"] == 3
    unknown = parse_link("ss://YWVzLTEyOC1nY206cGFzcw@203.0.113.5:443?plugin=foo#U")
    assert not unknown.supported


# --- подписка в формате sing-box --------------------------------------------------------


def _body(*outbounds, endpoints=()):
    return json.dumps({"outbounds": list(outbounds), "endpoints": list(endpoints)})


def test_singbox_subscription_keeps_proxies_and_drops_service_outbounds():
    body = _body(
        {"type": "direct", "tag": "direct"}, {"type": "block", "tag": "block"},
        {"type": "selector", "tag": "sel", "outbounds": ["a"]},
        {"type": "urltest", "tag": "auto", "outbounds": ["a"]},
        {"type": "trojan", "tag": "a", "server": "203.0.113.5", "server_port": 443,
         "password": "p", "routing_mark": 7, "domain_resolver": "x",
         "tls": {"enabled": True, "server_name": "a.example", "insecure": True}},
        {"type": "hysteria2", "tag": "h", "server": "203.0.113.6", "server_ports": ["20000:30000"],
         "password": "p"},
    )
    servers, _meta, warnings = parse_body(body, "sb")
    assert [server.name for server in servers] == ["a", "h"]
    a = servers[0].singbox.main
    assert "routing_mark" not in a and "domain_resolver" not in a  # свои метки задаёт XGW
    assert "insecure" not in a["tls"]
    assert any("insecure" in text for text in warnings)
    assert servers[1].port == 20000 and servers[1].outbound == {}


def test_singbox_server_equal_to_a_link_server_has_the_same_fingerprint():
    link = parse_link("trojan://p@203.0.113.5:443?sni=a.example&security=tls#a")
    body = _body({"type": "trojan", "tag": "a", "server": "203.0.113.5", "server_port": 443,
                  "password": "p", "tls": {"enabled": True, "server_name": "a.example",
                                           "utls": {"enabled": True, "fingerprint": "chrome"}}})
    (server,), _meta, _warnings = parse_body(body, "sb")
    assert raw_to_node(server, "sb").fingerprint == raw_to_node(link, "t").fingerprint
    assert server.outbound["protocol"] == "trojan"  # и Xray его тоже ведёт


def test_features_only_singbox_has_make_the_server_singbox_only():
    body = _body({"type": "vmess", "tag": "m", "server": "203.0.113.5", "server_port": 443,
                  "uuid": UUID, "multiplex": {"enabled": True, "protocol": "h2mux"}})
    (server,), _meta, _warnings = parse_body(body, "sb")
    assert server.outbound == {} and raw_to_node(server, "sb").capability == "singbox"


def test_only_shadowtls_chains_are_carried_over():
    body = _body(
        {"type": "shadowsocks", "tag": "s", "method": "aes-128-gcm", "password": "p",
         "detour": "st"},
        {"type": "shadowtls", "tag": "st", "server": "203.0.113.5", "server_port": 443,
         "version": 3, "password": "q", "tls": {"enabled": True, "server_name": "x.example"}},
        {"type": "trojan", "tag": "via", "server": "203.0.113.6", "server_port": 443,
         "password": "p", "detour": "s"},
    )
    servers, _meta, warnings = parse_body(body, "sb")
    assert [server.name for server in servers] == ["s"]
    assert servers[0].singbox.extra[0]["tag"] == "shadowtls" and servers[0].address == "203.0.113.5"
    assert any("via" in text for text in warnings)


def test_wireguard_endpoint_and_single_outbound_are_parsed():
    endpoint = {"type": "wireguard", "tag": "w", "address": ["10.0.0.2/32"],
                "private_key": "k" * 43 + "=",
                "peers": [{"address": "203.0.113.8", "port": 51820, "public_key": "p" * 43 + "=",
                           "allowed_ips": ["0.0.0.0/0"]}]}
    (server,), _meta, _warnings = parse_body(_body(endpoints=[endpoint]), "sb")
    assert server.singbox.endpoint and server.address == "203.0.113.8"
    single, _meta, _warnings = parse_body(json.dumps(
        {"type": "trojan", "tag": "one", "server": "203.0.113.5", "server_port": 443,
         "password": "p"}), "sb")
    assert [item.name for item in single] == ["one"]


def test_xray_json_servers_get_a_singbox_description_unless_chained():
    plain = {"protocol": "vless", "tag": "proxy", "settings": {"vnext": [{
        "address": "203.0.113.5", "port": 443,
        "users": [{"id": UUID, "encryption": "none"}]}]},
        "streamSettings": {"network": "tcp", "security": "none"}}
    body = json.dumps([{"remarks": "x", "outbounds": [plain, {"protocol": "freedom"}]}])
    (server,), _meta, _warnings = parse_body(body, "x")
    assert server.singbox is not None and raw_to_node(server, "x").capability == "dual"
    hy = {"protocol": "hysteria2", "tag": "hy", "settings": {}}
    servers, _meta, warnings = parse_body(json.dumps({"outbounds": [hy]}), "x")
    assert servers == [] and any("hysteria2" in text for text in warnings)
