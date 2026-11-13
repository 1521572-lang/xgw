"""Единая точка импорта Qt.

Основная привязка — PySide6. Если её нет, берётся PyQt6: код пакета пишется в общем
подмножестве обеих (полные имена перечислений, `exec()`, `Signal`/`Slot`/`Property` отсюда).
"""

import os

try:
    if os.environ.get("XGW_UI_QT") == "PyQt6":
        raise ImportError("XGW native pages use PyQt6")
    from PySide6 import QtCore, QtGui, QtSvg, QtWidgets
    from PySide6.QtCore import Property, Signal, Slot

    BINDING = "PySide6"
except ImportError:  # pragma: no cover - зависит от машины
    from PyQt6 import QtCore, QtGui, QtSvg, QtWidgets
    from PyQt6.QtCore import pyqtProperty as Property
    from PyQt6.QtCore import pyqtSignal as Signal
    from PyQt6.QtCore import pyqtSlot as Slot

    BINDING = "PyQt6"

Qt = QtCore.Qt

__all__ = ["BINDING", "Property", "Qt", "QtCore", "QtGui", "QtSvg", "QtWidgets", "Signal", "Slot"]
