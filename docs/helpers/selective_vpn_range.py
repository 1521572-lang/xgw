"""Compare one contiguous versus four sequential CDN ranges through Xray http-in."""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import time
from pathlib import Path

from docs.helpers.headless_playback import read_format

MIB = 1024**2
PHASE_SECONDS = 25
SEQUENCE = ("A", "B", "B", "A")
CONTENT_RANGE = re.compile(r"bytes ([0-9]+)-([0-9]+)/(?:[0-9]+|\*)")
METRICS = ("%{http_code}\t%{size_download}\t%{time_starttransfer}\t"
           "%{time_total}\t%{http_version}\t%header{content-range}\n")


def ranges(arm):
    size = 4 * MIB if arm == "A" else MIB
    return [(offset, offset + size - 1) for offset in range(0, 4 * MIB, size)]


def parse_metrics(output, rc, first, last):
    values = output.rstrip("\r\n").split("\t")
    if len(values) != 6:
        return {"ok": False, "reason": "metrics_unavailable", "curl_rc": rc}
    status, downloaded, first_byte, total, version, raw_range = values
    status, downloaded = int(status), int(downloaded)
    first_byte, total = float(first_byte), float(total)
    if not (math.isfinite(first_byte) and math.isfinite(total) and 0 <= first_byte <= total):
        return {"ok": False, "reason": "metrics_unavailable", "curl_rc": rc}
    span = CONTENT_RANGE.fullmatch(raw_range.strip())
    exact = span is not None and tuple(map(int, span.groups())) == (first, last)
    ok = (rc == 0 and status == 206 and downloaded == last - first + 1
          and exact and version == "1.1")
    return {"ok": ok, "http": status, "bytes": downloaded, "content_range_ok": exact,
            "protocol": "1.1" if version == "1.1" else None,
            "first_byte_s": first_byte, "elapsed_s": total, "curl_rc": rc}


def fetch_range(url, port, first, last, seconds):
    quoted_url = url.replace("\\", "\\\\").replace('"', '\\"')
    try:
        proc = subprocess.run(
            ["curl", "-q", "--http1.1", "--noproxy", "", "--proxy", f"http://127.0.0.1:{port}",
             "--proto", "=https", "--connect-timeout", "6", "--max-time", f"{seconds:.3f}",
             "--max-filesize", str(last - first + 1), "--range", f"{first}-{last}",
             "--silent", "--output", "/dev/null", "--write-out", METRICS, "--config", "-"],
            input=f'url = "{quoted_url}"\n', capture_output=True, text=True,
            timeout=seconds + 2, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "process_timeout", "curl_rc": 124}
    try:
        return parse_metrics(proc.stdout, proc.returncode, first, last)
    except ValueError:
        return {"ok": False, "reason": "metrics_unavailable", "curl_rc": proc.returncode}


def measure(url, port, arm):
    started = time.monotonic()
    rows = []
    for first, last in ranges(arm):
        remaining = PHASE_SECONDS - (time.monotonic() - started)
        if remaining < 0.1:
            rows.append({"ok": False, "reason": "phase_deadline"})
            break
        row = fetch_range(url, port, first, last, remaining)
        rows.append(row)
        if not row["ok"]:
            break
    elapsed = time.monotonic() - started
    read = sum(row.get("bytes", 0) for row in rows)
    ok = len(rows) == len(ranges(arm)) and all(row["ok"] for row in rows)
    return {"arm": arm, "ok": ok, "bytes": read, "elapsed_s": round(elapsed, 3),
            "bytes_per_s": round(read / elapsed) if ok and elapsed > 0 else None,
            "requests": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("format", type=Path)
    parser.add_argument("--proxy-port", type=int, required=True)
    args = parser.parse_args()
    if not 1 <= args.proxy_port <= 65535:
        parser.error("invalid loopback proxy port")
    try:
        url, _, _ = read_format(args.format)
        arms = [measure(url, args.proxy_port, arm) for arm in SEQUENCE]
    except (OSError, ValueError, KeyError):
        print(json.dumps({"state": "unavailable", "reason": "format_or_curl"}))
        return 2
    comparable = all(arm["ok"] for arm in arms)
    print(json.dumps({"state": "comparable" if comparable else "partial", "arms": arms},
                     sort_keys=True))
    return 0 if comparable else 1


if __name__ == "__main__":
    raise SystemExit(main())
