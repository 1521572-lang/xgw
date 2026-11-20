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

from docs.helpers.selective_probe_watch import parse_socket_stats
from docs.helpers.youtube_telemetry import media_host
from xgw.desync.schema import youtube_cdn_expiry

PROPERTIES = ("time-pos", "height", "paused-for-cache", "cache-speed", "demuxer-cache-time",
              "demuxer-cache-duration", "seeking")


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


def probe(url, size):
    # Pass the signed URL through stdin. stdout includes only explicit metrics.
    output = ('{"status":"%{http_code}","bytes":%{size_download},"tls":%{time_appconnect},'
              '"first_byte":%{time_starttransfer},"elapsed":%{time_total},'
              '"remote_ip":"%{remote_ip}"}')
    quoted_url = url.replace("\\", "\\\\").replace('"', '\\"')
    proc = subprocess.run(
        ["curl", "-q", "--http1.1", "--noproxy", "*", "--proto", "=https", "--max-time", "20",
         "--connect-timeout", "10", "--max-filesize", str(size), "--range", f"0-{size - 1}",
         "--silent", "--output", "/dev/null", "--write-out", output, "--config", "-"],
        input=f'url = "{quoted_url}"\n', capture_output=True, text=True, timeout=25, check=False,
    )
    result = json.loads(proc.stdout or "{}")
    result["status"] = int(result.get("status") or 0)
    if result.get("remote_ip"):
        result["remote_ip"] = str(ipaddress.ip_address(result["remote_ip"]))
    result["ok"] = (proc.returncode == 0 and result.get("status") in (200, 206)
                    and result.get("bytes", 0) > 0)
    result["curl_rc"] = proc.returncode
    return result


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
    verdict = "INSUFFICIENT_DATA"
    if len(rows) >= 10:
        verdict = "RATE_UNKNOWN"
        if (stalls > 0 or (minimum_buffer is not None and minimum_buffer < 5)
                or (bitrate and median_rate is not None and median_rate < bitrate / 8)):
            verdict = "THROTTLED"
        elif bitrate and median_rate is not None and minimum_buffer is not None:
            verdict = "OK" if median_rate >= 1.5 * bitrate / 8 else "LOW_HEADROOM"
    return {"ok": eligible >= required and progress_ratio >= 0.98 and quality_ratio >= 0.95
            and gaps <= 5 and stalls <= 0.02 * required,
            "eligible_seconds": eligible, "progress_ratio": progress_ratio,
            "target_height_ratio": quality_ratio, "sampling_gap_seconds": gaps,
            "stall_seconds": stalls, "cache_min_seconds": minimum_buffer,
            "cache_read_median_Bps": median_rate, "bitrate_bps": bitrate, "line": verdict}


def player_sockets(pid):
    try:
        output = subprocess.run(
            ["ss", "-HtaOeinp", "state", "big", "dport", "=", ":443"],
            capture_output=True, text=True, timeout=1, check=True,
        ).stdout
        owned = [line for line in output.splitlines() if re.search(rf"\bpid={pid},", line)]
        return parse_socket_stats("\n".join(owned))["sockets"]
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def capture(url, duration, output, required, seek, *, peers=False):
    """Return one phase. Begin timing only after playback starts or the seek lands."""
    rows, target, previous = [], None, None
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
                if player.command("loadfile", url)["error"] != "success":
                    raise ValueError("loadfile")
                started = time.monotonic()
                while time.monotonic() - started < required + 65:
                    tick = time.monotonic()
                    row = player.sample()
                    row.update(mono=tick, unix=time.time())
                    if peers and tick - started < 180:
                        row["sockets"] = player_sockets(proc.pid)
                        row["socket_unix"] = time.time()
                    if not rows:
                        position = row["time-pos"]
                        if (number(position) and row["height"] == 720 and row["seeking"] is False
                                and row["paused-for-cache"] is False
                                and number(previous) and position > previous):
                            landed = target is not None and abs(position - target) < 3
                            if seek is None or landed:
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
    parser.add_argument("format_json", type=Path)
    commands = parser.add_subparsers(dest="action", required=True)
    burst = commands.add_parser("probe")
    burst.add_argument("--bytes", type=int, choices=(65536, 10485760), default=65536)
    play = commands.add_parser("play")
    play.add_argument("--seconds", type=int, choices=(120, 300, 900), required=True)
    play.add_argument("--seek-forward", type=int, choices=(480,))
    play.add_argument("--samples", type=Path, required=True)
    play.add_argument("--peers", action="store_true",
                      help="Record private TCP socket counters for the first 180 s")
    args = parser.parse_args()
    try:
        if os.name != "posix" or not shutil.which("curl" if args.action == "probe" else "mpv"):
            raise ValueError("dependencies")
        url, duration, bitrate = read_format(args.format_json)
        if args.action == "probe":
            result = probe(url, args.bytes)
        else:
            if duration < args.seconds + 65 + (args.seek_forward or 0):
                raise ValueError("duration")
            rows, target, outcome = capture(url, duration, args.samples, args.seconds,
                                            args.seek_forward, peers=args.peers)
            result = measure(rows, args.seconds, bitrate)
            result.update(outcome=outcome, seek_target=target, samples=len(rows),
                          seek_observed=args.seek_forward is not None and bool(rows))
            result["ok"] = result["ok"] and outcome == "elapsed"
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        result = {"ok": False, "error": "invalid_format_or_runtime"}
    print(json.dumps(result, allow_nan=False))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
