"""Tailscale рядом с XGW (Т1 `TAILSCALE_MINIAPP_PLAN.md`, раздел 2.5): исключения К1–К4 в
правилах, набор ts_direct при route = direct и vpn, `xgw diag` (К5, К6), разбор вывода CLI.

Без Tailscale правила прежние — это проверяют и все остальные тесты правил."""

import dataclasses
import json

import fakexray
import pytest
from fakenet import FakeKernel
from fakesys import FakeSystem

from xgw import config, tailscale
from xgw.config import Config
from xgw.diag import FAIL, OK, WARN, Diag
from xgw.net import nft, sysctl
from xgw.net.capture import Capture
from xgw.paths import Paths

SKIP_TS = 'meta mark and 0xff0000 @ts_direct return'
SKIP_TS0 = 'oifname "tailscale0" return'


def _cfg(**capture) -> Config:
    cfg = Config()
    cfg.network.lan_if = "lan0"
    for key, value in capture.items():
        setattr(cfg.capture, key, value)
    return cfg


def _rules(cfg: Config, **kwargs) -> nft.Rules:
    kwargs.setdefault("capture", True)
    return nft.build_rules(cfg, time_uids=(), **kwargs)[0]


def _chain(text: str, name: str) -> list[str]:
    """Правила цепочки из текста render()/render6()."""
    lines = text.splitlines()
    start = lines.index(f"    chain {name} {{")
    end = lines.index("    }", start)
    return [line.strip() for line in lines[start + 2:end]]


def _set(text: str) -> list[str]:
    lines = text.splitlines()
    start = lines.index("    set ts_direct {")
    return [line.strip() for line in lines[start + 1:lines.index("    }", start)]]


# --- текст правил ---------------------------------------------------------------


@pytest.mark.parametrize("mode", ["on", "blocked", "off"])
def test_without_tailscaled_the_rules_have_no_exceptions(mode):
    """tailscaled не работает — правила прежние: ни набора, ни tailscale0."""
    cfg = _cfg()
    rules = _rules(cfg, capture=mode == "on", blocked=mode == "blocked")
    for text in (nft.render(rules), nft.render6(rules)):
        assert "tailscale0" not in text and "ts_direct" not in text and "0x80000" not in text


@pytest.mark.parametrize("method", ["tproxy", "tun"])
def test_tailscaled_and_tailscale0_skip_the_capture(method):
    """К1 и К2 в режиме on (TPROXY и TUN): метка tailscaled из набора ts_direct и всё, что
    уходит в tailscale0 (в том числе DNS к 100.100.100.100), — мимо «meta mark set 1»."""
    rules = _rules(_cfg(method=method), tailscale=True)
    output = _chain(nft.render(rules), "output")
    marking = next(i for i, line in enumerate(output) if "meta mark set" in line)
    assert output.index(SKIP_TS) < marking and output.index(SKIP_TS0) < marking
    # Раньше правила «ip daddr @reserved4 th dport != 53 return»: DNS туда не попадает.
    assert output.index(SKIP_TS0) < output.index("ip daddr @reserved4 th dport != 53 return")
    assert _set(nft.render(rules)) == ["type mark", "elements = { 0x80000 }"]  # route = direct


def test_route_vpn_keeps_tailscaled_in_xray_only_while_xray_answers():
    """route = "vpn": пока Xray отвечает, набор пуст (tailscaled идёт через Xray); Xray не
    отвечает, режим blocked или перехват снят — метка в наборе, tailscaled напрямую."""
    cfg = _cfg()
    cfg.tailscale.route = "vpn"
    assert _set(nft.render(_rules(cfg, tailscale=True))) == ["type mark"]
    down = _rules(cfg, tailscale=True, xray_down=True)
    assert _set(nft.render(down)) == ["type mark", "elements = { 0x80000 }"]
    for kwargs in ({"capture": False, "blocked": True}, {"capture": False}):
        assert _rules(cfg, tailscale=True, **kwargs).ts_direct
    assert _rules(Config(), tailscale=True).ts_direct  # route = direct — всегда


def test_blocked_lets_tailscale_through_always():
    """К3: в blocked tailscaled и tailscale0 проходят до reject — и при route = "vpn"
    (по метке, а не по набору: перехвата в blocked нет)."""
    cfg = _cfg()
    cfg.tailscale.route = "vpn"
    rules = _rules(cfg, capture=False, blocked=True, tailscale=True)
    text = nft.render(rules)
    output = _chain(text, "block_output")
    reject = next(i for i, line in enumerate(output) if "reject" in line)
    assert output.index("meta mark and 0xff0000 == 0x80000 accept") < reject
    assert output.index('oifname "tailscale0" accept') < reject
    assert "set ts_direct" not in text  # набор в blocked ни к чему
    assert "tailscale0" not in nft.render(_rules(cfg, capture=False, blocked=True))


@pytest.mark.parametrize("mode", ["on", "blocked", "off"])
def test_v6_guard_lets_the_tailnet_and_tailscaled_through(mode):
    """К4: v6_guard пропускает tailscale0 (fd7a:115c:a1e0::/48) и IPv6-сокеты tailscaled
    из набора ts_direct; остальной IPv6 машины по-прежнему отбит."""
    rules = _rules(_cfg(), capture=mode == "on", blocked=mode == "blocked", tailscale=True)
    text = nft.render6(rules)
    guard = _chain(text, "v6_guard")
    reject = next(i for i, line in enumerate(guard) if "reject" in line)
    assert guard.index('oifname "tailscale0" accept') < reject
    assert guard.index("meta mark and 0xff0000 @ts_direct accept") < reject
    assert _set(text) == ["type mark", "elements = { 0x80000 }"]


def test_proxied_ipv6_skips_tailscale_like_ipv4():
    """network.ipv6 = "proxy": в цепочке output таблицы ip6 — те же исключения."""
    cfg = _cfg()
    cfg.network.ipv6 = "proxy"
    cfg.tailscale.route = "vpn"
    rules = _rules(cfg, tailscale=True)
    output = _chain(nft.render6(rules), "output")
    marking = next(i for i, line in enumerate(output) if "meta mark set" in line)
    assert output.index(SKIP_TS) < marking and output.index(SKIP_TS0) < marking
    assert nft.ts_elements(rules) == (
        "flush set ip xgw ts_direct\nflush set ip6 xgw6 ts_direct\n"
    )
    direct = dataclasses.replace(rules, ts_direct=True)
    assert nft.ts_elements(direct) == (
        "add element ip xgw ts_direct { 0x80000 }\nadd element ip6 xgw6 ts_direct { 0x80000 }\n"
    )


def test_ts_state_reads_the_real_listing():
    """Вывод настоящего `nft list table` (nft 1.1.6): метка в наборе — 0x00080000."""
    listing = (
        "table ip xgw {\n\tset ts_direct {\n\t\ttype mark\n\t\telements = { 0x00080000 }\n\t}\n\n"
        "\tchain output {\n\t\ttype route hook output priority mangle; policy accept;\n"
        "\t\tmeta mark & 0x00ff0000 == @ts_direct return\n\t\toifname \"tailscale0\" return\n"
        "\t}\n}\n"
    )
    assert nft.ts_state(listing) == (True, True)
    assert nft.ts_state(listing.replace("\t\telements = { 0x00080000 }\n", "")) == (True, False)
    assert nft.ts_state("table ip xgw {\n}\n") == (False, None)


# --- Capture: правила следуют за tailscaled ---------------------------------------


@pytest.fixture()
def gateway(tmp_path, monkeypatch):
    """Шлюз на подменённом ядре; tailscaled запускается созданием tailscale0."""
    monkeypatch.setenv("XGW_ROOT", str(tmp_path / "root"))
    paths = Paths.from_env()
    paths.ensure()
    proc = tmp_path / "proc"
    (proc / "net/ipv4").mkdir(parents=True)
    (proc / sysctl.IP_FORWARD).write_text("0\n")
    cfg = _cfg(containers=False)
    fakexray.write(paths)
    kernel = FakeKernel()
    capture = Capture(cfg, paths, runner=kernel, proc_sys=proc, time_uids=())
    capture.kernel, capture.proc = kernel, proc
    capture.sys_net = tmp_path / "sys-class-net"
    capture.sys_net.mkdir()
    return capture


def _start_tailscaled(capture) -> None:
    (capture.sys_net / tailscale.INTERFACE).mkdir()


def _ipv6(capture) -> None:
    (capture.proc / "net/ipv6/conf/all").mkdir(parents=True)
    (capture.proc / "net/ipv6/conf/all/disable_ipv6").write_text("0\n")


def test_rules_appear_when_tailscaled_starts_and_go_when_it_stops(gateway):
    """Правила К1–К4 есть, только пока tailscaled работает. Запустился позже — правила уже
    не те (loaded() — False), и загрузка заново (демон, по событию или шагу) их добавляет."""
    assert gateway.enable() == "on"
    assert "tailscale0" not in gateway.kernel.table and gateway.loaded() is True
    _start_tailscaled(gateway)
    assert gateway.loaded() is False
    gateway.up()
    assert SKIP_TS in gateway.kernel.table and gateway.loaded() is True
    (gateway.sys_net / tailscale.INTERFACE).rmdir()
    assert gateway.loaded() is False
    gateway.up()
    assert "tailscale0" not in gateway.kernel.table and gateway.loaded() is True


def test_tailscaled_start_and_stop_wake_the_daemon():
    """Появление tailscale0 (`state DOWN` при создании) и его удаление — события сети (Ф2):
    демон сверяет правила сразу, а не на очередном шаге."""
    from xgw.watch import events

    created = ("6: tailscale0: <POINTOPOINT,MULTICAST,NOARP> mtu 1500 qdisc noop state DOWN "
               "group default qlen 500\\    link/none ")
    assert events.parse_net(created) == "tailscale0"
    assert events.parse_net("Deleted 6: tailscale0: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP> "
                            "mtu 1280 qdisc fq_codel state UNKNOWN") == "tailscale0"
    # Маршруты tailnet в таблице 52 меняются часто — шаг они не будят.
    assert events.parse_net("100.64.0.2 dev tailscale0 table 52") is None


def test_tailscaled_socket_alone_is_enough(gateway):
    """Без интерфейса (userspace-networking) tailscaled виден по сокету управления."""
    socket = tailscale.socket_path(gateway.paths)
    socket.parent.mkdir(parents=True)
    socket.write_text("")
    gateway.enable()
    assert SKIP_TS in gateway.kernel.table


def test_capture_local_off_needs_no_exceptions(gateway):
    gateway.cfg.capture.local = False
    _start_tailscaled(gateway)
    gateway.enable()
    assert SKIP_TS0 not in gateway.kernel.table and "ts_direct" not in gateway.kernel.table
    assert gateway.loaded() is True


def test_blocked_and_v6_guard_follow_tailscaled(gateway):
    _ipv6(gateway)
    _start_tailscaled(gateway)
    fakexray.write(gateway.paths, {"inbounds": []})  # inbound'а нет — режим blocked
    gateway.enable()
    assert "chain block_output" in gateway.kernel.table
    assert "meta mark and 0xff0000 == 0x80000 accept" in gateway.kernel.table
    assert 'oifname "tailscale0" accept' in gateway.kernel.table6
    assert gateway.loaded() is True and gateway.tailscale_loaded() is True


def test_route_vpn_moves_the_mark_without_reloading_the_tables(gateway):
    """route = "vpn": демон отмечает «Xray не отвечает» — метка ложится в набор одной
    командой (`add element`), без перезагрузки таблиц; отметка в /run переживает загрузку
    правил заново. Xray ответил — набор снова пуст."""
    _ipv6(gateway)
    _start_tailscaled(gateway)
    gateway.cfg.tailscale.route = "vpn"
    gateway.enable()
    assert _set(gateway.kernel.table) == ["type mark"] and gateway.loaded() is True
    loads = len(gateway.kernel.loads)
    assert gateway.tailscale_direct(True) == "Xray не отвечает — Tailscale идёт напрямую, мимо VPN"
    assert gateway.kernel.loads[loads:] == [
        "add element ip xgw ts_direct { 0x80000 }\nadd element ip6 xgw6 ts_direct { 0x80000 }\n"
    ]
    assert _set(gateway.kernel.table) == ["type mark", "elements = { 0x80000 }"]
    assert gateway.loaded() is True
    assert gateway.tailscale_direct(True) == ""  # уже — больше ничего
    assert len(gateway.kernel.loads) == loads + 1
    gateway.up()  # загрузка заново (flush, перезагрузка) — метка остаётся
    assert _set(gateway.kernel.table) == ["type mark", "elements = { 0x80000 }"]
    assert "Tailscale снова идёт через VPN" in gateway.tailscale_direct(False)
    assert _set(gateway.kernel.table) == ["type mark"] and gateway.loaded() is True
    assert not gateway.ts_marker.exists()


def test_route_direct_ignores_xray_outages(gateway):
    _start_tailscaled(gateway)
    gateway.enable()
    loads = len(gateway.kernel.loads)
    assert gateway.tailscale_direct(True) == ""
    assert len(gateway.kernel.loads) == loads and not gateway.ts_marker.exists()
    # route сменили с "vpn" на "direct", пока Xray не отвечал: отметка уходит молча.
    gateway.ts_marker.touch()
    assert gateway.tailscale_direct(True) == "" and not gateway.ts_marker.exists()
    assert gateway.loaded() is True


def test_mark_moved_by_someone_else_is_put_back(gateway):
    """Набор переложили мимо XGW — loaded() это видит, и загрузка заново его поправляет."""
    _start_tailscaled(gateway)
    gateway.enable()
    gateway.kernel(["nft", "-f", "-"], input="flush set ip xgw ts_direct\n")
    assert gateway.loaded() is False
    gateway.up()
    assert gateway.loaded() is True


def test_net_down_forgets_the_mark(gateway):
    gateway.cfg.tailscale.route = "vpn"
    _start_tailscaled(gateway)
    gateway.enable()
    gateway.tailscale_direct(True)
    gateway.down()
    assert not gateway.ts_marker.exists()


# --- config ---------------------------------------------------------------------


def test_route_setting(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[tailscale]\nroute = "VPN"\n', encoding="utf-8")
    cfg, warnings = config.load(path)
    assert cfg.tailscale.route == "vpn" and warnings == []
    path.write_text('[tailscale]\nroute = "exit"\n', encoding="utf-8")
    cfg, warnings = config.load(path)
    assert cfg.tailscale.route == "direct" and any("tailscale.route" in w for w in warnings)
    assert Config().tailscale.route == "direct"


# --- разбор вывода CLI ------------------------------------------------------------

# Отчёт `tailscale netcheck` 1.104.1 со шлюза (снимок Т0, адреса замаскированы).
NETCHECK = """\
2026/10/20 13:12:49 portmap: monitor: gateway and self IP changed: gw=192.168.50.1
2026/10/20 13:12:49 portmap: [v1] Got PCP response: epoch: 661931

Report:
\t* Time: 2026-10-20 13:12:51.102254288+03:00
\t* UDP: true
\t* IPv4: yes, 203.0.113.9:50789
\t* IPv6: no, but OS has support
\t* MappingVariesByDestIP: false
\t* PortMapping: UPnP, NAT-PMP, PCP
\t* CaptivePortal: false
\t* Nearest DERP: Frankfurt
\t* DERP latency:
\t\t- fra: 88.6ms  (Frankfurt)
\t\t- ams: 88.9ms  (Amsterdam)
\t\t- par: 138.7ms (Paris)
"""


def test_netcheck_is_parsed():
    found = tailscale.parse_netcheck(NETCHECK)
    assert found == tailscale.Netcheck(udp=True, derp="Frankfurt", latency_ms=88.6)
    no_udp = tailscale.parse_netcheck(NETCHECK.replace("UDP: true", "UDP: false"))
    assert no_udp.udp is False
    assert tailscale.parse_netcheck("") == tailscale.Netcheck()


def _status(state: str = "Running", **extra) -> str:
    return json.dumps({
        "Version": "1.104.1", "BackendState": state, "AuthURL": "",
        "Self": {"DNSName": "gw.tailnet-1.ts.net.", "TailscaleIPs": ["100.101.1.1", "fd7a::1"]},
        "CurrentTailnet": {"Name": "tailnet-1", "MagicDNSEnabled": True}, **extra,
    })


def test_status_is_read_carefully():
    """Поля читаются осторожно: нет поля — пусто, а не сбой."""
    state = tailscale.parse_status(_status())
    assert state.backend == "Running" and state.dns_name == "gw.tailnet-1.ts.net"
    assert state.addresses == ("100.101.1.1", "fd7a::1") and state.magic_dns is True
    bare = tailscale.parse_status('{"BackendState": "NeedsLogin", "Self": null}')
    assert bare == tailscale.Status(backend="NeedsLogin")
    assert tailscale.parse_status("tailscaled не запущен") is None
    assert tailscale.parse_status("[]") is None


# --- xgw diag ---------------------------------------------------------------------


class Box:
    """Машина после установки XGW, с подменённой системой и «ядром» без IPv6."""

    def __init__(self, tmp_path):
        self.paths = Paths(root=tmp_path / "root")
        self.paths.ensure()
        self.paths.systemd_dir.mkdir(parents=True, exist_ok=True)
        (self.paths.systemd_dir / "xgw.service").write_text("[Service]\n", encoding="utf-8")
        self.system = FakeSystem()
        self.cfg = _cfg(containers=False)
        self.proc = tmp_path / "proc"
        (self.proc / "net/ipv4").mkdir(parents=True)
        (self.proc / sysctl.IP_FORWARD).write_text("0\n")
        fakexray.write(self.paths)

    def capture(self) -> Capture:
        return Capture(self.cfg, self.paths, runner=self.system, proc_sys=self.proc)

    def tailscaled(self, state: str = "Running", **extra) -> None:
        socket = tailscale.socket_path(self.paths)
        socket.parent.mkdir(parents=True, exist_ok=True)
        socket.write_text("")
        self.system.tailscale_status = _status(state, **extra)

    def checks(self, **kwargs) -> dict[str, list]:
        options = {
            "runner": self.system, "net": False, "which": lambda name: f"/usr/bin/{name}",
            "is_root": True, "proc_sys": self.proc,
        }
        options.update(kwargs)
        found: dict[str, list] = {}
        for check in Diag(self.cfg, self.paths, **options)._tailscale():
            found.setdefault(check.name, []).append(check)
        return found


@pytest.fixture()
def box(tmp_path):
    return Box(tmp_path)


def test_diag_without_tailscale_is_not_an_error(box):
    checks = box.checks(which=lambda name: None if name == "tailscale" else f"/usr/bin/{name}")
    assert [(c.level, c.text) for c in checks["Tailscale"]] == [
        (OK, "не установлен — не используется")]
    assert box.checks()["Tailscale"][0].text == (
        "установлен, но tailscaled не запущен — не используется")


def test_diag_service_state(box):
    box.tailscaled("NeedsLogin", AuthURL="https://login.tailscale.com/a/abc123")
    service = box.checks()["Tailscale"][0]
    assert service.level == WARN and "нужен вход" in service.text
    assert "https://login.tailscale.com/a/abc123" in service.advice
    box.tailscaled()
    assert box.checks()["Tailscale"][0].level == OK


def test_diag_fails_when_tailscale_runs_without_the_exceptions(box):
    """Правила загружены до запуска tailscaled — исключений нет: FAIL с советом."""
    box.capture().enable()
    box.tailscaled()
    rules = box.checks()["Tailscale: правила"][0]
    assert rules.level == FAIL and "исключений" in rules.text
    assert rules.advice == "sudo xgw net up"
    assert box.checks(preinstall=True)["Tailscale: правила"][0].level == WARN
    box.capture().up()
    rules = box.checks()["Tailscale: правила"][0]
    assert rules.level == OK and "напрямую, мимо Xray" in rules.text


def test_diag_path_by_netcheck(box):
    box.tailscaled()
    box.system.tailscale_netcheck = NETCHECK
    path = box.checks(net=True)["Tailscale: связь"][0]
    assert path.level == OK and path.text == "UDP есть; ближайший DERP: Frankfurt, 88.6 мс"
    box.system.tailscale_netcheck = NETCHECK.replace("UDP: true", "UDP: false")
    path = box.checks(net=True)["Tailscale: связь"][0]
    assert path.level == WARN and "только через ретранслятор DERP" in path.text
    assert "Tailscale: связь" not in box.checks()  # без сети — не проверяется


def test_diag_cgnat_from_the_provider(box):
    """К5: адрес, шлюз или DNS провайдера из 100.64.0.0/10, а фаервол Tailscale (ts-input)
    включён — WARN с советом выключить его; адреса tailscale0 не в счёт."""
    box.tailscaled()
    ts_input = {"family": "ip", "table": "filter", "name": "ts-input"}
    box.system.addresses["tailscale0"] = ["100.101.1.1/32"]
    assert "Tailscale: CGNAT" not in box.checks()  # ts-input нет — отбрасывать некому
    box.system.nft_chains = [ts_input]
    clean = box.checks()["Tailscale: CGNAT"][0]
    assert clean.level == OK
    box.system.addresses["wan0"] = ["100.72.10.5/24"]
    box.system.gateway = "100.72.10.1"
    box.system.resolved_dns["wan0"] = "Link 2 (wan0): 100.72.0.53 192.168.1.1"
    warn = box.checks()["Tailscale: CGNAT"][0]
    assert warn.level == WARN and "Tailscale отбросит" in warn.text
    assert "адрес 100.72.10.0/24" in warn.text and "шлюз 100.72.10.1" in warn.text
    assert "DNS 100.72.0.53" in warn.text and "192.168.1.1" not in warn.text
    assert warn.advice.startswith("sudo tailscale set --netfilter-mode=off")


def test_diag_override_local_dns(box):
    """К6: у tailscale0 DefaultRoute — DNS машины идёт через Tailscale мимо VPN."""
    box.tailscaled()
    box.system.resolved["tailscale0"] = (
        "Link 6 (tailscale0)\n    Current Scopes: DNS\n"
        "         Protocols: -DefaultRoute -LLMNR -mDNS -DNSOverTLS DNSSEC=no/unsupported\n"
    )
    assert box.checks()["Tailscale: DNS"][0].level == OK
    box.system.resolved["tailscale0"] = box.system.resolved["tailscale0"].replace(
        "-DefaultRoute", "+DefaultRoute")
    dns = box.checks()["Tailscale: DNS"][0]
    assert dns.level == WARN and "Override local DNS" in dns.text
    assert "--accept-dns=false" in dns.advice


def test_foreign_tables_do_not_count_tailscale_chains(box):
    """Цепочки ts-* (и с политикой drop в nft-режиме Tailscale) — не посторонние."""
    box.system.nft_chains = [{"family": "ip", "table": "ts-filter", "name": "ts-forward",
                              "hook": "forward", "policy": "drop"}]
    checks = Diag(box.cfg, box.paths, runner=box.system, net=False, is_root=True,
                  which=lambda name: f"/usr/bin/{name}", proc_sys=box.proc)._firewall()
    assert [check.level for check in checks] == [OK]
