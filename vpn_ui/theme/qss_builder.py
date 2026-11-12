"""Глобальный QSS из токенов темы: фоны, кнопки, поля, полосы прокрутки и типографика.

То, что QSS не умеет (переключатель, график, кольцо, плитки, строки списка), рисуют сами
виджеты через QPainter и берут те же токены.
"""
from __future__ import annotations

from .tokens import (
    BODY,
    BODY_MEDIUM_STRONG,
    BODY_STRONG,
    CAPTION,
    CAPTION_STRONG,
    SUBTITLE,
    TITLE,
    Metrics,
    Palette,
    TextStyle,
)


def _font(style: TextStyle) -> str:
    return f"font-size: {style.size}px; font-weight: {style.weight};"


def build(colors: Palette, family: str, arrow_image: str = "") -> str:
    """`arrow_image` — путь к перекрашенной стрелке выпадающего списка (PNG)."""
    c = colors
    pane = f"background: {c.pane.qss}; border: 1px solid {c.border_weak.qss};" \
           f" border-radius: {Metrics.PANE_RADIUS}px;"
    arrow = f"image: url({arrow_image});" if arrow_image else ""
    return f"""
* {{ font-family: "{family}"; outline: 0; }}
QWidget#MainWindow {{ background: {c.bg_norm.qss}; }}
QLabel {{ color: {c.text.qss}; background: transparent; {_font(BODY)} }}
QToolTip {{ background: {c.bg_strong.qss}; color: {c.text.qss};
    border: 1px solid {c.border_weak.qss}; padding: 4px 8px; {_font(CAPTION)} }}
QToolButton {{ background: transparent; border: none; border-radius: {Metrics.CONTROL_RADIUS}px; }}
QToolButton:hover {{ background: {c.fill_hover.qss}; }}
QToolButton:pressed {{ background: {c.fill_active.qss}; }}
QToolButton:focus {{ border: 2px solid {c.border_focus.qss}; }}

QWidget#TitleBar {{ background: transparent; }}
QLabel#TitleLabel {{ color: {c.text.alpha(0.85).qss}; {_font(CAPTION_STRONG)} }}

QFrame#SidebarPane, QFrame#WidgetPane {{ {pane} }}
QFrame#WidgetSeparator {{ background: {c.border_weak.qss}; border: none; }}
QFrame#SearchBox {{ background: {c.fill_selected.qss}; border: none;
    border-bottom: 2px solid transparent; border-radius: {Metrics.CONTROL_RADIUS}px; }}
QFrame#SearchBox[focused="true"] {{ border-bottom: 2px solid {c.primary_active.qss}; }}
QLineEdit#SearchEdit {{ background: transparent; border: none; color: {c.text.qss};
    {_font(BODY)} selection-background-color: {c.primary.qss};
    selection-color: {c.text_on_primary.qss}; }}
QLabel#SearchShortcut, QLabel#HotkeyLabel {{ color: {c.text_hint.qss}; {_font(CAPTION)} }}
QToolButton#CompactSearch {{ background: {c.fill.qss}; }}
QToolButton#CompactSearch:hover {{ background: {c.fill_hover.qss}; }}
QLabel#ListHeader {{ color: {c.text_weak.qss}; {_font(BODY)} }}
QLabel#EmptyLabel {{ color: {c.text_hint.qss}; padding: 24px 0; {_font(BODY)} }}
QFrame#NoticeCard {{ background: {c.fill.qss}; border: 1px solid {c.border_weak.qss};
    border-radius: {Metrics.ROW_RADIUS}px; }}
QFrame#NoticeBubble {{ background: {c.fill_hover.qss}; border: none; border-radius: 20px; }}
QLabel#NoticeText {{ {_font(BODY_STRONG)} }}
QScrollArea#ServerScroll, QScrollArea#DrawerScroll, QWidget#ServerList, QWidget#DrawerBody {{
    background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {c.fill_active.qss}; border-radius: 3px;
    min-height: 28px; margin: 0 0 0 2px; }}
QScrollBar::handle:vertical:hover {{ background: {c.text_hint.qss}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; border: none; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QLabel#CardTitle {{ {_font(TITLE)} }}
QLabel#CardSubtitle {{ color: {c.text_weak.qss}; {_font(BODY_MEDIUM_STRONG)} }}
QLabel#ProtocolPill {{ background: {c.fill.qss}; color: {c.text_weak.qss};
    border: 1px solid {c.border_weak.qss}; border-radius: 6px; padding: 2px 8px;
    {_font(CAPTION_STRONG)} }}
QPushButton#ConnectButton, QPushButton#CancelButton, QPushButton#DisconnectButton {{
    border: 2px solid transparent; border-radius: {Metrics.CONTROL_RADIUS}px; padding: 0 22px;
    {_font(BODY_MEDIUM_STRONG)} }}
QPushButton#ConnectButton {{ background: {c.primary.qss}; color: {c.text_on_primary.qss}; }}
QPushButton#ConnectButton:hover {{ background: {c.primary_hover.qss}; }}
QPushButton#ConnectButton:pressed {{ background: {c.primary_active.qss}; }}
QPushButton#ConnectButton:focus {{ border: 2px solid {c.text.qss}; }}
QPushButton#CancelButton, QPushButton#DisconnectButton {{ background: {c.weak.qss};
    color: {c.text.qss}; }}
QPushButton#CancelButton:hover, QPushButton#DisconnectButton:hover {{
    background: {c.weak_danger_hover.qss}; }}
QPushButton#CancelButton:pressed, QPushButton#DisconnectButton:pressed {{
    background: {c.weak_danger_active.qss}; }}
QPushButton#CancelButton:focus, QPushButton#DisconnectButton:focus {{
    border: 2px solid {c.border_focus.qss}; }}
QFrame#ErrorBar {{ background: {c.bg_weak.qss}; border: 1px solid {c.border_weak.qss};
    border-radius: {Metrics.ROW_RADIUS}px; }}
QLabel#ErrorText {{ {_font(BODY)} }}

QLabel#StatusTitle {{ {_font(BODY_STRONG)} }}
QLabel#StatusDescription {{ color: {c.text_weak.qss}; {_font(BODY)} }}
QFrame#SpeedPanel {{ background: transparent; border: none;
    border-radius: {Metrics.ROW_RADIUS}px; }}
QLabel#SpeedUnit {{ color: {c.text_weak.qss}; {_font(CAPTION)} }}
QLabel#SpeedValue {{ {_font(CAPTION_STRONG)} }}

QFrame#SettingsDrawer {{ background: {c.bg_norm.qss}; border: 1px solid {c.border_weak.qss};
    border-radius: {Metrics.PANE_RADIUS}px; }}
QLabel#DrawerTitle {{ {_font(SUBTITLE)} }}
QLabel#SectionTitle {{ color: {c.text_weak.qss}; {_font(BODY_STRONG)} }}
QFrame#SettingsCard {{ background: {c.fill.qss}; border: none;
    border-radius: {Metrics.CONTROL_RADIUS}px; }}
QFrame#SettingsCard:hover {{ background: {c.fill_hover.qss}; }}
QLabel#SettingsTitle {{ {_font(BODY)} }}
QLabel#SettingsAbout {{ color: {c.text_weak.qss}; {_font(CAPTION)} }}
QRadioButton#ProtocolRadio {{ spacing: 0; background: transparent; }}
QRadioButton#ProtocolRadio::indicator {{ width: 16px; height: 16px; border-radius: 9px;
    border: 1px solid {c.text_weak.qss}; background: transparent; }}
QRadioButton#ProtocolRadio::indicator:hover {{ border: 1px solid {c.text.qss}; }}
QRadioButton#ProtocolRadio::indicator:checked {{ width: 8px; height: 8px;
    border: 5px solid {c.primary.qss}; background: {c.text_on_primary.qss}; }}
QRadioButton#ProtocolRadio:focus {{ border: 2px solid {c.border_focus.qss}; border-radius: 6px; }}
QComboBox#SettingsCombo {{ background: {c.fill_hover.qss}; color: {c.text.qss};
    border: 1px solid {c.border_weak.qss}; border-radius: {Metrics.CONTROL_RADIUS}px;
    padding: 5px 10px; min-height: 20px; {_font(BODY)} }}
QComboBox#SettingsCombo:hover {{ background: {c.fill_active.qss}; }}
QComboBox#SettingsCombo:focus {{ border: 1px solid {c.border_focus.qss}; }}
QComboBox#SettingsCombo::drop-down {{ border: none; width: 28px; }}
QComboBox#SettingsCombo::down-arrow {{ {arrow} width: 16px; height: 16px; }}
QComboBox QAbstractItemView {{ background: {c.bg_weak.qss}; color: {c.text.qss};
    border: 1px solid {c.border_weak.qss}; selection-background-color: {c.bg_strong.qss};
    selection-color: {c.text.qss}; padding: 4px; {_font(BODY)} }}
QLineEdit#DnsEdit {{ background: {c.fill.qss}; color: {c.text.qss};
    border: 1px solid {c.border_norm.qss}; border-radius: {Metrics.CONTROL_RADIUS}px;
    padding: 6px 10px; {_font(BODY)} selection-background-color: {c.primary.qss}; }}
QLineEdit#DnsEdit:focus {{ border: 1px solid {c.border_focus.qss}; }}

QMenu {{ background: {c.bg_weak.qss}; color: {c.text.qss};
    border: 1px solid {c.border_weak.qss}; padding: 4px; {_font(BODY)} }}
QMenu::item {{ padding: 8px 28px 8px 12px; border-radius: {Metrics.CONTROL_RADIUS}px; }}
QMenu::item:selected {{ background: {c.bg_strong.qss}; }}
QMenu::separator {{ height: 1px; background: {c.border_weak.qss}; margin: 4px 8px; }}
"""
