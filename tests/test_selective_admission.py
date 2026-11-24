"""Contract checks for the Selective acceptance helper. No live requests."""
from ipaddress import IPv4Address
from types import SimpleNamespace

import pytest

from docs.helpers import headless_playback
from docs.helpers import selective_admission as trial


def active(at, *, started=None, http=206, size=65536, proof=True):
    started = at - 1 if started is None else started
    return {
        "mode": "selective", "state": "active",
        "evidence": {"transport": "https_reachable", "last_transport_ok_at": at,
                     "transport_probes": {"cdn": {"ok": True, "http": http, "bytes": size,
                                                   "range_verified": proof, "started_at": started}}},
    }


@pytest.mark.parametrize(("samples", "result"), [
    ([active(110), active(110), active(170)], 0),
    ([active(110), active(110)], 2),
    ([active(110), active(170, http=200)], 2),
    ([active(110), active(170, proof=None)], 2),
    ([active(110), active(170, proof=False)], 2),
    ([active(110), active(170, started=109)], 2),
    ([active(110), active(170, started=110)], 2),
    ([active(110), active(170, started=171)], 2),
    ([active(110), active(150, started=109), active(170)], 0),
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


@pytest.mark.parametrize("strategy", ["multisplit", "fake_md5"])
def test_standalone_uses_a_confirmed_revision_and_can_restore_off(tmp_path, monkeypatch, strategy):
    card = {"mode": "off", "state": "off", "engine_mode": "off", "fresh": True,
            "policy_matched": True, "config_key": "initial", "blockers": {"standalone": []}}
    calls = []
    receipt = tmp_path / "standalone"

    def request(path, body=None):
        if body is None:
            return {"zapret2": card}
        assert receipt.exists()
        assert body["expected"] == card["config_key"]
        calls.append((path, body))
        if path.endswith("/settings"):
            assert body["settings"]["youtube_transport_probe"] is False
            assert body["settings"]["strategy"] == strategy
            card["config_key"] = "settings"
        else:
            mode = body["mode"]
            card.update(mode=mode, state="active" if mode == "standalone" else "off",
                        without_vpn=True, config_key=mode)
        return {"ok": True, "config_key": card["config_key"]}

    def observations(_client, key, _deadline):
        assert card["config_key"] == key
        if key == "standalone":
            yield {**card, "state": "blocked", "reason": "vpn_stopping", "without_vpn": False}
            yield {**card, "state": "preparing", "reason": "nfqueue", "without_vpn": False}
        yield card.copy()

    monkeypatch.setattr(trial, "observations", observations)
    client = SimpleNamespace(request=request)
    assert trial.start_standalone(client, receipt, strategy=strategy) == 0
    assert receipt.read_text().strip() == "standalone"
    assert trial.check_standalone(client, receipt) == 0
    card["without_vpn"] = False
    with pytest.raises(trial.TrialError, match="standalone_not_confirmed"):
        trial.check_standalone(client, receipt)
    assert trial.disable(client, receipt) == 0
    assert [body.get("mode") for _, body in calls] == [None, "standalone", "off"]


def test_standalone_reports_a_terminal_blocker_instead_of_waiting(tmp_path, monkeypatch, capsys):
    card = {"mode": "off", "state": "off", "engine_mode": "off", "fresh": True,
            "policy_matched": True, "config_key": "initial", "blockers": {"standalone": []}}
    monkeypatch.setattr(trial, "overview", lambda _client: card)
    monkeypatch.setattr(trial, "wait_off", lambda _client, _key: card)
    monkeypatch.setattr(trial, "update", lambda *_a, **_kw: "new-key")

    def observations(*_a):
        yield {**card, "mode": "standalone", "state": "blocked", "reason": "queue_busy"}
        pytest.fail("a terminal block must stop admission")

    monkeypatch.setattr(trial, "observations", observations)
    with pytest.raises(trial.TrialError, match="standalone_not_ready"):
        trial.start_standalone(None, tmp_path / "receipt")
    assert "queue_busy" in capsys.readouterr().out


@pytest.mark.parametrize(("first_override", "pinned_override", "state", "pinned"), [
    ({}, {}, "pass", True),
    ({"status": 200}, {}, "initial_range_failed", False),
    ({"remote_ip": "127.0.0.1"}, {}, "peer_unconfirmed", False),
    ({}, {"remote_ip": "8.8.8.8"}, "pinned_range_unconfirmed", True),
    ({}, {"bytes": 32768}, "pinned_range_unconfirmed", True),
])
def test_probe_pair_requires_full_ranges_at_the_same_public_peer(
        monkeypatch, first_override, pinned_override, state, pinned):
    calls = []
    url = "https://r1.googlevideo.com/videoplayback?sig=private"

    def probe(target, size, *, peer=None):
        assert target == url and size == 65536
        calls.append(peer)
        return {"ok": True, "status": 206, "bytes": 65536, "remote_ip": "1.1.1.1",
                **(first_override if peer is None else pinned_override)}

    monkeypatch.setattr(headless_playback, "probe", probe)
    result = headless_playback.probe_pair(url)
    assert result["ok"] is (state == "pass") and result["state"] == state
    assert calls == ([None, IPv4Address("1.1.1.1")] if pinned else [None])
