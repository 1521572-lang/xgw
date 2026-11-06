"""Светлая и тёмная тема окна XGW: палитра Qt и одна таблица стилей (QSS) по токенам цвета.

По умолчанию — тема системы. В Qt 6.5+ её говорит QStyleHints.colorScheme(); в Ubuntu 24.04 Qt
6.4, и тогда — настройка GNOME `color-scheme` (gsettings) либо яркость системной палитры (KDE
передаёт свою палитру Qt-программам сам). Состояние окно всегда пишет и словом, и значком —
цвет только подсказка.
"""

from __future__ import annotations

import shutil
import subprocess

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

THEMES = ("system", "light", "dark")
THEME_NAMES = {"system": "Как в системе", "light": "Светлая", "dark": "Тёмная"}

LIGHT = {
    "bg": "#f3f4f6", "surface": "#ffffff", "surface2": "#eef0f3", "border": "#d9dde3",
    "text": "#1b1e23", "muted": "#58606c", "accent": "#2b67c9", "accent_text": "#ffffff",
    "ok": "#1d7f46", "warn": "#9a6200", "bad": "#bf2a20", "off": "#626a75", "focus": "#2b67c9",
    "nav": "#e9ecf0", "selected": "#d6e2f7",
}
DARK = {
    "bg": "#15171b", "surface": "#1e2127", "surface2": "#262a31", "border": "#363c45",
    "text": "#e7e9ed", "muted": "#a3aab6", "accent": "#6f9fff", "accent_text": "#0e1116",
    "ok": "#53c48a", "warn": "#e2a83b", "bad": "#ff7468", "off": "#9aa1ab", "focus": "#8fb5ff",
    "nav": "#1a1d22", "selected": "#2b3a55",
}


def _gnome_dark() -> bool | None:
    tool = shutil.which("gsettings")
    if tool is None:
        return None
    try:
        found = subprocess.run([tool, "get", "org.gnome.desktop.interface", "color-scheme"],
                               capture_output=True, text=True, timeout=2.0)
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = found.stdout.strip().strip("'")
    if found.returncode != 0 or not value:
        return None
    return value == "prefer-dark"


def system_dark(app: QApplication) -> bool:
    hints = app.styleHints()
    scheme = getattr(hints, "colorScheme", None)
    if scheme is not None:  # Qt 6.5+
        from PyQt6.QtCore import Qt

        value = scheme()
        if value == Qt.ColorScheme.Dark:
            return True
        if value == Qt.ColorScheme.Light:
            return False
    gnome = _gnome_dark()
    if gnome is not None:
        return gnome
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def tokens(app: QApplication, choice: str) -> dict[str, str]:
    if choice == "system":
        # Тема системы — по палитре до первой своей: после apply палитра уже наша.
        known = app.property("xgw_system_dark")
        if known is None:
            known = system_dark(app)
            app.setProperty("xgw_system_dark", known)
        dark = bool(known)
    else:
        dark = choice == "dark"
    return DARK if dark else LIGHT


def palette(colors: dict[str, str]) -> QPalette:
    result = QPalette()
    role = QPalette.ColorRole
    for name, key in (
        (role.Window, "bg"), (role.WindowText, "text"), (role.Base, "surface"),
        (role.AlternateBase, "surface2"), (role.Text, "text"), (role.Button, "surface2"),
        (role.ButtonText, "text"), (role.Highlight, "accent"),
        (role.HighlightedText, "accent_text"), (role.ToolTipBase, "surface"),
        (role.ToolTipText, "text"), (role.PlaceholderText, "muted"), (role.Link, "accent"),
    ):
        result.setColor(name, QColor(colors[key]))
    disabled = QPalette.ColorGroup.Disabled
    for name in (role.WindowText, role.Text, role.ButtonText):
        result.setColor(disabled, name, QColor(colors["muted"]))
    return result


def stylesheet(c: dict[str, str]) -> str:
    """Таблица стилей. Размеры — в pt и em, не в пикселях: при масштабе 100–200 % Qt
    пересчитывает их сам."""
    return f"""
QMainWindow, QWidget#page {{ background: {c['bg']}; }}
QWidget#topbar {{ background: {c['surface']}; border-bottom: 1px solid {c['border']}; }}
QListWidget#nav {{
    background: {c['nav']}; border: none; border-right: 1px solid {c['border']};
    padding: 6px; outline: none;
}}
QListWidget#nav::item {{ padding: 8px 10px; border-radius: 6px; color: {c['text']}; }}
QListWidget#nav::item:selected {{ background: {c['selected']}; color: {c['text']}; }}
QListWidget#nav:focus {{ border-right: 2px solid {c['focus']}; }}
QWidget#navfoot {{ background: {c['nav']}; border-right: 1px solid {c['border']}; }}
QFrame#card {{
    background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px;
}}
QLabel#cardTitle {{ font-weight: 600; color: {c['muted']}; }}
QLabel#heroTitle {{ font-size: 18pt; font-weight: 600; }}
QLabel#muted, QLabel[role="muted"] {{ color: {c['muted']}; }}
QLabel[tone="ok"] {{ color: {c['ok']}; }}
QLabel[tone="warn"] {{ color: {c['warn']}; }}
QLabel[tone="bad"] {{ color: {c['bad']}; }}
QLabel[tone="off"] {{ color: {c['off']}; }}
QLabel#chip {{
    border: 1px solid {c['border']}; border-radius: 12px; padding: 2px 10px;
    background: {c['surface2']}; font-weight: 600;
}}
QPushButton {{
    background: {c['surface2']}; color: {c['text']}; border: 1px solid {c['border']};
    border-radius: 6px; padding: 6px 14px;
}}
QPushButton:hover {{ border-color: {c['accent']}; }}
QPushButton:focus {{ border: 2px solid {c['focus']}; }}
QPushButton:disabled {{ color: {c['muted']}; }}
QPushButton#primary {{
    background: {c['accent']}; color: {c['accent_text']}; border: 1px solid {c['accent']};
    font-weight: 600;
}}
QPushButton#power {{ font-size: 12pt; font-weight: 600; padding: 10px 22px; border-radius: 8px; }}
QPushButton#power[tone="ok"] {{
    background: {c['ok']}; color: {c['surface']}; border-color: {c['ok']}; }}
QPushButton#power[tone="warn"] {{
    background: {c['warn']}; color: {c['surface']}; border-color: {c['warn']}; }}
QPushButton#power[tone="bad"] {{
    background: {c['bad']}; color: {c['surface']}; border-color: {c['bad']}; }}
QPushButton#power:focus {{ border: 3px solid {c['focus']}; }}
QComboBox {{ padding: 4px 8px; border: 1px solid {c['border']}; border-radius: 6px;
    background: {c['surface']}; color: {c['text']}; }}
QComboBox:focus {{ border: 2px solid {c['focus']}; }}
QStatusBar {{ background: {c['surface']}; border-top: 1px solid {c['border']}; }}
"""


def apply(app: QApplication, choice: str) -> dict[str, str]:
    """Применить тему ко всему приложению; вернуть её токены (для значков)."""
    if choice not in THEMES:
        choice = "system"
    colors = tokens(app, choice)
    if app.property("xgw_system_dark") is None:
        app.setProperty("xgw_system_dark", system_dark(app))
    app.setStyle("Fusion")  # одинаковые элементы в GNOME и KDE; цвета — из палитры
    app.setPalette(palette(colors))
    app.setStyleSheet(stylesheet(colors))
    return colors
