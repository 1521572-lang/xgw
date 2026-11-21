from itertools import pairwise

import pytest

from docs.helpers import selective_flow_evidence as flow_evidence
from docs.helpers import selective_media_evidence as evidence
from docs.helpers import selective_probe_watch as watch
from docs.helpers import selective_wan_control as wan_control
from xgw.net import cmd


def test_socket_stats_distinguishes_received_data_from_missing_tcp_info(monkeypatch):
    text = (
        "ESTAB 0 517 192.0.2.1:43120 198.51.100.2:443 uid:150 ino:99 sk:abc "
        "cubic rto:208 bytes_sent:1034 bytes_acked:1 bytes_retrans:517 retrans:1/2\n"
        "ESTAB 0 0 [::ffff:192.0.2.1]:43121 [::ffff:198.51.100.3]:443 sk:def "
        "cubic rto:208 bytes_acked:518 bytes_received:3456 data_segs_in:3\n"
        "SYN-SENT 0 1 192.0.2.1:43122 198.51.100.4:443 sk:123\n"
    )

    def run(args, *, timeout):
        assert args[-7:] == ["fwmark", "=", "0x10000000", "and", "dport", "=", ":443"]
        assert timeout == 1
        return text

    monkeypatch.setattr(watch.cmd, "run", run)
    result = watch.socket_stats()
    assert result["state"] == "read"
    pending, received, unknown = result["sockets"]
    assert pending["bytes_received"] == 0 and pending["bytes_acked"] == 1
    assert pending["retrans_total"] == 2
    assert received["peer_ip"] == "198.51.100.3"
    assert (received["bytes_received"], received["data_segs_in"]) == (3456, 3)
    assert unknown["bytes_received"] is None
    assert "192.0.2.1" not in str(result)
    with_endpoint = watch.parse_socket_stats(text, include_local_endpoint=True)
    assert with_endpoint["sockets"][0]["local_endpoint"] == "192.0.2.1:43120"


@pytest.mark.parametrize(("text", "state"), [
    ("", "read"), ("unexpected row\n", "unexpected_format"),
])
def test_socket_stats_distinguishes_empty_read_from_bad_format(monkeypatch, text, state):
    monkeypatch.setattr(watch.cmd, "run", lambda *_args, **_kwargs: text)
    assert watch.socket_stats() == {"state": state, "sockets": []}


def test_socket_stats_denied_is_unavailable(monkeypatch):
    def run(*_args, **_kwargs):
        raise cmd.CommandError("private message")

    monkeypatch.setattr(watch.cmd, "run", run)
    assert watch.socket_stats() == {"state": "unavailable", "sockets": []}


def test_marked_socket_sampler_retains_owner_pids(monkeypatch):
    def run(args, *, timeout):
        assert "-HtaOeinp" in args and timeout == 1
        return ('ESTAB 0 0 192.0.2.1:43120 198.51.100.2:443 '
                'users:(("xray",pid=42,fd=3)) sk:abc rto:100 bytes_received:65536')

    monkeypatch.setattr(watch.cmd, "run", run)
    assert watch.socket_stats(owners=True)["sockets"][0]["owner_pids"] == [42]


def media_sample(seconds, packets, *, configured=True, semantic="policy", epoch="xray"):
    return {
        "revision": "abc", "worker_invocation": "worker",
        "probes": {},
        "gate": {"marked": True},
        "queue_start_unix": 99.75 + seconds, "queue_end_unix": 99.9 + seconds,
        "outgoing": {"handle": 8, "packets": packets},
        "queue": {"peer": 12, "sequence": packets},
        "route": {
            "unix": 100 + seconds, "monotonic_ns": seconds * 10**9, "xray_epoch": epoch,
            "config_sha256": str(seconds), "config_semantic_sha256": semantic,
            "client_zapret2_rule": configured,
            "tags": {"xgw-zapret2": {"group": "zapret2", "uplink": packets, "downlink": packets}},
        },
    }


def test_media_pair_accepts_stable_route_and_records_zero_or_positive_queue_growth():
    before = media_sample(1, 10)
    result = watch.media_pair(before, media_sample(4, 25))
    assert result["state"] == "accepted" and result["config_bytes_changed"]
    assert (result["start_unix"], result["end_unix"]) == (101, 103.75)
    assert result["nft_packets"] == result["queue_sequence_delta"] == 15
    assert result["groups"]["zapret2"]["downlink"] == 15
    assert watch.media_pair(before, media_sample(4, 10))["nft_packets"] == 0


@pytest.mark.parametrize(("after", "reason"), [
    (media_sample(4, 25) | {"route": None}, "route_sample_missing"),
    (media_sample(4, 25) | {"worker_invocation": "new"}, "policy_or_worker_changed"),
    (media_sample(4, 25, configured=False), "client_rule_inactive"),
    (media_sample(4, 25, semantic="new"), "incomparable_snapshots"),
    (media_sample(4, 25, epoch="new"), "incomparable_snapshots"),
    (media_sample(15, 25), "sample_gap"),
    (media_sample(4, 25) | {"gate": None}, "gate_unconfirmed"),
    (media_sample(4, 25) | {"queue_start_unix": 101}, "no_shared_window"),
    (media_sample(4, 25) | {"queue": {"peer": 13, "sequence": 25}}, "queue_changed"),
])
def test_media_pair_rejects_changes_and_missing_samples(after, reason):
    result = watch.media_pair(media_sample(1, 10), after)
    assert result["state"] == "rejected" and result["reason"] == reason


def socket_rows(sock, peer, owner):
    return [{"unix": 104.5 + i, "socket_start_unix": 104.5 + i,
             "socket_unix": 104.6 + i, "state": "read", "eligible_phase": True,
             "sockets": [{"socket": sock, "peer_ip": peer, "owner_pids": [owner],
                          "bytes_received": i * 65536}]} for i in range(2)]


@pytest.mark.parametrize(("bad_owner", "queued", "probe_overlap", "path", "queue"), [
    (False, False, False, "SUPPORTED", "UNCONFIRMED"),
    (False, True, False, "SUPPORTED", "OBSERVED"),
    (True, True, False, "UNKNOWN", "UNCONFIRMED"),
    (False, True, True, "UNKNOWN", "UNCONFIRMED"),
])
def test_media_matches_owned_socket_and_excludes_probe_time(
    bad_owner, queued, probe_overlap, path, queue,
):
    gateway = [media_sample(t, 10, epoch="boot:42:1") for t in (1, 4, 7)]
    for row in gateway:
        row["queue_owner_confirmed"] = True
        row["probes"] = {"page": {"started_at": 90, "elapsed_ms": 120}}
    if queued:
        gateway[-1]["queue"]["sequence"] = gateway[-1]["outgoing"]["packets"] = 100
    gateway[-1]["route"]["tags"]["xgw-zapret2"]["downlink"] = 131072
    if probe_overlap:
        gateway[-1]["probes"]["cdn"] = {"started_at": 105.1, "elapsed_ms": 100}
    for before, after in pairwise(gateway):
        after["media_pair"] = watch.media_pair(before, after)

    player = socket_rows("player", "198.51.100.2", 7)
    marked = socket_rows("upstream", "198.51.100.2", 2 if bad_owner else 42)
    result = evidence.analyze(player, marked, gateway)
    assert (result["media_path"], result["nfqueue"]) == (path, queue)
    assert result["background_windows"] == 1
    assert "198.51.100.2" not in str(result)


@pytest.mark.parametrize(("last_downlink", "background", "reason"), [
    (310, True, "no_growth"),
    (510, True, "at_or_below_background"),
    (510, False, "background_unavailable"),
    (None, True, "counter_unavailable"),
])
def test_media_reports_why_matched_sockets_lack_outbound_evidence(
    last_downlink, background, reason,
):
    gateway = [media_sample(t, 10, epoch="boot:42:1") for t in (1, 4, 7)]
    for row, downlink, vpn in zip(gateway, (10, 310, last_downlink), (0, 0, 50000), strict=True):
        row["queue_owner_confirmed"] = True
        row["probes"] = {"page": {"started_at": 90, "elapsed_ms": 120}}
        tags = row["route"]["tags"]
        tags["xgw-zapret2"]["downlink"] = downlink
        tags["private-server"] = {"group": "xray", "uplink": 0, "downlink": vpn}
    gateway[-1]["queue"]["sequence"] = gateway[-1]["outgoing"]["packets"] = 40
    gateway[0]["queue_owner_confirmed"] = background
    for before, after in pairwise(gateway):
        after["media_pair"] = watch.media_pair(before, after)

    player = socket_rows("player", "198.51.100.2", 7)
    marked = socket_rows("upstream", "198.51.100.2", 42)
    result = evidence.analyze(player, marked, gateway)

    assert result["media_path"] == "PARTIAL"
    assert result["counts"]["socket_matches"] == 1
    assert result["counts"]["outbound_matches"] == 0
    diagnostics = result["outbound_diagnostics"]
    assert diagnostics["unmatched_reasons"] == {reason: 1}
    assert diagnostics["zapret2_background_peak_bytes_per_second"] == (100 if background else None)
    (window,) = diagnostics["top_unmatched_windows"]
    assert window["downlink_bytes"] == {
        "zapret2": None if last_downlink is None else last_downlink - 310,
        "xray": 50000,
        "sing-box": None,
    }
    assert window["queue_above_background"] == background
    assert "198.51.100.2" not in str(result)
    assert "private-server" not in str(result)


@pytest.mark.parametrize(("matches", "group", "unmatched"), [
    (1, "xray", {}),
    (0, None, {"no_access_record": 1}),
    (2, None, {"ambiguous": 1}),
])
def test_flow_evidence_requires_exact_client_endpoint_and_unique_xray_record(
    matches, group, unmatched,
):
    boot = "01234567-abcd-0123-abcd-0123456789ab"
    epoch = f"{boot}:42:1"
    before = media_sample(1, 10, epoch=epoch)["route"]
    after = media_sample(7, 10, epoch=epoch)["route"]
    for snapshot in (before, after):
        snapshot["tags"]["proxy-private"] = {"group": "xray", "uplink": 0, "downlink": 10}
    player = socket_rows("player-private", "198.51.100.2", 7)
    for row in player:
        row["capture_started_unix"] = 104
        row["sockets"][0]["local_endpoint"] = "[::ffff:192.0.2.1]:43120"
    event = {
        "_SYSTEMD_UNIT": "xgw-xray.service", "_BOOT_ID": boot.replace("-", ""), "_PID": "42",
        "__REALTIME_TIMESTAMP": "104200000",
        "MESSAGE": "from tcp:192.0.2.1:43120 accepted tcp:198.51.100.2:443 "
                   "[tun-in -> proxy-private]",
    }
    wrong_port = event | {"MESSAGE": event["MESSAGE"].replace("43120", "43121")}
    wrong_peer = event | {"MESSAGE": event["MESSAGE"].replace("198.51.100.2", "198.51.100.3")}
    wrong_inbound = event | {"MESSAGE": event["MESSAGE"].replace("tun-in", "zapret2-probe")}
    other_process = event | {"_PID": "41"}
    result = flow_evidence.analyze(
        player, [wrong_port, wrong_peer, wrong_inbound, other_process, *([event] * matches)],
        before, after,
    )
    assert result["qualified_flows"] == 1
    assert result["groups"] == ({group: 1} if group else {})
    assert result["unmatched"] == unmatched
    assert result["state"] == ("observed" if group else "inconclusive")
    assert all(secret not in str(result)
               for secret in ("192.0.2.1", "198.51.100.2", "player-private", "proxy-private"))


@pytest.mark.parametrize(("mutation", "accepted"), [
    ("rotation", 1), ("different_group", None), ("epoch", None),
    ("vpn_outbound", 0), ("duplicate", 0), ("no_local_port", 0),
])
def test_replay_keeps_changed_window_inconclusive_and_reports_exact_zapret2_accepts(
    mutation, accepted,
):
    boot = "01234567-abcd-0123-abcd-0123456789ab"
    epoch = f"{boot}:42:1"
    before = media_sample(1, 10, epoch=epoch)["route"]
    after = media_sample(7, 20, epoch=epoch, semantic="rotation")["route"]
    if mutation == "epoch":
        after["xray_epoch"] = f"{boot}:43:1"
    if mutation == "different_group":
        after["tags"]["xgw-zapret2"]["group"] = "xray"
    player = socket_rows("player-private", "198.51.100.2", 7)
    for row in player:
        row["capture_started_unix"] = 104
        if mutation != "no_local_port":
            row["sockets"][0]["local_endpoint"] = "192.0.2.1:43120"
    tag = "proxy-private" if mutation == "vpn_outbound" else "xgw-zapret2"
    entry = {
        "_SYSTEMD_UNIT": "xgw-xray.service", "_BOOT_ID": boot.replace("-", ""), "_PID": "42",
        "__REALTIME_TIMESTAMP": "104200000",
        "MESSAGE": f"from tcp:192.0.2.1:43120 accepted tcp:198.51.100.2:443 [tun-in -> {tag}]",
    }
    journal = [entry, entry] if mutation == "duplicate" else [entry]
    assert "logged_zapret2" not in flow_evidence.analyze(player, journal, before, after)
    result = flow_evidence.analyze(player, journal, before, after, observe_applied_change=True)
    assert result["state"] == "inconclusive"
    if accepted is None:
        assert "logged_zapret2" not in result
    else:
        replay = result["logged_zapret2"]
        assert replay["accepted_flows"] == accepted
        assert replay["unconfirmed_flows"] == 1 - accepted
        assert replay["qualified_flows"] == 1
        other = int(mutation == "vpn_outbound")
        assert replay["accepted_other_outbound_flows"] == other
        assert replay["unmatched"] == {
            "duplicate": {"ambiguous": 1},
            "no_local_port": {"local_endpoint_unconfirmed": 1},
        }.get(mutation, {})
        assert accepted + other + sum(replay["unmatched"].values()) == replay["qualified_flows"]
        assert replay["capture_accept_records"] == {
            "other" if other else "zapret2": len(journal),
        }
    assert all(secret not in repr(result) for secret in ("private", "192.0.2.1", "198.51.100.2"))


def test_wan_control_skips_tcp_when_bypass_routes_to_another_interface(monkeypatch):
    monkeypatch.setattr(wan_control, "route", lambda *_args: {"dev": "xgw-tun"})

    def unexpected_connect(*_args, **_kwargs):
        pytest.fail("control must not send TCP traffic on an unconfirmed WAN")

    monkeypatch.setattr(wan_control.marknet, "connect_marked", unexpected_connect)
    result = wan_control.control("203.0.113.4", "wan0", 2, 111, 0)
    assert result["tcp"] == "wan_route_unconfirmed"


@pytest.mark.parametrize("tls_host", [None, "r1.googlevideo.com"])
def test_wan_control_binds_expected_interface_and_uses_configured_bypass(monkeypatch, tls_host):
    recorded = []

    class Sock:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def setsockopt(self, _level, _option, value):
            recorded.append(value)

        def settimeout(self, timeout):
            assert timeout == 5

        def connect(self, address):
            recorded.append(address)

        def getsockname(self):
            return "192.0.2.2", 1234

    def lookup(peer, mark, uid):
        recorded.append((peer, mark, uid))
        return {"dev": "wan0", "prefsrc": "192.0.2.2"}

    def tcp(host, port, *, timeout, mark, connect):
        assert mark == 2 and timeout == 5
        sock = Sock()
        connect(sock, (host, port))
        return sock

    monkeypatch.setattr(wan_control, "route", lookup)
    monkeypatch.setattr(wan_control.marknet, "connect_marked", tcp)
    monkeypatch.setattr(wan_control.socket, "SO_BINDTODEVICE", 25, raising=False)

    def handshake(sock, host):
        assert isinstance(sock, Sock)
        recorded.append(host)
        return {"tls": "connected"}

    monkeypatch.setattr(wan_control, "tls_control", handshake)
    result = wan_control.control("203.0.113.4", "wan0", 2, 111, 0, tls_host=tls_host)
    assert recorded == [
        ("203.0.113.4", 2, 0), ("203.0.113.4", 0x10000000, 111),
        b"wan0\0", ("203.0.113.4", 443),
    ] + ([tls_host] if tls_host else [])
    assert result["tcp"] == "connected" and result["source_matches_lookup"]
    assert result.get("tls") == ("connected" if tls_host else None)


@pytest.mark.parametrize("error, outcome", [
    (None, "connected"),
    (TimeoutError(), "timeout"),
    (wan_control.ssl.SSLCertVerificationError("local detail"), "certificate_error"),
])
def test_wan_tls_checks_name_and_distinguishes_failure(monkeypatch, error, outcome):
    raw = object()

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def settimeout(self, value):
            assert value == 10

        def do_handshake(self):
            if error:
                raise error

        def version(self):
            return "TLSv1.3"

    class Context:
        def wrap_socket(self, sock, *, server_hostname, do_handshake_on_connect):
            assert sock is raw and not do_handshake_on_connect
            assert server_hostname == "r1.googlevideo.com"
            return Socket()

    if isinstance(error, wan_control.ssl.SSLCertVerificationError):
        error.verify_code = 62
    monkeypatch.setattr(wan_control.ssl, "create_default_context", Context)
    result = wan_control.tls_control(raw, "r1.googlevideo.com")
    assert result["tls"] == outcome
    assert result["tls_finished_at"] >= result["tls_started_at"]
    assert "local detail" not in str(result)
    if outcome == "certificate_error":
        assert result["verify_code"] == 62


@pytest.mark.parametrize("ambiguous", [False, True])
def test_wan_tls_trigger_requires_unique_new_sending_socket(monkeypatch, ambiguous):
    peer = "203.0.113.4"
    old = {"socket": "1", "peer_ip": peer, "state": "ESTAB", "bytes_sent": 100}
    fresh = {**old, "socket": "2"}
    pending = {**old, "socket": "3", "bytes_sent": 0}
    other_peer = {**old, "socket": "4", "peer_ip": "203.0.113.5"}
    sockets = [old, fresh, pending, other_peer]
    if ambiguous:
        sockets.append({**fresh, "socket": "5"})
    samples = iter([[old], sockets])
    monkeypatch.setattr(watch, "socket_stats", lambda: {"state": "read", "sockets": next(samples)})
    result = wan_control.wait_for_selective_socket(peer, seconds=5)
    if ambiguous:
        assert result["state"] == "multiple_candidates"
    else:
        assert result["state"] == "matched" and result["socket"] == fresh
