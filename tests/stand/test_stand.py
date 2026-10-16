"""Проверки стенда (раздел 9 ТЗ), этап 2: переключение с «замороженного» узла,
контроль с HEAD, применение подписки без разрыва соединений, замена участника.

Нужен настоящий Xray: XGW_XRAY_BIN=<путь к xray> pytest tests/stand -q
Режим loopback работает без root на любой ОС; тот же набор в пространствах
имён (netns) запускается на Linux под root. Проверки из LAN (перехват, DNS,
fail-closed, enable/disable) — в test_stand_lan.py.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import netns
import pytest
from stand import Stand, wait_for

XRAY_BIN = os.environ.get("XGW_XRAY_BIN", "")
MODES = ["loopback"] + (["netns"] if netns.available() else [])
CYCLE = 10.0  # interval × sampling в конфиге стенда
SWITCH_LIMIT = 25.0  # «не позже чем через 2 цикла (не дольше 25 с)»

pytestmark = pytest.mark.skipif(
    not XRAY_BIN or not Path(XRAY_BIN).exists(),
    reason="нет XGW_XRAY_BIN — стенд пропущен",
)


@pytest.fixture(params=MODES)
def stand(request, tmp_path):
    instance = Stand(tmp_path, Path(XRAY_BIN), mode=request.param)
    try:
        instance.start()
        yield instance
    finally:
        instance.stop()


def _members(stand: Stand) -> dict[str, dict]:
    return stand.members()


def _up(stand: Stand, names=None, **config) -> list[str]:
    return stand.up(names, **config)


def _make_fastest(stand: Stand, tag: str) -> None:
    stand.make_fastest(tag, CYCLE)


def test_frozen_node_is_dropped_within_two_cycles(stand):
    """freeze_after=16384 на текущем узле → `xray api bi` показывает другой узел
    не позже чем через 2 цикла interval × sampling."""
    members = _up(stand)
    victim, other = members[0], members[1]
    _make_fastest(stand, victim)

    stand.server_of(victim).set_mode("freeze_after=16384")
    started = time.monotonic()
    switched = wait_for(lambda: stand.selecting() == (other,), SWITCH_LIMIT + 5)
    elapsed = time.monotonic() - started
    assert switched, f"балансировщик остался на {stand.selecting()}"
    assert elapsed <= SWITCH_LIMIT, f"переключение заняло {elapsed:.1f} с"
    assert _members(stand)[victim]["alive"] is False

    # Узел не возвращается, пока «заморозка» не снята…
    deadline = time.monotonic() + CYCLE + 3
    while time.monotonic() < deadline:
        assert victim not in stand.selecting()
        time.sleep(1)
    # …и восстанавливается после первой же удачной пробы.
    stand.server_of(victim).set_mode("pass")
    assert wait_for(lambda: stand.selecting() == (victim,), 3 * CYCLE)


def test_head_probe_keeps_frozen_node(stand):
    """Контроль: с httpMethod HEAD тот же «замороженный» узел остаётся выбранным —
    именно поэтому нужен GET."""
    members = _up(stand)
    victim = members[0]
    # Тот же конфиг шлюза, но проба — HEAD, как у sing-box и mihomo.
    stand.xray_service().stop()
    config_path = stand.root / "etc/xgw/xray/config.json"
    config = stand.applied()
    assert config["burstObservatory"]["pingConfig"]["httpMethod"] == "GET"
    config["burstObservatory"]["pingConfig"]["httpMethod"] = "HEAD"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    stand.gw_popen("xray-head", [str(stand.xray_bin), "run", "-c", str(config_path)])
    assert wait_for(lambda: all(m["alive"] for m in _members(stand).values()), 40)
    _make_fastest(stand, victim)

    stand.server_of(victim).set_mode("freeze_after=16384")
    deadline = time.monotonic() + SWITCH_LIMIT + 5  # дольше, чем нужно GET-пробе
    while time.monotonic() < deadline:
        assert _members(stand)[victim]["alive"] is True
        time.sleep(2)
    assert stand.selecting() == (victim,)

    # При этом настоящая загрузка через этот узел не проходит: сервер «жив» только для HEAD.
    probe = stand.xgw("probe", victim)
    assert probe.returncode == 1, probe.stdout
    assert "FROZEN" in probe.stdout, probe.stdout


def test_subscription_change_applies_without_dropping_connections(stand):
    """Добавление и удаление сервера в подписке применяются через API; длинная
    загрузка через неизменившийся узел при этом не прерывается."""
    _up(stand, names=("nl", "de"))
    pid = stand.xray_pid()
    config = stand.applied()
    keeper = next(o["tag"] for o in config["outbounds"] if o["tag"].startswith("proxy-nl-"))
    probe = next(i for i in config["inbounds"] if i["tag"] == keeper.replace("proxy-", "probe-"))
    account = probe["settings"]["accounts"][0]

    size, seconds = 1_500_000, 12
    download = stand.gw_popen(
        "download",
        [sys.executable, str(Path(__file__).with_name("download.py")),
         "--proxy", f"127.0.0.1:{probe['port']}", "--user", account["user"],
         # Через «=»: пароль проб случаен и бывает, что начинается с «-» — тогда argparse
         # принял бы его за следующий ключ, и тест падал раз в несколько десятков прогонов.
         f"--password={account['pass']}",
         stand.origin_url(f"/slow?bytes={size}&seconds={seconds}")],
    )
    time.sleep(2)

    stand.set_subscription(("nl", "de", "fr"))  # сервер добавлен
    added = stand.xgw("apply")
    assert added.returncode == 0 and "через API" in added.stdout, added.stdout + added.stderr
    assert "fr-" in stand.xray_api("lso")
    # Домена нового сервера нет в dns.hosts работающего ядра: Xray разрешает его
    # через свои DNS-серверы (раздел 6.4) — узел должен сразу работать.
    tags = stand.xray_api("lso").split('"')
    fresh = next(tag for tag in tags if tag.startswith(("spare-fr-", "proxy-fr-")))
    assert stand.xgw("probe", fresh).returncode == 0

    time.sleep(2)
    stand.set_subscription(("nl", "fr"))  # сервер удалён
    removed = stand.xgw("apply")
    assert removed.returncode == 0 and "через API" in removed.stdout, removed.stdout
    listing = stand.xray_api("lso")
    assert "-de-" not in listing and keeper in listing

    assert download.wait(timeout=seconds + 60) == 0, stand.tail("download")
    result = json.loads(stand.tail("download", 1))
    assert result["ok"] and result["bytes"] == size
    assert result["seconds"] >= seconds - 2  # загрузка шла всё это время, а не оборвалась
    assert stand.xray_pid() == pid  # Xray не перезапускался


def test_priority_levels_go_down_when_the_top_is_dead_and_come_back(stand):
    """Уровни приоритета на живом Xray: высокий (nl) работает один, хотя max_members = 2;
    перестал отвечать — демон переходит на средний (de), низкий (fr) не трогает; ожил —
    возвращается к высокому."""
    _up(stand)
    stand.start_daemon()

    def by_country(status: dict) -> dict[str, dict]:
        return {entry["tag"].split("-")[1]: entry
                for entry in [*status["members"], *status["spares"]]}

    status = wait_for(lambda: (s := stand.xgw_json("status"))["daemon"] and s, 60, step=2)
    assert status, stand.tail("daemon", 30)
    tags = {country: entry["tag"] for country, entry in by_country(status).items()}
    for country, level in (("nl", "high"), ("fr", "low")):
        result = stand.xgw("priority", tags[country], level)
        assert result.returncode == 0, result.stdout + result.stderr

    def working(country: str):
        def check():
            status = stand.xgw_json("status")
            members = [entry["tag"].split("-")[1] for entry in status["members"]]
            return members == [country] and status

        return check

    status = wait_for(working("nl"), 120, step=2)
    assert status, stand.tail("daemon", 60)
    assert status["tier"] == "high"
    assert wait_for(lambda: stand.selecting() and stand.selecting()[0].startswith("proxy-nl"),
                    40, step=2), stand.selecting()

    stand.servers["nl"].set_mode("drop")
    status = wait_for(working("de"), 150, step=2)
    assert status, stand.tail("daemon", 60)
    assert status["tier"] == "medium"
    assert any("на уровне «высокий» живых серверов нет" in event["detail"]
               for event in status["events"])

    stand.servers["nl"].set_mode("pass")
    status = wait_for(working("nl"), 200, step=2)
    assert status, stand.tail("daemon", 60)
    assert any("снова отвечает" in event["detail"] for event in status["events"])
    assert "fr" not in [entry["tag"].split("-")[1] for entry in status["members"]]


@pytest.fixture(params=MODES)
def priced_stand(request, tmp_path):
    """Стенд с четырьмя серверами: nl, de — в безлимитной подписке, fr (x1) и us (x10) — в
    подписке с лимитом трафика (заголовок subscription-userinfo в самом файле подписки)."""
    instance = Stand(
        tmp_path, Path(XRAY_BIN), mode=request.param, names=("nl", "de", "fr", "us")
    )
    try:
        instance.start()
        paid = tmp_path / "paid.txt"
        lines = [
            "# subscription-userinfo: upload=0; download=1000000000; total=100000000000",
            instance.servers["fr"].link("🇫🇷 x1 FR-stand"),
            instance.servers["us"].link("🇺🇸 x10 US-stand"),
        ]
        paid.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
        instance.set_subscription(("nl", "de"))
        extra = ["", "[[subscriptions]]", 'name = "paid"', f'url = "{paid.as_uri()}"',
                 "refresh_minutes = 1"]
        # Пробы и сквозная проверка — по имени origin через балансировщик: в режиме
        # loopback «интернет» — 127.0.0.1, и по адресу запрос ушёл бы напрямую.
        instance.write_config(
            max_members=2, extra="\n".join(extra) + "\n", probe_host="origin.stand.test",
            proxy_domains=("domain:stand.test",),
        )
        yield instance
    finally:
        instance.stop()


def test_limited_reserve_carries_the_traffic_only_while_the_unlimited_are_dead(priced_stand):
    """0.1.8 на живом Xray. Безлимитные nl и de — участники, лимитированные fr (x1) и us
    (x10) — запасные, fr — резервный выход балансировщика (fallbackTag). Ядро резервный не
    пробует. Безлимитные перестали отвечать — трафик идёт через fr (RESERVE), участники
    те же; fr тоже не отвечает — резервным становится us (через API, Xray не
    перезапускается); безлимитные ожили — Xray сам вернул трафик на них."""
    stand = priced_stand
    result = stand.xgw("apply", "--now")
    assert result.returncode == 0, result.stderr + stand.xray_log()
    stand.start_daemon()
    servers = stand.servers

    def country(tag: str) -> str:
        return tag.split("-")[1]

    def status_when(predicate, timeout: float):
        def check():
            status = stand.xgw_json("status")
            return status if status.get("daemon") and predicate(status) else None

        found = wait_for(check, timeout, step=2)
        assert found, stand.tail("daemon", 60)
        return found

    def reserve_is(name: str):
        return lambda s: country((s.get("reserve") or {}).get("tag", "x-x-x")) == name

    status = status_when(lambda s: s["state"] == "HEALTHY" and reserve_is("fr")(s) and all(
        spare["verdict"] for spare in s["spares"]), 90)
    assert sorted(country(member["tag"]) for member in status["members"]) == ["de", "nl"]
    costs = {country(spare["tag"]): spare["cost"] for spare in status["spares"]}
    assert costs == {"fr": 1.0, "us": 10.0}
    applied = stand.applied()
    assert applied["routing"]["balancers"][0]["fallbackTag"] == status["reserve"]["tag"]
    assert applied["burstObservatory"]["subjectSelector"] == ["proxy-"]
    # Ядро пробует участников, а резервный — нет: через fr за это время ни одного соединения.
    fr_before, nl_before = servers["fr"].connections(), servers["nl"].connections()
    time.sleep(2.5 * CYCLE)
    assert stand.via_balancer()  # запрос через балансировщик — через участника, не через fr
    assert servers["fr"].connections() == fr_before, stand.tail("daemon", 80)
    assert servers["nl"].connections() > nl_before
    pid = stand.xray_pid()

    for name in ("nl", "de"):
        servers[name].set_mode("drop")
    status = status_when(lambda s: s["state"] == "RESERVE", 60)
    assert sorted(country(member["tag"]) for member in status["members"]) == ["de", "nl"]
    assert any("трафик идёт через резервный сервер «🇫🇷 x1 FR-stand» (x1)" in event["detail"]
               for event in status["events"])
    fr_before = servers["fr"].connections()
    assert stand.via_balancer()  # трафик идёт — через резервный
    assert wait_for(lambda: servers["fr"].connections() >= fr_before + 3, 30, step=1)

    servers["fr"].set_mode("drop")
    status = status_when(lambda s: reserve_is("us")(s) and s["state"] == "RESERVE", 120)
    assert any("резервный сервер — «🇺🇸 x10 US-stand» (x10)" in event["detail"]
               for event in status["events"])
    assert stand.xray_pid() == pid  # fallbackTag сменился через API
    assert sorted(country(member["tag"]) for member in status["members"]) == ["de", "nl"]
    us_before = servers["us"].connections()
    assert stand.via_balancer()
    assert wait_for(lambda: servers["us"].connections() >= us_before + 3, 30, step=1)

    for name in ("nl", "de"):
        servers[name].set_mode("pass")
    status = status_when(lambda s: s["state"] == "HEALTHY", 60)
    assert any("серверы в работе снова отвечают" in event["detail"]
               for event in status["events"])
    assert stand.xray_pid() == pid
    time.sleep(3)
    us_before = servers["us"].connections()
    assert stand.via_balancer()
    time.sleep(CYCLE)
    assert servers["us"].connections() == us_before  # трафик ушёл с резервного


def test_daemon_replaces_frozen_member_and_expires_pin(stand):
    """«Замороженный» участник заменяется запасным; закрепление снимается по сроку."""
    members = _up(stand)
    pid = stand.xray_pid()
    stand.start_daemon()

    def ready():
        status = stand.xgw_json("status")
        scanned = [spare for spare in status["spares"] if spare["verdict"] == "OK"]
        return status["daemon"] and status["state"] == "HEALTHY" and scanned and status

    status = wait_for(ready, 60, step=2)
    assert status, stand.tail("daemon", 30)
    spare = status["spares"][0]["tag"]
    victim = members[0]

    stand.server_of(victim).set_mode("freeze_after=16384")

    def rotated():
        status = stand.xgw_json("status")
        tags = [member["tag"] for member in status["members"]]
        return spare.replace("spare-", "proxy-") in tags and victim not in tags and status

    status = wait_for(rotated, 90, step=2)
    assert status, stand.tail("daemon", 40)
    assert victim.replace("proxy-", "spare-") in [s["tag"] for s in status["spares"]]
    assert any(event["kind"] == "rotation" for event in status["events"])
    assert stand.xray_pid() == pid  # замена прошла через API, без перезапуска
    assert wait_for(lambda: stand.xgw_json("status")["state"] == "HEALTHY", 60, step=2)

    # Ручное закрепление: bo -b auto <тег>, по истечении срока демон делает bo -r.
    target = status["members"][0]["tag"]
    pinned = stand.xgw("pin", target, "--ttl", "6s")
    assert pinned.returncode == 0, pinned.stderr
    assert stand.xgw_json("status")["pin"]["tag"] == target
    assert "Override" in stand.xray_api("bi", "auto") and stand.selecting()
    assert wait_for(lambda: stand.xgw_json("status")["pin"] is None, 30, step=2)
    from xgw.xraycore.api import parse_balancer_info

    # Статус перестаёт показывать закрепление ровно в срок, а `bo -r` демон
    # выполняет на ближайшем шаге watchdog — ждём его, а не угадываем момент.
    assert wait_for(
        lambda: parse_balancer_info(stand.xray_api("bi", "auto")).override is None, 15, step=0.5
    ), stand.tail("daemon", 20)


def test_main_server_is_the_fastest_holds_and_fails_over(stand):
    """0.1.9 на живом Xray. Демон держит один основной сервер — самый быстрый по замеру
    скорости — и закрепляет его в ядре: выбор не скачет, хотя задержки у серверов равные
    (п. 49 ASSUMPTIONS — без этого leastPing прыгает). «Заморозка» основного — трафик сразу
    получает другой живой участник."""
    from xgw.xraycore.api import parse_balancer_info

    def override() -> str | None:
        try:
            return parse_balancer_info(stand.xray_api("bi", "auto")).override
        except RuntimeError:
            return None

    members = _up(
        stand, sticky=True, probe_host="origin.stand.test", proxy_domains=("domain:stand.test",),
    )
    slow, fast = members[0], members[1]
    stand.server_of(slow).set_rate(300)  # ~2,4 Мбит/с; у второго полоса не ограничена
    stand.start_daemon()

    def measured():
        status = stand.xgw_json("status")
        speeds = {m["tag"]: m.get("speed_mbps") for m in status["members"]}
        main = status.get("main") or {}
        return (
            main.get("tag") == fast and main.get("basis") == "speed"
            and None not in (speeds.get(slow), speeds.get(fast)) and status
        )

    status = wait_for(measured, 120, step=2)
    assert status, stand.tail("daemon", 40)
    by_tag = {m["tag"]: m for m in status["members"]}
    assert by_tag[fast]["speed_mbps"] > 3 * by_tag[slow]["speed_mbps"]
    assert by_tag[slow]["speed_mbps"] < 4
    assert override() == fast

    # Держится: три цикла проб ядра — ни одной смены.
    deadline = time.monotonic() + 3 * CYCLE
    while time.monotonic() < deadline:
        assert override() == fast
        time.sleep(1)

    stand.server_of(fast).set_mode("freeze_after=16384")
    started = time.monotonic()
    assert wait_for(lambda: override() == slow, SWITCH_LIMIT + 10, step=0.5), (
        stand.tail("daemon", 30)
    )
    elapsed = time.monotonic() - started
    assert elapsed <= SWITCH_LIMIT, f"переход с замороженного основного занял {elapsed:.1f} с"
    assert stand.via_balancer()  # трафик идёт
    events = [e["detail"] for e in stand.xgw_json("status")["events"] if e["kind"] == "main"]
    assert any("выбираю другой" in event for event in events), events
