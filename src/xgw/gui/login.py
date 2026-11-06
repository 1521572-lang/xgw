"""Вход окна в панель: pkexec спрашивает пароль администратора окном Ubuntu и запускает от root
`xgw panel --gui-login` — тот выдаёт одноразовый код панели (60 с, один раз) и её порт одной
строкой JSON в свой вывод. Окно меняет код на cookie панели (ApiClient.exchange) и хранит её в
~/.config/xgw/gui.json (0600). Код идёт через канал вывода процесса, не через командную строку
и не в журнал; постоянный токен панели окну не достаётся.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

from .. import desktop, masking
from ..paths import Paths
from . import model


def login_command() -> tuple[str, list[str]] | str:
    """(программа, аргументы) для входа или текст, почему войти нельзя."""
    pkexec = shutil.which("pkexec")
    if pkexec is None:
        return ("нет программы pkexec (пакет pkexec), которая спрашивает пароль "
                "администратора — установите её: sudo apt install pkexec")
    launcher = Paths.from_env().launcher
    if not launcher.exists():
        found = shutil.which("xgw")
        if found is None:
            return "XGW не установлен: нет команды xgw — установите его (packaging/install.sh)"
        launcher = Path(found)
    return pkexec, [str(launcher), "panel", "--gui-login"]


class LoginFlow(QObject):
    """Один вход за раз: finished(сеанс или None, текст ошибки; пусто — человек передумал)."""

    finished = pyqtSignal(object, str)

    def __init__(self, exchange: Callable[[int, str, Callable], None],
                 parent: QObject | None = None,
                 command: Callable[[], tuple[str, list[str]] | str] = login_command) -> None:
        super().__init__(parent)
        self.exchange, self.command = exchange, command
        self.process: QProcess | None = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)

    @property
    def running(self) -> bool:
        return self.process is not None

    def start(self) -> bool:
        if self.process is not None:
            return False
        found = self.command()
        if isinstance(found, str):
            self.finished.emit(None, found)
            return False
        program, args = found
        process = self.process = QProcess(self)
        process.finished.connect(self._done)
        process.errorOccurred.connect(self._failed)
        process.start(program, args)
        self.timer.start(int(desktop.PASSWORD_WAIT * 1000))
        return True

    def _timeout(self) -> None:
        if self.process is not None:
            self.process.kill()

    def _failed(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart and self.process is not None:
            self.process = None
            self.timer.stop()
            self.finished.emit(None, "pkexec не запустился")

    def _done(self, code: int, _status) -> None:
        process, self.process = self.process, None
        self.timer.stop()
        if process is None:
            return
        out = bytes(process.readAllStandardOutput()).decode("utf-8", "replace")
        err = bytes(process.readAllStandardError()).decode("utf-8", "replace")
        process.deleteLater()
        if code == desktop.PKEXEC_DISMISSED:
            self.finished.emit(None, "")  # окно пароля закрыли — человек передумал
            return
        if code == desktop.PKEXEC_REFUSED:
            self.finished.emit(None, "Пароль администратора не принят")
            return
        found = model.parse_login(out) if code == 0 else None
        if found is None:
            reason = masking.mask_text(err.strip().splitlines()[-1] if err.strip() else "")
            self.finished.emit(None, f"Вход не выполнен{': ' + reason if reason else ''}")
            return
        port, login_code = found
        self.exchange(port, login_code, lambda session, text: self.finished.emit(session, text))
