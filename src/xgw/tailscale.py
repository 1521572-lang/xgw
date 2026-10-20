"""Tailscale рядом с XGW (`TAILSCALE_MINIAPP_PLAN.md`): что о нём знать правилам и diag (Т1)
и что умеет карточка «Tailscale» в панели (Т2).

XGW Tailscale не ставит — он работает с уже установленным `tailscaled`. Настройки Tailscale
он меняет только кнопками карточки, каждую — по нажатию (CLI `tailscale`, демон XGW — root).
Как тот устроен на Linux (исходники Tailscale, проверено снимком Т0 на 1.104.1):

- свои сокеты (WireGuard, DERP, STUN, управление) он помечает меткой MARK в маске
  MARK_MASK, а правило `ip rule` 5210 ведёт их в таблицу main — мимо таблицы 52;
- адреса tailnet (100.64.0.0/10, fd7a:115c:a1e0::/48) и MagicDNS (100.100.100.100)
  маршрутизируются в интерфейс INTERFACE.

Без исключений в правилах XGW метку затирает «meta mark set 1», и Tailscale уходит в
Xray (К1); DNS к MagicDNS перехватывается (К2), blocked и v6_guard его отбивают (К3, К4).

Формат `tailscale status --json` (и `debug prefs`, `serve status --json`) Tailscale не
обещает сохранять: поля читаются осторожно, нет поля — «неизвестно», а не сбой.

Две команды карточки могут ждать человека, поэтому идут фоновыми заданиями (Job):
`tailscale login` ждёт входа в браузере, а `tailscale serve` — пока в tailnet не включат
HTTPS (и печатает ссылку, где это сделать). Остальные — обычный вызов runner.
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .net import cmd, lan
from .paths import Paths

INTERFACE = "tailscale0"
MARK = 0x80000
MARK_MASK = 0xFF0000
CGNAT = ipaddress.IPv4Network("100.64.0.0/10")
TAILNET6 = ipaddress.IPv6Network("fd7a:115c:a1e0::/48")
MAGIC_DNS = "100.100.100.100"
SOCKET = Path("run/tailscale/tailscaled.sock")  # от корня машины (paths.root)
ROUTES = ("direct", "vpn")
SERVE_PORT = 8443  # панель по tailnet: https://<шлюз>.<tailnet>.ts.net:8443/ (Serve, не Funnel)
FUNNEL_PORT = 443  # API приложения XGW для Android: https://<шлюз>.<tailnet>.ts.net/ (Funnel)
LOGIN_WAIT = "15m"  # столько `tailscale login` ждёт входа в браузере, потом выходит сам
COMMAND_TIMEOUT = 20.0
NETFILTER_OFF = 0  # prefs NetfilterMode: 0 — off, 1 — nodivert, 2 — on


def socket_path(paths: Paths) -> Path:
    return paths.root / SOCKET


def present(paths: Paths, sys_net: Path | None = None) -> bool:
    """tailscaled работает: есть его интерфейс или сокет управления. Без подпроцесса —
    правила собираются на каждом шаге демона. Сокет лежит в RuntimeDirectory службы и
    исчезает с её остановкой, интерфейс убирает `tailscaled --cleanup`."""
    try:
        if ((sys_net or lan.SYS_NET) / INTERFACE).exists():
            return True
        return socket_path(paths).exists()
    except OSError:
        return False


@dataclass(frozen=True)
class Status:
    """Нужное из `tailscale status --json`; пусто — поля нет."""

    backend: str = ""  # BackendState: Running, NeedsLogin, Stopped, Starting…
    auth_url: str = ""
    dns_name: str = ""  # Self.DNSName без точки в конце
    addresses: tuple[str, ...] = ()  # Self.TailscaleIPs
    magic_dns: bool | None = None  # CurrentTailnet.MagicDNSEnabled


def parse_status(text: str) -> Status | None:
    """Вывод `tailscale status --json`; None — не JSON-объект."""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    me = data.get("Self") if isinstance(data.get("Self"), dict) else {}
    tailnet = data.get("CurrentTailnet") if isinstance(data.get("CurrentTailnet"), dict) else {}
    addresses = me.get("TailscaleIPs")
    magic = tailnet.get("MagicDNSEnabled")
    return Status(
        backend=str(data.get("BackendState") or ""),
        auth_url=str(data.get("AuthURL") or ""),
        dns_name=str(me.get("DNSName") or "").rstrip("."),
        addresses=tuple(str(item) for item in addresses) if isinstance(addresses, list) else (),
        magic_dns=magic if isinstance(magic, bool) else None,
    )


def status(runner: cmd.Runner = cmd.run) -> Status | None:
    """`tailscale status --json`; None — CLI нет или он не ответил. Код возврата у CLI
    ненулевой и при NeedsLogin, а JSON он печатает всё равно."""
    try:
        return parse_status(runner(["tailscale", "status", "--json"], timeout=10.0, check=False))
    except cmd.CommandError:
        return None


@dataclass(frozen=True)
class Netcheck:
    udp: bool | None = None
    derp: str = ""  # «Nearest DERP»
    latency_ms: float | None = None  # задержка до него


_ITEM = re.compile(r"^\s*\*\s*([^:]+):\s*(.*?)\s*$")
_LATENCY = re.compile(r"^\s*-\s*\S+:\s*([\d.]+)\s*ms\s*\((.+)\)\s*$")


def parse_netcheck(text: str) -> Netcheck:
    """Отчёт `tailscale netcheck` (текст: строки «* UDP: true», «* Nearest DERP: …» и
    задержки «- fra: 88.6ms (Frankfurt)»). Строки portmap в начале пропускаются."""
    items: dict[str, str] = {}
    latency: dict[str, float] = {}
    for line in text.splitlines():
        match = _ITEM.match(line)
        if match:
            items[match.group(1).strip()] = match.group(2)
            continue
        match = _LATENCY.match(line)
        if match:
            latency.setdefault(match.group(2).strip(), float(match.group(1)))
    udp = items.get("UDP", "").lower()
    derp = items.get("Nearest DERP", "")
    return Netcheck(
        udp=True if udp == "true" else False if udp == "false" else None,
        derp=derp,
        latency_ms=latency.get(derp),
    )


def netcheck(runner: cmd.Runner = cmd.run) -> Netcheck | None:
    try:
        return parse_netcheck(runner(["tailscale", "netcheck"], timeout=30.0))
    except cmd.CommandError:
        return None


def default_route_dns(text: str) -> bool | None:
    """`resolvectl status tailscale0`: стоит ли у интерфейса DefaultRoute (Override local
    DNS в консоли tailnet — тогда через него идут все имена машины). None — не понять."""
    match = re.search(r"([+-])DefaultRoute\b", text)
    return None if match is None else match.group(1) == "+"


def override_dns(runner: cmd.Runner = cmd.run) -> bool | None:
    """К6: Override local DNS включён (tailscale0 — DNS по умолчанию). None — не понять."""
    try:
        text = runner(["resolvectl", "status", INTERFACE], timeout=10.0, check=False)
    except cmd.CommandError:
        return None
    return default_route_dns(text)


def cgnat(addresses: list[str] | tuple[str, ...]) -> list[str]:
    """Те из адресов IPv4, что попадают в 100.64.0.0/10."""
    found = []
    for item in addresses:
        try:
            address = ipaddress.ip_interface(item.strip()).ip
        except ValueError:
            continue
        if address.version == 4 and address in CGNAT:
            found.append(str(address))
    return found


def provider_cgnat(cfg, runner: cmd.Runner = cmd.run, *, skip: tuple[str, ...] = ()) -> list[str]:
    """К5: адреса, шлюз и DNS провайдера (WAN) из 100.64.0.0/10 — «адрес 100.64.0.0/10»,
    «шлюз …», «DNS …». Фаервол Tailscale (ts-input) отбросил бы их пакеты."""
    wan = lan.effective_wan(cfg, runner)
    found: list[str] = []
    for device, network, gateway in lan.occupied_networks(runner, skip=(*skip, INTERFACE)):
        if (not wan or device == wan) and network.overlaps(CGNAT):
            what = "шлюз" if gateway else "адрес"
            found.append(f"{what} {network.network_address if gateway else network}")
    if wan:
        try:
            text = runner(["resolvectl", "dns", wan], timeout=10.0, check=False)
        except cmd.CommandError:
            text = ""
        servers = text.partition(":")[2].split() if ":" in text else []
        found += [f"DNS {address}" for address in cgnat(servers)]
    return found


# --- Т2: карточка «Tailscale» ---------------------------------------------------------


@dataclass(frozen=True)
class Prefs:
    """Нужное из `tailscale debug prefs`; None — поля нет."""

    ssh: bool | None = None  # RunSSH: Tailscale SSH включён
    netfilter: int | None = None  # NetfilterMode
    accept_dns: bool | None = None  # CorpDNS: --accept-dns


def parse_prefs(text: str) -> Prefs | None:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    ssh, netfilter, dns = data.get("RunSSH"), data.get("NetfilterMode"), data.get("CorpDNS")
    return Prefs(
        ssh=ssh if isinstance(ssh, bool) else None,
        netfilter=netfilter if isinstance(netfilter, int) and not isinstance(netfilter, bool)
        else None,
        accept_dns=dns if isinstance(dns, bool) else None,
    )


def prefs(runner: cmd.Runner = cmd.run) -> Prefs | None:
    """Настройки узла: в `status --json` их нет, а `debug prefs` печатает их JSON."""
    try:
        return parse_prefs(runner(["tailscale", "debug", "prefs"], timeout=10.0))
    except cmd.CommandError:
        return None


def backend(port: int) -> str:
    """Куда Serve ведёт панель: на её адрес на самой машине."""
    return f"http://127.0.0.1:{port}"


def parse_serve(text: str, port: int, *, public: int = SERVE_PORT, funnel: bool = False
                ) -> bool | None:
    """`tailscale serve status --json`: ведёт ли порт public (по умолчанию SERVE_PORT) на
    port — панель или API приложения. Конфиг Serve: {"TCP": {"8443": {"HTTPS": true}},
    "Web": {"имя:8443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8781"}}}},
    "AllowFunnel": {"имя:443": true}}; пусто — выключено. funnel — ещё и открыт ли порт в
    интернет (AllowFunnel). None — не JSON."""
    try:
        data = json.loads(text) if text.strip() else {}
    except (json.JSONDecodeError, TypeError):
        return None
    if data is None:
        return False
    if not isinstance(data, dict):
        return None
    web = data.get("Web") if isinstance(data.get("Web"), dict) else {}
    allowed = data.get("AllowFunnel") if isinstance(data.get("AllowFunnel"), dict) else {}
    target = backend(port)
    for host, conf in web.items():
        if not str(host).endswith(f":{public}") or not isinstance(conf, dict):
            continue
        handlers = conf.get("Handlers") if isinstance(conf.get("Handlers"), dict) else {}
        root = handlers.get("/") if isinstance(handlers.get("/"), dict) else {}
        if str(root.get("Proxy") or "").rstrip("/") == target:
            return allowed.get(host) is True if funnel else True
    return False


def serve_status(port: int, runner: cmd.Runner = cmd.run) -> bool | None:
    try:
        return parse_serve(runner(["tailscale", "serve", "status", "--json"], timeout=10.0), port)
    except cmd.CommandError:
        return None


def funnel_status(port: int, runner: cmd.Runner = cmd.run) -> bool | None:
    """Funnel ведёт порт FUNNEL_PORT из интернета на API приложения (port)."""
    try:
        text = runner(["tailscale", "serve", "status", "--json"], timeout=10.0)
    except cmd.CommandError:
        return None
    return parse_serve(text, port, public=FUNNEL_PORT, funnel=True)


def login_command() -> list[str]:
    """Вход: CLI печатает ссылку и ждёт, AuthURL появляется и в `status --json`."""
    return ["tailscale", "login", f"--timeout={LOGIN_WAIT}"]


def serve_command(port: int) -> list[str]:
    """Панель по tailnet: --bg — Serve переживает перезапуск tailscaled и машины."""
    return ["tailscale", "serve", "--bg", f"--https={SERVE_PORT}", backend(port)]


def funnel_command(port: int) -> list[str]:
    """API приложения в интернет: --bg — Funnel переживает перезапуск. Если в правилах
    tailnet Funnel не разрешён, CLI печатает ссылку и ждёт, как serve с HTTPS."""
    return ["tailscale", "funnel", "--bg", f"--https={FUNNEL_PORT}", backend(port)]


def funnel_off(runner: cmd.Runner = cmd.run) -> None:
    runner(["tailscale", "funnel", f"--https={FUNNEL_PORT}", "off"], timeout=COMMAND_TIMEOUT)


def serve_off(runner: cmd.Runner = cmd.run) -> None:
    """Снимает только свой обработчик порта SERVE_PORT; чужие Serve не трогает."""
    runner(["tailscale", "serve", f"--https={SERVE_PORT}", "off"], timeout=COMMAND_TIMEOUT)


def set_ssh(on: bool, runner: cmd.Runner = cmd.run) -> None:
    """Tailscale SSH: `set` меняет только названную настройку (в отличие от `up`)."""
    runner(["tailscale", "set", "--ssh" if on else "--ssh=false"], timeout=COMMAND_TIMEOUT)


FIXES = {
    # К5: фаервол Tailscale (ts-input) отбрасывает адреса провайдера из 100.64.0.0/10.
    "netfilter": ["tailscale", "set", "--netfilter-mode=off"],
    # К6: Override local DNS — DNS машины идёт через tailscaled мимо VPN.
    "dns": ["tailscale", "set", "--accept-dns=false"],
}


def fix(name: str, runner: cmd.Runner = cmd.run) -> None:
    runner(FIXES[name], timeout=COMMAND_TIMEOUT)


_URL = re.compile(r"https://[^\s\"'<>]+")


def find_url(text: str) -> str:
    """Первая ссылка https в выводе CLI (ссылка входа, ссылка включения HTTPS)."""
    match = _URL.search(text)
    return match.group(0).rstrip(".,)") if match else ""


Spawn = Callable[[list[str], Path], "subprocess.Popen"]


def spawn(argv: list[str], output: Path) -> subprocess.Popen:
    """Фоновый процесс: вывод — в файл (на /run), ввода нет. Процесс остаётся в группе
    службы xgw и завершается сам (login — через LOGIN_WAIT, serve — когда HTTPS включат)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "wb") as out:
        return subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
            start_new_session=True,
        )


class Job:
    """Фоновая команда карточки: идёт ли, чем закончилась, что напечатала."""

    def __init__(self, argv: list[str], output: Path, starter: Spawn = spawn) -> None:
        self.argv = argv
        self.output = output
        self.proc = starter(argv, output)

    def code(self) -> int | None:
        """Код выхода; None — ещё идёт."""
        return self.proc.poll()

    def text(self) -> str:
        with contextlib.suppress(OSError):
            return self.output.read_text(encoding="utf-8", errors="replace")[-4000:]
        return ""

    def stop(self) -> None:
        if self.proc.poll() is None:
            with contextlib.suppress(OSError):
                self.proc.terminate()
