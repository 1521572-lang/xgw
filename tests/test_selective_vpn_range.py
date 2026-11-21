"""Check the VPN-only range benchmark without making network requests."""
import sys
from types import SimpleNamespace

import pytest

from docs.helpers import selective_vpn_range as bench


@pytest.mark.parametrize(("http", "length", "span", "expected"), [
    (206, 65536, "bytes 0-65535/314159", True),
    (200, 65536, "bytes 0-65535/314159", False),
    (206, 65535, "bytes 0-65535/314159", False),
    (206, 65536, "bytes 1-65536/314159", False),
    (206, 65536, "", False),
])
def test_range_verdict_requires_the_exact_span_and_body(http, length, span, expected):
    raw = f"{http}\t{length}\t0.3\t1.2\t1.1\t{span}\n"
    assert bench.parse_metrics(raw, 0, 0, 65535)["ok"] is expected


def test_range_uses_loopback_and_keeps_signed_url_in_stdin(monkeypatch):
    url = "https://r1.googlevideo.com/videoplayback?sig=fixture"

    def run(args, **kwargs):
        assert args[args.index("--proxy") + 1] == "http://127.0.0.1:8780"
        assert args[args.index("--noproxy") + 1] == ""
        assert args[args.index("--max-filesize") + 1] == "65536"
        assert "--location" not in args and url not in args and url in kwargs["input"]
        return SimpleNamespace(returncode=0, stdout="206\t65536\t0.3\t1.2\t1.1\tbytes 0-65535/314159\n")

    monkeypatch.setattr(bench.subprocess, "run", run)
    assert bench.fetch_range(url, 8780, 0, 65535, 10)["ok"]


def test_both_arms_cover_the_same_offsets():
    assert bench.ranges("A") == [(0, 4 * bench.MIB - 1)]
    chunks = bench.ranges("B")
    assert len(chunks) == 4
    assert chunks[0][0] == 0 and chunks[-1][-1] == 4 * bench.MIB - 1
    assert all(right - left + 1 == bench.MIB for left, right in chunks)


def test_profile_excludes_incomplete_bins_and_includes_a_full_stall():
    counts = {0: 5000000, 1: 1000000, 3: 500000, 4: 9000000}
    raw = f"206\t{sum(counts.values())}\t0.3\t23.4\t1.1\tbytes 0-{bench.PROFILE_BYTES-1}/*\n"
    measured = bench.summarize_profile(
        bench.parse_metrics(raw, 28, 0, bench.PROFILE_BYTES - 1), counts, 23, 800000,
    )
    assert measured["state"] == "profiled"
    assert measured["complete_bucket_bytes"] == [5000000, 1000000, 0, 500000]
    assert measured["first_5s_Bps"] == 1000000
    assert measured["late_15s_median_Bps"] == 100000
    assert measured["late_to_bitrate"] == 1


def test_profile_checks_body_and_metrics_from_separate_streams(monkeypatch):
    monkeypatch.setattr(bench, "PROFILE_BYTES", 65536)
    child = (
        "import sys\n"
        "sys.stdin.read()\n"
        "sys.stdout.buffer.write(bytes(65536))\n"
        "sys.stderr.write('206\\t65536\\t0.01\\t0.1\\t1.1\\tbytes 0-65535/314159\\n')\n"
    )
    monkeypatch.setattr(
        bench, "curl_request", lambda *args, **kwargs: ([sys.executable, "-u", "-c", child], ""),
    )
    measured = bench.profile("unused", 8780, 800000)
    assert measured["state"] == "short"
    assert measured["request"]["bytes"] == 65536
    assert measured["late_15s_median_Bps"] is None
