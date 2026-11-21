"""Trial the production status service and Panel lifecycle on a live snapshot."""

from __future__ import annotations

import configparser
import contextlib
import http.client
import json
import os
import pwd
import secrets
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from panel_ipc_lab import (  # noqa: E402
    Paths,
    check,
    check_process,
    config,
    panel,
    panel_read_http,
    read_status,
    show_unit,
    wait_for_listener,
    zapret2_control,
)

from xgw.watch import panel_status_runtime  # noqa: E402


def settings(path, section):
    policy = configparser.ConfigParser(interpolation=None)
    policy.optionxform = str
    with path.open() as source:
        policy.read_file(source)
    return dict(policy.items(section))


def start_socket(base, units, paths, identity):
    service = settings(base / "packaging/xgw-panel-read.service", "Service")
    activation = settings(base / "packaging/xgw-panel-read.socket", "Socket")
    service.pop("ExecStart")
    service.pop("Type")
    service.update(User=identity.pw_name, Group=str(identity.pw_gid), RuntimeMaxSec="60s")
    activation["ListenStream"] = str(paths.panel_relay_socket)
    entry = (
        "import sys; sys.path.insert(0,sys.argv.pop(1)); "
        "from xgw.watch.panel_read_http import main; main()"
    )
    subprocess.run([
        "/usr/bin/systemd-run", "--quiet", "--collect", "--service-type=exec", f"--unit={units}",
        *(f"--property={key}={value}" for key, value in service.items()),
        *(f"--socket-property={key}={value}" for key, value in activation.items()),
        sys.executable, "-I", "-B", "-c", entry, str(base / "src"),
        str(paths.panel_ipc_dir / "status.sock"), "--activated-relay", str(paths.panel_relay_socket),
    ], check=True, timeout=10)


def request(port, path, *, headers=None):
    with contextlib.closing(http.client.HTTPConnection("127.0.0.1", port, timeout=5)) as conn:
        conn.request("GET", path, headers=headers or {})
        response = conn.getresponse()
        return response.status, response.read(262145), response.getheader("Set-Cookie")


def run():
    identity = pwd.getpwnam("daemon")
    # The trial reuses an existing UID. Installation provisions its own identity.
    check(os.geteuid() == 0 and identity.pw_gid in os.getgroups(), "root_with_reader_group")
    caps = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines())
    check(int(caps["CapEff"], 16) & 7 == 0, "root_chown_or_dac_capability_present")
    panel_status_runtime.USER = identity.pw_name
    base = Path(__file__).resolve().parents[2]
    units = f"{base.name}-reader"
    paths = Paths(base / "candidate")
    paths.panel_ipc_dir.mkdir(mode=0o755, parents=True)
    paths.root.chmod(0o711)
    paths.panel_ipc_dir.parent.chmod(0o711)
    paths.panel_ipc_dir.chmod(0o755)
    ipc = paths.panel_ipc_dir / "status.sock"
    # An interrupted previous instance can leave a stale kernel socket name.
    with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as orphan:
        orphan.bind(str(ipc))

    live = Paths(Path("/"))
    cfg, _ = config.load(live.config_file)
    backend = True

    def overview():
        if not backend:
            return None
        snapshot = read_status(live.status_file)
        if not isinstance(snapshot, dict) or snapshot.get("daemon") is not True:
            return None
        capture = snapshot.get("capture")
        return {"zapret2": zapret2_control.card(
            cfg, snapshot, capture if isinstance(capture, dict) else {}, True)}

    view = panel.Panel(paths, paths.config_file, secrets.token_urlsafe(32), port=0,
                       root_problem=lambda: "Тестовый экземпляр доступен для чтения")
    view.configure(cfg)
    view.zapret2_overview = overview
    view.zapret2_status = overview
    try:
        start_socket(base, units, paths, identity)
        check(show_unit(f"{units}.socket", "ActiveState") == "active"
              and show_unit(f"{units}.service", "ActiveState") == "inactive",
              "service_starts_only_on_demand")
        relay = paths.panel_relay_socket.stat()
        check(stat.S_ISSOCK(relay.st_mode) and stat.S_IMODE(relay.st_mode) == 0o600
              and relay.st_uid == 0, "activation_socket_permissions")
        print("service_dormant OK", flush=True)

        view.start()
        wait_for_listener(ipc)
        info = ipc.stat()
        check(stat.S_ISSOCK(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o660
              and info.st_uid == 0 and info.st_gid == identity.pw_gid, "ipc_group_without_chown")
        print("stale_ipc_recovered OK", flush=True)
        route = panel_read_http.ROUTE
        check(request(view.port, route)[0] == 401
              and show_unit(f"{units}.service", "ActiveState") == "inactive", "anonymous_activation")
        code, _, cookie = request(view.port, f"/?login={panel.new_login(paths)}")
        check(code == 303 and cookie is not None, "panel_login")
        headers = {"Cookie": cookie.split(";", 1)[0]}
        check(request(view.port, "/", headers=headers)[0] == 200, "legacy_html")
        check(request(view.port, "/api/zapret2/overview", headers=headers)[0] == 200,
              "legacy_overview")
        print("panel_legacy_routes OK", flush=True)
        before = time.monotonic()
        code, raw, _ = request(view.port, route, headers=headers)
        check(code == 200, "activated_status")
        payload = json.loads(raw)
        pid = int(show_unit(f"{units}.service", "MainPID"))
        check(pid > 0, "activated_service_pid")
        check_process(pid, identity, sandbox=True)
        check(os.statvfs(f"/proc/{pid}/root/run").f_flag & os.ST_RDONLY,
              "reader_run_writable")
        print("reader_run_readonly OK", flush=True)
        print(f"cold_activation_ms {round((time.monotonic() - before) * 1000)}", flush=True)
        print("allowed", json.dumps(payload["zapret2"], sort_keys=True), flush=True)

        view.configure(cfg)
        check(ipc.stat().st_ino == info.st_ino, "config_reload_lost_listener")
        backend = False
        check(request(view.port, route, headers=headers)[0] == 503, "backend_failure")
        backend = True
        check(request(view.port, route, headers=headers)[:2] == (200, raw), "backend_recovery")
        print("backend_recovered OK", flush=True)

        subprocess.run(["/usr/bin/systemctl", "stop", f"{units}.service"], check=True, timeout=6)
        check(show_unit(f"{units}.service", "ActiveState") == "inactive", "service_did_not_stop")
        check(request(view.port, route, headers=headers)[:2] == (200, raw), "reactivation")
        check(int(show_unit(f"{units}.service", "MainPID")) not in (0, pid), "service_pid_reused")
        print("worker_reactivated OK", flush=True)
    finally:
        view.stop()
        subprocess.run(["/usr/bin/systemctl", "stop", f"{units}.socket"], timeout=8, check=False)
        subprocess.run(["/usr/bin/systemctl", "stop", f"{units}.service"], timeout=8, check=False)
    check(not ipc.exists() and not paths.panel_relay_socket.exists(), "socket_cleanup")
    print("candidate_cleanup OK", flush=True)


if __name__ == "__main__":
    try:
        run()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, config.ConfigError) as exc:
        reason = str(exc) if type(exc) is ValueError else type(exc).__name__
        print(f"FAILED {reason}", file=sys.stderr)
        sys.exit(1)
