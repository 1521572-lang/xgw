"""Read media DATA frames from a bounded Chrome NetLog with HTTP/2."""
from __future__ import annotations

import ipaddress
import json

from docs.helpers.youtube_telemetry import media_host

MAX_BYTES = 128 * 1024**2


def _headers(params):
    # Chromium records HTTP/2 pseudo-headers as lines such as ":status: 206".
    fields = {}
    for header in params.get("headers", []):
        if isinstance(header, str) and header.startswith(":"):
            key, sep, value = header[1:].partition(":")
            if sep:
                fields[key] = value.strip()
    return fields


def _peer(address):
    if not isinstance(address, str):
        return None
    host, _, port = address.rpartition(":")
    if port != "443":
        return None
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None
    return str(ip.ipv4_mapped or ip) if isinstance(ip, ipaddress.IPv6Address) else str(ip)


def read_media(path):
    """Return timestamped browser byte intervals, plus bounds of the full log."""
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("netlog_size")
    log = json.loads(raw)
    constants = log["constants"]
    kinds = {code: name for name, code in constants["logEventTypes"].items()}
    offset = int(constants["timeTickOffset"])
    peers, sockets, streams, media = {}, {}, {}, {}
    first = last = None
    for event in log["events"]:
        tick = int(event["time"])
        first = tick if first is None else min(tick, first)
        last = tick if last is None else max(tick, last)
        kind = kinds.get(event["type"])
        source = event["source"]["id"]
        params = event.get("params") or {}
        if kind == "TCP_CONNECT_ATTEMPT" and (ip := _peer(params.get("remote_address"))):
            peers[source] = ip
        elif kind == "HTTP2_SESSION_INITIALIZED":
            sockets[source] = (params.get("source_dependency") or {}).get("id")
        elif kind == "HTTP2_SESSION_SEND_HEADERS":
            headers = _headers(params)
            authority, path_part = headers.get("authority", ""), headers.get("path", "")
            key = (source, params.get("stream_id"))
            if (type(key[1]) is int and path_part.startswith("/") and
                    headers.get("method") in ("GET", "POST") and
                    media_host(f"https://{authority}{path_part}")):
                streams[key] = False
        elif kind == "HTTP2_SESSION_RECV_HEADERS":
            key = (source, params.get("stream_id", params.get("id")))
            status = _headers(params).get("status")
            if key in streams and status and not status.startswith("1"):
                streams[key] = status in ("200", "206")
        elif kind == "HTTP2_SESSION_RECV_DATA":
            stream_id, size = params.get("stream_id"), params.get("length")
            if not streams.get((source, stream_id)) or type(size) is not int or size <= 0:
                continue
            # Split by source, stream and second. Keep exact first/last times for joins.
            stamp = (offset + tick) / 1000
            key = (source, stream_id, (offset + tick) // 1000)
            row = media.setdefault(key, {"kind": "media_bytes", "start_unix": stamp,
                                         "end_unix": stamp, "encoded_bytes": 0})
            row["start_unix"] = min(row["start_unix"], stamp)
            row["end_unix"] = max(row["end_unix"], stamp)
            row["encoded_bytes"] += size
    if first is None or last <= first:
        raise ValueError("netlog_empty")
    result = [dict(row, remote_ip=peers.get(sockets.get(source)))
              for (source, _, _), row in media.items()]
    result.sort(key=lambda row: row["start_unix"])
    return result, ((offset + first) / 1000, (offset + last) / 1000)
