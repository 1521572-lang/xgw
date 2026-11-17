"""Read per-outbound Xray byte counters for controlled gateway experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from ..generator.singbox import bridge_variant
from ..net import cmd
from ..paths import Paths
from ..xraycore import metrics
from ..zapret2 import OUT, active
from .experiment import private_path

GROUPS = ("zapret2", "xray", "sing-box")
DIRECTIONS = ("uplink", "downlink")
MAX_CONFIG_BYTES = 16 * 1024 * 1024


class EvidenceError(ValueError):
    """A public reason code that contains no configuration details."""


def counters(applied: dict, sample: dict) -> dict:
    stats = sample.get("stats")
    outbound = stats.get("outbound") if isinstance(stats, dict) else None
    if not isinstance(outbound, dict):
        raise EvidenceError("outbound_counters_unavailable")
    result = {}
    for entry in applied["outbounds"]:
        tag = entry.get("tag", "")
        if tag == OUT:
            group = "zapret2"
        elif tag.startswith(("proxy-", "spare-", "pool-")):
            group = "sing-box" if bridge_variant(entry) else "xray"
        else:
            continue
        total = outbound.get(tag)
        result[tag] = {"group": group}
        for direction in DIRECTIONS:
            count = total.get(direction) if isinstance(total, dict) else None
            result[tag][direction] = count if type(count) is int and count >= 0 else None
    return result


def deltas(before: dict, after: dict) -> dict:
    start_time, end_time = before["monotonic_ns"], after["monotonic_ns"]
    if (before["xray_epoch"] != after["xray_epoch"]
            or before["config_sha256"] != after["config_sha256"]
            or type(start_time) is not int or type(end_time) is not int
            or not 0 < start_time < end_time
            or before["tags"].keys() != after["tags"].keys()):
        raise EvidenceError("incomparable_snapshots")
    totals = {group: {key: [] for key in DIRECTIONS} for group in GROUPS}
    unknown = dict.fromkeys(GROUPS, 0)
    for tag, end in after["tags"].items():
        start = before["tags"][tag]
        group = end["group"]
        if group != start["group"]:
            raise EvidenceError("incomparable_snapshots")
        if any(start[key] is None or end[key] is None for key in DIRECTIONS):
            unknown[group] += 1
        for key in DIRECTIONS:
            first, last = start[key], end[key]
            if first is None or last is None:
                continue
            if type(first) is not int or type(last) is not int or not 0 <= first <= last:
                raise EvidenceError("counter_reset_or_invalid")
            totals[group][key].append(last - first)
    return {
        "client_zapret2_rule": after["client_zapret2_rule"],
        "seconds": round((end_time - start_time) / 1e9, 3),
        "groups": {
            group: {**{key: sum(values) if values else None for key, values in info.items()},
                    "tags_with_unknown_counters": unknown[group]}
            for group, info in totals.items()
        },
    }


def _xray_epoch() -> str:
    pid = int(cmd.run(["systemctl", "show", "xgw-xray.service", "-p", "MainPID", "--value"],
                      timeout=4).strip())
    if pid <= 0:
        raise EvidenceError("xray_not_running")
    # Split after comm, which can itself contain spaces or parentheses.
    started = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    return f"{boot}:{pid}:{started}"


def _read_config(path: Path) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(MAX_CONFIG_BYTES + 1)
    if len(raw) > MAX_CONFIG_BYTES:
        raise EvidenceError("applied_config_too_large")
    return raw


def snapshot(path: Path) -> dict:
    epoch = _xray_epoch()
    raw = _read_config(path)
    applied = json.loads(raw)
    host, _, port = applied["metrics"]["listen"].rpartition(":")
    if host != "127.0.0.1" or not 1 <= int(port) <= 65535:
        raise EvidenceError("metrics_not_on_loopback")
    sample = metrics.fetch_metrics(int(port))
    when = time.monotonic_ns()
    if raw != _read_config(path) or epoch != _xray_epoch():
        raise EvidenceError("snapshot_changed_during_read")
    return {"xray_epoch": epoch, "config_sha256": hashlib.sha256(raw).hexdigest(),
            "monotonic_ns": when, "client_zapret2_rule": active(applied),
            "tags": counters(applied, sample)}


def _read_snapshot(path: Path) -> dict:
    private_path(path)
    with path.open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise EvidenceError("snapshot_too_large")
    return json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    read = actions.add_parser("snapshot")
    read.add_argument("--xray-config", type=Path, default=Paths.from_env().xray_config_file)
    diff = actions.add_parser("delta")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "snapshot":
            result = snapshot(args.xray_config)
        else:
            result = deltas(_read_snapshot(args.before), _read_snapshot(args.after))
    except EvidenceError as exc:
        print(json.dumps({"state": "route_counters_unavailable", "reason": str(exc)}))
        return 2
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError, IndexError,
            cmd.CommandError):
        print('{"state":"route_counters_unavailable","reason":"read_failed"}')
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
