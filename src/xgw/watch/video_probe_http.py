"""Bounded curl requests for the browser video probe's HTTP-version comparison."""

import json
import os
import re
import subprocess

from .. import zapret2
from ..generator.builder import PROBE_USER
from .checks import DownloadResult

CURL_ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
METADATA = (
    "%{response_code}\n%{http_version}\n%{size_download}\n"
    "%header{content-length}\n%header{content-encoding}\n%header{content-type}\n"
)
CONTENT_ENCODINGS = {"identity", "gzip", "deflate", "br", "zstd"}
ALPN_PROTOCOLS = {b"h2": "h2", b"http/1.1": "http/1.1", b"h3": "h3"}


def supports_http2(curl: str) -> bool:
    try:
        result = subprocess.run([curl, "--disable", "--version"], capture_output=True,
                                env=CURL_ENV, timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    lines = result.stdout.splitlines()
    version = re.match(rb"curl (\d{1,3})\.(\d{1,3})\.(\d{1,3})\b", lines[0]) if lines else None
    return (result.returncode == 0 and version is not None
            and tuple(map(int, version.groups())) >= (8, 4, 0)
            and any(row.startswith(b"Features:") and b"HTTP2" in row.split() for row in lines))


def _number(text: str) -> int | None:
    if re.fullmatch(r"[0-9]{1,19}", text):
        value = int(text)
        if value <= 2**63 - 1:
            return value
    return None


def _alpn(stderr: bytes | None) -> dict:
    """Extract only the protocol labels from curl's TLS diagnostics."""
    offered, selected = None, None
    offer_prefix = b"* ALPN: curl offers "
    accept_prefix = b"* ALPN: server accepted "
    for line in (stderr or b"").splitlines():
        if line.startswith(offer_prefix):
            protocols = line[len(offer_prefix):].split(b",")
            offered = list(dict.fromkeys(ALPN_PROTOCOLS.get(p.strip(), "other") for p in protocols))
            selected = None
        elif line.startswith(accept_prefix):
            selected = ALPN_PROTOCOLS.get(line[len(accept_prefix):].strip(), "other")
        elif line == b"* ALPN: server did not agree on a protocol. Uses default.":
            selected = "none"
    return {"alpn_offered": offered, "alpn_selected": selected}


def get(curl: str, url: str, port: int, password: str, agent: str,
        *, http2: bool, max_total: float) -> tuple[DownloadResult, dict]:
    """Send secrets over stdin and keep only selected response metadata."""
    metadata = {
        "http_requested": "2" if http2 else "1.1",
        "http_version": None,
        "content_length": None,
        "content_encoding": None,
        "curl_exit": None,
        "alpn_offered": None,
        "alpn_selected": None,
    }
    milliseconds = int(max_total * 1000)
    if milliseconds <= 0:
        return DownloadResult(False, kind="timeout"), metadata

    options = {"url": url, "proxy-user": f"{PROBE_USER}:{password}", "user-agent": agent}
    config = "".join(f"{key} = {json.dumps(value, ensure_ascii=False)}\n"
                     for key, value in options.items())
    command = [
        curl, "--disable", "--config", "-", "--silent", "--verbose", "--globoff", "--path-as-is",
        "--proto", "=https", "--proxy", f"http://127.0.0.1:{port}", "--noproxy", "",
        "--proxy-basic", "--http2" if http2 else "--http1.1",
        "--range", f"0-{zapret2.MIN_BODY - 1}", "--max-filesize", str(zapret2.MIN_BODY),
        "--max-time", f"{milliseconds / 1000:.3f}",
        "--output", os.devnull, "--write-out", METADATA,
    ]
    try:
        result = subprocess.run(command, input=config.encode(), capture_output=True,
                                env=CURL_ENV, timeout=max_total, check=False)
    except subprocess.TimeoutExpired as exc:
        metadata.update(_alpn(exc.stderr))
        return DownloadResult(False, kind="timeout"), metadata
    except OSError:
        return DownloadResult(False, kind="io"), metadata

    metadata["curl_exit"] = result.returncode
    metadata.update(_alpn(result.stderr))
    rows = result.stdout.decode("latin-1").split("\n")
    if len(rows) != 7 or rows[-1]:
        return DownloadResult(False, kind="io"), metadata
    code, version, size, length, encoding, mime, _ = rows
    status = _number(code) or 0
    downloaded = _number(size) or 0
    content_type = ""
    if 100 <= status <= 599:
        metadata["http_version"] = version if version in ("1", "1.0", "1.1", "2", "3") else None
        metadata["content_length"] = _number(length.strip())
        encoding = encoding.strip().lower()
        metadata["content_encoding"] = encoding if encoding in CONTENT_ENCODINGS else (
            "other" if encoding else None
        )
        content_type = mime.partition(";")[0].strip().lower()
    else:
        status = 0
    ok = (result.returncode in (0, 63) and 200 <= status < 300
          and downloaded == zapret2.MIN_BODY)
    kind = "timeout" if result.returncode == 28 else "http" if status else "io"
    return DownloadResult(
        ok, downloaded=downloaded, status=status, kind=kind, content_type=content_type,
        phase="body" if 200 <= status < 300 else "headers" if status else "",
    ), metadata
