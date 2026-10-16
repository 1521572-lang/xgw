"""Стенд XGW: «интернет» с замораживающим провайдером и шлюз на настоящем Xray.

Состав (раздел 9 ТЗ): origin с DNS-заглушкой, несколько VLESS-серверов Xray,
перед каждым — «замораживающее» реле; шлюз — XGW с конфигом стенда и подпиской
из локального файла.

Два режима с одними и теми же проверками:
  loopback — все процессы на 127.0.0.1, без root, на любой ОС. Его достаточно
             для проверок этапа 2: переключение, применение без разрыва, замена
             участника. Перехвата трафика в этом режиме нет.
  netns    — пространства имён inet/gw/lan (Linux, root): отдельные сетевые
             стеки, настоящие метки SO_MARK; на нём же строятся проверки этапа 3.
"""

from __future__ import annotations

import contextlib
import json
import os
import random
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[1] / "src"
for _path in (str(HERE), str(SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

sys.path.insert(0, str(HERE.parent))  # tests/ports.py

import netns  # noqa: E402
from ports import free_port  # noqa: E402

from xgw.xraycore.api import parse_balancer_info  # noqa: E402
from xgw.xraycore.service import PidfileXrayService  # noqa: E402

UUID = "11111111-2222-3333-4455-666666666661"
# Метка «мимо перехвата» шлюза стенда без перехвата. У XGW, установленного на самой машине,
# по умолчанию та же метка (2), и его правило loopback_guard отбрасывает такие пакеты к
# 127.0.0.0/8, а в режиме loopback узлы стенда живут именно там (отчёт 0.1.4, G5).
STAND_BYPASS_MARK = 0x5E
FLAGS = {"nl": "🇳🇱", "de": "🇩🇪", "fr": "🇫🇷", "us": "🇺🇸"}


def free_block(count: int = 16) -> int:
    """Начало свободного блока подряд идущих портов — для probe-inbounds шлюза.

    Блок берётся ниже диапазона временных портов ОС: иначе порты base+1, base+2…
    достались бы другим процессам стенда, которые просят «любой свободный».
    """
    for _ in range(50):
        base = random.randrange(21000, 29000)
        try:
            for port in range(base, base + count):
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", port))
        except OSError:
            continue
        return base
    raise RuntimeError("не нашлось свободного блока портов")


@dataclass
class Server:
    """VLESS-сервер стенда и реле перед ним."""

    name: str
    listen_port: int  # порт самого Xray-сервера (за реле)
    relay_port: int  # порт реле — его и видит шлюз
    mode_file: Path
    mode: str = "pass"
    latency_ms: int = 0

    @property
    def domain(self) -> str:
        return f"{self.name}.stand.test"

    def set_mode(self, mode: str) -> None:
        """pass | freeze_after=N | drop | blackhole — реле подхватит за 0,1 с."""
        self.mode = mode
        self._write()

    def set_latency(self, milliseconds: int) -> None:
        """Задержка первого ответа: делает сервер медленнее остальных для leastPing."""
        self.latency_ms = milliseconds
        self._write()

    def _write(self) -> None:
        self.mode_file.write_text(f"{self.mode};latency={self.latency_ms}", encoding="ascii")
        time.sleep(0.3)

    def link(self) -> str:
        label = quote(f"{FLAGS[self.name]} {self.name.upper()}-stand")
        return (
            f"vless://{UUID}@{self.domain}:{self.relay_port}"
            f"?type=tcp&security=none&encryption=none#{label}"
        )


@dataclass
class Stand:
    workdir: Path
    xray_bin: Path
    mode: str = "loopback"
    names: tuple[str, ...] = ("nl", "de", "fr")
    servers: dict[str, Server] = field(default_factory=dict)
    _procs: list[subprocess.Popen] = field(default_factory=list)
    # Готовая топология (шлюз — контейнер, см. machine.py); без неё режим netns
    # создаёт и удаляет свои пространства имён сам.
    _topology: netns.Topology | None = None
    _own_topology: bool = False
    ipv6: bool = False  # netns: IPv6 на стыке шлюза и «интернета», origin слушает и по IPv6

    def __post_init__(self) -> None:
        self.logs = self.workdir / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.root = self.workdir / "root"  # XGW_ROOT шлюза
        self.subscription = self.workdir / "subscription.txt"
        self.config_file = self.workdir / "config.toml"
        if self.mode == "netns":
            self.inet_ip = netns.INET_IP
            self.origin_port, self.dns_port = 8080, 53
        else:
            self.inet_ip = "127.0.0.1"
            self.origin_port, self.dns_port = free_port(), free_port()
        self.ports = {name: free_port() for name in ("api", "metrics", "socks", "http")}
        self.ports["probe_base"] = free_block()

    # --- запуск процессов ------------------------------------------------------

    def _prefix(self, where: str) -> list[str]:
        if self._topology is None:
            return []
        return self._topology.prefix(getattr(self._topology, where))

    def _spawn(self, name: str, where: str, argv: list[str], ready: str) -> subprocess.Popen:
        """Запускает процесс стенда и ждёт строки готовности в его логе."""
        log_path = self.logs / f"{name}.log"
        with open(log_path, "wb") as log:
            proc = subprocess.Popen(
                [*self._prefix(where), *argv], stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, env=self._env(),
            )
        self._procs.append(proc)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if ready in log_path.read_text(encoding="utf-8", errors="replace"):
                return proc
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        raise RuntimeError(f"{name} не запустился: {self.tail(name)}")

    def tail(self, name: str, lines: int = 15) -> str:
        with contextlib.suppress(OSError):
            text = (self.logs / f"{name}.log").read_text(encoding="utf-8", errors="replace")
            return "\n".join(text.splitlines()[-lines:])
        return ""

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update(
            XGW_ROOT=str(self.root),
            XGW_XRAY_BIN=str(self.xray_bin),
            XGW_XRAY_SERVICE="process",  # systemd-юнита на стенде нет
            PYTHONPATH=str(SRC),
            PYTHONIOENCODING="utf-8",
        )
        return env

    def start(self) -> None:
        if self.mode == "netns" and self._topology is None:
            self._topology = netns.Topology(ipv6=self.ipv6)
            self._topology.create()
            self._own_topology = True
        also = ["--dns-also", netns.INET_DNS_IP] if self.mode == "netns" else []
        if self.ipv6:
            also += ["--answer6", netns.INET_IP6]
        self._spawn(
            "origin", "inet",
            [sys.executable, str(HERE / "origin.py"), "--host", self.inet_ip,
             "--port", str(self.origin_port), "--dns-port", str(self.dns_port),
             "--answer", self.inet_ip, "--sub-file", str(self.subscription), *also],
            "READY",
        )
        if self.ipv6:
            self._spawn(
                "origin6", "inet",
                [sys.executable, str(HERE / "origin.py"), "--host", netns.INET_IP6,
                 "--port", str(self.origin_port)],
                "READY",
            )
        for name in self.names:
            self.add_server(name)

    def add_server(self, name: str) -> Server:
        """Ещё один VLESS-сервер с реле перед ним (можно добавлять на ходу)."""
        server = Server(name, free_port(), free_port(), self.workdir / f"relay-{name}.mode")
        server.mode_file.write_text("pass", encoding="ascii")
        stub = self.inet_ip if self.dns_port == 53 else {
            "address": self.inet_ip, "port": self.dns_port,
        }
        config = {
            "log": {"loglevel": "warning"},
            # Сниффинг на шлюзе подставляет домен вместо IP — сервер разрешает его
            # сам, как настоящий VPN-сервер; на стенде его резолвер — DNS-заглушка.
            "dns": {"servers": [stub]},
            "inbounds": [{
                "listen": "127.0.0.1", "port": server.listen_port, "protocol": "vless",
                "settings": {"clients": [{"id": UUID}], "decryption": "none"},
            }],
            # finalRules: с 26.10.10 freedom за VLESS-inbound'ом по умолчанию не пускает к
            # частным адресам и loopback (защита сервера), а «интернет» стенда в режиме
            # loopback — это 127.0.0.1. Xray 26.3.27 поля не знает и пропускает.
            "outbounds": [{"protocol": "freedom", "settings": {
                "domainStrategy": "UseIPv4", "finalRules": [{"action": "allow"}],
            }}],
        }
        config_path = self.workdir / f"server-{name}.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        self._spawn(f"server-{name}", "inet",
                    [str(self.xray_bin), "run", "-c", str(config_path)], "started")
        self._spawn(
            f"relay-{name}", "inet",
            [sys.executable, str(HERE / "freeze_relay.py"),
             "--listen", f"{self.inet_ip}:{server.relay_port}",
             "--upstream", f"127.0.0.1:{server.listen_port}",
             "--mode-file", str(server.mode_file)],
            "READY",
        )
        self.servers[name] = server
        return server

    def stop(self) -> None:
        with contextlib.suppress(Exception):
            self.xray_service().stop()
        for proc in reversed(self._procs):
            if proc.poll() is None:
                proc.terminate()
        for proc in self._procs:
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=5)
            if proc.poll() is None:
                proc.kill()
        self._procs.clear()
        if self._topology is not None and self._own_topology:
            self._topology.destroy()
            self._topology = None

    # --- шлюз ------------------------------------------------------------------

    def origin_url(self, path: str) -> str:
        return f"http://{self.inet_ip}:{self.origin_port}{path}"

    def set_subscription(self, names: tuple[str, ...] | list[str]) -> None:
        links = "\n".join(self.servers[name].link() for name in names)
        self.subscription.write_text(links + "\n", encoding="utf-8")

    def write_config(
        self, *, max_members: int = 2, watchdog_s: int = 2,
        capture: bool = False, fail_mode: str = "closed", extra: str = "",
        panel: bool = False, subscription: bool = True,
        direct_domains: tuple[str, ...] = (), ipv6: str = "off", method: str = "tproxy",
        refresh_minutes: int = 1, containers: bool = True,
    ) -> None:
        """Конфиг шлюза: подписка из файла, пробы на origin, interval 10 с, sampling 1.

        panel=True — с панелью управления, как на установленной машине; на стенде
        она по умолчанию выключена, чтобы шлюз не открывал лишний порт.
        subscription=False — без подписки: её добавят в панели (subscription_url).

        capture=True (только netns) — шлюз с перехватом: LAN на lan0, трафик самого
        шлюза тоже через Xray, одно устройство в обход VPN, прямой DNS на втором
        адресе «интернета». Без него XGW только управляет Xray (проверки этапа 2).

        refresh_minutes — как часто демон обновляет подписку. Обновление заодно чинит
        испорченный рабочий конфиг; тесту, которому нужен Xray, сломанный надолго,
        нужен и большой интервал.
        """
        dns = f"{self.inet_ip}:{self.dns_port}" if self.dns_port != 53 else self.inet_ip
        if capture:
            network = f"""
[network]
lan_if = "lan0"
lan_address = "{netns.GW_LAN_IP}/24"
ipv6 = "{ipv6}"
dhcp_range = "192.168.50.110,192.168.50.150,1h"
static_leases = ["{netns.LAN_BYPASS_MAC},{netns.LAN_BYPASS_IP},tv"]
bypass_hosts = ["{netns.LAN_BYPASS_MAC}"]

[capture]
lan = true
local = true
method = "{method}"
fail_mode = "{fail_mode}"
containers = {"true" if containers else "false"}
"""
            direct_dns = f'["{netns.INET_DNS_IP}"]'
        else:
            network = (
                f"\n[capture]\nlan = false\nlocal = false\nmark_bypass = {STAND_BYPASS_MARK}\n"
            )
            direct_dns = "[]"
        if not panel:
            extra += "\n[panel]\nenabled = false\n"
        source = f"""
[[subscriptions]]
name = "stand"
url = "{self.subscription.as_uri()}"
refresh_minutes = {refresh_minutes}
""" if subscription else ""
        self.config_file.write_text(
            f"""{network}{source}
[filters]
exclude_regex = ""
max_members = {max_members}
rotate_after_min = 0

[probe]
url = "{self.origin_url('/64k')}"
trace_url = "{self.origin_url('/trace')}"
interval = "10s"
sampling = 1
timeout = "3s"
scan_spares_minutes = 1

[routing]
direct_domains = {json.dumps(list(direct_domains))}
direct_ips = []

[dns]
proxy_servers = ["{dns}"]
direct_servers = {direct_dns}
bootstrap = ["udp://{self.inet_ip}:{self.dns_port}"]

[xray]
# Стенд проверяет тот Xray, что дан в XGW_XRAY_BIN, какой бы версии он ни был: установка
# на «одноразовой машине» его не меняет (сети там нет).
version = "latest"
api_port = {self.ports['api']}
metrics_port = {self.ports['metrics']}
socks_port = {self.ports['socks']}
http_port = {self.ports['http']}
probe_port_base = {self.ports['probe_base']}

[apply]
restart_window = "00:00-00:01"

[watchdog]
interval_s = {watchdog_s}
wan_check = "{self.inet_ip}:{self.origin_port}"
{extra}""",
            encoding="utf-8",
        )

    def subscription_url(self) -> str:
        """Та же подписка по HTTP — как у настоящего провайдера, с токеном в адресе."""
        return self.origin_url("/sub/s3cr3t-stand-token")

    def xgw(self, *args: str, timeout: float = 120) -> subprocess.CompletedProcess:
        """Команда `xgw …` в контексте шлюза."""
        return subprocess.run(
            [*self._prefix("gw"), sys.executable, "-m", "xgw", *args,
             "--config", str(self.config_file)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=self._env(), timeout=timeout,
        )

    def xgw_json(self, *args: str) -> dict:
        result = self.xgw(*args, "--json")
        if result.returncode != 0:
            raise RuntimeError(f"xgw {' '.join(args)}: {result.stderr.strip()}")
        return json.loads(result.stdout)

    def start_daemon(self) -> subprocess.Popen:
        log_path = self.logs / "daemon.log"
        with open(log_path, "wb") as log:
            proc = subprocess.Popen(
                [*self._prefix("gw"), sys.executable, "-m", "xgw", "run",
                 "--config", str(self.config_file)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=self._env(),
            )
        self._procs.append(proc)
        return proc

    def gw_popen(self, name: str, argv: list[str]) -> subprocess.Popen:
        """Произвольный процесс в контексте шлюза (свой Xray, клиент загрузки)."""
        log_path = self.logs / f"{name}.log"
        with open(log_path, "wb") as log:
            proc = subprocess.Popen(
                [*self._prefix("gw"), *argv], stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, env=self._env(),
            )
        self._procs.append(proc)
        return proc

    def xray_api(self, command: str, *args: str) -> str:
        """`xray api <command>` к ядру шлюза."""
        result = subprocess.run(
            [*self._prefix("gw"), str(self.xray_bin), "api", command,
             "-s", f"127.0.0.1:{self.ports['api']}", "-t", "5", *args],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stdout + result.stderr).strip())
        return result.stdout

    def selecting(self) -> tuple[str, ...]:
        """Кого сейчас выбирает балансировщик — по `xray api bi auto`."""
        try:
            return parse_balancer_info(self.xray_api("bi", "auto")).selects
        except RuntimeError:
            return ()

    def xray_log(self, lines: int = 15) -> str:
        """Хвост вывода ядра шлюза — в сообщения об ошибках."""
        with contextlib.suppress(OSError):
            text = (self.root / "run/xgw/xray.log").read_text(encoding="utf-8", errors="replace")
            return "\n".join(text.splitlines()[-lines:])
        return ""

    def applied(self) -> dict:
        return json.loads((self.root / "etc/xgw/xray/config.json").read_text(encoding="utf-8"))

    def xray_service(self):
        return PidfileXrayService(
            self.xray_bin, self.root / "etc/xgw/xray/config.json",
            self.root / "run/xgw/xray.pid",
        )

    def xray_pid(self) -> int:
        return int((self.root / "run/xgw/xray.pid").read_text(encoding="ascii").strip())

    def server_of(self, tag: str) -> Server:
        """Сервер стенда по тегу узла: страна в теге — это имя сервера."""
        return self.servers[tag.split("-")[1]]

    # --- готовые сценарии ------------------------------------------------------

    def members(self) -> dict[str, dict]:
        return {member["tag"]: member for member in self.xgw_json("servers")["members"]}

    def up(self, names=None, **config) -> list[str]:
        """Поднимает шлюз и ждёт, пока ядро проверит всех участников. Возвращает их теги."""
        self.set_subscription(names or self.names)
        self.write_config(**config)
        result = self.xgw("apply", "--now")
        assert result.returncode == 0, f"{result.stderr}\n{self.xray_log()}"
        assert "перезапуском" in result.stdout  # первый запуск — это запуск Xray
        alive = wait_for(
            lambda: (m := self.members()) and all(x["alive"] for x in m.values()) and m, 40
        )
        assert alive, f"участники не ожили: {self.members()}"
        return list(alive)

    def make_fastest(self, tag: str, cycle: float = 10.0) -> None:
        """Делает узел заведомо самым быстрым: leastPing выбирает его, пока он жив.

        Мало дождаться, что узел выбран: при равных задержках это бывает и
        случайно, а следующая проба выбор перевернёт. Ждём, пока ядро само
        замерит задержку у остальных участников.
        """
        for server in self.servers.values():
            server.set_latency(0 if server is self.server_of(tag) else 250)

        def settled() -> bool:
            others = [m for name, m in self.members().items() if name != tag and m["alive"]]
            slower = all((member["delay_ms"] or 0) >= 200 for member in others)
            return slower and self.selecting() == (tag,)

        assert wait_for(settled, 3 * cycle + 5), (
            f"балансировщик не выбрал {tag}: {self.selecting()}, {self.members()}"
        )

    # --- устройство в LAN и сам шлюз (режим netns) ------------------------------

    def client(self, where: str, *args: str, timeout: float = 40) -> dict:
        """`lan_client.py …` в пространстве имён lan или gw; ответ — словарь."""
        result = subprocess.run(
            [*self._prefix(where), sys.executable, str(HERE / "lan_client.py"), *args],
            capture_output=True, text=True, timeout=timeout,
        )
        try:
            return json.loads(result.stdout.strip().splitlines()[-1])
        except (IndexError, ValueError):
            raise RuntimeError(f"lan_client {args}: {result.stdout}{result.stderr}") from None

    def lan(self, *args: str) -> dict:
        """Запрос от устройства в LAN."""
        return self.client("lan", *args)

    def exit_ip(self, where: str = "lan", *args: str) -> str:
        """С какого адреса запрос дошёл до origin: адрес «интернета» — значит через
        VPN-сервер, адрес WAN шлюза — напрямую. Пусто — запрос не прошёл."""
        reply = self.client(where, "get", self.origin_url("/trace"), "--timeout", "4", *args)
        for line in reply.get("body", "").splitlines():
            if line.startswith("ip="):
                return line[3:]
        return ""

    def exit_ip6(self, where: str = "gw", *args: str) -> str:
        """То же по IPv6: адрес «интернета» — через VPN-сервер, адрес WAN шлюза — напрямую."""
        url = f"http://[{netns.INET_IP6}]:{self.origin_port}/trace"
        reply = self.client(where, "get", url, "--timeout", "4", *args)
        for line in reply.get("body", "").splitlines():
            if line.startswith("ip="):
                return line[3:]
        return ""

    def run_in(self, where: str, *argv: str) -> subprocess.CompletedProcess:
        """Произвольная команда в пространстве имён inet, gw или lan."""
        return subprocess.run(
            [*self._prefix(where), *argv], capture_output=True, text=True, timeout=30,
        )

    def gw_run(self, *argv: str, check: bool = True) -> str:
        """Команда в пространстве имён шлюза (nft, ip); возвращает её вывод."""
        result = self.run_in("gw", *argv)
        if check and result.returncode != 0:
            raise RuntimeError(f"{' '.join(argv)}: {result.stdout}{result.stderr}")
        return result.stdout

    def serve_in_gw(self, port: int, country: str, host: str = "127.0.0.1") -> subprocess.Popen:
        """HTTP-служба, слушающая только loopback шлюза: 127.0.0.1 или ::1 (отвечает /trace)."""
        return self._spawn(
            f"service-{port}", "gw",
            [sys.executable, str(HERE / "origin.py"), "--host", host,
             "--port", str(port), "--country", country],
            "READY",
        )

    def start_telegram(self, port: int = 8081) -> str:
        """Поддельный Telegram Bot API на стороне «интернета». Возвращает его адрес."""
        self._spawn(
            "telegram", "inet",
            [sys.executable, str(HERE.parent / "fake_telegram.py"),
             "--host", self.inet_ip, "--port", str(port)],
            "READY",
        )
        return f"http://{self.inet_ip}:{port}"

    def telegram(self, path: str, port: int = 8081):
        """Запрос к управлению поддельным Telegram; ответ разобран из JSON."""
        script = (
            "import json, sys, urllib.request\n"
            "print(urllib.request.urlopen(sys.argv[1], timeout=10).read().decode())"
        )
        result = self.run_in(
            "inet", sys.executable, "-c", script, f"http://{self.inet_ip}:{port}{path}"
        )
        if result.returncode != 0:
            raise RuntimeError(f"fake telegram {path}: {result.stderr}")
        return json.loads(result.stdout)

    def start_dnsmasq(self) -> subprocess.Popen:
        """dnsmasq шлюза с конфигом, который выдаёт `xgw net show dnsmasq`. Пользователь,
        pid-файл и файл аренд — свои у стенда: каталогов службы xgw-dhcp тут нет."""
        conf = self.workdir / "dnsmasq.conf"
        shown = self.xgw("net", "show", "dnsmasq")
        assert shown.returncode == 0, shown.stderr
        own = ("user=", "pid-file=", "dhcp-leasefile=")
        conf.write_text(
            "".join(line for line in shown.stdout.splitlines(keepends=True)
                    if not line.startswith(own)),
            encoding="utf-8",
        )
        return self._spawn(
            "dnsmasq", "gw",
            ["dnsmasq", "--keep-in-foreground", f"--conf-file={conf}", "--user=root",
             f"--dhcp-leasefile={self.workdir / 'dnsmasq.leases'}", "--pid-file=",
             "--log-dhcp", "--log-facility=-"],
            "started",
        )


def wait_for(predicate, timeout: float, step: float = 0.5):
    """Ждёт, пока predicate() не вернёт истинное значение; возвращает его или None."""
    deadline = time.monotonic() + timeout
    while True:
        value = predicate()
        if value:
            return value
        if time.monotonic() >= deadline:
            return None
        time.sleep(step)
