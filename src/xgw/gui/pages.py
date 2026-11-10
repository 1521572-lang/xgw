"""Разделы окна XGW «Серверы» и «Подписки» (этап 3, docs/GUI-NATIVE.md).

«Серверы»: вкладки «Подписки» и «Бесплатный пул». Серверы подписок — карточками по подпискам,
у каждой: замер скорости, «Выбрать» и меню «…» (ядро, приоритет, отключить, убрать).
Сверху — выбор сервера: основной сервер, «Автовыбор», замер, проверка запасных, обновление.
Бесплатный пул — сводка, режим (наблюдение, весь дом), серверы по источникам с «Выбрать».
«Подписки»: добавить адрес подписки или ссылки серверов, подписки с квотой, изменить, убрать.

Всё — через действия панели (Panel.act), как у браузерной страницы. Карточки
переиспользуются: опрос раз в 3 с меняет тексты, а не пересоздаёт виджеты.
"""

from __future__ import annotations

import contextlib

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import listing, model, theme
from .widgets import Badge, Elided, Switch, icon, label, server_details, set_text, tip, tone

POOL_SHOWN = 300  # строк пула на источник сразу; остальное — поиском (их бывают сотни)


def _scroll(inner: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    inner.setObjectName("page")
    scroll.setWidget(inner)
    return scroll


def _card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    box = QVBoxLayout(frame)
    box.setContentsMargins(18, 14, 18, 16)
    box.setSpacing(8)
    return frame, box


def _button(text: str, handler, name: str = "") -> QPushButton:
    button = QPushButton(text)
    button.setAccessibleName(text)
    if name:
        button.setObjectName(name)
    button.clicked.connect(lambda _checked=False: handler())
    return button


def confirm(parent: QWidget, title: str, text: str, yes: str) -> bool:
    """Вопрос перед необратимым действием (Убрать, Весь дом через бесплатные)."""
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(title)
    box.setInformativeText(text)
    accept = box.addButton(yes, QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is accept


class Tags(QWidget):
    """Метки у имени («основной», «Xray · дробление», «x2»): пилюли, переиспользуются."""

    def __init__(self) -> None:
        super().__init__()
        self.box = QHBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(6)
        self.pills: list[QLabel] = []

    def show_tags(self, tags: tuple[tuple[str, str], ...]) -> None:
        while len(self.pills) < len(tags):
            pill = label("", name="pill", wrap=False)
            self.box.addWidget(pill)
            self.pills.append(pill)
        for pill, (tone_name, text) in zip(self.pills, tags, strict=False):
            tone(pill, tone_name)
            set_text(pill, text)
            pill.show()
        for pill in self.pills[len(tags):]:
            pill.hide()
        self.setVisible(bool(tags))


class Row(QFrame):
    """Общая строка: значок страны, имя с метками, пояснение, цифры справа, кнопки."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("row")
        box = QHBoxLayout(self)
        box.setContentsMargins(12, 10, 12, 10)
        box.setSpacing(12)
        self.badge = Badge()
        box.addWidget(self.badge)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.name = Elided(name="rowName")
        top.addWidget(self.name, 1)
        self.tags = Tags()
        top.addWidget(self.tags)
        texts.addLayout(top)
        self.sub = Elided(name="small")
        texts.addWidget(self.sub)
        box.addLayout(texts, 1)
        values = QVBoxLayout()
        values.setSpacing(1)
        self.speed = label("", name="rowSpeed", wrap=False)
        self.value = label("", name="small", wrap=False)
        for widget in (self.speed, self.value):
            widget.setAlignment(Qt.AlignmentFlag.AlignRight)
            values.addWidget(widget)
        box.addLayout(values)
        self.dot = QLabel()
        self.dot.setObjectName("dot")
        box.addWidget(self.dot)
        self.tools = QHBoxLayout()
        self.tools.setSpacing(6)
        box.addLayout(self.tools)

    def fill(self, *, flag: str, code: str, name: str, tags, sub: str, speed: str,
             value: str, tone_name: str, selected: bool) -> None:
        self.badge.show_country(flag, code)
        set_text(self.name, name)
        tip(self.name, name)
        self.tags.show_tags(tags)
        set_text(self.sub, sub)
        tip(self.sub, sub)
        set_text(self.speed, speed)
        self.speed.setVisible(bool(speed))
        set_text(self.value, value)
        tone(self.dot, tone_name)
        tone(self, "true" if selected else "false", "main")


class ServerCard(Row):
    """Сервер подписки: замер, «Выбрать», меню «…» — ядро, приоритет, отключить, убрать."""

    def __init__(self, page: ServersPage) -> None:
        super().__init__()
        self.page = page
        self.item: listing.ServerItem | None = None
        self.measure = QToolButton()
        self.measure.setObjectName("iconButton")
        self.measure.setIconSize(QSize(18, 18))
        self.measure.clicked.connect(lambda: self.page.measure(self.item))
        self.choose = _button("Выбрать", lambda: self.page.choose(self.item))
        self.more = QToolButton()
        self.more.setObjectName("iconButton")
        self.more.setIconSize(QSize(18, 18))
        self.more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more.setMenu(QMenu(self.more))
        self.more.menu().aboutToShow.connect(self._menu)
        for widget in (self.measure, self.choose, self.more):
            self.tools.addWidget(widget)
        self.recolor()

    def recolor(self) -> None:
        colors = theme.current()
        self.measure.setIcon(icon("remeasure", colors["muted"]))
        self.more.setIcon(icon("more", colors["muted"]))

    def show_item(self, item: listing.ServerItem) -> None:
        self.item = item
        selected = item.pinned or any(text == "основной" for _t, text in item.tags)
        self.fill(flag=item.flag, code=item.code, name=item.name, tags=item.tags, sub=item.sub,
                  speed=item.speed, value=item.delay, tone_name=item.tone, selected=selected)
        status = {"member": "в работе", "spare": "запасной", "disabled": "отключён",
                  "skipped": "скрыт"}.get(item.status, item.status)
        tip(self, server_details(item.name, flag=item.flag, code=item.code, status=status,
                                 speed=item.speed, delay=item.delay, sub=item.sub, main=selected))
        self.measure.setVisible(item.measurable)
        self.measure.setEnabled(not item.measuring)
        tip(self.measure, "Скорость этого сервера замеряется…" if item.measuring
            else "Замерить скорость только этого сервера")
        self.measure.setAccessibleName(f"Замерить скорость «{item.name}»")
        self.choose.setVisible(item.choosable)
        tip(self.choose, f"Весь трафик — через «{item.name}», пока не нажмёте «Автовыбор»")
        self.choose.setAccessibleName(f"Выбрать {item.name}")
        self.more.setVisible(item.editable)
        self.more.setAccessibleName(f"Действия с сервером {item.name}")
        self.setAccessibleName(f"{item.name}: {item.sub}")

    def _menu(self) -> None:
        menu, item = self.more.menu(), self.item
        menu.clear()
        if item is None:
            return
        if item.dual:
            cores = menu.addMenu("Ядро")
            for value, text in listing.CORES:
                action = cores.addAction(text)
                action.setCheckable(True)
                action.setChecked(item.core_pin == value)
                action.triggered.connect(lambda _c=False, v=value: self.page.core(item, v))
        levels = menu.addMenu("Приоритет")
        for value, text in listing.LEVELS:
            action = levels.addAction(text)
            action.setCheckable(True)
            action.setChecked(item.priority == value)
            action.triggered.connect(lambda _c=False, v=value: self.page.priority(item, v))
        on = item.status != "disabled"
        menu.addAction("Отключить" if on else "Включить").triggered.connect(
            lambda: self.page.set_servers([item.fingerprint], "disabled" if on else "enabled"))
        menu.addSeparator()
        menu.addAction("Убрать из списка…").triggered.connect(lambda: self.page.remove(item))


class Group(QWidget):
    """Подписка: заголовок, «включено N из M», «Включить все», «Отключить все», карточки."""

    def __init__(self, page: ServersPage) -> None:
        super().__init__()
        self.page = page
        self.group: listing.Group | None = None
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 6, 0, 0)
        box.setSpacing(8)
        head = QHBoxLayout()
        self.title = label("", name="cardTitle", wrap=False)
        self.count = label("", name="small", wrap=False)
        head.addWidget(self.title)
        head.addWidget(self.count, 0, Qt.AlignmentFlag.AlignBottom)
        head.addStretch(1)
        self.enable = _button("Включить все", lambda: self._all("enabled"))
        self.disable = _button("Отключить все", lambda: self._all("disabled"))
        head.addWidget(self.enable)
        head.addWidget(self.disable)
        box.addLayout(head)
        self.list = QVBoxLayout()
        self.list.setSpacing(8)
        box.addLayout(self.list)
        self.cards: list[ServerCard] = []

    def show_group(self, group: listing.Group) -> None:
        self.group = group
        set_text(self.title, group.title)
        set_text(self.count, group.count)
        self.enable.setVisible(group.can_enable_all)
        self.disable.setVisible(group.can_disable_all)
        while len(self.cards) < len(group.items):
            card = ServerCard(self.page)
            self.list.addWidget(card)
            self.cards.append(card)
        for card, item in zip(self.cards, group.items, strict=False):
            card.show_item(item)
            card.show()
        for card in self.cards[len(group.items):]:
            card.hide()

    def _all(self, mode: str) -> None:
        if self.group is None:
            return
        wanted = ("disabled",) if mode == "enabled" else listing.ACTIVE
        chosen = [item.fingerprint for item in self.group.items
                  if item.editable and item.status in wanted]
        if chosen:
            self.page.set_servers(chosen, mode)


class PoolCard(Row):
    def __init__(self, page: ServersPage) -> None:
        super().__init__()
        self.page = page
        self.item: listing.PoolItem | None = None
        self.choose = _button("Выбрать", lambda: self.page.pool_pin(self.item))
        self.tools.addWidget(self.choose)

    def show_item(self, item: listing.PoolItem) -> None:
        self.item = item
        self.fill(flag="", code=item.country, name=item.name, tags=item.tags, sub=item.sub,
                  speed=item.speed,
                  value=item.value, tone_name=item.tone, selected=item.pinned or item.rank == 0)
        status = {0: "сейчас через него идёт трафик", 1: "в работе", 2: "допущен",
                  3: "рабочий", 4: "не прошёл проверку", 5: "не проверен"}.get(item.rank, "")
        delay = item.value if item.value.endswith("мс") else ""
        tip(self, server_details(item.name, code=item.country, status=status, speed=item.speed,
                                 delay=delay, sub=item.sub, main=item.rank == 0))
        self.choose.setText("Автовыбор" if item.pinned else "Выбрать")
        self.choose.setVisible(item.pinned or item.choosable)


class PoolGroup(QWidget):
    """Источник пула: рабочие на виду, не прошедшие и непроверенные — по кнопке."""

    def __init__(self, page: ServersPage) -> None:
        super().__init__()
        self.page = page
        self.expanded = False
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 6, 0, 0)
        box.setSpacing(8)
        head = QHBoxLayout()
        self.title = label("", name="cardTitle", wrap=False)
        self.status = label("", name="pill", wrap=False)
        self.count = label("", name="small", wrap=False)
        head.addWidget(self.title)
        head.addWidget(self.status)
        head.addWidget(self.count, 0, Qt.AlignmentFlag.AlignBottom)
        head.addStretch(1)
        self.toggle = _button("", self._flip)
        head.addWidget(self.toggle)
        box.addLayout(head)
        self.note = label("", name="small")
        box.addWidget(self.note)
        self.list = QVBoxLayout()
        self.list.setSpacing(8)
        box.addLayout(self.list)
        self.more = label("", name="small")
        box.addWidget(self.more)
        self.cards: list[PoolCard] = []
        self.group: listing.PoolGroup | None = None

    def _flip(self) -> None:
        self.expanded = not self.expanded
        if self.group is not None:
            self.show_group(self.group)

    def show_group(self, group: listing.PoolGroup) -> None:
        self.group = group
        set_text(self.title, group.title)
        tone(self.status, group.status[0])
        set_text(self.status, group.status[1])
        self.status.setVisible(bool(group.status[1]))
        set_text(self.count, group.count)
        set_text(self.note, group.note)
        works = [item for item in group.items if item.rank <= 3]
        rest = [item for item in group.items if item.rank > 3]
        items = works + rest if self.expanded or self.page.query else works
        self.toggle.setVisible(bool(rest) and not self.page.query)
        self.toggle.setText(f"Скрыть остальные ({len(rest)})" if self.expanded
                            else f"Показать остальные ({len(rest)})")
        shown = items[:POOL_SHOWN]
        set_text(self.more, f"Ещё {len(items) - len(shown)} — уточните поиском"
                 if len(items) > len(shown) else
                 "" if works or not group.items else "Рабочих серверов у источника сейчас нет.")
        self.more.setVisible(bool(self.more.text()))
        while len(self.cards) < len(shown):
            card = PoolCard(self.page)
            self.list.addWidget(card)
            self.cards.append(card)
        for card, item in zip(self.cards, shown, strict=False):
            card.show_item(item)
            card.show()
        for card in self.cards[len(shown):]:
            card.hide()


class ServersPage(QWidget):
    def __init__(self, main) -> None:
        super().__init__()
        self.main = main
        self.state: dict | None = None
        self.query = ""
        self.pool: dict | None = None
        self.pool_at: object = None
        self.confirm = lambda title, text, yes: confirm(self, title, text, yes)
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 0)
        outer.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(label("Серверы", name="pageTitle", wrap=False))
        head.addSpacing(16)
        self.tabs = QButtonGroup(self)
        self.tab_buttons = []
        for number, title in enumerate(("Подписки", "Бесплатный пул")):
            button = QPushButton(title)
            button.setObjectName("seg")
            button.setCheckable(True)
            button.setMinimumWidth(button.fontMetrics().horizontalAdvance(title) + 44)
            self.tabs.addButton(button, number)
            head.addWidget(button)
            self.tab_buttons.append(button)
        self.tab_buttons[0].setChecked(True)
        self.tabs.idClicked.connect(self._tab)
        head.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по имени или стране")
        self.search.setAccessibleName("Поиск серверов")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(self._search)
        head.addWidget(self.search)
        outer.addLayout(head)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.stack.addWidget(self._subs())
        self.stack.addWidget(self._pool())

    # --- вкладка «Подписки» ---------------------------------------------------------------------

    def _subs(self) -> QWidget:
        inner = QWidget()
        box = QVBoxLayout(inner)
        box.setContentsMargins(0, 0, 4, 24)
        box.setSpacing(10)
        frame, card = _card()
        top = QHBoxLayout()
        top.addWidget(label("Основной сервер", name="cardTitle", wrap=False))
        self.sticky = Switch("Основной сервер")
        self.sticky.clicked.connect(self._sticky)
        top.addWidget(self.sticky)
        top.addStretch(1)
        card.addLayout(top)
        self.selection = label("", name="muted")
        card.addWidget(self.selection)
        self.pin_note = label("")
        tone(self.pin_note, "busy")
        card.addWidget(self.pin_note)
        tools = QHBoxLayout()
        self.unpin = _button("Автовыбор", self.auto, "primary")
        self.speed_all = _button("Замерить скорость всех", lambda: self.run("speed"))
        self.scan = _button("Проверить запасные", lambda: self.run("scan"))
        self.refresh = _button("Обновить подписки", lambda: self.run("refresh"))
        for widget in (self.unpin, self.speed_all, self.scan, self.refresh):
            tools.addWidget(widget)
        tools.addStretch(1)
        card.addLayout(tools)
        box.addWidget(frame)
        self.notes = label("")
        tone(self.notes, "warn")
        box.addWidget(self.notes)
        self.groups_box = QVBoxLayout()
        self.groups_box.setSpacing(14)
        box.addLayout(self.groups_box)
        self.groups: dict[str, Group] = {}
        self.empty = label("", name="muted")
        box.addWidget(self.empty)
        self.removed_title = _button("", self._flip_removed)
        self.removed_open = False
        box.addWidget(self.removed_title, 0, Qt.AlignmentFlag.AlignLeft)
        self.removed_box = QVBoxLayout()
        self.removed_box.setSpacing(6)
        box.addLayout(self.removed_box)
        self.removed_rows: list[tuple[QFrame, QLabel, QLabel, QPushButton]] = []
        box.addStretch(1)
        return _scroll(inner)

    # --- вкладка «Бесплатный пул» ---------------------------------------------------------------

    def _pool(self) -> QWidget:
        inner = QWidget()
        box = QVBoxLayout(inner)
        box.setContentsMargins(0, 0, 4, 24)
        box.setSpacing(10)
        frame, card = _card()
        card.addWidget(label("Бесплатные серверы", name="cardTitle", wrap=False))
        self.pool_text = label("", name="muted")
        card.addWidget(self.pool_text)
        self.pool_flow = label("")
        tone(self.pool_flow, "busy")
        card.addWidget(self.pool_flow)
        tools = QHBoxLayout()
        self.pool_observe = _button("Включить наблюдение", lambda: self.pool_mode("observe"),
                                    "primary")
        self.pool_house = _button("Весь дом через бесплатные", self._house)
        self.pool_back = _button("Вернуть режим подписок", lambda: self.pool_mode("observe"))
        self.pool_off = _button("Выключить", lambda: self.pool_mode("off"))
        self.pool_refresh = _button("Обновить списки", lambda: self.run("freepool/refresh"))
        for widget in (self.pool_observe, self.pool_house, self.pool_back, self.pool_off,
                       self.pool_refresh):
            tools.addWidget(widget)
        tools.addStretch(1)
        card.addLayout(tools)
        box.addWidget(frame)
        self.pool_box = QVBoxLayout()
        self.pool_box.setSpacing(14)
        box.addLayout(self.pool_box)
        self.pool_groups: dict[str, PoolGroup] = {}
        self.pool_empty = label("", name="muted")
        box.addWidget(self.pool_empty)
        box.addStretch(1)
        return _scroll(inner)

    # --- отображение ----------------------------------------------------------------------------

    def show_state(self, state: dict | None) -> None:
        self.state = state
        if self.stack.currentIndex() == 0:
            self._show_subs()
        else:
            self._show_pool()

    def _show_subs(self) -> None:
        state = self.state
        on, measuring, text, pin_note = listing.selection(state)
        self.sticky.setChecked(on)
        self.sticky.setEnabled(not self.main.client.actions.busy("sticky"))
        set_text(self.selection, text)
        set_text(self.pin_note, pin_note)
        self.pin_note.setVisible(bool(pin_note))
        self.unpin.setVisible(bool((state or {}).get("pin")))
        self.speed_all.setVisible(measuring)
        for name, button in (("speed", self.speed_all), ("scan", self.scan),
                             ("refresh", self.refresh)):
            busy = bool(((state or {}).get("busy") or {}).get(name))
            button.setEnabled(not busy and not self.main.client.actions.busy(name))
        found = listing.notes(state)
        set_text(self.notes, " ".join(found))
        self.notes.setVisible(bool(found))
        groups = listing.groups(state, self.query)
        keep = set()
        for position, group in enumerate(groups):
            widget = self.groups.get(group.source)
            if widget is None:
                widget = Group(self)
                self.groups[group.source] = widget
            if self.groups_box.indexOf(widget) != position:
                self.groups_box.insertWidget(position, widget)
            widget.show_group(group)
            widget.show()
            keep.add(group.source)
        for source, widget in self.groups.items():
            if source not in keep:
                widget.hide()
        has_sources = bool((state or {}).get("subscriptions") or (state or {}).get("links"))
        empty = ("Ничего не найдено — измените поиск." if self.query else
                 "Серверы ещё не получены. Обычно это занимает до минуты." if has_sources else
                 "Серверов пока нет. Добавьте подписку в разделе «Подписки».")
        set_text(self.empty, empty if not groups else "")
        self.empty.setVisible(not groups)
        self._show_removed()

    def _show_removed(self) -> None:
        rows = listing.removed(self.state)
        self.removed_title.setVisible(bool(rows))
        self.removed_title.setText(("Скрыть убранные" if self.removed_open else
                                    "Убранные из списка") + f" — {len(rows)}")
        while len(self.removed_rows) < len(rows):
            frame = QFrame()
            frame.setObjectName("row")
            line = QHBoxLayout(frame)
            line.setContentsMargins(12, 8, 12, 8)
            name, source = label("", name="rowName", wrap=False), label("", name="small")
            back = QPushButton("Вернуть")
            line.addWidget(name)
            line.addWidget(source, 1)
            line.addWidget(back)
            self.removed_box.addWidget(frame)
            self.removed_rows.append((frame, name, source, back))
        for (frame, name, source, back), (fingerprint, title, where) in zip(
                self.removed_rows, rows, strict=False):
            set_text(name, model.split_flag(title)[1])
            set_text(source, where)
            with contextlib.suppress(TypeError):
                back.clicked.disconnect()
            back.clicked.connect(lambda _c=False, fp=fingerprint:
                                 self.set_servers([fp], "enabled"))
            frame.setVisible(self.removed_open)
        for frame, *_rest in self.removed_rows[len(rows):]:
            frame.hide()

    def _show_pool(self) -> None:
        state = self.state
        mode, text, flow = listing.pool_summary(state)
        set_text(self.pool_text, text)
        set_text(self.pool_flow, flow)
        self.pool_flow.setVisible(bool(flow))
        self.pool_observe.setVisible(mode == "off")
        self.pool_house.setVisible(mode == "observe")
        self.pool_back.setVisible(mode == "on")
        self.pool_off.setVisible(mode == "observe")
        self.pool_refresh.setVisible(mode != "off")
        summary = ((state or {}).get("free_pool") or {}).get("summary") or {}
        at = summary.get("computed_at") if mode != "off" else None
        if mode == "off" or not summary:
            self.pool, self.pool_at = None, None
        elif at != self.pool_at and self.isVisible():
            self.main.client.fetch("pool", "/api/pool", lambda data, error, a=at:
                                   self._pool_loaded(data, error, a))
        groups = listing.pool_groups(state, self.pool, self.query) if self.pool else []
        keep = set()
        for position, group in enumerate(groups):
            widget = self.pool_groups.get(group.source)
            if widget is None:
                widget = PoolGroup(self)
                self.pool_groups[group.source] = widget
            if self.pool_box.indexOf(widget) != position:
                self.pool_box.insertWidget(position, widget)
            widget.show_group(group)
            widget.show()
            keep.add(group.source)
        for source, widget in self.pool_groups.items():
            if source not in keep:
                widget.hide()
        empty = ("" if mode == "off" or not summary else
                 "Загружаю список серверов…" if self.pool is None else
                 "Источники ещё не дали серверов." if not groups else "")
        set_text(self.pool_empty, empty)
        self.pool_empty.setVisible(bool(empty))

    def _pool_loaded(self, data: dict | None, error: str, at: object) -> None:
        if data is None:
            set_text(self.pool_empty, f"Список серверов не получен: {error}")
            return
        self.pool, self.pool_at = data, at
        if self.stack.currentIndex() == 1:
            self._show_pool()

    def recolor(self) -> None:
        for group in self.groups.values():
            for card in group.cards:
                card.recolor()

    # --- действия -------------------------------------------------------------------------------

    def _tab(self, number: int) -> None:
        self.stack.setCurrentIndex(number)
        self.show_state(self.state)

    def _search(self, text: str) -> None:
        self.query = text
        self.show_state(self.state)

    def _flip_removed(self) -> None:
        self.removed_open = not self.removed_open
        self._show_removed()

    def run(self, name: str, body: dict | None = None, key: str | None = None) -> None:
        self.main.client.act(name, body or {}, key=key or name)

    def _sticky(self) -> None:
        self.run("sticky", {"on": self.sticky.isChecked()})

    def auto(self) -> None:
        self.run("unpin")

    def choose(self, item: listing.ServerItem | None) -> None:
        if item is not None and item.tag:
            self.run("pin", {"tag": item.tag, "ttl": "forever"}, key="pin")

    def measure(self, item: listing.ServerItem | None) -> None:
        if item is not None and item.tag:
            self.run("speed/one", {"tag": item.tag}, key=f"speed/one:{item.tag}")

    def core(self, item: listing.ServerItem, value: str) -> None:
        self.run("core", {"fingerprint": item.fingerprint, "core": value},
                 key=f"core:{item.fingerprint}")

    def priority(self, item: listing.ServerItem, level: str) -> None:
        self.run("priority", {"fingerprints": [item.fingerprint], "level": level},
                 key=f"priority:{item.fingerprint}")

    def set_servers(self, fingerprints: list[str], mode: str) -> None:
        self.run("servers", {"fingerprints": fingerprints, "mode": mode}, key="servers")

    def remove(self, item: listing.ServerItem) -> None:
        if self.confirm(f"Убрать сервер «{item.name}» из списка?",
                        "Шлюз перестанет к нему обращаться, и при обновлении подписки он не "
                        "вернётся. Вернуть можно в «Убранные из списка» внизу.", "Убрать"):
            self.set_servers([item.fingerprint], "removed")

    def pool_mode(self, mode: str) -> None:
        self.run("freepool/mode", {"mode": mode}, key="freepool/mode")

    def _house(self) -> None:
        if self.confirm("Весь дом через бесплатные серверы?",
                        "Устройства, эта машина, Docker и DNS пойдут через бесплатные серверы; "
                        "подписка останется только несущим каналом. Вернуть — «Вернуть режим "
                        "подписок».", "Включить"):
            self.pool_mode("on")

    def pool_pin(self, item: listing.PoolItem | None) -> None:
        if item is not None:
            self.run("freepool/pin", {"id": "" if item.pinned else item.id}, key="freepool/pin")


HAPP_TIP = ("Для поставщиков, которые незнакомой программе отдают заглушку. Шлюз запросит подписку "
            "с заголовками Happ и своим постоянным идентификатором; у поставщика с лимитом "
            "устройств шлюз займёт одно место.")


class EditDialog(QDialog):
    """«Изменить подписку»: User-Agent и заголовки, как в браузерной панели."""

    def __init__(self, parent: QWidget, sub: listing.SubItem) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Изменить подписку «{sub.name}»")
        box = QVBoxLayout(self)
        box.addWidget(label("User-Agent", name="cardTitle", wrap=False))
        self.agent = QLineEdit(sub.user_agent)
        self.agent.setPlaceholderText("пусто — по умолчанию xgw/0.1")
        box.addWidget(self.agent)
        box.addWidget(label("Заголовки, по одному в строке: Name: Value", name="cardTitle"))
        self.headers = QPlainTextEdit("\n".join(f"{k}: {v}" for k, v in sub.headers.items()))
        self.headers.setFixedHeight(90)
        box.addWidget(self.headers)
        self.preset = False  # нажата «Запрашивать как Happ»: значения подставит шлюз
        happ = QPushButton("Запрашивать как Happ")
        happ.setToolTip(HAPP_TIP)
        happ.clicked.connect(self._happ)
        box.addWidget(happ)
        buttons = QDialogButtonBox()
        buttons.addButton("Сохранить", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("Отмена", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)
        self.resize(520, 300)

    def _happ(self) -> None:
        self.preset = True
        self.accept()


class SubscriptionsPage(QWidget):
    def __init__(self, main) -> None:
        super().__init__()
        self.main = main
        self.state: dict | None = None
        self.confirm = lambda title, text, yes: confirm(self, title, text, yes)
        self.edit = lambda sub: self._edit(sub)
        self.setObjectName("page")
        inner = QWidget()
        box = QVBoxLayout(inner)
        box.setContentsMargins(28, 22, 28, 24)
        box.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(label("Подписки", name="pageTitle", wrap=False))
        head.addStretch(1)
        self.refresh = _button("Обновить все", lambda: self.main.client.act("refresh", {},
                                                                              key="refresh"))
        head.addWidget(self.refresh)
        box.addLayout(head)

        frame, card = _card()
        card.addWidget(label("Добавить", name="cardTitle", wrap=False))
        card.addWidget(label("Вставьте адрес подписки (https://…) или ссылки серверов "
                             "(vless://, vmess://, trojan://, ss://) — по одной в строке.",
                             name="muted"))
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("https://… или vless://…")
        self.text.setAccessibleName("Адрес подписки или ссылки серверов")
        self.text.setFixedHeight(76)
        card.addWidget(self.text)
        line = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Имя подписки (необязательно)")
        self.name.setAccessibleName("Имя подписки")
        line.addWidget(self.name, 1)
        self.add = _button("Добавить", self._add, "primary")
        line.addWidget(self.add)
        card.addLayout(line)
        options = QHBoxLayout()
        self.agent = QLineEdit()
        self.agent.setPlaceholderText("User-Agent (необязательно)")
        self.agent.setAccessibleName("User-Agent подписки")
        options.addWidget(self.agent, 1)
        self.happ = QCheckBox("Как Happ")
        self.happ.setToolTip(HAPP_TIP)
        self.happ.toggled.connect(self.agent.setDisabled)
        options.addWidget(self.happ)
        card.addLayout(options)
        box.addWidget(frame)

        self.subs_box = QVBoxLayout()
        self.subs_box.setSpacing(8)
        box.addLayout(self.subs_box)
        self.cards: list[tuple[QFrame, dict]] = []
        self.empty = label("", name="muted")
        box.addWidget(self.empty)
        self.links_title = label("Отдельные ссылки серверов", name="section", wrap=False)
        box.addWidget(self.links_title)
        self.links_box = QVBoxLayout()
        self.links_box.setSpacing(6)
        box.addLayout(self.links_box)
        self.link_rows: list[tuple[QFrame, QLabel, QLabel, QPushButton]] = []
        self.hidden_title = label("Убранные подписки из config.toml", name="section", wrap=False)
        box.addWidget(self.hidden_title)
        self.hidden_box = QVBoxLayout()
        self.hidden_box.setSpacing(6)
        box.addLayout(self.hidden_box)
        self.hidden_rows: list[tuple[QFrame, QLabel, QLabel, QPushButton]] = []
        box.addStretch(1)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(_scroll(inner))

    def _sub_card(self) -> tuple[QFrame, dict]:
        frame = QFrame()
        frame.setObjectName("row")
        box = QVBoxLayout(frame)
        box.setContentsMargins(16, 12, 16, 12)
        box.setSpacing(4)
        top = QHBoxLayout()
        parts: dict = {"name": label("", name="rowName", wrap=False), "tags": Tags()}
        top.addWidget(parts["name"])
        top.addWidget(parts["tags"])
        top.addStretch(1)
        parts["edit"] = QPushButton("Изменить")
        parts["remove"] = QPushButton("Убрать")
        top.addWidget(parts["edit"])
        top.addWidget(parts["remove"])
        box.addLayout(top)
        parts["sub"] = label("", name="small")
        parts["error"] = label("")
        tone(parts["error"], "bad")
        parts["quota"] = label("", name="small")
        parts["bar"] = QProgressBar()
        parts["bar"].setTextVisible(False)
        parts["bar"].setFixedHeight(6)
        parts["bar"].setRange(0, 1000)
        parts["expired"] = label("Срок подписки истёк")
        tone(parts["expired"], "bad")
        for key in ("sub", "error", "quota", "bar", "expired"):
            box.addWidget(parts[key])
        self.subs_box.addWidget(frame)
        return frame, parts

    def show_state(self, state: dict | None) -> None:
        self.state = state
        busy = bool(((state or {}).get("busy") or {}).get("refresh"))
        self.refresh.setEnabled(not busy and not self.main.client.actions.busy("refresh"))
        self.add.setEnabled(not self.main.client.actions.busy("add"))
        subs = listing.subscriptions(state)
        while len(self.cards) < len(subs):
            self.cards.append(self._sub_card())
        for (frame, parts), sub in zip(self.cards, subs, strict=False):
            set_text(parts["name"], sub.name)
            parts["tags"].show_tags(sub.tags)
            set_text(parts["sub"], sub.sub)
            set_text(parts["error"], sub.error)
            parts["error"].setVisible(bool(sub.error))
            set_text(parts["quota"], sub.quota)
            parts["quota"].setVisible(bool(sub.quota))
            parts["bar"].setVisible(sub.share is not None)
            if sub.share is not None:
                parts["bar"].setValue(int(sub.share * 1000))
                parts["bar"].setProperty("tone", "bad" if sub.share > 0.95 else
                                         "warn" if sub.share > 0.8 else "ok")
                parts["bar"].style().polish(parts["bar"])
            parts["expired"].setVisible(sub.expired)
            for key, handler in (("edit", lambda _c=False, s=sub: self.edit(s)),
                                 ("remove", lambda _c=False, s=sub: self._remove(s))):
                button = parts[key]
                with contextlib.suppress(TypeError):
                    button.clicked.disconnect()
                button.clicked.connect(handler)
                # Убрать можно любую (п. 337); изменить — только добавленную в окне или панели.
                button.setVisible(sub.managed or key == "remove")
                button.setAccessibleName(f"{button.text()} подписку {sub.name}")
            frame.show()
        for frame, _parts in self.cards[len(subs):]:
            frame.hide()
        found = listing.links(state)
        set_text(self.empty, "" if subs or found else
                 "Подписок пока нет. Вставьте адрес подписки в поле выше и нажмите «Добавить».")
        self.empty.setVisible(not subs and not found)
        self.links_title.setVisible(bool(found))
        while len(self.link_rows) < len(found):
            frame = QFrame()
            frame.setObjectName("row")
            line = QHBoxLayout(frame)
            line.setContentsMargins(14, 8, 14, 8)
            name = Elided(name="rowName")
            kind = label("отдельная ссылка сервера", name="small", wrap=False)
            button = QPushButton("Убрать")
            line.addWidget(name, 1)
            line.addWidget(kind)
            line.addWidget(button)
            self.links_box.addWidget(frame)
            self.link_rows.append((frame, name, kind, button))
        for (frame, name, kind, button), (identifier, text, managed) in zip(
                self.link_rows, found, strict=False):
            set_text(name, text)
            set_text(kind, "отдельная ссылка сервера" if managed else "из config.toml")
            with contextlib.suppress(TypeError):
                button.clicked.disconnect()
            button.clicked.connect(lambda _c=False, i=identifier, t=text: self._remove_link(i, t))
            button.setVisible(managed)
            frame.show()
        for frame, *_rest in self.link_rows[len(found):]:
            frame.hide()
        gone = listing.hidden(state)
        self.hidden_title.setVisible(bool(gone))
        while len(self.hidden_rows) < len(gone):
            frame = QFrame()
            frame.setObjectName("row")
            line = QHBoxLayout(frame)
            line.setContentsMargins(14, 8, 14, 8)
            name = Elided(name="rowName")
            host = label("", name="small", wrap=False)
            button = QPushButton("Вернуть")
            line.addWidget(name, 1)
            line.addWidget(host)
            line.addWidget(button)
            self.hidden_box.addWidget(frame)
            self.hidden_rows.append((frame, name, host, button))
        for (frame, name, host, button), (sub, where) in zip(self.hidden_rows, gone,
                                                              strict=False):
            set_text(name, sub)
            set_text(host, f"{where} · из config.toml")
            with contextlib.suppress(TypeError):
                button.clicked.disconnect()
            button.clicked.connect(lambda _c=False, s=sub: self.main.client.act(
                "subscription/restore", {"name": s}, key="subscription/restore"))
            button.setAccessibleName(f"Вернуть подписку {sub}")
            frame.show()
        for frame, *_rest in self.hidden_rows[len(gone):]:
            frame.hide()

    def _add(self) -> None:
        text = self.text.toPlainText().strip()
        if not text:
            self.main.statusBar().showMessage("Вставьте адрес подписки или ссылку сервера", 8000)
            return
        body = {"text": text, "name": self.name.text().strip()}
        if self.happ.isChecked():
            body["preset"] = "happ"
        elif self.agent.text().strip():
            body["user_agent"] = self.agent.text().strip()
        self.main.client.act("add", body, key="add")

    def action_done(self, key: str, ok: bool) -> None:
        """Добавлено — поле очищается (адрес подписки — секрет, держать его незачем); не вышло —
        текст остаётся, чтобы поправить и нажать снова."""
        if key == "add" and ok:
            self.text.clear()
            self.name.clear()
            self.agent.clear()
            self.happ.setChecked(False)

    def _edit(self, sub: listing.SubItem) -> None:
        dialog = EditDialog(self, sub)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            body = {
                "name": sub.name, "user_agent": dialog.agent.text().strip(),
                "headers": listing.parse_headers(dialog.headers.toPlainText()),
            }
            if dialog.preset:
                body["preset"] = "happ"
            self.main.client.act("subscription/edit", body, key="subscription/edit")

    def _remove(self, sub: listing.SubItem) -> None:
        text = "Её серверы пропадут из списка при следующем обновлении."
        if not sub.managed:
            text += (" Запись в config.toml останется: вернуть подписку можно здесь же, "
                     "в списке убранных.")
        if len(listing.subscriptions(self.state)) == 1 and not listing.links(self.state):
            text += " Это единственная подписка: без неё у шлюза не останется серверов."
        if self.confirm(f"Убрать подписку «{sub.name}»?", text, "Убрать"):
            self.main.client.act("subscription/remove", {"name": sub.name},
                                 key="subscription/remove")

    def _remove_link(self, identifier: str, text: str) -> None:
        if self.confirm("Убрать ссылку сервера?", text, "Убрать"):
            self.main.client.act("link/remove", {"id": identifier}, key="link/remove")
