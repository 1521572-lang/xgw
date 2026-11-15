"""Bounded, opt-in media experiments; never changes routes, workers or policy.

Run with ``python -m xgw.desync.experiment --help``. Results are evidence of a
single transfer, not proof of playback, direct routing or a particular DPI cause.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import os
import re
import stat
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

VERSION = 1
DURATION = 45
MIN_BYTES = 1024 * 1024
MAX_BYTES = 8 * 1024 * 1024
STALL_SECONDS = 10
TTL = 24 * 3600
LABEL = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}\Z")
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
FIELDS = {"url", "address", "network", "policy_sha256", "client", "protocol",
          "candidate", "family", "route", "round"}
# Only explicitly selected metadata, never %{json} (which includes signed URLs).
WRITE_OUT = ('{"status":"%{http_code}","bytes":%{size_download},'
             '"seconds":%{time_total},"tls_seconds":%{time_appconnect},'
             '"http_version":"%{http_version}","remote_ip":"%{remote_ip}",'
             '"content_type":"%{content_type}"}')


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"))
                          .encode()).hexdigest()


def validate_spec(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("spec_fields")
    if any(not isinstance(v, str) for v in value.values()):
        raise ValueError("spec_types")
    for field in ("network", "client", "candidate", "family", "round"):
        if not LABEL.fullmatch(value[field]):
            raise ValueError("spec_label")
    if not SHA256.fullmatch(value["policy_sha256"]):
        raise ValueError("spec_policy_hash")
    if value["protocol"] not in ("h1", "h2", "h3") or value["route"] not in ("direct", "vpn"):
        raise ValueError("spec_transport")
    url = value["url"]
    if len(url) > 16384 or any(ord(c) < 33 or ord(c) > 126 for c in url):
        raise ValueError("spec_url")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.fragment
            or not re.fullmatch(r"[a-zA-Z0-9.-]+", parsed.hostname)):
        raise ValueError("spec_url")
    address = ipaddress.ip_address(value["address"])
    if not address.is_global or "%" in value["address"]:
        raise ValueError("spec_address")
    return dict(value, address=str(address))


def contexts(spec: dict, client_hash: str) -> dict[str, str]:
    """Exact endpoint is the reuse boundary; prefix grouping is experimental only.

    Keep the full hostname: cutting a fixed number of labels is not a public-
    suffix lookup and can accidentally merge unrelated services.
    """
    address = ipaddress.ip_address(spec["address"])
    prefix = str(ipaddress.ip_network(f"{address}/{24 if address.version == 4 else 48}",
                                      strict=False))
    shared = [urlsplit(spec["url"]).hostname, spec["protocol"], spec["network"],
              spec["policy_sha256"], spec["client"], client_hash]
    return {"context_id": digest([*shared, str(address)]),
            "prefix_context_id": digest([*shared, prefix]),
            "target_id": digest(spec["url"])}


def curl_config(spec: dict, body: Path) -> str:
    host = urlsplit(spec["url"]).hostname
    addr = spec["address"]
    if ":" in addr:
        addr = f"[{addr}]"

    def quoted(value: str) -> str:
        if any(c in value for c in "\r\n\x00"):
            raise ValueError("curl_config_character")
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    options = {"url": spec["url"], "resolve": f"{host}:443:{addr}",
               "output": str(body), "write-out": WRITE_OUT, "noproxy": "*",
               "proxy": "", "proto": "=https", "range": f"0-{MAX_BYTES - 1}",
               "limit-rate": "128K", "max-time": str(DURATION), "connect-timeout": "10"}
    # No redirect/retry: a new target or attempt is a new observation.
    protocol = {"h1": "http1.1", "h2": "http2", "h3": "http3-only"}[spec["protocol"]]
    return "silent\ngloboff\n" + protocol + "\n" + "\n".join(
        f"{key} = {quoted(value)}" for key, value in options.items()) + "\n"


def classify(meta: dict, returncode: int, samples: list[tuple[float, int]],
             protocol: str) -> str:
    """An early success is SHORT_TRANSFER, never a sustained pass.

    curl exit 28 is expected at the explicit 45s observation boundary only when
    all progress checks pass. Late RST cannot be identified without packet data.
    """
    try:
        status = int(meta["status"])
        size, elapsed = float(meta["bytes"]), float(meta["seconds"])
        if not all(math.isfinite(v) and v >= 0 for v in (size, elapsed)):
            return "INVALID_MEASUREMENT"
        if status in (401, 403, 410, 416):
            return "HTTP_REFUSED_OR_STALE_URL"
        if status not in (200, 206):
            return "HTTP_OR_CONNECT_FAILURE"
        if str(meta["http_version"]) != {"h1": "1.1", "h2": "2", "h3": "3"}[protocol]:
            return "PROTOCOL_MISMATCH"
        if not str(meta["content_type"]).lower().startswith(("video/", "audio/")):
            return "NOT_MEDIA"
        if not samples or any(not math.isfinite(t) or t < 0 or type(b) is not int or b < 0
                              for t, b in samples):
            return "INVALID_MEASUREMENT"
        if abs(samples[-1][1] - size) > 16384 or samples[-1][1] > MAX_BYTES + 262144:
            return "INVALID_MEASUREMENT"
        last_progress, previous, armed, max_gap = 0.0, 0, False, 0.0
        for timestamp, received in samples:
            if received < previous or timestamp < last_progress:
                return "INVALID_MEASUREMENT"
            if armed:
                max_gap = max(max_gap, timestamp - last_progress)
            if received > previous:
                last_progress = timestamp
            if received >= 65536:
                armed = True
            previous = received
        if max_gap >= STALL_SECONDS:
            return "LATE_STALL_OBSERVED"
        if returncode not in (0, 28):
            return "TRANSFER_INTERRUPTED"
        if size < MIN_BYTES:
            return "INSUFFICIENT_BYTES"
        if elapsed < DURATION - 1 or samples[-1][0] < DURATION - 1:
            return "SHORT_TRANSFER"
        return "PASS_SUSTAINED"
    except (KeyError, TypeError, ValueError, OverflowError):
        return "INVALID_MEASUREMENT"


def private_path(path: Path, *, directory: bool = False) -> None:
    info = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if (not expected(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise ValueError("private_path_required")


def run_probe(spec: dict, curl: Path, output: Path) -> dict:
    if os.name != "posix":
        raise ValueError("real_linux_required")
    private_path(output, directory=True)
    curl = curl.resolve(strict=True)
    if not curl.is_file() or not os.access(curl, os.X_OK):
        raise ValueError("curl_executable")
    client_hash = hashlib.sha256(curl.read_bytes()).hexdigest()
    # Marking a run 'direct' is a declared route, not an observation of its path.
    result = {"schema": VERSION, "created": time.time(), **contexts(spec, client_hash),
              **{k: spec[k] for k in ("candidate", "family", "route", "round", "client",
                                      "protocol", "policy_sha256")},
              "client_sha256": client_hash, "path_verified": False,
              "playback": "NOT_RUN"}
    with tempfile.TemporaryDirectory(prefix=".probe-", dir=output) as temp:
        body = Path(temp) / "body"
        body.touch(mode=0o600)
        env = {k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")}
        # curlrc is disabled as the FIRST option. URL is sent via stdin, not argv.
        with tempfile.TemporaryFile() as metadata:
            proc = subprocess.Popen([str(curl), "--disable", "--config", "-"],
                                    stdin=subprocess.PIPE, stdout=metadata,
                                    stderr=subprocess.DEVNULL, env=env)
            start = time.monotonic()
            samples = [(0.0, 0)]
            budget_stop = False
            try:
                proc.stdin.write(curl_config(spec, body).encode())
                proc.stdin.close()
                while proc.poll() is None:
                    elapsed, size = time.monotonic() - start, body.stat().st_size
                    samples.append((round(elapsed, 3), size))
                    if elapsed > DURATION + 5 or size > MAX_BYTES:
                        budget_stop = True
                        proc.kill()
                        break
                    time.sleep(0.25)
                proc.wait(timeout=5)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5)
            samples.append((round(time.monotonic() - start, 3), body.stat().st_size))
            metadata.seek(0)
            try:
                meta = json.loads(metadata.read(16384))
                if not isinstance(meta, dict):
                    meta = {}
            except (ValueError, UnicodeDecodeError):
                meta = {}
    verdict = classify(meta, proc.returncode, samples, spec["protocol"])
    if budget_stop:
        verdict = "BUDGET_STOP"
    elif proc.returncode == 2 and not meta:
        verdict = "CLIENT_OPTIONS_UNSUPPORTED"
    elif meta.get("remote_ip") and ipaddress.ip_address(meta["remote_ip"]) != ipaddress.ip_address(
            spec["address"]):
        verdict = "ENDPOINT_MISMATCH"
    # Do not copy server-controlled strings into a public result.
    result.update(verdict=verdict, curl_exit=proc.returncode, samples=samples,
                  bytes=samples[-1][1], seconds=samples[-1][0],
                  media_type_ok=str(meta.get("content_type", "")).lower()
                  .startswith(("video/", "audio/")))
    for field in ("status", "tls_seconds"):
        try:
            number = float(meta[field])
            if math.isfinite(number) and 0 <= number < 1000:
                result[field] = number
        except (KeyError, TypeError, ValueError):
            pass
    return result


def select_candidates(records: list[dict], context_id: str, now: float) -> list[dict]:
    """Shortlist from immutable experiment history, NOT an automatically applied cache.

    Need two latest passing observations in distinct rounds. A newer failure
    invalidates older wins. Never combine endpoints/clients/transports/networks.
    """
    groups: dict[str, list[dict]] = {}
    for row in records:
        if (row.get("schema") != VERSION or row.get("context_id") != context_id
                or row.get("route") != "direct" or row.get("family") == "control"):
            continue
        stamp = row.get("created")
        if type(stamp) not in (int, float) or not 0 <= now - stamp <= TTL:
            continue
        if any(not isinstance(row.get(k), str) or not LABEL.fullmatch(row[k])
               for k in ("candidate", "family", "round")):
            continue
        groups.setdefault(row["candidate"], []).append(row)
    eligible = []
    for name, rows in groups.items():
        latest = sorted(rows, key=lambda r: r["created"], reverse=True)[:2]
        if (len(latest) == 2 and latest[0]["round"] != latest[1]["round"]
                and latest[0]["family"] == latest[1]["family"]
                and all(r.get("verdict") == "PASS_SUSTAINED" for r in latest)):
            eligible.append({"candidate": name, "family": latest[0]["family"],
                             "last_success": latest[0]["created"]})
    selected, families = [], set()
    for candidate in sorted(eligible, key=lambda r: (-r["last_success"], r["candidate"])):
        if candidate["family"] not in families:
            selected.append(candidate)
            families.add(candidate["family"])
        if len(selected) == 3:
            break
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("probe", help="45s media GET; no route/worker changes")
    probe.add_argument("--spec", required=True, type=Path, help="private JSON input")
    probe.add_argument("--curl", type=Path, default=Path("/usr/bin/curl"))
    probe.add_argument("--out", required=True, type=Path, help="existing private directory")
    emit = sub.add_parser("shortlist", help="emit up to 3 families; never applies policy")
    emit.add_argument("--results", required=True, type=Path)
    emit.add_argument("--context", required=True)
    args = parser.parse_args(argv)
    try:
        if os.name != "posix":
            raise ValueError("real_linux_required")
        if args.command == "probe":
            private_path(args.spec)
            if args.spec.stat().st_size > 32768:
                raise ValueError("spec_size")
            spec = validate_spec(json.loads(args.spec.read_text(encoding="utf-8")))
            result = run_probe(spec, args.curl, args.out)
            path = args.out / f"{uuid.uuid4().hex}.json"
            # Atomic individual records: readers never consume a partial JSON;
            # concurrent probes cannot overwrite a shared read/modify/write cache.
            fd, temporary = tempfile.mkstemp(prefix=".record-", dir=args.out)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(result, handle, ensure_ascii=True, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
            print(json.dumps({"file": path.name, "verdict": result["verdict"],
                              "context_id": result["context_id"]}))
            return 0 if result["verdict"] == "PASS_SUSTAINED" else 1
        private_path(args.results, directory=True)
        if not SHA256.fullmatch(args.context):
            raise ValueError("context_hash")
        records = []
        for path in args.results.glob("*.json"):
            if len(records) >= 2048:
                raise ValueError("history_limit")
            private_path(path)
            if path.stat().st_size > 65536:
                raise ValueError("record_size")
            record = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                raise ValueError("record_schema")
            records.append(record)
        print(json.dumps({"schema": VERSION, "context_id": args.context,
                          "ttl_seconds": TTL, "apply": False,
                          "status": "EXPERIMENTAL_SHORTLIST",
                          "requires": ["verified_direct_path", "browser_15_plus_5", "T03_T07"],
                          "candidates": select_candidates(records, args.context, time.time())},
                         indent=2))
        return 0
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        # Signed URLs, paths, and raw curl errors must not escape via tracebacks.
        print('{"error":"experiment_input_or_runtime_error"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
