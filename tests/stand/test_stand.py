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
    # STALL_BEFORE_BODY допустим только в Windows: там локальный HTTP-фильтр может
    # придержать неполный ответ, и тело до клиента не доходит (ASSUMPTIONS п. 45, 50).
    verdicts = ("FROZEN", "STALL_BEFORE_BODY") if sys.platform == "win32" else ("FROZEN",)
    assert any(verdict in probe.stdout for verdict in verdicts), probe.stdout


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
