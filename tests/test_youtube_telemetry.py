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


def sample(t, **changes):
    return dict(t_s=t, has_video=True, video_id=VIDEO, document_id=1, media_id=1,
                position=t, paused=False, seeking=False, ended=False, ad=False, hidden=False,
                playback_rate=1, ready_state=4, buffer_seconds=20, height=720, width=1280,
                total_frames=t * 30, dropped_frames=t, events=[], **changes)


def changed(t, **changes):
    return dict(sample(t), **changes)


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
