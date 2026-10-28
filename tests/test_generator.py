"""Тесты генератора: golden-конфиг и инварианты из раздела 6.6/9 ТЗ."""

import json
import re

import links
from conftest import golden

from xgw import rating
from xgw.config import Config
from xgw.generator.builder import (
    BuildResult,
    applied_nodes,
    assign_suffixes,
    build,
    member_fingerprints,
    probe_state,
    reserve_fingerprint,
    reserve_tag,
    select_nodes,
)
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


def test_device_with_its_own_server_falls_back_to_the_main_balancer():
    """Ф4, 0.2.0: устройство со своим сервером — правило по адресу источника прямо на выход
    сервера (запасной тоже годится), после direct_* и до общего балансировщика. Без
    балансировщика, loopback и пробы в burstObservatory: их появление требовало перезапуска
    Xray. Сервер мёртв (devices_down) или его нет в конфиге — устройство идёт как все."""
    raws, _meta, _warnings = parse_links_text("\n".join(links.FULL_LINKS), "test")
    nodes = [raw_to_node(raw, "test") for raw in raws]
    cfg = Config()
    cfg.filters.max_members = 2
    cfg.routing.direct_ips = ["198.51.100.0/24"]
    selection = select_nodes(nodes, cfg)
    spare = selection.spares[0].fingerprint
    cfg.managed.routes = {"192.168.50.120": spare, "192.168.50.130": "00000000"}
    result = build(cfg, selection, hosts={"de.example.com": ["203.0.113.11"],
                                          "fr.example.com": ["203.0.113.12"]})
    config = result.config
    tag = next(info.tag for info in result.nodes if info.fingerprint == spare)
    assert tag.startswith("spare-")
    assert [balancer["tag"] for balancer in config["routing"]["balancers"]] == ["auto"]
    assert config["burstObservatory"]["subjectSelector"] == ["proxy-"]
    assert not any(outbound["protocol"] == "loopback" for outbound in config["outbounds"])
    rules = config["routing"]["rules"]
    where = {json.dumps(rule, sort_keys=True): index for index, rule in enumerate(rules)}

    def at(rule: dict) -> int:
        return where[json.dumps({"type": "field", **rule}, sort_keys=True)]

    device = at({"source": ["192.168.50.120"], "outboundTag": tag})
    assert at({"ip": ["198.51.100.0/24"], "outboundTag": "direct"}) < device
    assert device < at({"network": "tcp,udp", "balancerTag": "auto"})
    assert not any("192.168.50.130" in json.dumps(rule) for rule in rules)
    down = build(cfg, selection, hosts={"de.example.com": ["203.0.113.11"],
                                        "fr.example.com": ["203.0.113.12"]},
                 devices_down={"192.168.50.120"}).config
    assert not any("192.168.50.120" in json.dumps(rule) for rule in down["routing"]["rules"])


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


def _node(fingerprint: str, name: str, country: str = "nl") -> ServerNode:
    outbound = {"protocol": "vless", "settings": {}}
    return ServerNode(fingerprint, name, country, "vless", "203.0.113.1", 443, outbound, "t")


def test_tag_collision_uses_more_hex():
    first, second, other = _node("abc12345", "A"), _node("abc12399", "B"), _node("abc1ffff", "C")
    third = _node("abc12345"[:4] + "0000", "D", country="de")  # другая страна — не коллизия
    suffixes = assign_suffixes([first, second, other, third])
    assert suffixes["abc1ffff"] == "nl-abc1ff"  # при коллизии — 6 hex
    assert suffixes["abc12345"] == "nl-abc12345"  # 6 hex тоже совпали — 8
    assert suffixes["abc12399"] == "nl-abc12399"
    assert suffixes["abc10000"] == "de-abc1"
    # результат не зависит от порядка обхода
    assert assign_suffixes([third, other, second, first]) == suffixes


def test_member_and_spare_with_same_prefix_get_distinct_probe_tags():
    """Участник и запасной с одинаковыми 4 hex не должны делить один probe-тег."""
    cfg = Config()
    cfg.filters.max_members = 1
    selection = select_nodes([_node("3fa2aaaa", "NL a"), _node("3fa2bbbb", "NL b")], cfg)
    result = build(cfg, selection, hosts={}, probe_password="P" * 32)
    assert [info.tag for info in result.nodes] == ["proxy-nl-3fa2aa", "spare-nl-3fa2bb"]
    inbound_tags = [inbound["tag"] for inbound in result.config["inbounds"]]
    assert len(inbound_tags) == len(set(inbound_tags))
    outbound_tags = [outbound["tag"] for outbound in result.config["outbounds"]]
    assert len(outbound_tags) == len(set(outbound_tags))


def _ports(result: BuildResult) -> dict[str, int]:
    return {info.probe_tag: info.probe_port for info in result.nodes}


def test_probe_ports_and_password_survive_new_server():
    """Новый сервер в подписке не меняет порты и пароль уже работающих probe-inbounds."""
    first, cfg, _ = _build(password=None)
    password, ports = probe_state(first.config)
    assert password and ports == _ports(first)

    raws, _, _ = parse_links_text("\n".join([*links.FULL_LINKS, links.TROJAN_INSECURE]), "test")
    nodes = [raw_to_node(raw, "test") for raw in raws]
    prefer = member_fingerprints(first.config, nodes)
    second = build(
        cfg, select_nodes(nodes, cfg, prefer=prefer), hosts={},
        probe_password=password, probe_ports=ports,
    )
    new_ports = _ports(second)
    assert all(new_ports[tag] == port for tag, port in ports.items())
    assert len(set(new_ports.values())) == len(new_ports) == 5
    assert probe_state(second.config)[0] == password
    # состав участников тоже сохранён: новый сервер стал запасным
    assert [i.tag for i in second.nodes if i.role == "proxy"] == [
        i.tag for i in first.nodes if i.role == "proxy"
    ]


def test_probe_ports_skip_service_ports():
    cfg = Config()
    cfg.xray.probe_port_base = cfg.xray.socks_port  # 10808; следом идёт http_port 10809
    selection = select_nodes([_node("11112222", "A"), _node("33334444", "B")], cfg)
    result = build(cfg, selection, hosts={}, probe_password="P" * 32)
    assert [info.probe_port for info in result.nodes] == [10810, 10811]


def test_probe_ports_skip_panel_core_and_sing_box_ports():
    """Проверки Xray не занимают порты панели, API sing-box и входов sing-box — ни
    работающего (bridge), ни новой сборки, чей перезапуск отложен (avoid_ports): аудит, F-04."""
    from xgw.generator import singbox as singboxing

    cfg = Config()
    cfg.xray.probe_port_base = cfg.panel.port  # 8781, следом app_port 8782
    cfg.core.api_port = 8784
    nodes = [_node("11112222", "A"), _node("33334444", "B"), _node("55556666", "C")]
    bridge = singboxing.Plan(config={}, ports={("ffff0000", "d"): 8783})
    result = build(cfg, select_nodes(nodes, cfg), hosts={}, probe_password="P" * 32,
                   bridge=bridge, avoid_ports={8786})
    assert [info.probe_port for info in result.nodes] == [8785, 8787, 8788]


def test_prefer_keeps_rotation_result():
    """select_nodes(prefer=…) закрепляет состав участников — замена не откатывается."""
    cfg = Config()
    cfg.filters.max_members = 2
    nodes = [_node("aaaa0000", "A"), _node("bbbb0000", "B"), _node("cccc0000", "C")]
    default = select_nodes(nodes, cfg)
    assert [n.fingerprint for n in default.members] == ["aaaa0000", "bbbb0000"]
    rotated = select_nodes(nodes, cfg, prefer=["cccc0000", "bbbb0000"])
    assert [n.fingerprint for n in rotated.members] == ["cccc0000", "bbbb0000"]
    assert [n.fingerprint for n in rotated.spares] == ["aaaa0000"]
    # отпечаток, которого больше нет в подписке, игнорируется; место занимает следующий
    gone = select_nodes(nodes, cfg, prefer=["dddd0000", "cccc0000"])
    assert [n.fingerprint for n in gone.members] == ["cccc0000", "aaaa0000"]


def _priced(nodes, cfg, prices, **kwargs):
    return select_nodes(nodes, cfg, costs=prices, **kwargs)


def test_reserve_is_the_fallback_tag_and_stays_out_of_the_observatory():
    cfg = Config()
    cfg.filters.max_members = 2
    nodes = [_node(fp, fp) for fp in ("aaaa0000", "bbbb0000", "cccc0000")]
    prices = {"aaaa0000": 0.0, "bbbb0000": 0.0, "cccc0000": 1.0}
    selection = _priced(nodes, cfg, prices)
    result = build(cfg, selection, hosts={}, probe_password="P" * 32)
    (balancer,) = result.config["routing"]["balancers"]
    assert balancer["fallbackTag"] == "spare-nl-cccc" == result.fallback_tag
    assert balancer["selector"] == ["proxy-"]
    assert result.config["burstObservatory"]["subjectSelector"] == ["proxy-"]
    assert reserve_tag(result.config) == "spare-nl-cccc"
    assert reserve_fingerprint(result.config, nodes) == "cccc0000"
    # Без классов хуже fallbackTag — первый участник, резервного нет.
    plain = build(cfg, select_nodes(nodes, cfg), hosts={}, probe_password="P" * 32)
    assert plain.config["routing"]["balancers"][0]["fallbackTag"] == "proxy-nl-aaaa"
    assert reserve_tag(plain.config) == "" and reserve_fingerprint(plain.config, nodes) is None
    assert reserve_tag(None) == "" and reserve_tag({"routing": "битый"}) == ""


def test_ipv6_server_dropped_when_ipv6_off():
    cfg = Config()
    node = _node("aaaa0000", "v6")
    node.address = "2001:db8::1"
    selection = select_nodes([node, _node("bbbb0000", "v4")], cfg)
    assert [n.name for n in selection.members] == ["v4"]
    assert any("IPv6" in warning for warning in selection.warnings)


def test_ipv6_server_kept_when_ipv6_is_proxied():
    cfg = Config()
    cfg.network.ipv6 = "proxy"
    node = _node("aaaa0000", "v6")
    node.address = "2001:db8::1"
    selection = select_nodes([node, _node("bbbb0000", "v4")], cfg)
    assert sorted(n.name for n in selection.members) == ["v4", "v6"]
    cfg.network.ipv6 = "что-то"  # непонятное слово — это «off», а не «proxy»
    assert [n.name for n in select_nodes([node, _node("bbbb0000", "v4")], cfg).members] == ["v4"]


def _v6_build(cfg, **kwargs):
    return build(cfg, select_nodes([_node("11112222", "A")], cfg), hosts={}, **kwargs).config


def test_ipv6_proxy_adds_a_second_tproxy_inbound_and_answers_aaaa():
    cfg = Config()
    cfg.network.ipv6 = "proxy"
    config = _v6_build(cfg, ipv6=True)
    tproxy = {i["tag"]: i for i in config["inbounds"] if i["tag"].startswith("tproxy")}
    assert list(tproxy) == ["tproxy-in", "tproxy-in6"]
    assert tproxy["tproxy-in6"]["listen"] == "::1"  # снаружи не виден
    assert tproxy["tproxy-in6"]["port"] == tproxy["tproxy-in"]["port"] == cfg.capture.tproxy_port
    # Остальное — то же, что у IPv4-inbound (UDP, tproxy, сниффинг).
    assert {k: v for k, v in tproxy["tproxy-in6"].items() if k not in ("tag", "listen")} == {
        k: v for k, v in tproxy["tproxy-in"].items() if k not in ("tag", "listen")
    }
    dns_rule = next(r for r in config["routing"]["rules"] if r.get("port") == "53")
    assert dns_rule["inboundTag"] == ["tproxy-in", "tproxy-in6"]
    # Приложения получают AAAA, а прямые подключения умеют ходить по IPv6.
    assert config["dns"]["queryStrategy"] == "UseIP"
    direct = next(o for o in config["outbounds"] if o["tag"] == "direct")
    assert direct["settings"]["domainStrategy"] == "UseIP"
    # Серверы подписки по имени по-прежнему ищутся по IPv4: у них своя стратегия.
    proxy = next(o for o in config["outbounds"] if o["tag"].startswith("proxy-"))
    assert proxy["streamSettings"]["sockopt"]["domainStrategy"] == "UseIPv4"


def _tags(config: dict) -> list[str]:
    return [i["tag"] for i in config["inbounds"] if i["tag"].startswith(("tproxy", "tun"))]


def test_tun_method_adds_the_tun_inbound_and_keeps_tproxy_for_lan():
    cfg = Config()
    cfg.capture.method = "tun"
    config = _v6_build(cfg)
    assert _tags(config) == ["tun-in", "tproxy-in"]
    tun = config["inbounds"][0]
    assert tun["protocol"] == "tun" and tun["settings"] == {"name": "xgwtun0", "mtu": 1500}
    assert "listen" not in tun and "port" not in tun  # TUN не слушает порт
    assert tun["sniffing"] == config["inbounds"][1]["sniffing"]  # домены определяются так же
    dns_rule = next(r for r in config["routing"]["rules"] if r.get("port") == "53")
    assert dns_rule["inboundTag"] == ["tproxy-in", "tun-in"]
    cfg.capture.tun_name = "xgwvpn7"
    assert _v6_build(cfg)["inbounds"][0]["settings"]["name"] == "xgwvpn7"


def test_tun_without_lan_capture_has_no_tproxy_inbound():
    cfg = Config()
    cfg.capture.method = "tun"
    cfg.capture.lan = False
    cfg.capture.containers = False
    config = _v6_build(cfg)
    assert _tags(config) == ["tun-in"]
    dns_rule = next(r for r in config["routing"]["rules"] if r.get("port") == "53")
    assert dns_rule["inboundTag"] == ["tun-in"]
    cfg.capture.local = False  # TUN — это про саму машину; без неё inbound не нужен
    assert _tags(_v6_build(cfg)) == []


def test_containers_get_a_tun_inbound_when_docker_is_there():
    """Контейнеры Docker идут в TUN-интерфейс при любом способе перехвата: с Docker на
    машине (containers_tun) в конфиге есть tun-in и при capture.method = "tproxy"; DNS из
    контейнеров обслуживает тот же dns-out. Без Docker inbound'а TUN нет."""
    cfg = Config()
    assert _tags(_v6_build(cfg)) == ["tproxy-in"]
    config = _v6_build(cfg, containers_tun=True)
    assert sorted(_tags(config)) == ["tproxy-in", "tun-in"]
    tun_in = next(i for i in config["inbounds"] if i["tag"] == "tun-in")
    assert tun_in["settings"]["name"] == cfg.capture.tun_name
    dns_rule = next(r for r in config["routing"]["rules"] if r.get("port") == "53")
    assert sorted(dns_rule["inboundTag"]) == ["tproxy-in", "tun-in"]
    # TPROXY самой машины остаётся: TUN — только для контейнеров.
    assert any(i["tag"] == "tproxy-in" for i in config["inbounds"])


def test_ipv6_over_tun_needs_no_second_inbound():
    cfg = Config()
    cfg.capture.method = "tun"
    cfg.network.ipv6 = "proxy"
    config = _v6_build(cfg, ipv6=True)
    assert _tags(config) == ["tun-in", "tproxy-in"]  # tproxy-in6 не нужен: TUN несёт оба семейства
    assert config["dns"]["queryStrategy"] == "UseIP"


def test_no_ipv6_inbound_by_default_or_without_local_capture(monkeypatch):
    config = _v6_build(Config())
    assert [i["tag"] for i in config["inbounds"] if i["tag"].startswith("tproxy")] == ["tproxy-in"]
    assert config["dns"]["queryStrategy"] == "UseIPv4"
    cfg = Config()
    cfg.network.ipv6 = "proxy"
    cfg.capture.local = False  # устройствам в Wi-Fi IPv6 не выдаётся
    config = _v6_build(cfg, ipv6=True)
    assert [i["tag"] for i in config["inbounds"] if i["tag"].startswith("tproxy")] == ["tproxy-in"]
    # По умолчанию решает ядро: IPv6 в нём нет — Xray не смог бы открыть ::1.
    cfg.capture.local = True
    monkeypatch.setattr("xgw.generator.builder.sysctl.ipv6_usable", lambda *_a: False)
    assert "tproxy-in6" not in [i["tag"] for i in _v6_build(cfg)["inbounds"]]
    monkeypatch.setattr("xgw.generator.builder.sysctl.ipv6_usable", lambda *_a: True)
    assert "tproxy-in6" in [i["tag"] for i in _v6_build(cfg)["inbounds"]]


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


def test_no_tproxy_inbound_when_capture_is_off():
    """Перехват выключен целиком — TPROXY-inbound и правило DNS не нужны (и без
    root не открылись бы)."""
    cfg = Config()
    cfg.capture.lan = cfg.capture.local = False
    result = build(cfg, select_nodes([_node("11112222", "A")], cfg), hosts={})
    assert [i["tag"] for i in result.config["inbounds"]][:2] == ["socks-in", "http-in"]
    assert not any(rule.get("port") == "53" for rule in result.config["routing"]["rules"])
    cfg.capture.local = True  # перехват только своей машины — inbound нужен
    result = build(cfg, select_nodes([_node("11112222", "A")], cfg), hosts={})
    assert result.config["inbounds"][0]["tag"] == "tproxy-in"


def test_tproxy_inbound_accepts_udp():
    """UDP у inbound tunnel включает поле network: Xray 26.3.27 не знает
    allowedNetwork и молча его игнорирует — без network перехватывался бы только
    TCP, а обычный DNS и QUIC устройств терялись бы (найдено на стенде)."""
    cfg = Config()
    tproxy = build(cfg, select_nodes([_node("11112222", "A")], cfg), hosts={}).config["inbounds"][0]
    assert tproxy["settings"]["network"] == "tcp,udp"
    assert tproxy["settings"]["followRedirect"] is True
    assert tproxy["listen"] == "127.0.0.1"  # из LAN порт не виден
    assert tproxy["streamSettings"]["sockopt"] == {"tproxy": "tproxy"}


def test_dns_servers_with_custom_port():
    """Порт не 53 Xray принимает только объектом {"address", "port"}."""
    cfg = Config()
    cfg.dns.proxy_servers = ["1.1.1.1", "203.0.113.53:5353"]
    cfg.dns.direct_servers = ["203.0.113.54:5354"]
    config = build(cfg, select_nodes([_node("11112222", "A")], cfg), hosts={}).config
    assert config["dns"]["servers"] == [
        {"address": "203.0.113.54", "port": 5354, "skipFallback": True,
         "domains": cfg.routing.direct_domains},
        "1.1.1.1",
        {"address": "203.0.113.53", "port": 5353},
    ]
    direct_rule = next(r for r in config["routing"]["rules"] if r.get("ip") == ["203.0.113.54"])
    assert direct_rule["outboundTag"] == "direct"


def test_applied_nodes_reads_running_layout():
    """Теги, роли и порты проб — из применённого конфига; отпечаток — если узел опознан."""
    result, _cfg, selection = _build()
    nodes = [*selection.members, *selection.spares]
    view = applied_nodes(result.config, nodes)
    assert [(i.tag, i.role, i.probe_tag, i.probe_port, i.fingerprint) for i in view] == [
        (i.tag, i.role, i.probe_tag, i.probe_port, i.fingerprint) for i in result.nodes
    ]
    blind = applied_nodes(result.config)  # подписка недоступна — следить за ядром всё равно можно
    assert [i.tag for i in blind] == [i.tag for i in result.nodes]
    assert all(len(i.fingerprint) == 4 for i in blind)
    assert applied_nodes(None) == [] and applied_nodes({"outbounds": [{"tag": "direct"}]}) == []


def test_host_header_of_websocket_and_httpupgrade_becomes_the_host_field():
    """JSON-подписки приносят streamSettings как есть — с `headers.Host`. Xray 26.3.27 у
    WebSocket объявил такую запись устаревшей (предупреждение в журнале при каждом
    запуске), а у HTTPUpgrade отклоняет вовсе; в конфиг идёт отдельное поле `host`."""
    def with_stream(fingerprint: str, stream: dict) -> ServerNode:
        node = _node(fingerprint, "ws")
        node.outbound = {**node.outbound, "streamSettings": stream}
        return node

    nodes = [
        with_stream("aaaa0001", {"network": "ws", "wsSettings": {
            "path": "/ws", "headers": {"Host": "cdn.example.org"}}}),
        with_stream("aaaa0002", {"network": "httpupgrade", "httpupgradeSettings": {
            "path": "/up", "headers": {"host": "up.example.org", "X-Extra": "1"}}}),
        # Явный host главнее заголовка; заголовок всё равно убирается.
        with_stream("aaaa0003", {"network": "ws", "wsSettings": {
            "path": "/", "host": "explicit.example.org", "headers": {"Host": "old.example.org"}}}),
        # Список значений — так записан Host у http-обфускации tcp: берётся первое.
        with_stream("aaaa0004", {"network": "ws", "wsSettings": {
            "headers": {"Host": ["a.example.org"]}}}),
        # Обфускация tcp/http — другое поле и другая запись: её не трогаем.
        with_stream("aaaa0005", {"network": "tcp", "tcpSettings": {"header": {
            "type": "http", "request": {"headers": {"Host": ["h.example.org"]}}}}}),
    ]
    cfg = Config()
    originals = [repr(node.outbound) for node in nodes]
    config = build(cfg, select_nodes(nodes, cfg), hosts={}, probe_password="P" * 32).config
    streams = {
        outbound["tag"].rsplit("-", 1)[1]: outbound["streamSettings"]
        for outbound in config["outbounds"] if "streamSettings" in outbound
        and outbound["tag"].startswith(("proxy-", "spare-"))
    }
    assert streams["aaaa0001"]["wsSettings"] == {"path": "/ws", "host": "cdn.example.org"}
    assert streams["aaaa0002"]["httpupgradeSettings"] == {
        "path": "/up", "host": "up.example.org", "headers": {"X-Extra": "1"}}
    assert streams["aaaa0003"]["wsSettings"] == {"path": "/", "host": "explicit.example.org"}
    assert streams["aaaa0004"]["wsSettings"] == {"host": "a.example.org"}
    assert streams["aaaa0005"]["tcpSettings"]["header"]["request"]["headers"] == {
        "Host": ["h.example.org"]}
    assert [repr(node.outbound) for node in nodes] == originals  # исходные узлы не тронуты
    assert '"Host"' not in json.dumps([streams[key] for key in ("aaaa0001", "aaaa0002")])


def test_selection_counts_what_was_dropped():
    cfg = Config()
    cfg.filters.max_members = 1
    cfg.managed.disabled = ["cccc0000"]
    service = _node("aaaa0000", "service")
    service.address = "127.0.0.1"
    gone = _node("bbbb0000", "gone")
    gone.address = "gone.example.net"
    nodes = [service, gone, _node("cccc0000", "off"), _node("dddd0000", "expire 2026"),
             _node("eeee0000", "A"), _node("eeee0000", "A copy"), _node("ffff0000", "B")]
    selection = select_nodes(nodes, cfg, dead={"gone.example.net"})
    assert selection.stats == {
        "total": 7, "junk": 1, "ipv6": 0, "filter": 1, "dns": 1, "excluded": 1, "duplicates": 1,
        "core": 0}
    assert [n.name for n in [*selection.members, *selection.spares]] == ["A", "B"]
    assert any("домен gone.example.net не разрешается" in text for text in selection.warnings)
    # Без карантина тот же сервер идёт в работу.
    assert select_nodes(nodes, cfg).stats["dns"] == 0


def test_members_are_the_best_rated_from_every_subscription():
    """Issue #2 и раздел 3 рекомендаций: участники — лучшие по рейтингу из всех подписок.
    «Средний» намного быстрее «высокого» — в участниках «средний»; чуть медленнее —
    предпочитается «высокий». x100 и подписка с исчерпанной квотой в участники не попадают;
    резервный — самый дешёвый лимитированный дороже самого дешёвого участника."""
    raws, _meta, _warnings = parse_links_text("\n".join(links.FULL_LINKS), "test")
    nodes = [raw_to_node(raw, "test") for raw in raws if raw.name]
    unique = sorted({node.fingerprint for node in nodes})
    high, medium, x10, x100 = unique[:4]
    cfg = Config()
    cfg.filters.max_members = 1
    cfg.managed.priority = {high: "high"}
    costs = dict.fromkeys(unique, 0.0)
    costs.update({x10: 10.0, x100: 100.0})

    def facts(fingerprint, mbps):
        return rating.score(rating.Facts(
            level="high" if fingerprint == high else "medium", price=costs[fingerprint],
            mbps=mbps, rtt_ms=60.0))

    scores = {fingerprint: facts(fingerprint, 20.0) for fingerprint in unique}
    scores[high] = facts(high, 40.0)
    scores[medium] = facts(medium, 100.0)  # в 2,5 раза быстрее — больше 1,86
    chosen = select_nodes(nodes, cfg, scores=scores, costs=costs)
    assert [node.fingerprint for node in chosen.members] == [medium]
    scores[medium] = facts(medium, 60.0)  # в 1,5 раза — «высокий» лучше
    chosen = select_nodes(nodes, cfg, scores=scores, costs=costs)
    assert [node.fingerprint for node in chosen.members] == [high]
    assert chosen.reserve is not None and chosen.reserve.fingerprint == x10
    cfg.filters.max_members = len(unique)
    chosen = select_nodes(nodes, cfg, scores=scores, costs=costs)
    assert x100 not in {node.fingerprint for node in chosen.members}
    chosen = select_nodes(nodes, cfg, scores=scores, costs=costs, quota_low={x10})
    assert x10 not in {node.fingerprint for node in chosen.members}


def test_rating_balance_matches_the_recommendations():
    """Раздел 3: «высокий × x10» опережает «средний × безлимит», незамеренный живой сервер —
    не ноль, задержка до 50 мс не штрафуется, x100 и квота на исходе — ноль."""
    assert rating.priority_factor("high") * rating.cost_factor(10.0) > 1.0
    assert rating.cost_factor(1.0) == 0.95 and abs(rating.cost_factor(10.0) - 0.75) < 1e-9
    assert rating.cost_factor(100.0) == 0 and rating.cost_factor(1.0, quota_low=True) == 0
    assert rating.score(rating.Facts()) > 0
    assert rating.latency_factor(40.0) == rating.latency_factor(50.0) == 1.0
    assert abs(rating.health_factor(1.0, 1.0) - 0.15) < 1e-9  # 1 − 0,6 − 0,25
    assert rating.quota_low({"total": 100, "upload": 0, "download": 96})
    assert not rating.quota_low({"total": 0})


def test_xhttp_download_leg_gets_the_bypass_mark():
    """Пятый аудит, T1: отдельный канал загрузки XHTTP (downloadSettings — прямо в
    xhttpSettings или в extra) у Xray 26.10.21 — свой StreamConfig со своим sockopt; без метки
    его соединение снова попало бы в перехват. Свои поля канала остаются; мост к 127.0.0.1
    метку не получает."""
    from xgw.generator.builder import _apply_sockopt

    for inline in (True, False):
        down = {"address": "down.example.com", "port": 443, "network": "xhttp",
                "sockopt": {"mark": 777, "tcpFastOpen": True},
                "xhttpSettings": {"downloadSettings": {"address": "deeper.example.com"}}}
        options = {"downloadSettings": down}
        xhttp = {"path": "/up", "mode": "packet-up", **(options if inline else {})}
        if not inline:
            xhttp["extra"] = options
        outbound = {"streamSettings": {"network": "xhttp", "xhttpSettings": xhttp}}
        _apply_sockopt(outbound, 2)
        assert outbound["streamSettings"]["sockopt"] == {"mark": 2, "domainStrategy": "UseIPv4"}
        assert down["sockopt"] == {"mark": 2, "domainStrategy": "UseIPv4", "tcpFastOpen": True}
        deeper = down["xhttpSettings"]["downloadSettings"]
        assert deeper["sockopt"]["mark"] == 2
    bridge = {"address": "127.0.0.1", "port": 1080}
    outbound = {"streamSettings": {"xhttpSettings": {"downloadSettings": bridge}}}
    _apply_sockopt(outbound, 2)
    assert "sockopt" not in bridge
