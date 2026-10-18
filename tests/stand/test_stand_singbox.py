"""Второе ядро (0.1.12) на живых Xray 26.10.10 и sing-box 1.14.3.

Нужны оба ядра и root (sing-box ставит метку на сокеты, routing_mark):
    XGW_XRAY_BIN=<xray> XGW_SINGBOX_BIN=<sing-box> pytest tests/stand/test_stand_singbox.py

Серверы sing-box на стенде: hysteria2 и TUIC (UDP, без реле), AnyTLS (TCP, перед ним «ТСПУ» —
реле freeze_relay.py). Серверы Xray, которые умеет и sing-box, — VLESS+TLS с самоподписанным
сертификатом: ссылка закрепляет и хеш сертификата (pcs, для Xray), и хеш открытого ключа (pks,
для sing-box).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import netns
import pytest
from stand import Stand, wait_for

XRAY_BIN = os.environ.get("XGW_XRAY_BIN", "")
SINGBOX_BIN = os.environ.get("XGW_SINGBOX_BIN", "")
MODES = ["loopback"] + (["netns"] if netns.available() else [])

pytestmark = pytest.mark.skipif(
    not XRAY_BIN or not Path(XRAY_BIN).exists() or not SINGBOX_BIN
    or not Path(SINGBOX_BIN).exists() or not hasattr(os, "geteuid") or os.geteuid() != 0,
    reason="нужны XGW_XRAY_BIN, XGW_SINGBOX_BIN и root — стенд sing-box пропущен",
)


@pytest.fixture(params=MODES)
def stand(request, tmp_path):
    instance = Stand(tmp_path, Path(XRAY_BIN), mode=request.param, singbox_bin=Path(SINGBOX_BIN))
    try:
        instance.start()
        yield instance
    finally:
        instance.stop()


def _config(stand: Stand, names, **kwargs) -> None:
    stand.set_subscription(names)
    stand.write_config(
        probe_host="origin.stand.test", proxy_domains=("domain:stand.test",), **kwargs,
    )


def _entry(status: dict, name: str) -> dict | None:
    return next(
        (item for item in [*status["members"], *status["spares"]]
         if item["tag"].split("-")[1] == name), None,
    )


def _pin_and_fetch(stand: Stand, name: str) -> None:
    """Весь трафик — через сервер name; запрос к origin должен дойти."""
    from xgw.xraycore.api import parse_balancer_info

    status = stand.xgw_json("status")
    tag = _entry(status, name)["tag"]
    result = stand.xgw("pin", tag, "--ttl", "forever")
    assert result.returncode == 0, result.stdout + result.stderr
    assert wait_for(lambda: parse_balancer_info(stand.xray_api("bi", "auto")).override == tag,
                    15, step=1), stand.xray_log()
    assert stand.via_balancer(), stand.xray_log() + stand.tail("daemon", 30)
    assert stand.xgw("unpin").returncode == 0


def _pin_and_fetch_cli(stand: Stand, name: str) -> None:
    """То же без демона: тег участника берётся из `xgw servers`."""
    from xgw.xraycore.api import parse_balancer_info

    servers = stand.xgw_json("servers")
    tag = next(item["tag"] for item in [*servers["members"], *servers["spares"]]
               if item["tag"].split("-")[1] == name)
    assert stand.xgw("pin", tag, "--ttl", "forever").returncode == 0
    assert wait_for(lambda: parse_balancer_info(stand.xray_api("bi", "auto")).override == tag,
                    15, step=1), stand.xray_log()
    assert stand.via_balancer(), stand.xray_log()
    assert stand.xgw("unpin").returncode == 0


def test_servers_that_only_singbox_can_run_carry_the_traffic(stand):
    """hysteria2, TUIC и AnyTLS Xray не умеет: их ведёт sing-box, а Xray подключён к нему через
    локальные мосты. Пока сервер выбран вручную, весь трафик идёт именно через него."""
    stand.add_singbox_server("hk", "hysteria2")
    stand.add_singbox_server("jp", "tuic")
    stand.add_singbox_server("se", "anytls")
    _config(stand, ("nl", "hk", "jp", "se"), max_members=4)
    result = stand.xgw("apply", "--now")
    assert result.returncode == 0, result.stdout + result.stderr + stand.xray_log()
    assert "sing-box запущен" in result.stdout
    assert (stand.root / "etc/xgw/sing-box/config.json").exists()
    stand.start_daemon()

    def alive():
        status = stand.xgw_json("status")
        members = status["members"]
        return status if status.get("daemon") and len(members) == 4 and all(
            member["alive"] for member in members) else None

    status = wait_for(alive, 90, step=3)
    assert status, stand.tail("daemon", 60) + stand.xray_log()
    by_name = {name: _entry(status, name) for name in ("nl", "hk", "jp", "se")}
    assert by_name["nl"]["profile"] == "xray:default" and by_name["nl"]["core"] == "xray"
    for name in ("hk", "jp", "se"):
        assert by_name[name]["profile"] == "singbox:default", by_name[name]
        assert by_name[name]["core"] == "sing-box"
    for name in ("hk", "jp", "se"):
        _pin_and_fetch(stand, name)


def test_blocked_singbox_server_is_moved_to_the_fragmenting_profile(stand):
    """AnyTLS-сервер за «ТСПУ»: целый ClientHello с именем сервера узнаётся, и соединение
    замирает после 16 КБ (FROZEN). Шлюз сам переводит сервер на профиль sing-box с дроблением
    TLS — заменой outbound'а в Xray через API: ни Xray, ни sing-box не перезапускаются, а
    конфиг sing-box остаётся прежним (профили заведены в нём заранее)."""
    se = stand.add_singbox_server("se", "anytls")
    se.set_mode(f"sni_freeze={se.domain}")
    _config(stand, (*stand.names, "se"), max_members=2)
    result = stand.xgw("apply", "--now")
    assert result.returncode == 0, result.stdout + result.stderr + stand.xray_log()
    xray_pid, singbox_pid = stand.xray_pid(), stand.singbox_pid()
    config_before = (stand.root / "etc/xgw/sing-box/config.json").read_text(encoding="utf-8")
    stand.start_daemon()

    def moved():
        status = stand.xgw_json("status")
        entry = _entry(status, "se") if status.get("daemon") else None
        ok = entry and entry["profile"] == "singbox:tls_fragment" and entry.get("verdict") == "OK"
        return status if ok else None

    status = wait_for(moved, 240, step=3)
    assert status, stand.tail("daemon", 120)
    log = stand.tail("daemon", 400)
    # Роль в метке меняется (proxy- → spare-) при замене участника, отпечаток остаётся. Вердикт до
    # перевода — FROZEN/STALL, но на повторном скане «ТСПУ» может не пропустить и установку
    # соединения (CONNECT_FAIL): профиль меняет любой из этих вердиктов.
    fingerprint = _entry(status, "se")["tag"].split("-", 1)[1]
    assert re.search(rf"скан \w+-{re.escape(fingerprint)}: (FROZEN|STALL_BEFORE_BODY|CONNECT_FAIL)",
                     log), log
    details = [event["detail"] for event in status["events"]]
    assert any("отвечает на профиле «sing-box с дроблением TLS» — он закреплён" in text
               for text in details), details
    assert stand.xray_pid() == xray_pid, "Xray перезапускался"
    assert stand.singbox_pid() == singbox_pid, "sing-box перезапускался"
    assert (stand.root / "etc/xgw/sing-box/config.json").read_text(
        encoding="utf-8") == config_before, "конфиг sing-box менялся"
    _pin_and_fetch(stand, "se")  # сквозь «ТСПУ» трафик идёт


def test_dual_server_is_pinned_to_singbox_and_back_without_restarts(stand):
    """Сервер VLESS+TLS умеют оба ядра. `xgw core … sing-box` переводит его на sing-box, `auto` —
    обратно; оба раза демон меняет только outbound в Xray через API."""
    us = stand.add_server("us", tls=True)
    _config(stand, (*stand.names, "us"), max_members=2)
    result = stand.xgw("apply", "--now")
    assert result.returncode == 0, result.stdout + result.stderr + stand.xray_log()
    xray_pid, singbox_pid = stand.xray_pid(), stand.singbox_pid()
    stand.start_daemon()

    def profile(want: str):
        status = stand.xgw_json("status")
        entry = _entry(status, "us") if status.get("daemon") else None
        return status if entry and entry["profile"] == want and entry.get("alive", True) else None

    assert wait_for(lambda: profile("xray:default"), 60, step=2), stand.tail("daemon", 60)
    tag = _entry(stand.xgw_json("status"), "us")["tag"]
    result = stand.xgw("core", tag, "sing-box")
    assert result.returncode == 0, result.stdout + result.stderr
    assert wait_for(lambda: profile("singbox:default"), 90, step=2), stand.tail("daemon", 80)
    before = us.connections()
    _pin_and_fetch(stand, "us")
    assert us.connections() > before, "трафик не прошёл через сервер us"
    assert stand.xgw("core", tag, "auto").returncode == 0
    assert wait_for(lambda: profile("xray:default"), 90, step=2), stand.tail("daemon", 80)
    assert stand.xray_pid() == xray_pid and stand.singbox_pid() == singbox_pid


def test_daemon_restarts_singbox_when_it_dies(stand):
    """sing-box убит — демон поднимает его заново, мосты снова отвечают."""
    stand.add_singbox_server("hk", "hysteria2")
    _config(stand, ("nl", "de", "hk"), max_members=3)
    result = stand.xgw("apply", "--now")
    assert result.returncode == 0, result.stdout + result.stderr + stand.xray_log()
    stand.start_daemon()
    assert wait_for(lambda: all(m["alive"] for m in stand.members().values()), 60, step=2)
    old = stand.singbox_pid()
    os.kill(old, 9)

    def back():
        try:
            return stand.singbox_pid() != old and stand.singbox_service().is_active()
        except (OSError, ValueError):
            return False

    assert wait_for(back, 90, step=2), stand.tail("daemon", 60)
    assert wait_for(lambda: all(m["alive"] for m in stand.members().values()), 60, step=2), (
        stand.tail("daemon", 60)
    )
    _pin_and_fetch(stand, "hk")


@pytest.mark.skipif(
    not netns.available() or __import__("shutil").which("nft") is None,
    reason="проверка из LAN: нужны Linux, root и nft",
)
def test_lan_device_goes_through_a_singbox_server_with_capture_on(tmp_path):
    """Перехват включён: устройство в LAN выходит через сервер hysteria2. Путь: TPROXY → Xray →
    мост на 127.0.0.1 (без метки: loopback_guard такие пакеты к loopback не пустил бы) →
    sing-box → сервер; сокеты sing-box помечены mark_bypass и идут мимо перехвата. Без метки
    UDP-пакеты sing-box сами попали бы в TPROXY, и hysteria2 не соединился бы."""
    stand = Stand(tmp_path, Path(XRAY_BIN), mode="netns", singbox_bin=Path(SINGBOX_BIN))
    try:
        stand.start()
        stand.add_singbox_server("hk", "hysteria2")
        stand.set_subscription(("hk",))
        stand.write_config(capture=True, max_members=1)
        result = stand.xgw("apply", "--now")
        assert result.returncode == 0, result.stdout + result.stderr + stand.xray_log()
        assert wait_for(lambda: all(m["alive"] for m in stand.members().values()), 60, step=2), (
            stand.xray_log()
        )
        enabled = stand.xgw("enable")
        assert enabled.returncode == 0 and "перехват включён" in enabled.stdout, enabled.stderr
        assert stand.exit_ip("lan") == netns.INET_IP  # вышел с сервера, а не напрямую
        assert stand.exit_ip("gw") == netns.INET_IP  # трафик самого шлюза — тоже
        assert stand.exit_ip("gw", "--mark", "2") == netns.GW_WAN_IP  # метка — мимо
        log = stand.xray_log(60)
        assert "tproxy-in -> proxy-hk" in log, log
    finally:
        stand.stop()


def test_reload_of_singbox_waits_while_a_member_goes_through_it(stand):
    """Перечитывание конфига sing-box рвёт все его соединения (проверено), поэтому, пока через
    него идёт участник, новый конфиг ждёт: `xgw apply` откладывает его, `xgw apply --now`
    применяет сразу. Профили в этом не участвуют — они заведены в конфиге заранее."""
    import json

    stand.add_singbox_server("hk", "hysteria2")
    stand.add_singbox_server("jp", "tuic")
    _config(stand, ("hk", "jp"), max_members=1)
    result = stand.xgw("apply", "--now")
    assert result.returncode == 0, result.stdout + result.stderr + stand.xray_log()
    assert wait_for(lambda: all(m["alive"] for m in stand.members().values()), 60, step=2), (
        stand.xray_log()
    )
    config_path = stand.root / "etc/xgw/sing-box/config.json"
    pending_path = stand.root / "etc/xgw/sing-box/config.pending.json"
    before = config_path.read_text(encoding="utf-8")
    pid = stand.singbox_pid()
    # По мосту на сервер: у hysteria2 и TUIC вариант один.
    assert "jp.stand.test" in before and len(json.loads(before)["inbounds"]) == 2

    stand.set_subscription(("hk",))  # состав серверов sing-box изменился
    result = stand.xgw("apply")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "перечитывание отложено" in result.stdout, result.stdout
    assert config_path.read_text(encoding="utf-8") == before and pending_path.exists()
    assert stand.singbox_pid() == pid

    result = stand.xgw("apply", "--now")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "конфиг sing-box перечитан" in result.stdout, result.stdout
    after = json.loads(config_path.read_text(encoding="utf-8"))
    assert len(after["inbounds"]) == 1 and not pending_path.exists()
    assert "jp.stand.test" not in json.dumps(after)
    assert stand.singbox_pid() == pid  # процесс тот же: перечитан, а не перезапущен
    assert wait_for(lambda: all(m["alive"] for m in stand.members().values()), 60, step=2)
    _pin_and_fetch_cli(stand, "hk")


def test_blocked_dual_server_leaves_xray_for_singbox_on_its_own(stand):
    """Приёмка 0.1.12, пункт 4: сервер VLESS+TLS, который умеют оба ядра, за «ТСПУ», узнающим и
    целый ClientHello, и мелкие записи Xray (sni_freeze_strict): на обычном профиле и с
    дроблением Xray он «замерзает» (FROZEN после 16 КБ). Шлюз сам перебирает профили и
    переводит сервер на sing-box с дроблением TLS — заменой outbound'а через API: ни Xray, ни
    sing-box не перезапускаются, конфиг sing-box не меняется."""
    us = stand.add_server("us", tls=True)
    us.set_mode(f"sni_freeze_strict={us.domain}")
    _config(stand, (*stand.names, "us"), max_members=2)
    result = stand.xgw("apply", "--now")
    assert result.returncode == 0, result.stdout + result.stderr + stand.xray_log()
    xray_pid, singbox_pid = stand.xray_pid(), stand.singbox_pid()
    config_before = (stand.root / "etc/xgw/sing-box/config.json").read_text(encoding="utf-8")
    stand.start_daemon()

    def moved():
        status = stand.xgw_json("status")
        entry = _entry(status, "us") if status.get("daemon") else None
        ok = entry and entry["profile"] == "singbox:tls_fragment" and entry.get("verdict") == "OK"
        return status if ok else None

    status = wait_for(moved, 300, step=3)
    assert status, stand.tail("daemon", 120)
    details = [event["detail"] for event in status["events"]]
    assert any("не отвечает на профиле «Xray с дроблением ClientHello» — пробую «sing-box с "
               "дроблением TLS»" in text for text in details), details
    assert any("отвечает на профиле «sing-box с дроблением TLS» — он закреплён" in text
               for text in details), details
    assert stand.xray_pid() == xray_pid and stand.singbox_pid() == singbox_pid
    assert (stand.root / "etc/xgw/sing-box/config.json").read_text(
        encoding="utf-8") == config_before
    before = us.connections()
    _pin_and_fetch(stand, "us")
    assert us.connections() > before, "трафик не прошёл через сервер us"
