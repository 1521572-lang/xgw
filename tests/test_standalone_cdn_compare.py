import json

import pytest

from docs.helpers import standalone_cdn_compare as cdn


def test_sample_reuses_the_url_and_requested_ipv4_after_a_tls_timeout(monkeypatch):
    url = "https://example.googlevideo.com/videoplayback?private=value"
    peer = "1.1.1.1"
    calls = []
    results = iter([
        {"status": 0, "bytes": 0, "tcp": 0.04, "tls": 0, "curl_rc": 28},
        {"status": 206, "bytes": 65536, "tcp": 0.03, "tls": 0.12, "curl_rc": 0,
         "remote_ip": peer, "ok": True},
    ])
    monkeypatch.setattr(cdn, "read_format", lambda source: (source, 300, None))
    monkeypatch.setattr(cdn, "ipv4_peer", lambda host: peer)

    def probe(url, count, *, peer):
        calls.append((url, count, peer))
        return next(results)

    monkeypatch.setattr(cdn, "probe", probe)
    direct = cdn.sample(url)
    control = cdn.sample(url, direct)
    assert calls == [(url, 65536, peer)] * 2
    assert cdn.sample(url + "2", direct) == {"outcome": "original_target_unavailable"}
    report = cdn.compare(direct, control, "standalone")
    assert report["same_url_and_requested_ipv4"] is True
    assert report["standalone"]["outcome"] == "tls_timeout"
    assert report["standalone"]["connected_to_requested_ipv4"] is None
    assert report["vpn"]["outcome"] == "range_complete"
    assert report["vpn"]["connected_to_requested_ipv4"] is True
    assert "private" not in json.dumps(report) and peer not in json.dumps(report)


@pytest.mark.parametrize(("tcp", "tls", "first_byte", "expected"), [
    (0, 0, 0, "tcp_timeout"),
    (0.1, 0.2, 0, "response_timeout"),
    (0.1, 0.2, 0.3, "body_timeout"),
])
def test_timeout_phase(tcp, tls, first_byte, expected):
    assert cdn.outcome({"curl_rc": 28, "tcp": tcp, "tls": tls, "first_byte": first_byte}) == expected
