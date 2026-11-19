"""Durable job transitions. Real flock runs on Ubuntu; Windows checks policy logic only."""
import json
import sys
from contextlib import contextmanager

import pytest

from xgw import config, managed
from xgw.desync import client, jobs, schema
from xgw.watch import zapret2_management as management


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


def test_corrupt_job_does_not_prevent_start(job_store):
    instance, _path, _policy = job_store
    instance.directory.mkdir()
    instance.path.write_text('{"version":1,"id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}')
    instance.recover()
    assert instance.public()["state"] == "unavailable"

def test_candidate_timeout_continues_only_after_confirmed_off(job_store, monkeypatch):
    instance, _path, policy = job_store
    assert start(instance)["ok"]
    original = instance._wait
    trials = []
    def wait(row, states, deadline, **kwargs):
        if "active" in states:
            trials.append(instance._policy()[0].zapret2.strategy)
            if len(trials) == 1:
                raise TimeoutError("trial_timeout")
        return original(row, states, deadline, **kwargs)
    monkeypatch.setattr(instance, "_wait", wait)
    instance._run()
    result = instance.public()
    assert result["state"] == "complete" and result["restore"] == "pass"
    assert len(trials) == len(result["results"]) == 4
    assert result["results"][0]["state"] == "timeout"
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
