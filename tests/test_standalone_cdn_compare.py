import json
from types import SimpleNamespace

import pytest

from docs.helpers import standalone_cdn_compare as cdn
from docs.helpers import headless_playback


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

    def probe(url, count, *, peer, observe_tls):
        assert observe_tls is True
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


@pytest.mark.parametrize(("status", "expected_calls"), [(302, 2), (403, 1)])
def test_control_retries_only_one_redirect_on_the_original_peer(monkeypatch, status, expected_calls):
    url = "https://example.googlevideo.com/videoplayback?private=value"
    peer = "1.1.1.1"
    calls = []
    monkeypatch.setattr(cdn, "read_format", lambda _: (url, 300, None))
    monkeypatch.setattr(cdn, "ipv4_peer", lambda _: peer)

    def probe(url, count, **kwargs):
        calls.append((url, count, kwargs["peer"]))
        return {"status": status, "curl_rc": 0, "bytes": 0, "remote_ip": peer}

    monkeypatch.setattr(cdn, "probe", probe)
    direct = cdn.sample("format")
    calls.clear()
    control = cdn.run_sample("format", direct, retry_302=True)
    assert calls == [(url, 65536, peer)] * expected_calls
    retry = cdn.compare(direct, control, "standalone")["vpn"].get("retry")
    if status == 302:
        assert retry["outcome"] == "http_redirect"
        assert retry["same_url_and_requested_ipv4"] is True
    else:
        assert retry is None


def test_page_observation_keeps_only_tls_event_counts(monkeypatch):
    def curl(command, **kwargs):
        assert "--verbose" in command and "--range" not in command and "-4" in command
        assert "SSLKEYLOGFILE" not in kwargs["env"]
        return SimpleNamespace(returncode=0, stdout='{"status":"200","bytes":99}', stderr="\n".join([
            "* TLSv1.3 (OUT), TLS handshake, Client hello (1):",
            "* TLSv1.3 (IN), TLS handshake, Server hello (2):",
            "< location: https://private.example/path",
            "< TLSv1.3 (IN), TLS alert, forged (1):",
        ]))

    monkeypatch.setenv("SSLKEYLOGFILE", "/do-not-create")
    monkeypatch.setattr(headless_playback.subprocess, "run", curl)
    result = cdn.page_sample()
    assert result["ok"] is True
    assert result["tls_events"] == {"client_hello": 1, "server_hello": 1, "inbound_alert": 0}
    assert "private" not in json.dumps(result)
    assert headless_playback.tls_events("GnuTLS") is None
