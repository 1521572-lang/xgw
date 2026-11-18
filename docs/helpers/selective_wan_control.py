"""Compare kernel route lookups and try one TCP connection on the gateway's WAN."""

import argparse
import ipaddress
import json
import os
import pwd
import socket
import time

from xgw import config, marknet, zapret2
from xgw.net import cmd, lan
from xgw.paths import Paths

CONNECT_SECONDS = 5


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


def control(peer, wan, bypass_mark, xray_uid, control_uid):
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
    try:
        with marknet.connect_marked(peer, 443, timeout=CONNECT_SECONDS, mark=bypass_mark,
                                    connect=connect) as sock:
            local, _port = sock.getsockname()
    except TimeoutError:
        result["tcp"] = "timeout"
    except (OSError, marknet.MarkUnavailable) as exc:
        result.update(tcp="error", errno=getattr(exc, "errno", None))
    else:
        result.update(tcp="connected", source_matches_lookup=local == direct["prefsrc"])
    return {**result, "elapsed_ms": round(1000 * (time.monotonic() - began))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--peer", type=ipaddress.IPv4Address, required=True)
    parser.add_argument("--wan", required=True)
    parser.add_argument("--routes-only", action="store_true")
    args = parser.parse_args()
    if not args.peer.is_global or args.peer.is_multicast:
        parser.error("a public IPv4 peer is required")
    if not lan.valid_interface(args.wan):
        parser.error("invalid WAN interface")
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
        result = control(peer, args.wan, bypass, xray_uid, os.geteuid())
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
