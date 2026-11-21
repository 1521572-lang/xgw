"""Observe one time-limited Xray switch and restore automatic selection."""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from gui_map_visibility import desktop_window, wait
from xgw.gui import model

XGW = "/usr/local/bin/xgw"
ACTIVE_JOBS = {"queued", "running", "restoring"}


def command(label, *args, timeout=15):
    result = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        raise ValueError(label)
    return result.stdout


def public_ip():
    raw = command("https_control", "curl", "-q", "-4fsS", "--noproxy", "*",
                  "--connect-timeout", "4", "--max-time", "8", "https://api.ipify.org")
    try:
        return ipaddress.IPv4Address(raw.decode("ascii").strip())
    except ValueError as exc:
        raise ValueError("https_address") from exc


def country(window, row):
    code = row.get("endpoint_country")
    return code.upper() if isinstance(code, str) and code.upper() in window.map.points else ""


def auto_row(window):
    bridge = window.bridge
    state = bridge.state
    capture = state.get("capture") or {}
    zapret = state.get("zapret2") or {}
    if (bridge.stale or state.get("pin") or model.pool_house(state)
            or capture.get("mode") != "on" or capture.get("loaded") is not True
            or capture.get("blocked") or zapret.get("mode") != "off"
            or zapret.get("engine_mode") != "off"
            or (zapret.get("job") or {}).get("state") in ACTIVE_JOBS):
        return {}
    selected = [row for row in state.get("servers") or []
                if row.get("status") == "member" and row.get("alive") is True and row.get("selected")]
    if len(selected) != 1:
        return {}
    row = selected[0]
    code = country(window, row)
    return row if code and window.map.focus_code == code and window.map._pulse.isActive() else {}


def eligible(window, current):
    for row in window.bridge.state.get("servers") or []:
        tag, code = row.get("tag"), country(window, row)
        if (row.get("status") == "member" and row.get("alive") is True
                and row.get("source") not in ("", None, "manual")
                and isinstance(tag, str) and re.fullmatch(r"proxy-[A-Za-z0-9-]+", tag)
                and code and code != country(window, current)):
            yield row


def pinned(window, candidate):
    bridge = window.bridge
    pin = bridge.state.get("pin") or {}
    tag = candidate["tag"]
    return (not bridge.stale and pin.get("tag") == tag and not pin.get("down")
            and isinstance(pin.get("until"), (int, float)) and pin["until"] > time.time()
            and any(row.get("tag") == tag and row.get("selected")
                    and country(window, row) == country(window, candidate)
                    for row in bridge.state.get("servers") or [])
            and window.map.focus_code == country(window, candidate)
            and window.map._pulse.isActive())


def snapshot(app, work, canvas, code, name, *, phase=(0.15, 0.35)):
    target = canvas.points[code]

    def settled():
        focus = canvas._focus
        return (canvas.focus_code == code and (focus.x(), focus.y()) == target
                and canvas._pulse.isActive() and phase[0] <= canvas._phase <= phase[1])

    wait(app, settled, "map_frame_not_settled", seconds=4)
    if not canvas.grab().save(str(work / name)):
        raise ValueError("map_screenshot")


def trial(work, app, window, current, candidate):
    canvas = window.map
    current_code, candidate_code = country(window, current), country(window, candidate)
    initial_ip = public_ip()
    snapshot(app, work, canvas, current_code, "switch-before.png")
    positions = set()

    def observe_pan(value):
        if canvas.focus_code == candidate_code:
            positions.add((value.x(), value.y()))

    unit = f"xgw-map-return-{os.getpid()}"
    command("arm_rollback", "sudo", "-n", "systemd-run", "--collect", f"--unit={unit}",
            "--on-active=120s", "--service-type=oneshot", "--timer-property=AccuracySec=1s",
            "/usr/bin/timeout", "-k", "3", "18", XGW, "unpin")
    attempted = False
    canvas._move.valueChanged.connect(observe_pan)
    try:
        command("rollback_not_active", "systemctl", "is-active", "--quiet", unit + ".timer")
        print("MAP_SWITCH_ROLLBACK_ARMED", flush=True)
        attempted = True
        command("pin_command", "sudo", "-n", XGW, "pin", candidate["tag"], "--ttl", "90s")
        wait(app, lambda: pinned(window, candidate), "pin_not_confirmed_by_map", seconds=35)
        changed = public_ip() != initial_ip
        snapshot(app, work, canvas, candidate_code, "switch-pinned.png")
        snapshot(app, work, canvas, candidate_code, "switch-pinned-second.png", phase=(0.45, 0.60))
        if len(positions) < 2 or not pinned(window, candidate):
            raise ValueError("map_pan_or_pin_not_confirmed")
        print("MAP_PAN_OK", len(positions), flush=True)
        print("MAP_SWITCH_OK", "PUBLIC_IP_CHANGED", int(changed), flush=True)
    finally:
        canvas._move.valueChanged.disconnect(observe_pan)
        if attempted:
            command("unpin_command", "sudo", "-n", XGW, "unpin")
            before = window.bridge.received
            window.bridge.client.poll_soon(0)
            wait(app, lambda: window.bridge.received > before and bool(auto_row(window)),
                 "auto_not_restored", seconds=65)
            restored = public_ip()
            snapshot(app, work, canvas, country(window, auto_row(window)), "switch-restored.png")
            if window.bridge.client.writes:
                raise ValueError("unexpected_gui_write")
        command("cancel_rollback", "sudo", "-n", "systemctl", "stop", unit + ".timer")
        if attempted:
            print("MAP_AUTO_RESTORED_OK", "ORIGINAL_PUBLIC_IP", int(restored == initial_ip),
                  flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--maintenance-window", action="store_true", required=True)
    args = parser.parse_args()
    try:
        with desktop_window(args.work) as (app, window):
            wait(app, lambda: bool(auto_row(window)), "no_unambiguous_automatic_route", seconds=18)
            current = auto_row(window)
            candidate = next(eligible(window, current), None)
            if candidate is None:
                print("MAP_SWITCH_BLOCKED_DEPENDENCY no_other_live_country", flush=True)
                return 3
            command("candidate_probe", "sudo", "-n", XGW, "probe", candidate["tag"], timeout=55)
            before = window.bridge.received
            window.bridge.client.poll_soon(0)
            wait(app, lambda: window.bridge.received > before, "no_fresh_preflight")
            if (auto_row(window).get("tag") != current.get("tag")
                    or not any(row.get("tag") == candidate["tag"]
                               and country(window, row) == country(window, candidate)
                               for row in eligible(window, current))):
                raise ValueError("route_changed_during_preflight")
            print("MAP_SWITCH_PREFLIGHT_OK", flush=True)
            trial(args.work, app, window, current, candidate)
    except ValueError as exc:
        print("MAP_SWITCH_FAILED", exc, file=sys.stderr)
        return 2
    except (OSError, subprocess.SubprocessError) as exc:
        print("MAP_SWITCH_FAILED", type(exc).__name__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
