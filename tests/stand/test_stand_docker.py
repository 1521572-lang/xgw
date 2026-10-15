"""Контейнеры Docker за шлюзом (F4 отчёта о живой машине 14.10): их трафик — через VPN.

Docker на стенде не нужен: его сеть устроена просто, и она повторяется руками — мост
docker0 с адресом 172.17.0.1/16 в пространстве имён шлюза, «контейнер» — своё
пространство имён с veth в этом мосту, маскарадинг на выходе и DNAT опубликованного
порта (`docker run -p 9090:9090`), как их ставит сам Docker:

    inet (5.5.5.1) ──eth0══wan0── gw ──docker0══vctr──eth0── ctr (172.17.0.2)

    sudo -E XGW_XRAY_BIN=<путь к xray> pytest tests/stand/test_stand_docker.py -q

Контейнеры идут в Xray не через TPROXY, а маршрутом в TUN-интерфейс XGW по своей метке:
с br_netfilter, который включает Docker, TPROXY для пакетов с моста не работает (сокет,
назначенный TPROXY, ядро сбрасывает). Если br_netfilter на машине со стендом загружен
(он общий для всех пространств имён), стенд проверяет и этот случай.

Как и в test_stand_lan.py: origin на /trace отдаёт адрес, с которого пришёл запрос, —
5.5.5.1 значит «через VPN-сервер», 5.5.5.2 (WAN шлюза) — «напрямую».
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import netns
import pytest
from stand import Stand, wait_for

XRAY_BIN = os.environ.get("XGW_XRAY_BIN", "")
HERE = Path(__file__).resolve().parent
VIA_VPN = netns.INET_IP
DIRECT = netns.GW_WAN_IP
BRIDGE_IP = "172.17.0.1"
CONTAINER_IP = "172.17.0.2"
PUBLISHED = 9090
TUN = "xgwtun0"
TUN_ADDRESS = "169.254.10.1/32"

pytestmark = [
    pytest.mark.skipif(
        not XRAY_BIN or not Path(XRAY_BIN).exists(), reason="нет XGW_XRAY_BIN — стенд пропущен"
    ),
    pytest.mark.skipif(
        not netns.available() or shutil.which("nft") is None,
        reason="проверки контейнеров: нужны Linux, root и nft",
    ),
]

# Что ставит сам Docker (iptables-nft): маскарадинг сети контейнеров и DNAT
# опубликованного порта. Своя таблица — как у Docker, отдельно от таблиц XGW.
DOCKER_NAT = f"""
table ip dockerish {{
    chain prerouting {{
        type nat hook prerouting priority dstnat; policy accept;
        iifname "wan0" tcp dport {PUBLISHED} dnat to {CONTAINER_IP}:{PUBLISHED}
    }}
    chain postrouting {{
        type nat hook postrouting priority srcnat; policy accept;
        ip saddr 172.17.0.0/16 oifname != "docker0" masquerade
    }}
}}
"""


def _ip(*args: str) -> None:
    subprocess.run(["ip", *args], check=True, capture_output=True, text=True, timeout=15)


class Container:
    """«Контейнер» за мостом Docker: пространство имён ctr, veth в мосту docker0 шлюза."""

    def __init__(self, stand: Stand) -> None:
        self.stand = stand
        self.gw = stand._topology.gw
        self.ns = f"xgw-ctr-{os.getpid()}"
        self.server: subprocess.Popen | None = None

    def create(self) -> None:
        """Сеть контейнера — так, как её поднимает dockerd при первом запуске."""
        _ip("netns", "add", self.ns)
        _ip("-n", self.ns, "link", "set", "lo", "up")
        _ip("-n", self.gw, "link", "add", "docker0", "type", "bridge")
        _ip("-n", self.gw, "addr", "add", f"{BRIDGE_IP}/16", "dev", "docker0")
        _ip("-n", self.gw, "link", "set", "docker0", "up")
        _ip("link", "add", "vctr", "netns", self.gw, "type", "veth",
            "peer", "name", "eth0", "netns", self.ns)
        _ip("-n", self.gw, "link", "set", "vctr", "master", "docker0", "up")
        _ip("-n", self.ns, "addr", "add", f"{CONTAINER_IP}/16", "dev", "eth0")
        _ip("-n", self.ns, "link", "set", "eth0", "up")
        _ip("-n", self.ns, "route", "add", "default", "via", BRIDGE_IP)
        self.stand.gw_run("sysctl", "-qw", "net.ipv4.ip_forward=1")  # так делает dockerd
        subprocess.run(
            ["ip", "netns", "exec", self.gw, "nft", "-f", "-"], input=DOCKER_NAT,
            check=True, capture_output=True, text=True, timeout=15,
        )
        # Служба в контейнере, опубликованная на порту шлюза.
        self.server = subprocess.Popen(
            ["ip", "netns", "exec", self.ns, sys.executable, str(HERE / "origin.py"),
             "--host", CONTAINER_IP, "--port", str(PUBLISHED), "--country", "DE"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        assert self.server.stdout is not None and "READY" in self.server.stdout.readline()

    def destroy(self) -> None:
        if self.server is not None:
            self.server.kill()
            self.server.wait(timeout=10)
        subprocess.run(["ip", "netns", "del", self.ns], capture_output=True, timeout=15)

    def client(self, namespace: str, *args: str) -> dict:
        result = subprocess.run(
            ["ip", "netns", "exec", namespace, sys.executable, str(HERE / "lan_client.py"),
             *args],
            capture_output=True, text=True, timeout=40,
        )
        return json.loads(result.stdout.strip().splitlines()[-1])

    def exit_ip(self) -> str:
        """С какого адреса запрос контейнера дошёл до «интернета»."""
        reply = self.client(
            self.ns, "get", self.stand.origin_url("/trace"), "--timeout", "4")
        for line in reply.get("body", "").splitlines():
            if line.startswith("ip="):
                return line[3:]
        return ""

    def published(self) -> str:
        """Запрос из «интернета» на опубликованный порт: кто ответил (loc=) — или пусто."""
        inet = self.stand._topology.inet
        reply = self.client(
            inet, "get", f"http://{netns.GW_WAN_IP}:{PUBLISHED}/trace", "--timeout", "4")
        for line in reply.get("body", "").splitlines():
            if line.startswith("loc="):
                return line[4:]
        return ""


@pytest.fixture()
def stand(tmp_path):
    instance = Stand(tmp_path, Path(XRAY_BIN), mode="netns")
    containers: list[Container] = []
    instance.container = lambda: containers.append(Container(instance)) or containers[-1]
    try:
        instance.start()
        yield instance
    finally:
        for container in containers:
            container.destroy()
        instance.stop()


def test_container_goes_through_vpn_and_its_published_port_still_answers(stand):
    container = stand.container()
    container.create()  # Docker был на машине ещё до XGW
    stand.up(capture=True)
    enabled = stand.xgw("enable")
    assert enabled.returncode == 0, enabled.stderr
    tables = stand.gw_run("nft", "list", "ruleset")
    # Сама машина и контейнер — через VPN; контейнер — через inbound TUN.
    assert stand.exit_ip("gw") == VIA_VPN
    assert container.exit_ip() == VIA_VPN, tables
    log = stand.xray_log(40)
    assert "tun-in -> proxy-" in log, log
    # DNS контейнера (к любому серверу) отвечает Xray, как у устройств LAN.
    answer = container.client(container.ns, "dns", "8.8.8.8", "example.org")
    assert answer.get("answers") == [netns.INET_IP], answer
    # Опубликованный порт контейнера: ответ уходит обратно напрямую, а не в Xray.
    assert container.published() == "DE"
    status = stand.xgw("status").stdout
    assert "контейнеры Docker" in status, status

    # Перехват снят — контейнер выходит напрямую, как и всё остальное.
    assert stand.xgw("disable").returncode == 0
    assert wait_for(lambda: container.exit_ip() == DIRECT, 10, step=0.5)
    assert stand.xgw("enable").returncode == 0
    assert wait_for(lambda: container.exit_ip() == VIA_VPN, 10, step=0.5)


def test_docker_installed_after_xgw_is_picked_up_by_the_daemon(stand):
    """Docker поставили уже после XGW (так было на живой машине): мост появился, а Xray
    запущен без inbound'а TUN. Демон замечает это сам, Xray перезапускается с ним — и
    контейнеры идут через VPN. До этого они закрыты (чёрная дыра), а не мимо VPN."""
    stand.up(capture=True)
    assert stand.xgw("enable").returncode == 0
    applied = stand.root / "etc/xgw/xray/config.json"
    assert "tun-in" not in stand.gw_run("cat", str(applied))  # Docker нет — TUN не нужен
    assert "xgwtun0" not in stand.gw_run("ip", "link")
    stand.start_daemon()
    assert wait_for(lambda: stand.xgw_json("status").get("state") == "HEALTHY", 40)

    container = stand.container()
    container.create()
    assert container.exit_ip() in ("", VIA_VPN)  # закрыт, но не напрямую
    assert wait_for(lambda: container.exit_ip() == VIA_VPN, 60, step=1), stand.tail("daemon", 60)
    assert "tun-in" in stand.gw_run("cat", str(applied))
    assert stand.exit_ip("lan") == VIA_VPN and stand.exit_ip("gw") == VIA_VPN
    assert "появился Docker" in stand.tail("daemon", 200)


def test_after_a_reboot_the_tun_of_the_containers_has_its_address(stand):
    """Перезагрузка (отчёт 0.1.4, G7). При capture.method = "tproxy" интерфейс TUN нужен
    только контейнерам, и создаёт его теперь `xgw net up` (xgw-net.service, раньше Xray) — с
    адресом. Интерфейс, который создал сам Xray, адреса не имеет: ядро отбрасывает ответы
    Xray, и контейнеры без интернета. Такой интерфейс видит проверка правил, а `xgw net up`
    (его же делает демон, заметив это) его чинит."""
    stand.gw_run("sysctl", "-qw", "net.ipv4.conf.all.rp_filter=2",
                 "net.ipv4.conf.default.rp_filter=2")  # умолчание Ubuntu
    container = stand.container()
    container.create()
    stand.up(capture=True)
    assert stand.xgw("enable").returncode == 0
    assert container.exit_ip() == VIA_VPN
    config = str(stand.root / "etc/xgw/xray/config.json")

    def address() -> str:
        return stand.gw_run("ip", "-br", "addr", "show", "dev", TUN, check=False)

    # Загрузка: правила раньше Xray — интерфейс готовит XGW, Xray к нему подключается.
    stand.xray_service().stop()
    stand.gw_run("ip", "link", "del", "dev", TUN)
    assert stand.xgw("net", "up").returncode == 0
    assert TUN_ADDRESS in address()
    xray = stand.gw_popen("xray-boot", [str(stand.xray_bin), "run", "-c", config])
    assert wait_for(lambda: container.exit_ip() == VIA_VPN, 30, step=1), stand.xray_log(30)

    # Интерфейс создал сам Xray (так было в 0.1.4 после перезагрузки): адреса нет.
    xray.terminate()
    xray.wait(timeout=10)
    stand.gw_run("ip", "link", "del", "dev", TUN)
    stand.gw_popen("xray-alone", [str(stand.xray_bin), "run", "-c", config])
    assert wait_for(lambda: TUN in stand.gw_run("ip", "-br", "link", check=False), 20)
    assert TUN_ADDRESS not in address()
    assert container.exit_ip() == ""  # ни через VPN, ни мимо
    assert stand.xgw_json("status")["capture"]["loaded"] is False  # проверка правил видит
    assert stand.xgw("net", "up").returncode == 0
    assert TUN_ADDRESS in address()
    assert wait_for(lambda: container.exit_ip() == VIA_VPN, 30, step=1), stand.xray_log(30)
    assert stand.xgw_json("status")["capture"]["loaded"] is True


def test_containers_can_be_left_outside_the_vpn(stand):
    """capture.containers = false — контейнеры ходят напрямую (так было до 0.1.4), сама
    машина — по-прежнему через VPN."""
    container = stand.container()
    container.create()
    stand.up(capture=True, containers=False)
    assert stand.xgw("enable").returncode == 0
    assert "containers" not in stand.gw_run("nft", "list", "table", "ip", "xgw")
    assert "tun-in" not in stand.gw_run("cat", str(stand.root / "etc/xgw/xray/config.json"))
    assert container.exit_ip() == DIRECT
    assert stand.exit_ip("gw") == VIA_VPN
    assert container.published() == "DE"
