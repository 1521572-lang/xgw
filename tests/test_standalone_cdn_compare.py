import json
import os
import stat
import time
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


@pytest.mark.parametrize(("header", "exact"), [
    ("bytes 0-65535/65536", True), ("bytes 1-65536/100000", False),
    ("bytes 0-65535/65535", False), ("", False),
])
def test_curl_reads_exact_range_and_keeps_redirect_separate(monkeypatch, header, exact):
    location = "https://r2.googlevideo.com/videoplayback?private=fixture"

    def curl(command, **kwargs):
        assert command[command.index("--range") + 1] == "0-65535"
        assert "--location" not in command and "--globoff" in command
        output = command[command.index("--write-out") + 1]
        assert output.endswith(r"\n%header{content-range}\n%{redirect_url}")
        return SimpleNamespace(returncode=0, stderr="",
                               stdout=f'{{"status":"206","bytes":65536}}\n{header}\n{location}')

    monkeypatch.setattr(headless_playback.subprocess, "run", curl)
    result = headless_playback.probe("https://r1.googlevideo.com/videoplayback",
                                     65536, capture_redirect=True)
    assert result["content_range_ok"] is exact
    assert result["redirect_url"] == location


@pytest.mark.parametrize("case", [
    "original_range", "follow", "wrong_host", "wrong_port", "expired", "second_302",
])
def test_vpn_first_preflight_saves_only_a_confirmed_target(tmp_path, monkeypatch, case):
    now = int(time.time())
    original = f"https://r1.googlevideo.com/videoplayback?expire={now + 600}&sig=private"
    target = f"https://r2.googlevideo.com/videoplayback?expire={now + 600}&sig=private"
    location = {
        "wrong_host": target.replace("googlevideo.com", "example.com"),
        "wrong_port": target.replace("googlevideo.com", "googlevideo.com:444"),
        "expired": target.replace(str(now + 600), str(now - 1)),
    }.get(case, target)
    path = tmp_path / "pair.json"
    calls = []
    monkeypatch.setattr(cdn, "read_format", lambda _: (original, 300, 10_000))
    monkeypatch.setattr(cdn, "ipv4_peer", lambda host: {
        "r1.googlevideo.com": "1.1.1.1", "r2.googlevideo.com": "8.8.8.8",
    }[host])

    def probe(url, count, *, peer, observe_tls, capture_redirect=False):
        assert (count, observe_tls) == (65536, True)
        calls.append((url, peer, capture_redirect))
        if (url == original and case != "original_range") or case == "second_302":
            return {"status": 302, "bytes": 0, "curl_rc": 0, "remote_ip": peer,
                    "redirect_url": location}
        return {"ok": True, "status": 206, "bytes": 65536, "curl_rc": 0,
                "content_range_ok": True, "remote_ip": peer}

    monkeypatch.setattr(cdn, "probe", probe)
    report = cdn.prepare_pair(tmp_path / "source.json", path)
    assert calls[0] == (original, "1.1.1.1", True)
    assert "private" not in json.dumps(report) and "googlevideo.com" not in json.dumps(report)
    if case in ("original_range", "follow"):
        assert report["state"] == "vpn_range_verified"
        saved = json.loads(path.read_text())
        final = (target, "8.8.8.8", False) if case == "follow" else calls[0]
        assert calls == ([calls[0], final] if case == "follow" else [final])
        assert (saved["url"], saved["peer"]) == final[:2]
        if os.name == "posix":
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
    else:
        assert not path.exists()
        assert len(calls) == (2 if case == "second_302" else 1)
        assert report["state"] in ("redirect_unusable", "vpn_range_unconfirmed")


@pytest.mark.parametrize(("change", "expected"), [
    ("none", "pair_verified"), ("different_url", "target_unconfirmed"),
    ("wrong_actual_peer", "path_unconfirmed"), ("ambiguous", "path_unconfirmed"),
    ("wrong_vpn_route", "path_unconfirmed"), ("missing_range_header", "range_unconfirmed"),
    ("direct_tls_timeout", "range_unconfirmed"),
])
def test_pair_evaluation_requires_exact_range_peer_and_matching_routes(change, expected):
    direct = {"url_sha256": "private-digest", "peer": "1.1.1.1", "actual_peer": "1.1.1.1",
              "outcome": "range_complete", "status": 206, "bytes": 65536, "curl_rc": 0,
              "content_range_ok": True}
    control = dict(direct)
    direct_route = {"state": "observed", "group": "zapret2"}
    retry_route = {"state": "observed", "group": "sing-box"}
    if change == "different_url":
        control["url_sha256"] = "different-private"
    elif change == "wrong_actual_peer":
        control["actual_peer"] = "8.8.8.8"
    elif change == "ambiguous":
        retry_route = {"state": "ambiguous"}
    elif change == "wrong_vpn_route":
        retry_route["group"] = "zapret2"
    elif change == "missing_range_header":
        del control["content_range_ok"]
    elif change == "direct_tls_timeout":
        direct.update(outcome="tls_timeout", status=0, bytes=0, curl_rc=28, content_range_ok=False)
    vpn = {**control, "url_sha256": direct["url_sha256"], "outcome": "http_redirect",
           "retry": control}
    vpn_route = {"state": "observed", "group": "xray", "retry": retry_route}
    result = cdn.evaluate_pair(direct, vpn, direct_route, vpn_route)
    assert result["state"] == expected and result["vpn_attempt"] == "retry"
    assert "private" not in repr(result) and "1.1.1.1" not in repr(result)
