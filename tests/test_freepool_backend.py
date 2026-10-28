"""Бэкенд OpenVPN бесплатного пула (веха М2а, docs/FREEPOOL-PLAN.md): конфиг клиента, агент
поколения, сторона демона, правила nftables и проверка туннелем в пуле. Сам OpenVPN здесь не
запускается (решение заказчика 28.10.2026) — работники и интерфейс управления подставные."""

import io
import json
import socket
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from xgw.config import Config
from xgw.freepool import agent as agenting
from xgw.freepool import backend as backending
from xgw.freepool import ovpn, ovpnconf
from xgw.net import cmd, nft
from xgw.paths import Paths, atomic_write_json

FIXTURES = Path(__file__).parent / "fixtures" / "freepool"
# Публичный адрес: документационные сети (198.51.100.0/24 образцов) peer_address не принимает.
PEER = "1.0.0.1"
GEN = "0123456789"
USERS = {agenting.OVPN_USER: (990, 990), agenting.SOCKS_USER: (991, 991)}


def _profile() -> ovpn.OvpnProfile:
    return ovpn.parse((FIXTURES / "vpnbook-profile.ovpn").read_text(encoding="utf-8"))


def _wait(condition, seconds: float = 5.0) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "не дождались"
        time.sleep(0.02)


# --- конфиг клиента (ovpnconf.py) -------------------------------------------------------------


def test_client_config_is_built_anew_from_the_parsed_profile():
    """Из профиля источника берутся только шифры, ключи и проверка сервера; адрес — один,
    закреплённый; маршрутов, скриптов и DNS сервера нет; учётка — файлом без кэша."""
    text = ovpnconf.client_config(_profile(), remote_ip=PEER, proto="tcp", port=443,
                                  with_auth=True, mgmt_port=agenting.MGMT_PORT)
    lines = text.splitlines()
    for line in ("client", "dev fpt0", "dev-type tun", "proto tcp-client", f"remote {PEER} 443",
                 "nobind", "ifconfig-noexec", "route-noexec", "disable-dco", "script-security 1",
                 'pull-filter ignore "redirect-gateway"', 'pull-filter ignore "route"',
                 'pull-filter ignore "dhcp-option"', "tls-version-min 1.2", "auth SHA256",
                 "auth-retry none", "auth-user-pass /tmp/xgw-ovpn/auth", "auth-nocache",
                 f"management 127.0.0.1 {agenting.MGMT_PORT}"):
        assert line in lines, line
    assert any(line.startswith("data-ciphers AES-256-GCM") for line in lines)
    assert "198.51.100.30" not in text and "dev tun1" not in text  # remote и dev источника
    assert "\nredirect-gateway" not in text and "explicit-exit-notify" not in text
    assert text.count("<ca>") == 1 and "<cert>" in text and "<key>" in text
    assert all(line == line.rstrip() for line in lines)
    udp = ovpnconf.client_config(_profile(), remote_ip=PEER, proto="udp", port=1194,
                                 with_auth=False, mgmt_port=7505).splitlines()
    assert "proto udp" in udp and "explicit-exit-notify 1" in udp
    assert not any(line.startswith("auth-user-pass") for line in udp)


@pytest.mark.parametrize("remote, proto, port", [
    ("10.0.0.1", "tcp", 443),  # частный
    ("198.51.100.7", "tcp", 443),  # документационный — не публичный
    ("vpn.example", "udp", 1194),  # имя здесь не резолвится (R45)
    (PEER, "icmp", 443),
    (PEER, "tcp", 0),
])
def test_client_config_refuses_what_it_cannot_pin(remote, proto, port):
    with pytest.raises(ovpn.OvpnRejected):
        ovpnconf.client_config(_profile(), remote_ip=remote, proto=proto, port=port,
                               with_auth=False, mgmt_port=7505)


def test_server_check_is_passed_on_but_never_weakened():
    with pytest.raises(ovpn.OvpnRejected):
        ovpnconf.client_config(replace(_profile(), remote_cert_tls="client"), remote_ip=PEER,
                               proto="tcp", port=443, with_auth=False, mgmt_port=7505)
    with pytest.raises(ovpn.OvpnRejected):  # кавычка сломала бы строку конфига
        ovpnconf.client_config(replace(_profile(), verify_x509_name='vpn" --up /bin/sh'),
                               remote_ip=PEER, proto="tcp", port=443, with_auth=False,
                               mgmt_port=7505)
    text = ovpnconf.client_config(
        replace(_profile(), remote_cert_tls="server", verify_x509_name="vpn.example name"),
        remote_ip=PEER, proto="tcp", port=443, with_auth=False, mgmt_port=7505)
    assert "remote-cert-tls server" in text and 'verify-x509-name "vpn.example" name' in text


def test_auth_file_takes_two_plain_lines_only():
    assert ovpnconf.auth_text("vpn", "vpn") == "vpn\nvpn\n"
    for username, password in (("", "x"), ("a\nb", "x"), ("a", "x\r"), ("a", "x" * 300)):
        with pytest.raises(ovpn.OvpnRejected):
            ovpnconf.auth_text(username, password)


# --- агент поколения: задание, охрана, разбор (agent.py) ---------------------------------------


def _data(**changes) -> dict:
    data = {
        "gen": GEN, "index": 3, "peer": PEER, "proto": "udp", "port": 1194,
        "openvpn_conf": "client\n", "auth": "fpuser\nFakePass77\n", "socks_pass": "s" * 24,
        "lan": ["192.168.50.0/24"], "xray_bin": "/opt/xgw/xray/xray",
        "openvpn_bin": "/usr/sbin/openvpn",
    }
    data.update(changes)
    return data


def _manifest(tmp_path, **changes) -> agenting.Manifest:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_data(**changes)), encoding="utf-8")
    return agenting.load_manifest(path, GEN)


def test_manifest_is_checked_field_by_field(tmp_path):
    """Агент — root, значения задания уходят в ip, nft и конфиги: каждое поле проверяется."""
    manifest = _manifest(tmp_path)
    assert (manifest.index, manifest.peer, manifest.lan) == (3, PEER, ("192.168.50.0/24",))
    for change in ({"index": 64}, {"peer": "10.1.1.1"}, {"peer": "vpn.example"},
                   {"proto": "icmp"}, {"port": 70000}, {"socks_pass": "short"},
                   {"socks_pass": "s" * 20 + " ;rm"}, {"xray_bin": "xray"},
                   {"openvpn_bin": "/usr/../bin/sh"}, {"lan": ["nope"]}, {"openvpn_conf": ""},
                   {"gen": "fedcba9876"}):
        with pytest.raises(agenting.AgentError) as info:
            _manifest(tmp_path, **change)
        assert info.value.code == "BAD_MANIFEST", change
    with pytest.raises(agenting.AgentError):
        agenting.load_manifest(tmp_path / "manifest.json", "../../etc")
    (tmp_path / "manifest.json").write_text("{", encoding="utf-8")
    with pytest.raises(agenting.AgentError):
        agenting.load_manifest(tmp_path / "manifest.json", GEN)


def test_guard_opens_only_the_server_and_the_tunnel(tmp_path):
    """Охрана (R46): таблица заменяется только своя; OpenVPN — только к серверу через veth,
    SOCKS — только в туннель; всё прочее на выходе — отказ со счётчиком, форвардинга нет."""
    text = agenting.guard_rules(_manifest(tmp_path), 990, 991)
    assert text.startswith("table inet xgwfp\ndelete table inet xgwfp\ntable inet xgwfp {\n")
    assert "flush" not in text and text.count("policy drop") == 3
    assert (f'meta skuid 990 oifname "fpi3" ip daddr {PEER} meta l4proto udp th dport 1194 '
            "accept") in text
    assert 'meta skuid 991 oifname "fpt0" meta nfproto ipv4 accept' in text
    assert 'oif "lo" meta skuid { 0, 990 } accept' in text  # управление — root и OpenVPN
    output = text.split("chain output {")[1].split("chain forward")[0]
    rules = [line.strip() for line in output.splitlines() if line.strip() not in ("", "}")]
    assert rules[-1] == 'counter name "refused_out" reject with icmpx type admin-prohibited'
    forward = text.split("chain forward {")[1].split("}")[0]
    assert "accept" not in forward


def test_socks_worker_listens_on_veth_with_a_password(tmp_path):
    config = agenting.socks_config(_manifest(tmp_path))
    [inbound] = config["inbounds"]
    assert (inbound["listen"], inbound["port"]) == ("10.250.3.2", agenting.SOCKS_PORT)
    assert inbound["settings"]["auth"] == "password" and inbound["settings"]["udp"] is True
    assert inbound["settings"]["accounts"] == [{"user": "xgw", "pass": "s" * 24}]
    assert config["outbounds"][0]["protocol"] == "freedom"
    assert config["dns"]["servers"] == ["1.1.1.1", "8.8.8.8"]
    with_server = agenting.socks_config(_manifest(tmp_path), ["10.8.0.1", "1.1.1.1", "10.8.0.1"])
    assert with_server["dns"]["servers"] == ["10.8.0.1", "1.1.1.1"]


def test_management_lines_and_pushed_options():
    assert agenting.parse_state(f">STATE:1730000000,CONNECTED,SUCCESS,10.8.0.6,{PEER},1194,,") \
        == ("CONNECTED", "SUCCESS", "10.8.0.6")
    assert agenting.parse_state("1730000001,RECONNECTING,ping-restart,,,,,") == (
        "RECONNECTING", "ping-restart", "")
    assert agenting.parse_state("SUCCESS: real-time state notification set to ON") is None
    line = ("PUSH: Received control message: 'PUSH_REPLY,route 10.8.0.1,topology net30,"
            "ping 10,ping-restart 120,ifconfig 10.8.0.6 10.8.0.5,tun-mtu 1400,peer-id 0'")
    assert agenting.pushed(line) == ("10.8.0.6", 1400)
    assert agenting.pushed("Initialization Sequence Completed") == ("", 0)
    # DNS сервера: в конфиг не принимается (pull-filter), но для работника — первым.
    dns = ("PUSH: Received control message: 'PUSH_REPLY,dhcp-option DNS 10.8.0.1,dhcp-option "
           "DNS 127.0.0.1,dhcp-option DNS 10.250.1.1,dhcp-option DNS 8.8.4.4,dhcp-option DNS "
           "9.9.9.9,ifconfig 10.8.0.6 10.8.0.5'")
    assert agenting.pushed_dns(dns) == ["10.8.0.1", "8.8.4.4"]
    assert agenting.pushed_dns("dhcp-option DNS 10.8.0.1") == []  # не из PUSH_REPLY


def test_tunnel_address_from_the_server_is_untrusted(tmp_path):
    manifest = _manifest(tmp_path)
    assert agenting.tunnel_problem("10.8.0.6", manifest) == ""
    for address in ("8.8.8.8", "127.0.0.2", "169.254.1.1", "10.250.3.9", "192.168.50.7", "x"):
        assert agenting.tunnel_problem(address, manifest), address


def test_failure_codes_from_the_openvpn_journal():
    assert agenting.classify(["AUTH: Received control message: AUTH_FAILED"]) == "AUTH_FAILED"
    assert agenting.classify(["TLS Error: TLS key negotiation failed to occur within 60 "
                              "seconds (check your network connectivity)"]) \
        == "TLS_HANDSHAKE_FAILED"
    assert agenting.classify(["VERIFY ERROR: depth=0, error=certificate has expired"]) \
        == "CERT_VERIFY_FAILED"
    assert agenting.classify(["TCP: connect to [AF_INET]1.0.0.1:443 failed: Connection "
                              "refused"]) == "CONNECT_REFUSED"
    assert agenting.classify([]) == "UNKNOWN"
    # В журнал службы — строка с причиной, но без адресов.
    assert agenting.evidence(["Initialization", "TCP: connect to [AF_INET]1.0.0.1:443 failed: "
                              "Connection refused"], "CONNECT_REFUSED") \
        == "TCP: connect to [AF_INET]<ip>:443 failed: Connection refused"
    assert agenting.evidence(["Initialization"], "AUTH_FAILED") == ""
    # «No route to host» — ICMP с пути (или охрана: run решает по её счётчику), «Network is
    # unreachable» — нет маршрута у себя (дефект шлюза). Отчёт М2а: оба были одним кодом.
    assert agenting.classify(["TCP: connect to [AF_INET]1.0.0.1:1535 failed: No route to "
                              "host"]) == "HOST_UNREACHABLE"
    assert agenting.classify(["connect to [AF_INET]1.0.0.1:443 failed: Network is "
                              "unreachable"]) == "NETWORK_UNREACHABLE"
    # UNKNOWN — последняя строка с пометкой ошибки, без адресов и имён хостов.
    assert agenting.evidence([
        "OpenVPN 2.6.19 x86_64-pc-linux-gnu", "VERIFY OK: depth=0, CN=vpn12.opengw.net",
        ">FATAL:Error: unexpected reply from 1.0.0.1, read /tmp/xgw-ovpn/client.conf",
    ], "UNKNOWN") == ">FATAL:Error: unexpected reply from <ip>, read /tmp/xgw-ovpn/client.conf"
    assert agenting.masked("VERIFY OK: depth=0, CN=vpn12.opengw.net") \
        == "VERIFY OK: depth=0, CN=<host>"


def test_inner_check_and_tunnel_counters_are_told_without_addresses():
    """Проверка изнутри: вывод дочернего процесса → итоги по меткам (адреса DNS в журнал не
    идут); DNS работника — ответившие первыми; счётчики fpt0 из `ip -s link`."""
    servers = agenting.inner_servers(["10.8.0.1"])
    assert servers == [("сервера", "10.8.0.1"), ("Cloudflare", "1.1.1.1")]
    inner = agenting.parse_inner("tcp OPEN 120\ndns 10.8.0.1 TIMEOUT\ndns 1.1.1.1 OK 35\n",
                                 servers)
    assert inner == {"tcp": "OPEN 120", "dns": [["сервера", "TIMEOUT"], ["Cloudflare", "OK 35"]]}
    assert agenting.inner_text(inner) == ("TCP Cloudflare:443 — OPEN (120 мс); DNS сервера — "
                                          "TIMEOUT; DNS Cloudflare — OK (35 мс)")
    assert agenting.worker_dns(servers, inner) == ["1.1.1.1", "10.8.0.1", "8.8.8.8"]
    assert agenting.parse_inner("garbage", servers)["tcp"] == "—"
    assert agenting.inner_servers(["1.1.1.1"]) == [("сервера", "1.1.1.1")]
    text = ("5: fpt0: <POINTOPOINT,UP> mtu 1500 qdisc fq_codel state UNKNOWN\n"
            "    link/none \n"
            "    RX:  bytes packets errors dropped  missed   mcast\n"
            "          2048       3      0       0       0       0\n"
            "    TX:  bytes packets errors dropped carrier collsns\n"
            "         10240      12      0       0       0       0\n")
    stats = agenting.parse_link_stats(text)
    assert stats == {"rx_bytes": 2048, "rx_packets": 3, "tx_bytes": 10240, "tx_packets": 12}
    assert agenting.tunnel_text(stats) == ("в туннель 12 пакетов (10 КБ), из туннеля 3 пакетов "
                                           "(2 КБ)")
    assert agenting.parse_link_stats("5: fpt0: <UP>\n") is None


# --- агент поколения: ход с подставными работниками -------------------------------------------


class _Runner:
    """Подставные ip и nft внутри пространства имён агента."""

    def __init__(self, *, grow: bool = False) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.refused = 0
        self.grow = grow

    def __call__(self, argv, *, input=None, timeout=15.0, check=True) -> str:
        self.calls.append(tuple(argv))
        if argv[:3] == ["ip", "-o", "link"]:
            return "7: fpi3@if8: <BROADCAST,MULTICAST> mtu 1500\n"
        if argv[:3] == ["ip", "-s", "link"]:
            return ("5: fpt0: <POINTOPOINT,UP> mtu 1500\n    link/none\n"
                    "    RX:  bytes packets errors dropped  missed   mcast\n"
                    "             0       0      0       0       0       0\n"
                    "    TX:  bytes packets errors dropped carrier collsns\n"
                    "          4096       9      0       0       0       0\n")
        if argv[:3] == ["nft", "list", "counter"]:
            if self.grow:
                self.refused += 1
            return (f"table inet xgwfp {{ counter refused_out {{ packets {self.refused} "
                    "bytes 0 } }")
        return ""


class _Proc:
    """Подставной процесс: работник (жив до terminate) или проба самопроверки (ответ)."""

    def __init__(self, lines=(), out: str = "") -> None:
        self.stdout = iter(lines)
        self.out = out
        self.returncode = None

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
    def __init__(self, probe: str = "ENETUNREACH", openvpn_lines=(),
                 inner: str = "tcp TIMEOUT\ndns 1.1.1.1 TIMEOUT\n") -> None:
        self.probe, self.openvpn_lines, self.inner = probe, openvpn_lines, inner
        self.workers: list[tuple[str, int, int]] = []
        self.inner_args: list[tuple] = []

    def __call__(self, argv, **kwargs):
        if argv[1] == "-I" and "recvfrom" in argv[3]:  # проверка изнутри
            self.inner_args.append((tuple(argv[4:]), kwargs["user"]))
            return _Proc(out=self.inner)
        if argv[1] == "-I":  # самопроверка охраны
            return _Proc(out=self.probe + "\n")
        self.workers.append((argv[0], kwargs["user"], kwargs["group"]))
        return _Proc(lines=self.openvpn_lines if argv[0].endswith("openvpn") else ())


class _Ready:
    """Порт SOCKS-работника открыт (подключение агента для проверки готовности)."""

    def close(self) -> None:
        pass


def _agent(tmp_path, monkeypatch, *, runner=None, spawn=None):
    paths = Paths(root=tmp_path / "root")
    paths.ensure()
    path = agenting.manifest_path(paths, GEN)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(_data(openvpn_conf="client\nremote 1.0.0.1 1194\n")),
                    encoding="utf-8")
    chowned: list[tuple[str, int, int]] = []
    monkeypatch.setattr(agenting.os, "chown",
                        lambda target, uid, gid: chowned.append((Path(target).name, uid, gid)))
    ours, theirs = socket.socketpair()
    ours.settimeout(5.0)
    agent = agenting.Agent(
        paths, GEN, runner=runner or _Runner(), spawn=spawn or _Spawn(),
        connect=lambda address, timeout: theirs if address[1] == agenting.MGMT_PORT
        else _Ready(),
        users=USERS.__getitem__,
        tmp=tmp_path / "tmp", out=io.StringIO(),
    )
    (tmp_path / "tmp").mkdir()
    return agent, ours, chowned


def _start(agent) -> list[int]:
    result: list[int] = []
    thread = threading.Thread(target=lambda: result.append(agent.run()), daemon=True)
    thread.start()
    agent.thread = thread
    return result


def test_agent_guards_first_and_routes_only_while_the_tunnel_is_up(tmp_path, monkeypatch):
    """Порядок: охрана → TUN с владельцем → «guarded» → veth → самопроверка → файлы OpenVPN →
    OpenVPN от своего пользователя → при CONNECTED маршрут по умолчанию, проверка изнутри (от
    пользователя SOCKS) и только затем SOCKS-работник с DNS сервера; обрыв — маршрут убран;
    остановка — фаза stopped и итог туннеля в журнале."""
    runner = _Runner()
    spawn = _Spawn(openvpn_lines=["PUSH: Received control message: 'PUSH_REPLY,dhcp-option "
                                  "DNS 10.8.0.1,ifconfig 10.8.0.6 10.8.0.5'"],
                   inner="tcp OPEN 90\ndns 10.8.0.1 OK 20\ndns 1.1.1.1 TIMEOUT\n")
    agent, ours, chowned = _agent(tmp_path, monkeypatch, runner=runner, spawn=spawn)
    result = _start(agent)
    _wait(lambda: agent.state.get("phase") == "connecting")
    assert ours.recv(64).startswith(b"state on\n")
    calls = runner.calls
    assert calls[:2] == [("ip", "link", "set", "lo", "up"), ("nft", "-f", "-")]
    assert calls[2] == ("ip", "tuntap", "add", "dev", "fpt0", "mode", "tun", "user", "990",
                        "group", "990")
    assert ("ip", "route", "add", f"{PEER}/32", "via", "10.250.3.1", "dev", "fpi3") in calls
    assert not any(call[:3] == ("ip", "route", "replace") for call in calls)
    assert spawn.workers == [("/usr/sbin/openvpn", 990, 990)]  # SOCKS — только с туннелем
    assert agent.state["selftest"]["ok"] is True
    conf = tmp_path / "tmp" / "xgw-ovpn" / "client.conf"
    assert conf.read_text(encoding="utf-8").startswith("client\n")
    assert oct(conf.stat().st_mode & 0o777) == "0o640"
    assert (tmp_path / "tmp" / "xgw-ovpn" / "auth").read_text(encoding="utf-8") \
        == "fpuser\nFakePass77\n"
    assert ("auth", 0, 990) in chowned and not (tmp_path / "tmp" / "xgw-socks").exists()

    ours.sendall(f">STATE:1730000000,CONNECTED,SUCCESS,10.8.0.6,{PEER},1194,,\n".encode())
    _wait(lambda: agent.state.get("phase") == "up")
    assert ("ip", "addr", "add", "10.8.0.6/32", "dev", "fpt0") in runner.calls
    assert ("ip", "route", "replace", "default", "dev", "fpt0") in runner.calls
    assert spawn.inner_args == [(("10.8.0.1", "1.1.1.1"), 991)]
    assert agent.state["inner"]["tcp"] == "OPEN 90"
    assert spawn.workers == [("/usr/sbin/openvpn", 990, 990), ("/opt/xgw/xray/xray", 991, 991)]
    socks = json.loads((tmp_path / "tmp" / "xgw-socks" / "socks.json").read_text(
        encoding="utf-8"))
    assert socks["dns"]["servers"] == ["10.8.0.1", "1.1.1.1", "8.8.8.8"]
    assert ("socks.json", 0, 991) in chowned
    journal = agent.out.getvalue()
    assert "через туннель: TCP Cloudflare:443 — OPEN (90 мс); DNS сервера — OK (20 мс)" \
        in journal and "10.8.0.1" not in journal
    ours.sendall(b">STATE:1730000001,RECONNECTING,ping-restart,,,,,\n")
    _wait(lambda: agent.state.get("phase") == "reconnecting")
    assert ("ip", "route", "del", "default", "dev", "fpt0") in runner.calls
    agent.stop.set()
    agent.thread.join(5)
    assert result == [0] and agent.state["phase"] == "stopped"
    saved = json.loads(agenting.state_path(agent.paths, GEN).read_text(encoding="utf-8"))
    assert saved["phase"] == "stopped" and "FakePass77" not in json.dumps(saved)
    assert saved["tun"]["tx_packets"] == 9 and saved["refused_after_up"] == 0
    assert ("итог туннеля: в туннель 9 пакетов (4 КБ), из туннеля 0 пакетов (0 КБ); ошибок "
            "канала данных 0; охрана отбила после подъёма 0") in agent.out.getvalue()


def test_guard_refusal_before_the_tunnel_is_a_gateway_defect(tmp_path, monkeypatch):
    """«No route to host» при подключении: счётчик охраны вырос — GUARD_BLOCKED (дефект шлюза);
    не вырос — HOST_UNREACHABLE (ICMP с пути к серверу, не дефект)."""
    lines = ["TCP: connect to [AF_INET]1.0.0.1:1535 failed: No route to host"]
    for grow, code in ((True, "GUARD_BLOCKED"), (False, "HOST_UNREACHABLE")):
        (tmp_path / code).mkdir()
        runner = _Runner(grow=grow)
        agent, ours, _chowned = _agent(tmp_path / code, monkeypatch, runner=runner,
                                       spawn=_Spawn(openvpn_lines=lines))
        if grow:  # самопроверка с растущим счётчиком: отказы — «охраной»
            agent._selftest = lambda manifest, ids: {}
        result = _start(agent)
        _wait(lambda agent=agent: agent.state.get("phase") == "connecting" and agent.log)
        assert ours.recv(64).startswith(b"state on\n")  # непрочитанное — RST вместо закрытия
        ours.close()  # OpenVPN закрыл управление
        agent.thread.join(5)
        assert result == [3] and agent.state["reason"] == code
        journal = agent.out.getvalue()
        assert "OpenVPN: TCP: connect to [AF_INET]<ip>:1535 failed: No route to host" in journal
        assert ("охрана отбила за подключение" in journal) is grow


def test_tunnel_address_is_taken_from_push_reply_when_state_has_none(tmp_path, monkeypatch):
    spawn = _Spawn(openvpn_lines=["PUSH: Received control message: 'PUSH_REPLY,ifconfig "
                                  "10.8.0.10 10.8.0.9,tun-mtu 1400'"])
    agent, ours, _chowned = _agent(tmp_path, monkeypatch, spawn=spawn)
    result = _start(agent)
    _wait(lambda: agent.state.get("phase") == "connecting")
    ours.sendall(b">STATE:1730000000,CONNECTED,SUCCESS,,,,,\n")
    _wait(lambda: agent.state.get("phase") == "up")
    assert (agent.state["tunnel"], agent.state["mtu"]) == ("10.8.0.10", 1400)
    agent.stop.set()
    agent.thread.join(5)
    assert result == [0]


def test_wrong_credentials_end_the_generation(tmp_path, monkeypatch):
    agent, ours, _chowned = _agent(tmp_path, monkeypatch)
    result = _start(agent)
    _wait(lambda: agent.state.get("phase") == "connecting")
    ours.sendall(b">PASSWORD:Verification Failed: 'Auth'\n")
    agent.thread.join(5)
    assert result == [3]
    assert (agent.state["phase"], agent.state["reason"]) == ("failed", "AUTH_FAILED")
    journal = agent.out.getvalue()
    assert "охрана проверена: socks_to_peer ENETUNREACH" in journal and PEER not in journal


def test_open_guard_stops_before_any_worker(tmp_path, monkeypatch):
    """Самопроверка нашла выход мимо туннеля — GUARD_FAILED, работники не запускаются."""
    spawn = _Spawn(probe="OPEN")
    agent, _ours, _chowned = _agent(tmp_path, monkeypatch, spawn=spawn)
    assert agent.run() == 3
    assert (agent.state["phase"], agent.state["reason"]) == ("failed", "GUARD_FAILED")
    assert spawn.workers == [] and not (tmp_path / "tmp" / "xgw-ovpn").exists()


def test_refusal_counts_as_closed_only_with_the_guard_counter(tmp_path, monkeypatch):
    """ECONNREFUSED и прочие отказы — «закрыто охраной», только если вырос счётчик
    refused_out; иначе пакет мог уйти, и это провал самопроверки."""
    agent, _ours, _chowned = _agent(tmp_path, monkeypatch, runner=_Runner(grow=True),
                                    spawn=_Spawn(probe="ECONNREFUSED"))
    manifest = _manifest(tmp_path)
    ids = {"ovpn": USERS[agenting.OVPN_USER], "socks": USERS[agenting.SOCKS_USER]}
    results = agent._selftest(manifest, ids)
    assert all(value == "ECONNREFUSED (охрана)" for value in results.values())
    agent.runner = _Runner(grow=False)
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
    return backend.prepare(peer=PEER, proto="udp", port=1194, openvpn_conf="client\n",
                           auth="vpn\nvpn\n", lan=("192.168.50.0/24",),
                           xray_bin=Path("/opt/xgw/xray/xray"))


def test_generation_is_prepared_in_order_and_removed_without_traces(tmp_path):
    """Адрес — в peers.json и fp_peers раньше veth; veth внутрь — только после фазы guarded;
    задание агент принимает как есть; остановка убирает службу, veth, адрес и каталог."""
    backend, host, paths = _backend(tmp_path)
    lease = _prepare(backend)
    element = f"{PEER} . udp . 1194"
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
    atomic_write_json(state, {"phase": "up", "tunnel": "10.8.0.6"}, mode=0o600)
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
    lease = backending.Lease(gen=GEN, index=5, peer=PEER, proto="tcp", port=443)
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
    """Без OpenVPN, пользователей, службы, пересылки IPv4 или набора fp_peers — проверки
    туннелем нет, и причина видна в сводке и в xgw diag."""
    paths = Paths(root=tmp_path / "root")
    paths.ensure()
    openvpn = tmp_path / "openvpn"
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
        return backending.unavailable(paths, runner, openvpn=openvpn, users=users,
                                      proc_sys=proc_sys)

    assert "нет OpenVPN" in check()
    openvpn.write_text("", encoding="utf-8")
    assert "нет пользователя xgw-ovpn" in check()
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
    element = f"{PEER} . udp . 1194"
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
        return backending.Lease(gen=GEN, index=1, peer=kwargs["peer"], proto=kwargs["proto"],
                                port=kwargs["port"], socks_pass="p" * 24)

    def wait(self, lease, *, cancel=None) -> dict:
        return {"phase": "up", "tunnel": "10.8.0.6"}

    def counters(self, lease) -> int:
        return 700_000

    def state(self, lease) -> dict:  # что агент записал к концу пробы
        return {"phase": "up", "inner": {"tcp": "TIMEOUT", "dns": [["Cloudflare", "TIMEOUT"]]},
                "tun": {"tx_packets": 30, "tx_bytes": 2048, "rx_packets": 0, "rx_bytes": 0}}

    def stop(self, lease) -> None:
        self.stopped.append(lease.gen)


def test_openvpn_server_is_checked_through_its_tunnel(tmp_path, monkeypatch):
    """Бэкенд годится — сервер OpenVPN проверяется настоящим туннелем: временный Xray идёт
    через SOCKS-работника поколения; трафик — больший из счётчиков; поколение убирается;
    подключений — не больше одного за шаг и не больше предела в час (R26, R29)."""
    from xgw.freepool import pool as pool_module
    from xgw.freepool import probe as probe_module
    from xgw.freepool import providers
    from xgw.freepool.models import Backend, ProviderResult, Status
    from xgw.freepool.pool import FreePool
    from xgw.freepool.probe import Outcome

    paths = Paths(root=tmp_path / "root")
    paths.ensure()
    cfg = Config()
    cfg.free_pool.mode = "observe"
    cfg.free_pool.providers = ["vpngate"]
    cfg.free_pool.handshakes_per_hour = 1
    catalog = providers.parse_vpngate((FIXTURES / "vpngate.csv").read_text(encoding="utf-8"),
                                      now=1_800_000_000.0)
    variants = [replace(variant, address=PEER, country_hint="DE")
                for variant in catalog.variants if variant.backend == Backend.OPENVPN][:2]
    assert len(variants) == 2
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
    assert runtime.prepared[0]["peer"] == PEER and "remote 1.0.0.1" in \
        runtime.prepared[0]["openvpn_conf"]
    assert seen == [{"tag": "pool", "protocol": "socks", "settings": {"servers": [{
        "address": "10.250.1.2", "port": 1080, "users": [{"user": "xgw", "pass": "p" * 24}],
    }]}}]
    summary = pool.summary()
    assert (summary["tunnels_up"], summary["handshakes_hour"], summary["ready"]) == (1, 1, 1)
    assert summary["openvpn_backend"] == "" and summary["by_region"] == {"EU": 1}
    assert pool.spent_today() == 700_000
    # Что агент видел изнутри — в записи кандидата и журнале демона, без адресов.
    [record] = [value for key, value in pool.store.candidates().items()
                if not key.startswith("_")]
    assert record["diagnosis"] == ("TCP Cloudflare:443 — TIMEOUT; DNS Cloudflare — TIMEOUT; "
                                   "в туннель 30 пакетов (2 КБ), из туннеля 0 пакетов (0 КБ)")
    # Предел подключений в час (1) исчерпан — второй сервер ждёт, а не подключается.
    assert pool.check_some(mark=2, xray_bin=Path("/opt/xgw/xray/xray")) == 0
    assert len(runtime.prepared) == 1


def test_without_backend_openvpn_falls_back_to_the_address_check(tmp_path, monkeypatch):
    from xgw.freepool import pool as pool_module

    paths = Paths(root=tmp_path / "root")
    paths.ensure()
    cfg = Config()
    cfg.free_pool.mode = "observe"
    pool = pool_module.FreePool(cfg, paths, runtime=_Runtime(), sleep=lambda seconds: None)
    monkeypatch.setattr(pool_module.backending, "unavailable",
                        lambda *args, **kwargs: "нет OpenVPN (пакет openvpn — ставит xgw install)")
    assert pool.refresh_backend().startswith("нет OpenVPN")
    assert "проверка туннелем недоступна: нет OpenVPN" in pool_module.render(pool.summary(), 0)


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


def _gate_variants(count: int, **changes):
    from xgw.freepool import providers
    from xgw.freepool.models import Backend

    catalog = providers.parse_vpngate((FIXTURES / "vpngate.csv").read_text(encoding="utf-8"),
                                      now=1_800_000_000.0)
    [first] = [variant for variant in catalog.variants if variant.backend == Backend.OPENVPN][:1]
    return [replace(first, host=f"vpn{index}.example", address=PEER, country_hint="DE",
                    **changes) for index in range(count)]


def test_exhausted_source_does_not_block_the_other(tmp_path, monkeypatch):
    """У VPN Gate предел подключений в час исчерпан — следующим шагом подключается сервер
    VPNBook, даже если перед ним в очереди много серверов VPN Gate."""
    gate = _gate_variants(9)
    book = [replace(_gate_variants(1)[0], provider="vpnbook", host="book.example",
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


def test_address_only_result_does_not_delay_the_tunnel(tmp_path, monkeypatch):
    """Сервер, у которого без бэкенда проверили только адрес (REACHABLE), туннелем проверяется
    сразу; закрытый адрес (CLOSED) — нет: туннель к нему не дойдёт."""
    reachable, closed = _gate_variants(2)
    pool, _runtime, clock = _tunnel_pool(tmp_path, monkeypatch, {"vpngate": [reachable, closed]})
    state = pool.store.candidates()
    for variant, verdict in ((reachable, "REACHABLE"), (closed, "CLOSED")):
        state[variant.variant_id] = {"checked_at": clock[0] - 60, "verdict": verdict,
                                     "backend": "openvpn", "provider": "vpngate"}
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
