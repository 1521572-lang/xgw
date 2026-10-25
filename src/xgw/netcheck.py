"""Проверка сети по кнопке (Ф3 `VPN_IMPROVEMENT_PLAN.md`, §2.4а; ASSUMPTIONS п. 242).

Кнопка «Проверить сеть» в панели и `xgw diag --netcheck`: разовые проверки того, чего не видят
ни watchdog, ни остальной `xgw diag`, — размер пакетов до основного сервера (PPPoE), пропускает
ли провайдер UDP (hysteria2, TUIC), идёт ли UDP через сервер, не уходят ли DNS и IPv6 самой
машины мимо VPN, и чужие правила фаервола. Демон их сам не запускает: каждая проверка шлёт
пакеты наружу, а нужны они, только когда человек разбирается, что не так.

Проверки идут одновременно, каждая — за секунды. Адресов серверов и внешнего IP в итоге нет:
только имя сервера и вердикт. Имена STUN-серверов разрешаются bootstrap-резолверами с меткой
мимо VPN (fetch.resolve_domain), а не системным резолвером.
"""

from __future__ import annotations

import contextlib
import errno
import ipaddress
import json
import re
import secrets
import shutil
import socket
import sqlite3
import struct
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from . import engine, fetch, log, marknet, masking
from .config import Config
from .diag import FAIL, OK, WARN, Check, Diag
from .generator.singbox import QUIC_TYPES
from .net import cmd
from .net.capture import Capture
from .paths import Paths
from .store import Store

META = "netcheck"  # ключ в базе состояния: итог последней проверки из панели
# STUN (RFC 5389): два оператора — один может быть недоступен сам по себе.
STUN_SERVERS = (("stun.l.google.com", 19302), ("stun.cloudflare.com", 3478))
STUN_COOKIE = 0x2112A442
# TEST-NET-1: ответить на запрос к этому адресу может только перехват (dns-out Xray).
DNS_PROBE = ("192.0.2.53", 53)
DNS_NAME = "example.com"
V6_PROBE = ("2606:4700:4700::1111", 443)  # Cloudflare DNS по IPv6
PMTU_SIZES = (1472, 1464, 1452, 1412)  # данные ICMP; + 28 байт заголовков = 1500…1440
IP_HEADERS = 28
TIMEOUT = 3.0


# --- сетевые операции (тесты подменяют их) --------------------------------------------------


def stun_request() -> tuple[bytes, bytes]:
    """Binding Request и его идентификатор."""
    txid = secrets.token_bytes(12)
    return struct.pack(">HHI", 0x0001, 0, STUN_COOKIE) + txid, txid


def is_stun_reply(data: bytes, txid: bytes) -> bool:
    """Binding Success Response на наш запрос."""
    return len(data) >= 20 and data[:2] == b"\x01\x01" and data[8:20] == txid


def _wait_reply(sock: socket.socket, accept: Callable[[bytes, tuple], bool],
                timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while (remaining := deadline - time.monotonic()) > 0:
        sock.settimeout(remaining)
        try:
            data, peer = sock.recvfrom(2048)
        except (TimeoutError, BlockingIOError):
            return False
        if accept(data, peer):
            return True
    return False


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("SOCKS: соединение закрыто")
        data += chunk
    return data


def _socks_address(sock: socket.socket, kind: int) -> str:
    if kind == 1:
        return socket.inet_ntoa(_recv_exact(sock, 4))
    if kind == 4:
        return socket.inet_ntop(socket.AF_INET6, _recv_exact(sock, 16))
    if kind == 3:
        return _recv_exact(sock, _recv_exact(sock, 1)[0]).decode("ascii", "replace")
    raise ConnectionError(f"SOCKS: неизвестный тип адреса {kind}")


def _socks_payload(data: bytes) -> bytes:
    """Датаграмма SOCKS5 UDP без заголовка (RFC 1928, §7)."""
    if len(data) < 4 or data[2] != 0:
        return b""
    kind, offset = data[3], 4
    if kind == 1:
        offset += 4
    elif kind == 4:
        offset += 16
    elif kind == 3 and len(data) > 4:
        offset += 1 + data[4]
    else:
        return b""
    return data[offset + 2:]


def socks_udp_stun(socks: tuple[str, int], host: str, port: int,
                   timeout: float = TIMEOUT) -> bool:
    """STUN через вход socks Xray (UDP ASSOCIATE): ответ пришёл — UDP идёт через сервер.
    Имя STUN-сервера разрешает сам Xray — путь тот же, что у трафика устройств."""
    with socket.create_connection(socks, timeout=timeout) as control:
        control.settimeout(timeout)
        control.sendall(b"\x05\x01\x00")
        if _recv_exact(control, 2) != b"\x05\x00":
            raise ConnectionError("SOCKS: вход не принял подключение без пароля")
        control.sendall(b"\x05\x03\x00\x01" + bytes(4) + bytes(2))
        reply = _recv_exact(control, 4)
        if reply[1] != 0:
            raise ConnectionError(f"SOCKS: UDP ASSOCIATE отклонён (код {reply[1]})")
        relay_host = _socks_address(control, reply[3])
        relay_port = struct.unpack(">H", _recv_exact(control, 2))[0]
        if relay_host in ("0.0.0.0", "::"):
            relay_host = socks[0]
        name = host.encode("idna")
        header = b"\x00\x00\x00\x03" + bytes([len(name)]) + name + struct.pack(">H", port)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            for _attempt in range(2):
                request, txid = stun_request()
                sock.sendto(header + request, (relay_host, relay_port))
                if _wait_reply(sock, lambda data, _peer, txid=txid: is_stun_reply(
                        _socks_payload(data), txid), timeout / 2):
                    return True
    return False


class Net:
    """Сетевые операции проверок: настоящие сокеты и `ping`."""

    def __init__(self, cfg: Config, runner: cmd.Runner, mark: int | None,
                 which: Callable[[str], str | None] = shutil.which) -> None:
        self.cfg = cfg
        self.runner = runner
        self.mark = mark  # None — без root: метки мимо VPN нет
        self.which = which

    def resolve(self, host: str) -> str | None:
        with contextlib.suppress(ValueError):
            if ipaddress.ip_address(host).version == 4:
                return host
            return None
        try:
            return fetch.resolve_domain(host, self.cfg.dns.resolvers, mark=self.mark)[0]
        except fetch.ResolveError:
            return None

    def ping(self, address: str, size: int | None = None) -> bool | None:
        """Ответил ли адрес на ping (size — без дробления, -M do); None — ping не установлен.
        ICMP XGW не перехватывает; метка — чтобы ping шёл и в режиме blocked."""
        if self.which("ping") is None:
            return None
        argv = ["ping", "-n", "-q", "-c", "2", "-i", "0.2", "-W", "1"]
        if size is not None:
            argv += ["-M", "do", "-s", str(size)]
        if self.mark is not None:
            argv += ["-m", str(self.mark)]
        try:
            text = self.runner([*argv, address], timeout=6.0, check=False)
        except cmd.CommandError:
            return False
        found = re.search(r"(\d+) received", text)
        return bool(found and int(found.group(1)) > 0)

    def stun(self, host: str, port: int) -> bool:
        """STUN напрямую, с меткой мимо VPN."""
        address = self.resolve(host)
        if address is None:
            return False
        with contextlib.closing(marknet.marked_udp(self.mark)) as sock:
            for _attempt in range(2):
                request, txid = stun_request()
                sock.sendto(request, (address, port))
                if _wait_reply(sock, lambda data, peer, txid=txid: peer[0] == address
                               and is_stun_reply(data, txid), TIMEOUT / 2):
                    return True
        return False

    def stun_via_xray(self, host: str, port: int) -> bool:
        try:
            return socks_udp_stun(("127.0.0.1", self.cfg.xray.socks_port), host, port)
        except OSError:
            return False

    def xray_up(self) -> bool:
        """Xray принимает соединения на своём входе socks."""
        try:
            with socket.create_connection(("127.0.0.1", self.cfg.xray.socks_port), timeout=1.0):
                return True
        except OSError:
            return False

    def dns_answered(self, server: tuple[str, int] = DNS_PROBE, *,
                     mark: int | None = None) -> bool:
        """Запрос A без метки — так ходит DNS самой машины. Ответ от недостижимого адреса
        может дать только перехват — или сеть, которая сама отвечает на любой порт 53
        (провайдер, подменяющий DNS): это видно по запросу с меткой мимо VPN."""
        wire = fetch._dns_query(DNS_NAME)
        with contextlib.closing(marknet.marked_udp(mark)) as sock:
            sock.sendto(wire, server)
            return _wait_reply(sock, lambda data, peer: peer[0] == server[0]
                               and data[:2] == wire[:2], TIMEOUT)

    def v6_connect(self, target: tuple[str, int] = V6_PROBE) -> str:
        """TCP по IPv6 без метки: connected — вышло мимо VPN; unreachable — IPv6 в сети нет;
        refused — закрыт фаерволом; timeout — ответа нет."""
        try:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        except OSError:
            return "unreachable"
        with sock:
            sock.settimeout(TIMEOUT)
            try:
                sock.connect(target)
            except TimeoutError:
                return "timeout"
            except OSError as exc:
                if exc.errno in (errno.ECONNREFUSED, errno.EPERM, errno.EACCES):
                    return "refused"
                return "unreachable"
        return "connected"


# --- проверки ---------------------------------------------------------------------------


def main_server(paths: Paths) -> dict | None:
    """Основной сервер (или первый в работе): имя и адрес из базы состояния демона."""
    try:
        store = Store(paths.db_file)
    except (OSError, sqlite3.Error):
        return None
    try:
        main = json.loads(store.get_meta("main") or "null") or {}
        nodes = store.all_nodes()
    except (ValueError, sqlite3.Error):
        return None
    finally:
        store.close()
    tag = main.get("tag") if isinstance(main, dict) else None
    chosen = next((node for node in nodes if node.get("tag") == tag), None) if tag else None
    return chosen or next((node for node in nodes if node.get("role") == "proxy"), None)


def quic_servers(paths: Paths) -> int:
    """Сколько серверов hysteria2 и TUIC ведёт sing-box (им нужен UDP напрямую)."""
    try:
        config = json.loads(paths.singbox_config_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    outbounds = config.get("outbounds") if isinstance(config, dict) else None
    return sum(1 for item in outbounds or () if isinstance(item, dict)
               and item.get("type") in QUIC_TYPES)


class Netcheck:
    def __init__(
        self, cfg: Config, paths: Paths, *, runner: cmd.Runner = cmd.run, logger=None,
        net: Net | None = None, capture: Capture | None = None, firewall: bool = True,
    ) -> None:
        self.cfg = cfg
        self.paths = paths
        self.runner = runner
        self.log = logger or log.get_logger("netcheck")
        self.net = net or Net(cfg, runner, engine.bypass_mark(cfg, self.log))
        self.capture = capture or Capture(cfg, paths, logger=self.log)
        # Чужие правила: в `xgw diag --netcheck` их уже показал сам diag.
        self.firewall = firewall
        self.xray = False

    def run(self) -> list[Check]:
        self.xray = self.net.xray_up()
        groups: list[tuple[str, Callable[[], list[Check]]]] = [
            ("MTU до сервера", self._pmtu),
            ("UDP напрямую", self._udp_direct),
            ("UDP через VPN", self._udp_vpn),
            ("Утечка DNS", self._dns),
            ("Утечка IPv6", self._ipv6),
        ]
        if self.firewall:
            groups.append(("Чужие правила", self._foreign))
        with ThreadPoolExecutor(max_workers=len(groups)) as pool:
            futures = [(name, pool.submit(group)) for name, group in groups]
        result: list[Check] = []
        for name, future in futures:
            try:
                result.extend(future.result())
            except Exception as exc:  # одна проверка не должна ронять остальные
                self.log.error("проверка сети «%s»: %s", name, exc)
                result.append(Check(name, WARN, f"проверка не выполнена: {exc}"))
        return [Check(item.name, item.level, masking.mask_text(item.text),
                      masking.mask_text(item.advice)) for item in result]

    def _server(self) -> tuple[dict | None, str]:
        server = main_server(self.paths)
        return server, f"«{server.get('name') or server.get('tag')}»" if server else ""

    def _pmtu(self) -> list[Check]:
        name = "MTU до сервера"
        server, label = self._server()
        if server is None:
            return [Check(name, OK, "серверов в работе нет — не проверен")]
        address = self.net.resolve(str(server.get("address") or ""))
        if address is None:
            return [Check(name, OK, f"адрес сервера {label} не разрешился (или это IPv6) — "
                                    "не проверен")]
        answered = self.net.ping(address)
        if answered is None:
            return [Check(name, OK, "ping не установлен — не проверен",
                          "sudo apt install iputils-ping")]
        if not answered:
            return [Check(name, OK, f"сервер {label} не отвечает на ping — размер пакетов не "
                                    "проверен (многие серверы ping закрывают)")]
        for size in PMTU_SIZES:
            if self.net.ping(address, size):
                if size == PMTU_SIZES[0]:
                    return [Check(name, OK, f"до сервера {label} проходят пакеты 1500 байт")]
                return [Check(
                    name, WARN,
                    f"до сервера {label} проходят пакеты до {size + IP_HEADERS} байт, а не 1500 "
                    "(так бывает у PPPoE)",
                    "TCP это не мешает — ядро само подбирает размер; UDP-серверы (hysteria2, "
                    "TUIC) и QUIC могут терять большие пакеты",
                )]
        return [Check(
            name, WARN,
            f"до сервера {label} не проходят без дробления даже пакеты "
            f"{PMTU_SIZES[-1] + IP_HEADERS} байт",
            "провайдер режет ICMP «нужна фрагментация» или путь очень короткий: сайты, которые "
            "открываются через раз, — признак этого",
        )]

    def _udp_direct(self) -> list[Check]:
        name = "UDP напрямую"
        if self.net.mark is None:
            return [Check(name, OK, "не проверен: нужна метка мимо VPN — запустите через sudo")]
        if any(self.net.stun(host, port) for host, port in STUN_SERVERS):
            return [Check(name, OK, "провайдер пропускает UDP: STUN-сервер ответил напрямую")]
        count = quic_servers(self.paths)
        yours = f" (у вас их {count})" if count else ""
        return [Check(
            name, WARN, "STUN-серверы не ответили напрямую: похоже, провайдер не пропускает UDP",
            f"серверы hysteria2 и TUIC работать не будут{yours}; VLESS, Trojan и Shadowsocks по "
            "TCP это не затрагивает",
        )]

    def _udp_vpn(self) -> list[Check]:
        name = "UDP через VPN"
        if not self.xray:
            return [Check(name, WARN, "Xray не отвечает — не проверен",
                          "что с Xray, покажет sudo xgw diag")]
        _server, label = self._server()
        via = f"сервер {label}" if label else "сервер"
        if any(self.net.stun_via_xray(host, port) for host, port in STUN_SERVERS):
            return [Check(name, OK, f"UDP идёт через {via}: STUN-сервер ответил через Xray")]
        return [Check(
            name, WARN,
            f"UDP через {via} не проходит: звонки, игры и QUIC через VPN работать не будут",
            "выберите основным другой сервер и проверьте снова",
        )]

    def _dns(self) -> list[Check]:
        name = "Утечка DNS"
        info = self.capture.describe(check=False)
        if not info.get("local"):
            return [Check(name, OK, "трафик самой машины не перехватывается "
                                    "(capture.local = false) — проверять нечего")]
        if info.get("mode") != "on":
            return [Check(name, OK, "перехват снят — DNS машины сейчас идёт напрямую")]
        if not self.xray or info.get("inbound_missing"):
            return [Check(name, WARN, "Xray не готов принимать перехваченный трафик — не проверен",
                          "что с Xray, покажет sudo xgw diag")]
        if not self.net.dns_answered():
            return [Check(
                name, FAIL,
                "DNS машины уходит мимо Xray: запрос к недоступному адресу не перехвачен",
                "sudo xgw net up загрузит правила заново; если не поможет — sudo xgw diag",
            )]
        if self.net.mark is not None and self.net.dns_answered(mark=self.net.mark):
            return [Check(name, OK, "не проверена: на запрос к недоступному адресу отвечает и "
                                    "сеть провайдера мимо VPN (он подменяет DNS) — утечку так "
                                    "не отличить")]
        return [Check(name, OK, "DNS машины идёт через Xray: на запрос к недоступному адресу "
                                "ответил перехват, а мимо VPN — никто")]

    def _ipv6(self) -> list[Check]:
        name = "Утечка IPv6"
        if self.cfg.network.ipv6_proxy:
            return [Check(name, OK, "IPv6 машины идёт через Xray (network.ipv6 = proxy)")]
        outcome = self.net.v6_connect()
        if outcome == "connected":
            return [Check(name, FAIL, "IPv6 машины выходит в интернет мимо VPN",
                          "sudo xgw net up загрузит правила заново; если не поможет — "
                          "sudo xgw diag")]
        texts = {
            "unreachable": "IPv6 в сети нет — мимо VPN ему идти некуда",
            "refused": "IPv6 машины мимо VPN закрыт фаерволом XGW",
            "timeout": "IPv6 машины мимо VPN не выходит",
        }
        return [Check(name, OK, texts.get(outcome, texts["timeout"]))]

    def _foreign(self) -> list[Check]:
        checks = Diag(self.cfg, self.paths, runner=self.runner, logger=self.log,
                      net=False).firewall()
        return checks or [Check("Чужие правила", OK, "не проверены: нужен root")]


# --- итог -------------------------------------------------------------------------------


def summary(checks: Sequence[Check]) -> str:
    """«OK — 4, WARN — 1, FAIL — 0: UDP напрямую» — для события."""
    counts = {level: sum(1 for check in checks if check.level == level)
              for level in (OK, WARN, FAIL)}
    text = ", ".join(f"{level} — {count}" for level, count in counts.items())
    bad = [check.name for check in checks if check.level != OK]
    return text + (": " + ", ".join(dict.fromkeys(bad)) if bad else "")


def dumps(checks: Sequence[Check], started: float, took: float) -> str:
    return json.dumps({"at": started, "took": round(took, 1),
                       "checks": [asdict(check) for check in checks]}, ensure_ascii=False)


def loads(text: str | None) -> dict:
    try:
        value = json.loads(text or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}
