import gzip
import json
import threading

import pytest

from xgw.watch import checks
from xgw.watch import video_probe as v

DOMAINS = ["domain:youtube.com", "domain:googlevideo.com"]
PAGE = "https://www.youtube.com/watch?v=fixture"
URL = "https://cdn.googlevideo.com/video?expire=1600&token=PRIVATE"


def body(url=URL, **kwargs):
    row = {"mimeType": "video/mp4", "url": url, **kwargs}
    player = {"playabilityStatus": {"status": "OK"}, "streamingData": {"formats": [row]}}
    return b"var ytInitialPlayerResponse = " + json.dumps(player).encode() + b"; unrelated"


def test_bounded_gzip_and_plain_player_without_executing_script():
    for raw in (body(), gzip.compress(body())):
        assert v.candidate(raw, DOMAINS, 1000) == (URL, "candidate")
    assert v.candidate(b"ytInitialPlayerResponse = runCode()", DOMAINS, 1000)[0] == ""
    assert v.candidate(gzip.compress(b"x" * (v.PAGE_BYTES + 1) + body()), DOMAINS, 1000)[0] == ""


@pytest.mark.parametrize("url", [
    "https://outside.test/v?expire=1600", "http://cdn.googlevideo.com/v?expire=1600",
    "https://cdn.googlevideo.com:444/v?expire=1600", "https://u@cdn.googlevideo.com/v?expire=1600",
    "https://cdn.googlevideo.com/v?expire=1100", "https://cdn.googlevideo.com/v?expire=1000000",
    "https://cdn.googlevideo.com/v?expire=1600&expire=1800", "https://cdn.googlevideo.com/v",
    "https://cdn.googlevideo.com/v?expire=1600#fragment",
])
def test_candidate_rejects_wrong_scope_and_expiry(url):
    assert v.candidate(body(url), DOMAINS, 1000)[0] == ""


def test_unknown_and_cipher_have_distinct_results():
    assert v.candidate(b"consent", DOMAINS, 1000)[1] == "player_missing"
    assert v.candidate(body("", signatureCipher="PRIVATE"), DOMAINS, 1000)[1] == "cipher_required"
    assert v.candidate(body(URL, mimeType="audio/mp4"), DOMAINS, 1000)[0] == ""


def test_same_proxy_agent_and_no_secrets_in_summary(monkeypatch):
    monkeypatch.setattr(v.time, "time", lambda: 1000)
    calls = []

    def fetch(host, port, url, **kw):
        calls.append((host, port, url, kw))
        return checks.DownloadResult(True, status=200, downloaded=32768,
                                     body=body() if len(calls) == 1 else b"PRIVATE")

    monkeypatch.setattr(checks, "http_get_via_proxy", fetch)
    result = v.check(PAGE, DOMAINS, 12345, "PRIVATE", "")
    assert result["result"] == "fresh_video_verified" and result["expires_in"] == 600
    assert len(calls) == 2 and calls[0][:2] == calls[1][:2]
    assert calls[0][3]["user_agent"] == calls[1][3]["user_agent"]
    assert calls[1][3]["min_body"] == 16384 and calls[1][3]["range_end"] == 65536
    assert "PRIVATE" not in json.dumps(result)


def test_no_extra_requests_after_page_failure_missing_video_or_cancel(monkeypatch):
    calls = []
    response = checks.DownloadResult(False, status=302, location="https://outside.test/")
    monkeypatch.setattr(checks, "http_get_via_proxy", lambda *a, **kw: calls.append(a) or response)
    assert v.check(PAGE, DOMAINS, 12345, "", "")["result"] == "page_failed"
    response.ok, response.status, response.body = True, 200, b"no player"
    assert v.check(PAGE, DOMAINS, 12345, "", "")["result"] == "player_missing"
    response.body = body()
    monkeypatch.setattr(v.time, "time", lambda: 1000)
    cancel = threading.Event()
    cancel.set()
    assert v.check(PAGE, DOMAINS, 12345, "", "", cancel=cancel)["result"] == "cancelled"
    assert len(calls) == 3


def test_candidate_is_not_success_until_video_body_passes(monkeypatch):
    monkeypatch.setattr(v.time, "time", lambda: 1000)
    replies = iter([checks.DownloadResult(True, status=200, body=body()),
                    checks.DownloadResult(False, status=403, kind="http", phase="headers",
                                          error="PRIVATE", location="PRIVATE")])
    monkeypatch.setattr(checks, "http_get_via_proxy", lambda *a, **kw: next(replies))
    result = v.check(PAGE, DOMAINS, 12345, "PRIVATE", "")
    assert result["result"] == "video_failed" and result["video"]["verdict"] == "http_error"
    assert "PRIVATE" not in json.dumps(result)


def test_browser_candidate_prefers_video_and_rejects_other_resources():
    url = URL.replace("/video?", "/videoplayback?")
    audio = url + "&mime=audio%2Fwebm"
    video = url + "&mime=video%2Fmp4"
    entries = [{"url": item} for item in (URL, audio, url, video, video)]
    assert v.browser_candidates(entries, DOMAINS, 1000) == [
        v.BrowserCandidate(video, 4, None, None),
        v.BrowserCandidate(url, 3, None, None),
    ]
    stale = url.replace("expire=1600", "expire=1100")
    other = video.replace("googlevideo.com", "outside.test")
    excluded = [{"url": item} for item in (audio, stale, other)]
    assert not v.browser_candidates(excluded, DOMAINS, 1000)


def test_browser_candidates_rank_by_transfer_size_and_keep_original_observation():
    url = URL.replace("/video?", "/videoplayback?")
    large, small, recent, unknown, audio = [f"{url}&fixture={n}" for n in range(5)]
    small += "&mime=video%2Fmp4"
    audio += "&mime=audio%2Fmp4"
    entries = [
        {"url": recent, "transferSize": 0, "decodedBodySize": -10, "nextHopProtocol": "PRIVATE"},
        {"url": large, "transferSize": 10, "decodedBodySize": 9},
        {"url": small, "transferSize": 20, "decodedBodySize": 18, "nextHopProtocol": "http/1.1"},
        {"url": unknown, "transferSize": "99", "decodedBodySize": True},
        {"url": large, "transferSize": 30, "decodedBodySize": 27, "nextHopProtocol": "h2"},
        {"url": audio, "transferSize": 90, "decodedBodySize": 80},
    ]
    assert v.browser_candidates(entries, DOMAINS, 1000) == [
        v.BrowserCandidate(large, 5, 30, 27, "h2"),
        v.BrowserCandidate(small, 3, 20, 18, "http/1.1"),
        v.BrowserCandidate(recent, 1, 0, None, "other"),
    ]
    assert v.browser_candidates(entries[3:4], DOMAINS, 1000) == [
        v.BrowserCandidate(unknown, 1, None, None),
    ]


@pytest.mark.parametrize("status,downloaded,mime,reported,expected", [
    (206, 16384, "video/webm", "video/webm", "browser_video_verified"),
    (200, 16384, "text/html", "text/html", "replay_not_video"),
    (200, 16384, "audio/mp4", "audio/mp4", "replay_not_video"),
    (200, 25, "video/mp4", "video/mp4", "replay_failed"),
    (200, 31, "text/plain", "text/plain", "replay_failed"),
    (200, 31, "text/private", "other", "replay_failed"),
    (302, 0, "", None, "replay_failed"),
])
def test_browser_replay_requires_downloaded_video(
    monkeypatch, status, downloaded, mime, reported, expected,
):
    monkeypatch.setattr(v.time, "time", lambda: 1000)
    url = URL.replace("/video?", "/videoplayback?")
    calls = []

    def fetch(host, port, target, **kwargs):
        calls.append((host, port, target, kwargs))
        return checks.DownloadResult(status in (200, 206), status=status, downloaded=downloaded,
                                     content_type=mime, error="PRIVATE")

    monkeypatch.setattr(checks, "http_get_via_proxy", fetch)
    result = v.replay(url, DOMAINS, 12345, "PRIVATE", "Firefox")
    assert result["result"] == expected and "PRIVATE" not in json.dumps(result)
    assert result["video"]["content_type"] == reported
    assert "text/private" not in json.dumps(result)
    assert len(calls) == 1 and calls[0][:3] == ("127.0.0.1", 12345, url)
    assert calls[0][3]["user_agent"] == "Firefox" and calls[0][3]["range_end"] == 16384
    assert calls[0][3]["strict_max_bytes"]


@pytest.mark.parametrize("success_at,exhaust_first,expected", [
    (1, False, "browser_video_verified"),
    (2, False, "browser_video_verified"),
    (0, False, "replay_failed"),
    (0, True, "replay_time_budget"),
    (1, True, "browser_video_verified"),
])
def test_browser_replays_compare_same_candidate_and_preserve_attempts(
    monkeypatch, success_at, exhaust_first, expected,
):
    now = [0.0]
    calls, observed = [], []
    url = URL.replace("/video?", "/videoplayback?") + "&range=20-40"
    candidate = v.BrowserCandidate(url, 4, 10, 8)
    monkeypatch.setattr(v.time, "time", lambda: 1000)
    monkeypatch.setattr(v.time, "monotonic", lambda: now[0])

    def fetch(host, port, target, **kwargs):
        assert len(observed) == len(calls)
        assert host == "127.0.0.1" and port == 12345 and kwargs["user_agent"] == "Firefox"
        assert kwargs["strict_max_bytes"] and kwargs["min_body"] == kwargs["max_bytes"] == 16384
        calls.append((target, kwargs["max_total"], kwargs["range_end"]))
        now[0] += kwargs["max_total"] if exhaust_first else 2
        if len(calls) == success_at:
            return checks.DownloadResult(True, status=206, downloaded=16384,
                                         content_type="video/mp4")
        return checks.DownloadResult(False, status=200, downloaded=31, kind="http",
                                     phase="body", error="PRIVATE", content_type="text/plain")

    monkeypatch.setattr(checks, "http_get_via_proxy", fetch)
    result = v.compare_replays(
        candidate, DOMAINS, 12345, "PRIVATE", "Firefox",
        lambda index, row: observed.append((index, row)),
    )
    attempts = 1 if exhaust_first else 2
    assert calls == [(url, 8, 16384), (url, 6, 0)][:attempts]
    assert [index for index, _ in observed] == list(range(1, attempts + 1))
    for index, row in observed:
        assert row["candidate_index"] == candidate.index
        assert row["transfer_size"] == candidate.transfer_size
        assert row["decoded_body_size"] == candidate.decoded_body_size
        assert row["range_header"] is (index == 1)
        mime = "video/mp4" if index == success_at else "text/plain"
        assert row["video"]["content_type"] == mime
    assert result["result"] == expected
    assert result["comparison_complete"] is (not exhaust_first)
    assert result["range_header"] is (success_at == 1 or exhaust_first)
    assert "PRIVATE" not in json.dumps(observed)


def test_browser_replays_record_negotiated_http_version(monkeypatch):
    url = URL.replace("/video?", "/videoplayback?")
    candidate = v.BrowserCandidate(url, 4, 100_000, 99_700)
    monkeypatch.setattr(v.time, "time", lambda: 1000)
    calls, attempts = [], []

    def fetch(curl, target, port, password, agent, *, http2, max_total):
        assert (curl, target, port, password, agent) == ("curl", url, 12345, "PRIVATE", "Firefox")
        assert 0 < max_total <= v.REPLAY_SECONDS
        calls.append(http2)
        return checks.DownloadResult(False, status=200, downloaded=31, content_type="text/plain",
                                     kind="http", phase="body"), {
            "http_requested": "2" if http2 else "1.1", "http_version": "1.1",
            "content_length": 31, "content_encoding": None, "curl_exit": 0,
        }

    monkeypatch.setattr(v.video_probe_http, "get", fetch)
    result = v.compare_replays(candidate, DOMAINS, 12345, "PRIVATE", "Firefox",
                               lambda _index, row: attempts.append(row), curl="curl")
    assert calls == [False, True]
    assert result["result"] == "replay_failed" and result["comparison_complete"]
    assert all(row["range_header"] and row["candidate_index"] == 4 for row in attempts)
    assert [row["video"]["http_requested"] for row in attempts] == ["1.1", "2"]
    assert [row["video"]["http_version"] for row in attempts] == ["1.1", "1.1"]
    assert [row["video"]["content_length"] for row in attempts] == [31, 31]
