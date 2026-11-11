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
