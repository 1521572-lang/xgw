"""Verify Unix peer separation using a temporary listener on a running XGW."""

from __future__ import annotations

import json
import os
import pwd
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
from xgw.watch import panel_ipc, zapret2_control  # noqa: E402

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


def run():
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
        else:
            raise ValueError("arguments")
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, config.ConfigError) as exc:
        detail = str(exc) if type(exc) is ValueError else type(exc).__name__
        print(f"FAILED {detail}", file=sys.stderr)
        sys.exit(1)
