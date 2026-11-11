#!/usr/bin/env python3
"""One Firefox run through an existing VPN probe inbound. Output is a redacted summary."""

import argparse
import hashlib
import json
import os
import pwd
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from video_probe_check import snapshot  # noqa: E402

from xgw import config  # noqa: E402
from xgw.generator import builder, singbox  # noqa: E402
from xgw.paths import Paths, atomic_write_json  # noqa: E402
from xgw.watch import video_browser, video_probe  # noqa: E402


@dataclass
class Checkpoint:
    state: dict
    settings: tuple
    units: bytes
    xray_digest: str
    xray: dict
    singbox: dict


def checkpoint(paths):
    for _ in range(3):
        state, (sums, units) = snapshot(paths)
        raw = paths.xray_config_file.read_bytes()
        if hashlib.sha256(raw).hexdigest() == sums[2]:
            break
    else:
        raise ValueError("snapshot_unstable")
    pin = state.get("pin") or {}
    pool = state.get("free_pool") or {}
    settings = (*sums[:2], pin.get("tag"), pin.get("until"), pool.get("mode"))
    try:
        bridge = json.loads(paths.singbox_config_file.read_bytes())
    except FileNotFoundError:
        bridge = {}
    return Checkpoint(state, settings, units, sums[2], json.loads(raw), bridge)


def target(rules, inbound, source, destination, fixed):
    """First rule that could apply to the probe, if it has the generated dedicated shape."""
    for rule in rules:
        tags = rule.get(source)
        if tags and inbound not in tags:
            continue
        route = rule.get(destination)
        if route and rule == {**fixed, source: [inbound], destination: route}:
            return route
        break
    raise ValueError("unverified_probe_route")


def chain(rows, first, links):
    by_tag = {row["tag"]: row for row in rows if row.get("tag")}
    found, pending = {}, [first]
    while pending:
        tag = pending.pop()
        if tag not in found:
            found[tag] = by_tag[tag]
            pending.extend(link for link in links(found[tag]) if link)
    return found


def xray_links(row):
    sockopt = row.get("streamSettings", {}).get("sockopt", {})
    return sockopt.get("dialerProxy"), row.get("proxySettings", {}).get("tag")


def bridge_path(outbound, applied):
    server = outbound["settings"]["servers"][0]
    port = server["port"]
    incoming = next(row for row in applied["inbounds"]
                    if row.get("listen") == "127.0.0.1" and row.get("listen_port") == port)
    route = target(applied["route"]["rules"], incoming["tag"], "inbound", "outbound",
                   {"action": "route"})
    rows = applied.get("outbounds", []) + applied.get("endpoints", [])
    return incoming, chain(rows, route, lambda row: (row.get("detour"),))


def selected_path(point, node, password):
    incoming = next(row for row in point.xray["inbounds"] if row.get("tag") == node.probe_tag)
    accounts = incoming.get("settings", {}).get("accounts", [])
    if (incoming.get("listen") != "127.0.0.1" or incoming.get("protocol") != "http"
            or incoming.get("port") != node.probe_port
            or not any(a.get("user") == builder.PROBE_USER and a.get("pass") == password
                       for a in accounts)):
        raise ValueError("probe_listener_changed")
    route = target(point.xray["routing"]["rules"], node.probe_tag, "inboundTag",
                   "outboundTag", {"type": "field"})
    if route != node.tag:
        raise ValueError("probe_target_changed")
    outbounds = chain(point.xray["outbounds"], route, xray_links)
    bridges = {tag: bridge_path(row, point.singbox) for tag, row in outbounds.items()
               if singbox.bridge_variant(row)}
    return incoming, outbounds, bridges


def compare(before, after, original_path, node, password):
    if before.settings != after.settings or before.units != after.units:
        return "gateway_settings_or_processes_changed"
    try:
        same = selected_path(after, node, password) == original_path
    except (KeyError, StopIteration, ValueError):
        same = False
    return "ok" if same else "selected_path_changed"


def verify(paths, before, original_path, node, password):
    try:
        after = checkpoint(paths)
        return (compare(before, after, original_path, node, password),
                before.xray_digest != after.xray_digest)
    except (OSError, KeyError, ValueError, TypeError, subprocess.SubprocessError):
        return "gateway_snapshot_unavailable", None


def finish(path, result, verification, xray_changed):
    atomic_write_json(path, {**result, "verification": verification,
                             "xray_config_changed": xray_changed}, mode=0o600)
    print("BROWSER bytes={} playback={} observation={} candidates={}".format(
        result["browser_bytes"], int(result["playback"]), result["observation"],
        result["candidate_count"]))
    if "video" in result:
        row = result["video"]
        print("VIDEO http={} bytes={} video_mime={} verdict={} expires_in={}".format(
            row["http"], row["bytes"], int(row["video_mime"]), row["verdict"],
            result["expires_in"]))
    if xray_changed is not None:
        print(f"CHECK xray_config_changed={int(xray_changed)}")
    if verification != "ok":
        print("STOP", verification)
        return 2
    print("OK settings_processes_and_selected_path_same")
    print("RESULT", result["result"])
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--page-file", type=Path)
    args = parser.parse_args()
    user = pwd.getpwnam(os.environ.get("SUDO_USER", "root"))
    firefox = shutil.which("firefox", path=video_browser.SEARCH)
    if not firefox or user.pw_uid == 0:
        print("NOT_RUN no_browser_or_user")
        return
    paths = Paths(root=Path("/"))
    cfg, _ = config.load(paths.config_file)
    if cfg.zapret2.mode != "off":
        raise ValueError("mode_not_off")
    before = checkpoint(paths)
    password, _ = builder.probe_state(before.xray)
    alive = {row["tag"] for row in before.state["members"]
             if row.get("alive") and row.get("cost") == 0}
    nodes = [n for n in builder.applied_nodes(before.xray) if n.tag in alive and n.probe_port]
    pages = ([args.page_file.read_text(encoding="utf-8").strip()] if args.page_file else
             [cfg.media.youtube_sign_url, *cfg.zapret2.probe_urls])
    domains = cfg.zapret2.domains
    page = next((url for url in pages if video_probe.allowed(url, domains, page=True)), "")
    if not page or not nodes or not password:
        print("NOT_RUN missing_page_or_live_proxy")
        return
    for node in nodes:
        try:
            original_path = selected_path(before, node, password)
        except (KeyError, StopIteration, ValueError):
            continue
        break
    else:
        print("NOT_RUN unverified_probe_route")
        return
    fd = os.open(args.state, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as receipt:
        receipt.write('{"started":true,"stages":[],"verification":"pending"}')
    diagnostics = {"stages": []}
    port = node.probe_port
    with video_browser.Relay(port, password, time.monotonic() + 120) as relay:
        threading.Thread(target=relay.serve_forever, daemon=True).start()

        def save_progress():
            atomic_write_json(args.state, {
                **diagnostics, "started": True, "browser_bytes": relay.spent,
                "verification": "pending",
            }, mode=0o600)

        def progress(stage):
            diagnostics["stages"].append(stage)
            save_progress()
            print("STAGE", stage, flush=True)

        def record_error(event):
            diagnostics["marionette_error"] = event
            save_progress()
            print("MARIONETTE_ERROR", json.dumps(event, sort_keys=True), flush=True)

        try:
            progress("relay_ready")
            candidates, agent, reason, played = video_browser.browser(
                firefox, user, page, domains, relay, progress, record_error)
        finally:
            relay.stopped.set()
            relay.shutdown()
        spent = relay.spent
    result = {**diagnostics, "result": reason, "observation": reason, "browser_bytes": spent,
              "playback": played, "candidate_count": len(candidates), "replay_attempts": []}
    atomic_write_json(args.state, {**result, "verification": "pending"}, mode=0o600)
    verification, changed = verify(paths, before, original_path, node, password)
    if verification != "ok" or not candidates:
        return finish(args.state, result, verification, changed)

    def record_attempt(index, observation):
        attempt = {"attempt": index, **observation}
        result["replay_attempts"].append(attempt)
        atomic_write_json(args.state, {**result, "verification": "pending"}, mode=0o600)
        print("ATTEMPT", json.dumps(attempt, sort_keys=True), flush=True)

    result.update(video_probe.replay_candidates(candidates, domains, port, password, agent,
                                               record_attempt))
    atomic_write_json(args.state, {**result, "verification": "pending"}, mode=0o600)
    verification, after_replay = verify(paths, before, original_path, node, password)
    changed = True if changed else after_replay
    return finish(args.state, result, verification, changed)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    try:
        sys.exit(main())
    except (OSError, EOFError, ValueError, KeyError, TypeError, config.ConfigError,
            subprocess.SubprocessError, KeyboardInterrupt):
        print("STOP browser_probe_failed")
        sys.exit(2)
