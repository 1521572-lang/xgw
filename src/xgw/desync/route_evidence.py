"""Read per-outbound Xray byte counters for controlled gateway experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from ..generator.singbox import bridge_variant
from ..net import cmd
from ..paths import LockTimeout, Paths, file_lock
from ..xraycore import metrics
from ..zapret2 import OUT, active
from .experiment import private_path

GROUPS = ("zapret2", "xray", "sing-box")
DIRECTIONS = ("uplink", "downlink")
MAX_CONFIG_BYTES = 16 * 1024 * 1024


class EvidenceError(ValueError):
    """A public reason code that contains no configuration details."""

    def __init__(self, reason: str, *, field: str | None = None):
        super().__init__(reason)
        self.field = field


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("duplicate_config_key")
        result[key] = value
    return result


def _config_identity(raw: bytes) -> tuple[dict, str]:
    applied = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(applied, dict):
        raise EvidenceError("invalid_applied_config")
    # Object order and whitespace are formatting. Array order can change routing priority.
    canonical = json.dumps(applied, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return applied, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    before_config = before.get("config_semantic_sha256")
    after_config = after.get("config_semantic_sha256")
    same_bytes = before["config_sha256"] == after["config_sha256"]
    # Legacy snapshots only recorded the byte hash. Keep their stricter comparison.
    same_config = (before_config == after_config if before_config and after_config else same_bytes)
    if before["xray_epoch"] != after["xray_epoch"]:
        raise EvidenceError("incomparable_snapshots", field="xray_epoch")
    if not same_config or before["client_zapret2_rule"] != after["client_zapret2_rule"]:
        raise EvidenceError("incomparable_snapshots", field="applied_config")
    if type(start_time) is not int or type(end_time) is not int or not 0 < start_time < end_time:
        raise EvidenceError("incomparable_snapshots", field="interval")
    if before["tags"].keys() != after["tags"].keys():
        raise EvidenceError("incomparable_snapshots", field="outbound_tags")
    totals = {group: {key: [] for key in DIRECTIONS} for group in GROUPS}
    unknown = dict.fromkeys(GROUPS, 0)
    for tag, end in after["tags"].items():
        start = before["tags"][tag]
        group = end["group"]
        if group != start["group"]:
            raise EvidenceError("incomparable_snapshots", field="outbound_groups")
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
        "config_bytes_changed": not same_bytes,
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


def snapshot(path: Path, *, paths: Paths | None = None) -> dict:
    paths = paths or Paths.from_env()
    # Keep the applied config and live API state in the same transaction while reading metrics.
    with file_lock(paths.lock_file, timeout=1):
        if paths.api_dirty_file.exists():
            raise EvidenceError("xray_api_state_uncertain")
        epoch = _xray_epoch()
        raw = _read_config(path)
        applied, identity = _config_identity(raw)
        host, _, port = applied["metrics"]["listen"].rpartition(":")
        if host != "127.0.0.1" or not 1 <= int(port) <= 65535:
            raise EvidenceError("metrics_not_on_loopback")
        sample = metrics.fetch_metrics(int(port), timeout=2)
        when = time.monotonic_ns()
        if raw != _read_config(path) or epoch != _xray_epoch():
            raise EvidenceError("snapshot_changed_during_read")
    return {"xray_epoch": epoch, "config_sha256": hashlib.sha256(raw).hexdigest(),
            "config_semantic_sha256": identity,
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
    exit_code = 2
    try:
        if args.action == "snapshot":
            result = snapshot(args.xray_config)
        else:
            result = deltas(_read_snapshot(args.before), _read_snapshot(args.after))
    except EvidenceError as exc:
        result = {"state": "route_counters_unavailable", "reason": str(exc)}
        if exc.field is not None:
            result["field"] = exc.field
    except LockTimeout:
        result = {"state": "route_counters_unavailable", "reason": "apply_in_progress"}
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError, IndexError,
            cmd.CommandError):
        result = {"state": "route_counters_unavailable", "reason": "read_failed"}
    else:
        exit_code = 0
    print(json.dumps(result, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
