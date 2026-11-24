"""Check fresh HTTPS sessions on the already-applied VPN configuration."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .. import config, zapret2
from ..generator import builder, singbox
from ..net import cmd
from ..paths import LockTimeout, Paths
from ..watch import checks
from ..xraycore.access import destination
from . import route_evidence as evidence
from . import vpn_access

LANES = ("http_in", "xray", "sing-box")
MAX_BODY = 4096


@dataclass(frozen=True)
class _Target:
    port: int
    tag: str = ""
    password: str = field(default="", repr=False)
    inbound: str = "http-in"


def _targets(applied):
    if zapret2.standalone(applied):
        return {}
    inbounds = [row for row in applied["inbounds"] if row.get("listen") == "127.0.0.1"
                and row.get("protocol") == "http" and type(row.get("port")) is int
                and 1 <= row["port"] <= 65535]
    tags = Counter(row.get("tag") for row in applied["inbounds"])
    ports = Counter(row["port"] for row in inbounds)
    listeners = {row["tag"]: row for row in inbounds
                 if tags[row.get("tag")] == 1 and ports[row["port"]] == 1}
    outbounds = {row["tag"]: row for row in applied["outbounds"]}
    if len(outbounds) != len(applied["outbounds"]):
        raise evidence.EvidenceError("ambiguous_outbounds")
    rules = applied["routing"]["rules"]
    result = {}
    if "http-in" in listeners:
        result["http_in"] = _Target(listeners["http-in"]["port"])
    for node in builder.applied_nodes(applied):
        if node.role != "proxy" or node.probe_tag not in listeners:
            continue
        # Rules for unrelated inbounds can precede the pinned node's rule. A
        # general or conditional matching rule makes this node unsuitable.
        first = next((rule for rule in rules if not rule.get("inboundTag")
                      or node.probe_tag in rule["inboundTag"]), None)
        if first != {"type": "field", "inboundTag": [node.probe_tag], "outboundTag": node.tag}:
            continue
        listener = listeners[node.probe_tag]
        accounts = (listener.get("settings") or {}).get("accounts") or []
        if len(accounts) != 1 or accounts[0].get("user") != builder.PROBE_USER:
            continue
        password = accounts[0].get("pass")
        outbound = outbounds[node.tag]
        protocol = outbound.get("protocol")
        if not password or not isinstance(password, str) or protocol in (
            None, "", "freedom", "blackhole", "dns", "loopback"
        ):
            continue
        lane = "sing-box" if singbox.bridge_variant(outbound) else "xray"
        result.setdefault(lane, _Target(listener["port"], node.tag, password, node.probe_tag))
    return result


def _exit_address(body):
    fields = [line[3:].strip() for line in body.splitlines() if line.startswith(b"ip=")]
    if len(fields) != 1 or b"%" in fields[0]:
        return None
    try:
        address = ipaddress.ip_address(fields[0].decode("ascii"))
    except ValueError:
        return None
    return address if address.is_global and not address.is_multicast else None


def _probe(target, url, user_agent, *, on_connect=None):
    start = time.monotonic()
    response = checks.http_get_via_proxy(
        "127.0.0.1", target.port, url, timeout=5, max_total=8, silence=3, min_body=1,
        keep_body=MAX_BODY, max_bytes=MAX_BODY, user_agent=user_agent,
        proxy_user=builder.PROBE_USER if target.password else "", proxy_pass=target.password,
        on_connect=on_connect,
    )
    complete = response.ok and response.status == 200 and 0 < response.downloaded < MAX_BODY
    address = _exit_address(response.body) if complete else None
    connect = response.phase == "connect"
    result = {"result": ("https_with_exit" if address else "https_only") if complete else "failed",
              "http": 0 if connect else response.status,
              "connect_http": response.status if connect else 0, "phase": response.phase,
              "bytes": response.downloaded, "elapsed_ms": round((time.monotonic() - start) * 1000),
              "exit_family": address.version if address else None}
    return result, address


def _counter_activity(before, after, tag):
    if not tag:
        return None
    start, end = before["tags"][tag], after["tags"][tag]
    if any(row[key] is None for row in (start, end) for key in evidence.DIRECTIONS):
        return None
    return all(end[key] > start[key] for key in evidence.DIRECTIONS)


def observe(paths: Paths, *, live: bool = False, route: bool = False) -> dict:
    path = paths.xray_config_file
    before = evidence.snapshot(path, paths=paths)
    raw = evidence._read_config(path)
    if hashlib.sha256(raw).hexdigest() != before["config_sha256"]:
        raise evidence.EvidenceError("snapshot_changed_during_read")
    targets = _targets(json.loads(raw))
    result = {"live": live, "paths": {lane: {"result": "available" if lane in targets
                                             else "unavailable"} for lane in LANES}}
    if not live or not targets:
        return result

    cfg, _ = config.load(paths.config_file)
    url = cfg.probe.trace_url.strip()
    parts = urlsplit(url)
    if (parts.scheme != "https" or not parts.hostname or parts.port not in (None, 443)
            or parts.username is not None or parts.password is not None or parts.fragment
            or parts.query or any(ord(c) < 33 for c in url)):
        raise evidence.EvidenceError("ordinary_https_trace_unavailable")
    addresses, connections = {}, {}
    authority = destination(f"{parts.hostname.encode('idna').decode('ascii')}:443") if route else None
    for lane in LANES:
        if lane in targets:
            target = targets[lane]
            sockets = []
            start = time.time_ns() // 1000
            result["paths"][lane], addresses[lane] = _probe(
                target, url, cfg.probe.user_agent, on_connect=sockets.append if route else None)
            if authority is not None:
                connections[lane] = vpn_access.Connection(
                    start, time.time_ns() // 1000, sockets[0] if len(sockets) == 1 else None,
                    authority, target.inbound, target.tag)

    after = evidence.snapshot(path, paths=paths)
    evidence.deltas(before, after)
    for lane, matched in vpn_access.routes(connections, before, after).items():
        result["paths"][lane]["accepted_route"] = matched
    for lane, target in targets.items():
        result["paths"][lane]["pinned_outbound_counters_increased"] = _counter_activity(
            before, after, target.tag)
        if target.tag:
            ordinary, pinned = addresses.get("http_in"), addresses[lane]
            result["paths"][lane]["exit_matches_http_in"] = (
                ordinary == pinned if ordinary is not None and pinned is not None else None)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Send up to three bounded HTTPS GETs")
    parser.add_argument("--route", action="store_true", help="Match new CONNECTs in the Xray journal")
    args = parser.parse_args()
    if args.route and not args.live:
        parser.error("--route requires --live")
    try:
        report = observe(Paths.from_env(), live=args.live, route=args.route)
    except evidence.EvidenceError as exc:
        report = {"state": "inconclusive", "reason": str(exc), **exc.details()}
    except LockTimeout:
        report = {"state": "inconclusive", "reason": "apply_in_progress"}
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AttributeError, IndexError,
            config.ConfigError, cmd.CommandError):
        report = {"state": "inconclusive", "reason": "read_failed"}
    print(json.dumps(report, sort_keys=True))
    return 2 if report.get("state") == "inconclusive" else 0


if __name__ == "__main__":
    raise SystemExit(main())
