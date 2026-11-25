"""Compare bounded HTTPS observations and correlate accepted Xray connections."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from docs.helpers.headless_playback import probe, read_format
from xgw.desync.schema import youtube_cdn_expiry

RANGE_BYTES = 65536
METRICS = ("status", "bytes", "tcp", "tls", "first_byte", "elapsed", "curl_rc", "tls_events",
           "content_range_ok")


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
    if (result.get("ok") and (result["status"], result["bytes"]) == (206, RANGE_BYTES)
            and result.get("content_range_ok") is not False):
        return "range_complete"
    if result.get("curl_rc") == 28:
        if not result.get("tcp"):
            return "tcp_timeout"
        if not result.get("tls"):
            return "tls_timeout"
        return "body_timeout" if result.get("first_byte") else "response_timeout"
    if (result.get("curl_rc"), result.get("status")) == (0, 302):
        return "http_redirect"
    if result.get("status"):
        return "http_or_range_incomplete"
    return "transport_failed"


def sample(source, first=None, *, wan_tcp_snapshot=None):
    try:
        url, _, _ = read_format(source)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {"outcome": "url_expired" if str(exc) == "media_url_expired" else "invalid_format"}
    digest = hashlib.sha256(url.encode()).hexdigest()
    if first is not None:
        if first.get("url_sha256") != digest:
            return {"outcome": "original_target_unavailable"}
        try:
            peer = public_ipv4(first.get("peer"))
        except ValueError:
            return {"outcome": "original_target_unavailable"}
    else:
        try:
            peer = ipv4_peer(urlsplit(url).hostname)
        except (OSError, ValueError):
            return {"outcome": "dns_ipv4_unavailable"}
    record, _ = observe(url, peer, wan_tcp_snapshot=wan_tcp_snapshot)
    return record


def observe(url, peer, *, capture_redirect=False, wan_tcp_snapshot=None):
    record = {"url_sha256": hashlib.sha256(url.encode()).hexdigest(), "peer": peer}
    started = time.time()
    started_monotonic_ns = time.monotonic_ns()
    options = {"capture_redirect": True} if capture_redirect else {}
    tcp = None

    def transfer():
        return probe(url, RANGE_BYTES, peer=peer, observe_tls=True, **options)

    try:
        if wan_tcp_snapshot is None:
            result = transfer()
        else:
            from docs.helpers.cdn_tcp_observation import snapshot_pid, watch_transfer

            pid = snapshot_pid(wan_tcp_snapshot)
            if pid is None:
                result, tcp = transfer(), {"state": "snapshot_unavailable"}
            else:
                result, tcp = watch_transfer(peer, pid, transfer)
    except (OSError, ValueError, subprocess.SubprocessError):
        return {**record, "outcome": "probe_runtime_error"}, None
    if tcp is not None:
        record["wan_tcp"] = tcp
        record["started_monotonic_ns"] = started_monotonic_ns
        record["finished_monotonic_ns"] = time.monotonic_ns()
    return {**record, "outcome": outcome(result), "actual_peer": result.get("remote_ip"),
            "started": started, "finished": time.time(),
            "local_ip": result.get("local_ip"), "local_port": result.get("local_port"),
            **{key: result.get(key) for key in METRICS}}, result.get("redirect_url")


def run_sample(source, first, *, retry_302=False, wan_tcp_snapshot=None):
    record = sample(source, first, wan_tcp_snapshot=wan_tcp_snapshot)
    if retry_302 and record["outcome"] == "http_redirect":
        # A fresh curl process repeats the same signed URL and IPv4 without following Location.
        record["retry"] = sample(source, record)
    return record


def public_sample(record):
    return {"outcome": record.get("outcome"),
            "connected_to_requested_ipv4": (record["actual_peer"] == record["peer"]
                                            if record.get("actual_peer") else None),
            **{key: record.get(key) for key in METRICS}}


def range_verified(record):
    return (record.get("outcome") == "range_complete"
            and (record.get("status"), record.get("bytes"), record.get("curl_rc"))
            == (206, RANGE_BYTES, 0) and record.get("content_range_ok") is True
            and bool(record.get("peer")) and record.get("actual_peer") == record["peer"])


def redirect_candidate(location):
    if (not isinstance(location, str) or not 0 < len(location) <= 32768
            or "#" in location or "\\" in location
            or any(ord(char) < 33 or ord(char) > 126 for char in location)):
        return None
    expires = youtube_cdn_expiry(location)
    if expires is None or expires <= time.time():
        return None
    parts = urlsplit(location)
    if parts.username is not None or parts.password is not None:
        return None
    try:
        return location if parts.port in (None, 443) else None
    except ValueError:
        return None


def prepare_pair(source, output):
    """Find one exact range through the working VPN and save its target privately."""
    try:
        url, duration, bitrate = read_format(source)
        record, location = observe(url, ipv4_peer(urlsplit(url).hostname), capture_redirect=True)
    except (OSError, ValueError, TypeError, KeyError):
        return {"state": "source_unavailable"}
    report = {"original": public_sample(record), "redirect": "not_needed"}
    if record["outcome"] == "http_redirect":
        report["redirect"] = "rejected"
        target = redirect_candidate(location)
        if not target or target == url or record.get("actual_peer") != record.get("peer"):
            return {"state": "redirect_unusable", **report}
        report["redirect"] = "followed"
        url = target
        try:
            record, _ = observe(url, ipv4_peer(urlsplit(url).hostname))
        except (OSError, ValueError):
            return {"state": "redirect_peer_unavailable", **report}
        report["target"] = public_sample(record)
    if not range_verified(record):
        return {"state": "vpn_range_unconfirmed", **report}
    if not output.is_absolute():
        return {"state": "output_unavailable", **report}
    try:
        with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w",
                       encoding="utf-8") as stream:
            json.dump({"url": url, "height": 720, "duration": duration,
                       "vbr": bitrate / 1000 if bitrate else None,
                       "url_sha256": record["url_sha256"], "peer": record["peer"]}, stream)
    except (OSError, ValueError):
        return {"state": "output_unavailable", **report}
    return {"state": "vpn_range_verified", **report}


def same_target(first, second):
    return bool(first.get("url_sha256") and first.get("peer")
                and all(first[key] == second.get(key) for key in ("url_sha256", "peer")))


def direct_retry_allowed(first, pinned, route):
    return (first.get("outcome") == "http_redirect" and first.get("status") == 302
            and first.get("curl_rc") == 0 and same_target(first, pinned)
            and route.get("state") == "observed" and route.get("group") == "zapret2"
            and first.get("actual_peer") == first["peer"])


def compare(direct, vpn, origin):
    control = public_sample(vpn)
    if vpn.get("outcome") == "http_redirect" and "retry" in vpn:
        control["retry"] = {**public_sample(vpn["retry"]),
                            "same_url_and_requested_ipv4": same_target(direct, vpn["retry"])}
    return {"url_origin": origin, "same_url_and_requested_ipv4": same_target(direct, vpn),
            "standalone": public_sample(direct), "vpn": control}


def evaluate_pair(direct, vpn, direct_route, vpn_route, *, queue_snapshots=None, retry=None):
    attempts = None
    direct_attempt = "first"
    if retry is not None:
        repeated, repeated_route, repeated_queue = retry
        attempts = {"first": evaluate_direct(direct, direct_route, queue_snapshots=queue_snapshots),
                    "retry": evaluate_direct(repeated, repeated_route, queue_snapshots=repeated_queue)}
        if (direct_retry_allowed(direct, vpn, direct_route) and same_target(direct, repeated)
                and attempts["retry"]["direct_route_verified"]
                and repeated.get("actual_peer") == direct["peer"]):
            direct, direct_route, queue_snapshots = repeated, repeated_route, repeated_queue
            direct_attempt = "retry"
    control, route = vpn, vpn_route
    if vpn.get("outcome") == "http_redirect" and "retry" in vpn:
        control = vpn["retry"]
        route = vpn_route.get("retry", {})
    direct_group = direct_route.get("group") if direct_route.get("state") == "observed" else None
    vpn_group = route.get("group") if route.get("state") == "observed" else None
    comparable = same_target(direct, vpn) and same_target(direct, control)
    same_peer = bool(comparable and all(
        record.get("actual_peer") == direct["peer"] for record in (direct, control)
    ))
    direct_ok, vpn_ok = range_verified(direct), range_verified(control)
    if not comparable:
        state = "target_unconfirmed"
    elif not same_peer or direct_group != "zapret2" or vpn_group not in ("xray", "sing-box"):
        state = "path_unconfirmed"
    elif not (direct_ok and vpn_ok):
        state = "range_unconfirmed"
    else:
        state = "pair_verified"
    report = {"state": state, "same_target": comparable, "same_connected_peer": same_peer,
              "vpn_route_verified": vpn_group in ("xray", "sing-box"),
              "vpn_range_verified": vpn_ok,
              "vpn_attempt": "retry" if control is not vpn else "first"}
    if attempts is not None:
        report.update(direct_attempt=direct_attempt, direct_attempts=attempts)
    return {**report, **direct_evidence(direct, direct_group == "zapret2", queue_snapshots)}


def direct_evidence(direct, route_verified, queue_snapshots):
    report = {"direct_route_verified": route_verified,
              "direct_range_verified": range_verified(direct)}
    observed_path = bool(route_verified and direct.get("peer")
                         and direct["peer"] == direct.get("actual_peer"))
    if "wan_tcp" in direct:
        from docs.helpers.cdn_tcp_observation import (
            FIELDS, MAX_SAMPLES, MAX_WINDOW, POLL_FIELDS, TIMING_FIELDS,
        )

        observed = direct["wan_tcp"]
        if observed_path:
            keys = ("state", "samples", "last_sample_before_end_ms", *FIELDS)
            report["direct_tcp"] = {key: observed[key] for key in keys if key in observed}
            if "syn_sent_retrans_total" in observed:
                value = observed["syn_sent_retrans_total"]
                if value is None or type(value) is int and 0 <= value <= (1 << 32) - 1:
                    report["direct_tcp"]["syn_sent_retrans_total"] = value
            for key in POLL_FIELDS:
                value = observed.get(key)
                if type(value) is int and 0 <= value <= MAX_SAMPLES:
                    report["direct_tcp"][key] = value
            for key in (*TIMING_FIELDS, "last_syn_sent_before_end_ms"):
                if key in observed:
                    value = observed[key]
                    if value is None or type(value) is int and 0 <= value <= MAX_WINDOW * 1000:
                        report["direct_tcp"][key] = value
        else:
            report["direct_tcp"] = {"state": "path_unconfirmed"}
    if queue_snapshots is not None:
        from docs.helpers.cdn_queue_observation import summarize

        if observed_path:
            report["direct_queue"] = summarize(*queue_snapshots, direct)
        else:
            report["direct_queue"] = {"state": "path_unconfirmed"}
    return report


def evaluate_direct(direct, route, *, queue_snapshots=None):
    verified = route.get("state") == "observed" and route.get("group") == "zapret2"
    return {"state": "direct_observed" if direct else "direct_unavailable",
            "direct": public_sample(direct),
            **direct_evidence(direct, verified, queue_snapshots)}


def page_sample():
    result = probe("https://www.youtube.com/t/terms", 1048576, range_request=False, observe_tls=True)
    return {"ok": result["ok"] and result["status"] == 200,
            **{key: result.get(key) for key in METRICS}}


def route_match(record, journal, before, after):
    from docs.helpers.selective_flow_evidence import MAX_CAPTURE_SECONDS, access_records
    from docs.helpers.selective_media_evidence import MAX_LOG_ROWS, number
    from xgw.desync import route_evidence
    from xgw.xraycore.access import endpoint

    try:
        route_evidence.deltas(before, after)
    except route_evidence.EvidenceError as exc:
        return {"state": "snapshots_incomparable", "reason": str(exc)}
    if len(journal) >= MAX_LOG_ROWS:
        return {"state": "journal_limit"}
    if not 0 < after["unix"] - before["unix"] <= MAX_CAPTURE_SECONDS:
        return {"state": "window_unconfirmed"}

    def match(attempt):
        start, end = attempt.get("started"), attempt.get("finished")
        if not (number(start) and number(end) and before["unix"] <= start < end <= after["unix"]):
            return {"state": "window_unconfirmed"}
        address, port, peer = attempt.get("local_ip"), attempt.get("local_port"), attempt.get("actual_peer")
        if not address or not peer or peer != attempt.get("peer") or type(port) is not int:
            return {"state": "socket_unconfirmed"}
        try:
            source = endpoint(f"{address}:{port}")
            target = (public_ipv4(peer), 443)
        except ValueError:
            return {"state": "socket_unconfirmed"}
        entries = access_records(journal, before, start, end).get((source, target), ())
        if len(entries) == 1:
            return {"state": "observed", "group": entries[0][1]}
        return {"state": "ambiguous" if entries else "no_access_record"}

    result = match(record)
    if "retry" in record:
        result["retry"] = match(record["retry"])
    return result


def read_sample(path):
    if path is None:
        return {}
    try:
        with path.open("rb") as stream:
            raw = stream.read(4097)
        record = json.loads(raw) if len(raw) <= 4096 else None
    except (OSError, ValueError):
        return {}
    return record if isinstance(record, dict) else {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser("sample")
    run.add_argument("source", type=Path)
    run.add_argument("--peer-from", type=Path)
    run.add_argument("--retry-302", action="store_true")
    run.add_argument("--wan-tcp-snapshot", type=Path)
    eligibility = commands.add_parser("can-retry-direct")
    eligibility.add_argument("first", type=Path)
    eligibility.add_argument("pinned", type=Path)
    eligibility.add_argument("route", type=Path)
    seed = commands.add_parser("prepare")
    seed.add_argument("source", type=Path)
    seed.add_argument("output", type=Path)
    decision = commands.add_parser("evaluate")
    for name in ("direct", "vpn", "direct_route", "vpn_route"):
        decision.add_argument(name, type=Path)
    for name in ("direct-retry", "direct-retry-route", "direct-retry-queue-before",
                 "direct-retry-queue-after"):
        decision.add_argument(f"--{name}", type=Path)
    direct = commands.add_parser("evaluate-direct")
    direct.add_argument("direct", type=Path)
    direct.add_argument("direct_route", type=Path)
    for command in (decision, direct):
        command.add_argument("--queue-before", type=Path)
        command.add_argument("--queue-after", type=Path)
    commands.add_parser("page")
    summary = commands.add_parser("compare")
    summary.add_argument("direct", type=Path)
    summary.add_argument("vpn", type=Path)
    summary.add_argument("origin", choices=("standalone", "vpn"))
    route = commands.add_parser("route")
    route.add_argument("sample", type=Path)
    route.add_argument("before", type=Path)
    route.add_argument("after", type=Path)
    args = parser.parse_args()
    if args.action == "sample":
        if args.retry_302 and not args.peer_from:
            parser.error("--retry-302 requires --peer-from")
        first = read_sample(args.peer_from) if args.peer_from else None
        record = run_sample(args.source, first, retry_302=args.retry_302,
                            wan_tcp_snapshot=args.wan_tcp_snapshot)
        ok = record.get("retry", record)["outcome"] == "range_complete"
    elif args.action == "can-retry-direct":
        ok = direct_retry_allowed(
            read_sample(args.first), read_sample(args.pinned), read_sample(args.route),
        )
        record = {"eligible": ok}
    elif args.action == "prepare":
        record = prepare_pair(args.source, args.output)
        ok = record["state"] == "vpn_range_verified"
    elif args.action in ("evaluate", "evaluate-direct"):
        if bool(args.queue_before) != bool(args.queue_after):
            parser.error("--queue-before and --queue-after must be supplied together")
        snapshots = ((read_sample(args.queue_before), read_sample(args.queue_after))
                     if args.queue_before is not None else None)
        try:
            direct_record, direct_route = read_sample(args.direct), read_sample(args.direct_route)
            if args.action == "evaluate-direct":
                record = evaluate_direct(direct_record, direct_route, queue_snapshots=snapshots)
            else:
                retry = None
                if args.direct_retry is not None:
                    retry = (read_sample(args.direct_retry), read_sample(args.direct_retry_route),
                             (read_sample(args.direct_retry_queue_before),
                              read_sample(args.direct_retry_queue_after)))
                record = evaluate_pair(direct_record, read_sample(args.vpn), direct_route,
                                       read_sample(args.vpn_route), queue_snapshots=snapshots,
                                       retry=retry)
        except (TypeError, AttributeError):
            record = {"state": "invalid_evidence"}
        ok = record["state"] in ("pair_verified", "direct_observed")
    elif args.action == "page":
        try:
            record = page_sample()
        except (OSError, ValueError, subprocess.SubprocessError):
            record = {"ok": False, "error": "probe_runtime_error"}
        ok = record["ok"]
    elif args.action == "route":
        from docs.helpers.selective_media_evidence import read_rows
        from xgw.desync.route_evidence import _read_snapshot

        try:
            record = route_match(read_sample(args.sample), read_rows(sys.stdin.buffer),
                                 _read_snapshot(args.before), _read_snapshot(args.after))
        except (OSError, KeyError, TypeError, ValueError, AttributeError):
            record = {"state": "invalid_evidence"}
        ok = record["state"] == "observed" or record.get("retry", {}).get("state") == "observed"
    else:
        record = compare(read_sample(args.direct), read_sample(args.vpn), args.origin)
        ok = True
    print(json.dumps(record, allow_nan=False))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
