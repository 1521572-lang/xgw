"""Туннельный бэкенд бесплатного пула со стороны демона (веха М2а; с М2в туннель — SSTP вместо
OpenVPN, docs/FREEPOOL-PLAN.md).

Поколение — одна служба xgw-fp@<gen> (агент в своём пространстве имён, agent.py) и пара veth.
Демон (хост, CAP_NET_ADMIN) делает то, что вне пространства имён агента:

  • задание поколения — /run/xgw/fp/<gen>/manifest.json (root, 0600): адрес, порт и имя
    сервера SSTP, общий вход источника, пароль SOCKS;
  • адрес сервера в наборе fp_peers таблицы ip xgw (адрес . протокол . порт): из fpv* в
    интернет — только к нему (net/nft.py); список — /run/xgw/fp/peers.json, чтобы полная
    перезагрузка таблицы его не потеряла;
  • veth fpv<idx> ↔ fpi<idx>: внутренний конец уходит в пространство имён агента по его PID
    (`ip link set … netns <pid>` — без setns, демону хватает CAP_NET_ADMIN; проверено в WSL);
  • счётчики fpv<idx> — внешний трафик поколения вместе с рукопожатием (R28).

Остановка службы уничтожает пространство имён, а с ним и veth (проверено). Перед каждой
проверкой и при запуске демона reconcile убирает то, что осталось от прошлых: службы xgw-fp@*,
интерфейсы fpv*, адреса в fp_peers, каталоги /run/xgw/fp/*.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..net import cmd
from ..paths import Paths, atomic_write_json
from . import agent as agenting

UNIT = "xgw-fp@{gen}.service"
UNIT_FILE = "xgw-fp@.service"
# Пакет Ubuntu sstp-client (тянет ppp): sstpc, pppd и модуль pppd для ключей MS-CHAPv2 — в
# каталоге модулей своей версии pppd.
SSTPC_BIN = Path("/usr/sbin/sstpc")
PPPD_BIN = Path("/usr/sbin/pppd")
PPPD_PLUGINS = Path("/usr/lib/pppd")
PLUGIN = "sstp-pppd-plugin.so"
PPP_DEVICE = Path("/dev/ppp")  # создаёт kmod-static-nodes; модуль ppp_generic ядро грузит само
START_WAIT = 10.0
# Сверх срока агента: veth, самопроверка, проверка изнутри (INNER_WAIT 12 с) и запуск
# работника (SOCKS_WAIT 5 с). Отчёт М2а.1: в коммит М2а.1 не попало — оставалось 20 с.
UP_MARGIN = 35.0
TABLE = "xgw"
PEERS_SET = "fp_peers"


class BackendError(Exception):
    """Поколение не подготовлено; code — причина (как у агента), текст — без секретов."""

    def __init__(self, code: str, text: str = "") -> None:
        super().__init__(text or code)
        self.code = code


@dataclass
class Lease:
    """Поколение, которое демон поднял: имя, номер veth, адрес сервера."""

    gen: str
    index: int
    peer: str
    port: int
    proto: str = "tcp"  # SSTP — только TCP (TLS)
    started: float = 0.0
    pid: int = 0
    socks_pass: str = ""

    @property
    def unit(self) -> str:
        return UNIT.format(gen=self.gen)

    @property
    def element(self) -> str:
        return f"{self.peer} . {self.proto} . {self.port}"


def peers_file(paths: Paths) -> Path:
    return paths.run / "fp" / "peers.json"


def peer_elements(paths: Paths) -> tuple[str, ...]:
    """Элементы fp_peers для полной перезагрузки таблицы (Capture.rules)."""
    try:
        data = json.loads(peers_file(paths).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    found = []
    for item in data.get("peers") or []:
        if isinstance(item, str) and re.fullmatch(
                r"\d{1,3}(?:\.\d{1,3}){3} \. (tcp|udp) \. \d{1,5}", item):
            found.append(item)
    return tuple(dict.fromkeys(found))


def unavailable(paths: Paths, runner: cmd.Runner, *, sstpc: Path = SSTPC_BIN,
                pppd: Path = PPPD_BIN, plugins: Path = PPPD_PLUGINS,
                ppp_device: Path = PPP_DEVICE, users: Callable[[str], object] | None = None,
                proc_sys: Path = Path("/proc/sys")) -> str:
    """Почему бэкенд SSTP сейчас не годится; пусто — годится. Без sstpc, pppd и его модуля
    sstp-pppd-plugin.so, /dev/ppp, пользователей работников, файла службы, пересылки IPv4
    (трафик туннеля идёт из fpv* в WAN через хост) или набора fp_peers в загруженной таблице
    XGW (без него из fpv* ничего не выйдет) проверять нечем."""
    if not sstpc.exists() or not pppd.exists():
        return "нет клиента SSTP (пакет sstp-client — ставит xgw install)"
    if not any(plugins.glob(f"*/{PLUGIN}")):
        return f"нет модуля pppd {PLUGIN} (пакет sstp-client)"
    if not ppp_device.exists():
        return "нет устройства /dev/ppp (модуль ядра ppp_generic)"
    lookup = users or _getpwnam
    for name in (agenting.VPN_USER, agenting.SOCKS_USER):
        try:
            lookup(name)
        except KeyError:
            return f"нет пользователя {name} (создаёт xgw install)"
    if not (paths.systemd_dir / UNIT_FILE).exists():
        return f"нет службы {UNIT_FILE} (ставит xgw install)"
    try:
        forwarding = (proc_sys / "net/ipv4/ip_forward").read_text(encoding="ascii").strip()
    except OSError:
        forwarding = ""
    if forwarding != "1":
        # XGW включает её только шлюзу с сетью LAN (net/sysctl.py); машина без LAN — М2б.
        return "пересылка IPv4 выключена (у шлюза нет сети LAN) — туннелю нечем выйти в интернет"
    try:
        runner(["nft", "list", "set", "ip", TABLE, PEERS_SET], timeout=10.0)
    except cmd.CommandError:
        return "в правилах XGW нет набора fp_peers — перехват не загружен"
    return ""


def _getpwnam(name: str):
    import pwd

    return pwd.getpwnam(name)


class Backend:
    def __init__(self, paths: Paths, *, runner: cmd.Runner = cmd.run, logger=None,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 sys_net: Path = Path("/sys/class/net")) -> None:
        self.paths, self.runner, self.log = paths, runner, logger
        self.clock, self.sleep, self.sys_net = clock, sleep, sys_net
        self.leases: dict[str, Lease] = {}

    # --- набор fp_peers -------------------------------------------------------------------

    def _save_peers(self) -> None:
        atomic_write_json(peers_file(self.paths),
                          {"peers": sorted({lease.element for lease in self.leases.values()})},
                          mode=0o600)

    def _nft_element(self, verb: str, element: str) -> None:
        self.runner(["nft", verb, "element", "ip", TABLE, PEERS_SET, "{", element, "}"],
                    timeout=10.0, check=verb == "add")

    # --- поколение --------------------------------------------------------------------------

    def _index(self) -> int:
        used = {lease.index for lease in self.leases.values()}
        for index in range(agenting.INDEX_MIN, agenting.INDEX_MAX + 1):
            if index not in used and not (self.sys_net / agenting.host_link(index)).exists():
                return index
        raise BackendError("RESOURCE_LIMIT", "нет свободного номера veth")

    def prepare(self, *, peer: str, port: int, host: str, user: str, password: str,
                lan: tuple[str, ...], xray_bin: Path, sstpc_bin: Path = SSTPC_BIN) -> Lease:
        """Задание, адрес в fp_peers, veth, служба; возвращается сразу после запуска службы
        (подключение — wait)."""
        gen = secrets.token_hex(5)
        lease = Lease(gen=gen, index=self._index(), peer=peer, port=port,
                      socks_pass=secrets.token_urlsafe(24))
        directory = agenting.run_dir(self.paths, gen)
        directory.mkdir(parents=True, mode=0o700)
        directory.chmod(0o700)
        atomic_write_json(agenting.manifest_path(self.paths, gen), {
            "gen": gen, "index": lease.index, "peer": peer, "port": port, "host": host,
            "user": user, "password": password,
            "socks_pass": lease.socks_pass, "lan": list(lan),
            "xray_bin": str(xray_bin), "sstpc_bin": str(sstpc_bin),
        }, mode=0o600)
        self.leases[gen] = lease
        try:
            # Сначала — в peers.json: перезагрузка таблицы между двумя шагами иначе потеряла бы
            # элемент.
            self._save_peers()
            self._nft_element("add", lease.element)
            host, inner = agenting.host_link(lease.index), agenting.inner_link(lease.index)
            self.runner(["ip", "link", "add", host, "type", "veth", "peer", "name", inner],
                        timeout=10.0)
            self.runner(["ip", "addr", "add", f"{agenting.host_address(lease.index)}/30",
                         "dev", host], timeout=10.0)
            self.runner(["ip", "link", "set", "dev", host, "up"], timeout=10.0)
            self.runner(["systemctl", "start", lease.unit], timeout=30.0)
            lease.started = self.clock()
            lease.pid = self._main_pid(lease)
            # Переносить — только когда агент уже в своём пространстве имён: PID службы
            # известен сразу после fork, а пространство имён systemd создаёт чуть позже —
            # перенос «в пространство PID» тогда остался бы на хосте (так было на стенде).
            # Признак — фаза guarded: её агент пишет, уже поставив охрану у себя. Сравнить
            # /proc/<pid>/ns/net демон не может: у агента есть возможности, которых нет у
            # демона (CAP_CHOWN, CAP_KILL), и ядро такое чтение запрещает.
            self._wait_guarded(lease)
            self.runner(["ip", "link", "set", "dev", inner, "netns", str(lease.pid)],
                        timeout=10.0)
        except BackendError:
            # Агент отказал или не запустился: veth, адрес в fp_peers и каталог — убрать
            # сейчас, а не при следующем запуске демона.
            self.stop(lease)
            raise
        except (cmd.CommandError, OSError) as exc:
            self.stop(lease)
            raise BackendError("BACKEND_START", f"поколение не подготовлено: {exc}") from exc
        return lease

    def _main_pid(self, lease: Lease) -> int:
        deadline = self.clock() + START_WAIT
        while True:
            text = self.runner(["systemctl", "show", "-p", "MainPID", "--value", lease.unit],
                               timeout=10.0, check=False).strip()
            if text.isdigit() and int(text) > 1:
                return int(text)
            if self.clock() > deadline:
                raise BackendError("BACKEND_START", "служба поколения не запустилась")
            self.sleep(0.2)

    def _wait_guarded(self, lease: Lease) -> None:
        deadline = self.clock() + START_WAIT
        while True:
            phase = self.state(lease).get("phase")
            if phase in ("guarded", "connecting", "up"):
                return
            if phase == "failed" or self.clock() > deadline:
                state = self.state(lease)
                raise BackendError(str(state.get("reason") or "BACKEND_START"),
                                   "агент поколения не поставил охрану")
            self.sleep(0.1)

    def state(self, lease: Lease) -> dict:
        try:
            data = json.loads(agenting.state_path(self.paths, lease.gen).read_text(
                encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def wait(self, lease: Lease, *, cancel=None) -> dict:
        """Ждать, пока поколение поднимется (phase up) или откажет (failed); срок — срок
        агента плюс запас. Истёк — {"phase": "failed", "reason": "TIMEOUT"}."""
        deadline = lease.started + agenting.VETH_WAIT + agenting.UP_WAIT + UP_MARGIN
        while True:
            state = self.state(lease)
            if state.get("phase") in ("up", "failed", "stopped"):
                return state
            active = self.runner(["systemctl", "is-active", lease.unit], timeout=10.0,
                                 check=False).strip()
            if active in ("failed", "inactive") and state.get("phase") != "up":
                return {**state, "phase": "failed",
                        "reason": state.get("reason") or "AGENT_EXITED"}
            if self.clock() > deadline or (cancel is not None and cancel.is_set()):
                return {**state, "phase": "failed", "reason": state.get("reason") or "TIMEOUT"}
            self.sleep(0.5)

    def counters(self, lease: Lease) -> int:
        """Внешний трафик поколения (оба направления) по счётчикам fpv<idx>; 0 — нет."""
        base = self.sys_net / agenting.host_link(lease.index) / "statistics"
        total = 0
        for name in ("rx_bytes", "tx_bytes"):
            try:
                total += int((base / name).read_text(encoding="ascii").strip())
            except (OSError, ValueError):
                return 0
        return total

    def stop(self, lease: Lease) -> None:
        """Служба, veth, адрес в fp_peers, каталог. Ничто из этого не должно остаться и при
        сбое на полпути (ошибки — в журнал, дальше)."""
        for argv in (["systemctl", "stop", lease.unit], ["systemctl", "reset-failed", lease.unit],
                     ["ip", "link", "del", "dev", agenting.host_link(lease.index)]):
            try:
                self.runner(argv, timeout=30.0, check=False)
            except (cmd.CommandError, OSError) as exc:
                self._warn(f"{' '.join(argv[:2])}: {exc}")
        self.leases.pop(lease.gen, None)
        try:
            self._nft_element("delete", lease.element)
        except (cmd.CommandError, OSError) as exc:
            self._warn(f"адрес сервера не убран из fp_peers: {exc}")
        try:
            self._save_peers()
        except OSError as exc:
            self._warn(f"peers.json не записан: {exc}")
        shutil.rmtree(agenting.run_dir(self.paths, lease.gen), ignore_errors=True)

    def reconcile(self) -> int:
        """Убрать следы поколений, которых демон не ведёт (после перезапуска демона или
        сбоя): службы, veth, адреса, каталоги. Сколько убрано."""
        removed = 0
        text = self.runner(["systemctl", "list-units", "--all", "--plain", "--no-legend",
                            "xgw-fp@*.service"], timeout=20.0, check=False)
        for line in text.splitlines():
            unit = line.split()[0] if line.split() else ""
            match = re.fullmatch(r"xgw-fp@([0-9a-f]{10})\.service", unit)
            if match and match.group(1) not in self.leases:
                self.runner(["systemctl", "stop", unit], timeout=30.0, check=False)
                self.runner(["systemctl", "reset-failed", unit], timeout=10.0, check=False)
                removed += 1
        ours = {agenting.host_link(lease.index) for lease in self.leases.values()}
        if self.sys_net.exists():
            for entry in self.sys_net.iterdir():
                if re.fullmatch(r"fpv\d{1,2}", entry.name) and entry.name not in ours:
                    self.runner(["ip", "link", "del", "dev", entry.name], timeout=10.0,
                                check=False)
                    removed += 1
        base = self.paths.run / "fp"
        if base.exists():
            for entry in base.iterdir():
                if entry.is_dir() and agenting.GEN_RE.fullmatch(entry.name) \
                        and entry.name not in self.leases:
                    shutil.rmtree(entry, ignore_errors=True)
        wanted = {lease.element for lease in self.leases.values()}
        if not wanted:
            self.runner(["nft", "flush", "set", "ip", TABLE, PEERS_SET], timeout=10.0,
                        check=False)
        if base.exists() or wanted:
            try:
                self._save_peers()
            except OSError as exc:
                self._warn(f"peers.json не записан: {exc}")
        return removed

    def _warn(self, text: str) -> None:
        if self.log is not None:
            self.log.warning("бесплатный пул: %s", text)
