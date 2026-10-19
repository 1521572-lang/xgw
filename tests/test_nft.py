"""Правила nftables: генерация текста и проверка `nft -c -f` (без root — пропуск)."""

import dataclasses
import os
import shutil
import subprocess
import sys

import pytest
from fakenet import FakeKernel

from xgw.config import Config, Network
from xgw.net import nft
from xgw.net.cmd import CommandError


def _cfg(**network) -> Config:
    cfg = Config()
    cfg.network.lan_if = "lan0"
    for key, value in network.items():
        setattr(cfg.network, key, value)
    return cfg


def _render(cfg: Config, capture: bool = True, uids=()) -> str:
    rules, _warnings = nft.build_rules(cfg, capture=capture, time_uids=uids)
    return nft.render(rules)


def _chain(text: str, name: str) -> list[str]:
    """Правила цепочки без заголовка."""
    lines = text.split(f"chain {name} {{")[1].split("}\n")[0].strip().splitlines()
    return [line.strip() for line in lines[1:]]


def test_gateway_with_lan_and_local_capture():
    text = _render(_cfg())
    # Таблица заменяется атомарно и только своя: никакого flush ruleset.
    assert text.startswith("table ip xgw\ndelete table ip xgw\ntable ip xgw {\n")
    assert "flush" not in text
    for chain in ("prerouting", "output", "loopback_guard", "dns_direct", "forward", "postrouting",
                  "containers"):
        assert f"chain {chain} {{" in text

    prerouting = _chain(text, "prerouting")
    assert "hook prerouting priority mangle" in text
    assert prerouting == [
        'iifname "docker0" goto containers',  # контейнеры Docker — своя цепочка
        'iifname "br-*" goto containers',
        'iifname != { "lan0", "lo" } return',  # входящие из интернета в Xray не попадают
        "meta l4proto != { tcp, udp } return",
        'iifname "lo" meta mark != 0x1 return',
        "ip saddr @bypass4 return",
        "fib daddr type local th dport != 53 return",
        "ip daddr @reserved4 th dport != 53 return",
        "meta l4proto { tcp, udp } counter tproxy to 127.0.0.1:12345 meta mark set 0x1 accept",
    ]

    output = _chain(text, "output")
    assert output[0] == "meta mark 0x2 return"  # сокеты Xray и прямые запросы XGW
    assert output[1] == "ct direction reply return"  # ответы на входящие (SSH на шлюз)
    assert "udp sport 68 return" in output  # DHCP-клиент WAN
    assert output[-1] == "meta l4proto { tcp, udp } counter meta mark set 0x1"
    assert output.index("ip daddr @reserved4 th dport != 53 return") < len(output) - 1

    forward = _chain(text, "forward")
    assert "policy drop" in text.split("chain forward {")[1].splitlines()[1]
    assert forward[0] == 'iifname != "lan0" oifname != "lan0" accept'  # чужой форвардинг
    assert "tcp flags syn tcp option maxseg size set rt mtu" in forward
    assert 'iifname "lan0" oifname != "lan0" ip saddr @bypass4 counter accept' in forward
    assert 'iifname "lan0" oifname != "lan0" meta l4proto icmp counter accept' in forward
    assert 'iifname "lan0" oifname != "lan0" counter accept' not in forward  # fail-closed
    assert _chain(text, "postrouting") == ['iifname "lan0" oifname != "lan0" counter masquerade']
    dns_direct = _chain(text, "dns_direct")[0]  # DNS устройств в обход VPN — на прямой резолвер
    assert "ip saddr @bypass4 meta l4proto { tcp, udp } th dport 53" in dns_direct
    assert dns_direct.endswith("dnat to 77.88.8.8")


def test_containers_go_through_xray_but_their_published_ports_answer_directly():
    """F4 отчёта 14.10: контейнер Docker выходил в интернет с адресом провайдера, пока
    сама машина шла через VPN. Его трафик — транзит с мостов docker0 и br-*: теперь у него
    своя цепочка, которая ставит метку mark_containers (по ней маршрут ведёт в TUN — с
    TPROXY мосты Docker не дружат). Ответы опубликованных портов (docker run -p 8080:80) —
    это ct direction reply, они в Xray не попадают; частные сети и сама машина — тоже мимо,
    а DNS (порт 53) к частным резолверам перехватывается, как у устройств LAN."""
    text = _render(_cfg())
    assert text.index("chain containers {") < text.index("chain prerouting {")
    body = text.split("chain containers {")[1].split("}\n")[0].strip().splitlines()
    assert [line.strip() for line in body] == [
        "meta l4proto != { tcp, udp } return",
        "ct direction reply return",
        "fib daddr type local return",
        "ip daddr @reserved4 th dport != 53 return",
        "meta l4proto { tcp, udp } counter meta mark set 0x3",
    ]
    # Обычная цепочка, без hook: в неё только переходят из prerouting.
    assert "hook" not in text.split("chain containers {")[1].split("chain prerouting")[0]
    # Выключено в конфиге либо перехват снят — ни цепочки, ни переходов в неё.
    cfg = _cfg()
    cfg.capture.containers = False
    assert "containers" not in _render(cfg)
    assert "containers" not in _render(_cfg(), capture=False)
    off = Config()
    off.capture.lan = off.capture.local = False
    assert nft.build_rules(off, capture=True, time_uids=())[0].containers == ()


def test_loopback_guard_refuses_marked_packets_to_loopback():
    """Сокеты direct в Xray помечены mark_bypass; имя из direct_domains, указывающее
    на 127.0.0.1, не должно привести их к службам самого шлюза (ASSUMPTIONS, п. 119)."""
    text = _render(_cfg())
    assert "hook output priority filter" in text.split("chain loopback_guard {")[1].splitlines()[1]
    assert _chain(text, "loopback_guard") == ["meta mark 0x2 ip daddr 127.0.0.0/8 counter reject"]
    cfg = _cfg()
    cfg.capture.mark_bypass = 255
    assert _chain(_render(cfg), "loopback_guard") == [
        "meta mark 0xff ip daddr 127.0.0.0/8 counter reject"
    ]
    # Нужна при любом перехвате: и когда Xray обслуживает только LAN, и только машину.
    lan_only = _cfg()
    lan_only.capture.local = False
    assert "chain loopback_guard {" in _render(lan_only)
    assert "chain loopback_guard {" in _render(Config())
    # Перехват снят — Xray трафик устройств не обслуживает, цепочка не нужна.
    assert "loopback_guard" not in _render(_cfg(), capture=False)


def test_reserved_set_has_ranges_from_xray_guide_and_excludes():
    cfg = _cfg()
    cfg.capture.exclude_cidrs = ["203.0.113.0/24", "10.1.0.0/16", "мусор"]
    rules, warnings = nft.build_rules(cfg, capture=True, time_uids=())
    assert rules.reserved == (
        "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
        "192.0.0.0/24", "192.168.0.0/16", "203.0.113.0/24",
        "224.0.0.0/3",  # 224/4, 240/4 и 255.255.255.255 — одним диапазоном, без пересечений
    )
    assert any("exclude_cidrs" in warning and "мусор" in warning for warning in warnings)
    assert "elements = { 10.0.0.0/8, 100.64.0.0/10," in nft.render(rules)


def test_bypass_hosts_mac_goes_through_static_lease():
    cfg = _cfg(
        static_leases=["AA-BB-CC-DD-EE-FF,192.168.50.20,tv"],
        bypass_hosts=["aa:bb:cc:dd:ee:ff", "192.168.50.30", "11:22:33:44:55:66", "не адрес"],
    )
    rules, warnings = nft.build_rules(cfg, capture=True, time_uids=())
    assert rules.bypass == ("192.168.50.20", "192.168.50.30")
    assert any("11:22:33:44:55:66" in warning and "аренды" in warning for warning in warnings)
    assert any("не адрес" in warning for warning in warnings)
    assert "elements = { 192.168.50.20, 192.168.50.30 }" in nft.render(rules)


def test_only_this_machine():
    """lan_if пуст: ни форвардинга, ни правил для LAN — только output и lo."""
    cfg = Config()
    text = _render(cfg)
    assert _chain(text, "prerouting")[2] == 'iifname != "lo" return'
    assert "chain output {" in text
    for absent in ("bypass4", "chain forward", "chain postrouting", "chain dns_direct", "lan"):
        assert absent not in text
    rules, _ = nft.build_rules(cfg, capture=True, time_uids=())
    text6 = nft.render6(rules)  # IPv6 машины закрыт (v6_guard), форвардинга IPv6 нет
    assert "chain v6_guard {" in text6 and "chain forward" not in text6


def test_lan_without_local_capture():
    cfg = _cfg()
    cfg.capture.local = False
    text = _render(cfg)
    assert "chain output {" not in text
    prerouting = _chain(text, "prerouting")
    assert prerouting[2] == 'iifname != "lan0" return'
    assert not any('"lo"' in rule for rule in prerouting)


def test_capture_removed_leaves_plain_router():
    """xgw disable и fail_mode = open: перехвата нет, сеть ходит напрямую."""
    text = _render(_cfg(), capture=False)
    assert "chain prerouting {" not in text and "chain output {" not in text
    assert "tproxy" not in text
    assert 'iifname "lan0" oifname != "lan0" counter accept' in _chain(text, "forward")
    assert "masquerade" in text
    # DNS-запросы к шлюзу теперь не обслуживает никто — все уходят на прямой резолвер.
    assert _chain(text, "dns_direct") == [
        'iifname "lan0" meta l4proto { tcp, udp } th dport 53 fib daddr type local '
        "counter dnat to 77.88.8.8"
    ]


def test_nothing_to_load_without_lan_and_capture():
    cfg = Config()
    cfg.capture.local = False  # режим none: перехватывать нечего
    rules, _ = nft.build_rules(cfg, capture=False, time_uids=())
    assert rules.empty and nft.render(rules) == "" and nft.render6(rules) == ""
    # Перехват машины снят (xgw disable): IPv4 напрямую, а IPv6 (network.ipv6 = off) закрыт.
    off, _ = nft.build_rules(Config(), capture=False, time_uids=())
    assert off.empty and nft.render(off) == "" and "chain v6_guard {" in nft.render6(off)
    kernel = FakeKernel()
    kernel.tables[("ip", "xgw")] = "table ip xgw {\n}\n"
    assert nft.apply(rules, kernel) == []
    assert kernel.tables == {}  # прежняя таблица убрана


def test_explicit_wan_marks_time_service_and_dns_port():
    cfg = _cfg(wan_if="wan0")
    cfg.capture.mark_proxy, cfg.capture.mark_bypass, cfg.capture.tproxy_port = 17, 255, 7893
    cfg.dns.direct_servers = ["resolver.example.com", "203.0.113.53:5353"]
    text = _render(cfg, uids=(988,))
    assert 'iifname "lan0" oifname "wan0" counter masquerade' in text
    assert "tproxy to 127.0.0.1:7893 meta mark set 0x11 accept" in text
    output = _chain(text, "output")
    assert output[0] == "meta mark 0xff return"
    # Служба времени — мимо перехвата: без точного времени не поднимется Reality.
    assert "meta skuid 988 udp dport 123 return" in output
    assert "meta skuid 988 tcp dport 4460 return" in output
    assert "dnat to 203.0.113.53:5353" in text  # первый direct_server, записанный адресом


def test_bad_interface_name_never_reaches_rules():
    cfg = _cfg(lan_if='lan0" accept; #', wan_if="wan 0")
    rules, warnings = nft.build_rules(cfg, capture=True, time_uids=())
    assert rules.lan_if == "" and rules.wan_if == ""
    assert sum("недопустимое имя интерфейса" in warning for warning in warnings) == 2
    assert "accept; #" not in nft.render(rules)


def test_missing_direct_dns_is_reported():
    cfg = _cfg()
    cfg.dns.direct_servers = []
    rules, warnings = nft.build_rules(cfg, capture=True, time_uids=())
    assert rules.dns_direct == "" and "chain dns_direct" not in nft.render(rules)
    assert any("direct_servers" in warning for warning in warnings)


def test_ip6_table_blocks_forwarding_through_lan():
    rules, _ = nft.build_rules(_cfg(), capture=True, time_uids=())
    text = nft.render6(rules)
    assert text.startswith("table ip6 xgw6\ndelete table ip6 xgw6\ntable ip6 xgw6 {\n")
    assert 'iifname "lan0" drop' in text and 'oifname "lan0" drop' in text


def _proxy6(**network):
    return _cfg(ipv6="proxy", **network)


def test_ip6_table_without_proxy_has_only_the_forward_block():
    text = nft.render6(nft.build_rules(_cfg(), capture=True, time_uids=())[0])
    assert "chain prerouting" not in text and "chain output" not in text
    assert "reserved6" not in text and "tproxy" not in text


def test_ip6_table_captures_the_machine_when_ipv6_is_proxied():
    rules, warnings = nft.build_rules(_proxy6(), capture=True, time_uids=(100,))
    assert warnings == [] and rules.capture6
    text = nft.render6(rules)
    assert text.startswith("table ip6 xgw6\ndelete table ip6 xgw6\ntable ip6 xgw6 {\n")
    assert "flush" not in text
    assert _chain(text, "prerouting") == [
        'iifname != "lo" return',  # только своя машина: LAN IPv6 не получает
        "meta l4proto != { tcp, udp } return",
        "meta mark != 0x1 return",
        "fib daddr type local th dport != 53 return",
        "ip6 daddr @reserved6 th dport != 53 return",
        "meta l4proto { tcp, udp } counter tproxy ip6 to [::1]:12345 meta mark set 0x1 accept",
    ]
    output = _chain(text, "output")
    assert output[:3] == [
        "meta mark 0x2 return", "ct direction reply return", "meta l4proto != { tcp, udp } return",
    ]
    assert "udp sport 546 return" in output  # DHCPv6-клиент
    assert "meta skuid 100 udp dport 123 return" in output  # служба времени мимо перехвата
    assert output[-1] == "meta l4proto { tcp, udp } counter meta mark set 0x1"
    # Прямой запрос Xray не должен попасть на службы шлюза через ::1 (как в ip xgw).
    assert _chain(text, "loopback_guard") == ["meta mark 0x2 ip6 daddr ::1 counter reject"]
    # Запрет форвардинга IPv6 из LAN остаётся: устройства IPv6 не получают.
    assert _chain(text, "forward") == ['iifname "lan0" drop', 'oifname "lan0" drop']
    assert "elements = { ::/127, fc00::/7, fe80::/10, ff00::/8 }" in text


def test_ip6_capture_follows_the_capture_mode_and_local_flag():
    rules, _ = nft.build_rules(_proxy6(), capture=False, time_uids=())
    assert not rules.capture6 and "tproxy" not in nft.render6(rules)  # xgw disable
    cfg = _proxy6()
    cfg.capture.local = False
    rules, _ = nft.build_rules(cfg, capture=True, time_uids=())
    assert not rules.capture6  # устройствам IPv6 не выдаётся — перехватывать нечего
    # Без LAN таблица нужна только для IPv6 самой машины: при «off» — закрыть его.
    rules, _ = nft.build_rules(Config(), capture=True, time_uids=())
    text6 = nft.render6(rules)
    assert "chain v6_guard {" in text6 and "chain prerouting" not in text6
    only = Config()
    only.network.ipv6 = "proxy"
    rules, _ = nft.build_rules(only, capture=True, time_uids=())
    text = nft.render6(rules)
    assert "chain prerouting" in text and "chain forward" not in text


def test_unknown_ipv6_value_is_off():
    rules, _ = nft.build_rules(_cfg(ipv6="auto"), capture=True, time_uids=())
    assert not rules.capture6


def test_exclude_cidrs_may_name_ipv6_networks_only_when_ipv6_is_proxied():
    cfg = _proxy6()
    cfg.capture.exclude_cidrs = ["2001:db8:77::/48", "203.0.113.0/24", "мусор"]
    rules, warnings = nft.build_rules(cfg, capture=True, time_uids=())
    assert "2001:db8:77::/48" in rules.reserved6 and "203.0.113.0/24" in rules.reserved
    assert any("мусор" in warning for warning in warnings)
    cfg = _cfg()
    cfg.capture.exclude_cidrs = ["2001:db8:77::/48"]
    rules, warnings = nft.build_rules(cfg, capture=True, time_uids=())
    assert "2001:db8:77::/48" not in rules.reserved6
    assert any("IPv6" in warning and "2001:db8:77::/48" in warning for warning in warnings)


def test_apply_fails_when_proxied_ipv6_rules_cannot_be_loaded():
    """Без таблицы IPv6 машины ушёл бы мимо перехвата: это ошибка, а не предупреждение."""
    kernel = FakeKernel()
    kernel.refuse_ip6 = True
    rules, _ = nft.build_rules(_proxy6(), capture=True, time_uids=())
    with pytest.raises(CommandError):
        nft.apply(rules, kernel)
    rules, _ = nft.build_rules(_cfg(), capture=True, time_uids=())
    # IPv6 в ядре нет: Capture.rules снимает v6_guard (закрывать нечего).
    rules = dataclasses.replace(rules, v6_guard=False)
    assert len(nft.apply(rules, kernel)) == 1  # без proxy — только предупреждение


def _tun(**network):
    cfg = _cfg(**network)
    cfg.capture.method = "tun"
    return cfg


def test_tun_leaves_tproxy_for_lan_only_and_keeps_the_marking_chain():
    rules, warnings = nft.build_rules(_tun(), capture=True, time_uids=())
    assert warnings == [] and rules.tun and rules.tun_name == "xgwtun0"
    text = nft.render(rules)
    # Сеть LAN — по-прежнему TPROXY, но на lo он больше не нужен.
    assert _chain(text, "prerouting") == [
        'iifname "docker0" goto containers',  # контейнеры Docker — своя цепочка
        'iifname "br-*" goto containers',
        'iifname != "lan0" return',
        "meta l4proto != { tcp, udp } return",
        "ip saddr @bypass4 return",
        "fib daddr type local th dport != 53 return",
        "ip daddr @reserved4 th dport != 53 return",
        "meta l4proto { tcp, udp } counter tproxy to 127.0.0.1:12345 meta mark set 0x1 accept",
    ]
    # Метит трафик машины та же цепочка output: дальше его ведёт маршрут, а не lo.
    assert _chain(text, "output") == _chain(_render(_cfg()), "output")
    assert "loopback_guard" in text


def test_tun_without_lan_has_no_tproxy_chain_at_all():
    cfg = Config()
    cfg.capture.method = "tun"
    cfg.capture.containers = False
    rules, _ = nft.build_rules(cfg, capture=True, time_uids=())
    text = nft.render(rules)
    assert "chain prerouting" not in text and "tproxy" not in text
    assert "chain output" in text and "chain loopback_guard" in text
    assert not rules.prerouting
    # С контейнерами TPROXY нужен только им: в prerouting — одни переходы в их цепочку.
    cfg.capture.containers = True
    rules, _ = nft.build_rules(cfg, capture=True, time_uids=())
    text = nft.render(rules)
    assert rules.prerouting and _chain(text, "prerouting") == [
        'iifname "docker0" goto containers', 'iifname "br-*" goto containers',
    ]
    assert "mark set 0x3" in text.split("chain containers {")[1].split("chain prerouting")[0]
    assert "tproxy" not in text
    cfg.network.ipv6 = "proxy"
    text6 = nft.render6(nft.build_rules(cfg, capture=True, time_uids=())[0])
    assert "chain prerouting" not in text6 and "tproxy" not in text6
    assert "chain output" in text6 and "chain loopback_guard" in text6


def test_tun_is_ignored_without_local_capture_or_while_capture_is_off():
    cfg = _tun()
    cfg.capture.local = False
    assert not nft.build_rules(cfg, capture=True, time_uids=())[0].tun
    assert not nft.build_rules(_tun(), capture=False, time_uids=())[0].tun
    assert not nft.build_rules(_cfg(), capture=True, time_uids=())[0].tun
    cfg = _cfg()
    cfg.capture.method = "что-то"  # непонятное слово — tproxy, а не tun
    assert not nft.build_rules(cfg, capture=True, time_uids=())[0].tun


def test_apply_checks_before_loading_and_tolerates_missing_ipv6():
    rules, _ = nft.build_rules(_cfg(), capture=True, time_uids=())
    kernel = FakeKernel()
    assert nft.apply(rules, kernel) == []
    # Обе таблицы — одной транзакцией: между ними правила семей не расходятся.
    assert [call[1:] for call in kernel.calls] == [("-c", "-f", "-"), ("-f", "-")]
    assert nft.loaded_chains(kernel) == {
        "prerouting", "containers", "output", "loopback_guard", "dns_direct", "forward",
        "postrouting",
    }

    class NoIpv6(FakeKernel):
        def _nft(self, argv, text):
            if "ip6" in text:
                raise CommandError("nft: Operation not supported")
            return super()._nft(argv, text)

    no_ipv6 = NoIpv6()
    warnings = nft.apply(dataclasses.replace(rules, v6_guard=False), no_ipv6)
    assert len(warnings) == 1 and "ip6 xgw6" in warnings[0]
    assert "tproxy" in no_ipv6.table  # IPv4 загружен отдельно, без таблицы IPv6


def _blocked(cfg: Config, uids=()) -> nft.Rules:
    rules, _warnings = nft.build_rules(cfg, capture=False, blocked=True, time_uids=uids)
    return rules


def test_blocked_mode_lets_only_xray_and_service_traffic_out():
    """Нет нужного inbound'а в Xray, hold = "block": мимо VPN не уходит ничего, кроме
    сокетов Xray (метка 2), служебного (DHCP, время) и связи с самим шлюзом и LAN."""
    rules = _blocked(_cfg(), uids=(104,))
    text = nft.render(rules)
    assert text.startswith("table ip xgw\ndelete table ip xgw\ntable ip xgw {\n")
    for chain in ("prerouting", "output", "loopback_guard", "containers"):
        assert f"chain {chain} {{" not in text  # перехвата нет — и TPROXY тоже
    assert "tproxy" not in text and "meta mark set" not in text
    assert _chain(text, "block_output") == [
        'oifname "lo" accept',
        "meta mark 0x2 accept",
        "ct direction reply accept",
        "fib daddr type local accept",
        "ip daddr @reserved4 meta l4proto != { tcp, udp } accept",
        "ip daddr @reserved4 th dport != 53 accept",
        "udp sport 68 udp dport 67 accept",
        "meta skuid 104 udp dport 123 accept",
        "meta skuid 104 tcp dport 4460 accept",
        "meta l4proto tcp counter reject with tcp reset",
        "counter reject with icmp type admin-prohibited",
    ]
    forward = _chain(text, "forward")
    assert "type filter hook forward priority filter; policy drop;" in text
    assert forward[-1] == 'iifname "lan0" counter reject with icmp type admin-prohibited'
    assert 'iifname "lan0" oifname != "lan0" ip saddr @bypass4 counter accept' in forward
    assert forward[-2] == 'iifname "lan0" meta l4proto tcp counter reject with tcp reset'
    assert "masquerade" in _chain(text, "postrouting")[-1]  # обход VPN по-прежнему работает


def test_blocked_keeps_established_only_for_bypass_devices():
    """Сессии, открытые в режиме «снят», в blocked не доживают по записи conntrack."""
    forward = _chain(nft.render(_blocked(_cfg())), "forward")
    assert "ct state established,related accept" not in forward
    assert 'iifname "lan0" ip saddr @bypass4 ct state established,related accept' in forward
    assert 'oifname "lan0" ip daddr @bypass4 ct state established,related accept' in forward


def test_blocked_rejects_containers_except_bypass_subnets():
    """Без цепочки containers мосты Docker прошли бы правилом «чужой форвардинг»."""
    text = nft.render(_blocked(_cfg()))
    forward = _chain(text, "forward")
    rejects = [rule for rule in forward if rule.startswith('iifname "docker0"')
               or rule.startswith('iifname "br-*"')]
    assert len(rejects) == 2
    for rule in rejects:
        assert 'oifname != "docker0" oifname != "br-*"' in rule  # между мостами — можно
        assert "ct direction original" in rule  # ответы опубликованных портов идут
        assert "ip daddr != @reserved4" in rule and "ip saddr != @bypass_containers" in rule
        assert rule.endswith("counter reject with icmp type admin-prohibited")
    # Отказ — раньше, чем «чужой форвардинг» успел бы их пропустить.
    assert forward.index(rejects[-1]) < forward.index('iifname != "lan0" oifname != "lan0" accept')
    assert "set bypass_containers {" in text
    cfg = _cfg()
    cfg.capture.containers = False  # контейнеры и в режиме on идут напрямую — не трогаем
    assert 'iifname "docker0"' not in nft.render(_blocked(cfg))


def test_blocked_without_lan_closes_the_machine_only():
    rules = _blocked(Config())
    assert not rules.empty
    text = nft.render(rules)
    assert "chain block_output {" in text and "chain forward {" in text  # контейнеры
    assert "lan0" not in text and "chain postrouting {" not in text


def test_v6_guard_with_ipv6_off_regardless_of_networkmanager():
    """network.ipv6 = off: IPv6 машины держит фаервол, а не только настройка NetworkManager
    (её нет, если WAN не под NetworkManager)."""
    for capture in (True, False):  # и при включённом перехвате, и при снятом
        rules, _ = nft.build_rules(_cfg(), capture=capture, time_uids=())
        assert rules.v6_guard
        guard = _chain(nft.render6(rules), "v6_guard")
        assert guard[-2:] == ["meta l4proto tcp counter reject with tcp reset",
                              "counter reject with icmpv6 type admin-prohibited"]
    only_machine, _ = nft.build_rules(Config(), capture=True, time_uids=())
    assert "chain v6_guard {" in nft.render6(only_machine)  # таблица нужна и без LAN
    rules, _ = nft.build_rules(_proxy6(), capture=True, time_uids=())
    assert not rules.v6_guard and "v6_guard" not in nft.render6(rules)  # IPv6 через Xray
    rules, _ = nft.build_rules(_proxy6(), capture=False, blocked=True, time_uids=())
    assert rules.v6_guard  # proxy, но перехват невозможен — IPv6 закрыт
    lan_only = _cfg()
    lan_only.capture.local = False  # машина не перехватывается — её IPv6 не наше дело
    assert not nft.build_rules(lan_only, capture=True, time_uids=())[0].v6_guard


def test_v6_guard_lets_xray_sockets_out():
    rules, _ = nft.build_rules(_cfg(), capture=True, time_uids=())
    guard = _chain(nft.render6(rules), "v6_guard")
    assert guard[:2] == ['oifname "lo" accept', "meta mark 0x2 accept"]
    assert "ip6 daddr { fe80::/10, ff00::/8 } accept" in guard
    assert "ct direction reply accept" in guard


def test_v6_guard_keeps_kernel_icmpv6():
    """ND и ошибки ICMPv6 шлёт само ядро: без метки и бывает на глобальный адрес."""
    rules, _ = nft.build_rules(_cfg(), capture=True, time_uids=())
    guard = _chain(nft.render6(rules), "v6_guard")
    icmp = [rule for rule in guard if rule.startswith("icmpv6 type")]
    assert len(icmp) == 1 and icmp[0].endswith(" accept")
    for kind in ("packet-too-big", "destination-unreachable", "nd-neighbor-solicit",
                 "nd-neighbor-advert", "nd-router-advert"):
        assert kind in icmp[0]
    assert guard.index(icmp[0]) < guard.index("meta l4proto tcp counter reject with tcp reset")


def test_both_families_load_in_one_transaction():
    rules = _blocked(_cfg())
    kernel = FakeKernel()
    assert nft.apply(rules, kernel) == []
    assert len(kernel.commands("nft", "-f", "-")) == 1
    assert "block_output" in kernel.table and "v6_guard" in kernel.table6
    assert kernel.loads[0].index("table ip xgw") < kernel.loads[0].index("table ip6 xgw6")


def test_v6_guard_that_cannot_be_loaded_is_an_error():
    """Без v6_guard IPv6 машины ушёл бы мимо VPN: ошибка, а не предупреждение."""
    kernel = FakeKernel()
    kernel.refuse_ip6 = True
    rules, _ = nft.build_rules(_cfg(), capture=True, time_uids=())
    with pytest.raises(CommandError):
        nft.apply(rules, kernel)
    assert kernel.tables == {}  # и таблица IPv4 не загружена: транзакция одна


def test_rejected_rules_are_not_loaded():
    rules, _ = nft.build_rules(_cfg(), capture=True, time_uids=())
    kernel = FakeKernel()
    kernel.refuse = "nft -c"
    with pytest.raises(CommandError):
        nft.apply(rules, kernel)
    assert kernel.tables == {}


def test_loaded_chains_distinguishes_absent_from_unknown():
    kernel = FakeKernel()
    assert nft.loaded_chains(kernel) == set()  # таблицы нет
    kernel.forbidden = True
    assert nft.loaded_chains(kernel) is None  # без root узнать нельзя


# --- настоящий nft: проверка синтаксиса без загрузки ---------------------------

_NFT = shutil.which("nft")
_ROOT = sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0


def _variants():
    full = _cfg(
        wan_if="wan0",
        static_leases=["aa:bb:cc:dd:ee:ff,192.168.50.20,tv"],
        bypass_hosts=["aa:bb:cc:dd:ee:ff", "192.168.50.64/28"],
    )
    full.capture.exclude_cidrs = ["203.0.113.0/24"]
    full.dns.direct_servers = ["203.0.113.53:5353"]
    lan_only = _cfg()
    lan_only.capture.local = False
    ipv6 = _proxy6(wan_if="wan0")
    ipv6.capture.exclude_cidrs = ["2001:db8:77::/48"]
    tun = _tun(wan_if="wan0")
    tun_only = Config(network=Network(ipv6="proxy"))
    tun_only.capture.method = "tun"
    return {
        "TUN": (tun, True),
        "TUN без LAN, с IPv6": (tun_only, True),
        "IPv6 машины": (ipv6, True),
        "IPv6 без LAN": (Config(network=Network(ipv6="proxy")), True),
        "шлюз": (_cfg(), True),
        "всё сразу": (full, True),
        "только эта машина": (Config(), True),
        "LAN без своей машины": (lan_only, True),
        "перехват снят": (_cfg(), False),
    }


@pytest.mark.skipif(not (_NFT and _ROOT), reason="нужны nft и root")
@pytest.mark.parametrize("name", list(_variants()))
def test_real_nft_accepts_rules(name):
    cfg, capture = _variants()[name]
    rules, _ = nft.build_rules(cfg, capture=capture, time_uids=(0,))
    for text in (nft.render(rules), nft.render6(rules)):
        if not text:
            continue
        done = subprocess.run(
            ["nft", "-c", "-f", "-"], input=text, capture_output=True, text=True, timeout=30
        )
        assert done.returncode == 0, f"{done.stderr}\n{text}"


def _blocked_variants():
    full = _cfg(wan_if="wan0", bypass_hosts=["192.168.50.64/28"])
    lan_only = _cfg()
    lan_only.capture.local = False
    return {
        "blocked: шлюз": _cfg(),
        "blocked: всё сразу": full,
        "blocked: только эта машина": Config(),
        "blocked: LAN без своей машины": lan_only,
        "blocked: IPv6 машины": _proxy6(),
    }


@pytest.mark.skipif(not (_NFT and _ROOT), reason="нужны nft и root")
@pytest.mark.parametrize("name", list(_blocked_variants()))
def test_real_nft_accepts_blocked_rules_in_one_transaction(name):
    rules = _blocked(_blocked_variants()[name], uids=(0,))
    text = nft.render(rules) + nft.render6(rules)
    done = subprocess.run(
        ["nft", "-c", "-f", "-"], input=text, capture_output=True, text=True, timeout=30
    )
    assert done.returncode == 0, f"{done.stderr}\n{text}"
