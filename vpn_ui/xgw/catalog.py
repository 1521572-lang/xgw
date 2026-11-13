"""Отображение каталога XGW без Qt и без собственных правил выбора VPN."""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from xgw.gui import listing

POOL = "pool:"


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    detail: str


@dataclass(frozen=True)
class Entry:
    id: str
    source: str
    name: str
    detail: str
    country: str
    status: str
    chosen: bool
    choosable: bool
    speed: float | None
    delay: float | None
    pool: bool = False
    rating: float | None = None
    active: bool = False


def _country(row: dict) -> str:
    code = row.get("endpoint_country")
    if isinstance(code, str) and len(code) == 2 and code.isascii() and code.isalpha():
        return code.upper()
    return ""


def _number(value: object) -> float | None:
    if type(value) in (int, float) and math.isfinite(value):
        return float(value)
    return None


def catalog(state: dict, pool: dict | None = None) -> tuple[list[Source], list[Entry]]:
    """Идентификаторы источников отделены от имён; совпадения с manual/pool не теряют строки."""
    subs = {sub.name: sub for sub in listing.subscriptions(state)}
    sources, entries = [], []
    raw = {str(row["fingerprint"]): row for row in state.get("servers", [])
           if isinstance(row, dict) and row.get("fingerprint")}
    tagged = {str(row["tag"]): row for row in state.get("servers", [])
              if isinstance(row, dict) and row.get("tag")}
    for group in listing.groups(state):
        source = "sub:" + group.source
        sub = subs.get(group.source)
        detail = " · ".join(part for part in (
            group.count, sub.quota if sub else "", sub.error if sub else "") if part)
        sources.append(Source(source, group.title, detail))
        for index, item in enumerate(group.items):
            row = raw.get(item.fingerprint) or tagged.get(item.tag, {})
            badges = " · ".join(text for _tone, text in item.tags)
            transport = " · ".join(str(row[key]) for key in ("protocol", "core") if row.get(key))
            detail = "\n".join(filter(None, (group.title, badges, transport, item.delay, item.sub)))
            delay = _number(row.get("rtt_ms"))
            entries.append(Entry(item.tag or f"missing:{source}:{item.fingerprint or index}",
                                 source, item.name, detail, _country(row), item.status,
                                 item.pinned, item.choosable, _number(row.get("speed_mbps")),
                                 delay if delay is not None else _number(row.get("delay_ms")),
                                 rating=_number(row.get("score")),
                                 active=any(text == "основной" for _tone, text in item.tags)))
    # Подписка с нулём серверов всё равно доступна для просмотра ошибки/квоты.
    for name, sub in subs.items():
        if not any(source.id == "sub:" + name for source in sources):
            sources.append(Source("sub:" + name, name,
                                  " · ".join(filter(None, ("Серверов нет", sub.quota, sub.error)))))
    sources.append(Source(POOL, "Бесплатный пул", listing.pool_summary(state)[1]))
    pool_rows = {row["id"]: row for row in (pool or {}).get("servers", [])
                 if isinstance(row, dict) and row.get("id")}
    flow = (((state.get("free_pool") or {}).get("summary") or {}).get("traffic") or {})
    live = [row for row in flow.get("servers", []) if isinstance(row, dict) and row.get("id")]
    for group in listing.pool_groups(state, pool):
        for item in group.items:
            row = pool_rows.get(item.id, {})
            observed = next((value for value in live if item.id.startswith(str(value["id"]))), {})
            entries.append(Entry("pool:" + item.id, POOL, item.name,
                                 "\n".join(filter(None, (group.title,
                                     " · ".join(text for _tone, text in item.tags),
                                     item.value, item.sub))),
                                 _country(row), "pool", item.pinned, item.choosable,
                                 _number(observed.get("mbps")), _number(row.get("delay_ms")),
                                 pool=True, rating=_number(row.get("score")),
                                 active=item.rank == 0))
    return sources, entries


def filtered(entries: list[Entry], source: str, query: str, status: str, order: str, *,
             country_name: Callable[[str], str] = str) -> list[Entry]:
    query = query.casefold().strip()
    result = [item for item in entries if item.source == source and
              (not query or query in
               f"{item.name} {item.country} {country_name(item.country)}".casefold()) and
              (status == "all" or (status == "chosen" and item.chosen) or
               (status == "usable" and (item.choosable or item.chosen)))]
    if order == "speed":
        result.sort(key=lambda item: (item.speed is None, -(item.speed or 0), item.name.casefold()))
    elif order == "delay":
        result.sort(key=lambda item: (item.delay is None, item.delay or 0, item.name.casefold()))
    elif order == "country":
        result.sort(key=lambda item: (not item.country, country_name(item.country).casefold(),
                                     item.name.casefold()))
    else:
        result.sort(key=lambda item: item.name.casefold())
    return result
