"""Exercise ALT9 preferences in Firefox against the real panel on demo data."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import panel_demo
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait

from xgw import config, managed
from xgw.desync import schema

SAVED = "initial.youtube.com"
CHANGED = "edited.googlevideo.com"
EXTERNAL = "other.youtube.com"


def set_demo_policy(panel, *, mode, exclusions):
    path = managed.path_for(panel.config_path)
    current = config.load(panel.config_path)[0].desync
    policy = schema.flatten(current)
    policy.update(strategy=schema.LIVE_STRATEGY, mode=mode, flowseal_exclude_domains=exclusions)
    raw = json.loads(path.read_bytes())
    raw["desync"], raw["zapret2"] = schema.migrate(policy), {}
    managed.save(path, raw)
    panel.configure(config.load(panel.config_path)[0], panel.daemon)


def read_saved(panel):
    return config.load(panel.config_path)[0].zapret2.flowseal_exclude_domains


def check(browser, panel, port, work):
    def element(name):
        return browser.find_element(By.ID, name)

    wait = WebDriverWait(browser, 15, poll_frequency=0.1)
    base = f"http://127.0.0.1:{port}"
    browser.set_page_load_timeout(18)
    browser.get(base)
    browser.add_cookie({"name": "xgw_panel", "value": panel._cookie(), "httpOnly": True})
    browser.get(base + "/zapret2")

    def open_settings():
        button = element("edit-settings")
        wait.until(lambda _: button.is_enabled())
        button.click()
        wait.until(lambda _: element("settings-form").is_displayed())
        return element("setting-flowseal-exclusions")

    def submit():
        button = element("settings-form").find_element(By.CSS_SELECTOR, '[type="submit"]')
        wait.until(lambda _: button.is_enabled())
        button.click()

    def edit(field, value):
        field.clear()
        if value:
            field.send_keys(value)

    field = open_settings()
    assert field.is_displayed() and not field.get_property("readOnly"), "off_field"
    assert field.get_property("value") == SAVED, "saved_value"
    browser.execute_script("arguments[0].scrollIntoView({block: 'center'})", field)
    assert browser.save_screenshot(str(work / "alt9-off.png")), "off_screenshot"
    edit(field, "  " + CHANGED.upper() + "  ")
    submit()
    wait.until(lambda _: not element("settings-form").is_displayed())
    assert read_saved(panel) == [CHANGED], "replacement_not_persisted"
    print("FLOWSEAL_WEB_PERSISTED", flush=True)

    field = open_settings()
    edit(field, "outside.example.test")
    submit()
    wait.until(lambda _: "flowseal_exclude_domains" in element("command-result").text)
    assert read_saved(panel) == [CHANGED] and element("settings-form").is_displayed(), "invalid_wrote"
    assert field.get_property("value") == "outside.example.test", "invalid_lost_draft"
    element("cancel-settings").click()
    print("FLOWSEAL_WEB_INVALID_PRESERVED", flush=True)

    field = open_settings()
    edit(field, SAVED)
    set_demo_policy(panel, mode="off", exclusions=[EXTERNAL])
    submit()
    wait.until(lambda _: "Настройки изменены в другом окне" in element("command-result").text)
    assert read_saved(panel) == [EXTERNAL] and field.get_property("value") == SAVED, "conflict_lost_data"
    element("cancel-settings").click()
    print("FLOWSEAL_WEB_CONFLICT_PRESERVED", flush=True)

    set_demo_policy(panel, mode="standalone", exclusions=[EXTERNAL])
    browser.get(base + "/zapret2")
    field = open_settings()
    assert field.get_property("value") == EXTERNAL and field.get_property("readOnly"), "active_not_locked"
    assert "Только чтение" in element("flowseal-exclusion-hint").text, "readonly_label"
    browser.execute_script("arguments[0].scrollIntoView({block: 'center'})", field)
    assert browser.save_screenshot(str(work / "alt9-active.png")), "active_screenshot"
    set_demo_policy(panel, mode="off", exclusions=[EXTERNAL])
    browser.get(base + "/zapret2")
    field = open_settings()
    edit(field, "")
    submit()
    wait.until(lambda _: not element("settings-form").is_displayed())
    assert open_settings().get_property("value") == "" and read_saved(panel) == [], "clear_not_persisted"
    print("FLOWSEAL_WEB_READONLY_AND_CLEAR", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("geckodriver")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="demo-", dir=args.work) as demo:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        panel = panel_demo.build(Path(demo), port, "work")
        set_demo_policy(panel, mode="off", exclusions=[SAVED])
        panel.start()
        try:
            with tempfile.TemporaryDirectory(prefix="profiles-", dir=args.work) as profile:
                service = Service(executable_path=args.geckodriver, log_output=subprocess.DEVNULL,
                                  service_args=["--profile-root", profile])
                options = webdriver.FirefoxOptions()
                options.set_preference("network.proxy.type", 0)
                with webdriver.Firefox(service=service, options=options) as browser:
                    print("FLOWSEAL_WEB_BROWSER Firefox", browser.capabilities.get("browserVersion"), flush=True)
                    check(browser, panel, port, args.work)
        except (OSError, AssertionError, WebDriverException) as exc:
            print("FLOWSEAL_WEB_FAILED", type(exc).__name__, file=sys.stderr, flush=True)
            print(str(exc), file=sys.stderr)
            return 2
        finally:
            panel.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
