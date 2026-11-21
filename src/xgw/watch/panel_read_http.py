"""Standalone loopback HTTP process for the five-field zapret2 status."""

from __future__ import annotations

import argparse
import hmac
import http.client
import json
import os
import re
import socket
import socketserver
import sys
from http import HTTPStatus
from pathlib import Path

from ..local_ipc import peer_uid
from . import httpbound, panel_ipc

ROUTE = "/api/zapret2/status"
LOOPBACK = "127.0.0.1"
TOKEN = re.compile(rb"[A-Za-z0-9_-]{43}")
RELAY_HOST = "xgw-panel-status"


class _UnixServer(httpbound.BoundedServer):
    address_family = socket.AF_UNIX

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = RELAY_HOST, 0
        os.chmod(self.server_address, 0o660)


class _RelayConnection(http.client.HTTPConnection):
    def __init__(self, path: Path, uid: int):
        super().__init__(RELAY_HOST, timeout=3)
        self.path = path
        self.uid = uid

    def connect(self):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            connection.settimeout(self.timeout)
            connection.connect(str(self.path))
            if peer_uid(connection) != self.uid:
                raise panel_ipc.ProtocolError("unexpected_http_uid")
        except BaseException:
            connection.close()
            raise
        self.sock = connection


def relay_status(path: Path, uid: int, tickets: panel_ipc.StatusTickets) -> dict:
    """Trusted panel call after verifying its existing session cookie."""
    connection = _RelayConnection(path, uid)
    try:
        with tickets.issue() as ticket:
            connection.request("GET", ROUTE, headers={"Authorization": f"Bearer {ticket}"})
            response = connection.getresponse()
            length = response.length
            if response.status != 200 or length is None or length > panel_ipc.MAX_RESPONSE:
                raise panel_ipc.ProtocolError("unavailable")
            data = json.loads(response.read(panel_ipc.MAX_RESPONSE + 1))
        if (not isinstance(data, dict) or set(data) != {"zapret2"}
                or not isinstance(data["zapret2"], dict)
                or set(data["zapret2"]) != set(panel_ipc.STATUS_FIELDS)):
            raise panel_ipc.ProtocolError("invalid_response")
        return panel_ipc.project(data["zapret2"])
    except (http.client.HTTPException, ValueError, RecursionError) as exc:
        raise panel_ipc.ProtocolError("unavailable") from exc
    finally:
        connection.close()


def create_server(path: Path, token: bytes | None, *, relay: Path | None = None):
    if relay is None:
        if token is None or TOKEN.fullmatch(token) is None:
            raise ValueError("invalid_http_key")
        authorization = b"Bearer " + token
    elif token is not None:
        raise ValueError("unexpected_http_key")
    else:
        authorization = b""

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
            host = RELAY_HOST if relay is not None else f"{LOOPBACK}:{self.server.server_port}"
            origin = self.headers.get_all("Origin")
            if (self.headers.get_all("Host") != [host]
                    or (origin is not None and (relay is not None or origin != [f"http://{host}"]))
                    or (relay is not None and peer_uid(self.connection) != 0)):
                self._respond(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                return
            if self.path != ROUTE:
                self._respond(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            headers = self.headers.get_all("Authorization") or []
            ticket = None
            if len(headers) == 1 and relay is not None:
                scheme, _, value = headers[0].partition(" ")
                if scheme == "Bearer" and panel_ipc.TICKET.fullmatch(value):
                    ticket = value
            valid = ticket is not None if relay is not None else (
                len(headers) == 1
                and hmac.compare_digest(headers[0].encode("latin1"), authorization))
            if not valid:
                self._respond(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            try:
                if ticket is None:
                    overview = panel_ipc.read_overview(path, server_uid=0)
                else:
                    overview = panel_ipc.read_overview(path, server_uid=0, ticket=ticket)
            except panel_ipc.ProtocolError as exc:
                if ticket is not None and str(exc) == "unauthorized":
                    self._respond(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                else:
                    self._respond(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "unavailable"})
                return
            except OSError:
                self._respond(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "unavailable"})
                return
            self._respond(HTTPStatus.OK, {"zapret2": overview})

        do_HEAD = do_GET

        def do_POST(self) -> None:
            if not self.cut:
                self.request_read()
                self._respond(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "method_not_allowed"})

        do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_POST

    if relay is not None:
        return _UnixServer(str(relay), Handler, slots=8, label="panel-read-http")
    return httpbound.BoundedServer((LOOPBACK, 0), Handler, slots=8, label="panel-read-http")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("socket", type=Path)
    parser.add_argument("--relay", type=Path)
    args = parser.parse_args()
    if os.geteuid() == 0 or os.getuid() == 0:
        parser.exit(2, "unprivileged_process_required\n")
    if not args.socket.is_absolute() or (args.relay is not None and not args.relay.is_absolute()):
        parser.exit(2, "absolute_socket_path_required\n")
    token = None
    if args.relay is None:
        line = sys.stdin.buffer.readline(45)
        if not line.endswith(b"\n") or TOKEN.fullmatch(line[:-1]) is None:
            parser.exit(2, "invalid_http_key\n")
        token = line[:-1]
    with create_server(args.socket, token, relay=args.relay) as server:
        print(server.server_address[1] if args.relay is None else "RELAY_READY", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
