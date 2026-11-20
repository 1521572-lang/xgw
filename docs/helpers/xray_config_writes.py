"""Attribute an applied Xray config to a write logged by xgw.service."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from uuid import UUID

from docs.helpers.selective_media_evidence import MAX_LOG_ROWS, read_rows
from xgw.apply.applier import WRITE_FINGERPRINT_LENGTH, ApplySource
from xgw.desync import route_evidence

RECORD = re.compile(
    r"(?:^|\s)xgw\.apply: xray_config_write source=([a-z0-9_]+) method=(api|restart|rollback)"
    rf" fingerprint=([0-9a-f]{{{WRITE_FINGERPRINT_LENGTH}}}) mono_ns=([0-9]{{1,20}})$"
)
SOURCES = frozenset(source.value for source in ApplySource)


def analyze(before, after, journal):
    if len(journal) >= MAX_LOG_ROWS:
        return {"state": "inconclusive", "reason": "journal_limit"}
    start, end = before["monotonic_ns"], after["monotonic_ns"]
    boot = UUID(before["xray_epoch"].split(":", 1)[0]).hex
    if not 0 < start < end or boot != UUID(after["xray_epoch"].split(":", 1)[0]).hex:
        return {"state": "inconclusive", "reason": "snapshot_window"}

    records = set()
    for entry in journal:
        if (entry.get("_BOOT_ID"), entry.get("_SYSTEMD_UNIT"), entry.get("_UID")) != (
            boot, "xgw.service", "0",
        ):
            continue
        message = entry.get("MESSAGE")
        match = RECORD.search(message) if isinstance(message, str) else None
        if match and match[1] in SOURCES:
            at = int(match[4])
            if start < at <= end:
                records.add((at, match[1], match[2], match[3]))

    same_bytes = before["config_sha256"] == after["config_sha256"]
    result = {
        "state": "none_observed" if same_bytes and not records else "unattributed",
        "same_config_at_boundaries": same_bytes,
        "writes": len(records),
        "by_source": dict(Counter(source for _, source, _, _ in sorted(records))),
    }
    if not records:
        return result
    most_recent = max(at for at, _, _, _ in records)
    latest = [row for row in records if row[0] == most_recent]
    fingerprint = after["config_sha256"][:WRITE_FINGERPRINT_LENGTH]
    if len(latest) == 1 and latest[0][3] == fingerprint:
        at, source, method, _ = latest[0]
        result.update(state="attributed", final_write={
            "source": source, "method": method, "offset_seconds": round((at - start) / 1e9, 3),
        })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = analyze(route_evidence._read_snapshot(args.before),
                         route_evidence._read_snapshot(args.after), read_rows(sys.stdin.buffer))
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        print(json.dumps({"state": "inconclusive", "reason": "invalid_evidence"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
