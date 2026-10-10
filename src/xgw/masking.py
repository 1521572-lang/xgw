"""Единственная точка маскирования секретов.

Через mask_text проходят логи, статус и экспорт: UUID остаются только
последними 4 символами, пароли/ключи/токены превращаются в «***»,
от URL подписок остаётся только домен.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlsplit

_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
# Длинные base64/hex-подобные токены (ключи реальности, токены ботов и т.п.).
_LONG_TOKEN_RE = re.compile(r"\b[A-Za-z0-9+/_=-]{40,}\b")
_URL_RE = re.compile(r"https?://[^\s\"'<>]+")


def mask_uuid(value: str) -> str:
    return f"****{value[-4:]}" if len(value) >= 8 else "***"


def mask_secret(_value: str) -> str:
    return "***"


def mask_url(url: str) -> str:
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return "***"
    return host or "***"


def mask_text(text: str, secrets: Iterable[str] = ()) -> str:
    """Маскирует строку: известные секреты, UUID, длинные токены и URL (остаётся домен)."""
    result = text
    for secret in secrets:
        if secret and len(secret) >= 4:
            result = result.replace(secret, "***")
    result = _URL_RE.sub(_mask_url_match, result)
    result = _UUID_RE.sub(lambda m: mask_uuid(m.group(0)), result)
    result = _LONG_TOKEN_RE.sub("***", result)
    return result


def _mask_url_match(match: re.Match[str]) -> str:
    return f"https://{mask_url(match.group(0))}/…"


def mask_obj(obj: object, secrets: Iterable[str] = ()) -> object:
    """Рекурсивно маскирует строки в словарях и списках (для статуса и экспорта)."""
    if isinstance(obj, str):
        return mask_text(obj, secrets)
    if isinstance(obj, dict):
        return {key: mask_obj(value, secrets) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [mask_obj(item, secrets) for item in obj]
    return obj
