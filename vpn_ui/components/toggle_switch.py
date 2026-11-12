"""Переключатель по эталону: дорожка 40×20, кружок плавно переезжает за 120 мс."""
from __future__ import annotations

from .. import theme
from ..qt import Property, Qt, QtCore, QtGui, QtWidgets
from ..theme.tokens import Metrics


class ToggleSwitch(QtWidgets.QAbstractButton):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setFixedSize(Metrics.TOGGLE[0] + 4, Metrics.TOGGLE[1] + 4)  # +2 на кольцо фокуса
        self._offset = 0.0
        self._animation = QtCore.QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(120)
        self._animation.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._slide)
        theme.manager().changed.connect(self.update)

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = float(value)
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def _slide(self, checked: bool) -> None:
        self._animation.stop()
        if not self.isVisible():  # до показа окна анимация не нужна
            self._set_offset(1.0 if checked else 0.0)
            return
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def set_checked_silently(self, checked: bool) -> None:
        """Выставить состояние от бэкенда, не посылая `toggled` обратно."""
        if checked == self.isChecked():
            return
        blocked = self.blockSignals(True)
        self.setChecked(checked)
        self.blockSignals(blocked)
        self._slide(checked)

    def sizeHint(self) -> QtCore.QSize:
        return self.size()

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        colors = theme.palette()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        width, height = Metrics.TOGGLE
        track = QtCore.QRectF(2, 2, width, height)
        on, off = theme.qcolor(colors.primary), theme.qcolor(colors.text_weak)
        if self.underMouse() and self.isEnabled():
            on = theme.qcolor(colors.primary_hover)
        mix = self._offset
        fill = QtGui.QColor(on)
        fill.setAlphaF(mix)
        border = QtGui.QColor(off)
        border.setAlphaF(off.alphaF() * (1.0 - mix))
        painter.setOpacity(1.0 if self.isEnabled() else 0.4)
        painter.setPen(QtGui.QPen(border, 1.0))
        painter.setBrush(fill)
        inner = track.adjusted(0.5, 0.5, -0.5, -0.5)
        painter.drawRoundedRect(inner, inner.height() / 2, inner.height() / 2)
        radius = 7.0 if self.underMouse() and self.isEnabled() else 6.0
        centre_x = track.left() + 10 + (width - 20) * mix
        knob = QtGui.QColor(theme.qcolor(colors.text_on_primary if mix > 0.5 else colors.text_weak))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob)
        painter.drawEllipse(QtCore.QPointF(centre_x, track.center().y()), radius, radius)
        if self.hasFocus():
            painter.setOpacity(1.0)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(theme.qcolor(colors.border_focus), 2.0))
            ring = QtCore.QRectF(1, 1, width + 2, height + 2)
            painter.drawRoundedRect(ring, ring.height() / 2, ring.height() / 2)
        painter.end()

    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self.update()
        super().leaveEvent(event)
