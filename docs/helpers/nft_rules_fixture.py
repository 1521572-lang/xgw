"""Render a synthetic XGW ruleset for kernel validation in a network namespace."""

from __future__ import annotations

import argparse
from dataclasses import replace

from xgw.config import Config
from xgw.net import nft

CASES = ("off", "capture", "selected", "selected-replies", "engine",
         "tailscale-direct", "tailscale-vpn", "containers", "blocked")
SELECTED = ("selected", "selected-replies")
SINGBOX_UID = 27123


def render(case: str) -> str:
    cfg = Config()
    cfg.network.lan_if = "lan0"
    cfg.network.wan_if = "wan0"
    cfg.dns.direct_servers = ["192.0.2.53"]
    cfg.capture.containers = case == "containers"
    if cfg.capture.containers:
        cfg.capture.method = "tun"
    if case in SELECTED:
        cfg.zapret2.mode = "selective"
        cfg.zapret2.observe_synack = True
    if case == "tailscale-vpn":
        cfg.tailscale.route = "vpn"
    tailscale = case in ("tailscale-direct", "tailscale-vpn")
    rules, warnings = nft.build_rules(
        cfg, capture=case != "off", blocked=case == "blocked",
        time_uids=(), tailscale=tailscale, tailnet=tailscale,
    )
    if warnings:
        raise ValueError(warnings)
    # Exercise the dedicated UID independently of NSS on the machine running the gate.
    # The accounting prerequisites themselves are covered by the contract tests.
    rules = replace(
        rules, singbox_uid=None if case == "off" else SINGBOX_UID,
        zapret2_reply_packets=8 if case == "selected-replies" else 0,
        engine_queue=cfg.zapret2.engine_queue if case == "engine" else None,
    )
    assert (rules.zapret2_queue is not None) == (case in SELECTED)
    assert bool(rules.containers) == cfg.capture.containers
    return nft.render(rules) + nft.render6(rules) + nft.render_guard(rules)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    args = parser.parse_args()
    print(render(args.case), end="")


if __name__ == "__main__":
    main()
