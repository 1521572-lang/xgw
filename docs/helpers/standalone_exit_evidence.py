"""Project the local gateway state at a failed Standalone exit."""

import json
import time

from xgw import engine, zapret2
from xgw.desync import event_socket, worker
from xgw.net import cmd
from xgw.paths import Paths
from xgw.watch.zapret2_control import FRESH_SECONDS, REASONS, TITLES


def project(status, applied, *, now, api_dirty):
    status = status if isinstance(status, dict) else {}
    updated = status.get("updated")
    fresh = (status.get("daemon") is True and type(updated) in (float, int)
             and 0 <= now - updated <= FRESH_SECONDS)
    selected = status.get("zapret2")
    selected = selected if isinstance(selected, dict) else {}
    state, reason = selected.get("state"), selected.get("reason")
    reservation = status.get("zapret2_reservation")
    unit = reservation.get("unit") if isinstance(reservation, dict) else None
    reserved = {worker.SELECTED_UNIT: "selected", worker.ENGINE_UNIT: "engine"}
    reservation_state = (reserved.get(unit, "unknown") if isinstance(unit, str)
                         else "none" if "zapret2_reservation" in status and reservation is None
                         else "unknown")
    try:
        standalone_config = zapret2.standalone(applied) if applied is not None else None
    except (AttributeError, TypeError):
        standalone_config = None
    return {
        "daemon_snapshot_fresh": fresh,
        "selected_state": state if isinstance(state, str) and state in TITLES else "unknown",
        "selected_reason": reason if isinstance(reason, str) and reason in REASONS else "unknown",
        "reservation": reservation_state,
        "standalone_config_applied": standalone_config,
        "api_dirty": api_dirty,
    }


def main():
    paths = Paths.from_env()
    try:
        status = event_socket.read_status(paths.status_file)
    except (OSError, ValueError):
        status = None
    applied = engine.read_json(paths.xray_config_file)
    summary = project(status, applied, now=time.time(), api_dirty=paths.api_dirty_file.exists())
    try:
        service = cmd.run(["systemctl", "show", worker.SELECTED_UNIT, "-p", "ActiveState", "--value"],
                          check=False, timeout=1).strip()
    except (OSError, cmd.CommandError):
        service = ""
    known = ("active", "inactive", "activating", "deactivating", "failed", "reloading")
    summary["selected_service"] = service if service in known else "unknown"
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
