"""Подписки над серверами. Просмотр и выбор маршрута — разные действия."""
from __future__ import annotations

from functools import lru_cache

from xgw.gui import model

from .. import theme
from ..qt import Qt, QtCore, QtGui, QtWidgets, Signal
from ..theme import svg_loader
from ..theme.tokens import Metrics
from ..views.sidebar_view import SearchBox
from .catalog import POOL, filtered


@lru_cache(maxsize=256)
def country_name(code: str) -> str:
    # Qt возвращает английские имена; распространённые страны интерфейса переводим.
    localized = {
        "AT": "Австрия", "AU": "Австралия", "BE": "Бельгия", "CA": "Канада",
        "CH": "Швейцария", "CZ": "Чехия", "DE": "Германия", "DK": "Дания",
        "EE": "Эстония", "ES": "Испания", "FI": "Финляндия", "FR": "Франция",
        "GB": "Великобритания", "HK": "Гонконг", "IE": "Ирландия", "IL": "Израиль",
        "IN": "Индия", "IT": "Италия", "JP": "Япония", "KR": "Южная Корея",
        "KZ": "Казахстан", "LT": "Литва", "LV": "Латвия", "NL": "Нидерланды",
        "NO": "Норвегия", "PL": "Польша", "RU": "Россия", "SE": "Швеция",
        "SG": "Сингапур", "TR": "Турция", "UA": "Украина", "US": "США",
    }
    if code in localized:
        return localized[code]
    territory = QtCore.QLocale.codeToTerritory(code)
    if territory.value == 0:
        return code or "Страна неизвестна"
    return QtCore.QLocale.territoryToString(territory)


class ServerDetails(QtWidgets.QFrame):
    """Карточка над картой, привязанная к строке списка."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("ServerDetails")
        self.setAccessibleName("Сведения о сервере")
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(6)
        self.title = self._label("ServerDetailsTitle")
        self.metrics = self._label("ServerDetailsMetrics")
        self.body = self._label("ServerDetailsBody")
        for label in (self.title, self.metrics, self.body):
            box.addWidget(label)
        self.slide = QtCore.QPropertyAnimation(self, b"pos", self)
        self.slide.setDuration(130)
        self.slide.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self.hide()
        theme.manager().changed.connect(self.retint)
        self.retint()

    def _label(self, name):
        label = QtWidgets.QLabel(self)
        label.setObjectName(name)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        return label

    def retint(self):
        c = theme.palette()
        self.setStyleSheet(f"""
            QFrame#ServerDetails {{ background: {c.bg_norm.qss};
                border: 1px solid {c.border_norm.qss}; border-radius: {Metrics.PANE_RADIUS}px; }}
            QFrame#ServerDetails QLabel {{ color: {c.text.qss}; background: transparent; }}
            QLabel#ServerDetailsTitle {{ font-weight: 600; }}
            QLabel#ServerDetailsMetrics {{ color: {c.text_weak.qss}; }}
        """)

    def place(self, item, anchor, animate):
        bounds = self.parentWidget().rect().adjusted(8, 38, -8, -8)
        left, right = anchor.left() - bounds.left(), bounds.right() - anchor.right()
        room = right if right >= 230 or right >= left else left
        width = min(340, max(180, room - 8))
        self.setFixedWidth(width)
        self.title.setText(item.name)
        self.metrics.setText(f"{country_name(item.country)} · {model.mbps_text(item.speed)} · "
                             f"Рейтинг {rating_text(item.rating)}")
        self.body.setText(item.detail)
        # QLabel с переносом рассчитывает высоту по реальной ширине, а не sizeHint.
        padding = self.layout().contentsMargins()
        text_width = width - padding.left() - padding.right() - 2
        for label in (self.title, self.metrics, self.body):
            label.setMinimumHeight(label.heightForWidth(text_width))
        self.layout().activate()
        self.resize(width, self.layout().totalMinimumSize().height())
        x = anchor.right() + 8 if room == right else anchor.left() - width - 8
        x = max(bounds.left(), min(x, bounds.right() - width + 1))
        y = max(bounds.top(), min(anchor.top(), bounds.bottom() - self.height() + 1))
        target = QtCore.QPoint(x, y)
        self.slide.stop()
        if animate:
            self.move(max(bounds.left(), x - 10), y)
        else:
            self.move(target)
        self.show()
        self.raise_()
        if animate:
            self.slide.setStartValue(self.pos())
            self.slide.setEndValue(target)
            self.slide.start()


def rating_text(value):
    return "—" if value is None else f"{value:.2f}".replace(".", ",")


class Sidebar(QtWidgets.QFrame):
    expand_requested = Signal()
    activated = Signal()

    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.compact = False
        self._key = None
        self._source = ""
        self._preview = ""
        self._details_locked = False
        self._rows = {}
        self._sort_column = 0
        self._descending = False
        self.info = ServerDetails(parent)
        self.info.installEventFilter(self)
        self.hover_timer = QtCore.QTimer(self, singleShot=True, interval=160)
        self.hover_timer.timeout.connect(self._open_hover)
        self.leave_timer = QtCore.QTimer(self, singleShot=True, interval=160)
        self.leave_timer.timeout.connect(self._close_hover)
        self._hovered = ""
        self.setObjectName("SidebarPane")
        self.stack = QtWidgets.QStackedLayout(self)
        self.stack.setContentsMargins(0, 0, 0, 0)
        page = QtWidgets.QWidget()
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(12, 12, 12, 12)
        column.setSpacing(8)
        self.search = SearchBox(page)
        self.search.edit.setPlaceholderText("Найти сервер…")
        self.search.edit.textChanged.connect(self.render)
        column.addWidget(self.search)
        head = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Подписки")
        title.setObjectName("ListHeader")
        head.addWidget(title)
        head.addStretch()
        manage = QtWidgets.QPushButton("Изменить")
        manage.setAccessibleName("Изменить подписки")
        manage.clicked.connect(lambda: bridge.section_requested.emit("subscriptions"))
        head.addWidget(manage)
        column.addLayout(head)
        self.sources = QtWidgets.QListWidget()
        self.sources.setAccessibleName("Подписки и источники серверов")
        self.sources.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.sources.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.sources.currentItemChanged.connect(self.source_changed)
        column.addWidget(self.sources)
        self.source_note = QtWidgets.QLabel()
        self.source_note.setObjectName("GatewayCaption")
        self.source_note.setWordWrap(True)
        self.source_note.setTextFormat(Qt.TextFormat.PlainText)
        column.addWidget(self.source_note)
        self.filter = QtWidgets.QTabBar()
        self.filter.setObjectName("ServerFilter")
        self.filter.setDrawBase(False)
        self.filter.setExpanding(False)
        for title, value in (("Все", "all"), ("Доступные", "usable"), ("Выбранные", "chosen")):
            self.filter.setTabData(self.filter.addTab(title), value)
        self.filter.setAccessibleName("Состояние серверов")
        self.filter.currentChanged.connect(self.render)
        column.addWidget(self.filter)
        self.servers = QtWidgets.QTreeWidget()
        self.servers.setHeaderLabels(["Серверы", "Мбит/с", "Рейтинг"])
        self.servers.setRootIsDecorated(False)
        self.servers.setColumnCount(3)
        self.servers.header().setSectionsClickable(True)
        self.servers.header().setSectionsMovable(False)
        self.servers.header().setSortIndicatorShown(False)
        self.servers.header().setIconSize(QtCore.QSize(12, 12))
        self.servers.header().sectionClicked.connect(self.sort_by_column)
        self.servers.header().setMinimumSectionSize(55)
        self.servers.header().setStretchLastSection(False)
        self.servers.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.servers.header().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.servers.header().setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.servers.setAllColumnsShowFocus(True)
        self.servers.setUniformRowHeights(True)
        self.servers.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.servers.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.servers.setMouseTracking(True)
        self._server_viewport = self.servers.viewport()
        self._server_viewport.installEventFilter(self)
        self.servers.setAccessibleName("Серверы выбранной подписки")
        self.servers.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.servers.itemClicked.connect(self.details)
        self.servers.itemActivated.connect(self.details)
        self.servers.itemEntered.connect(self._row_entered)
        self.servers.currentItemChanged.connect(self.controls)
        self.servers.verticalScrollBar().valueChanged.connect(self._scroll_changed)
        column.addWidget(self.servers, 1)
        self.empty = QtWidgets.QLabel()
        self.empty.setWordWrap(True)
        column.addWidget(self.empty)
        self.choose = QtWidgets.QPushButton("Выбрать сервер")
        self.choose.clicked.connect(self.choose_current)
        self.auto = QtWidgets.QPushButton("Автовыбор XGW")
        self.auto.setToolTip("Вернуть выбор серверов демону. "
                             "Фильтр подписки не ограничивает автовыбор.")
        self.auto.clicked.connect(lambda: bridge.automatic(self._source))
        actions = QtWidgets.QHBoxLayout()
        actions.addWidget(self.choose)
        actions.addWidget(self.auto)
        column.addLayout(actions)
        self.stack.addWidget(page)
        compact = QtWidgets.QWidget()
        buttons = QtWidgets.QVBoxLayout(compact)
        show = QtWidgets.QPushButton("☰")
        show.setAccessibleName("Показать подписки и серверы")
        show.clicked.connect(self.expand_requested)
        buttons.addWidget(show)
        buttons.addStretch(1)
        self.stack.addWidget(compact)
        bridge.gateway_changed.connect(self.render)
        theme.manager().changed.connect(self.retint)
        self.retint()
        self.render()

    def set_compact(self, compact):
        if compact and not self.compact:
            self.hide_details()
        self.compact = compact
        self.stack.setCurrentIndex(1 if compact else 0)
        overlay = not compact and self.window().width() < Metrics.SIDEBAR_BREAK
        if self.property("overlay") != overlay:
            self.setProperty("overlay", overlay)
            self.style().unpolish(self)
            self.style().polish(self)

    def retint(self):
        c = theme.palette()
        self.setStyleSheet(f"""
            QFrame#SidebarPane {{ background: {c.pane.qss};
                border: 1px solid {c.border_weak.qss}; border-radius: {Metrics.PANE_RADIUS}px; }}
            QFrame#SidebarPane[overlay="true"] {{ background: {c.bg_norm.qss}; }}
            QTabBar#ServerFilter::tab {{ background: transparent; color: {c.text_weak.qss};
                padding: 6px 7px; border-bottom: 2px solid transparent; }}
            QTabBar#ServerFilter::tab:selected {{ color: {c.text.qss};
                border-color: {c.text.qss}; }}
            QTabBar#ServerFilter::tab:hover {{ background: {c.fill_hover.qss}; }}
            QTabBar#ServerFilter:focus {{ border: 1px solid {c.border_focus.qss}; }}
            QFrame#SidebarPane QTreeWidget::item {{ padding: 3px 4px; }}
            QFrame#SidebarPane QTreeWidget::item:hover {{ background: {c.fill_hover.qss}; }}
            QFrame#SidebarPane QTreeWidget::item:selected {{ background: {c.fill_selected.qss}; }}
            QFrame#SidebarPane QHeaderView::section {{ background: {c.bg_weak.qss};
                color: {c.text_weak.qss}; border: none; padding: 6px 3px; font-size: 12px; }}
            QFrame#SidebarPane QHeaderView::section:hover {{ background: {c.bg_weak_hover.qss}; }}
        """)
        self.size_metric_columns()
        self.update_headings(self.servers.topLevelItemCount())

    def size_metric_columns(self):
        header = self.servers.header()
        font = QtGui.QFont(header.font())
        font.setPixelSize(12)
        labels = QtGui.QFontMetrics(font)
        value_width = self.servers.fontMetrics().horizontalAdvance("999999,99") + 8
        # Reserve the same space for the sort icon in both states.
        for column, title in enumerate(("Мбит/с", "Рейтинг"), start=1):
            header.resizeSection(column, max(value_width, labels.horizontalAdvance(title) + 32))

    def update_headings(self, count):
        palette = theme.palette()
        key = (count, self._sort_column, self._descending, palette.name)
        if key == getattr(self, "_heading_key", None):
            return
        self._heading_key = key
        header = self.servers.headerItem()
        icon_name = "ChevronDownFilled" if self._descending else "ChevronUpFilled"
        direction = "По убыванию" if self._descending else "По возрастанию"
        marker = QtGui.QIcon(svg_loader.icon_pixmap(icon_name, palette.text, 12))
        for column, title in enumerate((f"Серверы ({count})", "Мбит/с", "Рейтинг")):
            active = column == self._sort_column
            header.setText(column, title)
            header.setIcon(column, marker if active else QtGui.QIcon())
            header.setToolTip(column, f"{title} · {direction}" if active else title)

    def sort_by_column(self, column):
        if column not in (0, 1, 2):
            return
        self._descending = not self._descending if column == self._sort_column else column != 0
        self._sort_column = column
        self.render()

    def focus_search(self):
        self.search.edit.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def source_changed(self, current, _previous=None):
        self.hide_details()
        self._source = current.data(Qt.ItemDataRole.UserRole) if current else ""
        self.bridge.pool_visible = self._source == POOL
        self.search.edit.clear()
        self.render()
        if self.bridge.pool_visible:
            self.bridge.fetch_pool()

    def current_entry(self):
        return self._entry(self._id(self.servers.currentItem()))

    @staticmethod
    def _id(row):
        return row.data(0, Qt.ItemDataRole.UserRole) if row else ""

    def _entry(self, identifier):
        return next((item for item in self.bridge.entries if item.id == identifier), None)

    def controls(self, *_args):
        item = self.current_entry()
        self.choose.setEnabled(bool(item and item.choosable and self.bridge.can_select))
        self.auto.setEnabled(self.bridge.can_select)

    def choose_current(self):
        item = self.current_entry()
        if item:
            self.select(item)

    def select(self, item):
        if not item.choosable or not self.bridge.can_select:
            return
        box = QtWidgets.QMessageBox(self)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setWindowTitle("Выбрать сервер")
        source = next((source.name for source in self.bridge.sources if source.id == item.source),
                      "")
        action = ("Выбрать сервер бесплатного пула для его текущей области трафика?"
                  if item.pool else "Закрепить этот сервер в шлюзе?")
        details = (item.name, source, country_name(item.country), action)
        box.setText("\n".join(filter(None, details)))
        accept = box.addButton("Выбрать", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton("Отмена", QtWidgets.QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        c = theme.palette()
        box.setStyleSheet(f"QMessageBox {{ background: {c.bg_norm.qss}; }}")
        box.exec()
        if box.clickedButton() is accept:
            self.bridge.select(item.id)

    def details(self, row=None, _column=0):
        self._details_locked = True
        self._show_details(self._id(row or self.servers.currentItem()))

    def hide_details(self):
        visible = self.info.isVisible()
        self.hover_timer.stop()
        self.leave_timer.stop()
        self.info.slide.stop()
        self.info.hide()
        self._preview = self._hovered = ""
        self._details_locked = False
        return visible

    def eventFilter(self, watched, event):
        kind = event.type()
        if watched is self.info and kind == QtCore.QEvent.Type.Hide:
            self._preview = ""
        if watched is self.info or watched is getattr(self, "_server_viewport", None):
            if kind == QtCore.QEvent.Type.Leave:
                self.hover_timer.stop()
                self.leave_timer.start()
            elif kind == QtCore.QEvent.Type.Enter:
                self.leave_timer.stop()
            elif (kind == QtCore.QEvent.Type.MouseMove and watched is not self.info
                  and self.servers.itemAt(event.position().toPoint()) is None):
                self.hover_timer.stop()
                if not self.leave_timer.isActive():
                    self.leave_timer.start()
        return super().eventFilter(watched, event)

    def _row_entered(self, row, _column):
        identifier = self._id(row)
        self.leave_timer.stop()
        if identifier != self._preview or not self.info.isVisible():
            self._details_locked = False
            self._hovered = identifier
            self.hover_timer.start()

    def _open_hover(self):
        point = self.servers.viewport().mapFromGlobal(QtGui.QCursor.pos())
        row = self.servers.itemAt(point)
        if self._id(row) == self._hovered:
            self._show_details(self._hovered)

    def _close_hover(self):
        if not self._details_locked:
            self.hide_details()

    def _scroll_changed(self):
        if not self.servers.signalsBlocked():
            self.hide_details()

    def _show_details(self, identifier, *, animate=True):
        item, row = self._entry(identifier), self._rows.get(identifier)
        if not self.isVisible() or self.compact or item is None or row is None:
            self.hide_details()
            return
        cell = self.servers.visualItemRect(row)
        if not cell.intersects(self.servers.viewport().rect()):
            self.hide_details()
            return
        host = self.info.parentWidget()
        origin = self.mapTo(host, QtCore.QPoint(0, 0))
        y = self.servers.viewport().mapTo(host, cell.topLeft()).y()
        anchor = QtCore.QRect(origin.x(), y, self.width(), cell.height())
        self._preview = identifier
        self.info.place(item, anchor, animate)

    def _update_servers(self, entries):
        current = self._id(self.servers.currentItem())
        first = self.servers.itemAt(1, 1)
        anchor = self._id(first)
        y = self.servers.visualItemRect(first).top() if first else 0
        scroll = self.servers.verticalScrollBar()
        self.servers.blockSignals(True)
        rows = self._rows
        ids = {item.id for item in entries}
        for identifier in rows.keys() - ids:
            row = rows.pop(identifier)
            self.servers.takeTopLevelItem(self.servers.indexOfTopLevelItem(row))
        for index, item in enumerate(entries):
            row = rows.get(item.id)
            if row is None:
                row = rows[item.id] = QtWidgets.QTreeWidgetItem()
                row.setData(0, Qt.ItemDataRole.UserRole, item.id)
                row.setSizeHint(0, QtCore.QSize(0, 48))
                row.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                row.setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.servers.insertTopLevelItem(index, row)
            elif self.servers.indexOfTopLevelItem(row) != index:
                self.servers.takeTopLevelItem(self.servers.indexOfTopLevelItem(row))
                self.servers.insertTopLevelItem(index, row)
            row.setText(0, f"{item.name}\n{country_name(item.country)}")
            row.setToolTip(0, f"{item.name}\nСтрана по IP: {country_name(item.country)}")
            speed = model.mbps_text(item.speed).removesuffix(" Мбит/с")
            row.setText(1, speed)
            row.setText(2, rating_text(item.rating))
            row.setData(0, Qt.ItemDataRole.AccessibleTextRole,
                        f"{item.name}, {country_name(item.country)}")
            row.setData(1, Qt.ItemDataRole.AccessibleTextRole,
                        f"Скорость {model.mbps_text(item.speed)}")
            row.setData(2, Qt.ItemDataRole.AccessibleTextRole,
                        f"Рейтинг {rating_text(item.rating)}")
            active = item.chosen or item.active
            font = row.font(0)
            font.setWeight(QtGui.QFont.Weight.DemiBold if active else QtGui.QFont.Weight.Normal)
            row.setFont(0, font)
            row.setIcon(0, QtGui.QIcon(svg_loader.flag_pixmap(item.country, 24, 16)))
        if self._id(self.servers.currentItem()) != current:
            self.servers.setCurrentItem(rows.get(current))
        if anchor in rows:
            self.servers.doItemsLayout()
            scroll.setValue(scroll.value() + self.servers.visualItemRect(rows[anchor]).top() - y)
        self.servers.blockSignals(False)

    def render(self, *_args):
        sources = self.bridge.sources
        # Не пересоздавать строки при каждом опросе: сохраняются прокрутка, выбор и фокус.
        source_key = tuple(sources)
        if source_key != getattr(self, "_sources_key", None):
            self._sources_key = source_key
            self.sources.blockSignals(True)
            self.sources.clear()
            for source in sources:
                row = QtWidgets.QListWidgetItem(source.name)
                row.setToolTip(source.name + "\n" + source.detail)
                row.setData(Qt.ItemDataRole.UserRole, source.id)
                self.sources.addItem(row)
                if source.id == self._source:
                    self.sources.setCurrentItem(row)
            height = max(24, self.sources.sizeHintForRow(0))
            self.sources.setFixedHeight(height * max(1, min(3, len(sources))) + 4)
            if self.sources.currentRow() < 0 and sources:
                self.sources.setCurrentRow(0)
            current = self.sources.currentItem()
            self._source = current.data(Qt.ItemDataRole.UserRole) if current else ""
            self.bridge.pool_visible = self._source == POOL
            self.sources.blockSignals(False)
        source = next((item for item in sources if item.id == self._source), None)
        self.source_note.setText(source.detail if source else
                                 "Добавьте подписку или ссылку сервера")
        order = ("name", "speed", "rating")[self._sort_column]
        pool_source = self._source == POOL
        self.filter.setTabText(1, "Допущенные" if pool_source else "Доступные")
        self.filter.setTabData(1, "admitted" if pool_source else "usable")
        self.filter.setTabToolTip(1, "Допуск по правилам пула. Ручной выбор зависит от режима."
                                  if pool_source else "Можно выбрать или уже выбраны")
        entries = filtered(self.bridge.entries, self._source, self.search.edit.text(),
                           self.filter.tabData(self.filter.currentIndex()), order,
                           country_name=country_name, descending=self._descending)
        self.update_headings(len(entries))
        key = tuple(entries)
        if key != self._key:
            self._key = key
            self._update_servers(entries)
            if self._preview:
                self._show_details(self._preview, animate=False)
        self.empty.setText(self.bridge.pool_error or
            ("Загрузка бесплатного пула…" if self._source == POOL and self.bridge.pool is None
             else "По выбранному фильтру серверов нет"))
        self.empty.setVisible(not entries)
        self.controls()
