"""Test the local panel's read-only recovery in a separate system Firefox profile."""

from __future__ import annotations

import argparse
import contextlib
import hmac
import http.client
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait

OVERVIEW = "/api/zapret2/overview"
ASSETS = ("/app.css", "/zapret2.css", "/icon.svg")
LIMIT = 1024 * 1024


class FailedCheck(ValueError):
    pass


def require(condition, label):
    if not condition:
        raise FailedCheck(label)


def login():
    result = subprocess.run(["sudo", "-n", "xgw", "panel", "--gui-login"],
                            capture_output=True, check=False, timeout=20)
    require(result.returncode == 0, "login_cli")
    data = json.loads(result.stdout)
    require(isinstance(data, dict), "login_payload")
    port, code = data.get("port"), data.get("code")
    require(type(port) is int and 0 < port < 65536 and isinstance(code, str)
            and re.fullmatch(r"[A-Za-z0-9_-]{16,128}", code), "login_payload")
    with contextlib.closing(http.client.HTTPConnection("127.0.0.1", port, timeout=8)) as client:
        client.request("GET", f"/?login={code}")
        response = client.getresponse()
        cookie = SimpleCookie(response.getheader("Set-Cookie", "")).get("xgw_panel")
        require(response.status == 303 and cookie is not None, "login_exchange")
    return port, f"xgw_panel={cookie.value}"


class Bridge(ThreadingHTTPServer):
    def __init__(self, upstream, ui):
        super().__init__(("127.0.0.1", 0), Handler)
        self.port, self.cookie = upstream
        self.access = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.fault = self.reads = self.writes = 0
        self.last_get = 0.0
        self.files = {
            "/zapret2": ("text/html; charset=utf-8", (ui / "zapret2.html").read_bytes()),
            "/zapret2.js": ("text/javascript; charset=utf-8", (ui / "zapret2.js").read_bytes()),
        }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send(self, status, content_type="text/plain", body=b""):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with contextlib.suppress(OSError):
            self.wfile.write(body)

    def authenticated(self):
        host = f"127.0.0.1:{self.server.server_port}"
        supplied = self.headers.get("Cookie", "").encode("latin-1")
        expected = f"xgw_trial={self.server.access}".encode("ascii")
        return self.headers.get("Host") == host and hmac.compare_digest(supplied, expected)

    def do_POST(self):
        if self.authenticated():
            with self.server.lock:
                self.server.writes += 1
        self.send(405)

    def do_GET(self):
        if self.path == "/":
            self.send(200, "text/html", b"<title>XGW browser trial</title>")
        elif not self.authenticated():
            self.send(403)
        elif self.path in self.server.files:
            self.send(200, *self.server.files[self.path])
        elif self.path in (*ASSETS, OVERVIEW):
            self.forward()
        else:
            self.send(404)

    def forward(self):
        if self.path == OVERVIEW:
            with self.server.lock:
                self.server.reads += 1
                self.server.last_get = time.monotonic()
                fault = self.server.fault
            if fault:
                self.send(fault)
                return
        try:
            with contextlib.closing(http.client.HTTPConnection(
                "127.0.0.1", self.server.port, timeout=8,
            )) as client:
                client.request("GET", self.path, headers={"Cookie": self.server.cookie})
                result = client.getresponse()
                body = result.read(LIMIT + 1)
                if len(body) <= LIMIT:
                    self.send(result.status, result.getheader("Content-Type", "text/plain"), body)
                    return
        except (OSError, http.client.HTTPException):
            pass
        self.send(502)


def check(browser, bridge, work):
    def element(name):
        return browser.find_element(By.ID, name)

    wait = WebDriverWait(browser, 16, poll_frequency=0.1)
    base = f"http://127.0.0.1:{bridge.server_port}"
    browser.set_page_load_timeout(18)
    browser.get(base)
    browser.add_cookie({"name": "xgw_trial", "value": bridge.access, "httpOnly": True})
    browser.get(base + "/zapret2")
    wait.until(lambda _: element("edit-settings").is_enabled())
    require(not element("retry-overview").is_displayed(), "retry_visible_when_healthy")
    element("edit-settings").click()
    wait.until(lambda _: element("settings-form").is_displayed())
    field = element("setting-check")
    draft = "240" if field.get_property("value") != "240" else "180"
    field.clear()
    field.send_keys(draft)
    submit = element("settings-form").find_element(By.CSS_SELECTOR, '[type="submit"]')

    with bridge.lock:
        bridge.fault = 503
    retry = element("retry-overview")
    wait.until(lambda _: retry.is_displayed() and retry.is_enabled())
    require(element("state").text == "Связь с панелью прервана", "missing_unavailable")
    require(browser.execute_script("return navigator.onLine"), "not_local_failure")
    require(field.get_property("value") == draft and not submit.is_enabled(), "offline_draft")
    browser.save_screenshot(str(work / "retry-unavailable.png"))
    print("WEB_RETRY_OFFERED", flush=True)

    with bridge.lock:
        bridge.fault = 0
        before = bridge.reads
        started = time.monotonic()
    retry.click()
    wait.until(lambda _: not retry.is_displayed() and submit.is_enabled())
    with bridge.lock:
        elapsed = round(1000 * (bridge.last_get - started))
        require(bridge.reads == before + 1 and 0 <= elapsed <= 3000, "retry_get_count_or_latency")
    require(field.get_property("value") == draft, "retry_draft")
    browser.save_screenshot(str(work / "retry-recovered.png"))
    print("WEB_RETRY_OK", elapsed, flush=True)
    element("cancel-settings").click()

    with bridge.lock:
        bridge.fault = 401
    wait.until(lambda _: element("state").text == "Войдите в XGW")
    require(not retry.is_displayed() and not element("edit-settings").is_enabled(), "expired_login")
    with bridge.lock:
        require(bridge.writes == 0, "unexpected_write")
    print("WEB_RETRY_AUTH_OK POST_0", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("geckodriver")
    args = parser.parse_args()
    stage = "bridge"
    try:
        require(os.geteuid() != 0 and os.environ.get("DISPLAY"), "display_required")
        with Bridge(login(), args.work / "src/xgw/ui") as bridge:
            thread = threading.Thread(target=bridge.serve_forever, daemon=True)
            thread.start()
            try:
                stage = "firefox"
                profile = args.work / "profiles"
                profile.mkdir(mode=0o700, exist_ok=True)
                service = Service(executable_path=args.geckodriver, log_output=subprocess.DEVNULL,
                                  service_args=["--profile-root", str(profile)])
                options = webdriver.FirefoxOptions()
                options.set_preference("network.proxy.type", 0)
                with webdriver.Firefox(service=service, options=options) as browser:
                    print("WEB_BROWSER Firefox", browser.capabilities.get("browserVersion"),
                          flush=True)
                    stage = "ui"
                    check(browser, bridge, args.work)
            finally:
                bridge.shutdown()
    except (OSError, ValueError, subprocess.SubprocessError, WebDriverException) as exc:
        label = str(exc) if isinstance(exc, FailedCheck) else type(exc).__name__
        print("WEB_RETRY_FAILED", stage, label, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
