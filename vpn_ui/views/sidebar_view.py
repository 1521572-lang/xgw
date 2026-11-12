"""Левая панель: поиск, разделы (Страны / Профили / Шлюзы), фильтры и дерево серверов."""
from __future__ import annotations

from .. import theme
from ..components.custom_titlebar import IconLabel
from ..core.bridge import VpnUiBridge
from ..core.state import (
    AUTO_ID,
    GROUP_COUNTRIES,
    GROUP_GATEWAYS,
    GROUP_PROFILES,
    ConnectionState,
    ServerNode,
    best_node,
)
from ..qt import Qt, QtCore, QtGui, QtWidgets, Signal
from ..theme import svg_loader, tokens
from ..theme.tokens import Metrics

SECTIONS = (
    (GROUP_COUNTRIES, "Страны", "Earth", "ctrl + 2"),
    (GROUP_PROFILES, "Профили", "WindowTerminal", "ctrl + 3"),
    (GROUP_GATEWAYS, "Шлюзы", "Servers", "ctrl + 4"),
)
FILTERS = (("all", "Все"), ("fast", "Быстрые"), ("p2p", "P2P"), ("stream", "Стриминг"))
HEADERS = {GROUP_COUNTRIES: "Страны", GROUP_PROFILES: "Профили", GROUP_GATEWAYS: "Шлюзы"}
CHEVRON_ZONE = 40  # правая часть строки страны раскрывает список её серверов
LIST_GUTTER = 18  # от правого края строк до рамки панели; в нём живёт полоса прокрутки
SCROLLBAR = 8


class NavButton(QtWidgets.QAbstractButton):
    """Пункт раздела: иконка и название; у выбранного — подложка и полоска слева."""

    def __init__(self, text: str, icon: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon = icon
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(text)
        theme.manager().changed.connect(self.update)

    def sizeHint(self) -> QtCore.QSize:
        metrics = QtGui.QFontMetrics(theme.font(tokens.BODY_STRONG))
        return QtCore.QSize(15 + 16 + 7 + metrics.horizontalAdvance(self.text()) + 16,
                            Metrics.NAV_ITEM)

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        colors = theme.palette()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        box = QtCore.QRectF(self.rect())
        back = colors.fill_selected if self.isChecked() else (
            colors.fill_hover if self.underMouse() else None)
        painter.setPen(Qt.PenStyle.NoPen)
        if back is not None:
            painter.setBrush(theme.qcolor(back))
            painter.drawRoundedRect(box, Metrics.CONTROL_RADIUS, Metrics.CONTROL_RADIUS)
        if self.isChecked():
            painter.setBrush(theme.qcolor(colors.text))
            painter.drawRoundedRect(QtCore.QRectF(4, (box.height() - 16) / 2, 3, 16), 1.5, 1.5)
        ink = colors.text if self.isChecked() else colors.text_weak
        painter.drawPixmap(15, round((box.height() - 16) / 2),
                           svg_loader.icon_pixmap(self._icon, ink, 16, self.devicePixelRatioF()))
        painter.setFont(theme.font(tokens.BODY_STRONG if self.isChecked() else tokens.BODY))
        painter.setPen(theme.qcolor(ink))
        painter.drawText(QtCore.QRectF(38, 0, box.width() - 38, box.height()),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text())
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(theme.qcolor(colors.border_focus), 2.0))
            painter.drawRoundedRect(box.adjusted(1, 1, -1, -1), Metrics.CONTROL_RADIUS,
                                    Metrics.CONTROL_RADIUS)
        painter.end()

    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self.update()
        super().leaveEvent(event)


class PivotTab(QtWidgets.QAbstractButton):
    """Текстовая вкладка фильтра; под выбранной — черта 16×2."""

    def __init__(self, key: str, text: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(text)
        theme.manager().changed.connect(self.update)

    def sizeHint(self) -> QtCore.QSize:
        metrics = QtGui.QFontMetrics(theme.font(tokens.BODY))
        return QtCore.QSize(metrics.horizontalAdvance(self.text()) + 24, Metrics.PIVOT_HEIGHT)

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        colors = theme.palette()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        active = self.isChecked()
        ink = colors.text if active or self.underMouse() else colors.text_weak
        painter.setFont(theme.font(tokens.BODY))
        painter.setPen(theme.qcolor(ink))
        text_box = QtCore.QRectF(0, 0, self.width(), 26)
        painter.drawText(text_box, Qt.AlignmentFlag.AlignCenter, self.text())
        if active:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.qcolor(colors.text))
            painter.drawRoundedRect(QtCore.QRectF((self.width() - 16) / 2, 30, 16, 2), 1, 1)
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(theme.qcolor(colors.border_focus), 2.0))
            painter.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1), 4, 4)
        painter.end()

    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self.update()
        super().leaveEvent(event)


class ServerRow(QtWidgets.QAbstractButton):
    """Строка списка: «самый быстрый», страна (раскрывается), сервер, профиль или шлюз."""

    expand_toggled = Signal(str)

    def __init__(self, kind: str, title: str, target: str, parent: QtWidgets.QWidget | None = None,
                 *, code: str = "", meta: str = "", expandable: bool = False,
                 expanded: bool = False) -> None:
        super().__init__(parent)
        self.kind, self.title, self.target, self.code, self.meta = kind, title, target, code, meta
        self.expandable, self.expanded = expandable, expanded
        self.active = False
        self.active_state = ConnectionState.DISCONNECTED
        height = {"fastest": Metrics.ROW_FASTEST, "server": Metrics.ROW_SERVER}.get(
            kind, Metrics.ROW_COUNTRY)
        self.setFixedHeight(height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setMouseTracking(True)
        self._over_chevron = False
        self.setAccessibleName(title)
        self.setToolTip(f"Подключиться: {title}")
        theme.manager().changed.connect(self.update)

    def set_active(self, active: bool, state: ConnectionState) -> None:
        if (active, state) != (self.active, self.active_state):
            self.active, self.active_state = active, state
            self.update()

    # --- мышь и клавиатура -----------------------------------------------------------
    def _in_chevron(self, x: float) -> bool:
        return self.expandable and x >= self.width() - CHEVRON_ZONE

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        over = self._in_chevron(event.position().x())
        if over != self._over_chevron:
            self._over_chevron = over
            self.setToolTip("Показать серверы страны" if over else f"Подключиться: {self.title}")
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        inside = self.rect().contains(event.position().toPoint())
        if (event.button() == Qt.MouseButton.LeftButton and inside
                and self._in_chevron(event.position().x())):
            self.setDown(False)
            self.expand_toggled.emit(self.code)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
        elif self.expandable and key in (Qt.Key.Key_Right, Qt.Key.Key_Left):
            if (key == Qt.Key.Key_Right) != self.expanded:
                self.expand_toggled.emit(self.code)
        else:
            super().keyPressEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._over_chevron = False
        self.update()
        super().leaveEvent(event)

    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        self.update()
        super().enterEvent(event)

    # --- отрисовка -------------------------------------------------------------------
    def _draw_badge(self, painter: QtGui.QPainter, box: QtCore.QRectF) -> None:
        colors = theme.palette()
        ratio = self.devicePixelRatioF()
        if self.kind in ("country", "server") and self.code:
            flag = svg_loader.flag_pixmap(self.code, int(box.width()), int(box.height()), ratio)
            painter.drawPixmap(box.topLeft(), flag)
            return
        fastest = self.kind == "fastest"
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.qcolor(colors.success if fastest else colors.fill_hover))
        painter.drawRoundedRect(box, 4, 4)
        name = {"fastest": "BoltFilled", "profile": "WindowTerminal"}.get(self.kind, "Servers")
        ink = colors.text_invert if fastest else colors.text_weak
        painter.drawPixmap(QtCore.QPointF(box.center().x() - 8, box.center().y() - 8),
                           svg_loader.icon_pixmap(name, ink, 16, ratio))

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        colors = theme.palette()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        child = self.kind == "server"
        inset = 0 if self.kind == "fastest" else 2
        body = QtCore.QRectF(self.rect()).adjusted(0, inset, 0, -inset)
        painter.setPen(Qt.PenStyle.NoPen)
        if self.isDown():
            painter.setBrush(theme.qcolor(colors.fill_active))
            painter.drawRoundedRect(body, 4, 4)
        elif self.underMouse() or self.active:
            painter.setBrush(theme.qcolor(colors.fill_hover if self.underMouse() else colors.fill))
            painter.drawRoundedRect(body, 4, 4)
        flag_w, flag_h = Metrics.FLAG
        centre_y = self.height() / 2
        text_left = 13 + flag_w + 12  # серверы страны стоят под её названием, без флага
        if not child:
            self._draw_badge(painter, QtCore.QRectF(13, centre_y - flag_h / 2, flag_w, flag_h))
        right_edge = self.width() - 12
        if self.expandable:
            zone = QtCore.QRectF(self.width() - 28, centre_y - 10, 20, 20)
            if self._over_chevron:
                painter.setBrush(theme.qcolor(colors.fill_active))
                painter.drawRoundedRect(zone, 4, 4)
            name = "ChevronUpFilled" if self.expanded else "ChevronDownFilled"
            painter.drawPixmap(QtCore.QPointF(zone.left() + 2, zone.top() + 2),
                               svg_loader.icon_pixmap(name, colors.text_weak, 16,
                                                      self.devicePixelRatioF()))
            right_edge = zone.left() - 8
        if self.active and self.active_state is ConnectionState.CONNECTED and not self.expandable:
            painter.setBrush(theme.qcolor(colors.vpn_green))
            painter.drawEllipse(QtCore.QPointF(right_edge - 4, centre_y), 4, 4)
            right_edge -= 16
        if self.meta:
            painter.setFont(theme.font(tokens.CAPTION))
            painter.setPen(theme.qcolor(colors.text_hint))
            width = painter.fontMetrics().horizontalAdvance(self.meta)
            painter.drawText(QtCore.QRectF(right_edge - width, 0, width, self.height()),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.meta)
            right_edge -= width + 8
        font = theme.font(tokens.BODY if child else tokens.BODY_MEDIUM)
        painter.setFont(font)
        painter.setPen(theme.qcolor(colors.link if self.active else colors.text))
        room = max(0.0, right_edge - text_left)
        text = painter.fontMetrics().elidedText(self.title, Qt.TextElideMode.ElideRight, int(room))
        painter.drawText(QtCore.QRectF(text_left, 0, room, self.height()),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(theme.qcolor(colors.border_focus), 2.0))
            painter.drawRoundedRect(body.adjusted(1, 1, -1, -1), 4, 4)
        painter.end()


class SearchBox(QtWidgets.QFrame):
    """Поле поиска: лупа, строка ввода и подсказка сочетания клавиш справа."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SearchBox")
        self.setFixedHeight(Metrics.SEARCH_HEIGHT)
        self.edit = QtWidgets.QLineEdit(self)
        self.edit.setObjectName("SearchEdit")
        self.edit.setPlaceholderText("Поиск серверов…")
        self.edit.setClearButtonEnabled(False)
        self.edit.setAccessibleName("Поиск серверов")
        self.edit.installEventFilter(self)
        self.shortcut = QtWidgets.QLabel("ctrl + F", self)
        self.shortcut.setObjectName("SearchShortcut")
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(10)
        row.addWidget(IconLabel("Magnifier", 16, "text_hint", self))
        row.addWidget(self.edit, 1)
        row.addWidget(self.shortcut)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if watched is self.edit and event.type() in (QtCore.QEvent.Type.FocusIn,
                                                     QtCore.QEvent.Type.FocusOut):
            self.setProperty("focused", event.type() == QtCore.QEvent.Type.FocusIn)
            self.style().unpolish(self)
            self.style().polish(self)
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        self.edit.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)


class NoticeCard(QtWidgets.QFrame):
    """Карточка-сообщение над списком (остаток подписки, совет). Пустой текст её скрывает."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("NoticeCard")
        self.text = QtWidgets.QLabel(self)
        self.text.setObjectName("NoticeText")
        self.text.setWordWrap(True)
        self.text.setProperty("elide", True)  # длинный текст переносится, высота карточки растёт
        self.text.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,
                                QtWidgets.QSizePolicy.Policy.Preferred)
        bubble = QtWidgets.QFrame(self)
        bubble.setObjectName("NoticeBubble")
        bubble.setFixedSize(40, 40)
        inner = QtWidgets.QVBoxLayout(bubble)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.addWidget(IconLabel("Globe", 20, "link", bubble), 0, Qt.AlignmentFlag.AlignCenter)
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(16, 14, 16, 14)
        row.setSpacing(14)
        row.addWidget(bubble, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.text, 1)
        self.setMinimumHeight(72)
        self.hide()

    def set_text(self, text: str) -> None:
        self.text.setText(text)
        self.setVisible(bool(text))


class SidebarView(QtWidgets.QFrame):
    expand_requested = Signal()  # в свёрнутом виде нажали значок: окно раскрывает панель
    activated = Signal()  # выбран сервер: развёрнутую поверх окна панель можно свернуть

    def __init__(self, bridge: VpnUiBridge, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self.setObjectName("SidebarPane")
        self.group = GROUP_COUNTRIES
        self.filter = "all"
        self.expanded: set[str] = set()
        self.rows: list[ServerRow] = []
        self.compact = False

        self.pages = QtWidgets.QStackedLayout(self)
        self.pages.setContentsMargins(0, 0, 0, 0)
        self.pages.addWidget(self._build_expanded())
        self.pages.addWidget(self._build_compact())

        bridge.servers_changed.connect(lambda _servers: self.rebuild())
        bridge.connection_changed.connect(lambda _snapshot: self._mark_active())
        bridge.notice_changed.connect(self.notice.set_text)
        self.notice.set_text(bridge.notice)
        self.rebuild()

    # --- построение ------------------------------------------------------------------
    def _build_expanded(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(Metrics.PANE_PADDING, Metrics.PANE_PADDING, 0,
                                  Metrics.PANE_PADDING)
        column.setSpacing(0)

        self.search = SearchBox(page)
        self.search.edit.textChanged.connect(lambda _text: self.rebuild())
        holder = QtWidgets.QHBoxLayout()
        holder.setContentsMargins(4, 4, 4 + Metrics.PANE_PADDING, 4)
        holder.addWidget(self.search)
        column.addLayout(holder)
        column.addSpacing(12)

        self.nav_group = QtWidgets.QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, NavButton] = {}
        self.nav_rows: dict[str, QtWidgets.QWidget] = {}
        for key, title, icon, hotkey in SECTIONS:
            line = QtWidgets.QWidget(page)
            row = QtWidgets.QHBoxLayout(line)
            row.setContentsMargins(0, 0, LIST_GUTTER - 1, 0)
            row.setSpacing(0)
            button = NavButton(title, icon, line)
            button.clicked.connect(lambda _checked=False, k=key: self.set_group(k))
            hint = QtWidgets.QLabel(hotkey, line)
            hint.setObjectName("HotkeyLabel")
            row.addWidget(button)
            row.addStretch(1)
            row.addWidget(hint)
            self.nav_group.addButton(button)
            self.nav_buttons[key], self.nav_rows[key] = button, line
            column.addWidget(line)
        self.nav_buttons[self.group].setChecked(True)
        column.addSpacing(16)

        self.pivot = QtWidgets.QWidget(page)
        tabs = QtWidgets.QHBoxLayout(self.pivot)
        tabs.setContentsMargins(0, 0, 0, 0)
        tabs.setSpacing(0)
        self.pivot_group = QtWidgets.QButtonGroup(self)
        self.pivot_group.setExclusive(True)
        self.pivot_tabs: dict[str, PivotTab] = {}
        for key, title in FILTERS:
            tab = PivotTab(key, title, self.pivot)
            tab.clicked.connect(lambda _checked=False, k=key: self.set_filter(k))
            self.pivot_group.addButton(tab)
            self.pivot_tabs[key] = tab
            tabs.addWidget(tab)
        tabs.addStretch(1)
        self.pivot_tabs["all"].setChecked(True)
        column.addWidget(self.pivot)

        self.scroll = QtWidgets.QScrollArea(page)
        self.scroll.setObjectName("ServerScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().setAutoFillBackground(False)
        self.body = QtWidgets.QWidget()
        self.body.setObjectName("ServerList")
        self.items = QtWidgets.QVBoxLayout(self.body)
        self.items.setContentsMargins(0, 0, LIST_GUTTER, 0)
        self.items.setSpacing(1)
        self.scroll.setWidget(self.body)
        bar = self.scroll.verticalScrollBar()
        bar.rangeChanged.connect(lambda low, high: self.items.setContentsMargins(
            0, 0, LIST_GUTTER - (SCROLLBAR if high > low else 0), 0))
        self.notice = NoticeCard(self.body)
        self.header_line = QtWidgets.QWidget(self.body)
        self.header = QtWidgets.QLabel(self.header_line)
        self.header.setObjectName("ListHeader")
        header_row = QtWidgets.QHBoxLayout(self.header_line)
        header_row.setContentsMargins(12, 0, 0, 8)
        header_row.addWidget(self.header)
        self.empty = QtWidgets.QLabel("Ничего не найдено", self.body)
        self.empty.setObjectName("EmptyLabel")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        column.addWidget(self.scroll, 1)
        return page

    def _build_compact(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget(self)
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(4 + Metrics.PANE_PADDING, 4 + Metrics.PANE_PADDING,
                                  4 + Metrics.PANE_PADDING, 4)
        column.setSpacing(18)
        self.compact_buttons: list[QtWidgets.QToolButton] = []
        entries = [("Magnifier", "Поиск серверов", None)]
        entries += [(icon, title, key) for key, title, icon, _hotkey in SECTIONS]
        for icon, title, key in entries:
            button = QtWidgets.QToolButton(page)
            button.setObjectName("CompactSearch" if key is None else "CompactNav")
            button.setFixedSize(36, 36 if key is None else 24)
            button.setIconSize(QtCore.QSize(16, 16))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(title)
            button.setAccessibleName(title)
            button.setProperty("icon_name", icon)
            button.setProperty("section", key or "")
            button.clicked.connect(lambda _checked=False, k=key: self._compact_clicked(k))
            self.compact_buttons.append(button)
            column.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addStretch(1)
        theme.manager().changed.connect(self._retint_compact)
        self._retint_compact()
        return page

    def _retint_compact(self) -> None:
        colors = theme.palette()
        for button in self.compact_buttons:
            ink = colors.text_hint if button.objectName() == "CompactSearch" else colors.text_weak
            button.setIcon(svg_loader.load_svg_icon(button.property("icon_name"), ink.hex,
                                                    QtCore.QSize(16, 16)))

    def _compact_clicked(self, key: str | None) -> None:
        if key is not None:
            self.set_group(key)
        self.expand_requested.emit()
        if key is None:
            QtCore.QTimer.singleShot(0, self.focus_search)

    # --- управление ------------------------------------------------------------------
    def set_compact(self, compact: bool) -> None:
        self.compact = compact
        self.pages.setCurrentIndex(1 if compact else 0)

    def focus_search(self) -> None:
        self.search.edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search.edit.selectAll()

    def set_group(self, group: str) -> None:
        if group not in self.nav_buttons or not self.nav_rows[group].isVisibleTo(self):
            group = GROUP_COUNTRIES
        self.group = group
        self.nav_buttons[group].setChecked(True)
        self.rebuild()

    def set_filter(self, key: str) -> None:
        self.filter = key
        self.pivot_tabs[key].setChecked(True)
        self.rebuild()

    def _toggle_country(self, code: str) -> None:
        self.expanded.symmetric_difference_update({code})
        self.rebuild()

    def _choose(self, target: str) -> None:
        self.bridge.request_connect(target)
        self.activated.emit()

    # --- список ----------------------------------------------------------------------
    def _matching(self) -> list[ServerNode]:
        nodes = [node for node in self.bridge.servers if node.group == self.group]
        if self.group == GROUP_COUNTRIES and self.filter != "all":
            nodes = [node for node in nodes if self.filter in node.features]
        query = self.search.edit.text().strip().casefold()
        if query:
            nodes = [node for node in nodes
                     if query in f"{node.name} {node.country_name} {node.city}".casefold()]
        return nodes

    def _add_row(self, row: ServerRow) -> None:
        row.clicked.connect(lambda _checked=False, target=row.target: self._choose(target))
        row.expand_toggled.connect(self._toggle_country)
        self.rows.append(row)
        self.items.addWidget(row)

    @staticmethod
    def _meta(node: ServerNode) -> str:
        return f"{node.ping_ms} мс" if node.ping_ms is not None else ""

    def rebuild(self) -> None:
        """Перестроить список под раздел, фильтр и строку поиска."""
        gateways = any(node.group == GROUP_GATEWAYS for node in self.bridge.servers)
        self.nav_rows[GROUP_GATEWAYS].setVisible(gateways)
        if self.group == GROUP_GATEWAYS and not gateways:
            self.group = GROUP_COUNTRIES
            self.nav_buttons[self.group].setChecked(True)
        self.pivot.setVisible(self.group == GROUP_COUNTRIES)
        focused = next((row.target for row in self.rows if row.hasFocus()), None)
        while self.items.count():
            item = self.items.takeAt(0)
            widget = item.widget()
            if isinstance(widget, ServerRow):
                widget.deleteLater()
            elif widget is not None:
                widget.hide()  # постоянные части списка вернутся ниже
        self.rows = []
        nodes = self._matching()
        searching = bool(self.search.edit.text().strip())
        self.items.addSpacing(10)
        self.items.addWidget(self.notice)
        self.notice.setVisible(bool(self.notice.text.text()))
        self.items.addSpacing(12)
        self.items.addWidget(self.header_line)
        self.header_line.show()
        if self.group == GROUP_COUNTRIES:
            countries: dict[str, list[ServerNode]] = {}
            for node in nodes:
                countries.setdefault(node.country_code or "??", []).append(node)
            self.header.setText(f"Страны ({len(countries)})")
            if nodes and not searching and self.filter == "all":
                self._add_row(ServerRow("fastest", "Самый быстрый сервер", AUTO_ID, self.body))
            ordered = sorted(countries.items(), key=lambda pair: pair[1][0].country_name.casefold())
            for code, members in ordered:
                leader = best_node(members) or members[0]
                opened = code in self.expanded or searching
                self._add_row(ServerRow("country", leader.country_name or code, leader.id,
                                        self.body, code=code, expandable=True, expanded=opened))
                if opened:
                    for node in sorted(members, key=lambda item: item.name.casefold()):
                        title = " · ".join(part for part in (node.city, node.name) if part)
                        self._add_row(ServerRow("server", title, node.id, self.body, code=code,
                                                meta=self._meta(node)))
        else:
            self.header.setText(f"{HEADERS[self.group]} ({len(nodes)})")
            kind = "profile" if self.group == GROUP_PROFILES else "gateway"
            for node in sorted(nodes, key=lambda item: item.name.casefold()):
                self._add_row(ServerRow(kind, node.name, node.id, self.body,
                                        meta=self._meta(node)))
        self.items.addWidget(self.empty)
        self.empty.setVisible(not nodes)
        self.items.addStretch(1)
        self._mark_active()
        if focused is not None:
            for row in self.rows:
                if row.target == focused:
                    row.setFocus(Qt.FocusReason.OtherFocusReason)
                    break

    def _mark_active(self) -> None:
        snapshot = self.bridge.connection
        live = snapshot.state is not ConnectionState.DISCONNECTED
        current = self.bridge.node(snapshot.server_id)
        for row in self.rows:
            if row.kind == "fastest":
                active = live and snapshot.server_id == AUTO_ID
            elif row.kind == "country":
                active = live and current is not None and current.country_code == row.code \
                    and current.group == GROUP_COUNTRIES
            else:
                active = live and row.target == snapshot.server_id
            row.set_active(active, snapshot.state)
