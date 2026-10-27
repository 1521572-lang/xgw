"""Читатель geoip.dat Xray (Ф6): сети страны для разгрузки прямого трафика в ядро (net/nft.py).

Формат — protobuf v2fly: `GeoIPList { repeated GeoIP entry = 1; }`, `GeoIP { string
country_code = 1; repeated CIDR cidr = 2; bool reverse_match = 3; }`, `CIDR { bytes ip = 1;
uint32 prefix = 2; }`. Зависимостей нет: разбирается только нужная страна, остальные записи
пропускаются по длине. Берутся только сети IPv4.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterator
from pathlib import Path

# Сеть короче /8 у страны не бывает: такая запись — порча файла, и в «напрямую» она увела бы
# мимо VPN полинтернета. Пропускается.
MIN_PREFIX = 8


class GeoError(Exception):
    """geoip.dat не прочитан: нет файла или он испорчен."""


def cidrs(path: Path, code: str) -> list[ipaddress.IPv4Network]:
    """Сети IPv4 страны code (как в `geoip:ru` — регистр не важен) из geoip.dat. Страны в
    файле нет — пустой список."""
    try:
        data = memoryview(Path(path).read_bytes())
    except OSError as exc:
        raise GeoError(f"{path} не читается: {exc.strerror or exc}") from exc
    wanted = code.upper().encode("ascii", "replace")
    for number, kind, value in _fields(data, 0, len(data)):
        if number != 1 or kind != 2:
            continue
        name, ranges, reverse = b"", [], False
        for field, sort, item in _fields(data, *value):
            if field == 1 and sort == 2:
                name = bytes(data[item[0]:item[1]]).upper()
                if name != wanted:
                    break  # чужая страна: остальное в записи не нужно
            elif field == 2 and sort == 2:
                ranges.append(item)
            elif field == 3 and sort == 0:
                reverse = bool(item)
        if name != wanted:
            continue
        if reverse:
            raise GeoError(f"страна {code} записана в {path} «наоборот» (reverse_match)")
        return [network for network in (_cidr(data, *item) for item in ranges) if network]
    return []


def _cidr(data: memoryview, start: int, end: int) -> ipaddress.IPv4Network | None:
    ip, prefix = b"", 0
    for field, sort, item in _fields(data, start, end):
        if field == 1 and sort == 2:
            ip = bytes(data[item[0]:item[1]])
        elif field == 2 and sort == 0:
            prefix = item
    if len(ip) != 4 or not MIN_PREFIX <= prefix <= 32:
        return None  # IPv6 или испорченная запись
    return ipaddress.IPv4Network((ip, prefix), strict=False)


def _fields(data: memoryview, start: int, end: int) -> Iterator[tuple[int, int, object]]:
    """Поля сообщения: (номер, тип, значение); у типа 0 значение — число, у типа 2 — границы
    (начало, конец) внутри data."""
    pos = start
    while pos < end:
        key, pos = _varint(data, pos)
        number, kind = key >> 3, key & 7
        if kind == 0:
            value, pos = _varint(data, pos)
            yield number, kind, value
        elif kind == 2:
            size, pos = _varint(data, pos)
            if pos + size > end:
                raise GeoError("geoip.dat испорчен: запись обрывается")
            yield number, kind, (pos, pos + size)
            pos += size
        elif kind in (1, 5):
            pos += 8 if kind == 1 else 4
        else:
            raise GeoError(f"geoip.dat испорчен: неизвестный тип поля {kind}")
    if pos != end:
        raise GeoError("geoip.dat испорчен: запись обрывается")


def _varint(data: memoryview, pos: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if pos >= len(data):
            raise GeoError("geoip.dat испорчен: запись обрывается")
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, pos
        shift += 7
        if shift > 63:
            raise GeoError("geoip.dat испорчен: слишком длинное число")
