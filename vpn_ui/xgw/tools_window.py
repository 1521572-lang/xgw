"""Существующие функциональные страницы XGW с тем же клиентом и защитами действий."""
from xgw.gui import theme
from xgw.gui.devices import DevicesPage
from xgw.gui.operations import DiagnosticsPage, ExtraPage
from xgw.gui.pages import ServersPage, SubscriptionsPage
from xgw.gui.traffic import TrafficPage
from xgw.gui.zapret2 import Zapret2Page

from ..qt import QtCore, QtGui, QtWidgets
from ..theme.qss_builder import combo_controls

PAGES = {"servers": ("Серверы", ServersPage), "subscriptions": ("Подписки", SubscriptionsPage),
         "devices": ("Устройства", DevicesPage), "traffic": ("Трафик", TrafficPage),
         "diagnostics": ("Диагностика", DiagnosticsPage), "extra": ("Ещё", ExtraPage),
         "zapret2": ("zapret2", Zapret2Page)}


class ToolsWindow(QtWidgets.QMainWindow):
    def __init__(self, bridge, parent=None, *, arrow_image=""):
        super().__init__(parent)
        self.bridge = bridge
        self.client = bridge.client
        self.pages = {}
        self.key = ""
        self.stack = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.stack)
        self.resize(900, 720)
        self.setMinimumSize(680, 520)
        colors = theme.current()
        self.setPalette(theme.palette(colors))
        self.setStyleSheet(theme.stylesheet(colors) + combo_controls(arrow_image))
        bridge.gateway_changed.connect(self.refresh)
        self.client.actionFinished.connect(self.action_done)

    @property
    def state(self):
        return self.bridge.state

    @property
    def stale(self):
        return self.bridge.stale

    @property
    def link(self):
        return self.bridge.link

    def open_browser(self):
        port = self.client.session.port if self.client.session else 8781
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(f"http://127.0.0.1:{port}/"))

    def open_section(self, key):
        if key not in PAGES:
            return
        self.key = key
        title, factory = PAGES[key]
        if key not in self.pages:
            self.pages[key] = factory(self)
            self.stack.addWidget(self.pages[key])
        self.setWindowTitle("XGW · " + title)
        self.stack.setCurrentWidget(self.pages[key])
        self.show()
        self.raise_()
        self.refresh()

    def refresh(self):
        page = self.pages.get(self.key)
        if page is None or not self.isVisible():
            return
        # Отключается вся страница, включая прежние обработчики меню, при потере связи.
        page.setEnabled(not self.stale and not self.bridge.busy)
        if self.key == "traffic":
            page.refresh()
        else:
            page.show_state(self.state)
        if self.stale:
            self.statusBar().showMessage("Нет свежих данных шлюза. Изменения недоступны.")
        elif self.statusBar().currentMessage() == "Нет свежих данных шлюза. Изменения недоступны.":
            self.statusBar().clearMessage()

    def action_done(self, key, ok, text):
        if self.isVisible():
            self.statusBar().showMessage(text, 15000)
        if "subscriptions" in self.pages:
            self.pages["subscriptions"].action_done(key, ok)

    def closeEvent(self, event):
        # Закрытие вспомогательного окна не закрывает общий ApiClient.
        self.hide()
        event.accept()
