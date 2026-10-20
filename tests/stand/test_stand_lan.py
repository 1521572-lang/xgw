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
import subprocess
import sys
import time
from pathlib import Path

import netns
import pytest
from stand import Stand, wait_for

XRAY_BIN = os.environ.get("XGW_XRAY_BIN", "")
HERE = Path(__file__).resolve().parent
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


def test_lan_device_cannot_reach_gateway_loopback_through_direct(tmp_path):
    """Имя из direct_domains, указывающее на 127.0.0.1, не приводит Xray к службам
    самого шлюза (ASSUMPTIONS, п. 119): сниффинг подставляет имя, outbound direct
    разрешает его сам, а цепочка loopback_guard отвергает пакеты с меткой обхода
    к 127.0.0.0/8. Без цепочки это достижимо — тест доказывает и то, и другое."""
    stand = Stand(tmp_path, Path(XRAY_BIN), mode="netns")
    try:
        stand.start()
        stand.up(capture=True, direct_domains=("domain:direct.stand.test",))
        assert stand.xgw("enable").returncode == 0
        stand.serve_in_gw(8080, "GW-LOOPBACK")
        metrics = stand.ports["metrics"]

        def through_name(name: str, port: int, path: str) -> dict:
            # Устройство идёт на адрес «интернета», а в Host (и в SNI) называет домен;
            # имя разрешает DNS-заглушка стенда: loopback.* → 127.0.0.1.
            return stand.lan(
                "get", f"http://{name}.direct.stand.test:{port}{path}",
                "--connect", netns.INET_IP, "--timeout", "6", "--body",
            )

        def reached_gateway() -> bool:
            service = through_name("loopback", 8080, "/trace")
            stats = through_name("loopback", metrics, "/debug/vars")
            return "GW-LOOPBACK" in service.get("body", "") or stats.get("status") == 200

        # Обычное имя из direct_domains по-прежнему идёт напрямую.
        named = through_name("site", 8080, "/trace")
        assert f"ip={DIRECT}" in named.get("body", ""), named

        assert not reached_gateway()
        guard = stand.gw_run("nft", "list", "chain", "ip", "xgw", "loopback_guard")
        assert "packets 0 " not in guard and "reject" in guard, guard  # отказал именно он

        # Контроль: без цепочки службы шлюза достижимы — тест видит дыру.
        stand.gw_run("nft", "flush", "chain", "ip", "xgw", "loopback_guard")
        assert reached_gateway()
        # Команды XGW возвращают правила на место (enable заменяет таблицу целиком).
        assert stand.xgw("net", "up").returncode == 0
        assert not reached_gateway()

        # Свой трафик XGW не страдает: проба идёт через probe-inbounds на 127.0.0.1.
        assert stand.xgw("probe", "--all").returncode == 0
        assert stand.exit_ip("lan") == VIA_VPN
    finally:
        stand.stop()


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


def test_capture_enabled_in_the_config_is_applied_at_once_and_internet_survives(tmp_path):
    """Дефект с настоящей машины (docs/TEST-REPORT-2026-10-14.md, D1). Шлюз работал без
    перехвата — в конфиге Xray нет tproxy-in. В config.toml включают capture.lan и
    capture.local при живом демоне. Раньше правила загружались сразу, а перезапуск Xray
    ждал окна (до 04:00): весь трафик уходил на порт, который никто не слушает, и машина
    оставалась без интернета. Теперь Xray перезапускается сразу, а правила загружаются
    только после этого: связь не пропадает дольше, чем на перезапуск."""
    stand = Stand(tmp_path, Path(XRAY_BIN), mode="netns")
    try:
        stand.start()
        stand.up()  # перехват в конфиге выключен: XGW только управляет Xray
        applied = stand.root / "etc/xgw/xray/config.json"
        assert "tproxy-in" not in stand.gw_run("cat", str(applied))
        assert stand.exit_ip("gw") == DIRECT
        stand.start_daemon()
        assert wait_for(lambda: stand.xgw_json("status").get("state") == "HEALTHY", 40)
        pid = stand.xray_pid()

        stand.write_config(capture=True)
        seen: list[str] = []
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and seen[-1:] != [VIA_VPN]:
            seen.append(stand.exit_ip("gw"))
            time.sleep(0.3)
        assert seen[-1] == VIA_VPN, f"{seen[-10:]}\n{stand.tail('daemon', 60)}"
        # Без связи — не дольше перезапуска Xray: счёт на секунды, а не до окна.
        assert seen.count("") <= 3, seen
        assert "tproxy-in" in stand.gw_run("cat", str(applied))
        assert stand.xray_pid() != pid  # Xray перезапущен, хотя окно перезапуска не наступило
        assert not (stand.root / "etc/xgw/xray/config.pending.json").exists()
        assert "tproxy to 127.0.0.1:12345" in stand.gw_run("nft", "list", "table", "ip", "xgw")
        assert stand.exit_ip("lan") == VIA_VPN
        capture = _capture(stand)
        assert capture["mode"] == "on" and capture["inbound_missing"] == ""
        assert capture["loaded"] is True
        log = stand.tail("daemon", 200)
        assert "изменение inbound перехвата" in log, log
    finally:
        stand.stop()


def test_capture_is_not_loaded_while_xray_runs_without_the_inbound(tmp_path):
    """Предохранитель сам по себе, без демона: конфиг Xray собран без перехвата, а
    человек (или xgw-net.service при загрузке) просит правила. Правила перехвата не
    загружаются, интернет остаётся прямым (capture.hold = "direct"), команда говорит правду."""
    stand = Stand(tmp_path, Path(XRAY_BIN), mode="netns")
    try:
        stand.start()
        stand.up()  # Xray запущен без tproxy-in
        # Настройки сменили, конфиг Xray ещё прежний.
        stand.write_config(capture=True, hold="direct")
        for command in (("net", "up"), ("enable",)):
            result = stand.xgw(*command)
            table = stand.gw_run("nft", "list", "table", "ip", "xgw")
            assert "tproxy" not in table and "masquerade" in table, command
            assert stand.exit_ip("gw") == DIRECT and stand.exit_ip("lan") == DIRECT
        assert result.returncode == 1 and "перехват пока не включён" in result.stderr
        assert "tproxy-in на порту 12345" in result.stderr
        status = stand.xgw("status").stdout
        assert "Перехват: НЕ ВКЛЮЧЁН (ожидание применения inbound в Xray)" in status, status
        # Выбор «включено» запомнен: после применения конфига правила загружаются сами.
        assert stand.xgw("apply", "--now").returncode == 0
        assert stand.xgw("net", "up").returncode == 0
        assert wait_for(lambda: stand.exit_ip("gw") == VIA_VPN, 30, step=1), stand.xray_log(30)
        assert stand.exit_ip("lan") == VIA_VPN
    finally:
        stand.stop()


def test_lan_is_blocked_without_capture_inbound(tmp_path):
    """capture.hold = "block" (по умолчанию): Xray запущен с конфигом без tproxy-in, а
    правила просят. Мимо VPN не уходит ничего — ни из LAN, ни с самой машины; проходят
    устройства в обход, сокеты самого XGW (метка mark_bypass) и связь LAN со шлюзом."""
    stand = Stand(tmp_path, Path(XRAY_BIN), mode="netns")
    try:
        stand.start()
        stand.up()  # Xray запущен без tproxy-in
        stand.write_config(capture=True)  # настройки сменили, конфиг Xray ещё прежний
        result = stand.xgw("net", "up")
        table = stand.gw_run("nft", "list", "table", "ip", "xgw")
        assert "tproxy" not in table and "chain block_output" in table, table
        assert stand.exit_ip("lan") == "" and stand.exit_ip("gw") == ""
        assert stand.exit_ip("lan", "--bind", netns.LAN_BYPASS_IP) == DIRECT
        assert stand.exit_ip("gw", "--mark", "2") == DIRECT
        assert "error" in stand.lan("dns", "8.8.8.8", "example.org", "--timeout", "3")
        # Отбой, а не таймаут: соединение отклоняется сразу.
        started = time.monotonic()
        refused = stand.lan("get", stand.origin_url("/trace"), "--timeout", "8")
        assert "error" in refused and time.monotonic() - started < 4.0, refused
        assert "трафик заблокирован" in (result.stderr + result.stdout).lower()
        status = stand.xgw("status").stdout
        assert "трафик заблокирован, мимо VPN ничего не уходит" in status, status
        # Конфиг применён — перехват включается, трафик идёт через VPN.
        assert stand.xgw("apply", "--now").returncode == 0
        assert stand.xgw("net", "up").returncode == 0
        assert wait_for(lambda: stand.exit_ip("gw") == VIA_VPN, 30, step=1), stand.xray_log(30)
        assert stand.exit_ip("lan") == VIA_VPN
        assert "chain block_output" not in stand.gw_run("nft", "list", "table", "ip", "xgw")
    finally:
        stand.stop()


def test_direct_session_is_cut_when_blocked(tmp_path):
    """Сессия, открытая при снятом перехвате, после перехода в blocked не доживает по
    записи conntrack: соединение обрывается, остаток тела не приходит."""
    stand = Stand(tmp_path, Path(XRAY_BIN), mode="netns")
    try:
        stand.start()
        stand.up()  # Xray запущен без tproxy-in
        stand.write_config(capture=True)
        assert stand.xgw("disable").returncode == 0
        assert stand.exit_ip("lan") == DIRECT
        url = stand.origin_url("/slow?bytes=2000000&seconds=12")
        download = subprocess.Popen(
            [*stand._prefix("lan"), sys.executable, str(HERE / "lan_client.py"), "get", url,
             "--timeout", "4"],
            stdout=subprocess.PIPE, text=True,
        )
        time.sleep(2.5)  # загрузка идёт напрямую
        assert download.poll() is None
        enabled = stand.xgw("enable")  # перехват включить нельзя — blocked
        assert "трафик заблокирован" in (enabled.stdout + enabled.stderr).lower(), enabled
        cut = time.monotonic()
        out, _ = download.communicate(timeout=20)
        reply = json.loads(out.strip().splitlines()[-1])
        assert "error" in reply, reply  # тело целиком не пришло
        assert time.monotonic() - cut < 6.0  # оборвалась сразу, а не дождалась 12 с
    finally:
        stand.stop()


# --- события (Ф2): шаг watchdog — минута, всё, что быстрее, сделано по событию -----------


@pytest.fixture()
def watched(tmp_path):
    """Шлюз с перехватом и демоном, у которого шаг watchdog — минута: всё, что случается
    быстрее, сделано по событию (watch/events.py), а не очередным шагом."""
    stand = Stand(tmp_path, Path(XRAY_BIN), mode="netns")
    try:
        stand.start()
        stand.up(capture=True, watchdog_s=60)
        enabled = stand.xgw("enable")
        assert enabled.returncode == 0, enabled.stderr
        stand.start_daemon()
        assert wait_for(
            lambda: (s := stand.xgw_json("status"))["daemon"] and s["state"] == "HEALTHY",
            60, step=1,
        ), stand.tail("daemon", 30)
        time.sleep(1.5)  # мониторы событий подписались на netlink
        yield stand
    finally:
        stand.stop()


def _rules_back(stand: Stand) -> bool:
    """Таблица ip xgw на месте и её цепочки не пустые (не только имена после flush)."""
    import re

    listing = stand.run_in("gw", "nft", "list", "table", "ip", "xgw")
    if listing.returncode != 0:
        return False
    chains = {
        name: any(line.strip() and not line.strip().startswith("type ")
                  for line in body.splitlines())
        for name, body in re.findall(
            r"^\s*chain (\w+) \{\n(.*?)^\s*\}", listing.stdout, flags=re.MULTILINE | re.DOTALL
        )
    }
    return {"output", "forward", "prerouting"} <= set(chains) and all(chains.values())


def _log_times(stand: Stand, needle: str) -> list[float]:
    """Время (time.time()) строк журнала демона с needle."""
    import datetime

    times = []
    for line in (stand.logs / "daemon.log").read_text(encoding="utf-8").splitlines():
        if needle in line:
            stamp = datetime.datetime.strptime(line[:23], "%Y-%m-%d %H:%M:%S,%f")
            times.append(stamp.timestamp())
    return times


def test_foreign_flush_is_restored_quickly(watched):
    """Чужие flush ruleset, flush table и delete chain: правила снова на месте ≤ 2 с (шаг
    watchdog — минута), а своя загрузка XGW внеочередной проверки не вызывает."""
    stand = watched
    check = "внеочередная проверка правил перехвата"
    assert _log_times(stand, check) == []
    for count, argv in enumerate((
        ("nft", "flush", "ruleset"),
        ("nft", "flush", "table", "ip", "xgw"),
        ("nft", "delete", "chain", "ip", "xgw", "output"),
    ), start=1):
        assert _rules_back(stand)
        began = time.monotonic()
        stand.gw_run(*argv)
        assert not _rules_back(stand), argv
        assert wait_for(lambda: _rules_back(stand), 2.0, step=0.05), (
            argv, stand.tail("daemon", 30))
        assert time.monotonic() - began <= 2.0
        time.sleep(3.0)  # окно debounce прошло: свои загрузки не будят демон
        assert len(_log_times(stand, check)) == count, (argv, stand.tail("daemon", 30))
    assert gateway_exit(stand) == VIA_VPN


def gateway_exit(stand: Stand) -> str:
    return stand.exit_ip("lan")


def test_wan_flap_wakes_daemon(watched):
    """WAN пропал и вернулся: внеочередной шаг — не позже 2 с после подъёма (по журналу),
    а не через минуту, и шлюз снова HEALTHY."""
    stand = watched
    step = "внеочередной шаг: событие сети"
    members = set(stand.members())
    stand.gw_run("ip", "link", "set", "wan0", "down")
    assert wait_for(lambda: stand.xgw_json("status")["state"] == "WAN_DOWN", 10, step=0.5), (
        stand.tail("daemon", 30))
    time.sleep(3)
    up_at = time.time()
    stand.gw_run("ip", "link", "set", "wan0", "up")
    assert wait_for(lambda: [t for t in _log_times(stand, step) if t >= up_at - 0.05], 5, 0.1), (
        stand.tail("daemon", 30))
    first = min(t for t in _log_times(stand, step) if t >= up_at - 0.05)
    assert first - up_at <= 2.0
    assert wait_for(lambda: stand.xgw_json("status")["state"] == "HEALTHY", 15, step=0.5), (
        stand.tail("daemon", 30))
    assert stand.exit_ip("lan") == VIA_VPN
    # Пробы, не прошедшие без связи, — не повод менять исправные серверы.
    assert set(stand.members()) == members, stand.tail("daemon", 30)
    assert "замена участников" not in (stand.logs / "daemon.log").read_text(encoding="utf-8")


def test_daemon_with_event_monitors_stops_quickly(watched):
    """Мониторы событий (ip, busctl, nft monitor) не задерживают остановку демона:
    `systemctl restart xgw` занимал ~0,5 с (ASSUMPTIONS 215–217) и должен таким остаться."""
    import signal

    stand = watched
    daemon = next(
        proc for proc in stand._procs if "xgw" in proc.args and "run" in proc.args
    )
    monitors = stand.run_in("gw", "pgrep", "-f", "-a", "nft monitor|ip -o monitor").stdout
    assert "nft monitor" in monitors and "ip -o monitor" in monitors, monitors
    began = time.monotonic()
    daemon.send_signal(signal.SIGTERM)
    daemon.wait(timeout=10)
    took = time.monotonic() - began
    print(f"остановка демона: {took:.2f} с")
    assert took < 1.5, (took, stand.tail("daemon", 20))
    left = stand.run_in("gw", "pgrep", "-f", "nft monitor|ip -o monitor")
    assert left.returncode == 1, left.stdout  # мониторы не пережили демон
