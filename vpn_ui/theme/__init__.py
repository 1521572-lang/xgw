"""Текущая тема окна: палитра, шрифты и оповещение виджетов о смене."""
from __future__ import annotations

from ..qt import QtCore, QtGui, Signal
from . import tokens
from .tokens import Color, Palette, TextStyle


class ThemeManager(QtCore.QObject):
    """Хранит выбранную палитру. Рисующие сами виджеты слушают `changed`."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.palette: Palette = tokens.DARK
        self._family: str | None = None

    def set_theme(self, name: str) -> None:
        palette = tokens.PALETTES.get(name, tokens.DARK)
        if palette is not self.palette:
            self.palette = palette
            self.changed.emit()

    def family(self) -> str:
        """Первый из списка шрифтов, который есть в системе."""
        if self._family is None:
            known = set(QtGui.QFontDatabase.families())
            self._family = next((name for name in tokens.FONT_FAMILIES if name in known),
                                QtGui.QFont().defaultFamily())
        return self._family


_manager: ThemeManager | None = None


def manager() -> ThemeManager:
    global _manager
    if _manager is None:
        _manager = ThemeManager()
    return _manager


def palette() -> Palette:
    return manager().palette


def qcolor(color: Color) -> QtGui.QColor:
    return QtGui.QColor(color.r, color.g, color.b, round(color.a * 255))


def font(style: TextStyle) -> QtGui.QFont:
    result = QtGui.QFont(manager().family())
    result.setPixelSize(style.size)
    result.setWeight(QtGui.QFont.Weight(style.weight))
    return result


__all__ = ["ThemeManager", "font", "manager", "palette", "qcolor", "tokens"]
