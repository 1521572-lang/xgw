"""Root transaction for the temporary installed-panel status-reader trial."""

from __future__ import annotations

import fcntl
import grp
import json
import os
import pwd
import re
import stat
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from desync_batch1_install import atomic, require, require_idle_workers, sha, trusted  # noqa: E402

PACKAGE = Path("/opt/xgw/lib/xgw")
UNITS = Path("/etc/systemd/system")
MAIN = "xgw.service"
SOCKET = "xgw-panel-read.socket"
READER = "xgw-panel-read.service"
USER = "xgw-panel-read"
TIMER = "xgw-panel-reader-rollback.timer"
RUNTIME = Path("/run/xgw-panel-ipc")
RELAY = Path("/run/xgw-panel-read.sock")
FILES = (
    "cli.py", "install.py", "watch/panel.py", "ui/login.html", "ui/app.css", "geodat.py",
    "watch/server_geo.py", "paths.py", "watch/httpbound.py", "local_ipc.py", "watch/panel_ipc.py",
    "watch/panel_read_http.py", "watch/panel_status_runtime.py",
)


def target(relative):
    name = relative.removeprefix("src/xgw/")
    if name != relative and name in FILES:
        return PACKAGE / name
    name = relative.removeprefix("packaging/")
    if name != relative and name in (MAIN, SOCKET, READER):
        return UNITS / name
    raise ValueError("unexpected_overlay_file")


RELATIVE = (*[f"src/xgw/{name}" for name in FILES],
            *[f"packaging/{name}" for name in (MAIN, SOCKET, READER)])


def command(*args, timeout=120):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout).stdout


def systemctl(*args, timeout=120):
    return command("/usr/bin/systemctl", *args, timeout=timeout).strip()


def lookup(find):
    try:
        return find(USER)
    except KeyError:
        return None


def reader_identity():
    account, group = lookup(pwd.getpwnam), lookup(grp.getgrnam)
    if account is None and group is None:
        return None
    require(account is not None and group is not None, "partial_reader_account")
    require(account.pw_uid > 0 and account.pw_gid == group.gr_gid > 0
            and account.pw_dir == "/nonexistent" and account.pw_shell == "/usr/sbin/nologin"
            and set(os.getgrouplist(USER, group.gr_gid)) == {group.gr_gid}, "unsafe_reader_account")
    return account


def prepare(stage):
    require(not (stage / "manifest.json").exists(), "already_prepared")
    require(systemctl("is-active", MAIN) == "active", "xgw_not_active")
    require(systemctl("show", "-p", "FragmentPath", "--value", MAIN) == str(UNITS / MAIN),
            "unexpected_xgw_unit_path")
    require_idle_workers()
    for unit in (SOCKET, READER):
        require(systemctl("show", "-p", "LoadState", "--value", unit) == "not-found",
                f"preexisting_unit {unit}")
    require(not os.path.lexists(RUNTIME) and not os.path.lexists(RELAY), "runtime_already_present")
    created = reader_identity() is None
    rows = {}
    mismatches = []
    for relative in RELATIVE:
        destination = target(relative)
        baseline, candidate = stage / "base" / relative, stage / "code" / relative
        for path in (destination, baseline, candidate):
            trusted(path)
        before = destination.read_bytes() if destination.exists() else None
        approved = baseline.read_bytes() if baseline.exists() else None
        if before != approved:
            mismatches.append(relative)
            continue
        after = candidate.read_bytes()
        if relative.endswith(".py"):
            compile(after, relative, "exec")
        if before is not None:
            info = destination.stat()
            rows[relative] = {"before": sha(before), "gid": info.st_gid,
                              "mode": stat.S_IMODE(info.st_mode), "after": sha(after)}
        else:
            rows[relative] = {"before": None, "gid": 0, "mode": 0o644, "after": sha(after)}
    require(not mismatches, "baseline_mismatch " + ",".join(mismatches))
    atomic(stage / "manifest.json", json.dumps({"created": created, "files": rows}).encode(), 0o600)
    print(f"BASELINE_MATCH {len(rows)}", flush=True)


def verify(rows, phase):
    for relative, row in rows.items():
        path = target(relative)
        trusted(path)
        actual = sha(path.read_bytes()) if path.exists() else None
        require(actual == row[phase], f"{phase}_mismatch {relative}")
        if path.exists():
            info = path.stat()
            require(info.st_gid == row["gid"] and stat.S_IMODE(info.st_mode) == row["mode"],
                    f"{phase}_permissions {relative}")


def apply(stage, manifest):
    require(not (stage / "started").exists(), "apply_already_started")
    require(systemctl("is-active", TIMER) == "active", "rollback_timer_not_active")
    require_idle_workers()
    rows = manifest["files"]
    verify(rows, "before")
    account = reader_identity()
    require((account is None) == manifest["created"], "reader_account_changed")
    atomic(stage / "started", b"1\n", 0o600)
    if account is None:
        command("/usr/sbin/useradd", "--system", "--user-group", "--no-create-home",
                "--home-dir", "/nonexistent", "--shell", "/usr/sbin/nologin",
                "--comment", stage.name, USER, timeout=20)
        require(reader_identity() is not None, "account_creation_failed")
    atomic(stage / "overlay-started", b"1\n", 0o600)
    systemctl("stop", MAIN)
    for relative, row in rows.items():
        atomic(target(relative), (stage / "code" / relative).read_bytes(), row["mode"], row["gid"])
    verify(rows, "after")
    systemctl("daemon-reload")
    systemctl("start", MAIN)
    print("CANDIDATE_STARTED", flush=True)


def remove_runtime_file(path, expect_socket):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    kind = stat.S_ISSOCK if expect_socket else stat.S_ISREG
    require(info.st_uid == 0 and kind(info.st_mode), "unexpected_runtime_file")
    path.unlink()


def remove_trial_identity(stage):
    account = lookup(pwd.getpwnam)
    if account is not None:
        require(account.pw_gecos == stage.name, "reader_identity_changed")
        group = lookup(grp.getgrnam)
        require(group is not None and group.gr_gid == account.pw_gid, "reader_group_changed")
        # Remember the exact group before userdel, which may remove it itself.
        atomic(stage / "created-gid", str(group.gr_gid).encode(), 0o600)
        command("/usr/sbin/userdel", USER, timeout=20)
    group = lookup(grp.getgrnam)
    if group is not None:
        saved = stage / "created-gid"
        require(saved.is_file() and int(saved.read_text()) == group.gr_gid
                and not group.gr_mem and not any(row.pw_gid == group.gr_gid for row in pwd.getpwall()),
                "reader_group_still_in_use")
        command("/usr/sbin/groupdel", USER, timeout=20)


def rollback(stage, manifest):
    rows = manifest["files"]
    if (stage / "overlay-started").exists():
        for relative, row in rows.items():
            path = target(relative)
            trusted(path)
            current = sha(path.read_bytes()) if path.exists() else None
            require(current in (row["before"], row["after"]), f"target_changed {relative}")
        systemctl("stop", MAIN)
        for unit in (SOCKET, READER):
            if systemctl("show", "-p", "LoadState", "--value", unit) != "not-found":
                systemctl("stop", unit)
        for relative, row in rows.items():
            destination = target(relative)
            if row["before"] is None:
                trusted(destination)
                destination.unlink(missing_ok=True)
            else:
                atomic(destination, (stage / "base" / relative).read_bytes(), row["mode"], row["gid"])
        verify(rows, "before")
        systemctl("daemon-reload")
        systemctl("start", MAIN)
        remove_runtime_file(RELAY, expect_socket=True)
        if RUNTIME.exists():
            trusted(RUNTIME)
            remove_runtime_file(RUNTIME / "status.sock", expect_socket=True)
            remove_runtime_file(RUNTIME / "serve.lock", expect_socket=False)
            RUNTIME.rmdir()
        (stage / "overlay-started").unlink()
    if (stage / "started").exists():
        if manifest["created"]:
            remove_trial_identity(stage)
        (stage / "started").unlink()
    verify(rows, "before")
    require(systemctl("is-active", MAIN) == "active", "restored_xgw_inactive")
    print("BASELINE_RESTORED", flush=True)


def main():
    require(os.geteuid() == 0 and len(sys.argv) == 3, "root_and_arguments_required")
    action, name = sys.argv[1:]
    stage = Path(name)
    require(re.fullmatch(r"/opt/xgw/handoff/panel-reader\.[A-Za-z0-9]{8}", name), "invalid_stage")
    trusted(stage)
    if action == "paths":
        print("\n".join(RELATIVE))
        return
    lock = stage / "operation.lock"
    trusted(lock)
    with lock.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        if action == "prepare":
            prepare(stage)
            return
        manifest_path = stage / "manifest.json"
        trusted(manifest_path)
        manifest = json.loads(manifest_path.read_bytes())
        rows = manifest["files"]
        require(set(rows) == set(RELATIVE), "unexpected_manifest_files")
        for relative, row in rows.items():
            for directory, phase in (("code", "after"), ("base", "before")):
                path = stage / directory / relative
                trusted(path)
                value = sha(path.read_bytes()) if path.exists() else None
                require(value == row[phase], f"archive_mismatch {relative}")
        if action == "apply":
            apply(stage, manifest)
        elif action == "rollback":
            rollback(stage, manifest)
        else:
            raise ValueError("unknown_action")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"FAILED {exc}", file=sys.stderr)
        sys.exit(2)
