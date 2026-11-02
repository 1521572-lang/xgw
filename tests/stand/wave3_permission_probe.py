"""Narrow live DAC/netlink checks; never changes gateway networking or services."""

import hashlib
import importlib.util
import json
import os
import pwd
import shutil
import stat
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path("/run/xgw-w3m")
spec = importlib.util.spec_from_file_location(
    "on_reader", Path(__file__).with_name("wave3_on_observer.py")
)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)

WORKER = r"""
import errno,json,os,socket,stat,subprocess,sys
from pathlib import Path

def identity(expected):
    lines=Path('/proc/self/status').read_text().splitlines()
    fields=dict(line.split(':',1) for line in lines if ':' in line)
    return ([int(x) for x in fields['Uid'].split()]==[expected['uid']]*4
            and [int(x) for x in fields['Gid'].split()]==[expected['gid']]*4
            and {int(x) for x in fields['Groups'].split()}==set(expected['groups'])
            and all(int(fields[key],16)==0 for key in
                    ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
            and fields.get('NoNewPrivs','').strip()=='1')

def attempt(action,target):
    try:
        if action=='open':
            fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW)
            os.close(fd)
            return {'outcome':'ALLOWED'}
        if action=='unix':
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
                sock.settimeout(0.5)
                sock.connect(target)
            return {'outcome':'ALLOWED'}
        if action=='create':
            fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            try:
                created=os.fstat(fd)
                current=os.lstat(target)
                same=(current.st_dev,current.st_ino)==(created.st_dev,created.st_ino)
                cleaned=False
                if same and stat.S_ISREG(current.st_mode) and current.st_uid==os.geteuid():
                    try:
                        os.unlink(target)
                        cleaned=True
                    except OSError:
                        pass
                return {'outcome':'ALLOWED','own_empty_file_removed':cleaned}
            finally:
                os.close(fd)
        if action=='nft':
            p=subprocess.run([target,'list','tables'],stdout=subprocess.DEVNULL,
                             stderr=subprocess.PIPE,timeout=2,check=False)
            denied=b'Operation not permitted' in p.stderr or b'Permission denied' in p.stderr
            return {'outcome':('ALLOWED' if p.returncode==0 else 'DENIED_PERMISSION'
                               if denied else 'OTHER_COMMAND_FAILURE')}
        return {'outcome':'INVALID_ACTION'}
    except OSError as exc:
        return {'outcome':'DENIED_PERMISSION' if exc.errno in (errno.EACCES,errno.EPERM)
                else 'TARGET_UNAVAILABLE' if exc.errno in (errno.ENOENT,errno.ECONNREFUSED)
                else 'OTHER_OS_ERROR','error_class':type(exc).__name__}
    except subprocess.TimeoutExpired:
        return {'outcome':'COMMAND_TIMEOUT'}

if __name__=='__main__':
    try:
        args=json.loads(sys.argv[1])
        verified=identity(args['identity'])
        result=(attempt(args['action'],args['target']) if verified
                else {'outcome':'IDENTITY_MISMATCH'})
        result['identity_verified']=verified
        print(json.dumps(result))
    except Exception as exc:
        print(json.dumps({'outcome':'CHILD_ERROR','error_class':type(exc).__name__,'identity_verified':False}))
"""


def save(name, value):
    fd = os.open(ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream)
        stream.write("\n")


def identity_for(snapshot, unit, account):
    pid = int(snapshot["unit_private"][unit]["MainPID"])
    proc = Path("/proc") / str(pid)
    before = (proc / "stat").read_text().rsplit(")", 1)[1].split()[19]
    fields = dict(
        line.split(":", 1) for line in (proc / "status").read_text().splitlines() if ":" in line
    )
    after = (proc / "stat").read_text().rsplit(")", 1)[1].split()[19]
    user = pwd.getpwnam(account)
    uid, gid = [int(x) for x in fields["Uid"].split()], [int(x) for x in fields["Gid"].split()]
    if before != after or uid != [user.pw_uid] * 4 or gid != [user.pw_gid] * 4 or user.pw_uid == 0:
        raise ValueError("identity race or unexpected account")
    if int(fields["CapEff"], 16) & 6:
        raise ValueError("process has DAC bypass capabilities")
    if unit == "xgw-singbox" and [pid, before] != snapshot["singbox"].get("process_identity"):
        raise ValueError("singbox changed")
    return {
        "uid": user.pw_uid,
        "gid": user.pw_gid,
        "groups": [int(x) for x in fields["Groups"].split()],
    }


def child(identity, action, target, tools):
    group_args = (
        ["--groups", ",".join(str(x) for x in identity["groups"])]
        if identity["groups"]
        else ["--clear-groups"]
    )
    argv = [
        tools["setpriv"],
        "--reuid",
        str(identity["uid"]),
        "--regid",
        str(identity["gid"]),
        *group_args,
        "--bounding-set=-all",
        "--inh-caps=-all",
        "--ambient-caps=-all",
        "--no-new-privs",
        tools["python3"],
        "-I",
        "-",
        json.dumps({"identity": identity, "action": action, "target": str(target)}),
    ]
    try:
        p = subprocess.run(
            argv,
            input=WORKER.encode(),
            capture_output=True,
            timeout=3,
            check=False,
            cwd="/",
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "LANG": "C"},
        )
        value = json.loads(p.stdout) if p.returncode == 0 else {}
        outcomes = {
            "ALLOWED",
            "DENIED_PERMISSION",
            "TARGET_UNAVAILABLE",
            "OTHER_OS_ERROR",
            "OTHER_COMMAND_FAILURE",
            "COMMAND_TIMEOUT",
            "INVALID_ACTION",
            "IDENTITY_MISMATCH",
            "CHILD_ERROR",
        }
        if (
            not isinstance(value, dict)
            or value.get("outcome") not in outcomes
            or value.get("identity_verified") is not True
        ):
            return {"outcome": "CHILD_OR_IDENTITY_ERROR", "identity_verified": False}
        result = {"outcome": value["outcome"], "identity_verified": True}
        if "own_empty_file_removed" in value:
            result["own_empty_file_removed"] = value["own_empty_file_removed"] is True
        return result
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"outcome": "CHILD_OR_IDENTITY_ERROR", "identity_verified": False}


def run_cases(cases, tools):
    results = []
    for name, identity, action, target, expected in cases:
        value = child(identity, action, target, tools)
        value.update(
            case=name,
            expected=expected,
            pass_expected=value.get("outcome") == expected
            and value.get("identity_verified") is True,
        )
        results.append(value)
        if not value["pass_expected"]:
            break
    return results


def main():
    if (
        os.geteuid() != 0
        or ROOT.is_symlink()
        or ROOT.stat().st_uid != 0
        or ROOT.stat().st_mode & 0o777 != 0o700
    ):
        raise ValueError("private directory")
    if sys.argv[1] == "show":
        print((ROOT / "summary.json").read_text())
        return 0
    if sys.argv[1] != "run" or (ROOT / "summary.json").exists():
        raise ValueError("already run or invalid mode")
    before = reader.snapshot()
    result = {
        "before": reader.public(before),
        "cases": [],
        "marker": "STOP_PRECONDITION",
        "worker_sha256": hashlib.sha256(WORKER.encode()).hexdigest(),
    }
    target = reader.PATHS.var / (".xgw-w3m-empty-" + uuid.uuid4().hex + ".probe")
    try:
        sb = before["singbox"]
        if (
            not reader.good(before)
            or not all(
                sb.get(key) is True
                for key in (
                    "account_nonprivileged",
                    "uid_all_match_service",
                    "gid_all_match_service",
                    "forbidden_groups_absent",
                    "no_new_privs",
                    "same_process_during_read",
                )
            )
            or not all(
                sb.get("cap_sets_zero", {}).get(key) is True
                for key in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
            )
        ):
            raise ValueError("process or on context unknown")
        tools = {name: shutil.which(name) for name in ("setpriv", "python3", "nft")}
        result["tools_available"] = {key: value is not None for key, value in tools.items()}
        if not all(tools.values()):
            raise ValueError("tool unavailable")
        a = identity_for(before, "xgw-singbox", "xgw-singbox")
        b = identity_for(before, "xgw-xray", "xray")
        xr, sc, api = (
            reader.PATHS.xray_config_file,
            reader.PATHS.singbox_config_file,
            reader.PATHS.xray_api_socket,
        )
        targets = {
            "xray_config": stat.S_ISREG(xr.lstat().st_mode),
            "singbox_config": stat.S_ISREG(sc.lstat().st_mode),
            "xray_api": stat.S_ISSOCK(api.lstat().st_mode),
            "state_directory": stat.S_ISDIR(reader.PATHS.var.lstat().st_mode),
            "probe_path_unused": not target.exists() and not target.is_symlink(),
        }
        result["target_preconditions"] = targets
        if not all(targets.values()):
            raise ValueError("target absent or unexpected type")
        check = subprocess.run(
            [tools["nft"], "list", "tables"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
        result["nft_root_read_control"] = check.returncode == 0
        if check.returncode != 0:
            raise ValueError("root read control failed")
        cases = [
            ("SB_OWN_CONFIG", a, "open", sc, "ALLOWED"),
            ("SB_XRAY_CONFIG", a, "open", xr, "DENIED_PERMISSION"),
            ("SB_XRAY_API", a, "unix", api, "DENIED_PERMISSION"),
            ("SB_STATE_CREATE", a, "create", target, "DENIED_PERMISSION"),
            ("SB_NFT_READ", a, "nft", tools["nft"], "DENIED_PERMISSION"),
            ("XRAY_SB_CONFIG", b, "open", sc, "DENIED_PERMISSION"),
        ]
        result["cases"] = run_cases(cases, tools)
        if target.exists() or target.is_symlink():
            save("cleanup-private.json", {"only_test_path": str(target)})
            result["private_cleanup_recorded"] = True
    except Exception as exc:
        result["precondition_error_class"] = type(exc).__name__
    try:
        after = reader.snapshot()
        result["after"] = reader.public(after)
        result["settings_unchanged"] = [
            a is not None and a == b
            for a, b in zip(before["hashes_private"], after["hashes_private"], strict=True)
        ]
        result["same_boot"] = before["boot_private"] == after["boot_private"]
        result["service_pid_same"] = {
            unit: before["unit_private"].get(unit, {}).get("MainPID")
            == after["unit_private"].get(unit, {}).get("MainPID")
            if before["unit_private"].get(unit) and after["unit_private"].get(unit)
            else None
            for unit in reader.UNITS
        }
        result["on_context_preserved"] = reader.good(before) and reader.good(after)
        result["marker"] = "PERMISSION_PROBES_RECORDED"
        passed = (
            len(result["cases"]) == 6
            and all(case["pass_expected"] for case in result["cases"])
            and result["on_context_preserved"]
            and all(result["settings_unchanged"])
            and result["same_boot"]
            and all(x is True for x in result["service_pid_same"].values())
            and not result.get("private_cleanup_recorded")
        )
        if passed:
            result["marker"] = "PERMISSION_PROBES_PASS"
    except Exception as exc:
        result["after_read_error_class"] = type(exc).__name__
    save("summary.json", result)
    print(json.dumps(result))
    return 0 if result["marker"] == "PERMISSION_PROBES_PASS" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("STOP_PERMISSION_PROBE", type(exc).__name__)
        raise SystemExit(3) from None
