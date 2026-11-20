#!/usr/bin/env python3
"""Ubuntu-only, bounded file overlay for batch 1.

Run prepare, arm the independent rollback timer from NEXT_STEP, then apply.
Only root-owned immutable payloads are accepted. Unknown installed versions are refused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

BACKEND = ("config.py", "managed.py", "daemon.py", "watch/panel.py", "zapret2.py",
           "watch/zapret2_control.py", "desync/__init__.py", "desync/schema.py")
GUI = ("vpn_ui/xgw/overview.py", "src/xgw/gui/zapret2.py")
T03 = ("cli.py", "daemon.py", "nfqws2.py", "zapret2.py", "desync/schema.py",
       "desync/worker.py", "watch/zapret2_control.py")
T04 = ("apply/applier.py", "cli.py", "config.py", "daemon.py", "desync/schema.py", "engine.py",
       "generator/builder.py", "net/nft.py", "nfqws2.py", "watch/standalone.py",
       "watch/zapret2_control.py", "zapret2.py")
VPN_CONTROL = ("zapret2.py", "watch/zapret2_control.py")
T05 = ("config.py", "desync/schema.py", "net/nft.py", "zapret2.py")
T05_REPLIES = (*T05, "net/capture.py")
T06 = ("desync/preflight.py", "nfqws2.py", "zapret2.py", "watch/zapret2_control.py")
H05 = ("desync/h05.py", "desync/schema.py", "nfqws2.py", "zapret2.py")
T08_EVENTS = ("daemon.py", "desync/worker.py", "nfqws2.py", "zapret2.py")
T09_TOURNAMENT = ("desync/schema.py", "zapret2.py")
T10_FLOWSEAL = ("desync/schema.py", "desync/flowseal.py", "desync/experiment.py", "zapret2.py")
YOUTUBE_TRANSPORT = (*T10_FLOWSEAL, "config.py", "watch/zapret2_control.py")
ZAPRET2_WEB = ("watch/panel.py", "desync/event_socket.py", "ui/index.html",
               "ui/zapret2.html", "ui/zapret2.css", "ui/zapret2.js",
               "ui/zapret2.LICENSE.txt", "ui/zapret2.NOTICE.txt")
ZAPRET2_MANAGEMENT = ("watch/panel.py", "watch/zapret2_control.py", "watch/zapret2_management.py",
                      "ui/zapret2.html", "ui/zapret2.css", "ui/zapret2.js", "zapret2.py")
MANAGEMENT_GUI = ("src/xgw/gui/zapret2.py",)
TIMER = "xgw-desync-b1-rollback.timer"
T03_TIMER = "xgw-desync-t03-rollback.timer"
T04_TIMER = "xgw-desync-t04-rollback.timer"
VPN_CONTROL_TIMER = "xgw-desync-vpn-control-rollback.timer"
T05_TIMER = "xgw-desync-t05-rollback.timer"
T05_REPLIES_TIMER = "xgw-desync-t05-replies-rollback.timer"
T06_TIMER = "xgw-desync-t06-rollback.timer"
H05_TIMER = "xgw-desync-h05-rollback.timer"
T08_EVENTS_TIMER = "xgw-desync-t08-events-rollback.timer"
T09_TOURNAMENT_TIMER = "xgw-desync-t09-tournament-rollback.timer"
T10_FLOWSEAL_TIMER = "xgw-desync-t10-flowseal-rollback.timer"
YOUTUBE_TRANSPORT_TIMER = "xgw-selective-youtube-transport-rollback.timer"
ZAPRET2_WEB_TIMER = "xgw-zapret2-web-rollback.timer"
ZAPRET2_MANAGEMENT_TIMER = "xgw-zapret2-management-rollback.timer"
SELECTIVE_TLS = ("zapret2.py", "watch/checks.py")
SELECTIVE_TLS_TIMER = "xgw-selective-tls-rollback.timer"
SELECTIVE_PROBE_INFO = (
    "zapret2.py", "watch/zapret2_control.py", "ui/zapret2.html", "ui/zapret2.js",
)
SELECTIVE_PROBE_INFO_TIMER = "xgw-selective-probe-info-rollback.timer"
SELECTIVE_CDN_RETRY = (*SELECTIVE_PROBE_INFO, "desync/schema.py", "watch/zapret2_management.py")
SELECTIVE_CDN_RETRY_TIMER = "xgw-selective-cdn-retry-rollback.timer"
SELECTIVE_WEB_RESUME = ("ui/zapret2.js",)
SELECTIVE_WEB_RESUME_TIMER = "xgw-selective-web-resume-rollback.timer"
SELECTIVE_EXPIRY = ("zapret2.py", "desync/schema.py", "watch/zapret2_control.py",
                    "watch/zapret2_management.py", "ui/zapret2.js")
SELECTIVE_EXPIRY_TIMER = "xgw-selective-expiry-rollback.timer"
SELECTIVE_STATUS = ("watch/zapret2_control.py",)
SELECTIVE_STATUS_TIMER = "xgw-selective-status-rollback.timer"
SELECTIVE_BUDGET = ("zapret2.py", "watch/panel.py", "watch/zapret2_control.py",
                    "ui/zapret2.html", "ui/zapret2.js")
SELECTIVE_BUDGET_TIMER = "xgw-selective-budget-rollback.timer"
SELECTIVE_JOBS = ("desync/schema.py", "desync/jobs.py", "desync/client.py", "watch/panel.py",
                  "watch/zapret2_management.py", "ui/zapret2.html", "ui/zapret2.js")
SELECTIVE_JOBS_TIMER = "xgw-selective-jobs-rollback.timer"
SELECTIVE_ADMISSION = ("zapret2.py", "watch/zapret2_control.py", "watch/panel.py",
                       "watch/zapret2_management.py", "desync/jobs.py")
SELECTIVE_ADMISSION_TIMER = "xgw-selective-admission-rollback.timer"
COMBINED_ADMISSION = (*SELECTIVE_ADMISSION, "daemon.py", "desync/client.py",
                      "generator/profiles.py", "net/nft.py", "net/sysctl.py", "nfqws2.py")
COMBINED_ADMISSION_TIMER = "xgw-combined-admission-rollback.timer"
SELECTIVE_RANGE = ("zapret2.py", "desync/jobs.py", "desync/client.py")
SELECTIVE_RANGE_TIMER = "xgw-selective-range-rollback.timer"
SELECTIVE_STARTUP = (*SELECTIVE_RANGE, "watch/zapret2_control.py", "daemon.py")
SELECTIVE_STARTUP_TIMER = "xgw-selective-startup-rollback.timer"
SELECTIVE_CDN_UPDATE = ("watch/zapret2_management.py", "watch/zapret2_control.py",
                        "ui/zapret2.html", "ui/zapret2.js")
SELECTIVE_CDN_UPDATE_TIMER = "xgw-selective-cdn-update-rollback.timer"
XRAY_WRITE_TRACE = ("apply/applier.py", "apply/singbox_generation.py", "daemon.py")
XRAY_WRITE_TRACE_TIMER = "xgw-write-trace-rollback.timer"


def gui_files(files):
    if files == BACKEND:
        return GUI
    if files in (ZAPRET2_MANAGEMENT, SELECTIVE_BUDGET, SELECTIVE_JOBS, SELECTIVE_CDN_UPDATE):
        return MANAGEMENT_GUI
    return ()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def trusted(path):
    """Reject symlinks and writable parents, including for not-yet-existing targets."""
    require(path.is_absolute(), "absolute path required")
    for part in [*reversed(path.parents), path]:
        require(not part.is_symlink(), f"symlink: {part}")
        if part.exists():
            info = part.stat()
            require(info.st_uid == 0 and not info.st_mode & 0o022, f"untrusted: {part}")
            require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode),
                    f"special file: {part}")


def bounded(value, root):
    # Validate Ubuntu lexical paths independently of the development OS.
    pure = PurePosixPath(value)
    require(pure.is_absolute() and ".." not in pure.parts and "\\" not in value,
            "invalid target path")
    require(pure.is_relative_to(root) and str(pure) != root, "target outside allowed root")
    path = Path(str(pure))
    trusted(path)
    return path


def atomic(path, data, mode=0o644, gid=0):
    trusted(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    fd, name = tempfile.mkstemp(prefix=".batch1-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchown(stream.fileno(), 0, gid)
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def service(action, name="xgw.service"):
    return subprocess.run(["systemctl", action, name], check=True, capture_output=True,
                          text=True, timeout=120).stdout.strip()


def require_idle_workers():
    for unit in ("xgw-nfqws2.service", "xgw-zapret2.service"):
        probe = subprocess.run(["systemctl", "is-active", unit], capture_output=True,
                               text=True, timeout=10)
        require(probe.stdout.strip() in ("inactive", "failed", "unknown"),
                "active/transitioning worker: stop and report, do not disable it")


def prepare(args, backup):
    require(not (backup / "manifest.json").exists(), "backup already prepared")
    payload = bounded(args.payload, "/opt/xgw")
    package = bounded(args.package, "/opt/xgw")
    require(package.name == "xgw" and package.is_dir(), "expected installed xgw package")
    require(service("is-active") == "active", "daemon must initially be active")
    files, _timer = overlay(args)
    if files == COMBINED_ADMISSION:
        # Snapshot the owner's policy before arming rollback and switching to off/off.
        require(service("is-active", "xgw-net.service") == "active", "network unit is unavailable")
    else:
        require_idle_workers()
    gui_overlay = gui_files(files)
    require(not args.gui or bool(gui_overlay), "this overlay is backend only")
    pairs = [(payload / "code/src/xgw" / rel, package / rel,
              payload / "base/src/xgw" / rel) for rel in files]
    if args.gui:
        gui = bounded(args.gui, "/opt/xgw")
        pairs.extend((payload / "code" / rel, gui / rel, payload / "gui_base" / rel)
                     for rel in gui_overlay)
    rows = []
    for index, (source, target, baseline) in enumerate(pairs):
        for path in (source, target, baseline):
            trusted(path)
        new = source.read_bytes()
        if target.parent == package / "ui":
            new.decode("utf-8")
        else:
            compile(new, str(source), "exec")
        old = target.read_bytes() if target.exists() else None
        if baseline.exists():
            require(old == baseline.read_bytes(), f"installed baseline differs: {target}")
        else:
            require(old is None, f"unexpected pre-existing file: {target}")
        row = {"target": str(target), "old_sha": sha(old) if old is not None else None,
               "mode": stat.S_IMODE(target.stat().st_mode) if old is not None else 0o644,
               "gid": target.stat().st_gid if old is not None else 0,
               "new_sha": sha(new), "old": f"{index}.old", "new": f"{index}.new"}
        if old is not None:
            atomic(backup / row["old"], old, 0o600)
        atomic(backup / row["new"], new, 0o600)
        rows.append(row)
    atomic(backup / "manifest.json", (json.dumps(rows, indent=2) + "\n").encode(), 0o600)


def records(backup, files):
    trusted(backup / "manifest.json")
    rows = json.loads((backup / "manifest.json").read_text())
    expected = {len(files)}
    if gui_overlay := gui_files(files):
        expected.add(len(files) + len(gui_overlay))
    require(isinstance(rows, list) and len(rows) in expected, "invalid manifest")
    seen = set()
    for row in rows:
        bounded(row["target"], "/opt/xgw")
        require(row["target"] not in seen, "duplicate target")
        seen.add(row["target"])
        for kind in ("new", "old"):
            if kind == "old" and row["old_sha"] is None:
                continue
            require(Path(row[kind]).name == row[kind], "invalid backup filename")
            path = backup / row[kind]
            trusted(path)
            require(sha(path.read_bytes()) == row[kind + "_sha"], "backup hash mismatch")
    return rows


def restore(backup, rows):
    for row in rows:
        target = Path(row["target"])
        trusted(target)
        if row["old_sha"] is None:
            target.unlink(missing_ok=True)
        else:
            atomic(target, (backup / row["old"]).read_bytes(), row["mode"], row["gid"])


def start_services(*, reload_net):
    if reload_net:
        service("reload", "xgw-net.service")
    service("start")


def apply(backup, rows, timer=TIMER, *, reload_net=False):
    require(service("is-active", timer) == "active",
            "arm independent rollback timer before apply")
    for row in rows:
        target = Path(row["target"])
        actual = sha(target.read_bytes()) if target.exists() else None
        require(actual == row["old_sha"], "installed files changed after prepare")
    if reload_net:
        require_idle_workers()
    service("stop")
    try:
        for row in rows:
            atomic(Path(row["target"]), (backup / row["new"]).read_bytes(),
                   row["mode"], row["gid"])
        start_services(reload_net=reload_net)
    except BaseException:
        service("stop")
        restore(backup, rows)
        start_services(reload_net=reload_net)
        raise


def overlay(args):
    if getattr(args, "xray_write_trace", False):
        return XRAY_WRITE_TRACE, XRAY_WRITE_TRACE_TIMER
    if getattr(args, "selective_cdn_update", False):
        return SELECTIVE_CDN_UPDATE, SELECTIVE_CDN_UPDATE_TIMER
    if getattr(args, "selective_startup", False):
        return SELECTIVE_STARTUP, SELECTIVE_STARTUP_TIMER
    if getattr(args, "selective_range", False):
        return SELECTIVE_RANGE, SELECTIVE_RANGE_TIMER
    if getattr(args, "combined_admission", False):
        return COMBINED_ADMISSION, COMBINED_ADMISSION_TIMER
    if getattr(args, "selective_admission", False):
        return SELECTIVE_ADMISSION, SELECTIVE_ADMISSION_TIMER
    if getattr(args, "selective_jobs", False):
        return SELECTIVE_JOBS, SELECTIVE_JOBS_TIMER
    if getattr(args, "selective_budget", False):
        return SELECTIVE_BUDGET, SELECTIVE_BUDGET_TIMER
    if getattr(args, "selective_status", False):
        return SELECTIVE_STATUS, SELECTIVE_STATUS_TIMER
    if getattr(args, "selective_expiry", False):
        return SELECTIVE_EXPIRY, SELECTIVE_EXPIRY_TIMER
    if getattr(args, "selective_web_resume", False):
        return SELECTIVE_WEB_RESUME, SELECTIVE_WEB_RESUME_TIMER
    if getattr(args, "selective_cdn_retry", False):
        return SELECTIVE_CDN_RETRY, SELECTIVE_CDN_RETRY_TIMER
    if getattr(args, "selective_probe_info", False):
        return SELECTIVE_PROBE_INFO, SELECTIVE_PROBE_INFO_TIMER
    if getattr(args, "selective_tls", False):
        return SELECTIVE_TLS, SELECTIVE_TLS_TIMER
    if getattr(args, "zapret2_management", False):
        return ZAPRET2_MANAGEMENT, ZAPRET2_MANAGEMENT_TIMER
    if args.zapret2_web:
        return ZAPRET2_WEB, ZAPRET2_WEB_TIMER
    if args.youtube_transport:
        return YOUTUBE_TRANSPORT, YOUTUBE_TRANSPORT_TIMER
    if args.flowseal_t10:
        return T10_FLOWSEAL, T10_FLOWSEAL_TIMER
    if args.tournament_t09:
        return T09_TOURNAMENT, T09_TOURNAMENT_TIMER
    if args.worker_events:
        return T08_EVENTS, T08_EVENTS_TIMER
    if args.h05_profiles:
        return H05, H05_TIMER
    if args.preflight_t06:
        return T06, T06_TIMER
    if args.nft_t05_replies:
        return T05_REPLIES, T05_REPLIES_TIMER
    if args.nft_t05:
        return T05, T05_TIMER
    if args.vpn_control:
        return VPN_CONTROL, VPN_CONTROL_TIMER
    if args.worker_t04:
        return T04, T04_TIMER
    if args.worker_t03:
        return T03, T03_TIMER
    return BACKEND, TIMER


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "apply", "rollback"))
    parser.add_argument("--backup", required=True)
    parser.add_argument("--payload")
    parser.add_argument("--package")
    parser.add_argument("--gui")
    stage = parser.add_mutually_exclusive_group()
    stage.add_argument("--worker-t03", action="store_true")
    stage.add_argument("--worker-t04", action="store_true")
    stage.add_argument("--vpn-control", action="store_true")
    stage.add_argument("--nft-t05", action="store_true")
    stage.add_argument("--nft-t05-replies", action="store_true")
    stage.add_argument("--preflight-t06", action="store_true")
    stage.add_argument("--h05-profiles", action="store_true")
    stage.add_argument("--worker-events", action="store_true")
    stage.add_argument("--tournament-t09", action="store_true")
    stage.add_argument("--flowseal-t10", action="store_true")
    stage.add_argument("--youtube-transport", action="store_true")
    stage.add_argument("--zapret2-web", action="store_true")
    stage.add_argument("--zapret2-management", action="store_true")
    stage.add_argument("--selective-tls", action="store_true")
    stage.add_argument("--selective-probe-info", action="store_true")
    stage.add_argument("--selective-cdn-retry", action="store_true")
    stage.add_argument("--selective-web-resume", action="store_true")
    stage.add_argument("--selective-expiry", action="store_true")
    stage.add_argument("--selective-status", action="store_true")
    stage.add_argument("--selective-budget", action="store_true")
    stage.add_argument("--selective-jobs", action="store_true")
    stage.add_argument("--selective-admission", action="store_true")
    stage.add_argument("--combined-admission", action="store_true")
    stage.add_argument("--selective-range", action="store_true")
    stage.add_argument("--selective-startup", action="store_true")
    stage.add_argument("--selective-cdn-update", action="store_true")
    stage.add_argument("--xray-write-trace", action="store_true")
    args = parser.parse_args()
    require(sys.platform.startswith("linux") and os.geteuid() == 0, "Ubuntu root required")
    import fcntl

    backup = bounded(args.backup, "/var/lib/xgw/handoff")
    backup.mkdir(parents=True, exist_ok=True, mode=0o700)
    trusted(backup / "operation.lock")
    with (backup / "operation.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # timer and apply may not race
        if args.action == "prepare":
            require(bool(args.payload and args.package), "prepare needs payload and package")
            prepare(args, backup)
        else:
            files, timer = overlay(args)
            rows = records(backup, files)
            reload_net = files == COMBINED_ADMISSION
            if args.action == "apply":
                apply(backup, rows, timer, reload_net=reload_net)
            else:
                service("stop")
                restore(backup, rows)
                start_services(reload_net=reload_net)
    print(args.action + ": complete")


if __name__ == "__main__":
    main()
