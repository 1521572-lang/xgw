"""A minimized map follows new state while leaving its animations stopped."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XGW_UI_QT"] = "PyQt6"
pytest.importorskip("PyQt6.QtWidgets")
pytest.importorskip("PyQt6.QtSvg")

from vpn_ui.core.state import ConnectionState  # noqa: E402
from vpn_ui.qt import QtCore, QtWidgets  # noqa: E402
from vpn_ui.views.map_canvas_view import MapCanvasView  # noqa: E402


@pytest.fixture(scope="session")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_map_snaps_to_latest_country_and_stays_idle_when_minimized(app):
    window = QtWidgets.QWidget()
    canvas = MapCanvasView(window)
    window.resize(900, 600)
    canvas.resize(window.size())
    window.show()
    app.processEvents()
    running = QtCore.QAbstractAnimation.State.Running
    stopped = QtCore.QAbstractAnimation.State.Stopped

    def assert_idle(code):
        assert canvas._move.state() == stopped
        assert canvas._tint.state() == stopped
        assert not canvas._pulse.isActive()
        assert canvas._focus == QtCore.QPointF(*canvas.points[code])

    try:
        canvas.set_state(ConnectionState.CONNECTED)
        canvas.set_focus("JP")
        assert canvas._move.state() == running
        assert canvas._tint.state() == running
        assert canvas._pulse.isActive()

        window.showMinimized()
        app.processEvents()
        assert window.isMinimized()
        assert_idle("JP")

        canvas.set_focus("DE")
        canvas.set_state(ConnectionState.CONNECTING)
        assert_idle("DE")

        window.showNormal()
        app.processEvents()
        assert canvas._pulse.isActive()
        assert canvas._focus == QtCore.QPointF(*canvas.points["DE"])
        canvas.set_focus("NL")
        assert canvas._move.state() == running
    finally:
        window.close()
