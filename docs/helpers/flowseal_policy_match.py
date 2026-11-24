"""Check ALT9 host filtering over loopback TLS with a pass-through Lua hook."""

from __future__ import annotations

import http.client
import json
import re
import socket
import ssl
import subprocess
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from xgw.desync import worker
from xgw.net import cmd

PORT = 443
BODY = b"xgw-scope-control\n"
LOG_LIMIT = 1024 * 1024
PASS = "--lua-desync=xgw_scope_pass"
LUA = "function xgw_scope_pass(ctx, desync) return VERDICT_PASS end"
SEARCH = "desync profile search for "
HOST = re.compile(r"\bl7proto=tls .* hostname='([^']+)'$")
MATCH = re.compile(r"desync profile (\d+) \(.*\) matches$")
# Label, SNI, eligibility before/after narrowing. All connections are to loopback.
CASES = (
    ("page_included", "control.youtube.com", True, True),
    ("cdn_included", "control.googlevideo.com", True, True),
    ("cdn_excluded", "example.googlevideo.com", True, False),
    ("excluded_subdomain", "child.example.youtube.com", True, False),
    ("removed_domain", "control.ytimg.com", True, False),
    ("suffix_negative", "googlevideo.com.example.test", False, False),
)


def observation_args(args):
    return [args[0], "--debug=1", "--lua-init=" + LUA,
            *(PASS if token.startswith("--lua-desync=") else token for token in args[1:])]


def matched_profiles(trace):
    """Only decisions following a search for a known TLS hostname provide evidence."""
    decisions = defaultdict(set)
    hostname = None
    for line in trace.splitlines():
        if line.startswith(SEARCH):
            match = HOST.search(line)
            hostname = match[1] if match else None
        elif hostname:
            match = MATCH.fullmatch(line)
            if match or line == "desync profile not found":
                decisions[hostname].add(int(match[1]) if match else 0)
                hostname = None
    return dict(decisions)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY)


@contextmanager
def https_server(root):
    cert, key = root / "scope.crt", root / "scope.key"
    san = "subjectAltName=" + ",".join("DNS:" + host for _, host, _, _ in CASES)
    cmd.run(["/usr/bin/openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-days", "1", "-subj", "/CN=xgw-scope", "-addext", san,
             "-out", str(cert), "-keyout", str(key)], timeout=12)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    client = ssl.create_default_context(cafile=str(cert))

    class Server(ThreadingHTTPServer):
        def get_request(self):
            sock, address = super().get_request()
            try:
                sock.settimeout(4)
                return context.wrap_socket(sock, server_side=True), address
            except OSError:
                sock.close()
                raise

    with Server(("0.0.0.0", PORT), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        thread.start()
        try:
            yield client
        finally:
            server.shutdown()
            thread.join(timeout=2)


def https_get(context, host, address):
    try:
        with socket.create_connection((address, PORT), timeout=3) as sock:
            with context.wrap_socket(sock, server_hostname=host) as tls:
                tls.sendall(f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode("ascii"))
                with http.client.HTTPResponse(tls) as response:
                    response.begin()
                    return response.status == 200 and response.read(len(BODY) + 1) == BODY
    except (OSError, http.client.HTTPException):
        return False


def check_phase(root, phase, args, queue, context):
    if worker.occupied(queue):
        raise ValueError("matching_queue_busy")
    log = root / f"scope-{phase}.log"
    with log.open("xb") as output:
        proc = subprocess.Popen(["/usr/bin/prlimit", f"--fsize={LOG_LIMIT}:{LOG_LIMIT}", "--",
                                 *observation_args(args)],
                                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 4
            while not worker.occupied(queue):
                if proc.poll() is not None or time.monotonic() >= deadline:
                    raise ValueError(f"{phase}_queue_not_ready")
                time.sleep(0.05)
            delivered = {host: https_get(context, host, f"127.0.0.{index}")
                         for index, (_, host, _, _) in enumerate(CASES, 2)}
            if proc.poll() is not None:
                raise ValueError(f"{phase}_worker_exited")
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
    if worker.occupied(queue):
        raise ValueError(f"{phase}_queue_not_released")
    decisions = matched_profiles(log.read_text(encoding="utf-8", errors="replace"))
    passed = 0
    for name, host, full, narrow in CASES:
        expected = 2 if (narrow if phase == "narrowed" else full) else 0
        profiles = sorted(decisions.get(host, ()))
        ok = delivered[host] and profiles == [expected]
        passed += ok
        print(json.dumps({"phase": phase, "case": name, "https_body_ok": delivered[host],
                          "expected_profile": expected, "profiles": profiles, "ok": ok}), flush=True)
    return passed


def check_matching(root, snapshots):
    queue = int(next(arg for arg in snapshots["base"] if arg.startswith("--qnum=")).split("=", 1)[1])
    cmd.run(["/usr/sbin/ip", "link", "set", "lo", "up"], timeout=3)
    rules = ("table inet xgw_scope_trial { chain loopback_only { "
             "type filter hook output priority filter; policy accept; "
             f'oifname "lo" ip daddr 127.0.0.0/8 tcp dport {PORT} queue num {queue}; '
             "} }\n")
    try:
        with https_server(root) as context:
            cmd.run(["/usr/sbin/nft", "-f", "-"], input=rules, timeout=3)
            try:
                passed = sum(check_phase(root, phase, args, queue, context)
                             for phase, args in snapshots.items())
            finally:
                cmd.run(["/usr/sbin/nft", "delete", "table", "inet", "xgw_scope_trial"], timeout=3)
    except subprocess.SubprocessError as exc:
        raise ValueError("matching_process_failed") from exc
    total = len(snapshots) * len(CASES)
    print(f"FLOWSEAL_POLICY_MATCH {passed}/{total}", flush=True)
    return passed == total
