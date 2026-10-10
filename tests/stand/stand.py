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

import netns  # noqa: E402

from xgw.xraycore.api import parse_balancer_info  # noqa: E402
from xgw.xraycore.service import PidfileXrayService  # noqa: E402

UUID = "11111111-2222-3333-4455-666666666661"
FLAGS = {"nl": "🇳🇱", "de": "🇩🇪", "fr": "🇫🇷", "us": "🇺🇸"}


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


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
    _topology: netns.Topology | None = None

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
        if self.mode == "netns":
            self._topology = netns.Topology()
            self._topology.create()
        self._spawn(
            "origin", "inet",
            [sys.executable, str(HERE / "origin.py"), "--host", self.inet_ip,
             "--port", str(self.origin_port), "--dns-port", str(self.dns_port),
             "--answer", self.inet_ip],
            "READY",
        )
        for name in self.names:
            self.add_server(name)

    def add_server(self, name: str) -> Server:
        """Ещё один VLESS-сервер с реле перед ним (можно добавлять на ходу)."""
        server = Server(name, free_port(), free_port(), self.workdir / f"relay-{name}.mode")
        server.mode_file.write_text("pass", encoding="ascii")
        config = {
            "log": {"loglevel": "warning"},
            "inbounds": [{
                "listen": "127.0.0.1", "port": server.listen_port, "protocol": "vless",
                "settings": {"clients": [{"id": UUID}], "decryption": "none"},
            }],
            "outbounds": [{"protocol": "freedom"}],
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
        if self._topology is not None:
            self._topology.destroy()
            self._topology = None

    # --- шлюз ------------------------------------------------------------------

    def origin_url(self, path: str) -> str:
        return f"http://{self.inet_ip}:{self.origin_port}{path}"

    def set_subscription(self, names: tuple[str, ...] | list[str]) -> None:
        links = "\n".join(self.servers[name].link() for name in names)
        self.subscription.write_text(links + "\n", encoding="utf-8")

    def write_config(self, *, max_members: int = 2, watchdog_s: int = 2) -> None:
        """Конфиг шлюза: подписка из файла, пробы на origin, interval 10 с, sampling 1."""
        dns = f"{self.inet_ip}:{self.dns_port}" if self.dns_port != 53 else self.inet_ip
        self.config_file.write_text(
            f"""
[capture]            # перехват — этап 3; здесь XGW только управляет Xray
lan = false
local = false

[[subscriptions]]
name = "stand"
url = "{self.subscription.as_uri()}"
refresh_minutes = 1

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
direct_domains = []
direct_ips = []

[dns]
proxy_servers = ["{dns}"]
direct_servers = []
bootstrap = ["udp://{self.inet_ip}:{self.dns_port}"]

[xray]
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
""",
            encoding="utf-8",
        )

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
