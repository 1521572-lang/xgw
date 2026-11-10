"""Расход трафика из отдельного запроса к локальной панели."""

from __future__ import annotations

import time
from html import escape

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import client, listing
from .widgets import label, set_text

REFRESH_SECONDS = 60
PERIODS = {1: "Сегодня", 7: "7 дней", 30: "30 дней"}


class TrafficPage(QWidget):
    def __init__(self, main) -> None:
        super().__init__()
        self.main = main
        self.days = 1
        self.session = main.client.session
        self.report: listing.TrafficReport | None = None
        self.last_attempt: float | None = None
        self.error = ""
        self.setObjectName("page")
        box = QVBoxLayout(self)
        box.setContentsMargins(28, 22, 28, 16)
        box.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(label("Трафик", name="pageTitle", wrap=False))
        head.addStretch(1)
        self.periods = QButtonGroup(self)
        for days, title in PERIODS.items():
            button = QPushButton(title)
            button.setObjectName("seg")
            button.setCheckable(True)
            button.setChecked(days == self.days)
            self.periods.addButton(button, days)
            head.addWidget(button)
        self.periods.idClicked.connect(self._period)
        box.addLayout(head)
        self.note = label("Ожидаю данные панели…", name="muted")
        self.note.setTextFormat(Qt.TextFormat.PlainText)
        box.addWidget(self.note)
        box.addWidget(label(
            "Устройства — весь расход по счётчикам шлюза. «Учтено» — расход с множителями "
            "серверов. Строки подписок, выходов и WAN показывают разные срезы.",
            name="muted",
        ))
        self.table = QTreeWidget()
        self.table.setAccessibleName("Расход трафика")
        self.table.setHeaderLabels(("Строка", "Получено", "Отправлено", "Подробности"))
        self.table.setAlternatingRowColors(True)
        header = self.table.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.devices = QTreeWidgetItem(self.table, ["Устройства"])
        self.exits = QTreeWidgetItem(self.table, ["Подписки и выходы"])
        self.devices.setExpanded(True)
        self.exits.setExpanded(True)
        self.table.hide()
        box.addWidget(self.table, 1)

    def _clear(self) -> None:
        self.report = None
        self.last_attempt = None
        self.error = ""
        self.table.hide()

    def _period(self, days: int) -> None:
        if days != self.days:
            self.days = days
            self._clear()
            self.refresh()

    def refresh(self) -> None:
        api = self.main.client
        if self.session is not api.session:
            self.session = api.session
            self._clear()
        reachable = self.main.link in (client.LINK_OK, client.LINK_STALE)
        due = self.last_attempt is None or time.monotonic() - self.last_attempt >= REFRESH_SECONDS
        if (self.session is not None and reachable and due and self.isVisible() and api.visible
                and api.fetch("traffic", f"/api/traffic?days={self.days}",
                              lambda data, error, days=self.days: self._loaded(days, data, error))):
            self.last_attempt = time.monotonic()
        self._note(reachable)

    def _note(self, reachable: bool) -> None:
        if self.report is not None:
            text = self.report.period
            if self.error or not reachable:
                text += " · последние полученные данные"
        elif self.error:
            text = self.error
        else:
            text = "Загружаю отчёт…" if reachable else "Ожидаю данные панели…"
        if self.error and self.report is not None:
            text += " · " + self.error
        set_text(self.note, text)

    def _loaded(self, days: int, data: dict | None, error: str) -> None:
        if days != self.days:
            self.refresh()
            return
        self.last_attempt = time.monotonic()
        if data is None or data.get("error"):
            self.error = "Не удалось получить отчёт" + (f": {error}" if error else "")
        else:
            try:
                report = listing.traffic_report(data, days)
            except (KeyError, ValueError, TypeError, AttributeError, OverflowError, OSError):
                self.error = "Панель вернула неполный отчёт"
            else:
                self.error = ""
                if report != self.report:
                    self.report = report
                    self._show_report(report)
        self._note(self.main.link in (client.LINK_OK, client.LINK_STALE))

    @staticmethod
    def _text(item: QTreeWidgetItem, row: listing.TrafficRow) -> None:
        for column, value in enumerate((row.name, row.down, row.up, row.detail)):
            item.setText(column, value)
            item.setToolTip(column, f"<p>{escape(value)}</p>" if value else "")

    def _rows(self, parent: QTreeWidgetItem, rows: tuple[listing.TrafficRow, ...]) -> None:
        while parent.childCount() > len(rows):
            parent.takeChild(parent.childCount() - 1)
        for index, row in enumerate(rows):
            item = parent.child(index)
            if item is None:
                item = QTreeWidgetItem(parent)
            self._text(item, row)

    def _show_report(self, report: listing.TrafficReport) -> None:
        self._text(self.devices, report.total)
        self._rows(self.devices, report.devices or (listing.TrafficRow("Данных пока нет", "", ""),))
        self._rows(self.exits, report.exits)
        self.table.show()
