"""Учёт расхода трафика (usage.py): таблица учёта nftables и разбор её счётчиков, разницы
отсчётов со сбросами, запись по дням, сводка для панели и `xgw traffic`."""

import json
from urllib.parse import quote

import pytest

from xgw import usage
from xgw.config import Config
from xgw.generator import builder
from xgw.model import raw_to_node
from xgw.net import dnsmasq
from xgw.parsers.common import parse_links_text
from xgw.paths import Paths
from xgw.store import Store

UUID = "0b6a2a3c-1d2e-4f50-8a9b-0c1d2e3f4a5b"
NOW = 1_800_000_000.0
PHONE = "aa:bb:cc:00:11:22"


@pytest.fixture()
def paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    found = Paths.from_env()
    found.ensure()
    return found


def _node(host: str, name: str, source: str):
    link = f"vless://{UUID}@{host}:443?security=tls&sni=a.example.com&type=tcp#{quote(name)}"
    raws, _meta, _warnings = parse_links_text(link, source)
    return raw_to_node(raws[0], source)


def _nft_json(ups: dict, downs: dict, wan_in: int, wan_out: int) -> str:
    def elems(found: dict) -> list:
        return [{"elem": {"val": ip, "timeout": 86400, "expires": 86000,
                          "counter": {"packets": 1, "bytes": value}}}
                for ip, value in found.items()]

    return json.dumps({"nftables": [
        {"metainfo": {"version": "1.0.9", "json_schema_version": 1}},
        {"table": {"family": "ip", "name": usage.TABLE, "handle": 1}},
        {"set": {"family": "ip", "name": "dev_up", "table": usage.TABLE, "type": "ipv4_addr",
                 "flags": ["dynamic", "timeout"], "elem": elems(ups)}},
        {"set": {"family": "ip", "name": "dev_down", "table": usage.TABLE, "type": "ipv4_addr",
                 "flags": ["dynamic", "timeout"], "elem": elems(downs)}},
        {"counter": {"family": "ip", "name": "wan_in", "table": usage.TABLE, "packets": 9,
                     "bytes": wan_in}},
        {"counter": {"family": "ip", "name": "wan_out", "table": usage.TABLE, "packets": 9,
                     "bytes": wan_out}},
    ]})


class _Nft:
    """Подставной nft: таблицу учёта запоминает, её счётчики отдаёт из listing."""

    def __init__(self):
        self.loads: list[str] = []
        self.listing = ""

    def __call__(self, argv, *, input=None, timeout=15.0, check=True):
        if argv[:3] == ["nft", "-f", "-"]:
            self.loads.append(input)
            return ""
        if argv[:5] == ["nft", "-j", "list", "table", "ip"]:
            return self.listing
        raise AssertionError(f"неожиданная команда: {argv}")


def test_accounting_table_counts_devices_and_wan():
    """Своя таблица ip xgw_acct: наборы со счётчиком на адрес устройства (от LAN и в LAN),
    счётчики WAN; только считает (policy accept). Разбор JSON nft — по адресам и именам."""
    text = usage.render("lan0", "192.168.50.0/24", "wan0")
    assert text.startswith("table ip xgw_acct\ndelete table ip xgw_acct\n")
    assert 'iifname "lan0" ip saddr 192.168.50.0/24 update @dev_up { ip saddr counter }' in text
    assert 'oifname "lan0" ip daddr 192.168.50.0/24 update @dev_down { ip daddr counter }' in text
    assert 'iifname "wan0" counter name "wan_in"' in text
    assert 'oifname "wan0" counter name "wan_out"' in text
    assert "flags dynamic,timeout" in text and "timeout 1d" in text
    assert "hook prerouting priority -300; policy accept;" in text
    assert "hook postrouting priority 300; policy accept;" in text
    only_wan = usage.render("", "", "wan0")
    assert "dev_up" not in only_wan and "wan_out" in only_wan
    assert usage.render("", "", "") == ""
    up, down, named = usage.parse(_nft_json({"192.168.50.20": 700}, {"192.168.50.20": 9000},
                                            50, 5))
    assert up == {"192.168.50.20": 700} and down == {"192.168.50.20": 9000}
    assert named == {"wan_in": 50, "wan_out": 5}
    bare = {"nftables": [{"set": {"name": "dev_up", "elem": ["192.168.50.9"]}}]}
    assert usage.parse(json.dumps(bare)) == ({}, {}, {})
    assert [usage.size(value) for value in (850_000, 12_400_000, 3_100_000_000, 250_000_000_000)] \
        == ["850 КБ", "12,4 МБ", "3,1 ГБ", "250 ГБ"]


def test_meter_writes_deltas_by_device_subscription_and_exit(paths):
    """Первый отсчёт — база; дальше — разницы. Сброс (перезапуск Xray, пересозданный элемент
    набора) — разница равна самому значению. Устройство — по MAC из аренды; подписка — по
    серверу тега, учтено подпиской — с множителем (x10); pool-* — бесплатные, direct —
    напрямую, служебные теги не считаются. Сводка: «шлюз и служебное» = WAN − устройства."""
    cfg = Config()
    cfg.network.lan_if, cfg.network.wan_if = "lan0", "wan0"
    dnsmasq.leases_path(paths).write_text(f"1900000000 {PHONE} 192.168.50.20 phone *\n",
                                          encoding="utf-8")
    nodes = [_node("203.0.113.10", "DE x10", "main"), _node("203.0.113.11", "NL", "second")]
    applied = builder.build(cfg, builder.Selection(members=nodes), hosts={}).config
    tags = {info.fingerprint: info.tag for info in builder.applied_nodes(applied, nodes)}
    ten, one = tags[nodes[0].fingerprint], tags[nodes[1].fingerprint]

    def metrics(ten_up, ten_down, one_down, pool_down, direct_down):
        return {"stats": {"outbound": {
            ten: {"uplink": ten_up, "downlink": ten_down}, one: {"uplink": 0, "downlink": one_down},
            "pool-de-aaaa": {"uplink": 0, "downlink": pool_down},
            "direct": {"uplink": 0, "downlink": direct_down},
            "dns-out": {"uplink": 999, "downlink": 999}}}}

    clock = [NOW]
    nft = _Nft()
    meter = usage.Meter(cfg, paths, runner=nft, clock=lambda: clock[0])
    store = Store(paths.db_file)
    store.add_usage("2020-01-01", [(usage.DEVICE, PHONE, 1, 1, 0)])  # старше USAGE_DAYS
    assert not meter.step(store, metrics(100, 1000, 0, 0, 0), applied, nodes)
    assert len(nft.loads) == 1 and "xgw_acct" in nft.loads[0]  # таблица учёта поставлена
    clock[0] += usage.USAGE_EVERY - 1
    assert not meter.step(store, metrics(9e9, 9e9, 0, 0, 0), applied, nodes)  # рано
    clock[0] = NOW + usage.USAGE_EVERY
    nft.listing = _nft_json({"192.168.50.20": 1000}, {"192.168.50.20": 5000}, 8000, 3000)
    assert meter.step(store, metrics(300, 2000, 400, 700, 60), applied, nodes)
    clock[0] = NOW + 2 * usage.USAGE_EVERY
    nft.listing = _nft_json({"192.168.50.20": 10}, {"192.168.50.20": 5100}, 8100, 3050)
    assert meter.step(store, metrics(50, 70, 450, 700, 60), applied, nodes)  # Xray перезапущен
    assert len(nft.loads) == 1  # таблица та же — не перезаписывается
    day = usage.today(lambda: clock[0])
    rows = {(row["kind"], row["key"]): (row["up"], row["down"], row["billed"])
            for row in store.usage_since(day)}
    assert rows == {
        (usage.DEVICE, PHONE): (1010, 5100, 0),
        (usage.WAN, usage.WAN): (3050, 8100, 0),
        (usage.SUB, "main"): (250, 1070, 13_200),
        (usage.SUB, "second"): (0, 450, 450),
        (usage.POOL, usage.POOL): (0, 700, 0),
        (usage.DIRECT, usage.DIRECT): (0, 60, 0),
    }
    assert store.usage_since("2000-01-01") == store.usage_since(day)  # старое убрано
    store.set_meta("quota", json.dumps({"main": {"upload": 1_000, "download": 2_000,
                                                 "total": 100_000_000_000, "expire": 0}}))
    found = usage.report(cfg, paths, 1, clock=lambda: clock[0], store=store)
    assert found["devices"] == [{"key": PHONE, "name": "phone", "ip": "192.168.50.20",
                                 "up": 1010, "down": 5100}]
    assert found["gateway"] == {"up": 3050 - 1010, "down": 8100 - 5100}
    assert [item["name"] for item in found["subscriptions"]] == ["main", "second"]
    assert found["subscriptions"][0]["quota"]["used"] == 3_000
    assert found["subscriptions"][1]["quota"] is None
    printed = usage.text(found)
    assert "phone (192.168.50.20)" in printed and "учтено подпиской" in printed
    store.close()


def test_meter_without_nftables_counts_only_xray(paths):
    """Демон без перехвата (и тесты демона) nft не запускает: только счётчики Xray."""
    cfg = Config()
    cfg.network.lan_if, cfg.network.wan_if = "lan0", "wan0"
    clock = [NOW]
    meter = usage.Meter(cfg, paths, runner=None, clock=lambda: clock[0])
    store = Store(paths.db_file)
    out = {"stats": {"outbound": {"direct": {"uplink": 1, "downlink": 2}}}}
    meter.step(store, out, None, ())
    clock[0] += usage.USAGE_EVERY
    out = {"stats": {"outbound": {"direct": {"uplink": 11, "downlink": 32}}}}
    assert meter.step(store, out, None, ())
    assert store.usage_since("2000-01-01") == [
        {"kind": usage.DIRECT, "key": usage.DIRECT, "up": 10, "down": 30, "billed": 0}]
    store.close()
