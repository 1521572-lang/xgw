#!/usr/bin/env python3
"""One Firefox run through an existing VPN probe inbound. Output is a redacted summary."""

import argparse
import json
import os
import pwd
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from video_probe_check import snapshot  # noqa: E402

from xgw import config  # noqa: E402
from xgw.generator import builder  # noqa: E402
from xgw.paths import Paths  # noqa: E402
from xgw.watch import video_browser, video_probe  # noqa: E402


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
    state, before = snapshot(paths)
    applied = json.loads(paths.xray_config_file.read_bytes())
    password, _ = builder.probe_state(applied)
    alive = {row["tag"] for row in state["members"] if row.get("alive") and row.get("cost") == 0}
    nodes = [n for n in builder.applied_nodes(applied) if n.tag in alive and n.probe_port]
    pages = ([args.page_file.read_text(encoding="utf-8").strip()] if args.page_file else
             [cfg.media.youtube_sign_url, *cfg.zapret2.probe_urls])
    domains = cfg.zapret2.domains
    page = next((url for url in pages if video_probe.allowed(url, domains, page=True)), "")
    if not page or not nodes or not password:
        print("NOT_RUN missing_page_or_live_proxy")
        return
    fd = os.open(args.state, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as receipt:
        receipt.write('{"started":true}')
    port = nodes[0].probe_port
    with video_browser.Relay(port, password, time.monotonic() + 120) as relay:
        threading.Thread(target=relay.serve_forever, daemon=True).start()
        try:
            url, agent, reason, played = video_browser.browser(firefox, user, page, domains, relay)
        finally:
            relay.stopped.set()
            relay.shutdown()
        spent = relay.spent
    result = video_probe.replay(url, domains, port, password, agent) if url else {"result": reason}
    _, after = snapshot(paths)
    if before != after:
        raise ValueError("gateway_changed")
    result.update(browser_bytes=spent, playback=played)
    args.state.write_text(json.dumps(result), encoding="utf-8")
    print("RESULT", result["result"])
    print(f"BROWSER bytes={spent} playback={int(played)}")
    if "video" in result:
        row = result["video"]
        print("VIDEO http={} bytes={} video_mime={} verdict={} expires_in={}".format(
            row["http"], row["bytes"], int(row["video_mime"]), row["verdict"],
            result["expires_in"]))
    print("OK settings_and_processes_same")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    try:
        main()
    except (OSError, EOFError, ValueError, KeyError, TypeError, config.ConfigError,
            subprocess.SubprocessError, KeyboardInterrupt):
        print("STOP browser_probe_failed")
        sys.exit(2)
