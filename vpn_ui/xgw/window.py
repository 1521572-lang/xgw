"""Оформление Proton с каталогом и семантикой XGW."""
from xgw.gui import client as api
from xgw.gui import model

from .. import theme
from ..qt import QtCore, QtGui, QtWidgets, Signal
from ..views.main_window import MainWindow
from .panels import Card, Details, Settings, WidgetBar
from .sidebar import Sidebar
from .tools_window import ToolsWindow


class XgwWindow(MainWindow):
    closed = Signal()
    sidebar_type = Sidebar
    card_type = Card
    details_type = Details
    widgets_type = WidgetBar
    drawer_type = Settings

    def __init__(self, bridge, login, session_path, **kwargs):
        self.login, self.session_path = login, session_path
        super().__init__(bridge, title="XGW", **kwargs)
        self.tools = ToolsWindow(bridge, self)
        bridge.section_requested.connect(self.open_section)
        login.finished.connect(self.on_login)
        bridge.gateway_changed.connect(self._refocus)

    def _build_shortcuts(self):
        self.shortcuts = []
        for keys, handler in {"Ctrl+F": self.focus_search, "Ctrl+,": self.open_settings,
                              "Escape": self._escape,
                              "F5": lambda: self.bridge.client.poll_soon(0)}.items():
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(keys), self)
            shortcut.activated.connect(handler)
            self.shortcuts.append(shortcut)

    def apply_theme(self, name):
        super().apply_theme(name)
        c = theme.palette()
        app = QtWidgets.QApplication.instance()
        app.setStyleSheet(app.styleSheet() + f"""
            #SidebarPane QListWidget, #SidebarPane QTreeWidget {{
                background: {c.pane.qss}; color: {c.text.qss}; border: 0;
            }}
            #SidebarPane QTreeWidget::item {{ padding: 8px 4px; }}
            #SidebarPane QListWidget::item {{ padding: 6px 4px; }}
            #SidebarPane QAbstractItemView::item:selected {{
                background: {c.fill_active.qss}; color: {c.text.qss};
            }}
            #SidebarPane QPushButton, #SidebarPane QComboBox, #SettingsDrawer QPushButton,
            #SettingsDrawer QComboBox, QToolButton#XgwTool {{
                background: {c.pane.qss}; color: {c.text.qss};
                border: 1px solid {c.border_weak.qss}; border-radius: 6px; padding: 5px;
            }}
            #SidebarPane QPushButton:hover, QToolButton#XgwTool:hover {{
                background: {c.fill_active.qss};
            }}
            #SidebarPane QPushButton:disabled {{ color: {c.text_hint.qss}; }}
        """)

    def _refocus(self):
        b = self.bridge
        direct = (b.state.get("zapret2") or {}).get("mode") == "standalone"
        main = (model.main_server(b.state) if not b.stale and not direct and
                (b.state.get("capture") or {}).get("mode") == "on" else None)
        code = main.country if main else ""
        if code != self.map.focus_code:
            self.map.set_focus(code)

    def open_section(self, key):
        self.close_settings()
        if key == "login" or self.bridge.link == api.LINK_AUTH:
            self.login.start()
        else:
            self.tools.open_section(key)

    def on_login(self, session, text):
        if session is None:
            self.bridge.message = text or "Вход отменён"
        else:
            try:
                model.save_session(self.session_path, session)
            except OSError:
                self.bridge.message = "Вход выполнен, но сохранить сеанс не удалось"
            self.bridge.client.set_session(session)
        self.bridge.render()

    def bring_to_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        self.tools.hide()
        self.bridge.close()
        if self.login.process is not None:
            self.login.process.kill()
        self.closed.emit()
        event.accept()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.WindowStateChange:
            self.bridge.client.set_visible(not self.isMinimized())
