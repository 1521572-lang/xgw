"""Постоянные SNI и short_id REALITY между опросами подписки (отчёт tspu-audit 06.11.2026).

Часть подписок при каждом скачивании выдаёт тем же серверам другие SNI и short_id REALITY —
по-видимому, по очереди из списков, которые принимает сервер. Для сервера годится любое
значение из его списка, а для шлюза каждое скачивание — новые параметры у десятков серверов:
новое поколение sing-box (прежнее 5 минут доотдаёт соединения) и замена тех же серверов в Xray
раз в час — «карусель» (18 смен поколения за сутки, все server_settings, поля
tls.reality.short_id и tls.server_name у 44 серверов sing-box).

Поэтому сервер с теми же протоколом, адресом, портом, ключом, транспортом и публичным ключом
REALITY, у которого сменились только SNI и/или short_id, сохраняет прежнюю пару до
KEEP_SECONDS. Свежая берётся, когда срок вышел, или раньше — через DEAD_SECONDS, если сервер по
последнему состоянию шлюза мёртв: вдруг прежнего значения уже нет в списке сервера. Несколько
записей на одну точку входа и публичный ключ (варианты, model.split_variants) не трогаются —
у них SNI различает выходы. Работает до split_variants: сводка полей варианта тогда тоже
постоянна.

Файл REALITY_FILE (каталог состояния, 0600): ключ — хеш точки входа и публичного ключа,
значение — пара, когда она принята, когда сервер виден и его итоговый отпечаток (для проверки
«мёртв»). Записи серверов, не виденных KEEP_UNSEEN, забываются.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection
from pathlib import Path

from .model import ServerNode
from .paths import Paths, atomic_write_json

KEEP_SECONDS = 86400.0
DEAD_SECONDS = 6 * 3600.0
KEEP_UNSEEN = 7 * 86400.0
# Проверки, после которых запасной считается годным (watch/scan.py), — как в status.py.
USABLE_VERDICTS = ("OK", "SLOW")


def reality_file(paths: Paths) -> Path:
    return paths.var / "reality.json"


def _settings(node: ServerNode) -> tuple[dict | None, dict | None]:
    """realitySettings Xray и tls sing-box сервера с REALITY (None — нет такой части)."""
    xray = None
    stream = node.outbound.get("streamSettings") if node.outbound else None
    if isinstance(stream, dict) and str(stream.get("security") or "").lower() == "reality":
        settings = stream.get("realitySettings")
        xray = settings if isinstance(settings, dict) else None
    box = None
    if node.singbox is not None and not node.singbox.endpoint:
        tls = node.singbox.main.get("tls")
        if isinstance(tls, dict) and isinstance(tls.get("reality"), dict):
            box = tls
    return xray, box


def pair(node: ServerNode) -> tuple[str, str, str] | None:
    """(публичный ключ, SNI, short_id) сервера с REALITY; None — не REALITY."""
    xray, box = _settings(node)
    if xray is not None:
        key = str(xray.get("publicKey") or "")
        sni, sid = str(xray.get("serverName") or ""), str(xray.get("shortId") or "")
    elif box is not None:
        key = str(box["reality"].get("public_key") or "")
        sni, sid = str(box.get("server_name") or ""), str(box["reality"].get("short_id") or "")
    else:
        return None
    return (key, sni, sid) if key else None


def _put(target: dict, name: str, value: str) -> None:
    if value:
        target[name] = value
    else:
        target.pop(name, None)


def _apply(node: ServerNode, sni: str, sid: str) -> None:
    xray, box = _settings(node)
    if xray is not None:
        _put(xray, "serverName", sni)
        _put(xray, "shortId", sid)
    if box is not None:
        _put(box, "server_name", sni)
        _put(box["reality"], "short_id", sid)


def _key(fingerprint: str, public_key: str) -> str:
    return hashlib.sha256(f"{fingerprint}|{public_key}".encode()).hexdigest()[:16]


def dead_fingerprints(status: dict | None) -> frozenset[str]:
    """Серверы, мёртвые по последнему состоянию шлюза (status.json): участник не жив,
    запасной проверен и не годен. Не проверенный ещё запасной мёртвым не считается."""
    if not isinstance(status, dict):
        return frozenset()
    dead = {str(item.get("fingerprint")) for item in status.get("members") or []
            if isinstance(item, dict) and item.get("alive") is False}
    dead |= {str(item.get("fingerprint")) for item in status.get("spares") or []
             if isinstance(item, dict) and item.get("verdict") is not None
             and item.get("verdict") not in USABLE_VERDICTS}
    return frozenset(dead)


def stabilize(
    nodes: list[ServerNode], known: dict[str, dict], *, now: float,
    dead: Collection[str] = (),
) -> tuple[int, list[tuple[str, ServerNode]]]:
    """Вернуть серверам прежние SNI и short_id (см. описание модуля); known дополняется.
    Отпечатки узлов — ещё общие (до split_variants). Возвращает, скольким серверам пара
    оставлена прежней, и пары (ключ записи, узел) — для remember после split_variants."""
    groups: dict[str, list[tuple[ServerNode, tuple[str, str, str]]]] = {}
    for node in nodes:
        found = pair(node)
        if found is not None:
            groups.setdefault(_key(node.fingerprint, found[0]), []).append((node, found))
    held, tracked = 0, []
    for key, group in groups.items():
        if len(group) != 1:
            known.pop(key, None)  # варианты: SNI различает выходы
            continue
        node, (_public, sni, sid) = group[0]
        entry = known.get(key)
        if not isinstance(entry, dict) or not isinstance(entry.get("sni"), str) \
                or not isinstance(entry.get("sid"), str):
            entry = None
        if entry is not None and (entry["sni"], entry["sid"]) != (sni, sid):
            limit = DEAD_SECONDS if entry.get("fp") in dead else KEEP_SECONDS
            if now - float(entry.get("since") or 0) < limit:
                _apply(node, entry["sni"], entry["sid"])
                held += 1
            else:
                entry = None
        if entry is None:
            entry = {"sni": sni, "sid": sid, "since": now}
        entry["seen"] = now
        known[key] = entry
        tracked.append((key, node))
    return held, tracked


def remember(known: dict[str, dict], tracked: list[tuple[str, ServerNode]], now: float) -> None:
    """Итоговые отпечатки (после split_variants) — для проверки «мёртв» при следующем опросе;
    давно не виденные серверы забываются."""
    for key, node in tracked:
        if key in known:
            known[key]["fp"] = node.fingerprint
    for key in [key for key, entry in known.items()
                if now - float(entry.get("seen") or 0) >= KEEP_UNSEEN]:
        del known[key]


def load(path: Path, read_json) -> dict[str, dict]:
    loaded = read_json(path) or {}
    known = loaded.get("known") if isinstance(loaded, dict) else None
    if not isinstance(known, dict):
        return {}
    return {str(key): dict(entry) for key, entry in known.items() if isinstance(entry, dict)}


def save(path: Path, known: dict[str, dict], now: float, logger) -> None:
    try:
        atomic_write_json(path, {"saved": now, "known": known}, mode=0o600)
    except OSError as exc:  # не root (xgw build) — пары не запоминаются, как раньше
        logger.debug("пары REALITY не записаны: %s", exc)
