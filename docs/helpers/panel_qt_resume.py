"""Read only the installed panel while exercising hide/show in the XGW Qt window."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from xgw.gui import client as clienting
from xgw.gui import login, model, window


def wait(app, ready, stage, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if ready():
            return
        time.sleep(0.01)
    raise ValueError(stage)


def check(private_dir):
    session = model.load_session(model.session_file())
    if session is None:
        raise ValueError("qt_session")
    app = QApplication([])
    if app.platformName() in ("offscreen", "minimal"):
        raise ValueError("qt_desktop_not_available")
    client = clienting.ApiClient(session)
    flow = login.LoginFlow(client.exchange)
    main = window.MainWindow(client, flow, private_dir / "qt-gui-session.json")
    arrivals = []
    client.stateReceived.connect(lambda _: arrivals.append(time.monotonic()))
    main.setWindowTitle("XGW · проверка обновления")
    # Distinguish an immediate follow-up from an ordinary scheduled poll.
    model.POLL_VISIBLE = model.POLL_HIDDEN = 30.0

    try:
        main.show()
        client.start()
        wait(app, lambda: len(arrivals) == 1, "qt_first_state")
        if not main.isVisible() or main.state is None:
            raise ValueError("qt_window_state")
        if client.link not in (clienting.LINK_OK, clienting.LINK_STALE):
            raise ValueError("qt_window_link")

        client.poll()
        active = client.gate.issued
        if not client.gate.busy:
            raise ValueError("qt_expected_pending")
        main.hide()
        if client.visible:
            raise ValueError("qt_hide")
        main.show()
        if not client.visible:
            raise ValueError("qt_show")
        client.poll_soon(0.0)  # same callback as F5
        if client.gate.issued != active:
            raise ValueError("qt_overlapping_poll")
        wait(app, lambda: len(arrivals) == 3, "qt_followup")
        if client.gate.issued != active + 1 or client.timer.interval() != 30000:
            raise ValueError("qt_followup_count")
        print("QT_RESUME_OK", round(1000 * (arrivals[-1] - arrivals[-2])), flush=True)
    finally:
        main.close()


if __name__ == "__main__":
    try:
        check(Path(sys.argv[1]))
    except ValueError as exc:
        print(f"QT_RESUME_FAILED {exc}", file=sys.stderr)
        sys.exit(2)
