"""Durable job transitions. Real flock runs on Ubuntu; Windows checks policy logic only."""
import json
import sys
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from xgw import config, managed
from xgw.desync import client, jobs, schema
from xgw.watch import zapret2_management as management


def test_matrix_report_validates_one_job_and_two_distinct_https_rounds(tmp_path):
    profiles = list(jobs.CANDIDATES)
    rows = [{"round": n, "candidate": p, "state": "active", "transport": "https_reachable"}
            for n, sequence in ((1, profiles), (2, reversed(profiles))) for p in sequence]
    rows[0].update(state="timeout", transport="unknown")
    rows[1]["transport"] = "unknown"
    rows[0].update(reason="trial_timeout", wait_stage="nfqueue")
    rows[1].update(reason="youtube_page_probe_failed", probes={
        "page": {"ok": False, "phase": "tls", "kind": "timeout", "url": "private"}})
    job = {"id": "a" * 32, "state": "complete", "restore": "pass",
           "candidates": profiles, "rounds": 2, "results": rows}
    path = tmp_path / "status.json"
    path.write_text(json.dumps({"job": job, "secret": "private"}))
    result = client.matrix_report(path)
    assert result["ok"] and result["full_matrix"]
    assert result["states"] == {"timeout": 1, "active": 17}
    assert result["two_https_pass"] == profiles[2:]
    assert result["profiles"][profiles[0]][0]["reason"] == "trial_timeout"
    assert result["profiles"][profiles[0]][0]["wait_stage"] == "nfqueue"
    assert result["profiles"][profiles[1]][0]["probes"]["page"]["phase"] == "tls"
    assert "private" not in json.dumps(result)
    job["results"] = rows[:-1]
    path.write_text(json.dumps(job))
    assert not client.matrix_report(path)["ok"]
    job["results"] = [*rows[:-1], rows[0]]
    path.write_text(json.dumps(job))
    with pytest.raises(ValueError, match="matrix_row_or_order"):
        client.matrix_report(path)


def test_matrix_replay_ranks_from_round_one_and_measures_cost_in_round_two(
    tmp_path, monkeypatch, capsys,
):
    first, second, third, fourth = jobs.CANDIDATES[:4]
    candidates = [first, second, third, fourth]
    rows = [
        {"round": n, "candidate": candidate, "state": "active",
         "transport": "https_reachable", "elapsed_ms": cost,
         "probes": {"page": {"ok": True, "bytes": 20000}}}
        for n, names, costs in ((1, candidates, [5000, 4000, 7000, 1000]),
                                (2, reversed(candidates), [9000, 5000, 4000, 10000]))
        for candidate, cost in zip(names, costs, strict=True)
    ]
    rows[1].update(state="fallback", transport="unknown", reason="youtube_cdn_expired")
    rows[0]["probes"]["page"]["elapsed_ms"] = 210
    rows[3].update(state="fallback", transport="unknown", reason="youtube_cdn_probe_failed",
                   probes={"page": {"ok": True},
                           "cdn": {"ok": False, "phase": "body", "kind": "stall",
                                   "bytes": 16384, "elapsed_ms": 307}})
    rows[4].update(state="timeout", transport="unknown", reason="trial_timeout",
                   wait_stage="status_stale", probes={},
                   phase_ms={"policy_apply": 700, "outcome_wait": 8300, "off_confirm": 1000,
                             "worker_start": 17, "raw_args": "private_phase"})
    rows[5]["phase_ms"] = {"policy_apply": 10, "outcome_wait": 20, "off_confirm": 0,
                           "worker_start": 88}
    rows[6]["phase_ms"] = {"policy_apply": False, "outcome_wait": 4000, "off_confirm": -1,
                           "worker_start": 9999}
    rows[7].update(state="fallback", transport="unknown", reason="youtube_page_probe_failed",
                   probes={"page": {"ok": False, "phase": "tls", "kind": "timeout",
                                    "bytes": 0, "url": "private_url"}})
    job = {"id": "b" * 32, "state": "complete", "restore": "pass",
           "candidates": candidates, "rounds": 2, "results": rows}
    path = tmp_path / "saved.json"
    path.write_text(json.dumps({"job": job, "url": "private_url"}))
    report = client.matrix_replay(client.matrix_report(path))
    assert report["outcomes_by_round"] == {
        1: {"https_pass": 2, "expired_cdn_url": 1, "body_stall": 1},
        2: {"https_pass": 2, "tls_timeout": 1, "control_wait_timeout": 1},
    }
    assert report["two_https_pass"] == [third]
    assert report["timing_by_round"][1]["off_confirm"] == {"samples": 0, "total_ms": None}
    assert report["timing_by_round"][1]["page_probe"] == {"samples": 1, "total_ms": 210}
    assert report["timing_by_round"][1]["cdn_probe"] == {"samples": 1, "total_ms": 307}
    assert report["timing_by_round"][2] == {
        "attempt": {"samples": 4, "total_ms": 28000},
        "policy_apply": {"samples": 1, "total_ms": 700},
        "outcome_wait": {"samples": 1, "total_ms": 8300},
        "off_confirm": {"samples": 2, "total_ms": 1000},
        "worker_start": {"samples": 1, "total_ms": 88},
        "attempt_with_worker_start": {"samples": 1, "total_ms": 5000},
        "page_probe": {"samples": 0, "total_ms": None},
        "cdn_probe": {"samples": 0, "total_ms": None},
    }
    baseline, proposed = (report["replay"][key] for key in ("recorded", "prior_round_order"))
    assert baseline["order"] == candidates[::-1]
    assert proposed["order"] == [first, third, fourth, second]
    assert baseline["first_pass_ms"] == 14000 and proposed["first_pass_ms"] == 15000
    assert baseline["full_attempt_ms"] == proposed["full_attempt_ms"] == 28000
    assert baseline["untried_https_passes"] == proposed["untried_https_passes"] == [second]
    assert proposed["observed_probe_bytes_if_stop_after_pass"] == 20000
    assert proposed["attempts_with_byte_samples"] == 2
    assert report["endpoint_context"] == "NOT_VERIFIED" and report["apply"] is False
    assert "job_id" not in report and "private" not in json.dumps(report)

    def network_access():
        pytest.fail("offline replay must not create an HTTP client")

    monkeypatch.setattr(client, "Client", network_access)
    monkeypatch.setattr(sys, "argv", ["xgw.desync.client", "matrix", str(path), "--replay"])
    assert client.main() == 0
    assert json.loads(capsys.readouterr().out)["replay"] == report["replay"]

    del rows[7]["elapsed_ms"]
    path.write_text(json.dumps(job))
    missing = client.matrix_replay(client.matrix_report(path))["replay"]
    assert missing["prior_round_order"]["first_pass_ms"] is None
    assert missing["recorded"]["first_pass_ms"] == 14000
    assert missing["prior_round_order"]["first_pass_attempt"] == 2

    job["results"] = rows[:-1]
    path.write_text(json.dumps(job))
    partial = client.matrix_replay(client.matrix_report(path))
    assert not partial["ok"] and partial["replay"]["state"] == "two_complete_rounds_required"


def test_matrix_replay_does_not_guess_expiry_or_transport_failure_without_evidence():
    row = {"round": 1, "state": "fallback", "https_ok": False,
           "reason": "youtube_cdn_probe_failed", "probes": {}}
    assert client._matrix_outcome(row) == "probe_details_unavailable"
    for kind, phase, expected in (
        ("http", "headers", "http_or_proxy_failure"),
        ("truncated", "body", "body_interrupted"),
        ("cancelled", "request", "probe_cancelled"),
    ):
        probe = {"ok": False, "phase": phase, "kind": kind, "http": 403}
        assert client._matrix_outcome(row | {"probes": {"cdn": probe}}) == expected


@pytest.fixture
def job_store(tmp_path, monkeypatch):
    if sys.platform == "win32":
        @contextmanager
        def lock(*args, **kwargs):
            yield
        monkeypatch.setattr(jobs, "file_lock", lock)
        monkeypatch.setattr(managed, "file_lock", lock)
    path = tmp_path / "config.toml"
    path.write_text('[capture]\nlocal=true\nfail_mode="closed"\nhold="block"\n'
                    '[network]\nquic_mode="reject"\n')
    policy = schema.migrate({**schema.DEFAULTS, "youtube_transport_probe": True,
                            "domains": list(schema.YOUTUBE_DOMAINS), "probe_urls": [
                                "https://www.youtube.com/t/terms",
                                "https://r1.googlevideo.com/videoplayback?sig=private-token"]})
    managed.path_for(path).write_text(json.dumps({"desync": policy, "extension": 42}))
    def observe():
        current = config.load(path)[0]
        return {"fresh": True, "policy_matched": True,
                "config_key": schema.fingerprint(current.desync),
                "blockers": {"selective": []}, "state": (
                    "active" if current.zapret2.mode == "selective" else "off"),
                "reason": "youtube_transport_ok", "evidence": {"transport": "https_reachable",
                    "transport_probes": {"page": {"ok": True, "phase": "body", "http": 200,
                                                  "url": "private-token"}}}}
    instance = jobs.Jobs(tmp_path / "jobs", path, observe, lambda: None,
                        budget_reader=lambda cfg: management.zapret2.read_probe_budget(
                            None, cfg.zapret2.daily_probe_mb, now=0))
    monkeypatch.setattr(instance, "_launch", lambda **kw: None)
    return instance, path, policy


def start(instance, **extra):
    body = {"expected": schema.fingerprint(instance._policy()[1]), "rounds": 2,
            "candidates": ["multisplit", "multidisorder"], "budget_seconds": 1800, **extra}
    return instance.command("start", body)


def test_complete_matrix_restores_policy_and_preserves_unrelated_fields(job_store):
    instance, path, policy = job_store
    assert start(instance)["ok"]
    instance._run()
    public = instance.public()
    assert (public["state"], public["restore"]) == ("complete", "pass")
    assert [r["candidate"] for r in public["results"]] == [
        "multisplit", "multidisorder", "multidisorder", "multisplit"]
    assert instance._policy()[1] == policy
    assert json.loads(managed.path_for(path).read_text())["extension"] == 42
    assert "private-token" not in json.dumps(public)


def test_cancel_before_run_restores_and_terminal_cancel_is_rejected(job_store):
    instance, _path, policy = job_store
    assert start(instance)["ok"]
    assert instance.command("cancel", {"id": instance.public()["id"]})["ok"]
    instance._run()
    assert instance.public()["state"] == "cancelled"
    assert instance.public()["restore"] == "pass"
    assert instance._policy()[1] == policy
    assert not instance.command("cancel", {"id": instance.public()["id"]})["ok"]


@pytest.mark.parametrize("replace_first", [False, True])
def test_recovery_handles_both_sides_of_policy_commit(job_store, replace_first):
    instance, path, policy = job_store
    start(instance)
    row = instance._read()
    proposed = management.candidate(config.load(path)[0], {"mode": "selective"})[0]
    row["pending"] = schema.fingerprint(proposed)
    instance._write(row)
    if replace_first:
        instance._replace(row["expected"], proposed)
    instance._run(recovery=True)
    assert instance.public()["state"] == "interrupted"
    assert instance.public()["restore"] == "pass"
    assert instance._policy()[1] == policy


def test_recovery_after_restore_commit_is_idempotent(job_store):
    instance, _path, policy = job_store
    start(instance)
    row = instance._read()
    instance._transition(row, {"mode": "selective"})
    row["pending"] = schema.fingerprint(policy)
    row["state"] = "restoring"
    instance._write(row)
    instance._replace(row["expected"], policy)
    instance._run(recovery=True)
    assert instance.public()["restore"] == "pass"


def test_external_change_is_never_overwritten(job_store, monkeypatch):
    instance, path, _policy = job_store
    start(instance)
    original_wait = instance._wait
    def change(row, states, deadline, **kw):
        if not kw.get("restoring"):
            cfg, current = instance._policy()
            changed = management.candidate(cfg, {"retry_seconds": 120})[0]
            instance._replace(schema.fingerprint(current), changed)
        return original_wait(row, states, deadline, **kw)
    monkeypatch.setattr(instance, "_wait", change)
    instance._run()
    assert instance.public()["restore"] == "unconfirmed"
    assert config.load(path)[0].zapret2.retry_seconds == 120


@pytest.mark.parametrize("extra", [
    {"rounds": True}, {"rounds": 3}, {"budget_seconds": 3601}, {"budget_seconds": 60},
    {"candidates": ["multisplit", "multisplit"]}, {"candidates": ["flowseal_alt9"]},
    {"candidates": [None]}, {"candidates": []}, {"extra": "private-token"},
])
def test_invalid_start_does_not_write(job_store, extra):
    instance, path, _policy = job_store
    before = managed.path_for(path).read_bytes()
    assert not start(instance, **extra)["ok"]
    assert not instance.path.exists()
    assert managed.path_for(path).read_bytes() == before


def test_pin_reset_and_changed_context_rejection(job_store):
    instance, path, policy = job_store
    start(instance)
    instance._run()
    def command(action, **extra):
        return instance.command(action, {"id": instance.public()["id"],
            "expected": schema.fingerprint(instance._policy()[1]), **extra})
    assert command("pin", candidate="multidisorder")["ok"]
    assert config.load(path)[0].zapret2.mode == "off"
    assert config.load(path)[0].zapret2.strategy == "multidisorder"
    assert command("reset")["ok"]
    assert instance._policy()[1] == policy
    cfg, current = instance._policy()
    changed = management.candidate(cfg, {"probe_urls": [
        "https://www.youtube.com/t/terms", "https://r2.googlevideo.com/generate_204"]})[0]
    instance._replace(schema.fingerprint(current), changed)
    assert command("pin", candidate="multidisorder")["code"] == "conflict"


def test_persistent_probe_drops_credentials_and_import_checks_assets(job_store, monkeypatch):
    from xgw.desync import flowseal

    instance, path, _policy = job_store
    def command(action, **extra):
        return management.command(path, action, {
            "expected": schema.fingerprint(instance._policy()[1]), **extra},
            ready=True, capture={"mode": "on"})
    assert command("probe", probe="persistent")["ok"]
    cfg = config.load(path)[0]
    assert cfg.zapret2.probe_urls[1] == "https://r1.googlevideo.com/generate_204"
    assert schema.valid_youtube_transport("selective", cfg.zapret2.domains, cfg.zapret2.probe_urls)
    assert "private-token" not in managed.path_for(path).read_text()
    def missing():
        raise ValueError("private-token")
    monkeypatch.setattr(flowseal, "live_arguments", missing)
    assert command("import", **{"import": schema.LIVE_STRATEGY})["code"] == "blocked"
    monkeypatch.setattr(flowseal, "live_arguments", lambda: [])
    assert command("import", **{"import": schema.LIVE_STRATEGY})["ok"]
    assert config.load(path)[0].zapret2.strategy == schema.LIVE_STRATEGY
    assert config.load(path)[0].zapret2.mode == "off"
    assert not command("mode", mode="selective")["ok"]


def test_monitor_whitelist_excludes_private_payload():
    row = client.observation({"servers": ["private-token"], "zapret2": {
        "probe_urls": ["private-token"], "job": {"original": "private-token"},
        "evidence": {"transport_probes": {"cdn": {"ok": True, "url": "private-token"}}}}})
    assert row["probes"]["cdn"] == {"ok": True}
    assert "private-token" not in json.dumps(row)

def test_all_nine_profiles_receive_two_rounds(job_store):
    instance, _path, policy = job_store
    assert start(instance, candidates=list(jobs.CANDIDATES), budget_seconds=3600)["ok"]
    instance._run()
    assert instance.public()["state"] == "complete"
    assert len(instance.public()["results"]) == 18
    assert instance._policy()[1] == policy


def test_monitor_analysis_preserves_gaps_and_does_not_claim_playback(tmp_path):
    path = tmp_path / "monitor.jsonl"
    rows = []
    for at, reset in [(86300, 86400), (86360, 86400), (86420, 172800), (90000, 172800)]:
        rows.append({"at": at, "fresh": True, "policy_matched": True,
                     "config_key": "same", "state": "active", "budget": {"resets_at": reset}})
    path.write_text("\n".join(json.dumps(r) for r in rows))
    result = client.analyze(path)
    assert result["utc_boundary_sample_pairs"] == 1
    assert result["confirmed_interval_seconds"] == {"active": 120}
    assert result["large_or_backward_gaps"] == 1


def test_monitor_separates_policy_from_state_and_reads_legacy_journals(tmp_path):
    first = client.observation({"zapret2": {"config_key": "a", "state": "off",
                               "fresh": True, "policy_matched": True, "mode": "off",
                               "engine_mode": "off"}})
    assert first["engine_mode"] == "off"
    legacy = dict(first)
    del legacy["engine_mode"]
    standalone = first | {"config_key": "b", "mode": "standalone", "state": "active"}
    rows = [legacy, legacy, first, first, standalone, standalone | {"state": "fallback"},
            standalone | {"fresh": False}, first | {"config_key": None},
            first | {"config_key": None}]
    path = tmp_path / "day.jsonl"
    path.write_text("\n".join(json.dumps(row | {"at": 60 * i}) for i, row in enumerate(rows)))
    stats = client.analyze(path)
    assert stats["policy_interval_seconds"] == {
        "off/unknown": 60, "off/off": 60, "standalone/off": 60, "unconfirmed": 300}
    assert stats["elapsed_seconds"] == 480


def test_corrupt_job_does_not_prevent_start(job_store):
    instance, _path, _policy = job_store
    instance.directory.mkdir()
    instance.path.write_text('{"version":1,"id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}')
    instance.recover()
    assert instance.public()["state"] == "unavailable"

def test_candidate_timeout_continues_only_after_confirmed_off(job_store, monkeypatch):
    instance, _path, policy = job_store
    assert start(instance)["ok"]
    original_wait, original_transition = instance._wait, instance._transition
    tick = 0.0
    trials = []

    def advance(seconds):
        nonlocal tick
        tick += seconds

    monkeypatch.setattr(jobs, "time", SimpleNamespace(
        monotonic=lambda: tick, time=lambda: 10000 - tick, sleep=advance,
    ))

    def transition(row, patch):
        original_transition(row, patch)
        advance(0.25 if patch["mode"] == "selective" else 0.5)

    def wait(row, states, deadline, **kwargs):
        if "active" in states:
            trials.append(instance._policy()[0].zapret2.strategy)
            if len(trials) == 1:
                advance(95)
                raise jobs.TrialTimeout("nfqueue")
            advance(4.5)
        else:
            advance(1.25)
        view = original_wait(row, states, deadline, **kwargs)
        if view["state"] == "active":
            view["evidence"]["worker_start_ms"] = 180 if len(trials) == 2 else 99999
        return view

    monkeypatch.setattr(instance, "_transition", transition)
    monkeypatch.setattr(instance, "_wait", wait)
    instance._run()
    result = instance.public()
    assert result["state"] == "complete" and result["restore"] == "pass"
    assert len(trials) == len(result["results"]) == 4
    assert result["results"][0]["state"] == "timeout"
    assert result["results"][0]["wait_stage"] == "nfqueue"
    assert result["results"][0]["elapsed_ms"] == 95250
    assert result["results"][0]["phase_ms"] == {
        "policy_apply": 250, "outcome_wait": 95000, "off_confirm": 1750,
    }
    assert result["results"][1]["phase_ms"] == {
        "policy_apply": 250, "outcome_wait": 4500, "off_confirm": 1750, "worker_start": 180,
    }
    assert "worker_start" not in result["results"][2]["phase_ms"]
    assert instance._policy()[1] == policy


def test_off_wait_failure_leaves_only_observed_phase_times(job_store, monkeypatch):
    instance, _path, policy = job_store
    assert start(instance)["ok"]
    original_wait = instance._wait

    def wait(row, states, deadline, *, restoring=False):
        if states == ("off",) and not restoring:
            raise jobs.TrialTimeout("policy_pending")
        return original_wait(row, states, deadline, restoring=restoring)

    monkeypatch.setattr(instance, "_wait", wait)
    instance._run()
    result = instance.public()
    assert (result["state"], result["restore"]) == ("failed", "pass")
    (attempt,) = result["results"]
    assert attempt["state"] == "active"
    assert set(attempt["phase_ms"]) == {"policy_apply", "outcome_wait"}
    assert sum(attempt["phase_ms"].values()) == attempt["elapsed_ms"]
    assert instance._policy()[1] == policy


def test_low_budget_rejects_job_and_stops_before_next_candidate(job_store):
    instance, _path, policy = job_store
    instance.budget_reader = lambda cfg: management.zapret2.ProbeBudget(0, 0, 262144)
    assert start(instance)["code"] == "probe_budget"
    assert not instance.path.exists()
    assert instance._policy()[1] == policy
    instance.budget_reader = lambda cfg: management.zapret2.ProbeBudget(0, 0, 786432)
    assert start(instance)["ok"]
    calls = 0
    def budget(cfg):
        nonlocal calls
        calls += 1
        return management.zapret2.ProbeBudget(0, 0, 786432 if calls == 1 else 262144)
    instance.budget_reader = budget
    instance._run()
    result = instance.public()
    assert len(result["results"]) == 1
    assert result["error"] == "probe_budget" and result["restore"] == "pass"
    assert instance._policy()[1] == policy
