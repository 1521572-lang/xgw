"""Проверки стенда: трафик самой машины через TUN-интерфейс (capture.method = "tun").

Только режим netns, на настоящем ядре и настоящем Xray; нужны Linux, root, nft:

    sudo -E XGW_XRAY_BIN=<путь к xray> pytest tests/stand/test_stand_tun.py -q

Как отличить путь трафика — как в test_stand_lan.py: origin на /trace отдаёт адрес, с
которого пришёл запрос. 5.5.5.1 (2001:db8:5::1) — запрос вышел с VPN-сервера, 5.5.5.2
(2001:db8:5::2) — ушёл с WAN шлюза напрямую.
"""

from __future__ import annotations

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
VIA_VPN6 = netns.INET_IP6
DIRECT6 = netns.GW_WAN_IP6
TUN = "xgwtun0"
TPROXY_TABLE, TUN_TABLE = "100", "101"

pytestmark = [
    pytest.mark.skipif(
        not XRAY_BIN or not Path(XRAY_BIN).exists(), reason="нет XGW_XRAY_BIN — стенд пропущен"
    ),
    pytest.mark.skipif(
        not netns.available() or shutil.which("nft") is None,
        reason="проверки TUN: нужны Linux, root и nft",
    ),
]


def _stand(tmp_path: Path, **config) -> Stand:
    stand = Stand(tmp_path, Path(XRAY_BIN), mode="netns", ipv6=config.get("ipv6") == "proxy")
    stand.start()
    # Контейнеры Docker — в test_stand_docker.py: здесь таблица TUN только у самой машины.
    config.setdefault("containers", False)
    stand.up(capture=True, method="tun", **config)
    enabled = stand.xgw("enable")
    assert enabled.returncode == 0, enabled.stderr
    return stand


@pytest.fixture()
def gateway(tmp_path):
    stand = None
    try:
        stand = _stand(tmp_path)
        yield stand
    finally:
        if stand is not None:
            stand.stop()


def _capture(stand: Stand) -> dict:
    return stand.xgw_json("status")["capture"]


def _link(stand: Stand) -> str:
    return stand.gw_run("ip", "-br", "link", "show", TUN, check=False)


def _routes(stand: Stand, *family: str, table: str = TUN_TABLE) -> str:
    return stand.gw_run("ip", *family, "route", "show", "table", table, check=False)


def _rules(stand: Stand, *family: str) -> str:
    return stand.gw_run("ip", *family, "rule", "show")


def test_gateway_traffic_goes_through_tun_and_lan_stays_on_tproxy(gateway):
    # Сначала убеждаемся, что прямой путь вообще работает (иначе тест ничего не докажет).
    assert gateway.exit_ip("gw", "--mark", "2") == DIRECT
    assert gateway.exit_ip("gw") == VIA_VPN
    assert gateway.exit_ip("lan") == VIA_VPN  # сеть Wi-Fi — по-прежнему TPROXY
    assert gateway.exit_ip("lan", "--bind", netns.LAN_BYPASS_IP) == DIRECT  # обход VPN

    # DNS самой машины: резолвера 8.8.8.8 на стенде нет, отвечает только Xray (UDP и TCP).
    for transport in ((), ("--tcp",)):
        answer = gateway.client("gw", "dns", "8.8.8.8", "example.org", *transport)
        assert answer.get("answers") == [netns.INET_IP], answer
        assert answer["from"] == "8.8.8.8"
    # Сайт по имени: имя разрешает Xray, сниффинг подставляет домен вместо адреса.
    named = gateway.client("gw", "get", "http://site.stand.test:8080/trace", "--dns", "8.8.8.8")
    assert f"ip={VIA_VPN}" in named.get("body", ""), named
    # Много данных подряд: пакеты не теряются на пути через интерфейс.
    big = gateway.client("gw", "get", gateway.origin_url("/bytes?n=3000000"), "--timeout", "30")
    assert big.get("bytes") == 3000000, big

    log = gateway.xray_log(80)
    assert "tun-in -> proxy-" in log and "tun-in -> dns-out" in log
    assert "tproxy-in -> proxy-" in log  # устройство из LAN пришло через TPROXY

    # Устройство, правило и маршруты. Постоянный TUN держит открытым Xray.
    link = _link(gateway)
    assert TUN in link and "LOWER_UP" in link
    assert f"default dev {TUN}" in _routes(gateway)
    assert "blackhole default metric 4096" in _routes(gateway)
    # Пакеты самой машины — в TUN (iif lo), помеченные пакеты LAN — по-прежнему локально.
    rules = _rules(gateway)
    assert f"from all fwmark 0x1 iif lo lookup {TUN_TABLE}" in rules
    assert f"from all fwmark 0x1 lookup {TPROXY_TABLE}" in rules
    assert "local default dev lo" in _routes(gateway, table=TPROXY_TABLE)
    table = gateway.gw_run("nft", "list", "table", "ip", "xgw")
    assert 'iifname "lo"' not in table and "chain output" in table  # TPROXY на lo не нужен
    capture = _capture(gateway)
    assert capture["mode"] == "on" and capture["loaded"] is True and capture["tun"] is True
    assert "эта машина через TUN" in gateway.xgw("status").stdout
    assert gateway.xgw("probe", "--all").returncode == 0  # пробы XGW с перехватом работают


def test_tun_is_fail_closed_and_recovers_when_xray_returns(gateway):
    assert gateway.exit_ip("gw") == VIA_VPN
    gateway.xray_service().stop()
    assert TUN in _link(gateway) and "NO-CARRIER" in gateway.gw_run("ip", "link", "show", TUN)
    assert gateway.exit_ip("gw") == ""  # ни через VPN, ни мимо
    assert gateway.exit_ip("lan") == ""
    assert gateway.exit_ip("gw", "--mark", "2") == DIRECT  # запросы самого XGW — напрямую

    # Xray вернулся и подключился к тому же интерфейсу: никаких действий XGW не нужно.
    config = gateway.root / "etc/xgw/xray/config.json"
    gateway.gw_popen("xray-again", [str(gateway.xray_bin), "run", "-c", str(config)])
    assert wait_for(lambda: gateway.exit_ip("gw") == VIA_VPN, 20)


def test_tun_follows_enable_disable_and_net_down(gateway):
    assert gateway.xgw("disable").returncode == 0
    assert gateway.exit_ip("gw") == DIRECT  # перехват снят — всё напрямую
    assert TUN in _link(gateway)  # интерфейс остаётся: его держит Xray
    assert "default" not in _routes(gateway) and "fwmark" not in _rules(gateway)
    assert _capture(gateway)["loaded"] is True
    assert gateway.xgw("enable").returncode == 0
    assert gateway.exit_ip("gw") == VIA_VPN  # тот же работающий Xray, без перезапуска

    for _ in range(2):  # повторные включения не плодят правил и маршрутов
        assert gateway.xgw("net", "up").returncode == 0
    assert _rules(gateway).count("fwmark 0x1") == 2  # TUN для машины и TPROXY для LAN
    assert _routes(gateway).count(f"default dev {TUN}") == 1

    down = gateway.xgw("net", "down")
    assert down.returncode == 0, down.stderr
    assert f"интерфейс TUN {TUN} оставлен" in down.stdout
    assert "xgw" not in gateway.gw_run("nft", "list", "tables")
    assert _routes(gateway).strip() == "" and "fwmark" not in _rules(gateway)
    assert _routes(gateway, table=TPROXY_TABLE).strip() == ""
    assert TUN in _link(gateway)  # Xray держит его открытым; убирает uninstall
    assert gateway.exit_ip("gw") == DIRECT
    assert gateway.xgw("net", "up").returncode == 0
    assert gateway.exit_ip("gw") == VIA_VPN  # интерфейс тот же — Xray его не терял


def test_method_can_be_switched_both_ways(tmp_path):
    stand = _stand(tmp_path)
    try:
        assert stand.exit_ip("gw") == VIA_VPN and f"default dev {TUN}" in _routes(stand)
        # tun → tproxy. Сеть LAN включена, поэтому tproxy-in в Xray есть в обоих режимах, и
        # машина переключается на него сразу, ещё до применения нового конфига Xray.
        stand.write_config(capture=True, method="tproxy", containers=False)
        assert stand.xgw("net", "up").returncode == 0
        table = stand.gw_run("nft", "list", "table", "ip", "xgw")
        assert 'iifname "lo"' in table and "tproxy to 127.0.0.1:12345" in table
        assert "local default dev lo" in _routes(stand, table=TPROXY_TABLE)
        assert _routes(stand).strip() == "" and "iif lo" not in _rules(stand)
        assert stand.exit_ip("gw") == VIA_VPN and stand.exit_ip("lan") == VIA_VPN
        assert _capture(stand)["tun"] is False and "через TUN" not in stand.xgw("status").stdout
        assert stand.xgw("apply", "--now").returncode == 0  # Xray теперь без inbound tun
        assert wait_for(lambda: stand.exit_ip("gw") == VIA_VPN, 30, step=1), stand.xray_log(30)
        assert "tun-in" not in stand.gw_run("cat", str(stand.root / "etc/xgw/xray/config.json"))

        # tproxy → tun. Inbound'а tun в работающем Xray ещё нет: маршрут в интерфейс увёл бы
        # трафик машины в никуда (так машина и оставалась без интернета — отчёт о проверке
        # на настоящей машине, дефект D1). Поэтому перехват не загружается вовсе: сеть
        # работает напрямую, а команды и статус говорят, чего ждут.
        stand.write_config(capture=True, method="tun", containers=False)
        assert stand.xgw("net", "up").returncode == 0
        assert _routes(stand).strip() == "" and "fwmark" not in _rules(stand)
        table = stand.gw_run("nft", "list", "table", "ip", "xgw")
        assert "tproxy" not in table and "masquerade" in table  # шлюз — обычный роутер
        assert stand.exit_ip("gw") == DIRECT and stand.exit_ip("lan") == DIRECT
        status = stand.xgw("status").stdout
        assert "Перехват: НЕ ВКЛЮЧЁН (ожидание применения inbound в Xray)" in status, status
        assert "tun-in" in status and "ПРАВИЛА НЕ ЗАГРУЖЕНЫ" not in status
        refused = stand.xgw("enable")
        assert refused.returncode == 1 and "перехват пока не включён" in refused.stderr
        assert "xgw apply --now" in refused.stderr and stand.exit_ip("gw") == DIRECT
        # Конфиг применён (Xray перезапущен с tun-in) — правила загружаются как обычно.
        assert stand.xgw("apply", "--now").returncode == 0
        assert "tun-in" in stand.gw_run("cat", str(stand.root / "etc/xgw/xray/config.json"))
        assert stand.xgw("net", "up").returncode == 0
        assert f"default dev {TUN}" in _routes(stand)
        assert 'iifname "lo"' not in stand.gw_run("nft", "list", "table", "ip", "xgw")
        assert wait_for(lambda: stand.exit_ip("gw") == VIA_VPN, 30, step=1), stand.xray_log(30)
        assert stand.exit_ip("lan") == VIA_VPN
        assert _capture(stand)["tun"] is True and _capture(stand)["inbound_missing"] == ""
        # Интерфейс подготовлен до запуска Xray и постоянный: он переживает остановку.
        stand.xray_service().stop()
        assert TUN in _link(stand) and stand.exit_ip("gw") == ""
    finally:
        stand.stop()


def test_ipv6_of_the_machine_goes_through_the_same_tun(tmp_path):
    stand = _stand(tmp_path, ipv6="proxy")
    try:
        assert stand.exit_ip6("gw", "--mark", "2") == DIRECT6
        assert stand.exit_ip6("gw") == VIA_VPN6
        assert stand.exit_ip("gw") == VIA_VPN
        assert f"default dev {TUN}" in _routes(stand, "-6")
        assert "blackhole" in _routes(stand, "-6")
        assert f"from all fwmark 0x1 iif lo lookup {TUN_TABLE}" in _rules(stand, "-6")
        assert "tproxy-in6" not in stand.xray_log(80)  # отдельный inbound на ::1 не нужен
        table6 = stand.gw_run("nft", "list", "table", "ip6", "xgw6")
        assert "chain output" in table6 and "chain prerouting" not in table6
        capture = _capture(stand)
        assert capture["tun"] is True and capture["ipv6"] is True and capture["loaded"] is True
        stand.xray_service().stop()
        assert stand.exit_ip6("gw") == ""  # fail-closed и для IPv6
    finally:
        stand.stop()


def test_strict_reverse_path_filter_breaks_tun_and_diag_says_so(gateway):
    """Ответы Xray приходят с интерфейса, которого нет в обратном маршруте до их
    отправителя. «Мягкий» rp_filter (2, умолчание Ubuntu) их пропускает — но только
    потому, что на интерфейсе есть адрес; строгий (1) отбрасывает всегда. Тест
    фиксирует и то и другое: это граница применимости режима, а `xgw diag` о ней
    предупреждает."""
    assert "169.254.10.1/32" in gateway.gw_run("ip", "-br", "addr", "show", TUN)
    assert gateway.gw_run("sysctl", "-n", "net.ipv4.conf.all.rp_filter").strip() == "2"
    assert gateway.exit_ip("gw") == VIA_VPN

    gateway.gw_run("sysctl", "-w", "net.ipv4.conf.all.rp_filter=1")
    gateway.gw_run("sysctl", "-w", f"net.ipv4.conf.{TUN}.rp_filter=1")
    assert gateway.exit_ip("gw") == ""
    diag = gateway.xgw("diag").stdout
    assert "rp_filter" in diag and "WARN" in diag, diag

    gateway.gw_run("sysctl", "-w", "net.ipv4.conf.all.rp_filter=2")
    gateway.gw_run("sysctl", "-w", f"net.ipv4.conf.{TUN}.rp_filter=0")
    assert wait_for(lambda: gateway.exit_ip("gw") == VIA_VPN, 15)


def test_validation_does_not_fight_the_running_xray_for_the_interface(gateway):
    """`xray run -test` создаёт интерфейс из inbound tun, а рабочий Xray держит его
    открытым. Контрольный опыт: с настоящим именем проверка занятого интерфейса
    проваливается; XGW подставляет одноразовое имя, и применение конфига проходит."""
    assert gateway.exit_ip("gw") == VIA_VPN
    config = gateway.root / "etc/xgw/xray/config.json"
    control = gateway.run_in("gw", str(gateway.xray_bin), "run", "-test", "-c", str(config))
    assert control.returncode != 0, control.stdout + control.stderr  # занято работающим Xray
    applied = gateway.xgw("apply")
    assert applied.returncode == 0, applied.stdout + applied.stderr
    assert gateway.exit_ip("gw") == VIA_VPN  # и сам Xray это не задело
    assert TUN in _link(gateway) and "xgwchk" not in gateway.gw_run("ip", "-br", "link")


def _watch_switch(stand: Stand, done, limit: float = 90.0) -> list[str]:
    """Опрашивает, с какого адреса выходит сама машина, пока смена способа не завершится.
    Возвращает всё, что видел: адрес VPN, адрес WAN (напрямую) или пусто (нет связи)."""
    seen: list[str] = []
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        seen.append(stand.exit_ip("gw"))
        if seen[-1] == VIA_VPN and done():
            return seen
        time.sleep(0.3)
    raise AssertionError(f"смена способа не завершилась: {seen[-10:]}\n{stand.tail('daemon', 40)}")


def test_daemon_switches_the_method_by_itself_and_never_lets_traffic_out_directly(tmp_path):
    """Способ перехвата меняют в config.toml при работающем демоне: tproxy → tun → tproxy.
    Никаких команд и никакого окна перезапуска (на стенде оно — минута после полуночи):
    демон сам перезапускает Xray с новым inbound'ом и только после этого меняет правила.
    Пока это происходит, машина либо ходит через VPN по прежним правилам, либо секунду
    без связи — но не напрямую."""
    stand = Stand(tmp_path, Path(XRAY_BIN), mode="netns")
    try:
        stand.start()
        stand.up(capture=True, method="tproxy", containers=False)
        assert stand.xgw("enable").returncode == 0
        assert stand.exit_ip("gw") == VIA_VPN and _routes(stand).strip() == ""
        stand.start_daemon()
        assert wait_for(lambda: stand.xgw_json("status").get("state") == "HEALTHY", 40)
        config_json = stand.root / "etc/xgw/xray/config.json"

        stand.write_config(capture=True, method="tun", containers=False)
        seen = _watch_switch(stand, lambda: f"default dev {TUN}" in _routes(stand))
        assert DIRECT not in seen, seen
        assert "tun-in" in stand.gw_run("cat", str(config_json))
        assert not (stand.root / "etc/xgw/xray/config.pending.json").exists()
        capture = _capture(stand)
        assert capture["tun"] is True and capture["inbound_missing"] == ""
        assert stand.exit_ip("lan") == VIA_VPN
        log = stand.tail("daemon", 200)
        assert "изменение inbound перехвата" in log, log

        stand.write_config(capture=True, method="tproxy", containers=False)
        seen = _watch_switch(
            stand, lambda: "tun-in" not in stand.gw_run("cat", str(config_json))
            and _routes(stand).strip() == ""
        )
        assert DIRECT not in seen, seen
        assert 'iifname "lo"' in stand.gw_run("nft", "list", "table", "ip", "xgw")
        assert stand.exit_ip("gw") == VIA_VPN and stand.exit_ip("lan") == VIA_VPN
    finally:
        stand.stop()
