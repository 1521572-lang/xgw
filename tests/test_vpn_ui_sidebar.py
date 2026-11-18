"""Ряды с одинаковой страной сохраняют идентичность при живом обновлении списка."""

import os
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XGW_UI_QT"] = "PyQt6"
pytest.importorskip("PyQt6.QtWidgets")
pytest.importorskip("PyQt6.QtSvg")

from PyQt6.QtTest import QSignalSpy, QTest
from vpn_ui.qt import Qt, QtCore, QtWidgets, Signal

from vpn_ui.xgw.catalog import POOL, Entry, Source
from vpn_ui.xgw.sidebar import Sidebar


class Bridge(QtCore.QObject):
    gateway_changed = Signal()
    section_requested = Signal(str)
    can_select = True
    pool_error = ""

    def __init__(self):
        super().__init__()
        self.pool = {}
        self.sources = [Source("sub:A", "Подписка", "")]
        self.entries = [Entry(str(index), "sub:A", f"Имя {index:02d}", "VLESS · 22 мс", "NL",
                              "member", False, True, 100 - index, 22, rating=0.75)
                        for index in range(30)]
        self.sent = []

    def select(self, identifier):
        self.sent.append(identifier)

    def fetch_pool(self):
        pass


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
        assert selected.text(0) == "Имя 18\nНидерланды" and "82,0" in selected.text(1)
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
        assert "81,0" in selected.text(1) and "0,50" in selected.text(2)
        assert sidebar.info.title.text() == "Имя 18"
        assert sidebar.hide_details()
        QTest.keyClick(servers, Qt.Key.Key_Return)
        assert sidebar.info.title.text() == "Имя 18" and sidebar.info.isVisible()
        assert not bridge.sent
        if os.environ.get("XGW_SIDEBAR_SCREENSHOT"):
            parent.grab().save(os.environ["XGW_SIDEBAR_SCREENSHOT"])
    finally:
        parent.close()


def test_header_clicks_sort_without_selecting_server(app):
    bridge = Bridge()
    bridge.entries = [replace(bridge.entries[0], name="b", speed=9, rating=0.9, chosen=True),
                      replace(bridge.entries[1], name="a", speed=100, rating=0.1),
                      replace(bridge.entries[2], name="c", speed=None, rating=None)]
    parent = QtWidgets.QWidget()
    sidebar = Sidebar(bridge, parent)
    parent.resize(1024, 720)
    sidebar.setGeometry(8, 38, 340, 650)
    parent.show()
    app.processEvents()
    header = sidebar.servers.header()

    def names():
        return [sidebar.servers.topLevelItem(i).text(0).splitlines()[0] for i in range(3)]

    def indicator(column, direction):
        row = sidebar.servers.headerItem()
        assert [row.text(i) for i in range(3)] == ["Серверы (3)", "Мбит/с", "Рейтинг"]
        assert [i for i in range(3) if not row.icon(i).isNull()] == [column]
        assert row.toolTip(column).endswith(direction)

    def click(column):
        x = header.sectionViewportPosition(column) + header.sectionSize(column) // 2
        QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton,
                         pos=QtCore.QPoint(x, header.height() // 2))
        app.processEvents()

    try:
        assert names() == ["a", "b", "c"]
        assert not header.isSortIndicatorShown()
        indicator(0, "По возрастанию")
        click(0)
        assert names() == ["c", "b", "a"]
        indicator(0, "По убыванию")
        click(1)
        assert names() == ["a", "b", "c"]
        indicator(1, "По убыванию")
        click(1)
        assert names() == ["b", "a", "c"]
        indicator(1, "По возрастанию")
        click(2)
        assert names() == ["b", "a", "c"]
        indicator(2, "По убыванию")
        click(2)
        assert names() == ["a", "b", "c"]
        indicator(2, "По возрастанию")
        bridge.gateway_changed.emit()
        assert names() == ["a", "b", "c"]
        assert not header.isSortIndicatorShown()
        indicator(2, "По возрастанию")
        QTest.mouseClick(sidebar.filter, Qt.MouseButton.LeftButton,
                         pos=sidebar.filter.tabRect(2).center())
        assert sidebar.servers.topLevelItemCount() == 1
        assert sidebar.servers.topLevelItem(0).text(0).splitlines()[0] == "b"
        bridge.gateway_changed.emit()
        assert sidebar.servers.topLevelItemCount() == 1
        sidebar.filter.setCurrentIndex(0)
        assert names() == ["a", "b", "c"]
        bridge.sources.append(Source(POOL, "Бесплатный пул", "Наблюдение"))
        bridge.entries.extend([
            replace(bridge.entries[0], id="pool:ok", source=POOL, pool=True,
                    chosen=False, choosable=False, admitted=True),
            replace(bridge.entries[1], id="pool:no", source=POOL, pool=True,
                    chosen=False, choosable=False, admitted=False),
        ])
        bridge.gateway_changed.emit()
        sidebar.sources.setCurrentRow(1)
        sidebar.filter.setCurrentIndex(1)
        assert sidebar.filter.tabText(1) == "Допущенные"
        assert sidebar.servers.topLevelItemCount() == 1
        sidebar.servers.setCurrentItem(sidebar.servers.topLevelItem(0))
        assert not sidebar.choose.isEnabled()
        assert bridge.sent == []
    finally:
        parent.close()


def test_map_pulses_only_for_visible_known_active_country(app):
    from vpn_ui.core.state import ConnectionState

    from vpn_ui.views.map_canvas_view import MapCanvasView

    canvas = MapCanvasView()
    canvas.resize(900, 600)
    canvas.show()
    try:
        canvas.set_state(ConnectionState.CONNECTED)
        assert not canvas._pulse.isActive()
        canvas.set_focus("JP")
        assert canvas._pulse.isActive()
        assert canvas._move.state() == QtCore.QAbstractAnimation.State.Running
        before = canvas._phase
        ticks = QSignalSpy(canvas._pulse.timeout)
        assert ticks.wait(1500), "таймер не выпустил ни одного импульса"
        assert canvas._phase != before
        canvas.set_focus("")
        assert not canvas._pulse.isActive()
        canvas.set_focus("DE")
        assert canvas._pulse.isActive()
        canvas.hide()
        assert not canvas._pulse.isActive()
        canvas.show()
        assert canvas._pulse.isActive()
        canvas.set_state(ConnectionState.DISCONNECTED)
        assert not canvas._pulse.isActive()
    finally:
        canvas.close()
