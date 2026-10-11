"""Проверки стенда: IPv6 самой машины через Xray (network.ipv6 = "proxy", этап 5).

Только режим netns, на настоящем ядре и настоящем Xray; нужны Linux, root, nft:

    sudo -E XGW_XRAY_BIN=<путь к xray> pytest tests/stand/test_stand_ipv6.py -q

На стыке шлюза и «интернета» есть IPv6 (2001:db8:5::/64), origin слушает и по IPv6.
Как отличить путь трафика — как в test_stand_lan.py: origin на /trace отдаёт адрес,
с которого пришёл запрос. 2001:db8:5::1 — запрос вышел с VPN-сервера (он живёт в том
же «интернете»), 2001:db8:5::2 — ушёл с WAN шлюза напрямую.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import netns
import pytest
from stand import Stand, wait_for

XRAY_BIN = os.environ.get("XGW_XRAY_BIN", "")
VIA_VPN = netns.INET_IP
VIA_VPN6 = netns.INET_IP6
DIRECT6 = netns.GW_WAN_IP6
NOWHERE6 = "2001:db8:77::8888"  # адреса нет нигде на стенде: ответить может только Xray

pytestmark = [
    pytest.mark.skipif(
        not XRAY_BIN or not Path(XRAY_BIN).exists(), reason="нет XGW_XRAY_BIN — стенд пропущен"
    ),
    pytest.mark.skipif(
        not netns.available() or shutil.which("nft") is None,
        reason="проверки IPv6: нужны Linux, root и nft",
    ),
]


def _stand(tmp_path: Path, **config) -> Stand:
    stand = Stand(tmp_path, Path(XRAY_BIN), mode="netns", ipv6=True)
    stand.start()
    stand.up(capture=True, **config)
    enabled = stand.xgw("enable")
    assert enabled.returncode == 0, enabled.stderr
    return stand


@pytest.fixture()
def gateway(tmp_path):
    """Шлюз с перехватом IPv6 самой машины."""
    stand = None
    try:
        stand = _stand(tmp_path, ipv6="proxy")
        yield stand
    finally:
        if stand is not None:
            stand.stop()


def _capture(stand: Stand) -> dict:
    return stand.xgw_json("status")["capture"]


def _table6(stand: Stand) -> str:
    return stand.gw_run("nft", "list", "table", "ip6", "xgw6", check=False)


def _v6_rules(stand: Stand) -> str:
    return stand.gw_run("ip", "-6", "rule", "show")


def test_gateway_ipv6_goes_through_vpn_and_dns_is_answered_by_xray(gateway):
    # Сначала убеждаемся, что нужный IPv6 вообще работает (иначе тест ничего не докажет).
    assert gateway.exit_ip6("gw", "--mark", "2") == DIRECT6
    assert gateway.exit_ip6("gw") == VIA_VPN6
    assert gateway.exit_ip("gw") == VIA_VPN  # IPv4 по-прежнему через VPN
    assert gateway.exit_ip6("gw", "--mark", "2") == DIRECT6  # метка mark_bypass — мимо перехвата

    # DNS по IPv6: резолвера нет нигде, отвечает только Xray (UDP и TCP). A-запрос
    # получает A-запись, AAAA-запрос — AAAA (queryStrategy = UseIP).
    for transport in ((), ("--tcp",)):
        answer = gateway.client("gw", "dns", NOWHERE6, "example.org", *transport)
        assert answer.get("answers") == [netns.INET_IP], answer
        assert answer["from"] == NOWHERE6  # ответ «от того, кого спросили»
    aaaa = gateway.client("gw", "dns", NOWHERE6, "example.org", "--type", "AAAA")
    assert aaaa.get("answers") == [VIA_VPN6], aaaa

    log = gateway.xray_log(60)
    assert "tproxy-in6 -> proxy-" in log and "tproxy-in6 -> dns-out" in log

    capture = _capture(gateway)
    assert capture["mode"] == "on" and capture["loaded"] is True and capture["ipv6"] is True
    table = _table6(gateway)
    assert "tproxy to [::1]:12345" in table and "chain loopback_guard" in table
    assert "fwmark 0x1 lookup 100" in _v6_rules(gateway)
    assert gateway.gw_run("ip", "-6", "route", "show", "table", "100").startswith("local default")
    # TPROXY-порт IPv6 не виден снаружи: inbound слушает только ::1.
    assert "[::1]:12345" in gateway.gw_run("ss", "-ltnH", "sport = :12345")
    assert gateway.xgw("probe", "--all").returncode == 0  # пробы XGW с перехватом работают


def test_ipv6_is_not_touched_when_it_is_not_proxied(tmp_path):
    """ipv6 = off: правил перехвата IPv6 нет, трафик идёт напрямую — поэтому установка
    и отключает IPv6 в профиле WAN. Тест фиксирует именно это положение дел."""
    stand = _stand(tmp_path)
    try:
        assert stand.exit_ip6("gw") == DIRECT6
        assert stand.exit_ip("gw") == VIA_VPN
        assert _capture(stand)["ipv6"] is False
        table = _table6(stand)
        assert "tproxy" not in table and "reserved6" not in table
        assert "fwmark" not in _v6_rules(stand)
        assert "tproxy-in6" not in stand.xray_log(60)
    finally:
        stand.stop()


def test_ipv6_follows_enable_disable_and_net_down(gateway):
    assert gateway.exit_ip6("gw") == VIA_VPN6
    assert gateway.xgw("disable").returncode == 0
    assert gateway.exit_ip6("gw") == DIRECT6  # перехват снят — всё напрямую, и IPv6 тоже
    assert "tproxy" not in _table6(gateway) and "fwmark" not in _v6_rules(gateway)
    assert _capture(gateway)["loaded"] is True
    assert gateway.xgw("enable").returncode == 0
    assert gateway.exit_ip6("gw") == VIA_VPN6

    for _ in range(2):  # повторные включения не плодят правил
        assert gateway.xgw("net", "up").returncode == 0
    assert _v6_rules(gateway).count("fwmark 0x1") == 1

    assert gateway.xgw("net", "down").returncode == 0
    assert "xgw6" not in gateway.gw_run("nft", "list", "tables")
    assert "fwmark" not in _v6_rules(gateway)
    assert gateway.gw_run("ip", "-6", "route", "show", "table", "100", check=False).strip() == ""
    assert gateway.exit_ip6("gw") == DIRECT6
    assert gateway.xgw("net", "up").returncode == 0
    assert gateway.exit_ip6("gw") == VIA_VPN6

    # Чужой сбой: пропала таблица IPv6 — XGW замечает и возвращает её.
    gateway.gw_run("nft", "delete", "table", "ip6", "xgw6")
    assert _capture(gateway)["loaded"] is False
    assert gateway.xgw("net", "up").returncode == 0
    assert _capture(gateway)["loaded"] is True and gateway.exit_ip6("gw") == VIA_VPN6


def test_ipv6_is_fail_closed(gateway):
    """Xray остановлен: IPv6 машины не уходит мимо VPN, как и IPv4."""
    assert gateway.exit_ip6("gw") == VIA_VPN6
    gateway.xray_service().stop()
    assert gateway.exit_ip6("gw") == ""
    assert gateway.exit_ip("gw") == ""
    assert gateway.exit_ip6("gw", "--mark", "2") == DIRECT6  # запросы самого XGW — напрямую


def test_gateway_ipv6_loopback_is_not_reachable_through_direct(tmp_path):
    """Имя из direct_domains, указывающее на ::1, не приводит Xray к службам шлюза
    (как п. 119 для 127.0.0.1): имя разрешает сам outbound direct, а loopback_guard в
    ip6 xgw6 отвергает пакеты с меткой обхода к ::1. Без цепочки это достижимо."""
    stand = _stand(tmp_path, ipv6="proxy", direct_domains=("domain:direct.stand.test",))
    try:
        stand.serve_in_gw(8080, "GW-LOOPBACK6", host="::1")

        def through_name(name: str) -> dict:
            # Машина идёт на адрес «интернета», а в Host (и в SNI) называет домен;
            # имя разрешает DNS-заглушка: loopback.* → 127.0.0.1 и ::1.
            return stand.client(
                "gw", "get", f"http://{name}.direct.stand.test:8080/trace",
                "--connect", netns.INET_IP6, "--timeout", "6", "--body",
            )

        def reached_gateway() -> bool:
            # direct выбирает между A и AAAA сам: несколько попыток, пока не попадёт на ::1.
            return any("GW-LOOPBACK6" in through_name("loopback").get("body", "")
                       for _ in range(12))

        named = through_name("site").get("body", "")
        assert f"ip={netns.GW_WAN_IP}" in named or f"ip={DIRECT6}" in named, named  # прямо

        assert not reached_gateway()
        guard = stand.gw_run("nft", "list", "chain", "ip6", "xgw6", "loopback_guard")
        assert "packets 0 " not in guard and "reject" in guard, guard  # отказал именно он

        stand.gw_run("nft", "flush", "chain", "ip6", "xgw6", "loopback_guard")
        assert wait_for(reached_gateway, 20, step=0.5), "без цепочки ::1 шлюза должен быть виден"
        assert stand.xgw("net", "up").returncode == 0  # команды XGW возвращают цепочку
        assert not reached_gateway()
    finally:
        stand.stop()


def test_switching_to_proxy_blocks_ipv6_until_xray_listens_and_never_leaks(tmp_path):
    """Правка одного config.toml: правила IPv6 загружаются сразу, а inbound на ::1 Xray
    получает при перезапуске. В промежутке IPv6 машины блокируется (TPROXY без
    слушателя), а не идёт мимо VPN; после `xgw apply --now` — через VPN."""
    stand = _stand(tmp_path)  # ipv6 = off
    try:
        assert stand.exit_ip6("gw") == DIRECT6
        stand.write_config(capture=True, ipv6="proxy")
        assert stand.xgw("net", "up").returncode == 0
        assert "tproxy to [::1]:12345" in _table6(stand)
        assert "tproxy-in6" not in stand.xray_log(60)
        for _ in range(3):
            assert stand.exit_ip6("gw") == ""  # ни через VPN, ни мимо
        assert stand.exit_ip("gw") == VIA_VPN  # IPv4 работает как обычно

        applied = stand.xgw("apply", "--now")
        assert applied.returncode == 0, applied.stderr
        assert wait_for(lambda: stand.exit_ip6("gw") == VIA_VPN6, 30, step=1), stand.xray_log(30)

        # И обратно: правила IPv6 исчезают, IPv6 снова идёт напрямую.
        stand.write_config(capture=True, ipv6="off")
        assert stand.xgw("net", "up").returncode == 0
        assert stand.exit_ip6("gw") == DIRECT6
        assert "fwmark" not in _v6_rules(stand) and "tproxy" not in _table6(stand)
    finally:
        stand.stop()
