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
5. OpenVPN (от xgw-ovpn): конфиг — в /tmp службы (PrivateTmp — у каждого поколения свой),
   root:<группа работника>, 0640;
6. интерфейс управления OpenVPN (127.0.0.1 в своём пространстве): CONNECTED — адрес туннеля
   на fpt0 и маршрут по умолчанию в fpt0; RECONNECTING, EXITING и прочие — маршрут убран;
7. после первого CONNECTED — проверка изнутри (inner_check, от пользователя SOCKS): TCP к
   Cloudflare:443 и DNS через туннель — DNS сервера (dhcp-option из PUSH_REPLY) и Cloudflare;
   затем SOCKS-работник (Xray от xgw-fps; конфиг так же в /tmp службы) с ответившим DNS
   первым. Отчёт М2а 28.10.2026: четыре туннеля поднялись, а через них не прошло ни одного
   запроса — без этой проверки не понять, кто не пропускает: сервер (или ТСПУ) или путь до
   работника. Готовность работника — по /proc/net/tcp (порт слушается), без подключения:
   отчёт М2а.1 — подключение агента к порту работника охрана отбивала (ответ работника через
   lo ей не разрешён), и все туннели кончались SOCKS_FAILED;
8. состояние — /run/xgw/fp/<gen>/state.json (его читает демон; пока туннель поднят — и
   счётчики fpt0 и охраны раз в 2 с). SIGTERM или отказ — работники останавливаются, итог
   туннеля (пакеты в туннель и из него, ошибки канала данных, отбитое охраной) — одной строкой
   в журнал и в состояние раньше фазы failed (демон берёт его в запись проверки),
   пространство имён исчезает вместе со службой, а с ним и veth.

Счётчики охраны — по отправителю (отчёт М2а.1: общий счётчик принимал за отказ OpenVPN ответы
ядра): refused_ovpn — пакеты OpenVPN (рост до подъёма — GUARD_BLOCKED), refused_socks —
работника SOCKS и проверки изнутри (после подъёма — попытка мимо туннеля), refused_other — без
сокета работника (ответы ядра серверу: сброс TCP после закрытия соединения, ICMP), dropped_v6 —
служебный IPv6 ядра при подъёме fpi и fpt0 (IPv6 здесь не нужен никому).

Строки журнала OpenVPN в журнал службы не пишутся: в состоянии — только коды причин
(classify). Исключение — при отказе одна строка, по которой он распознан, с адресами IPv4 и
именами хостов, заменёнными на <ip> и <host> (evidence): без неё отказ на машине заказчика не
разобрать.
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

from .. import masking
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
REFUSED_OVPN, REFUSED_SOCKS, REFUSED_OTHER = "refused_ovpn", "refused_socks", "refused_other"
DROPPED_V6 = "dropped_v6"
COUNTERS = (REFUSED_OVPN, REFUSED_SOCKS, REFUSED_OTHER, DROPPED_V6)
PROC_TCP = Path("/proc/net/tcp")  # сокеты TCP своего пространства имён
VETH_WAIT = 20.0  # сколько ждать внутренний конец veth от демона
UP_WAIT = 45.0  # подключение OpenVPN вместе с рукопожатием (R54: холодный кандидат — 45 с)
RECONNECT_WAIT = 60.0  # после обрыва: не вернулся — отказ, а не вечные попытки
MGMT_WAIT = 10.0
STOP_WAIT = 5.0
SOCKS_WAIT = 5.0  # SOCKS-работник открывает порт
INNER_WAIT = 12.0  # проверка изнутри целиком (TCP 3 с и DNS по 2 с на сервер)
STATS_EVERY = 2.0  # счётчики fpt0 в состояние, пока туннель поднят
LOG_LINES = 60
MAX_MANIFEST = 512 * 1024
PUBLIC_DNS = ("1.1.1.1", "8.8.8.8")  # после DNS сервера; 1.1.1.1 проверяется изнутри

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
    # Маршрута нет в своём пространстве имён — дефект шлюза (маршрут к серверу ставит агент).
    ("NETWORK_UNREACHABLE", ("Network is unreachable",)),
    # EHOSTUNREACH: ICMP «узел недоступен» или «запрещено» с пути к серверу — либо отказ своей
    # охраны (admin-prohibited). Охрана — только если вырос её счётчик (run: GUARD_BLOCKED).
    ("HOST_UNREACHABLE", ("No route to host",)),
)
# Канал данных после подъёма: пакеты не расшифровываются или отброшены (сжатие, шифр, адрес).
_DATA_ERRORS = ("Decrypt", "decompression header", "bad source address",
                "HMAC authentication failed", "Bad compression")
# Отказ, причина которого не распознана: последняя строка с такой пометкой (evidence).
_MARKERS = ("FATAL", "ERROR", "error", "failed", "Exiting due to")
_STATE = re.compile(r"^(?:>STATE:)?(\d+),([A-Z_]+),([^,]*),?([^,]*),?([^,]*)")
_PUSH_IFCONFIG = re.compile(r"PUSH_REPLY.*?\bifconfig (\d{1,3}(?:\.\d{1,3}){3}) ")
_PUSH_MTU = re.compile(r"PUSH_REPLY.*?\btun-mtu (\d{3,5})\b")
_PUSH_DNS = re.compile(r"\bdhcp-option DNS (\d{1,3}(?:\.\d{1,3}){3})\b")
_IPV4_ANY = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_HOSTNAME = re.compile(r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\b")
_FILE_SUFFIXES = {"conf", "ovpn", "json", "txt", "pem", "crt", "key", "py"}


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
    Новые входящие из туннеля (сервер VPN к агенту, к SOCKS, к управлению) — закрыты.
    Отбитое считается по отправителю (COUNTERS, docstring модуля)."""
    inner, host = inner_link(manifest.index), host_address(manifest.index)
    me = inner_address(manifest.index)
    reject = "reject with icmpx type admin-prohibited"
    return "\n".join((
        f"table inet {TABLE}",
        f"delete table inet {TABLE}",
        f"table inet {TABLE} {{",
        *(f"    counter {name} {{ }}" for name in COUNTERS),
        "    chain input {",
        "        type filter hook input priority filter; policy drop;",
        '        iif "lo" accept',
        "        ct state established,related accept",
        f'        iifname "{inner}" ip saddr {host} ip daddr {me} meta l4proto {{ tcp, udp }} '
        f"th dport {SOCKS_PORT} accept",
        "    }",
        "    chain output {",
        "        type filter hook output priority filter; policy drop;",
        # IPv6 здесь не нужен никому (OpenVPN — к IPv4 сервера, работник — UseIPv4), а ядро
        # само шлёт служебный (поиск маршрутизатора, MLD, DAD) при подъёме fpi и fpt0: в
        # отбитое он не идёт — отчёт М2а.1 принял его за отказ подключения OpenVPN.
        f'        meta nfproto ipv6 counter name "{DROPPED_V6}" drop',
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
        f'        meta skuid {ovpn_uid} counter name "{REFUSED_OVPN}" {reject}',
        f'        meta skuid {socks_uid} counter name "{REFUSED_SOCKS}" {reject}',
        # Без сокета работника: ответы ядра серверу (сброс TCP на его пакеты после закрытия
        # соединения OpenVPN, ICMP), сам агент.
        f'        counter name "{REFUSED_OTHER}" {reject}',
        "    }",
        "    chain forward {",
        "        type filter hook forward priority filter; policy drop;",
        "    }",
        "}",
    )) + "\n"


def socks_config(manifest: Manifest, dns: tuple[str, ...] | list[str] = PUBLIC_DNS) -> dict:
    """SOCKS-работник: Xray, socks с паролем на внутреннем адресе veth (TCP и UDP), выход —
    freedom по маршруту по умолчанию (он есть только в туннель), DNS — серверы через туннель
    (системного резолвера в пространстве имён нет): DNS сервера VPN, если он прислал и тот
    ответил, затем публичные. Проверено xray run -test (26.10.21)."""
    me = inner_address(manifest.index)
    return {
        "log": {"loglevel": "warning"},
        "dns": {"servers": list(dict.fromkeys(dns)) or list(PUBLIC_DNS),
                "queryStrategy": "UseIPv4"},
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


def pushed_dns(line: str) -> list[str]:
    """DNS сервера из PUSH_REPLY (dhcp-option DNS; в конфиг они не принимаются — pull-filter,
    но в журнал OpenVPN строка попадает целиком): IPv4 не из служебных сетей и не из сети veth,
    не больше двух."""
    if "PUSH_REPLY" not in line:
        return []
    found: list[str] = []
    for text in _PUSH_DNS.findall(line):
        try:
            ip = ipaddress.IPv4Address(text)
        except ValueError:
            continue
        if ip.is_loopback or ip.is_multicast or ip.is_unspecified or ip.is_link_local \
                or ip in ipaddress.IPv4Network(SUBNET) or str(ip) in found:
            continue
        found.append(str(ip))
    return found[:2]


def masked(line: str) -> str:
    """Строка журнала OpenVPN для журнала службы: адреса IPv4 — <ip>, имена хостов — <host>
    (имена файлов остаются), не длиннее 200 знаков."""
    text = _IPV4_ANY.sub("<ip>", line.strip())

    def host(match: re.Match[str]) -> str:
        word = match.group(0)
        return word if word.rsplit(".", 1)[-1].lower() in _FILE_SUFFIXES else "<host>"

    return _HOSTNAME.sub(host, text)[:200]


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
    """Строка журнала OpenVPN, по которой распознана причина code (masked); у UNKNOWN —
    последняя строка с пометкой ошибки (FATAL, ERROR…): отчёт М2а — четыре UNKNOWN, и ни
    одной строки, по которой их разобрать. Пусто — такой нет."""
    lines = list(lines)
    needles = dict(_CAUSES).get(code, ())
    for line in lines:
        if any(needle in line for needle in needles):
            return masked(line)
    if code == "UNKNOWN":
        for line in reversed(lines):
            if any(marker in line for marker in _MARKERS):
                return masked(line)
    return ""


# Проверка изнутри (после подъёма, от пользователя SOCKS): TCP к Cloudflare:443 и запрос A
# cloudflare.com к каждому DNS из аргументов. Итог — строки «tcp <итог>» и «dns <адрес> <итог>»;
# итог — OPEN/OK с миллисекундами, EMPTY (ответ без адресов), TIMEOUT или код ошибки.
_INNER = (
    "import errno,socket,struct,sys,time\n"
    "def fail(e):\n"
    "    return errno.errorcode.get(e.errno,'TIMEOUT') if e.errno else 'TIMEOUT'\n"
    "def tcp():\n"
    "    s=socket.socket()\n"
    "    s.settimeout(3)\n"
    "    t=time.monotonic()\n"
    "    try:\n"
    "        s.connect(('1.1.1.1',443))\n"
    "        return 'OPEN %d'%((time.monotonic()-t)*1000)\n"
    "    except OSError as e:\n"
    "        return fail(e)\n"
    "    finally:\n"
    "        s.close()\n"
    "def dns(a):\n"
    "    q=struct.pack('>6H',0x5847,0x0100,1,0,0,0)+b'\\x0acloudflare\\x03com\\x00'"
    "+struct.pack('>2H',1,1)\n"
    "    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)\n"
    "    s.settimeout(2)\n"
    "    t=time.monotonic()\n"
    "    try:\n"
    "        s.sendto(q,(a,53))\n"
    "        d=s.recvfrom(512)[0]\n"
    "        if d[:2]!=q[:2] or len(d)<12:\n"
    "            return 'BAD'\n"
    "        if struct.unpack('>H',d[6:8])[0]==0:\n"
    "            return 'EMPTY'\n"
    "        return 'OK %d'%((time.monotonic()-t)*1000)\n"
    "    except OSError as e:\n"
    "        return fail(e)\n"
    "    finally:\n"
    "        s.close()\n"
    "print('tcp',tcp(),flush=True)\n"
    "for a in sys.argv[1:]:\n"
    "    print('dns',a,dns(a),flush=True)\n"
)


def inner_servers(pushed: list[str]) -> list[tuple[str, str]]:
    """DNS для проверки изнутри: (метка для журнала, адрес). Адреса в журнал не попадают."""
    servers = [("сервера", address) for address in pushed]
    if PUBLIC_DNS[0] not in pushed:
        servers.append(("Cloudflare", PUBLIC_DNS[0]))
    return servers


def parse_inner(text: str, servers: list[tuple[str, str]]) -> dict:
    """Вывод проверки изнутри → {"tcp": итог, "dns": [[метка, итог], …]} (без адресов)."""
    labels = {address: label for label, address in servers}
    result: dict = {"tcp": "—", "dns": [[label, "—"] for label, _address in servers]}
    for line in text.splitlines():
        words = line.split()
        if len(words) >= 2 and words[0] == "tcp":
            result["tcp"] = " ".join(words[1:3])
        elif len(words) >= 3 and words[0] == "dns" and words[1] in labels:
            for item in result["dns"]:
                if item[0] == labels[words[1]] and item[1] == "—":
                    item[1] = " ".join(words[2:4])
                    break
    return result


def _result_text(value: object) -> str:
    words = str(value or "—").split()
    if len(words) == 2 and words[1].isdigit():
        return f"{words[0]} ({words[1]} мс)"
    return words[0] if words else "—"


def inner_text(inner: object) -> str:
    """Итог проверки изнутри по-русски и без адресов: «TCP Cloudflare:443 — OPEN (120 мс);
    DNS сервера — TIMEOUT; DNS Cloudflare — OK (35 мс)»; пусто — проверки не было."""
    if not isinstance(inner, dict) or not inner:
        return ""
    parts = [f"TCP Cloudflare:443 — {_result_text(inner.get('tcp'))}"]
    for item in inner.get("dns") or []:
        if isinstance(item, list) and len(item) == 2:
            parts.append(f"DNS {item[0]} — {_result_text(item[1])}")
    return "; ".join(parts)


def worker_dns(servers: list[tuple[str, str]], inner: dict) -> list[str]:
    """DNS SOCKS-работника: ответившие в проверке изнутри — первыми, затем остальные из
    проверки и публичные."""
    results = {label: str(value) for label, value in inner.get("dns") or []
               if isinstance(label, str)}
    answered = [address for label, address in servers
                if results.get(label, "").startswith("OK")]
    return list(dict.fromkeys([*answered, *(address for _label, address in servers),
                               *PUBLIC_DNS]))


def parse_link_stats(text: str) -> dict[str, int] | None:
    """Счётчики из `ip -s link show`: под строками «RX:»/«TX:» — байты, затем пакеты (так у
    iproute2 разных версий). None — не разобрать."""
    lines = text.splitlines()
    found: dict[str, int] = {}
    for index, line in enumerate(lines[:-1]):
        head = line.strip()
        if head.startswith(("RX:", "TX:")):
            numbers = lines[index + 1].split()
            if len(numbers) >= 2 and numbers[0].isdigit() and numbers[1].isdigit():
                side = head[:2].lower()
                found[f"{side}_bytes"], found[f"{side}_packets"] = int(numbers[0]), int(numbers[1])
    return found if len(found) == 4 else None


def tunnel_text(stats: object) -> str:
    """Счётчики fpt0 по-русски: TX ядра — в туннель (к серверу), RX — из туннеля (от него)."""
    if not isinstance(stats, dict):
        return ""
    try:
        return (f"в туннель {int(stats['tx_packets'])} пакетов "
                f"({int(stats['tx_bytes']) // 1024} КБ), из туннеля {int(stats['rx_packets'])} "
                f"пакетов ({int(stats['rx_bytes']) // 1024} КБ)")
    except (KeyError, TypeError, ValueError):
        return ""


def listening(text: str, port: int) -> bool:
    """Слушается ли TCP-порт по тексту /proc/net/tcp: локальный адрес «ADDR:PORT» (порт —
    hex в порядке байт сети), состояние 0A — LISTEN."""
    for line in text.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 4 and fields[3] == "0A" \
                and fields[1].rpartition(":")[2].upper() == f"{port:04X}":
            return True
    return False


def deltas(start: dict | None, end: dict | None) -> dict[str, int]:
    """Прирост счётчиков охраны между двумя снимками (_counters); нечитаемый — без него."""
    if not isinstance(start, dict) or not isinstance(end, dict):
        return {}
    found = {}
    for name in COUNTERS:
        a, b = start.get(name, -1), end.get(name, -1)
        if isinstance(a, int) and isinstance(b, int) and a >= 0 and b >= a:
            found[name] = b - a
    return found


def guard_text(found: object) -> str:
    """Прирост счётчиков охраны по-русски: «OpenVPN 0, работник 0, ответы ядра 2, служебный
    IPv6 5»; пусто — счётчики не прочитаны."""
    if not isinstance(found, dict) or not found:
        return ""
    labels = ((REFUSED_OVPN, "OpenVPN"), (REFUSED_SOCKS, "работник"),
              (REFUSED_OTHER, "ответы ядра"), (DROPPED_V6, "служебный IPv6"))
    return ", ".join(f"{label} {found[name]}" for name, label in labels if name in found)


# Строка отказа ядра (Xray: «Failed to start: … > infra/conf: unknown cipher method: …»;
# sing-box: «FATAL[0000] …»): сначала такие, затем ошибки, затем прочие пометки — не
# предупреждения (у Xray «might be removed» есть и в них).
_CORE_FATAL = ("Failed to start", "FATAL")
_CORE_ERROR = ("[Error]", "ERROR")
_CORE_MARKERS = ("failed", "invalid", "unknown", "removed", "not supported")
_CORE_PREFIX = re.compile(r"^(?:[A-Z]+\[\d+\]\s*)?(?:(?:infra/conf|common/errors|main): )*")


def core_reason(lines, secrets=()) -> str:
    """Почему ядро (Xray, sing-box) не запустилось, по его выводу: последнее звено цепочки
    «… > …» без имён модулей; секреты конфига (secrets — и части пароля «ключ:ключ»), ссылки,
    UUID, адреса и имена хостов скрыты (Xray печатает в ошибке ключ или пароль). Не длиннее
    120 знаков; пусто — строки с ошибкой нет."""
    lines = [line.strip() for line in lines if line.strip()]
    quiet = [line for line in lines if "[Warning]" not in line and "[Info]" not in line]
    found = ""
    for group, pool in ((_CORE_FATAL, lines), (_CORE_ERROR, quiet), (_CORE_MARKERS, quiet)):
        found = next((line for line in reversed(pool) if any(m in line for m in group)), "")
        if found:
            break
    if not found:
        return ""
    text = _CORE_PREFIX.sub("", found.rsplit(" > ", 1)[-1])
    parts = {piece for secret in secrets if isinstance(secret, str)
             for piece in (secret, *secret.split(":")) if len(piece) >= 4}
    return masked(masking.mask_text(text, parts))[:120]


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
# отбитого охраной у этого пользователя (refused_ovpn, refused_socks): иначе пакет мог уйти.
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
        proc_tcp: Callable[[], str] = lambda: PROC_TCP.read_text(encoding="ascii"),
    ) -> None:
        self.paths, self.gen = paths, gen
        self.runner, self.spawn, self.connect = runner, spawn, connect
        self.proc_tcp = proc_tcp
        self.users = users or _user_ids
        self.clock, self.sleep = clock, sleep
        self.tmp, self.out = tmp, out
        self.stop = threading.Event()
        self.children: dict[str, subprocess.Popen] = {}
        self.log: deque[str] = deque(maxlen=LOG_LINES)
        self.pushed_address, self.pushed_mtu = "", 0
        self.pushed_dns: list[str] = []
        self.data_errors, self.data_error_line = 0, ""
        self.state: dict = {"gen": gen, "phase": "starting", "since": time.time()}
        self.manifest: Manifest | None = None
        self.ids: dict[str, tuple[int, int]] = {}
        # Снимки счётчиков охраны (_counters): после самопроверки (подключение OpenVPN) и при
        # подъёме (дальше — работник и проверка изнутри).
        self.refused_base: dict[str, int] | None = None
        self.refused_up: dict[str, int] | None = None
        self.was_up = False
        self.summarized = False
        self.socks_log: deque[str] = deque(maxlen=8)

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
            "socks_to_peer": (socks, REFUSED_SOCKS, manifest.peer, manifest.port),
            "socks_to_internet": (socks, REFUSED_SOCKS, "1.1.1.1", 443),
            "socks_to_mgmt": (socks, REFUSED_SOCKS, "127.0.0.1", MGMT_PORT),
            "ovpn_to_host": (ovpn, REFUSED_OVPN, host_address(manifest.index), 22),
            "ovpn_to_internet": (ovpn, REFUSED_OVPN, "1.1.1.1", 443),
        }
        results: dict[str, str] = {}
        bad: list[str] = []
        for name, (who, counter, address, port) in cases.items():
            before = self._counter(counter)
            result = self._probe(*who, address, port)
            counted = self._counter(counter) > before
            results[name] = result + (" (охрана)" if counted else "")
            if not (result == NO_ROUTE or (result in REJECTED and counted)):
                bad.append(name)
        self._write(selftest={"results": results, "ok": not bad})
        self._say("охрана проверена: " + ", ".join(f"{name} {value}"
                                                   for name, value in results.items()))
        if bad:
            raise AgentError("GUARD_FAILED", "охрана пропускает: " + ", ".join(bad))
        return results

    def _counter(self, name: str) -> int:
        text = self.runner(["nft", "list", "counter", "inet", TABLE, name],
                           timeout=10.0, check=False)
        match = _PACKETS.search(text)
        return int(match.group(1)) if match else -1

    def _counters(self) -> dict[str, int]:
        return {name: self._counter(name) for name in COUNTERS}

    def _write_dir(self, directory: Path, gid: int, content: dict[str, str]) -> None:
        """Каталог работника в /tmp службы: root:<группа работника>, 0750; файлы — 0640."""
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

    def _files(self, manifest: Manifest, ids: dict[str, tuple[int, int]]) -> Path:
        ovpn_dir = self.tmp / Path(OVPN_DIR).name
        content = {"client.conf": manifest.openvpn_conf}
        if manifest.auth:
            content["auth"] = manifest.auth
        self._write_dir(ovpn_dir, ids["ovpn"][1], content)
        return ovpn_dir / "client.conf"

    def _inner_check(self, manifest: Manifest) -> tuple[list[tuple[str, str]], dict]:
        """Через поднятый туннель, от пользователя SOCKS: TCP и DNS (inner_servers). Итог — в
        состояние и одной строкой в журнал, без адресов."""
        servers = inner_servers(self.pushed_dns)
        uid, gid = self.ids["socks"]
        proc = self.spawn(
            [sys.executable, "-I", "-c", _INNER, *(address for _label, address in servers)],
            user=uid, group=gid, extra_groups=[], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, close_fds=True,
        )
        try:
            out, _err = proc.communicate(timeout=INNER_WAIT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            out = ""
        inner = parse_inner(out or "", servers)
        self._write(inner=inner)
        self._say("через туннель: " + inner_text(inner))
        return servers, inner

    def _start_socks(self, manifest: Manifest, dns: list[str]) -> None:
        """SOCKS-работник — только при поднятом туннеле: DNS берётся из проверки изнутри.
        Готов — когда его порт слушается (/proc/net/tcp своего пространства имён). Не
        подключением: ответ работника через lo охрана не пропускает (отчёт М2а.1)."""
        socks_dir = self.tmp / Path(SOCKS_DIR).name
        self._write_dir(socks_dir, self.ids["socks"][1], {
            "socks.json": json.dumps(socks_config(manifest, dns), ensure_ascii=False)})
        proc = self._start("socks", [manifest.xray_bin, "run", "-c",
                                     str(socks_dir / "socks.json")], self.ids["socks"])
        reader = threading.Thread(target=self._drain, args=(proc,), daemon=True)
        reader.start()
        deadline = self.clock() + SOCKS_WAIT
        while True:
            if self._dead("socks"):
                reader.join(timeout=1.0)
                why = core_reason(self.socks_log, (manifest.socks_pass,))
                raise AgentError("SOCKS_FAILED", "SOCKS-работник завершился при запуске"
                                 + (f": {why}" if why else ""))
            try:
                if listening(self.proc_tcp(), SOCKS_PORT):
                    return
            except OSError as exc:
                raise AgentError("SOCKS_FAILED", f"/proc/net/tcp не читается: {exc}") from exc
            if self.clock() > deadline or self.stop.is_set():
                raise AgentError("SOCKS_FAILED", "SOCKS-работник не открыл порт")
            self.sleep(0.1)

    def _tun_stats(self) -> dict[str, int] | None:
        try:
            return parse_link_stats(self._ip("-s", "link", "show", "dev", TUN, check=False))
        except (OSError, cmd.CommandError):
            return None

    def _summary(self) -> None:
        """Итог поднимавшегося туннеля — в журнал и состояние: пакеты в туннель и из него,
        ошибки канала данных, отбитое охраной после подъёма (у работника — попытки мимо
        туннеля). Один раз; сбой здесь — не повод не остановить работников."""
        if self.summarized:
            return
        self.summarized = True
        stats = self._tun_stats()
        after = deltas(self.refused_up, self._counters())
        parts = [tunnel_text(stats) or "счётчики fpt0 не прочитаны",
                 f"ошибок канала данных {self.data_errors}"
                 + (f" ({self.data_error_line})" if self.data_error_line else ""),
                 f"охрана после подъёма: {guard_text(after) or '—'}"]
        self._write(tun=stats, refused_after_up=after)
        self._say("итог туннеля: " + "; ".join(parts))

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
            dns = pushed_dns(line)
            if dns:
                self.pushed_dns = dns
            if any(needle in line for needle in _DATA_ERRORS):
                self.data_errors += 1
                if not self.data_error_line:
                    self.data_error_line = masked(line)

    def _drain(self, proc: subprocess.Popen) -> None:
        """Вывод работника SOCKS — не в журнал службы: последние строки только для причины
        отказа при запуске (core_reason)."""
        for line in proc.stdout or ():
            self.socks_log.append(line.rstrip("\n")[:400])

    def _up(self, address: str, manifest: Manifest) -> None:
        problem = tunnel_problem(address, manifest)
        if problem:
            raise AgentError("BAD_TUNNEL_ADDRESS", problem)
        mtu = self.pushed_mtu if 576 <= self.pushed_mtu <= 1500 else 1500
        self._ip("addr", "flush", "dev", TUN)
        self._ip("addr", "add", f"{address}/32", "dev", TUN)
        self._ip("link", "set", "dev", TUN, "mtu", str(mtu), "up")
        self._ip("route", "replace", "default", "dev", TUN)
        if not self.was_up:
            # Первый подъём: проверка изнутри и SOCKS-работник — до фазы up (демон начинает
            # пробу, как только её видит). Туннель поднят — в состояние сразу: откажет
            # работник — демон всё равно запишет, что туннель был и что видно изнутри.
            self.was_up = True
            self.refused_up = self._counters()
            self._write(tunnel=address, mtu=mtu, tunnel_at=time.time())
            self._say(f"туннель поднят, MTU {mtu}")
            servers, inner = self._inner_check(manifest)
            self._start_socks(manifest, worker_dns(servers, inner))
            self._say("SOCKS-работник готов")
        else:
            self._say(f"туннель снова поднят, MTU {mtu}")
        self._write(phase="up", tunnel=address, mtu=mtu, up_at=time.time())

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
        stats_at = 0.0
        try:
            while not self.stop.is_set():
                if up and self.clock() - stats_at >= STATS_EVERY:
                    stats_at = self.clock()
                    stats = self._tun_stats()
                    values: dict = {"refused_after_up": deltas(self.refused_up,
                                                               self._counters())}
                    if stats is not None:
                        values["tun"] = stats
                    self._write(**values)
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
                            self.log.append(line)  # её текст — улика отказа (evidence)
                            raise AgentError(classify(self.log), "OpenVPN: FATAL")
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
            self.ids = ids
            self._guard(manifest, ids["ovpn"][0], ids["socks"][0])
            self._tun(*ids["ovpn"])
            self._write(phase="guarded")
            self._veth(manifest)
            self._selftest(manifest, ids)
            conf = self._files(manifest, ids)
            self.refused_base = self._counters()
            proc = self._start("openvpn", [manifest.openvpn_bin, "--config", str(conf)],
                               ids["ovpn"])
            threading.Thread(target=self._read_openvpn, args=(proc,), daemon=True).start()
            self._write(phase="connecting")
            self._manage(manifest)
            self._write(phase="stopped")
            return 0
        except AgentError as exc:
            code, text = exc.code, str(exc)
            before_up = self._before_up()
            if before_up.get(REFUSED_OVPN, 0) > 0 and not self.was_up:
                # До подъёма работает только OpenVPN, а его пакеты отбила своя охрана — дефект
                # шлюза, как бы ни назвал отказ сам OpenVPN («No route to host» и т. п.).
                # Ответы ядра и служебный IPv6 — не его пакеты (отчёт М2а.1).
                code, text = "GUARD_BLOCKED", f"охрана отбила пакеты OpenVPN ({text})"
            self._summarize()  # раньше фазы failed: демон берёт итог в запись проверки
            self._write(phase="failed", reason=code, openvpn_code=exc.code, detail=text[:200],
                        refused_before_up=before_up)
            self._say(f"поколение {self.gen}: {code}"
                      + (f" (по журналу OpenVPN: {exc.code})" if code != exc.code else "")
                      + f" — {text}")
            line = evidence(list(self.log), exc.code)
            if line:
                self._say(f"OpenVPN: {line}")
            if any(before_up.values()):
                self._say(f"охрана за подключение: {guard_text(before_up)}")
            return 3
        except (OSError, cmd.CommandError, subprocess.SubprocessError) as exc:
            self._summarize()
            self._write(phase="failed", reason="AGENT_ERROR", detail=type(exc).__name__)
            self._say(f"поколение {self.gen}: ошибка агента — {exc}")
            return 4
        finally:
            self._summarize()
            self._stop_children()

    def _summarize(self) -> None:
        if not self.was_up:
            return
        try:
            self._summary()
        except (OSError, cmd.CommandError, ValueError) as exc:
            self._say(f"итог туннеля не собран: {exc}")

    def _before_up(self) -> dict[str, int]:
        """Прирост счётчиков охраны с запуска OpenVPN до подъёма туннеля (или до сих пор);
        пусто — OpenVPN не запускался или счётчики не прочитаны."""
        if self.refused_base is None:
            return {}
        try:
            end = self.refused_up if self.refused_up is not None else self._counters()
        except (OSError, cmd.CommandError):
            return {}
        return deltas(self.refused_base, end)


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
