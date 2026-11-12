"""Иконки, флаги и иллюстрации: SVG перекрашивается под тему и рисуется чётко при любом масштабе."""
from __future__ import annotations

from pathlib import Path

from ..qt import Qt, QtCore, QtGui, QtSvg
from .tokens import Color

ASSETS = Path(__file__).resolve().parent.parent / "assets"
ICON_SIZES = (16, 20, 24, 32)
FLAG_ALIASES = {"GB": "UK"}  # в наборе флагов Великобритания лежит как UK

_cache: dict[tuple, QtGui.QPixmap] = {}
_texts: dict[Path, str] = {}


def clear_cache() -> None:
    _cache.clear()


def device_ratio() -> float:
    app = QtGui.QGuiApplication.instance()
    screen = app.primaryScreen() if app is not None else None
    return float(screen.devicePixelRatio()) if screen is not None else 1.0


def _text(path: Path) -> str:
    if path not in _texts:
        _texts[path] = path.read_text(encoding="utf-8")
    return _texts[path]


def icon_file(name: str, px: int) -> Path:
    """Файл иконки ближайшего размера: сначала не меньше нужного, иначе самый крупный."""
    sizes = [size for size in ICON_SIZES if (ASSETS / "icons" / f"{name}_{size}.svg").is_file()]
    if not sizes:
        raise FileNotFoundError(f"нет иконки {name}")
    best = next((size for size in sizes if size >= px), sizes[-1])
    return ASSETS / "icons" / f"{name}_{best}.svg"


def render_svg(data: str | bytes, size: QtCore.QSize, ratio: float,
               opacity: float = 1.0) -> QtGui.QPixmap:
    """SVG → QPixmap заданного логического размера с учётом масштаба экрана."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(raw))
    pixmap = QtGui.QPixmap(max(1, round(size.width() * ratio)),
                           max(1, round(size.height() * ratio)))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.setOpacity(opacity)
    renderer.render(painter, QtCore.QRectF(0, 0, pixmap.width(), pixmap.height()))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def icon_pixmap(name: str, color: Color, px: int, ratio: float | None = None) -> QtGui.QPixmap:
    """Одноцветная иконка набора в цвете темы (`currentColor` заменяется на HEX)."""
    ratio = device_ratio() if ratio is None else ratio
    key = ("icon", name, color, px, ratio)
    if key not in _cache:
        text = _text(icon_file(name, px)).replace("currentColor", color.hex)
        _cache[key] = render_svg(text, QtCore.QSize(px, px), ratio, color.a)
    return _cache[key]


def load_svg_icon(name: str, color_hex: str, size: QtCore.QSize) -> QtGui.QIcon:
    """QIcon из SVG набора: цвет подставляется вместо `currentColor`, масштаб экрана учтён."""
    value = color_hex.lstrip("#")
    color = Color(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    icon = QtGui.QIcon()
    side = max(size.width(), size.height())
    for ratio in sorted({1.0, device_ratio(), 2.0}):
        icon.addPixmap(icon_pixmap(name, color, side, ratio))
    return icon


def flag_pixmap(code: str, width: int, height: int, ratio: float | None = None) -> QtGui.QPixmap:
    """Флаг страны по коду ISO; неизвестный код — нейтральная заглушка."""
    ratio = device_ratio() if ratio is None else ratio
    code = FLAG_ALIASES.get(code.upper(), code.upper())
    key = ("flag", code, width, height, ratio)
    if key not in _cache:
        path = ASSETS / "flags" / f"{code}.svg"
        if not path.is_file():
            path = ASSETS / "flags" / "Placeholder.svg"
        _cache[key] = render_svg(_text(path), QtCore.QSize(width, height), ratio)
    return _cache[key]


def illustration(name: str, theme: str, px: int, ratio: float | None = None) -> QtGui.QPixmap:
    """Цветная иллюстрация виджета (PNG 128 px) в нужном размере."""
    ratio = device_ratio() if ratio is None else ratio
    key = ("art", name, theme, px, ratio)
    if key not in _cache:
        source = QtGui.QPixmap(str(ASSETS / "illustrations" / theme / f"{name}.png"))
        side = max(1, round(px * ratio))
        scaled = source.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(ratio)
        _cache[key] = scaled
    return _cache[key]


def world_map_svg(land: Color, outline: Color) -> bytes:
    """Карта мира, перекрашенная под тему (в исходнике у всех стран одна заливка)."""
    text = _text(ASSETS / "world-map.svg")
    paint = f'fill="{land.hex}" stroke="{outline.hex}" stroke-width="0.35"'
    return text.replace('fill="#494D55"', paint).encode("utf-8")
