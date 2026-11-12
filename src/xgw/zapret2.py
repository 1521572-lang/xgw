"""Выбранные HTTPS-домены через nfqws2: самостоятельный режим и дополнение к VPN.

XGW не запускает install_easy и не меняет sysctl. Два собственных SO_MARK не
пересекаются с bypass/TPROXY/Tailscale. Разрешение WAN имеет срок жизни в nft;
без слушателя NFQUEUE пакеты не проходят (нет queue bypass).
"""

from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
import re
import stat
import time
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urljoin, urlsplit

from . import log
from .net import cmd

if TYPE_CHECKING:
    from .config import Config
    from .watch.checks import DownloadResult

MARK = 0x10000000
FAKE_BIT = 0x40000000
FAKE_MARK = MARK | FAKE_BIT
MARKS = f"{{ {MARK:#x}, {FAKE_MARK:#x} }}"
OUT = "xgw-zapret2"
DIRECT = "xgw-without-vpn"
PROBE = "xgw-zapret2-probe"
UNIT = "xgw-zapret2.service"
LIVE = "zapret2_live"
BUDGET = "zapret2_probe_budget"
PROBE_BYTES = 64 * 1024
MIN_BODY = 16 * 1024
# Резерв на тело, TLS и заголовки; списывается до запроса, включая прерванный.
PROBE_CHARGE = 256 * 1024
REDIRECT_LIMIT = 5
# Самостоятельный режим: после запуска nfqws2 очередь NFQUEUE появляется не мгновенно (Lua,
# netlink). До START_WAIT секунд обработчик не считается упавшим; всё это время выбранные
# домены закрыты, а демон шагает каждые START_POLL секунд (отчёт standalone r3, п. 385).
START_WAIT = 20.0
START_POLL = 2.0
_DOMAIN = re.compile(r"(?:domain|full):[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?")


def config_key(cfg: Config) -> str:
    """Версия настроек для сверки запроса окна с применённым снимком демона."""
    raw = json.dumps(asdict(cfg.zapret2), sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def matches(host: str, domains: list[str]) -> bool:
    for item in domains:
        kind, _, name = item.partition(":")
        if host == name or (kind == "domain" and host.endswith("." + name)):
            return True
    return False


def expiry(url: str) -> int | None:
    """Подсказка из параметра expire, не проверка подписи или доступности URL."""
    try:
        values = parse_qs(urlsplit(url).query, max_num_fields=100).get("expire", [])
        if len(values) == 1 and values[0].isascii() and values[0].isdigit():
            value = int(values[0])
            if 0 < value <= 253402300799:
                return value
    except ValueError:
        pass
    return None


def probe_row(index: int, result) -> dict:
    phase = result.phase if result.phase in (
        "connect", "tls", "request", "headers", "body") else "unknown"
    kind = result.kind if result.kind in (
        "http", "timeout", "stall", "truncated", "reset", "tls", "connect", "proxy",
        "cancelled", "io") else "unknown"
    if result.ok:
        verdict = "ok"
    elif phase == "connect":
        verdict = kind
    elif result.status == 204:
        verdict = "empty_body"
    elif 300 <= result.status < 400:
        verdict = "redirect"
    elif 200 <= result.status < 300 and kind == "http" and result.downloaded < MIN_BODY:
        verdict = "short_body"
    elif result.status >= 400:
        verdict = "http_error"
    else:
        verdict = kind
    return {"probe": index, "path": "zapret2", "ok": result.ok, "verdict": verdict,
            "phase": phase, "http": 0 if phase == "connect" else result.status,
            "connect_http": result.status if phase == "connect" else 0,
            "bytes": result.downloaded, "redirects": 0, "checked_at": int(time.time())}


def validate(cfg: Config) -> list[str]:
    z = cfg.zapret2
    problems = []
    if z.mode not in ("off", "selective", "compare", "standalone"):
        problems.append("mode: ожидается off, selective, compare или standalone")
    if not z.domains or any(not _DOMAIN.fullmatch(d) for d in z.domains):
        problems.append("domains: нужны domain:имя или full:имя")
    if z.strategy not in ("multisplit", "multidisorder"):
        problems.append("strategy: ожидается multisplit или multidisorder")
    if not 1 <= z.queue_num <= 65535 or not 1024 <= z.probe_port <= 65535:
        problems.append("queue_num или probe_port вне допустимого диапазона")
    if z.probe_port in (cfg.capture.tproxy_port, cfg.xray.metrics_port, cfg.xray.socks_port,
                        cfg.xray.http_port, cfg.panel.port, cfg.panel.app_port, cfg.core.api_port):
        problems.append("probe_port занят другой службой XGW")
    if not 60 <= z.check_seconds <= 900 or not 60 <= z.retry_seconds <= 3600:
        problems.append("check_seconds: 60–900; retry_seconds: 60–3600")
    if not 1 <= z.daily_probe_mb <= 1024:
        problems.append("daily_probe_mb: ожидается 1–1024")
    for value in (z.binary, z.lua_dir):
        if not value.startswith("/") or any(c in value for c in "\r\n\x00"):
            problems.append("пути binary и lua_dir должны быть абсолютными Linux-путями")
    if len(z.probe_urls) > 4:
        problems.append("probe_urls: не больше четырёх адресов")
    if z.mode == "compare" and len(z.probe_urls) != 2:
        problems.append("compare требует ровно два HTTPS-адреса")
    for value in z.probe_urls:
        try:
            u = urlsplit(value)
            ok = (u.scheme == "https" and u.port in (None, 443) and not u.username
                  and not u.password and not u.fragment and matches(u.hostname or "", z.domains)
                  and not any(ord(c) < 33 or ord(c) > 126 for c in value))
        except ValueError:
            ok = False
        if not ok:
            problems.append("probe_urls: нужны HTTPS-адреса выбранных доменов, порт 443")
            break
    # В первой версии YouTube нельзя разделить: страница и видеосеть меняют выход вместе.
    if (any("youtube" in d or "googlevideo" in d for d in z.domains)
            and not {"domain:youtube.com", "domain:googlevideo.com"} <= set(z.domains)):
        problems.append("для YouTube нужны вместе youtube.com и googlevideo.com")
    if z.probe_enabled and cfg.routing.proxy_domains:
        problems.append("первая версия требует общего маршрута через VPN (proxy_domains пуст)")
    if z.enabled and not cfg.network.block_quic:
        problems.append("для общего выхода страницы и видео требуется network.block_quic = true")
    if z.mode == "standalone" and cfg.capture.fail_mode != "closed":
        problems.append("standalone требует capture.fail_mode = closed")
    for mark in (cfg.capture.mark_proxy, cfg.capture.mark_bypass, cfg.capture.mark_containers):
        if mark & (MARK | FAKE_BIT):
            problems.append("метки capture пересекаются с зарезервированными битами zapret2")
            break
    if problems and z.mode != "standalone":
        z.mode = "off"
    prefix = "zapret2 не готов" if z.mode == "standalone" else "zapret2 выключен"
    return [f"{prefix}: {p}" for p in problems]


def configured(cfg: Config) -> bool:
    """Для YouTube нужны обе стороны; пустой адрес никогда не заменяется сторонним CDN."""
    z = cfg.zapret2
    hosts = [urlsplit(url).hostname or "" for url in z.probe_urls]
    if not hosts:
        return False
    if "domain:youtube.com" in z.domains:
        return all(any(matches(host, [domain]) for host in hosts)
                   for domain in ("domain:youtube.com", "domain:googlevideo.com"))
    return True


def active(config: dict) -> bool:
    return any(r.get("outboundTag") == OUT and r.get("inboundTag") != [PROBE]
               for r in config.get("routing", {}).get("rules", []))


def standalone(config: dict | None) -> bool:
    return any(o.get("tag") == DIRECT for o in (config or {}).get("outbounds", []))


def without_vpn(config: dict, cfg: Config, capture_tags: list[str]) -> dict:
    """Самостоятельный маршрут: нет серверов, балансировщиков и проб VPN."""
    from .generator.builder import _dns_server

    result = copy.deepcopy(config)
    result.pop("burstObservatory", None)
    direct = next(o for o in result["outbounds"] if o["tag"] == "direct")
    result["outbounds"] = [direct, {**copy.deepcopy(direct), "tag": DIRECT},
                           {"tag": "block", "protocol": "blackhole"},
                           next(o for o in result["outbounds"] if o["tag"] == "dns-out"),
                           {"tag": OUT, "protocol": "freedom",
                            "settings": {"domainStrategy": "UseIPv4"},
                            "streamSettings": {"sockopt": {"mark": MARK}}}]
    # DNS и LAN доступны без VPN. Правило доменов выше общих прямых исключений.
    clients = [*capture_tags, "http-in", "socks-in"]
    for inbound in result["inbounds"]:
        if inbound["tag"] in clients:
            inbound["sniffing"] = {"enabled": True, "destOverride": ["http", "tls", "quic"]}
    result["routing"] = {"domainStrategy": "IPIfNonMatch", "rules": [
        {"type": "field", "inboundTag": capture_tags, "port": "53",
         "outboundTag": "dns-out"},
        {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
        {"type": "field", "inboundTag": clients, "domain": cfg.zapret2.domains,
         "network": "tcp", "port": "443", "outboundTag": OUT},
        {"type": "field", "inboundTag": clients, "domain": cfg.zapret2.domains,
         "outboundTag": "block"},
        {"type": "field", "network": "tcp,udp", "outboundTag": DIRECT},
    ]}
    result["dns"]["servers"] = [address if port is None else {"address": address, "port": port}
                                for address, port in map(_dns_server, cfg.dns.direct_servers)]
    result["dns"]["hosts"] = {}
    return result


def patch(config: dict, cfg: Config, *, enabled: bool = False, probe: bool = True) -> dict:
    """Статические вход/выход и временное правило. Полная сборка всегда начинает с VPN."""
    from .generator import builder

    result = copy.deepcopy(config)
    rules = [r for r in result["routing"]["rules"]
             if r.get("outboundTag") != OUT and r.get("inboundTag") != [PROBE]]
    result["routing"]["rules"] = rules
    result["inbounds"] = [i for i in result["inbounds"] if i.get("tag") != PROBE]
    result["outbounds"] = [o for o in result["outbounds"] if o.get("tag") != OUT]
    if not probe or not cfg.zapret2.probe_enabled:
        return result
    password, _ = builder.probe_state(config)
    if not password or any(i.get("port") == cfg.zapret2.probe_port for i in result["inbounds"]):
        raise ValueError("служебный вход zapret2 недоступен")
    result["outbounds"].append({
        "tag": OUT, "protocol": "freedom", "settings": {"domainStrategy": "UseIPv4"},
        "streamSettings": {"sockopt": {"mark": MARK}},
    })
    result["inbounds"].append({
        "tag": PROBE, "protocol": "http", "listen": "127.0.0.1", "port": cfg.zapret2.probe_port,
        "settings": {"accounts": [{"user": builder.PROBE_USER, "pass": password}]},
    })
    # Даже с паролем этот вход не является общим прокси; private всегда закрыт.
    rules[:0] = [
        {"type": "field", "inboundTag": [PROBE], "ip": ["geoip:private"],
         "outboundTag": "block"},
        {"type": "field", "inboundTag": [PROBE], "domain": cfg.zapret2.domains,
         "network": "tcp", "port": "443", "outboundTag": OUT},
        {"type": "field", "inboundTag": [PROBE], "outboundTag": "block"},
    ]
    if enabled and cfg.zapret2.mode == "selective" and not builder.applied_whole(config):
        # Прямые исключения, устройства и пул главнее. Служебные входы не включены.
        at = next((n for n, r in enumerate(rules) if
                   r.get("balancerTag") == builder.YOUTUBE_BALANCER
                   or (cfg.routing.proxy_domains and r.get("domain") == cfg.routing.proxy_domains)
                   or r.get("network") == "tcp,udp"), None)
        if at is None:
            raise ValueError("нет общего правила маршрутизации")
        rules.insert(at, {
            "type": "field", "inboundTag": ["tproxy-in", "tproxy-in6", "tun-in"],
            "domain": list(cfg.zapret2.domains), "network": "tcp", "port": "443",
            "outboundTag": OUT,
        })
    return result


def guard_blocks(queue: int | None) -> list[list[str]]:
    """Внутри xgw_guard: разрешение с TTL, NFQUEUE после NAT, notrack своих копий."""
    if queue is None:
        return []
    return [
        [f"  set {LIVE} {{", "    type mark", "    flags timeout", "  }"],
        ["  chain zapret2_raw {", "    type filter hook output priority -401; policy accept;",
         f"    meta mark {FAKE_MARK:#x} notrack", "  }"],
        ["  chain zapret2_queue {",
         "    type filter hook postrouting priority 101; policy accept;",
         f"    meta mark {MARK:#x} tcp dport 443 "
         f"counter queue num {queue}", "  }"],
    ]


def guard_rules(queue: int | None) -> list[str]:
    lines = [f"meta mark {MARKS} ip daddr {{ 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, "
             "127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.0.0.0/24, 192.168.0.0/16, "
             "224.0.0.0/4, 240.0.0.0/4 } counter drop"]
    if queue is not None:
        lines.append(f"meta nfproto ipv4 meta mark {MARKS} meta mark @{LIVE} "
                     "tcp dport 443 counter accept")
    lines.append(f"meta mark {MARKS} counter drop")
    return lines


def arguments(cfg: Config) -> list[str]:
    from .zapret2_trace import LUA

    z = cfg.zapret2
    args = [z.binary, f"--qnum={z.queue_num}", f"--fwmark={FAKE_BIT:#x}",
            f"--lua-init=@{z.lua_dir}/zapret-lib.lua",
            f"--lua-init=@{z.lua_dir}/zapret-antidpi.lua"]
    strategy = z.strategy
    if z.mode == "compare":
        args += ["--debug=0", "--lua-init=" + LUA]
        strategy = "xgw_trace:strategy=" + strategy
    return [*args, "--filter-tcp=443", "--filter-l7=tls", "--payload=tls_client_hello",
            f"--lua-desync={strategy}:pos=1,midsld"]


class Runtime:
    def __init__(self, runner=cmd.run):
        self.runner = runner
        self.started = False
        self.evidence = None

    def gate(self, seconds: int = 0) -> None:
        from .net.capture import Capture

        script = f"flush set inet xgw_guard {LIVE}\n"
        if seconds:
            script += (f"add element inet xgw_guard {LIVE} {{ {MARK:#x} timeout {seconds}s, "
                       f"{FAKE_MARK:#x} timeout {seconds}s }}\n")
        # Как при загрузке таблиц XGW: свои nft monitor события не будят новый круг.
        Capture.ignore_rules_until = float("inf")
        try:
            self.runner(["nft", "-f", "-"], input=script, timeout=5)
        finally:
            Capture.ignore_rules_until = time.monotonic() + Capture.RULES_QUIET

    def alive(self, queue: int) -> bool:
        return self.state(queue) == "ready"

    def state(self, queue: int) -> str:
        """ready — unit активен и очередь занята; starting — unit жив, очереди ещё нет;
        dead — unit не работает (упал, остановлен, не создан)."""
        unit = self.runner(["systemctl", "is-active", UNIT], check=False, timeout=5).strip()
        if unit == "active":
            return "ready" if self.occupied(queue) else "starting"
        return "starting" if unit == "activating" else "dead"

    def describe(self) -> str:
        """Состояние unit для журнала: только слова и коды systemd, без argv и вывода."""
        names = ("ActiveState", "SubState", "Result", "ExecMainStatus")
        try:
            raw = self.runner(["systemctl", "show", UNIT, *[f"--property={n}" for n in names]],
                              check=False, timeout=5)
        except (OSError, cmd.CommandError):
            return ""
        found = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
        return " ".join(f"{name}={found[name]}" for name in names
                        if re.fullmatch(r"[A-Za-z0-9-]{1,32}", found.get(name, "")))

    @staticmethod
    def occupied(queue: int) -> bool:
        try:
            lines = Path("/proc/net/netfilter/nfnetlink_queue").read_text().splitlines()
        except OSError:
            return False
        return any(line.split() and line.split()[0] == str(queue) for line in lines)

    def start(self, cfg: Config) -> None:
        if self.alive(cfg.zapret2.queue_num):
            # Не перенимаем чужой/оставшийся процесс с неизвестной стратегией.
            self.stop()
        if self.occupied(cfg.zapret2.queue_num):
            raise ValueError("queue_busy")
        for name in (cfg.zapret2.binary, f"{cfg.zapret2.lua_dir}/zapret-lib.lua",
                     f"{cfg.zapret2.lua_dir}/zapret-antidpi.lua"):
            path = Path(name).resolve(strict=True)
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                raise ValueError("unsafe_files")
            for parent in path.parents:
                info = parent.stat()
                if info.st_uid != 0 or info.st_mode & 0o022:
                    raise ValueError("unsafe_directory")
        args = arguments(cfg)
        # intercept=0 проверяет Lua, dry-run этого не делает. Вывод не попадает в журнал XGW.
        self.runner([*args, "--intercept=0"], timeout=10)
        properties = [
            "Type=exec", "BindsTo=xgw.service", "After=xgw.service", "Restart=no",
            "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes", "NoNewPrivileges=yes",
            "CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW", "ProtectKernelTunables=yes",
            "ProtectKernelModules=yes",
            "RestrictAddressFamilies=AF_INET AF_INET6 AF_NETLINK AF_UNIX",
        ]
        self.runner(["systemd-run", "--quiet", "--collect", "--unit", UNIT,
                     *[arg for p in properties for arg in ("--property", p)], *args], timeout=15)
        self.started = True
        self.evidence = None
        if cfg.zapret2.mode == "compare":
            from .zapret2_trace import Evidence

            self.evidence = Evidence(self.runner, UNIT, cfg.zapret2.queue_num)
            self.evidence.begin()

    def sample_trace(self) -> None:
        if self.evidence is not None:
            self.evidence.sample()

    def finish_trace(self) -> dict:
        return self.evidence.finish() if self.evidence is not None else {}

    def stop(self) -> None:
        self.runner(["systemctl", "stop", UNIT], check=False, timeout=10)
        state = self.runner(["systemctl", "is-active", UNIT], check=False, timeout=5).strip()
        if state in ("active", "activating", "deactivating"):
            raise cmd.CommandError("zapret2: остановка не подтверждена")
        self.started = False


class Controller:
    """Шаг выполняется в демоне перед выбором основного сервера (adrules снимает pin)."""

    def __init__(self, store, runtime=None):
        self.store = store
        self.runtime = runtime or Runtime()
        self.next_check = 0.0
        self.healthy = False
        self.ready = False
        # Самостоятельный режим: срок (часы демона), до которого ждём очередь после запуска.
        self.starting: float | None = None
        self.started_at = 0.0
        self.log = log.get_logger("zapret2")
        self.last_error = ""
        self.probes: list[dict] = []
        self.comparison: list[dict] | None = None
        self.comparison_trace: dict | None = None
        self.view = {"state": "off", "reason": "off"}

    def _budget(self, cfg: Config) -> bool:
        day = int(time.time() // 86400)
        try:
            budget = json.loads(self.store.get_meta(BUDGET) or "{}")
            spent = budget.get("bytes", 0) if budget.get("day") == day else 0
            if type(spent) is not int or spent < 0:
                return False
        except (ValueError, TypeError, AttributeError):
            return False  # повреждённый учёт не превращается в бесплатный бюджет
        charge = len(cfg.zapret2.probe_urls) * PROBE_CHARGE
        if cfg.zapret2.mode == "compare":
            charge *= REDIRECT_LIMIT + 2  # исходный GET, переходы VPN и один прямой GET
        if spent + charge > cfg.zapret2.daily_probe_mb * 1024 * 1024:
            return False
        self.store.set_meta(BUDGET, json.dumps({"day": day, "bytes": spent + charge}))
        return True

    @staticmethod
    def _request(url: str, port: int, password: str, user_agent: str, cancel,
                 *, max_total: float = 8) -> DownloadResult:
        from .generator import builder
        from .watch import checks

        return checks.http_get_via_proxy(
            "127.0.0.1", port, url, proxy_user=builder.PROBE_USER,
            proxy_pass=password, timeout=5, silence=4, max_total=max_total,
            max_bytes=PROBE_BYTES, min_body=MIN_BODY, user_agent=user_agent, cancel=cancel,
        )

    def probe(self, cfg: Config, applied: dict, cancel) -> bool:
        from .generator import builder

        password, _ = builder.probe_state(applied)
        self.probes = []
        for index, url in enumerate(cfg.zapret2.probe_urls, 1):
            verdict = self._request(url, cfg.zapret2.probe_port, password or "",
                                    cfg.probe.user_agent, cancel)
            self.probes.append(probe_row(index, verdict))
            if not verdict.ok:
                self.probes.extend({"probe": n, "path": "zapret2", "ok": False,
                                    "verdict": "not_run", "checked_at": 0}
                                   for n in range(index + 1, len(cfg.zapret2.probe_urls) + 1))
                return False
        return True

    def _control(self, cfg: Config, url: str, port: int, password: str, agent: str, cancel):
        """До пяти разрешённых переходов VPN за общий срок 8 с; URL остаётся приватным."""
        from .watch.checks import DownloadResult

        deadline = time.monotonic() + 8
        seen = {url}
        hops, redirect = 0, "none"
        last_result, last_url, last_hops = None, url, 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                result = last_result or DownloadResult(False, kind="timeout", phase="connect")
                return result, last_url, last_hops, "time_limit"
            result = self._request(url, port, password, agent, cancel, max_total=remaining)
            last_result, last_url, last_hops = result, url, hops
            if not result.ok and time.monotonic() >= deadline:
                return result, url, hops, "time_limit"
            if result.phase == "connect" or result.status not in (301, 302, 303, 307, 308):
                return result, url, hops, redirect
            try:
                location = result.location
                if not location or any(ord(c) < 33 or ord(c) > 126 for c in location):
                    raise ValueError("bad_location")
                target = urljoin(url, location)
                parts = urlsplit(target)
                host = parts.hostname or ""
                if (parts.scheme != "https" or parts.port not in (None, 443)
                        or parts.username is not None or parts.password is not None
                        or parts.fragment or not matches(host, cfg.zapret2.domains)):
                    raise ValueError("bad_target")
                try:
                    ipaddress.ip_address(host)
                except ValueError:
                    pass
                else:
                    raise ValueError("literal_ip")
            except ValueError:
                return result, url, hops, "blocked"
            if target in seen:
                return result, url, hops, "loop"
            if hops == REDIRECT_LIMIT:
                return result, url, hops, "hop_limit"
            seen.add(target)
            url, hops, redirect = target, hops + 1, "followed"

    def _compare(self, cfg: Config, applied: dict, vpn_port: int, cancel) -> list[dict]:
        from .generator import builder
        from .watch import checks

        password, _ = builder.probe_state(applied)
        if not password or not vpn_port:
            return []
        agent = checks.pick_agent(cfg.probe.user_agent)
        rows = []
        for index, url in enumerate(cfg.zapret2.probe_urls, 1):
            for path, port in (("vpn", vpn_port), ("zapret2", cfg.zapret2.probe_port)):
                if cancel is not None and cancel.is_set():
                    return rows
                if path == "vpn":
                    result, url, hops, redirect = self._control(
                        cfg, url, port, password, agent, cancel)
                else:
                    # Тот же конечный адрес, который запросил VPN; свой редирект не скрываем.
                    result = self._request(url, port, password, agent, cancel)
                    hops, redirect = 0, "none"
                connect = result.phase == "connect"
                rows.append({
                    **probe_row(index, result),
                    "probe": index, "path": path, "phase": result.phase,
                    "kind": result.kind or "ok", "ok": result.ok,
                    "http": 0 if connect else result.status,
                    "connect_http": result.status if connect else 0,
                    "bytes": result.downloaded,
                    "redirects": hops, "redirect": redirect,
                })
        return rows

    def step(self, cfg: Config, applied: dict, now: float, apply, *, allowed=True,
             vpn_probe_port: int = 0, cancel=None, gating: str = "") -> bool:
        from .generator import builder

        if cfg.zapret2.mode == "standalone":
            self._standalone_step(cfg, applied, now, allowed=allowed, gating=gating)
            return False

        present = any(o.get("tag") == OUT for o in applied.get("outbounds", []))
        comparing = cfg.zapret2.mode == "compare"
        finished = comparing and self.comparison is not None
        wanted = (cfg.zapret2.probe_enabled and allowed and not finished
                  and not builder.applied_whole(applied))
        if finished and not present and not self.ready and self.view["state"] == "compared":
            return False
        if not finished and not wanted and not present and not self.ready:
            self.view = {"state": "off", "reason": "off"}
            return False
        reason = "off" if not wanted else "waiting_for_probe_urls"
        changed = False
        try:
            if wanted and configured(cfg):
                scaffold = patch(applied, cfg, enabled=active(applied))
                if scaffold != applied:
                    # Сначала служебный вход; прямое правило здесь не появляется.
                    self.runtime.gate()
                    changed = apply(patch(applied, cfg), applied)
                    if not changed:
                        raise ValueError("apply_failed")
                    self.view = {"state": "preparing", "reason": "probe_inbound"}
                    return changed
                if not self.ready and now >= self.next_check:
                    self.runtime.gate()
                    self.runtime.start(cfg)
                    self.ready = True
                    self.view = {"state": "preparing", "reason": "nfqueue"}
                    return False  # следующая итерация подтвердит живую очередь
                if self.ready and not self.runtime.alive(cfg.zapret2.queue_num):
                    raise ValueError("worker_down")
                if self.ready and now >= self.next_check:
                    self.healthy = False
                    if not self._budget(cfg):
                        raise ValueError("probe_budget")
                    if comparing:
                        self.runtime.gate(45)
                        self.comparison = self._compare(cfg, applied, vpn_probe_port, cancel)
                        self.runtime.sample_trace()
                    else:
                        self.runtime.gate(cfg.zapret2.check_seconds + 60)
                        if not self.probe(cfg, applied, cancel):
                            raise ValueError("probe_failed")
                        self.healthy = True
                        self.last_error = ""
                        self.next_check = now + cfg.zapret2.check_seconds
                if self.healthy and not comparing:
                    # Старый удачный GET не продлевает разрешение бесконечно.
                    lease = max(1, int(self.next_check - now) + 60)
                    self.runtime.gate(lease)
                    target = patch(applied, cfg, enabled=True)
                    changed = target != applied and apply(target, applied)
                    if target != applied and not changed:
                        raise ValueError("apply_failed")
                    self.view = {"state": "active", "reason": "probes_ok",
                                 "valid_until": time.time() + lease, "probes": self.probes}
                    return changed
                reason = self.last_error or "retry_wait"
        except (OSError, ValueError, cmd.CommandError) as exc:
            # Ни URL, ни argv/вывод nfqws2, ни пароль служебного входа не публикуются.
            codes = {"queue_busy", "unsafe_files", "unsafe_directory", "worker_down",
                     "probe_budget", "probe_failed", "apply_failed"}
            reason = str(exc) if isinstance(exc, ValueError) and str(exc) in codes else (
                "dependency_missing" if isinstance(exc, FileNotFoundError) else "runtime_failed")
            self.last_error = reason
            self.next_check = now + cfg.zapret2.retry_seconds
        self.healthy = False
        gate_closed = True
        try:
            self.runtime.gate()
        except cmd.CommandError:
            gate_closed = False  # очередь всё ещё без bypass; lease сам истечёт
        try:
            finished = comparing and self.comparison is not None
            target = patch(applied, cfg, probe=not finished)
            changed = target != applied and apply(target, applied)
            routed_back = (target == applied or changed) and reason != "apply_failed"
        except (ValueError, cmd.CommandError, OSError):
            routed_back = False
        stopped = True
        if self.ready or present:
            try:
                self.runtime.stop()
            except cmd.CommandError:
                reason = "stop_failed"
                stopped = False
        self.ready = comparing and not stopped
        if comparing and self.comparison is not None:
            if stopped and self.comparison_trace is None:
                self.comparison_trace = self.runtime.finish_trace()
            complete = len(self.comparison) == 4 and all(
                row["kind"] != "cancelled" for row in self.comparison)
            cleaned = routed_back and gate_closed and stopped
            self.view = {"state": "compared" if cleaned else "blocked",
                         "reason": ("comparison_done" if complete else "comparison_incomplete")
                         if cleaned else "comparison_cleanup_failed",
                         "gate_closed": gate_closed, "probes": self.comparison,
                         "trace": self.comparison_trace or {}}
            return changed
        self.view = {"state": "fallback" if routed_back else "blocked", "reason": reason,
                     "gate_closed": gate_closed, "probes": self.probes}
        return changed

    def _standalone_step(self, cfg: Config, applied: dict, now: float, *, allowed: bool,
                         gating: str = "") -> None:
        """Готовность обработчика открывает маршрут, но не означает успех обхода DPI.

        Запуск — в два приёма: start, затем ожидание очереди до START_WAIT (шаги демона, не
        sleep). Пока очереди нет, gate закрыт и процесс не трогаем; упал или срок вышел —
        остановка, причина в журнале, новая попытка через retry_seconds. gating — почему шаг
        не разрешён (перехват, мосты, Xray): только для журнала."""
        queue = cfg.zapret2.queue_num
        reason = "off" if not allowed else "apply_failed"
        cause = gating or reason
        try:
            if allowed and standalone(applied):
                if not self.ready and self.starting is None and now >= self.next_check:
                    self.runtime.gate()
                    self.runtime.start(cfg)
                    self.starting, self.started_at = now + START_WAIT, now
                    self.log.info("обработчик запущен, очередь ожидается до %d с",
                                  START_WAIT)
                up = False
                if self.starting is not None:
                    state = self.runtime.state(queue)
                    if state == "dead":
                        raise ValueError("worker_exited")
                    if state != "ready":
                        if now >= self.starting:
                            raise ValueError("start_timeout")
                        self.view = {"state": "preparing", "reason": "worker_starting",
                                     "gate_closed": True, "probes": []}
                        return
                    self.starting, self.ready, up = None, True, True
                    self.log.info("обработчик готов, очередь занята через %.1f с",
                                  now - self.started_at)
                if not self.ready:
                    reason = cause = self.last_error or "retry_wait"
                elif not up and not self.runtime.alive(queue):
                    raise ValueError("worker_down")
                else:
                    lease = cfg.zapret2.check_seconds + 60
                    self.runtime.gate(lease)
                    self.view = {"state": "active", "reason": "worker_ready",
                                 "valid_until": time.time() + lease, "probes": []}
                    self.last_error = ""
                    return
        except (OSError, ValueError, cmd.CommandError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) and str(exc) in (
                "worker_down", "worker_exited", "start_timeout", "queue_busy", "unsafe_files",
                "unsafe_directory",
            ) else "runtime_failed"
            cause = reason
            self.last_error = reason
            self.next_check = now + cfg.zapret2.retry_seconds
            detail = self.runtime.describe() if reason in (
                "worker_exited", "start_timeout", "worker_down") else ""
            self.log.warning("отказ обработчика: %s%s; новая попытка через %d с",
                             reason, f" ({detail})" if detail else "", cfg.zapret2.retry_seconds)
        running = self.ready or self.starting is not None
        closed = False
        try:
            self.runtime.gate()
            closed = True
        except cmd.CommandError:
            pass
        try:
            self.runtime.stop()
            self.ready, self.starting = False, None
        except cmd.CommandError:
            reason = "stop_failed"
        if running:
            # Решение демона видно в журнале: без argv, адресов и вывода nfqws2.
            self.log.warning("обработчик остановлен демоном: %s; выбранные домены "
                             "закрыты%s", cause, "" if reason != "stop_failed"
                             else "; остановка не подтверждена")
        self.view = {"state": "blocked" if allowed else "off", "reason": reason,
                     "gate_closed": closed, "probes": []}

    def close(self, cause: str = "close") -> None:
        if not self.ready and self.starting is None:
            return
        try:
            self.runtime.gate()
        finally:
            self.runtime.stop()
            self.ready = self.healthy = False
            self.starting = None
            self.log.info("обработчик остановлен демоном: %s", cause)
