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
пар: место записи — хеш прочих полей (без SNI и short_id) и имени, и запись получает пару
своего места из прошлого опроса. Отчёт reality-pin-r2: число записей в группе меняется от
опроса к опросу (20–23 свежие пары за опрос, когда при другом числе записей обновлялась вся
группа), — поэтому место, которого не было, берёт ещё не занятую прежнюю пару группы (место
пропало — его пара свободна: все записи группы — один сервер), и только когда их не осталось —
свежую. Отчёт reality-pin-r3: записи группы пропадают и возвращаются (80 → 76 → 80), и
вернувшаяся получала свежую пару — новый отпечаток и проверки заново. Поэтому пара пропавшего
места помнится (`gone`, до KEEP_SECONDS) и возвращается ему, если её не заняла другая запись.
Работает до split_variants: сводка полей варианта тогда тоже постоянна, и вернувшаяся запись
получает прежний отпечаток (история split_variants).

Отчёт sb-composition: состав sing-box меняет только подписка (за 3 часа новых 12, пропавших 17),
а записей групп пропало 35 и вернулось лишь 4 — подписка выдаёт группе то больше записей, то
меньше. Когда записей столько же, новая берёт пару пропавшей и сохраняет её отпечаток; смена
состава — только от другого числа записей. Поэтому пропавшее место группы, чья точка входа
осталась, держится копией (`copies`): соседняя запись того же вида (поля без SNI, short_id и
имени те же) с парой пропавшей — тот же сервер REALITY, и отпечаток тот же. Копия живёт, пока
помнится пара пропавшего места (KEEP_SECONDS), пока группа держит пары и пока копия по
состоянию шлюза не мертва; новая запись группы сначала занимает пару пропавшего места, и копия
уходит. Группа пропала целиком — копий нет.

Файл REALITY_FILE (каталог состояния, 0600): ключ — хеш точки входа и публичного ключа,
значение — пары по местам (`pairs`, `ids`), когда они приняты, когда группа видна и итоговые
отпечатки (для
проверки «мёртв»). Записи, не виденные KEEP_UNSEEN, забываются.
"""

from __future__ import annotations

import copy
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
    прежняя была: срок вышел, сервер мёртв или в группе новая запись, а свободной прежней пары
    нет."""

    held: int = 0
    grouped: int = 0
    renewed: int = 0
    # Записи групп, пропавшие в этом опросе, и вернувшиеся с прежней парой.
    vanished: int = 0
    returned: int = 0
    # Пропавших мест, оставленных копиями соседней записи (группа того же размера в sing-box).
    copies: int = 0


def _stable(node: ServerNode, *, named: bool = True) -> str:
    """Описание сервера без SNI и short_id (и без имени, named=False) — порядок записей
    внутри группы."""
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
    return json.dumps([outbound, main, node.name if named else ""], sort_keys=True,
                      ensure_ascii=False)


def _shape(node: ServerNode) -> str:
    """Вид записи: хеш описания без SNI, short_id и имени — копия пропавшей записи делается
    только с соседки того же вида."""
    return hashlib.sha256(_stable(node, named=False).encode()).hexdigest()[:12]


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


def _places(ordered: list[ServerNode]) -> list[str]:
    """Место записи в группе: хеш прочих полей и имени; одинаковые — с номером по порядку."""
    seen: dict[str, int] = {}
    ids = []
    for node in ordered:
        base = hashlib.sha256(_stable(node).encode()).hexdigest()[:12]
        seen[base] = seen.get(base, 0) + 1
        ids.append(base if seen[base] == 1 else f"{base}#{seen[base]}")
    return ids


def _gone(entry: dict, now: float, dead: Collection[str] = ()) -> dict[str, list]:
    """Пары пропавших мест: место → [SNI, short_id, когда пропало, вид записи, отпечаток
    копии]; старше KEEP_SECONDS и с мёртвой копией — нет. Прежний формат (три поля) — без вида:
    копии у такого места не будет."""
    found = entry.get("gone")
    if not isinstance(found, dict):
        return {}
    gone = {}
    for pid, item in found.items():
        if not (isinstance(item, list) and len(item) in (3, 5)
                and all(isinstance(value, str) for value in item[:2] + item[3:])
                and isinstance(item[2], int | float) and now - float(item[2]) < KEEP_SECONDS):
            continue
        item = [*item[:3], *(item[3:] or ["", ""])]
        if not item[4] or item[4] not in dead:
            gone[str(pid)] = item
    return gone


def _choose(
    ids: list[str], fresh: list[list[str]], entry: dict, pairs: list[list[str]], now: float,
    dead: Collection[str] = (),
) -> tuple[list[list[str]], list[bool], dict[str, list], int, int]:
    """Пары по местам: своё место — его прежняя пара; вернувшееся — пара, с которой оно
    пропало, если её не заняли; новое — пара пропавшего места (сначала пропавшего сейчас), нет
    такой — свежая. Возвращает пары, признаки «пара из прошлого», пропавшие места с ещё не
    занятыми парами, сколько мест вернулось и сколько пропало сейчас."""
    old_ids = [str(pid) for pid in entry.get("ids") or []] if isinstance(
        entry.get("ids"), list) and len(entry["ids"]) == len(pairs) else []
    shapes = entry.get("shapes")
    if not (isinstance(shapes, list) and len(shapes) == len(old_ids)
            and all(isinstance(shape, str) for shape in shapes)):
        shapes = [""] * len(old_ids)
    places = list(zip(old_ids, pairs, shapes, strict=True)) if old_ids else []
    by_id = {pid: item for pid, item, _shape in places}
    gone = _gone(entry, now, dead)
    current = set(ids)
    vanished = 0
    for pid, item, shape in places:
        if pid not in current:
            gone[pid] = [*item, now, shape, ""]
            vanished += 1
    chosen: list[list[str] | None] = [by_id.get(pid) for pid in ids]
    used = {tuple(item) for item in chosen if item is not None}
    returned = 0
    for index, pid in enumerate(ids):
        back = gone.get(pid)
        if chosen[index] is None and back is not None and tuple(back[:2]) not in used:
            chosen[index] = back[:2]
            used.add(tuple(back[:2]))
            returned += 1
    if old_ids:
        free = [item[:2] for _pid, item in sorted(
            ((pid, item) for pid, item in gone.items() if pid not in current),
            key=lambda found: -float(found[1][2]))]
    else:
        free = [list(item) for item in pairs]
    kept = [item is not None for item in chosen]
    for index, new in enumerate(fresh):
        if chosen[index] is not None:
            continue
        while free and tuple(free[0]) in used:
            free.pop(0)
        if free:
            chosen[index] = free.pop(0)
            kept[index] = True
        else:
            chosen[index] = new
        used.add(tuple(chosen[index]))
    gone = {pid: item for pid, item in gone.items()
            if pid not in current and tuple(item[:2]) not in used}
    return [list(item) for item in chosen if item is not None], kept, gone, returned, vanished


def _copies(
    ordered: list[ServerNode], gone: dict[str, list], taken: list[list[str]],
) -> list[tuple[str, ServerNode]]:
    """Копии пропавших мест группы: соседняя запись того же вида с парой пропавшей — тот же
    сервер REALITY (см. описание модуля). Записи с исходным тегом цепочки не копируются: тег
    в Xray должен быть один."""
    used = {tuple(item) for item in taken}
    by_shape: dict[str, ServerNode] = {}
    for node in ordered:
        by_shape.setdefault(_shape(node), node)
    found = []
    for pid, item in gone.items():
        sibling = by_shape.get(item[3]) if item[3] else None
        if sibling is None or sibling.keep_tag or tuple(item[:2]) in used:
            continue
        twin = copy.deepcopy(sibling)
        _apply(twin, item[0], item[1])
        used.add(tuple(item[:2]))
        found.append((pid, twin))
    return found


def copies(tracked: list[tuple[str, list[ServerNode], list]]) -> list[ServerNode]:
    """Копии пропавших мест из итога stabilize — их добавляют к серверам до split_variants."""
    return [twin for _key, _ordered, found in tracked for _pid, twin in found]


def stabilize(
    nodes: list[ServerNode], known: dict[str, dict], *, now: float,
    dead: Collection[str] = (),
) -> tuple[Outcome, list[tuple[str, list[ServerNode], list[tuple[str, ServerNode]]]]]:
    """Вернуть серверам прежние SNI и short_id (см. описание модуля); known дополняется.
    Отпечатки узлов — ещё общие (до split_variants). Возвращает итог и группы (ключ записи,
    узлы по местам, копии пропавших мест) — для copies и remember после split_variants.
    Сами копии в nodes не добавляются."""
    groups: dict[str, list[tuple[ServerNode, tuple[str, str, str]]]] = {}
    for node in nodes:
        found = pair(node)
        if found is not None:
            groups.setdefault(_key(node.fingerprint, found[0]), []).append((node, found))
    outcome, tracked = Outcome(), []
    for key, group in groups.items():
        group.sort(key=lambda item: _stable(item[0]))
        ordered = [node for node, _found in group]
        ids = _places(ordered)
        fresh = [[sni, sid] for _node, (_public, sni, sid) in group]
        entry = known.get(key)
        pairs = _pairs(entry)
        since, gone, twins = now, {}, []
        if pairs is not None:
            limit = DEAD_SECONDS if _fingerprints(entry) & set(dead) else KEEP_SECONDS
            within = now - float(entry.get("since") or 0) < limit
            previous, kept, gone, returned, vanished = _choose(
                ids, fresh, entry, pairs, now, dead)
            outcome.vanished += vanished
            if within:
                outcome.returned += returned
                twins = _copies(ordered, gone, previous)
                outcome.copies += len(twins)
            else:
                gone = {}
            for node, prev, new, from_past in zip(ordered, previous, fresh, kept, strict=True):
                if within and from_past:
                    if prev != new:
                        _apply(node, *prev)
                        outcome.held += 1
                        outcome.grouped += len(ordered) > 1
                elif not from_past or prev != new:
                    outcome.renewed += 1
            if within:
                since = float(entry.get("since", now))
            pairs = previous if within else fresh
        else:
            pairs = fresh
        entry = {name: value for name, value in (entry or {}).items()
                 if name not in ("sni", "sid", "fp")}
        entry.update(pairs=pairs, ids=ids, shapes=[_shape(node) for node in ordered],
                     since=since, seen=now, gone=gone)
        known[key] = entry
        tracked.append((key, ordered, twins))
    return outcome, tracked


def remember(known: dict[str, dict],
             tracked: list[tuple[str, list[ServerNode], list[tuple[str, ServerNode]]]],
             now: float) -> None:
    """Итоговые отпечатки (после split_variants) — для проверки «мёртв» при следующем опросе
    (у копий — в записи пропавшего места); давно не виденные серверы забываются."""
    for key, ordered, twins in tracked:
        if key in known:
            known[key].pop("fp", None)
            known[key]["fps"] = [node.fingerprint for node in ordered]
            gone = known[key].get("gone") or {}
            for pid, twin in twins:
                if pid in gone:
                    gone[pid][4] = twin.fingerprint
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
