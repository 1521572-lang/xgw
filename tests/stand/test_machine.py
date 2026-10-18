"""Этап 4 на «одноразовой машине»: установка, работа после перезагрузки, удаление.

Шлюз здесь — не пространство имён, а загруженная система в контейнере
systemd-nspawn (см. machine.py): настоящие systemd, NetworkManager, dnsmasq и
ufw. `xgw install` и `xgw uninstall` выполняются внутри него целиком, сеть
хоста не затрагивается.

    sudo -E XGW_XRAY_BIN=<путь к xray> pytest tests/stand/test_machine.py -q

Путь к xray можно дать и относительным (tools/xray/xray) — от каталога, откуда
запущен pytest.

Проверки идут по порядку и продолжают одна другую: первый запуск без конфига →
установка без подписки и всё остальное из панели (подписка, включение VPN, список
серверов) → удаление → установка с подпиской в config.toml → работа из LAN →
правка конфига → уведомление → перезагрузка → удаление.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import sys
import tarfile
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import machine as machine_mod
import netns
import pytest
from fake_telegram import TOKEN as TELEGRAM_TOKEN
from machine import Machine, MachineTopology
from stand import UUID, Stand, wait_for

# Абсолютный путь: внутри контейнера команды выполняются из «/», и относительный путь
# там указывал бы не туда.
_XRAY_ENV = os.environ.get("XGW_XRAY_BIN", "")
XRAY_BIN = str(Path(_XRAY_ENV).resolve()) if _XRAY_ENV else ""
_SINGBOX_ENV = os.environ.get("XGW_SINGBOX_BIN", "")
# sing-box (0.1.12) на «машине» необязателен: без него второе ядро выключено, как до 0.1.12.
SINGBOX_BIN = str(Path(_SINGBOX_ENV).resolve()) if _SINGBOX_ENV else ""
REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PANEL_PORT = "8781"
LAUNCHER = "/usr/local/share/applications/xgw-panel.desktop"
STATUS_PAGE = "\n[status]\nlan_page = true\n"
VIA_VPN = netns.INET_IP
DIRECT = netns.GW_WAN_IP
VIA_VPN6 = netns.INET_IP6
DIRECT6 = netns.GW_WAN_IP6
UNITS = ("xgw-net", "xgw-xray", "xgw", "xgw-dhcp")

pytestmark = [
    pytest.mark.skipif(
        not XRAY_BIN or not Path(XRAY_BIN).exists(), reason="нет XGW_XRAY_BIN — стенд пропущен"
    ),
    pytest.mark.skipif(bool(machine_mod.unavailable()), reason=machine_mod.unavailable()),
]


def _snapshot(box: Machine) -> dict[str, str]:
    """Состояние системы, которое установка меняет, а удаление должно вернуть."""
    ruleset = box.sh("nft list ruleset")
    return {
        # Счётчики пакетов в правилах ufw меняются сами по себе.
        "nft": re.sub(r"packets \d+ bytes \d+", "", ruleset),
        "ip rule": box.sh("ip rule show"),
        "ip -6 rule": box.sh("ip -6 rule show"),
        "table 100": box.sh("ip route show table 100 2>/dev/null || true"),
        "table 100 v6": box.sh("ip -6 route show table 100 2>/dev/null || true"),
        "table 101": box.sh("ip route show table 101 2>/dev/null || true"),
        "tun link": box.sh("ip -br link show xgwtun0 2>&1 || true"),
        # Профиль lo NetworkManager создаёт заново при каждой загрузке.
        "profiles": box.sh(
            "nmcli -t -f NAME,UUID,AUTOCONNECT connection show | grep -v '^lo:' | sort"
        ),
        "wan ipv6": box.sh("nmcli -g ipv6.method connection show stand-wan"),
        "sysctl": box.sh(
            "cat /proc/sys/net/ipv4/ip_forward /proc/sys/net/ipv6/conf/all/forwarding"
        ),
        "sleep": box.sh(
            "systemctl is-enabled sleep.target suspend.target hibernate.target "
            "hybrid-sleep.target || true"
        ),
        "units": box.sh("systemctl list-unit-files 'xgw*' --no-legend || true"),
        "user": box.sh("getent passwd xray || true"),
        "ufw": box.sh("ufw status 2>/dev/null || true"),
        "ufw before.rules": box.sh("cat /etc/ufw/before.rules 2>/dev/null || true"),
        "files": box.sh(
            "ls -d /opt/xgw /usr/local/bin/xgw /etc/dnsmasq.d/xgw.conf /etc/xgw/dnsmasq.conf "
            "/etc/sysctl.d/90-xgw.conf "
            f"/var/lib/xgw /etc/xgw/xray /etc/xgw/sing-box {LAUNCHER} "
            "/usr/local/share/applications "
            "2>/dev/null || true"
        ),
    }


@pytest.fixture(scope="module")
def gw():
    """Машина с «заводской» системой и работающим «интернетом»; XGW ещё не установлен."""
    box = Machine()
    box.create()
    stand = Stand(box.share / "stand", Path(XRAY_BIN), mode="netns",
                  _topology=MachineTopology(box),
                  singbox_bin=Path(SINGBOX_BIN) if SINGBOX_BIN else None)
    # Команды шлюза — установленный `xgw` внутри контейнера, файлы — в его корне.
    stand.root = box.root
    stand.xgw = lambda *args, timeout=180: box.run("xgw", *args, check=False, timeout=timeout)
    try:
        stand.start()
        box.boot()
        box.prepare()
        # Перезагрузка — чтобы система была в устоявшемся виде: без профилей,
        # которые NetworkManager создаёт в памяти до появления настоящих.
        box.reboot()
        before = _snapshot(box)
        stand.set_subscription(stand.names)
        stand.write_config(capture=True, panel=True, extra=STATUS_PAGE)
        yield SimpleNamespace(box=box, stand=stand, before=before)
    finally:
        stand.stop()
        box.destroy()


def _xgw(gw, *args: str, timeout: float = 180):
    return gw.stand.xgw(*args, timeout=timeout)


def _state(gw) -> str:
    result = _xgw(gw, "status", "--json")
    if result.returncode != 0:
        return ""
    return json.loads(result.stdout).get("state") or ""


def _exit_ip(gw, *args: str) -> str:
    return gw.stand.exit_ip("lan", *args)


def _active(gw) -> dict[str, str]:
    out = gw.box.run("systemctl", "is-active", *UNITS, check=False).stdout.split()
    return dict(zip(UNITS, out, strict=False))


def _install(gw, *args: str):
    return gw.box.run(
        "sh", str(REPO / "packaging/install.sh"), *args, check=False, timeout=300
    )


def _put_xray(box: Machine) -> None:
    """Xray стенда — в /opt/xgw/xray. Сети в контейнере нет, поэтому он кладётся заранее:
    установка его не скачивает, если версия подходит. Прежний файл сначала удаляется
    (--remove-destination): поверх работающего Xray cp отвечает «Text file busy»."""
    box.sh(f"mkdir -p /opt/xgw/xray && cp --remove-destination {Path(XRAY_BIN).parent}/* "
           "/opt/xgw/xray/")


def _put_singbox(box: Machine) -> None:
    """sing-box — в /opt/xgw/sing-box, по той же причине, что и Xray: сети в контейнере нет."""
    if SINGBOX_BIN:
        box.sh(f"mkdir -p /opt/xgw/sing-box && cp --remove-destination "
               f"{Path(SINGBOX_BIN).parent}/* /opt/xgw/sing-box/")


def _put_config(gw) -> None:
    """Конфиг стенда — на место /etc/xgw/config.toml, Xray и sing-box — на свои места."""
    shutil.copyfile(gw.stand.config_file, gw.box.root / "etc/xgw/config.toml")
    _put_xray(gw.box)
    _put_singbox(gw.box)
    gw.box.sh("chmod 600 /etc/xgw/config.toml")


def _panel(gw, *args: str) -> dict:
    """Запрос к панели с самого шлюза — как из браузера на этой машине."""
    result = gw.box.run(
        "python3", str(HERE / "panel_client.py"), PANEL_PORT, *args, check=False, timeout=60
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def _panel_token(gw) -> str:
    return gw.box.sh("cat /var/lib/xgw/panel-token").strip()


def _panel_state(gw) -> dict:
    return _panel(gw, "state", _panel_token(gw))


def _press(gw, name: str, **body) -> dict:
    return _panel(gw, "act", _panel_token(gw), name, json.dumps(body))


def _core_tags(gw) -> list[str]:
    """Теги серверов, которые сейчас заведены в работающий Xray."""
    servers = gw.stand.xgw_json("servers")
    return [node["tag"] for node in [*servers["members"], *servers["spares"]]]


def test_first_run_creates_the_config_and_changes_nothing_else(gw):
    box = gw.box
    first = _install(gw, "--yes")
    assert first.returncode == 1, first.stdout + first.stderr
    assert "Создан /etc/xgw/config.toml" in first.stdout
    assert box.sh("stat -c '%U:%G %a' /etc/xgw/config.toml").strip() == "root:root 600"
    example = (REPO / "config.example.toml").read_text(encoding="utf-8")
    assert (box.root / "etc/xgw/config.toml").read_text(encoding="utf-8") == example
    # Что делать дальше: команды xgw ещё нет — повторить установку из каталога проекта.
    assert "sudo sh packaging/install.sh" in first.stdout
    after = _snapshot(box)
    assert {key: after[key] for key in after if key != "files"} == {
        key: gw.before[key] for key in gw.before if key != "files"
    }
    # С подпиской-примером, если её раскомментировать, установка не начинается.
    (box.root / "etc/xgw/config.toml").write_text(
        example.replace("# [[subscriptions]]", "[[subscriptions]]").replace(
            '# url = "https://example.com/sub/TOKEN"', 'url = "https://example.com/sub/TOKEN"'),
        encoding="utf-8",
    )
    second = _install(gw, "--yes")
    assert second.returncode == 1 and "подписка-пример" in second.stdout
    assert "Установка не начата" in second.stdout


# --- путь «без терминала»: установка без подписки, дальше всё из панели ---------------


def test_install_without_a_subscription_leaves_the_internet_direct(gw):
    box, stand = gw.box, gw.stand
    stand.write_config(capture=True, panel=True, subscription=False, extra=STATUS_PAGE)
    _put_config(gw)
    result = _install(gw, "--yes")
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout
    if os.environ.get("XGW_MACHINE_PREINSTALL_DNSMASQ") == "1":
        assert box.dnsmasq_preinstalled, "пакет dnsmasq не удалось поставить в контейнер заранее"
    # DHCP раздаёт своя служба xgw-dhcp: нужна только программа из dnsmasq-base (на Ubuntu
    # Desktop она уже стоит), пакет dnsmasq со штатной службой не нужен вовсе.
    assert "пакеты: dnsmasq" not in out
    assert box.run("dnsmasq", "--test", "--conf-file=/etc/xgw/dnsmasq.conf",
                   check=False).returncode == 0
    assert not (box.root / "etc/dnsmasq.d/xgw.conf").exists()
    assert "dnsmasq" in box.sh("ss -lunpH 'sport = :67'")
    lease = stand.lan("dhcp", "eth0")
    assert "error" not in lease, f"{lease}\n{box.journal('xgw-dhcp', 20)}"
    assert lease["router"] == netns.GW_LAN_IP
    # Аренда — в своём файле, его читает панель.
    assert wait_for(lambda: lease["ip"] in box.sh("cat /var/lib/xgw/dhcp.leases"), 10)
    if box.dnsmasq_preinstalled:
        # Штатную службу пакета dnsmasq XGW не трогает: она осталась выключенной.
        assert box.run("systemctl", "is-enabled", "dnsmasq.service",
                       check=False).stdout.strip() != "enabled"
    assert "подписок пока нет: VPN не включится" in out  # сказано ещё в плане
    assert "XGW установлен. Подписок пока нет — VPN выключен" in out
    token = _panel_token(gw)
    assert len(token) >= 24
    assert f"Панель управления: http://127.0.0.1:{PANEL_PORT}/?token={token}" in out
    assert box.sh("stat -c '%U:%G %a' /var/lib/xgw/panel-token").strip() == "root:root 600"

    # Xray запускать не с чем; остальное работает, шлюз — обычный роутер.
    active = _active(gw)
    assert active["xgw-xray"] != "active"
    assert [active[unit] for unit in ("xgw-net", "xgw", "xgw-dhcp")] == ["active"] * 3
    assert wait_for(lambda: _exit_ip(gw) == DIRECT, 20), "устройство осталось без интернета"
    assert stand.exit_ip("gw") == DIRECT
    table = box.sh("nft list table ip xgw")
    assert "tproxy" not in table and "masquerade" in table

    # Ярлык в меню приложений: открывает панель, токена в нём нет.
    entry = box.sh(f"cat {LAUNCHER}")
    assert f"Exec=xdg-open http://127.0.0.1:{PANEL_PORT}/" in entry and token not in entry
    assert "Icon=/opt/xgw/lib/xgw/ui/icon.svg" in entry
    assert box.sh("test -f /opt/xgw/lib/xgw/ui/icon.svg && echo есть").strip() == "есть"
    check = box.sh(
        f"command -v desktop-file-validate >/dev/null && desktop-file-validate {LAUNCHER}; true"
    )
    assert check.strip() == "", check
    printed = _xgw(gw, "panel")
    assert printed.returncode == 0 and f"?token={token}" in printed.stdout


def test_panel_is_reachable_only_from_the_machine_itself_and_by_token(gw):
    box, stand = gw.box, gw.stand

    def sockets() -> str:
        return box.sh(f"ss -ltnH 'sport = :{PANEL_PORT}'")

    # Установка заканчивается перезапуском демона, а порт панели он открывает чуть
    # позже — на медленной машине между этими событиями проходят секунды.
    assert wait_for(lambda: f"127.0.0.1:{PANEL_PORT}" in sockets(), 10, step=0.3), (
        sockets(), box.journal("xgw", 40))
    listening = sockets()
    for elsewhere in ("0.0.0.0", "*", netns.GW_LAN_IP, netns.GW_WAN_IP):
        assert f"{elsewhere}:{PANEL_PORT}" not in listening, listening
    for address in (netns.GW_LAN_IP, netns.GW_WAN_IP):
        where = "lan" if address == netns.GW_LAN_IP else "inet"
        reply = stand.client(where, "get", f"http://{address}:{PANEL_PORT}/", "--timeout", "3")
        assert "error" in reply and reply.get("status", 0) != 200, reply

    assert wait_for(lambda: _panel(gw, "raw", "/").get("status") == 200, 30), box.journal("xgw")
    assert 'name="token"' in _panel(gw, "raw", "/")["body"]  # без токена — только вход
    assert _panel(gw, "raw", "/api/state")["status"] == 401
    assert "error" in _panel(gw, "state", "не-тот-токен")

    state = _panel_state(gw)
    assert state["subscriptions"] == [] and state["servers"] == [] and state["members"] == []
    assert state["capture"]["mode"] == "off" and state["lan"]["interface"] == "lan0"
    assert state["power"]["can_on"] is False and "добавьте подписку" in state["power"]["why"]
    refused = _press(gw, "power", on=True)
    assert not refused["ok"] and "Xray не отвечает" in refused["text"]
    assert _exit_ip(gw) == DIRECT


def test_sign_in_again_opens_a_one_time_link_in_the_users_browser(gw):
    """«Войти заново» у ярлыка «XGW»: pkexec запускает `xgw panel --login` от root, а
    браузер открывается у человека — xdg-open в его пользовательском менеджере systemd,
    по одноразовой ссылке. Окна пароля и браузера в контейнере нет: pkexec изображает
    PKEXEC_UID, браузер — заглушка xdg-open, сеанс GNOME — переменная WAYLAND_DISPLAY.
    Менеджер пользователя запускается напрямую (`systemctl start user@UID`), как это
    делает logind при входе: `loginctl enable-linger` в контейнере отвечает «Protocol
    driver not attached»."""
    box = gw.box
    box.sh(
        r"""
set -e
id walker >/dev/null 2>&1 || useradd --create-home walker
systemctl start "user@$(id -u walker).service"
cat > /usr/local/bin/xdg-open <<'EOF'
#!/bin/sh
echo "user=$(id -un) url=$1" >> "$HOME/xdg-open.log"
EOF
chmod 755 /usr/local/bin/xdg-open
"""
    )
    try:
        uid = box.sh("id -u walker").strip()

        def manager() -> bool:
            state = box.run("systemctl", "is-active", f"user@{uid}.service", check=False)
            return state.stdout.strip() == "active"

        assert wait_for(manager, 30), box.journal(f"user@{uid}.service")

        def login():
            return box.run("env", f"PKEXEC_UID={uid}", "xgw", "panel", "--login", check=False)

        # Человек вошёл только по SSH: графического сеанса нет — честный отказ.
        refused = login()
        assert refused.returncode == 1 and "нет графического сеанса" in refused.stderr, refused
        box.run("systemctl", "--user", "--machine=walker@", "set-environment",
                "WAYLAND_DISPLAY=wayland-0")
        opened = login()
        assert opened.returncode == 0 and "вход выполнен" in opened.stdout, opened

        def logged() -> str:
            return box.sh("cat /home/walker/xdg-open.log 2>/dev/null", check=False).strip()

        assert wait_for(logged, 20), box.sh("journalctl -n 30 --no-pager", check=False)
        line = logged().splitlines()[-1]
        prefix = f"user=walker url=http://127.0.0.1:{PANEL_PORT}/?login="
        assert line.startswith(prefix) and _panel_token(gw) not in line, line
        code = line[len(prefix):]
        first = _panel(gw, "raw", f"/?login={code}")
        assert first["status"] == 303, first
        assert _panel(gw, "raw", f"/?login={code}")["status"] == 403  # второй раз не годится
        assert box.sh("stat -c '%U %a' /run/xgw/panel-login").strip() == "root 700"
    finally:
        box.sh(
            'systemctl stop "user@$(id -u walker).service"; rm -f /usr/local/bin/xdg-open; '
            "userdel -r walker 2>/dev/null; true"
        )


def test_subscription_added_in_the_panel_starts_xray_and_the_button_turns_vpn_on(gw):
    box, stand = gw.box, gw.stand
    added = _press(gw, "add", text=stand.subscription_url())
    assert added["ok"] and "получаю серверы" in added["text"], added

    def ready() -> bool:
        state = _panel_state(gw)
        return len(state.get("members") or []) == 2 and state.get("state") == "HEALTHY"

    # Демон сам заметил новую подписку, получил серверы и запустил Xray.
    assert wait_for(ready, 90), box.journal("xgw", 60)
    assert _active(gw)["xgw-xray"] == "active"
    assert box.sh("ps -o user= -C xray").split() == ["xray"]
    rights = box.sh("stat -c '%U:%G %a' /etc/xgw/panel.json /etc/xgw/xray/config.json")
    assert rights.splitlines() == ["root:root 600", "root:xray 640"]

    state = _panel_state(gw)
    (sub,) = state["subscriptions"]
    assert sub["managed"] and sub["host"] == netns.INET_IP and sub["secure"] is False
    assert sub["servers"] == 3 and sub["error"] == "" and sub["fetched"]
    assert sub["quota"]["total"] == 100_000_000_000  # квота из заголовка ответа
    text = json.dumps(state, ensure_ascii=False)
    assert "s3cr3t-stand-token" not in text and UUID not in text
    assert sorted(server["status"] for server in state["servers"]) == ["member", "member", "spare"]
    assert all(len(server["fingerprint"]) == 8 for server in state["servers"])
    assert "s3cr3t-stand-token" not in box.journal("xgw", 300)

    # Подписка есть, но VPN включает человек: до нажатия интернет прямой.
    assert _exit_ip(gw) == DIRECT and state["power"]["can_on"] is True
    pressed = _press(gw, "power", on=True)
    assert pressed["ok"] and "перехват включён" in pressed["text"], pressed
    assert wait_for(lambda: _exit_ip(gw) == VIA_VPN, 10, step=0.2), "VPN не включился"
    assert stand.exit_ip("gw") == VIA_VPN
    assert "tproxy to 127.0.0.1:12345" in box.sh("nft list table ip xgw")
    state = _panel_state(gw)
    assert state["capture"]["mode"] == "on" and state["power"]["can_off"] is True
    assert sum(1 for server in state["servers"] if server.get("selected")) == 1

    assert _press(gw, "power", on=False)["ok"]
    assert wait_for(lambda: _exit_ip(gw) == DIRECT, 5, step=0.2)
    assert _press(gw, "power", on=True)["ok"]
    assert wait_for(lambda: _exit_ip(gw) == VIA_VPN, 10, step=0.2)


def test_servers_are_switched_off_and_removed_from_the_panel(gw):
    box = gw.box
    servers = _panel_state(gw)["servers"]
    spare = next(server for server in servers if server["status"] == "spare")
    member = next(server for server in servers if server["status"] == "member")
    last = next(s for s in servers if s["status"] == "member" and s is not member)
    xray_pid = box.sh("pgrep -x xray").strip()

    def row(fingerprint: str) -> dict:
        return next(
            (s for s in _panel_state(gw)["servers"] if s["fingerprint"] == fingerprint), {})

    # Убрать запасной: шлюз перестаёт его проверять, обновление подписки его не возвращает.
    removed = _press(gw, "servers", fingerprints=[spare["fingerprint"]], mode="removed")
    assert removed["ok"], removed
    assert wait_for(lambda: spare["tag"] not in _core_tags(gw), 40), box.journal("xgw")
    state = _panel_state(gw)
    assert [server["fingerprint"] for server in state["removed"]] == [spare["fingerprint"]]
    assert spare["fingerprint"] not in [server["fingerprint"] for server in state["servers"]]
    assert _press(gw, "refresh")["ok"]
    assert wait_for(lambda: not _panel_state(gw)["busy"]["refresh"], 40)
    time.sleep(3)
    assert spare["tag"] not in _core_tags(gw)

    # Отключить участника: из ядра он уходит, в списке остаётся — отключённым.
    assert _press(gw, "servers", fingerprints=[member["fingerprint"]], mode="disabled")["ok"]
    assert wait_for(lambda: _core_tags(gw) == [last["tag"]], 40), box.journal("xgw")
    assert wait_for(lambda: row(member["fingerprint"]).get("pending") is False, 20)
    assert row(member["fingerprint"])["status"] == "disabled"
    config_text = (box.root / "etc/xgw/xray/config.json").read_text(encoding="utf-8")
    assert member["tag"] not in config_text and spare["tag"] not in config_text
    # Через API, без перезапуска Xray и без нового запроса подписки; трафик идёт.
    assert box.sh("pgrep -x xray").strip() == xray_pid
    events = [event["detail"] for event in _panel_state(gw)["events"]]
    assert any("изменение настроек: применено через API" in text for text in events), events
    assert _exit_ip(gw) == VIA_VPN

    # Последний включённый сервер отключить нельзя.
    refused = _press(gw, "servers", fingerprints=[last["fingerprint"]], mode="disabled")
    assert not refused["ok"] and "ни одного включённого сервера" in refused["text"]
    assert _core_tags(gw) == [last["tag"]]

    # Вернуть оба: снова два участника и запасной.
    both = [member["fingerprint"], spare["fingerprint"]]
    assert _press(gw, "servers", fingerprints=both, mode="enabled")["ok"]
    assert wait_for(lambda: len(_core_tags(gw)) == 3, 40), box.journal("xgw")
    state = _panel_state(gw)
    assert state["removed"] == []
    assert sorted(server["status"] for server in state["servers"]) == ["member", "member", "spare"]
    assert box.sh("pgrep -x xray").strip() == xray_pid
    assert wait_for(lambda: _state(gw) == "HEALTHY", 60), _xgw(gw, "status").stdout
    assert _exit_ip(gw) == VIA_VPN


def test_device_is_taken_around_the_vpn_and_back_from_the_panel(gw):
    """Переключатель устройства в панели: аренда DHCP закрепляется, адрес попадает в
    набор bypass4, устройство выходит напрямую, остальные — через VPN; демон не
    теряет это при перезагрузке правил."""
    box, stand = gw.box, gw.stand
    mac = "02:00:00:00:00:51"
    lease = stand.lan("dhcp", "eth0", "--mac", mac)
    assert "error" not in lease, f"{lease}\n{box.journal('xgw-dhcp', 20)}"
    ip = lease["ip"]
    stand.run_in("lan", "ip", "addr", "add", f"{ip}/24", "dev", "eth0")  # адрес «получен»
    try:
        assert wait_for(lambda: mac in [d["mac"] for d in _panel_state(gw)["devices"]], 20)
        assert stand.exit_ip("lan", "--bind", ip) == VIA_VPN

        pressed = _press(gw, "device", mac=mac, bypass=True)
        assert pressed["ok"] and "идёт мимо VPN" in pressed["text"], pressed
        assert ip in box.sh("nft list set ip xgw bypass4")
        assert f"dhcp-host={mac},{ip}" in box.sh("cat /etc/xgw/dnsmasq.conf")
        assert box.sh("stat -c '%U:%G %a' /etc/xgw/panel.json").strip() == "root:root 600"
        assert wait_for(lambda: stand.exit_ip("lan", "--bind", ip) == DIRECT, 10, step=0.3)
        assert _exit_ip(gw) == VIA_VPN  # остальные устройства — через VPN
        (device,) = [d for d in _panel_state(gw)["devices"] if d["mac"] == mac]
        assert device["bypass"] is True and device["managed"] is True

        # Правила пропали (чужой сбой) — демон загружает их заново, уже с этим устройством.
        box.sh("nft delete table ip xgw")
        assert wait_for(lambda: _exit_ip(gw) == VIA_VPN, 30, step=1), box.journal("xgw", 40)
        assert stand.exit_ip("lan", "--bind", ip) == DIRECT

        back = _press(gw, "device", mac=mac, bypass=False)
        assert back["ok"] and "снова идёт через VPN" in back["text"], back
        assert ip not in box.sh("nft list set ip xgw bypass4")
        assert mac not in box.sh("cat /etc/xgw/dnsmasq.conf")
        assert wait_for(lambda: stand.exit_ip("lan", "--bind", ip) == VIA_VPN, 10, step=0.3)
        assert json.loads(box.sh("cat /etc/xgw/panel.json"))["devices"] == []
    finally:
        stand.run_in("lan", "ip", "addr", "del", f"{ip}/24", "dev", "eth0")


def test_telegram_bot_is_paired_from_the_panel_and_obeys_commands(gw):
    """Бот в службе с урезанными правами: токен вставлен в панели, чат подключён кодом,
    команды выполняются, чужие и старые сообщения — нет. «Telegram» — процесс стенда."""
    box, stand = gw.box, gw.stand
    api = stand.start_telegram()
    config_file = box.root / "etc/xgw/config.toml"
    config_file.write_text(
        config_file.read_text(encoding="utf-8") + f'\n[notify]\ntelegram_api = "{api}"\n',
        encoding="utf-8")

    def say(text: str, **query) -> None:
        params = "&".join(f"{k}={quote(str(v))}" for k, v in {"text": text, **query}.items())
        stand.telegram(f"/_say?{params}")

    def replies() -> list[str]:
        # Ответы на команды; уведомления тоже идут в чат, их заголовок — «XGW: …».
        texts = [item["text"] for item in stand.telegram("/_sent")]
        return [text for text in texts if not text.startswith("XGW: ")]

    def shown() -> str:
        return "\n---\n".join(replies())

    def bot() -> dict:
        return _panel_state(gw)["telegram"]

    def vpn_is(expected: str) -> bool:
        return wait_for(lambda: _exit_ip(gw) == expected, 15, step=0.3) is True

    assert bot()["mode"] == "off"
    refused = _press(gw, "telegram/connect", token="не токен")
    assert not refused["ok"] and "токен бота" in refused["text"]

    connected = _press(gw, "telegram/connect", token=TELEGRAM_TOKEN)
    assert connected["ok"], connected
    assert wait_for(lambda: bot()["mode"] == "pairing" and bot()["username"], 40), (
        bot(), box.journal("xgw", 40))
    assert box.sh("stat -c '%U:%G %a' /etc/xgw/panel.json").strip() == "root:root 600"
    state = bot()
    assert TELEGRAM_TOKEN not in json.dumps(state) and state["username"] == "xgw_test_bot"
    code = state["code"]
    assert len(code) == 6

    # Без кода и с чужим кодом чат не подключается; с верным — подключается.
    say("/start")
    say("/start 000000" if code != "000000" else "/start 111111")
    assert wait_for(lambda: len(replies()) == 2, 20), shown()
    assert "Отправьте /start и шесть цифр" in replies()[0] and "Неверный код" in replies()[1]
    say(f"/start {code}")
    assert wait_for(lambda: any(r.startswith("Готово") for r in replies()), 20), shown()
    assert wait_for(lambda: bot()["mode"] == "connected", 30), bot()
    saved = json.loads(box.sh("cat /etc/xgw/panel.json"))["telegram"]
    assert saved == {"token": TELEGRAM_TOKEN, "chat_id": "1001"}

    # Команды из своего чата.
    say("/status")
    assert wait_for(lambda: any("Состояние:" in r for r in replies()), 20), (
        shown(), box.journal("xgw", 80))
    assert "Состояние: HEALTHY" in shown(), shown()
    assert vpn_is(VIA_VPN)
    sent = len(replies())
    say("/disable")
    assert vpn_is(DIRECT), box.journal("xgw", 40)
    assert wait_for(lambda: any("перехват снят" in r for r in replies()), 20), replies()
    say("/enable")
    assert vpn_is(VIA_VPN), box.journal("xgw", 40)
    assert wait_for(lambda: any("перехват включён" in r for r in replies()), 20), replies()

    # Чужой чат и давняя команда: ни ответа, ни действия.
    sent = len(replies())
    say("/disable", chat=424242)
    say("/disable", age=600)
    say("/status")  # свежая команда выстроена после них и ответит — значит, предыдущие разобраны
    assert wait_for(lambda: len(replies()) == sent + 1, 20), replies()
    assert "Состояние: HEALTHY" in replies()[-1]
    assert _exit_ip(gw) == VIA_VPN

    # Закрепление по номеру из /servers, через настоящее API Xray.
    say("/servers")
    assert wait_for(lambda: any("1. " in r for r in replies()), 20), replies()
    say("/pin 1 10m")
    assert wait_for(lambda: any("выбран вручную на 10m" in r for r in replies()), 20), replies()
    assert _panel_state(gw)["pin"] is not None
    say("/unpin")
    assert wait_for(lambda: _panel_state(gw)["pin"] is None, 20)
    events = [event["detail"] for event in _panel_state(gw)["events"]]
    assert any("Telegram: команда /disable" in text for text in events), events
    assert TELEGRAM_TOKEN not in box.journal("xgw", 400)

    # Отключение в панели: токен забыт, бот молчит.
    assert _press(gw, "telegram/disconnect")["ok"]
    assert wait_for(lambda: bot()["mode"] == "off", 30), bot()
    assert json.loads(box.sh("cat /etc/xgw/panel.json"))["telegram"] == {"token": "", "chat_id": ""}
    sent = len(replies())
    say("/disable")
    time.sleep(5)
    assert len(replies()) == sent and _exit_ip(gw) == VIA_VPN


def test_uninstall_after_the_panel_keeps_only_the_users_settings(gw):
    box = gw.box
    result = _xgw(gw, "uninstall", "--yes", timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ярлык панели удалён" in result.stdout and "panel.json" in result.stdout
    after = _snapshot(box)
    for key, value in gw.before.items():
        assert after[key] == value, f"{key}:\n--- было\n{value}\n--- стало\n{after[key]}"
    # Остаются только настройки пользователя: конфиг и подписки, добавленные в панели.
    assert sorted(path.name for path in (box.root / "etc/xgw").iterdir()) == [
        "config.toml", "panel.json"]
    assert _exit_ip(gw) == ""  # шлюза больше нет

    # Дальше — обычный путь: подписка вписана в config.toml.
    (box.root / "etc/xgw/panel.json").unlink()
    gw.stand.write_config(capture=True, panel=True, extra=STATUS_PAGE)
    _put_config(gw)


def test_diag_before_install_has_no_failures(gw):
    result = gw.box.run(
        "env", f"PYTHONPATH={REPO / 'src'}", "python3", "-P", "-m", "xgw", "diag", check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FAIL — 0" in result.stdout
    assert "ядро принимает правила TPROXY" in result.stdout
    # ufw включён, правил для LAN ещё нет — diag должен это видеть.
    assert "ufw: включён и запрещает входящие" in result.stdout
    assert "профиль xgw-lan создаст установка" in result.stdout


def test_install(gw):
    box = gw.box
    result = _install(gw, "--yes")
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout
    assert "План установки XGW" in out and "XGW установлен." in out
    assert "ufw: ufw allow in on lan0" in out
    assert f"Панель управления: http://127.0.0.1:{PANEL_PORT}/?token={_panel_token(gw)}" in out
    assert box.sh(f"stat -c '%U:%G %a' {LAUNCHER}").strip() == "root:root 644"

    assert _active(gw) == dict.fromkeys(UNITS, "active")
    # Xray — от пользователя xray и только с двумя возможностями.
    assert box.sh("ps -o user= -C xray").split() == ["xray"]
    caps = box.sh("grep CapEff /proc/$(pgrep -x xray)/status").split()[1]
    assert int(caps, 16) == (1 << 12) | (1 << 10)  # CAP_NET_ADMIN, CAP_NET_BIND_SERVICE
    rights = box.sh(
        "stat -c '%U:%G %a' /etc/xgw/config.toml /etc/xgw/xray /etc/xgw/xray/config.json "
        "/var/lib/xgw /usr/local/bin/xgw"
    ).splitlines()
    assert rights == ["root:root 600", "root:xray 2750", "root:xray 640", "root:root 700",
                      "root:root 755"]
    assert not box.sh("find /opt/xgw -perm /022 ! -type l")  # ничего, куда пишут не root

    # Сеть: профиль LAN, прежние профили отключены, IPv6 на WAN выключен.
    devices = box.sh("nmcli -t -f DEVICE,STATE,CONNECTION device")
    assert "lan0:connected:xgw-lan" in devices and "wan0:connected:stand-wan" in devices
    assert f"{netns.GW_LAN_IP}/24" in box.sh("ip -br addr show lan0")
    profiles = box.sh("nmcli -t -f NAME,AUTOCONNECT connection show")
    assert "old-lan:no" in profiles and "xgw-lan:yes" in profiles and "stand-wan:yes" in profiles
    assert box.sh("nmcli -g ipv6.method connection show stand-wan").strip() == "disabled"
    assert box.sh("nmcli -g ipv4.never-default connection show xgw-lan").strip() == "yes"
    # Файл профиля находит та же функция, что убирает XGW хоста из корня стенда: и без
    # журнала, по имени в файле (keyfile или файл netplan — смотря по NetworkManager).
    assert machine_mod.xgw_profile_files(box.root), box.sh(
        "ls /etc/netplan /etc/NetworkManager/system-connections"
    )
    assert "default" not in box.sh("ip route show dev lan0")
    assert box.sh("cat /proc/sys/net/ipv4/ip_forward").strip() == "1"
    assert box.sh("systemctl is-enabled sleep.target suspend.target || true").split() == [
        "masked", "masked"
    ]
    table = box.sh("nft list table ip xgw")
    assert "tproxy to 127.0.0.1:12345" in table and "masquerade" in table
    assert "fwmark 0x1 lookup 100" in box.sh("ip rule show")
    ufw = box.sh("ufw status")
    assert "on lan0" in ufw and "ALLOW FWD" in ufw
    # Без этой строки ufw отбрасывал бы перехваченные пакеты устройств (ufw-not-local).
    assert "-A ufw-before-input -i lan0 -m mark --mark 0x1 -j ACCEPT" in box.sh(
        "cat /etc/ufw/before.rules"
    )

    assert wait_for(lambda: _state(gw) == "HEALTHY", 60), _xgw(gw, "status").stdout


def test_second_install_changes_nothing_and_keeps_the_original_state(gw):
    box = gw.box
    journal = box.root / "var/lib/xgw/backup/install.json"
    first = json.loads(journal.read_text(encoding="utf-8"))
    xray_pid = box.sh("pgrep -x xray").strip()
    result = _install(gw, "--yes")
    assert result.returncode == 0, result.stdout + result.stderr
    second = json.loads(journal.read_text(encoding="utf-8"))
    # Пакетов установка могла не ставить вовсе (dnsmasq-base уже был) — тогда записи о
    # них нет ни в одном журнале.
    for key in ("sysctl", "nm_lan", "nm_wan", "packages", "user_created", "sleep"):
        assert second.get(key) == first.get(key), key
    assert [item["autoconnect"] for item in second["nm_lan"]["disabled"]] == ["yes"]
    assert box.sh("pgrep -x xray").strip() == xray_pid  # Xray не перезапускался
    assert box.sh("nmcli -t -f NAME connection show").count("xgw-lan") == 1
    assert box.sh("cat /etc/ufw/before.rules").count("-i lan0 -m mark --mark 0x1") == 1
    assert box.sh("ufw status").count("ALLOW FWD") == 2  # IPv4 и IPv6, без дублей
    assert wait_for(lambda: _state(gw) == "HEALTHY", 60), _xgw(gw, "status").stdout


def test_lan_device_works_through_the_installed_gateway(gw):
    stand = gw.stand
    assert _exit_ip(gw) == VIA_VPN
    assert stand.exit_ip("gw") == VIA_VPN  # и сама машина
    assert _exit_ip(gw, "--bind", netns.LAN_BYPASS_IP) == DIRECT  # устройство в обход
    reply = stand.lan("dns", "8.8.8.8", "example.com")
    assert reply["answers"] == [netns.INET_IP] and reply["from"] == "8.8.8.8"

    # Адреса раздаёт служба xgw-dhcp: из диапазона и по статической аренде.
    lease = stand.lan("dhcp", "eth0")
    assert lease["router"] == lease["dns"] == netns.GW_LAN_IP
    assert 110 <= int(lease["ip"].rsplit(".", 1)[1]) <= 150
    assert stand.lan("dhcp", "eth0", "--mac", netns.LAN_BYPASS_MAC)["ip"] == netns.LAN_BYPASS_IP


@pytest.mark.skipif(not SINGBOX_BIN, reason="нет XGW_SINGBOX_BIN — проверка sing-box пропущена")
def test_singbox_runs_under_systemd_as_the_service_user(gw):
    """Второе ядро (0.1.12) на настоящем systemd: служба xgw-singbox от пользователя xray с
    двумя возможностями, конфиг читается группой xray, перечитывание (systemctl reload) не
    перезапускает процесс, `xgw diag` видит ядро, ошибок в журнале службы нет."""
    box = gw.box
    assert box.run("systemctl", "is-active", "xgw-singbox", check=False).stdout.strip() == "active"
    assert box.sh("ps -o user= -C sing-box").split() == ["xray"]
    caps = box.sh("grep CapEff /proc/$(pgrep -x sing-box)/status").split()[1]
    assert int(caps, 16) == (1 << 12) | (1 << 10)  # CAP_NET_ADMIN, CAP_NET_BIND_SERVICE
    rights = box.sh("stat -c '%U:%G %a' /etc/xgw/sing-box /etc/xgw/sing-box/config.json")
    assert rights.splitlines() == ["root:xray 2750", "root:xray 640"]
    assert box.sh("stat -c '%U:%G %a' /var/lib/xgw/sing-box.last-good.json 2>/dev/null || true"
                  ).strip() in ("", "root:root 640", "root:root 600")
    config = json.loads((box.root / "etc/xgw/sing-box/config.json").read_text(encoding="utf-8"))
    assert config["inbounds"] and "secret" in json.dumps(config)
    assert _active(gw)["xgw-xray"] == "active"  # Xray и sing-box работают рядом

    pid = box.sh("pgrep -x sing-box").strip()
    reload = box.run("systemctl", "reload", "xgw-singbox", check=False)
    assert reload.returncode == 0, reload.stdout + reload.stderr
    time.sleep(1.5)
    assert box.sh("pgrep -x sing-box").strip() == pid  # перечитан, а не перезапущен
    assert _exit_ip(gw) == VIA_VPN  # и интернет через шлюз работает

    result = _xgw(gw, "diag")
    assert "sing-box: версия 1.14.3" in result.stdout, result.stdout
    assert "sing-box: конфиг: принят sing-box check" in result.stdout, result.stdout
    errors = box.sh("journalctl -u xgw-singbox -p err --no-pager -o cat | head -5 || true")
    assert errors.strip() == "", errors
    servers = _xgw(gw, "servers").stdout
    assert "[xray]" in servers, servers
    assert box.sh("journalctl -u xgw -n 300 --no-pager -o cat").count("Traceback") == 0


def test_disable_gives_direct_internet_and_enable_returns_vpn(gw):
    started = time.monotonic()
    assert _xgw(gw, "disable").returncode == 0
    assert wait_for(lambda: _exit_ip(gw) == DIRECT, 5, step=0.2), "прямой интернет не появился"
    assert time.monotonic() - started < 5.0
    assert _xgw(gw, "enable").returncode == 0
    assert wait_for(lambda: _exit_ip(gw) == VIA_VPN, 5, step=0.2)


def test_status_page_is_read_only_and_needs_the_token(gw):
    stand, box = gw.stand, gw.box
    url = f"http://{netns.GW_LAN_IP}:8780"
    token = box.sh("cat /var/lib/xgw/status-token").strip()
    assert len(token) >= 20
    assert stand.lan("get", f"{url}/")["status"] == 403
    assert stand.lan("get", f"{url}/?token=wrong")["status"] == 403
    entered = stand.lan("get", f"{url}/?token={token}")
    assert entered["status"] == 303 and entered["location"] == "/"
    assert "HttpOnly" in entered["set-cookie"] and token not in entered["set-cookie"]
    cookie = entered["set-cookie"].split(";")[0]
    page = stand.lan("get", f"{url}/", "--header", f"Cookie: {cookie}", "--body")
    assert page["status"] == 200
    for text in ("HEALTHY", "proxy-", "Устройства (аренды DHCP)", netns.LAN_BYPASS_IP,
                 "мимо VPN"):
        assert text in page["body"], text
    assert UUID not in page["body"]
    # Слушает только адрес шлюза в LAN: со стороны провайдера страницы нет.
    listening = box.sh("ss -ltnH 'sport = :8780'")
    assert f"{netns.GW_LAN_IP}:8780" in listening and "0.0.0.0:8780" not in listening
    outside = stand.client("inet", "get", f"http://{netns.GW_WAN_IP}:8780/?token={token}",
                           "--timeout", "3")
    assert outside.get("status", 0) != 200 and "error" in outside


def test_config_change_is_picked_up_without_restarting_the_daemon(gw):
    stand, box = gw.stand, gw.box
    pid = box.sh("systemctl show xgw -p MainPID --value").strip()
    stand.write_config(capture=True, max_members=3, panel=True, extra=STATUS_PAGE)
    text = stand.config_file.read_text(encoding="utf-8").replace(
        "192.168.50.150", "192.168.50.160"
    )
    (box.root / "etc/xgw/config.toml").write_text(text, encoding="utf-8")

    def three_members() -> bool:
        return len(stand.xgw_json("servers")["members"]) == 3

    # Демон сам замечает правку и применяет её через API: Xray не перезапускается.
    xray_pid = box.sh("pgrep -x xray").strip()
    assert wait_for(three_members, 40), box.journal("xgw")
    assert box.sh("systemctl show xgw -p MainPID --value").strip() == pid
    assert box.sh("pgrep -x xray").strip() == xray_pid
    assert "настройки перечитаны" in box.journal("xgw", 200)
    # Конфиг, записанный демоном, по-прежнему читается пользователем xray.
    assert box.sh("stat -c '%U:%G %a' /etc/xgw/xray/config.json").strip() == "root:xray 640"
    # `xgw apply` доводит до конфига и DHCP: диапазон адресов изменился.
    applied = _xgw(gw, "apply")
    assert applied.returncode == 0, applied.stderr
    assert "dnsmasq: настройки DHCP обновлены" in applied.stdout
    assert "192.168.50.160" in box.sh("cat /etc/xgw/dnsmasq.conf")
    assert _active(gw)["xgw-dhcp"] == "active"


def test_desktop_notification_is_sent_from_the_sandboxed_daemon(gw):
    """Xray остановлен → демон (служба с урезанными правами) зовёт notify-send от
    имени пользователя графической сессии и сам запускает Xray снова."""
    box = gw.box
    box.sh(
        r"""
set -e
id tester >/dev/null 2>&1 || useradd --create-home tester
uid=$(id -u tester)
mkdir -p /run/user/$uid && touch /run/user/$uid/bus && chown tester /run/user/$uid
# Настоящей графической сессии в контейнере нет: её изображает loginctl-заглушка.
cat > /usr/local/bin/loginctl <<EOF
#!/bin/sh
case "\$1" in
  list-sessions) echo '[{"session":"7","uid":$uid,"user":"tester","class":"user"}]' ;;
  show-session) printf 'Type=wayland\nActive=yes\nRemote=no\n' ;;
esac
EOF
# Заглушка notify-send пишет в журнал: у службы с ProtectSystem=strict файловая
# система доступна только на чтение, а сокеты (журнал, шина D-Bus) работают.
cat > /usr/local/bin/notify-send <<'EOF'
#!/bin/sh
logger -t xgw-notify-stub -- "user=$(id -un) bus=$DBUS_SESSION_BUS_ADDRESS args=$*"
EOF
chmod 755 /usr/local/bin/loginctl /usr/local/bin/notify-send
"""
    )
    try:
        box.run("systemctl", "stop", "xgw-xray")

        def shown() -> str:
            return box.sh("journalctl -t xgw-notify-stub -o cat --no-pager", check=False).strip()

        assert wait_for(shown, 30), box.journal("xgw")
        uid = box.sh("id -u tester").strip()
        text = shown()
        assert f"user=tester bus=unix:path=/run/user/{uid}/bus" in text
        assert "--urgency=critical XGW: Xray не отвечает" in text
        # Уведомление — запись уровня warning: `journalctl -p warning` её находит.
        warnings = box.sh("journalctl -u xgw -p warning -o cat --no-pager", check=False)
        assert "Xray не отвечает" in warnings, box.sh(
            "journalctl -u xgw -n 40 -o json --no-pager", check=False
        )
        # Та же проверка — строкой «Журнал» в xgw diag (D1 отчёта 0.1.10).
        assert "OK    Журнал: предупреждения демона — с уровнем warning" in _xgw(gw, "diag").stdout
        # Демон поднял Xray сам, шлюз снова в строю.
        assert wait_for(lambda: _state(gw) == "HEALTHY", 60), _xgw(gw, "status").stdout
        assert wait_for(lambda: _exit_ip(gw) == VIA_VPN, 20)
    finally:
        box.sh("rm -f /usr/local/bin/loginctl /usr/local/bin/notify-send")


def test_diag_after_install_and_log_export_without_secrets(gw):
    box = gw.box
    result = _xgw(gw, "diag")
    assert result.returncode == 0, result.stdout
    services = ("xgw-net, xgw-xray, xgw-singbox, xgw, xgw-dhcp работают" if SINGBOX_BIN
                else "xgw-net, xgw-xray, xgw, xgw-dhcp работают")
    for text in (services,
                 "Перехват: включён, правила загружены",
                 "ufw: включён, правила для lan0 есть", "профиль xgw-lan активен",
                 "цели сна замаскированы", "через Xray: 65536 Б"):
        assert text in result.stdout, text

    exported = _xgw(gw, "logs", "--export", "--out", "/var/local/xgw-logs.tar.gz")
    assert exported.returncode == 0, exported.stderr
    data = (box.root / "var/local/xgw-logs.tar.gz").read_bytes()
    members: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive.getmembers():
            members[member.name] = archive.extractfile(member).read().decode("utf-8")
    token = box.sh("cat /var/lib/xgw/status-token").strip()
    for name, text in members.items():
        assert UUID not in text, name
        assert token not in text, name
    assert "xgw.daemon" in members["xgw-logs/journal.txt"]
    assert "****6661" in members["xgw-logs/xray-config.json"]
    assert "table ip xgw" in members["xgw-logs/network.txt"]
    assert "Итог: OK" in members["xgw-logs/diag.txt"]
    if SINGBOX_BIN:
        # Конфиг второго ядра в архиве есть, но пароли, ключи и секрет Clash API скрыты.
        singbox = members["xgw-logs/singbox-config.json"]
        assert '"secret": "***"' in singbox and "password" in singbox
        assert '"password": "***"' in singbox
        assert not re.search(r'"password": "[^*]', singbox)
        assert UUID not in singbox


def test_everything_comes_up_after_reboot_rules_before_network(gw):
    """Перезагрузка. Заодно — живая машина 14.10: пакет ubuntu-fan (ставится вместе с
    docker.io) кладёт в /etc/dnsmasq.d строку bind-interfaces, и штатный dnsmasq с
    конфигом XGW после перезагрузки не запускался. Своя служба DHCP этот каталог не
    читает: тот же файл ей не мешает."""
    box = gw.box
    box.sh("mkdir -p /etc/dnsmasq.d && printf 'bind-interfaces\\n' > /etc/dnsmasq.d/ubuntu-fan")
    try:
        box.reboot()
        assert wait_for(lambda: _active(gw) == dict.fromkeys(UNITS, "active"), 60), _active(gw)
        if SINGBOX_BIN:  # второе ядро поднимается само, как и Xray
            assert wait_for(lambda: box.run("systemctl", "is-active", "xgw-singbox",
                                            check=False).stdout.strip() == "active", 60)
        assert "cannot set" not in box.journal("xgw-dhcp", 50)
        _came_up_after_reboot(gw)
    finally:
        box.sh("rm -f /etc/dnsmasq.d/ubuntu-fan")


def _came_up_after_reboot(gw) -> None:
    box = gw.box

    def moment(unit: str) -> int:
        return int(box.sh(f"systemctl show {unit} -p ActiveEnterTimestampMonotonic --value"))

    # Правила загружены раньше, чем начала подниматься сеть.
    assert 0 < moment("xgw-net.service") <= moment("network-pre.target")
    assert moment("xgw-net.service") < moment("NetworkManager.service")
    assert "tproxy to 127.0.0.1:12345" in box.sh("nft list table ip xgw")
    assert "lan0:connected:xgw-lan" in box.sh("nmcli -t -f DEVICE,STATE,CONNECTION device")
    assert wait_for(lambda: _state(gw) == "HEALTHY", 90), _xgw(gw, "status").stdout
    assert wait_for(lambda: _exit_ip(gw) == VIA_VPN, 20)
    assert gw.stand.lan("dhcp", "eth0")["router"] == netns.GW_LAN_IP


def test_uninstall_returns_the_system_to_its_original_state(gw):
    box = gw.box
    result = _xgw(gw, "uninstall", "--yes", timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "XGW удалён" in result.stdout and "✗" not in result.stdout

    after = _snapshot(box)
    for key, value in gw.before.items():
        assert after[key] == value, f"{key}:\n--- было\n{value}\n--- стало\n{after[key]}"
    # Подписка пользователя остаётся; служба DHCP и её конфиг — нет.
    assert (box.root / "etc/xgw/config.toml").exists()
    assert not (box.root / "etc/xgw/dnsmasq.conf").exists()
    assert box.run("systemctl", "is-active", "xgw-dhcp", check=False).stdout.strip() != "active"
    assert box.run("systemctl", "is-active", "dnsmasq", check=False).stdout.strip() != "active"
    assert not box.sh("pgrep -x xray || true")
    # Прежний профиль карты снова подключается сам.
    assert "old-lan:yes" in box.sh("nmcli -t -f NAME,AUTOCONNECT connection show")
    # Шлюза больше нет: устройство за ним в интернет не выходит.
    assert _exit_ip(gw) == ""


def test_machine_only_mode_without_a_second_card(gw):
    """Без LAN-карты XGW защищает только саму машину: ни dnsmasq, ни профиля LAN,
    ни правил ufw — и удаление так же возвращает всё на место."""
    box, stand = gw.box, gw.stand
    stand.write_config(capture=True)
    text = stand.config_file.read_text(encoding="utf-8").replace(
        'lan_if = "lan0"', 'lan_if = ""'
    )
    (box.root / "etc/xgw/config.toml").write_text(text, encoding="utf-8")
    _put_xray(box)

    result = _install(gw, "--yes")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "XGW установлен." in result.stdout and "Роутер:" not in result.stdout
    assert "режим — только эта машина" in result.stdout
    assert box.run("systemctl", "is-active", "xgw-net", "xgw-xray", "xgw",
                   check=False).stdout.split() == ["active"] * 3
    assert "xgw-lan" not in box.sh("nmcli -t -f NAME connection show")
    assert not (box.root / "etc/dnsmasq.d/xgw.conf").exists()
    assert not (box.root / "etc/xgw/dnsmasq.conf").exists()
    assert not (box.root / "etc/sysctl.d/90-xgw.conf").exists()
    assert box.sh("cat /proc/sys/net/ipv4/ip_forward").strip() == "0"
    assert box.sh("ufw status") == gw.before["ufw"]  # правила ufw для LAN не нужны
    table = box.sh("nft list table ip xgw")
    assert "chain output" in table and "tproxy to 127.0.0.1:12345" in table
    assert "lan0" not in table and "masquerade" not in table

    assert wait_for(lambda: _state(gw) == "HEALTHY", 60), _xgw(gw, "status").stdout
    assert stand.exit_ip("gw") == VIA_VPN  # трафик самой машины — через VPN
    assert stand.exit_ip("gw", "--mark", "2") == DIRECT  # метка mark_bypass — напрямую
    assert "Перехват: включён — эта машина" in _xgw(gw, "status").stdout

    removed = _xgw(gw, "uninstall", "--yes", "--purge", timeout=300)
    assert removed.returncode == 0, removed.stdout + removed.stderr
    after = _snapshot(box)
    for key, value in gw.before.items():
        assert after[key] == value, f"{key}:\n--- было\n{value}\n--- стало\n{after[key]}"
    assert not (box.root / "etc/xgw").exists()  # --purge убирает и конфиг
    assert stand.exit_ip("gw") == DIRECT


def test_ipv6_of_the_machine_goes_through_vpn_on_the_installed_system(gw):
    """network.ipv6 = "proxy" на настоящей системе (systemd, NetworkManager): установка
    оставляет IPv6 на WAN включённым, службы открывают TPROXY-inbound на ::1 под
    песочницей, трафик IPv6 самой машины идёт через VPN, демон возвращает пропавшую
    таблицу, а удаление возвращает систему в прежнее состояние."""
    box, stand = gw.box, gw.stand
    # IPv6 на стыке «интернета» и машины. Роутера с RA в контейнере нет, поэтому
    # адреса и маршрут ставятся вручную — NetworkManager их не трогает, пока профиль цел.
    for address in (netns.INET_IP6, netns.INET_DNS_IP6):
        machine_mod._run(["ip", "-n", machine_mod.INET_NS, "addr", "replace",
                          f"{address}/64", "dev", "eth0", "nodad"])
    # IPv6 на wan0 мог остаться выключенным после прошлых проверок (ipv6 = off): на
    # NetworkManager 1.46 профиль после удаления XGW возвращается, а карта — только после
    # перезагрузки (ASSUMPTIONS, п. 168). Проверке нужен IPv6, включаем его явно.
    box.sh("sysctl -qw net.ipv6.conf.wan0.disable_ipv6=0")
    box.sh(f"ip addr replace {netns.GW_WAN_IP6}/64 dev wan0 nodad "
           f"&& ip -6 route replace default via {netns.INET_IP6}")
    stand._spawn(
        "origin6", "inet",
        [sys.executable, str(HERE / "origin.py"), "--host", netns.INET_IP6,
         "--port", str(stand.origin_port)],
        "READY",
    )
    assert stand.exit_ip6("gw") == DIRECT6  # до установки IPv6 идёт напрямую

    stand.write_config(capture=True, ipv6="proxy")
    text = stand.config_file.read_text(encoding="utf-8").replace('lan_if = "lan0"', 'lan_if = ""')
    box.sh("mkdir -p /etc/xgw")
    (box.root / "etc/xgw/config.toml").write_text(text, encoding="utf-8")
    _put_xray(box)
    box.sh("chmod 600 /etc/xgw/config.toml")

    result = _install(gw, "--yes")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "IPv6 самой машины пойдёт через Xray" in result.stdout
    assert "будет отключён" not in result.stdout
    assert wait_for(lambda: _state(gw) == "HEALTHY", 60), _xgw(gw, "status").stdout

    # IPv6 на WAN не тронут (в отличие от ipv6 = off), перехват собран и загружен.
    assert box.sh("nmcli -g ipv6.method connection show stand-wan").strip() == "auto"
    table6 = box.sh("nft list table ip6 xgw6")
    assert "tproxy to [::1]:12345" in table6 and "chain loopback_guard" in table6
    assert "fwmark 0x1 lookup 100" in box.sh("ip -6 rule show")
    assert "[::1]:12345" in box.sh("ss -ltnH 'sport = :12345'")  # inbound открыт службой xray
    assert "tproxy-in6" in box.sh("cat /etc/xgw/xray/config.json")

    assert stand.exit_ip6("gw") == VIA_VPN6  # трафик IPv6 самой машины — через VPN
    assert stand.exit_ip6("gw", "--mark", "2") == DIRECT6  # метка mark_bypass — напрямую
    assert stand.exit_ip("gw") == VIA_VPN  # IPv4 — как раньше
    status = _xgw(gw, "status", "--json")
    assert json.loads(status.stdout)["capture"]["ipv6"] is True
    diag = _xgw(gw, "diag")
    assert "IPv6: IPv6 самой машины идёт через Xray" in diag.stdout, diag.stdout

    # Таблица пропала («чужой» сбой): демон возвращает её сам, и IPv6 снова под перехватом.
    box.sh("nft delete table ip6 xgw6")
    assert wait_for(lambda: "xgw6" in box.sh("nft list tables"), 40, step=2), box.journal("xgw")
    assert wait_for(lambda: stand.exit_ip6("gw") == VIA_VPN6, 20)

    removed = _xgw(gw, "uninstall", "--yes", "--purge", timeout=300)
    assert removed.returncode == 0, removed.stdout + removed.stderr
    after = _snapshot(box)
    for key, value in gw.before.items():
        assert after[key] == value, f"{key}:\n--- было\n{value}\n--- стало\n{after[key]}"
    assert "xgw6" not in box.sh("nft list tables")
    assert stand.exit_ip6("gw") == DIRECT6


def test_tun_method_on_the_installed_system(gw):
    """capture.method = "tun" на настоящей системе: интерфейс создаёт XGW до Xray, Xray
    от пользователя xray подключается к нему под песочницей systemd, трафик машины идёт
    через VPN, при остановке Xray закрыт (а не мимо), после перезагрузки всё на месте, а
    удаление убирает и интерфейс."""
    box, stand = gw.box, gw.stand
    stand.write_config(capture=True, method="tun")
    text = stand.config_file.read_text(encoding="utf-8").replace('lan_if = "lan0"', 'lan_if = ""')
    box.sh("mkdir -p /etc/xgw")
    (box.root / "etc/xgw/config.toml").write_text(text, encoding="utf-8")
    _put_xray(box)
    box.sh("chmod 600 /etc/xgw/config.toml")

    result = _install(gw, "--yes")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "TUN: постоянный интерфейс xgwtun0" in result.stdout
    assert wait_for(lambda: _state(gw) == "HEALTHY", 60), _xgw(gw, "status").stdout
    # Роутера нет — сон остаётся как был: без интернета уснувшая машина никого не оставит.
    assert "сон не трогается" in result.stdout and "сон замаскирован" not in result.stdout
    assert "masked" not in box.sh("systemctl is-enabled sleep.target suspend.target || true")

    link = box.sh("ip -d -br link show xgwtun0")
    assert "LOWER_UP" in link and "tun" in box.sh("ip -d link show xgwtun0")  # Xray подключён
    assert box.sh("ps -o user= -C xray").split() == ["xray"]  # от пользователя xray, без root
    rules = box.sh("ip rule show")
    assert "fwmark 0x1 iif lo lookup 101" in rules
    # Контейнеры Docker — меткой mark_containers в ту же таблицу TUN; TPROXY (таблица 100)
    # не нужен никому: LAN нет.
    assert "fwmark 0x3 lookup 101" in rules and "lookup 100" not in rules
    table = box.sh("ip route show table 101")
    assert "default dev xgwtun0" in table and "blackhole default metric 4096" in table
    nft_table = box.sh("nft list table ip xgw")
    prerouting = nft_table.split("chain prerouting {")[1].split("}")[0]
    assert "tproxy" not in prerouting and '"lo"' not in prerouting  # самой машине TPROXY не нужен
    containers = nft_table.split("chain containers {")[1].split("chain prerouting")[0]
    assert "tproxy" not in containers and "meta mark set 0x" in containers
    assert "tun-in" in box.sh("cat /etc/xgw/xray/config.json")

    assert stand.exit_ip("gw") == VIA_VPN  # трафик самой машины — через VPN
    assert stand.exit_ip("gw", "--mark", "2") == DIRECT  # метка mark_bypass — напрямую
    assert json.loads(_xgw(gw, "status", "--json").stdout)["capture"]["tun"] is True
    assert "через TUN" in _xgw(gw, "status").stdout
    diag = _xgw(gw, "diag").stdout
    assert "TUN: /dev/net/tun есть; интерфейс xgwtun0" in diag, diag
    assert "Сон: роутера нет (network.lan_if пуст) — сон не трогается" in diag, diag

    # Остановили Xray: интерфейс постоянный, поэтому трафик закрыт, а не уходит мимо VPN.
    # Вернули — он подключается к тому же интерфейсу, и ничего больше делать не нужно.
    index = box.sh("cat /sys/class/net/xgwtun0/ifindex").strip()
    box.sh("systemctl stop xgw")  # демон не должен сам поднять Xray посреди проверки
    box.sh("systemctl stop xgw-xray")
    # 26.3.27 оставляет интерфейс поднятым (NO-CARRIER), 26.10.10 выключает его: маршрут
    # через него пропадает, а запросы машины — в чёрную дыру, не мимо VPN. После запуска
    # xgw-xray.service маршрут возвращает сам (xgw net tun).
    assert "LOWER_UP" not in box.sh("ip link show xgwtun0")
    assert stand.exit_ip("gw") == ""
    box.sh("systemctl start xgw-xray")
    assert wait_for(lambda: stand.exit_ip("gw") == VIA_VPN, 40, step=2)
    assert box.sh("cat /sys/class/net/xgwtun0/ifindex").strip() == index
    box.sh("systemctl start xgw")

    # Перезагрузка: xgw-net.service создаёт интерфейс раньше Xray, и тот его не теряет.
    box.reboot()
    assert wait_for(lambda: _state(gw) == "HEALTHY", 120), _xgw(gw, "status").stdout
    assert wait_for(lambda: stand.exit_ip("gw") == VIA_VPN, 30, step=2)
    box.sh("systemctl stop xgw")
    box.sh("systemctl stop xgw-xray")
    assert "xgwtun0" in box.sh("ip -br link")  # создан XGW, а не Xray — иначе исчез бы
    assert stand.exit_ip("gw") == ""
    box.sh("systemctl start xgw-xray")
    assert wait_for(lambda: stand.exit_ip("gw") == VIA_VPN, 40, step=2)
    box.sh("systemctl start xgw")

    removed = _xgw(gw, "uninstall", "--yes", "--purge", timeout=300)
    assert removed.returncode == 0, removed.stdout + removed.stderr
    assert "интерфейс TUN убраны" in removed.stdout
    after = _snapshot(box)
    for key, value in gw.before.items():
        assert after[key] == value, f"{key}:\n--- было\n{value}\n--- стало\n{after[key]}"
    assert "does not exist" in after["tun link"] or "Cannot find" in after["tun link"]
    assert stand.exit_ip("gw") == DIRECT
