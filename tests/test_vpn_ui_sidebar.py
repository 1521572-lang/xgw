"""Ряды с одинаковой страной сохраняют идентичность при живом обновлении списка."""

import os
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XGW_UI_QT"] = "PyQt6"
pytest.importorskip("PyQt6.QtWidgets")
pytest.importorskip("PyQt6.QtSvg")

from PyQt6.QtTest import QTest

from vpn_ui.qt import Qt, QtCore, QtWidgets, Signal
from vpn_ui.xgw.catalog import Entry, Source
from vpn_ui.xgw.sidebar import Sidebar


class Bridge(QtCore.QObject):
    gateway_changed = Signal()
    section_requested = Signal(str)
    can_select = True
    pool_error = ""

    def __init__(self):
        super().__init__()
        self.sources = [Source("sub:A", "Подписка", "")]
        self.entries = [Entry(str(index), "sub:A", f"Имя {index:02d}", "VLESS · 22 мс", "NL",
                              "member", False, True, 100 - index, 22, rating=0.75)
                        for index in range(30)]
        self.sent = []

    def select(self, identifier):
        self.sent.append(identifier)


@pytest.fixture(scope="session")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_preview_is_anchored_and_refresh_keeps_scroll_and_selection(app):
    bridge = Bridge()
    parent = QtWidgets.QWidget()
    parent.resize(1024, 720)
    sidebar = Sidebar(bridge, parent)
    sidebar.setGeometry(8, 38, 280, 650)
    parent.show()
    app.processEvents()
    try:
        servers = sidebar.servers
        selected = servers.topLevelItem(18)
        servers.setCurrentItem(selected)
        servers.scrollToItem(selected, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)
        app.processEvents()
        scroll = servers.verticalScrollBar().value()
        assert scroll > 0
        assert selected.text(0) == "Нидерланды" and "82,0" in selected.text(1)
        assert servers.columnWidth(1) >= servers.fontMetrics().horizontalAdvance(selected.text(1))
        position = servers.visualItemRect(selected).center()
        QTest.mouseMove(servers.viewport(), position)
        QTest.qWait(400)
        assert sidebar.info.isVisible()
        assert sidebar.info.title.text() == "Имя 18"
        assert sidebar.info.x() > sidebar.geometry().right()
        assert not bridge.sent
        bridge.entries[18] = replace(bridge.entries[18], speed=81, rating=0.5)
        bridge.gateway_changed.emit()
        app.processEvents()
        assert servers.currentItem() is selected
        assert servers.verticalScrollBar().value() == scroll
        assert "81,0" in selected.text(1) and "0,50" in selected.text(1)
        assert sidebar.info.title.text() == "Имя 18"
        assert sidebar.hide_details()
        QTest.keyClick(servers, Qt.Key.Key_Return)
        assert sidebar.info.title.text() == "Имя 18" and sidebar.info.isVisible()
        assert not bridge.sent
        if os.environ.get("XGW_SIDEBAR_SCREENSHOT"):
            parent.grab().save(os.environ["XGW_SIDEBAR_SCREENSHOT"])
    finally:
        parent.close()
