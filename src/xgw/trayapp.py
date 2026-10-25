"""Значок XGW в трее — окно Qt (0.1.18, ТЗ R9). Логика — в tray.py, здесь только Qt.

Один графический фреймворк — PyQt6 из пакета Ubuntu python3-pyqt6 (его ставит установка);
нет его — PyQt5 (python3-pyqt5), тот же код. QSystemTrayIcon в KDE Plasma показывается через
StatusNotifierItem рядом с часами. Значок рисуется здесь же: роутер цвета состояния (корпус с
огоньками и три антенны, по рисунку заказчика) — файлов картинок не нужно.
"""

from __future__ import annotations

import importlib
import sys
import threading
import time
from pathlib import Path

from . import tray

COLORS = {
    "ok": "#2e9d57", "warn": "#d99a14", "down": "#d23f31", "job": "#2f74c0", "off": "#8a8f98",
}
WAIT_TRAY = 60.0  # столько ждать, пока у сеанса появится трей (панель KDE поднимается позже)
SIZES = (16, 22, 24, 32, 48, 64)  # трей KDE берёт ближайший размер — на 22 точках не мылится


def _qt():
    """(QtCore, QtGui, QtWidgets) из PyQt6, а без него — из PyQt5."""
    for name in ("PyQt6", "PyQt5"):
        try:
            return (importlib.import_module(f"{name}.QtCore"),
                    importlib.import_module(f"{name}.QtGui"),
                    importlib.import_module(f"{name}.QtWidgets"))
        except ImportError:
            continue
    raise tray.TrayError("нет PyQt6 и PyQt5: установите python3-pyqt6 (sudo apt install "
                         "python3-pyqt6) или переустановите XGW")


def _enum(owner, group: str, name: str):
    """Значение перечисления Qt и в PyQt6 (Owner.Group.Name), и в PyQt5 (Owner.Name)."""
    scoped = getattr(owner, group, None)
    return getattr(scoped, name) if scoped is not None else getattr(owner, name)


def icon(QtGui, QtCore, kind: str):
    """Роутер цвета состояния на прозрачном фоне: корпус с тремя огоньками и три антенны с
    шариками. Рисунок задан в клетке 64×64 и рисуется заново под каждый размер из SIZES."""
    color = QtGui.QColor(COLORS.get(kind, COLORS["off"]))
    result = QtGui.QIcon()
    for size in SIZES:
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(_enum(QtCore.Qt, "GlobalColor", "transparent"))
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(_enum(QtGui.QPainter, "RenderHint", "Antialiasing"))
        painter.scale(size / 64, size / 64)
        pen = QtGui.QPen(color)
        pen.setWidthF(6.0)
        pen.setCapStyle(_enum(QtCore.Qt, "PenCapStyle", "RoundCap"))
        painter.setPen(pen)
        painter.setBrush(_enum(QtCore.Qt, "BrushStyle", "NoBrush"))
        antennas = QtGui.QPainterPath()
        antennas.moveTo(32, 38)
        antennas.lineTo(32, 14)
        for side in (14, 50):  # боковые: от корпуса в сторону и вверх
            antennas.moveTo(32, 36)
            antennas.quadTo(side, 35, side, 22)
        painter.drawPath(antennas)
        # Корпус и шарики — одной заливкой; огоньки — дыры в корпусе (правило чёт-нечет).
        solid = QtGui.QPainterPath()
        solid.addRoundedRect(QtCore.QRectF(6, 38, 52, 20), 6, 6)
        for x in (16, 24, 32):
            solid.addEllipse(QtCore.QPointF(x, 48), 3, 3)
        for x, y, radius in ((32, 9, 6), (14, 17, 5.5), (50, 17, 5.5)):
            solid.addEllipse(QtCore.QPointF(x, y), radius, radius)
        painter.setPen(_enum(QtCore.Qt, "PenStyle", "NoPen"))
        painter.setBrush(color)
        painter.drawPath(solid)
        painter.end()
        result.addPixmap(pixmap)
    return result


class TrayApp:
    def __init__(self, client: tray.Client, qt) -> None:
        self.QtCore, self.QtGui, self.QtWidgets = qt
        self.client = client
        self.state: dict | None = None
        self.error = ""
        self.app = self.QtWidgets.QApplication.instance() or self.QtWidgets.QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.icons = {name: icon(self.QtGui, self.QtCore, name) for name in COLORS}
        self.icon = self.QtWidgets.QSystemTrayIcon(self.icons["off"])
        self.menu = self.QtWidgets.QMenu()
        self.actions: dict[str, object] = {}
        for action, label in tray.MENU:
            item = self.menu.addAction(label)
            item.triggered.connect(lambda _checked=False, name=action: self.do(name))
            self.actions[action] = item
            if action == "about":
                self.menu.addSeparator()
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self.clicked)
        self.timer = self.QtCore.QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(int(tray.POLL_SECONDS * 1000))

    # --- данные ---------------------------------------------------------------

    def refresh(self) -> None:
        try:
            self.state, self.error = self.client.state(), ""
        except tray.TrayError as exc:
            self.state, self.error = None, str(exc)
        if self.state is not None and self.state.get("enabled") is False:
            self.app.exit(0)  # tray.enabled = false: значок не нужен
            return
        kind = tray.kind(self.state)
        self.icon.setIcon(self.icons[kind])
        self.icon.setToolTip(tray.tooltip(self.state, self.error))
        for action, _label, enabled in tray.menu(self.state):
            self.actions[action].setEnabled(enabled)

    # --- действия ---------------------------------------------------------------

    def clicked(self, reason) -> None:
        if reason == _enum(self.QtWidgets.QSystemTrayIcon, "ActivationReason", "Trigger"):
            self.do("open")

    def do(self, action: str) -> None:
        if action == "quit":
            self.app.exit(0)  # закрывается только значок; шлюз работает
        elif action == "open":
            url = (self.state or {}).get("panel") or f"http://127.0.0.1:{self.client.port}/"
            # Вывести вперёд вкладку на экране ждёт до 2 с — не в потоке Qt, чтобы меню не
            # замирало; open_panel окна Qt не трогает.
            threading.Thread(target=self._open, args=(url,), daemon=True).start()
        elif action == "about":
            self.QtWidgets.QMessageBox.information(None, "XGW", tray.about(self.state))
        else:
            self._act(action)

    def _open(self, url: str) -> None:
        try:
            tray.open_panel(url, self.client)
        except OSError as exc:
            print(f"значок XGW: браузер не открылся: {exc}", file=sys.stderr)

    def _act(self, action: str) -> None:
        """Запрос к панели: она только ставит отметку демону и отвечает сразу (таймаут 5 с),
        поэтому — прямо в потоке Qt (из другого потока Qt окно трогать нельзя)."""
        try:
            result = self.client.act(action)
            text, failed = str(result.get("text") or "Готово"), not result.get("ok")
        except tray.TrayError as exc:
            text, failed = str(exc), True
        icon_kind = _enum(
            self.QtWidgets.QSystemTrayIcon, "MessageIcon", "Warning" if failed else "Information",
        )
        self.icon.showMessage("XGW", text, icon_kind, 5000)
        self.refresh()

    def run(self) -> int:
        self.refresh()
        self.icon.show()
        return int(self.app.exec())


def run() -> int:
    """`xgw tray --run`: значок в трее до «Выхода». Код 0 — закрыт человеком (или значок
    выключен в конфиге), NO_TRAY — у сеанса нет трея, NOT_SET — не настроен."""
    try:
        port, token = tray.read_user_file(Path.home())
        qt = _qt()
    except tray.TrayError as exc:
        print(f"значок XGW: {exc}", file=sys.stderr)
        return tray.NOT_SET
    QtWidgets = qt[2]
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    started = time.monotonic()
    while not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
        if time.monotonic() - started > WAIT_TRAY:
            print("значок XGW: у сеанса нет системного трея", file=sys.stderr)
            return tray.NO_TRAY
        app.processEvents()
        time.sleep(1.0)
    return TrayApp(tray.Client(port, token), qt).run()
