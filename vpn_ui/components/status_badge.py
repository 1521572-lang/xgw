"""Строка статуса защиты («Защищено» / «Не защищено»), кольцо ожидания и плашка протокола."""
from __future__ import annotations

from .. import theme
from ..core.state import ConnectionState
from ..qt import Qt, QtCore, QtGui, QtWidgets
from ..theme import svg_loader, tokens

STATUS_TEXT = {
    ConnectionState.DISCONNECTED: (
        "Не защищено", "Подключитесь к VPN, чтобы зашифровать свои действия в сети."),
    ConnectionState.CONNECTING: ("Подключение…", "Устанавливается защищённое соединение."),
    ConnectionState.CONNECTED: ("Защищено", "Ваше соединение зашифровано."),
    ConnectionState.ERROR: ("Ошибка подключения", "Соединение установить не удалось."),
}


def status_color(state: ConnectionState) -> tokens.Color:
    colors = theme.palette()
    return {ConnectionState.DISCONNECTED: colors.danger,
            ConnectionState.CONNECTING: colors.text,
            ConnectionState.CONNECTED: colors.vpn_green,
            ConnectionState.ERROR: colors.warning}[state]


class ProgressRing(QtWidgets.QWidget):
    """Крутящаяся дуга 20×20 — кольцо ожидания из эталона."""

    def __init__(self, parent: QtWidgets.QWidget | None = None, side: int = 20) -> None:
        super().__init__(parent)
        self.setFixedSize(side, side)
        self._angle = 0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._advance)

    def _advance(self) -> None:
        self._angle = (self._angle + 12) % 360
        self.update()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        self._timer.stop()  # скрытое кольцо процессор не тратит
        super().hideEvent(event)

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        pen = QtGui.QPen(theme.qcolor(theme.palette().text), 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        box = QtCore.QRectF(self.rect()).adjusted(2, 2, -2, -2)
        painter.drawArc(box, -self._angle * 16, 270 * 16)
        painter.end()


class StatusIcon(QtWidgets.QWidget):
    """Замок 20×20: открытый красный, закрытый зелёный, знак внимания при ошибке."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self._state = ConnectionState.DISCONNECTED

    def set_state(self, state: ConnectionState) -> None:
        self._state = state
        self.update()

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        names = {ConnectionState.CONNECTED: "LockFilled",
                 ConnectionState.ERROR: "ExclamationCircleFilled"}
        name = names.get(self._state, "LockOpenFilled2")
        painter = QtGui.QPainter(self)
        painter.drawPixmap(0, 0, svg_loader.icon_pixmap(name, status_color(self._state), 20,
                                                        self.devicePixelRatioF()))
        painter.end()


class StatusBadge(QtWidgets.QWidget):
    """Иконка состояния, цветной заголовок и пояснение после точки-разделителя."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = ConnectionState.DISCONNECTED
        self.icon = StatusIcon(self)
        self.ring = ProgressRing(self)
        self.title = QtWidgets.QLabel(self)
        self.title.setObjectName("StatusTitle")
        self.description = QtWidgets.QLabel(self)
        self.description.setObjectName("StatusDescription")
        self.description.setProperty("elide", True)
        self.description.setMinimumWidth(0)
        self.description.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,
                                       QtWidgets.QSizePolicy.Policy.Preferred)
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self.icon)
        row.addWidget(self.ring)
        row.addWidget(self.title)
        row.addWidget(self.description, 1)
        self._detail = ""
        theme.manager().changed.connect(self._refresh)
        self.show_state(self.state)

    def show_state(self, state: ConnectionState, detail: str = "") -> None:
        self.state, self._detail = state, detail
        self._refresh()

    def _refresh(self) -> None:
        title, description = STATUS_TEXT[self.state]
        busy = self.state is ConnectionState.CONNECTING
        self.icon.setVisible(not busy)
        self.ring.setVisible(busy)
        self.icon.set_state(self.state)
        self.title.setText(title)
        self.title.setStyleSheet(f"color: {status_color(self.state).qss};")
        self._full = "• " + (self._detail or description)
        self.description.setToolTip(self._detail or description)
        self._elide()

    def _elide(self) -> None:
        metrics = self.description.fontMetrics()
        self.description.setText(metrics.elidedText(
            self._full, Qt.TextElideMode.ElideRight, max(0, self.description.width())))

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        QtCore.QTimer.singleShot(0, self._elide)  # ширина подписи известна после раскладки


class ProtocolPill(QtWidgets.QLabel):
    """Небольшая плашка с названием протокола; вид задаёт QSS (#ProtocolPill)."""

    def __init__(self, text: str = "", parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("ProtocolPill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
