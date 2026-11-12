"""Светлая тема окна XGW (единственная): палитра Qt и одна таблица стилей (QSS) по токенам цвета.

Вид следует Proton VPN для Windows: навигация с подписями, карта во всю область «Обзора»,
поверх неё — карточка подключения с крупной кнопкой; состояние защиты — значком, словом и
цветным свечением сверху. Остальные разделы — белые карточки на сером фоне.

Палитра — Proton Light: белые поверхности, пурпурный акцент #6D4AFF, сигнальные цвета с
затемнением под контраст на белом. Состояние окно всегда пишет и словом, и значком — цвет
только подсказка.

Правило Qt: скругление больше половины высоты виджета не рисуется вовсе (углы выходят
прямыми), поэтому у кнопок и меток радиусы малы, а высота задана явно.
"""

from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

THEMES = ("light",)
THEME_NAMES = {"light": "Светлая"}

LIGHT = {
    # bg — фон страниц, panel — навигация и список серверов, surface — карточки и поля,
    # surface2 — слабая заливка (кнопки, наведение), accent — interaction-norm Proton
    # (текст на нём белый), ok/warn/bad — signal-* с затемнением ради контраста на белом,
    # off — выключено, busy — идёт работа, selected — акцент ~12 % на белом.
    "bg": "#f6f5fa", "panel": "#ffffff", "surface": "#ffffff", "surface2": "#f0eff5",
    "border": "#e4e2eb", "text": "#1b1a24", "muted": "#6c6a7b", "accent": "#6d4aff",
    "accent_hover": "#5b3ce6", "accent_text": "#ffffff", "ok": "#128369", "warn": "#9d6400",
    "bad": "#c42f50", "off": "#9a97a8", "busy": "#7a5cff", "focus": "#6d4aff",
    "nav": "#ffffff", "selected": "#efeaff",
    "map_bg": "#f4f2fa", "map_land": "#e1ddee", "map_border": "#f4f2fa",
    "map_selected": "#c3b3f7",
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
        result.setColor(disabled, name, QColor(colors["off"]))
    return result


def _tones(c: dict[str, str]) -> str:
    rules = []
    for tone in TONES:
        color = c[tone]
        rules += [
            f'QLabel[tone="{tone}"] {{ color: {color}; }}',
            f'QFrame#alert[tone="{tone}"] {{ border: 1px solid {mix(color, c["surface"], 0.35)}; '
            f'background: {mix(color, c["surface"], 0.07)}; }}',
            f'QLabel#dot[tone="{tone}"] {{ background: {color}; }}',
            f'QLabel#pill[tone="{tone}"] {{ color: {color}; '
            f'background: {mix(color, c["surface"], 0.13)}; }}',
            f'QLabel#chip[tone="{tone}"] {{ color: {color}; '
            f'background: {mix(color, c["surface"], 0.10)}; }}',
            f'QPushButton#linkRow[tone="{tone}"] {{ color: '
            f'{c["text"] if tone == "off" else color}; }}',
        ]
    return NL.join(rules)


def stylesheet(c: dict[str, str]) -> str:
    """Таблица стилей. Шрифты — в pt: при масштабе 100–200 % Qt пересчитывает их сам."""
    hover = mix(c["accent"], c["surface"], 0.06)
    return f"""
QMainWindow, QWidget#page, QScrollArea {{ background: {c['bg']}; }}
QWidget {{ color: {c['text']}; }}
QWidget#rail {{ background: {c['nav']}; border-right: 1px solid {c['border']}; }}
QLabel#brand {{ color: {c['text']}; font-size: 14pt; font-weight: 700; }}
QToolButton#navButton {{
    color: {c['muted']}; background: transparent; border: 1px solid transparent;
    border-radius: 8px; padding: 6px 10px; font-size: 10.5pt; font-weight: 500;
    text-align: left;
}}
QToolButton#navButton:hover {{ background: {c['surface2']}; color: {c['text']}; }}
QToolButton#navButton:checked {{ background: {c['selected']}; color: {c['accent']};
    font-weight: 700; }}
QToolButton#navButton:focus {{ border: 1px solid {c['focus']}; }}
QToolButton#navButton::menu-indicator {{ image: none; width: 0; }}
QWidget#serverPanel {{ background: {c['panel']}; }}
QScrollArea#serverScroll {{ background: {c['panel']}; border: none;
    border-right: 1px solid {c['border']}; }}
QFrame#conn {{ background: {c['map_bg']}; border: none; }}
QWidget#connectionContent {{ background: transparent; }}
QFrame#connCard, QFrame#featureTile {{
    background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 14px;
}}
QFrame#featureTile {{ border-radius: 12px; }}
QFrame#divider {{ background: {c['border']}; border: none; max-height: 1px; min-height: 1px; }}
QFrame#card, QFrame#alert {{
    background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px;
}}
QFrame#alert {{ border-radius: 10px; }}
QFrame#metric {{ background: transparent; border: none; }}
QFrame#row {{ background: {c['surface']}; border: 1px solid transparent; border-radius: 10px; }}
QFrame#row:hover {{ background: {c['surface2']}; }}
QFrame#row:focus {{ border: 1px solid {c["focus"]}; }}
QFrame#row[main="true"] {{ background: {c['selected']}; }}
QLabel#shieldWord {{ font-size: 16pt; font-weight: 700; }}
QLabel#heroSub {{ color: {c['muted']}; font-size: 10.5pt; }}
QLabel#heroTitle {{ font-size: 15pt; font-weight: 700; }}
QLabel#pageTitle {{ font-size: 16pt; font-weight: 700; }}
QLabel#listTitle {{ font-size: 13pt; font-weight: 700; }}
QLabel#serverName {{ font-size: 12pt; font-weight: 600; }}
QLabel#rowName {{ font-size: 10.5pt; font-weight: 600; }}
QLabel#rowSpeed {{ font-size: 10pt; font-weight: 600; }}
QLabel#metricValue {{ font-size: 15pt; font-weight: 700; }}
QLabel#metricTitle, QLabel#section {{ color: {c['muted']}; font-size: 8.5pt; font-weight: 700; }}
QLabel#cardTitle {{ font-weight: 600; font-size: 11pt; }}
QLabel#tileValue {{ font-weight: 600; font-size: 10pt; }}
QLabel#small {{ color: {c['muted']}; font-size: 9.5pt; }}
QLabel#muted, QLabel[role="muted"] {{ color: {c['muted']}; }}
QLabel#badge {{
    background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 10px;
    color: {c['text']}; font-weight: 700; font-size: 9.5pt;
}}
QLabel#dot {{ border-radius: 5px; min-width: 10px; max-width: 10px; min-height: 10px;
    max-height: 10px; }}
QLabel#pill {{ border-radius: 8px; padding: 2px 8px; font-size: 8.5pt; font-weight: 700;
    max-height: 16px; }}
QLabel#chip {{
    font-size: 9.5pt; border: none; border-radius: 8px; padding: 5px 10px;
    background: {c['surface2']}; font-weight: 600;
}}
{_tones(c)}
QPushButton {{
    background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']};
    border-radius: 8px; padding: 6px 14px; min-height: 20px; font-weight: 500;
}}
QPushButton:hover {{ background: {hover}; border-color: {mix(c['accent'], c['border'], 0.5)}; }}
QPushButton:pressed {{ background: {c['selected']}; }}
QPushButton:focus {{ border: 1px solid {c['focus']}; }}
QPushButton:disabled {{ color: {c['off']}; background: {c['surface2']};
    border-color: {c['border']}; }}
QPushButton#primary, QPushButton#connect[tone="off"] {{
    background: {c['accent']}; color: {c['accent_text']}; border: 1px solid {c['accent']};
    font-weight: 700;
}}
QPushButton#primary:hover, QPushButton#connect[tone="off"]:hover {{
    background: {c['accent_hover']}; border-color: {c['accent_hover']}; }}
QPushButton#connect {{
    font-size: 11.5pt; font-weight: 700; padding: 10px 18px; border-radius: 10px;
    min-height: 24px;
}}
QPushButton#connect[tone="on"] {{
    background: {c['surface2']}; color: {c['text']}; border: 1px solid {c['border']};
}}
QPushButton#connect[tone="on"]:hover {{ border-color: {c['bad']}; color: {c['bad']};
    background: {mix(c['bad'], c['surface'], 0.06)}; }}
QPushButton#connect:disabled, QPushButton#connect[tone="off"]:disabled,
QPushButton#connect[tone="on"]:disabled {{
    background: {c['surface2']}; color: {c['off']}; border: 1px solid {c['border']}; }}
QPushButton#connect:focus {{ border: 2px solid {c['text']}; }}
QPushButton#linkRow {{
    background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px;
    padding: 10px 14px; text-align: left; font-weight: 600;
}}
QPushButton#linkRow:hover {{ background: {hover}; border-color: {c['accent']}; }}
QPushButton#seg {{ border-radius: 8px; padding: 5px 14px; background: transparent;
    border: 1px solid transparent; color: {c['muted']}; font-weight: 600; }}
QPushButton#seg:hover {{ background: {c['surface2']}; color: {c['text']}; }}
QPushButton#seg:checked {{ background: {c['selected']}; color: {c['accent']};
    border-color: transparent; }}
QToolButton#iconButton {{ background: transparent; border: 1px solid transparent;
    border-radius: 8px; padding: 4px; }}
QToolButton#iconButton:hover {{ border-color: {c['border']}; background: {c['surface2']}; }}
QToolButton#iconButton:disabled {{ background: transparent; }}
QToolButton#iconButton::menu-indicator {{ image: none; width: 0; }}
QLineEdit, QPlainTextEdit, QComboBox {{ background: {c['surface']}; color: {c['text']};
    border: 1px solid {c['border']}; border-radius: 8px; padding: 6px 10px;
    selection-background-color: {c['accent']}; selection-color: {c['accent_text']}; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 1px solid {c['focus']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QProgressBar {{ background: {c['surface2']}; border: none; border-radius: 3px; }}
QProgressBar::chunk {{ background: {c['ok']}; border-radius: 3px; }}
QProgressBar[tone="warn"]::chunk {{ background: {c['warn']}; }}
QProgressBar[tone="bad"]::chunk {{ background: {c['bad']}; }}
QTextBrowser#serverDetails {{ background: {c["surface"]}; border: none; }}
QDialog, QMessageBox {{ background: {c['surface']}; }}
QMenu {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px;
    padding: 6px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['selected']}; color: {c['text']}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {mix(c['off'], c['surface'], 0.45)};
    border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['off']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QStatusBar {{ background: {c['panel']}; color: {c['muted']};
    border-top: 1px solid {c['border']}; }}
QToolTip {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']};
    border-radius: 6px; padding: 6px 9px; font-size: 9.5pt; }}
"""


def apply(app: QApplication, choice: str) -> dict[str, str]:
    """Применить тему ко всему приложению; вернуть её токены (для значков)."""
    colors = tokens(app, choice)  # тема одна: любой выбор даёт светлую
    app.setStyle("Fusion")  # одинаковые элементы в GNOME и KDE; цвета — из палитры
    app.setPalette(palette(colors))
    app.setProperty("xgw_colors", dict(colors))
    app.setStyleSheet(stylesheet(colors))
    return colors
