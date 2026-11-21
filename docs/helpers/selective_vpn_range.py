"""Compare one contiguous versus four sequential CDN ranges through Xray http-in."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import selectors
import statistics
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path

from docs.helpers.headless_playback import read_format

MIB = 1024**2
PHASE_SECONDS = 25
SEQUENCE = ("A", "B", "B", "A")
PROFILE_BYTES = 24 * MIB
PROFILE_SECONDS = 135
BUCKET_SECONDS = 5
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


def curl_request(url, port, first, last, seconds, *, output="/dev/null", metrics=METRICS):
    quoted_url = url.replace("\\", "\\\\").replace('"', '\\"')
    buffering = ["--no-buffer"] if output == "-" else []
    return (
        ["curl", "-q", *buffering, "--http1.1", "--noproxy", "", "--proxy", f"http://127.0.0.1:{port}",
         "--proto", "=https", "--connect-timeout", "6", "--max-time", f"{seconds:.3f}",
         "--max-filesize", str(last - first + 1), "--range", f"{first}-{last}",
         "--silent", "--output", output, "--write-out", metrics, "--config", "-"],
        f'url = "{quoted_url}"\n',
    )


def fetch_range(url, port, first, last, seconds):
    command, request = curl_request(url, port, first, last, seconds)
    try:
        proc = subprocess.run(
            command, input=request, capture_output=True, text=True, timeout=seconds + 2, check=False,
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


def summarize_profile(metrics, counts, body_seconds, bitrate):
    complete = int(body_seconds // BUCKET_SECONDS)
    valid = (metrics.get("http") == 206 and metrics.get("content_range_ok") is True
             and metrics["protocol"] == "1.1" and metrics["bytes"] == sum(counts.values())
             and 0 < metrics["bytes"] <= PROFILE_BYTES
             and (metrics["ok"] or metrics["curl_rc"] == 28))
    early = counts.get(0, 0) // BUCKET_SECONDS if valid and complete else None
    tail = [counts.get(index, 0) for index in range(1, complete)]
    late = statistics.median(tail[-3:]) / BUCKET_SECONDS if valid and len(tail) >= 3 else None
    return {
        "state": "profiled" if late is not None else "short" if valid else "partial",
        "request": metrics, "body_seconds": round(body_seconds, 3),
        "complete_bucket_bytes": [counts.get(index, 0) for index in range(complete)] if valid else [],
        "first_5s_Bps": early, "late_15s_median_Bps": late, "bitrate_bps": bitrate,
        "late_to_bitrate": round(late * 8 / bitrate, 3) if late is not None and bitrate else None,
    }


def profile(url, port, bitrate):
    command, request = curl_request(url, port, 0, PROFILE_BYTES - 1, PROFILE_SECONDS,
                                    output="-", metrics="%{stderr}" + METRICS)
    counts = Counter()
    first_body = None
    deadline = time.monotonic() + PROFILE_SECONDS + 3
    with tempfile.TemporaryFile() as trailer, subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=trailer,
    ) as proc, selectors.DefaultSelector() as selector:
        try:
            with proc.stdin:
                proc.stdin.write(request.encode("ascii"))
            selector.register(proc.stdout, selectors.EVENT_READ)
            while (remaining := deadline - time.monotonic()) > 0 and selector.select(remaining):
                chunk = os.read(proc.stdout.fileno(), 65536)
                observed = time.monotonic()
                if not chunk:
                    break
                if first_body is None:
                    first_body = observed
                counts[int((observed - first_body) // BUCKET_SECONDS)] += len(chunk)
            else:
                raise subprocess.TimeoutExpired("curl", PROFILE_SECONDS)
            rc = proc.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return {"state": "partial", "reason": "process_timeout"}
        except BaseException:
            proc.kill()
            proc.wait()
            raise
        trailer.seek(0)
        try:
            metrics = parse_metrics(trailer.read(4096).decode("ascii", errors="replace"),
                                    rc, 0, PROFILE_BYTES - 1)
        except ValueError:
            metrics = {"ok": False, "reason": "metrics_unavailable", "curl_rc": rc}
    body_seconds = observed - first_body if first_body is not None else 0.0
    return summarize_profile(metrics, counts, body_seconds, bitrate)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("format", type=Path)
    parser.add_argument("--proxy-port", type=int, required=True)
    parser.add_argument("--profile", action="store_true",
                        help="Profile one bounded contiguous transfer in five-second buckets")
    args = parser.parse_args()
    if not 1 <= args.proxy_port <= 65535:
        parser.error("invalid loopback proxy port")
    try:
        url, _, bitrate = read_format(args.format)
        if args.profile:
            result = profile(url, args.proxy_port, bitrate)
            print(json.dumps(result, sort_keys=True))
            return int(result["state"] == "partial")
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
