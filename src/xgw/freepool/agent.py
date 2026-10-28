"""Агент бесплатного сервера OpenVPN (веха М2а): процесс службы xgw-fp@<gen>.

Демон запускает службу с PrivateNetwork=yes: у агента своё пространство имён сети, в нём
только lo. Возможности — CAP_NET_ADMIN (правила, адреса и маршруты своего пространства),
CAP_SETUID и CAP_SETGID (работники — от своих пользователей), CAP_CHOWN (файлы работников),
CAP_KILL (их остановка: uid другой); NoNewPrivileges. По шагам:

1. охрана nftables (таблица inet xgwfp, guard_rules): ввод, вывод и форвардинг закрыты,
   открыто только перечисленное там, — раньше, чем появится хоть один маршрут;
2. постоянный TUN fpt0 с владельцем xgw-ovpn (`ip tuntap add … user`): работник OpenVPN
   подключается к нему без возможностей, а создать другое устройство не может (проверено в
   пространстве имён WSL);
3. veth: демон создаёт пару fpv<idx>/fpi<idx> и переносит fpi<idx> сюда по PID агента; агент
   ставит 10.250.<idx>.2/30 и маршрут только к адресу сервера (/32 через хост);
4. самопроверка охраны (R46, «самый важный тест»): при живом маршруте к серверу и без
   туннеля пользователь SOCKS к серверу и наружу не выходит, пользователь OpenVPN — к хосту и
   наружу, кроме сервера; не так — GUARD_FAILED, работники не запускаются;
5. SOCKS-работник (Xray от xgw-fps) и OpenVPN (от xgw-ovpn): конфиги — в /tmp службы
   (PrivateTmp — у каждого поколения свой), root:<группа работника>, 0640;
6. интерфейс управления OpenVPN (127.0.0.1 в своём пространстве): CONNECTED — адрес туннеля
   на fpt0 и маршрут по умолчанию в fpt0; RECONNECTING, EXITING и прочие — маршрут убран;
7. состояние — /run/xgw/fp/<gen>/state.json (его читает демон). SIGTERM — работники
   останавливаются, пространство имён исчезает вместе со службой, а с ним и veth.

Строки журнала OpenVPN в журнал службы не пишутся: в состоянии — только коды причин
(classify). Исключение — при отказе одна строка, по которой он распознан, с адресами IPv4,
заменёнными на <ip> (evidence): без неё отказ на машине заказчика не разобрать.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import select
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..net import cmd
from ..paths import Paths, atomic_write_json
from .ovpn import OvpnRejected
from .ovpnconf import AUTH_FILE, TUN, peer_address

GEN_RE = re.compile(r"[0-9a-f]{10}")
INDEX_MIN, INDEX_MAX = 1, 63
SUBNET = "10.250.0.0/16"
SOCKS_PORT = 1080
MGMT_PORT = 7505
SOCKS_USER_NAME = "xgw"
OVPN_USER, SOCKS_USER = "xgw-ovpn", "xgw-fps"
OVPN_DIR, SOCKS_DIR = "/tmp/xgw-ovpn", "/tmp/xgw-socks"
TABLE = "xgwfp"
VETH_WAIT = 20.0  # сколько ждать внутренний конец veth от демона
UP_WAIT = 45.0  # подключение OpenVPN вместе с рукопожатием (R54: холодный кандидат — 45 с)
RECONNECT_WAIT = 60.0  # после обрыва: не вернулся — отказ, а не вечные попытки
MGMT_WAIT = 10.0
STOP_WAIT = 5.0
LOG_LINES = 60
MAX_MANIFEST = 512 * 1024

# Строки журнала OpenVPN 2.6 → причина (ТЗ R31, R42). Порядок важен: первая найденная.
_CAUSES = (
    ("AUTH_FAILED", ("AUTH_FAILED", "auth-failure")),
    ("CONFIG_REJECTED", ("Options error", "Unrecognized option")),
    ("TUN_FAILED", ("Cannot open TUN/TAP", "TUNSETIFF", "Cannot ioctl")),
    ("UNSUPPORTED_CRYPTO", ("md too weak", "key too small", "Unsupported cipher",
                            "unsupported certificate", "no shared cipher")),
    ("CERT_VERIFY_FAILED", ("VERIFY ERROR", "certificate verify failed", "VERIFY X509NAME",
                            "VERIFY KU ERROR", "VERIFY EKU ERROR")),
    ("CONNECT_REFUSED", ("Connection refused",)),
    ("CONNECT_TIMEOUT", ("Connection timed out", "server-poll-timeout")),
    ("TLS_HANDSHAKE_FAILED", ("TLS key negotiation failed", "TLS handshake failed",
                              "TLS Error")),
    ("TRANSPORT_RESET", ("Connection reset", "connection-reset")),
    ("NETWORK_UNREACHABLE", ("Network is unreachable", "No route to host")),
)
_STATE = re.compile(r"^(?:>STATE:)?(\d+),([A-Z_]+),([^,]*),?([^,]*),?([^,]*)")
_PUSH_IFCONFIG = re.compile(r"PUSH_REPLY.*?\bifconfig (\d{1,3}(?:\.\d{1,3}){3}) ")
_PUSH_MTU = re.compile(r"PUSH_REPLY.*?\btun-mtu (\d{3,5})\b")
_IPV4_ANY = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


class AgentError(Exception):
    """Поколение не поднялось; code — причина для демона, текст — без секретов."""

    def __init__(self, code: str, text: str = "") -> None:
        super().__init__(text or code)
        self.code = code


@dataclass(frozen=True)
class Manifest:
    """Задание поколения от демона (/run/xgw/fp/<gen>/manifest.json, root, 0600)."""

    gen: str
    index: int
    peer: str
    proto: str
    port: int
    openvpn_conf: str
    auth: str  # содержимое auth-user-pass или ""
    socks_pass: str
    lan: tuple[str, ...]  # сети, с которыми адрес туннеля не должен пересекаться
    xray_bin: str
    openvpn_bin: str


def host_address(index: int) -> str:
    return f"10.250.{index}.1"


def inner_address(index: int) -> str:
    return f"10.250.{index}.2"


def host_link(index: int) -> str:
    return f"fpv{index}"


def inner_link(index: int) -> str:
    return f"fpi{index}"


def run_dir(paths: Paths, gen: str) -> Path:
    return paths.run / "fp" / gen


def manifest_path(paths: Paths, gen: str) -> Path:
    return run_dir(paths, gen) / "manifest.json"


def state_path(paths: Paths, gen: str) -> Path:
    return run_dir(paths, gen) / "state.json"


def load_manifest(path: Path, gen: str) -> Manifest:
    """Задание с проверкой каждого поля: агент — root, а значения уходят в ip, nft и конфиги."""
    if not GEN_RE.fullmatch(gen):
        raise AgentError("BAD_MANIFEST", "имя поколения не то")
    try:
        if path.stat().st_size > MAX_MANIFEST:
            raise AgentError("BAD_MANIFEST", "задание слишком большое")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AgentError("BAD_MANIFEST", f"задание не читается: {type(exc).__name__}") from exc
    try:
        manifest = Manifest(
            gen=str(data["gen"]), index=int(data["index"]), peer=str(data["peer"]),
            proto=str(data["proto"]), port=int(data["port"]),
            openvpn_conf=str(data["openvpn_conf"]), auth=str(data.get("auth") or ""),
            socks_pass=str(data["socks_pass"]),
            lan=tuple(str(item) for item in data.get("lan") or ()),
            xray_bin=str(data["xray_bin"]), openvpn_bin=str(data["openvpn_bin"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AgentError("BAD_MANIFEST", f"в задании нет поля или оно не того вида: {exc}") from exc
    problems = []
    if manifest.gen != gen:
        problems.append("поколение не совпадает")
    if not INDEX_MIN <= manifest.index <= INDEX_MAX:
        problems.append("номер veth вне диапазона")
    try:
        peer_address(manifest.peer)
    except OvpnRejected as exc:
        problems.append(str(exc))
    if manifest.proto not in ("tcp", "udp") or not 0 < manifest.port < 65536:
        problems.append("протокол или порт сервера")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", manifest.socks_pass):
        problems.append("пароль SOCKS")
    for binary in (manifest.xray_bin, manifest.openvpn_bin):
        if not binary.startswith("/") or ".." in binary:
            problems.append("путь программы")
    for network in manifest.lan:
        try:
            ipaddress.IPv4Network(network, strict=False)
        except ValueError:
            problems.append("сеть LAN")
    if not manifest.openvpn_conf or "\x00" in manifest.openvpn_conf:
        problems.append("конфиг OpenVPN")
    if problems:
        raise AgentError("BAD_MANIFEST", "; ".join(problems))
    return manifest


def guard_rules(manifest: Manifest, ovpn_uid: int, socks_uid: int) -> str:
    """Охрана пространства имён (R46). Вывод: lo — только root (агент) и OpenVPN (к своему
    интерфейсу управления); OpenVPN — только к адресу, протоколу и порту сервера через veth;
    SOCKS-работник — только в туннель (IPv4) и ответами на подключения хоста к своему порту.
    Ввод: lo, ответы на свои соединения и подключение хоста к SOCKS. Форвардинга нет вовсе.
    Новые входящие из туннеля (сервер VPN к агенту, к SOCKS, к управлению) — закрыты."""
    inner, host = inner_link(manifest.index), host_address(manifest.index)
    me = inner_address(manifest.index)
    return "\n".join((
        f"table inet {TABLE}",
        f"delete table inet {TABLE}",
        f"table inet {TABLE} {{",
        "    counter refused_out { }",
        "    chain input {",
        "        type filter hook input priority filter; policy drop;",
        '        iif "lo" accept',
        "        ct state established,related accept",
        f'        iifname "{inner}" ip saddr {host} ip daddr {me} meta l4proto {{ tcp, udp }} '
        f"th dport {SOCKS_PORT} accept",
        "    }",
        "    chain output {",
        "        type filter hook output priority filter; policy drop;",
        f'        oif "lo" meta skuid {{ 0, {ovpn_uid} }} accept',
        # Ответ отказа (reject ниже) ядро шлёт отправителю через lo, без сокета: без этого
        # правила охрана отбросила бы и его, и отказ превратился бы в таймаут.
        '        oif "lo" icmp type destination-unreachable accept',
        f'        meta skuid {ovpn_uid} oifname "{inner}" ip daddr {manifest.peer} '
        f"meta l4proto {manifest.proto} th dport {manifest.port} accept",
        f'        meta skuid {socks_uid} oifname "{TUN}" meta nfproto ipv4 accept',
        f'        meta skuid {socks_uid} oifname "{inner}" ip daddr {host} ct state established '
        "accept",
        f'        oifname "{inner}" ip daddr {host} icmp type {{ destination-unreachable, '
        "time-exceeded } accept",
        # Отказ, а не тихий сброс: работник узнаёт сразу, а самопроверка отличает «закрыто
        # охраной» от «пакет ушёл и не ответили» (TCP при drop ждал бы до таймаута).
        '        counter name "refused_out" reject with icmpx type admin-prohibited',
        "    }",
        "    chain forward {",
        "        type filter hook forward priority filter; policy drop;",
        "    }",
        "}",
    )) + "\n"


def socks_config(manifest: Manifest) -> dict:
    """SOCKS-работник: Xray, socks с паролем на внутреннем адресе veth (TCP и UDP), выход —
    freedom по маршруту по умолчанию (он есть только в туннель), DNS — серверы через туннель
    (системного резолвера в пространстве имён нет). Проверено xray run -test (26.10.21)."""
    me = inner_address(manifest.index)
    return {
        "log": {"loglevel": "warning"},
        "dns": {"servers": ["1.1.1.1", "8.8.8.8"], "queryStrategy": "UseIPv4"},
        "inbounds": [{
            "tag": "socks-in", "protocol": "socks", "listen": me, "port": SOCKS_PORT,
            "settings": {
                "auth": "password",
                "accounts": [{"user": SOCKS_USER_NAME, "pass": manifest.socks_pass}],
                "udp": True, "ip": me,
            },
        }],
        "outbounds": [{
            "tag": "tunnel", "protocol": "freedom",
            "streamSettings": {"sockopt": {"domainStrategy": "UseIPv4"}},
        }],
    }


def parse_state(line: str) -> tuple[str, str, str] | None:
    """Строка состояния интерфейса управления (`>STATE:` или ответ на `state`): время,
    состояние, описание, адрес TUN, адрес сервера… → (состояние, описание, адрес TUN)."""
    match = _STATE.match(line.strip())
    if not match:
        return None
    return match.group(2), match.group(3), match.group(4)


def pushed(line: str) -> tuple[str, int]:
    """Из строки журнала с PUSH_REPLY: адрес туннеля и MTU, если сервер их прислал."""
    address = _PUSH_IFCONFIG.search(line)
    mtu = _PUSH_MTU.search(line)
    return (address.group(1) if address else ""), (int(mtu.group(1)) if mtu else 0)


def tunnel_problem(address: str, manifest: Manifest) -> str:
    """Адрес туннеля от сервера недоверенный (R45): только частный IPv4, не из сети veth, не
    из LAN и не служебный. Пусто — годится."""
    try:
        ip = ipaddress.IPv4Address(address)
    except ValueError:
        return "адрес туннеля — не IPv4"
    if not ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
        return "адрес туннеля — не частный"
    if ip in ipaddress.IPv4Network(SUBNET):
        return "адрес туннеля пересекается с сетью veth"
    for network in manifest.lan:
        if ip in ipaddress.IPv4Network(network, strict=False):
            return "адрес туннеля пересекается с LAN"
    return ""


def classify(lines) -> str:
    """Причина отказа по журналу OpenVPN; UNKNOWN — не распознана."""
    text = "\n".join(lines)
    for code, needles in _CAUSES:
        if any(needle in text for needle in needles):
            return code
    return "UNKNOWN"


def evidence(lines, code: str) -> str:
    """Строка журнала OpenVPN, по которой распознана причина code, — без адресов IPv4 и не
    длиннее 200 знаков; пусто — такой нет."""
    needles = dict(_CAUSES).get(code, ())
    for line in lines:
        if any(needle in line for needle in needles):
            return _IPV4_ANY.sub("<ip>", line.strip())[:200]
    return ""


# Самопроверка охраны: дочерний процесс от пользователя работника пытается открыть TCP.
_PROBE = (
    "import errno,socket,sys\n"
    "s=socket.socket()\n"
    "s.settimeout(2)\n"
    "try:\n"
    "    s.connect((sys.argv[1],int(sys.argv[2])))\n"
    "    print('OPEN')\n"
    "except OSError as e:\n"
    "    print(errno.errorcode.get(e.errno,'TIMEOUT') if e.errno else 'TIMEOUT')\n"
)
# Закрыто: нет маршрута (ENETUNREACH) — само по себе; остальное — только если вырос счётчик
# отбитого охраной (refused_out): иначе пакет мог уйти.
NO_ROUTE = "ENETUNREACH"
REJECTED = ("EPERM", "EACCES", "EHOSTUNREACH", "ECONNREFUSED", "EHOSTDOWN")
_PACKETS = re.compile(r"packets (\d+)")


class Agent:
    def __init__(
        self, paths: Paths, gen: str, *, runner: cmd.Runner = cmd.run,
        spawn: Callable[..., subprocess.Popen] = subprocess.Popen,
        connect: Callable[..., socket.socket] = socket.create_connection,
        users: Callable[[str], tuple[int, int]] | None = None,
        clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
        tmp: Path = Path("/tmp"), out=sys.stdout,
    ) -> None:
        self.paths, self.gen = paths, gen
        self.runner, self.spawn, self.connect = runner, spawn, connect
        self.users = users or _user_ids
        self.clock, self.sleep = clock, sleep
        self.tmp, self.out = tmp, out
        self.stop = threading.Event()
        self.children: dict[str, subprocess.Popen] = {}
        self.log: deque[str] = deque(maxlen=LOG_LINES)
        self.pushed_address, self.pushed_mtu = "", 0
        self.state: dict = {"gen": gen, "phase": "starting", "since": time.time()}
        self.manifest: Manifest | None = None

    # --- состояние для демона --------------------------------------------------------------

    def _write(self, **values) -> None:
        self.state.update(values, updated=time.time())
        try:
            atomic_write_json(state_path(self.paths, self.gen), self.state, mode=0o600)
        except OSError as exc:  # демон тогда увидит истёкший срок, а причину — журнал службы
            print(f"состояние не записано: {exc}", file=self.out, flush=True)

    def _say(self, text: str) -> None:
        print(text, file=self.out, flush=True)

    # --- шаги -----------------------------------------------------------------------------

    def _ip(self, *args: str, check: bool = True) -> str:
        return self.runner(["ip", *args], timeout=10.0, check=check)

    def _guard(self, manifest: Manifest, ovpn_uid: int, socks_uid: int) -> None:
        self._ip("link", "set", "lo", "up")
        self.runner(["nft", "-f", "-"], input=guard_rules(manifest, ovpn_uid, socks_uid),
                    timeout=10.0)

    def _tun(self, ovpn_uid: int, ovpn_gid: int) -> None:
        self._ip("tuntap", "add", "dev", TUN, "mode", "tun", "user", str(ovpn_uid),
                 "group", str(ovpn_gid))

    def _veth(self, manifest: Manifest) -> None:
        name = inner_link(manifest.index)
        deadline = self.clock() + VETH_WAIT
        while True:
            if self._ip("-o", "link", "show", "dev", name, check=False).strip():
                break
            if self.stop.is_set():
                raise AgentError("STOPPED", "остановлен до подключения")
            if self.clock() > deadline:
                raise AgentError("NO_VETH", "демон не передал veth")
            self.sleep(0.2)
        self._ip("addr", "add", f"{inner_address(manifest.index)}/30", "dev", name)
        self._ip("link", "set", "dev", name, "up")
        self._ip("route", "add", f"{manifest.peer}/32", "via", host_address(manifest.index),
                 "dev", name)

    def _probe(self, uid: int, gid: int, address: str, port: int) -> str:
        proc = self.spawn(
            [sys.executable, "-I", "-c", _PROBE, address, str(port)], user=uid, group=gid,
            extra_groups=[], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, close_fds=True,
        )
        try:
            out, _err = proc.communicate(timeout=10.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return "TIMEOUT"
        return (out or "").strip() or "TIMEOUT"

    def _selftest(self, manifest: Manifest, ids: dict[str, tuple[int, int]]) -> dict:
        """R46: SOCKS к серверу (маршрут /32 есть, туннеля нет) и наружу, OpenVPN к хосту и
        наружу, SOCKS к интерфейсу управления — всё должно быть закрыто."""
        socks, ovpn = ids["socks"], ids["ovpn"]
        cases = {
            "socks_to_peer": (socks, manifest.peer, manifest.port),
            "socks_to_internet": (socks, "1.1.1.1", 443),
            "socks_to_mgmt": (socks, "127.0.0.1", MGMT_PORT),
            "ovpn_to_host": (ovpn, host_address(manifest.index), 22),
            "ovpn_to_internet": (ovpn, "1.1.1.1", 443),
        }
        results: dict[str, str] = {}
        bad: list[str] = []
        for name, (who, address, port) in cases.items():
            before = self._refused()
            result = self._probe(*who, address, port)
            counted = self._refused() > before
            results[name] = result + (" (охрана)" if counted else "")
            if not (result == NO_ROUTE or (result in REJECTED and counted)):
                bad.append(name)
        self._write(selftest={"results": results, "ok": not bad})
        self._say("охрана проверена: " + ", ".join(f"{name} {value}"
                                                   for name, value in results.items()))
        if bad:
            raise AgentError("GUARD_FAILED", "охрана пропускает: " + ", ".join(bad))
        return results

    def _refused(self) -> int:
        text = self.runner(["nft", "list", "counter", "inet", TABLE, "refused_out"],
                           timeout=10.0, check=False)
        match = _PACKETS.search(text)
        return int(match.group(1)) if match else -1

    def _files(self, manifest: Manifest, ids: dict[str, tuple[int, int]]) -> tuple[Path, Path]:
        ovpn_dir = self.tmp / Path(OVPN_DIR).name
        socks_dir = self.tmp / Path(SOCKS_DIR).name
        files = [(ovpn_dir, ids["ovpn"][1], {"client.conf": manifest.openvpn_conf}),
                 (socks_dir, ids["socks"][1],
                  {"socks.json": json.dumps(socks_config(manifest), ensure_ascii=False)})]
        if manifest.auth:
            files[0][2]["auth"] = manifest.auth
        for directory, gid, content in files:
            directory.mkdir(mode=0o750, exist_ok=True)
            os.chown(directory, 0, gid)
            directory.chmod(0o750)
            for name, text in content.items():
                path = directory / name
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(text)
                os.chown(path, 0, gid)
                path.chmod(0o640)
        return ovpn_dir / "client.conf", socks_dir / "socks.json"

    def _start(self, name: str, argv: list[str], ids: tuple[int, int]) -> subprocess.Popen:
        proc = self.spawn(
            argv, user=ids[0], group=ids[1], extra_groups=[], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, close_fds=True,
            start_new_session=True,
        )
        self.children[name] = proc
        return proc

    def _read_openvpn(self, proc: subprocess.Popen) -> None:
        for line in proc.stdout or ():
            line = line.rstrip("\n")
            self.log.append(line)
            address, mtu = pushed(line)
            if address:
                self.pushed_address = address
            if mtu:
                self.pushed_mtu = mtu

    def _drain(self, proc: subprocess.Popen) -> None:
        for _line in proc.stdout or ():
            pass  # предупреждения Xray: журнал службы не засоряется

    def _up(self, address: str, manifest: Manifest) -> None:
        problem = tunnel_problem(address, manifest)
        if problem:
            raise AgentError("BAD_TUNNEL_ADDRESS", problem)
        mtu = self.pushed_mtu if 576 <= self.pushed_mtu <= 1500 else 1500
        self._ip("addr", "flush", "dev", TUN)
        self._ip("addr", "add", f"{address}/32", "dev", TUN)
        self._ip("link", "set", "dev", TUN, "mtu", str(mtu), "up")
        self._ip("route", "replace", "default", "dev", TUN)
        self._write(phase="up", tunnel=address, mtu=mtu, up_at=time.time())
        self._say(f"туннель поднят, MTU {mtu}")

    def _down(self, why: str) -> None:
        self._ip("route", "del", "default", "dev", TUN, check=False)
        self._ip("addr", "flush", "dev", TUN, check=False)
        self._write(phase="reconnecting", why=why)

    def _manage(self, manifest: Manifest) -> None:
        """Цикл интерфейса управления, пока не попросили остановиться."""
        deadline = self.clock() + MGMT_WAIT
        sock = None
        while sock is None:
            try:
                sock = self.connect(("127.0.0.1", MGMT_PORT), 2.0)
            except OSError:
                if self.clock() > deadline or self._dead("openvpn"):
                    raise AgentError(classify(self.log) if self.log else "NO_MANAGEMENT",
                                     "интерфейс управления OpenVPN не ответил") from None
                self.sleep(0.3)
        sock.setblocking(False)
        sock.sendall(b"state on\nstate\n")
        buffer = b""
        up = False
        started = self.clock()
        lost_at: float | None = None
        try:
            while not self.stop.is_set():
                ready, _w, _x = select.select([sock], [], [], 1.0)
                if ready:
                    chunk = sock.recv(4096)
                    if not chunk:
                        if self.stop.is_set():
                            return  # остановка: OpenVPN закрылся вместе со службой
                        raise AgentError(classify(self.log), "OpenVPN закрыл управление")
                    buffer += chunk
                    while b"\n" in buffer:
                        raw, buffer = buffer.split(b"\n", 1)
                        line = raw.decode("utf-8", "replace").strip()
                        if line.startswith(">FATAL:"):
                            raise AgentError(classify([*self.log, line]), "OpenVPN: FATAL")
                        if line.startswith(">PASSWORD:Verification Failed"):
                            raise AgentError("AUTH_FAILED", "учётка не принята")
                        parsed = parse_state(line)
                        if parsed is None:
                            continue
                        name, _desc, address = parsed
                        if name == "CONNECTED":
                            # Адреса в строке состояния нет — берём из PUSH_REPLY журнала: его
                            # читает другой поток, строка может отстать на мгновение.
                            waited = self.clock() + 2.0
                            while not address and not self.pushed_address \
                                    and self.clock() < waited:
                                self.sleep(0.1)
                            address = address or self.pushed_address
                            if not address:
                                raise AgentError("NO_TUNNEL_ADDRESS",
                                                 "OpenVPN не сообщил адрес туннеля")
                            self._up(address, manifest)
                            up, lost_at = True, None
                        elif name in ("RECONNECTING", "EXITING") and up:
                            self._down(name)
                            up, lost_at = False, self.clock()
                        else:
                            self._write(phase="up" if up else "connecting", openvpn=name)
                if self.stop.is_set():
                    return
                if self._dead("openvpn"):
                    raise AgentError(classify(self.log), "OpenVPN завершился")
                if self._dead("socks"):
                    raise AgentError("SOCKS_FAILED", "SOCKS-работник завершился")
                now = self.clock()
                if not up and lost_at is None and now - started > UP_WAIT:
                    raise AgentError(classify(self.log) if self.log else "TIMEOUT",
                                     "туннель не поднялся за отведённое время")
                if lost_at is not None and now - lost_at > RECONNECT_WAIT:
                    raise AgentError(classify(self.log), "туннель не вернулся после обрыва")
        finally:
            sock.close()

    def _dead(self, name: str) -> bool:
        proc = self.children.get(name)
        return proc is not None and proc.poll() is not None

    def _stop_children(self) -> None:
        """Работников — SIGTERM, затем SIGKILL. Сигнал не прошёл (нет CAP_KILL) — их добьёт
        systemd после выхода агента (KillMode=mixed); это не повод не убрать маршрут."""
        for proc in self.children.values():
            if proc.poll() is None:
                try:
                    proc.terminate()
                except OSError as exc:
                    self._say(f"работник не остановлен сигналом: {exc.strerror}")
        for proc in self.children.values():
            try:
                proc.wait(timeout=STOP_WAIT)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    proc.wait(timeout=STOP_WAIT)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    self._say(f"работник не остановлен: {exc}")

    def run(self) -> int:
        try:
            manifest = load_manifest(manifest_path(self.paths, self.gen), self.gen)
            self.manifest = manifest
            ids = {"ovpn": self.users(OVPN_USER), "socks": self.users(SOCKS_USER)}
            self._guard(manifest, ids["ovpn"][0], ids["socks"][0])
            self._tun(*ids["ovpn"])
            self._write(phase="guarded")
            self._veth(manifest)
            self._selftest(manifest, ids)
            conf, socks = self._files(manifest, ids)
            proc = self._start("socks", [manifest.xray_bin, "run", "-c", str(socks)],
                               ids["socks"])
            threading.Thread(target=self._drain, args=(proc,), daemon=True).start()
            proc = self._start("openvpn", [manifest.openvpn_bin, "--config", str(conf)],
                               ids["ovpn"])
            threading.Thread(target=self._read_openvpn, args=(proc,), daemon=True).start()
            self._write(phase="connecting")
            self._manage(manifest)
            self._write(phase="stopped")
            return 0
        except AgentError as exc:
            self._write(phase="failed", reason=exc.code, detail=str(exc)[:200])
            self._say(f"поколение {self.gen}: {exc.code} — {exc}")
            line = evidence(list(self.log), exc.code)
            if line:
                self._say(f"OpenVPN: {line}")
            return 3
        except (OSError, cmd.CommandError, subprocess.SubprocessError) as exc:
            self._write(phase="failed", reason="AGENT_ERROR", detail=type(exc).__name__)
            self._say(f"поколение {self.gen}: ошибка агента — {exc}")
            return 4
        finally:
            self._stop_children()


def _user_ids(name: str) -> tuple[int, int]:
    import pwd

    try:
        entry = pwd.getpwnam(name)
    except KeyError as exc:
        raise AgentError("NO_USER", f"нет пользователя {name}") from exc
    return entry.pw_uid, entry.pw_gid


def main(gen: str, paths: Paths) -> int:
    """`xgw pool agent <gen>` — так его запускает служба xgw-fp@<gen>."""
    agent = Agent(paths, gen)

    def stop(*_args) -> None:
        agent.stop.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    return agent.run()


__all__ = ["AUTH_FILE", "Agent", "AgentError", "Manifest", "main"]
