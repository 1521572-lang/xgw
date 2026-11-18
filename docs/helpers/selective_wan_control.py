"""Compare routes and try one TCP or TLS connection on the gateway's WAN."""

import argparse
import ipaddress
import json
import os
import pwd
import socket
import ssl
import sys
import time

from xgw import config, marknet, zapret2
from xgw.desync.schema import valid_youtube_cdn_host
from xgw.net import cmd, lan
from xgw.paths import Paths

CONNECT_SECONDS = 5
WAIT_LIMIT = 90


def route(peer, mark, uid):
    try:
        rows = json.loads(cmd.run(
            ["ip", "-4", "-j", "route", "get", peer, "mark", hex(mark),
             "uid", str(uid), "ipproto", "tcp", "dport", "443"], timeout=2,
        ))
    except (cmd.CommandError, ValueError):
        return None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        return None
    row = rows[0]
    if row.get("type", "unicast") != "unicast" or not row.get("dev"):
        return None
    return {key: row.get(key) for key in ("dev", "gateway", "prefsrc", "table")}


def wait_for_selective_socket(peer, seconds):
    """Trigger once on a new marked socket that started sending data to this peer."""
    from docs.helpers.selective_probe_watch import socket_stats

    deadline = time.monotonic() + seconds
    baseline = socket_stats()
    if baseline["state"] != "read":
        return {"state": "socket_stats_unavailable", "detail": baseline["state"]}
    existing = {row["socket"] for row in baseline["sockets"]}
    print("READY: waiting for a new marked socket", file=sys.stderr, flush=True)
    while time.monotonic() < deadline:
        current = socket_stats()
        sampled_at = time.time()
        if time.monotonic() >= deadline:
            break
        if current["state"] != "read":
            return {"state": "socket_stats_unavailable", "detail": current["state"]}
        candidates = [row for row in current["sockets"]
                      if row["socket"] not in existing and row["peer_ip"] == peer
                      and row["state"] == "ESTAB" and (row["bytes_sent"] or 0) > 0]
        if len(candidates) > 1:
            return {"state": "multiple_candidates", "sampled_at": sampled_at}
        if candidates:
            return {"state": "matched", "sampled_at": sampled_at, "socket": candidates[0]}
        time.sleep(min(0.25, max(0, deadline - time.monotonic())))
    return {"state": "not_observed"}


def tls_control(sock, hostname):
    result = {"tls_started_at": time.time()}
    try:
        context = ssl.create_default_context()
        with context.wrap_socket(sock, server_hostname=hostname,
                                 do_handshake_on_connect=False) as secured:
            secured.settimeout(zapret2.YOUTUBE_TRANSPORT_TLS_SECONDS)
            secured.do_handshake()
            result.update(tls="connected", tls_version=secured.version())
    except TimeoutError:
        result["tls"] = "timeout"
    except ssl.SSLCertVerificationError as exc:
        result.update(tls="certificate_error", verify_code=exc.verify_code)
    except OSError as exc:
        result.update(tls="error", tls_errno=exc.errno)
    return {**result, "tls_finished_at": time.time()}


def control(peer, wan, bypass_mark, xray_uid, control_uid, *, tls_host=None):
    direct = route(peer, bypass_mark, control_uid)
    selected = route(peer, zapret2.MARK, xray_uid)
    result = {"wan": wan, "control_route": direct, "selective_route": selected}
    if direct is None or direct["dev"] != wan:
        return {**result, "tcp": "wan_route_unconfirmed"}

    def connect(sock, address):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, wan.encode("ascii") + b"\0")
        sock.settimeout(CONNECT_SECONDS)
        sock.connect(address)

    began = time.monotonic()
    if tls_host:
        result.update(peer_ip=peer, tcp_started_at=time.time())
    try:
        with marknet.connect_marked(peer, 443, timeout=CONNECT_SECONDS, mark=bypass_mark,
                                    connect=connect) as sock:
            local, _port = sock.getsockname()
            result.update(tcp="connected", source_matches_lookup=local == direct["prefsrc"],
                          elapsed_ms=round(1000 * (time.monotonic() - began)))
            if tls_host:
                result["tcp_finished_at"] = time.time()
                result.update(tls_control(sock, tls_host))
    except TimeoutError:
        result["tcp"] = "timeout"
    except (OSError, marknet.MarkUnavailable) as exc:
        result.update(tcp="error", errno=getattr(exc, "errno", None))
    if "elapsed_ms" not in result:
        result["elapsed_ms"] = round(1000 * (time.monotonic() - began))
    if tls_host and "tcp_finished_at" not in result:
        result["tcp_finished_at"] = time.time()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--peer", type=ipaddress.IPv4Address, required=True)
    parser.add_argument("--wan", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--routes-only", action="store_true")
    mode.add_argument("--tls-host", help="googlevideo.com hostname for TLS certificate checks")
    parser.add_argument("--during-selective", type=int, metavar="SECONDS",
                        help="wait for a new marked socket to this peer before sending")
    args = parser.parse_args()
    if not args.peer.is_global or args.peer.is_multicast:
        parser.error("a public IPv4 peer is required")
    if not lan.valid_interface(args.wan):
        parser.error("invalid WAN interface")
    if args.tls_host is not None and not valid_youtube_cdn_host(args.tls_host):
        parser.error("expected a CDN hostname under googlevideo.com, without a URL or port")
    wait = args.during_selective
    if wait is not None and (not args.tls_host or not 1 <= wait <= WAIT_LIMIT):
        parser.error(f"--during-selective requires --tls-host and 1–{WAIT_LIMIT} seconds")
    cfg, _warnings = config.load(Paths.from_env().config_file)
    configured_wan = cfg.network.wan_if.strip()
    if configured_wan and configured_wan != args.wan:
        parser.error("WAN differs from configured interface")
    bypass = cfg.capture.mark_bypass
    if bypass <= 0 or bypass & zapret2.FAKE_MARK:
        parser.error("invalid bypass mark")
    peer = str(args.peer)
    xray_uid = pwd.getpwnam("xray").pw_uid
    if args.routes_only:
        result = {"wan": args.wan, "control_route": route(peer, bypass, os.geteuid()),
                  "selective_route": route(peer, zapret2.MARK, xray_uid)}
    else:
        trigger = wait_for_selective_socket(peer, wait) if wait is not None else None
        if trigger is not None and trigger["state"] != "matched":
            result = {"trigger": trigger, "tcp": "not_run"}
        else:
            result = control(peer, args.wan, bypass, xray_uid, os.geteuid(),
                             tls_host=args.tls_host)
            if trigger is not None:
                result["trigger"] = trigger
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
