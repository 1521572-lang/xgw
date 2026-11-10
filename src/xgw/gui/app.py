"""`xgw gui`: окно XGW от имени человека, в его графическом сеансе.

Один экземпляр на пользователя: второй запуск находит первый через QLocalServer и просит его
вывести окно вперёд, а сам выходит — второго опросника демона не появляется. Окно не зависит
от системного трея: значок (`xgw tray`) — отдельная программа. Закрытие окна не трогает ни
демон, ни Xray, ни sing-box. После обновления XGW новый запуск закрывает открытое окно
прежней версии и открывает своё.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import sys
import time
from pathlib import Path

NO_QT = ("окно XGW: нет PyQt6 — установите пакет Ubuntu: sudo apt install python3-pyqt6 "
         "(браузерная панель и значок в трее работают и без него: xgw panel --open)")
RAISE = b"raise\n"


INSTANCE_ENV = "XGW_GUI_INSTANCE"  # своё имя сокета одного экземпляра — демо и тесты


def server_name() -> str:
    return os.environ.get(INSTANCE_ENV) or f"xgw-gui-{os.getuid()}"


QUIT = b"quit\n"
REPLY_S = 0.8  # столько ждать ответа открытого окна (прежние версии не отвечают)
HANDOVER_S = 5.0  # столько ждать, пока окно прежней версии закроется


def code_stamp() -> str:
    """Отпечаток установленного кода XGW: после обновления он другой, и новый запуск окна
    заменяет открытое окно прежней версии, а не выводит его вперёд (отчёт gui-look2)."""
    package = Path(__file__).resolve().parent.parent
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        with contextlib.suppress(OSError):
            digest.update(path.relative_to(package).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def _pump(socket, seconds: float, done) -> bool:
    """Крутить события Qt, пока done() не станет True или не выйдет время."""
    from PyQt6.QtCore import QCoreApplication

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if done():
            return True
        socket.waitForReadyRead(20)
    return done()


class SingleInstance:
    """Первый запуск слушает локальный сокет; следующий будит его и выходит. Если открыто
    окно другой версии кода, оно закрывается, и место занимает новое."""

    def __init__(self, name: str, stamp: str = "") -> None:
        from PyQt6.QtNetwork import QLocalServer

        self.name = name
        self.stamp = stamp
        self.server = QLocalServer()
        self.handlers: list = []
        self.replace_handlers: list = []

    def notify_running(self) -> bool:
        """True — окно уже открыто (и ему сказано выйти вперёд). False — окна нет или окно
        прежней версии закрылось ради этого запуска: можно открывать своё."""
        from PyQt6.QtNetwork import QLocalSocket

        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if not socket.waitForConnected(500):
            return False
        socket.write(RAISE.strip() + (b" " + self.stamp.encode() if self.stamp else b"") + b"\n")
        socket.waitForBytesWritten(500)
        reply = bytearray()

        def answered() -> bool:
            reply.extend(bytes(socket.readAll()))
            return bool(reply) or socket.state() != QLocalSocket.LocalSocketState.ConnectedState

        _pump(socket, REPLY_S, answered)
        socket.disconnectFromServer()
        if not bytes(reply).startswith(QUIT.strip()):
            return True
        probe = QLocalSocket()

        def gone() -> bool:
            probe.abort()
            probe.connectToServer(self.name)
            return not probe.waitForConnected(50)

        _pump(probe, HANDOVER_S, gone)
        return False

    def listen(self, on_raise, on_replace=None) -> bool:
        from PyQt6.QtNetwork import QLocalServer

        self.handlers.append(on_raise)
        if on_replace is not None:
            self.replace_handlers.append(on_replace)
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
            data = bytes(socket.readAll()).strip()
            if not data.startswith(RAISE.strip()):
                socket.disconnectFromServer()
                return
            theirs = data[len(RAISE.strip()):].strip().decode("ascii", "replace")
            if theirs and self.stamp and theirs != self.stamp and self.replace_handlers:
                socket.write(QUIT)
                socket.flush()
                self.server.close()  # сокет свободен для окна новой версии
                for handler in self.replace_handlers:
                    handler()
                return
            for handler in self.handlers:
                handler()
            socket.disconnectFromServer()

        socket.readyRead.connect(read)


EXIT_GRACE_S = 15  # столько ждать выхода после закрытия окна, потом — стек и выход


def _watch_exit(main_window, app) -> None:
    """Закрыли окно — программа выходит сама, не дожидаясь решения Qt о «последнем окне»
    (отчёт gui-s3: на рабочем столе окно закрылось, а процесс остался). Не вышла за
    EXIT_GRACE_S — стек всех потоков в stderr (там видно, где застряло) и выход.
    `kill -USR1 <pid>` — тот же стек без выхода, для проверки на машине."""
    import faulthandler
    import signal

    with contextlib.suppress(AttributeError, ValueError, RuntimeError):
        faulthandler.register(signal.SIGUSR1, all_threads=True)

    def closed() -> None:
        faulthandler.dump_traceback_later(EXIT_GRACE_S, exit=True)
        app.quit()

    main_window.closed.connect(closed)


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
    from PyQt6.QtGui import QGuiApplication

    from .. import trayapp
    from . import client as clienting
    from . import login, model, theme, window

    app = QApplication.instance() or QApplication([sys.argv[0], *(argv or [])])
    app.setApplicationName("XGW")
    app.setApplicationDisplayName("XGW")
    QGuiApplication.setDesktopFileName("xgw-panel")  # ярлык «XGW»: его значок на панели задач
    single = SingleInstance(server_name(), code_stamp())
    if single.notify_running():
        return 0
    theme.apply(app, "light")
    from PyQt6 import QtCore, QtGui

    app.setWindowIcon(trayapp.icon(QtGui, QtCore, "ok"))
    path = model.session_file()
    client = clienting.ApiClient(model.load_session(path))
    flow = login.LoginFlow(client.exchange)
    main_window = window.MainWindow(client, flow, path)
    _watch_exit(main_window, app)

    def replaced() -> None:  # запущено окно новой версии: это закрывается
        main_window.close()
        app.quit()

    single.listen(main_window.bring_to_front, replaced)
    main_window.show()
    client.start()
    return int(app.exec())
