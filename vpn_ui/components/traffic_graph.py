"""График скорости: две сглаженные кривые (приём и отдача) с заливкой и сеткой."""
from __future__ import annotations

import itertools
import math
from collections import deque

from .. import theme
from ..core.state import format_speed
from ..qt import Qt, QtCore, QtGui, QtWidgets
from ..theme import tokens
from ..theme.tokens import Metrics

SAMPLES = 60  # одна точка в секунду — минута истории


def nice_ceiling(value: float) -> float:
    """Верх шкалы: ближайшее сверху из ряда 1–2–5 × 10ⁿ (не меньше 100 Кбит/с)."""
    value = max(value, 100_000.0)
    power = 10 ** math.floor(math.log10(value))
    for step in (1, 2, 5, 10):
        if value <= step * power:
            return float(step * power)
    return float(10 * power)


class TrafficGraphWidget(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(Metrics.CHART_HEIGHT)
        self.setMinimumWidth(120)
        self._down: deque[float] = deque(maxlen=SAMPLES)
        self._up: deque[float] = deque(maxlen=SAMPLES)
        theme.manager().changed.connect(self.update)

    def push(self, down_bps: float, up_bps: float) -> None:
        self._down.append(max(0.0, float(down_bps)))
        self._up.append(max(0.0, float(up_bps)))
        self.update()

    def clear(self) -> None:
        self._down.clear()
        self._up.clear()
        self.update()

    def upper_bound(self) -> float:
        return nice_ceiling(max([*self._down, *self._up, 0.0]))

    # --- отрисовка -------------------------------------------------------------------
    def _curve(self, values: deque[float], area: QtCore.QRectF, top: float) -> QtGui.QPainterPath:
        """Кривая через середины отрезков: изломы сглаживаются квадратичными дугами."""
        step = area.width() / (SAMPLES - 1)
        start = area.right() - step * (len(values) - 1)
        points = [QtCore.QPointF(start + index * step,
                                 area.bottom() - area.height() * min(1.0, value / top))
                  for index, value in enumerate(values)]
        path = QtGui.QPainterPath(points[0])
        for before, after in itertools.pairwise(points):
            middle = QtCore.QPointF((before.x() + after.x()) / 2, (before.y() + after.y()) / 2)
            path.quadTo(before, middle)
        path.lineTo(points[-1])
        return path

    def _draw_series(self, painter: QtGui.QPainter, values: deque[float], area: QtCore.QRectF,
                     top: float, color: tokens.Color) -> None:
        if len(values) < 2:
            return
        line = self._curve(values, area, top)
        fill = QtGui.QPainterPath(line)
        fill.lineTo(area.right(), area.bottom())
        fill.lineTo(line.elementAt(0).x, area.bottom())
        fill.closeSubpath()
        gradient = QtGui.QLinearGradient(0, area.top(), 0, area.bottom())
        gradient.setColorAt(0.0, theme.qcolor(color.alpha(0.251)))
        gradient.setColorAt(1.0, theme.qcolor(color.alpha(0.0)))
        painter.fillPath(fill, QtGui.QBrush(gradient))
        pen = QtGui.QPen(theme.qcolor(color), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.strokePath(line, pen)

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        colors = theme.palette()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        font = theme.font(tokens.CAPTION)
        font.setPixelSize(10)
        painter.setFont(font)
        metrics = QtGui.QFontMetrics(font)
        top = self.upper_bound()
        labels = [format_speed(top), format_speed(top / 2), "0"]
        gutter = max(metrics.horizontalAdvance(text) for text in labels) + 6
        area = QtCore.QRectF(0.5, 6.5, self.width() - gutter - 1, self.height() - 13)
        grid = QtGui.QPen(theme.qcolor(colors.border_weak), 1.0, Qt.PenStyle.DashLine)
        for index, text in enumerate(labels):
            y = area.top() + area.height() * index / 2
            painter.setPen(grid)
            painter.drawLine(QtCore.QPointF(area.left(), y), QtCore.QPointF(area.right(), y))
            painter.setPen(theme.qcolor(colors.text_hint))
            painter.drawText(QtCore.QRectF(area.right() + 6, y - 7, gutter, 14),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        painter.setPen(QtGui.QPen(theme.qcolor(colors.border_weak.alpha(colors.border_weak.a / 2)),
                                  1.0))
        for column in range(1, 6):  # вертикальные линии каждые 10 секунд
            x = area.left() + area.width() * column / 6
            painter.drawLine(QtCore.QPointF(x, area.top()), QtCore.QPointF(x, area.bottom()))
        painter.setClipRect(area.adjusted(0, -2, 0, 1))
        self._draw_series(painter, self._up, area, top, colors.chart_up)
        self._draw_series(painter, self._down, area, top, colors.chart_down)
        painter.end()
