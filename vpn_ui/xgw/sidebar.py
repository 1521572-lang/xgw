"""Подписки над серверами. Просмотр и выбор маршрута — разные действия."""
from __future__ import annotations

from ..qt import Qt, QtWidgets, Signal
from ..views.sidebar_view import SearchBox
from .catalog import POOL, filtered


class Sidebar(QtWidgets.QFrame):
    expand_requested = Signal()
    activated = Signal()

    def __init__(self, bridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.compact = False
        self._key = None
        self._source = ""
        self.info = None
        self.setObjectName("SidebarPane")
        self.stack = QtWidgets.QStackedLayout(self)
        self.stack.setContentsMargins(0, 0, 0, 0)
        page = QtWidgets.QWidget()
        column = QtWidgets.QVBoxLayout(page)
        column.setContentsMargins(12, 12, 12, 12)
        head = QtWidgets.QHBoxLayout()
        head.addWidget(QtWidgets.QLabel("Подписки"))
        manage = QtWidgets.QPushButton("Изменить")
        manage.clicked.connect(lambda: bridge.section_requested.emit("subscriptions"))
        head.addWidget(manage)
        column.addLayout(head)
        self.sources = QtWidgets.QListWidget()
        self.sources.setAccessibleName("Подписки и источники серверов")
        self.sources.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.sources.setMaximumHeight(155)
        self.sources.setMinimumHeight(85)
        self.sources.currentItemChanged.connect(self.source_changed)
        column.addWidget(self.sources)
        self.source_note = QtWidgets.QLabel()
        self.source_note.setWordWrap(True)
        self.source_note.setTextFormat(Qt.TextFormat.PlainText)
        column.addWidget(self.source_note)
        self.search = SearchBox(page)
        self.search.edit.setPlaceholderText("Найти сервер в подписке")
        self.search.edit.textChanged.connect(self.render)
        column.addWidget(self.search)
        options = QtWidgets.QHBoxLayout()
        self.filter = QtWidgets.QComboBox()
        for title, value in (("Все", "all"), ("Доступны к выбору", "usable"),
                             ("Выбран вручную", "chosen")):
            self.filter.addItem(title, value)
        self.sort = QtWidgets.QComboBox()
        for title, value in (("По имени", "name"), ("По скорости", "speed"),
                             ("По задержке", "delay")):
            self.sort.addItem(title, value)
        self.filter.setAccessibleName("Состояние серверов")
        self.sort.setAccessibleName("Порядок серверов")
        self.filter.currentIndexChanged.connect(self.render)
        self.sort.currentIndexChanged.connect(self.render)
        options.addWidget(self.filter)
        options.addWidget(self.sort)
        column.addLayout(options)
        self.header = QtWidgets.QLabel("Серверы")
        column.addWidget(self.header)
        self.servers = QtWidgets.QTreeWidget()
        self.servers.setHeaderHidden(True)
        self.servers.setRootIsDecorated(False)
        self.servers.setColumnCount(1)
        self.servers.setAccessibleName("Серверы выбранной подписки")
        self.servers.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.servers.itemClicked.connect(self.details)
        self.servers.itemActivated.connect(self.details)
        self.servers.currentItemChanged.connect(self.controls)
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
        column.addWidget(self.choose)
        column.addWidget(self.auto)
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
        self.render()

    def set_compact(self, compact):
        self.compact = compact
        self.stack.setCurrentIndex(1 if compact else 0)

    def focus_search(self):
        self.search.edit.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def source_changed(self, current, _previous=None):
        self._source = current.data(Qt.ItemDataRole.UserRole) if current else ""
        self.bridge.pool_visible = self._source == POOL
        self.search.edit.clear()
        self.render()
        if self.bridge.pool_visible:
            self.bridge.fetch_pool()

    def current_entry(self):
        row = self.servers.currentItem()
        identifier = row.data(0, Qt.ItemDataRole.UserRole) if row else ""
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
        if item.pool:
            from xgw.gui.pages import confirm
            if not confirm(self, "Выбрать бесплатный сервер?",
                           "Будет изменён сервер бесплатного пула для его текущей области трафика.",
                           "Выбрать"):
                return
        self.bridge.select(item.id)

    def details(self, _row=None, _column=0):
        item = self.current_entry()
        if item is None:
            return
        if self.info is not None:
            self.info.close()
            self.info.deleteLater()
        dialog = self.info = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Сведения о сервере")
        dialog.resize(450, 300)
        layout = QtWidgets.QVBoxLayout(dialog)
        for text in (item.name, item.detail):
            label = QtWidgets.QLabel(text)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(label)
        layout.addWidget(QtWidgets.QLabel("Снимок данных. Выбор маршрута — отдельной кнопкой."))
        manage = QtWidgets.QPushButton("Управление сервером")
        manage.clicked.connect(lambda: self.bridge.section_requested.emit("servers"))
        layout.addWidget(manage)
        close = QtWidgets.QPushButton("Закрыть")
        close.clicked.connect(dialog.close)
        layout.addWidget(close)
        dialog.show()

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
            if self.sources.currentRow() < 0 and sources:
                self.sources.setCurrentRow(0)
            current = self.sources.currentItem()
            self._source = current.data(Qt.ItemDataRole.UserRole) if current else ""
            self.bridge.pool_visible = self._source == POOL
            self.sources.blockSignals(False)
        source = next((item for item in sources if item.id == self._source), None)
        self.source_note.setText(source.detail if source else
                                 "Добавьте подписку или ссылку сервера")
        entries = filtered(self.bridge.entries, self._source, self.search.edit.text(),
                           self.filter.currentData(), self.sort.currentData())
        self.header.setText(f"Серверы ({len(entries)})")
        key = tuple(entries)
        if key != self._key:
            self._key = key
            current = self.current_entry()
            scroll = self.servers.verticalScrollBar().value()
            self.servers.blockSignals(True)
            self.servers.clear()
            for item in entries:
                from xgw.gui import model

                status = item.detail.splitlines()[0] if item.detail else "Нет данных состояния"
                metrics = (f"{model.mbps_text(item.speed)} · {model.ms_text(item.delay)}"
                           if item.speed is not None or item.delay is not None
                           else "Замер: нет данных")
                row = QtWidgets.QTreeWidgetItem([f"{item.name}\n{status}\n{metrics}"])
                row.setData(0, Qt.ItemDataRole.UserRole, item.id)
                row.setToolTip(0, item.name + "\n" + item.detail)
                self.servers.addTopLevelItem(row)
                if current and current.id == item.id:
                    self.servers.setCurrentItem(row)
            self.servers.verticalScrollBar().setValue(scroll)
            self.servers.blockSignals(False)
        self.empty.setText(self.bridge.pool_error or
            ("Загрузка бесплатного пула…" if self._source == POOL and self.bridge.pool is None
             else "По выбранному фильтру серверов нет"))
        self.empty.setVisible(not entries)
        self.controls()
