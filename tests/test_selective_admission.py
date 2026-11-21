"""Contract checks for the Selective acceptance helper. No live requests."""
from types import SimpleNamespace

import pytest

from docs.helpers import selective_admission as trial


def active(at, *, http=206, size=65536):
    return {
        "mode": "selective", "state": "active",
        "evidence": {"transport": "https_reachable", "last_transport_ok_at": at,
                     "transport_probes": {"cdn": {"ok": True, "http": http, "bytes": size}}},
    }


@pytest.mark.parametrize(("samples", "result"), [
    ([active(110), active(110), active(170)], 0),
    ([active(110), active(110)], 2),
    ([active(110), active(170, http=200)], 2),
    ([active(99), active(110)], 2),
])
def test_two_checks_require_distinct_fresh_range_results(monkeypatch, samples, result):
    monkeypatch.setattr(trial, "observations", lambda *_args: iter(samples))
    monkeypatch.setattr(trial.time, "time", lambda: 180)
    assert trial.observe_admission(None, "revision", 2, 100, 180) == result


def test_late_recovery_after_fallback_does_not_qualify_original_trial(monkeypatch):
    fallback = {
        "mode": "selective", "state": "fallback", "reason": "youtube_cdn_probe_failed",
        "evidence": {"vpn_control_retry_pending": True, "transport_probes": {}},
    }
    monkeypatch.setattr(trial, "observations", lambda *_args: iter([fallback, active(170)]))
    assert trial.observe_admission(None, "revision", 1, 100, 180) == 2


@pytest.mark.parametrize(("next_sample", "expected"), [(None, 0), (160, 2)])
def test_base_observes_only_one_watchdog_recovery(monkeypatch, next_sample, expected):
    def fallback(at):
        return {
            "mode": "selective", "state": "fallback", "reason": "youtube_cdn_probe_failed",
            "evidence": {"transport_probes": {
                "cdn": {"started_at": at, "phase": "tls", "kind": "timeout"},
            }},
        }

    samples = [active(105), fallback(110), fallback(110)]
    if next_sample is not None:
        samples.append(fallback(next_sample))
    samples += [active(170), active(230)]
    monkeypatch.setattr(trial, "observations", lambda *_args: iter(samples))
    monkeypatch.setattr(trial.time, "time", lambda: 240)
    assert trial.observe_admission(None, "revision", 2, 100, 360,
                                   recover_cdn_once=True) == expected


def test_admit_posts_once_and_records_the_policy_revision(tmp_path, monkeypatch):
    initial = {"mode": "off", "engine_mode": "off", "state": "off", "fresh": True,
               "policy_matched": True, "config_key": "off-key", "youtube_transport_probe": True,
               "blockers": {"selective": []}}
    calls = []

    def request(path, body=None):
        calls.append((path, body))
        if body is None:
            return {"zapret2": initial}
        return {"ok": True, "config_key": "selective-key"}

    client = SimpleNamespace(request=request)
    args = SimpleNamespace(receipt=tmp_path / "receipt", format=None, checks=2, timeout=180,
                           recover_cdn_once=False)
    monkeypatch.setattr(trial, "observe_admission", lambda *_args, **_kwargs: 0)
    assert trial.activate(client, args) == 0
    assert args.receipt.read_text().strip() == "selective-key"
    with pytest.raises(FileExistsError):
        trial.activate(client, args)
    assert [entry for entry in calls if entry[0] == trial.MODE] == [
        (trial.MODE, {"expected": "off-key", "mode": "selective"}),
    ]


def test_off_never_posts_against_changed_policy(tmp_path):
    receipt = tmp_path / "receipt"
    receipt.write_text("observed-key\n")

    def request(path, body=None):
        assert path == trial.OVERVIEW and body is None
        return {"zapret2": {"config_key": "other-key", "mode": "selective"}}

    with pytest.raises(trial.TrialError, match="policy_changed"):
        trial.disable(SimpleNamespace(request=request), receipt)
