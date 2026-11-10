"""Данные разделов «Серверы», «Подписки» и «Устройства» окна XGW без Qt: строки серверов пула и
подписок — уже словами. Тексты те же, что у браузерной панели (ui/app.js: serverRow,
serverNote, renderMain, renderSubs, poolRow, poolNote), чтобы окно и страница говорили об одном
и том же одинаково. Действия — только существующие действия панели (Panel.act).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import model

MANUAL = "manual"  # ui/app.js MANUAL: отдельные ссылки серверов
VERDICTS = {
    "OK": ("ok", "в порядке"), "SLOW": ("warn", "медленный"),
    "FROZEN": ("bad", "замораживается"), "BODY_RESET": ("bad", "обрывается"),
    "STALL_BEFORE_BODY": ("bad", "не отвечает"), "CONNECT_FAIL": ("bad", "недоступен"),
    "TIMEOUT": ("bad", "тайм-аут"),
}
POOL_VERDICTS = {
    **VERDICTS, "REACHABLE": ("warn", "адрес открыт"), "CLOSED": ("bad", "адрес закрыт"),
    "UNTESTED": ("off", "не проверить"),
}
SKIPS = {
    "filter": "не используется: отсеян фильтром имён из config.toml",
    "junk": "не используется: служебная запись подписки",
    "ipv6": "не используется: адрес IPv6",
    "dns": "не используется: имя сервера не находится в DNS — шлюз проверит его снова через "
           "несколько часов или по кнопке «Обновить»",
    "core": "не используется: сервер умеет только sing-box, а он выключен или не установлен",
}
PROFILES = {
    "xray:fragment": "Xray · дробление", "xray:split": "Xray · нарезка",
    "singbox:default": "sing-box", "singbox:tls_fragment": "sing-box · дробление",
    "singbox:mux_padded": "sing-box · mux",
}
LEVELS = (("high", "Высокий"), ("medium", "Средний"), ("low", "Низкий"))
CORES = (("auto", "Авто"), ("xray", "Xray"), ("sing-box", "sing-box"))
POOL_SOURCES = {
    "vpngate": "VPN Gate", "vpnbook": "VPNBook",
    "igareck": "GitHub igareck (проверены в России)", "mahdibland": "GitHub mahdibland",
}
POOL_STATUS = {
    "SUCCESS": ("ok", "ок"), "PARTIAL": ("warn", "частично"),
    "UNAVAILABLE": ("bad", "недоступен"), "RATE_LIMITED": ("warn", "просит реже"),
    "SCHEMA_CHANGED": ("bad", "формат изменился"), "DISABLED": ("off", "выключен"),
    "RESOURCE_LIMIT": ("bad", "слишком большой ответ"),
}
POOL_PROTOCOLS = {
    "vless": "VLESS", "vmess": "VMess", "trojan": "Trojan", "shadowsocks": "Shadowsocks",
    "hysteria2": "Hysteria2", "tuic": "TUIC", "anytls": "AnyTLS", "sstp": "SSTP",
}
ACTIVE = ("member", "spare", "waiting")


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def _num(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def stamp(ts: object, now: float) -> str:
    """Время события: сегодня — «14:05», иначе «06.11 14:05» (stamp в ui/app.js)."""
    value = _num(ts)
    if not value:
        return "—"
    when, today = time.localtime(value), time.localtime(now)
    clock = time.strftime("%H:%M", when)
    return clock if when[:3] == today[:3] else f"{time.strftime('%d.%m', when)} {clock}"


def ago(ts: object, now: float) -> str:
    """«5 мин назад» (ago в ui/app.js)."""
    value = _num(ts)
    if not value:
        return "—"
    minutes = max(0, int((now - value) // 60))
    if minutes < 1:
        return "только что"
    if minutes < 60:
        return f"{minutes} мин назад"
    if minutes < 48 * 60:
        return f"{minutes // 60} ч назад"
    return f"{minutes // 1440} дн назад"


def gigabytes(value: float) -> str:
    amount = value / 1e9
    return f"{amount:.0f}" if amount >= 100 else f"{amount:.1f}".replace(".", ",")


def source_name(source: str) -> str:
    return "Отдельные ссылки" if source == MANUAL else source or "Без подписки"


def multiplier_text(value: float) -> str:
    return "x" + f"{round(value * 100) / 100:g}".replace(".", ",")


# --- серверы подписок -------------------------------------------------------------------------


@dataclass(frozen=True)
class ServerItem:
    fingerprint: str
    tag: str
    name: str
    flag: str
    code: str
    source: str
    status: str
    tone: str  # точка: ok, warn, bad, off
    tags: tuple[tuple[str, str], ...]  # (тон, текст) меток у имени
    sub: str
    speed: str
    delay: str
    editable: bool  # полный отпечаток есть — отключить, убрать, приоритет можно
    choosable: bool  # «Выбрать» — весь трафик через него
    pinned: bool
    dual: bool  # умеет оба ядра — ядро можно выбрать
    core_pin: str
    priority: str
    measurable: bool  # кнопка замера скорости этого сервера
    measuring: bool


@dataclass(frozen=True)
class Group:
    source: str
    title: str
    count: str
    items: tuple[ServerItem, ...]
    can_enable_all: bool
    can_disable_all: bool


def _same(tag: str, other: object) -> bool:
    """sameServer в ui/app.js: probe-тег и тег сервера — один сервер."""
    if not tag or not isinstance(other, str) or not other:
        return False
    tail = lambda value: value.split("-", 1)[1] if "-" in value else value  # noqa: E731
    return tag == other or tail(tag) == tail(other)


def _tone(row: dict) -> str:
    if row.get("status") == "member":
        alive = row.get("alive")
        return "ok" if alive is True else "bad" if alive is False else "off"
    if row.get("status") == "spare":
        return VERDICTS.get(str(row.get("verdict") or ""), ("off", ""))[0]
    return "off"


def _delay(row: dict) -> str:
    rtt, delay = _num(row.get("rtt_ms")), _num(row.get("delay_ms"))
    status = row.get("status")
    if status == "member" and row.get("alive") is False:
        return "нет ответа"
    parts = [f"RTT {model.ms_text(rtt)}" if rtt is not None else "",
             f"проба {model.ms_text(delay)}" if delay is not None else ""]
    text = " · ".join(part for part in parts if part)
    if text:
        return text
    if status == "member":
        return "жив" if row.get("alive") else "проверяется"
    if status == "spare":
        return VERDICTS.get(str(row.get("verdict") or ""), ("off", "не проверялся"))[1]
    return ""


def _speed_note(row: dict, now: float) -> str:
    if _num(row.get("speed_mbps")) is not None:
        return f" · замер скорости {stamp(row.get('speed_ts'), now)}"
    if row.get("status") == "member" and row.get("alive") is False and not row.get("speed_error"):
        return ""
    return f" · {row['speed_note']}" if row.get("speed_note") else ""


def _extra(row: dict, now: float) -> str:
    text = ""
    if _num(row.get("score")) is not None:
        text += f" · рейтинг {row['score']:.2f}".replace(".", ",")
    esc = _dict(row.get("escalation"))
    if esc:
        since = f" с {stamp(esc.get('ts'), now)}" if esc.get("ts") else ""
        after = f" (после {esc['verdict']})" if esc.get("verdict") else ""
        text += f" · обход{since}: {esc.get('label') or ''}{after}"
    unstable = _num(row.get("unstable_until"))
    if unstable and unstable > now:
        text += f" · нестабилен по ТСПУ: шлюз сам его в работу не ставит до {stamp(unstable, now)}"
    if row.get("closed_ts"):
        text += (f" · адрес закрыт: напрямую не открывается (проверено "
                 f"{stamp(row['closed_ts'], now)}), обход не поможет")
    passive = _num(row.get("speed_passive_mbps"))
    if passive is not None and passive >= 1:
        text += f" · из трафика {model.mbps_text(passive)}"
    return text


def _note(row: dict, main: bool, now: float) -> str:
    status = row.get("status")
    if status == "member":
        dead = ""
        if row.get("alive") is False and row.get("dead_since"):
            dead = f" · не отвечает {ago(row['dead_since'], now).replace(' назад', '')}"
        role = "основной" if main else "в работе"
        return role + _speed_note(row, now) + dead + _extra(row, now)
    if status == "spare":
        role = ("резервный: через него пойдёт трафик, если серверы в работе перестанут отвечать"
                if row.get("reserve") else "запасной")
        checked = f" · проверен {stamp(row['scanned'], now)}" if row.get("scanned") else ""
        return role + checked + _speed_note(row, now) + _extra(row, now)
    if status == "disabled":
        return ("отключён — шлюз сейчас уберёт его из работы" if row.get("pending")
                else "отключён: шлюз к нему не обращается")
    if status == "skipped":
        return SKIPS.get(str(row.get("skip") or ""), "не используется")
    return "включён — шлюз сейчас возьмёт его в работу"


def server_item(row: dict, state: dict) -> ServerItem:
    now = _num(state.get("now")) or time.time()
    pin = _dict(state.get("pin"))
    tag = str(row.get("tag") or "")
    fingerprint = str(row.get("fingerprint") or "")
    status = str(row.get("status") or "")
    pinned = bool(pin) and _same(tag, pin.get("tag"))
    main = bool(row.get("main")) and not (pin and not pin.get("down"))
    tags: list[tuple[str, str]] = []
    if pinned:
        tags.append(("warn", "выбран · не отвечает") if pin.get("down") else
                    ("busy", "выбран вручную"))
    elif main:
        tags.append(("busy", "основной"))
    elif row.get("selected"):
        tags.append(("busy", "выбран"))
    if row.get("reserve"):
        tags.append(("warn" if state.get("state") == "RESERVE" else "off", "резервный"))
    profile = str(row.get("profile") or ("xray:fragment" if row.get("fragment") else ""))
    if profile in PROFILES:
        tags.append(("off", PROFILES[profile]))
    multiplier = _num(row.get("multiplier"))
    if multiplier is not None and multiplier != 1:  # x1 у каждого сервера — шум, не сведения
        tags.append(("off", multiplier_text(multiplier)))
    flag, name = model.split_flag(str(row.get("name") or tag or fingerprint))
    speed = _num(row.get("speed_mbps"))
    live = status in ("member", "spare")
    asked = [str(item) for item in _list(_dict(state.get("busy")).get("speed_one"))]
    probe = "probe-" + tag.split("-", 1)[1] if "-" in tag else ""
    editable = len(fingerprint) == 8 and status != "skipped"
    return ServerItem(
        fingerprint=fingerprint, tag=tag, name=name, flag=flag, code=model.country_of(tag),
        source=str(row.get("source") or ""), status=status, tone=_tone(row), tags=tuple(tags),
        sub=_note(row, main, now),
        speed=model.mbps_text(speed) if speed is not None and live else "",
        delay=_delay(row), editable=editable,
        choosable=live and not pinned and bool(tag), pinned=pinned,
        dual=editable and str(row.get("capability") or "dual") == "dual",
        core_pin=str(row.get("core_pin") or "auto"),
        priority=str(row.get("priority") or "medium"),
        measurable=live and bool(tag) and (multiplier or 0) < 100,
        measuring=bool(row.get("speed_queued")) or any(
            key in asked for key in (tag, fingerprint, probe) if key),
    )


def groups(state: dict | None, query: str = "") -> list[Group]:
    """Серверы по подпискам, как renderServers: порядок подписок — sources, затем прочие."""
    if not state:
        return []
    rows = [row for row in _list(state.get("servers")) if isinstance(row, dict)]
    sources = [str(item) for item in _list(state.get("sources"))]
    for row in rows:
        if str(row.get("source") or "") not in sources:
            sources.append(str(row.get("source") or ""))
    needle = query.strip().casefold()
    result = []
    for source in sources:
        mine = [row for row in rows if str(row.get("source") or "") == source]
        on = sum(1 for row in mine if row.get("status") in ACTIVE)
        off = sum(1 for row in mine if row.get("status") == "disabled")
        items = [server_item(row, state) for row in mine]
        if needle:
            items = [item for item in items if needle in item.name.casefold()
                     or needle in item.code.casefold()]
            if not items:
                continue
        result.append(Group(
            source=source, title=source_name(source),
            count=f"включено {on} из {len(mine)}" if mine else "серверов нет",
            items=tuple(items), can_enable_all=off > 0, can_disable_all=on >= 2,
        ))
    return result


def removed(state: dict | None) -> list[tuple[str, str, str]]:
    """Убранные из списка: (отпечаток, имя, подписка)."""
    return [(str(row.get("fingerprint") or ""), str(row.get("name") or ""),
             source_name(str(row.get("source") or "")))
            for row in _list((state or {}).get("removed")) if isinstance(row, dict)]


def selection(state: dict | None) -> tuple[bool, bool, str, str]:
    """(основной сервер включён, замеры идут, пояснение, строка ручного выбора) — renderMain."""
    if not state:
        return False, False, "", ""
    sticky = _dict(state.get("sticky"))
    on = bool(sticky.get("on"))
    unlimited, limited = sticky.get("unlimited_hours") or 0, sticky.get("limited_hours") or 0
    measuring = bool(unlimited or limited)
    pin = _dict(state.get("pin"))
    pinned = bool(pin) and not pin.get("down")
    main = _dict(state.get("main"))
    if not on:
        text = ("Основной сервер выключен: шлюз сам выбирает сервер с наименьшей задержкой и "
                "может менять его каждые полминуты.")
    elif pinned:
        text = ("Пока сервер выбран вручную, основной сервер не выбирается — шлюз выберет его, "
                "когда выбор снимут.")
    elif main:
        speed = _num(main.get("mbps"))
        rate = f" — {model.mbps_text(speed)}" if speed is not None else ""
        basis = "" if main.get("basis") == "speed" else " (скорость ещё не замерена — по задержке)"
        name = model.split_flag(str(main.get("name") or main.get("tag") or ""))[1]
        text = (f"Весь трафик идёт через «{name}»{rate}{basis}. "
                "Шлюз меняет его, если он перестанет отвечать (на сервер той же страны, если "
                "такой есть) или если другой сервер окажется заметно быстрее.")
    else:
        text = ("Весь трафик пойдёт через самый быстрый сервер в работе — шлюз выберет его, как "
                "только серверы ответят.")
    if measuring:
        every = lambda hours: f"раз в {hours} ч" if hours else "не замеряются"  # noqa: E731
        text += (f" Скорость замеряется фоном: серверы в работе — {every(unlimited)}, "
                 f"лимитированные — {every(limited)}, x100 — не замеряются.")
    note = ""
    if pin:
        rows = {str(row.get("tag")): row for row in _list(state.get("servers"))
                if isinstance(row, dict)}
        found = next((row for tag, row in rows.items() if _same(tag, pin.get("tag"))), {})
        name = model.split_flag(str(found.get("name") or pin.get("name") or pin.get("tag")))[1]
        now = _num(state.get("now")) or time.time()
        until = f" до {stamp(pin['until'], now)}" if pin.get("until") else ""
        note = (f"Выбранный вручную «{name}» не отвечает — трафик идёт через серверы, выбранные "
                "автоматически. Когда он снова ответит, шлюз вернётся к нему." if pin.get("down")
                else f"Выбран вручную «{name}»{until}: весь трафик идёт через него. "
                     "«Автовыбор» вернёт выбор шлюзу.")
    return on, measuring, text, note


def notes(state: dict | None) -> list[str]:
    """Предупреждения над списком: мёртвого заменить некем, класс серверов, приоритеты."""
    if not state:
        return []
    found = [model.capital(str(state.get(key) or "")) for key in ("stranded", "class_warning")]
    if any((row.get("priority") or "medium") != "medium"
           for row in _list(state.get("servers")) if isinstance(row, dict)):
        found.append("Приоритет — вес в рейтинге сервера: «высокий» ×1,45, «низкий» ×0,65.")
    return [text for text in found if text]


# --- бесплатный пул -------------------------------------------------------------------------


@dataclass(frozen=True)
class PoolItem:
    id: str
    source: str
    name: str
    tags: tuple[tuple[str, str], ...]
    tone: str
    value: str
    speed: str
    sub: str
    rank: int  # 0 сейчас через, 1 в работе, 2 допущен, 3 рабочий, 4 не прошёл, 5 не проверен
    choosable: bool
    pinned: bool
    country: str = ""


@dataclass(frozen=True)
class PoolGroup:
    source: str
    title: str
    status: tuple[str, str]
    count: str
    note: str
    items: tuple[PoolItem, ...] = field(default_factory=tuple)


def pool_summary(state: dict | None) -> tuple[str, str, str]:
    """(режим off/observe/on, текст сводки, строка трафика устройств)."""
    pool = _dict((state or {}).get("free_pool"))
    mode = str(pool.get("mode") or "off")
    summary = _dict(pool.get("summary")) if mode != "off" else {}
    if not summary:
        text = ("Наблюдение включено: первый опрос источников — в ближайшую минуту." if
                mode != "off" else
                "Альтернативный режим: бесплатные серверы (списки GitHub, VPN Gate, VPNBook) "
                "вместо подписки. Наблюдение собирает их списки через подписку и проверяет "
                "серверы, а трафик идёт как прежде — через подписку.")
        return mode, text, ""
    regions = ", ".join(f"{name} {count}" for name, count in
                        _dict(summary.get("by_region")).items())
    head = "Весь дом через бесплатные серверы" if mode == "on" else "Наблюдение"
    text = (f"{head} (регион {summary.get('region') or '—'}): найдено {summary.get('found') or 0}, "
            f"проверено {summary.get('checked') or 0}, пригодно {summary.get('ready') or 0}"
            + (f" ({regions})" if regions else "")
            + f". Трафик проверок за сутки — {summary.get('spent_mb') or 0} из "
              f"{summary.get('budget_mb') or 0} МБ.")
    return mode, text, _flow_text(_dict(summary.get("traffic")))


def _flow_text(flow: dict) -> str:
    if not flow:
        return ""
    names = "весь дом" if flow.get("all") else f"устройств: {len(_list(flow.get('devices')))}"
    if flow.get("closed"):
        why = "все серверы пула молчат" if flow.get("members") else "допущенных серверов нет"
        return f"Через бесплатные серверы: {names} — закрыто: {why}."
    speed = _num(flow.get("mbps"))
    rate = f", {model.mbps_text(speed)}" if speed is not None else ""
    country = f" ({flow['country']})" if flow.get("country") else ""
    return (f"Через бесплатные серверы: {names} — сервер «{flow.get('server') or '?'}»{country}"
            f"{rate}, задержка {flow.get('delay_ms') or 0} мс; живых {flow.get('alive') or 0} из "
            f"{flow.get('members') or 0}.")


def _works(row: dict) -> bool:
    return row.get("verdict") in ("OK", "SLOW")


def _pool_verdict(row: dict) -> tuple[str, str]:
    if not row.get("verdict"):
        return "off", "не проверялся"
    return POOL_VERDICTS.get(str(row["verdict"]),
                             ("bad", "отказ туннеля" if row.get("backend") == "sstp" else "отказ"))


def _pool_item(row: dict, live: dict | None, current: bool, state: dict) -> PoolItem:
    now = _num(state.get("now")) or time.time()
    pool = _dict(state.get("free_pool"))
    flow = model.pool_flow(state) or {}
    pinned = bool(row.get("id")) and row.get("id") == (pool.get("pin") or "")
    tags: list[tuple[str, str]] = []
    if pinned:
        tags.append(("warn", "выбран · не отвечает") if flow.get("manual") == "down" else
                    ("busy", "выбран вручную"))
    if current:
        tags.append(("busy", "сейчас через"))
    elif live:
        tags.append(("busy", "в работе"))
    elif not row.get("why"):
        tags.append(("ok", "допущен"))
    protocol = POOL_PROTOCOLS.get(str(row.get("protocol") or ""), str(row.get("protocol") or ""))
    tags.append(("off", f"{protocol} · sing-box" if row.get("backend") == "sing-box" else protocol))
    if row.get("country"):
        tags.append(("off", row["country"] if row.get("egress") else
                     f"{row['country']} по каталогу"))
    verdict_tone, verdict = _pool_verdict(row)
    if live:
        tone = "ok" if live.get("alive") else "bad"
        delay = _num(live.get("delay_ms"))
        value = ("нет ответа" if not live.get("alive") else
                 model.ms_text(delay) if delay else "жив")
    else:
        tone = verdict_tone
        delay = _num(row.get("delay_ms"))
        value = model.ms_text(delay) if delay is not None else verdict
    speed = _num((live or {}).get("mbps"))
    failed = bool(row.get("checked_at")) and not _works(row)
    parts = []
    if current:
        parts.append("через него сейчас идут устройства")
    elif live:
        parts.append("в работе у устройств: подхватит трафик, если текущий перестанет отвечать")
    elif not row.get("why"):
        parts.append("допущен к трафику устройств")
    elif not failed:
        parts.append(str(row["why"]))
    if row.get("checked_at"):
        checked = f"проверен {stamp(row['checked_at'], now)}"
        if failed:
            code = "" if row.get("verdict") in POOL_VERDICTS else f" ({row.get('verdict')})"
            error = f": {row['error']}" if row.get("error") else ""
            checked += f" — {verdict}{code}{error}"
        parts.append(checked)
        nxt = _num(row.get("next_at"))
        parts.append(f"перепроверка не раньше {stamp(nxt, now)}" if nxt and nxt > now
                     else "ждёт перепроверки")
    rank = (0 if current else 1 if live else 2 if not row.get("why") else
            3 if _works(row) else 4 if row.get("checked_at") else 5)
    return PoolItem(
        id=str(row.get("id") or ""), source=str(row.get("source") or ""),
        name=str(row.get("name") or ""), tags=tuple(tags), tone=tone, value=value,
        speed=model.mbps_text(speed) if speed is not None else "", sub=" · ".join(parts),
        rank=rank, choosable=not row.get("why") and bool(flow) and not pinned, pinned=pinned,
        country=str(row.get("country") or "").upper()[:2],
    )


def pool_groups(state: dict | None, pool: dict | None, query: str = "") -> list[PoolGroup]:
    """Серверы пула по источникам (renderPoolGroups): порядок внутри — сейчас через, в работе,
    допущенные, рабочие, остальные; при равенстве — по задержке, затем свежие проверки."""
    summary = _dict(_dict((state or {}).get("free_pool")).get("summary"))
    rows = [row for row in _list((pool or {}).get("servers")) if isinstance(row, dict)]
    flow = _dict(summary.get("traffic"))
    live = [item for item in _list(flow.get("servers")) if isinstance(item, dict)]
    known = [item for item in _list(summary.get("sources")) if isinstance(item, dict)]
    sources = [str(item.get("id") or "") for item in known]
    for row in rows:
        if str(row.get("source") or "") not in sources:
            sources.append(str(row.get("source") or ""))
    needle = query.strip().casefold()
    now = _num((state or {}).get("now")) or time.time()
    result = []
    for source in sources:
        src = next((item for item in known if item.get("id") == source), {})
        items = []
        for row in rows:
            if str(row.get("source") or "") != source:
                continue
            hit = next((item for item in live if item.get("id")
                        and str(row.get("id") or "").startswith(str(item["id"]))), None)
            current = bool(hit and flow and not flow.get("closed")
                           and hit.get("tag") == flow.get("tag"))
            items.append((_pool_item(row, hit, current, state or {}), row))
        items.sort(key=lambda pair: (pair[0].rank, _num(pair[1].get("delay_ms")) or 1e9,
                                     -(_num(pair[1].get("checked_at")) or 0)))
        checked = sum(1 for _item, row in items if row.get("checked_at"))
        admitted = sum(1 for _item, row in items if not row.get("why"))
        shown = [item for item, _row in items if not needle or needle in item.name.casefold()]
        status = str(src.get("status") or "")
        note = (f"Список от {stamp(src['retrieved_at'], now)}" if src.get("retrieved_at")
                else "Списка ещё нет")
        note += (" · список устарел" if src.get("stale") else "") + (
            f" · {src['detail']}" if src.get("detail") else "")
        result.append(PoolGroup(
            source=source, title=POOL_SOURCES.get(source, source),
            status=POOL_STATUS.get(status, ("off", status if status != "—" else "")),
            count=(f"допущено {admitted} · проверено {checked} из {len(items)}" if items
                   else "серверов нет"),
            note=note, items=tuple(shown),
        ))
    return result


# --- подписки ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class SubItem:
    name: str
    managed: bool
    tags: tuple[tuple[str, str], ...]
    sub: str
    error: str
    quota: str
    share: float | None  # доля израсходованной квоты 0…1; None — без лимита
    expired: bool
    user_agent: str
    headers: dict


def subscriptions(state: dict | None) -> list[SubItem]:
    now = _num((state or {}).get("now")) or time.time()
    result = []
    for sub in _list((state or {}).get("subscriptions")):
        if not isinstance(sub, dict):
            continue
        tags = []
        if not sub.get("secure"):
            tags.append(("warn", "http, без шифрования"))
        if not sub.get("managed"):
            tags.append(("off", "из config.toml"))
        fetched = f"обновлена {ago(sub['fetched'], now)}" if sub.get("fetched") else \
            "ещё не получена"
        quota = _dict(sub.get("quota"))
        share, text, expired = None, "", False
        if quota:
            used = (_num(quota.get("upload")) or 0) + (_num(quota.get("download")) or 0)
            total = _num(quota.get("total")) or 0
            text = (f"Израсходовано {gigabytes(used)} ГБ из {gigabytes(total)} ГБ, осталось "
                    f"{gigabytes(max(0, total - used))} ГБ" if total else
                    f"Безлимитная · израсходовано {gigabytes(used)} ГБ")
            expire = _num(quota.get("expire"))
            if expire:
                text += f" · до {time.strftime('%d.%m.%Y', time.localtime(expire))}"
                expired = expire < now
            share = min(1.0, used / total) if total else None
        elif sub.get("fetched"):
            text = "Безлимитная: лимит трафика подписка не сообщает"
        result.append(SubItem(
            name=str(sub.get("name") or ""), managed=bool(sub.get("managed")), tags=tuple(tags),
            sub=f"{sub.get('host') or '—'} · серверов: {sub.get('servers') or 0} · {fetched}",
            error=f"Не обновилась: {sub['error']}" if sub.get("error") else "",
            quota=text, share=share, expired=expired,
            user_agent=str(sub.get("user_agent") or ""), headers=_dict(sub.get("headers")),
        ))
    return result


def hidden(state: dict | None) -> list[tuple[str, str]]:
    """Подписки config.toml, убранные в окне или панели (п. 337): (имя, адрес под маской)."""
    return [(str(item.get("name") or ""), str(item.get("host") or "—"))
            for item in _list((state or {}).get("hidden_subscriptions"))
            if isinstance(item, dict) and item.get("name")]


def links(state: dict | None) -> list[tuple[str, str, bool]]:
    """Отдельные ссылки серверов: (id, подпись, можно ли убрать из панели)."""
    return [(str(link.get("id") or ""), str(link.get("label") or ""), bool(link.get("managed")))
            for link in _list((state or {}).get("links")) if isinstance(link, dict)]


def parse_headers(text: str) -> dict[str, str]:
    """Заголовки подписки из поля «Name: Value» по строке (editSubscription в ui/app.js)."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip():
            found[key.strip()] = value.strip()
    return found


@dataclass(frozen=True)
class DeviceItem:
    mac: str
    ip: str
    name: str
    status: str
    bypass: bool
    locked: bool
    offline: bool
    kernel: bool
    route: str
    choices: tuple[tuple[str, str], ...]


def devices(state: dict | None) -> list[DeviceItem]:
    """Устройства и допустимые серверы из того же снимка, что у браузерной панели."""
    state = state or {}
    if not _dict(state.get("lan")).get("interface"):
        return []
    pool = _dict(state.get("free_pool"))
    mode = pool.get("mode", "off")
    flow = _dict(_dict(pool.get("summary")).get("traffic"))
    closed = mode == "off" or bool(flow.get("closed"))
    choices = {"": "Сервер: авто"}
    if mode != "off":
        choices["pool"] = "Бесплатные серверы"
    for row in _list(state.get("servers")):
        row = _dict(row)
        fingerprint = row.get("fingerprint")
        if not isinstance(fingerprint, str) or not fingerprint or row.get("status") not in (
                "member", "spare", "waiting"):
            continue
        name = str(row.get("name") or "Сервер без имени")
        price = _num(row.get("multiplier"))
        choices[fingerprint] = f"{name} · лимит ×{price:g}" if price else name
    result: list[DeviceItem] = []
    for row in _list(state.get("devices")):
        row = _dict(row)
        mac = row.get("mac")
        if not isinstance(mac, str) or not mac:
            continue
        bypass, offline = bool(row.get("bypass")), bool(row.get("offline"))
        locked = bypass and not row.get("managed")
        route = str(row.get("route") or "")
        options = dict(choices)
        if route == "pool" and route not in options:
            options[route] = "Бесплатные серверы (пул выключен)"
        elif route not in options:
            options[route] = "Выбранный сервер недоступен"
        if bypass:
            status = "Мимо VPN · задано в config.toml" if locked else "Мимо VPN"
        elif mode == "on" or route == "pool":
            status = "Бесплатные серверы"
            if closed:
                status += " · зарубежные сайты закрыты"
        elif route and row.get("route_down"):
            status = "Свой сервер недоступен · через основной"
        else:
            status = "Свой сервер" if route else "Через VPN · автовыбор"
        if offline:
            status += " · не в сети"
        result.append(DeviceItem(
            mac, str(row.get("ip") or ""), str(row.get("name") or "Без имени"), status,
            bypass, locked, offline, bool(row.get("kernel")), route, tuple(options.items()),
        ))
    return result
