"""Summarize changes in kernel queue counters across contiguous observations."""

from collections import Counter, defaultdict

from .monitor_policy import policy_label
from .monitor_probes import MAX_SAMPLE_GAP_SECONDS, matched_policy
from .worker import monitor_queue_sample


def queue_losses(rows: list[dict]) -> dict:
    by_policy = defaultdict(Counter)
    delivery_by_policy = defaultdict(Counter)
    latest_at = -1
    previous_row = previous_sample = None
    samples = 0
    for row in rows:
        at = row["at"]
        if at <= latest_at:
            previous_row = previous_sample = None
            continue
        latest_at = at
        label = policy_label(row)
        sample = (monitor_queue_sample(row.get("queue_loss_sample"), at)
                  if label and row.get("state") == "active" and matched_policy(row, row) else None)
        if sample is not None:
            samples += 1
        if (sample is not None and previous_sample is not None
                and at - previous_row["at"] <= MAX_SAMPLE_GAP_SECONDS
                and label == policy_label(previous_row) and matched_policy(previous_row, row)
                and (sample["epoch"], sample["series"]) ==
                (previous_sample["epoch"], previous_sample["series"])):
            seconds = sample["at"] - previous_sample["at"]
            overflow = sample["overflow"] - previous_sample["overflow"]
            netlink = sample["netlink"] - previous_sample["netlink"]
            if 0 < seconds <= MAX_SAMPLE_GAP_SECONDS and overflow >= 0 and netlink >= 0:
                by_policy[label].update(intervals=1, seconds=seconds,
                                        overflow_delta=overflow, netlink_delta=netlink)
                if "packet_ids" in previous_sample and "packet_ids" in sample:
                    assigned = sample["packet_ids"] - previous_sample["packet_ids"]
                    # A delivery failure already has an ID. Queue overflow can occur earlier.
                    if assigned >= netlink:
                        delivery_by_policy[label].update(intervals=1, seconds=seconds,
                                                        assigned_ids=assigned, failed_delivery=netlink)
        previous_row, previous_sample = row, sample
    result = {"samples_with_counters": samples,
              "by_policy": {label: dict(counts) for label, counts in by_policy.items()}}
    if delivery_by_policy:
        result["netlink_delivery_by_policy"] = {
            label: {**counts, "loss_fraction": (counts["failed_delivery"] / counts["assigned_ids"]
                                               if counts["assigned_ids"] else None)}
            for label, counts in delivery_by_policy.items()
        }
    return result
