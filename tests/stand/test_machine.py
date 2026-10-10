"""Этап 4 на «одноразовой машине»: установка, работа после перезагрузки, удаление.

Шлюз здесь — не пространство имён, а загруженная система в контейнере
systemd-nspawn (см. machine.py): настоящие systemd, NetworkManager, dnsmasq и
ufw. `xgw install` и `xgw uninstall` выполняются внутри него целиком, сеть
хоста не затрагивается.

    sudo -E XGW_XRAY_BIN=<путь к xray> pytest tests/stand/test_machine.py -q

Проверки идут по порядку и продолжают одна другую: первый запуск без конфига →
установка → работа из LAN → правка конфига → уведомление → перезагрузка → удаление.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import tarfile
import time
from pathlib import Path
from types import SimpleNamespace

import machine as machine_mod
import netns
import pytest
from machine import Machine, MachineTopology
from stand import UUID, Stand, wait_for

XRAY_BIN = os.environ.get("XGW_XRAY_BIN", "")
REPO = Path(__file__).resolve().parents[2]
VIA_VPN = netns.INET_IP
DIRECT = netns.GW_WAN_IP
UNITS = ("xgw-net", "xgw-xray", "xgw", "dnsmasq")

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
        "table 100": box.sh("ip route show table 100 2>/dev/null || true"),
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
            "ls -d /opt/xgw /usr/local/bin/xgw /etc/dnsmasq.d/xgw.conf /etc/sysctl.d/90-xgw.conf "
            "/var/lib/xgw /etc/xgw/xray 2>/dev/null || true"
        ),
    }


@pytest.fixture(scope="module")
def gw():
    """Машина с «заводской» системой и работающим «интернетом»; XGW ещё не установлен."""
    box = Machine()
    box.create()
    stand = Stand(box.share / "stand", Path(XRAY_BIN), mode="netns",
                  _topology=MachineTopology(box))
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
        stand.write_config(capture=True, extra="\n[status]\nlan_page = true\n")
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


def test_first_run_creates_the_config_and_changes_nothing_else(gw):
    box = gw.box
    first = _install(gw, "--yes")
    assert first.returncode == 1, first.stdout + first.stderr
    assert "Создан /etc/xgw/config.toml" in first.stdout
    assert box.sh("stat -c '%U:%G %a' /etc/xgw/config.toml").strip() == "root:root 600"
    example = (REPO / "config.example.toml").read_text(encoding="utf-8")
    assert (box.root / "etc/xgw/config.toml").read_text(encoding="utf-8") == example
    # С подпиской-примером установка не начинается.
    second = _install(gw, "--yes")
    assert second.returncode == 1 and "нет ни подписки" in second.stdout
    assert "Установка не начата" in second.stdout
    after = _snapshot(box)
    assert {key: after[key] for key in after if key != "files"} == {
        key: gw.before[key] for key in gw.before if key != "files"
    }
    # «Пользователь вписывает подписку»: конфиг стенда. Сети в контейнере нет —
    # Xray кладём заранее; установка его не скачивает, если версия подходит.
    shutil.copyfile(gw.stand.config_file, box.root / "etc/xgw/config.toml")
    box.sh(f"mkdir -p /opt/xgw/xray && cp {Path(XRAY_BIN).parent}/* /opt/xgw/xray/ "
           "&& chmod 600 /etc/xgw/config.toml")


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
    assert "пакеты: dnsmasq" in out  # поставлен через apt-get из репозитория контейнера
    assert "ufw: ufw allow in on lan0" in out

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
    for key in ("sysctl", "nm_lan", "nm_wan", "dnsmasq", "packages", "user_created", "sleep"):
        assert second[key] == first[key], key
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

    # Адреса раздаёт dnsmasq.service: из диапазона и по статической аренде.
    lease = stand.lan("dhcp", "eth0")
    assert lease["router"] == lease["dns"] == netns.GW_LAN_IP
    assert 110 <= int(lease["ip"].rsplit(".", 1)[1]) <= 150
    assert stand.lan("dhcp", "eth0", "--mac", netns.LAN_BYPASS_MAC)["ip"] == netns.LAN_BYPASS_IP


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
    stand.write_config(capture=True, max_members=3, extra="\n[status]\nlan_page = true\n")
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
    assert "192.168.50.160" in box.sh("cat /etc/dnsmasq.d/xgw.conf")
    assert _active(gw)["dnsmasq"] == "active"


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
        # Демон поднял Xray сам, шлюз снова в строю.
        assert wait_for(lambda: _state(gw) == "HEALTHY", 60), _xgw(gw, "status").stdout
        assert wait_for(lambda: _exit_ip(gw) == VIA_VPN, 20)
    finally:
        box.sh("rm -f /usr/local/bin/loginctl /usr/local/bin/notify-send")


def test_diag_after_install_and_log_export_without_secrets(gw):
    box = gw.box
    result = _xgw(gw, "diag")
    assert result.returncode == 0, result.stdout
    for text in ("xgw-net, xgw-xray, xgw, dnsmasq работают", "Перехват: включён, правила загружены",
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


def test_everything_comes_up_after_reboot_rules_before_network(gw):
    box = gw.box
    box.reboot()
    assert wait_for(lambda: _active(gw) == dict.fromkeys(UNITS, "active"), 60), _active(gw)

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
    # Подписка пользователя остаётся; пакет dnsmasq — тоже, но служба выключена.
    assert (box.root / "etc/xgw/config.toml").exists()
    assert box.run("systemctl", "is-active", "dnsmasq", check=False).stdout.strip() != "active"
    assert box.run("systemctl", "is-enabled", "dnsmasq", check=False).stdout.strip() != "enabled"
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
    box.sh(f"mkdir -p /opt/xgw/xray && cp {Path(XRAY_BIN).parent}/* /opt/xgw/xray/")

    result = _install(gw, "--yes")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "XGW установлен." in result.stdout and "Роутер:" not in result.stdout
    assert "режим — только эта машина" in result.stdout
    assert box.run("systemctl", "is-active", "xgw-net", "xgw-xray", "xgw",
                   check=False).stdout.split() == ["active"] * 3
    assert "xgw-lan" not in box.sh("nmcli -t -f NAME connection show")
    assert not (box.root / "etc/dnsmasq.d/xgw.conf").exists()
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

