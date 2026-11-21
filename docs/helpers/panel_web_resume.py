"""Check polling and draft preservation in a headed browser against the installed XGW."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import Error, sync_playwright

from youtube_telemetry import browser_context

OVERVIEW = "/api/zapret2/overview"


class CheckFailed(ValueError):
    pass


def require(ok, stage):
    if not ok:
        raise CheckFailed(stage)


def authorize(context):
    completed = subprocess.run(["sudo", "-n", "xgw", "panel", "--gui-login"],
                               capture_output=True, timeout=20, check=False)
    require(completed.returncode == 0, "login_cli")
    data = json.loads(completed.stdout)
    require(isinstance(data, dict), "login_payload")
    port, code = data.get("port"), data.get("code")
    require(type(port) is int and 0 < port < 65536 and isinstance(code, str)
            and re.fullmatch(r"[A-Za-z0-9_-]{16,128}", code), "login_payload")
    base = f"http://127.0.0.1:{port}"
    response = context.request.get(f"{base}/?login={code}", max_redirects=0, timeout=8000)
    require(response.status == 303, "login_exchange")
    response.dispose()
    return base


def check(context, script):
    stage = "login"
    try:
        base = authorize(context)
        metrics = {"gets": 0, "writes": 0, "script": 0, "errors": 0}

        def route_read_only(route):
            request = route.request
            if request.method not in ("GET", "HEAD"):
                metrics["writes"] += 1
                route.abort()
            elif request.url == base + "/zapret2.js":
                metrics["script"] += 1
                route.fulfill(body=script, content_type="text/javascript; charset=utf-8")
            elif request.url.startswith(base + "/"):
                route.continue_()
            else:
                route.abort()

        def overview(request):
            return request.url == base + OVERVIEW and request.method == "GET"

        def overview_ok(response):
            return overview(response.request) and response.status == 200

        def count(entry):
            metrics["gets"] += int(overview(entry))

        def count_error(_):
            metrics["errors"] += 1

        context.route("**/*", route_read_only)
        stage = "page"
        page = context.new_page()
        page.on("request", count)
        page.on("pageerror", count_error)
        page.set_default_timeout(8000)
        with page.expect_response(overview_ok, timeout=15000):
            page.goto(base + "/zapret2", wait_until="domcontentloaded", timeout=15000)
        require(metrics["script"] == 1, "candidate_asset")
        page.locator("#edit-settings").click()
        form = page.locator("#settings-form")
        field = page.locator("#setting-check")
        submit = form.locator('[type="submit"]')
        form.wait_for(state="visible")
        draft = "240" if field.input_value() != "240" else "180"
        field.fill(draft)

        stage = "hidden_tab"
        other = context.new_page()
        other.bring_to_front()
        page.wait_for_function("document.visibilityState === 'hidden'", polling=100, timeout=5000)
        before = metrics["gets"]
        page.wait_for_timeout(30_000)
        require(metrics["gets"] == before, "hidden_tab_requests")
        print("WEB_HIDDEN_GETS 0", flush=True)

        stage = "visible_tab"
        with page.expect_response(overview_ok, timeout=8000):
            page.bring_to_front()
        require(page.evaluate("document.visibilityState") == "visible", "visible_tab_state")
        require(form.is_visible() and field.input_value() == draft, "draft_after_show")
        print("WEB_VISIBLE_OK", flush=True)

        stage = "offline"
        context.set_offline(True)
        page.wait_for_function("!navigator.onLine", polling=100, timeout=5000)
        page.get_by_text("Связь с панелью прервана", exact=True).wait_for(timeout=15000)
        require(form.is_visible() and field.input_value() == draft and submit.is_disabled(),
                "draft_offline")
        print("WEB_OFFLINE_DRAFT_OK", flush=True)

        stage = "online"
        with page.expect_response(overview_ok, timeout=8000):
            with page.expect_request(overview, timeout=3000):
                started = time.monotonic()
                context.set_offline(False)
            recovered_ms = round(1000 * (time.monotonic() - started))
        response_ms = round(1000 * (time.monotonic() - started))
        require(recovered_ms <= 3000, "online_get_late")
        require(page.evaluate("navigator.onLine"), "browser_still_offline")
        page.get_by_text("Связь с панелью прервана", exact=True).wait_for(state="hidden")
        require(form.is_visible() and field.input_value() == draft and submit.is_enabled(),
                "draft_after_online")
        page.locator("#cancel-settings").click()
        require(not form.is_visible(), "draft_not_closed")
        require(metrics["writes"] == 0 and metrics["errors"] == 0, "page_writes_or_errors")
        print("WEB_ONLINE_GET_MS", recovered_ms, flush=True)
        print("WEB_ONLINE_HTTP_200_MS", response_ms, flush=True)
        print("WEB_UI04_OK", json.dumps(metrics, sort_keys=True), flush=True)
    except Error:
        # Playwright errors can include the one-time login URL or selectors with data.
        raise CheckFailed(stage) from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("script", type=Path)
    parser.add_argument("--channel", default="chrome")
    args = parser.parse_args()
    args.disable_quic = args.desktop_chrome = False
    try:
        require(os.geteuid() != 0 and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
                "desktop_session_required")
        script = args.script.read_bytes()
        with sync_playwright() as pw, browser_context(pw, args) as (browser, context):
            print("WEB_BROWSER", browser.version, flush=True)
            check(context, script)
    except (OSError, ValueError, subprocess.SubprocessError, Error) as exc:
        detail = str(exc) if isinstance(exc, CheckFailed) else type(exc).__name__
        print("WEB_UI04_FAILED", detail, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
