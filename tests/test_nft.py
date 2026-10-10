"""Правила nftables: генерация текста и проверка `nft -c -f` (без root — пропуск)."""

import os
import shutil
import subprocess
import sys

import pytest
from fakenet import FakeKernel

from xgw.config import Config
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
    for chain in ("prerouting", "output", "dns_direct", "forward", "postrouting"):
        assert f"chain {chain} {{" in text

    prerouting = _chain(text, "prerouting")
    assert "hook prerouting priority mangle" in text
    assert prerouting == [
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
    assert _chain(text, "prerouting")[0] == 'iifname != "lo" return'
    assert "chain output {" in text
    for absent in ("bypass4", "chain forward", "chain postrouting", "chain dns_direct", "lan"):
        assert absent not in text
    rules, _ = nft.build_rules(cfg, capture=True, time_uids=())
    assert nft.render6(rules) == ""


def test_lan_without_local_capture():
    cfg = _cfg()
    cfg.capture.local = False
    text = _render(cfg)
    assert "chain output {" not in text
    prerouting = _chain(text, "prerouting")
    assert prerouting[0] == 'iifname != "lan0" return'
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
    rules, _ = nft.build_rules(Config(), capture=False, time_uids=())
    assert rules.empty and nft.render(rules) == "" and nft.render6(rules) == ""
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


def test_apply_checks_before_loading_and_tolerates_missing_ipv6():
    rules, _ = nft.build_rules(_cfg(), capture=True, time_uids=())
    kernel = FakeKernel()
    assert nft.apply(rules, kernel) == []
    assert [call[1:] for call in kernel.calls] == [("-c", "-f", "-"), ("-f", "-"), ("-f", "-")]
    assert nft.loaded_chains(kernel) == {
        "prerouting", "output", "dns_direct", "forward", "postrouting"
    }

    class NoIpv6(FakeKernel):
        def _nft(self, argv, text):
            if "ip6" in text:
                raise CommandError("nft: Operation not supported")
            return super()._nft(argv, text)

    warnings = nft.apply(rules, NoIpv6())
    assert len(warnings) == 1 and "ip6 xgw6" in warnings[0]


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
    return {
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
