"""Состояние XGW: SQLite (известные узлы, события, мета) и кэш подписок."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from .paths import atomic_write_bytes, atomic_write_json

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS nodes (
    fingerprint TEXT PRIMARY KEY,
    tag TEXT,
    role TEXT,
    name TEXT,
    source TEXT,
    address TEXT,
    port INTEGER,
    updated INTEGER
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL,
    kind TEXT,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS scans (
    probe_tag TEXT PRIMARY KEY,
    verdict TEXT,
    bytes INTEGER,
    seconds REAL,
    error TEXT,
    ts REAL
);
"""


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def upsert_nodes(self, entries: list[dict]) -> None:
        self.conn.executemany(
            "INSERT INTO nodes (fingerprint, tag, role, name, source, address, port, updated) "
            "VALUES (:fingerprint, :tag, :role, :name, :source, :address, :port, :updated) "
            "ON CONFLICT(fingerprint) DO UPDATE SET tag=excluded.tag, role=excluded.role, "
            "name=excluded.name, source=excluded.source, address=excluded.address, "
            "port=excluded.port, updated=excluded.updated",
            entries,
        )
        self.conn.commit()

    def replace_nodes(self, entries: list[dict]) -> None:
        """Таблица узлов отражает последний сгенерированный конфиг целиком:
        серверы, пропавшие из подписки, в ней не остаются."""
        with self.conn:
            self.conn.execute("DELETE FROM nodes")
            self.conn.executemany(
                "INSERT INTO nodes (fingerprint, tag, role, name, source, address, port, updated) "
                "VALUES (:fingerprint, :tag, :role, :name, :source, :address, :port, :updated)",
                entries,
            )

    def all_nodes(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM nodes ORDER BY role, tag").fetchall()
        return [dict(row) for row in rows]

    def add_event(self, kind: str, detail: str) -> None:
        self.conn.execute(
            "INSERT INTO events (ts, kind, detail) VALUES (?, ?, ?)",
            (time.time(), kind, detail),
        )
        self.conn.commit()

    def recent_events(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT ts, kind, detail FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def last_event_time(self, kind: str) -> float | None:
        row = self.conn.execute(
            "SELECT ts FROM events WHERE kind = ? ORDER BY id DESC LIMIT 1", (kind,)
        ).fetchone()
        return float(row["ts"]) if row else None

    def save_scan(
        self,
        probe_tag: str,
        verdict: str,
        bytes_read: int,
        seconds: float,
        error: str = "",
        ts: float | None = None,
    ) -> None:
        """Результат скана. Ключ — probe-тег: он не меняется, когда узел переходит
        из запасных в участники и обратно."""
        self.conn.execute(
            "INSERT INTO scans (probe_tag, verdict, bytes, seconds, error, ts) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(probe_tag) DO UPDATE SET "
            "verdict=excluded.verdict, bytes=excluded.bytes, seconds=excluded.seconds, "
            "error=excluded.error, ts=excluded.ts",
            (probe_tag, verdict, bytes_read, seconds, error, time.time() if ts is None else ts),
        )
        self.conn.commit()

    def scans(self) -> dict[str, dict]:
        rows = self.conn.execute("SELECT * FROM scans").fetchall()
        return {row["probe_tag"]: dict(row) for row in rows}

    def prune_scans(self, keep: set[str]) -> None:
        """Убирает сканы узлов, которых больше нет в конфиге."""
        stale = [(tag,) for tag in self.scans() if tag not in keep]
        if stale:
            self.conn.executemany("DELETE FROM scans WHERE probe_tag = ?", stale)
            self.conn.commit()

    def dump_state(self) -> str:
        return json.dumps(
            {"meta": {r["key"]: r["value"] for r in self.conn.execute("SELECT * FROM meta")},
             "nodes": self.all_nodes(),
             "events": self.recent_events(10)},
            ensure_ascii=False,
            indent=2,
        )


@dataclass
class CachedSubscription:
    body: bytes
    userinfo: dict[str, int] = field(default_factory=dict)
    saved_at: float = 0.0


# Сколько хранится адрес домена подписки (HostCache): неделю — дольше владелец подписки мог
# переехать, а сертификат прежнего адреса уже никто не продлевает.
HOST_CACHE_TTL = 7 * 86400.0
HOST_CACHE_FILE = "dns-cache.json"
HOST_CACHE_MAX = 4  # адресов на имя: последние удачные
# Подписка пришла через Xray (прямого запроса не было): прямой адрес её сервера проверяется не
# чаще раза в сутки (engine._check_direct), неудачная проверка повторяется через 6 часов.
HOST_CHECK_EVERY = 86400.0
HOST_CHECK_RETRY = 6 * 3600.0


class HostCache:
    """Адреса доменов подписок, с которыми запрос уже удался: `cache/dns-cache.json`.

    Запись появляется только после удачного прямого соединения — рукопожатие TLS с
    проверкой сертификата по имени прошло — и только для адреса, с которым оно и было: либо
    прямой запрос подписки, из ответа которого разобрались серверы (engine._load_subscription),
    либо (подписка пришла через Xray, а прямого запроса при живом Xray не бывает — отчёт 0.2.0:
    файла не было вовсе) раз в сутки отдельное рукопожатие без запроса HTTP
    (fetch.check_direct). Служебные адреса (fetch.is_bogon) не записываются. Нужен кэш, когда
    шифрованные резолверы недоступны: подписка всё равно получается по прежнему адресу, а
    подменить его DNS провайдера не может — запись делается
    не по ответу DNS, а по проверенному соединению (п. 1.1 рекомендаций к аудиту 0.1.18)."""

    def __init__(self, directory: Path, *, clock=time.time) -> None:
        self.path = directory / HOST_CACHE_FILE
        self.clock = clock

    def _load(self) -> dict[str, dict]:
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(loaded, dict):
            return {}
        return {
            str(host): entry for host, entry in loaded.items()
            if isinstance(entry, dict) and isinstance(entry.get("ips"), list)
        }

    def addresses(self) -> dict[str, list[str]]:
        """Имя → адреса, записанные не раньше HOST_CACHE_TTL назад (новые первыми)."""
        now = self.clock()
        result: dict[str, list[str]] = {}
        for host, entry in self._load().items():
            stamp = entry.get("ts")
            if not isinstance(stamp, (int, float)) or now - stamp > HOST_CACHE_TTL:
                continue
            ips = [str(ip) for ip in entry["ips"] if isinstance(ip, str)]
            if ips:
                result[host] = ips
        return result

    def age(self, host: str) -> float | None:
        """Сколько секунд назад адрес host последний раз подтвердился; None — записи нет."""
        stamp = (self._load().get(host) or {}).get("ts")
        if not isinstance(stamp, (int, float)):
            return None
        return max(0.0, self.clock() - stamp)

    def remember(self, host: str, address: str) -> None:
        """Адрес, с которым запрос к host только что удался."""
        from .fetch import is_bogon

        if not host or not address or is_bogon(address):
            return
        entries = self._load()
        now = self.clock()
        known = [ip for ip in (entries.get(host) or {}).get("ips", []) if ip != address]
        entries[host] = {"ips": [address, *known][:HOST_CACHE_MAX], "ts": now}
        fresh = {
            name: entry for name, entry in entries.items()
            if isinstance(entry.get("ts"), (int, float)) and now - entry["ts"] <= HOST_CACHE_TTL
        }
        atomic_write_json(self.path, fresh, mode=0o600)


class SubscriptionCache:
    """Последняя удачная версия каждой подписки в /var/lib/xgw/cache.

    Тело содержит ссылки с секретами, поэтому файлы — 0600. Сохраняется только
    ответ, из которого удалось разобрать серверы: пустой или битый кэш не затирает.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _stem(self, name: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._") or "sub"
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
        return f"{safe[:40]}-{digest}"

    def save(self, name: str, body: bytes, userinfo: dict[str, int] | None = None) -> None:
        stem = self._stem(name)
        atomic_write_bytes(self.directory / f"{stem}.body", body, mode=0o600)
        atomic_write_json(
            self.directory / f"{stem}.json",
            {"name": name, "saved_at": time.time(), "userinfo": userinfo or {}},
            mode=0o600,
        )

    def saved_at(self, name: str) -> float:
        """Когда подписку удалось получить в последний раз; 0 — ни разу."""
        try:
            loaded = json.loads(
                (self.directory / f"{self._stem(name)}.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return 0.0
        value = loaded.get("saved_at") if isinstance(loaded, dict) else None
        return float(value) if isinstance(value, (int, float)) else 0.0

    def forget(self, name: str) -> None:
        """Убирает кэш удалённой подписки: в теле — ссылки с ключами."""
        stem = self._stem(name)
        for suffix in (".body", ".json"):
            (self.directory / f"{stem}{suffix}").unlink(missing_ok=True)

    def load(self, name: str) -> CachedSubscription | None:
        stem = self._stem(name)
        try:
            body = (self.directory / f"{stem}.body").read_bytes()
        except OSError:
            return None
        meta: dict = {}
        try:
            loaded = json.loads((self.directory / f"{stem}.json").read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                meta = loaded
        except (OSError, json.JSONDecodeError):
            pass
        userinfo = meta.get("userinfo")
        saved_at = meta.get("saved_at")
        return CachedSubscription(
            body=body,
            userinfo=userinfo if isinstance(userinfo, dict) else {},
            saved_at=float(saved_at) if isinstance(saved_at, (int, float)) else 0.0,
        )
