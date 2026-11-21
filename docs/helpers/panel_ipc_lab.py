"""Verify Unix peer separation using a temporary listener on a running XGW."""

from __future__ import annotations

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
from xgw.watch import panel_ipc, panel_read_http, zapret2_control  # noqa: E402

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


def check_process(pid, identity):
    fields = dict(line.split(":", 1) for line in Path(f"/proc/{pid}/status").read_text().splitlines())
    check(fields["Uid"].split() == [str(identity.pw_uid)] * 4, "http_uid")
    check(fields["Gid"].split() == [str(identity.pw_gid)] * 4 and not fields["Groups"].strip(),
          "http_groups")
    caps = ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
    check(all(int(fields[key], 16) == 0 for key in caps), "http_caps")
    check(fields["NoNewPrivs"].strip() == "1", "http_no_new_privs")
    print("http_privileges OK", flush=True)


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


def exercise_http(path, identity, unavailable, reads):
    prefix = [
        "/usr/bin/setpriv", "--reuid", str(identity.pw_uid), "--regid", str(identity.pw_gid),
        "--clear-groups", "--inh-caps=-all", "--ambient-caps=-all", "--bounding-set=-all",
        "--no-new-privs", sys.executable, "-I", "-B",
    ]
    env = {"PATH": "/usr/bin:/bin"}
    paths = Paths(Path("/"))
    check(paths.panel_token_file.is_file(), "panel_token_file_missing")
    trial = subprocess.run(
        [*prefix, "-c", "import json, os, sys; "
         "print(json.dumps([os.access(path, os.R_OK) for path in sys.argv[1:]]))",
         str(paths.panel_token_file), str(paths.config_file), str(paths.status_file)],
        cwd="/", env=env, capture_output=True, timeout=5,
    )
    check(trial.returncode == 0, "http_file_access_probe")
    token_readable, config_readable, status_readable = json.loads(trial.stdout)
    check(token_readable is False, "http_worker_can_read_panel_token")
    print("http_panel_token_denied OK", flush=True)
    print("http_file_readability", json.dumps({"config": config_readable,
                                               "snapshot": status_readable}), flush=True)

    token = secrets.token_urlsafe(32)
    source = str(Path(__file__).resolve().parents[2] / "src")
    launch = (
        "import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); "
        "runpy.run_module('xgw.watch.panel_read_http', run_name='__main__')"
    )
    with subprocess.Popen(
        [*prefix, "-c", launch, source, str(path)], cwd="/", env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    ) as worker:
        try:
            worker.stdin.write(f"{token}\n".encode("ascii"))
            worker.stdin.close()
            with selectors.DefaultSelector() as poller:
                poller.register(worker.stdout, selectors.EVENT_READ)
                check(bool(poller.select(timeout=5)), "http_startup")
            port = int(worker.stdout.readline(8))
            check(0 < port < 65536, "http_port")
            check_process(worker.pid, identity)
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
            worker.terminate()
            try:
                worker.wait(timeout=3)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=3)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        try:
            probe.connect(("127.0.0.1", port))
        except ConnectionRefusedError:
            print("http_cleanup OK", flush=True)
        else:
            raise ValueError("http_endpoint_still_listening")


def run(*, with_http=False):
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
                              daemon=True)
    thread.start()
    try:
        wait_for_listener(path)
        info = path.stat()
        check(stat.S_ISSOCK(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o660
              and info.st_uid == 0 and info.st_gid == permitted.pw_gid, "socket_permissions")
        print("socket_permissions OK", flush=True)
        if with_http:
            exercise_http(path, permitted, unavailable, reads)
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
        else:
            raise ValueError("arguments")
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, config.ConfigError) as exc:
        detail = str(exc) if type(exc) is ValueError else type(exc).__name__
        print(f"FAILED {detail}", file=sys.stderr)
        sys.exit(1)
