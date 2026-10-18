"""Хеш открытого ключа сертификата — так sing-box закрепляет сертификат сервера (pks).

Только стандартная библиотека: сертификат разбирается как DER, без openssl.
"""

import base64
import hashlib


def _tlv(der: bytes, pos: int) -> tuple[int, int, int]:
    """Элемент DER: (тег, начало содержимого, конец)."""
    tag, first = der[pos], der[pos + 1]
    if first < 0x80:
        return tag, pos + 2, pos + 2 + first
    count = first & 0x7F
    size = int.from_bytes(der[pos + 2:pos + 2 + count], "big")
    return tag, pos + 2 + count, pos + 2 + count + size


def spki_pin(pem: str) -> str:
    """SHA-256 открытого ключа сертификата в base64 — так его закрепляет sing-box (pks)."""
    body = "".join(line for line in pem.splitlines() if line and not line.startswith("-----"))
    der = base64.b64decode(body)
    _tag, start, _end = _tlv(der, 0)  # Certificate
    _tag, pos, end = _tlv(der, start)  # tbsCertificate
    items: list[tuple[int, int]] = []
    while pos < end:
        _tag, _s, stop = _tlv(der, pos)
        items.append((pos, stop))
        pos = stop
    shift = 1 if der[items[0][0]] == 0xA0 else 0  # необязательная версия [0]
    first, last = items[shift + 5]  # serial, signature, issuer, validity, subject, spki
    return base64.b64encode(hashlib.sha256(der[first:last]).digest()).decode("ascii")
