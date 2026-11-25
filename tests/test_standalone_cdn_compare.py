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


@pytest.mark.parametrize("route", ["observed", "ambiguous"])
def test_pair_reports_tcp_only_with_an_observed_direct_route(route):
    direct = {"url_sha256": "digest", "peer": "1.1.1.1", "actual_peer": "1.1.1.1",
              "outcome": "tls_timeout",
              "wan_tcp": {"state": "ack_without_tcp_data", "samples": 23, "bytes_acked": 518,
                          "first_send_ms": 280, "first_payload_ack_ms": 340,
                          "first_receive_ms": None, "first_retransmit_ms": "private",
                          "largest_sample_gap_ms": 99999, "first_sample_ms": True,
                          "established_polls": 23, "syn_sent_only_polls": 70,
                          "established_polls_without_tcp_info": 0,
                          "cookie": "private"}}
    result = cdn.evaluate_pair(direct, {}, {"state": route, "group": "zapret2"}, {})
    expected = ({"state": "ack_without_tcp_data", "samples": 23, "bytes_acked": 518,
                 "first_send_ms": 280, "first_payload_ack_ms": 340, "first_receive_ms": None,
                 "established_polls": 23, "established_polls_without_tcp_info": 0}
                if route == "observed" else {"state": "path_unconfirmed"})
    assert result["direct_tcp"] == expected


def test_queue_comparison_is_published_only_for_the_observed_direct_peer(monkeypatch):
    from docs.helpers import cdn_queue_observation as queue

    direct = {"peer": "1.1.1.1", "actual_peer": "1.1.1.1"}
    route = {"state": "observed", "group": "zapret2"}
    snapshots = ({"boundary": "before"}, {"boundary": "after"})

    def summarize(before, after, request):
        assert (before, after) == snapshots and request is direct
        return {"state": "observed", "netlink_delta": 0}

    monkeypatch.setattr(queue, "summarize", summarize)
    before = cdn.evaluate_pair(direct, {}, route, {}, queue_snapshots=snapshots)
    assert before["direct_queue"] == {"state": "observed", "netlink_delta": 0}
    direct["actual_peer"] = "8.8.8.8"
    after = cdn.evaluate_pair(direct, {}, route, {}, queue_snapshots=snapshots)
    assert after["direct_queue"] == {"state": "path_unconfirmed"}


def test_direct_report_preserves_redirect_and_tcp_without_a_vpn_sample():
    direct = {"peer": "1.1.1.1", "actual_peer": "1.1.1.1", "url_sha256": "private",
              "outcome": "http_redirect", "status": 302,
              "wan_tcp": {"state": "tcp_data_received", "bytes_received": 4188}}
    result = cdn.evaluate_direct(direct, {"state": "observed", "group": "zapret2"})
    assert result["state"] == "direct_observed"
    assert result["direct"]["status"] == 302 and result["direct"]["outcome"] == "http_redirect"
    assert result["direct_route_verified"] and not result["direct_range_verified"]
    assert result["direct_tcp"] == direct["wan_tcp"]
    assert "private" not in repr(result) and "1.1.1.1" not in repr(result)


@pytest.mark.parametrize(("changes", "route", "expected"), [
    ({}, {"state": "observed", "group": "zapret2"}, True),
    ({"outcome": "tls_timeout"}, {"state": "observed", "group": "zapret2"}, False),
    ({"status": 403}, {"state": "observed", "group": "zapret2"}, False),
    ({"curl_rc": 28}, {"state": "observed", "group": "zapret2"}, False),
    ({"actual_peer": "8.8.8.8"}, {"state": "observed", "group": "zapret2"}, False),
    ({"url_sha256": "changed"}, {"state": "observed", "group": "zapret2"}, False),
    ({}, {"state": "observed", "group": "xray"}, False),
    ({}, {"state": "ambiguous"}, False),
])
def test_direct_retry_requires_a_confirmed_redirect_on_the_original_target(changes, route, expected):
    pinned = {"peer": "1.1.1.1", "url_sha256": "private"}
    first = pinned | {"outcome": "http_redirect", "status": 302, "curl_rc": 0,
                      "actual_peer": pinned["peer"]} | changes
    assert cdn.direct_retry_allowed(first, pinned, route) is expected


@pytest.mark.parametrize(("changes", "retry_route", "used", "verdict"), [
    ({}, {"state": "observed", "group": "zapret2"}, "retry", "pair_verified"),
    ({"content_range_ok": False}, {"state": "observed", "group": "zapret2"},
     "retry", "range_unconfirmed"),
    ({"outcome": "http_redirect", "status": 302}, {"state": "observed", "group": "zapret2"},
     "retry", "range_unconfirmed"),
    ({}, {"state": "ambiguous"}, "first", "range_unconfirmed"),
    ({"actual_peer": "8.8.8.8"}, {"state": "observed", "group": "zapret2"},
     "first", "range_unconfirmed"),
    ({"url_sha256": "changed"}, {"state": "observed", "group": "zapret2"},
     "first", "range_unconfirmed"),
])
def test_pair_keeps_direct_attempts_separate(changes, retry_route, used, verdict, monkeypatch):
    from docs.helpers import cdn_queue_observation as queue

    vpn = {"peer": "1.1.1.1", "actual_peer": "1.1.1.1", "url_sha256": "private",
           "outcome": "range_complete", "status": 206, "bytes": 65536, "curl_rc": 0,
           "content_range_ok": True}
    first = vpn | {"outcome": "http_redirect", "status": 302, "content_range_ok": False,
                   "wan_tcp": {"bytes_received": 100}}
    repeated = vpn | {"wan_tcp": {"bytes_received": 65536}} | changes
    direct_route = {"state": "observed", "group": "zapret2"}
    vpn_route = {"state": "observed", "group": "xray"}
    first_queue = ({"assigned_ids": 1}, {})
    repeated_queue = ({"assigned_ids": 2}, {})
    monkeypatch.setattr(queue, "summarize", lambda before, _after, _request: before)
    result = cdn.evaluate_pair(first, vpn, direct_route, vpn_route, queue_snapshots=first_queue,
                               retry=(repeated, retry_route, repeated_queue))
    assert result["state"] == verdict and result["direct_attempt"] == used
    assert result["direct_attempts"]["first"]["direct"]["status"] == 302
    assert result["direct_attempts"]["retry"]["direct"]["outcome"] == repeated["outcome"]
    assert result["direct_queue"] == {"assigned_ids": 2 if used == "retry" else 1}
    assert result["direct_tcp"] == {"bytes_received": 65536 if used == "retry" else 100}
    assert "private" not in json.dumps(result) and "1.1.1.1" not in json.dumps(result)
