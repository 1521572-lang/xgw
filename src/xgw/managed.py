"""Подписки и ссылки, добавленные из панели: /etc/xgw/panel.json.

config.toml пишет человек — с комментариями и в своём порядке; программа его не
переписывает. То, что добавлено кнопкой в панели, лежит отдельным файлом рядом
(права 0600: в адресах подписок токены) и при чтении конфига дополняет его:
подписки и ссылки из обоих файлов складываются.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from .parsers.common import parse_links_text
from .paths import atomic_write_json

FILE_NAME = "panel.json"
MAX_SUBSCRIPTIONS = 16
MAX_LINKS = 200
MAX_SERVERS = 2000  # сколько отключённых и убранных серверов помнить
MAX_URL = 2048
MAX_NAME = 40
DEFAULT_REFRESH = 60
SERVER_MODES = ("enabled", "disabled", "removed")
_FINGERPRINT_RE = re.compile(r"[0-9a-f]{8}")


class ManagedError(Exception):
    """Добавить или убрать не удалось; текст — для пользователя панели."""


def path_for(config_path: Path) -> Path:
    return Path(config_path).with_name(FILE_NAME)


def load(path: Path) -> tuple[dict, str]:
    """Содержимое panel.json и текст ошибки (пустой, если файла нет или он цел).

    Возвращается только проверенное: подписки с именем и адресом, ссылки — строки,
    отключённые и убранные серверы — отпечатки.
    """
    empty: dict = {"subscriptions": [], "links": [], "disabled": [], "removed": []}
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty, ""
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return empty, f"{path} не читается ({exc}) — добавленное из панели не загружено"
    if not isinstance(raw, dict):
        return empty, f"{path}: ожидается объект JSON — добавленное из панели не загружено"
    subscriptions = []
    for item in raw.get("subscriptions") or []:
        if not isinstance(item, dict):
            continue
        name, url = item.get("name"), item.get("url")
        if not isinstance(name, str) or not isinstance(url, str) or not name or not url:
            continue
        agent, refresh = item.get("user_agent"), item.get("refresh_minutes")
        subscriptions.append({
            "name": name,
            "url": url,
            "user_agent": agent if isinstance(agent, str) else "",
            "refresh_minutes": refresh
            if isinstance(refresh, int) and not isinstance(refresh, bool) and refresh > 0
            else DEFAULT_REFRESH,
        })
    links = [link for link in raw.get("links") or [] if isinstance(link, str) and link]
    removed = _fingerprints(raw.get("removed"))
    disabled = [item for item in _fingerprints(raw.get("disabled")) if item not in removed]
    return {
        "subscriptions": subscriptions, "links": links, "disabled": disabled, "removed": removed,
    }, ""


def _fingerprints(value: object) -> list[str]:
    result: list[str] = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, str) and _FINGERPRINT_RE.fullmatch(item) and item not in result:
            result.append(item)
    return result


def set_servers(path: Path, fingerprints: list[str], mode: str) -> bool:
    """Включает, отключает или убирает серверы; True — что-то изменилось.

    Сервер опознаётся по отпечатку (протокол, адрес, порт, ключ, транспорт):
    запись переживает обновление подписки и смену имени сервера. Если владелец
    подписки сменит адрес или ключ, это будет уже другой сервер.
    """
    if mode not in SERVER_MODES or not fingerprints or not all(
        isinstance(item, str) and _FINGERPRINT_RE.fullmatch(item) for item in fingerprints
    ):
        raise ManagedError("неизвестный сервер или действие")
    data, error = load(path)
    if error:
        raise ManagedError(error)
    before = (set(data["disabled"]), set(data["removed"]))
    chosen = list(dict.fromkeys(fingerprints))
    for key in ("disabled", "removed"):
        data[key] = [item for item in data[key] if item not in chosen]
    if mode != "enabled":
        # Самые старые записи вытесняются: серверы, которых давно нет в подписке.
        data[mode] = [*data[mode], *chosen][-MAX_SERVERS:]
    if (set(data["disabled"]), set(data["removed"])) == before:
        return False
    save(path, data)
    return True


def save(path: Path, data: dict) -> None:
    atomic_write_json(Path(path), data, mode=0o600)


def link_id(link: str) -> str:
    """Короткий идентификатор ссылки: саму ссылку (в ней ключ) панель наружу не отдаёт."""
    return hashlib.sha256(link.encode("utf-8")).hexdigest()[:12]


def check_url(url: str) -> str:
    """Адрес подписки, пригодный для запроса; иначе ManagedError."""
    url = url.strip()
    if not url or len(url) > MAX_URL or re.search(r"[\s\x00-\x1f]", url):
        raise ManagedError("адрес подписки пуст, слишком длинный или содержит пробелы")
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError as exc:
        raise ManagedError("адрес подписки не разобрать") from exc
    # Только http и https: file:// заставил бы демон читать файлы машины от root.
    if parts.scheme not in ("http", "https") or not host:
        raise ManagedError("адрес подписки должен начинаться с https:// или http://")
    return url


def _clean_name(name: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f]+", " ", name).strip()[:MAX_NAME].strip()


def _free_name(wanted: str, taken: set[str]) -> str:
    if wanted not in taken:
        return wanted
    for number in range(2, 1000):
        suffix = f"-{number}"
        candidate = wanted[: MAX_NAME - len(suffix)] + suffix
        if candidate not in taken:
            return candidate
    raise ManagedError("не удалось подобрать имя подписки")


def add_subscription(path: Path, url: str, name: str = "", *, taken: set[str]) -> str:
    """Добавляет подписку и возвращает её имя. taken — имена, занятые в config.toml."""
    url = check_url(url)
    data, error = load(path)
    if error:
        raise ManagedError(error)
    if len(data["subscriptions"]) >= MAX_SUBSCRIPTIONS:
        raise ManagedError(f"подписок из панели уже {MAX_SUBSCRIPTIONS} — больше нельзя")
    if any(item["url"] == url for item in data["subscriptions"]):
        raise ManagedError("такая подписка уже добавлена")
    used = set(taken) | {item["name"] for item in data["subscriptions"]}
    name = _clean_name(name)
    if name and name in used:
        raise ManagedError(f"подписка с именем «{name}» уже есть")
    if not name:
        name = _free_name((urlsplit(url).hostname or "sub")[:MAX_NAME], used)
    data["subscriptions"].append(
        {"name": name, "url": url, "user_agent": "", "refresh_minutes": DEFAULT_REFRESH}
    )
    save(path, data)
    return name


def remove_subscription(path: Path, name: str) -> bool:
    data, error = load(path)
    if error:
        raise ManagedError(error)
    kept = [item for item in data["subscriptions"] if item["name"] != name]
    if len(kept) == len(data["subscriptions"]):
        return False
    data["subscriptions"] = kept
    save(path, data)
    return True


def split_links(text: str) -> list[str]:
    """Ссылки серверов из вставленного текста — по одной на строку."""
    return [line.strip() for line in text.splitlines() if "://" in line]


def add_links(path: Path, text: str, *, taken: set[str]) -> int:
    """Добавляет ссылки серверов (vless://, vmess://, trojan://, ss://); возвращает,
    сколько добавлено. Ссылка, которую XGW не разбирает, не принимается."""
    data, error = load(path)
    if error:
        raise ManagedError(error)
    known = set(taken) | set(data["links"])
    added = 0
    for link in split_links(text):
        if link in known:
            continue
        raws, _meta, warnings = parse_links_text(link, "manual")
        if not raws:
            reason = warnings[0] if warnings else "формат не распознан"
            raise ManagedError(f"ссылку сервера разобрать не удалось: {reason}")
        if len(data["links"]) >= MAX_LINKS:
            raise ManagedError(f"ссылок из панели уже {MAX_LINKS} — больше нельзя")
        data["links"].append(link)
        known.add(link)
        added += 1
    if added:
        save(path, data)
    return added


def remove_link(path: Path, identifier: str) -> bool:
    data, error = load(path)
    if error:
        raise ManagedError(error)
    kept = [link for link in data["links"] if link_id(link) != identifier]
    if len(kept) == len(data["links"]):
        return False
    data["links"] = kept
    save(path, data)
    return True
