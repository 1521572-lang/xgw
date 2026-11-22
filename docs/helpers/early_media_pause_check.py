"""Exercise the XGW body sampler against a controlled TLS server on loopback."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import ssl
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from xgw.desync import experiment

FULL = 128 * 1024
TIMEOUT = 8


@dataclass(frozen=True)
class Case:
    name: str
    status: int
    size: int
    first: int
    delay: float | None
    thresholds: tuple[int, ...] = ()


CASES = (
    Case("full", 200, FULL, 0, 0),
    Case("flat_16k", 206, FULL, 16384, None, (3, 5)),
    Case("flat_20k", 206, FULL, 20480, None, (3, 5)),
    Case("resume_16k", 200, FULL, 16384, 4.2, (3,)),
    Case("resume_20k", 200, FULL, 20480, 6.1, (3, 5)),
    Case("short_20k", 200, 20480, 0, 0),
    Case("no_content", 204, 0, 0, 0),
)


def handler_for(case: Case, finished: threading.Event) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            with contextlib.suppress(OSError):
                self.send_response(case.status)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(case.size))
                if case.status == 206:
                    self.send_header("Content-Range", f"bytes 0-{case.size - 1}/{case.size}")
                self.end_headers()
                if case.first:
                    self.wfile.write(b"0" * case.first)
                    self.wfile.flush()
                if case.delay is None:
                    finished.wait(TIMEOUT + 2)
                elif not finished.wait(case.delay):
                    self.wfile.write(b"1" * (case.size - case.first))

    return Handler


def measure(case: Case, context: ssl.SSLContext, cert: Path, body: Path) -> dict:
    finished = threading.Event()
    with ThreadingHTTPServer(("127.0.0.1", 0), handler_for(case, finished)) as server:
        server.socket = context.wrap_socket(server.socket, server_side=True)
        listener = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1},
                                    daemon=True)
        listener.start()
        try:
            options = {"url": f"https://127.0.0.1:{server.server_port}/body",
                       "cacert": str(cert), "output": str(body),
                       "write-out": experiment.WRITE_OUT, "noproxy": "*",
                       "proxy": "", "proto": "=https", "range": f"0-{case.size - 1}"
                       if case.status == 206 else "", "max-time": str(TIMEOUT)}
            config = "silent\ngloboff\nhttp1.1\n" + "".join(
                f"{key} = {json.dumps(value, ensure_ascii=False)}\n"
                for key, value in options.items() if value or key == "proxy"
            )
            body.write_bytes(b"")
            rc, samples, meta, capped = experiment.sample_curl(Path("/usr/bin/curl"), body, config)
        finally:
            finished.set()
            server.shutdown()
            listener.join()
    return {"schema": experiment.VERSION, "status": int(meta.get("status", 0)),
            "media_type_ok": str(meta.get("content_type", "")).startswith("video/"),
            "curl_exit": rc, "samples": samples, "bytes": samples[-1][1],
            "output_buffering": "disabled", "budget_stop": capped}


def expected(case: Case, row: dict, analysis: dict) -> bool:
    flat = case.delay is None
    if (row["status"] != case.status or row["curl_exit"] != (28 if flat else 0)
            or row["bytes"] != (case.first if flat else case.size) or row["budget_stop"]):
        return False
    if not case.thresholds:
        state = "NOT_APPLICABLE" if case.status == 204 else "NO_PAUSE"
        return analysis["state"] == state and not analysis["pauses"]
    if analysis["state"] != "OBSERVED" or len(analysis["pauses"]) != 1:
        return False
    pause, = analysis["pauses"]
    return (pause["bytes"] == case.first and pause["thresholds_s"] == list(case.thresholds)
            and pause["outcome"] == ("flat_at_end" if flat else "resumed"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    experiment.private_path(args.out, directory=True)
    passed = 0
    with tempfile.TemporaryDirectory(dir=args.out) as directory:
        work = Path(directory)
        cert, key = work / "cert.pem", work / "key.pem"
        subprocess.run(
            ["/usr/bin/openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-days", "1", "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1",
             "-out", str(cert), "-keyout", str(key)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        for case in CASES:
            row = measure(case, context, cert, work / "body")
            with (args.out / f"{case.name}.json").open("x", encoding="utf-8") as handle:
                json.dump(row, handle)
            analysis = experiment.analyze_early_pauses(row)
            ok = expected(case, row, analysis)
            passed += ok
            print(json.dumps({"case": case.name, "ok": ok, "status": row["status"],
                              "curl_exit": row["curl_exit"], "bytes": row["bytes"],
                              **analysis}), flush=True)
    print(f"EARLY_PAUSE_CASES {passed}/{len(CASES)}")
    return int(passed != len(CASES))


if __name__ == "__main__":
    raise SystemExit(main())
