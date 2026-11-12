"""Главное окно: шапка, левая панель, карта с карточкой, правая панель функций и настройки."""
from __future__ import annotations

from .. import theme
from ..components.custom_titlebar import CustomTitleBar
from ..components.feature_tile import FeatureTile
from ..core.bridge import VpnUiBridge
from ..core.state import (
    GROUP_COUNTRIES,
    GROUP_GATEWAYS,
    GROUP_PROFILES,
    ConnectionSnapshot,
    ConnectionState,
    FeaturesState,
    LocationInfo,
    UiSettings,
)
from ..qt import Qt, QtCore, QtGui, QtWidgets, Signal
from ..theme import qss_builder, svg_loader, tokens
from ..theme.tokens import Metrics
from .connection_card_view import ConnectionCardView, SessionDetailsView
from .map_canvas_view import MapCanvasView
from .settings_drawer_view import SettingsDrawerView
from .sidebar_view import SidebarView

# ключ функции → подпись и иллюстрации «выключено» / «включено»
WIDGETS = (
    ("kill_switch", "Kill switch", "kill-switch-off", "kill-switch-on-standard"),
    ("split_tunneling", "Раздельное туннелирование", "split-tunneling-off",
     "split-tunneling-standard"),
    ("custom_dns", "Свой DNS", "netshield-off", "netshield-on-level-1"),
    ("lan_bypass", "Локальная сеть", "port-forwarding-off", "port-forwarding-on"),
)
SIDEBAR_RANGE = (200, 400)  # SidebarMinWidth..SidebarMaxWidth


def prepare_application(app: QtWidgets.QApplication) -> None:
    """Единый вид на любом рабочем столе: стиль Fusion и шрифт темы."""
    app.setStyle("Fusion")
    font = QtGui.QFont(theme.manager().family())
    font.setPixelSize(tokens.BODY.size)
    app.setFont(font)


class WidgetBar(QtWidgets.QFrame):
    """Правая панель: плитки быстрых функций и кнопка настроек под разделителем."""

    settings_requested = Signal()

    def __init__(self, bridge: VpnUiBridge, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self.setObjectName("WidgetPane")
        column = QtWidgets.QVBoxLayout(self)
        column.setContentsMargins(6, 6, 6, 6)
        column.setSpacing(6)
        self.tiles: dict[str, FeatureTile] = {}
        for key, caption, art_off, art_on in WIDGETS:
            tile = FeatureTile(key, caption, art_off, art_on, self)
            tile.clicked.connect(lambda _checked=False, k=key: self._toggle(k))
            self.tiles[key] = tile
            column.addWidget(tile)
        separator = QtWidgets.QFrame(self)
        separator.setObjectName("WidgetSeparator")
        separator.setFixedHeight(1)
        column.addWidget(separator)
        self.settings = FeatureTile("settings", "Настройки", "settings", None, self)
        self.settings.clicked.connect(self.settings_requested)
        column.addWidget(self.settings)
        bridge.features_changed.connect(self.show_features)
        self.show_features(bridge.features)

    def _toggle(self, key: str) -> None:
        self.bridge.request_feature(key, not self.tiles[key].is_on())

    def show_features(self, features: FeaturesState) -> None:
        for key, tile in self.tiles.items():
            tile.set_on(features.enabled(key))

    def set_bar_width(self, width: int) -> None:
        self.setFixedWidth(width)
        inner = width - 14  # поля 6 и рамка 1 с каждой стороны
        for tile in (*self.tiles.values(), self.settings):
            tile.setFixedHeight(tile.heightForWidth(inner))


class Backdrop(QtWidgets.QWidget):
    """Затемнение под панелью настроек; нажатие по нему закрывает панель."""

    clicked = Signal()

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), theme.qcolor(theme.palette().backdrop))
        painter.end()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        self.clicked.emit()
        event.accept()


class SizeGrip(QtWidgets.QWidget):
    """Полоска между левой панелью и картой: тянется мышью, меняет ширину панели."""

    dragged = Signal(int)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setToolTip("Потяните, чтобы изменить ширину панели")

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.dragged.emit(round(event.globalPosition().x()))


class MainWindow(QtWidgets.QWidget):
    """`use_custom_titlebar=True` — окно без системной рамки со своей шапкой."""

    def __init__(self, bridge: VpnUiBridge | None = None, *, use_custom_titlebar: bool = True,
                 title: str = "XGW VPN", theme_name: str | None = None,
                 parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.bridge = bridge or VpnUiBridge(self)
        self.use_custom_titlebar = use_custom_titlebar
        self.sidebar_width = Metrics.SIDEBAR
        self._overlay = False  # узкое окно: панель раскрыта поверх карты
        self._shown = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._arrow_dir = QtCore.QTemporaryDir()
        self.setObjectName("MainWindow")
        self.setWindowTitle(title)
        self.setMinimumSize(*Metrics.WINDOW_MIN)
        self.setMouseTracking(True)
        if use_custom_titlebar:
            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)

        self.map = MapCanvasView(self)
        self.map.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.titlebar = CustomTitleBar(title, native=not use_custom_titlebar, parent=self)
        self.card = ConnectionCardView(self.bridge, self)
        self.details = SessionDetailsView(self.bridge, self)
        self.details.setMaximumWidth(Metrics.CONTENT_MAX)
        self.widgets = WidgetBar(self.bridge, self)
        self.sidebar_slot = QtWidgets.QWidget(self)
        self.sidebar_slot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.grid = QtWidgets.QGridLayout()
        self.grid.setContentsMargins(Metrics.EDGE, 0, Metrics.EDGE, Metrics.EDGE)
        self.grid.setHorizontalSpacing(Metrics.EDGE)
        self.grid.setVerticalSpacing(0)
        self.grid.addWidget(self.sidebar_slot, 0, 0, 3, 1)
        self.grid.addWidget(self.card, 0, 1, Qt.AlignmentFlag.AlignTop)
        self.grid.addWidget(self.widgets, 0, 2, 2, 1, Qt.AlignmentFlag.AlignTop)
        self.grid.addWidget(self.details, 2, 1, 1, 2)
        self.grid.setColumnStretch(1, 1)
        self.grid.setRowStretch(1, 1)
        self.grid.setRowMinimumHeight(1, 32)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.titlebar)
        outer.addLayout(self.grid, 1)

        self.sidebar = SidebarView(self.bridge, self)
        self.grip = SizeGrip(self)
        self.backdrop = Backdrop(self)
        self.backdrop.hide()
        self.drawer = SettingsDrawerView(self.bridge, self)
        self.drawer.hide()
        self._slide = QtCore.QPropertyAnimation(self.drawer, b"pos", self)
        self._slide.setDuration(180)
        self._slide.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._slide.finished.connect(self._slide_finished)

        self._build_menu()
        self._build_shortcuts()
        self.widgets.settings_requested.connect(lambda: self.open_settings())
        self.drawer.close_requested.connect(self.close_settings)
        self.backdrop.clicked.connect(self.close_settings)
        self.sidebar.expand_requested.connect(lambda: self.set_overlay(True))
        self.sidebar.activated.connect(lambda: self.set_overlay(False))
        self.grip.dragged.connect(self._grip_dragged)
        self.bridge.connection_changed.connect(self._connection)
        self.bridge.servers_changed.connect(self._servers)
        self.bridge.location_changed.connect(self._location)
        self.bridge.settings_changed.connect(self._settings)

        self.apply_theme(theme_name or self.bridge.settings.theme)
        self.resize(*Metrics.WINDOW)
        self._servers(self.bridge.servers)
        self._connection(self.bridge.connection)

    # --- меню и горячие клавиши ------------------------------------------------------
    def _build_menu(self) -> None:
        self.menu = QtWidgets.QMenu(self)
        # лямбды: сигнал triggered несёт флаг «отмечено», слотам он не нужен
        self.menu.addAction("Настройки", lambda: self.open_settings())
        self.theme_action = self.menu.addAction("", lambda: self.toggle_theme())
        self.menu.addSeparator()
        self.menu.addAction("Выход", lambda: self.close())
        self.titlebar.menu_requested.connect(self._show_menu)

    def _show_menu(self) -> None:
        button = self.titlebar.menu_button
        self.menu.popup(button.mapToGlobal(QtCore.QPoint(0, button.height() + 2)))

    def _build_shortcuts(self) -> None:
        bindings = {
            "Ctrl+F": self.focus_search,
            "Ctrl+2": lambda: self._open_section(GROUP_COUNTRIES),
            "Ctrl+3": lambda: self._open_section(GROUP_PROFILES),
            "Ctrl+4": lambda: self._open_section(GROUP_GATEWAYS),
            "Ctrl+,": lambda: self.open_settings(),
            "Escape": self._escape,
        }
        self.shortcuts = []
        for keys, handler in bindings.items():
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(keys), self)
            shortcut.activated.connect(handler)
            self.shortcuts.append(shortcut)

    def _open_section(self, group: str) -> None:
        if self.sidebar.compact:
            self.set_overlay(True)
        self.sidebar.set_group(group)

    def focus_search(self) -> None:
        if self.sidebar.compact:
            self.set_overlay(True)
        self.sidebar.focus_search()

    def _escape(self) -> None:
        if self.drawer.isVisible():
            self.close_settings()
        elif self._overlay:
            self.set_overlay(False)

    # --- тема ------------------------------------------------------------------------
    def apply_theme(self, name: str) -> None:
        manager = theme.manager()
        manager.set_theme(name)
        colors = manager.palette
        arrow = ""
        if self._arrow_dir.isValid():
            arrow = f"{self._arrow_dir.path()}/chevron-{colors.name}.png"
            svg_loader.icon_pixmap("ChevronDown", colors.text_weak, 16, 2.0).save(arrow)
        app = QtWidgets.QApplication.instance()
        app.setStyleSheet(qss_builder.build(colors, manager.family(), arrow))
        self.theme_action.setText("Светлая тема" if colors.name == "dark" else "Тёмная тема")
        self.update()

    def toggle_theme(self) -> None:
        name = "light" if theme.palette().name == "dark" else "dark"
        self.bridge.request_settings(theme=name)

    def _settings(self, settings: UiSettings) -> None:
        if settings.theme != theme.palette().name:
            self.apply_theme(settings.theme)

    # --- состояние от моста ----------------------------------------------------------
    def _connection(self, snapshot: ConnectionSnapshot) -> None:
        self.map.set_state(snapshot.state)
        self._refocus()

    def _servers(self, servers: list) -> None:
        self.map.set_markers(node.country_code for node in servers
                             if node.group == GROUP_COUNTRIES and node.country_code)
        self._refocus()

    def _location(self, _location: LocationInfo) -> None:
        self._refocus()

    def _refocus(self) -> None:
        """Карта показывает страну сервера, а без подключения — где пользователь сейчас."""
        snapshot = self.bridge.connection
        node = self.bridge.node(snapshot.server_id)
        code = self.bridge.location.country_code
        if snapshot.state is not ConnectionState.DISCONNECTED and node is not None \
                and node.country_code:
            code = node.country_code
        if code and code.upper() != self.map.focus_code:
            self.map.set_focus(code)

    # --- настройки -------------------------------------------------------------------
    def _drawer_rect(self) -> QtCore.QRect:
        width = min(Metrics.DRAWER, self.width() - 2 * Metrics.EDGE)
        top = Metrics.TITLE_BAR
        return QtCore.QRect(self.width() - Metrics.EDGE - width, top, width,
                            self.height() - top - Metrics.EDGE)

    def open_settings(self, animate: bool = True) -> None:
        target = self._drawer_rect()
        self.backdrop.setGeometry(0, Metrics.TITLE_BAR, self.width(),
                                  self.height() - Metrics.TITLE_BAR)
        self.backdrop.show()
        self.backdrop.raise_()
        self.drawer.resize(target.size())
        self.drawer.show()
        self.drawer.raise_()
        self._slide.stop()
        if animate and self.isVisible():
            self.drawer.move(self.width(), target.top())
            self._slide.setStartValue(self.drawer.pos())
            self._slide.setEndValue(target.topLeft())
            self._slide.start()
        else:
            self.drawer.move(target.topLeft())
        self.drawer.setFocus(Qt.FocusReason.OtherFocusReason)

    def close_settings(self) -> None:
        if not self.drawer.isVisible():
            return
        self._slide.stop()
        self.backdrop.hide()
        if self.isVisible():
            self._slide.setStartValue(self.drawer.pos())
            self._slide.setEndValue(QtCore.QPoint(self.width(), self.drawer.y()))
            self._slide.start()
        else:
            self.drawer.hide()

    def _slide_finished(self) -> None:
        if not self.backdrop.isVisible():
            self.drawer.hide()

    # --- адаптивная раскладка --------------------------------------------------------
    def set_overlay(self, shown: bool) -> None:
        if not self.sidebar.compact and not self._overlay:
            return
        self._overlay = shown and self.width() < Metrics.SIDEBAR_BREAK
        self._place()

    def _grip_dragged(self, global_x: int) -> None:
        local = self.mapFromGlobal(QtCore.QPoint(global_x, 0)).x()
        self.sidebar_width = max(SIDEBAR_RANGE[0], min(SIDEBAR_RANGE[1], local - Metrics.EDGE))
        self._place()

    def _place(self) -> None:
        """Пороги ширины окна и положение всего, что лежит вне сетки."""
        width = self.width()
        narrow = width < Metrics.SIDEBAR_BREAK
        if not narrow:
            self._overlay = False
        compact = narrow and not self._overlay
        self.sidebar_slot.setFixedWidth(Metrics.SIDEBAR_COMPACT if narrow else self.sidebar_width)
        self.widgets.set_bar_width(Metrics.WIDGETS if width >= Metrics.WIDGETS_BREAK
                                   else Metrics.WIDGETS_COMPACT)
        self.details.set_wide(width >= Metrics.DETAILS_BREAK)
        self.sidebar.set_compact(compact)
        self.grid.activate()
        top = Metrics.TITLE_BAR
        height = self.height() - top - Metrics.EDGE
        shown = Metrics.SIDEBAR_COMPACT if compact else min(
            self.sidebar_width, width - 2 * Metrics.EDGE)
        self.map.setGeometry(self.rect())
        self.map.lower()
        self.sidebar.setGeometry(Metrics.EDGE, top, shown, height)
        self.sidebar.raise_()
        self.grip.setGeometry(Metrics.EDGE + shown, top, Metrics.EDGE, height)
        self.grip.setVisible(not narrow)
        self.grip.raise_()
        free_left = Metrics.EDGE + self.sidebar_slot.width() + Metrics.EDGE
        free_right = width - Metrics.EDGE - self.widgets.width() - Metrics.EDGE
        self.map.set_free_area(QtCore.QRectF(free_left, top, max(1, free_right - free_left),
                                             height))
        sliding = self._slide.state() == QtCore.QAbstractAnimation.State.Running
        if self.drawer.isVisible() and not sliding:
            self.backdrop.setGeometry(0, top, width, self.height() - top)
            self.drawer.setGeometry(self._drawer_rect())
            self.backdrop.raise_()
            self.drawer.raise_()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._place()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self._place()
        if not self._shown:  # рамка фокуса появляется только после Tab, а не при открытии
            self._shown = True
            self.setFocus(Qt.FocusReason.OtherFocusReason)

    # --- изменение размера окна без системной рамки ----------------------------------
    def edges_at(self, position: QtCore.QPointF) -> Qt.Edge:
        edges = Qt.Edge(0)
        if not self.use_custom_titlebar or self.isMaximized():
            return edges
        grip = Metrics.RESIZE_GRIP
        if position.x() < grip:
            edges |= Qt.Edge.LeftEdge
        elif position.x() >= self.width() - grip:
            edges |= Qt.Edge.RightEdge
        if position.y() < grip:
            edges |= Qt.Edge.TopEdge
        elif position.y() >= self.height() - grip:
            edges |= Qt.Edge.BottomEdge
        return edges

    @staticmethod
    def _cursor_for(edges: Qt.Edge) -> Qt.CursorShape:
        horizontal = bool(edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge))
        vertical = bool(edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge))
        if horizontal and vertical:
            falling = bool(edges & Qt.Edge.LeftEdge) == bool(edges & Qt.Edge.TopEdge)
            return Qt.CursorShape.SizeFDiagCursor if falling else Qt.CursorShape.SizeBDiagCursor
        if horizontal:
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor if vertical else Qt.CursorShape.ArrowCursor

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        self.setCursor(self._cursor_for(self.edges_at(event.position())))
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        edges = self.edges_at(event.position())
        handle = self.windowHandle()
        if event.button() == Qt.MouseButton.LeftButton and edges and handle is not None:
            handle.startSystemResize(edges)
            event.accept()
            return
        if self._overlay:
            self.set_overlay(False)
        super().mousePressEvent(event)
