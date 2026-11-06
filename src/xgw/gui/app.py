"""`xgw gui`: окно XGW от имени человека, в его графическом сеансе.

Один экземпляр на пользователя: второй запуск находит первый через QLocalServer и просит его
вывести окно вперёд, а сам выходит — второго опросника демона не появляется. Окно не зависит
от системного трея: значок (`xgw tray`) — отдельная программа. Закрытие окна не трогает ни
демон, ни Xray, ни sing-box.
"""

from __future__ import annotations

import os
import sys

NO_QT = ("окно XGW: нет PyQt6 — установите пакет Ubuntu: sudo apt install python3-pyqt6 "
         "(браузерная панель и значок в трее работают и без него: xgw panel --open)")
RAISE = b"raise\n"


INSTANCE_ENV = "XGW_GUI_INSTANCE"  # своё имя сокета одного экземпляра — демо и тесты


def server_name() -> str:
    return os.environ.get(INSTANCE_ENV) or f"xgw-gui-{os.getuid()}"


class SingleInstance:
    """Первый запуск слушает локальный сокет; следующий будит его и выходит."""

    def __init__(self, name: str) -> None:
        from PyQt6.QtNetwork import QLocalServer

        self.name = name
        self.server = QLocalServer()
        self.handlers: list = []

    def notify_running(self) -> bool:
        """True — окно уже открыто (и ему сказано выйти вперёд)."""
        from PyQt6.QtNetwork import QLocalSocket

        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if not socket.waitForConnected(500):
            return False
        socket.write(RAISE)
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        return True

    def listen(self, on_raise) -> bool:
        from PyQt6.QtNetwork import QLocalServer

        self.handlers.append(on_raise)
        if not self.server.listen(self.name):
            # Сокет от упавшего окна остался в /run/user/<uid>: убрать и занять снова.
            QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):
                return False
        self.server.newConnection.connect(self._accept)
        return True

    def _accept(self) -> None:
        socket = self.server.nextPendingConnection()
        if socket is None:
            return

        def read() -> None:
            if bytes(socket.readAll()).startswith(RAISE.strip()):
                for handler in self.handlers:
                    handler()
            socket.disconnectFromServer()

        socket.readyRead.connect(read)


def main(argv: list[str] | None = None) -> int:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        print("окно XGW запускается от имени пользователя, не от root: xgw gui", file=sys.stderr)
        return 2
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        print(NO_QT, file=sys.stderr)
        from .. import desktop

        desktop.notify(None, NO_QT)
        return 2
    from PyQt6.QtCore import QSettings
    from PyQt6.QtGui import QGuiApplication

    from .. import trayapp
    from . import client as clienting
    from . import login, model, theme, window

    app = QApplication.instance() or QApplication([sys.argv[0], *(argv or [])])
    app.setApplicationName("XGW")
    app.setApplicationDisplayName("XGW")
    QGuiApplication.setDesktopFileName("xgw")
    single = SingleInstance(server_name())
    if single.notify_running():
        return 0
    theme.apply(app, str(QSettings("XGW", "gui").value("theme", "system")))
    from PyQt6 import QtCore, QtGui

    app.setWindowIcon(trayapp.icon(QtGui, QtCore, "ok"))
    path = model.session_file()
    client = clienting.ApiClient(model.load_session(path))
    flow = login.LoginFlow(client.exchange)
    main_window = window.MainWindow(client, flow, path)
    single.listen(main_window.bring_to_front)
    main_window.show()
    client.start()
    return int(app.exec())
