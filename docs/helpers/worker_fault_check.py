"""Confirm generation-scoped diagnosis through the real system journal."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

BINARY = "/opt/xgw/zapret2/1.0.7/nfqws2"


def main(folder: Path) -> int:
    sys.path.insert(0, str(folder / "src"))
    from xgw.desync import worker
    from xgw.net import cmd

    name = f"xgw-fault-trial-{uuid.uuid4().hex}.service"
    slot = worker.WorkerSlot()
    cases = (
        ("hostlist_marker", ["/usr/bin/printf", "%s\n", "hostlists load failed. this is fatal."],
         0, "hostlist_reload_failed"),
        ("ipset_marker", ["/usr/bin/printf", "%s\n", "ipset load failed. this is fatal."],
         0, "ipset_reload_failed"),
        ("lua_init", [BINARY, "--uid=65534:65534", "--intercept=0", "--qnum=201",
                      '--lua-init=error("synthetic Lua initialization failure")'],
         1, "lua_error_observed"),
        ("clean_exit", ["/usr/bin/true"], 0, None),
    )
    previous = None
    failures = 0
    for case, argv, rc_expected, reason in cases:
        lease = slot.reserve(name, 201)
        lookup = slot.log_property(lease).removeprefix("LogExtraFields=")
        # Each case reuses the unit name after --collect but has a new launch field.
        try:
            with (folder / f"fault-{case}.log").open("xb") as output:
                proc = subprocess.run(
                    ["/usr/bin/systemd-run", "--quiet", "--wait", "--collect", "--unit", name,
                     "--property=PrivateNetwork=yes", "--property=RuntimeMaxSec=5s",
                     "--property=Type=exec", "--property=StandardOutput=journal",
                     "--property=StandardError=journal", "--property=" + slot.log_property(lease),
                     *argv],
                    check=False, timeout=10, stdout=output, stderr=output,
                )
            if reason is not None:
                deadline = time.monotonic() + 3
                while worker.read_fault(cmd.run, name, lookup) is None and time.monotonic() < deadline:
                    time.sleep(0.1)
            slot.observe_stopped(lease, cmd.run)
            events = slot.snapshot()[1]["events"]
            observed = next((e["reason"] for e in reversed(events)
                             if e["generation"] == lease.generation and e["phase"] == "worker_fault"),
                            None)
            # A clean exit on the reused name must never pick up the previous Lua failure.
            ok = proc.returncode == rc_expected and observed == reason and lookup != previous
            print(json.dumps({"case": case, "generation": lease.generation,
                              "exit": proc.returncode, "reason": observed, "ok": ok}), flush=True)
        except (OSError, subprocess.SubprocessError) as exc:
            print(json.dumps({"case": case, "error": type(exc).__name__, "ok": False}), flush=True)
            ok = False
        finally:
            slot.release(lease)
            # Only the synthetic unit created by this helper can remain after a timeout.
            subprocess.run(["/usr/bin/systemctl", "stop", name], check=False, timeout=6,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        failures += not ok
        previous = lookup
    print(f"WORKER_FAULT_CASES {len(cases) - failures}/{len(cases)}")
    return int(failures != 0)


if __name__ == "__main__":
    os.umask(0o077)
    work = Path(sys.argv[1])
    if (os.geteuid() != 0 or work.parent != Path("/run")
            or not work.name.startswith("xgw-worker-diag.") or not work.is_dir()
            or work.resolve() != work or work.stat().st_uid != 0 or work.stat().st_mode & 0o077):
        raise SystemExit("private_root_dir_required")
    raise SystemExit(main(work))
