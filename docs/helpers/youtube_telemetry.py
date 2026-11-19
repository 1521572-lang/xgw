"""Measure a visible YouTube player and its real CDP media traffic; never change XGW.

Optional Playwright dependency is imported only by collect. Summaries and unit tests use
stdlib. Output excludes signed URLs, headers, cookies, payloads and YouTube session IDs.
Network evidence is browser-side: it cannot prove the gateway's outbound or NFQUEUE path.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import ipaddress
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections import Counter
from itertools import pairwise
from pathlib import Path
from urllib.parse import urlsplit


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def token(value):
    return value if isinstance(value, str) and re.fullmatch(r"[\w.-]{1,96}", value) else None


def media_host(url):
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if (parsed.scheme == "https" and host.endswith(".googlevideo.com")
                and parsed.path == "/videoplayback"
                and re.fullmatch(r"[a-z0-9.-]{1,253}", host)):
            return host
    except ValueError:
        pass
    return None


class MediaNetwork:
    """Track in-flight streaming POSTs, redirects and completed requests without double counts."""

    def __init__(self, emit, clock):
        self.emit, self.clock = emit, clock
        self.active = {}
        self.encoded_bytes = 0
        self.data_bytes = 0
        self.requests = 0
        self.failures = 0
        self.canceled = 0
        self.statuses = Counter()
        self.protocols = Counter()

    def response(self, row, response):
        status = response.get("status")
        row["status"] = int(status) if number(status) else None
        row["protocol"] = token(response.get("protocol"))
        row["cache"] = bool(response.get("fromDiskCache") or response.get("fromServiceWorker")
                            or row.get("cache"))
        try:
            row["remote_ip"] = str(ipaddress.ip_address(response.get("remoteIPAddress", "")))
        except ValueError:
            row["remote_ip"] = None
        row["response_s"] = self.clock()
        self.statuses[str(row["status"])] += 1
        self.protocols[str(row["protocol"])] += 1
        self.emit({"kind": "response", **row})

    def handle(self, kind, params):
        rid = params.get("requestId")
        row = self.active.get(rid)
        if kind == "requestWillBeSent":
            if row:
                if params.get("redirectResponse"):
                    self.response(row, params["redirectResponse"])
                self.emit({"kind": "redirect", "at_s": self.clock(), **row})
                del self.active[rid]
            request = params.get("request", {})
            host = media_host(request.get("url", ""))
            if host:
                self.requests += 1
                self.active[rid] = {"id": self.requests, "host": host,
                                    "method": token(request.get("method")),
                                    "started_s": self.clock(), "encoded_bytes": 0,
                                    "data_bytes": 0, "cache": False}
                self.emit({"kind": "request", **self.active[rid]})
            return
        if not row:
            return
        if kind == "responseReceived":
            self.response(row, params.get("response", {}))
        elif kind == "requestServedFromCache":
            row["cache"] = True
        elif kind == "dataReceived":
            for source, dest in (("encodedDataLength", "encoded_bytes"),
                                 ("dataLength", "data_bytes")):
                value = params.get(source, 0)
                value = max(0, int(value)) if number(value) else 0
                row[dest] += value
                setattr(self, dest, getattr(self, dest) + value)
        elif kind in {"loadingFinished", "loadingFailed"}:
            if kind == "loadingFinished":
                final = params.get("encodedDataLength", 0)
                final = max(0, int(final)) if number(final) else 0
                self.encoded_bytes += max(0, final - row["encoded_bytes"])
                row["encoded_bytes"] = max(final, row["encoded_bytes"])
            else:
                error = params.get("errorText", "")
                row["error"] = error if re.fullmatch(r"net::ERR_[A-Z_]+", error) else "unknown"
                row["canceled"] = params.get("canceled") is True
                self.canceled += row["canceled"]
                self.failures += not row["canceled"]
            self.emit({"kind": kind, "at_s": self.clock(), **row})
            del self.active[rid]

    def snapshot(self):
        return {"encoded_bytes": self.encoded_bytes, "data_bytes": self.data_bytes,
                "requests": self.requests, "inflight": len(self.active),
                "failures": self.failures, "canceled": self.canceled,
                "statuses": dict(self.statuses),
                "protocols": dict(self.protocols)}


def gateway_snapshot(path, now):
    if path is None:
        return {"observation": "not_collected"}
    try:
        with path.open(encoding="utf-8") as stream:
            raw = stream.read(4_000_001)
        if len(raw) > 4_000_000:
            return {"observation": "oversize"}
        data = json.loads(raw)
        updated = data.get("updated")
        age = now - updated if number(updated) else None
        selected = data.get("zapret2") or {}
        capture = data.get("capture") or {}
        engine = capture.get("nfqws2") or {}
        return {"observation": "fresh" if age is not None and 0 <= age <= 90 else "stale",
                "age_seconds": age, "policy_key": token(data.get("zapret2_policy_key")),
                "selected_state": token(selected.get("state")),
                "engine_state": token(engine.get("state")),
                "reason": token(selected.get("reason")),
                "reported_without_vpn": selected.get("without_vpn") is True,
                "capture_loaded": capture.get("loaded") is True}
    except (OSError, ValueError, AttributeError, TypeError):
        return {"observation": "unavailable"}


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    return values[round((len(values) - 1) * fraction)]


def eligible(sample, video_id):
    return (sample.get("has_video") is True and sample.get("video_id") == video_id
            and not any(sample.get(k) for k in ("ad", "hidden", "paused", "seeking", "ended"))
            and number(sample.get("position")) and number(sample.get("playback_rate"))
            and sample["playback_rate"] > 0)


def summarize(samples, video_id, target_height):
    """Conservative one-second estimates. Events retained separately catch subsecond waits."""
    eligible_s = playing_s = stalled_s = frozen_s = progress = missing_s = 0.0
    frames = dropped = waiting = stall_count = 0
    stall_open = False
    buffers, resolutions = [], Counter()
    play_events, startup_delays, overflows = {}, [], {}
    first_progress = None
    for current in samples:
        doc = current.get("document_id")
        overflows[doc] = max(overflows.get(doc, 0), current.get("event_overflow", 0))
        for event in current.get("events", []):
            if (current.get("video_id") != video_id or event.get("ad") or event.get("hidden")
                    or event.get("media_id") != current.get("media_id")):
                continue
            key = (doc, event.get("media_id"))
            if event.get("name") == "play":
                play_events[key] = event["at_ms"]
            if event.get("name") == "playing" and key in play_events:
                startup_delays.append(max(0, (event["at_ms"] - play_events.pop(key)) / 1000))
            waiting += (event.get("name") == "waiting" and not event.get("seeking")
                        and not event.get("paused"))
        if eligible(current, video_id) and number(current.get("buffer_seconds")):
            buffers.append(current["buffer_seconds"])
    for previous, current in pairwise(samples):
        dt = current["t_s"] - previous["t_s"]
        same = all(previous.get(k) == current.get(k) for k in ("document_id", "media_id"))
        transition = any(e.get("name") in {"seeking", "seeked", "emptied", "loadedmetadata",
                                           "pause", "ended"}
                         for e in current.get("events", []))
        if not 0 < dt <= 2.5:
            missing_s += max(0, dt)
            stall_open = False
            continue
        if not (same and not transition and eligible(previous, video_id)
                and eligible(current, video_id)):
            stall_open = False
            continue
        delta = current["position"] - previous["position"]
        rate = previous["playback_rate"]
        if delta < 0 or delta > dt * rate + 0.5:
            stall_open = False  # unobserved seek/discontinuity; never count it as playback
            continue
        eligible_s += dt
        progress += delta
        if first_progress is None and delta > 0.1:
            first_progress = current["t_s"]
        playing_s += min(dt, delta / rate)
        is_stall = delta < 0.1 and current.get("ready_state", 4) < 3
        if is_stall:
            stalled_s += dt
            stall_count += not stall_open
        elif delta < 0.1:
            frozen_s += dt
        stall_open = is_stall
        resolutions[str(previous.get("height", 0))] += dt
        for key, dest in (("total_frames", "frames"), ("dropped_frames", "dropped")):
            a, b = previous.get(key), current.get(key)
            if number(a) and number(b) and b >= a:
                if dest == "frames":
                    frames += b - a
                else:
                    dropped += b - a
    high = sum(seconds for height, seconds in resolutions.items() if int(height) >= target_height)
    return {"samples": len(samples), "eligible_seconds": eligible_s,
            "estimated_playing_seconds": playing_s, "content_progress_seconds": progress,
            "estimated_stall_seconds": stalled_s, "estimated_stall_count": stall_count,
            "estimated_stall_ratio": stalled_s / eligible_s if eligible_s else None,
            "freeze_with_ready_data_seconds": frozen_s, "waiting_events": waiting,
            "first_content_progress_at_s": first_progress,
            "play_to_playing_delays_seconds": startup_delays,
            "lost_media_events": sum(overflows.values()),
            "sampling_gap_seconds": missing_s,
            "buffer_p10_seconds": percentile(buffers, 0.1),
            "buffer_median_seconds": percentile(buffers, 0.5),
            "observed_frames": frames, "dropped_frames": dropped,
            "dropped_frame_ratio": dropped / frames if frames else None,
            "height_seconds": dict(resolutions), "target_height": target_height,
            "target_height_ratio": high / eligible_s if eligible_s else None,
            "route_verdict": "UNKNOWN", "zapret2_effectiveness": "NOT_ESTABLISHED",
            "audio_verdict": "NOT_TESTED"}


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def write_report(out, summary, samples):
    columns = ("t_s", "position", "height", "buffer_seconds", "total_frames", "dropped_frames",
               "ready_state", "paused", "ad", "hidden", "seeking", "media_encoded_bytes")
    with (out / "timeline.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for sample in samples:
            row = {key: sample.get(key) for key in columns}
            row["media_encoded_bytes"] = sample.get("network", {}).get("encoded_bytes")
            writer.writerow(row)
    lines = [f"# YouTube telemetry: {summary['label']}", "",
             f"Collection: **{summary['outcome']}**. Video: `{summary['video_id']}`.", "",
             "| Measurement | Value |", "|---|---|"]
    for key in ("eligible_seconds", "estimated_playing_seconds", "estimated_stall_seconds",
                "estimated_stall_count", "waiting_events", "sampling_gap_seconds",
                "buffer_p10_seconds", "buffer_median_seconds", "dropped_frame_ratio",
                "target_height_ratio", "freeze_with_ready_data_seconds"):
        value = summary[key]
        rendered = "unknown" if value is None else str(round(value, 3))
        lines.append(f"| {key} | {rendered} |")
    lines.extend([
        "", "Route: **UNKNOWN**. Zapret2 benefit: **NOT_ESTABLISHED**. Audio: NOT_TESTED.",
        "", "One-second estimates exclude ads, pauses, seeks, hidden pages and gaps.",
        "Media counters cover the entire tab, possibly including ads and prefetch.",
        "Fresh media bytes plus playback still require independent gateway route evidence.",
        "Connection speed in the optional overlay is an estimate, not link capacity.", "",
    ])
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")


@contextlib.contextmanager
def browser_context(pw, args):
    flags = ["--no-proxy-server"]
    if args.disable_quic:
        flags.append("--disable-quic")
    if not args.desktop_chrome:
        browser = pw.chromium.launch(channel=args.channel, headless=False,
                                     chromium_sandbox=True, args=flags)
        try:
            yield browser, browser.new_context(viewport={"width": 1440, "height": 900})
        finally:
            browser.close()
        return

    chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if chrome is None:
        raise OSError("desktop_chrome_missing")
    with tempfile.TemporaryDirectory(prefix="xgw-chrome-") as profile:
        port_file = Path(profile) / "DevToolsActivePort"
        cmd = [chrome, *flags, f"--user-data-dir={profile}", "--remote-debugging-port=0",
               "--remote-debugging-address=127.0.0.1", "--no-first-run",
               "--no-default-browser-check", "--window-size=1440,900", "about:blank"]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 25
            while proc.poll() is None and time.monotonic() < deadline:
                if port_file.exists():
                    lines = port_file.read_text(encoding="ascii").splitlines()
                    if (len(lines) == 2 and re.fullmatch("[0-9]{1,5}", lines[0])
                            and 0 < int(lines[0]) <= 65535
                            and re.fullmatch(r"/devtools/browser/[0-9a-f-]{36}", lines[1])):
                        break
                time.sleep(0.1)
            else:
                raise OSError("desktop_chrome_startup")
            browser = pw.chromium.connect_over_cdp(f"ws://127.0.0.1:{lines[0]}{lines[1]}",
                                                   timeout=10000)
            yield browser, browser.contexts[0]
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)


def collect(args, trial=None):
    # Optional dependency: no browser/OS access is needed to import the analyzer.
    from playwright.sync_api import Error, TimeoutError, sync_playwright

    os.umask(0o077)
    args.out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    clock = lambda: round(time.monotonic() - start, 6)  # noqa: E731
    samples = []
    outcome = "complete"
    meta = {"schema": 1, "label": args.label, "video_id": args.video,
            "started_unix": time.time(), "requested_seconds": args.seconds,
            "channel": args.channel, "disable_quic": args.disable_quic,
            "browser_launch": "desktop_cdp" if args.desktop_chrome else "playwright",
            "target_height": args.height, "route": "UNKNOWN"}
    dump(args.out / "run.json", meta)
    with (args.out / "network.jsonl").open("w", encoding="utf-8") as network_file, \
            (args.out / "samples.jsonl").open("w", encoding="utf-8") as sample_file:
        def emit(record):
            network_file.write(json.dumps(record, allow_nan=False) + "\n")
            network_file.flush()

        network = MediaNetwork(emit, clock)
        try:
            with sync_playwright() as pw, browser_context(pw, args) as (browser, context):
                meta["browser_version"] = browser.version
                context.add_init_script(path=Path(__file__).with_suffix(".js"))
                page = context.new_page()
                session = context.new_cdp_session(page)
                for name in ("requestWillBeSent", "responseReceived", "dataReceived",
                             "loadingFinished", "loadingFailed", "requestServedFromCache"):
                    session.on("Network." + name,
                               lambda params, name=name: network.handle(name, params))
                session.send("Network.enable")
                # Cache remains normal, but every run gets a fresh context and profile.
                # No route interception, body download or replay of signed/SABR requests.
                with contextlib.suppress(TimeoutError):
                    page.goto("https://www.youtube.com/watch?v=" + args.video,
                              wait_until="domcontentloaded", timeout=30000)
                print("Browser opened. Select quality and handle consent if prompted.", flush=True)
                if trial:
                    page.bring_to_front()
                else:
                    print("Start the video and open Stats for nerds.", flush=True)
                deadline = time.monotonic() + args.seconds
                while time.monotonic() < deadline:
                    tick = time.monotonic()
                    try:
                        sample = page.evaluate("() => window.__xgwTelemetry?.() || {}")
                    except Error:
                        if page.is_closed():
                            outcome = "browser_closed"
                            break
                        sample = {"probe_error": True}
                    sample.update(t_s=clock(), unix=time.time(), network=network.snapshot(),
                                  gateway=gateway_snapshot(args.status_file, time.time()))
                    samples.append(sample)
                    # Store the sample even if navigating/closing the tab interrupts control.
                    try:
                        terminal = trial.step(page, samples) if trial else None
                    finally:
                        sample_file.write(json.dumps(sample, allow_nan=False) + "\n")
                        sample_file.flush()
                    if terminal:
                        outcome = terminal
                        break
                    if len(samples) % 60 == 0:
                        print(f"samples={len(samples)} media_bytes={network.encoded_bytes}",
                              flush=True)
                    page.wait_for_timeout(max(10, (1 - (time.monotonic() - tick)) * 1000))
                else:
                    if trial:
                        outcome = "measurement_timeout"
                for row in network.active.values():
                    emit({"kind": "inflight_at_stop", "at_s": clock(), **row})
                # Intentional shutdown must not become a measured transport failure.
                with contextlib.suppress(Error):
                    session.detach()
        except KeyboardInterrupt:
            outcome = "interrupted"
        except (Error, OSError):
            # Exception text may contain signed URLs or a browser command line.
            outcome = "browser_error"
        finally:
            meta.update(outcome=outcome, finished_unix=time.time())
            dump(args.out / "run.json", meta)
            summary = {**meta, **summarize(samples, args.video, args.height),
                       "network": network.snapshot()}
            if trial:
                summary["verification"] = trial.finish(samples, outcome)
            dump(args.out / "summary.json", summary)
            write_report(args.out, summary, samples)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if outcome == "complete" and samples else 2


def verify(args):
    from docs.helpers.playback_trial import SECONDS, PlaybackTrial

    os.umask(0o077)
    args.out.mkdir(parents=True, exist_ok=False)
    attempts = []
    for attempt in range(1, args.attempts + 1):
        folder = args.out / f"attempt-{attempt}"
        options = argparse.Namespace(**(vars(args) | {
            "out": folder, "seconds": SECONDS[args.verify] + 150,
        }))
        collect(options, PlaybackTrial(args.verify, args.video))
        result = json.loads((folder / "summary.json").read_text(encoding="utf-8"))["verification"]
        attempts.append(result)
        report = {"ok": result["ok"], "attempts": attempts, "route_verdict": "UNKNOWN"}
        dump(args.out / "verification.json", report)
        if result["ok"] or result["outcome"] in (
            "interrupted", "browser_closed", "seek_unavailable", "browser_error"
        ):
            break
    return 0 if attempts[-1]["ok"] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, help="Public YouTube video ID (11 characters)")
    parser.add_argument("--label", required=True, help="Trial label; not route evidence")
    parser.add_argument("--out", type=Path, required=True, help="New private output directory")
    parser.add_argument("--seconds", type=int, help="Passive collection time (default 1200 s)")
    parser.add_argument("--verify", choices=("control", "long", "seek"),
                        help="Start visible playback and measure 120/900/300 eligible seconds")
    parser.add_argument("--attempts", type=int, choices=(1, 2), default=1,
                        help="Maximum independent verification attempts")
    parser.add_argument("--height", type=int, choices=(480, 720, 1080, 1440, 2160), default=720)
    parser.add_argument("--channel", choices=("chrome", "chromium", "msedge"), default="chrome")
    parser.add_argument("--desktop-chrome", action="store_true",
                        help="Start installed Google Chrome with its own temporary desktop profile")
    parser.add_argument("--disable-quic", action="store_true", help="Use for the T04 TCP trial")
    parser.add_argument("--status-file", type=Path, help="Optional readable gateway status.json")
    args = parser.parse_args()
    if not re.fullmatch(r"[\w-]{11}", args.video, flags=re.ASCII):
        parser.error("invalid public video ID")
    if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}", args.label):
        parser.error("label must be 1..80 ASCII letters/digits/._-")
    if args.verify and (args.seconds is not None or args.height != 720):
        parser.error("verification measures 720p for a fixed time")
    if args.desktop_chrome and args.channel != "chrome":
        parser.error("--desktop-chrome requires the chrome channel")
    if args.attempts != 1 and not args.verify:
        parser.error("--attempts requires --verify")
    if args.seconds is not None and not 30 <= args.seconds <= 3600:
        parser.error("seconds must be between 30 and 3600")
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        parser.error("run as the desktop user, not root")
    if args.verify:
        return verify(args)
    if args.seconds is None:
        args.seconds = 1200
    return collect(args)


if __name__ == "__main__":
    raise SystemExit(main())
