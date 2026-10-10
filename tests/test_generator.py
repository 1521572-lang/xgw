"""Тесты генератора: golden-конфиг и инварианты из раздела 6.6/9 ТЗ."""

import re

import links
from conftest import golden

from xgw.config import Config
from xgw.generator.builder import BuildResult, _unique_tag, build, select_nodes
from xgw.model import ServerNode, raw_to_node
from xgw.parsers.common import parse_links_text


def _build(password: str = "P" * 32, link_list: list[str] = links.FULL_LINKS):
    raws, _meta, _warnings = parse_links_text("\n".join(link_list), "test")
    nodes = [raw_to_node(raw, "test") for raw in raws]
    cfg = Config()
    cfg.filters.max_members = 2  # из 4 ссылок: 2 участника + 2 запасных
    selection = select_nodes(nodes, cfg)
    hosts = {
        "de.example.com": ["203.0.113.11"],
        "fr.example.com": ["203.0.113.12"],
    }
    result = build(cfg, selection, hosts=hosts, probe_password=password)
    return result, cfg, selection


def test_full_config_golden():
    result, _cfg, _selection = _build()
    expected = golden("full_config.json", result.config)
    assert result.config == expected


def test_invariants():
    result, cfg, _selection = _build()
    config = result.config
    proxy_tags = [info.tag for info in result.nodes if info.role == "proxy"]
    spare_tags = [info.tag for info in result.nodes if info.role == "spare"]
    assert len(proxy_tags) == 2 and len(spare_tags) == 2

    # первый outbound — proxy-узел; direct, block, dns-out — в конце
    assert config["outbounds"][0]["tag"].startswith("proxy-")
    assert [outbound["tag"] for outbound in config["outbounds"][-3:]] == [
        "direct",
        "block",
        "dns-out",
    ]

    # у каждого proxy/spare есть sockopt.mark и domainStrategy UseIPv4
    for outbound in config["outbounds"]:
        if outbound["tag"].startswith(("proxy-", "spare-")):
            sockopt = outbound["streamSettings"]["sockopt"]
            assert sockopt["mark"] == cfg.capture.mark_bypass
            assert sockopt["domainStrategy"] == "UseIPv4"

    # правила проб — первые, DNS — сразу за ними, catch-all — последний
    rules = config["routing"]["rules"]
    probe_rule_count = len(result.nodes)
    probe_rules = rules[:probe_rule_count]
    assert all(rule["inboundTag"][0].startswith("probe-") for rule in probe_rules)
    dns_rule = rules[probe_rule_count]
    assert dns_rule["port"] == "53" and dns_rule["outboundTag"] == "dns-out"
    assert rules[-1] == {"type": "field", "network": "tcp,udp", "balancerTag": "auto"}
    direct_rule = [r for r in rules if r.get("ip") == ["77.88.8.8"]]
    assert direct_rule and direct_rule[0]["outboundTag"] == "direct"

    # балансировщик и fallbackTag
    balancer = config["routing"]["balancers"][0]
    assert balancer["selector"] == ["proxy-"]
    assert balancer["strategy"] == {"type": "leastPing"}
    assert balancer["fallbackTag"] == proxy_tags[0]

    # GET-проба в burstObservatory
    ping = config["burstObservatory"]["pingConfig"]
    assert ping["httpMethod"] == "GET"
    assert ping["interval"] == cfg.probe.interval
    assert config["burstObservatory"]["subjectSelector"] == ["proxy-"]

    # в dns.servers нет localhost
    for server in config["dns"]["servers"]:
        address = server if isinstance(server, str) else server["address"]
        assert address not in ("localhost", "127.0.0.53", "127.0.0.1")

    # теги и порты проб
    ports = [info.probe_port for info in result.nodes]
    assert ports == sorted(ports) and len(set(ports)) == len(ports)
    assert ports[0] == cfg.xray.probe_port_base
    for info in result.nodes:
        assert re.fullmatch(r"(proxy|spare)-[a-z]{2}-[0-9a-f]{4,8}", info.tag)
        assert info.probe_tag == "probe-" + info.tag.split("-", 1)[1]

    # все служебные inbounds слушают только loopback
    for inbound in config["inbounds"]:
        assert inbound["listen"] == "127.0.0.1"

    # домены серверов попали в dns.hosts
    assert config["dns"]["hosts"]["de.example.com"] == ["203.0.113.11"]

    # policy.connIdle из конфига
    assert config["policy"]["levels"]["0"]["connIdle"] == cfg.routing.conn_idle_s


def test_tags_stable_when_input_shuffled():
    straight, _, _ = _build()
    shuffled, _, _ = _build(link_list=list(reversed(links.FULL_LINKS)))
    assert straight.config == shuffled.config


def test_tag_collision_uses_more_hex():
    taken: set[str] = set()
    first = ServerNode("abc12345", "A", "nl", "vless", "203.0.113.1", 443, {}, "t")
    second = ServerNode("abc12399", "B", "nl", "vless", "203.0.113.2", 443, {}, "t")
    tag1 = _unique_tag("proxy", first, taken)
    tag2 = _unique_tag("proxy", second, taken)
    assert tag1 == "proxy-nl-abc1"
    assert tag2 == "proxy-nl-abc123"  # при коллизии — 6 hex


def test_select_filters_and_junk():
    cfg = Config()
    raws, _, _ = parse_links_text(
        "\n".join(
            [
                links.VLESS_REALITY,
                links.VLESS_REALITY,  # дубль по отпечатку
                links.VLESS_JUNK_ADDRESS,
                links.VLESS_EXPIRED_NAME,  # «Истекает» отсекается exclude_regex
                links.VLESS_WS,
            ]
        ),
        "test",
    )
    nodes = [raw_to_node(raw, "test") for raw in raws]
    selection = select_nodes(nodes, cfg)
    names = [node.name for node in selection.members + selection.spares]
    assert names.count("🇳🇱 NL-1") == 1  # дубль схлопнут
    assert "junk-zero" not in names
    assert not any("Истекает" in name for name in names)
    assert "🇩🇪 DE-1" in names

    cfg.filters.include_regex = "NL"
    selection_nl = select_nodes(nodes, cfg)
    assert [node.country for node in selection_nl.members + selection_nl.spares] == ["nl"]


def test_build_requires_members():
    import pytest

    from xgw.generator.builder import BuildError, Selection

    with pytest.raises(BuildError):
        build(Config(), Selection(), hosts={})


def test_max_members_moves_rest_to_spares():
    raws, _, _ = parse_links_text("\n".join(links.FULL_LINKS), "test")
    nodes = [raw_to_node(raw, "test") for raw in raws]
    cfg = Config()
    cfg.filters.max_members = 1
    selection = select_nodes(nodes, cfg)
    result = build(cfg, selection, hosts={}, probe_password="P" * 32)
    roles = [info.role for info in result.nodes]
    assert roles == ["proxy", "spare", "spare", "spare"]
    assert isinstance(result, BuildResult)
