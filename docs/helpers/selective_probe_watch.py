"""Sample Selective state, its outgoing nft counter and NFQUEUE without packet capture."""

import argparse
import ipaddress
import json
import re
import time

from xgw import zapret2
from xgw.desync import route_evidence, worker
from xgw.net import cmd
from xgw.paths import LockTimeout, Paths
from xgw.watch import status
from xgw.watch.zapret2_control import transport_probes

TCP_FIELDS = ("bytes_sent", "bytes_acked", "bytes_received", "bytes_retrans", "data_segs_in")
MAX_SOCKETS = 32
MEDIA_INTERVAL = 3
MAX_PAIR_SECONDS = 10
SOCKET_INTERVAL = 0.4


def nft_rows(kind, name):
    try:
        return json.loads(cmd.run(
            ["nft", "-j", "list", kind, "inet", "xgw_guard", name], timeout=1
        ))["nftables"]
    except (cmd.CommandError, ValueError, KeyError):
        return []


def mark_value(item):
    if isinstance(item, dict):
        item = item.get("elem", {}).get("val")
    if type(item) is int:
        return item
    if isinstance(item, str):
        try:
            return int(item, 0)
        except ValueError:
            pass
    return None


def gate():
    for row in nft_rows("set", zapret2.LIVE):
        if (entry := row.get("set")) and entry.get("name") == zapret2.LIVE:
            values = [mark_value(item) for item in entry.get("elem", [])]
            if None in values:
                return None
            return {"marked": zapret2.MARK in values, "fake": zapret2.FAKE_MARK in values}
    return None


def outgoing_counter(queue):
    counters = []
    for row in nft_rows("chain", "zapret2_queue"):
        rule = row.get("rule", {})
        exprs = rule.get("expr", [])
        if not any(expr.get("queue", {}).get("num") == queue for expr in exprs):
            continue
        counters.extend({"handle": rule.get("handle"), **expr["counter"]}
                        for expr in exprs if "counter" in expr)
    if len(counters) == 1:
        counter = counters[0]
        return {key: counter.get(key) for key in ("handle", "packets", "bytes")}
    return None


def queue_state(queue):
    try:
        rows = worker.QUEUE_STATE.read_text().splitlines()
    except OSError:
        return None
    for row in rows:
        fields = row.split()
        if len(fields) < 8 or fields[0] != str(queue):
            continue
        try:
            return dict(zip(
                ("peer", "backlog", "kernel_drops", "socket_drops", "sequence"),
                (int(fields[index]) for index in (1, 2, 5, 6, 7)), strict=True,
            ))
        except ValueError:
            return None
    return None


def worker_invocation():
    try:
        value = cmd.run(
            ["systemctl", "show", worker.SELECTED_UNIT, "-p", "InvocationID", "--value"],
            timeout=1,
        ).strip()
    except cmd.CommandError:
        return None
    return value if re.fullmatch(r"[0-9a-f]{32}", value) and int(value, 16) else None


def parse_socket_stats(text, *, include_local_endpoint=False):
    sockets = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if len(sockets) == MAX_SOCKETS:
            return {"state": "too_many_sockets", "sockets": []}
        fields = line.split(maxsplit=5)
        if len(fields) != 6:
            raise ValueError("invalid socket row")
        state, _, _, local, remote, details = fields
        address, sep, port = remote.rpartition(":")
        if not sep or port != "443":
            raise ValueError("invalid socket destination")
        peer = ipaddress.ip_address(address.removeprefix("[").removesuffix("]"))
        if isinstance(peer, ipaddress.IPv6Address) and peer.ipv4_mapped:
            peer = peer.ipv4_mapped
        match = re.search(r"(?:^|\s)sk:([a-f0-9]+)(?=\s|$)", details)
        if match is None:
            raise ValueError("missing socket cookie")
        tcp_info = re.search(r"(?:^|\s)rto:\d+(?=\s|$)", details) is not None
        metrics = {}
        for name in TCP_FIELDS:
            value = re.search(rf"(?:^|\s){name}:(\d+)(?=\s|$)", details)
            metrics[name] = int(value[1]) if value else (0 if tcp_info else None)
        retrans = re.search(r"(?:^|\s)retrans:\d+/(\d+)(?=\s|$)", details)
        metrics["retrans_total"] = int(retrans[1]) if retrans else (0 if tcp_info else None)
        row = {"socket": match[1], "peer_ip": str(peer), "state": state, **metrics}
        if include_local_endpoint:
            row["local_endpoint"] = local
        owners = re.findall(r"\bpid=([1-9][0-9]*),", details)
        if owners:
            row["owner_pids"] = sorted({int(pid) for pid in owners})
        sockets.append(row)
    return {"state": "read", "sockets": sockets}


def socket_stats(*, owners=False):
    try:
        flags = "-HtaOeinp" if owners else "-HtaOein"
        text = cmd.run(["ss", flags, "state", "big", "fwmark", "=", hex(zapret2.MARK),
                        "and", "dport", "=", ":443"], timeout=1)
        return parse_socket_stats(text)
    except cmd.CommandError:
        return {"state": "unavailable", "sockets": []}
    except ValueError:
        return {"state": "unexpected_format", "sockets": []}


def sample(paths, queue, *, sockets=False):
    started = time.time()
    try:
        view = status.read_status(paths, max_age=60) or {}
    except (ValueError, TypeError):
        view = {}
    selected = view.get("zapret2", {})
    if not isinstance(selected, dict):
        selected = {}
    lease = view.get("zapret2_reservation")
    generation = lease.get("generation") if isinstance(lease, dict) else None
    revision = view.get("zapret2_policy_key")
    invocation = worker_invocation()
    queue_start = time.time()
    live, outgoing, queued = gate(), outgoing_counter(queue), queue_state(queue)
    result = {
        "sample_at": started,
        "status_at": view.get("updated"),
        "revision": revision[:8] if isinstance(revision, str) else None,
        "state": selected.get("state"),
        "reason": selected.get("reason"),
        "generation": generation,
        "worker_invocation": invocation,
        "probes": transport_probes(selected.get("transport_probes"), now=started),
        "gate": live,
        "outgoing": outgoing,
        "queue": queued,
        "queue_start_unix": queue_start,
        "queue_end_unix": time.time(),
    }
    if sockets:
        result["tcp_at"] = time.time()
        result["tcp"] = socket_stats()
    result["sample_end_at"] = time.time()
    return result


def media_sample(paths, queue, *, sockets=False):
    row = sample(paths, queue, sockets=sockets)
    row["route"] = None
    if row["state"] != "active":
        row["route_error"] = "selective_not_active"
        return row
    try:
        snapshot = route_evidence.snapshot(paths.xray_config_file, paths=paths)
    except route_evidence.EvidenceError as exc:
        row["route_error"] = str(exc)
    except LockTimeout:
        row["route_error"] = "apply_in_progress"
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, IndexError, AttributeError,
            cmd.CommandError):
        row["route_error"] = "read_failed"
    else:
        invocation = row["worker_invocation"]
        if invocation and invocation == worker_invocation():
            row["route"] = snapshot
            row["queue_owner_confirmed"] = worker.verify_owner(cmd.run, worker.SELECTED_UNIT, queue)
        else:
            row["route_error"] = "worker_changed"
    return row


def media_pair(before, after):
    previous, current = before["route"], after["route"]
    if not (previous and current):
        return {"state": "rejected", "reason": "route_sample_missing"}
    if (not before["revision"] or not before["worker_invocation"]
            or before["revision"] != after["revision"]
            or before["worker_invocation"] != after["worker_invocation"]):
        return {"state": "rejected", "reason": "policy_or_worker_changed"}
    if not (previous["client_zapret2_rule"] and current["client_zapret2_rule"]):
        return {"state": "rejected", "reason": "client_rule_inactive"}
    try:
        change = route_evidence.deltas(previous, current)
    except route_evidence.EvidenceError as exc:
        return {"state": "rejected", "reason": str(exc), **exc.details()}
    if current["monotonic_ns"] - previous["monotonic_ns"] > MAX_PAIR_SECONDS * 10**9:
        return {"state": "rejected", "reason": "sample_gap"}
    if not all((row["gate"] or {}).get("marked") is True for row in (before, after)):
        return {"state": "rejected", "reason": "gate_unconfirmed"}
    start = max(previous["unix"], before["queue_end_unix"])
    end = min(current["unix"], after["queue_start_unix"])
    if not 0 < end - start <= MAX_PAIR_SECONDS:
        return {"state": "rejected", "reason": "no_shared_window"}

    first_rule, last_rule = before["outgoing"], after["outgoing"]
    first_queue, last_queue = before["queue"], after["queue"]
    if not all((first_rule, last_rule, first_queue, last_queue)):
        return {"state": "rejected", "reason": "queue_sample_missing"}
    handle, peer = first_rule["handle"], first_queue["peer"]
    first_packets, last_packets = first_rule["packets"], last_rule["packets"]
    if (type(handle) is not int or handle != last_rule["handle"] or peer != last_queue["peer"]
            or type(first_packets) is not int or type(last_packets) is not int
            or not 0 <= first_packets <= last_packets
            or first_queue["sequence"] > last_queue["sequence"]):
        return {"state": "rejected", "reason": "queue_changed"}

    return {"state": "accepted", "start_unix": start, "end_unix": end,
            "queue_seconds": after["queue_end_unix"] - before["queue_end_unix"],
            "nft_packets": last_packets - first_packets,
            "queue_sequence_delta": last_queue["sequence"] - first_queue["sequence"],
            "probe_after": after["probes"].get("page", {}).get("started_at"),
            "probe_before": before["probes"].get("page", {}).get("started_at"), **change}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=int)
    parser.add_argument("--seconds", type=int, default=75)
    parser.add_argument("--socket-stats", action="store_true",
                        help="include TCP counters and private peer IPs in the local file")
    parser.add_argument("--media-pairs", action="store_true",
                        help="sample Xray counters with the queue and compare adjacent readings")
    parser.add_argument("--marked-sockets", action="store_true",
                        help="sample marked sockets and owner PIDs independently of counters")
    args = parser.parse_args()
    if not 1 <= args.seconds <= 180:
        parser.error("seconds must be 1–180")
    if args.marked_sockets:
        if args.queue is not None or args.socket_stats or args.media_pairs:
            parser.error("--marked-sockets is a standalone collection mode")
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            tick = time.monotonic()
            start = time.time()
            details = socket_stats(owners=True)
            print(json.dumps({"socket_start_unix": start, "socket_unix": time.time(),
                              "sockets": details["sockets"], "state": details["state"]}),
                  flush=True)
            time.sleep(max(0, min(deadline, tick + SOCKET_INTERVAL) - time.monotonic()))
        return
    if args.queue is None or not 1 <= args.queue <= 65535:
        parser.error("queue must be 1–65535 and seconds 1–180")
    paths = Paths.from_env()
    deadline = time.monotonic() + args.seconds
    previous = None
    while time.monotonic() < deadline:
        interval = MEDIA_INTERVAL if args.media_pairs else 1
        next_sample = time.monotonic() + interval
        if args.media_pairs:
            row = media_sample(paths, args.queue, sockets=args.socket_stats)
            if previous is not None:
                row["media_pair"] = media_pair(previous, row)
            previous = row
        else:
            row = sample(paths, args.queue, sockets=args.socket_stats)
        print(json.dumps(row, allow_nan=False), flush=True)
        time.sleep(max(0, min(next_sample, deadline) - time.monotonic()))


if __name__ == "__main__":
    main()
