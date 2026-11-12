"""Подложка окна: карта мира, отметки стран, свечение по состоянию и затухание к низу."""
from __future__ import annotations

import json
from collections.abc import Iterable

from .. import theme
from ..core.state import ConnectionState
from ..qt import Qt, QtCore, QtGui, QtSvg, QtWidgets
from ..theme import svg_loader, tokens
from ..theme.tokens import Metrics

DEFAULT_FOCUS = (640.0, 165.0)  # Европа: пока страна неизвестна
ANCHOR_Y = 0.44  # где по высоте окна стоит выбранная страна


def load_points() -> dict[str, tuple[float, float]]:
    data = json.loads((svg_loader.ASSETS / "map_points.json").read_text(encoding="utf-8"))
    return {code: (float(x), float(y)) for code, (x, y) in data["points"].items()}


class MapCanvasView(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MapCanvas")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.points = load_points()
        self.state = ConnectionState.DISCONNECTED
        self.focus_code = ""
        self.markers: list[str] = []
        self._focus = QtCore.QPointF(*DEFAULT_FOCUS)
        self._free = QtCore.QRectF()
        self._glow = theme.qcolor(tokens.STATE_GLOW[self.state.value])
        self._phase = 0.0
        self._renderer: QtSvg.QSvgRenderer | None = None
        self._map_cache: tuple[tuple, QtGui.QPixmap] | None = None

        self._move = QtCore.QVariantAnimation(self)
        self._move.setDuration(450)
        self._move.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._move.valueChanged.connect(self._moved)
        self._tint = QtCore.QVariantAnimation(self)
        self._tint.setDuration(300)
        self._tint.valueChanged.connect(self._tinted)
        self._pulse = QtCore.QTimer(self)
        self._pulse.setInterval(33)
        self._pulse.timeout.connect(self._beat)
        theme.manager().changed.connect(self._theme_changed)

    # --- внешнее управление ----------------------------------------------------------
    def set_free_area(self, area: QtCore.QRectF) -> None:
        """Часть окна, не закрытая панелями: выбранная страна ставится в её середину."""
        if area != self._free:
            self._free = QtCore.QRectF(area)
            self.update()

    def set_markers(self, codes: Iterable[str]) -> None:
        self.markers = sorted({code.upper() for code in codes if code.upper() in self.points})
        self.update()

    def set_focus(self, code: str, animate: bool = True) -> None:
        code = code.upper()
        self.focus_code = code
        target = QtCore.QPointF(*self.points.get(code, DEFAULT_FOCUS))
        self._move.stop()
        if animate and self.isVisible() and target != self._focus:
            self._move.setStartValue(QtCore.QPointF(self._focus))
            self._move.setEndValue(target)
            self._move.start()
        else:
            self._focus = target
            self.update()

    def set_state(self, state: ConnectionState) -> None:
        self.state = state
        target = theme.qcolor(tokens.STATE_GLOW[state.value])
        self._tint.stop()
        if self.isVisible():
            self._tint.setStartValue(QtGui.QColor(self._glow))
            self._tint.setEndValue(target)
            self._tint.start()
        else:
            self._glow = target
        if state is ConnectionState.CONNECTING and self.isVisible():
            self._pulse.start()
        else:
            self._pulse.stop()
            self._phase = 0.0
        self.update()

    # --- анимации --------------------------------------------------------------------
    def _moved(self, value: QtCore.QPointF) -> None:
        self._focus = QtCore.QPointF(value)
        self.update()

    def _tinted(self, value: QtGui.QColor) -> None:
        self._glow = QtGui.QColor(value)
        self.update()

    def _beat(self) -> None:
        self._phase = (self._phase + 0.025) % 1.0
        self.update()

    def _theme_changed(self) -> None:
        self._renderer = None
        self._map_cache = None
        self.update()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        if self.state is ConnectionState.CONNECTING:
            self._pulse.start()
        super().showEvent(event)

    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        self._pulse.stop()
        super().hideEvent(event)

    # --- геометрия -------------------------------------------------------------------
    def _anchor(self) -> QtCore.QPointF:
        free = self._free if self._free.isValid() else QtCore.QRectF(self.rect())
        return QtCore.QPointF(free.center().x(), self.height() * ANCHOR_Y)

    def _visible(self) -> QtCore.QRectF:
        """Какая часть карты (в её единицах) попадает в окно при текущем фокусе."""
        scale, anchor = Metrics.MAP_SCALE, self._anchor()
        return QtCore.QRectF(self._focus.x() - anchor.x() / scale,
                             self._focus.y() - anchor.y() / scale,
                             self.width() / scale, self.height() / scale)

    def map_to_widget(self, code: str) -> QtCore.QPointF | None:
        point = self.points.get(code.upper())
        if point is None:
            return None
        visible = self._visible()
        return QtCore.QPointF((point[0] - visible.left()) * Metrics.MAP_SCALE,
                              (point[1] - visible.top()) * Metrics.MAP_SCALE)

    # --- отрисовка -------------------------------------------------------------------
    def _map_pixmap(self) -> QtGui.QPixmap:
        colors = theme.palette()
        ratio = self.devicePixelRatioF()
        visible = self._visible()
        key = (self.width(), self.height(), ratio, colors.name,
               round(visible.left(), 2), round(visible.top(), 2))
        if self._map_cache is not None and self._map_cache[0] == key:
            return self._map_cache[1]
        if self._renderer is None:
            self._renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(
                svg_loader.world_map_svg(colors.map_land, colors.map_outline)))
        pixmap = QtGui.QPixmap(max(1, round(self.width() * ratio)),
                               max(1, round(self.height() * ratio)))
        pixmap.fill(theme.qcolor(colors.map_sea))
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        self._renderer.setViewBox(visible)
        self._renderer.render(painter, QtCore.QRectF(0, 0, pixmap.width(), pixmap.height()))
        painter.end()
        pixmap.setDevicePixelRatio(ratio)
        self._map_cache = (key, pixmap)
        return pixmap

    def _draw_markers(self, painter: QtGui.QPainter) -> None:
        colors = theme.palette()
        painter.setPen(Qt.PenStyle.NoPen)
        for code in self.markers:
            spot = self.map_to_widget(code)
            if spot is None or code == self.focus_code:
                continue
            painter.setBrush(theme.qcolor(colors.text_hint))
            painter.drawEllipse(spot, 2.5, 2.5)
        spot = self.map_to_widget(self.focus_code) if self.focus_code else None
        if spot is None:
            return
        ink = {ConnectionState.DISCONNECTED: colors.danger, ConnectionState.CONNECTING: colors.text,
               ConnectionState.CONNECTED: colors.vpn_green,
               ConnectionState.ERROR: colors.warning}[self.state]
        if self.state is ConnectionState.CONNECTING:
            ring = QtGui.QColor(theme.qcolor(ink))
            ring.setAlphaF((1.0 - self._phase) * 0.8)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(ring, 2.0))
            radius = 6.0 + 18.0 * self._phase
            painter.drawEllipse(spot, radius, radius)
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            painter.setBrush(theme.qcolor(ink.alpha(0.22)))
            painter.drawEllipse(spot, 12.0, 12.0)
        painter.setBrush(theme.qcolor(ink))
        painter.drawEllipse(spot, 5.0, 5.0)
        painter.setBrush(theme.qcolor(colors.bg_norm))
        painter.drawEllipse(spot, 2.0, 2.0)

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        colors = theme.palette()
        painter = QtGui.QPainter(self)
        painter.drawPixmap(0, 0, self._map_pixmap())
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        self._draw_markers(painter)
        glow = QtGui.QLinearGradient(0, 0, 0, Metrics.GLOW_HEIGHT)
        top = QtGui.QColor(self._glow)
        if colors.name == "light":
            top.setAlphaF(top.alphaF() * 0.6)  # на белом то же свечение читается резче
        clear = QtGui.QColor(top)
        clear.setAlphaF(0.0)
        glow.setColorAt(0.0, top)
        glow.setColorAt(1.0, clear)
        painter.fillRect(QtCore.QRectF(0, 0, self.width(), Metrics.GLOW_HEIGHT), QtGui.QBrush(glow))
        bottom = self.height()
        fade = QtGui.QLinearGradient(0, bottom, 0, bottom - Metrics.FADE_HEIGHT)
        fade.setColorAt(0.0, theme.qcolor(colors.bg_norm.alpha(0.941)))
        fade.setColorAt(1.0, theme.qcolor(colors.bg_norm.alpha(0.0)))
        painter.fillRect(QtCore.QRectF(0, bottom - Metrics.FADE_HEIGHT, self.width(),
                                       Metrics.FADE_HEIGHT), QtGui.QBrush(fade))
        painter.end()
