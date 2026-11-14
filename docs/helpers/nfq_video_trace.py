"""Check a private nft trace for the exact TCP flow already identified as video."""

import argparse
import ipaddress
import re
from collections.abc import Iterable
from pathlib import Path

_EVENT = re.compile(r"^trace id ([0-9a-fA-F]+) (\w+) (\S+) (\S+) (.*)$")
_QUEUE = re.compile(r"\bqueue(?: flags bypass)? (?:num|to) (\d+)\b")
_QUEUED = re.compile(r"\(verdict queue(?: num \d+)?\)\s*$")
_PACKET = re.compile(
    r"\bip6? saddr (\S+).*?\bip6? daddr (\S+).*?"
    r"\btcp sport (\d+).*?\btcp dport (\d+)\b"
)
Flow = tuple[str, int, str, int]


def _flow(src: str, sport: int, dst: str, dport: int) -> Flow:
    source, destination = ipaddress.ip_address(src), ipaddress.ip_address(dst)
    if source.version != destination.version or not all(
        1 <= port <= 65535 for port in (sport, dport)
    ):
        raise ValueError("invalid TCP tuple")
    return (str(source), sport, str(destination), dport)


def queued_packets(lines: Iterable[str], flow: Flow, queue: int) -> int:
    """Count packet IDs showing both the tuple and a queue verdict in XGW's chain."""
    matched = set()
    counted = set()
    for line in lines:
        event = _EVENT.match(line)
        if event is None:
            continue
        trace_id, family, table, chain, body = event.groups()
        if body.startswith("packet:"):
            matched.discard(trace_id)
            packet = _PACKET.search(body)
            if packet is not None:
                src, dst, sport, dport = packet.groups()
                try:
                    if _flow(src, int(sport), dst, int(dport)) == flow:
                        matched.add(trace_id)
                except ValueError:
                    continue
        if trace_id not in matched or (family, table, chain) != (
            "inet", "xgw_guard", "nfq_output"
        ):
            continue
        rule = _QUEUE.search(body)
        if body.startswith("rule ") and rule and int(rule[1]) == queue and _QUEUED.search(body):
            counted.add(trace_id)
    return len(counted)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("src")
    parser.add_argument("sport", type=int)
    parser.add_argument("dst")
    parser.add_argument("dport", type=int)
    parser.add_argument("queue", type=int)
    args = parser.parse_args()
    try:
        flow = _flow(args.src, args.sport, args.dst, args.dport)
        if not 0 <= args.queue <= 65535:
            raise ValueError("invalid queue")
        with args.trace.open(encoding="utf-8") as trace:
            count = queued_packets(trace, flow, args.queue)
    except (OSError, ValueError):
        print("NFQ_TRACE=INVALID_INPUT")
        return 2
    print(f"NFQ_TRACE={'MATCH' if count else 'UNCONFIRMED'} packets={count}")
    return 0 if count else 1


if __name__ == "__main__":
    raise SystemExit(main())
