"""Шлюз — выходной узел tailnet (ASSUMPTIONS п. 230): интернет устройств tailnet через Xray
(TPROXY из tailscale0), «напрямую» для отмеченных в панели, blocked, IPv6, маршрут throw,
разбор `tailscale status`/`debug prefs`, panel.json и кнопки карточки «Tailscale»."""

import json

import fakexray
import pytest
from fake_tailscale import FakeTailscale
from fakenet import FakeKernel
from test_panel import Rig
from test_tailscale import _cfg, _chain, _ipv6, _rules, _start_tailscaled

from xgw import managed, tailscale
from xgw.net import nft, sysctl
from xgw.net.capture import Capture
from xgw.paths import Paths

PHONE_TS = "100.101.2.3"
TPROXY = "meta l4proto { tcp, udp } counter tproxy to 127.0.0.1:12345 meta mark set 0x1 accept"


def _set(text: str, name: str) -> list[str]:
    lines = text.splitlines()
    start = lines.index(f"    set {name} {{")
    return [line.strip() for line in lines[start + 1:lines.index("    }", start)]]


# --- текст правил ---------------------------------------------------------------------


def test_tailnet_internet_goes_through_xray_and_direct_devices_around_it():
    cfg = _cfg(containers=False)
    cfg.managed.tailscale_direct = [PHONE_TS]
    rules = _rules(cfg, tailscale=True, tailnet=True)
    text = nft.render(rules)
    prerouting = _chain(text, "prerouting")
    assert prerouting[0] == 'iifname != { "lan0", "lo", "tailscale0" } return'
    for line in ('iifname "tailscale0" ip saddr != 100.64.0.0/10 return',
                 'iifname "tailscale0" ip saddr @ts_exit_direct return'):
        assert prerouting.index(line) < prerouting.index(TPROXY)
    assert _set(text, "ts_exit_direct") == ["type ipv4_addr", f"elements = {{ {PHONE_TS} }}"]
    forward = _chain(text, "forward")
    generic = forward.index('iifname != "lan0" oifname != "lan0" accept')
    assert forward.index('iifname "tailscale0" ip saddr @ts_exit_direct counter accept') < generic
    assert forward.index('iifname "tailscale0" counter reject with icmp type admin-prohibited') \
        < generic
    assert ('iifname "tailscale0" oifname != "tailscale0" ip saddr @ts_exit_direct '
            "ip daddr != @reserved4 counter masquerade") in _chain(text, "postrouting")
    # IPv6 через выходной узел закрыт: иначе мимо VPN.
    assert ('iifname "tailscale0" ip6 daddr != fd7a:115c:a1e0::/48 counter reject with '
            "icmpv6 type admin-prohibited") in _chain(nft.render6(rules), "forward")


def test_exit_node_works_without_lan_and_without_capturing_the_machine():
    cfg = _cfg(local=False, containers=False)
    cfg.network.lan_if = ""
    rules = _rules(cfg, tailnet=True)
    text = nft.render(rules)
    assert rules.tproxy and not rules.empty
    assert _chain(text, "prerouting")[0] == 'iifname != "tailscale0" return'
    assert "policy accept;" in text.split("chain forward {")[1].split("\n")[1]
    assert "chain output" not in text
    assert nft.render6(rules)  # таблица ip6 нужна ради закрытого IPv6


@pytest.mark.parametrize("mode", ["off", "blocked"])
def test_exit_node_without_capture(mode):
    """Перехват снят — tailnet идёт как LAN, напрямую (правил нет); blocked — в интернет
    только устройства «напрямую», остальное отбивается."""
    cfg = _cfg()
    cfg.managed.tailscale_direct = [PHONE_TS]
    rules = _rules(cfg, capture=False, blocked=mode == "blocked", tailnet=True)
    text = nft.render(rules)
    assert "tproxy" not in text
    if mode == "off":
        assert 'iifname "tailscale0"' not in text and "ts_exit_direct" not in text
        return
    forward = _chain(text, "forward")
    assert forward[:3] == [
        'iifname "tailscale0" ip daddr @reserved4 accept',
        'iifname "tailscale0" ip saddr @ts_exit_direct counter accept',
        'iifname "tailscale0" counter reject with icmp type admin-prohibited',
    ]
    assert nft.ts_exit_state(text) and not nft.ts_state(text)[0]


def test_set_elements_reads_the_real_listing():
    listing = ("table ip xgw {\n\tset ts_exit_direct {\n\t\ttype ipv4_addr\n\t\tflags interval\n"
               "\t\telements = { 100.101.2.3, 100.101.2.9 }\n\t}\n}\n")
    assert nft.set_elements(listing, "ts_exit_direct") == {"100.101.2.3", "100.101.2.9"}
    assert nft.set_elements("table ip xgw {\n}\n", "ts_exit_direct") == set()


# --- Capture: правила, маршрут throw, «загружено» -----------------------------------


@pytest.fixture()
def gateway(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path / "root"))
    paths = Paths.from_env()
    paths.ensure()
    proc = tmp_path / "proc"
    (proc / "net/ipv4").mkdir(parents=True)
    (proc / sysctl.IP_FORWARD).write_text("0\n")
    fakexray.write(paths)
    kernel = FakeKernel()
    capture = Capture(_cfg(containers=False), paths, runner=kernel, proc_sys=proc, time_uids=())
    capture.kernel, capture.proc = kernel, proc
    capture.sys_net = tmp_path / "sys-class-net"
    capture.sys_net.mkdir()
    return capture


def test_exit_rules_and_throw_follow_tailscaled_and_the_direct_list(gateway):
    _ipv6(gateway)
    gateway.enable()
    assert not nft.ts_exit_state(gateway.kernel.table)
    _start_tailscaled(gateway)
    assert gateway.loaded() is False  # tailscaled запустился — выходной узел не загружен
    gateway.up()
    assert nft.ts_exit_state(gateway.kernel.table) and gateway.loaded() is True
    # src_valid_mark = 1 у tailscaled: без throw пакет 100.x с меткой — «чужой адрес».
    assert {"type": "throw", "dst": "100.64.0.0/10"} in gateway.kernel.routes(100)
    gateway.cfg.managed.tailscale_direct = [PHONE_TS]
    assert gateway.loaded() is False  # устройство пустили напрямую — набор не тот
    gateway.up()
    assert nft.set_elements(gateway.kernel.table, "ts_exit_direct") == {PHONE_TS}
    assert gateway.loaded() is True
    (gateway.sys_net / tailscale.INTERFACE).rmdir()
    gateway.up()
    assert not nft.ts_exit_state(gateway.kernel.table)
    assert {"type": "throw", "dst": "100.64.0.0/10"} not in gateway.kernel.routes(100)
    assert gateway.loaded() is True


# --- tailscale status / prefs, panel.json -------------------------------------------


def test_status_lists_tailnet_devices_and_exit_approval():
    fake = FakeTailscale()
    fake.peers = [
        {"HostName": "laptop", "TailscaleIPs": ["100.101.2.9", "fd7a:115c:a1e0::9"],
         "OS": "windows", "Online": False},
        {"HostName": "", "DNSName": "galaxy-s25.tailnet-1.ts.net.",
         "TailscaleIPs": [PHONE_TS], "OS": "android", "Online": True},
        {"HostName": "broken", "TailscaleIPs": ["fd7a:115c:a1e0::7"]},  # без IPv4 — пропуск
    ]
    state = tailscale.status(fake)
    assert state.peers == (
        tailscale.Peer("galaxy-s25", PHONE_TS, "android", True),
        tailscale.Peer("laptop", "100.101.2.9", "windows", False),
    )
    assert state.exit_approved is False
    fake.exit_node = fake.exit_approved = True
    assert tailscale.status(fake).exit_approved is True
    assert tailscale.prefs(fake).exit_node is True
    assert tailscale.parse_status('{"Self": {}}').exit_approved is None


def test_panel_store_keeps_only_tailnet_addresses(tmp_path):
    store = tmp_path / "panel.json"
    assert managed.set_tailscale_direct(store, PHONE_TS, "phone", direct=True)
    assert not managed.set_tailscale_direct(store, PHONE_TS, "phone", direct=True)
    with pytest.raises(managed.ManagedError):
        managed.set_tailscale_direct(store, "192.168.1.5", "lan", direct=True)
    raw = json.loads(store.read_text(encoding="utf-8"))
    raw["tailscale"]["direct"] += [{"ip": "8.8.8.8"}, {"ip": PHONE_TS}, "junk"]
    store.write_text(json.dumps(raw), encoding="utf-8")
    assert managed.load(store)[0]["tailscale"]["direct"] == [{"ip": PHONE_TS, "name": "phone"}]
    assert managed.set_tailscale_direct(store, PHONE_TS, "", direct=False)
    assert managed.load(store)[0]["tailscale"]["direct"] == []


# --- панель ---------------------------------------------------------------------------


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    instance = Rig(tmp_path, monkeypatch)
    fake = FakeTailscale()
    fake.peers = [{"HostName": "galaxy-s25", "TailscaleIPs": [PHONE_TS], "OS": "android",
                   "Online": True}]
    instance.fake_ts = fake
    system = instance.panel.runner

    def runner(argv, **kwargs):
        if argv and argv[0] == "tailscale":
            return fake(argv, **kwargs)
        return system(argv, **kwargs)

    instance.panel.runner = runner
    instance.panel.which = lambda name: f"/usr/bin/{name}"
    instance.panel.sys_net = tmp_path / "sys-class-net"
    (instance.panel.sys_net / tailscale.INTERFACE).mkdir(parents=True)
    instance.client.login()
    yield instance
    instance.panel.stop()


def _card(rig) -> dict:
    rig.panel._ts_card = (0.0, None)
    return rig.client.state()["tailscale"]


def test_panel_turns_the_gateway_into_an_exit_node(rig):
    assert _card(rig)["exit"] == {"advertised": False, "approved": False}
    result = rig.client.act("tailscale/exit", {"on": True})
    assert result["ok"] and "Edit route settings" in result["notes"][0]
    assert rig.fake_ts.exit_node is True
    rig.fake_ts.exit_approved = True
    assert _card(rig)["exit"] == {"advertised": True, "approved": True}
    assert rig.client.act("tailscale/exit", {"on": False})["ok"] and not rig.fake_ts.exit_node
    assert not rig.client.act("tailscale/exit", {"on": "yes"})["ok"]


def test_panel_lets_a_tailnet_device_out_directly_and_back(rig):
    peers = _card(rig)["peers"]
    assert peers == [{"name": "galaxy-s25", "ip": PHONE_TS, "os": "android", "online": True,
                      "direct": False}]
    result = rig.client.act("tailscale/direct", {"ip": PHONE_TS, "name": "galaxy-s25",
                                                 "direct": True})
    assert result["ok"] and "напрямую" in result["text"]
    assert managed.load(rig.store_path)[0]["tailscale"]["direct"] == [
        {"ip": PHONE_TS, "name": "galaxy-s25"}]
    assert _card(rig)["peers"][0]["direct"] is True
    assert rig.client.act("tailscale/direct", {"ip": PHONE_TS, "direct": False})["ok"]
    assert _card(rig)["peers"][0]["direct"] is False
    assert not rig.client.act("tailscale/direct", {"ip": "192.168.50.7", "direct": True})["ok"]
