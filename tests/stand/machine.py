"""Одноразовая «машина» для проверки установки: контейнер systemd-nspawn.

`xgw install` меняет систему — службы systemd, профили NetworkManager,
пользователей, sysctl. Проверять это на своей машине нельзя, а в пространстве
имён нечем: там нет ни systemd, ни NetworkManager. Поэтому установка
проверяется на загруженной системе в контейнере:

    inet (5.5.5.1) ──eth0══wan0── контейнер ──lan0══eth0── lan (192.168.50.100)

  * корень контейнера — оверлей поверх корня хоста: в нём та же Ubuntu, а всё,
    что в нём меняется, остаётся в tmpfs и исчезает вместе с ним;
  * сеть у контейнера своя (--private-network): правила nftables, ip rule и
    профили NetworkManager хоста не затрагиваются;
  * «интернет» и «устройство в LAN» — пространства имён на стороне хоста,
    соединённые с контейнером veth-парами, как в стенде раздела 9.

Нужны root, systemd-nspawn (пакет systemd-container) и NetworkManager — в самой
системе либо .deb-пакетами в каталоге XGW_MACHINE_DEBS: они ставятся только
внутри контейнера. XGW_MACHINE_PREINSTALL_DNSMASQ=1 ставит в контейнер пакет dnsmasq ещё
до установки XGW — так проверяется хост, на котором dnsmasq уже есть.

XGW, установленный на самом хосте, стенду не мешает: его файлы, службы и следы в
настройках убираются из верхнего слоя оверлея ещё до загрузки контейнера (см.
scrub_host_xgw) — хост при этом не меняется, а контейнер получает систему, на которой
XGW никогда не ставили.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import netns

# Не в /tmp и не в /var/tmp: у служб с PrivateTmp они свои, а подписку стенда
# (файл в общем каталоге) должен видеть демон xgw.service.
BASE = Path(os.environ.get("XGW_MACHINE_DIR", "/var/lib/xgw-machine"))
DEBS = Path(os.environ.get("XGW_MACHINE_DEBS", "/root/xgw-debs"))
NAME = "xgwm"
INET_NS = "xgwm-inet"
LAN_NS = "xgwm-lan"
WAN_LINK = "xgwm-wan"  # концы veth на стороне хоста; в контейнере — wan0 и lan0
LAN_LINK = "xgwm-lan"
PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Что оставляет в системе `xgw install` (пути от корня).
HOST_XGW_PATHS = (
    "etc/xgw", "opt/xgw", "var/lib/xgw", "usr/local/bin/xgw",
    "etc/dnsmasq.d/xgw.conf", "etc/sysctl.d/90-xgw.conf",
    "usr/local/share/applications/xgw-panel.desktop",
)
HOST_XGW_GLOBS = (
    "etc/systemd/system/xgw*.service",
    "etc/systemd/system/*.wants/xgw*.service",
    "etc/systemd/system/*.requires/xgw*.service",
)
# Профиль xgw-lan: keyfile NetworkManager либо — у NetworkManager с netplan (Ubuntu 24.04 и
# новее) — файл netplan 90-NM-<uuid>.yaml, а в system-connections тогда пусто.
XGW_PROFILE_KEYFILES = "etc/NetworkManager/system-connections/xgw-lan*"
NETPLAN_PROFILES = "etc/netplan/90-NM-*.yaml"
_XGW_PROFILE_NAME = re.compile(r"""^\s*name:\s*["']?xgw-lan["']?\s*$""", re.MULTILINE)
SLEEP_TARGETS = ("sleep.target", "suspend.target", "hibernate.target", "hybrid-sleep.target")
# Службы хоста, которым в контейнере не место: корень — оверлей поверх хоста, и Docker,
# включённый на хосте, запустился бы и в контейнере — со своими правилами nftables,
# мостом docker0 и профилем NetworkManager для него. Сверка «до установки / после
# удаления» тогда расходилась бы сама по себе.
HOST_SERVICES_OFF = ("docker.service", "docker.socket", "containerd.service")
# «Заводская» система — не роутер. Сетевое пространство имён контейнера при создании
# наследует значения хоста, а на хосте форвардинг бывает включён (Docker, установленный
# XGW): этот файл возвращает его при каждой загрузке контейнера. Файл XGW (90-xgw.conf)
# читается позже и для шлюза с LAN включает форвардинг обратно.
STAND_SYSCTL = "etc/sysctl.d/00-xgw-stand.conf"


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def xgw_profile_files(root: Path, uuid: str | None = None) -> list[Path]:
    """Файлы профиля xgw-lan в корне root; uuid — профиль из журнала установки (файл netplan
    назван по нему), без него профиль узнаётся по имени в файле."""
    found = sorted(root.glob(XGW_PROFILE_KEYFILES))
    for path in sorted(root.glob(NETPLAN_PROFILES)):
        if uuid and path.name == f"90-NM-{uuid}.yaml":
            found.append(path)
            continue
        with contextlib.suppress(OSError, UnicodeDecodeError):
            if _XGW_PROFILE_NAME.search(path.read_text(encoding="utf-8")):
                found.append(path)
    return found


def scrub_host_xgw(root: Path) -> dict:
    """Убирает из корня контейнера XGW, установленный на хосте.

    Корень контейнера — оверлей поверх корня хоста: всё, что `xgw install` оставил на
    хосте, видно и внутри. С этим не прошла бы ни одна проверка «первого запуска»
    (config.toml уже есть), а при загрузке контейнера стартовали бы службы xgw хоста.
    Удаление идёт в верхнем слое оверлея и хост не затрагивает.

    Журнал установки хоста (var/lib/xgw/backup/install.json) говорит, что ещё XGW менял
    вне своих каталогов: маски целей сна убираются сразу, а правила ufw и пользователь
    xray — после загрузки, командами внутри контейнера (см. Machine.prepare). Возвращает
    журнал, если он был.
    """
    root = Path(root)
    if root.resolve() == Path(root.anchor):
        raise RuntimeError(f"{root} — это корень системы, а не корень контейнера")
    journal: dict = {}
    with contextlib.suppress(OSError, json.JSONDecodeError):
        loaded = json.loads((root / "var/lib/xgw/backup/install.json").read_text("utf-8"))
        if isinstance(loaded, dict):
            journal = loaded
    for relative in HOST_XGW_PATHS:
        _remove(root / relative)
    for pattern in HOST_XGW_GLOBS:
        for path in root.glob(pattern):
            _remove(path)
    # Профиль xgw-lan хоста: иначе установка в контейнере нашла бы его по имени и взяла
    # себе, а удаление — снесло бы, и сверка «до/после» разошлась (отчёт 0.1.4, G4).
    lan_record = journal.get("nm_lan")
    uuid = lan_record.get("profile") if isinstance(lan_record, dict) else None
    for path in xgw_profile_files(root, uuid if isinstance(uuid, str) else None):
        _remove(path)
    for target in journal.get("sleep") or []:
        link = root / "etc/systemd/system" / str(target)
        if str(target) in SLEEP_TARGETS and link.is_symlink() and os.readlink(link) == "/dev/null":
            link.unlink()
    if journal.get("ufw_before"):
        rules = root / "etc/ufw/before.rules"
        with contextlib.suppress(OSError):
            lines = rules.read_text(encoding="utf-8").splitlines(keepends=True)
            kept = [
                line for line in lines
                if not (line.startswith("-A ufw-before-input -i ") and "--mark" in line
                        and line.rstrip().endswith("-j ACCEPT"))
            ]
            if kept != lines:
                rules.write_text("".join(kept), encoding="utf-8")
    sysctl = root / STAND_SYSCTL
    sysctl.parent.mkdir(parents=True, exist_ok=True)
    sysctl.write_text(
        "net.ipv4.ip_forward = 0\nnet.ipv6.conf.all.forwarding = 0\n", encoding="utf-8"
    )
    return journal


def mask_host_services(root: Path) -> None:
    """Маскирует в корне контейнера службы хоста из HOST_SERVICES_OFF (маска — в верхнем
    слое оверлея, хост не меняется)."""
    units = Path(root) / "etc/systemd/system"
    units.mkdir(parents=True, exist_ok=True)
    for name in HOST_SERVICES_OFF:
        unit = units / name
        if unit.is_symlink() or unit.exists():
            _remove(unit)
        unit.symlink_to("/dev/null")


def unavailable() -> str:
    """Почему машину не поднять; пусто — можно."""
    if not netns.available():
        return "нужны Linux и root"
    for tool in ("systemd-nspawn", "machinectl", "nsenter"):
        if shutil.which(tool) is None:
            return f"нет {tool} (пакет systemd-container)"
    if not Path("/run/systemd/system").is_dir():
        return "на хосте не работает systemd"
    if shutil.which("nmcli") is None and not list(DEBS.glob("network-manager_*.deb")):
        return f"нет NetworkManager: ни в системе, ни .deb в {DEBS}"
    return ""


def _run(
    argv: list[str], *, check: bool = True, timeout: float = 60
) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=check, capture_output=True, text=True, timeout=timeout)


class MachineTopology:
    """То же, что netns.Topology, но шлюз — контейнер, а не пространство имён."""

    inet = INET_NS
    lan = LAN_NS
    gw = "machine"

    def __init__(self, machine: Machine) -> None:
        self.machine = machine

    def prefix(self, namespace: str) -> list[str]:
        if namespace == self.gw:
            return self.machine.prefix()
        return ["ip", "netns", "exec", namespace]


class Machine:
    def __init__(self) -> None:
        self.root = BASE / "root"  # корень контейнера, виден и с хоста
        self.share = BASE / "share"  # общий каталог: в контейнере — по тому же пути
        self.leader = 0
        self._proc: subprocess.Popen | None = None
        self.host_journal: dict = {}  # журнал установки XGW на хосте, если он там стоит
        # Пакет dnsmasq достался контейнеру от хоста: установке XGW ставить его незачем.
        self.dnsmasq_preinstalled = False

    # --- создание и удаление ----------------------------------------------------

    def create(self) -> None:
        self.destroy()
        BASE.mkdir(parents=True, exist_ok=True)
        _run(["mount", "-t", "tmpfs", "-o", "size=2G,mode=0755", "tmpfs", str(BASE)])
        for name in ("upper", "work", "root", "share"):
            (BASE / name).mkdir()
        _run(["mount", "-t", "overlay", "overlay", "-o",
              f"lowerdir=/,upperdir={BASE / 'upper'},workdir={BASE / 'work'}", str(self.root)])
        if _run(["mountpoint", "-q", str(self.root)], check=False).returncode != 0:
            raise RuntimeError(f"оверлей не смонтирован в {self.root}")
        self.host_journal = scrub_host_xgw(self.root)
        mask_host_services(self.root)
        for namespace in (INET_NS, LAN_NS):
            _run(["ip", "netns", "add", namespace])
            _run(["ip", "-n", namespace, "link", "set", "lo", "up"])
        self._links()  # «интернет» можно запускать ещё до загрузки контейнера

    def destroy(self) -> None:
        self.poweroff()
        _run(["machinectl", "terminate", NAME], check=False)
        for namespace in (INET_NS, LAN_NS):
            _run(["ip", "netns", "del", namespace], check=False)
        for link in (WAN_LINK, LAN_LINK):
            _run(["ip", "link", "del", link], check=False)
        for mount in (self.root, BASE):
            for _ in range(20):
                if _run(["mountpoint", "-q", str(mount)], check=False).returncode != 0:
                    break
                if _run(["umount", str(mount)], check=False).returncode != 0:
                    time.sleep(0.5)

    def _links(self) -> None:
        """«Кабели»: veth-пары между хостом (их концы уйдут в контейнер) и inet/lan."""
        plan = (
            (WAN_LINK, INET_NS, (f"{netns.INET_IP}/24", f"{netns.INET_DNS_IP}/24")),
            (LAN_LINK, LAN_NS, (f"{netns.LAN_IP}/24", f"{netns.LAN_BYPASS_IP}/24")),
        )
        for link, namespace, addresses in plan:
            if _run(["ip", "link", "show", link], check=False).returncode != 0:
                _run(["ip", "-n", namespace, "link", "del", "eth0"], check=False)
                _run(["ip", "link", "add", link, "type", "veth",
                      "peer", "name", "eth0", "netns", namespace])
            for address in addresses:
                _run(["ip", "-n", namespace, "addr", "replace", address, "dev", "eth0"])
            _run(["ip", "-n", namespace, "link", "set", "eth0", "up"])
        _run(["ip", "-n", LAN_NS, "route", "replace", "default", "via", netns.GW_LAN_IP])

    # --- загрузка ---------------------------------------------------------------

    def boot(self, timeout: float = 90) -> None:
        self._links()
        argv = [
            "systemd-nspawn", "--quiet", "--boot", f"--directory={self.root}",
            f"--machine={NAME}", "--private-network",
            f"--network-interface={WAN_LINK}:wan0", f"--network-interface={LAN_LINK}:lan0",
            f"--bind={self.share}", "--resolv-conf=off", "--timezone=off", "--link-journal=no",
        ]
        if DEBS.is_dir():
            argv.append(f"--bind-ro={DEBS}:/debs")
        with open(BASE / "console.log", "ab") as console:
            self._proc = subprocess.Popen(
                argv, stdin=subprocess.DEVNULL, stdout=console, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        deadline = time.monotonic() + timeout
        self.leader = 0
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(f"контейнер не загрузился: {self.console()}")
            if not self.leader:
                shown = _run(["machinectl", "show", NAME, "-p", "Leader", "--value"], check=False)
                self.leader = int(shown.stdout.strip() or 0) if shown.returncode == 0 else 0
            elif self.run("systemctl", "is-system-running", check=False).stdout.strip() in (
                "running", "degraded"
            ):
                return
            time.sleep(0.5)
        raise RuntimeError(f"контейнер не загрузился за {timeout:.0f} с: {self.console()}")

    def poweroff(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            self.leader = 0
            return
        with contextlib.suppress(Exception):
            self.run("systemctl", "poweroff", check=False, timeout=20)
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            _run(["machinectl", "terminate", NAME], check=False)
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=20)
            if proc.poll() is None:
                proc.kill()
        self.leader = 0

    def reboot(self, timeout: float = 90) -> None:
        """Перезагрузка изнутри (`systemctl reboot`): диск (оверлей) сохраняется,
        всё остальное — заново, включая сетевое пространство имён."""
        before = self.leader
        self.run("systemctl", "reboot", check=False, timeout=20)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(1)
            if self._proc is not None and self._proc.poll() is not None:
                raise RuntimeError(f"контейнер не пережил перезагрузку: {self.console()}")
            shown = _run(["machinectl", "show", NAME, "-p", "Leader", "--value"], check=False)
            leader = int(shown.stdout.strip() or 0) if shown.returncode == 0 else 0
            if not leader or leader == before:
                continue
            self.leader = leader
            state = self.run("systemctl", "is-system-running", check=False).stdout.strip()
            if state in ("running", "degraded"):
                return
        raise RuntimeError(f"контейнер не загрузился после перезагрузки: {self.console()}")

    def console(self, lines: int = 20) -> str:
        with contextlib.suppress(OSError):
            text = (BASE / "console.log").read_text(encoding="utf-8", errors="replace")
            return "\n".join(text.splitlines()[-lines:])
        return ""

    # --- команды внутри ---------------------------------------------------------

    def prefix(self) -> list[str]:
        """Префикс команды, чтобы выполнить её внутри контейнера с чистым окружением."""
        return ["nsenter", "-a", "-t", str(self.leader), "--",
                "env", "-i", f"PATH={PATH}", "HOME=/root", "LANG=C.UTF-8"]

    def run(
        self, *argv: str, check: bool = True, timeout: float = 120, input: str | None = None
    ) -> subprocess.CompletedProcess:
        result = subprocess.run(
            [*self.prefix(), *argv], capture_output=True, text=True, timeout=timeout,
            input=input, encoding="utf-8", errors="replace",
        )
        if check and result.returncode != 0:
            raise RuntimeError(
                f"{' '.join(argv)}: код {result.returncode}\n{result.stdout}{result.stderr}"
            )
        return result

    def sh(self, script: str, *, check: bool = True, timeout: float = 120) -> str:
        return self.run("bash", "-c", script, check=check, timeout=timeout).stdout

    def journal(self, unit: str, lines: int = 30) -> str:
        return self.run(
            "journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "cat", check=False
        ).stdout

    # --- «заводская» система -----------------------------------------------------

    def prepare(self, *, ufw: bool = True) -> None:
        """Доводит систему до вида Ubuntu Desktop: NetworkManager управляет картами,
        у WAN есть профиль с адресом и шлюзом, у LAN — прежний профиль с DHCP.

        ufw включается намеренно: его политика «входящие запрещены» — самый
        частый способ оставить устройства за шлюзом без сети."""
        self.sh(
            r"""
set -e
if ! command -v nmcli >/dev/null; then
    DEBIAN_FRONTEND=noninteractive dpkg -i $(ls /debs/*.deb | grep -v '/dnsmasq_') >/dev/null
fi
# Сети в контейнере нет — пакеты для `apt-get install` лежат в локальном репозитории.
if ls /debs/dnsmasq_*.deb >/dev/null 2>&1; then
    mkdir -p /var/local/repo && cp /debs/dnsmasq_*.deb /var/local/repo/ && cd /var/local/repo
    for deb in *.deb; do
        dpkg-deb -f "$deb"
        echo "Filename: ./$deb"
        echo "Size: $(stat -c %s "$deb")"
        echo "SHA256: $(sha256sum "$deb" | cut -d' ' -f1)"
        echo
    done > Packages
    mkdir -p /etc/apt/disabled
    mv /etc/apt/sources.list.d/* /etc/apt/disabled/ 2>/dev/null || true
    : > /etc/apt/sources.list
    echo 'deb [trusted=yes] file:/var/local/repo ./' > /etc/apt/sources.list.d/local.list
    apt-get update -q >/dev/null 2>&1 || true
fi
# В Ubuntu Desktop этот файл пуст: NetworkManager управляет всеми картами.
: > /etc/NetworkManager/conf.d/10-globally-managed-devices.conf
systemctl restart NetworkManager
"""
        )
        if os.environ.get("XGW_MACHINE_PREINSTALL_DNSMASQ") == "1":
            # Изобразить хост, на котором пакет dnsmasq уже стоит (так было на настоящей
            # машине после удаления XGW: пакеты удаление не трогает). Служба со своим
            # конфигом по умолчанию может и не запуститься — порт 53 занят резолвером.
            self.sh(
                "DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "
                "dnsmasq >/dev/null 2>&1 || true"
            )
        self._forget_host_xgw()
        self._wait_nm()
        self.sh(
            f"""
set -e
nmcli connection add type ethernet con-name stand-wan ifname wan0 \\
    ipv4.method manual ipv4.addresses {netns.GW_WAN_IP}/24 ipv4.gateway {netns.INET_IP} \\
    ipv6.method auto connection.autoconnect-priority 10 >/dev/null
nmcli connection add type ethernet con-name old-lan ifname lan0 ipv4.method auto \\
    connection.autoconnect-priority 10 >/dev/null
nmcli --wait 20 connection up stand-wan >/dev/null
"""
        )
        if ufw and self.run("bash", "-c", "command -v ufw", check=False).returncode == 0:
            # reload — чтобы набор правил ufw был в том же виде, что и после любой
            # его перезагрузки: по нему сверяется состояние до установки и после удаления.
            self.sh("ufw --force enable >/dev/null && ufw reload >/dev/null")

    def _forget_host_xgw(self) -> None:
        """То, что XGW хоста оставил вне своих каталогов и что убирается командами:
        правила ufw для его карты LAN и пользователь xray. И dnsmasq: если пакет уже
        стоит (достался от хоста), служба выключается — как на машине, где его
        поставили, но не настраивали; установке XGW тогда ставить нечего."""
        for rule in self.host_journal.get("ufw") or []:
            if isinstance(rule, list) and all(isinstance(item, str) for item in rule):
                routed = rule[:1] == ["route"]
                args = ["route", "delete", *rule[1:]] if routed else ["delete", *rule]
                self.run("ufw", *args, check=False, timeout=60)
        if self.host_journal.get("user_created"):
            self.run("userdel", "xray", check=False)
        installed = self.run(
            "dpkg-query", "-W", "-f=${Status}", "dnsmasq", check=False
        ).stdout
        self.dnsmasq_preinstalled = "ok installed" in installed
        if self.dnsmasq_preinstalled:
            self.run("systemctl", "disable", "--now", "dnsmasq.service", check=False)

    def _wait_nm(self, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            shown = self.run("nmcli", "-t", "-f", "RUNNING", "general", check=False)
            if shown.stdout.strip() == "running":
                return
            time.sleep(0.5)
        raise RuntimeError("NetworkManager в контейнере не запустился")
