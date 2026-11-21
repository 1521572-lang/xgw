"""Exercise the real XGW desktop map against the installed panel, using only GET."""

from __future__ import annotations

import contextlib
import sys
import time
from pathlib import Path

from vpn_ui.qt import QtCore, QtWidgets
from vpn_ui.views.main_window import prepare_application
from vpn_ui.xgw.backend import GuardedApiClient, XgwBridge
from vpn_ui.xgw.window import XgwWindow
from xgw.gui import login, model


class ReadOnlyClient(GuardedApiClient):
    writes = 0

    def act(self, name, body=None, key=None):
        self.writes += 1
        return False


def wait(app, condition, label, seconds=16):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        time.sleep(0.01)
    raise ValueError(label)


def confirmed_country(state):
    if model.pool_house(state):
        row = model.pool_flow(state) or {}
    else:
        main = model.main_server(state)
        rows = state.get("servers") or []
        if main:
            row = next((row for row in rows if row.get("tag") == main.tag), {})
        else:
            selected = [row for row in rows if row.get("selected")]
            row = selected[0] if len(selected) == 1 else {}
    return str(row.get("endpoint_country") or "").upper()


@contextlib.contextmanager
def desktop_window(work, *, client_type=ReadOnlyClient):
    session = model.load_session(model.session_file())
    if session is None:
        raise ValueError("no_desktop_session")
    app = QtWidgets.QApplication([])
    if app.platformName() in ("minimal", "offscreen"):
        raise ValueError("no_desktop_display")
    prepare_application(app)
    # The installed panel may still compile its first state on the cold path.
    model.REQUEST_TIMEOUT = 25
    client = client_type(session)
    flow = login.LoginFlow(client.exchange, command=lambda: "Используется действующий сеанс.")
    bridge = XgwBridge(client)
    window = XgwWindow(bridge, flow, work / "gui-session.json", theme_name="dark")
    window.setWindowTitle("XGW · проверка карты")
    try:
        window.show()
        client.start()
        wait(app, lambda: bridge.received and not bridge.stale, "no_fresh_state", seconds=35)
        yield app, window
    finally:
        window.close()
        app.processEvents()


def check(work):
    with desktop_window(work) as (app, window):
        bridge = window.bridge
        client = bridge.client
        canvas = window.map
        stopped = QtCore.QAbstractAnimation.State.Stopped
        wait(app, lambda: bool(canvas.focus_code and canvas._pulse.isActive()),
             "no_confirmed_active_country", seconds=18)
        if canvas.focus_code != confirmed_country(bridge.state):
            raise ValueError("wrong_country_source")
        if not canvas.grab().save(str(work / "map-before.png")):
            raise ValueError("screenshot_before")
        print("MAP_LIVE_COUNTRY_OK", flush=True)

        window.showMinimized()
        wait(app, lambda: window.isMinimized() and not client.visible, "not_minimized")
        before = bridge.received
        client.poll_soon(0)
        wait(app, lambda: bridge.received > before, "no_snapshot_while_minimized")
        if (canvas._pulse.isActive() or canvas._move.state() != stopped
                or canvas._tint.state() != stopped):
            raise ValueError("animation_running_when_minimized")
        print("MAP_MINIMIZED_IDLE_OK", flush=True)

        before = bridge.received
        window.showNormal()
        wait(app, lambda: client.visible and bridge.received > before and canvas._pulse.isActive(),
             "map_did_not_resume")
        if canvas.focus_code != confirmed_country(bridge.state):
            raise ValueError("wrong_restored_country")
        phase = canvas._phase
        wait(app, lambda: canvas._phase != phase, "no_pulse_after_resume", seconds=3)
        if not canvas.grab().save(str(work / "map-restored.png")):
            raise ValueError("screenshot_restored")
        print("MAP_RESTORED_OK", flush=True)

        window.hide()
        wait(app, lambda: not client.visible and not canvas._pulse.isActive(), "not_hidden")
        window.show()
        wait(app, lambda: client.visible and canvas._pulse.isActive(), "not_shown")
        if client.writes:
            raise ValueError("write_attempt")
        print("MAP_HIDE_SHOW_OK POST_0", flush=True)


if __name__ == "__main__":
    try:
        check(Path(sys.argv[1]))
    except ValueError as exc:
        print("MAP_LIVE_FAILED", exc, file=sys.stderr)
        sys.exit(2)
