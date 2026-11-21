"""Open and cancel the installed server confirmation without a write request."""

from __future__ import annotations

import sys
from pathlib import Path

from gui_map_visibility import desktop_window, wait
from vpn_ui.qt import QtCore, QtWidgets


def check(work):
    with desktop_window(work) as (app, window):
        bridge = window.bridge
        wait(app, lambda: bridge.can_select and any(
            item.choosable and not item.pool for item in bridge.entries
        ), "no_selectable_subscription_server", seconds=15)
        chosen = next(item for item in bridge.entries if item.choosable and not item.pool)
        results = []
        timer = QtCore.QTimer(window)

        def inspect():
            box = app.activeModalWidget()
            if not isinstance(box, QtWidgets.QMessageBox):
                return
            timer.stop()
            buttons = {button.text(): button for button in box.buttons()}
            cancel = buttons.get("Отмена")
            valid = (set(buttons) == {"На 10 минут", "Бессрочно", "Отмена"}
                     and box.defaultButton() is cancel and box.escapeButton() is cancel)
            results.append(valid and box.grab().save(str(work / "pin-installed-dialog.png")))
            if cancel is not None:
                cancel.click()
            else:
                box.reject()

        timer.timeout.connect(inspect)
        timer.start(25)
        try:
            window.sidebar.select(chosen)
        finally:
            timer.stop()
        if results != [True] or bridge.client.writes:
            raise ValueError("installed_dialog_or_cancel")
        print("PIN_INSTALLED_DIALOG_OK POST_0", flush=True)


if __name__ == "__main__":
    try:
        check(Path(sys.argv[1]))
    except ValueError as exc:
        print("PIN_INSTALLED_FAILED", exc, file=sys.stderr)
        sys.exit(2)
