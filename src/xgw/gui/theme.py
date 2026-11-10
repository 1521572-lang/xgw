"""Светлая тема окна XGW (единственная): палитра Qt и одна таблица стилей (QSS) по токенам цвета.

Вид — как у современных VPN-клиентов: крупный знак защиты с подсветкой цветом состояния,
карточки со скруглением вместо таблиц, узкая навигация со значками.

Палитра — Proton Light (веб-интерфейс Proton): белые поверхности, пурпурный акцент
#6D4AFF, сигнальные цвета с затемнением под контраст на белом. Выбор «системная/тёмная»
убран вместе с переключателем в навигации. Состояние окно всегда пишет и словом, и значком —
цвет только подсказка.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

THEMES = ("light",)
THEME_NAMES = {"light": "Светлая"}

LIGHT = {
    # Proton Light: bg/surface=background-norm (#FFFFFF), surface2=background-weak (#F1F1F4),
    # border=border-weak, text=text-norm, muted=text-hint, accent=interaction-norm (#6D4AFF,
    # текст на нём белый), ok/warn/bad=signal-* (warn и bad затемнены ради контраста на белом),
    # off=text-disabled, busy=interaction-norm-active, focus=акцент, nav=рейка background-weak,
    # selected=акцент ~14% на белом. Палитра одна: тёмной темы в окне больше нет.
    "bg": "#ffffff", "panel": "#fbfbfd", "surface": "#ffffff", "surface2": "#f1f1f4",
    "border": "#e3e2e9", "text": "#1c1b24", "muted": "#716f7f", "accent": "#6d4aff",
    "accent_text": "#ffffff", "ok": "#1ea885", "warn": "#c77700", "bad": "#d93757",
    "off": "#a7a4b5", "busy": "#8a6eff", "focus": "#6d4aff", "nav": "#f1f1f4",
    "selected": "#ebe6ff",
}
TONES = ("ok", "warn", "bad", "off", "busy")
NL = chr(10)


def mix(one: str, two: str, share: float) -> str:
    """Цвет между one и two: share — доля one (0…1)."""
    a = [int(one[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(two[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * share + y * (1 - share)):02x}"
                         for x, y in zip(a, b, strict=True))


def tokens(app: QApplication, choice: str) -> dict[str, str]:
    """Токены темы. Тема одна — светлая; аргументы сохранены ради прежних вызовов."""
    return LIGHT


def current(app: QApplication | None = None) -> dict[str, str]:
    """Токены темы, применённой последней, — для виджетов, которые рисуют сами."""
    app = app or QApplication.instance()
    found = app.property("xgw_colors") if app is not None else None
    return dict(found) if isinstance(found, dict) else dict(LIGHT)


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


def _tones(c: dict[str, str]) -> str:
    rules = []
    for tone in TONES:
        color = c[tone]
        top = mix(color, c["panel"], 0.16)
        rules += [
            f'QLabel[tone="{tone}"] {{ color: {color}; }}',
            f'QFrame#conn[tone="{tone}"] {{ background: qlineargradient(x1:0, y1:0, x2:0, '
            f'y2:1, stop:0 {top}, stop:0.42 {c["panel"]}, stop:1 {c["panel"]}); }}',
            f'QFrame#alert[tone="{tone}"] {{ border-left: 4px solid {color}; '
            f'background: {mix(color, c["surface"], 0.08)}; }}',
            f'QLabel#dot[tone="{tone}"] {{ background: {color}; }}',
            f'QLabel#pill[tone="{tone}"] {{ color: {color}; '
            f'background: {mix(color, c["surface"], 0.14)}; }}',
        ]
    return NL.join(rules)


def stylesheet(c: dict[str, str]) -> str:
    """Таблица стилей. Шрифты — в pt: при масштабе 100–200 % Qt пересчитывает их сам."""
    return f"""
QMainWindow, QWidget#page, QScrollArea {{ background: {c['bg']}; }}
QWidget {{ color: {c['text']}; }}
QWidget#rail {{ background: {c['nav']}; border-right: 1px solid {c['border']}; }}
QToolButton#navButton {{
    color: {c['muted']}; background: transparent; border: none; border-radius: 12px;
    padding: 8px 2px; font-size: 9.5pt;
}}
QToolButton#navButton:hover {{ background: {c['surface2']}; color: {c['text']}; }}
QToolButton#navButton:checked {{ background: {c['selected']}; color: {c['text']};
    font-weight: 600; }}
QToolButton#navButton:focus {{ border: 2px solid {c['focus']}; }}
QToolButton#navButton::menu-indicator {{ image: none; width: 0; }}
QFrame#conn {{ background: {c['panel']}; border-right: 1px solid {c['border']}; }}
QFrame#card, QFrame#alert {{
    background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 14px;
}}
QFrame#alert {{ border-radius: 12px; }}
QFrame#metric {{
    background: {mix(c['surface2'], c['panel'], 0.7)}; border: 1px solid {c['border']};
    border-radius: 12px;
}}
QFrame#row {{
    background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px;
}}
QFrame#row:hover {{ border-color: {mix(c['accent'], c['border'], 0.5)}; }}
QFrame#row[main="true"] {{ border: 2px solid {c['accent']};
    background: {mix(c['accent'], c['surface'], 0.07)}; }}
QLabel#shieldWord {{ font-size: 10pt; font-weight: 700; }}
QLabel#heroTitle {{ font-size: 20pt; font-weight: 700; }}
QLabel#pageTitle {{ font-size: 16pt; font-weight: 700; }}
QLabel#serverName {{ font-size: 12pt; font-weight: 600; }}
QLabel#rowName, QLabel#rowSpeed {{ font-size: 11.5pt; font-weight: 600; }}
QLabel#metricValue {{ font-size: 16pt; font-weight: 700; }}
QLabel#metricTitle, QLabel#section {{ color: {c['muted']}; font-size: 9pt; font-weight: 700; }}
QLabel#cardTitle {{ font-weight: 600; font-size: 11pt; }}
QLabel#small {{ color: {c['muted']}; font-size: 10pt; }}
QLabel#muted, QLabel[role="muted"] {{ color: {c['muted']}; }}
QLabel#badge {{
    background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 18px;
    color: {c['text']}; font-weight: 700; font-size: 9.5pt;
}}
QLabel#dot {{ border-radius: 5px; min-width: 10px; max-width: 10px; min-height: 10px;
    max-height: 10px; }}
QLabel#pill {{ border-radius: 9px; padding: 2px 9px; font-size: 9pt; font-weight: 700; }}
QLabel#chip {{
    border: 1px solid {c['border']}; border-radius: 13px; padding: 3px 12px;
    background: {c['surface']}; font-weight: 600;
}}
{_tones(c)}
QPushButton {{
    background: {c['surface2']}; color: {c['text']}; border: 1px solid {c['border']};
    border-radius: 10px; padding: 7px 16px;
}}
QPushButton:hover {{ border-color: {c['accent']}; }}
QPushButton:focus {{ border: 2px solid {c['focus']}; }}
QPushButton:disabled {{ color: {c['muted']}; }}
QPushButton#primary, QPushButton#connect[tone="off"] {{
    background: {c['accent']}; color: {c['accent_text']}; border: 1px solid {c['accent']};
    font-weight: 700;
}}
QPushButton#connect {{
    font-size: 12pt; font-weight: 700; padding: 12px 22px; border-radius: 24px;
    min-height: 24px;
}}
QPushButton#connect[tone="on"] {{
    background: transparent; color: {c['text']}; border: 2px solid {c['border']};
}}
QPushButton#connect[tone="on"]:hover {{ border-color: {c['bad']}; color: {c['bad']}; }}
QPushButton#connect:disabled, QPushButton#connect[tone="off"]:disabled,
QPushButton#connect[tone="on"]:disabled {{
    background: transparent; color: {c['muted']}; border: 2px dashed {c['border']}; }}
QPushButton#connect:focus {{ border: 3px solid {c['focus']}; }}
QPushButton#seg {{ border-radius: 16px; padding: 6px 16px; background: transparent; }}
QPushButton#seg:checked {{ background: {c['selected']}; border-color: {c['accent']}; }}
QToolButton#iconButton {{ background: transparent; border: 1px solid transparent;
    border-radius: 8px; padding: 4px; }}
QToolButton#iconButton:hover {{ border-color: {c['border']}; background: {c['surface2']}; }}
QToolButton#iconButton:disabled {{ background: {c['surface2']}; }}
QToolButton#iconButton::menu-indicator {{ image: none; width: 0; }}
QLineEdit, QPlainTextEdit {{ background: {c['surface']}; color: {c['text']};
    border: 1px solid {c['border']}; border-radius: 10px; padding: 6px 10px;
    selection-background-color: {c['accent']}; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border: 2px solid {c['focus']}; }}
QProgressBar {{ background: {c['surface2']}; border: none; border-radius: 3px; }}
QProgressBar::chunk {{ background: {c['ok']}; border-radius: 3px; }}
QProgressBar[tone="warn"]::chunk {{ background: {c['warn']}; }}
QProgressBar[tone="bad"]::chunk {{ background: {c['bad']}; }}
QDialog, QMessageBox {{ background: {c['surface']}; }}
QMenu {{ background: {c['surface']}; border: 1px solid {c['border']}; padding: 6px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['selected']}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QStatusBar {{ background: {c['bg']}; color: {c['muted']}; border-top: 1px solid {c['border']}; }}
QToolTip {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']};
    padding: 4px 8px; }}
"""


def apply(app: QApplication, choice: str) -> dict[str, str]:
    """Применить тему ко всему приложению; вернуть её токены (для значков)."""
    colors = tokens(app, choice)  # тема одна: любой выбор даёт светлую
    app.setStyle("Fusion")  # одинаковые элементы в GNOME и KDE; цвета — из палитры
    app.setPalette(palette(colors))
    app.setProperty("xgw_colors", dict(colors))
    app.setStyleSheet(stylesheet(colors))
    return colors
