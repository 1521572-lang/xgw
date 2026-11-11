#!/usr/bin/env python3
"""One bounded VPN experiment, no routing changes. Never prints URLs or server identities."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from xgw import config, managed  # noqa: E402
from xgw.generator import builder  # noqa: E402
from xgw.paths import Paths  # noqa: E402
from xgw.watch import video_probe  # noqa: E402


def snapshot(paths):
    state = json.loads((paths.run / "status.json").read_text())
    if (not 0 <= time.time() - state.get("updated", 0) <= 90
            or (state.get("capture") or {}).get("mode") != "on"
            or (state.get("zapret2") or {}).get("state") != "off"
            or not (state.get("xray") or {}).get("ok")):
        raise ValueError("gateway_not_ready")
    sums = []
    for path in (paths.config_file, managed.path_for(paths.config_file), paths.xray_config_file):
        sums.append(hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None)
    units = subprocess.run(
        ["systemctl", "show", "xgw.service", "xgw-xray.service", "xgw-singbox.service",
         "-p", "ActiveState", "-p", "MainPID"], capture_output=True, check=True,
        timeout=10).stdout
    return state, (sums, units)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--page-file", type=Path)
    args = parser.parse_args()
    paths = Paths(root=Path("/"))
    cfg, _ = config.load(paths.config_file)
    if cfg.zapret2.mode != "off":
        raise ValueError("mode_not_off")
    state, before = snapshot(paths)
    applied = json.loads(paths.xray_config_file.read_text())
    password, _ = builder.probe_state(applied)
    alive = {row.get("tag") for row in state.get("members", []) if row.get("alive") is True}
    nodes = [n for n in builder.applied_nodes(applied) if n.tag in alive and n.probe_port]
    pages = ([args.page_file.read_text().strip()] if args.page_file else
             [cfg.media.youtube_sign_url, *cfg.zapret2.probe_urls])
    page = next((p for p in pages if video_probe.allowed(p, cfg.zapret2.domains, page=True)), "")
    if not page or not nodes or not password:
        print("NOT_RUN missing_page_or_live_proxy")
        return
    # Exclusive receipt prevents accidental repetition with the same handoff directory.
    fd = os.open(args.state, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write('{"started":true}')
    result = video_probe.check(page, cfg.zapret2.domains, nodes[0].probe_port,
                               password, cfg.probe.user_agent)
    _, after = snapshot(paths)
    if before != after:
        raise ValueError("gateway_changed")
    args.state.write_text(json.dumps(result), encoding="utf-8")
    print("RESULT", result["result"])
    print("PAGE http={} bytes={}".format(result.get("page_http", 0), result.get("page_bytes", 0)))
    if "video" in result:
        row = result["video"]
        print("VIDEO http={} bytes={} verdict={} expires_in={}".format(
            row["http"], row["bytes"], row["verdict"], result["expires_in"]))
    print("OK settings_and_processes_same")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, TypeError, KeyError, config.ConfigError,
            subprocess.SubprocessError):
        print("STOP video_probe_check_failed")
        sys.exit(2)
