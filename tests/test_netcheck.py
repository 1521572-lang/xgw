"""Проверка сети (Ф3 `VPN_IMPROVEMENT_PLAN.md`, ASSUMPTIONS п. 242): вердикты каждой проверки на
подменённой сети; STUN, SOCKS5 UDP и DNS — на настоящих сокетах loopback; кнопка панели и
`xgw diag --netcheck`. Наружу тесты не ходят — настоящую сеть проверяет ТЗ на машине."""

import json
import socket
import struct
import threading
import time

import pytest
from test_ops import root  # noqa: F401  (фикстура)
from test_panel import Rig

from xgw import cli, netcheck
from xgw.config import Config
from xgw.diag import FAIL, OK, WARN, Check
from xgw.paths import Paths
from xgw.store import Store


class FakeNet:
    """Сеть проверок по сценарию: что ответит каждый вызов."""

    def __init__(self, **answers) -> None:
        self.mark = answers.pop("mark", 2)
        self.pings: dict = answers.pop("pings", {})  # размер (None — обычный) → ответ
        self.answers = answers
        self.asked: list = []

    def resolve(self, host):
        return self.answers.get("resolve", {}).get(host, host)

    def ping(self, address, size=None):
        self.asked.append(("ping", size))
        return self.pings.get(size, False)

    def stun(self, host, port):
        self.asked.append(("stun", host))
        return host in self.answers.get("stun", ())

    def stun_via_xray(self, host, port):
        self.asked.append(("xray", host))
        return host in self.answers.get("xray_stun", ())

    def xray_up(self):
        return self.answers.get("xray", True)

    def dns_answered(self, *, mark=None):
        if mark is not None:
            return self.answers.get("dns_bypass", False)  # провайдер, подменяющий DNS
        return self.answers.get("dns", True)

    def v6_connect(self):
        return self.answers.get("v6", "unreachable")


class FakeCapture:
    def __init__(self, **info) -> None:
        self.info = {"mode": "on", "local": True, "inbound_missing": "", **info}

    def describe(self, *, check=True):
        return self.info


def _paths(tmp_path, *, main="proxy-de-aaaa") -> Paths:
    paths = Paths(root=tmp_path / "root")
    paths.ensure()
    store = Store(paths.db_file)
    store.replace_nodes([
        {"fingerprint": "aaaa", "tag": "proxy-de-aaaa", "role": "proxy", "name": "Германия 1",
         "source": "main", "address": "de.example.net", "port": 443, "updated": 1},
        {"fingerprint": "bbbb", "tag": "proxy-nl-bbbb", "role": "proxy", "name": "Нидерланды",
         "source": "main", "address": "198.51.100.7", "port": 443, "updated": 1},
    ])
    if main:
        store.set_meta("main", json.dumps({"tag": main}))
    store.close()
    return paths


def _check(tmp_path, net, *, cfg=None, capture=None, main="proxy-de-aaaa", **kwargs):
    return netcheck.Netcheck(
        cfg or Config(), _paths(tmp_path, main=main), net=net,
        capture=capture or FakeCapture(), runner=lambda *a, **k: "", **kwargs,
    )


def _one(checks, name) -> Check:
    found = [check for check in checks if check.name == name]
    assert len(found) == 1, checks
    return found[0]


# --- вердикты ---------------------------------------------------------------------------


def test_pmtu_full_path_short_path_and_closed_ping(tmp_path):
    net = FakeNet(pings={None: True, 1472: True}, resolve={"de.example.net": "203.0.113.5"})
    check = _check(tmp_path / "a", net)._pmtu()[0]
    assert check.level == OK and "1500" in check.text and "«Германия 1»" in check.text
    assert "203.0.113.5" not in check.text and "de.example.net" not in check.text
    # PPPoE: проходит 1492 (1464 + 28), а 1500 — нет.
    net = FakeNet(pings={None: True, 1464: True})
    check = _check(tmp_path / "b", net)._pmtu()[0]
    assert check.level == WARN and "1492" in check.text and "PPPoE" in check.text
    assert [size for kind, size in net.asked] == [None, 1472, 1464]
    # Сервер не отвечает на ping — это не ошибка: размер просто не проверен.
    net = FakeNet(pings={})
    check = _check(tmp_path / "c", net)._pmtu()[0]
    assert check.level == OK and "не проверен" in check.text and net.asked == [("ping", None)]
    net = FakeNet(pings={None: True})
    assert _check(tmp_path / "d", net)._pmtu()[0].level == WARN  # даже 1440 не проходит


def test_pmtu_without_ping_main_or_servers(tmp_path):
    net = FakeNet(pings={None: None})
    check = _check(tmp_path / "a", net)._pmtu()[0]
    assert check.level == OK and "iputils-ping" in check.advice
    # Основного нет (sticky выключен) — первый сервер в работе.
    net = FakeNet(pings={None: True, 1472: True})
    assert "«Германия 1»" in _check(tmp_path / "b", net, main="")._pmtu()[0].text
    paths = Paths(root=tmp_path / "c")
    paths.ensure()
    empty = netcheck.Netcheck(Config(), paths, net=net, capture=FakeCapture())
    assert "серверов в работе нет" in empty._pmtu()[0].text


def test_udp_direct_counts_hysteria_and_tuic_when_blocked(tmp_path):
    ok = _check(tmp_path / "a", FakeNet(stun={"stun.cloudflare.com"}))._udp_direct()[0]
    assert ok.level == OK
    check = _check(tmp_path / "b", FakeNet())
    check.paths.singbox_config_file.parent.mkdir(parents=True, exist_ok=True)
    check.paths.singbox_config_file.write_text(json.dumps({"outbounds": [
        {"type": "hysteria2", "tag": "a"}, {"type": "tuic", "tag": "b"},
        {"type": "vless", "tag": "c"}, {"type": "direct", "tag": "direct"},
    ]}), encoding="utf-8")
    blocked = check._udp_direct()[0]
    assert blocked.level == WARN and "у вас их 2" in blocked.advice
    # Без root метки нет — напрямую не проверить (без неё запрос ушёл бы в VPN).
    assert "sudo" in _check(tmp_path / "c", FakeNet(mark=None))._udp_direct()[0].text


def test_udp_through_vpn(tmp_path):
    check = _check(tmp_path / "a", FakeNet(xray_stun={"stun.l.google.com"}))
    check.xray = True
    result = check._udp_vpn()[0]
    assert result.level == OK and "«Германия 1»" in result.text
    check = _check(tmp_path / "b", FakeNet())
    check.xray = True
    assert check._udp_vpn()[0].level == WARN and "другой сервер" in check._udp_vpn()[0].advice
    check.xray = False
    assert "Xray не отвечает" in check._udp_vpn()[0].text


def test_dns_leak(tmp_path):
    check = _check(tmp_path / "a", FakeNet(dns=True))
    check.xray = True
    assert check._dns()[0].level == OK and "мимо VPN — никто" in check._dns()[0].text
    check = _check(tmp_path / "b", FakeNet(dns=False))
    check.xray = True
    assert check._dns()[0].level == FAIL and "xgw net up" in check._dns()[0].advice
    # Провайдер сам отвечает на любой порт 53 (так и WSL): ответ без метки ничего не доказывает.
    check = _check(tmp_path / "h", FakeNet(dns=True, dns_bypass=True))
    check.xray = True
    assert check._dns()[0].level == OK and "не проверена" in check._dns()[0].text
    # Нечего проверять: перехват снят, машина не перехватывается, Xray не готов.
    check = _check(tmp_path / "c", FakeNet(dns=False), capture=FakeCapture(mode="off"))
    check.xray = True
    assert check._dns()[0].level == OK and "перехват снят" in check._dns()[0].text
    check = _check(tmp_path / "d", FakeNet(dns=False), capture=FakeCapture(local=False))
    check.xray = True
    assert "capture.local = false" in check._dns()[0].text
    check = _check(tmp_path / "e", FakeNet(dns=False))
    check.xray = False
    assert check._dns()[0].level == WARN and "не проверен" in check._dns()[0].text


def test_ipv6_leak(tmp_path):
    assert _check(tmp_path / "a", FakeNet(v6="connected"))._ipv6()[0].level == FAIL
    for outcome in ("unreachable", "refused", "timeout"):
        assert _check(tmp_path / outcome, FakeNet(v6=outcome))._ipv6()[0].level == OK
    cfg = Config()
    cfg.network.ipv6 = "proxy"
    assert "proxy" in _check(tmp_path / "p", FakeNet(v6="connected"), cfg=cfg)._ipv6()[0].text


def test_run_keeps_going_when_a_check_breaks(tmp_path, monkeypatch):
    check = _check(tmp_path, FakeNet(stun={"stun.l.google.com"},
                                     xray_stun={"stun.l.google.com"}), firewall=False)
    monkeypatch.setattr(check, "_ipv6", lambda: 1 / 0)
    checks = check.run()
    names = [item.name for item in checks]
    assert names == ["MTU до сервера", "UDP напрямую", "UDP через VPN", "Утечка DNS",
                     "Утечка IPv6"]
    assert _one(checks, "Утечка IPv6").level == WARN
    assert "не выполнена" in _one(checks, "Утечка IPv6").text


def test_summary_and_saved_result():
    checks = [Check("UDP напрямую", WARN, "x"), Check("Утечка DNS", OK, "y")]
    assert netcheck.summary(checks) == "OK — 1, WARN — 1, FAIL — 0: UDP напрямую"
    saved = netcheck.loads(netcheck.dumps(checks, 100.0, 4.26))
    assert saved["at"] == 100.0 and saved["took"] == 4.3 and saved["checks"][0]["level"] == WARN
    assert netcheck.loads("не JSON") == {} and netcheck.loads(None) == {}


# --- настоящие сокеты на loopback ------------------------------------------------------


def _stun_server():
    """STUN-сервер на 127.0.0.1: отвечает Binding Success на любой Binding Request."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(5)

    def serve():
        with sock:
            try:
                data, peer = sock.recvfrom(2048)
            except OSError:
                return
            sock.sendto(b"\x01\x01\x00\x00" + data[4:20], peer)

    threading.Thread(target=serve, daemon=True).start()
    return sock.getsockname()[1]


def test_stun_answer_is_recognised_by_its_transaction():
    request, txid = netcheck.stun_request()
    assert len(request) == 20 and request[:2] == b"\x00\x01"
    assert netcheck.is_stun_reply(b"\x01\x01\x00\x00" + request[4:20], txid)
    assert not netcheck.is_stun_reply(b"\x01\x01\x00\x00" + request[4:8] + bytes(12), txid)
    port = _stun_server()
    assert netcheck.Net(Config(), lambda *a, **k: "", None).stun("127.0.0.1", port)


def test_stun_through_socks5_udp_associate():
    """Поддельный вход socks Xray: UDP ASSOCIATE и датаграммы с заголовком RFC 1928."""
    relay = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    relay.bind(("127.0.0.1", 0))
    relay.settimeout(5)
    control = socket.socket()
    control.bind(("127.0.0.1", 0))
    control.listen(1)
    control.settimeout(5)
    seen: dict = {}

    def serve():
        conn, _ = control.accept()
        with conn:
            assert conn.recv(3) == b"\x05\x01\x00"
            conn.sendall(b"\x05\x00")
            assert conn.recv(10)[:2] == b"\x05\x03"
            conn.sendall(b"\x05\x00\x00\x01" + socket.inet_aton("0.0.0.0")
                         + struct.pack(">H", relay.getsockname()[1]))
            data, peer = relay.recvfrom(2048)
            length = data[4]
            seen["host"] = data[5:5 + length].decode()
            seen["port"] = struct.unpack(">H", data[5 + length:7 + length])[0]
            stun = data[7 + length:]
            header = b"\x00\x00\x00\x01" + socket.inet_aton("203.0.113.9") + b"\x4b\x66"
            relay.sendto(header + b"\x01\x01\x00\x00" + stun[4:20], peer)
            time.sleep(0.2)

    threading.Thread(target=serve, daemon=True).start()
    try:
        assert netcheck.socks_udp_stun(control.getsockname(), "stun.l.google.com", 19302)
    finally:
        control.close()
        relay.close()
    assert seen == {"host": "stun.l.google.com", "port": 19302}


def test_dns_answer_only_from_the_probed_address():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    server.settimeout(5)

    def serve():
        with server:
            data, peer = server.recvfrom(512)
            server.sendto(data[:2] + b"\x81\x80" + data[4:], peer)

    threading.Thread(target=serve, daemon=True).start()
    net = netcheck.Net(Config(), lambda *a, **k: "", None)
    assert net.dns_answered(server.getsockname())


# --- панель и CLI -----------------------------------------------------------------------


@pytest.fixture()
def rig(tmp_path, monkeypatch):
    instance = Rig(tmp_path, monkeypatch)
    yield instance
    instance.panel.stop()


def test_panel_button_runs_the_check_in_the_background(rig, monkeypatch):
    gate = threading.Event()

    def run(self):
        gate.wait(5)
        return [Check("UDP напрямую", WARN, "STUN-серверы не ответили напрямую", "совет"),
                Check("Утечка DNS", OK, "DNS машины идёт через Xray")]

    monkeypatch.setattr(netcheck.Netcheck, "run", run)
    rig.client.login()
    assert rig.client.state()["netcheck"] == {"running": False}
    result = rig.client.act("netcheck", {})
    assert result["ok"] and "до 15 секунд" in result["text"]
    assert rig.client.state()["netcheck"]["running"] is True
    assert "уже идёт" in rig.client.act("netcheck", {})["text"]  # второй раз не запускается
    gate.set()
    rig.panel._netcheck.join(5)
    card = rig.client.state()["netcheck"]
    assert card["running"] is False and card["at"] and len(card["checks"]) == 2
    assert card["checks"][0] == {"name": "UDP напрямую", "level": WARN,
                                 "text": "STUN-серверы не ответили напрямую", "advice": "совет"}
    events = rig.panel._db("SELECT kind, detail FROM events")
    assert any(row["kind"] == "netcheck"
               and row["detail"] == "проверка сети: OK — 1, WARN — 1, FAIL — 0: UDP напрямую"
               for row in events)


def test_diag_netcheck_adds_the_network_group(root, monkeypatch, capsys):  # noqa: F811
    taken: dict = {}

    def run(self):
        taken["firewall"] = self.firewall
        return [Check("Утечка IPv6", FAIL, "IPv6 машины выходит в интернет мимо VPN")]

    monkeypatch.setattr(netcheck.Netcheck, "run", run)
    assert cli.main(["diag", "--no-net", "--json", "--netcheck"]) == 1
    checks = json.loads(capsys.readouterr().out)
    assert checks[-1]["name"] == "Утечка IPv6" and checks[-1]["level"] == FAIL
    assert taken == {"firewall": False}  # чужие правила diag уже показал
