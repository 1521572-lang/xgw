"""Record one bounded HTTPS range and compare two samples without exposing the URL or peer."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from docs.helpers.headless_playback import probe, read_format

RANGE_BYTES = 65536
METRICS = ("status", "bytes", "tcp", "tls", "first_byte", "elapsed", "curl_rc")


def public_ipv4(value):
    peer = ipaddress.IPv4Address(value)
    if not peer.is_global or peer.is_multicast:
        raise ValueError("public_ipv4_required")
    return str(peer)


def ipv4_peer(host):
    for row in socket.getaddrinfo(host, 443, family=socket.AF_INET, type=socket.SOCK_STREAM):
        try:
            return public_ipv4(row[4][0])
        except ValueError:
            continue
    raise ValueError("public_ipv4_required")


def outcome(result):
    if result.get("ok") and (result["status"], result["bytes"]) == (206, RANGE_BYTES):
        return "range_complete"
    if result.get("curl_rc") == 28:
        if not result.get("tcp"):
            return "tcp_timeout"
        if not result.get("tls"):
            return "tls_timeout"
        return "body_timeout" if result.get("first_byte") else "response_timeout"
    if result.get("status"):
        return "http_or_range_incomplete"
    return "transport_failed"


def sample(source, first=None):
    try:
        url, _, _ = read_format(source)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {"outcome": "url_expired" if str(exc) == "media_url_expired" else "invalid_format"}
    digest = hashlib.sha256(url.encode()).hexdigest()
    if first is not None:
        if first.get("url_sha256") != digest or not first.get("peer"):
            return {"outcome": "original_target_unavailable"}
        peer = public_ipv4(first["peer"])
    else:
        try:
            peer = ipv4_peer(urlsplit(url).hostname)
        except (OSError, ValueError):
            return {"outcome": "dns_ipv4_unavailable"}
    record = {"url_sha256": digest, "peer": peer}
    try:
        result = probe(url, RANGE_BYTES, peer=peer)
    except (OSError, ValueError, subprocess.SubprocessError):
        return {**record, "outcome": "probe_runtime_error"}
    return {**record, "outcome": outcome(result), "actual_peer": result.get("remote_ip"),
            **{key: result.get(key) for key in METRICS}}


def compare(direct, vpn, origin):
    same_target = bool(direct.get("url_sha256") and direct.get("peer")
                       and direct["url_sha256"] == vpn.get("url_sha256")
                       and direct["peer"] == vpn.get("peer"))
    return {
        "url_origin": origin, "same_url_and_requested_ipv4": same_target,
        **{phase: {"outcome": record.get("outcome"),
                   "connected_to_requested_ipv4": (record["actual_peer"] == record["peer"]
                                                   if record.get("actual_peer") else None),
                   **{key: record.get(key) for key in METRICS}}
           for phase, record in (("standalone", direct), ("vpn", vpn))},
    }


def read_sample(path):
    if not path or not path.is_file() or path.stat().st_size > 4096:
        return {}
    try:
        record = json.loads(path.read_bytes())
    except ValueError:
        return {}
    return record if isinstance(record, dict) else {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser("sample")
    run.add_argument("source", type=Path)
    run.add_argument("--peer-from", type=Path)
    summary = commands.add_parser("compare")
    summary.add_argument("direct", type=Path)
    summary.add_argument("vpn", type=Path)
    summary.add_argument("origin", choices=("standalone", "vpn"))
    args = parser.parse_args()
    if args.action == "sample":
        first = read_sample(args.peer_from) if args.peer_from else None
        record = sample(args.source, first)
    else:
        record = compare(read_sample(args.direct), read_sample(args.vpn), args.origin)
    print(json.dumps(record, allow_nan=False))
    return 0 if args.action == "compare" or record["outcome"] == "range_complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
