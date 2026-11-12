"""Границы нового выхода и возврат на VPN при отказах; без скачивания nfqws2."""

import copy
import json
import time

import pytest
from test_generator import _build

from xgw import zapret2 as z
from xgw.config import load, service_ports
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
        self.slow = 0  # столько опросов после start очередь ещё не занята
        self.exits = False  # процесс завершается сразу после start

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
        return self.state(queue) == "ready"

    def state(self, queue):
        if not self.up or self.exits:
            return "dead"
        if self.slow:
            self.slow -= 1
            return "starting"
        return "ready"

    def describe(self):
        return "ActiveState=inactive Result=success"

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


def test_off_is_original_config_without_starting_anything():
    result, cfg, _ = _build()
    assert z.patch(result.config, cfg) == result.config
    runtime = Runtime()
    ctl = z.Controller(Store(), runtime)
    assert not ctl.step(cfg, result.config, 0, lambda *_: pytest.fail("apply called"))
    assert not runtime.events
    assert "zapret2.probe_port" not in service_ports(cfg)


@pytest.mark.parametrize("status,body,kind,phase,expected", [
    (204, 0, "http", "body", "empty_body"),
    (200, 25, "http", "body", "short_body"),
    (302, 0, "http", "headers", "redirect"),
    (403, 0, "http", "headers", "http_error"),
    (200, 25, "timeout", "body", "timeout"),
    (407, 0, "proxy", "connect", "proxy"),
])
def test_selective_evidence_preserves_failure_and_stops_requests(
        monkeypatch, status, body, kind, phase, expected):
    h = Harness()
    h.controller.probe = z.Controller.probe.__get__(h.controller)
    calls = []

    def request(*args, **kwargs):
        calls.append(kwargs)
        return checks.DownloadResult(False, status=status, downloaded=body, kind=kind,
                                     phase=phase, error="PRIVATE", location="PRIVATE")

    monkeypatch.setattr(checks, "http_get_via_proxy", request)
    for now in (0, 1, 2):
        h.step(now)
    assert h.controller.view["state"] == "fallback" and not z.active(h.current)
    rows = h.controller.view["probes"]
    assert [row["verdict"] for row in rows] == [expected, "not_run"]
    assert rows[0]["checked_at"] > 0 and rows[1]["checked_at"] == 0
    assert "PRIVATE" not in json.dumps(rows)
    assert len(calls) == 1 and calls[0]["min_body"] == 16384
    h.step(3)
    assert h.controller.view["probes"] == rows and len(calls) == 1


def test_selective_success_replaces_old_evidence(monkeypatch):
    h = Harness()
    h.controller.probe = z.Controller.probe.__get__(h.controller)
    monkeypatch.setattr(checks, "http_get_via_proxy", lambda *a, **kw: checks.DownloadResult(
        True, status=200, downloaded=32768, phase="body"))
    h.controller.probes = [{"verdict": "old"}]
    h.activate()
    assert [r["verdict"] for r in h.controller.view["probes"]] == ["ok", "ok"]


@pytest.mark.parametrize("query,expected", [
    ("expire=1", 1), ("expire=2000000000&token=PRIVATE", 2000000000),
    ("expire=1&expire=2", None), ("expire=no", None), ("expire=-1", None),
    ("expire=9999999999999999", None), ("token=PRIVATE", None),
])
def test_expiry_is_only_a_bounded_timestamp(query, expected):
    assert z.expiry("https://example.test/video?" + query) == expected


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
    cfg, warnings = load(path)
    assert cfg.zapret2.mode == "off"
    assert any("strategy" in w for w in warnings)
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


def test_nft_does_not_broaden_bypass_or_queue_other_traffic():
    cfg, _, _ = setup()
    rules, _ = nft.build_rules(cfg, capture=True, time_uids=())
    guard = nft.render_guard(rules)
    text = nft.render(rules)
    assert "meta mark 0x2 return" in text
    assert "meta mark and" not in "\n".join(line for line in text.splitlines() if "0x2" in line)
    assert "meta mark 0x10000000 tcp dport 443 counter queue num 200" in guard
    assert "queue num 200 bypass" not in guard
    assert "ct original packets" not in guard  # не требует nf_conntrack_acct/sysctl
    assert "meta mark 0x50000000 notrack" in guard
    output = guard.split("chain output {")[1]
    assert output.index("meta mark { 0x10000000, 0x50000000 } counter drop") < output.index(
        "jump pass")
    cfg.zapret2.mode = "off"
    rules, _ = nft.build_rules(cfg, capture=True, time_uids=())
    assert "queue num" not in nft.render_guard(rules)


def test_gate_refresh_is_atomic_and_expires():
    calls = []
    runtime = z.Runtime(lambda argv, **kw: calls.append((argv, kw)))
    runtime.gate(240)
    assert len(calls) == 1
    script = calls[0][1]["input"]
    assert script.startswith("flush set inet xgw_guard zapret2_live\n")
    assert script.count("timeout 240s") == 2
    assert "bypass" not in script


def test_guard_fingerprint_ignores_only_live_lease():
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


def test_runtime_tells_starting_from_dead_and_describes_unit_safely(monkeypatch):
    """п. 385: unit жив, а очереди ещё нет — это запуск, а не падение."""
    answers = {"is-active": "active\n", "show": (
        "ActiveState=active\nSubState=running\nResult=success\nExecMainStatus=0\n"
        "ExecStart={ path=/opt/private ; argv[]=secret }\n")}
    runtime = z.Runtime(lambda argv, **kw: answers[argv[1]])
    queue = {"busy": False}
    monkeypatch.setattr(runtime, "occupied", lambda _queue: queue["busy"])
    assert runtime.state(200) == "starting" and not runtime.alive(200)
    queue["busy"] = True
    assert runtime.state(200) == "ready" and runtime.alive(200)
    answers["is-active"] = "activating\n"
    assert runtime.state(200) == "starting"
    for word in ("inactive", "failed", "deactivating", ""):
        answers["is-active"] = word + "\n"
        assert runtime.state(200) == "dead"
    text = runtime.describe()
    assert text == "ActiveState=active SubState=running Result=success ExecMainStatus=0"
    answers["show"] = "ActiveState=bad value; rm\nResult=exit-code\n"
    assert runtime.describe() == "Result=exit-code"
