"""Значок XGW для Windows (.ico) — тот же рисунок, что в панели (src/xgw/ui/icon.svg):
тёмный скруглённый квадрат и зелёный знак «включено».

Рисуется здесь же, без сторонних библиотек: по ТЗ у проекта только стандартная
библиотека Python, а готового растрового значка в репозитории нет. Размеры 16–48 —
несжатые (BMP), 256 — PNG: так значок читают и Проводник, и NSIS.

    python packaging/windows/make_icon.py build/xgw.ico
"""

from __future__ import annotations

import math
import struct
import sys
import zlib
from pathlib import Path

SIZES = (16, 24, 32, 48, 64, 256)
SAMPLES = 4  # точек на сторону пикселя при сглаживании
BG = ((0x17, 0x26, 0x3A), (0x0B, 0x12, 0x20))
RING = ((0x4C, 0xE3, 0xB0), (0x1F, 0xB8, 0x86))
RADIUS = 15.0  # скругление квадрата 64 × 64
CENTER = (32.0, 33.21)  # центр дуги: M21.4 22.6 a15 15 0 1 0 21.2 0
ARC = 15.0
HALF = 2.5  # половина толщины линии
BAR = ((32.0, 14.0), (32.0, 31.0))


def _mix(pair: tuple[tuple[int, int, int], tuple[int, int, int]], t: float) -> tuple[float, ...]:
    t = min(1.0, max(0.0, t))
    return tuple(a + (b - a) * t for a, b in zip(*pair, strict=True))


def _in_square(x: float, y: float) -> bool:
    dx = max(RADIUS - x, x - (64.0 - RADIUS), 0.0)
    dy = max(RADIUS - y, y - (64.0 - RADIUS), 0.0)
    return 0.0 <= x <= 64.0 and 0.0 <= y <= 64.0 and dx * dx + dy * dy <= RADIUS * RADIUS


def _on_sign(x: float, y: float) -> bool:
    """Точка на дуге с разрывом сверху либо на вертикальной черте (концы скруглены)."""
    (ax, ay), (_bx, by) = BAR
    nearest = min(max(y, ay), by)
    if math.hypot(x - ax, y - nearest) <= HALF:
        return True
    dx, dy = x - CENTER[0], y - CENTER[1]
    angle = math.degrees(math.atan2(dy, dx))
    if -135.0 < angle < -45.0:  # разрыв: до дуги ближе всего один из её концов
        ends = ((21.4, 22.6), (42.6, 22.6))
        return min(math.hypot(x - ex, y - ey) for ex, ey in ends) <= HALF
    return abs(math.hypot(dx, dy) - ARC) <= HALF


def render(size: int) -> list[list[tuple[int, int, int, int]]]:
    """Строки пикселей RGBA сверху вниз."""
    scale = 64.0 / size
    rows = []
    for py in range(size):
        row = []
        for px in range(size):
            inside = 0
            red = green = blue = 0.0
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    x = (px + (sx + 0.5) / SAMPLES) * scale
                    y = (py + (sy + 0.5) / SAMPLES) * scale
                    if not _in_square(x, y):
                        continue
                    inside += 1
                    if _on_sign(x, y):
                        color = _mix(RING, ((x - 17.0) + (y - 14.0)) / 68.0)
                    else:
                        color = _mix(BG, (x + y) / 128.0)
                    red, green, blue = red + color[0], green + color[1], blue + color[2]
            if not inside:
                row.append((0, 0, 0, 0))
                continue
            alpha = round(255 * inside / SAMPLES**2)
            row.append((round(red / inside), round(green / inside), round(blue / inside), alpha))
        rows.append(row)
    return rows


def _png(rows: list[list[tuple[int, int, int, int]]]) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    size = len(rows)
    raw = b"".join(b"\x00" + bytes(value for pixel in row for value in pixel) for row in rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _bmp(rows: list[list[tuple[int, int, int, int]]]) -> bytes:
    """Картинка значка без сжатия: BGRA снизу вверх и маска прозрачности."""
    size = len(rows)
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    pixels = b"".join(
        bytes(value for red, green, blue, alpha in row for value in (blue, green, red, alpha))
        for row in reversed(rows)
    )
    stride = (size + 31) // 32 * 4
    mask = b""
    for row in reversed(rows):
        bits = bytearray(stride)
        for index, pixel in enumerate(row):
            if pixel[3] == 0:
                bits[index // 8] |= 0x80 >> (index % 8)
        mask += bytes(bits)
    return header + pixels + mask


def build(path: Path, sizes: tuple[int, ...] = SIZES) -> None:
    images = []
    for size in sizes:
        rows = render(size)
        images.append((size, _png(rows) if size >= 256 else _bmp(rows)))
    offset = 6 + 16 * len(images)
    directory = b""
    for size, data in images:
        directory += struct.pack(
            "<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset
        )
        offset += len(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        struct.pack("<HHH", 0, 1, len(images)) + directory + b"".join(d for _s, d in images)
    )


SIDE = (328, 628)  # вдвое крупнее обычных 164 × 314: установщик сам ужимает под экран
SIDE_SIGN = 0.62  # сторона квадрата 64 × 64 со знаком — в долях ширины картинки
SIDE_TOP = 0.16  # его отступ сверху — в долях высоты


def build_side(path: Path, size: tuple[int, int] = SIDE) -> None:
    """Картинка слева на первой и последней страницах установщика (BMP, 24 бита):
    тот же тёмный фон и знак «включено», что у значка."""
    width, height = size
    scale = 64.0 / (width * SIDE_SIGN)
    left, top = width * (1.0 - SIDE_SIGN) / 2.0, height * SIDE_TOP
    rows = []
    for py in range(height):
        back = _mix(BG, py / height)
        row = bytearray()
        for px in range(width):
            color = back
            x0, y0 = (px - left) * scale, (py - top) * scale
            if -1.0 <= x0 <= 65.0 and -1.0 <= y0 <= 65.0:
                hits = sum(
                    _on_sign(x0 + (sx + 0.5) / SAMPLES * scale, y0 + (sy + 0.5) / SAMPLES * scale)
                    for sy in range(SAMPLES) for sx in range(SAMPLES)
                )
                if hits:
                    share = hits / SAMPLES**2
                    ring = _mix(RING, ((x0 - 17.0) + (y0 - 14.0)) / 68.0)
                    color = tuple(b + (r - b) * share for b, r in zip(back, ring, strict=True))
            row += bytes((round(color[2]), round(color[1]), round(color[0])))  # BGR
        rows.append(bytes(row) + b"\x00" * (-len(row) % 4))
    body = b"".join(reversed(rows))  # строки BMP идут снизу вверх
    header = struct.pack("<2sIHHI", b"BM", 54 + len(body), 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(body), 2835, 2835, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + info + body)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("использование: make_icon.py <куда записать .ico>")
    build(Path(sys.argv[1]))
    print(f"значок записан: {sys.argv[1]}")
