"""Check the VPN-only range benchmark without making network requests."""
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
