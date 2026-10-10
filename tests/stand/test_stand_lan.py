"""Проверки стенда из LAN (раздел 9 ТЗ), этап 3: перехват TPROXY, DNS через Xray,
fail-closed, enable/disable, обход VPN, DHCP.

Только режим netns: шлюз с двумя картами (wan0, lan0), «интернет» и устройство —
отдельные сетевые стеки. Нужны Linux, root, nft и настоящий Xray:

    sudo -E XGW_XRAY_BIN=<путь к xray> pytest tests/stand/test_stand_lan.py -q

Как отличить путь трафика: origin на /trace отдаёт адрес, с которого пришёл запрос.
Адрес «интернета» (5.5.5.1) — запрос вышел с VPN-сервера, то есть прошёл через
Xray; адрес WAN шлюза (5.5.5.2) — ушёл напрямую, с маскарадингом.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import netns
import pytest
from stand import Stand, wait_for

XRAY_BIN = os.environ.get("XGW_XRAY_BIN", "")
VIA_VPN = netns.INET_IP
DIRECT = netns.GW_WAN_IP
SWITCH_LIMIT = 25.0

pytestmark = [
    pytest.mark.skipif(
        not XRAY_BIN or not Path(XRAY_BIN).exists(), reason="нет XGW_XRAY_BIN — стенд пропущен"
    ),
    pytest.mark.skipif(
        not netns.available() or shutil.which("nft") is None,
        reason="проверки из LAN: нужны Linux, root и nft",
    ),
]


@pytest.fixture()
def gateway(tmp_path):
    """Шлюз с включённым перехватом: Xray работает, участники живы."""
    stand = Stand(tmp_path, Path(XRAY_BIN), mode="netns")
    try:
        stand.start()
        stand.up(capture=True)
        enabled = stand.xgw("enable")
        assert enabled.returncode == 0, enabled.stderr
        assert "перехват включён" in enabled.stdout and "внимание" not in enabled.stdout
        yield stand
    finally:
        stand.stop()


def _capture(stand: Stand) -> dict:
    return stand.xgw_json("status")["capture"]


def test_lan_device_goes_through_vpn_and_dns_is_answered_by_xray(gateway):
    """curl из lan проходит и идёт через VPN; dig @8.8.8.8 отвечает Xray."""
    assert gateway.exit_ip("lan") == VIA_VPN
    assert gateway.lan("get", gateway.origin_url("/64k"))["bytes"] == 65536

    # 8.8.8.8 на стенде нет вовсе: ответить может только Xray, перехватив запрос.
    for transport in ((), ("--tcp",)):
        answer = gateway.lan("dns", "8.8.8.8", "example.org", *transport)
        assert answer.get("answers") == [netns.INET_IP], answer
        assert answer["from"] == "8.8.8.8"  # устройство видит ответ «от того, кого спросило»
    # DNS-сервер из DHCP — сам шлюз: на его порту 53 никто не слушает, отвечает тоже Xray.
    assert gateway.lan("dns", netns.GW_LAN_IP, "example.org").get("answers") == [netns.INET_IP]

    # Сайт по имени: имя разрешает Xray, а сниффинг подставляет домен вместо адреса.
    named = gateway.lan("get", "http://site.stand.test:8080/trace", "--dns", netns.GW_LAN_IP)
    assert f"ip={VIA_VPN}" in named.get("body", ""), named
    log = gateway.xray_log(40)
    assert "tproxy-in -> proxy-" in log and "tproxy-in -> dns-out" in log

    # ICMP проксировать нельзя — он форвардится напрямую (forward_icmp).
    if shutil.which("ping"):
        assert gateway.run_in("lan", "ping", "-c", "1", "-W", "2", netns.INET_IP).returncode == 0
    # Сам шлюз из LAN доступен как обычно: порт без слушателя отвечает отказом сразу.
    refused = gateway.lan("get", f"http://{netns.GW_LAN_IP}:22/", "--timeout", "3")
    assert "ConnectionRefused" in refused.get("error", ""), refused
    # TPROXY-порт Xray из LAN не виден: inbound слушает только 127.0.0.1.
    tproxy = gateway.lan("get", f"http://{netns.GW_LAN_IP}:12345/", "--timeout", "3")
    assert "ConnectionRefused" in tproxy.get("error", ""), tproxy


def test_bypass_host_goes_direct(gateway):
    """Устройство из bypass_hosts (MAC → IP через статическую аренду) ходит мимо VPN,
    а DNS-запрос к шлюзу от него уходит на прямой резолвер."""
    assert _capture(gateway)["bypass"] == [netns.LAN_BYPASS_IP]
    assert gateway.exit_ip("lan", "--bind", netns.LAN_BYPASS_IP) == DIRECT
    assert gateway.exit_ip("lan") == VIA_VPN  # остальные устройства — по-прежнему через VPN
    answer = gateway.lan("dns", netns.GW_LAN_IP, "example.org", "--bind", netns.LAN_BYPASS_IP)
    assert answer.get("answers") == [netns.INET_IP], answer
    named = gateway.lan(
        "get", "http://site.stand.test:8080/trace",
        "--dns", netns.GW_LAN_IP, "--bind", netns.LAN_BYPASS_IP,
    )
    assert f"ip={DIRECT}" in named.get("body", ""), named


def test_gateway_own_traffic_is_captured(gateway):
    """Трафик самой машины идёт через Xray; сокеты с меткой mark_bypass — напрямую.
    Повторное включение не плодит правил, `xgw net down` убирает всё."""
    assert gateway.exit_ip("gw") == VIA_VPN
    assert gateway.exit_ip("gw", "--mark", "2") == DIRECT
    assert gateway.client("gw", "dns", "8.8.8.8", "example.org").get("answers") == [netns.INET_IP]
    # Команды XGW с перехватом работают: пробы идут через probe-inbounds на 127.0.0.1.
    assert gateway.xgw("probe", "--all").returncode == 0
    assert gateway.xgw("apply").returncode == 0

    capture = _capture(gateway)
    assert capture["mode"] == "on" and capture["loaded"] is True
    assert capture["lan"] and capture["local"] and capture["lan_if"] == "lan0"
    assert "Перехват: включён — сеть lan0 и эта машина" in gateway.xgw("status").stdout

    def marked_rules() -> list[dict]:
        rules = json.loads(gateway.gw_run("ip", "-j", "rule", "show"))
        return [rule for rule in rules if rule.get("fwmark") == "0x1"]

    for _ in range(2):  # повторное применение не создаёт дубликатов
        assert gateway.xgw("enable").returncode == 0
        assert gateway.xgw("net", "up").returncode == 0
    assert len(marked_rules()) == 1
    assert gateway.exit_ip("lan") == VIA_VPN

    down = gateway.xgw("net", "down")
    assert down.returncode == 0, down.stderr
    assert "xgw" not in gateway.gw_run("nft", "list", "tables")
    assert marked_rules() == []
    assert gateway.gw_run("ip", "route", "show", "table", "100", check=False).strip() == ""
    assert gateway.gw_run("sysctl", "-n", "net.ipv4.ip_forward").strip() == "0"  # как было


def test_fail_closed_then_disable_gives_direct_internet(gateway):
    """Остановленный Xray → из lan не проходит (fail-closed); после `xgw disable`
    проходит напрямую не дольше чем за 5 с; `xgw enable` возвращает перехват."""
    gateway.xray_service().stop()
    assert gateway.exit_ip("lan") == ""  # никуда: ни через VPN, ни мимо
    assert gateway.exit_ip("gw") == ""  # сама машина — тоже
    assert "error" in gateway.lan("dns", "8.8.8.8", "example.org", "--timeout", "3")
    # Кроме устройств в обход VPN и запросов самого XGW (метка mark_bypass).
    assert gateway.exit_ip("lan", "--bind", netns.LAN_BYPASS_IP) == DIRECT
    assert gateway.exit_ip("gw", "--mark", "2") == DIRECT

    started = time.monotonic()
    disabled = gateway.xgw("disable")
    assert disabled.returncode == 0, disabled.stderr
    assert gateway.exit_ip("lan") == DIRECT
    assert time.monotonic() - started <= 5.0
    assert gateway.exit_ip("gw") == DIRECT
    # DNS после снятия перехвата: запрос к шлюзу уходит на прямой резолвер.
    named = gateway.lan("get", "http://site.stand.test:8080/trace", "--dns", netns.GW_LAN_IP)
    assert f"ip={DIRECT}" in named.get("body", ""), named
    capture = _capture(gateway)
    assert capture["mode"] == "off" and capture["loaded"] is True
    assert "СНЯТ" in gateway.xgw("status").stdout
    table = gateway.gw_run("nft", "list", "table", "ip", "xgw")
    assert "tproxy" not in table and "chain output" not in table
    assert json.loads(gateway.gw_run("ip", "-j", "rule", "show"))[1]["table"] == "main"

    # Обратно: без Xray — снова закрыто, с Xray — через VPN.
    enabled = gateway.xgw("enable")
    assert enabled.returncode == 0 and "внимание: Xray не отвечает" in enabled.stdout
    assert gateway.exit_ip("lan") == ""
    config = gateway.root / "etc/xgw/xray/config.json"
    gateway.gw_popen("xray-again", [str(gateway.xray_bin), "run", "-c", str(config)])
    assert wait_for(lambda: gateway.exit_ip("lan") == VIA_VPN, 20)


def test_frozen_node_new_connections_use_another_server(gateway):
    """Цель из раздела 2: при «заморозке» текущего сервера новые соединения
    устройств идут через рабочий сервер — без действий пользователя."""
    members = list(gateway.members())
    victim, other = members[0], members[1]
    gateway.make_fastest(victim)
    assert gateway.lan("get", gateway.origin_url("/64k"))["bytes"] == 65536

    gateway.server_of(victim).set_mode("freeze_after=16384")
    started = time.monotonic()
    assert wait_for(lambda: gateway.selecting() == (other,), SWITCH_LIMIT + 5)
    assert time.monotonic() - started <= SWITCH_LIMIT
    for _ in range(3):  # все новые соединения — через живой узел
        assert gateway.lan("get", gateway.origin_url("/64k")).get("bytes") == 65536
    assert f"tproxy-in -> {other}" in gateway.xray_log(10)


def test_daemon_restores_rules_and_dhcp_serves_leases(gateway):
    """Демон следит за правилами: пропавшую таблицу возвращает сам. Заодно DHCP:
    устройство получает адрес, шлюз и DNS-сервер — адрес шлюза."""
    gateway.start_daemon()
    assert wait_for(
        lambda: (s := gateway.xgw_json("status"))["daemon"] and s["state"] == "HEALTHY", 60, step=2
    ), gateway.tail("daemon", 30)

    gateway.gw_run("nft", "delete", "table", "ip", "xgw")  # «чужой» сбой правил
    assert wait_for(lambda: gateway.exit_ip("lan") == VIA_VPN, 30, step=1), gateway.tail("daemon")
    events = [event["detail"] for event in gateway.xgw_json("status")["events"]]
    assert any("загружены заново" in detail for detail in events), events
    assert gateway.exit_ip("lan", "--bind", netns.LAN_BYPASS_IP) == DIRECT

    if shutil.which("dnsmasq") is None:
        pytest.skip("dnsmasq не установлен — выдача адресов не проверена")
    gateway.start_dnsmasq()
    lease = gateway.lan("dhcp", "eth0", "--mac", "02:00:00:00:00:77")
    assert "error" not in lease, f"{lease}\n{gateway.tail('dnsmasq')}"
    network, _, last = lease["ip"].rpartition(".")
    assert network == "192.168.50" and 110 <= int(last) <= 150  # из dhcp_range стенда
    assert lease["router"] == lease["dns"] == netns.GW_LAN_IP
    assert lease["mask"] == "255.255.255.0" and lease["lease"] == 3600
    static = gateway.lan("dhcp", "eth0", "--mac", netns.LAN_BYPASS_MAC)
    assert static.get("ip") == netns.LAN_BYPASS_IP, static  # статическая аренда по MAC


def test_fail_open_removes_capture_until_xray_returns(tmp_path):
    """fail_mode = "open": Xray недоступен дольше минуты — демон снимает перехват,
    сеть работает напрямую; Xray вернулся — перехват возвращается сам."""
    switch = tmp_path / "xray-off"
    wrapper = tmp_path / "xray-wrapper.sh"  # Xray, который можно «сломать»: не запускается
    wrapper.write_text(
        "#!/bin/sh\n"
        f'if [ -e "{switch}" ] && [ "$1" = run ]; then\n'
        '    echo "xray отключён тестом" >&2\n'
        "    exit 1\n"
        "fi\n"
        f'exec "{XRAY_BIN}" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    stand = Stand(tmp_path / "stand", wrapper, mode="netns")
    try:
        stand.start()
        stand.up(capture=True, fail_mode="open")
        assert stand.xgw("enable").returncode == 0
        stand.start_daemon()
        assert wait_for(
            lambda: (s := stand.xgw_json("status"))["daemon"] and s["state"] == "HEALTHY",
            60, step=2,
        ), stand.tail("daemon", 30)

        switch.touch()
        stand.xray_service().stop()
        started = time.monotonic()
        assert stand.exit_ip("lan") == ""  # первую минуту — закрыто, как при fail-closed
        assert wait_for(lambda: stand.exit_ip("lan") == DIRECT, 100, step=3), stand.tail("daemon")
        assert time.monotonic() - started >= 55  # не раньше чем через минуту без Xray
        assert _capture(stand)["mode"] == "open"
        assert "ВРЕМЕННО СНЯТ" in stand.xgw("status").stdout

        switch.unlink()  # Xray снова запускается — демон поднимает его и возвращает перехват
        assert wait_for(lambda: stand.exit_ip("lan") == VIA_VPN, 60, step=2), stand.tail("daemon")
        assert _capture(stand)["mode"] == "on"
        details = [event["detail"] for event in stand.xgw_json("status")["events"]]
        assert any("временно снят" in detail for detail in details)
        assert any("перехват возвращён" in detail for detail in details)
    finally:
        stand.stop()
