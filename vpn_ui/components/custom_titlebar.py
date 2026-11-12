"""Шапка окна высотой 38: меню, значок и название слева, кнопки окна справа.

В режиме системной рамки (`native=True`) остаётся только кнопка меню: заголовок и кнопки
окна рисует оконный менеджер.
"""
from __future__ import annotations

from .. import theme
from ..qt import Qt, QtCore, QtGui, QtWidgets, Signal
from ..theme import svg_loader
from ..theme.tokens import Metrics


class CaptionButton(QtWidgets.QAbstractButton):
    """Свернуть / развернуть / закрыть: тонкий значок 10×10."""

    def __init__(self, kind: str, tip: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(*Metrics.CAPTION_BUTTON)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip(tip)
        self.setAccessibleName(tip)
        self.setObjectName(f"Caption_{kind}")

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        colors = theme.palette()
        painter = QtGui.QPainter(self)
        hover = self.underMouse()
        ink = theme.qcolor(colors.text)
        if hover:
            closing = self.kind == "close"
            back = colors.caption_close_hover if closing else colors.fill_hover
            painter.fillRect(self.rect(), theme.qcolor(back))
            if closing:
                ink = QtGui.QColor("#FFFFFF")
        painter.setPen(QtGui.QPen(ink, 1.0))
        cx, cy = self.width() // 2, self.height() // 2
        if self.kind == "minimize":
            painter.drawLine(cx - 5, cy, cx + 5, cy)
        elif self.kind == "maximize":
            if self.window().isMaximized():  # два наложенных квадрата — «восстановить»
                painter.drawRect(cx - 5, cy - 3, 8, 8)
                painter.drawLine(cx - 3, cy - 5, cx + 5, cy - 5)
                painter.drawLine(cx + 5, cy - 5, cx + 5, cy + 3)
            else:
                painter.drawRect(cx - 5, cy - 5, 10, 10)
        else:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            painter.drawLine(QtCore.QPointF(cx - 5, cy - 5), QtCore.QPointF(cx + 5, cy + 5))
            painter.drawLine(QtCore.QPointF(cx + 5, cy - 5), QtCore.QPointF(cx - 5, cy + 5))
        painter.end()

    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self.update()
        super().leaveEvent(event)


class IconLabel(QtWidgets.QLabel):
    """Одноцветная иконка набора, которая перекрашивается при смене темы."""

    def __init__(self, name: str, px: int, role: str = "text",
                 parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._name, self._px, self._role = name, px, role
        self.setFixedSize(px, px)
        theme.manager().changed.connect(self.refresh)
        self.refresh()

    def set_icon(self, name: str, role: str | None = None) -> None:
        self._name = name
        self._role = role or self._role
        self.refresh()

    def refresh(self) -> None:
        color = getattr(theme.palette(), self._role)
        self.setPixmap(svg_loader.icon_pixmap(self._name, color, self._px))


class CustomTitleBar(QtWidgets.QWidget):
    menu_requested = Signal()

    def __init__(self, title: str, native: bool = False,
                 parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.native = native
        self.setObjectName("TitleBar")
        self.setFixedHeight(Metrics.TITLE_BAR)
        self.menu_button = QtWidgets.QToolButton(self)
        self.menu_button.setObjectName("TitleMenuButton")
        self.menu_button.setFixedSize(Metrics.MENU_BUTTON, Metrics.MENU_BUTTON)
        self.menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_button.setToolTip("Меню")
        self.menu_button.setAccessibleName("Меню")
        self.menu_button.clicked.connect(self.menu_requested)
        self.app_icon = IconLabel("ShieldFilled", 16, "link", self)
        self.title = QtWidgets.QLabel(title, self)
        self.title.setObjectName("TitleLabel")
        self.buttons = {
            "minimize": CaptionButton("minimize", "Свернуть", self),
            "maximize": CaptionButton("maximize", "Развернуть", self),
            "close": CaptionButton("close", "Закрыть", self),
        }
        self.buttons["minimize"].clicked.connect(lambda: self.window().showMinimized())
        self.buttons["maximize"].clicked.connect(self.toggle_maximized)
        self.buttons["close"].clicked.connect(lambda: self.window().close())
        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(Metrics.EDGE, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.menu_button, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addSpacing(8)
        row.addWidget(self.app_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addSpacing(8)
        row.addWidget(self.title, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        for button in self.buttons.values():
            row.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
        for widget in (self.app_icon, self.title, *self.buttons.values()):
            widget.setVisible(not native)
        theme.manager().changed.connect(self._retint)
        self._retint()

    def _retint(self) -> None:
        colors = theme.palette()
        self.menu_button.setIcon(svg_loader.load_svg_icon(
            "ThreeDotsVertical", colors.text.hex, QtCore.QSize(16, 16)))
        self.menu_button.setIconSize(QtCore.QSize(16, 16))

    def toggle_maximized(self) -> None:
        window = self.window()
        if window.isMaximized():
            window.showNormal()
        else:
            window.showMaximized()
        self.buttons["maximize"].setToolTip(
            "Восстановить" if window.isMaximized() else "Развернуть")

    # Перетаскивание окна за шапку — средствами оконной системы (работает в X11 и Wayland).
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        handle = self.window().windowHandle()
        if not self.native and event.button() == Qt.MouseButton.LeftButton and handle is not None:
            handle.startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        if not self.native and event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
