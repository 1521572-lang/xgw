"""Attribute one ordinary HTTPS request from a LAN client to XGW's TPROXY route."""

from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path

from . import route_evidence, vpn_access
from .experiment import private_path

TRACE_HOST = "www.cloudflare.com"
MAX_TRACE_BYTES = 4096
MAX_JOURNAL_BYTES = 4 * 1024 * 1024
PRIVATE_NETWORKS = tuple(ipaddress.IPv4Network(net) for net in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10"))


def _lan_address(value):
    if not isinstance(value, str):
        raise ValueError("lan_address")
    address = ipaddress.IPv4Address(value)
    if not any(address in network for network in PRIVATE_NETWORKS):
        raise ValueError("lan_address")
    return address


def _client_route(client, gateway, before, after):
    host, source, hop = (_lan_address(item) for item in
                         (gateway, client.get("local_ip"), client.get("next_hop")))
    peer_text, port = client.get("remote_ip"), client.get("local_port")
    if not isinstance(peer_text, str) or type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("client_socket")
    peer = ipaddress.IPv4Address(peer_text)
    if host != hop or source == host or not peer.is_global or peer.is_multicast:
        raise ValueError("client_route")
    stamps = [round(row["unix"] * vpn_access.MICROSECONDS) for row in (before, after)]
    return vpn_access.Connection(*stamps, (str(source), port), (TRACE_HOST, 443),
                                 "tproxy-in", "", (str(peer), 443))


def analyze(client, gateway, journal, before, after):
    route_evidence.deltas(before, after)
    http, size, curl_rc = (client.get(field) for field in ("http", "bytes", "curl_rc"))
    if (type(http) is not int or not 0 <= http <= 599 or type(size) is not int
            or not 0 <= size <= 16 * 1024 * 1024 or type(curl_rc) is not int
            or not 0 <= curl_rc <= 255):
        raise ValueError("client_outcome")
    result = {"http": http, "bytes": size, "curl_rc": curl_rc,
              "https_complete": curl_rc == 0 and http == 200 and 0 < size <= MAX_TRACE_BYTES}
    try:
        connection = _client_route(client, gateway, before, after)
    except ValueError:
        result["accepted_route"] = {"state": "client_route_unconfirmed"}
    else:
        result["accepted_route"] = vpn_access.match(connection, journal, before, after)
    return result


def _read(path, limit):
    private_path(path)
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("evidence_size_limit")
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", required=True, help="LAN IPv4 of the observed gateway")
    for name in ("client", "before", "after", "journal"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    try:
        client = json.loads(_read(args.client, 4096))
        before = route_evidence._read_snapshot(args.before)
        after = route_evidence._read_snapshot(args.after)
        journal = [json.loads(line) for line in _read(args.journal, MAX_JOURNAL_BYTES).splitlines()]
        if not isinstance(client, dict) or not all(isinstance(row, dict) for row in journal):
            raise ValueError("evidence_schema")
        result = analyze(client, args.gateway, journal, before, after)
    except route_evidence.EvidenceError as exc:
        result = {"state": "inconclusive", "reason": str(exc), **exc.details()}
    except (OSError, ValueError, TypeError, AttributeError, OverflowError, KeyError, RecursionError):
        result = {"state": "inconclusive", "reason": "invalid_or_missing_evidence"}
    print(json.dumps(result, sort_keys=True))
    return 2 if result.get("state") == "inconclusive" else 0


if __name__ == "__main__":
    raise SystemExit(main())
