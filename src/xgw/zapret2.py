"""Выбранные HTTPS-домены через nfqws2; отказ возвращает новые соединения в VPN.

XGW не запускает install_easy и не меняет sysctl. Два собственных SO_MARK не
пересекаются с bypass/TPROXY/Tailscale. Разрешение WAN имеет срок жизни в nft;
без слушателя NFQUEUE пакеты не проходят (нет queue bypass).
"""

from __future__ import annotations

import copy
import ipaddress
import json
import re
import time
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlsplit

from .desync import flowseal, h05, preflight, worker
from .desync.schema import (
    MAX_REPLY_PACKETS,
    SELECTED_PROFILES,
    valid_youtube_transport,
    youtube_cdn_expiry,
)
from .net import cmd

if TYPE_CHECKING:
    from .config import Config
    from .watch.checks import DownloadResult

MARK = 0x10000000
FAKE_BIT = 0x40000000
FAKE_MARK = MARK | FAKE_BIT
MARKS = f"{{ {MARK:#x}, {FAKE_MARK:#x} }}"
# This conntrack bit is independent of skb marks and nft.GUARD_CT.
SYNACK_CT = 0x10000000
REPLY_CT = 0x08000000
CONNTRACK_ACCT = "net/netfilter/nf_conntrack_acct"
TCP_HANDSHAKE_FLAGS = "(fin | syn | rst | ack)"
OUT = "xgw-zapret2"
DIRECT = "xgw-standalone-direct"
PROBE = "xgw-zapret2-probe"
UNIT = worker.SELECTED_UNIT
LIVE = "zapret2_live"
BUDGET = "zapret2_probe_budget"
PROBE_BYTES = 64 * 1024
YOUTUBE_TRANSPORT_MAX_SECONDS = 12
YOUTUBE_TRANSPORT_TLS_SECONDS = 10
YOUTUBE_PAGE_SILENCE_SECONDS = 6
CDN_EXPIRED = "youtube_cdn_expired"
# Резерв на тело, TLS и заголовки; списывается до запроса, включая прерванный.
PROBE_CHARGE = 256 * 1024
REDIRECT_LIMIT = 5
START_WAIT = 20
START_POLL = 2
STANDALONE_LEASE = 60
TRACED = ("multisplit", "multidisorder")
_FAKE = "fake:blob=fake_default_tls:{}:repeats=2:tls_mod=rnd,dupsid"
STRATEGIES = {
    "multisplit": ("multisplit:pos=1,midsld",),
    "multidisorder": ("multidisorder:pos=1,midsld",),
    "fake_md5": (_FAKE.format("tcp_md5"), "multidisorder:pos=1,midsld"),
    "fake_seq": (_FAKE.format("tcp_seq=-10000"), "multidisorder:pos=1,midsld"),
    "fake_md5_split": (_FAKE.format("tcp_md5"), "multisplit:pos=1,midsld"),
    "fake_seq_split": (_FAKE.format("tcp_seq=-10000"), "multisplit:pos=1,midsld"),
    "fake_ts": (_FAKE.format("tcp_ts=-600000"), "multisplit:pos=1,midsld"),
    "fakedsplit_md5": ("fakedsplit:pos=midsld:tcp_md5",),
    "hostfakesplit_md5": ("hostfakesplit:midhost=midsld:tcp_md5",),
    "seqovl": ("multisplit:pos=1:seqovl=681:seqovl_pattern=fake_default_tls",),
}
_DOMAIN = re.compile(r"(?:domain|full):[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?")


def matches(host: str, domains: list[str]) -> bool:
    for item in domains:
        kind, _, name = item.partition(":")
        if host == name or (kind == "domain" and host.endswith("." + name)):
            return True
    return False


def validate(cfg: Config) -> list[str]:
    z = cfg.zapret2
    problems = []
    if z.mode not in ("off", "standalone", "selective", "compare"):
        problems.append("mode: ожидается off, standalone, selective или compare")
    if not z.domains or any(not _DOMAIN.fullmatch(d) for d in z.domains):
        problems.append("domains: нужны domain:имя или full:имя")
    # Keep dormant preferences intact; off never executes a selected strategy.
    # Enabling a profile still requires support in this controller, not just in the schema.
    strategies = TRACED if z.mode == "compare" else SELECTED_PROFILES
    if z.strategy not in strategies:
        problems.append("strategy: неизвестная или неподдерживаемая в выбранном режиме")
    if z.strategy == flowseal.LIVE_STRATEGY and not flowseal.valid_live_scope(z.mode, z.domains):
        problems.append("Flowseal ALT9 требует Standalone и домены YouTube")
    if z.youtube_transport_probe and not valid_youtube_transport(z.mode, z.domains, z.probe_urls):
        problems.append("youtube_transport_probe требует Selective, страницу YouTube и CDN")
    if not 1 <= z.queue_num <= 65535 or not 1024 <= z.probe_port <= 65535:
        problems.append("queue_num или probe_port вне допустимого диапазона")
    if z.probe_port in (cfg.capture.tproxy_port, cfg.xray.metrics_port, cfg.xray.socks_port,
                        cfg.xray.http_port, cfg.panel.port, cfg.panel.app_port, cfg.core.api_port):
        problems.append("probe_port занят другой службой XGW")
    if not 60 <= z.check_seconds <= 900 or not 60 <= z.retry_seconds <= 3600:
        problems.append("check_seconds: 60–900; retry_seconds: 60–3600")
    if not 1 <= z.daily_probe_mb <= 1024:
        problems.append("daily_probe_mb: ожидается 1–1024")
    if not 0 <= z.observe_reply_packets <= MAX_REPLY_PACKETS:
        problems.append(f"observe_reply_packets: ожидается 0–{MAX_REPLY_PACKETS}")
    if z.observe_reply_packets and not z.observe_synack:
        problems.append("observe_reply_packets требует observe_synack")
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
    if z.selected_enabled and cfg.network.effective_quic_mode != "reject":
        problems.append("для общего выхода страницы и видео требуется network.quic_mode = reject")
    if z.mode == "standalone":
        if not cfg.capture.hold_blocks or cfg.capture.fail_mode != "closed":
            problems.append("standalone требует capture.fail_mode = closed и capture.hold = block")
        if not (cfg.capture.local or cfg.capture.lan):
            problems.append("standalone требует настроенного перехвата")
    for mark in (cfg.capture.mark_proxy, cfg.capture.mark_bypass, cfg.capture.mark_containers):
        if mark & (MARK | FAKE_BIT):
            problems.append("метки capture пересекаются с зарезервированными битами zapret2")
            break
    if problems:
        z.mode = "off"
    return [f"zapret2 выключен: {p}" for p in problems]


def configured(cfg: Config) -> bool:
    """Для YouTube нужны обе стороны; пустой адрес никогда не заменяется сторонним CDN."""
    z = cfg.zapret2
    if z.youtube_transport_probe:
        return z.probe_enabled and valid_youtube_transport(z.mode, z.domains, z.probe_urls)
    hosts = [urlsplit(url).hostname or "" for url in z.probe_urls]
    if not hosts:
        return False
    if "domain:youtube.com" in z.domains:
        return all(any(matches(host, [domain]) for host in hosts)
                   for domain in ("domain:youtube.com", "domain:googlevideo.com"))
    return True


def youtube_probe_page_kind(url: str) -> str:
    """Report a fixed category instead of publishing a configured URL."""
    path = urlsplit(url).path
    if path == "/t/terms":
        return "terms"
    if path == "/watch":
        return "watch"
    return "other"


def probe_expiry(settings) -> int | None:
    if settings.youtube_transport_probe and len(settings.probe_urls) == 2:
        return youtube_cdn_expiry(settings.probe_urls[1])
    return None


def probe_lease(seconds: int, expires_at: int | None) -> int:
    if expires_at is not None:
        seconds = min(seconds, int(expires_at - time.time()))
        if seconds < 1:
            raise ValueError(CDN_EXPIRED)
    return seconds


def active(config: dict) -> bool:
    return any(r.get("outboundTag") == OUT and r.get("inboundTag") != [PROBE]
               for r in config.get("routing", {}).get("rules", []))


def standalone(config: dict | None) -> bool:
    return any(o.get("tag") == DIRECT for o in (config or {}).get("outbounds", []))


def selected_outbound() -> dict:
    return {
        "tag": OUT, "protocol": "freedom", "settings": {"domainStrategy": "UseIPv4"},
        "streamSettings": {"sockopt": {"mark": MARK}},
    }


def standalone_route(config: dict, *, enabled: bool) -> dict:
    """The selected-domain block rule stays in place across open/close."""
    result = copy.deepcopy(config)
    rules = [r for r in result["routing"]["rules"] if r.get("outboundTag") != OUT]
    result["routing"]["rules"] = rules
    if enabled:
        index = next(i for i, rule in enumerate(rules) if rule.get("outboundTag") == "block")
        rules.insert(index, {**rules[index], "network": "tcp", "port": "443", "outboundTag": OUT})
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
    result["outbounds"].append(selected_outbound())
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


def guard_blocks(
    queue: int | None, *, observe_synack: bool = False, observe_reply_packets: int = 0,
) -> list[list[str]]:
    """Внутри xgw_guard: разрешение с TTL, NFQUEUE после NAT, notrack своих копий."""
    if queue is None:
        return []
    blocks = [
        [f"  set {LIVE} {{", "    type mark", "    flags timeout", "  }"],
        ["  chain zapret2_raw {", "    type filter hook output priority -401; policy accept;",
         f"    meta mark {FAKE_MARK:#x} notrack", "  }"],
    ]
    outgoing = ["  chain zapret2_queue {",
                "    type filter hook postrouting priority 101; policy accept;"]
    if observe_synack:
        # Only a new locally-originated SYN admitted by the live gate arms a reply.
        outgoing.append(
            f"    meta iif 0 meta nfproto ipv4 meta mark {MARK:#x} meta mark @{LIVE} "
            f"ct direction original ct state new tcp dport 443 "
            f"tcp flags & {TCP_HANDSHAKE_FLAGS} == syn "
            f"ct mark & {SYNACK_CT:#x} == 0 counter ct mark set ct mark | {SYNACK_CT:#x}"
        )
    outgoing.extend([f"    meta mark {MARK:#x} tcp dport 443 counter queue num {queue}", "  }"])
    blocks.append(outgoing)
    if observe_synack:
        blocks.append(_reply_block(queue, observe_reply_packets))
    return blocks


def _reply_block(queue: int, observe_reply_packets: int) -> list[str]:
    # INPUT follows conntrack and only covers replies delivered to this machine.
    bit = f"{SYNACK_CT:#x}"
    bits = SYNACK_CT | REPLY_CT
    qualifier = (f'iifname != "lo" meta nfproto ipv4 meta mark & {FAKE_BIT:#x} == 0 '
                 "ct direction reply ct state established tcp sport 443")
    live = f"ct mark & {bit} @{LIVE}"
    if observe_reply_packets:
        # Keep SYNACK_CT for the existing gate lookup. REPLY_CT records the observed SYN/ACK.
        synack_match = f"ct mark & {bits:#x} == {bit}"
        on_synack = f"ct mark set ct mark | {REPLY_CT:#x}"
    else:
        synack_match = f"ct mark & {bit} == {bit}"
        on_synack = f"ct mark set ct mark & {0xffffffff ^ SYNACK_CT:#x}"
    lines = [
        "  chain zapret2_reply {",
        "    type filter hook input priority -149; policy accept;",
        f"    {qualifier} tcp flags & {TCP_HANDSHAKE_FLAGS} == (syn | ack) "
        f"{synack_match} {live} limit rate 256/second burst 128 packets "
        f"counter {on_synack} queue num {queue}",
    ]
    if observe_reply_packets:
        # The counter includes SYN/ACK and any ACK/retransmit already seen by conntrack.
        match = f"{qualifier} ct mark & {bits:#x} == {bits:#x}"
        stop = 1 + observe_reply_packets
        lines += [
            f"    {match} {live} tcp flags & syn == 0 ct reply packets 2-{stop} "
            f"limit rate 128/second burst 64 packets counter queue num {queue}",
            f"    {match} ct reply packets > {stop} "
            f"ct mark set ct mark & {0xffffffff ^ bits:#x}",
        ]
    return [*lines, "  }"]


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
    if z.strategy == flowseal.LIVE_STRATEGY:
        if z.mode != "standalone" or not flowseal.valid_live_scope(z.mode, z.domains):
            raise ValueError("flowseal_standalone_scope_required")
        return [*args, *flowseal.live_arguments()]
    if z.strategy in ("fake_static_md5", "fake_clone_md5"):
        source = "static" if z.strategy == "fake_static_md5" else "clone"
        return [*args, "--filter-tcp=443", "--filter-l7=tls", "--payload=tls_client_hello",
                *h05.arguments(source)]
    calls = STRATEGIES[z.strategy]
    if z.mode == "compare":
        args += ["--debug=0", "--lua-init=" + LUA]
        calls = (f"xgw_trace:strategy={z.strategy}:pos=1,midsld",)
    return [*args, "--filter-tcp=443", "--filter-l7=tls", "--payload=tls_client_hello",
            *(f"--lua-desync={call}" for call in calls)]


class Runtime:
    def __init__(self, runner=cmd.run, *, slot: worker.WorkerSlot | None = None):
        self.runner = runner
        self.evidence = None
        self.slot = slot if slot is not None else worker.WorkerSlot()
        self.lease: worker.Lease | None = None

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
        lease = self.lease
        if lease is None or self.slot.lease is not lease or lease.queue != queue:
            return False
        state = self.runner(["systemctl", "is-active", UNIT], check=False, timeout=5).strip()
        return self.slot.observe_owner(
            lease, state == "active" and worker.verify_owner(self.runner, UNIT, queue))

    @staticmethod
    def occupied(queue: int) -> bool:
        return worker.occupied(queue)

    def start(self, cfg: Config) -> None:
        worker.require_stopped(self.runner, UNIT)
        if self.occupied(cfg.zapret2.queue_num):
            raise ValueError("queue_busy")
        args = preflight.check(arguments(cfg), self.runner)
        properties = [
            "Type=exec", "BindsTo=xgw.service", "After=xgw.service", "Restart=no",
            "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes", "NoNewPrivileges=yes",
            "CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW", "ProtectKernelTunables=yes",
            "ProtectKernelModules=yes",
            "RestrictAddressFamilies=AF_INET AF_INET6 AF_NETLINK AF_UNIX",
        ]
        worker.require_stopped(self.runner, worker.ENGINE_UNIT)
        self.lease = self.slot.reserve(UNIT, cfg.zapret2.queue_num,
                                       policy_key=worker.policy_revision(cfg.zapret2))
        self.evidence = None
        # Даже при таймауте запуска systemd мог уже создать unit.
        self.runner(["systemd-run", "--quiet", "--collect", "--unit", UNIT,
                     *[arg for p in properties for arg in ("--property", p)], *args], timeout=15)
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
        if self.lease is None or self.slot.lease is not self.lease:
            return
        self.runner(["systemctl", "stop", UNIT], check=False, timeout=10)
        state = self.runner(["systemctl", "is-active", UNIT], check=False, timeout=5).strip()
        if state not in worker.STOPPED:
            raise cmd.CommandError("zapret2: остановка не подтверждена")
        self.slot.release(self.lease)
        self.lease = None


class Controller:
    """Шаг выполняется в демоне перед выбором основного сервера (adrules снимает pin)."""

    def __init__(self, store, runtime=None):
        self.store = store
        self.runtime = runtime or Runtime()
        self.next_check = 0.0
        self.healthy = False
        self.ready = False
        self.cleanup_pending = False
        self.start_deadline: float | None = None
        self.last_error = ""
        self.probe_failure = "probe_failed"
        self.transport_probes: dict[str, dict] = {}
        self.comparison: list[dict] | None = None
        self.comparison_trace: dict | None = None
        self.view = {"state": "off", "reason": "off"}

    def _budget(self, cfg: Config, *, single_probe: bool = False) -> bool:
        day = int(time.time() // 86400)
        try:
            budget = json.loads(self.store.get_meta(BUDGET) or "{}")
            spent = budget.get("bytes", 0) if budget.get("day") == day else 0
            if type(spent) is not int or spent < 0:
                return False
        except (ValueError, TypeError, AttributeError):
            return False  # повреждённый учёт не превращается в бесплатный бюджет
        charge = (1 if single_probe else len(cfg.zapret2.probe_urls)) * PROBE_CHARGE
        if not single_probe and cfg.zapret2.mode == "compare":
            charge *= REDIRECT_LIMIT + 2  # исходный GET, переходы VPN и один прямой GET
        if spent + charge > cfg.zapret2.daily_probe_mb * 1024 * 1024:
            return False
        self.store.set_meta(BUDGET, json.dumps({"day": day, "bytes": spent + charge}))
        return True

    @staticmethod
    def _request(url: str, port: int, password: str, user_agent: str, cancel,
                 *, max_total: float = 8, silence: float = 4,
                 min_body: int = 16 * 1024, tls_timeout: float | None = None) -> DownloadResult:
        from .generator import builder
        from .watch import checks

        return checks.http_get_via_proxy(
            "127.0.0.1", port, url, proxy_user=builder.PROBE_USER,
            proxy_pass=password, timeout=5, tls_timeout=tls_timeout, silence=silence,
            max_total=max_total,
            max_bytes=PROBE_BYTES, min_body=min_body, user_agent=user_agent, cancel=cancel,
        )

    def probe(self, cfg: Config, applied: dict, cancel) -> bool:
        from .generator import builder

        password, _ = builder.probe_state(applied)
        z = cfg.zapret2
        self.transport_probes = {}
        if z.youtube_transport_probe and (not configured(cfg) or not password):
            return False
        for index, url in enumerate(z.probe_urls):
            media_transport = z.youtube_transport_probe and index == 1
            expires_at = probe_expiry(z) if media_transport else None
            if expires_at is not None and expires_at <= time.time():
                self.probe_failure = CDN_EXPIRED
                return False
            options = {}
            if z.youtube_transport_probe:
                options = {"max_total": YOUTUBE_TRANSPORT_MAX_SECONDS,
                           "tls_timeout": YOUTUBE_TRANSPORT_TLS_SECONDS}
                if media_transport:
                    options["min_body"] = 0
                else:
                    options["silence"] = YOUTUBE_PAGE_SILENCE_SECONDS
            started = time.monotonic()
            started_at = time.time() if z.youtube_transport_probe else None
            verdict = self._request(url, z.probe_port, password or "",
                                    cfg.probe.user_agent, cancel, **options)
            first_tls_timeout_ms = None
            if expires_at is not None and expires_at <= time.time():
                self.probe_failure = CDN_EXPIRED
                return False
            if (media_transport and not verdict.ok and verdict.phase == "tls"
                    and verdict.kind == "timeout" and (cancel is None or not cancel.is_set())
                    and self.runtime.alive(z.queue_num) and self._budget(cfg, single_probe=True)):
                first_tls_timeout_ms = round((time.monotonic() - started) * 1000)
                verdict = self._request(url, z.probe_port, password, cfg.probe.user_agent,
                                        cancel, **options)
            ok = verdict.ok and (not media_transport or verdict.status in (200, 204))
            if z.youtube_transport_probe:
                self.transport_probes["cdn" if media_transport else "page"] = {
                    "ok": ok, "phase": verdict.phase,
                    "kind": verdict.kind or ("ok" if ok else "http"),
                    "http": 0 if verdict.phase == "connect" else verdict.status,
                    "connect_http": verdict.status if verdict.phase == "connect" else 0,
                    "bytes": verdict.downloaded,
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "started_at": started_at,
                    **({} if media_transport else {"page_kind": youtube_probe_page_kind(url)}),
                }
                if first_tls_timeout_ms is not None:
                    self.transport_probes["cdn"]["first_tls_timeout_ms"] = first_tls_timeout_ms
            if not ok:
                if z.youtube_transport_probe:
                    self.probe_failure = ("youtube_cdn_probe_failed" if media_transport
                                          else "youtube_page_probe_failed")
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
                    "probe": index, "path": path, "phase": result.phase,
                    "kind": result.kind or "ok", "ok": result.ok,
                    "http": 0 if connect else result.status,
                    "connect_http": result.status if connect else 0,
                    "bytes": result.downloaded,
                    "redirects": hops, "redirect": redirect,
                })
        return rows

    def _fallback_vpn_control(
        self, cfg: Config, applied: dict, port: int, cancel, *,
        gate_closed: bool, routed_back: bool, stopped: bool,
    ) -> tuple[str, str]:
        from .generator import builder

        if not gate_closed:
            return "not_run", "gate_not_closed"
        if not routed_back:
            return "not_run", "route_not_restored"
        if not stopped:
            return "not_run", "worker_not_stopped"
        if cancel is not None and cancel.is_set():
            return "not_run", "cancelled"
        if not cfg.zapret2.probe_urls:
            return "not_run", "no_probe_url"
        if not port:
            return "not_run", "no_vpn_probe_port"
        password, _ = builder.probe_state(applied)
        if not password:
            return "not_run", "no_probe_credentials"
        if not self._budget(cfg, single_probe=True):
            return "not_run", "budget_unavailable"
        result = self._request(cfg.zapret2.probe_urls[0], port, password,
                               cfg.probe.user_agent, cancel)
        if result.kind == "cancelled":
            return "not_run", "cancelled"
        return ("pass", "ok") if result.ok else ("fail", "request_failed")

    def step(self, cfg: Config, applied: dict, now: float, apply, *, allowed=True,
             vpn_probe_port: int = 0, cancel=None) -> bool:
        from .generator import builder

        present = any(o.get("tag") == OUT for o in applied.get("outbounds", []))
        comparing = cfg.zapret2.mode == "compare"
        finished = comparing and self.comparison is not None
        cancelled = cancel is not None and cancel.is_set()
        wanted = (cfg.zapret2.probe_enabled and allowed and not finished and not cancelled
                  and not self.cleanup_pending
                  and not builder.applied_whole(applied))
        if finished and not present and not self.ready and self.view["state"] == "compared":
            return False
        if (not finished and not wanted and not present and not self.ready
                and not self.cleanup_pending):
            self.view = {"state": "off", "reason": "off"}
            return False
        reason = "off" if not wanted else "waiting_for_probe_urls"
        changed = False
        starting = False
        check_vpn = False
        try:
            if wanted and configured(cfg):
                expires_at = probe_expiry(cfg.zapret2)
                if expires_at is not None and expires_at - time.time() < 1:
                    if (not present and not self.ready and self.view.get("reason") == CDN_EXPIRED
                            and self.view.get("gate_closed") is True):
                        return False
                    raise ValueError(CDN_EXPIRED)
                scaffold = patch(applied, cfg, enabled=active(applied))
                if scaffold != applied:
                    # Сначала служебный вход; прямое правило здесь не появляется.
                    self.runtime.gate()
                    changed = apply(patch(applied, cfg), applied)
                    if not changed:
                        raise ValueError("apply_failed")
                    self.view = {"state": "preparing", "reason": "probe_inbound"}
                    return changed
                if (cfg.zapret2.mode == "selective" and not self.ready and not active(applied)
                        and now < self.next_check and self.view.get("state") == "fallback"
                        and self.view.get("gate_closed") is True):
                    # The closed route and the result belong to the current retry window.
                    # Replacing the snapshot here used to erase the VPN result on the next tick.
                    return False
                if not self.ready and now >= self.next_check:
                    self.runtime.gate()
                    starting = True
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
                        self.runtime.gate(probe_lease(cfg.zapret2.check_seconds + 60, expires_at))
                        self.probe_failure = "probe_failed"
                        if not self.probe(cfg, applied, cancel):
                            raise ValueError(self.probe_failure)
                        self.healthy = True
                        self.last_error = ""
                        self.next_check = now + cfg.zapret2.check_seconds
                if self.healthy and not comparing and (cancel is None or not cancel.is_set()):
                    if not self.runtime.alive(cfg.zapret2.queue_num):
                        raise ValueError("worker_down")
                    # Старый удачный GET не продлевает разрешение бесконечно.
                    lease = max(1, int(self.next_check - now) + 60)
                    lease = probe_lease(lease, expires_at)
                    self.runtime.gate(lease)
                    target = patch(applied, cfg, enabled=True)
                    changed = target != applied and apply(target, applied)
                    if target != applied and not changed:
                        raise ValueError("apply_failed")
                    valid_until = time.time() + lease
                    if expires_at is not None:
                        valid_until = min(valid_until, expires_at)
                    self.view = {"state": "active", "reason": (
                                     "youtube_transport_ok" if cfg.zapret2.youtube_transport_probe
                                     else "probes_ok"),
                                 "valid_until": valid_until}
                    if cfg.zapret2.youtube_transport_probe and self.transport_probes:
                        self.view["transport_probes"] = self.transport_probes
                    return changed
                reason = self.last_error or "retry_wait"
        except (OSError, ValueError, cmd.CommandError) as exc:
            # Ни URL, ни argv/вывод nfqws2, ни пароль служебного входа не публикуются.
            probe_errors = {"probe_failed", "youtube_cdn_probe_failed",
                            "youtube_page_probe_failed"}
            codes = {"queue_busy", "unsafe_files", "unsafe_directory", "worker_down",
                     "bundle_mismatch", "bad_worker_options", "lua_init_failed",
                     "probe_budget", "apply_failed", CDN_EXPIRED,
                     "worker_unit_busy", "worker_handoff_pending", *probe_errors}
            reason = str(exc) if isinstance(exc, ValueError) and str(exc) in codes else (
                "dependency_missing" if isinstance(exc, FileNotFoundError) else "runtime_failed")
            self.last_error = reason
            self.next_check = now if reason == CDN_EXPIRED else now + cfg.zapret2.retry_seconds
            check_vpn = reason == "worker_down" or reason in probe_errors
        self.healthy = False
        gate_closed = True
        try:
            self.runtime.gate()
        except cmd.CommandError:
            gate_closed = False  # очередь всё ещё без bypass; lease сам истечёт
        try:
            finished = comparing and self.comparison is not None
            target = patch(applied, cfg, probe=not finished and reason != CDN_EXPIRED)
            changed = target != applied and apply(target, applied)
            routed_back = (target == applied or changed) and reason != "apply_failed"
        except (ValueError, cmd.CommandError, OSError):
            routed_back = False
        stopped = True
        if self.ready or present or starting or self.cleanup_pending:
            try:
                self.runtime.stop()
            except (OSError, cmd.CommandError):
                reason = "stop_failed"
                stopped = False
        self.ready = False
        self.cleanup_pending = not stopped
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
        self.view = {"state": "fallback" if routed_back and stopped else "blocked",
                     "reason": reason, "gate_closed": gate_closed}
        if (reason in ("youtube_page_probe_failed", "youtube_cdn_probe_failed")
                and self.transport_probes):
            self.view["transport_probes"] = self.transport_probes
        if cfg.zapret2.mode == "selective" and check_vpn:
            verdict, why = self._fallback_vpn_control(
                cfg, applied, vpn_probe_port, cancel, gate_closed=gate_closed,
                routed_back=routed_back, stopped=stopped,
            )
            self.view.update(vpn_control=verdict, vpn_control_reason=why,
                             vpn_control_at=time.time())
        return changed

    def step_standalone(self, cfg: Config, applied: dict, now: float, apply,
                        *, allowed: bool, blocked_reason: str = "capture_not_ready",
                        cancel=None) -> None:
        """Keep selected domains blocked until both NFQUEUE and the route are ready."""
        reason = blocked_reason
        queue = cfg.zapret2.queue_num
        live_route = active(applied)
        try:
            if allowed and (cancel is None or not cancel.is_set()):
                if self.cleanup_pending:
                    self.close()
                if not self.ready and now >= self.next_check:
                    self.runtime.gate()
                    self.cleanup_pending = True
                    self.runtime.start(cfg)
                    self.cleanup_pending = False
                    self.ready = True
                    self.start_deadline = now + START_WAIT
                if self.ready and self.runtime.alive(queue):
                    if cancel is not None and cancel.is_set():
                        raise ValueError("stopping")
                    self.start_deadline = None
                    # Measure from the start of the nft request, never overstate its TTL.
                    valid_until = time.time() + STANDALONE_LEASE
                    self.runtime.gate(STANDALONE_LEASE)
                    if not live_route:
                        target = standalone_route(applied, enabled=True)
                        if not apply(target, applied):
                            raise ValueError("apply_failed")
                    self.view = {"state": "active", "reason": "worker_ready",
                                 "valid_until": valid_until, "without_vpn": True}
                    return
                if self.start_deadline is not None and now < self.start_deadline:
                    self.view = {"state": "preparing", "reason": "nfqueue"}
                    return
                if self.ready:
                    raise ValueError("worker_start_timeout" if self.start_deadline is not None
                                     else "worker_down")
                reason = self.last_error or "retry_wait"
        except (OSError, ValueError, cmd.CommandError) as exc:
            codes = {"queue_busy", "unsafe_files", "unsafe_directory", "worker_down",
                     "bundle_mismatch", "bad_worker_options", "lua_init_failed",
                     "worker_start_timeout", "apply_failed", "worker_unit_busy",
                     "worker_handoff_pending", "stopping"}
            reason = (str(exc) if isinstance(exc, ValueError) and str(exc) in codes
                      else "dependency_missing" if isinstance(exc, FileNotFoundError)
                      else "runtime_failed")
            self.last_error = reason
            self.next_check = now + cfg.zapret2.retry_seconds
        closed = True
        try:
            self.close()  # Flush the TTL set before stopping the worker.
        except (OSError, cmd.CommandError):
            closed = False
            if self.cleanup_pending:
                reason = "stop_failed"
        if live_route:
            try:
                if not apply(standalone_route(applied, enabled=False), applied):
                    reason = "apply_failed"
            except (OSError, cmd.CommandError, ValueError):
                reason = "apply_failed"
        self.view = {"state": "blocked", "reason": reason, "gate_closed": closed}

    def close(self) -> None:
        if not self.ready and not self.cleanup_pending:
            return
        try:
            self.runtime.gate()
        finally:
            self.start_deadline = None
            self.cleanup_pending = True
            self.ready = self.healthy = False
            self.runtime.stop()
            self.cleanup_pending = False
            self.view = {"state": "off", "reason": "off"}
