"""Единственная точка маскирования секретов.

Через mask_text проходят логи, статус и экспорт: UUID остаются только
последними 4 символами, пароли/ключи/токены превращаются в «***»,
от URL подписок остаётся только домен, от ссылок серверов — только схема.
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
# Ссылки серверов целиком секретны: в userinfo лежит UUID или пароль.
_LINK_RE = re.compile(
    r"\b(vless|vmess|trojan|ss|ssr|socks5?|hysteria2?|hy2|tuic|wireguard)://[^\s\"'<>]+",
    re.IGNORECASE,
)
# Токен Telegram-бота: <id>:<35 символов> — короче порога _LONG_TOKEN_RE.
_BOT_TOKEN_RE = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}")

# Поля outbound, значения которых — секреты (UUID маскируются регуляркой отдельно).
_SECRET_KEYS = frozenset(
    {
        "id", "password", "pass", "publicKey", "privateKey", "secretKey", "preSharedKey",
        "shortId", "seed", "mldsa65Verify", "auth",
    }
)

SECRET_KEYS = _SECRET_KEYS


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
    """Маскирует строку: известные секреты, ссылки серверов, UUID, токены и URL."""
    result = text
    # Длинные секреты первыми: короткий не должен «откусить» часть длинного.
    for secret in sorted({s for s in secrets if s and len(s) >= 4}, key=len, reverse=True):
        result = result.replace(secret, "***")
    result = _LINK_RE.sub(lambda m: f"{m.group(1).lower()}://***", result)
    result = _URL_RE.sub(_mask_url_match, result)
    result = _UUID_RE.sub(lambda m: mask_uuid(m.group(0)), result)
    result = _BOT_TOKEN_RE.sub("***", result)
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


def collect_secrets(obj: object) -> set[str]:
    """Значения секретных полей (пароли, ключи) из outbound/конфига Xray —
    для точной замены в логах: короткий пароль регулярками не поймать."""
    found: set[str] = set()
    _walk_secrets(obj, found)
    return found


def _walk_secrets(obj: object, found: set[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in _SECRET_KEYS and isinstance(value, str):
                if len(value) >= 4 and not _UUID_RE.fullmatch(value):
                    found.add(value)
            else:
                _walk_secrets(value, found)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _walk_secrets(item, found)
