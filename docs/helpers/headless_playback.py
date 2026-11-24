"""Probe and measure a resolved HTTPS video on Linux using curl and mpv JSON IPC."""
from __future__ import annotations

import argparse
import contextlib
import ipaddress
import json
import math
import os
import re
import shutil
import socket
import statistics
import subprocess
import tempfile
import time
from itertools import pairwise
from pathlib import Path
from urllib.parse import urlsplit

from docs.helpers.selective_media_evidence import read_log
from docs.helpers.youtube_telemetry import media_host
from xgw.desync.experiment import private_path
from xgw.desync.schema import youtube_cdn_expiry

PROPERTIES = ("time-pos", "height", "paused-for-cache", "cache-speed", "demuxer-cache-time",
              "demuxer-cache-duration", "seeking")
PLAYBACK_SECONDS = (120, 300, 900)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def read_format(source):
    with source.open("rb") as stream:
        raw = stream.read(8 * 1024**2 + 1)
    if len(raw) > 8 * 1024**2:
        raise ValueError("format_size")
    info = json.loads(raw)
    url, duration = info["url"], info.get("duration")
    if (not isinstance(url, str) or len(url) > 32768
            or any(ord(c) < 33 or ord(c) > 126 for c in url) or not media_host(url)):
        raise ValueError("media_url")
    parts = urlsplit(url)
    if parts.username or parts.password or parts.fragment or parts.port not in (None, 443):
        raise ValueError("media_url")
    if info.get("height") != 720 or not number(duration) or duration < 150:
        raise ValueError("format_or_duration")
    expires = youtube_cdn_expiry(url)
    if expires is not None and expires <= time.time():
        raise ValueError("media_url_expired")
    bitrate = info.get("vbr") or info.get("tbr")
    return url, duration, bitrate * 1000 if number(bitrate) and bitrate > 0 else None


def tls_events(stderr):
    """Retain counts of client-side OpenSSL log events, never the raw trace."""
    events = {"client_hello": 0, "server_hello": 0, "inbound_alert": 0}
    for line in stderr.splitlines():
        if not line.startswith("* TLSv"):
            continue
        if line.endswith(" (OUT), TLS handshake, Client hello (1):"):
            events["client_hello"] += 1
        elif line.endswith(" (IN), TLS handshake, Server hello (2):"):
            events["server_hello"] += 1
        elif " (IN), TLS alert, " in line:
            events["inbound_alert"] += 1
    return events if any(events.values()) else None


def probe(url, size, *, peer=None, range_request=True, observe_tls=False):
    # Pass the signed URL through stdin. stdout includes only explicit metrics.
    output = ('{"status":"%{http_code}","bytes":%{size_download},"tcp":%{time_connect},'
              '"tls":%{time_appconnect},'
              '"first_byte":%{time_starttransfer},"elapsed":%{time_total},'
              '"remote_ip":"%{remote_ip}"')
    quoted_url = url.replace("\\", "\\\\").replace('"', '\\"')
    target = ["--resolve", f"{urlsplit(url).hostname}:443:{peer}"] if peer else []
    transfer = ["--range", f"0-{size - 1}"] if range_request else ["-4"]
    diagnostics = ["--verbose"] if observe_tls else []
    environment = None
    if observe_tls:
        output += ',"local_ip":"%{local_ip}","local_port":%{local_port}'
        environment = os.environ.copy()
        environment.pop("SSLKEYLOGFILE", None)
    proc = subprocess.run(
        ["curl", "-q", "--http1.1", "--noproxy", "*", "--proto", "=https", "--max-time", "20",
         "--connect-timeout", "10", "--max-filesize", str(size), *transfer,
         "--silent", *diagnostics, "--output", "/dev/null", "--write-out", output + "}",
         *target, "--config", "-"],
        input=f'url = "{quoted_url}"\n', capture_output=True, text=True, errors="replace",
        env=environment, timeout=25, check=False,
    )
    result = json.loads(proc.stdout or "{}")
    result["status"] = int(result.get("status") or 0)
    if result.get("remote_ip"):
        result["remote_ip"] = str(ipaddress.ip_address(result["remote_ip"]))
    result["ok"] = (proc.returncode == 0 and result.get("status") in (200, 206)
                    and result.get("bytes", 0) > 0)
    result["curl_rc"] = proc.returncode
    if observe_tls:
        result["tls_events"] = tls_events(proc.stderr)
    return result


def probe_pair(url):
    """Require one complete Range response and repeat on the same IPv4 peer."""
    def full_range(result):
        return result["ok"] and (result["status"], result["bytes"]) == (206, 65536)

    first = probe(url, 65536)
    if not full_range(first):
        return {"ok": False, "state": "initial_range_failed", "first": first}
    try:
        peer = ipaddress.IPv4Address(first.get("remote_ip"))
    except ipaddress.AddressValueError:
        return {"ok": False, "state": "peer_unconfirmed", "first": first}
    if not peer.is_global or peer.is_multicast:
        return {"ok": False, "state": "peer_unconfirmed", "first": first}
    pinned = probe(url, 65536, peer=peer)
    same_peer = pinned.get("remote_ip") == str(peer)
    ok = full_range(pinned) and same_peer
    return {"ok": ok, "state": "pass" if ok else "pinned_range_unconfirmed", "first": first,
            "pinned": pinned, "same_peer": same_peer}


class Player:
    def __init__(self, sock):
        self.stream = sock.makefile("rwb")
        self.request = 0

    def command(self, *command):
        self.request += 1
        serial = self.request
        self.stream.write(json.dumps({"command": command, "request_id": serial}).encode() + b"\n")
        self.stream.flush()
        for _ in range(128):
            line = self.stream.readline(65536)
            if not line:
                raise EOFError("mpv_closed")
            reply = json.loads(line)
            if reply.get("event") == "end-file":
                raise EOFError("mpv_end_file")
            if reply.get("request_id") == serial:
                return reply
        raise ValueError("mpv_ipc_reply")

    def sample(self):
        return {name: self.command("get_property", name).get("data") for name in PROPERTIES}


def measure(rows, required, bitrate):
    """Use elapsed sample intervals and playback position at 1×."""
    eligible = progress = stalls = quality = gaps = 0.0
    speed, buffers = [], []
    for first, last in pairwise(rows):
        seconds = last["mono"] - first["mono"]
        if not 0 < seconds <= 2.5 or not all(number(r.get("time-pos")) for r in (first, last)):
            gaps += max(0, seconds)
            continue
        if any(r.get("seeking") is not False for r in (first, last)):
            gaps += seconds
            continue
        movement = last["time-pos"] - first["time-pos"]
        if not 0 <= movement <= seconds + 0.5:
            gaps += seconds
            continue
        if last.get("paused-for-cache") is True:
            stalls += seconds
        if movement > 0.05 and last.get("paused-for-cache") is False:
            eligible += seconds
            progress += min(seconds, movement)
            if first.get("height") == last.get("height") == 720:
                quality += seconds
        buffer = last.get("demuxer-cache-duration")
        if number(buffer) and buffer >= 0:
            buffers.append(buffer)
        rate = last.get("cache-speed")
        if number(rate) and rate > 0:
            speed.append(rate)
    progress_ratio = progress / eligible if eligible else 0
    quality_ratio = quality / eligible if eligible else 0
    median_rate = statistics.median(speed) if speed else None
    minimum_buffer = min(buffers) if buffers else None
    read_ratio = 8 * median_rate / bitrate if median_rate is not None and bitrate else None
    return {"ok": eligible >= required and progress_ratio >= 0.98 and quality_ratio >= 0.95
            and gaps <= 5 and stalls <= 0.02 * required,
            "eligible_seconds": eligible, "progress_ratio": progress_ratio,
            "target_height_ratio": quality_ratio, "sampling_gap_seconds": gaps,
            "stall_seconds": stalls, "cache_min_seconds": minimum_buffer,
            "cache_buffer_below_5s": None if minimum_buffer is None else minimum_buffer < 5,
            "cache_read_to_bitrate_ratio": read_ratio,
            "cache_read_below_bitrate": None if read_ratio is None else read_ratio < 1,
            "cache_read_median_Bps": median_rate, "bitrate_bps": bitrate}


def playback_acceptance(rows, required):
    """Evaluate the first complete wall-clock window, including frozen playback."""
    times = [row.get("mono") for row in rows]
    if (not times or not all(map(number, times))
            or any(last <= first for first, last in pairwise(times))):
        return {"ok": False, "reason": "timestamps_unconfirmed"}
    end = times[0] + required
    observed = min(required, times[-1] - times[0])
    sampled = progress = quality = stalls = longest = run = 0.0
    for first, last in pairwise(rows):
        if first["mono"] >= end:
            break
        duration = last["mono"] - first["mono"]
        seconds = min(last["mono"], end) - first["mono"]
        if (duration > 2.5 or any(row.get("seeking") is not False for row in (first, last))
                or any(type(row.get("paused-for-cache")) is not bool for row in (first, last))
                or not all(number(row.get("time-pos")) for row in (first, last))):
            run = 0.0
            continue
        movement = last["time-pos"] - first["time-pos"]
        if not 0 <= movement <= duration + 0.5:
            run = 0.0
            continue
        sampled += seconds
        if first.get("height") == last.get("height") == 720:
            quality += seconds
        if last["paused-for-cache"] or movement <= 0.05:
            stalls += seconds
            run += seconds
            longest = max(longest, run)
        else:
            run = 0.0
            progress += min(duration, movement) * seconds / duration
    gaps = max(0.0, observed - sampled)
    progress_ratio = progress / required
    quality_ratio = quality / sampled if sampled else 0.0
    return {
        "ok": (times[-1] >= end and gaps <= 5 and progress_ratio >= 0.98
               and quality_ratio >= 0.99 and stalls <= 0.01 * required and longest <= 5),
        "required_seconds": required, "observed_seconds": observed,
        "progress_ratio": progress_ratio, "target_height_ratio": quality_ratio,
        "sampling_gap_seconds": gaps, "stall_seconds": stalls,
        "longest_stall_seconds": longest,
    }


def replay(summary_path, samples_path):
    """Recompute strict playback and cache metrics from a private recorded phase."""
    private_path(summary_path)
    private_path(samples_path)
    with summary_path.open("rb") as stream:
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise ValueError("summary_size")
    previous = json.loads(raw)
    required = previous["acceptance"]["required_seconds"]
    bitrate = previous["bitrate_bps"]
    if (type(required) is not int or required not in PLAYBACK_SECONDS
            or (bitrate is not None and (not number(bitrate) or bitrate <= 0))):
        raise ValueError("summary_metrics")
    logged = read_log(samples_path)
    rows = [row for row in logged if row.get("eligible_phase") is True]
    if not rows or logged[-len(rows):] != rows:
        raise ValueError("invalid_phase")

    result = measure(rows, required, bitrate)
    result.update(acceptance=playback_acceptance(rows, required), samples=len(rows),
                  seek_observed=rows[0].get("seek") is not None)
    fields = ("acceptance", "samples", "seek_observed", "cache_min_seconds", "cache_read_median_Bps")
    differing_fields = [name for name in fields if result[name] != previous[name]]
    result.update(ok=not differing_fields, differing_fields=differing_fields)
    return result


def player_sockets(pid):
    from docs.helpers.selective_probe_watch import parse_socket_stats

    try:
        output = subprocess.run(
            ["ss", "-HtaOeinp", "state", "big", "dport", "=", ":443"],
            capture_output=True, text=True, timeout=1, check=True,
        ).stdout
        owned = [line for line in output.splitlines() if re.search(rf"\bpid={pid},", line)]
        return parse_socket_stats("\n".join(owned), include_local_endpoint=True)["sockets"]
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def capture(url, duration, output, required, seek, *, peers=False):
    """Return one phase. Begin timing only after playback starts or the seek lands."""
    rows, target, previous = [], None, None
    seek_request = None
    outcome = "elapsed"
    fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as log, tempfile.TemporaryDirectory() as tmp:
        address = str(Path(tmp) / "mpv.sock")
        with subprocess.Popen(
            ["mpv", "--no-config", "--no-ytdl", "--no-terminal", "--idle=yes",
             "--vo=null", "--no-audio", "--tls-verify=yes", "--network-timeout=10",
             "--cache=yes", "--cache-secs=25", "--demuxer-max-bytes=32MiB",
             "--speed=1", f"--input-ipc-server={address}"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")},
        ) as proc, socket.socket(socket.AF_UNIX) as sock:
            try:
                deadline = time.monotonic() + 5
                while not Path(address).is_socket() and proc.poll() is None:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("mpv_socket")
                    time.sleep(0.1)
                sock.settimeout(3)
                sock.connect(address)
                player = Player(sock)
                capture_started_unix = time.time()
                if player.command("loadfile", url)["error"] != "success":
                    raise ValueError("loadfile")
                started = time.monotonic()
                while time.monotonic() - started < required + 65:
                    tick = time.monotonic()
                    row = player.sample()
                    row.update(mono=tick, unix=time.time())
                    if peers and tick - started < 180:
                        row["capture_started_unix"] = capture_started_unix
                        row["socket_start_unix"] = time.time()
                        row["sockets"] = player_sockets(proc.pid)
                        row["socket_unix"] = time.time()
                    if not rows:
                        position = row["time-pos"]
                        if (number(position) and row["height"] == 720 and row["seeking"] is False
                                and row["paused-for-cache"] is False
                                and number(previous) and position > previous):
                            landed = (seek_request is not None and abs(position - target) < 3
                                      and position > seek_request["cached_until"])
                            if seek is None or landed:
                                if landed:
                                    row["seek"] = {**seek_request, "landed": position}
                                rows.append(row)
                            elif target is None and position >= 5:
                                cache_end = row["demuxer-cache-time"]
                                if not number(cache_end):
                                    raise ValueError("seek_buffer_unknown")
                                target = max(position + seek, cache_end + 5)
                                if target + required + 15 >= duration:
                                    raise ValueError("seek_target_duration")
                                response = player.command("seek", target, "absolute+exact")
                                if response["error"] != "success":
                                    raise ValueError("seek_rejected")
                                seek_request = {"from": position, "cached_until": cache_end,
                                                "target": target}
                        previous = position
                    else:
                        rows.append(row)
                    row["eligible_phase"] = bool(rows)
                    log.write(json.dumps(row, allow_nan=False) + "\n")
                    log.flush()
                    if rows and tick - rows[0]["mono"] >= required + 15:
                        break
                    if not rows and tick - started >= 50:
                        outcome = "startup_unconfirmed" if target is None else "seek_unconfirmed"
                        break
                    time.sleep(max(0, tick + 1 - time.monotonic()))
            except (OSError, EOFError, ValueError, KeyError):
                outcome = "mpv_or_seek_error"
            finally:
                with contextlib.suppress(ProcessLookupError):
                    proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
    return rows, target, outcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Format JSON for probe/play, saved summary for replay")
    commands = parser.add_subparsers(dest="action", required=True)
    burst = commands.add_parser("probe")
    burst.add_argument("--bytes", type=int, choices=(65536, 10485760), default=65536)
    burst.add_argument("--peer", type=ipaddress.IPv4Address,
                       help="Use this public IPv4 address with the original hostname and TLS")
    commands.add_parser("probe-pair", help="Check a 64 KiB range twice on the same IPv4 peer")
    play = commands.add_parser("play")
    play.add_argument("--seconds", type=int, choices=PLAYBACK_SECONDS, required=True)
    play.add_argument("--seek-forward", type=int, choices=(480,))
    play.add_argument("--samples", type=Path, required=True)
    play.add_argument("--peers", action="store_true",
                      help="Record private TCP endpoints and counters for the first 180 s")
    play.add_argument("--strict", action="store_true",
                      help="Apply the complete-window playback and stall acceptance limits")
    saved = commands.add_parser("replay", help="Recompute saved strict playback without loading media")
    saved.add_argument("--samples", type=Path, required=True)
    args = parser.parse_args()
    try:
        if os.name != "posix":
            raise ValueError("dependencies")
        if args.action == "replay":
            result = replay(args.source, args.samples)
            print(json.dumps(result, allow_nan=False))
            return 0 if result["ok"] else 2
        if not shutil.which("curl" if args.action in ("probe", "probe-pair") else "mpv"):
            raise ValueError("dependencies")
        url, duration, bitrate = read_format(args.source)
        if args.action == "probe":
            if args.peer and (not args.peer.is_global or args.peer.is_multicast):
                raise ValueError("public_ipv4_required")
            result = probe(url, args.bytes, peer=args.peer)
        elif args.action == "probe-pair":
            result = probe_pair(url)
        else:
            if duration < args.seconds + 65 + (args.seek_forward or 0):
                raise ValueError("duration")
            rows, target, outcome = capture(url, duration, args.samples, args.seconds,
                                            args.seek_forward, peers=args.peers)
            result = measure(rows, args.seconds, bitrate)
            if args.strict:
                result["acceptance"] = playback_acceptance(rows, args.seconds)
                result["ok"] = result["acceptance"]["ok"]
            seek_evidence = rows[0].get("seek") if rows else None
            result.update(outcome=outcome, seek_target=target, samples=len(rows),
                          seek_observed=seek_evidence is not None, seek=seek_evidence)
            result["ok"] = result["ok"] and outcome == "elapsed"
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        result = {"ok": False, "error": ("invalid_replay" if args.action == "replay"
                                        else "invalid_format_or_runtime")}
    print(json.dumps(result, allow_nan=False))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
