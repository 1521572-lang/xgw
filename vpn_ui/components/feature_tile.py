"""Плитка быстрой функции в правой панели: иллюстрация 28 px и подпись в одну-две строки."""
from __future__ import annotations

from .. import theme
from ..qt import Qt, QtCore, QtGui, QtWidgets
from ..theme import svg_loader, tokens
from ..theme.tokens import Metrics

TEXT_HIDDEN_BELOW = 70  # SideWidgetTextVisibilitySizeThreshold


class FeatureTile(QtWidgets.QAbstractButton):
    """`art_off`/`art_on` — имена иллюстраций; включённая функция показывает вторую."""

    def __init__(self, key: str, caption: str, art_off: str, art_on: str | None = None,
                 parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.key, self.caption = key, caption
        self._art = (art_off, art_on or art_off)
        self._on = False
        self.setObjectName(f"Tile_{key}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Fixed)
        self.setAccessibleName(caption)
        theme.manager().changed.connect(self.update)
        self._describe()

    def set_on(self, enabled: bool) -> None:
        if enabled != self._on:
            self._on = enabled
            self._describe()
            self.update()

    def is_on(self) -> bool:
        return self._on

    def _describe(self) -> None:
        plain = self._art[0] == self._art[1]  # у кнопки настроек состояния нет
        state = "" if plain else (": включено" if self._on else ": выключено")
        self.setToolTip(self.caption + state)

    # --- размеры ---------------------------------------------------------------------
    def _font(self) -> QtGui.QFont:
        return theme.font(tokens.CAPTION)

    def _lines(self, width: int) -> list[str]:
        """Подпись, разложенная не более чем на две строки; вторая обрезается многоточием."""
        if width < TEXT_HIDDEN_BELOW:
            return []
        metrics = QtGui.QFontMetrics(self._font())
        room = max(10, width - 8)
        if metrics.horizontalAdvance(self.caption) <= room:
            return [self.caption]
        words, first = self.caption.split(), ""
        while words and metrics.horizontalAdvance((first + " " + words[0]).strip()) <= room:
            first = (first + " " + words.pop(0)).strip()
        if not first:  # одно длинное слово: режем посимвольно
            return [metrics.elidedText(self.caption, Qt.TextElideMode.ElideRight, room)]
        rest = metrics.elidedText(" ".join(words), Qt.TextElideMode.ElideRight, room)
        return [first, rest] if rest else [first]

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        lines = len(self._lines(width))
        return {0: Metrics.WIDGET_TILE_COMPACT, 1: Metrics.WIDGET_TILE}.get(
            lines, Metrics.WIDGET_TILE_TALL)

    def sizeHint(self) -> QtCore.QSize:
        width = max(self.width(), 58)
        return QtCore.QSize(width, self.heightForWidth(width))

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        wanted = self.heightForWidth(self.width())
        if self.minimumHeight() != wanted:
            self.setFixedHeight(wanted)

    # --- отрисовка -------------------------------------------------------------------
    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        colors = theme.palette()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        box = QtCore.QRectF(self.rect())
        if self.isDown():
            back = colors.fill_active
        elif self.underMouse():
            back = colors.fill_hover
        else:
            back = None
        if back is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.qcolor(back))
            painter.drawRoundedRect(box, Metrics.CONTROL_RADIUS, Metrics.CONTROL_RADIUS)
        side = Metrics.WIDGET_ICON
        art = svg_loader.illustration(self._art[1 if self._on else 0], colors.name, side,
                                      self.devicePixelRatioF())
        logical = art.deviceIndependentSize()
        painter.drawPixmap(QtCore.QPointF((box.width() - logical.width()) / 2,
                                          8 + (side - logical.height()) / 2), art)
        painter.setFont(self._font())
        painter.setPen(theme.qcolor(colors.text))
        top = 8 + side + 4
        for line in self._lines(self.width()):
            painter.drawText(QtCore.QRectF(0, top, box.width(), tokens.CAPTION.line),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, line)
            top += tokens.CAPTION.line
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QtGui.QPen(theme.qcolor(colors.border_focus), 2.0))
            painter.drawRoundedRect(box.adjusted(1, 1, -1, -1), Metrics.CONTROL_RADIUS,
                                    Metrics.CONTROL_RADIUS)
        painter.end()

    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self.update()
        super().leaveEvent(event)
