"""Observe only the new marked Xray socket during one CDN request."""

import threading
import time
from itertools import pairwise

from xgw import zapret2
from xgw.net import cmd

INTERVAL = 0.25
MAX_SAMPLES = 64
MAX_WINDOW = 16
LATE_SAMPLE_SECONDS = 1.0
MIN_OBSERVATIONS = 3
FIELDS = ("bytes_sent", "bytes_acked", "bytes_received", "bytes_retrans",
          "data_segs_in", "retrans_total")
TIMING_FIELDS = (
    "first_sample_ms", "largest_sample_gap_ms", "first_send_ms", "first_payload_ack_ms",
    "first_receive_ms", "first_retransmit_ms",
)
POLL_FIELDS = ("established_polls", "syn_sent_only_polls", "established_polls_without_tcp_info")


def read_sockets(peer):
    from docs.helpers.selective_probe_watch import parse_socket_stats

    try:
        rows = cmd.run(
            ["sudo", "-n", "--", "ss", "-HtaOeinp", "state", "big",
             "fwmark", "=", hex(zapret2.MARK), "and", "dst", "=", f"{peer}:443"],
            timeout=1,
        )
        return parse_socket_stats(rows)
    except (cmd.CommandError, OSError, ValueError):
        return {"state": "unavailable", "sockets": []}


def snapshot_pid(path):
    from xgw.desync.route_evidence import _read_snapshot

    try:
        pid = int(_read_snapshot(path)["xray_epoch"].split(":")[1])
    except (OSError, ValueError, IndexError, KeyError, TypeError):
        return None
    return pid if pid > 0 else None


def _sample_timing(samples, started):
    first_sample = samples[0][0]
    return {
        "first_sample_ms": round((first_sample - started) * 1000),
        "largest_sample_gap_ms": _largest_sample_gap_ms(samples),
        **{
            label: next((round((at - started) * 1000) for at, row in samples if criterion(row)),
                        None)
            for label, criterion in (
                ("first_send_ms", lambda row: row["bytes_sent"] > 0),
                ("first_payload_ack_ms", lambda row: row["bytes_acked"] > 1),
                ("first_receive_ms",
                 lambda row: row["bytes_received"] > 0 and row["data_segs_in"] > 0),
                ("first_retransmit_ms", lambda row: row["bytes_retrans"] > 0),
            )
        },
    }


def _largest_sample_gap_ms(samples):
    return max((round((late[0] - early[0]) * 1000) for early, late in pairwise(samples)),
               default=None)


def summarize(baseline, observations, *, peer, pid, finished, tls_timeout, started=None):
    observations = [(at, row) for at, row in observations
                    if at <= finished and (started is None or started <= at)]
    if baseline["state"] != "read" or any(row["state"] != "read" for _, row in observations):
        return {"state": "socket_stats_unavailable"}
    existing = {row["socket"] for row in baseline["sockets"]}
    candidates = set()
    samples = []
    syn_samples = []
    unowned = False
    established_polls = 0
    for observed, listing in observations:
        established = False
        syn_sent = None
        measured = set()
        for row in listing["sockets"]:
            if (row["socket"] in existing or row["peer_ip"] != peer
                    or row["state"] not in ("ESTAB", "SYN-SENT")):
                continue
            owners = row.get("owner_pids")
            if not owners or (pid in owners and owners != [pid]):
                unowned = True
            if owners != [pid]:
                continue
            candidates.add(row["socket"])
            established |= row["state"] == "ESTAB"
            if row["state"] == "SYN-SENT" and syn_sent is None:
                syn_sent = row
            if (row["state"] == "ESTAB" and row["socket"] not in measured
                    and all(type(row.get(key)) is int for key in FIELDS)):
                measured.add(row["socket"])
                samples.append((observed, row))
        established_polls += established
        if syn_sent is not None and not established:
            syn_samples.append((observed, syn_sent))
    if len(candidates) > 1:
        return {"state": "ambiguous"}
    if unowned:
        return {"state": "owner_unconfirmed"}
    if not candidates:
        return {"state": "socket_unobserved"}
    coverage = {
        "established_polls": established_polls,
        "syn_sent_only_polls": len(syn_samples),
        "established_polls_without_tcp_info": established_polls - len(samples),
    }
    if not samples:
        if syn_samples and established_polls == 0:
            last_at, last_syn = syn_samples[-1]
            elapsed = finished - last_at
            state = ("syn_sent_without_established" if tls_timeout
                     and len(syn_samples) >= MIN_OBSERVATIONS
                     and elapsed <= LATE_SAMPLE_SECONDS else "insufficient_coverage")
            retrans = last_syn.get("retrans_total")
            return {"state": state, **coverage,
                    "last_syn_sent_before_end_ms": round(elapsed * 1000),
                    "largest_sample_gap_ms": _largest_sample_gap_ms(syn_samples),
                    "syn_sent_retrans_total": retrans if type(retrans) is int else None}
        return {"state": "tcp_info_unobserved", **coverage}

    last_at, counters = samples[-1]
    late_gap = max(0, finished - last_at)
    result = {"samples": len(samples), "last_sample_before_end_ms": round(late_gap * 1000),
              **{key: counters[key] for key in FIELDS}}
    if started is not None:
        result.update(_sample_timing(samples, started))
    if counters["bytes_received"] > 0 and counters["data_segs_in"] > 0:
        state = "tcp_data_received"
    elif not tls_timeout or late_gap > LATE_SAMPLE_SECONDS or len(samples) < MIN_OBSERVATIONS:
        state = "insufficient_coverage"
    elif not counters["bytes_sent"]:
        state = "send_unobserved"
    elif counters["bytes_acked"] > 1:
        state = "ack_without_tcp_data"
    elif counters["bytes_retrans"] > 0:
        state = "retransmit_without_payload_ack"
    else:
        state = "ack_inconclusive"
    return {"state": state, **result, **coverage}


def watch_transfer(peer, pid, transfer):
    baseline = read_sockets(peer)
    if baseline["state"] != "read":
        return transfer(), {"state": "socket_stats_unavailable"}

    stop = threading.Event()
    observations = []
    started = time.monotonic()
    deadline = started + MAX_WINDOW

    def collect():
        for _ in range(MAX_SAMPLES):
            if stop.is_set() or time.monotonic() >= deadline:
                return
            result = read_sockets(peer)
            observed_at = time.monotonic()
            if observed_at > deadline:
                return
            observations.append((observed_at, result))
            if result["state"] != "read" or stop.wait(INTERVAL):
                return

    watcher = threading.Thread(target=collect)
    watcher.start()
    try:
        result = transfer()
        finished = time.monotonic()
    finally:
        stop.set()
        watcher.join()
    tls_timeout = (result.get("curl_rc") == 28 and bool(result.get("tcp"))
                   and not result.get("tls"))
    return result, summarize(baseline, observations, peer=peer, pid=pid, started=started,
                             finished=finished, tls_timeout=tls_timeout)
