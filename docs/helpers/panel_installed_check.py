"""Read-only HTTP and systemd checks for the installed status-reader trial."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import http.client
import json
import os
import pwd
import stat
import subprocess
import sys
import time
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent), "/opt/xgw/lib"]

from panel_installed_trial import MAIN, READER, RELAY, RUNTIME, SOCKET, USER, systemctl  # noqa: E402
from t11_panel_login_check import require, verify  # noqa: E402
from xgw import config  # noqa: E402
from xgw.paths import Paths  # noqa: E402
from xgw.watch.panel import read_token  # noqa: E402

ROUTE = "/api/zapret2/status"
OVERVIEW = "/api/zapret2/overview"
FIELDS = ("mode", "engine_mode", "state", "fresh", "policy_matched")


def read(port, path=ROUTE, *, cookie="", method="GET", headers=None):
    send = dict(headers or {})
    if cookie:
        send["Cookie"] = cookie
    with contextlib.closing(http.client.HTTPConnection("127.0.0.1", port, timeout=7)) as conn:
        conn.request(method, path, headers=send)
        response = conn.getresponse()
        body = response.read(262145)
        require(len(body) <= 262144, "response_limit")
        if response.status == 200 and method != "HEAD":
            return response.status, json.loads(body)
        return response.status, body


def listener_info(path, gid, mode):
    info = path.lstat()
    require(stat.S_ISSOCK(info.st_mode) and info.st_uid == 0 and info.st_gid == gid
            and stat.S_IMODE(info.st_mode) == mode, "socket_permissions")


def reader_pid(identity):
    pid = int(systemctl("show", "-p", "MainPID", "--value", READER, timeout=5))
    require(pid > 0, "reader_not_running")
    proc = Path(f"/proc/{pid}")
    fields = dict(line.split(":", 1) for line in (proc / "status").read_text().splitlines())
    require(fields["Uid"].split() == [str(identity.pw_uid)] * 4
            and fields["Gid"].split() == [str(identity.pw_gid)] * 4
            and set(fields["Groups"].split()) <= {str(identity.pw_gid)}, "reader_identity")
    require(all(int(fields[key], 16) == 0 for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"))
            and fields["NoNewPrivs"].strip() == "1", "reader_privileges")
    require(os.statvfs(proc / "root/run").f_flag & os.ST_RDONLY, "reader_run_writable")
    return pid


def check_candidate(port, token, cookie):
    identity = pwd.getpwnam(USER)
    require(systemctl("is-active", SOCKET) == "active", "relay_inactive")
    require(systemctl("show", "-p", "ActiveState", "--value", READER) == "inactive", "reader_not_idle")
    listener_info(RELAY, 0, 0o600)
    listener_info(RUNTIME / "status.sock", identity.pw_gid, 0o660)
    main_pid = systemctl("show", "-p", "MainPID", "--value", MAIN)
    require(main_pid.isdigit() and int(main_pid) > 0, "xgw_not_running")

    auth = verify(port, token, "candidate")
    auth.pop("phase", None)
    print("ONE_TIME_CLI_OK", json.dumps(auth), flush=True)
    require(read(port)[0] == 401, "anonymous")
    require(read(port, cookie=cookie, headers={"Host": "foreign.invalid"})[0] == 403, "bad_host")
    require(read(port, cookie=cookie, headers={"Origin": "http://foreign.invalid"})[0] == 403,
            "bad_origin")
    require(read(port, cookie=cookie, method="POST")[0] == 405, "status_is_read_only")
    require(systemctl("show", "-p", "ActiveState", "--value", READER) == "inactive",
            "rejected_requests_activated_reader")
    print("READER_DORMANT_OK", flush=True)

    code, overview = read(port, OVERVIEW, cookie=cookie)
    require(code == 200 and isinstance(overview.get("zapret2"), dict), "full_overview")
    summary = {key: overview["zapret2"].get(key) for key in FIELDS}
    require(summary == dict(zip(FIELDS, ("off", "off", "off", True, True), strict=True)), "off_off")
    start = time.monotonic()
    code, body = read(port, cookie=cookie)
    elapsed = round((time.monotonic() - start) * 1000)
    require(code == 200 and body == {"zapret2": summary}, "status_differs")
    pid = reader_pid(identity)
    require(read(port, cookie=cookie, method="HEAD") == (200, b""), "head")
    print("INSTALLED_STATUS_MATCH", json.dumps({"cold_ms": elapsed, **summary}), flush=True)
    print("READER_RUN_READONLY_OK", flush=True)

    systemctl("stop", SOCKET, READER, timeout=15)
    try:
        require(read(port, cookie=cookie)[0] == 503, "outage_not_reported")
        require(read(port, OVERVIEW, cookie=cookie)[0] == 200, "overview_during_outage")
    finally:
        systemctl("start", SOCKET, timeout=15)
    require(read(port, cookie=cookie) == (200, {"zapret2": summary}), "status_recovery")
    require(reader_pid(identity) != pid, "reader_not_reactivated")
    require(systemctl("show", "-p", "MainPID", "--value", MAIN) == main_pid, "xgw_pid_changed")
    print("INSTALLED_READER_RECOVERED_OK", flush=True)


def main():
    require(os.geteuid() == 0 and len(sys.argv) == 2, "root_and_phase_required")
    paths = Paths(Path("/"))
    cfg, _ = config.load(paths.config_file)
    token = read_token(paths)
    require(bool(token), "no_panel_token")
    cookie = "xgw_panel=" + hmac.new(token.encode(), b"xgw-panel", hashlib.sha256).hexdigest()
    port = cfg.panel.port
    phase = sys.argv[1]
    if phase == "candidate":
        check_candidate(port, token, cookie)
    elif phase in ("baseline", "restored"):
        require(read(port, ROUTE, cookie=cookie)[0] == 404, "unexpected_status_route")
        require(read(port, OVERVIEW, cookie=cookie)[0] == 200, "legacy_overview")
        print(f"{phase.upper()}_HTTP_OK", flush=True)
    else:
        raise ValueError("invalid_phase")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, http.client.HTTPException, subprocess.SubprocessError,
            config.ConfigError) as exc:
        print(json.dumps({"error": type(exc).__name__,
                          "stage": str(exc) if isinstance(exc, ValueError) else "request"}),
              file=sys.stderr)
        sys.exit(2)
