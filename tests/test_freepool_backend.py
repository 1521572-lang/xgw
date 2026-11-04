"""Туннельный бэкенд бесплатного пула (вехи М2а и М2в, docs/FREEPOOL-PLAN.md): агент поколения
(SSTP — sstpc и pppd), сторона демона, правила nftables и проверка туннелем в пуле. sstpc и
pppd здесь не запускаются — их проверяет ТЗ на машине заказчика; работники подставные."""

import io
import json
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from xgw.config import Config
from xgw.freepool import agent as agenting
from xgw.freepool import backend as backending
from xgw.net import cmd, nft
from xgw.paths import Paths, atomic_write_json

FIXTURES = Path(__file__).parent / "fixtures" / "freepool"
# Публичный адрес: документационные сети (198.51.100.0/24 образцов) peer_address не принимает.
PEER = "1.0.0.1"
HOST = "vpn-1.opengw.example"
GEN = "0123456789"
USERS = {agenting.VPN_USER: (990, 990), agenting.SOCKS_USER: (991, 991)}
TUNNEL, GATEWAY = "10.211.1.5", "10.211.254.254"  # так раздаёт SecureNAT серверов VPN Gate


def _wait(condition, seconds: float = 5.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "не дождались"
        time.sleep(0.02)


# --- агент поколения: задание, ключи клиента, охрана, разбор (agent.py) ----------------------


def _data(**changes) -> dict:
    data = {
        "gen": GEN, "index": 3, "peer": PEER, "port": 443, "host": HOST, "user": "vpn",
        "password": "vpn", "socks_pass": "s" * 24, "lan": ["192.168.50.0/24"],
        "xray_bin": "/opt/xgw/xray/xray", "sstpc_bin": "/usr/sbin/sstpc",
    }
    data.update(changes)
    return data


def _manifest(tmp_path, **changes) -> agenting.Manifest:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_data(**changes)), encoding="utf-8")
    return agenting.load_manifest(path, GEN)


def test_manifest_is_checked_field_by_field(tmp_path):
    """Агент — root, значения задания уходят в ip, nft, аргументы sstpc и файл ключей pppd:
    каждое поле проверяется."""
    manifest = _manifest(tmp_path)
    assert (manifest.index, manifest.peer, manifest.host) == (3, PEER, HOST)
    assert manifest.lan == ("192.168.50.0/24",)
    for change in ({"index": 64}, {"peer": "10.1.1.1"}, {"peer": "vpn.example"},
                   {"port": 70000}, {"host": "bad host"}, {"host": "-x.example"},
                   {"host": "x"}, {"user": 'vpn"'}, {"password": "a b"}, {"password": ""},
                   {"socks_pass": "short"}, {"socks_pass": "s" * 20 + " ;rm"},
                   {"xray_bin": "xray"}, {"sstpc_bin": "/usr/../bin/sh"}, {"lan": ["nope"]},
                   {"gen": "fedcba9876"}):
        with pytest.raises(agenting.AgentError) as info:
            _manifest(tmp_path, **change)
        assert info.value.code == "BAD_MANIFEST", change
    with pytest.raises(agenting.AgentError):
        agenting.load_manifest(tmp_path / "manifest.json", "../../etc")
    (tmp_path / "manifest.json").write_text("{", encoding="utf-8")
    with pytest.raises(agenting.AgentError):
        agenting.load_manifest(tmp_path / "manifest.json", GEN)


def test_sstpc_and_pppd_get_only_what_the_tunnel_needs(tmp_path):
    """sstpc: журнал — в вывод агента (не syslog), цепочка сертификата — по системным, имя — в
    HTTP (SNI не посылается: без --tls-ext), без --cert-warn и без маршрута к серверу (его
    ставит агент), права — xgw-vpn после подключения; ключи pppd — файлом (у sstpc под них
    массив на 20 мест): интерфейс fpt0, без маршрута по умолчанию, DNS сервера и IPv6."""
    manifest = _manifest(tmp_path)
    options = tmp_path / "ppp.options"
    argv = agenting.sstpc_argv(manifest, options)
    assert argv[0] == "/usr/sbin/sstpc"
    assert argv[1:4] == ["--log-stderr", "--log-level", "2"]
    def value(option: str) -> str:
        return argv[argv.index(option) + 1]

    # --ca-path, а не --ca-dir: такого ключа у sstpc нет (отчёт М2в.1).
    assert value("--ca-path") == "/etc/ssl/certs" and value("--host") == HOST
    # Только ключи из таблицы getopt_long sstp-option.c 1.0.18 и 1.0.20 (и --log-*, их снимает
    # sstp-log.c): неизвестный ключ — sstpc завершается, не подключаясь.
    known = {"--ca-cert", "--ca-path", "--cert-warn", "--help", "--host", "--ipparam",
             "--nolaunchpppd", "--password", "--priv-user", "--priv-group", "--priv-dir",
             "--proxy", "--user", "--uuid", "--save-server-route", "--tls-ext", "--version",
             "--crl-file", "--crl-path", "--log-level", "--log-stderr"}
    assert {item for item in argv if item.startswith("--")} <= known
    assert (value("--user"), value("--password")) == ("vpn", "vpn")
    assert (value("--priv-user"), value("--priv-group")) == ("xgw-vpn", "xgw-vpn")
    for forbidden in ("--cert-warn", "--tls-ext", "--save-server-route", "--priv-dir",
                      "--nolaunchpppd"):
        assert forbidden not in argv
    server = argv.index(f"{PEER}:443")
    assert argv[server + 1:] == ["file", str(options)]
    lines = agenting.ppp_options().splitlines()
    for line in ("ifname fpt0", "nodetach", "logfd 2", "noauth", "noipdefault",
                 "nodefaultroute", "noipv6", "require-mschap-v2", "refuse-pap", "refuse-eap"):
        assert line in lines, line
    for line in lines:
        assert line.split()[0] not in ("defaultroute", "usepeerdns", "persist", "noresolvconf",
                                       "replacedefaultroute", "proxyarp")


def test_guard_opens_only_the_server_and_the_tunnel(tmp_path):
    """Охрана (R46): таблица заменяется только своя; к серверу через veth — только root (сокет
    sstpc создан до сброса прав), xgw-vpn — никуда; SOCKS — только в туннель; всё прочее на
    выходе — отказ со счётчиком, форвардинга нет."""
    text = agenting.guard_rules(_manifest(tmp_path), 990, 991)
    assert text.startswith("table inet xgwfp\ndelete table inet xgwfp\ntable inet xgwfp {\n")
    assert "flush" not in text and text.count("policy drop") == 3
    assert f'meta skuid 0 oifname "fpi3" ip daddr {PEER} tcp dport 443 accept' in text
    assert 'meta skuid 991 oifname "fpt0" meta nfproto ipv4 accept' in text
    assert 'oif "lo" meta skuid 0 accept' in text
    output = text.split("chain output {")[1].split("chain forward")[0]
    rules = [line.strip() for line in output.splitlines() if line.strip() not in ("", "}")]
    # Отчёт М2а.1: отбитое — по отправителю; служебный IPv6 ядра — не в отбитое.
    assert all(f"counter {name} {{ }}" in text for name in agenting.COUNTERS)
    assert rules[1] == 'meta nfproto ipv6 counter name "dropped_v6" drop'
    reject = "reject with icmpx type admin-prohibited"
    assert rules[-3:] == [f'meta skuid {{ 0, 990 }} counter name "refused_vpn" {reject}',
                          f'meta skuid 991 counter name "refused_socks" {reject}',
                          f'counter name "refused_other" {reject}']
    # Пользователю VPN не открыто ничего; работнику на lo — ничего (готовность — /proc/net/tcp).
    assert not any("990" in rule and "accept" in rule for rule in rules)
    assert not any("991" in rule and '"lo"' in rule for rule in rules)
    forward = text.split("chain forward {")[1].split("}")[0]
    assert "accept" not in forward


def test_socks_worker_listens_on_veth_with_a_password(tmp_path):
    config = agenting.socks_config(_manifest(tmp_path))
    [inbound] = config["inbounds"]
    assert (inbound["listen"], inbound["port"]) == ("10.250.3.2", agenting.SOCKS_PORT)
    assert inbound["settings"]["auth"] == "password" and inbound["settings"]["udp"] is True
    assert inbound["settings"]["accounts"] == [{"user": "xgw", "pass": "s" * 24}]
    assert config["outbounds"][0]["protocol"] == "freedom"
    # Отчёт М2а.2: с UseIPv4 Xray спрашивал системный резолвер (127.0.0.53 на lo).
    assert config["outbounds"][0]["streamSettings"]["sockopt"]["domainStrategy"] == "ForceIPv4"
    assert config["dns"]["servers"] == ["1.1.1.1", "8.8.8.8"]
    with_gateway = agenting.socks_config(_manifest(tmp_path), [GATEWAY, "1.1.1.1", GATEWAY])
    assert with_gateway["dns"]["servers"] == [GATEWAY, "1.1.1.1"]


def test_tunnel_addresses_come_from_the_ppp_interface():
    """Подъём — адрес на fpt0 (IPCP): свой и другой конец PPP из `ip -4 -o addr`; MTU — из
    `ip -o link`."""
    line = (f"8: fpt0    inet {TUNNEL} peer {GATEWAY}/32 scope global fpt0\\       "
            "valid_lft forever preferred_lft forever\n")
    assert agenting.parse_addr(line) == (TUNNEL, GATEWAY)
    assert agenting.parse_addr(f"8: fpt0    inet {TUNNEL}/32 scope global fpt0\n") == (TUNNEL, "")
    assert agenting.parse_addr("") == ("", "")
    assert agenting.parse_addr('Device "fpt0" does not exist.') == ("", "")
    assert agenting.parse_mtu("8: fpt0: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP> mtu 1400 "
                              "qdisc fq_codel state UNKNOWN mode DEFAULT") == 1400
    assert agenting.parse_mtu("") == 0


def test_tunnel_address_from_the_server_is_untrusted(tmp_path):
    manifest = _manifest(tmp_path)
    assert agenting.tunnel_problem(TUNNEL, manifest) == ""
    for address in ("8.8.8.8", "127.0.0.2", "169.254.1.1", "10.250.3.9", "192.168.50.7", "x"):
        assert agenting.tunnel_problem(address, manifest), address


def test_failure_codes_from_the_client_output():
    """Строки sstpc 1.0.20 и pppd (по их исходникам) → код; более точная причина — раньше
    общей «TCP или TLS не сложились»."""
    assert agenting.classify(["CHAP authentication failed"]) == "AUTH_FAILED"
    assert agenting.classify(["MS-CHAP authentication failed: E=691"]) == "AUTH_FAILED"
    assert agenting.classify(["SSL certificate verification failed: unable to get local "
                              "issuer certificate (20)",
                              "Verification of server certificate failed"]) \
        == "CERT_VERIFY_FAILED"
    assert agenting.classify(["HTTP handshake with server failed"]) == "SSTP_REFUSED"
    assert agenting.classify(["LCP: timeout sending Config-Requests"]) == "PPP_TIMEOUT"
    assert agenting.classify(["No response to 3 echo-requests",
                              "Serial link appears to be disconnected."]) == "LINK_LOST"
    assert agenting.classify(["Could not setup notification"]) == "SSTPC_SOCKET"
    assert agenting.classify(["Could not complete connect to the client"]) == "CONNECT_FAILED"
    assert agenting.classify(["Could not complete connect to the client",
                              "connect: Connection refused"]) == "CONNECT_REFUSED"
    # «No route to host» — ICMP с пути (или охрана: run решает по её счётчику), «Network is
    # unreachable» — нет маршрута у себя (дефект шлюза). Отчёт М2а: оба были одним кодом.
    assert agenting.classify(["connect: No route to host"]) == "HOST_UNREACHABLE"
    assert agenting.classify(["connect: Network is unreachable"]) == "NETWORK_UNREACHABLE"
    assert agenting.classify([]) == "UNKNOWN"
    # Этапы sstpc (отчёт М2в.2, sstp-stream.c и sstp-http.c 1.0.20): SYN без ответа 10 с —
    # CONNECT_TIMEOUT; обрыв на TLS — TLS_FAILED; туннель не поднялся за UP_WAIT без строки
    # ошибки — этап, до которого дошёл клиент.
    assert agenting.classify(["Connect timed out", "Could not complete connect to the client"]) \
        == "CONNECT_TIMEOUT"
    assert agenting.classify(["Connected to x", "Unrecoverable SSL error -1",
                              "HTTP handshake with server failed"]) == "TLS_FAILED"
    connected = [f"Resolved {HOST} to 1.0.0.1", f"Connected to {HOST}"]
    assert agenting.classify(connected) == "UNKNOWN"
    assert agenting.classify(connected, timed_out=True) == "SSTP_NO_REPLY"
    assert agenting.classify([*connected, "Started PPP Link Negotiation"], timed_out=True) \
        == "PPP_TIMEOUT"
    assert agenting.classify(connected[:1], timed_out=True) == "TIMEOUT"
    assert agenting.evidence(connected, "SSTP_NO_REPLY") == "Connected to <host>"
    # sstpc не принял свою строку — дефект шлюза, а не UNKNOWN (отчёт М2в.1).
    assert agenting.classify(["**Error: Could not execute `/usr/sbin/sstpc', Invalid command "
                              "line option: `?' (-1)"]) == "SSTPC_ARGS"
    # В журнал службы — строка с причиной, но без адресов и имён хостов.
    assert agenting.evidence(["Connected to 1.0.0.1", "Could not connect to `1.0.0.1:443'"],
                             "CONNECT_FAILED") == "Could not connect to `<ip>:443'"
    assert agenting.evidence(["Connected"], "AUTH_FAILED") == ""
    assert agenting.evidence([f"Connected to {HOST}", "read failed from 1.0.0.1, ret -1"],
                             "UNKNOWN") == "read failed from <ip>, ret -1"
    assert agenting.masked(f"Connected to {HOST}") == "Connected to <host>"
    assert agenting.masked("plugin sstp-pppd-plugin.so loaded") \
        == "plugin sstp-pppd-plugin.so loaded"


def test_inner_check_and_tunnel_counters_are_told_without_addresses():
    """Проверка изнутри: вывод дочернего процесса → итоги по меткам (адреса DNS в журнал не
    идут); DNS работника — ответившие первыми; счётчики fpt0 из `ip -s link`."""
    servers = agenting.inner_servers([GATEWAY])
    assert servers == [("шлюза туннеля", GATEWAY), ("Cloudflare", "1.1.1.1")]
    inner = agenting.parse_inner(f"tcp OPEN 120\ndns {GATEWAY} TIMEOUT\ndns 1.1.1.1 OK 35\n",
                                 servers)
    assert inner == {"tcp": "OPEN 120",
                     "dns": [["шлюза туннеля", "TIMEOUT"], ["Cloudflare", "OK 35"]]}
    assert agenting.inner_text(inner) == ("TCP Cloudflare:443 — OPEN (120 мс); DNS шлюза "
                                          "туннеля — TIMEOUT; DNS Cloudflare — OK (35 мс)")
    assert agenting.worker_dns(servers, inner) == ["1.1.1.1", GATEWAY, "8.8.8.8"]
    assert agenting.parse_inner("garbage", servers)["tcp"] == "—"
    assert agenting.inner_servers([]) == [("Cloudflare", "1.1.1.1")]
    text = ("8: fpt0: <POINTOPOINT,UP> mtu 1400 qdisc fq_codel state UNKNOWN\n"
            "    link/ppp \n"
            "    RX:  bytes packets errors dropped  missed   mcast\n"
            "          2048       3      0       0       0       0\n"
            "    TX:  bytes packets errors dropped carrier collsns\n"
            "         10240      12      0       0       0       0\n")
    stats = agenting.parse_link_stats(text)
    assert stats == {"rx_bytes": 2048, "rx_packets": 3, "tx_bytes": 10240, "tx_packets": 12}
    assert agenting.tunnel_text(stats) == ("в туннель 12 пакетов (10 КБ), из туннеля 3 пакетов "
                                           "(2 КБ)")
    assert agenting.parse_link_stats("8: fpt0: <UP>\n") is None
    assert agenting.deltas({"refused_vpn": 2, "refused_socks": -1}, {
        "refused_vpn": 5, "refused_socks": 3}) == {"refused_vpn": 3}
    assert agenting.guard_text({"refused_vpn": 0, "refused_socks": 20, "refused_other": 2,
                                "dropped_v6": 5}) \
        == "клиент VPN 0, работник 20, ответы ядра 2, служебный IPv6 5"
    assert agenting.guard_text({}) == ""
    # Канал к серверу (fpi): RX — от сервера, TX — к нему.
    delta = agenting.link_delta(
        {"rx_bytes": 1000, "rx_packets": 5, "tx_bytes": 2000, "tx_packets": 8},
        {"rx_bytes": 4096, "rx_packets": 9, "tx_bytes": 7120, "tx_packets": 20})
    assert agenting.link_text(delta) == ("от сервера 4 пакетов (3 КБ), к серверу 12 пакетов "
                                         "(5 КБ)")
    assert agenting.link_delta(None, delta) is None and agenting.link_text(None) == ""


_LISTEN = ("  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid\n"
           "   0: 0100007F:1D51 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0\n"
           "   1: 0203FA0A:0438 00000000:0000 0A 00000000:00000000 00:00000000 00000000   991\n")


def test_socks_readiness_and_core_failure_reasons():
    """Порт работника — по /proc/net/tcp (LISTEN, порт hex); причина отказа ядра — последнее
    звено цепочки Xray или строка FATAL sing-box, без секретов, адресов и имён."""
    assert agenting.listening(_LISTEN, 1080) and agenting.listening(_LISTEN, 7505)
    assert not agenting.listening(_LISTEN.replace(":0438 00000000:0000 0A",
                                                  ":0438 0A00000A:9C40 01"), 1080)
    assert not agenting.listening(_LISTEN.splitlines()[0], 1080)
    key = "5Yi9hS3Vk3jRVFJ6AHVNMw=="
    assert agenting.core_reason([
        "2026/10/28 22:53:38 [Info] infra/conf/serial: Reading config",
        f"Failed to start: main: failed to create server > proxy/shadowsocks_2022: invalid key: "
        f"{key} > proxy/shadowsocks_2022: bad key",
        "2026/10/28 22:53:38 [Warning] common/errors: The feature Shadowsocks is deprecated "
        "and might be removed",
    ], {f"{key}:{key}"}) == "proxy/shadowsocks_2022: bad key"
    pbk = "KMxOyjmYIWpwGe_lfbKyS5r5FOpofIhE3rhoqy-MYbg"
    reason = agenting.core_reason([
        "Failed to start: main: failed to load config files: [/tmp/pool-x/config.json] > "
        "infra/conf: Failed to build REALITY config. > infra/conf: invalid \"password\": "
        f"{pbk}"], {pbk})
    assert reason == 'invalid "password": ***'
    assert agenting.core_reason([
        "FATAL[0000] start service: initialize outbound[0]: dial 198.51.100.7 at "
        "h.example.org failed"]) \
        == "start service: initialize outbound[0]: dial <ip> at <host> failed"
    assert agenting.core_reason(["started", "[Warning] might be removed"]) == ""


# --- агент поколения: ход с подставными работниками -------------------------------------------


class _Runner:
    """Подставные ip и nft внутри пространства имён агента. address — адрес fpt0 (пусто —
    туннеля нет); grow — счётчики охраны, которые растут на единицу при каждом чтении."""

    def __init__(self, *, grow=()) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.counters = dict.fromkeys(agenting.COUNTERS, 0)
        self.grow = set(grow)
        self.address, self.gateway = "", ""

    def __call__(self, argv, *, input=None, timeout=15.0, check=True) -> str:
        self.calls.append(tuple(argv))
        if argv[:3] == ["ip", "-o", "link"]:
            if argv[-1] == "fpt0":
                return ("8: fpt0: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP> mtu 1400\n"
                        if self.address else "")
            return "7: fpi3@if8: <BROADCAST,MULTICAST> mtu 1500\n"
        if argv[:4] == ["ip", "-4", "-o", "addr"]:
            if not self.address:
                return ""
            return (f"8: fpt0    inet {self.address} peer {self.gateway}/32 scope global fpt0"
                    "\\       valid_lft forever preferred_lft forever\n")
        if argv[:3] == ["ip", "-s", "link"]:
            return ("8: fpt0: <POINTOPOINT,UP> mtu 1400\n    link/ppp\n"
                    "    RX:  bytes packets errors dropped  missed   mcast\n"
                    "             0       0      0       0       0       0\n"
                    "    TX:  bytes packets errors dropped carrier collsns\n"
                    "          4096       9      0       0       0       0\n")
        if argv[:3] == ["nft", "list", "counter"]:
            name = argv[-1]
            if name in self.grow:
                self.counters[name] += 1
            return (f"table inet xgwfp {{ counter {name} {{ packets {self.counters[name]} "
                    "bytes 0 } }")
        return ""


class _Proc:
    """Подставной процесс: работник (жив до terminate или до exit) или проба (ответ)."""

    def __init__(self, lines=(), out: str = "", exited: bool = False) -> None:
        self.stdout = iter(lines)
        self.out = out
        self.returncode = 1 if exited else None

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def communicate(self, timeout=None):
        self.returncode = 0
        return self.out, ""


class _Spawn:
    def __init__(self, probe: str = "ENETUNREACH", client_lines=(), client_exits=False,
                 inner: str = "tcp TIMEOUT\ndns 1.1.1.1 TIMEOUT\n") -> None:
        self.probe, self.client_lines, self.client_exits = probe, client_lines, client_exits
        self.inner = inner
        self.workers: list[tuple[str, int, int]] = []
        self.inner_args: list[tuple] = []
        self.client: _Proc | None = None
        self.client_argv: list[str] = []

    def __call__(self, argv, **kwargs):
        if argv[1] == "-I" and "recvfrom" in argv[3]:  # проверка изнутри
            self.inner_args.append((tuple(argv[4:]), kwargs["user"]))
            return _Proc(out=self.inner)
        if argv[1] == "-I":  # самопроверка охраны
            return _Proc(out=self.probe + "\n")
        self.workers.append((argv[0], kwargs["user"], kwargs["group"]))
        if argv[0].endswith("sstpc"):
            self.client_argv = list(argv)
            self.client = _Proc(lines=self.client_lines, exited=self.client_exits)
            return self.client
        return _Proc()


def _agent(tmp_path, monkeypatch, *, runner=None, spawn=None, proc_tcp=lambda: _LISTEN):
    monkeypatch.setattr(agenting, "POLL_EVERY", 0.01)
    monkeypatch.setattr(agenting, "STATS_EVERY", 0.05)
    paths = Paths(root=tmp_path / "root")
    paths.ensure()
    path = agenting.manifest_path(paths, GEN)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_data()), encoding="utf-8")
    chowned: list[tuple[str, int, int]] = []
    monkeypatch.setattr(agenting.os, "chown",
                        lambda target, uid, gid: chowned.append((Path(target).name, uid, gid)))
    agent = agenting.Agent(
        paths, GEN, runner=runner or _Runner(), spawn=spawn or _Spawn(),
        users=USERS.__getitem__, tmp=tmp_path / "tmp", out=io.StringIO(), proc_tcp=proc_tcp,
    )
    (tmp_path / "tmp").mkdir()
    return agent, chowned


def _start(agent) -> list[int]:
    result: list[int] = []
    thread = threading.Thread(target=lambda: result.append(agent.run()), daemon=True)
    thread.start()
    agent.thread = thread
    return result


def test_agent_guards_first_and_routes_only_while_the_tunnel_is_up(tmp_path, monkeypatch):
    """Порядок: охрана → «guarded» → veth → самопроверка → файл ключей pppd → sstpc от root →
    адрес на fpt0: маршрут по умолчанию, проверка изнутри (от пользователя SOCKS, DNS шлюза
    туннеля) и только затем SOCKS-работник; остановка — фаза stopped и итог туннеля в
    журнале, без адресов."""
    runner = _Runner()
    spawn = _Spawn(client_lines=[f"Connected to {HOST}",
                                 "Could not set process user id, Operation not permitted (1)"],
                   inner=f"tcp OPEN 90\ndns {GATEWAY} OK 20\ndns 1.1.1.1 TIMEOUT\n")
    agent, chowned = _agent(tmp_path, monkeypatch, runner=runner, spawn=spawn)
    result = _start(agent)
    _wait(lambda: agent.state.get("phase") == "connecting")
    calls = runner.calls
    assert calls[:2] == [("ip", "link", "set", "lo", "up"), ("nft", "-f", "-")]
    assert not any(call[:2] == ("ip", "tuntap") for call in calls)  # интерфейс создаёт pppd
    assert ("ip", "route", "add", f"{PEER}/32", "via", "10.250.3.1", "dev", "fpi3") in calls
    assert not any(call[:3] == ("ip", "route", "replace") for call in calls)
    assert spawn.workers == [("/usr/sbin/sstpc", 0, 0)]  # SOCKS — только с туннелем
    assert spawn.client_argv[-2:] == ["file", str(tmp_path / "tmp" / "xgw-vpn" / "ppp.options")]
    assert agent.state["selftest"]["ok"] is True
    assert set(agent.state["selftest"]["results"]) == {
        "socks_to_peer", "socks_to_internet", "vpn_to_peer", "vpn_to_host", "vpn_to_internet"}
    options = tmp_path / "tmp" / "xgw-vpn" / "ppp.options"
    assert options.read_text(encoding="utf-8") == agenting.ppp_options()
    assert oct(options.stat().st_mode & 0o777) == "0o640" and ("ppp.options", 0, 0) in chowned
    assert not (tmp_path / "tmp" / "xgw-socks").exists()

    runner.address, runner.gateway = TUNNEL, GATEWAY
    _wait(lambda: agent.state.get("phase") == "up")
    assert ("ip", "route", "replace", "default", "dev", "fpt0") in runner.calls
    assert not any(call[:3] == ("ip", "addr", "add") and call[-1] == "fpt0"
                   for call in runner.calls)  # адрес ставит pppd
    assert (agent.state["tunnel"], agent.state["mtu"]) == (TUNNEL, 1400)
    assert spawn.inner_args == [((GATEWAY, "1.1.1.1"), 991)]
    assert agent.state["inner"]["tcp"] == "OPEN 90"
    assert spawn.workers == [("/usr/sbin/sstpc", 0, 0), ("/opt/xgw/xray/xray", 991, 991)]
    socks = json.loads((tmp_path / "tmp" / "xgw-socks" / "socks.json").read_text(
        encoding="utf-8"))
    assert socks["dns"]["servers"] == [GATEWAY, "1.1.1.1", "8.8.8.8"]
    assert ("socks.json", 0, 991) in chowned
    journal = agent.out.getvalue()
    assert ("через туннель: TCP Cloudflare:443 — OPEN (90 мс); DNS шлюза туннеля — OK (20 мс)"
            in journal) and "10.211." not in journal
    # «Туннель поднят» — до проверки изнутри; готовность работника — без подключения к нему.
    assert journal.index("туннель поднят, MTU 1400") < journal.index("через туннель:") \
        < journal.index("SOCKS-работник готов")
    assert agent.state["tunnel_at"] > 0
    _wait(lambda: "tun" in agent.state)  # счётчики, пока туннель поднят
    agent.stop.set()
    agent.thread.join(5)
    assert result == [0] and agent.state["phase"] == "stopped"
    saved = json.loads(agenting.state_path(agent.paths, GEN).read_text(encoding="utf-8"))
    assert saved["phase"] == "stopped" and saved["tun"]["tx_packets"] == 9
    assert saved["refused_after_up"] == dict.fromkeys(agenting.COUNTERS, 0)
    assert saved["link_after_up"] == {"rx_bytes": 0, "rx_packets": 0, "tx_bytes": 0,
                                      "tx_packets": 0}
    assert ("итог туннеля: в туннель 9 пакетов (4 КБ), из туннеля 0 пакетов (0 КБ); канал к "
            "серверу после подъёма: от сервера 0 пакетов (0 КБ), к серверу 0 пакетов (0 КБ); "
            "охрана после подъёма: клиент VPN 0, работник 0, ответы ядра 0, служебный IPv6 0; "
            "предупреждения клиента: Could not set process user id, Operation not permitted "
            "(1)") in agent.out.getvalue()
    assert saved["notices"] == ["Could not set process user id, Operation not permitted (1)"]
    assert HOST not in agent.out.getvalue()


def test_lost_link_ends_the_generation(tmp_path, monkeypatch):
    """Адрес fpt0 пропал (pppd завершился: эхо LCP без ответа) — LINK_LOST; переподключения нет
    — поколение заменяет демон; итог туннеля — один раз, со счётчиками последнего снимка."""
    runner = _Runner()
    spawn = _Spawn(client_lines=["No response to 3 echo-requests",
                                 "Serial link appears to be disconnected."])
    agent, _chowned = _agent(tmp_path, monkeypatch, runner=runner, spawn=spawn)
    result = _start(agent)
    _wait(lambda: agent.state.get("phase") == "connecting")
    runner.address, runner.gateway = TUNNEL, GATEWAY
    _wait(lambda: agent.state.get("phase") == "up")
    runner.address = ""
    agent.thread.join(5)
    assert result == [3]
    saved = json.loads(agenting.state_path(agent.paths, GEN).read_text(encoding="utf-8"))
    assert (saved["phase"], saved["reason"]) == ("failed", "LINK_LOST")
    journal = agent.out.getvalue()
    assert journal.count("итог туннеля:") == 1
    assert journal.index("итог туннеля:") < journal.index(f"поколение {GEN}: LINK_LOST")
    assert "SSTP: No response to 3 echo-requests" in journal


def test_guard_refusal_before_the_tunnel_is_a_gateway_defect(tmp_path, monkeypatch):
    """«No route to host» при подключении: вырос счётчик пакетов клиента — GUARD_BLOCKED
    (дефект шлюза; код по выводу клиента — рядом); выросли только ответы ядра и служебный
    IPv6 (отчёт М2а.1) или ничего — HOST_UNREACHABLE (ICMP с пути к серверу, не дефект)."""
    lines = ["Could not complete connect to the client", "connect: No route to host"]
    cases = (({agenting.REFUSED_VPN}, "GUARD_BLOCKED"),
             ({agenting.REFUSED_OTHER, agenting.DROPPED_V6}, "HOST_UNREACHABLE"),
             ((), "HOST_UNREACHABLE"))
    for number, (grow, code) in enumerate(cases):
        (tmp_path / str(number)).mkdir()
        runner = _Runner(grow=grow)
        agent, _chowned = _agent(tmp_path / str(number), monkeypatch, runner=runner,
                                 spawn=_Spawn(client_lines=lines, client_exits=True))
        if grow:  # самопроверка с растущими счётчиками не нужна здесь
            agent._selftest = lambda manifest, ids: {}
        assert agent.run() == 3
        assert agent.state["reason"] == code and agent.state["client_code"] == "HOST_UNREACHABLE"
        journal = agent.out.getvalue()
        assert "SSTP: connect: No route to host" in journal
        assert ("охрана за подключение:" in journal) is bool(grow)
        assert ("(по выводу клиента: HOST_UNREACHABLE)" in journal) is (code == "GUARD_BLOCKED")
        assert "итог туннеля" not in journal  # туннель не поднимался


def test_worker_failure_after_the_tunnel_keeps_what_was_seen_inside(tmp_path, monkeypatch):
    """Туннель поднялся, а работник порт не открыл: SOCKS_FAILED, но в состоянии раньше фазы
    failed — что туннель был, проверка изнутри и итог туннеля (демон берёт их в запись)."""
    monkeypatch.setattr(agenting, "SOCKS_WAIT", 0.3)
    runner = _Runner()
    runner.address, runner.gateway = TUNNEL, GATEWAY
    agent, _chowned = _agent(tmp_path, monkeypatch, runner=runner,
                             proc_tcp=lambda: _LISTEN.splitlines()[0])
    assert agent.run() == 3
    saved = json.loads(agenting.state_path(agent.paths, GEN).read_text(encoding="utf-8"))
    assert (saved["phase"], saved["reason"]) == ("failed", "SOCKS_FAILED")
    assert saved["tunnel_at"] > 0 and saved["inner"]["tcp"] == "TIMEOUT"
    assert saved["tun"]["tx_packets"] == 9 and saved["refused_after_up"]["refused_socks"] == 0
    journal = agent.out.getvalue()
    assert journal.index("итог туннеля:") < journal.index(f"поколение {GEN}: SOCKS_FAILED")
    assert journal.count("итог туннеля:") == 1


@pytest.mark.parametrize("lines, code", [
    (["MS-CHAP authentication failed: E=691", "CHAP authentication failed"], "AUTH_FAILED"),
    (["SSL certificate verification failed: self-signed certificate (18)",
      "Verification of server certificate failed"], "CERT_VERIFY_FAILED"),
    (["HTTP handshake with server failed"], "SSTP_REFUSED"),
    ([], "UNKNOWN"),
])
def test_client_refusal_ends_the_generation(tmp_path, monkeypatch, lines, code):
    agent, _chowned = _agent(tmp_path, monkeypatch,
                             spawn=_Spawn(client_lines=lines, client_exits=True))
    assert agent.run() == 3
    assert (agent.state["phase"], agent.state["reason"]) == ("failed", code)
    journal = agent.out.getvalue()
    assert "охрана проверена: socks_to_peer ENETUNREACH" in journal and PEER not in journal


def test_tunnel_that_never_comes_up_times_out_with_the_ppp_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(agenting, "UP_WAIT", 0.2)
    agent, _chowned = _agent(tmp_path, monkeypatch, spawn=_Spawn(
        client_lines=["LCP: timeout sending Config-Requests"]))
    assert agent.run() == 3 and agent.state["reason"] == "PPP_TIMEOUT"
    (tmp_path / "quiet").mkdir()
    quiet, _chowned = _agent(tmp_path / "quiet", monkeypatch)  # клиент молчит
    assert quiet.run() == 3 and quiet.state["reason"] == "TIMEOUT"
    # Отчёт М2в.2: TCP и TLS прошли, а на запрос SSTP сервер молчит — этап, а не UNKNOWN.
    (tmp_path / "silent").mkdir()
    silent, _chowned = _agent(tmp_path / "silent", monkeypatch, spawn=_Spawn(
        client_lines=[f"Resolved {PEER} to {PEER}", f"Connected to {PEER}"]))
    assert silent.run() == 3 and silent.state["reason"] == "SSTP_NO_REPLY"
    assert "SSTP: Connected to <ip>" in silent.out.getvalue()


def test_foreign_tunnel_address_is_refused(tmp_path, monkeypatch):
    runner = _Runner()
    runner.address, runner.gateway = "8.8.8.8", GATEWAY
    agent, _chowned = _agent(tmp_path, monkeypatch, runner=runner)
    assert agent.run() == 3 and agent.state["reason"] == "BAD_TUNNEL_ADDRESS"
    assert not any(call[:3] == ("ip", "route", "replace") for call in runner.calls)


def test_open_guard_stops_before_any_worker(tmp_path, monkeypatch):
    """Самопроверка нашла выход мимо туннеля — GUARD_FAILED, клиент не запускается."""
    spawn = _Spawn(probe="OPEN")
    agent, _chowned = _agent(tmp_path, monkeypatch, spawn=spawn)
    assert agent.run() == 3
    assert (agent.state["phase"], agent.state["reason"]) == ("failed", "GUARD_FAILED")
    assert spawn.workers == [] and not (tmp_path / "tmp" / "xgw-vpn").exists()


def test_refusal_counts_as_closed_only_with_the_guard_counter(tmp_path, monkeypatch):
    """ECONNREFUSED и прочие отказы — «закрыто охраной», только если вырос счётчик этого
    пользователя (refused_socks, refused_vpn); вырос чужой (ответы ядра) или никакой — пакет
    мог уйти, и это провал самопроверки."""
    agent, _chowned = _agent(
        tmp_path, monkeypatch, spawn=_Spawn(probe="ECONNREFUSED"),
        runner=_Runner(grow={agenting.REFUSED_VPN, agenting.REFUSED_SOCKS}))
    manifest = _manifest(tmp_path)
    ids = {"vpn": USERS[agenting.VPN_USER], "socks": USERS[agenting.SOCKS_USER]}
    results = agent._selftest(manifest, ids)
    assert all(value == "ECONNREFUSED (охрана)" for value in results.values())
    for grow in ({agenting.REFUSED_OTHER, agenting.DROPPED_V6}, ()):
        agent.runner = _Runner(grow=grow)
        with pytest.raises(agenting.AgentError) as info:
            agent._selftest(manifest, ids)
        assert info.value.code == "GUARD_FAILED"


# --- сторона демона (backend.py) --------------------------------------------------------------


class _HostRunner:
    """Подставные systemctl, ip и nft хоста; «служба» сразу пишет фазу агента."""

    def __init__(self, paths: Paths, *, phase: str = "guarded", fail: tuple = (),
                 active: str = "active") -> None:
        self.paths, self.phase, self.fail, self.active = paths, phase, fail, active
        self.calls: list[tuple[str, ...]] = []
        self.units = ""

    def __call__(self, argv, *, input=None, timeout=15.0, check=True) -> str:
        self.calls.append(tuple(argv))
        if self.fail and tuple(argv[:len(self.fail)]) == self.fail:
            raise cmd.CommandError(f"{argv[0]}: отказ")
        if argv[:2] == ["systemctl", "start"]:
            gen = argv[2].split("@")[1].split(".")[0]
            atomic_write_json(agenting.state_path(self.paths, gen),
                              {"phase": self.phase, "reason": "NO_USER"}, mode=0o600)
        if argv[:3] == ["systemctl", "show", "-p"]:
            return "4242\n"
        if argv[:2] == ["systemctl", "is-active"]:
            return self.active + "\n"
        if argv[:2] == ["systemctl", "list-units"]:
            return self.units
        return ""


def _backend(tmp_path, **runner):
    paths = Paths(root=tmp_path / "root")
    paths.ensure()
    host = _HostRunner(paths, **runner)
    clock = [100.0]
    backend = backending.Backend(paths, runner=host, clock=lambda: clock[0],
                                 sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
                                 sys_net=tmp_path / "sys-class-net")
    (tmp_path / "sys-class-net").mkdir()
    return backend, host, paths


def _prepare(backend):
    return backend.prepare(peer=PEER, port=443, host=HOST, user="vpn", password="vpn",
                           lan=("192.168.50.0/24",), xray_bin=Path("/opt/xgw/xray/xray"))


def test_generation_is_prepared_in_order_and_removed_without_traces(tmp_path):
    """Адрес — в peers.json и fp_peers раньше veth; veth внутрь — только после фазы guarded;
    задание агент принимает как есть; остановка убирает службу, veth, адрес и каталог."""
    backend, host, paths = _backend(tmp_path)
    lease = _prepare(backend)
    element = f"{PEER} . tcp . 443"
    assert (lease.index, lease.pid, lease.element) == (1, 4242, element)
    calls = host.calls
    add = calls.index(("nft", "add", "element", "ip", "xgw", "fp_peers", "{", element, "}"))
    veth = calls.index(("ip", "link", "add", "fpv1", "type", "veth", "peer", "name", "fpi1"))
    start = calls.index(("systemctl", "start", lease.unit))
    move = calls.index(("ip", "link", "set", "dev", "fpi1", "netns", "4242"))
    assert add < veth < start < move
    manifest_file = agenting.manifest_path(paths, lease.gen)
    assert oct(manifest_file.stat().st_mode & 0o777) == "0o600"
    manifest = agenting.load_manifest(manifest_file, lease.gen)
    assert (manifest.peer, manifest.index, manifest.socks_pass) == (PEER, 1, lease.socks_pass)
    assert (manifest.host, manifest.sstpc_bin) == (HOST, "/usr/sbin/sstpc")
    assert backending.peer_elements(paths) == (element,)

    backend.stop(lease)
    assert ("systemctl", "stop", lease.unit) in host.calls
    assert ("ip", "link", "del", "dev", "fpv1") in host.calls
    assert ("nft", "delete", "element", "ip", "xgw", "fp_peers", "{", element, "}") in host.calls
    assert not agenting.run_dir(paths, lease.gen).exists()
    assert backending.peer_elements(paths) == () and backend.leases == {}


@pytest.mark.parametrize("runner, code", [
    ({"fail": ("ip", "link", "add")}, "BACKEND_START"),
    ({"phase": "failed"}, "NO_USER"),  # агент отказал до охраны
])
def test_failed_preparation_leaves_nothing_behind(tmp_path, runner, code):
    backend, host, paths = _backend(tmp_path, **runner)
    with pytest.raises(backending.BackendError) as info:
        _prepare(backend)
    assert info.value.code == code
    assert any(call[:3] == ("nft", "delete", "element") for call in host.calls)
    assert any(call[:4] == ("ip", "link", "del", "dev") for call in host.calls)
    assert backending.peer_elements(paths) == () and backend.leases == {}
    assert not [entry for entry in (paths.run / "fp").iterdir() if entry.is_dir()]


def test_waiting_ends_on_up_on_exit_and_on_the_deadline(tmp_path):
    backend, host, paths = _backend(tmp_path)
    lease = _prepare(backend)
    state = agenting.state_path(paths, lease.gen)
    atomic_write_json(state, {"phase": "up", "tunnel": TUNNEL}, mode=0o600)
    assert backend.wait(lease)["phase"] == "up"
    atomic_write_json(state, {"phase": "connecting"}, mode=0o600)
    host.active = "failed"
    assert backend.wait(lease)["reason"] == "AGENT_EXITED"
    host.active = "active"
    assert backend.wait(lease)["reason"] == "TIMEOUT"  # часы идут подставным sleep
    stop = threading.Event()
    stop.set()
    assert backend.wait(lease, cancel=stop)["phase"] == "failed"


def test_traffic_is_counted_on_the_host_veth(tmp_path):
    backend, _host, _paths = _backend(tmp_path)
    lease = backending.Lease(gen=GEN, index=5, peer=PEER, port=443)
    assert backend.counters(lease) == 0
    stats = tmp_path / "sys-class-net" / "fpv5" / "statistics"
    stats.mkdir(parents=True)
    (stats / "rx_bytes").write_text("1200\n", encoding="ascii")
    (stats / "tx_bytes").write_text("300\n", encoding="ascii")
    assert backend.counters(lease) == 1500


def test_reconcile_removes_generations_of_a_previous_daemon(tmp_path):
    backend, host, paths = _backend(tmp_path)
    host.units = "xgw-fp@aaaaaaaaaa.service loaded failed failed XGW\n"
    (tmp_path / "sys-class-net" / "fpv9").mkdir()
    (tmp_path / "sys-class-net" / "eth0").mkdir()
    stale = paths.run / "fp" / "bbbbbbbbbb"
    stale.mkdir(parents=True)
    assert backend.reconcile() == 2
    assert ("systemctl", "stop", "xgw-fp@aaaaaaaaaa.service") in host.calls
    assert ("ip", "link", "del", "dev", "fpv9") in host.calls
    assert not any(call[-1] == "eth0" for call in host.calls)  # чужие интерфейсы не трогаются
    assert ("nft", "flush", "set", "ip", "xgw", "fp_peers") in host.calls
    assert not stale.exists()


def test_peer_elements_accept_only_address_proto_port(tmp_path):
    paths = Paths(root=tmp_path)
    paths.ensure()
    file = backending.peers_file(paths)
    file.parent.mkdir(parents=True)
    file.write_text(json.dumps({"peers": [f"{PEER} . tcp . 443", "1.2.3.4 . tcp . 1; flush",
                                          f"{PEER} . tcp . 443", 7]}), encoding="utf-8")
    assert backending.peer_elements(paths) == (f"{PEER} . tcp . 443",)


def test_backend_unavailable_says_why(tmp_path):
    """Без sstpc и pppd, модуля sstp-pppd-plugin.so, /dev/ppp, пользователей, службы,
    пересылки IPv4 или набора fp_peers — проверки туннелем нет, и причина видна в сводке и в
    xgw diag."""
    paths = Paths(root=tmp_path / "root")
    paths.ensure()
    sstpc, pppd = tmp_path / "sstpc", tmp_path / "pppd"
    plugins, ppp = tmp_path / "pppd-plugins", tmp_path / "dev-ppp"
    proc_sys = tmp_path / "proc-sys"
    (proc_sys / "net" / "ipv4").mkdir(parents=True)
    forward = proc_sys / "net" / "ipv4" / "ip_forward"
    known: set[str] = set()

    def users(name: str):
        if name not in known:
            raise KeyError(name)
        return name

    def nft_ok(argv, **kwargs) -> str:
        return ""

    def check(runner=nft_ok) -> str:
        return backending.unavailable(paths, runner, sstpc=sstpc, pppd=pppd, plugins=plugins,
                                      ppp_device=ppp, users=users, proc_sys=proc_sys)

    assert "нет клиента SSTP (пакет sstp-client" in check()
    sstpc.write_text("", encoding="utf-8")
    assert "нет клиента SSTP" in check()  # без pppd — тоже
    pppd.write_text("", encoding="utf-8")
    assert "нет модуля pppd sstp-pppd-plugin.so" in check()
    (plugins / "2.5.2").mkdir(parents=True)
    (plugins / "2.5.2" / "sstp-pppd-plugin.so").write_text("", encoding="utf-8")
    assert "нет устройства /dev/ppp" in check()
    ppp.write_text("", encoding="utf-8")
    assert "нет пользователя xgw-vpn" in check()
    known.update(USERS)
    assert "нет службы xgw-fp@.service" in check()
    paths.systemd_dir.mkdir(parents=True, exist_ok=True)
    (paths.systemd_dir / "xgw-fp@.service").write_text("[Service]\n", encoding="utf-8")
    assert "пересылка IPv4 выключена" in check()
    forward.write_text("0\n", encoding="ascii")
    assert "пересылка IPv4 выключена" in check()
    forward.write_text("1\n", encoding="ascii")

    def nft_missing(argv, **kwargs) -> str:
        raise cmd.CommandError("Error: No such file or directory")

    assert "нет набора fp_peers" in check(nft_missing)
    assert check() == ""


# --- правила хоста (net/nft.py) ---------------------------------------------------------------


def _forward_rules(text: str) -> list[str]:
    body = text.split("chain forward {")[1].split("\n    }")[0]
    return [line.strip() for line in body.splitlines()[2:] if line.strip()]


@pytest.mark.parametrize("lan_if, capture", [("lan0", True), ("lan0", False), ("", True)])
def test_pool_rules_exist_only_with_the_pool_and_go_first(lan_if, capture):
    """Набор fp_peers, форвардинг из fpv* только к нему (первым — раньше «чужого
    форвардинга») и маскарадинг 10.250.0.0/16 — только при free_pool.mode не off."""
    cfg = Config()
    cfg.network.lan_if = lan_if
    element = f"{PEER} . tcp . 443"
    off = nft.render(nft.build_rules(cfg, capture=capture, time_uids=(),
                                     fp_peers=(element,))[0])
    assert "fp_peers" not in off and "fpv" not in off and "10.250." not in off
    cfg.free_pool.mode = "observe"
    text = nft.render(nft.build_rules(cfg, capture=capture, time_uids=(), fp_peers=(element,))[0])
    assert "type ipv4_addr . inet_proto . inet_service" in text
    assert f"elements = {{ {element} }}" in text
    assert _forward_rules(text)[:2] == [
        'iifname "fpv*" ip daddr . meta l4proto . th dport @fp_peers counter accept',
        'iifname "fpv*" counter drop',
    ]
    assert 'ip saddr 10.250.0.0/16 oifname != "fpv*" counter masquerade' in text
    assert "flush" not in text


# --- проверка туннелем в пуле (pool.py, probe.py) ----------------------------------------------


class _Runtime:
    """Подставной бэкенд: поколение поднимается сразу, трафик — по «счётчикам veth»."""

    def __init__(self) -> None:
        self.prepared: list[dict] = []
        self.stopped: list[str] = []

    def reconcile(self) -> int:
        return 0

    def prepare(self, **kwargs) -> backending.Lease:
        self.prepared.append(kwargs)
        return backending.Lease(gen=GEN, index=1, peer=kwargs["peer"], port=kwargs["port"],
                                socks_pass="p" * 24)

    def wait(self, lease, *, cancel=None) -> dict:
        return {"phase": "up", "tunnel": TUNNEL}

    def counters(self, lease) -> int:
        return 700_000

    def state(self, lease) -> dict:  # что агент записал к концу пробы
        return {"phase": "up", "inner": {"tcp": "TIMEOUT", "dns": [["Cloudflare", "TIMEOUT"]]},
                "tun": {"tx_packets": 30, "tx_bytes": 2048, "rx_packets": 0, "rx_bytes": 0}}

    def stop(self, lease) -> None:
        self.stopped.append(lease.gen)


def _gate_variants(count: int, **changes):
    from xgw.freepool import providers

    catalog = providers.parse_vpngate((FIXTURES / "vpngate.html").read_text(encoding="utf-8"),
                                      now=1_800_000_000.0)
    first = catalog.variants[0]
    return [replace(first, host=f"vpn{index}.opengw.example", address=PEER, country_hint="DE",
                    **changes) for index in range(count)]


def test_sstp_server_is_checked_through_its_tunnel(tmp_path, monkeypatch):
    """Бэкенд годится — сервер SSTP проверяется настоящим туннелем: временный Xray идёт через
    SOCKS-работника поколения; задание — адрес, порт, имя и общий вход VPN Gate; трафик —
    больший из счётчиков; поколение убирается; подключений — не больше одного за шаг и не
    больше предела в час (R26, R29)."""
    from xgw.freepool import pool as pool_module
    from xgw.freepool import probe as probe_module
    from xgw.freepool.models import ProviderResult, Status
    from xgw.freepool.pool import FreePool
    from xgw.freepool.probe import Outcome

    paths = Paths(root=tmp_path / "root")
    paths.ensure()
    cfg = Config()
    cfg.free_pool.mode = "observe"
    cfg.free_pool.providers = ["vpngate"]
    cfg.free_pool.handshakes_per_hour = 1
    variants = _gate_variants(2)
    runtime = _Runtime()
    pool = FreePool(cfg, paths, runtime=runtime, clock=lambda: 1_800_000_100.0,
                    sleep=lambda seconds: None)
    pool.store.commit(ProviderResult("vpngate", Status.SUCCESS, variants=variants,
                                     retrieved_at=1_800_000_000.0, complete_response=True))
    monkeypatch.setattr(pool_module.backending, "unavailable", lambda *args, **kwargs: "")
    seen: list[dict] = []

    def check_xray(variant, cfg, xray_bin, run_dir, spawn=None):
        seen.append(variant.outbound)
        return Outcome("OK", 0.6, 600_000, "DE")

    monkeypatch.setattr(probe_module, "check_xray", check_xray)
    assert pool.check_some(mark=2, xray_bin=Path("/opt/xgw/xray/xray"),
                           via=("127.0.0.1", 10809)) == 1
    assert len(runtime.prepared) == 1 and runtime.stopped == [GEN]
    prepared = runtime.prepared[0]
    assert (prepared["peer"], prepared["port"], prepared["user"], prepared["password"]) == (
        PEER, 443, "vpn", "vpn")
    assert prepared["host"] in {variant.host for variant in variants}
    assert seen == [{"tag": "pool", "protocol": "socks", "settings": {"servers": [{
        "address": "10.250.1.2", "port": 1080, "users": [{"user": "xgw", "pass": "p" * 24}],
    }]}}]
    summary = pool.summary()
    assert (summary["tunnels_up"], summary["handshakes_hour"], summary["ready"]) == (1, 1, 1)
    assert summary["tunnel_attempts"] == 1
    assert summary["tunnel_backend"] == "" and summary["by_region"] == {"EU": 1}
    assert pool.spent_today() == 700_000
    # Что агент видел изнутри — в записи кандидата и журнале демона, без адресов.
    [record] = [value for key, value in pool.store.candidates().items()
                if not key.startswith("_")]
    assert record["backend"] == "sstp"
    assert record["diagnosis"] == ("TCP Cloudflare:443 — TIMEOUT; DNS Cloudflare — TIMEOUT; "
                                   "в туннель 30 пакетов (2 КБ), из туннеля 0 пакетов (0 КБ)")
    # Предел подключений в час (1) исчерпан — второй сервер ждёт, а не подключается.
    assert pool.check_some(mark=2, xray_bin=Path("/opt/xgw/xray/xray")) == 0
    assert len(runtime.prepared) == 1
    # Сервер ушёл из списка VPN Gate — итог по нему убран, а журнал подключений за сутки
    # помнит попытку (отчёт М2в.1: сводка показывала 2–3 при 18).
    left = [variant for variant in variants if variant.host != prepared["host"]]
    pool.store.commit(ProviderResult("vpngate", Status.SUCCESS, variants=left,
                                     retrieved_at=1_800_000_050.0, complete_response=True))
    pool._prune_candidates()
    summary = pool.summary()
    assert (summary["tunnel_attempts"], summary["tunnels_up"]) == (1, 1)


def test_tunnel_that_came_up_is_recorded_even_when_the_worker_fails(tmp_path):
    """Отчёт М2а.1: туннели поднялись, работник отказал — а в записях ни «туннель поднимался»,
    ни что видно изнутри. Теперь — и то и другое, вместе с отбитым охраной после подъёма."""
    from xgw.freepool import probe as probe_module

    [variant] = _gate_variants(1)

    class Failing(_Runtime):
        def wait(self, lease, *, cancel=None) -> dict:
            return {**_Runtime.state(self, lease), "phase": "failed", "reason": "SOCKS_FAILED",
                    "detail": "SOCKS-работник не открыл порт", "tunnel_at": 1_800_000_050.0,
                    "link_after_up": {"rx_packets": 4, "rx_bytes": 2048, "tx_packets": 12,
                                      "tx_bytes": 4096},
                    "refused_after_up": {"refused_vpn": 0, "refused_socks": 20,
                                         "refused_other": 1, "dropped_v6": 4}}

    runtime = Failing()
    outcome = probe_module.check_tunnel(
        variant, runtime=runtime, cfg=Config(), xray_bin=Path("/opt/xgw/xray/xray"),
        run_dir=tmp_path, user="vpn", password="vpn")
    assert (outcome.verdict, outcome.tunnel_up) == ("SOCKS_FAILED", True)
    assert outcome.diagnosis == (
        "TCP Cloudflare:443 — TIMEOUT; DNS Cloudflare — TIMEOUT; в туннель 30 пакетов (2 КБ), "
        "из туннеля 0 пакетов (0 КБ); канал к серверу: от сервера 4 пакетов (2 КБ), к серверу "
        "12 пакетов (4 КБ); охрана после подъёма: клиент VPN 0, работник 20, ответы ядра 1, "
        "служебный IPv6 4")
    assert runtime.stopped == [GEN]


def test_without_backend_sstp_falls_back_to_the_address_check(tmp_path, monkeypatch):
    """Бэкенда нет — у сервера SSTP проверяется только TCP к публичному адресу напрямую, а
    причина видна в сводке."""
    from xgw.freepool import pool as pool_module
    from xgw.freepool import probe as probe_module

    paths = Paths(root=tmp_path / "root")
    paths.ensure()
    cfg = Config()
    cfg.free_pool.mode = "observe"
    pool = pool_module.FreePool(cfg, paths, runtime=_Runtime(), sleep=lambda seconds: None)
    monkeypatch.setattr(pool_module.backending, "unavailable",
                        lambda *args, **kwargs: "нет клиента SSTP (пакет sstp-client — ставит "
                        "xgw install)")
    assert pool.refresh_backend().startswith("нет клиента SSTP")
    assert "проверка туннелем недоступна: нет клиента SSTP" in pool_module.render(
        pool.summary(), 0)
    [variant] = _gate_variants(1)
    calls: list[tuple] = []

    def tcp_check(address, port, *, timeout, mark):
        calls.append((address, port, mark))
        return True

    assert probe_module.check_tunnel_reach(variant, 2, tcp_check=tcp_check).verdict \
        == "REACHABLE"
    assert calls == [(PEER, 443, 2)]
    private = replace(variant, address="198.51.100.7")
    assert probe_module.check_tunnel_reach(private, 2, tcp_check=tcp_check).verdict \
        == "UNTESTED" and len(calls) == 1


def _tunnel_pool(tmp_path, monkeypatch, catalogs: dict, **values):
    """Пул с подставным бэкендом и каталогами {источник: [варианты]}; проба через туннель —
    всегда OK из Германии."""
    from xgw.freepool import pool as pool_module
    from xgw.freepool import probe as probe_module
    from xgw.freepool.models import ProviderResult, Status
    from xgw.freepool.pool import FreePool
    from xgw.freepool.probe import Outcome

    paths = Paths(root=tmp_path / "root")
    paths.ensure()
    cfg = Config()
    cfg.free_pool.mode = "observe"
    cfg.free_pool.providers = list(catalogs)
    for name, value in values.items():
        setattr(cfg.free_pool, name, value)
    clock = [1_800_000_100.0]
    runtime = _Runtime()
    pool = FreePool(cfg, paths, runtime=runtime, clock=lambda: clock[0],
                    sleep=lambda seconds: None)
    for provider, variants in catalogs.items():
        pool.store.commit(ProviderResult(provider, Status.SUCCESS, variants=variants,
                                         retrieved_at=clock[0], complete_response=True))
    monkeypatch.setattr(pool_module.backending, "unavailable", lambda *args, **kwargs: "")
    monkeypatch.setattr(probe_module, "check_xray",
                        lambda variant, cfg, xray_bin, run_dir, spawn=None:
                        Outcome("OK", 0.6, 600_000, "DE"))
    return pool, runtime, clock


def test_exhausted_source_does_not_block_the_other(tmp_path, monkeypatch):
    """У одного источника предел подключений в час исчерпан — следующим шагом подключается
    сервер другого (здесь — подставной второй источник туннелей), даже если перед ним в
    очереди много серверов первого."""
    gate = _gate_variants(9)
    book = [replace(_gate_variants(1)[0], provider="vpnbook", host="book.opengw.example",
                    country_hint="")]
    pool, runtime, clock = _tunnel_pool(tmp_path, monkeypatch, {"vpngate": gate,
                                                                "vpnbook": book},
                                        provider_handshakes_per_hour=1)
    xray = Path("/opt/xgw/xray/xray")
    assert pool.check_some(mark=2, xray_bin=xray) == 1
    clock[0] += 60
    assert pool.check_some(mark=2, xray_bin=xray) == 1
    assert [item["peer"] for item in runtime.prepared] == [PEER, PEER]
    assert sorted(item[1] for item in pool.handshakes()) == ["vpnbook", "vpngate"]


def test_exhausted_day_limit_says_when_it_frees(tmp_path, monkeypatch):
    """Отчёт М2а.3: ночное наблюдение заняло суточный предел, а в сводке было только
    «подключений за час 0». Теперь — сколько из предела и когда освободится следующее."""
    from xgw.freepool import pool as pool_module

    pool, runtime, clock = _tunnel_pool(tmp_path, monkeypatch, {"vpngate": _gate_variants(3)},
                                        handshakes_per_day=2)
    xray = Path("/opt/xgw/xray/xray")
    first = clock[0]
    assert pool.check_some(mark=2, xray_bin=xray) == 1
    summary = pool.summary()
    assert (summary["handshakes_day"], summary["handshakes_day_limit"],
            summary["handshakes_free_at"]) == (1, 2, 0.0)
    assert "за сутки 1 из 2\n" in pool_module.render(summary, clock[0]) + "\n"
    clock[0] += 3600
    assert pool.check_some(mark=2, xray_bin=xray) == 1
    clock[0] += 3600
    assert pool.check_some(mark=2, xray_bin=xray) == 0
    summary = pool.summary()
    assert summary["handshakes_free_at"] == first + pool_module.DAY
    text = pool_module.render(summary, clock[0])
    assert "за сутки 2 из 2 — суточный предел занят, следующее после " in text
    assert len(runtime.prepared) == 2


def test_address_only_result_does_not_delay_the_tunnel(tmp_path, monkeypatch):
    """Сервер, у которого без бэкенда проверили только адрес (REACHABLE), туннелем проверяется
    сразу; закрытый адрес (CLOSED) — нет: туннель к нему не дойдёт."""
    reachable, closed = _gate_variants(2)
    pool, _runtime, clock = _tunnel_pool(tmp_path, monkeypatch, {"vpngate": [reachable, closed]})
    state = pool.store.candidates()
    for variant, verdict in ((reachable, "REACHABLE"), (closed, "CLOSED")):
        state[variant.variant_id] = {"checked_at": clock[0] - 60, "verdict": verdict,
                                     "backend": "sstp", "provider": "vpngate"}
    pool.store.save_candidates(state)
    assert pool.next_checks(None) == []
    assert [variant.variant_id for variant in pool.next_checks(None, tunnels=True)] == [
        reachable.variant_id]


def test_server_without_public_address_spends_no_handshake(tmp_path, monkeypatch):
    private = [replace(variant, address="198.51.100.7") for variant in _gate_variants(1)]
    pool, runtime, _clock = _tunnel_pool(tmp_path, monkeypatch, {"vpngate": private})
    assert pool.check_some(mark=2, xray_bin=Path("/opt/xgw/xray/xray")) == 1
    [record] = [value for key, value in pool.store.candidates().items()
                if not key.startswith("_")]
    assert (record["verdict"], record["error"]) == ("UNTESTED", "у сервера нет публичного IPv4")
    assert runtime.prepared == [] and pool.handshakes() == []
