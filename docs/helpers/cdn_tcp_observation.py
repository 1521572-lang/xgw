"""Observe only the new marked Xray socket during one CDN request."""

import threading
import time

from xgw import zapret2
from xgw.net import cmd

INTERVAL = 0.25
MAX_SAMPLES = 64
MAX_WINDOW = 16
LATE_SAMPLE_SECONDS = 1.0
FIELDS = ("bytes_sent", "bytes_acked", "bytes_received", "bytes_retrans",
          "data_segs_in", "retrans_total")


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


def summarize(baseline, observations, *, peer, pid, finished, tls_timeout):
    observations = [(at, row) for at, row in observations if at <= finished]
    if baseline["state"] != "read" or any(row["state"] != "read" for _, row in observations):
        return {"state": "socket_stats_unavailable"}
    existing = {row["socket"] for row in baseline["sockets"]}
    candidates = set()
    samples = []
    unowned = False
    for observed, listing in observations:
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
            if row["state"] == "ESTAB" and all(type(row.get(key)) is int for key in FIELDS):
                samples.append((observed, row))
    if len(candidates) > 1:
        return {"state": "ambiguous"}
    if unowned:
        return {"state": "owner_unconfirmed"}
    if not candidates:
        return {"state": "socket_unobserved"}
    if not samples:
        return {"state": "tcp_info_unobserved"}

    last_at, counters = samples[-1]
    late_gap = max(0, finished - last_at)
    result = {"samples": len(samples), "last_sample_before_end_ms": round(late_gap * 1000),
              **{key: counters[key] for key in FIELDS}}
    if counters["bytes_received"] > 0 and counters["data_segs_in"] > 0:
        state = "tcp_data_received"
    elif not tls_timeout or late_gap > LATE_SAMPLE_SECONDS or len(samples) < 3:
        state = "insufficient_coverage"
    elif not counters["bytes_sent"]:
        state = "send_unobserved"
    elif counters["bytes_acked"] > 1:
        state = "ack_without_tcp_data"
    elif counters["bytes_retrans"] > 0:
        state = "retransmit_without_payload_ack"
    else:
        state = "ack_inconclusive"
    return {"state": state, **result}


def watch_transfer(peer, pid, transfer):
    baseline = read_sockets(peer)
    if baseline["state"] != "read":
        return transfer(), {"state": "socket_stats_unavailable"}

    stop = threading.Event()
    observations = []
    deadline = time.monotonic() + MAX_WINDOW

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
    return result, summarize(baseline, observations, peer=peer, pid=pid, finished=finished,
                             tls_timeout=tls_timeout)
