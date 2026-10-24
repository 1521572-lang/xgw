"""Устойчивость к ТСПУ (0.1.18, docs/SPEC-0.1.18-TSPU-SPEED-TRAY-2026-10-24.md): R1 — сервер в
работе переводится на дробление на месте, а не списывается; R3 — проверочные хосты по кругу;
R4 — монитор bootstrap-DNS и аварийный маршрут Tailscale через VPN."""

import json

import pytest
from test_daemon import Harness, _started
from test_daemon_main import _free_inventory
from test_dualcore import Dual, _has, _rescan, _start

from xgw import config, fetch, tailscale
from xgw.config import Config
from xgw.daemon import Daemon
from xgw.generator import fragment as fragmenting
from xgw.net import nft
from xgw.paths import Paths
from xgw.watch import hosts as probehosts
from xgw.watch import resolvers as resolving
from xgw.watch import target
from xgw.watch.checks import DownloadResult
from xgw.watch.scan import ScanResult
from xgw.watch.states import State

# --- общие заготовки ----------------------------------------------------------------


@pytest.fixture()
def paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    found = Paths.from_env()
    found.ensure()
    return found


@pytest.fixture()
def tspu(paths):
    """Демон двух ядер со всей лестницей 0.1.18 (обе ступени дробления в Xray)."""
    cfg = Config()
    cfg.filters.max_members = 2
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []
    cfg.speed.sticky = False
    instance = Dual(cfg, paths)
    yield instance
    instance.store.close()


def _member(daemon: Dual):
    """Участник на Xray, которому дробление подходит (TLS или REALITY поверх TCP)."""
    for info in daemon.view():
        if info.role != "proxy" or info.profile != "xray:default":
            continue
        outbound = daemon.node(info).outbound
        if outbound and fragmenting.eligible(outbound):
            return info
    pytest.skip("в участниках нет сервера, которому подходит дробление")


def _entry(daemon, tag: str) -> dict:
    status = daemon.status()
    return next(entry for entry in [*status["members"], *status["spares"]] if entry["tag"] == tag)


# --- R1: эскалация у сервера в работе ---------------------------------------------------


def test_a_frozen_member_climbs_the_xray_steps_in_place_and_keeps_the_one_that_answers(tspu):
    """R1.1–R1.2, R1.4: участник «заморозился» — его не меняют, а на месте переводят на
    дробление ClientHello, затем на нарезку первых пакетов; ответил — так и остаётся в работе,
    событие и панель говорят, какой обход и после какого вердикта."""
    _start(tspu)
    member = _member(tspu)
    tspu.table[member.probe_tag] = {
        "xray:default": "FROZEN", "xray:fragment": "STALL_BEFORE_BODY", "xray:split": "OK",
    }
    tspu.vetted.clear()  # первая проверка участника — снова
    _rescan(tspu)
    tspu.tick()
    assert tspu.profile(member) == "xray:fragment" and member.tag in tspu.tags("proxy")
    assert tspu.applied[-1][1] is True  # срочно: трафик через участника ждёт
    tspu.tick()
    assert tspu.profile(member) == "xray:split" and member.tag in tspu.tags("proxy")
    tspu.tick()
    assert tspu.profile(member) == "xray:split" and not tspu._profile_trial
    assert member.tag in tspu.tags("proxy") and member.tag not in tspu.bad_members
    assert _has(tspu, "в работе не отвечает (FROZEN) — не меняю его, а пробую «Xray с дроблением "
                      "ClientHello»")
    assert _has(tspu, "отвечает только с нарезкой первых пакетов — она включена")
    escalation = _entry(tspu, member.tag)["escalation"]
    assert escalation["label"] == "xray+split" and escalation["verdict"] == "FROZEN"
    config_text = json.dumps(tspu.applied[-1][0])
    assert fragmenting.SPLIT_TAG in config_text  # outbound второй ступени заведён


def test_a_member_dead_on_every_xray_step_is_replaced(tspu):
    """Умершим участник считается только после неудачи и с дроблением: тогда — замена."""
    tspu.cfg.filters.rotate_after_min = 0
    _start(tspu)
    member = _member(tspu)
    tspu.table[member.probe_tag] = {"*": "CONNECT_FAIL"}
    tspu.vetted.clear()
    _rescan(tspu)
    for _ in range(6):
        tspu.tick()
        if member.tag not in tspu.tags("proxy"):
            break
    assert member.tag not in tspu.tags("proxy")
    probed = [profile for tag, profile in tspu.seen if tag == member.probe_tag]
    assert probed[:3] == ["xray:default", "xray:fragment", "xray:split"]
    assert _has(tspu, "в работе не отвечает ни на одной ступени дробления в Xray (CONNECT_FAIL)")


def test_escalations_are_limited_and_an_unstable_server_is_not_chosen(tspu):
    """R1.5: больше fragment.escalations переводов за fragment.escalation_hours — сервер
    «нестабилен по ТСПУ»: шлюз его сам в работу не ставит, пока окно не пройдёт."""
    tspu.cfg.filters.rotate_after_min = 0
    _start(tspu)
    spares = [info for info in tspu.view() if info.role == "spare"]
    first, *others = spares
    assert tspu._may_escalate(first.fingerprint, "Сервер") is True
    assert tspu._may_escalate(first.fingerprint, "Сервер") is True
    assert tspu._may_escalate(first.fingerprint, "Сервер") is False
    assert tspu._is_unstable(first.fingerprint)
    assert _has(tspu, "«Сервер» нестабилен по ТСПУ: 2 перевода на обход за 6 ч")
    tspu.tick()  # статус пишет шаг
    assert _entry(tspu, first.tag)["unstable_until"] is not None
    # Замену мёртвому участнику берут из остальных запасных.
    for info in others:
        tspu._unstable[info.fingerprint] = tspu.t + 3600
    keep = others[0]
    del tspu._unstable[keep.fingerprint]
    victim = tspu.tags("proxy")[0]
    tspu.set_alive(**{victim.replace("-", "_"): False})
    for _ in range(4):
        tspu.tick()
        if victim not in tspu.tags("proxy"):
            break
    members = {info.fingerprint for info in tspu.view() if info.role == "proxy"}
    assert keep.fingerprint in members and first.fingerprint not in members
    # Окно прошло — отметка снимается сама.
    tspu.t += 6 * 3600 + 1
    assert not tspu._is_unstable(first.fingerprint)


def test_a_calm_member_goes_back_to_plain_xray(tspu):
    """R1.3: участник на дроблении, который 20 проверок ядра подряд отвечает и пробыл на нём
    12 ч, пробуется без дробления — на месте; ответил — дробление снято, отметка «обход»
    тоже."""
    _start(tspu)
    member = _member(tspu)
    tspu.table[member.probe_tag] = {"xray:default": "FROZEN"}
    tspu.vetted.clear()
    _rescan(tspu)
    tspu.tick()
    tspu.tick()
    assert tspu.profile(member) == "xray:fragment" and not tspu._profile_trial
    assert _entry(tspu, member.tag)["escalation"]["label"] == "xray+frag"
    tspu.table[member.probe_tag] = {}  # провайдер перестал блокировать
    for _ in range(26):  # пробы ядра каждые полчаса — 13 ч
        tspu.t += 1800
        tspu.set_alive()
        tspu.tick()
        if tspu.profile(member) == "xray:default":
            break
    assert tspu.profile(member) == "xray:default"
    tspu.tick()  # скан на базе прошёл
    assert _has(tspu, "отвечает и без дробления ClientHello — оно выключено")
    assert _entry(tspu, member.tag)["escalation"] is None


# --- R3: проверочные хосты ------------------------------------------------------------


def test_probe_hosts_go_round_and_a_failed_one_rests():
    clock = [1000.0]
    cfg = Config()
    hosts = probehosts.ProbeHosts(cfg, clock=lambda: clock[0])
    urls = probehosts.all_urls(cfg)
    assert urls[0] == cfg.probe.url and len(urls) == 4
    picked = [hosts.next() for _ in range(8)]
    assert set(picked) == set(urls)  # по кругу — все
    text = hosts.failed(urls[1], "HTTP 403")
    assert "code.jquery.com не отвечает (HTTP 403)" in text and "30 мин" in text
    assert hosts.failed(urls[1], "HTTP 403") == ""  # пауза уже идёт — без нового события
    assert urls[1] not in hosts.active() and urls[1] not in [hosts.next() for _ in range(8)]
    assert hosts.next(avoid=urls[0]) != urls[0]
    clock[0] += 31 * 60
    assert urls[1] in hosts.active()
    hosts.answered(urls[1])
    snapshot = hosts.snapshot()
    item = next(entry for entry in snapshot["hosts"] if entry["url"] == urls[1])
    assert item["errors"] == 2 and item["ok"] == 1 and item["paused_until"] is None
    again = probehosts.ProbeHosts(cfg, clock=lambda: clock[0])
    assert again.load(hosts.dumps()) == 0
    assert again.states[urls[1]].errors == 2
    assert again.load("не json") == 1
    assert again.load(json.dumps({"hosts": ["сломано", {"url": urls[0], "ok": "x"}]})) == 2
    lines = probehosts.describe(snapshot)
    assert lines[0].startswith("cdn.jsdelivr.net (активный)")


def test_only_an_http_error_is_the_host_s_fault():
    assert probehosts.host_specific("http", 403)
    assert not probehosts.host_specific("timeout", 0)
    assert not probehosts.host_specific("stall", 0)
    assert not probehosts.host_specific("http", 0)


class Hosts(Harness):
    """Демон с проверочными хостами: bad — хост, который отвечает 403 через любой сервер."""

    def __init__(self, cfg, paths, **kwargs):
        super().__init__(cfg, paths, hosts=list(config.DEFAULT_PROBE_HOSTS), **kwargs)
        self.bad = ""
        self.e2e_urls: list[str] = []

    _check_e2e = Daemon._check_e2e

    def _e2e_get(self, url):
        self.e2e_urls.append(url)
        if url == self.bad:
            return DownloadResult(ok=False, kind="http", status=403, error="HTTP 403")
        return DownloadResult(ok=True, downloaded=57620)

    def _scan(self, info, password, url=None):
        url = url or self.cfg.probe.url
        self.scanned.append(info.tag)
        self.scan_urls[info.tag] = url
        if url == self.bad:
            return ScanResult(info.tag, "CONNECT_FAIL", 0, 0.2, "HTTP 403", "http", 403)
        return ScanResult(info.tag, "OK", 65536, 0.5)


@pytest.fixture()
def hosted(paths):
    cfg = Config()
    cfg.filters.max_members = 2
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []
    instance = Hosts(cfg, paths)
    instance.source = _free_inventory()  # безлимитная подписка: запасные — полной пробой
    yield instance
    instance.store.close()


def test_e2e_tries_another_host_and_rests_the_one_that_answered_403(hosted):
    """R3.2: хост ответил ошибкой — та же проверка другим хостом; прошла — сквозная проверка
    засчитана, хост на паузе, событие-наблюдение, а не состояние."""
    hosted.bad = hosted.cfg.probe.url
    _started(hosted)
    for _ in range(12):  # хосты берут по кругу и сканы — до probe.url дойдёт за несколько шагов
        if hosted.bad in hosted.e2e_urls:
            break
        hosted.t += 20
        assert hosted.tick() is State.HEALTHY
    assert hosted.bad in hosted.e2e_urls
    assert hosted.tick() is State.HEALTHY and hosted.e2e_streak == 0
    assert hosted.hosts.states[hosted.bad].paused_until > hosted.t
    assert _has(hosted, "проверочный хост cdn.jsdelivr.net не отвечает (HTTP 403)")
    tried = len(hosted.e2e_urls)
    hosted.t += 20
    hosted.tick()
    assert hosted.bad not in hosted.e2e_urls[tried:]  # пока на паузе — не берётся
    status = hosted.status()
    assert status["probe_hosts"]["current"] != hosted.bad
    assert any(item["errors"] for item in status["probe_hosts"]["hosts"])


def test_a_scan_that_got_403_from_the_host_is_repeated_with_another(hosted):
    """Скан запасного: хост ответил 403 — та же проба другим хостом; вердикт — по ней."""
    _started(hosted)
    hosted.bad = probehosts.all_urls(hosted.cfg)[2]
    hosted.hosts._turns["scan"] = 1  # следующий по кругу сканов — bad
    spare = next(info for info in hosted.view() if info.role == "spare")
    result = hosted._probe_scan(spare, "secret")
    assert result.verdict == "OK"
    assert hosted.hosts.states[hosted.bad].errors == 1


def test_probe_target_state_only_when_every_host_is_down(hosted, monkeypatch):
    """R3.3: не отвечает только probe.url, а другой хост через серверы открывается — ядро
    переходит на него, состояние прежнее (не PROBE_TARGET_UNREACHABLE, не ALL_DEAD). Не
    открывается ни один — PROBE_TARGET_UNREACHABLE, как раньше."""
    hosted.cfg.filters.rotate_after_min = 0
    _started(hosted)
    hosted.bad = hosted.cfg.probe.url
    hosted.failures["*"] = ScanResult("", "CONNECT_FAIL", 0, 0.2, "HTTP 403", "http", 403)
    hosted.direct = "HTTP 403"
    hosted.set_alive(**{tag.replace("-", "_"): False for tag in hosted.tags("proxy")})
    members = hosted.tags("proxy")
    alternate = probehosts.all_urls(hosted.cfg)[1]
    monkeypatch.setattr(
        target, "answers_via",
        lambda cfg, members, password, url, user="": url == alternate,
    )
    state = hosted.tick()
    assert state is not State.PROBE_TARGET_UNREACHABLE and state is not State.ALL_DEAD
    assert hosted.applied, "ядро должно перейти на другой хост"
    probes = hosted.applied[-1][0]["burstObservatory"]["pingConfig"]["destination"]
    assert probes == alternate and hosted.tags("proxy") == members  # замен нет
    assert _has(hosted, "ядро пробует серверы по https://code.jquery.com/")
    # Ни один хост не открывается — это адрес проверки, как до 0.1.18.
    monkeypatch.setattr(target, "answers_via", lambda *args, **kwargs: False)
    target.use_fallback(hosted.cfg, hosted.paths, False)
    hosted.next_target_check = 0.0
    hosted.t += 20
    assert hosted.tick() is State.PROBE_TARGET_UNREACHABLE


def test_wan_is_down_only_when_every_check_host_is_down(hosted, monkeypatch):
    """R3.3: «нет провайдера» — когда не отвечает ни wan_check, ни watchdog.wan_checks."""
    answers = {"ya.ru": False, "vk.com": True, "mail.ru": False}
    monkeypatch.setattr(hosted, "_provider_address", lambda host: host)
    monkeypatch.setattr(
        "xgw.watch.checks.tcp_check",
        lambda address, port, mark=None, timeout=5.0: answers[address],
    )
    assert Daemon._check_provider(hosted) is True
    answers["vk.com"] = False
    assert Daemon._check_provider(hosted) is False
    hosted.cfg.watchdog.wan_check, hosted.cfg.watchdog.wan_checks = "", []
    assert Daemon._check_provider(hosted) is True  # проверять нечем


# --- R4a: bootstrap-DNS ------------------------------------------------------------------


def test_resolver_check_tells_each_resolver(monkeypatch):
    cfg = Config()
    down = {"https://9.9.9.9:5053/dns-query"}

    def resolve(name, entries, mark=None, cancel=None):
        assert name == "cdn.jsdelivr.net"
        if entries[0] in down:
            raise fetch.ResolveError(f"не удалось разрешить {name}: {entries[0]}: таймаут")
        return ["203.0.113.5"]

    monkeypatch.setattr(resolving.fetch, "resolve_domain", resolve)
    results = resolving.check_all(cfg, mark=None)
    assert [item["entry"] for item in results] == [
        "https://1.1.1.1", "https://8.8.8.8", "udp://77.88.8.8", "https://94.140.14.140",
        "https://185.222.222.222", "https://9.9.9.9:5053",
    ]
    assert len(cfg.dns.resolvers) == 6  # три из dns.bootstrap и три из bootstrap_extra
    assert resolving.verdict(results) == "partial"
    text = resolving.event_text(results)
    assert "отвечают 5 из 6" in text and "9.9.9.9:5053" in text
    down.update(cfg.dns.resolvers)
    assert resolving.verdict(resolving.check_all(cfg, mark=None)) == "down"
    assert resolving.verdict([]) == ""


def test_a_resolver_that_failed_is_tried_last(monkeypatch):
    entries = ["https://a/dns-query", "https://b/dns-query", "udp://c"]
    monkeypatch.setattr(fetch, "_resolver_down", {})
    assert fetch.resolver_order(entries, now=10.0) == entries
    fetch.resolver_failed("https://a/dns-query", now=10.0)
    assert fetch.resolver_order(entries, now=20.0) == [entries[1], entries[2], entries[0]]
    assert fetch.resolver_order(entries, now=10.0 + fetch.RESOLVER_PAUSE + 1) == entries
    fetch.resolver_answered("https://a/dns-query")
    assert fetch.resolver_order(entries, now=20.0) == entries


def test_daemon_reports_resolver_changes_once(paths):
    cfg = Config()
    cfg.dns.bootstrap = []
    daemon = Harness(cfg, paths)
    try:
        good = [{"entry": "https://1.1.1.1/dns-query", "ok": True, "ms": 30, "error": ""}]
        bad = [*good, {"entry": "https://9.9.9.9:5053/dns-query", "ok": False, "ms": 8000,
                       "error": "таймаут"}]
        daemon._resolvers_done(daemon.t, good)
        assert not any(event.startswith("dns:") for event in daemon.events())
        daemon._resolvers_done(daemon.t, bad)
        daemon._resolvers_done(daemon.t, bad)  # то же — без нового события
        events = [event for event in daemon.events() if event.startswith("dns:")]
        assert len(events) == 1 and "отвечают 1 из 2" in events[0]
        daemon._resolvers_done(daemon.t, [{**bad[1]}])
        daemon._resolvers_done(daemon.t, good)
        # Журнал — новые сверху.
        events = [event for event in daemon.events() if event.startswith("dns:")][::-1]
        assert len(events) == 3 and "ни один резолвер" in events[1]
        assert "снова отвечают все" in events[2]
        assert resolving.loads(daemon.store.get_meta(resolving.META))["results"] == good
    finally:
        daemon.store.close()


# --- R4b: DERP и аварийный маршрут Tailscale -----------------------------------------------


def test_derp_hosts_of_the_home_region():
    derp_map = json.dumps({"Regions": {
        "1": {"RegionCode": "nyc", "Nodes": [{"HostName": "derp1.tailscale.com"}]},
        "4": {"RegionCode": "fra", "Nodes": [{"HostName": "derp4.tailscale.com"},
                                             {"HostName": "derp4b.tailscale.com"}]},
    }})
    assert tailscale.parse_derp_hosts(derp_map, "fra") == [
        "derp4.tailscale.com", "derp4b.tailscale.com"]
    assert tailscale.parse_derp_hosts(derp_map, "") == [
        "derp1.tailscale.com", "derp4.tailscale.com", "derp4b.tailscale.com"]
    assert tailscale.parse_derp_hosts("не json", "fra") == []
    status = tailscale.parse_status(json.dumps({"Self": {"Relay": "fra"}}))
    assert status is not None and status.relay == "fra"


def test_route_direct_with_dead_derp_takes_tailscaled_through_the_vpn():
    """R4b: при route = "direct" метка tailscaled убирается из набора ts_direct только по
    отметке «DERP напрямую не отвечает»; Xray не отвечает — снова напрямую (метка в наборе)."""
    cfg = Config()
    rules, _ = nft.build_rules(cfg, capture=True, time_uids=(), tailscale=True)
    assert rules.ts_direct is True
    rules, _ = nft.build_rules(cfg, capture=True, time_uids=(), tailscale=True, ts_fallback=True)
    assert rules.ts_direct is False
    rules, _ = nft.build_rules(
        cfg, capture=True, time_uids=(), tailscale=True, ts_fallback=True, xray_down=True,
    )
    assert rules.ts_direct is True


class DerpCapture:
    """Перехват, который помнит аварийный маршрут Tailscale."""

    def __init__(self) -> None:
        self.via_vpn = False
        self.calls: list[bool] = []

    def tailscale_via_vpn(self) -> bool:
        return self.via_vpn

    def tailscale_fallback(self, on: bool) -> str:
        self.calls.append(on)
        if on == self.via_vpn:
            return ""
        self.via_vpn = on
        return "через VPN" if on else "снова напрямую"


def test_daemon_moves_tailscaled_after_derp_fails_and_back_after_it_answers(paths):
    cfg = Config()
    cfg.dns.bootstrap = []
    daemon = Harness(cfg, paths)
    daemon.capture = DerpCapture()
    try:
        for _ in range(cfg.tailscale.derp_fails - 1):
            daemon._derp_done("derp4.tailscale.com: таймаут", xray_ok=True)
        assert daemon.capture.via_vpn is False
        daemon._derp_done("derp4.tailscale.com: таймаут", xray_ok=False)
        assert daemon.capture.via_vpn is False  # Xray не отвечает — через него идти некуда
        daemon._derp_done("derp4.tailscale.com: таймаут", xray_ok=True)
        assert daemon.capture.via_vpn is True
        assert _has(daemon, "через VPN (не отвечает: derp4.tailscale.com: таймаут)")
        daemon._derp_done("", xray_ok=True)
        assert daemon.capture.via_vpn is True  # одной удачи мало
        daemon._derp_done(None, xray_ok=True)  # проверять было нечем — ничего не меняется
        daemon._derp_done("", xray_ok=True)
        assert daemon.capture.via_vpn is False and _has(daemon, "снова напрямую")
    finally:
        daemon.store.close()


# --- конфиг ------------------------------------------------------------------------------


def test_new_keys_have_defaults_and_bad_values_are_dropped(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[probe]\n"
        'urls = ["ftp://x", "https://a.example/f.bin", "https://a.example/f.bin"]\n'
        "host_pause_minutes = 0\n"
        "[watchdog]\n"
        'wan_checks = ["vk.com", "vk.com:443", "ya.ru:443"]\n'
        "[dns]\n"
        'bootstrap_extra = ["8.8.8.8", "https://94.140.14.140/dns-query"]\n'
        "[fragment]\n"
        'split_packets = "много"\n'
        "calm_probes = 0\n"
        "[speed]\n"
        "low_count = 50\n"
        "[network]\n"
        "block_quic = false\n"
        "[tray]\n"
        "enabled = false\n",
        encoding="utf-8",
    )
    cfg, warnings = config.load(path)
    assert cfg.probe.urls == ["https://a.example/f.bin"]
    assert cfg.probe.host_pause_minutes == 30
    assert cfg.watchdog.wan_checks == ["vk.com:443"]  # ya.ru:443 — уже wan_check
    assert cfg.dns.bootstrap_extra == ["https://94.140.14.140/dns-query"]
    assert cfg.fragment.split_packets == "1-3" and cfg.fragment.calm_probes == 20
    assert cfg.speed.low_count == 3
    assert cfg.network.block_quic is False and cfg.tray.enabled is False
    assert len(warnings) == 7, warnings
    defaults = Config()
    assert defaults.network.block_quic and defaults.tray.enabled and defaults.speed.guard
    assert defaults.speed.unlimited_hours == 6 and defaults.speed.spare_hours == 24
    assert config.probe_bytes(config.DEFAULT_PROBE_HOSTS[1]) == 45_404
