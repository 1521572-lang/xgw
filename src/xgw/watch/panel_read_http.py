"""Standalone loopback HTTP process for the five-field zapret2 status."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import sys
from http import HTTPStatus
from pathlib import Path

from . import httpbound, panel_ipc

ROUTE = "/api/zapret2/status"
LOOPBACK = "127.0.0.1"
TOKEN = re.compile(rb"[A-Za-z0-9_-]{43}")


def create_server(path: Path, token: bytes) -> httpbound.BoundedServer:
    authorization = b"Bearer " + token

    class Handler(httpbound.DeadlineHandler):
        read_deadline = 3.0
        timeout = 3.0
        server_version = "xgw"
        sys_version = ""

        def log_message(self, *_args) -> None:
            pass

        def _respond(self, code: HTTPStatus, payload: dict) -> None:
            raw = json.dumps(payload, separators=(",", ":")).encode("ascii")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if code == HTTPStatus.UNAUTHORIZED:
                self.send_header("WWW-Authenticate", "Bearer")
            if code == HTTPStatus.METHOD_NOT_ALLOWED:
                self.send_header("Allow", "GET, HEAD")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(raw)

        def do_GET(self) -> None:
            if self.cut:
                return
            self.request_read()
            host = f"{LOOPBACK}:{self.server.server_address[1]}"
            origin = self.headers.get_all("Origin")
            if (self.headers.get_all("Host") != [host]
                    or (origin is not None and origin != [f"http://{host}"])):
                self._respond(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                return
            if self.path != ROUTE:
                self._respond(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            headers = self.headers.get_all("Authorization") or []
            if (len(headers) != 1 or not hmac.compare_digest(
                    headers[0].encode("latin1"), authorization)):
                self._respond(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            try:
                overview = panel_ipc.read_overview(path, server_uid=0)
            except (OSError, panel_ipc.ProtocolError):
                self._respond(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "unavailable"})
                return
            self._respond(HTTPStatus.OK, {"zapret2": overview})

        do_HEAD = do_GET

        def do_POST(self) -> None:
            if not self.cut:
                self.request_read()
                self._respond(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"})

        do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_POST

    if TOKEN.fullmatch(token) is None:
        raise ValueError("invalid_http_key")
    return httpbound.BoundedServer((LOOPBACK, 0), Handler, slots=8, label="panel-read-http")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("socket", type=Path)
    args = parser.parse_args()
    if os.geteuid() == 0 or os.getuid() == 0:
        parser.exit(2, "unprivileged_process_required\n")
    if not args.socket.is_absolute():
        parser.exit(2, "absolute_socket_path_required\n")
    line = sys.stdin.buffer.readline(45)
    if not line.endswith(b"\n") or TOKEN.fullmatch(line[:-1]) is None:
        parser.exit(2, "invalid_http_key\n")
    with create_server(args.socket, line[:-1]) as server:
        print(server.server_address[1], flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
