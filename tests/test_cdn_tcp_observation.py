"""Evidence from only the new marked socket owned by the sampled Xray process."""

import pytest

from docs.helpers import cdn_tcp_observation as tcp
from xgw.net.cmd import CommandError

PEER = "198.51.100.2"
PID = 42


def listing(*rows):
    return {"state": "read", "sockets": rows}


def socket_row(**extra):
    return {"socket": "private-cookie", "peer_ip": PEER, "owner_pids": [PID], "state": "ESTAB",
            "bytes_sent": 517, "bytes_acked": 1, "bytes_received": 0, "bytes_retrans": 0,
            "data_segs_in": 0, "retrans_total": 0, **extra}


@pytest.mark.parametrize(("updates", "expected"), [
    ({"bytes_retrans": 1034, "retrans_total": 2}, "retransmit_without_payload_ack"),
    ({"bytes_acked": 518}, "ack_without_tcp_data"),
    ({"bytes_acked": 518, "bytes_received": 48, "data_segs_in": 1}, "tcp_data_received"),
    ({"bytes_sent": 0}, "send_unobserved"),
    ({}, "ack_inconclusive"),
])
def test_last_established_sample_distinguishes_ack_retransmit_and_data(updates, expected):
    baseline = listing(socket_row(socket="existing"))
    observations = [
        (at, listing(socket_row(**updates), socket_row(socket="existing"),
                     socket_row(socket="other-process", owner_pids=[7]),
                     socket_row(socket="other-peer", peer_ip="198.51.100.3")))
        for at in (2, 5, 9.7)
    ]
    result = tcp.summarize(baseline, observations, peer=PEER, pid=PID, finished=10,
                           tls_timeout=True)
    assert result["state"] == expected
    assert result["samples"] == 3 and result["last_sample_before_end_ms"] == 300
    assert all(secret not in repr(result) for secret in ("cookie", PEER, "owner_pids"))


@pytest.mark.parametrize(("observations", "expected"), [
    ([(9.8, listing(socket_row(bytes_acked=518)))], "insufficient_coverage"),
    ([(2, listing(socket_row())), (3, listing(socket_row())), (4, listing(socket_row()))],
     "insufficient_coverage"),
    ([(9.7, listing(socket_row(owner_pids=[])))], "owner_unconfirmed"),
    ([(9.7, listing(socket_row(owner_pids=[7, PID])))], "owner_unconfirmed"),
    ([(9.6, listing(socket_row())), (9.8, listing(socket_row(socket="replacement")))],
     "ambiguous"),
    ([(9.8, listing(socket_row(bytes_acked=None)))], "tcp_info_unobserved"),
    ([(9.8, {"state": "unavailable", "sockets": []})], "socket_stats_unavailable"),
    ([(9.8, listing(socket_row(owner_pids=[7])))], "socket_unobserved"),
])
def test_tcp_observation_requires_owner_unique_socket_and_late_coverage(observations, expected):
    result = tcp.summarize(listing(), observations, peer=PEER, pid=PID, finished=10,
                           tls_timeout=True)
    assert result["state"] == expected


def test_tcp_timing_only_uses_samples_taken_in_the_transfer_window():
    observations = [
        (9.9, listing(socket_row(bytes_acked=518))),
        (10.2, listing(socket_row(bytes_sent=0))),
        (10.5, listing(socket_row())),
        (11.1, listing(socket_row(bytes_retrans=517))),
        (11.4, listing(socket_row(bytes_retrans=517, bytes_acked=518))),
        (11.6, listing(socket_row(bytes_retrans=517, bytes_acked=518,
                                  bytes_received=32, data_segs_in=1))),
        (12.1, listing(socket_row(bytes_received=64, data_segs_in=2))),
    ]
    result = tcp.summarize(listing(), observations, peer=PEER, pid=PID,
                           started=10, finished=12, tls_timeout=False)
    assert result["state"] == "tcp_data_received" and result["samples"] == 5
    assert {key: result[key] for key in tcp.TIMING_FIELDS} == {
        "first_sample_ms": 200, "largest_sample_gap_ms": 600, "first_send_ms": 500,
        "first_payload_ack_ms": 1400, "first_receive_ms": 1600, "first_retransmit_ms": 1100,
    }


def test_duplicate_rows_in_one_poll_do_not_supply_multiple_tcp_observations():
    row = socket_row(bytes_acked=518)
    result = tcp.summarize(listing(), [(9.8, listing(row, row, row))], peer=PEER, pid=PID,
                           started=0, finished=10, tls_timeout=True)
    assert result["state"] == "insufficient_coverage" and result["samples"] == 1
    assert result["largest_sample_gap_ms"] is None
    assert result["first_receive_ms"] is None and result["first_retransmit_ms"] is None


def test_tcp_sampler_uses_only_one_marked_peer_and_keeps_transfer_when_unavailable(monkeypatch):
    def run(argv, *, timeout):
        assert argv[:4] == ["sudo", "-n", "--", "ss"]
        assert argv[-7:] == ["fwmark", "=", "0x10000000", "and", "dst", "=", f"{PEER}:443"]
        assert timeout == 1
        raise CommandError("unavailable")

    monkeypatch.setattr(tcp.cmd, "run", run)
    answer = {"curl_rc": 28, "tcp": 0.01, "tls": 0}
    assert tcp.watch_transfer(PEER, PID, lambda: answer) == (
        answer, {"state": "socket_stats_unavailable"},
    )
