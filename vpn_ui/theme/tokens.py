"""Цвета, шрифты и размеры из DESIGN_TOKENS.json (обе темы). Qt здесь не нужен.

Размеры — в логических единицах XAML. Эталонный снимок окна снят при масштабе 125 %,
поэтому измеренные на нём пиксели делятся на 1,25 (REFERENCE_SCALE).
Значения с пометкой «замер» в токенах отсутствуют (акриловые кисти) и сняты со снимка.
"""
from __future__ import annotations

from dataclasses import dataclass

REFERENCE_SCALE = 1.25


@dataclass(frozen=True)
class Color:
    r: int
    g: int
    b: int
    a: float = 1.0

    @property
    def qss(self) -> str:
        return f"rgba({self.r}, {self.g}, {self.b}, {self.a:.3f})"

    @property
    def hex(self) -> str:
        return f"#{self.r:02X}{self.g:02X}{self.b:02X}"

    def alpha(self, a: float) -> Color:
        return Color(self.r, self.g, self.b, a)


def rgb(value: str, a: float = 1.0) -> Color:
    value = value.lstrip("#")
    return Color(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), a)


@dataclass(frozen=True)
class Palette:
    name: str
    # фоны
    bg_norm: Color  # BackgroundNormColorBrush
    bg_weak: Color  # BackgroundWeakColorBrush
    bg_strong: Color  # BackgroundStrongColorBrush
    bg_weak_hover: Color  # BackgroundWeakHoverColorBrush
    pane: Color  # акрил панелей — замер
    map_sea: Color  # фон под картой — замер
    map_land: Color  # замер (CountryFillBrush с прозрачностью карты)
    map_outline: Color
    backdrop: Color  # BackdropNormColorBrush
    # взаимодействие
    fill: Color  # InteractionDefaultColorBrush
    fill_hover: Color  # InteractionDefaultHoverColorBrush
    fill_active: Color  # InteractionDefaultActiveColorBrush
    fill_selected: Color  # выбранный пункт и поле поиска — замер
    weak: Color  # InteractionWeakColorBrush
    weak_hover: Color
    weak_active: Color
    weak_danger_hover: Color  # InteractionWeakDangerHoverColorBrush
    weak_danger_active: Color
    primary: Color  # InteractionNormColorBrush (кнопка «Подключить»)
    primary_hover: Color
    primary_active: Color
    link: Color  # LinkNormColorBrush / PrimaryColorBrush
    # текст
    text: Color
    text_weak: Color
    text_hint: Color
    text_disabled: Color
    text_invert: Color
    text_on_primary: Color
    # рамки
    border_weak: Color
    border_norm: Color
    border_focus: Color
    # сигналы
    danger: Color
    warning: Color
    success: Color
    vpn_green: Color
    # графика
    chart_down: Color
    chart_up: Color
    caption_close_hover: Color


DARK = Palette(
    name="dark",
    bg_norm=rgb("#16141C"), bg_weak=rgb("#292733"), bg_strong=rgb("#3F3B4C"),
    bg_weak_hover=rgb("#3F3D48"),
    pane=rgb("#16141C", 0.50), map_sea=rgb("#24222D"), map_land=rgb("#34303F"),
    map_outline=rgb("#595368"), backdrop=rgb("#000000", 0.478),
    fill=rgb("#FFFFFF", 0.051), fill_hover=rgb("#FFFFFF", 0.102), fill_active=rgb("#FFFFFF", 0.2),
    fill_selected=rgb("#FFFFFF", 0.16),
    weak=rgb("#4A4658"), weak_hover=rgb("#5C5969"), weak_active=rgb("#6E6B79"),
    weak_danger_hover=rgb("#995B70"), weak_danger_active=rgb("#A4667A"),
    primary=rgb("#6D4AFF"), primary_hover=rgb("#7C5CFF"), primary_active=rgb("#8A6EFF"),
    link=rgb("#9880FF"),
    text=rgb("#FFFFFF"), text_weak=rgb("#FFFFFF", 0.702), text_hint=rgb("#FFFFFF", 0.502),
    text_disabled=rgb("#FFFFFF", 0.302), text_invert=rgb("#1C1B24"),
    text_on_primary=rgb("#FFFFFF"),
    border_weak=rgb("#FFFFFF", 0.102), border_norm=rgb("#FFFFFF", 0.2),
    border_focus=rgb("#6D4AFF"),
    danger=rgb("#F7607B"), warning=rgb("#FFAD33"), success=rgb("#4BB99D"),
    vpn_green=rgb("#2CFFCC"),
    chart_down=rgb("#4BB99D"), chart_up=rgb("#F7607B"), caption_close_hover=rgb("#C42B1C"),
)

LIGHT = Palette(
    name="light",
    bg_norm=rgb("#FFFFFF"), bg_weak=rgb("#F5F4F2"), bg_strong=rgb("#E5E4E1"),
    bg_weak_hover=rgb("#E3E2E1"),
    pane=rgb("#FFFFFF", 0.72), map_sea=rgb("#F5F4F2"), map_land=rgb("#E5E5E6"),
    map_outline=rgb("#BCBCC3"), backdrop=rgb("#0C0C14", 0.322),
    fill=rgb("#0C0C14", 0.039), fill_hover=rgb("#0C0C14", 0.078),
    fill_active=rgb("#0C0C14", 0.122), fill_selected=rgb("#0C0C14", 0.09),
    weak=rgb("#E5E4E1"), weak_hover=rgb("#D4D3D1"), weak_active=rgb("#CAC9C8"),
    weak_danger_hover=rgb("#E1C1C7"), weak_danger_active=rgb("#D1B1B8"),
    primary=rgb("#6D4AFF"), primary_hover=rgb("#6243E6"), primary_active=rgb("#573BCC"),
    link=rgb("#6D4AFF"),
    text=rgb("#0C0C14"), text_weak=rgb("#0C0C14", 0.702), text_hint=rgb("#0C0C14", 0.502),
    text_disabled=rgb("#0C0C14", 0.302), text_invert=rgb("#FFFFFF"),
    text_on_primary=rgb("#FFFFFF"),
    border_weak=rgb("#0C0C14", 0.078), border_norm=rgb("#0C0C14", 0.161),
    border_focus=rgb("#6D4AFF"),
    danger=rgb("#B71432"), warning=rgb("#FF9900"), success=rgb("#1EA885"),
    vpn_green=rgb("#1C9C7C"),
    chart_down=rgb("#1EA885"), chart_up=rgb("#B71432"), caption_close_hover=rgb("#C42B1C"),
)

PALETTES = {"dark": DARK, "light": LIGHT}

# Цвет верхнего свечения по состоянию: GradientUnprotected/Connecting/Protected/Warning.
STATE_GLOW = {
    "disconnected": rgb("#F7607B", 0.502),
    "connecting": rgb("#FFFFFF", 0.502),
    "connected": rgb("#2CFFCC", 0.502),
    "error": rgb("#FFAD33", 0.502),
}

# Шрифт эталона — Segoe UI Variable; в Ubuntu его нет, дальше — близкие по метрикам.
FONT_FAMILIES = ("Segoe UI Variable Display", "Segoe UI", "Inter", "Ubuntu Sans", "Ubuntu",
                 "Noto Sans", "DejaVu Sans")


@dataclass(frozen=True)
class TextStyle:
    size: int  # px
    line: int  # px
    weight: int  # 400 обычный, 600 полужирный


# typography_text_styles
TITLE = TextStyle(28, 40, 600)  # TitleTextBlockStyle
SUBTITLE = TextStyle(20, 28, 600)  # SubtitleTextBlockStyle
BODY_LARGE_STRONG = TextStyle(18, 24, 600)
BODY_MEDIUM_STRONG = TextStyle(16, 24, 600)  # BodyMediumStrongTextBlockStyle
BODY_MEDIUM = TextStyle(16, 24, 400)
BODY_STRONG = TextStyle(14, 20, 600)  # BodyStrongTextBlockStyle
BODY = TextStyle(14, 20, 400)
CAPTION_STRONG = TextStyle(12, 16, 600)
CAPTION = TextStyle(12, 16, 400)


class Metrics:
    """Размеры в логических единицах (эталон 1252×813 при 125 % = 1002×650)."""

    WINDOW = (1002, 650)
    WINDOW_MIN = (566, 609)  # MainWindow.xaml
    TITLE_BAR = 38  # MainTitleBarHeight
    CAPTION_BUTTON = (46, 32)
    MENU_BUTTON = 26
    EDGE = 8  # поля главной сетки и зазор между колонками
    RESIZE_GRIP = 6

    SIDEBAR = 280  # SidebarWidth по умолчанию (200..400)
    SIDEBAR_COMPACT = 62  # SidebarCompactWidth
    SIDEBAR_BREAK = 885  # уже — боковая панель сворачивается
    WIDGETS = 110
    WIDGETS_COMPACT = 72
    WIDGETS_BREAK = 1000  # уже — панель виджетов без подписей
    DETAILS_BREAK = 900  # ConnectionDetailsPage: широкая и узкая раскладка
    CONTENT_MAX = 856  # MaximumHomePageContentWidth

    PANE_RADIUS = 8
    PANE_PADDING = 8
    CONTROL_RADIUS = 4
    ROW_RADIUS = 8

    SEARCH_HEIGHT = 36
    NAV_ITEM = 34
    PIVOT_HEIGHT = 35
    NOTICE_HEIGHT = 105
    ROW_FASTEST = 43
    ROW_COUNTRY = 48
    ROW_SERVER = 40
    FLAG = (30, 20)  # ComplexCountryFlag
    FLAG_SMALL = (24, 16)  # MainFlagWidth × MainFlagHeight
    CARD_FLAG = (54, 36)  # ConnectionCardFlagWidth × Height

    CONNECT_BUTTON = (250, 39)  # MinButtonSpaceWidth × высота LargePrimaryButton
    CONNECT_BUTTON_MIN = 180
    WIDGET_TILE = 66  # одна строка подписи
    WIDGET_TILE_TALL = 82  # две строки
    WIDGET_TILE_COMPACT = 44
    WIDGET_ICON = 28
    DETAIL_ROW = 54
    STATUS_ROW = 20
    CHART_HEIGHT = 70  # SpeedChartControl

    GLOW_HEIGHT = 332  # ConnectionStatusGradientHeight
    FADE_HEIGHT = 264  # ConnectionDetailsGradientHeight
    MAP_SCALE = 2.9  # логических точек на единицу карты (замер по снимку)

    TOGGLE = (40, 20)  # ToggleSwitchMinWidth × MinHeight
    SETTINGS_CARD = 54  # SettingsCardMinHeight
    DRAWER = 420
