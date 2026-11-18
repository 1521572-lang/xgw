"""Compare private pytest JUnit reports without waiving new or changed failures."""

from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_BYTES = 16 * 1024 * 1024


def read(path: Path, checkout: Path) -> dict:
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("junit_size")
    root = ET.fromstring(raw)
    if root.tag not in ("testsuite", "testsuites"):
        raise ValueError("junit_root")
    result = {}
    for case in root.iter("testcase"):
        name, group = case.get("name"), case.get("classname")
        if not name or not group:
            raise ValueError("junit_identity")
        identity = group + "::" + name
        if identity in result:
            raise ValueError("junit_duplicate")
        failures = [child for child in case if child.tag in ("failure", "error")]
        skipped = case.find("skipped")
        if len(failures) > 1 or (failures and skipped is not None):
            raise ValueError("junit_outcome")
        outcome = "passed"
        signature = None
        if failures:
            failure = failures[0]
            # Only the caller-supplied checkout prefix is normalized. Assertion
            # values, IPs, error codes and other differences remain significant.
            message = failure.get("message")
            if not message:
                raise ValueError("junit_failure_message")
            for prefix in (str(checkout.resolve()), checkout.resolve().as_posix()):
                message = message.replace(prefix, "<CHECKOUT>")
            signature = hashlib.sha256(message.encode()).hexdigest()
            outcome = failure.tag
        elif skipped is not None:
            outcome = "skipped"
        result[identity] = {"outcome": outcome, "signature": signature}
    if not result:
        raise ValueError("junit_empty")
    # A collection/internal error outside a testcase cannot be ignored.
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    for attribute, outcome in (("errors", "error"), ("failures", "failure")):
        recorded = sum(r["outcome"] == outcome for r in result.values())
        if sum(int(s.get(attribute, "0")) for s in suites) != recorded:
            raise ValueError("junit_unrepresented_error")
    return result


def compare(current: dict, baseline: dict) -> dict:
    known, changed, fresh = [], [], []
    for identity, row in current.items():
        if row["outcome"] not in ("failure", "error"):
            continue
        previous = baseline.get(identity)
        if previous is None or previous["outcome"] not in ("failure", "error"):
            fresh.append(identity)
        elif previous != row:
            changed.append(identity)
        else:
            known.append(identity)
    missing = sorted(set(baseline) - set(current))
    added = sorted(set(current) - set(baseline))
    skipped = sorted(k for k in set(current) & set(baseline)
                     if current[k]["outcome"] == "skipped"
                     and baseline[k]["outcome"] != "skipped")
    return {"ok": not (fresh or changed or missing or added or skipped),
            "matching_baseline_failures": sorted(known), "new_failures": sorted(fresh),
            "changed_failures": sorted(changed), "missing_tests": missing,
            "added_tests": added, "new_skips": skipped,
            "current_cases": len(current), "baseline_cases": len(baseline)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--current-source", type=Path, required=True)
    parser.add_argument("--baseline-source", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = compare(read(args.current, args.current_source),
                         read(args.baseline, args.baseline_source))
    except (OSError, ValueError, ET.ParseError):
        result = {"ok": False, "error": "invalid_or_incomplete_junit"}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

