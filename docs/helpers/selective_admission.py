"""Run the bounded Selective admission steps through the desktop panel session."""
from __future__ import annotations

import argparse
import http.client
import json
import os
import time
from pathlib import Path

from docs.helpers.headless_playback import read_format
from xgw.desync.client import Client
from xgw.desync.schema import YOUTUBE_DOMAINS
from xgw.zapret2 import STANDALONE_PREPARING_REASONS

OVERVIEW = "/api/zapret2/overview"
MODE = "/api/zapret2/mode"
RANGE_BYTES = 65536
TERMINAL = frozenset({"fallback", "blocked", "error"})


class TrialError(ValueError):
    """A fixed reason code safe for the report."""


def log(state, **fields):
    print(json.dumps({"state": state, **fields}), flush=True)


def overview(client):
    return client.request(OVERVIEW)["zapret2"]


def matched(card):
    return card["fresh"] is True and card["policy_matched"] is True and card["engine_mode"] == "off"


def off(card):
    return matched(card) and card["mode"] == card["state"] == "off"


def update(client, action, expected, **settings):
    reply = client.request(action, {"expected": expected, **settings})
    key = reply.get("config_key")
    if reply.get("ok") is not True or not isinstance(key, str) or not key:
        raise TrialError("panel_update_rejected")
    return key


def observations(client, key, deadline):
    while time.monotonic() < deadline:
        try:
            card = overview(client)
        except (OSError, KeyError, ValueError, http.client.HTTPException):
            time.sleep(1)
            continue
        if card["config_key"] != key:
            raise TrialError("policy_changed")
        if matched(card):
            yield card
        time.sleep(1)


def wait_off(client, key):
    for card in observations(client, key, time.monotonic() + 55):
        if off(card):
            return card
    raise TrialError("off_deadline")


def prepare(client, card, format_file):
    url, duration, _ = read_format(format_file)
    if duration < 195:
        raise TrialError("video_too_short")
    key = update(client, "/api/zapret2/settings", card["config_key"], settings={
        "strategy": "fake_md5", "domains": list(YOUTUBE_DOMAINS),
        "youtube_transport_probe": True, "check_seconds": 60, "retry_seconds": 120,
        "daily_probe_mb": 512, "probe_urls": ["https://www.youtube.com/t/terms", url],
    })
    return wait_off(client, key)


def observe_admission(client, key, checks, since, timeout, *, recover_cdn_once=False):
    count = 0
    last_sample = since
    pending_seen = False
    recovery_sample = None
    for card in observations(client, key, time.monotonic() + timeout):
        if card["mode"] != "selective":
            raise TrialError("unexpected_mode")
        evidence = card["evidence"]
        cdn = evidence["transport_probes"].get("cdn", {})
        state = card["state"]
        if state in TERMINAL:
            pending = evidence.get("vpn_control_retry_pending") is True
            started = cdn.get("started_at")
            if (recover_cdn_once and state == "fallback"
                    and card["reason"] == "youtube_cdn_probe_failed"
                    and cdn.get("phase") == "tls" and cdn.get("kind") == "timeout"
                    and type(started) in (int, float) and since < started <= time.time()):
                if recovery_sample is None:
                    recovery_sample = started
                    count = 0
                    last_sample = max(last_sample, started)
                    log("waiting_for_cdn_retry", reason=card["reason"], cdn_phase="tls",
                        cdn_kind="timeout", control=evidence.get("vpn_control"),
                        target=evidence.get("vpn_control_target"),
                        elapsed_s=round(started - since, 2))
                if recovery_sample == started and count == 0:
                    continue
            if pending and pending_seen:
                continue
            log(state, reason=card["reason"], cdn_phase=cdn.get("phase"), cdn_kind=cdn.get("kind"),
                control=evidence.get("vpn_control"), target=evidence.get("vpn_control_target"),
                attempts=evidence.get("vpn_control_attempts", []), retry_pending=pending)
            if not pending:
                return 2
            pending_seen = True
            continue
        if pending_seen:
            # The first admission already fell back. A later watchdog cycle belongs
            # to another trial even when its policy revision stayed the same.
            log("fallback", reason="retry_window_ended")
            return 2
        if state != "active" or evidence["transport"] != "https_reachable":
            if count:
                log("not_ready", reason="active_interrupted", checks=count)
                return 2
            continue
        at = evidence.get("last_transport_ok_at")
        if type(at) not in (int, float) or not last_sample < at <= time.time():
            continue
        if cdn.get("ok") is not True or (cdn.get("http"), cdn.get("bytes")) != (206, RANGE_BYTES):
            log("not_ready", reason="range_unconfirmed", http=cdn.get("http"), bytes=cdn.get("bytes"))
            return 2
        if cdn.get("range_verified") is not True:
            log("not_ready", reason="range_evidence_unavailable", http=206, bytes=RANGE_BYTES)
            return 2
        started = cdn.get("started_at")
        if type(started) not in (int, float) or not last_sample < started <= at:
            continue
        count += 1
        last_sample = at
        log("ready" if count == checks else "checking", checks=count, http=206, bytes=RANGE_BYTES,
            elapsed_s=round(at - since, 2))
        if count == checks:
            return 0
    log("not_ready", reason="admission_deadline", checks=count)
    return 2


def activate(client, args):
    card = overview(client)
    if not off(card):
        raise TrialError("expected_fresh_off")
    # Create the receipt before any request. An ambiguous POST is left to
    # the independent restore guard rather than sent again.
    with args.receipt.open("x", encoding="utf-8") as receipt:
        if args.format is not None:
            card = prepare(client, card, args.format)
        if (card.get("blockers", {}).get("selective") != []
                or card.get("youtube_transport_probe") is not True):
            raise TrialError("settings_not_ready")
        since = time.time()
        key = update(client, MODE, card["config_key"], mode="selective")
        receipt.write(key + "\n")
    return observe_admission(client, key, args.checks, since, args.timeout,
                             recover_cdn_once=args.recover_cdn_once)


def standalone_ready(card):
    return (matched(card) and card["mode"] == "standalone" and card["state"] == "active"
            and card.get("without_vpn") is True)


def start_standalone(client, receipt, *, strategy="multisplit"):
    card = overview(client)
    if not off(card):
        raise TrialError("expected_fresh_off")
    with receipt.open("x", encoding="utf-8") as stream:
        key = update(client, "/api/zapret2/settings", card["config_key"], settings={
            "strategy": strategy, "domains": list(YOUTUBE_DOMAINS),
            "youtube_transport_probe": False,
        })
        card = wait_off(client, key)
        if card.get("blockers", {}).get("standalone") != []:
            raise TrialError("standalone_settings_not_ready")
        key = update(client, MODE, key, mode="standalone")
        stream.write(key + "\n")
    started = time.monotonic()
    last = None
    for card in observations(client, key, started + 120):
        if card["mode"] != "standalone":
            raise TrialError("unexpected_mode")
        if standalone_ready(card):
            log("standalone_ready", waited_s=round(time.monotonic() - started, 2))
            return 0
        state, reason = card["state"], card.get("reason")
        if (state, reason) != last:
            last = (state, reason)
            log("standalone_progress", phase=state, reason=reason,
                waited_s=round(time.monotonic() - started, 2))
        if state in TERMINAL and not (state == "blocked" and reason in STANDALONE_PREPARING_REASONS):
            raise TrialError("standalone_not_ready")
    if last is not None:
        log("standalone_deadline", phase=last[0], reason=last[1])
    raise TrialError("standalone_not_ready")


def check_standalone(client, receipt):
    key = receipt.read_text(encoding="utf-8").strip()
    card = overview(client)
    if not key or card["config_key"] != key or not standalone_ready(card):
        raise TrialError("standalone_not_confirmed")
    log("standalone_ready")
    return 0


def disable(client, receipt):
    key = receipt.read_text(encoding="utf-8").strip()
    card = overview(client)
    if not key or card["config_key"] != key or card["mode"] not in ("selective", "standalone"):
        raise TrialError("policy_changed_or_receipt_missing")
    wait_off(client, update(client, MODE, key, mode="off"))
    log("off")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    admission = actions.add_parser("admit")
    admission.add_argument("receipt", type=Path)
    admission.add_argument("--format", type=Path)
    admission.add_argument("--checks", type=int, choices=(1, 2), default=1)
    admission.add_argument("--timeout", type=int, choices=range(60, 361), default=180,
                           metavar="60..360")
    admission.add_argument("--recover-cdn-once", action="store_true",
                           help="Observe one normal watchdog retry after a CDN TLS timeout")
    turn_off = actions.add_parser("off")
    turn_off.add_argument("receipt", type=Path)
    standalone = actions.add_parser("standalone")
    standalone.add_argument("receipt", type=Path)
    standalone.add_argument("--strategy", choices=("multisplit", "fake_md5"), default="multisplit")
    actions.add_parser("check-standalone").add_argument("receipt", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        client = Client()
        if args.action == "admit":
            return activate(client, args)
        if args.action == "standalone":
            return start_standalone(client, args.receipt, strategy=args.strategy)
        if args.action == "check-standalone":
            return check_standalone(client, args.receipt)
        return disable(client, args.receipt)
    except TrialError as exc:
        log("error", reason=str(exc))
        return 2
    except (OSError, KeyError, ValueError, http.client.HTTPException):
        log("error", reason="panel_or_preparation_failed")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
