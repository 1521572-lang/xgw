"""Batch-1 status contract; no worker, Linux command, socket, or Qt is started."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from xgw.config import Config
from xgw.desync import client, schema, worker
from xgw.watch.zapret2_control import card, transport_probes

NOW = 1000

@pytest.mark.parametrize("remaining", [None, 0, 262144, 786431, 786432])
def test_selective_budget_blocker_works_before_enabling_the_mode(remaining):
    cfg, snap = fixture(engine="off", state="off")
    cfg.zapret2.youtube_transport_probe = True
    cfg.zapret2.domains = list(schema.YOUTUBE_DOMAINS)
    cfg.zapret2.probe_urls = ["https://www.youtube.com/t/terms",
                             "https://r1.googlevideo.com/generate_204"]
    cfg.desync = schema.migrate(vars(cfg.zapret2))
    snap["zapret2_policy_key"] = schema.fingerprint(cfg.desync)
    budget = None if remaining is None else {"remaining_bytes": remaining}
    result = view(cfg, snap, probe_budget=budget)
    assert bool(result["blockers"]["selective"]) is (remaining != 786432)


def test_imported_alt9_is_retained_but_not_offered_as_an_ordinary_choice():
    cfg, snap = fixture(engine="off", state="off")
    cfg.zapret2.strategy = schema.LIVE_STRATEGY
    cfg.zapret2.domains = list(schema.YOUTUBE_DOMAINS)
    cfg.desync = schema.migrate(vars(cfg.zapret2))
    snap["zapret2_policy_key"] = schema.fingerprint(cfg.desync)
    result = view(cfg, snap)
    assert result["selected_strategy"] == schema.LIVE_STRATEGY
    assert schema.LIVE_STRATEGY not in result["strategies"]
    assert not result["blockers"]["standalone"]
    assert result["blockers"]["selective"]


@pytest.mark.parametrize("mode", ["off", "standalone"])
def test_alt9_view_exposes_saved_exclusions_with_edit_capability_only_while_off(mode):
    cfg, snap = fixture(mode=mode, engine="off", state="off")
    cfg.zapret2.strategy = schema.LIVE_STRATEGY
    cfg.zapret2.flowseal_exclude_domains = ["sample.googlevideo.com"]
    cfg.desync = schema.migrate(vars(cfg.zapret2))
    snap["zapret2_policy_key"] = schema.fingerprint(cfg.desync)
    result = view(cfg, snap)
    assert result["flowseal_exclude_domains"] == ["sample.googlevideo.com"]
    assert result["can_edit_flowseal_exclusions"] is (mode == "off")



def fixture(*, mode="off", engine="auto", state="active", reason="", **extra):
    cfg = Config()
    cfg.zapret2.mode, cfg.zapret2.engine = mode, engine
    cfg.desync = schema.migrate(vars(cfg.zapret2))
    raw = {"state": state, "reason": reason, "profile": "hostfakesplit-md5", "queue": 200,
           **extra}
    snapshot = {"updated": NOW, "daemon": True, "capture": {"loaded": True, "nfqws2": raw},
                "zapret2": raw if mode != "off" else {"state": "off"},
                "zapret2_policy_key": schema.fingerprint(cfg.desync)}
    return cfg, snapshot


def view(cfg, snapshot, **kwargs):
    return card(cfg, snapshot, {"mode": "on"}, True, now=NOW, **kwargs)


def test_youtube_transport_is_never_reported_as_playback():
    cfg, snap = fixture(mode="selective", engine="off", reason="youtube_transport_ok",
                        valid_until=NOW + 60)
    cfg.zapret2.youtube_transport_probe = True
    cfg.desync = schema.migrate(vars(cfg.zapret2))
    snap["zapret2_policy_key"] = schema.fingerprint(cfg.desync)
    snap["zapret2"]["last_transport_ok_at"] = NOW - 1
    result = view(cfg, snap)
    assert result["evidence"]["transport"] == "https_reachable"
    assert result["evidence"]["playback"] == "not_tested"
    assert result["evidence"]["last_transport_ok_at"] == NOW - 1
    snap["zapret2"]["valid_until"] = NOW
    assert view(cfg, snap)["evidence"]["transport"] == "unknown"
    snap["zapret2_policy_key"] = "previous"
    assert view(cfg, snap)["evidence"]["last_transport_ok_at"] is None


@pytest.mark.parametrize(("path", "http", "written", "expected"), [
    ("videoplayback", 206, True, True),
    ("videoplayback", 206, None, None),
    ("videoplayback", 206, "true", None),
    ("videoplayback", 200, True, False),
    ("generate_204", 204, None, None),
    ("generate_204", 206, True, None),
])
def test_cdn_range_proof_is_explicit_and_revision_bound(path, http, written, expected):
    cfg, snap = fixture(mode="selective", engine="off", reason="youtube_transport_ok",
                        valid_until=NOW + 60)
    cfg.zapret2.youtube_transport_probe = True
    cfg.zapret2.probe_urls = ["https://www.youtube.com/t/terms",
                             f"https://r1.googlevideo.com/{path}"]
    cfg.desync = schema.migrate(vars(cfg.zapret2))
    snap["zapret2_policy_key"] = schema.fingerprint(cfg.desync)
    snap["zapret2"]["transport_probes"] = {
        "page": {"ok": True},
        "cdn": {"ok": True, "phase": "body", "http": http, "bytes": 65536,
                "range_verified": written, "content-range": "private-header"},
    }
    result = view(cfg, snap)
    assert result["evidence"]["playback"] == "not_tested"
    assert result["evidence"]["transport_probes"]["cdn"].get("range_verified") is expected
    assert ("проверочный диапазон" in result["detail"]) is (expected is True)
    assert ("служебный адрес" in result["detail"]) is (path == "generate_204")
    assert "private-header" not in json.dumps(result)
    snap["zapret2_policy_key"] = "previous"
    assert not view(cfg, snap)["evidence"]["transport_probes"]


@pytest.mark.parametrize(("phase", "reason"), [
    ("pending", "route_reconcile"), ("unknown", "route_unconfirmed"),
])
def test_route_status_does_not_report_https_ready(phase, reason):
    cfg, snap = fixture(mode="selective", engine="off", state=phase, reason=reason)
    result = view(cfg, snap)
    assert (result["state"], result["reason"]) == (phase, reason)
    assert result["evidence"]["transport"] == "unknown"


def test_cdn_expiry_exposes_only_deadline_and_blocks_selective():
    cfg, snap = fixture(engine="off")
    cfg.zapret2.youtube_transport_probe = True
    cfg.zapret2.probe_urls = ["https://www.youtube.com/t/terms",
                             "https://r1.googlevideo.com/videoplayback?expire=1000&sig=private"]
    cfg.desync = schema.migrate(vars(cfg.zapret2))
    result = view(cfg, snap)
    assert result["probe_expiry"] == [{"probe": 2, "expires_at": 1000}]
    assert result["can_replace_cdn_probe"] is True
    assert any("Истёк срок" in part for part in result["blockers"]["selective"])
    assert "sig=private" not in json.dumps(result)
    assert "r1.googlevideo.com" not in json.dumps(result)
    cfg.zapret2.youtube_transport_probe = False
    cfg.desync = schema.migrate(vars(cfg.zapret2))
    assert view(cfg, snap)["can_replace_cdn_probe"] is True
    cfg.zapret2.probe_urls = []
    cfg.desync = schema.migrate(vars(cfg.zapret2))
    assert view(cfg, snap)["can_replace_cdn_probe"] is False


def test_monitor_tracks_cdn_expiry_from_panel_without_leaking_probe(tmp_path, monkeypatch):
    expiry = NOW + 20
    cfg, snap = fixture(mode="selective", engine="off", reason="youtube_transport_ok",
                        valid_until=expiry)
    cfg.zapret2.youtube_transport_probe = True
    cfg.zapret2.probe_urls = ["https://www.youtube.com/t/terms",
                             f"https://r1.googlevideo.com/videoplayback?expire={expiry}&sig=private"]
    cfg.desync = schema.migrate(vars(cfg.zapret2))
    snap["zapret2_policy_key"] = schema.fingerprint(cfg.desync)
    clock = SimpleNamespace(elapsed=0)

    def sleep(seconds):
        clock.elapsed += seconds

    time_api = client.time
    monkeypatch.setattr(client, "time", SimpleNamespace(
        time=lambda: NOW + clock.elapsed, monotonic=lambda: clock.elapsed, sleep=sleep,
        strftime=time_api.strftime, gmtime=time_api.gmtime))

    def panel_request(path):
        assert path == "/api/state"
        if clock.elapsed >= 45:
            snap["updated"] = NOW + 42
            snap["zapret2"].update(state="fallback", gate_closed=True, reason="youtube_cdn_expired")
        return {"zapret2": card(cfg, snap, {"mode": "on"}, True, now=NOW + clock.elapsed)}

    journal = tmp_path / "expiry.jsonl"
    result = client.monitor(SimpleNamespace(request=panel_request), journal, seconds=60, interval=15)
    assert result["samples"] == 5
    raw = journal.read_text(encoding="utf-8")
    assert "sig=private" not in raw and "r1.googlevideo.com" not in raw
    assert all(row["cdn_expires_at"] == expiry for row in map(json.loads, raw.splitlines()))
    summary = client.analyze(journal)["cdn_expiry"]
    assert summary["observed_crossings"] == summary["crossings_with_post_expiry_status"] == 1
    assert summary["confirmed_expiry_reactions"] == {"fallback": 1}


@pytest.mark.parametrize("expiry", [None, "1020", True, -1, 253402300800])
def test_monitor_ignores_missing_or_malformed_cdn_deadline(expiry):
    observation = client.observation({"zapret2": {
        "mode": "selective", "probe_expiry": [{"probe": 2, "expires_at": expiry}],
    }})
    assert "cdn_expires_at" not in observation and "observed_at" not in observation


def test_transport_probe_details_are_private_and_revision_bound():
    cfg, snap = fixture(mode="selective", engine="off", state="fallback",
                        reason="youtube_page_probe_failed", gate_closed=True)
    cfg.zapret2.youtube_transport_probe = True
    cfg.zapret2.probe_urls = ["https://www.youtube.com/t/terms?secret-token"]
    cfg.desync = schema.migrate(vars(cfg.zapret2))
    snap["zapret2_policy_key"] = schema.fingerprint(cfg.desync)
    snap["zapret2"]["transport_probes"] = {
        "page": {"ok": False, "phase": "tls", "kind": "timeout", "connect_http": 0,
                 "page_kind": "terms", "started_at": NOW - 5,
                 "http": 0, "bytes": 0, "elapsed_ms": 4974, "url": "secret-token"},
        "cdn": {"ok": True, "phase": "body"},
    }
    evidence = view(cfg, snap)["evidence"]
    assert view(cfg, snap)["youtube_probe_page_kind"] == "terms"
    assert set(evidence["transport_probes"]) == {"page"}
    assert evidence["transport_probes"]["page"]["elapsed_ms"] == 4974
    assert evidence["transport_probes"]["page"]["page_kind"] == "terms"
    assert evidence["transport_probes"]["page"]["started_at"] == NOW - 5
    assert evidence["transport"] == "unknown" and evidence["playback"] == "not_tested"
    assert "secret" not in json.dumps(evidence)
    snap["zapret2"]["transport_probes"]["page"].update(
        phase="unexpected-private-value", page_kind="secret-token", started_at=NOW + 1)
    filtered = view(cfg, snap)["evidence"]["transport_probes"]["page"]
    assert all(filtered[field] is None for field in ("phase", "page_kind", "started_at"))
    snap["zapret2_policy_key"] = "previous"
    assert view(cfg, snap)["evidence"]["transport_probes"] == {}


@pytest.mark.parametrize(("first", "visible"), [(10000, True), (10501, False), ("secret", False)])
def test_cdn_retry_diagnostic_is_bounded(first, visible):
    rows = transport_probes({
        "page": {"ok": True, "elapsed_ms": 10001, "first_tls_timeout_ms": 10000},
        "cdn": {"ok": True, "elapsed_ms": 10500, "first_tls_timeout_ms": first},
    }, now=NOW)
    assert "first_tls_timeout_ms" not in rows["page"]
    assert ("first_tls_timeout_ms" in rows["cdn"]) is visible
    if visible:
        assert rows["cdn"]["first_tls_timeout_ms"] == first


@pytest.mark.parametrize(("state", "reason", "expected"), [
    ("active", "", "active"), ("off", "not_found", "absent"),
    ("fallback", "worker_down", "error"), ("fallback", "queue_busy", "error"),
    ("fallback", "conntrack_accounting_required", "error"),
    ("off", "inactive", "off"), ("preparing", "", "preparing"),
])
def test_engine_states(state, reason, expected):
    cfg, snap = fixture(state=state, reason=reason)
    result = view(cfg, snap)
    assert result["state"] == expected
    assert result["source"] == "engine"
    if reason == "conntrack_accounting_required":
        assert reason == result["reason"]
        assert "nf_conntrack_acct=1" in result["detail"]
    assert "восстановлен" not in result["title"].lower()
    assert result["state"] != "fallback"
    assert result["without_vpn"] is False
    assert result["evidence"]["playback"] == "not_tested"
    assert result["can_off"] and result["can_edit"]
    assert result["blockers"]["compare"]
    assert all(value is None for value in result["counters"].values())


@pytest.mark.parametrize("mode", ["off", "selective"])
def test_losses_are_fresh_and_bound_to_the_active_policy_and_generation(mode, monkeypatch):
    monkeypatch.setattr(worker.time, "time", lambda: NOW)
    cfg, snap = fixture(mode=mode, valid_until=NOW + 60)
    slot = worker.WorkerSlot()
    unit = worker.ENGINE_UNIT if mode == "off" else worker.SELECTED_UNIT
    queue = 200 if mode == "off" else cfg.zapret2.queue_num
    lease = slot.reserve(unit, queue, policy_key=snap["zapret2_policy_key"])
    snap["zapret2_reservation"] = {"unit": unit, "queue": queue, "generation": lease.generation}
    slot.observe_owner(lease, True, worker.QueueOwner("socket:[1111]", (0, 4, 24)))
    history = slot.snapshot()[1]
    snap["zapret2_worker_events"] = history
    result = view(cfg, snap)
    keys = ("queue_overflow", "queue_netlink_dropped", "queue_dropped")
    assert [result["counters"][name] for name in keys] == [0, 4, 4]
    assert "socket:[" not in json.dumps(result)

    sample = history["queue_counters"]
    item = history["events"][-1]
    for target, field, value in (
        (sample, "at", NOW - 91), (sample, "netlink", False),
        (snap["zapret2_reservation"], "generation", 2),
        (snap["zapret2_reservation"], "queue", queue + 1),
        (item, "policy_key", None), (item, "phase", "owner_unverified"),
        (snap, "zapret2_policy_key", "previous"),
    ):
        original = target[field]
        target[field] = value
        assert [view(cfg, snap)["counters"][name] for name in keys] == [None] * 3
        target[field] = original

    del snap["zapret2_worker_events"]
    assert all(view(cfg, snap)["counters"][name] is None for name in keys)


def test_off_and_unconfirmed_stop():
    cfg, snap = fixture(engine="off", state="off")
    assert view(cfg, snap)["state"] == "off"
    snap["capture"]["nfqws2"]["state"] = "active"
    assert view(cfg, snap)["state"] == "pending"


def test_startup_value_requires_the_current_active_worker_and_policy(monkeypatch):
    monkeypatch.setattr(worker.time, "monotonic_ns", Mock(side_effect=[0, 475_000_000]))
    cfg, snap = fixture(mode="selective", engine="off", valid_until=NOW + 60)
    slot = worker.WorkerSlot()
    lease = slot.reserve(worker.SELECTED_UNIT, cfg.zapret2.queue_num,
                         policy_key=snap["zapret2_policy_key"])
    reservation = {"unit": lease.unit, "queue": lease.queue, "generation": lease.generation}
    snap["zapret2_reservation"] = reservation

    def elapsed():
        return view(cfg, snap)["evidence"]["worker_start_ms"]

    snap["zapret2_worker_events"] = slot.snapshot()[1]
    assert elapsed() is None
    slot.observe_owner(lease, True)
    history = slot.snapshot()[1]
    snap["zapret2_worker_events"] = history
    assert elapsed() == 475
    for target, field, value in (
        (reservation, "unit", worker.ENGINE_UNIT), (reservation, "generation", 2),
        (history["startup"], "queue", lease.queue + 1), (history["startup"], "generation", True),
        (history["startup"], "policy_key", None), (history["startup"], "elapsed_ms", -1),
        (snap, "updated", NOW - 120), (snap["zapret2"], "state", "fallback"),
    ):
        original = target[field]
        target[field] = value
        assert elapsed() is None
        target[field] = original
    slot.observe_owner(lease, False)
    snap["zapret2_worker_events"] = slot.snapshot()[1]
    assert elapsed() is None


@pytest.mark.parametrize("stamp", [None, True, NOW - 91, NOW + 1, float("nan")])
def test_stale_or_invalid_snapshot_clears_active_profile(stamp):
    cfg, snap = fixture()
    snap["updated"] = stamp
    result = view(cfg, snap)
    assert result["state"] == "unknown" and not result["fresh"]
    assert result["strategy"] is None and result["worker"]["profile"] is None


def test_changed_policy_and_legacy_snapshot():
    cfg, snap = fixture()
    snap["zapret2_policy_key"] = "previous"
    assert view(cfg, snap)["state"] == "pending"
    del snap["zapret2_policy_key"]
    assert view(cfg, snap)["reason"] == "legacy_snapshot"
    assert card(cfg, snap, {"mode": "on"}, False, now=NOW)["fresh"] is False


def test_capture_must_be_confirmed():
    cfg, snap = fixture()
    snap["capture"]["loaded"] = False
    assert view(cfg, snap)["reason"] == "capture_unconfirmed"


def test_selected_controller_has_precedence_and_checks_expiry():
    cfg, snap = fixture(mode="selective", valid_until=NOW + 60)
    assert view(cfg, snap)["source"] == "selected"
    assert view(cfg, snap)["state"] == "active"
    snap["zapret2"]["valid_until"] = NOW
    assert view(cfg, snap)["reason"] == "expired"


def test_selected_fallback_requires_gate_and_never_asserts_vpn_health():
    cfg, snap = fixture(mode="selective", state="fallback", gate_closed=True)
    assert view(cfg, snap)["state"] == "fallback"
    assert "проверяется отдельно" in view(cfg, snap)["detail"]
    snap["zapret2"]["gate_closed"] = False
    assert view(cfg, snap)["state"] == "blocked"
    assert "Возврат маршрута не подтверждён" in view(cfg, snap)["detail"]


def test_fallback_evidence_is_policy_bound_and_keeps_the_original_probe_time():
    cfg, snap = fixture(mode="selective", state="fallback", gate_closed=True,
                        vpn_control="not_run", vpn_control_reason="no_vpn_probe_port",
                        vpn_control_at=NOW - 120)
    result = view(cfg, snap)["evidence"]
    assert result["vpn_control_reason"] == "no_vpn_probe_port"
    assert result["vpn_control_at"] == NOW - 120
    snap["zapret2"].update(vpn_control_reason="secret-token")
    assert view(cfg, snap)["evidence"]["vpn_control_reason"] is None
    snap["zapret2"].update(vpn_control="pass", vpn_control_reason="ok")
    assert view(cfg, snap)["evidence"]["vpn_control"] == "pass"
    snap["zapret2_policy_key"] = "previous"
    assert view(cfg, snap)["evidence"]["vpn_control"] == "not_run"
    assert view(cfg, snap)["evidence"]["vpn_control_at"] is None


@pytest.mark.parametrize(("reason", "probe", "failure", "expected"), [
    ("youtube_page_probe_failed", "page",
     {"phase": "tls", "kind": "timeout"}, "Проба CDN не запускалась"),
    ("youtube_cdn_probe_failed", "cdn",
     {"phase": "tls", "kind": "timeout", "first_tls_timeout_ms": 10000,
      "elapsed_ms": 20100}, "Повтор тоже завершился таймаутом"),
    ("youtube_cdn_probe_failed", "cdn",
     {"phase": "headers", "kind": "http", "http": 403}, "CDN вернул HTTP 403"),
    ("youtube_cdn_probe_failed", "cdn",
     {"phase": "headers", "kind": "range", "http": 200}, "не подтвердила полный диапазон"),
    ("youtube_cdn_probe_failed", "cdn",
     {"phase": "body", "kind": "truncated", "http": 206}, "не подтвердила полный диапазон"),
])
def test_transport_failure_detail_uses_only_current_probe(reason, probe, failure, expected):
    cfg, snap = fixture(mode="selective", engine="off", state="fallback", reason=reason,
                        gate_closed=True, vpn_control="pass", vpn_control_reason="ok",
                        vpn_control_at=NOW - 5)
    cfg.zapret2.youtube_transport_probe = True
    cfg.desync = schema.migrate(vars(cfg.zapret2))
    snap["zapret2_policy_key"] = schema.fingerprint(cfg.desync)
    snap["zapret2"]["transport_probes"] = {
        "page": {"ok": True}, probe: dict(failure, ok=False, url="private signed URL"),
    }
    detail = view(cfg, snap)["detail"]
    assert expected in detail and "Свежая контрольная проба через VPN прошла" in detail
    assert "private" not in detail
    snap["zapret2"]["gate_closed"] = False
    detail = view(cfg, snap)["detail"]
    assert expected in detail and "Контроллер снял" not in detail and "VPN прошла" not in detail
    snap["zapret2_policy_key"] = "previous"
    assert expected not in view(cfg, snap)["detail"]


def test_fallback_reports_same_cdn_control_only_for_the_current_revision():
    cfg, snap = fixture(mode="selective", engine="off", state="fallback", gate_closed=True,
                        reason="youtube_cdn_probe_failed", vpn_control="pass",
                        vpn_control_reason="ok", vpn_control_target="cdn", vpn_control_at=NOW - 5)
    result = view(cfg, snap)
    assert result["evidence"]["vpn_control_target"] == "cdn"
    assert "Тот же пробный URL CDN ответил через VPN" in result["detail"]
    snap["zapret2"]["vpn_control_at"] = NOW - 120
    assert "CDN ответил через VPN" not in view(cfg, snap)["detail"]
    snap["zapret2_policy_key"] = "previous"
    assert view(cfg, snap)["evidence"]["vpn_control_target"] is None


def test_vpn_retry_keeps_both_attempts_and_filters_private_details():
    cfg, snap = fixture(mode="selective", engine="off", state="fallback", gate_closed=True,
                        vpn_control="pass", vpn_control_target="cdn",
                        vpn_control_reason="ok", vpn_control_at=NOW - 1)
    snap["zapret2"]["vpn_control_attempts"] = [
        {"verdict": "fail", "reason": "request_failed", "at": NOW - 35, "phase": "tls",
         "kind": "timeout", "error": "private URL"},
        {"verdict": "pass", "reason": "ok", "at": NOW - 1, "phase": "body",
         "http": 206, "bytes": 65536},
    ]
    result = view(cfg, snap)
    rows = result["evidence"]["vpn_control_attempts"]
    assert [(row["verdict"], row["phase"]) for row in rows] == [("fail", "tls"), ("pass", "body")]
    assert rows[1]["http"] == 206 and rows[1]["bytes"] == 65536
    assert "private" not in json.dumps(result)
    assert "Повторная проба" in result["detail"]
    snap["zapret2_policy_key"] = "previous"
    assert view(cfg, snap)["evidence"]["vpn_control_attempts"] == []


def test_vpn_redirect_card_reports_final_range_without_location():
    cfg, snap = fixture(mode="selective", engine="off", state="fallback", gate_closed=True,
                        vpn_control="pass", vpn_control_target="cdn",
                        vpn_control_reason="ok", vpn_control_at=NOW - 1)
    snap["zapret2"]["vpn_control_attempts"] = [{
        "verdict": "pass", "reason": "ok", "at": NOW - 1, "phase": "body", "kind": "ok",
        "http": 206, "bytes": 65536, "range_verified": True,
        "redirect": {"http": 302, "state": "followed", "host_changed": True,
                     "location": "private"},
    }]
    result = view(cfg, snap)
    row, = result["evidence"]["vpn_control_attempts"]
    assert row["redirect"] == {"http": 302, "state": "followed", "host_changed": True}
    assert row["http"] == 206
    assert row["range_verified"] is True
    assert "private" not in json.dumps(result)
    assert "после перенаправления" in result["detail"]
    assert "Диапазон CDN через VPN подтверждён" in result["detail"]


def test_private_and_untrusted_fields_are_not_published():
    cfg, snap = fixture(reason="secret-in-error", profile="secret-profile", queue="secret")
    snap["capture"]["nfqws2"]["probes"] = [{"url": "secret-token"}]
    cfg.desync["selected"]["probe_urls"] = ["https://youtube.com/?secret-token"]
    snap["zapret2_policy_key"] = schema.fingerprint(cfg.desync)
    result = view(cfg, snap)
    assert "secret" not in json.dumps(result)
    assert result["worker"]["profile"] is None


def test_panel_state_wires_card_to_real_response(tmp_path, monkeypatch):
    from xgw.watch import panel

    cfg, snap = fixture(state="fallback", reason="worker_down")
    monkeypatch.setattr(panel.time, "time", lambda: NOW)
    p = Mock()
    p.cfg, p.paths.cache_dir = cfg, tmp_path
    p._core.return_value = snap, True, [], []
    p._capture.return_value.describe.return_value = {"mode": "on", "lan_if": ""}
    p._servers.return_value = [], []
    p._devices.return_value = []
    p._db.return_value = []
    p._probe_budget.side_effect = lambda *args: panel.Panel._probe_budget(p, *args)
    p.desync_jobs.public.return_value = {"state": "idle"}
    p._zapret2_card.side_effect = lambda *args: panel.Panel._zapret2_card(p, *args)
    p.daemon.speed_one_pending.return_value = []
    for field in ("refresh_pending", "scan_pending", "speed_pending", "cores_pending"):
        setattr(p.daemon, field, False)
    for method in ("_power", "_pin", "_cores_card", "_netcheck_card", "_tailscale_card",
                   "_phones_card"):
        getattr(p, method).return_value = {}
    p.recorder.state.return_value = {}
    result = panel.Panel.state(p)
    assert result["zapret2"]["state"] == "error"
    assert result["zapret2"]["probe_budget"] is None
    p._db.side_effect = lambda query, *_args: (
        [{"value": '{"day": 0, "bytes": 262144}'}] if "FROM meta" in query else []
    )
    budget = panel.Panel.state(p)["zapret2"]["probe_budget"]
    assert budget["spent_bytes"] == 256 * 1024 and budget["resets_at"] == 86400
    assert budget["remaining_bytes"] == budget["limit_bytes"] - budget["spent_bytes"]
    assert result["zapret2"]["source"] == "engine"
    json.dumps(result)  # response must be serializable, not a mock or private object


def test_overview_renders_new_states_and_expired_daemon():
    file = Path(__file__).parents[1] / "vpn_ui" / "xgw" / "overview.py"
    spec = importlib.util.spec_from_file_location("batch1_overview", file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        for phase, label in (("error", "Ошибка обработчика"), ("absent", "Не установлен"),
                             ("fallback", "Прямой путь отключён")):
            assert module.zapret_status({"zapret2": {"state": phase}}, False).text == label
        result = module.zapret_status({"zapret2": {"state": "active", "fresh": False}}, False)
        assert result.tone == "warn" and result.text == "Не подтверждён"
    finally:
        sys.modules.pop(spec.name, None)
