"""Exercise the kernel gate and the Selective controller in a fresh netns."""

import os
import re
import socket
import subprocess
import time
from types import SimpleNamespace

from nft_rules_fixture import render
from test_zapret2 import Harness

from xgw import zapret2
from xgw.net import nft


def run(*argv, input_text=None):
    return subprocess.run(
        argv, input=input_text, capture_output=True, text=True, check=True, timeout=5,
    ).stdout


def require(condition, label):
    if not condition:
        raise RuntimeError(label)
    print(f"OK {label}", flush=True)


def marks():
    listing = run("nft", "-n", "list", "set", "inet", nft.GUARD, zapret2.LIVE)
    items = listing.partition("elements =")[2]
    return {mark for mark in (zapret2.MARK, zapret2.FAKE_MARK)
            if re.search(rf"\b(?:{mark:#x}|{mark})\b", items, re.IGNORECASE)}


def main():
    require(
        os.geteuid() == 0
        and not os.path.samefile("/proc/self/ns/net", "/proc/1/ns/net")
        and socket.if_nameindex() == [(1, "lo")]
        and not run("nft", "list", "tables").strip(),
        "fresh_network_namespace",
    )
    run("nft", "-f", "-", input_text=render("selected"))
    require(not marks(), "guard_initially_closed")

    h = Harness()
    kernel = zapret2.Runtime()
    h.runtime.gate = kernel.gate
    offset = 0
    actual_time = zapret2.time
    zapret2.time = SimpleNamespace(time=lambda: time.time() + offset, monotonic=time.monotonic)
    cdn = "https://r1.googlevideo.com/videoplayback"
    h.cfg.zapret2.youtube_transport_probe = True
    h.cfg.zapret2.probe_urls[1] = f"{cdn}?expire={int(time.time()) + 9}"
    expected = {zapret2.MARK, zapret2.FAKE_MARK}
    try:
        for seconds in (0, 1, 2):
            h.step(seconds)
        require(zapret2.active(h.current) and marks() == expected, "both_marks_present")
        original_until = h.controller.cdn_gate_until

        offset = -120
        h.step(3)
        renewed_until = h.controller.cdn_gate_until
        require(renewed_until <= original_until + 0.2 and marks() == expected,
                "clock_rollback_does_not_extend_lease")

        # No controller step runs while the kernel lease expires.
        while time.monotonic() <= original_until + 0.7 and marks():
            time.sleep(0.1)
        require(not marks() and zapret2.active(h.current), "kernel_expires_without_watchdog")
        print(f"KERNEL_EXPIRED_AFTER_S {time.monotonic() - renewed_until:.2f}", flush=True)

        h.step(20)
        require(h.controller.view["reason"] == zapret2.CDN_EXPIRED
                and h.controller.view["gate_closed"] and not zapret2.active(h.current)
                and not marks() and not h.runtime.up, "watchdog_confirms_fallback")

        offset = 0
        h.cfg.zapret2.probe_urls[1] = f"{cdn}?expire={int(time.time()) + 14}"
        for seconds in (21, 22, 23):
            h.step(seconds)
        require(zapret2.active(h.current) and marks() == expected, "fresh_url_can_reopen_gate")
    finally:
        zapret2.time = actual_time
        h.controller.close()
    require(not marks(), "guard_closed_on_exit")


if __name__ == "__main__":
    main()
