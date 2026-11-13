"""Отображение каталога XGW без Qt и без собственных правил выбора VPN."""
from __future__ import annotations

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


def catalog(state: dict, pool: dict | None = None) -> tuple[list[Source], list[Entry]]:
    """Идентификаторы источников отделены от имён; совпадения с manual/pool не теряют строки."""
    subs = {sub.name: sub for sub in listing.subscriptions(state)}
    sources, entries = [], []
    raw = {str(row.get("tag") or ""): row for row in state.get("servers", [])}
    for group in listing.groups(state):
        source = "sub:" + group.source
        sub = subs.get(group.source)
        detail = " · ".join(part for part in (
            group.count, sub.quota if sub else "", sub.error if sub else "") if part)
        sources.append(Source(source, group.title, detail))
        for index, item in enumerate(group.items):
            row = raw.get(item.tag, {})
            badges = " · ".join(text for _tone, text in item.tags)
            detail = "\n".join(part for part in (badges, item.delay, item.speed, item.sub) if part)
            entries.append(Entry(item.tag or f"missing:{source}:{index}", source, item.name,
                                 detail, item.code, item.status, item.pinned, item.choosable,
                                 row.get("speed_mbps"), row.get("rtt_ms", row.get("delay_ms"))))
    # Подписка с нулём серверов всё равно доступна для просмотра ошибки/квоты.
    for name, sub in subs.items():
        if not any(source.id == "sub:" + name for source in sources):
            sources.append(Source("sub:" + name, name,
                                  " · ".join(filter(None, ("Серверов нет", sub.quota, sub.error)))))
    sources.append(Source(POOL, "Бесплатный пул", listing.pool_summary(state)[1]))
    for group in listing.pool_groups(state, pool):
        for item in group.items:
            entries.append(Entry("pool:" + item.id, POOL, item.name,
                                 "\n".join(filter(None, (group.title,
                                     " · ".join(text for _tone, text in item.tags),
                                     item.value, item.speed, item.sub))),
                                 "", "pool", item.pinned, item.choosable, None, None, True))
    return sources, entries


def filtered(entries: list[Entry], source: str, query: str, status: str, order: str) -> list[Entry]:
    query = query.casefold().strip()
    result = [item for item in entries if item.source == source and
              (not query or query in (item.name + " " + item.country).casefold()) and
              (status == "all" or (status == "chosen" and item.chosen) or
               (status == "usable" and (item.choosable or item.chosen)))]
    if order == "speed":
        result.sort(key=lambda item: (item.speed is None, -(item.speed or 0), item.name.casefold()))
    elif order == "delay":
        result.sort(key=lambda item: (item.delay is None, item.delay or 0, item.name.casefold()))
    else:
        result.sort(key=lambda item: item.name.casefold())
    return result
