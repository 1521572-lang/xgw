"""Читатель geoip.dat Xray (Ф6): сети страны для разгрузки прямого трафика в ядро."""

import ipaddress
from pathlib import Path

import pytest

from xgw import geodat


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte, value = value & 0x7F, value >> 7
        if not value:
            out.append(byte)
            return bytes(out)
        out.append(byte | 0x80)


def _field(number: int, payload: bytes) -> bytes:
    return _varint(number << 3 | 2) + _varint(len(payload)) + payload


def write_geoip(path: Path, countries: dict, reverse=frozenset()) -> Path:
    """Маленький geoip.dat в формате v2fly: {страна: [(адрес, префикс), …]}."""
    body = b""
    for code, networks in countries.items():
        entry = _field(1, code.encode())
        for address, prefix in networks:
            packed = ipaddress.ip_address(address).packed
            entry += _field(2, _field(1, packed) + _varint(2 << 3) + _varint(prefix))
        if code in reverse:
            entry += _varint(3 << 3) + _varint(1)
        body += _field(1, entry)
    path.write_bytes(body)
    return path


def test_country_networks_are_read_from_geoip_dat(tmp_path):
    """Только IPv4 нужной страны; запись короче /8 — порча файла, её в «напрямую» не берём."""
    path = write_geoip(tmp_path / "geoip.dat", {
        "CN": [("1.0.1.0", 24)],
        "RU": [("5.8.0.0", 13), ("2a00:1fa0::", 29), ("77.88.8.1", 24), ("16.0.0.0", 4)],
    })
    assert geodat.cidrs(path, "ru") == [
        ipaddress.IPv4Network("5.8.0.0/13"), ipaddress.IPv4Network("77.88.8.0/24")]
    assert geodat.cidrs(path, "DE") == []
    write_geoip(path, {"RU": [("5.8.0.0", 13)]}, reverse={"RU"})
    with pytest.raises(geodat.GeoError, match="наоборот"):
        geodat.cidrs(path, "RU")
    path.write_bytes(b"\x0a\x05RU")  # запись обрывается
    with pytest.raises(geodat.GeoError, match="испорчен"):
        geodat.cidrs(path, "RU")
    with pytest.raises(geodat.GeoError, match="не читается"):
        geodat.cidrs(tmp_path / "нет.dat", "RU")
