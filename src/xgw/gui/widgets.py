"""Виджеты окна XGW, которые рисуются сами: значки разделов, навигация, большой знак защиты,
значок страны, плитка метрики и строка сервера.

Значки нарисованы линиями в клетке 24×24 (как тонкие контурные наборы), без файлов и без
модуля SVG — в Ubuntu 24.04 с одним python3-pyqt6 его может не быть. Цвета берутся из
текущей темы (theme.current); после смены темы окно вызывает recolor().
"""

from __future__ import annotations

import html

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFontDatabase,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import model, theme

RAIL_WIDTH = 184


def label(text: str = "", *, name: str = "", wrap: bool = True) -> QLabel:
    found = QLabel(text)
    found.setWordWrap(wrap)
    found.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if name:
        found.setObjectName(name)
    return found


def tone(widget: QWidget, value: str, prop: str = "tone") -> None:
    """Свойство для таблицы стилей; стиль пересчитывается, только если оно сменилось."""
    if widget.property(prop) != value:
        widget.setProperty(prop, value)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def set_text(widget: QLabel, text: str) -> None:
    if widget.text() != text:
        widget.setText(text)


def tip(widget: QWidget, text: str) -> None:
    """Подсказка меняется, только если другой текст: опрос раз в несколько секунд не трогает
    подсказку, которую человек сейчас читает (отчёт gui-s3)."""
    if widget.toolTip() != text:
        widget.setToolTip(text)


def server_details(name: str, *, flag: str = "", code: str = "", status: str = "",
                   speed: str = "", delay: str = "", sub: str = "", note: str = "",
                   main: bool = False) -> str:
    """Карточка сервера при наведении: только сведения, уже полученные от шлюза."""
    rows = [("Состояние", status), ("Скорость", speed), ("Задержка", delay),
            ("Параметры", sub), ("Последний замер", note)]
    if main:
        rows.insert(0, ("Роль", "сервер в работе"))
    colors = theme.current()
    title = " ".join(part for part in (flag, name) if part)
    if code and code != "XX":
        title += f" · {code.upper()}"
    body = []
    for title_text, value in rows:
        if not value or value == "—":
            continue
        body.append(f"<tr><td style='color:{colors['muted']}; padding:5px 18px 5px 0'>"
                    f"{html.escape(title_text)}</td><td style='padding:5px 0'>"
                    f"<b>{html.escape(value)}</b></td></tr>")
    return (f"<html><body style='color:{colors['text']}'><div style='padding:4px'>"
            f"<div style='font-size:14pt; padding-bottom:8px'><b>{html.escape(title)}</b></div>"
            f"<table cellspacing='0' cellpadding='0'>{''.join(body)}</table></div></body></html>")


class Elided(QLabel):
    """Подпись в одну строку: не влезает — обрезается многоточием, целиком — в подсказке."""

    def __init__(self, text: str = "", name: str = "") -> None:
        super().__init__(text)
        if name:
            self.setObjectName(name)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setFont(self.font())
        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight,
                                             rect.width())
        painter.drawText(rect, int(self.alignment()), text)
        painter.end()


# --- значки ------------------------------------------------------------------------------------


def _shield(path: QPainterPath, x: float = 0, y: float = 0, k: float = 1.0) -> None:
    def p(px: float, py: float) -> QPointF:
        return QPointF(x + px * k, y + py * k)

    path.moveTo(p(12, 2.8))
    path.lineTo(p(19.5, 5.8))
    path.lineTo(p(19.5, 11.5))
    path.cubicTo(p(19.5, 16.2), p(16.3, 19.6), p(12, 21.2))
    path.cubicTo(p(7.7, 19.6), p(4.5, 16.2), p(4.5, 11.5))
    path.lineTo(p(4.5, 5.8))
    path.closeSubpath()


def draw(painter: QPainter, name: str, color: QColor, width: float = 1.8) -> None:
    """Значок name в клетке 24×24 (painter уже масштабирован)."""
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    if name == "overview":
        _shield(path)
        path.moveTo(8.6, 12)
        path.lineTo(11, 14.4)
        path.lineTo(15.6, 9.6)
    elif name == "servers":
        path.addEllipse(QPointF(12, 12), 8.5, 8.5)
        path.addEllipse(QPointF(12, 12), 3.8, 8.5)
        path.moveTo(3.5, 12)
        path.lineTo(20.5, 12)
    elif name == "subscriptions":
        for y in (7, 12, 17):
            path.moveTo(9, y)
            path.lineTo(19.5, y)
        painter.setBrush(color)
        for y in (7, 12, 17):
            painter.drawEllipse(QPointF(5, y), 1.4, 1.4)
        painter.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "devices":
        path.addRoundedRect(QRectF(3, 4, 18, 12), 2, 2)
        path.moveTo(12, 16)
        path.lineTo(12, 20)
        path.moveTo(8, 20)
        path.lineTo(16, 20)
    elif name == "traffic":
        for x, top in ((6, 13), (12, 5.5), (18, 9.5)):
            path.moveTo(x, 20)
            path.lineTo(x, top)
    elif name == "diagnostics":
        path.moveTo(3, 12)
        for px, py in ((7, 12), (10, 5), (14, 19), (17, 12), (21, 12)):
            path.lineTo(px, py)
    elif name == "extra":
        for y, knob in ((7, 9), (12, 15), (17, 7)):
            path.moveTo(4, y)
            path.lineTo(20, y)
            path.addEllipse(QPointF(knob, y), 1.9, 1.9)
    elif name == "theme":
        path.addEllipse(QPointF(12, 12), 8, 8)
        half = QPainterPath()
        half.moveTo(12, 4)
        half.arcTo(QRectF(4, 4, 16, 16), 90, 180)
        half.closeSubpath()
        painter.fillPath(half, color)
    elif name == "power":
        path.arcMoveTo(QRectF(5, 5, 14, 14), 60)
        path.arcTo(QRectF(5, 5, 14, 14), 60, -300)
        path.moveTo(12, 3.5)
        path.lineTo(12, 11)
    elif name == "remeasure":
        path.arcMoveTo(QRectF(4, 4, 16, 16), 30)
        path.arcTo(QRectF(4, 4, 16, 16), 30, 300)
        path.moveTo(20, 4.5)
        path.lineTo(19.9, 9.4)
        path.lineTo(15, 9.2)
    elif name == "more":
        painter.setBrush(color)
        for x in (6, 12, 18):
            painter.drawEllipse(QPointF(x, 12), 1.6, 1.6)
        painter.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "search":
        path.addEllipse(QPointF(10.5, 10.5), 6, 6)
        path.moveTo(15, 15)
        path.lineTo(20, 20)
    painter.drawPath(path)


class Switch(QAbstractButton):
    """Переключатель «вкл/выкл» как в мобильных и VPN-клиентах; состояние — и словом рядом."""

    def __init__(self, label: str = "") -> None:
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(label)
        self.setFixedSize(46, 26)

    def paintEvent(self, _event) -> None:
        colors = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        track = QColor(colors["accent"] if on else colors["border"])
        if not self.isEnabled():
            track.setAlpha(110)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(1, 3, 44, 20), 10, 10)
        painter.setBrush(QColor(colors["surface"] if on else colors["text"]))
        painter.drawEllipse(QPointF(35 if on else 11, 13), 8, 8)
        if self.hasFocus():
            pen = QPen(QColor(colors["focus"]))
            pen.setWidthF(2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(1, 2, 44, 22), 11, 11)
        painter.end()


def icon(name: str, normal: str, active: str | None = None, size: int = 24) -> QIcon:
    """QIcon значка: обычный цвет и цвет выбранного (On) состояния."""
    result = QIcon()
    for scale in (1, 2):
        for color, state in ((normal, QIcon.State.Off), (active or normal, QIcon.State.On)):
            pixmap = QPixmap(size * scale, size * scale)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.scale(size * scale / 24, size * scale / 24)
            draw(painter, name, QColor(color))
            painter.end()
            result.addPixmap(pixmap, QIcon.Mode.Normal, state)
    return result


# --- навигация ----------------------------------------------------------------------------------


class NavRail(QWidget):
    """Панель разделов Proton: значок слева от подписи, спокойная плашка выбора."""

    currentRowChanged = pyqtSignal(int)

    def __init__(self, sections: tuple[tuple[str, str], ...]) -> None:
        super().__init__()
        self.setObjectName("rail")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(RAIL_WIDTH)
        self.setAccessibleName("Разделы")
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(14, 18, 14, 14)
        self.box.setSpacing(6)
        self.logo = QLabel("XGW")
        self.logo.setObjectName("brand")
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo.setFixedHeight(52)
        self.box.addWidget(self.logo)
        self.box.addSpacing(12)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: list[QToolButton] = []
        self.names = [key for key, _title in sections]
        for row, (_key, title) in enumerate(sections):
            button = self._button(title)
            button.setCheckable(True)
            button.setAccessibleName(f"Раздел «{title}»")
            self.group.addButton(button, row)
            self.box.addWidget(button)
            self.buttons.append(button)
        self.box.addStretch(1)
        self.group.idClicked.connect(self.setCurrentRow)
        self._row = -1

    def _button(self, title: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName("navButton")
        button.setText(title)
        button.setToolTip(title)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setIconSize(QSize(22, 22))
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setFixedHeight(46)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)  # мышью — без рамки фокуса
        return button

    def add_bottom(self, title: str) -> QToolButton:
        button = self._button(title)
        self.box.addWidget(button)
        return button

    def currentRow(self) -> int:
        return self._row

    def setCurrentRow(self, row: int) -> None:
        if not 0 <= row < len(self.buttons):
            return
        self.buttons[row].setChecked(True)
        if row != self._row:
            self._row = row
            self.currentRowChanged.emit(row)

    def recolor(self, colors: dict[str, str], extra: dict[QToolButton, str]) -> None:
        for name, button in zip(self.names, self.buttons, strict=True):
            button.setIcon(icon(name, colors["muted"], colors["accent"]))
        for button, name in extra.items():
            button.setIcon(icon(name, colors["muted"]))


# --- знак защиты --------------------------------------------------------------------------------


CONTINENTS = (
    ((.05, .22), (.13, .12), (.27, .17), (.31, .29), (.25, .39), (.20, .42),
     (.18, .55), (.12, .49), (.08, .36)),
    ((.23, .56), (.31, .55), (.36, .64), (.33, .78), (.28, .94), (.24, .80)),
    ((.43, .26), (.49, .20), (.58, .24), (.62, .34), (.55, .41), (.48, .37)),
    ((.46, .43), (.56, .40), (.63, .50), (.60, .70), (.54, .88), (.48, .70)),
    ((.57, .22), (.72, .13), (.91, .25), (.88, .44), (.79, .48), (.75, .65),
     (.68, .59), (.61, .43)),
    ((.76, .72), (.85, .68), (.92, .77), (.88, .89), (.78, .86)),
    ((.33, .07), (.39, .06), (.41, .17), (.35, .20), (.31, .14)),
)
COUNTRY_POINTS = {
    "AE": (.66, .55), "AR": (.29, .84), "AT": (.54, .34), "AU": (.84, .79),
    "BE": (.50, .31), "BG": (.59, .40), "BR": (.32, .71), "CA": (.19, .28),
    "CH": (.51, .35), "CL": (.27, .84), "CN": (.76, .40), "CY": (.61, .47),
    "CZ": (.54, .32), "DE": (.52, .29), "DK": (.52, .23), "DZ": (.49, .45),
    "EE": (.57, .23), "EG": (.58, .49), "ES": (.46, .40), "FI": (.57, .16),
    "FR": (.48, .33), "GB": (.45, .26), "GR": (.58, .45), "HK": (.78, .50),
    "HU": (.55, .35), "ID": (.78, .69), "IE": (.43, .26), "IL": (.61, .50),
    "IN": (.71, .54), "IS": (.40, .15), "IT": (.53, .40), "JP": (.87, .40),
    "KE": (.61, .63), "KR": (.82, .41), "LT": (.56, .27), "LV": (.57, .25),
    "MA": (.44, .44), "MX": (.17, .51), "MY": (.75, .60), "NG": (.52, .59),
    "NL": (.50, .28), "NO": (.51, .15), "NZ": (.91, .87), "PL": (.55, .29),
    "PT": (.44, .40), "RO": (.58, .36), "RU": (.72, .22), "SE": (.54, .15),
    "SG": (.76, .64), "SK": (.56, .33), "TH": (.74, .54), "TR": (.63, .44),
    "TW": (.81, .48), "UA": (.60, .32), "US": (.19, .38), "VN": (.77, .53),
    "ZA": (.56, .82),
}


class ShieldOrb(QWidget):
    """Карта мира и знак защиты в приблизительной точке страны VPN-сервера."""

    def __init__(self) -> None:
        super().__init__()
        self.tone = "off"
        self.country = ""
        self.setMinimumHeight(210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("Карта и знак защиты")

    def set_tone(self, value: str) -> None:
        if value != self.tone:
            self.tone = value
            self.update()

    def set_country(self, value: str) -> None:
        value = value.upper()
        if value != self.country:
            self.country = value
            self.setAccessibleName("Карта и знак защиты" +
                                   (f"; страна сервера {value}" if value in COUNTRY_POINTS else ""))
            self.update()

    def _map(self, painter: QPainter) -> None:
        colors = theme.current()
        painter.setPen(QPen(QColor(colors["border"]), 1.1))
        painter.setBrush(QColor(colors["surface2"]))
        for points in CONTINENTS:
            polygon = QPolygonF([QPointF(x * self.width(), y * self.height())
                                 for x, y in points])
            painter.drawPolygon(polygon)

    def paintEvent(self, _event) -> None:
        colors = theme.current()
        color = QColor(colors.get(self.tone, colors["off"]))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._map(painter)
        point = COUNTRY_POINTS.get(self.country, (.5, .5))
        center = QPointF(self.width() * point[0], self.height() * point[1])
        core = max(25.0, min(43.0, min(self.width(), self.height()) * .16))
        glow = QRadialGradient(center, core * 3.6)
        for stop, alpha in ((0.0, 105), (0.55, 45), (1.0, 0)):
            shade = QColor(color)
            shade.setAlpha(alpha if self.tone != "off" else alpha // 3)
            glow.setColorAt(stop, shade)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, core * 3.6, core * 3.6)
        for factor, alpha in ((2.7, 75), (1.9, 125)):
            ring = QColor(color)
            ring.setAlpha(alpha if self.tone != "off" else alpha // 2)
            painter.setPen(QPen(ring, 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center, core * factor, core * factor)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(center, core, core)
        painter.translate(center.x() - core * .63, center.y() - core * .63)
        painter.scale(core * 1.26 / 24, core * 1.26 / 24)
        path = QPainterPath()
        _shield(path)
        pen = QPen(QColor(colors["panel"]), 1.9)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPath(path)
        sign = QPainterPath()
        if self.tone == "ok":
            sign.moveTo(8.6, 12)
            sign.lineTo(11, 14.4)
            sign.lineTo(15.6, 9.6)
        elif self.tone == "bad":
            sign.moveTo(9.4, 9.2)
            sign.lineTo(14.6, 14.4)
            sign.moveTo(14.6, 9.2)
            sign.lineTo(9.4, 14.4)
        elif self.tone in ("warn", "busy"):
            sign.moveTo(12, 7.8)
            sign.lineTo(12, 12.6)
            sign.moveTo(12, 15.6)
            sign.lineTo(12, 15.7)
        else:
            sign.moveTo(9, 12)
            sign.lineTo(15, 12)
        painter.drawPath(sign)
        painter.end()


# --- значок страны, плитка, строка сервера ------------------------------------------------------

EMOJI_FONTS = ("Noto Color Emoji", "Twemoji", "Apple Color Emoji")


def emoji_flags() -> bool:
    families = set(QFontDatabase.families())
    return any(name in families for name in EMOJI_FONTS)


class Badge(QLabel):
    """Круглый значок страны: флаг, если в системе есть цветной шрифт эмодзи, иначе код."""

    def __init__(self, size: int = 40) -> None:
        super().__init__()
        self.setObjectName("badge")
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def show_country(self, flag: str, code: str) -> None:
        known = code if code not in ("", "XX") else ""  # XX — страна в теге не указана
        text = flag if flag and emoji_flags() else (known or "··")
        set_text(self, text)
        self.setAccessibleName(f"Страна {known}" if known else "Страна не указана")


class Metric(QFrame):
    """Плитка: подпись мелко, число крупно, единица под ним."""

    def __init__(self, title: str, about: str = "") -> None:
        super().__init__()
        self.setObjectName("metric")
        self.setToolTip(about or title)
        box = QVBoxLayout(self)
        box.setContentsMargins(14, 10, 14, 12)
        box.setSpacing(2)
        box.addWidget(label(title.upper(), name="metricTitle", wrap=False))
        self.value = label("—", name="metricValue", wrap=False)
        self.unit = label("", name="small", wrap=False)
        box.addWidget(self.value)
        box.addWidget(self.unit)
        self.setAccessibleName(title)

    def set(self, text: str) -> None:
        """«87,3 Мбит/с» → 87,3 крупно и «Мбит/с» мелко; «—» без единицы."""
        number, _space, unit = text.partition(" ")
        set_text(self.value, number)
        set_text(self.unit, unit)

    def text(self) -> str:
        return f"{self.value.text()} {self.unit.text()}".strip()


class ServerRowWidget(QFrame):
    """Строка сервера: страна, имя и подробности, скорость и задержка, состояние."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("row")
        box = QHBoxLayout(self)
        box.setContentsMargins(12, 10, 14, 10)
        box.setSpacing(12)
        self.badge = Badge()
        box.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.name = Elided(name="rowName")
        self.main = label("В РАБОТЕ", name="pill", wrap=False)
        tone(self.main, "busy")
        top.addWidget(self.name, 1)
        top.addWidget(self.main)
        texts.addLayout(top)
        details = QHBoxLayout()
        details.setSpacing(8)
        self.sub = Elided(name="small")
        details.addWidget(self.sub, 1)
        self.speed = label("", name="rowSpeed", wrap=False)
        self.speed.setAlignment(Qt.AlignmentFlag.AlignRight)
        details.addWidget(self.speed)
        texts.addLayout(details)
        box.addLayout(texts, 1)
        status = QVBoxLayout()
        status.setSpacing(3)
        self.dot = QLabel()
        self.dot.setObjectName("dot")
        self.state = label("", name="small")
        self.state.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        status.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignHCenter)
        status.addWidget(self.state, 0, Qt.AlignmentFlag.AlignHCenter)
        self.holder = QWidget()
        self.holder.setLayout(status)
        self.holder.setFixedWidth(124)
        box.addWidget(self.holder)

    is_main = False
    PILL_WIDTH = 640  # уже — без метки «В работе» (основной виден по рамке) и слова состояния

    def _fit(self) -> None:
        """Узкая строка: без метки «В работе» и без слова состояния — точка и подсказка."""
        wide = self.width() >= self.PILL_WIDTH
        self.main.setVisible(self.is_main and wide)
        self.state.setVisible(wide)
        self.holder.setFixedWidth(124 if wide else 24)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit()

    def show_row(self, row: model.ServerRow) -> None:
        self.badge.show_country(row.flag, row.code)
        set_text(self.name, row.name)
        tip(self.name, row.name)
        set_text(self.sub, row.sub)
        tip(self.sub, row.sub)
        self.is_main = row.main
        self._fit()
        set_text(self.speed, row.speed if row.speed != "—" else "")
        tip(self.speed, row.note)
        tone(self.dot, row.tone)
        set_text(self.state, f"{model.MARKS.get(row.tone, '')} {row.status}".strip())
        # В узкой строке слово состояния доступно подсказкой у всей правой колонки.
        for widget in (self.dot, self.holder):
            tip(widget, row.status)
        tip(self, server_details(row.name, flag=row.flag, code=row.code, status=row.status,
                                 speed=row.speed, delay=row.delay, sub=row.sub, note=row.note,
                                 main=row.main))
        tone(self, "true" if row.main else "false", "main")
        self.setAccessibleName(f"{row.name}: {row.status}, {row.speed}")


class ServerList(QWidget):
    """Список строк серверов; строки переиспользуются — опрос не пересоздаёт виджеты."""

    def __init__(self) -> None:
        super().__init__()
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(8)
        self.rows: list[ServerRowWidget] = []

    def show_rows(self, rows: list[model.ServerRow]) -> None:
        while len(self.rows) < len(rows):
            widget = ServerRowWidget()
            self.box.addWidget(widget)
            self.rows.append(widget)
        for widget, row in zip(self.rows, rows, strict=False):
            widget.show_row(row)
            widget.show()
        for widget in self.rows[len(rows):]:
            widget.hide()

    def visible_rows(self) -> list[ServerRowWidget]:
        return [widget for widget in self.rows if not widget.isHidden()]
