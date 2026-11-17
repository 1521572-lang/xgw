"""Границы нового выхода и возврат на VPN при отказах; без скачивания nfqws2."""

import copy
import json
import time
from dataclasses import replace

import pytest
from test_generator import _build

from xgw import zapret2 as z
from xgw.config import ConfigError, load, service_ports
from xgw.generator import builder
from xgw.generator.diff import diff_configs
from xgw.net import nft
from xgw.net.cmd import CommandError
from xgw.watch import checks


def setup():
    built, cfg, selection = _build()
    cfg.zapret2.mode = "selective"
    cfg.zapret2.probe_urls = ["https://www.youtube.com/watch?v=test",
                             "https://cdn.googlevideo.com/video"]
    return cfg, built.config, selection


class Store:
    def __init__(self):
        self.data = {}

    def get_meta(self, name):
        return self.data.get(name)

    def set_meta(self, name, value):
        self.data[name] = value


class Runtime:
    def __init__(self):
        self.events = []
        self.up = False
        self.broken = False

    def gate(self, seconds=0):
        self.events.append(("gate", seconds))
        if self.broken:
            raise CommandError("private command detail")

    def start(self, cfg):
        self.events.append(("start", 0))
        self.up = True

    def stop(self):
        self.events.append(("stop", 0))
        self.up = False

    def alive(self, queue):
        return self.up

    def sample_trace(self):
        self.events.append(("sample", 0))

    def finish_trace(self):
        assert not self.up
        return {"state": "observed", "queue_packets": 8, "hello": 2,
                "send_calls": 6, "send_ok": 6, "applied": 2, "lua_errors": 0}


class Harness:
    def __init__(self):
        self.cfg, self.current, _ = setup()
        self.runtime = Runtime()
        self.controller = z.Controller(Store(), self.runtime)
        self.ok = True
        self.accept = True
        self.controller.probe = lambda *args: self.ok

    def apply(self, target, base):
        assert base == self.current
        self.runtime.events.append(("apply", z.active(target)))
        if self.accept:
            self.current = copy.deepcopy(target)
        return self.accept

    def step(self, now, **kwargs):
        return self.controller.step(self.cfg, self.current, now, self.apply, **kwargs)

    def activate(self):
        self.step(0)  # служебный вход
        assert not z.active(self.current)
        self.step(1)  # старт очереди
        assert not z.active(self.current)
        self.step(2)  # проверка
        assert z.active(self.current)


@pytest.mark.parametrize("strategy", ["multisplit", "hostfakesplit_md5"])
def test_off_is_original_config_without_starting_anything(strategy):
    result, cfg, _ = _build()
    cfg.zapret2.strategy = strategy
    assert not z.validate(cfg)
    assert z.patch(result.config, cfg) == result.config
    runtime = Runtime()
    ctl = z.Controller(Store(), runtime)
    assert not ctl.step(cfg, result.config, 0, lambda *_: pytest.fail("apply called"))
    assert not runtime.events
    assert "zapret2.probe_port" not in service_ports(cfg)


def test_selected_route_scope_and_priorities():
    cfg, original, _ = setup()
    rules = original["routing"]["rules"]
    rules.insert(-1, {"type": "field", "source": ["192.168.50.5"], "outboundTag": "proxy-a"})
    rules.insert(-1, {"type": "field", "domain": ["domain:youtube.com"], "balancerTag": "youtube"})
    target = z.patch(original, cfg, enabled=True)
    routed = target["routing"]["rules"]
    at = next(i for i, r in enumerate(routed) if r.get("outboundTag") == z.OUT
              and r.get("inboundTag") != [z.PROBE])
    assert routed[at]["network"] == "tcp" and routed[at]["port"] == "443"
    assert set(routed[at]["inboundTag"]) == {"tproxy-in", "tproxy-in6", "tun-in"}
    assert at > max(i for i, r in enumerate(routed) if r.get("source")
                    or r.get("outboundTag") == "direct")
    assert at < next(i for i, r in enumerate(routed) if r.get("balancerTag") == "youtube")
    assert target["inbounds"][-1]["settings"]["accounts"][0]["pass"] == "P" * 32
    assert target["outbounds"][-1]["streamSettings"]["sockopt"]["mark"] == z.MARK
    assert z.patch(target, cfg, enabled=True) == target
    assert not diff_configs(original, target).restart_reasons
    assert not diff_configs(target, z.patch(target, cfg)).restart_reasons
    cfg.zapret2.mode = "off"
    assert z.patch(target, cfg) == original


def test_build_reserves_probe_port_and_starts_without_direct_rule():
    cfg, _, selection = setup()
    cfg.xray.probe_port_base = cfg.zapret2.probe_port
    config = builder.build(cfg, selection, hosts={}, probe_password="P" * 32).config
    ports = [i["port"] for i in config["inbounds"] if "port" in i]
    assert len(ports) == len(set(ports))
    assert not z.active(config)


@pytest.mark.parametrize("value", ["http://www.youtube.com/", "https://evil.example/",
                                    "https://www.youtube.com:444/", "https://u:p@youtube.com/",
                                    "https://www.youtube.com/\r\nInjected:yes"])
def test_bad_probe_never_enables_direct(value):
    cfg, _, _ = setup()
    cfg.zapret2.probe_urls = [value]
    assert z.validate(cfg)
    assert cfg.zapret2.mode == "off"


def test_toml_validation_and_separate_marks(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[zapret2]\nmode="selective"\nstrategy="invalid"\n')
    # Versioned migration must reject invalid policy, not silently choose another route.
    with pytest.raises(ConfigError, match="strategy"):
        load(path)
    cfg, _, _ = setup()
    cfg.capture.mark_bypass = z.MARK
    assert z.validate(cfg)
    assert cfg.zapret2.mode == "off"


def test_missing_video_probe_does_not_launch_worker():
    h = Harness()
    h.cfg.zapret2.probe_urls.pop()
    h.step(0)
    assert not z.active(h.current)
    assert not any(name == "start" for name, _ in h.runtime.events)


@pytest.mark.parametrize(
    ("enabled", "media_status", "opens"),
    [(False, 204, False), (True, 204, True), (True, 200, True),
     (True, 302, False), (True, 403, False)],
)
def test_youtube_transport_gate_retains_page_and_cdn_checks(enabled, media_status, opens):
    h = Harness()
    h.cfg.zapret2.youtube_transport_probe = enabled
    h.cfg.zapret2.probe_urls[1] = "https://r1---sn-test.googlevideo.com/videoplayback"
    h.controller.probe = z.Controller.probe.__get__(h.controller)
    seen = []

    def request(url, *_args, min_body=16 * 1024, max_total=8, silence=4, tls_timeout=None):
        seen.append((min_body, max_total, silence, tls_timeout))
        if "googlevideo.com" not in url:
            return checks.DownloadResult(ok=True, status=200, downloaded=32768, phase="body")
        return checks.DownloadResult(ok=min_body == 0 and media_status in (200, 204),
                                     status=media_status, downloaded=0, phase="headers")

    h.controller._request = request
    for now in (0, 1, 2):
        h.step(now)
    assert seen == ([(16384, 12, 6, 10), (0, 12, 4, 10)] if enabled
                    else [(16384, 8, 4, None)] * 2)
    assert z.active(h.current) is opens
    if enabled:
        rows = h.controller.view["transport_probes"]
        assert rows["page"]["bytes"] == 32768 and rows["page"]["ok"]
        assert rows["cdn"]["http"] == media_status and rows["cdn"]["ok"] is opens
    else:
        assert "transport_probes" not in h.controller.view
    if opens:
        assert h.controller.view["reason"] == "youtube_transport_ok"
        h.runtime.up = False
        h.step(3)
        assert not z.active(h.current)
        assert h.controller.view["reason"] == "worker_down"
        assert "transport_probes" not in h.controller.view
    else:
        assert h.controller.view["reason"] == (
            "youtube_cdn_probe_failed" if enabled else "probe_failed"
        )


def test_youtube_page_failure_records_phase_and_preserves_closed_route():
    h = Harness()
    h.cfg.zapret2.youtube_transport_probe = True
    h.cfg.zapret2.probe_urls[1] = "https://r1.googlevideo.com/videoplayback"
    h.controller.probe = z.Controller.probe.__get__(h.controller)

    def request(url, *_args, **options):
        assert "googlevideo.com" not in url
        return checks.DownloadResult(ok=False, kind="stall", phase="headers", error="private")

    h.controller._request = request
    for now in (0, 1, 2, 3):
        h.step(now)
    assert not z.active(h.current)
    view = h.controller.view
    assert (view["state"], view["reason"]) == ("fallback", "youtube_page_probe_failed")
    assert set(view["transport_probes"]) == {"page"}
    row = view["transport_probes"]["page"]
    assert (row["phase"], row["kind"], row["ok"]) == ("headers", "stall", False)
    assert "private" not in repr(row)


def test_selective_recheck_reports_actual_page_and_new_time(monkeypatch):
    h = Harness()
    h.cfg.zapret2.youtube_transport_probe = True
    page = "https://www.youtube.com/t/terms?private=test"
    cdn = "https://r1.googlevideo.com/videoplayback?private=test"
    h.cfg.zapret2.probe_urls = [page, cdn]
    h.controller.probe = z.Controller.probe.__get__(h.controller)
    checks_seen = []
    wall = 1000.0
    monkeypatch.setattr(z.time, "time", lambda: wall)

    def request(url, *_args, **_kwargs):
        checks_seen.append(url)
        if wall == 2000.0 and url == page:
            return checks.DownloadResult(ok=False, kind="timeout", phase="tls")
        return checks.DownloadResult(ok=True, status=200, downloaded=32768, phase="body")

    h.controller._request = request
    h.activate()
    rows = h.controller.view["transport_probes"]
    assert rows["page"]["page_kind"] == "terms" and rows["page"]["started_at"] == 1000
    assert "page_kind" not in rows["cdn"]

    wall = 2000.0
    h.step(h.controller.next_check)
    assert not z.active(h.current)
    assert h.controller.view["reason"] == "youtube_page_probe_failed"
    rows = h.controller.view["transport_probes"]
    assert set(rows) == {"page"}
    assert rows["page"]["page_kind"] == "terms" and rows["page"]["started_at"] == 2000
    assert checks_seen == [page, cdn, page]
    assert "private" not in repr(rows)


@pytest.mark.parametrize(("scenario", "attempts", "active"), [
    ("recovers", 2, True), ("double_timeout", 2, False),
    ("http_error", 1, False), ("no_budget", 1, False), ("lost_worker", 1, False),
])
def test_selective_cdn_retry_is_bounded_and_charged(scenario, attempts, active):
    h = Harness()
    h.cfg.zapret2.youtube_transport_probe = True
    h.cfg.zapret2.daily_probe_mb = 1 if scenario == "no_budget" else 256
    page = "https://www.youtube.com/t/terms"
    cdn = "https://r1.googlevideo.com/videoplayback?sig=fixture"
    h.cfg.zapret2.probe_urls = [page, cdn]
    h.controller.probe = z.Controller.probe.__get__(h.controller)
    urls = []

    def request(url, *_args, **_options):
        urls.append(url)
        if url == page or urls.count(cdn) == 1 or (scenario == "recovers" and urls.count(cdn) == 3):
            return checks.DownloadResult(ok=True, status=200, downloaded=32768, phase="body")
        if scenario == "http_error":
            return checks.DownloadResult(ok=False, status=403, kind="http", phase="headers")
        if scenario == "lost_worker":
            h.runtime.up = False
        return checks.DownloadResult(ok=False, kind="timeout", phase="tls")

    h.controller._request = request
    h.activate()
    h.step(h.controller.next_check)
    assert urls == [page, cdn, page, *[cdn] * attempts]
    assert z.active(h.current) is active
    reason = "youtube_transport_ok" if active else "youtube_cdn_probe_failed"
    assert h.controller.view["reason"] == reason
    row = h.controller.view["transport_probes"]["cdn"]
    assert row["ok"] is active
    assert ("first_tls_timeout_ms" in row) is (attempts == 2)
    assert "fixture" not in repr(row)
    charged = json.loads(h.controller.store.get_meta(z.BUDGET))["bytes"]
    assert charged == (3 + attempts) * z.PROBE_CHARGE


def test_youtube_transport_rejects_wrong_media_url_or_extra_domains():
    cfg, _, _ = setup()
    cfg.zapret2.youtube_transport_probe = True
    assert not z.configured(cfg)  # generic CDN URL is insufficient even with opt-in
    cfg.zapret2.probe_urls[1] = "https://r1---sn-test.googlevideo.com/videoplayback"
    assert z.configured(cfg)
    cfg.zapret2.domains.append("domain:example.org")
    assert not z.configured(cfg)
    assert z.validate(cfg)


def test_conflicting_probe_port_disables_new_mode():
    cfg, _, _ = setup()
    cfg.zapret2.probe_port = cfg.xray.metrics_port
    assert z.validate(cfg)
    assert cfg.zapret2.mode == "off"


@pytest.mark.parametrize("failure", ["probe", "worker", "budget", "apply"])
def test_failure_closes_gate_before_fallback(failure):
    h = Harness()
    h.activate()
    h.runtime.events.clear()
    if failure == "probe":
        h.ok = False
    elif failure == "worker":
        h.runtime.up = False
    elif failure == "budget":
        budget = json.loads(h.controller.store.get_meta(z.BUDGET))
        budget["bytes"] = 1024 ** 3
        h.controller.store.set_meta(z.BUDGET, json.dumps(budget))
    else:
        # Отказ убрать прямое правило: ворота закрыты, состояние честно blocked.
        h.ok = h.accept = False
    h.step(200)
    events = h.runtime.events
    close = events.index(("gate", 0))
    fallback = events.index(("apply", False))
    assert close < fallback < events.index(("stop", 0))
    assert h.controller.view["state"] == ("blocked" if failure == "apply" else "fallback")
    assert not h.controller.healthy
    assert not h.runtime.up
    if failure != "apply":
        assert not z.active(h.current)


def test_recovery_waits_and_rechecks():
    h = Harness()
    h.activate()
    h.ok = False
    h.step(200)
    h.ok = True
    h.step(201)
    assert not z.active(h.current)
    assert h.controller.view["reason"] == "probe_failed"
    h.step(501)
    assert not z.active(h.current)
    h.step(502)
    assert z.active(h.current)


def test_vpn_control_runs_after_closing_gate_and_withdrawing_direct_route(monkeypatch):
    h = Harness()
    h.activate()
    h.ok = False
    calls = []

    def vpn_control(url, port, *_args):
        assert not z.active(h.current)
        assert not h.runtime.up
        assert ("gate", 0) in h.runtime.events
        calls.append((url, port))
        return checks.DownloadResult(True)

    monkeypatch.setattr(h.controller, "_request", vpn_control)
    h.step(200, vpn_probe_port=20011)
    assert calls == [(h.cfg.zapret2.probe_urls[0], 20011)]
    assert h.controller.view["vpn_control"] == "pass"
    assert h.controller.view["state"] == "fallback"
    result = dict(h.controller.view)
    h.step(220, vpn_probe_port=20011)
    h.step(240, vpn_probe_port=0)
    assert h.controller.view == result
    assert len(calls) == 1
    h.step(500, vpn_probe_port=20011)
    assert h.controller.view["state"] == "preparing"
    assert "vpn_control" not in h.controller.view


@pytest.mark.parametrize(("port", "budget_ok", "gate_ok", "reason"), [
    (0, True, True, "no_vpn_probe_port"),
    (20011, False, True, "budget_unavailable"),
    (20011, True, False, "gate_not_closed"),
])
def test_vpn_control_reports_why_cleanup_or_probe_could_not_complete(
    monkeypatch, port, budget_ok, gate_ok, reason,
):
    h = Harness()
    h.activate()
    h.runtime.up = False
    h.runtime.broken = not gate_ok
    monkeypatch.setattr(h.controller, "_budget", lambda *_args, **_kwargs: budget_ok)
    monkeypatch.setattr(h.controller, "_request", lambda *_: pytest.fail("unexpected VPN probe"))
    h.step(200, vpn_probe_port=port)
    assert h.controller.view["vpn_control"] == "not_run"
    assert h.controller.view["vpn_control_reason"] == reason
    if gate_ok:
        result = dict(h.controller.view)
        h.step(220, vpn_probe_port=20011)
        assert h.controller.view == result


def test_uncertain_start_runs_cleanup_and_retries_unconfirmed_stop(monkeypatch):
    h = Harness()
    h.step(0)

    def failed_start(cfg):
        h.runtime.up = True
        raise CommandError("systemd start timed out")

    def failed_stop():
        raise CommandError("systemd stop timed out")

    with monkeypatch.context() as patch:
        patch.setattr(h.runtime, "start", failed_start)
        patch.setattr(h.runtime, "stop", failed_stop)
        h.step(1)
    assert h.runtime.up and h.controller.cleanup_pending
    assert h.controller.view["state"] == "blocked"
    assert not z.active(h.current)
    h.step(2)
    assert not h.runtime.up and not h.controller.cleanup_pending
    assert not z.active(h.current)


@pytest.mark.parametrize("direct_ok", [False, True])
def test_compare_runs_both_pairs_without_enabling_client_route(monkeypatch, direct_ok):
    h = Harness()
    h.cfg.zapret2.mode = "compare"
    assert not z.validate(h.cfg)
    vpn_port = builder.applied_nodes(h.current)[0].probe_port
    direct_port = h.cfg.zapret2.probe_port
    calls = []

    def request(host, port, url, **kwargs):
        calls.append((port, url, kwargs["user_agent"]))
        if port == direct_port and not direct_ok:
            return checks.DownloadResult(False, kind="timeout", phase="tls", error="secret")
        return checks.DownloadResult(True, downloaded=32768, status=206, phase="body",
                                     location="secret")

    monkeypatch.setattr(checks, "http_get_via_proxy", request)
    original = copy.deepcopy(h.current)
    assert not z.active(z.patch(original, h.cfg, enabled=True))
    for now in (0, 1, 2, 600):
        h.step(now, vpn_probe_port=vpn_port)
    assert h.current == original
    assert h.controller.view["state"] == "compared"
    assert h.controller.view["reason"] == "comparison_done"
    assert h.controller.view["trace"]["applied"] == 2
    assert h.runtime.events.index(("sample", 0)) < h.runtime.events.index(("stop", 0))
    assert [(port, url) for port, url, _ in calls] == [
        (port, url) for url in h.cfg.zapret2.probe_urls for port in (vpn_port, direct_port)
    ]
    assert len({agent for _, _, agent in calls}) == 1
    assert not h.runtime.up and h.runtime.events[-1] == ("stop", 0)
    assert all(not enabled for action, enabled in h.runtime.events if action == "apply")
    assert ("gate", 45) in h.runtime.events
    assert json.loads(h.controller.store.get_meta(z.BUDGET))["bytes"] == 14 * z.PROBE_CHARGE
    rows = h.controller.view["probes"]
    assert [(row["probe"], row["path"], row["ok"]) for row in rows] == [
        (1, "vpn", True), (1, "zapret2", direct_ok), (2, "vpn", True), (2, "zapret2", direct_ok)
    ]
    payload = json.dumps(rows)
    assert "secret" not in payload and "https://" not in payload


def test_compare_without_a_vpn_control_is_incomplete(monkeypatch):
    h = Harness()
    h.cfg.zapret2.mode = "compare"
    monkeypatch.setattr(checks, "http_get_via_proxy", lambda *_a, **_k: pytest.fail("no control"))
    for now in range(3):
        h.step(now)
    assert h.controller.view["reason"] == "comparison_incomplete"
    assert h.controller.view["probes"] == [] and not h.runtime.up


def test_capture_disabled_removes_route_and_stops():
    h = Harness()
    h.activate()
    h.step(3, allowed=False)
    assert not z.active(h.current)
    assert not h.runtime.up


def test_old_probe_does_not_extend_lease_and_rejected_scaffold_is_blocked():
    h = Harness()
    h.activate()
    h.step(102)
    assert h.runtime.events[-1] == ("gate", 140)
    h = Harness()
    h.accept = False
    h.step(0)
    assert h.controller.view["state"] == "blocked"
    assert h.controller.view["reason"] == "apply_failed"


def test_missing_gate_stops_worker_and_does_not_claim_active():
    h = Harness()
    h.activate()
    h.runtime.broken = True
    h.step(3)
    assert not z.active(h.current)
    assert not h.runtime.up
    assert "private" not in json.dumps(h.controller.view)


def test_nft_does_not_broaden_bypass_or_queue_other_traffic(monkeypatch):
    monkeypatch.setattr(nft, "singbox_user_uid", lambda: None)
    cfg, _, _ = setup()
    rules, _ = nft.build_rules(cfg, capture=True, time_uids=())
    guard = nft.render_guard(rules)
    text = nft.render(rules)
    assert "meta mark 0x2 return" in text
    assert "meta mark and" not in "\n".join(line for line in text.splitlines() if "0x2" in line)
    assert "meta mark 0x10000000 tcp dport 443 counter queue num 200" in guard
    assert "queue num 200 bypass" not in guard
    assert "ct original packets" not in guard  # не требует nf_conntrack_acct/sysctl


def test_synack_observation_arms_only_marked_handshakes_and_uses_selected_queue(monkeypatch):
    monkeypatch.setattr(nft, "singbox_user_uid", lambda: None)
    cfg, _, _ = setup()
    cfg.zapret2.observe_synack = True
    cfg.zapret2.queue_num = 201
    rules, _ = nft.build_rules(cfg, capture=True, time_uids=())
    guard = nft.render_guard(rules)
    arm = next(line for line in guard.splitlines() if "ct mark set ct mark |" in line)
    assert "meta iif 0 meta nfproto ipv4 meta mark 0x10000000" in arm
    assert "ct direction original ct state new tcp dport 443" in arm
    assert "meta mark @zapret2_live" in arm and "== syn" in arm
    reply = next(line for line in guard.splitlines() if "ct mark set ct mark &" in line)
    assert 'iifname != "lo" meta nfproto ipv4' in reply
    assert "ct direction reply ct state established tcp sport 443" in reply
    assert "== (syn | ack)" in reply and "@zapret2_live" in reply
    assert "ct mark set ct mark & 0xefffffff queue num 201" in reply
    assert "ct reply packets" not in guard and "queue num 201 bypass" not in guard
    ipv6_output = nft.render6(replace(rules, capture6=True)).split("  chain output {", 1)[1]
    assert ipv6_output.index(f"meta mark {z.MARKS} return") < ipv6_output.index("meta mark set")
    cfg.zapret2.mode = "off"
    rules, _ = nft.build_rules(cfg, capture=True, time_uids=())
    assert "zapret2_reply" not in nft.render_guard(rules)
    assert "meta mark 0x50000000 notrack" in guard
    output = guard.split("chain output {")[1]
    assert output.index("meta mark { 0x10000000, 0x50000000 } counter drop") < output.index(
        "jump pass")
    cfg.zapret2.mode = "off"
    rules, _ = nft.build_rules(cfg, capture=True, time_uids=())
    assert "queue num" not in nft.render_guard(rules)


def test_reply_window_requires_accounting_and_keeps_first_packets_bounded(monkeypatch, tmp_path):
    monkeypatch.setattr(nft, "singbox_user_uid", lambda: None)
    cfg, _, _ = setup()
    cfg.zapret2.observe_synack = True
    cfg.zapret2.observe_reply_packets = 8
    acct = tmp_path / z.CONNTRACK_ACCT
    acct.parent.mkdir(parents=True)
    acct.write_text("0\n")
    rules, warnings = nft.build_rules(cfg, capture=True, time_uids=(), proc_sys=tmp_path)
    guard = nft.render_guard(rules)
    assert "zapret2_reply" in guard and "ct reply packets" not in guard
    assert any("nf_conntrack_acct=1" in warning for warning in warnings)
    assert acct.read_text() == "0\n"
    acct.write_text("1\n")
    rules, _ = nft.build_rules(cfg, capture=True, time_uids=(), proc_sys=tmp_path)
    guard = nft.render_guard(rules)
    replies = [line for line in guard.splitlines() if "ct reply packets" in line]
    assert len(replies) == 2
    assert "ct direction reply ct state established tcp sport 443" in replies[0]
    assert "ct mark & 0x18000000 == 0x18000000 ct mark & 0x10000000 @zapret2_live" in replies[0]
    assert "ct reply packets 2-9" in replies[0] and "queue num 200" in replies[0]
    assert "ct reply packets > 9 ct mark set ct mark & 0xe7ffffff" in replies[1]
    rules, _ = nft.build_rules(cfg, capture=False, time_uids=(), proc_sys=tmp_path)
    assert "ct reply packets" not in nft.render_guard(rules)


def test_gate_refresh_is_atomic_and_expires():
    calls = []
    runtime = z.Runtime(lambda argv, **kw: calls.append((argv, kw)))
    runtime.gate(240)
    assert len(calls) == 1
    script = calls[0][1]["input"]
    assert script.startswith("flush set inet xgw_guard zapret2_live\n")
    assert script.count("timeout 240s") == 2
    assert "bypass" not in script


def test_guard_fingerprint_ignores_only_live_lease(monkeypatch):
    monkeypatch.setattr(nft, "singbox_user_uid", lambda: None)
    cfg, _, _ = setup()
    rules, _ = nft.build_rules(cfg, capture=True, time_uids=())
    text = nft.render_guard(rules)
    active = text.replace("flags timeout\n", "flags timeout\n"
                          "    elements = { 0x10000000 timeout 4m expires 3m59s,\n"
                          "                 0x50000000 timeout 4m expires 3m59s }\n")
    fingerprint = nft.structure(text, "inet", nft.GUARD)
    assert nft.structure(active, "inet", nft.GUARD) == fingerprint
    assert nft.structure(active.replace("queue num 200", "queue num 201"),
                         "inet", nft.GUARD) != fingerprint
    assert nft.structure(active.replace("flags timeout", "flags constant"),
                         "inet", nft.GUARD) != fingerprint


@pytest.mark.parametrize("spent", [-1, True, "0"])
def test_corrupt_budget_cannot_grant_probe(spent):
    h = Harness()
    h.controller.store.set_meta(z.BUDGET, json.dumps({"day": int(time.time() // 86400),
                                                   "bytes": spent}))
    assert not h.controller._budget(h.cfg)


def test_busy_queue_is_not_taken(monkeypatch):
    calls = []
    runtime = z.Runtime(lambda argv, **kw: calls.append(argv) or "inactive")
    monkeypatch.setattr(runtime, "occupied", lambda _queue: True)
    cfg, _, _ = setup()
    with pytest.raises(ValueError, match="queue_busy"):
        runtime.start(cfg)
    assert all(call[0] != "systemd-run" for call in calls)
    assert all("stop" not in call for call in calls)
