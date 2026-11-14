"""Trace evidence is scoped to one media connection and its queue."""

import runpy
from pathlib import Path

import pytest

HELPER = Path(__file__).parents[1] / "docs/helpers/nfq_video_trace.py"
queued_packets = runpy.run_path(str(HELPER))["queued_packets"]
FLOW = ("192.0.2.10", 40420, "203.0.113.25", 443)


def packet(trace_id="a1", sport=40420):
    return (
        f'trace id {trace_id} inet xgw_video_test output packet: oif "test0" '
        f"ip saddr 192.0.2.10 ip daddr 203.0.113.25 tcp sport {sport} tcp dport 443"
    )


def verdict(trace_id="a1", table="xgw_guard", queue=200, decision="queue"):
    return (
        f"trace id {trace_id} inet {table} nfq_output rule "
        f"meta mark 0x00000002 meta l4proto tcp ct packets <= 8 "
        f"queue num {queue} bypass (verdict {decision})"
    )


@pytest.mark.parametrize("statement", ["queue num 200 bypass", "queue flags bypass to 200"])
def test_same_tuple_queue_verdict_counts_once(statement):
    event = verdict().replace("queue num 200 bypass", statement + " # handle 4")
    assert queued_packets([packet(), event, event], FLOW, 200) == 1


@pytest.mark.parametrize("lines", [
    [packet(), packet("b2", 40421), verdict("b2")],
    [packet(), verdict(queue=201)],
    [packet(), verdict(table="another_table")],
    [packet(), verdict(decision="continue")],
    [verdict()],
])
def test_background_traffic_and_non_queue_events_cannot_pass(lines):
    assert queued_packets(lines, FLOW, 200) == 0


def test_ipv6_with_expanded_spelling_is_matched():
    lines = [
        "trace id a1 inet xgw_video_test output packet: "
        "ip6 saddr 2001:db8:0:0:0:0:0:10 ip6 daddr 2001:db8::20 "
        "tcp sport 40420 tcp dport 443",
        verdict().replace("queue num 200 bypass", "queue flags bypass num 200"),
    ]
    assert queued_packets(lines, ("2001:db8::10", 40420, "2001:db8::20", 443), 200) == 1
