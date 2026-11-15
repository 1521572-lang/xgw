"""Локальная база geoip.dat Xray: сети для Ф6 и страна публичного IP сервера.

Формат — protobuf v2fly: `GeoIPList { repeated GeoIP entry = 1; }`, `GeoIP { string
country_code = 1; repeated CIDR cidr = 2; bool reverse_match = 3; }`, `CIDR { bytes ip = 1;
uint32 prefix = 2; }`. Индекс для интерфейса учитывает IPv4 и IPv6 и переиспользуется
до замены файла. Чтение одной страны для Ф6 по-прежнему использует только IPv4.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from threading import Lock

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
    ip, prefix = _packed_cidr(data, start, end)
    if len(ip) != 4 or not MIN_PREFIX <= prefix <= 32:
        return None  # IPv6 или испорченная запись
    return ipaddress.IPv4Network((ip, prefix), strict=False)


def _packed_cidr(data: memoryview, start: int, end: int) -> tuple[bytes, int]:
    ip, prefix = b"", 0
    for field, sort, item in _fields(data, start, end):
        if field == 1 and sort == 2:
            ip = bytes(data[item[0]:item[1]])
        elif field == 2 and sort == 0:
            prefix = item
    return ip, prefix


class Countries:
    """Публичные IPv4/IPv6 → страны, от наиболее узкой сети к более широкой."""

    def __init__(self, index: dict | None = None) -> None:
        self._index = index or {}

    def lookup(self, address: str) -> str:
        """Пустая строка для неизвестного, частного или неоднозначного адреса."""
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return ""
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global or ip.is_multicast:
            return ""
        value = int(ip)
        for shift, ranges in self._index.get(ip.max_prefixlen, ()):
            code = ranges.get(value >> shift)
            if code is not None:
                return code
        return ""


_country_lock = Lock()


def countries(path: Path) -> Countries:
    """Открыть актуальный индекс; одновременно его строит только один поток."""
    try:
        info = path.stat()
    except OSError:
        return Countries()
    with _country_lock:
        return _countries(path, (info.st_ino, info.st_mtime_ns, info.st_size))


def country(path: Path, address: str) -> str:
    return countries(path).lookup(address)


def ui_asset(xray_dir: Path) -> Path:
    """Отдельная мировая база для интерфейса, с локальной базой ядра как запасной."""
    preferred = xray_dir / "geoip-ui.dat"
    return preferred if preferred.is_file() else xray_dir / "geoip.dat"


@lru_cache(maxsize=1)
def _countries(path: Path, _stamp: tuple[int, int, int]) -> Countries:
    """Разобрать только двухбуквенные записи, отдавая приоритет более узкой сети."""
    try:
        data = memoryview(path.read_bytes())
        index: dict[int, dict[int, dict[int, str]]] = {}
        for number, kind, value in _fields(data, 0, len(data)):
            if number != 1 or kind != 2:
                continue
            name, ranges, reverse = b"", [], False
            for field, sort, item in _fields(data, *value):
                if field == 1 and sort == 2:
                    name = bytes(data[item[0]:item[1]]).upper()
                elif field == 2 and sort == 2:
                    ranges.append(item)
                elif field == 3 and sort == 0:
                    reverse = bool(item)
            if len(name) != 2 or not name.isalpha() or reverse:
                continue
            code = name.decode("ascii")
            for item in ranges:
                packed, prefix = _packed_cidr(data, *item)
                bits = len(packed) * 8
                if bits not in (32, 128) or not MIN_PREFIX <= prefix <= bits:
                    continue
                shift = bits - prefix
                ranges_at_prefix = index.setdefault(bits, {}).setdefault(shift, {})
                key = int.from_bytes(packed, "big") >> shift
                if ranges_at_prefix.setdefault(key, code) != code:
                    ranges_at_prefix[key] = ""  # несколько стран для одной сети
    except (OSError, GeoError):
        return Countries()
    return Countries({bits: sorted(ranges.items()) for bits, ranges in index.items()})


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
