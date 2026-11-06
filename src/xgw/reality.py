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
последнему состоянию шлюза мёртв: вдруг прежнего значения уже нет в списке сервера.

Несколько записей на одну точку входа и публичный ключ (отчёт reality-pin: без них удержание
ловило 12–14 серверов, а смены с полями REALITY остались) — для REALITY это один и тот же
сервер: адрес, порт и ключ определяют его, SNI — лишь маскировка. Такая группа держит набор
пар целиком: записи упорядочены по прочим полям (без SNI и short_id) и имени, и каждая
получает пару своего места из прошлого опроса, если число записей то же. Работает до
split_variants: сводка полей варианта тогда тоже постоянна.

Файл REALITY_FILE (каталог состояния, 0600): ключ — хеш точки входа и публичного ключа,
значение — пары по местам, когда они приняты, когда группа видна и итоговые отпечатки (для
проверки «мёртв»). Записи, не виденные KEEP_UNSEEN, забываются.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection
from dataclasses import dataclass
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


@dataclass
class Outcome:
    """Итог stabilize для журнала: held — скольким серверам пара оставлена прежней (из них
    grouped — в группах из нескольких записей); renewed — сколько приняли свежую пару, когда
    подписка её сменила: срок вышел, сервер мёртв или число записей группы другое."""

    held: int = 0
    grouped: int = 0
    renewed: int = 0


def _stable(node: ServerNode) -> str:
    """Описание сервера без SNI и short_id — порядок записей внутри группы."""
    outbound = json.loads(json.dumps(node.outbound or {}, default=str))
    main = json.loads(json.dumps(node.singbox.main if node.singbox else {}, default=str))
    stream = outbound.get("streamSettings")
    settings = stream.get("realitySettings") if isinstance(stream, dict) else None
    if isinstance(settings, dict):
        settings.pop("serverName", None)
        settings.pop("shortId", None)
    tls = main.get("tls")
    if isinstance(tls, dict):
        tls.pop("server_name", None)
        if isinstance(tls.get("reality"), dict):
            tls["reality"].pop("short_id", None)
    return json.dumps([outbound, main, node.name], sort_keys=True, ensure_ascii=False)


def _pairs(entry: object) -> list[list[str]] | None:
    """Пары записи по местам; прежний формат (одна пара sni/sid) — список из одной."""
    if not isinstance(entry, dict):
        return None
    pairs = entry.get("pairs")
    if pairs is None and isinstance(entry.get("sni"), str) and isinstance(entry.get("sid"), str):
        pairs = [[entry["sni"], entry["sid"]]]
    if not isinstance(pairs, list) or not all(
            isinstance(item, list) and len(item) == 2
            and all(isinstance(value, str) for value in item) for item in pairs):
        return None
    return [list(item) for item in pairs]


def _fingerprints(entry: dict) -> set[str]:
    found = entry.get("fps")
    fps = {str(fp) for fp in found} if isinstance(found, list) else set()
    if entry.get("fp"):
        fps.add(str(entry["fp"]))
    return fps


def stabilize(
    nodes: list[ServerNode], known: dict[str, dict], *, now: float,
    dead: Collection[str] = (),
) -> tuple[Outcome, list[tuple[str, list[ServerNode]]]]:
    """Вернуть серверам прежние SNI и short_id (см. описание модуля); known дополняется.
    Отпечатки узлов — ещё общие (до split_variants). Возвращает итог и группы (ключ записи,
    узлы по местам) — для remember после split_variants."""
    groups: dict[str, list[tuple[ServerNode, tuple[str, str, str]]]] = {}
    for node in nodes:
        found = pair(node)
        if found is not None:
            groups.setdefault(_key(node.fingerprint, found[0]), []).append((node, found))
    outcome, tracked = Outcome(), []
    for key, group in groups.items():
        group.sort(key=lambda item: _stable(item[0]))
        ordered = [node for node, _found in group]
        fresh = [[sni, sid] for _node, (_public, sni, sid) in group]
        entry = known.get(key)
        pairs = _pairs(entry)
        if pairs is not None and pairs != fresh:
            limit = DEAD_SECONDS if _fingerprints(entry) & set(dead) else KEEP_SECONDS
            if len(pairs) == len(fresh) and now - float(entry.get("since") or 0) < limit:
                for node, (sni, sid) in zip(ordered, pairs, strict=True):
                    _apply(node, sni, sid)
                changed = sum(1 for old, new in zip(pairs, fresh, strict=True) if old != new)
                outcome.held += changed
                if len(ordered) > 1:
                    outcome.grouped += changed
            else:
                outcome.renewed += len(fresh)
                pairs = None
        if pairs is None:
            entry = {"pairs": fresh, "since": now}
        else:
            entry = {name: value for name, value in entry.items() if name not in ("sni", "sid")}
            entry["pairs"] = pairs
        entry["seen"] = now
        known[key] = entry
        tracked.append((key, ordered))
    return outcome, tracked


def remember(known: dict[str, dict], tracked: list[tuple[str, list[ServerNode]]],
             now: float) -> None:
    """Итоговые отпечатки (после split_variants) — для проверки «мёртв» при следующем опросе;
    давно не виденные серверы забываются."""
    for key, ordered in tracked:
        if key in known:
            known[key].pop("fp", None)
            known[key]["fps"] = [node.fingerprint for node in ordered]
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
