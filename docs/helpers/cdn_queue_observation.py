"""Read the Selected listener's queue counters around a single controlled probe."""

import json
import time

from xgw.desync import event_socket, worker
from xgw.net import cmd
from xgw.paths import Paths

MAX_BOUNDARY_GAP_NS = 4 * 10**9
MAX_WINDOW_NS = 40 * 10**9
UNKNOWN = "queue_counters_unavailable"
IDENTITY_FIELDS = ("epoch", "generation", "queue", "policy_key", "socket")
COUNTERS = ("overflow", "netlink", "packet_ids")


def snapshot(path, runner=cmd.run):
    status = event_socket.read_status(path)
    now = time.time()
    cursor = event_socket.cursor_response(status, None, 0, now)
    if cursor["state"] != "snapshot" or not cursor["events"]:
        return {"state": UNKNOWN}
    selected = status.get("zapret2")
    if not isinstance(selected, dict) or selected.get("state") != "active":
        return {"state": UNKNOWN}
    expires = selected.get("valid_until")
    if type(expires) not in (int, float) or not now < expires < 1e11:
        return {"state": UNKNOWN}
    lease = status.get("zapret2_reservation")
    latest = cursor["events"][-1]
    if (not isinstance(lease, dict) or lease.get("unit") != worker.SELECTED_UNIT
            or latest["phase"] not in ("owner_verified", "queue_drops")
            or any(lease.get(key) != latest[key] for key in ("unit", "generation", "queue"))
            or latest["policy_key"] is None
            or latest["policy_key"] != status.get("zapret2_policy_key")):
        return {"state": UNKNOWN}
    owner = worker.owner_sample(runner, worker.SELECTED_UNIT, lease["queue"])
    if owner is None or owner.counters is None:
        return {"state": UNKNOWN}
    owner_changes = [item["seq"] for item in cursor["events"]
                     if item["phase"] in ("reserved", "owner_verified", "owner_unverified", "released")]
    return {
        "state": "observed", "monotonic_ns": time.monotonic_ns(),
        "epoch": cursor["epoch"], "last_seq": cursor["last_seq"],
        "owner_change": max(owner_changes, default=cursor["discarded"]),
        "generation": lease["generation"], "queue": lease["queue"],
        "policy_key": latest["policy_key"], "socket": owner.socket,
        **dict(zip(COUNTERS, owner.counters, strict=True)),
    }


def summarize(before, after, request):
    if before.get("state") != "observed" or after.get("state") != "observed":
        return {"state": UNKNOWN}
    boundary = (before.get("monotonic_ns"), request.get("started_monotonic_ns"),
                request.get("finished_monotonic_ns"), after.get("monotonic_ns"))
    if not all(type(value) is int and value > 0 for value in boundary):
        return {"state": "probe_window_unconfirmed"}
    left, start, end, right = boundary
    if not (0 < end - start and 0 <= start - left <= MAX_BOUNDARY_GAP_NS
            and 0 <= right - end <= MAX_BOUNDARY_GAP_NS and right - left <= MAX_WINDOW_NS):
        return {"state": "probe_window_unconfirmed"}
    if (any(before.get(key) is None or before[key] != after.get(key) for key in IDENTITY_FIELDS)
            or any(type(row.get(key)) is not int for row in (before, after)
                   for key in ("last_seq", "owner_change"))
            or not (0 <= before["owner_change"] <= after["owner_change"]
                    <= before["last_seq"] <= after["last_seq"])):
        return {"state": "queue_owner_changed"}
    if not all(type(row.get(key)) is int and 0 <= row[key] <= worker.COUNTER_MAX
               for row in (before, after) for key in COUNTERS):
        return {"state": UNKNOWN}
    overflow, netlink, packet_ids = (after[key] - before[key] for key in COUNTERS)
    if min(overflow, netlink, packet_ids) < 0 or netlink > packet_ids:
        return {"state": "queue_counters_reset"}
    return {
        "state": "observed", "seconds": round((right - left) / 1e9, 3),
        "overflow_delta": overflow, "netlink_delta": netlink, "assigned_ids": packet_ids,
        "netlink_loss_fraction": netlink / packet_ids if packet_ids else None,
    }


def main():
    try:
        result = snapshot(Paths.from_env().status_file)
    except (OSError, TypeError, ValueError, cmd.CommandError):
        result = {"state": UNKNOWN}
    print(json.dumps(result))
    return 0 if result["state"] == "observed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
