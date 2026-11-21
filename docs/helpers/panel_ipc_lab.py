"""Verify Unix peer separation using a temporary listener on a running XGW."""

from __future__ import annotations

import configparser
import contextlib
import errno
import http.client
import json
import os
import pwd
import secrets
import selectors
import socket
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from xgw import config  # noqa: E402
from xgw.desync.event_socket import read_status  # noqa: E402
from xgw.paths import Paths  # noqa: E402
from xgw.watch import httpbound, panel, panel_ipc, panel_read_http, zapret2_control  # noqa: E402

QUERY = b'{"version":1,"op":"zapret2.overview"}'
CASES = {
    "version": (b'{"version":2,"op":"zapret2.overview"}', "unsupported_version"),
    "operation": (b'{"version":1,"op":"zapret2.mode"}', "unsupported_operation"),
    "length": (b" " * 4096, "request_too_large"),
}


def check(condition, name):
    if not condition:
        raise ValueError(name)


def client_case(path, name):
    if name == "allowed":
        return panel_ipc.read_overview(path, server_uid=0)
    if name == "other_ingress":
        with contextlib.closing(panel_read_http._RelayConnection(path, os.getuid())) as conn:
            conn.request("GET", panel_read_http.ROUTE,
                         headers={"Authorization": "Bearer " + "a" * 43})
            return conn.getresponse().status == 403
    if name in ("server_uid", "backend_down"):
        expected = "unexpected_server_uid" if name == "server_uid" else "unavailable"
        try:
            panel_ipc.read_overview(path, server_uid=1 if name == "server_uid" else 0)
        except panel_ipc.ProtocolError as exc:
            check(str(exc) == expected, name)
        else:
            raise ValueError(name)
        return True
    with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as connection:
        connection.settimeout(panel_ipc.TIMEOUT)
        connection.connect(str(path))
        if name == "other_uid":
            try:
                connection.send(QUERY)
                check(not connection.recv(panel_ipc.MAX_RESPONSE), name)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return True
        if name == "unscoped":
            connection.send(QUERY)
            response = json.loads(connection.recv(panel_ipc.MAX_RESPONSE + 1))
            check(response == {"version": 2, "ok": False, "error": "unsupported_version"}, name)
            return True
        request, error = CASES[name]
        connection.send(request)
        response = json.loads(connection.recv(panel_ipc.MAX_RESPONSE + 1))
        check(response == {"version": 1, "ok": False, "error": error}, name)
        return True


def wait_for_listener(path):
    deadline = time.monotonic() + 3
    with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as probe:
        probe.settimeout(0.25)
        while time.monotonic() < deadline:
            try:
                probe.connect(str(path))
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.02)
            else:
                return
    raise ValueError("socket_startup")


def check_process(pid, identity, *, sandbox):
    fields = dict(line.split(":", 1) for line in Path(f"/proc/{pid}/status").read_text().splitlines())
    check(fields["Uid"].split() == [str(identity.pw_uid)] * 4, "http_uid")
    groups = {int(gid) for gid in fields["Groups"].split()}
    allowed_groups = {identity.pw_gid} if sandbox else set()
    check(fields["Gid"].split() == [str(identity.pw_gid)] * 4 and groups <= allowed_groups,
          "http_groups")
    caps = ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
    check(all(int(fields[key], 16) == 0 for key in caps), "http_caps")
    check(fields["NoNewPrivs"].strip() == "1", "http_no_new_privs")
    print("http_privileges OK", flush=True)
    if sandbox:
        check(not os.path.samefile(f"/proc/{pid}/ns/mnt", "/proc/self/ns/mnt"),
              "http_mount_namespace")
        print("http_mount_namespace OK", flush=True)


def http_request(port, route, *, token=None, method="GET", headers=()):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=4)
    try:
        connection.putrequest(method, route, skip_host=True)
        connection.putheader("Host", f"127.0.0.1:{port}")
        if token is not None:
            connection.putheader("Authorization", f"Bearer {token}")
        for name, value in headers:
            connection.putheader(name, value)
        connection.endheaders()
        response = connection.getresponse()
        raw = response.read(2049)
        check(len(raw) <= 2048, "http_body_limit")
        check(response.getheader("Cache-Control") == "no-store", "http_cache_control")
        check(response.getheader("Access-Control-Allow-Origin") is None, "http_no_cors")
        return response.status, json.loads(raw) if raw else None
    finally:
        connection.close()


def plain_python(identity):
    return [
        "/usr/bin/setpriv", "--reuid", str(identity.pw_uid), "--regid", str(identity.pw_gid),
        "--clear-groups", "--inh-caps=-all", "--ambient-caps=-all", "--bounding-set=-all",
        "--no-new-privs", sys.executable, "-I", "-B",
    ]


def file_readability(prefix, files):
    trial = subprocess.run(
        [*prefix, "-c", "import json, os, sys; "
         "print(json.dumps([os.access(path, os.R_OK) for path in sys.argv[1:]]))", *map(str, files)],
        cwd="/", env={"PATH": "/usr/bin:/bin"}, capture_output=True, timeout=5,
    )
    check(trial.returncode == 0, "http_file_access_probe")
    return json.loads(trial.stdout)


def plain_http_command(path, prefix, paths):
    check(paths.panel_token_file.is_file(), "panel_token_file_missing")
    token_readable, config_readable, status_readable = file_readability(
        prefix, (paths.panel_token_file, paths.config_file, paths.status_file))
    check(token_readable is False, "http_worker_can_read_panel_token")
    print("http_panel_token_denied OK", flush=True)
    print("http_file_readability", json.dumps({"config": config_readable,
                                               "snapshot": status_readable}), flush=True)

    source = str(Path(__file__).resolve().parents[2] / "src")
    launch = (
        "import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); "
        "runpy.run_module('xgw.watch.panel_read_http', run_name='__main__')"
    )
    return [*prefix, "-c", launch, source, str(path)]


def sandbox_file_check(socket_path, files, relay=None):
    for label, file in zip(("config", "snapshot", "token", "database"), files, strict=True):
        try:
            fd = os.open(file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except (PermissionError, FileNotFoundError, NotADirectoryError):
            continue
        os.close(fd)
        raise ValueError(f"sandbox_readable_{label}")
    print("SANDBOX_FILES_DENIED", flush=True)
    sys.argv = [__file__, socket_path]
    if relay is not None:
        for family in (socket.AF_INET, socket.AF_INET6):
            try:
                with socket.socket(family, socket.SOCK_STREAM):
                    raise ValueError("http_inet_allowed")
            except OSError as exc:
                check(exc.errno in (errno.EAFNOSUPPORT, errno.EPERM, errno.EACCES),
                      "http_inet_probe")
        print("RELAY_INET_DENIED", flush=True)
        sys.argv.extend(("--relay", relay))
    panel_read_http.main()


def sandbox_command(path, identity, unit, files, relay=None):
    base = path.parent.parent
    policy = configparser.ConfigParser(interpolation=None)
    policy.optionxform = str
    with (base / "packaging" / "panel-read-hardening.conf").open() as stream:
        policy.read_file(stream)
    if relay is not None:
        policy.set("Service", "RestrictAddressFamilies", "AF_UNIX")
    writable = [f"--property=ReadWritePaths={relay.parent}"] if relay is not None else []
    return [
        "/usr/bin/systemd-run", "--quiet", "--pipe", "--collect", "--service-type=exec",
        f"--unit={unit}", f"--property=User={identity.pw_name}",
        f"--property=Group={identity.pw_gid}", "--property=RuntimeMaxSec=40s",
        "--property=TimeoutStopSec=3s",
        *(f"--property={key}={value}" for key, value in policy.items("Service")),
        *writable,
        sys.executable, "-I", "-B", __file__, "--sandbox-worker", str(path), *map(str, files),
        *([str(relay)] if relay is not None else []),
    ]


def show_unit(unit, prop):
    return subprocess.check_output(["/usr/bin/systemctl", "show", "--property", prop,
                                    "--value", unit], timeout=4, text=True).strip()


def read_startup(worker):
    with selectors.DefaultSelector() as poller:
        poller.register(worker.stdout, selectors.EVENT_READ)
        check(bool(poller.select(timeout=6)), "http_startup")
        line = worker.stdout.readline(64)
    check(line.endswith(b"\n"), "http_startup_output")
    return line.rstrip(b"\n")


def exercise_session_route(relay, identity, tickets, unavailable, reads):
    route = panel_read_http.ROUTE
    child = subprocess.run(
        [sys.executable, "-I", "-B", __file__, "--client", str(relay), "other_ingress"],
        cwd="/", env={"PATH": "/usr/bin:/bin"}, user=identity.pw_uid, group=identity.pw_gid,
        extra_groups=[], capture_output=True, timeout=5,
    )
    check(child.returncode == 0 and json.loads(child.stdout) is True, "session_ingress_uid")
    print("session_ingress_uid OK", flush=True)
    ingress = Paths(relay.parent.parent / "ingress")
    view = panel.Panel(ingress, ingress.config_file, secrets.token_urlsafe(32), port=0,
                       status_reader=lambda: panel_read_http.relay_status(
                           relay, identity.pw_uid, tickets))

    class Handler(httpbound.DeadlineHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if self.path.partition("?")[0] in ("/", route):
                view.handle(self, self.command)
            else:
                self.send_error(404)

        do_HEAD = do_GET

        def do_POST(self):
            if self.path == route:
                view.handle(self, self.command)
            else:
                self.send_error(405)

    def exchange(port, endpoint, method="GET", headers=None):
        with contextlib.closing(http.client.HTTPConnection("127.0.0.1", port, timeout=4)) as conn:
            conn.request(method, endpoint, headers=headers or {})
            response = conn.getresponse()
            return response.status, response.read(2049), response.getheader("Set-Cookie")

    # The worker rejects a normal panel cookie even over the trusted transport.
    def worker_status(headers):
        with contextlib.closing(panel_read_http._RelayConnection(relay, identity.pw_uid)) as conn:
            conn.request("GET", route, headers=headers)
            response = conn.getresponse()
            response.read(2049)
            return response.status

    with httpbound.BoundedServer(("127.0.0.1", 0), Handler, slots=4, label="ingress") as server:
        view.port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1})
        thread.start()
        try:
            check(exchange(view.port, route)[0] == 401, "session_anonymous")
            once = panel.new_login(ingress)
            endpoint = f"/?login={once}"
            code, _, cookie = exchange(view.port, endpoint)
            check(code == 303 and cookie is not None, "session_login")
            check(exchange(view.port, endpoint)[0] == 403, "session_login_replayed")
            print("session_one_time_login OK", flush=True)
            headers = {"Cookie": cookie.split(";", 1)[0]}
            check(exchange(view.port, route, headers={"Cookie": "xgw_panel=" + "0" * 64})[0]
                  == 401, "session_wrong_cookie")
            other_origin = {**headers, "Origin": "http://foreign.invalid"}
            check(exchange(view.port, route, headers=other_origin)[0] == 403, "session_origin")
            check(exchange(view.port, route, method="POST", headers=headers)[0]
                  == 405, "session_not_mutable")
            check(worker_status(headers) == 401 and not reads, "session_cookie_denied_by_worker")
            print("session_ingress_guards OK", flush=True)

            code, raw, _ = exchange(view.port, route, headers=headers)
            check(code == 200, "session_allowed")
            payload = json.loads(raw)
            print("allowed", json.dumps(payload["zapret2"], sort_keys=True), flush=True)
            head, body, _ = exchange(view.port, route, method="HEAD", headers=headers)
            check((head, body) == (200, b""), "session_head")
            print("session_head OK", flush=True)
            from xgw.desync.client import Client
            from xgw.gui.model import Session

            client = Client.__new__(Client)
            client.session = Session(view.port, headers["Cookie"].split("=", 1)[1])
            check(client.request(route) == payload, "session_qt_cli_client")
            print("session_qt_cli_client OK", flush=True)

            with tickets.issue() as ticket:
                ticket_header = {"Authorization": f"Bearer {ticket}"}
                check(worker_status(ticket_header) == 200, "session_ticket_allowed")
                check(worker_status(ticket_header) == 401, "session_ticket_replayed")
            with tickets.issue() as revoked:
                revoked_header = {"Authorization": f"Bearer {revoked}"}
            check(worker_status(revoked_header) == 401, "session_ticket_revoked")
            check(len(reads) == 4, "session_no_extra_reads")
            print("session_ticket_single_use OK", flush=True)

            unavailable.set()
            check(exchange(view.port, route, headers=headers)[0] == 503, "session_unavailable")
            unavailable.clear()
            code, raw, _ = exchange(view.port, route, headers=headers)
            check(code == 200 and json.loads(raw) == payload, "session_recovered")
            print("session_recovered OK", flush=True)
        finally:
            server.shutdown()
            thread.join(timeout=3)
    print("session_ingress_stopped OK", flush=True)


def exercise_http(path, identity, unavailable, reads, *, sandbox, tickets):
    unit = f"{path.parent.parent.name}.service" if sandbox else None
    paths = Paths(Path("/"))
    prefix = plain_python(identity)
    relay = None
    if tickets is not None:
        directory = path.parent.parent / "http"
        directory.mkdir()
        os.chown(directory, identity.pw_uid, 0)
        directory.chmod(0o2750)
        relay = directory / "status.sock"
    if sandbox:
        files = (paths.config_file, paths.status_file, paths.panel_token_file, paths.db_file)
        check(all(file.is_file() for file in files), "sandbox_host_files_missing")
        snapshot_readable, = file_readability(prefix, (paths.status_file,))
        print("http_unsandboxed_snapshot", json.dumps(snapshot_readable), flush=True)
        command = sandbox_command(path, identity, unit, files, relay)
    else:
        command = plain_http_command(path, prefix, paths)

    token = secrets.token_urlsafe(32)
    with subprocess.Popen(command, cwd="/", env={"PATH": "/usr/bin:/bin"}, bufsize=0,
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as worker:
        try:
            if relay is None:
                worker.stdin.write(f"{token}\n".encode("ascii"))
            worker.stdin.close()
            if sandbox:
                check(read_startup(worker) == b"SANDBOX_FILES_DENIED", "http_sandbox_files")
                print("http_sandbox_files_denied OK", flush=True)
            if relay is not None:
                check(read_startup(worker) == b"RELAY_INET_DENIED", "http_inet_denied")
                print("http_inet_denied OK", flush=True)
            ready = read_startup(worker)
            pid = int(show_unit(unit, "MainPID")) if sandbox else worker.pid
            check(pid > 0, "http_worker_pid")
            check_process(pid, identity, sandbox=sandbox)
            if relay is not None:
                check(ready == b"RELAY_READY", "http_relay_startup")
                info = relay.stat()
                check(stat.S_ISSOCK(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o660
                      and info.st_uid == identity.pw_uid and info.st_gid == 0,
                      "http_relay_permissions")
                print("http_unix_relay OK", flush=True)
                exercise_session_route(relay, identity, tickets, unavailable, reads)
                return
            port = int(ready)
            check(0 < port < 65536, "http_port")
            route = panel_read_http.ROUTE
            for name, expected, options in (
                ("anonymous", 401, {}),
                ("wrong_key", 401, {"token": "invalid"}),
                ("duplicate_authorization", 401,
                 {"token": token, "headers": (("Authorization", "Bearer invalid"),)}),
                ("other_origin", 403,
                 {"token": token, "headers": (("Origin", "https://foreign.invalid"),)}),
                ("duplicate_host", 403,
                 {"token": token, "headers": (("Host", "foreign.invalid"),)}),
                ("post", 405, {"token": token, "method": "POST"}),
            ):
                status, payload = http_request(port, route, **options)
                check(status == expected and set(payload) == {"error"}, name)
                print(f"http_{name} OK", flush=True)
            check(http_request(port, "/api/state", token=token)[0] == 404, "http_route_boundary")
            check(not reads, "http_rejected_requests_reached_backend")
            print("http_only_read_route OK", flush=True)
            status, payload = http_request(port, route, token=token)
            check(status == 200 and set(payload) == {"zapret2"}, "http_allowed")
            print("allowed", json.dumps(payload["zapret2"], sort_keys=True), flush=True)
            check(http_request(port, route, token=token, method="HEAD") == (200, None),
                  "http_head")
            print("http_head OK", flush=True)
            unavailable.set()
            check(http_request(port, route, token=token) == (503, {"error": "unavailable"}),
                  "http_unavailable")
            print("http_unavailable OK", flush=True)
            unavailable.clear()
            check(http_request(port, route, token=token) == (200, payload) and len(reads) == 4,
                  "http_recovered")
            print("http_recovered OK", flush=True)
        finally:
            try:
                if sandbox and show_unit(unit, "ActiveState") not in ("inactive", "failed"):
                    subprocess.run(["/usr/bin/systemctl", "stop", unit], check=True, timeout=6)
            finally:
                worker.terminate()
                try:
                    worker.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait(timeout=3)
            if sandbox:
                check(show_unit(unit, "ActiveState") in ("inactive", "failed"),
                      "http_unit_still_active")
                print("http_unit_stopped OK", flush=True)
            if relay is not None:
                relay.unlink(missing_ok=True)
                print("http_relay_removed OK", flush=True)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        try:
            probe.connect(("127.0.0.1", port))
        except ConnectionRefusedError:
            print("http_cleanup OK", flush=True)
        else:
            raise ValueError("http_endpoint_still_listening")


def run(*, with_http=False, sandbox=False, sessions=False):
    check(os.geteuid() == 0, "root_required")
    permitted = pwd.getpwnam("nobody")
    rejected = pwd.getpwnam("daemon")
    check(0 not in (permitted.pw_uid, rejected.pw_uid, permitted.pw_gid)
          and permitted.pw_uid != rejected.pw_uid, "distinct_unprivileged_uids_required")
    directory = Path(__file__).resolve().parents[2] / "socket"
    directory.mkdir(mode=0o711)
    directory.chmod(0o711)
    path = directory / "panel.sock"
    paths = Paths(Path("/"))
    cfg, _ = config.load(paths.config_file)
    stop = threading.Event()
    unavailable = threading.Event()
    reads = []
    tickets = panel_ipc.StatusTickets() if sessions else None

    def overview():
        reads.append(True)
        if unavailable.is_set():
            return None
        snapshot = read_status(paths.status_file)
        if not isinstance(snapshot, dict) or snapshot.get("daemon") is not True:
            return None
        capture = snapshot.get("capture")
        return {"zapret2": zapret2_control.card(
            cfg, snapshot, capture if isinstance(capture, dict) else {}, True)}

    def as_client(name, *, uid=permitted.pw_uid):
        child = subprocess.run(
            [sys.executable, "-I", "-B", __file__, "--client", str(path), name],
            user=uid, group=permitted.pw_gid, extra_groups=[], cwd="/",
            env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True, timeout=8,
        )
        check(child.returncode == 0, name)
        return json.loads(child.stdout)

    thread = threading.Thread(target=panel_ipc.serve,
                              args=(path, permitted.pw_uid, permitted.pw_gid, overview, stop),
                              kwargs={"tickets": tickets},
                              daemon=True)
    thread.start()
    try:
        wait_for_listener(path)
        info = path.stat()
        check(stat.S_ISSOCK(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o660
              and info.st_uid == 0 and info.st_gid == permitted.pw_gid, "socket_permissions")
        print("socket_permissions OK", flush=True)
        if sessions:
            check(as_client("unscoped") is True and not reads, "session_denies_unscoped_ipc")
            print("session_denies_unscoped_ipc OK", flush=True)
        if with_http:
            exercise_http(path, permitted, unavailable, reads, sandbox=sandbox, tickets=tickets)
            return
        overview_status = as_client("allowed")
        print("allowed", json.dumps(overview_status, sort_keys=True), flush=True)
        check(as_client("other_uid", uid=rejected.pw_uid) is True, "other_uid")
        print("other_uid OK", flush=True)
        for name in ("server_uid", *CASES):
            check(as_client(name) is True, name)
            print(f"{name} OK", flush=True)
        check(len(reads) == 1, "only_valid_request_reached_backend")
        print("only_valid_request_reached_backend OK", flush=True)
        unavailable.set()
        check(as_client("backend_down") is True and len(reads) == 2, "backend_down")
        print("backend_down OK", flush=True)
    finally:
        stop.set()
        thread.join(timeout=4)
        check(not thread.is_alive() and not path.exists(), "socket_cleanup")
        print("socket_cleanup OK", flush=True)


if __name__ == "__main__":
    try:
        if len(sys.argv) == 4 and sys.argv[1] == "--client":
            check(os.geteuid() != 0 and not os.getgroups(), "unprivileged_client_required")
            print(json.dumps(client_case(Path(sys.argv[2]), sys.argv[3])))
        elif len(sys.argv) == 1:
            run()
        elif sys.argv[1:] == ["--http"]:
            run(with_http=True)
        elif sys.argv[1:] == ["--http-sandbox"]:
            run(with_http=True, sandbox=True)
        elif sys.argv[1:] == ["--http-session"]:
            run(with_http=True, sandbox=True, sessions=True)
        elif len(sys.argv) in (7, 8) and sys.argv[1] == "--sandbox-worker":
            check(os.getuid() != 0 and os.geteuid() != 0, "unprivileged_client_required")
            relay = sys.argv[7] if len(sys.argv) == 8 else None
            sandbox_file_check(sys.argv[2], sys.argv[3:7], relay)
        else:
            raise ValueError("arguments")
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, config.ConfigError) as exc:
        detail = str(exc) if type(exc) is ValueError else type(exc).__name__
        print(f"FAILED {detail}", file=sys.stderr)
        sys.exit(1)
