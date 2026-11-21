"""Portable measurement regressions. Actual browser/CDP acceptance belongs on Ubuntu."""

import json

import pytest

from docs.helpers.youtube_telemetry import (
    MediaNetwork,
    gateway_snapshot,
    media_host,
    summarize,
    write_report,
)

VIDEO = "abcdefghijk"

@pytest.mark.parametrize("scenario", ["short", "long", "clock", "no_network", "seek_missing"])
def test_acceptance_requires_seconds_and_fresh_media_not_sample_counts(scenario):
    from docs.helpers.acceptance_playback_check import evaluate

    seconds = 60 if scenario == "short" else 901
    rows = [dict(sample(i), unix=10000 + i, network={"encoded_bytes": i * 65536})
            for i in range(seconds + 1)]
    if scenario == "clock":
        rows[-1]["unix"] += 100
    if scenario == "no_network":
        for row in rows:
            row["network"]["encoded_bytes"] = 0
    result = evaluate(rows, VIDEO, 900, require_seek=scenario == "seek_missing")
    assert result["ok"] is (scenario == "long")
    assert result["route_verdict"] == "UNKNOWN"



def sample(t, **changes):
    return dict(t_s=t, has_video=True, video_id=VIDEO, document_id=1, media_id=1,
                position=t, paused=False, seeking=False, ended=False, ad=False, hidden=False,
                playback_rate=1, ready_state=4, buffer_seconds=20, height=720, width=1280,
                total_frames=t * 30, dropped_frames=t, events=[], **changes)


def changed(t, **changes):
    return dict(sample(t), **changes)


def test_headless_playback_counts_elapsed_progress_and_cache_stalls():
    from docs.helpers.headless_playback import measure

    rows = [{"mono": i + i / 1230, "time-pos": i, "seeking": False, "height": 720,
             "paused-for-cache": False, "cache-speed": 400000, "demuxer-cache-duration": 10}
            for i in range(123)]
    result = measure(rows, 120, 1600000)
    assert result["ok"] and result["line"] == "OK"
    assert result["cache_buffer_below_5s"] is False
    assert result["cache_read_to_bitrate_ratio"] == 2
    rows[1]["demuxer-cache-duration"] = 0.56
    result = measure(rows, 120, 1600000)
    assert result["ok"] and result["stall_seconds"] == 0
    assert result["cache_buffer_below_5s"] is True
    assert result["cache_read_to_bitrate_ratio"] == 2
    rows[20]["paused-for-cache"] = True
    rows[40]["paused-for-cache"] = True
    rows[80]["paused-for-cache"] = True
    result = measure(rows, 120, 1600000)
    assert not result["ok"] and result["line"] == "THROTTLED"
    assert result["stall_seconds"] == pytest.approx(3, abs=0.01)


@pytest.mark.parametrize(("end", "frozen", "paused", "expected"), [
    (900, set(), set(), True),
    (900, set(range(50, 56)), set(), False),
    (900, set(range(50, 54)), set(range(300, 304)), True),
    (900, set(range(50, 55)), set(range(300, 305)), False),
    (899, set(), set(), False),
])
def test_headless_strict_acceptance_counts_frozen_wall_clock_time(end, frozen, paused, expected):
    from docs.helpers.headless_playback import playback_acceptance

    rows = []
    position = 0
    for i in range(end + 1):
        if i and i not in frozen | paused:
            position += 1
        rows.append({"mono": i, "time-pos": position, "seeking": False, "height": 720,
                     "paused-for-cache": i in paused})
    result = playback_acceptance(rows, 900)
    assert result["ok"] is expected
    assert result["observed_seconds"] == end
    assert result["stall_seconds"] == len(frozen | paused)
    assert result["longest_stall_seconds"] == max(len(frozen), len(paused))


def test_headless_strict_acceptance_rejects_sampling_gaps_and_caps_window():
    from docs.helpers.headless_playback import playback_acceptance

    rows = [{"mono": i, "time-pos": i, "seeking": False, "height": 720 if i <= 900 else 480,
             "paused-for-cache": False} for i in range(916)]
    assert playback_acceptance(rows, 900)["ok"]
    del rows[50:56]
    result = playback_acceptance(rows, 900)
    assert not result["ok"]
    assert result["sampling_gap_seconds"] == 7
    assert result["observed_seconds"] == 900


def test_read_netlog_counts_only_successful_media_streams(tmp_path):
    from docs.helpers.playback_netlog import read_media

    events = []
    kinds = {}

    def event(kind, source, time, **params):
        code = kinds.setdefault(kind, len(kinds))
        events.append({"type": code, "source": {"id": source}, "time": str(time),
                       "params": params})

    event("TCP_CONNECT_ATTEMPT", 8, 100, remote_address="[::ffff:203.0.113.1]:443")
    event("HTTP2_SESSION_INITIALIZED", 10, 120, source_dependency={"id": 8})
    for stream, status in ((1, "206"), (3, "403")):
        event("HTTP2_SESSION_SEND_HEADERS", 10, 150, stream_id=stream,
              headers=[":authority: r1.googlevideo.com", ":method: POST",
                       ":path: /videoplayback?sig=private"])
        event("HTTP2_SESSION_RECV_HEADERS", 10, 200, stream_id=stream,
              headers=[f":status: {status}"])
        event("HTTP2_SESSION_RECV_DATA", 10, 210, stream_id=stream, length=2000)
    event("HTTP2_SESSION_RECV_DATA", 11, 220, stream_id=1, length=5000)
    event("HTTP2_SESSION_RECV_DATA", 10, 230, stream_id=1, length=1000)
    log = tmp_path / "netlog.json"
    log.write_text(json.dumps({"constants": {"timeTickOffset": "1000000",
                                             "logEventTypes": kinds}, "events": events}))
    rows, bounds = read_media(log)
    assert bounds == (1000.1, 1000.23)
    assert rows == [{"kind": "media_bytes", "start_unix": 1000.21, "end_unix": 1000.23,
                     "encoded_bytes": 3000, "remote_ip": "203.0.113.1"}]


@pytest.mark.parametrize("cached", [False, True])
def test_acceptance_passive_seek_requires_jump_outside_prior_buffer(cached):
    from docs.helpers.acceptance_playback_check import evaluate

    rows = [changed(t, unix=1000 + t, position=(t + 499 if t else 0),
                    buffer_ranges=[[0, 550 if cached else 20]]) for t in range(123)]
    rows[1]["events"] = [{"name": name, "media_id": 1, "position": 500}
                         for name in ("seeking", "seeked")]
    netlog = ([{"start_unix": 1020, "end_unix": 1021, "encoded_bytes": 1048576}],
              (999, 1123))
    verdict = evaluate(rows, VIDEO, 120, minimum_jump=400, netlog=netlog)
    assert verdict["ok"] is not cached
    assert verdict["seek_observed"] is not cached
    partial = evaluate(rows, VIDEO, 120, minimum_jump=400, netlog=([], (1100, 1123)))
    assert not partial["ok"] and partial["network_source"] == "netlog_incomplete"
    assert partial["player_ok"] is not cached


def test_progress_and_quality_do_not_claim_zapret_or_route():
    result = summarize([sample(i) for i in range(11)], VIDEO, 720)
    assert result["estimated_playing_seconds"] == 10
    assert result["observed_frames"] == 300
    assert result["dropped_frame_ratio"] == pytest.approx(10 / 300)
    assert result["target_height_ratio"] == 1
    assert result["buffer_p10_seconds"] == 20
    assert result["route_verdict"] == "UNKNOWN"
    assert result["zapret2_effectiveness"] == "NOT_ESTABLISHED"


@pytest.mark.parametrize("changes", [
    {"ad": True}, {"paused": True}, {"seeking": True}, {"hidden": True},
    {"video_id": "wrong_video"}, {"has_video": False}, {"playback_rate": None},
])
def test_no_ad_pause_seek_background_or_other_video_credit(changes):
    result = summarize([dict(sample(i), **changes) for i in range(5)], VIDEO, 720)
    assert result["eligible_seconds"] == 0
    assert result["estimated_stall_ratio"] is None
    assert result["dropped_frame_ratio"] is None


def test_short_seek_event_large_jump_reload_and_sampling_gap_excluded():
    for current in (changed(1, position=100), changed(1, document_id=2),
                    changed(1, media_id=2), changed(1, events=[{"name": "seeked"}]),
                    sample(8)):
        result = summarize([sample(0), current], VIDEO, 720)
        assert result["content_progress_seconds"] == 0
    assert result["sampling_gap_seconds"] == 8


def test_network_wait_and_ready_data_freeze_are_distinct():
    result = summarize([sample(0), changed(1, position=0, ready_state=2),
                        changed(2, position=0, ready_state=2),
                        changed(3, position=0, ready_state=4), changed(4, position=1)], VIDEO, 1080)
    assert result["estimated_stall_count"] == 1
    assert result["estimated_stall_seconds"] == 2
    assert result["freeze_with_ready_data_seconds"] == 1
    assert result["estimated_playing_seconds"] == 1
    assert result["target_height_ratio"] == 0


def test_events_include_brief_wait_and_play_delay():
    events = [{"name": name, "at_ms": t, "media_id": 1} for name, t in
              (("play", 10), ("waiting", 20), ("playing", 210))]
    result = summarize([changed(0, events=events), sample(1)], VIDEO, 720)
    assert result["waiting_events"] == 1
    assert result["play_to_playing_delays_seconds"] == [0.2]
    assert result["estimated_stall_seconds"] == 0


def test_streaming_post_counts_before_finish_and_finish_is_not_double_counted():
    records = []
    network = MediaNetwork(records.append, lambda: 1)
    network.handle("requestWillBeSent", {"requestId": "1", "request": {
        "url": "https://r1.googlevideo.com/videoplayback?sig=SECRET", "method": "POST",
        "postData": "PRIVATE_SABR", "headers": {"Cookie": "PRIVATE_COOKIE"}}})
    network.handle("responseReceived", {"requestId": "1", "response": {
        "status": 200, "protocol": "h2", "remoteIPAddress": "8.8.8.8"}})
    network.handle("dataReceived", {"requestId": "1", "encodedDataLength": 100, "dataLength": 150})
    assert network.snapshot()["encoded_bytes"] == 100
    assert network.snapshot()["inflight"] == 1
    network.handle("loadingFinished", {"requestId": "1", "encodedDataLength": 120})
    assert network.snapshot()["encoded_bytes"] == 120
    assert network.snapshot()["data_bytes"] == 150
    assert network.snapshot()["inflight"] == 0
    exported = json.dumps(records)
    assert "POST" in exported and "h2" in exported
    assert "SECRET" not in exported and "PRIVATE" not in exported


def test_failed_partial_and_cached_transfers_keep_correct_counters():
    network = MediaNetwork(lambda r: None, lambda: 0)
    for rid in ("failed", "cached", "canceled"):
        network.handle("requestWillBeSent", {"requestId": rid, "request": {
            "url": "https://r1.googlevideo.com/videoplayback", "method": "GET"}})
    network.handle("dataReceived", {"requestId": "failed", "encodedDataLength": 123})
    network.handle("loadingFailed", {"requestId": "failed", "errorText": "net::ERR_TIMED_OUT"})
    network.handle("requestServedFromCache", {"requestId": "cached"})
    network.handle("dataReceived", {"requestId": "cached", "dataLength": 200})
    network.handle("loadingFinished", {"requestId": "cached", "encodedDataLength": 0})
    network.handle("loadingFailed", {"requestId": "canceled", "canceled": True,
                                     "errorText": "net::ERR_ABORTED"})
    assert network.snapshot()["encoded_bytes"] == 123
    assert network.snapshot()["failures"] == 1
    assert network.snapshot()["canceled"] == 1


def test_redirect_to_unrelated_origin_stops_tracking():
    network = MediaNetwork(lambda r: None, lambda: 0)
    network.handle("requestWillBeSent", {"requestId": "1", "request": {
        "url": "https://r1.googlevideo.com/videoplayback", "method": "GET"}})
    network.handle("requestWillBeSent", {"requestId": "1", "redirectResponse": {"status": 302},
                                        "request": {"url": "https://other.test/"}})
    network.handle("dataReceived", {"requestId": "1", "encodedDataLength": 999})
    assert network.encoded_bytes == 0
    assert network.statuses == {"302": 1}


def test_media_byte_intervals_use_browser_clock_and_exclude_cache_and_finish_totals():
    records = []
    network = MediaNetwork(records.append, lambda: 100)
    for index, cached in enumerate((False, True)):
        rid = str(index)
        network.handle("requestWillBeSent", {"requestId": rid, "timestamp": 50, "wallTime": 1000,
                       "request": {"url": "https://r1.googlevideo.com/videoplayback?sig=private"}})
        network.handle("responseReceived", {"requestId": rid, "response": {
            "status": 206, "remoteIPAddress": "203.0.113.1", "fromDiskCache": cached}})
        for stamp in (52.25, 52.5):
            network.handle("dataReceived", {"requestId": rid, "timestamp": stamp,
                                            "encodedDataLength": 75})
        network.handle("loadingFinished", {"requestId": rid, "encodedDataLength": 2000})
    network.flush_body_intervals()
    network.flush_body_intervals()
    assert [r for r in records if r["kind"] == "media_bytes"] == [
        {"kind": "media_bytes", "id": 1, "start_unix": 1002.25, "end_unix": 1002.5,
         "encoded_bytes": 150, "remote_ip": "203.0.113.1"}]
    assert "private" not in json.dumps(records)


@pytest.mark.parametrize("url", ["https://googlevideo.com.evil.test/videoplayback",
                                 "https://r1.googlevideo.com/other",
                                 "https://www.youtube.com/watch?v=abcdefghijk", "http://[/"])
def test_only_media_endpoint_tracked(url):
    assert media_host(url) is None


def test_gateway_status_missing_stale_and_filtered(tmp_path):
    path = tmp_path / "status.json"
    assert gateway_snapshot(None, 1000) == {"observation": "not_collected"}
    assert gateway_snapshot(path, 1000) == {"observation": "unavailable"}
    path.write_text(json.dumps({"updated": 100, "zapret2": {"state": "active", "without_vpn": True,
                                                            "secret": "SECRET"}}))
    result = gateway_snapshot(path, 1000)
    assert result["observation"] == "stale"
    assert result["reported_without_vpn"] is True  # declaration, never a route verdict
    assert "SECRET" not in json.dumps(result)
    path.write_text("[]")
    assert gateway_snapshot(path, 1000) == {"observation": "unavailable"}


def test_empty_partial_report_stays_unknown(tmp_path):
    result = dict(summarize([], VIDEO, 720), label="empty", video_id=VIDEO, outcome="browser_error")
    write_report(tmp_path, result, [])
    report = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "browser_error" in report and "UNKNOWN" in report and "NOT_ESTABLISHED" in report
    assert "PASS" not in report
    assert len((tmp_path / "timeline.csv").read_text().splitlines()) == 1


class TrialPage:
    def __init__(self):
        self.actions = []

    def evaluate(self, script, args):
        self.actions.append(args["action"])
        return 407 if args["action"] == "seek" else None

    def bring_to_front(self):
        self.actions.append("foreground")


def trial_row(t, **changes):
    return changed(t, unix=10000 + t, network={"encoded_bytes": t * 65536}, **changes)


def test_trial_waits_for_ready_video_then_requires_measured_progress():
    from docs.helpers.playback_trial import PlaybackTrial

    trial, page, rows = PlaybackTrial("control", VIDEO), TrialPage(), []
    for t in range(124):
        row = trial_row(t)
        if t == 0:
            row.update(hidden=True, ready_state=0, paused=True)
        if t == 1:
            row.update(paused=True)
        rows.append(row)
        outcome = trial.step(page, rows)
        assert outcome == ("complete" if t == 123 else None)
    assert page.actions == ["foreground", "play"]
    assert trial.finish(rows, outcome)["measurement"]["eligible_seconds"] == 120


@pytest.mark.parametrize("matched", [True, False])
def test_seek_trial_requires_event_at_requested_position(matched):
    from docs.helpers.playback_trial import PlaybackTrial

    trial, page, rows = PlaybackTrial("seek", VIDEO), TrialPage(), []
    for t in range(303):
        row = trial_row(t)
        if t >= 2:
            row["position"] = 407 + t - 2
        if t == 2:
            row["events"] = [{"name": "seeked", "media_id": 1, "position": 407 if matched else 7}]
        rows.append(row)
        outcome = trial.step(page, rows)
        if outcome:
            break
    assert page.actions == ["seek"]
    assert outcome == ("complete" if matched else "seek_unconfirmed")
    assert trial.finish(rows, outcome)["ok"] is matched


def test_error_or_document_change_ends_attempt_without_combining_samples():
    from docs.helpers.playback_trial import PlaybackTrial

    for change, reason in (({"player_error_visible": True}, "player_error"),
                           ({"document_id": 2}, "player_replaced")):
        trial, page, rows = PlaybackTrial("long", VIDEO), TrialPage(), []
        for row in (trial_row(0), trial_row(1), trial_row(2, **change)):
            rows.append(row)
            outcome = trial.step(page, rows)
        assert outcome == reason
        result = trial.finish(rows, outcome)
        assert not result["ok"] and "eligible" in result["measurement"]["failed_checks"]


@pytest.mark.parametrize("second_ok", [False, True])
def test_retries_keep_independent_attempt_verdicts(tmp_path, monkeypatch, second_ok):
    from argparse import Namespace

    from docs.helpers import youtube_telemetry as telemetry

    def stub(args, trial):
        args.out.mkdir()
        ok = second_ok and args.out.name == "attempt-2"
        telemetry.dump(args.out / "summary.json", {"verification": {
            "ok": ok, "outcome": "complete" if ok else "playback_interrupted",
            "measurement": {"eligible_seconds": 900 if ok else 550}}})

    monkeypatch.setattr(telemetry, "collect", stub)
    monkeypatch.setattr(telemetry.os, "umask", lambda _: 0)
    dest = tmp_path / "watch"
    rc = telemetry.verify(Namespace(out=dest, verify="long", video=VIDEO, attempts=2))
    report = json.loads((dest / "verification.json").read_text())
    assert rc == (0 if second_ok else 2)
    assert [r["ok"] for r in report["attempts"]] == [False, second_ok]
