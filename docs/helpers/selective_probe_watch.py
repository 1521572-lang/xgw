"""Sample Selective state, its outgoing nft counter and NFQUEUE without packet capture."""

import argparse
import json
import re
import time

from xgw import zapret2
from xgw.desync import worker
from xgw.net import cmd
from xgw.paths import Paths
from xgw.watch import status
from xgw.watch.zapret2_control import transport_probes


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


def sample(paths, queue):
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
    result = {
        "sample_at": started,
        "status_at": view.get("updated"),
        "revision": revision[:8] if isinstance(revision, str) else None,
        "state": selected.get("state"),
        "reason": selected.get("reason"),
        "generation": generation,
        "worker_invocation": worker_invocation(),
        "probes": transport_probes(selected.get("transport_probes"), now=started),
        "gate": gate(),
        "outgoing": outgoing_counter(queue),
        "queue": queue_state(queue),
    }
    result["sample_end_at"] = time.time()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=int, required=True)
    parser.add_argument("--seconds", type=int, default=75)
    args = parser.parse_args()
    if not 1 <= args.queue <= 65535 or not 1 <= args.seconds <= 180:
        parser.error("queue must be 1–65535 and seconds 1–180")
    paths = Paths.from_env()
    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        next_sample = time.monotonic() + 1
        print(json.dumps(sample(paths, args.queue), allow_nan=False), flush=True)
        time.sleep(max(0, min(next_sample, deadline) - time.monotonic()))


if __name__ == "__main__":
    main()
