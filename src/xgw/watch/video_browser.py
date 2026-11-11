"""Isolated Firefox and the bounded VPN relay for the video probe experiment."""

import contextlib
import json
import os
import random
import re
import select
import signal
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from .. import fetch, zapret2
from ..generator import builder
from . import video_probe

SEARCH = "/snap/bin:/usr/local/bin:/usr/bin:/bin"
LIMIT = 16 * 1024 * 1024
SESSION_TIMEOUT = 30
EPHEMERAL_PORTS = Path("/proc/sys/net/ipv4/ip_local_port_range")
ASSETS = ["domain:youtube.com", "domain:ytimg.com", "domain:googlevideo.com",
          "full:youtubei.googleapis.com", "full:jnn-pa.googleapis.com", "domain:gstatic.com"]
CONNECT = re.compile(rb"CONNECT ([a-zA-Z0-9.-]+):443 HTTP/1\.[01]")
OBSERVE = """
const host = location.hostname;
if (!['youtube.com', 'www.youtube.com', 'consent.youtube.com'].includes(host))
    return {state: 'other_page'};
const reject = Array.from(document.querySelectorAll('button')).find(
    b => /^Reject all$/i.test((b.getAttribute('aria-label') || b.innerText || '').trim()));
if (reject && arguments[0]) { reject.click(); return {state: 'consent_rejected'}; }
if (reject || host === 'consent.youtube.com') return {state: 'consent'};
const v = document.querySelector('video');
const ad = !!document.querySelector('.ad-showing');
const error = document.querySelector('.ytp-error, yt-playability-error-supported-renderers');
if (error && error.innerText.trim()) return {state: 'player_refused'};
if (v && v.error) return {state: 'media_error'};
if (!v || ad) return {state: ad ? 'ad' : 'no_video'};
v.muted = true;
if (v.paused) v.play().catch(() => {});
const urls = performance.getEntriesByType('resource').reverse()
    .map(entry => entry.name).filter(url => url.length <= 8192 && url.includes('/videoplayback?'))
    .slice(0, 16);
const position = v.videoWidth > 0 && !v.paused && !v.seeking ? v.currentTime : null;
return {state: 'player', position, urls, agent: navigator.userAgent};
"""


class Relay(socketserver.ThreadingTCPServer):
    daemon_threads = True

    def __init__(self, port, password, deadline):
        super().__init__(("127.0.0.1", 0), Tunnel)
        self.upstream = ("127.0.0.1", port)
        self.password, self.deadline = password, deadline
        self.stopped = threading.Event()
        self.lock = threading.Lock()
        self.spent = self.connections = 0

    def verify_request(self, request, address):
        self.connections += 1
        return self.connections <= 128 and not self.stopped.is_set()

    def charge(self, size):
        with self.lock:
            if self.stopped.is_set():
                return False
            if self.spent + size > LIMIT:
                self.stopped.set()
                return False
            self.spent += size
            return True


class Tunnel(socketserver.BaseRequestHandler):
    def handle(self):
        relay, client = self.server, self.request
        try:
            head = b""
            while fetch.HEAD_END not in head and len(head) < 8192:
                remaining = relay.deadline - time.monotonic()
                if remaining <= 0 or relay.stopped.is_set():
                    return
                client.settimeout(min(2, remaining))
                chunk = client.recv(min(1024, 8192 - len(head)))
                if not chunk:
                    return
                head += chunk
            match = CONNECT.fullmatch(head.split(b"\r\n", 1)[0])
            if not head.endswith(fetch.HEAD_END) or not match:
                return
            host = match[1].decode("ascii").lower()
            if not zapret2.matches(host, ASSETS):
                return
            with fetch.open_tunnel(
                relay.upstream, host, 443, timeout=4, user=builder.PROBE_USER,
                password=relay.password, deadline=relay.deadline, cancel=relay.stopped,
            ) as upstream:
                client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                peers = {client: upstream, upstream: client}
                while not relay.stopped.is_set() and time.monotonic() < relay.deadline:
                    ready, _, _ = select.select(list(peers), [], [], 0.5)
                    for source in ready:
                        data = source.recv(16384)
                        if not data or not relay.charge(len(data)):
                            return
                        peers[source].settimeout(1)
                        peers[source].sendall(data)
        except (OSError, fetch.ProxyError, fetch.Cancelled):
            return


class Marionette:
    def __init__(self, sock, deadline):
        self.sock, self.deadline, self.seq = sock, deadline, 0
        greeting = self.read()
        if not isinstance(greeting, dict) or greeting.get("marionetteProtocol") != 3:
            raise ValueError("unexpected_marionette")

    def recv(self, size, deadline, max_wait):
        data = bytearray()
        while len(data) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            self.sock.settimeout(min(remaining, max_wait))
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise EOFError
            data.extend(chunk)
        return bytes(data)

    def read(self, *, deadline=None, max_wait=8):
        if deadline is None:
            deadline = self.deadline
        prefix = b""
        for _ in range(8):
            char = self.recv(1, deadline, max_wait)
            if char == b":" and prefix:
                size = int(prefix)
                if size <= 256 * 1024:
                    return json.loads(self.recv(size, deadline, max_wait))
                break
            if not char.isdigit():
                break
            prefix += char
        raise ValueError("bad_marionette_frame")

    def call(self, method, params, *, timeout=None):
        now = time.monotonic()
        deadline = self.deadline if timeout is None else min(self.deadline, now + timeout)
        if deadline <= now:
            raise TimeoutError
        self.seq += 1
        body = json.dumps([0, self.seq, method, params]).encode()
        self.sock.settimeout(min(deadline - now, 1))
        self.sock.sendall(str(len(body)).encode() + b":" + body)
        while True:
            reply = self.read(deadline=deadline, max_wait=8 if timeout is None else timeout)
            if isinstance(reply, list) and len(reply) == 4 and reply[:2] == [1, self.seq]:
                if reply[2]:
                    raise ValueError("marionette_command")
                return reply[3]


def observe(client, page, domains, relay, profile, progress):
    progress("session_requested")
    try:
        session = client.call("WebDriver:NewSession", {"capabilities": {"alwaysMatch": {
            "pageLoadStrategy": "eager", "timeouts": {"pageLoad": 7000, "script": 5000}}}},
            timeout=SESSION_TIMEOUT)
    except TimeoutError:
        return "", "", "browser_session_timeout", False
    capabilities = session.get("capabilities") if isinstance(session, dict) else None
    reported = capabilities.get("moz:profile") if isinstance(capabilities, dict) else None
    if not isinstance(reported, str) or Path(reported).resolve() != profile.resolve():
        return "", "", "browser_profile_unverified", False
    progress("session_ready")
    progress("navigation_started")
    # Состояние плеера можно проверить после таймаута загрузки.
    with contextlib.suppress(ValueError):
        client.call("WebDriver:Navigate", {"url": page})
    last, rejected, played, state = None, False, False, "no_video"
    while time.monotonic() + 2 < client.deadline and not relay.stopped.is_set():
        sample = client.call("WebDriver:ExecuteScript", {
            "script": OBSERVE, "args": [not rejected]})["value"]
        state = sample["state"]
        rejected |= state == "consent_rejected"
        if state in ("player_refused", "media_error", "other_page"):
            break
        position = sample.get("position")
        if position is None:
            last = None
        else:
            if last is None:
                last = position
            if not played and position >= last + 2:
                played = True
                progress("playback_observed")
        if played and position is not None:
            url = video_probe.browser_candidate(sample["urls"], domains, time.time())
            agent = sample["agent"]
            if url and re.fullmatch(r"[ -~]{1,512}", agent):
                return url, agent, "played", True
        time.sleep(1)
    if relay.stopped.is_set():
        return "", "", "browser_budget", played
    reason = "browser_url_missing" if played else "no_playback" if state == "player" else state
    return "", "", reason, played


def reserve_control_port():
    """Reserve an unused loopback port that outbound TCP connections won't auto-select."""
    low, high = map(int, EPHEMERAL_PORTS.read_text(encoding="ascii").split())
    if not 1 <= low <= high <= 65535:
        raise ValueError("invalid_ephemeral_port_range")
    # Prefer the low unprivileged range used by the successful machine check.
    for start, end in ((1024, 10000), (10000, 65536)):
        candidates = [port for port in range(start, end) if not low <= port <= high]
        for port in random.sample(candidates, min(32, len(candidates))):
            reservation = socket.socket()
            try:
                reservation.bind(("127.0.0.1", port))
            except OSError:
                reservation.close()
            else:
                return reservation
    raise OSError("marionette_port_unavailable")


def browser(firefox, user, page, domains, relay, progress):
    with (tempfile.TemporaryDirectory(prefix="xgw-video-", dir=user.pw_dir) as directory,
          reserve_control_port() as reservation):
        port = reservation.getsockname()[1]
        progress("marionette_port_reserved")
        profile = Path(directory)
        prefs = {
            "marionette.port": port, "intl.accept_languages": "en-US",
            "network.proxy.type": 1, "network.proxy.no_proxies_on": "",
            "network.proxy.allow_hijacking_localhost": True,
            "network.http.http3.enable": False, "network.trr.mode": 5,
            "media.peerconnection.enabled": False, "media.autoplay.default": 0,
            "browser.privatebrowsing.autostart": True, "browser.cache.disk.enable": False,
        }
        for scheme in ("http", "ssl"):
            prefs[f"network.proxy.{scheme}"] = "127.0.0.1"
            prefs[f"network.proxy.{scheme}_port"] = relay.server_address[1]
        settings = profile / "user.js"
        settings.write_text("".join(f"user_pref({json.dumps(k)}, {json.dumps(v)});\n"
                                    for k, v in prefs.items()), encoding="utf-8")
        os.chown(settings, user.pw_uid, user.pw_gid)
        os.chown(profile, user.pw_uid, user.pw_gid)
        reservation.close()
        process = subprocess.Popen(
            ["runuser", "-u", user.pw_name, "--", "env", "-i", f"HOME={user.pw_dir}",
             f"PATH={SEARCH}", f"XDG_RUNTIME_DIR=/run/user/{user.pw_uid}",
             f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{user.pw_uid}/bus",
             firefox, "--headless", "--marionette", "--no-remote", "--profile", str(profile)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        try:
            progress("firefox_started")
            start_by = min(relay.deadline, time.monotonic() + 35)
            while process.poll() is None and time.monotonic() < start_by:
                try:
                    sock = socket.create_connection(("127.0.0.1", port), timeout=0.5)
                except OSError:
                    time.sleep(0.25)
                    continue
                with sock:
                    client = Marionette(sock, start_by)
                    progress("marionette_ready")
                    client.deadline = relay.deadline
                    return observe(client, page, domains, relay, profile, progress)
            reason = ("marionette_listen_timeout" if process.poll() is None
                      else "browser_start_failed")
            return "", "", reason, False
        except (OSError, EOFError, ValueError):
            return "", "", "browser_control_failed", False
        finally:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
