"""The Selective controller's real CONNECT and TLS path over loopback."""

import shutil
import socketserver
import ssl
import subprocess
import threading
import time

import pytest
from test_zapret2 import Harness

from xgw import zapret2 as z

PAGE = "www.youtube.com"
CDN = "r1.googlevideo.com"
REDIRECT_CDN = "r2.googlevideo.com"
FULL_PAGE = b"HTTP/1.1 200 OK\r\nContent-Length: 65536\r\n\r\n" + b"x" * z.PROBE_BYTES
FULL_RANGE = (b"HTTP/1.1 206 Partial Content\r\nContent-Length: 65536\r\n"
              b"Content-Range: bytes 0-65535/131072\r\n\r\n" + b"x" * z.PROBE_BYTES)
MISSING_RANGE = FULL_RANGE.replace(b"Content-Range: bytes 0-65535/131072\r\n", b"")


def read_headers(stream):
    lines = []
    for _ in range(40):
        line = stream.readline(4096)
        if line == b"\r\n":
            return lines
        if not line.endswith(b"\r\n"):
            break
        lines.append(line)
    raise ValueError("incomplete test request")


@pytest.fixture(scope="module")
def cert_files(tmp_path_factory):
    openssl = shutil.which("openssl")
    if not openssl:
        pytest.skip("openssl is required for the loopback HTTPS trial")
    folder = tmp_path_factory.mktemp("selective-tls")
    cert, key = folder / "cert.pem", folder / "key.pem"
    san = ",".join(f"DNS:{host}" for host in (PAGE, CDN, REDIRECT_CDN))
    subprocess.run(
        [openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-keyout", str(key), "-out", str(cert), "-subj", f"/CN={PAGE}",
         "-addext", f"subjectAltName={san}"],
        check=True, capture_output=True, timeout=10,
    )
    return cert, key


@pytest.fixture
def tunnel(cert_files, monkeypatch):
    cert, key = cert_files
    monkeypatch.setenv("SSL_CERT_FILE", str(cert))
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(cert, key)
    release = threading.Event()
    responses = {}
    connected = []

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            sock = self.request
            sock.settimeout(3)
            try:
                with sock.makefile("rb") as raw:
                    line = read_headers(raw)[0]
                method, destination, _ = line.decode("ascii").split()
                host, port = destination.split(":")
                assert method == "CONNECT" and port == "443"
                response = responses[host]
                connected.append(host)
                sock.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                if response is None:
                    release.wait(7)
                    return
                with (
                    tls.wrap_socket(sock, server_side=True) as secure,
                    secure.makefile("rb") as request,
                ):
                    read_headers(request)
                    secure.sendall(response)
            except OSError:
                # An expired client may already have closed its end of the tunnel.
                return

    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
        thread.start()
        try:
            yield server.server_address[1], responses, connected
        finally:
            release.set()
            server.shutdown()
            thread.join()


def media_url(host, expires):
    return f"https://{host}/videoplayback?expire={expires}"


@pytest.mark.parametrize(("reply", "expected"), [
    (FULL_PAGE, "range"),
    (MISSING_RANGE, "range"),
    (FULL_RANGE.replace(b"0-65535", b"1-65536"), "range"),
    (FULL_RANGE.replace(b"0-65535/131072", b"0-65535/65535"), "range"),
    (FULL_RANGE.replace(b"Content-Range:",
                        b"Content-Range: bytes 0-65535/131072\r\nContent-Range:"),
     "range"),
    (FULL_RANGE[:-1], "truncated"),
    (FULL_RANGE, "ok"),
], ids=["http_200", "missing", "shifted", "invalid_total", "duplicate", "partial", "exact"])
def test_selective_requires_exact_video_range_over_loopback(tunnel, reply, expected):
    port, responses, connected = tunnel
    responses.update({PAGE: FULL_PAGE, CDN: reply})
    h = Harness()
    h.cfg.zapret2.probe_port = port
    h.cfg.zapret2.youtube_transport_probe = True
    h.cfg.zapret2.probe_urls = [f"https://{PAGE}/t/terms", media_url(CDN, int(time.time()) + 30)]
    h.controller.probe = z.Controller.probe.__get__(h.controller)
    for now in (0, 1, 2):
        h.step(now)
    assert connected == [PAGE, CDN]
    assert h.controller.view["transport_probes"]["cdn"]["kind"] == expected
    assert h.controller.view["transport_probes"]["cdn"]["range_verified"] is (expected == "ok")
    assert z.active(h.current) is (expected == "ok")
    if expected != "ok":
        assert h.controller.view["gate_closed"] and not h.runtime.up


@pytest.mark.parametrize("stall_page", [False, True],
                         ids=["active_then_expired", "page_tls_stalled"])
def test_selective_cdn_expiry_over_loopback(tunnel, stall_page):
    port, responses, connected = tunnel
    responses.update({PAGE: None if stall_page else FULL_PAGE, CDN: FULL_RANGE})
    h = Harness()
    expires = int(time.time()) + 4
    h.cfg.zapret2.probe_port = port
    h.cfg.zapret2.youtube_transport_probe = True
    h.cfg.zapret2.probe_urls = [f"https://{PAGE}/t/terms", media_url(CDN, expires)]
    h.controller.probe = z.Controller.probe.__get__(h.controller)

    started = time.monotonic()
    for now in (0, 1, 2):
        h.step(now)
    elapsed = time.monotonic() - started
    if stall_page:
        assert elapsed < 5
        assert connected == [PAGE]
        assert h.controller.last_transport_ok_at is None
    else:
        assert connected == [PAGE, CDN]
        assert z.active(h.current)
        media = h.controller.view["transport_probes"]["cdn"]
        assert (media["http"], media["bytes"]) == (206, z.PROBE_BYTES)
        assert h.controller.view["valid_until"] <= expires
        time.sleep(max(0, expires - time.time()) + 0.05)
        h.step(2 + (time.monotonic() - started))
    assert time.time() + 0.1 >= expires
    assert h.controller.view["reason"] == z.CDN_EXPIRED
    assert h.controller.view["gate_closed"] and not z.active(h.current) and not h.runtime.up


@pytest.mark.parametrize("reply", [FULL_RANGE, MISSING_RANGE, None],
                         ids=["full_range", "missing_content_range", "redirect_tls_stalled"])
def test_vpn_redirect_respects_shorter_cdn_expiry_over_loopback(tunnel, reply):
    port, responses, connected = tunnel
    h = Harness()
    expires = int(time.time()) + 3
    target = media_url(REDIRECT_CDN, expires)
    responses[CDN] = (
        f"HTTP/1.1 302 Found\r\nLocation: {target}\r\nContent-Length: 0\r\n\r\n".encode()
    )
    responses[REDIRECT_CDN] = reply
    h.cfg.zapret2.youtube_transport_probe = True
    h.cfg.zapret2.probe_urls[1] = media_url(CDN, expires + 4)

    started = time.monotonic()
    control = h.controller._fallback_vpn_control(
        h.cfg, h.current, port, None, gate_closed=True, routed_back=True, stopped=True,
        target="cdn",
    )
    assert connected == [CDN, REDIRECT_CDN]
    if reply is None:
        assert time.monotonic() - started < 4.5
        assert time.time() + 0.1 >= expires
        assert control.verdict == "fail" and control.result.status == 302
        assert control.redirect.state == "expired"
    elif reply == FULL_RANGE:
        assert control.verdict == "pass" and control.redirect.state == "followed"
        assert (control.result.status, control.result.downloaded) == (206, z.PROBE_BYTES)
    else:
        assert control.verdict == "fail" and control.redirect.state == "followed"
        assert (control.result.status, control.result.kind) == (206, "range")
