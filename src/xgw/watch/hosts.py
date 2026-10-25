"""Проверочные хосты (0.1.18, ТЗ R3): probe.url и probe.urls по кругу.

До 0.1.18 все собственные пробы шлюза — сквозная проверка, сканы запасных, проверка
участников — качали один probe.url. Хост перестал отвечать (403 от CDN, сайт лёг, ТСПУ
отрезал направление) — и пробы падали у всех серверов разом: шлюз объявлял «не отвечает
адрес проверки» и останавливал замену серверов, хотя другие адреса через те же серверы
открывались.

Теперь хостов несколько, на разных доменах и CDN. Пробы берут их по кругу (next), чтобы
ни один хост не видел всех запросов шлюза. Хост, который не ответил, когда другой через тот
же путь ответил, — это наблюдение, а не состояние: он пропускается host_pause_minutes и
отмечается событием. «Не отвечает адрес проверки» (PROBE_TARGET_UNREACHABLE) — только когда
не отвечает ни один хост (daemon._probe_target).

Счётчики удач и ошибок по каждому хосту демон кладёт в базу (META) — их показывают
`xgw diag`, `xgw status` и панель вместе с активным хостом.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ..config import Config

META = "probe_hosts"  # ключ в базе состояния (Store.set_meta)


def host_of(url: str) -> str:
    return urlsplit(url).hostname or url


def all_urls(cfg: Config) -> list[str]:
    """Все проверочные адреса по порядку: probe.url первым."""
    return list(dict.fromkeys([cfg.probe.url, *cfg.probe.urls]))


@dataclass
class HostState:
    ok: int = 0  # удачных проб
    errors: int = 0  # проб, где этот хост не ответил, а другой ответил (или ответил ошибкой)
    paused_until: float = 0.0
    last_error: str = ""
    last_ok: float = 0.0


@dataclass
class ProbeHosts:
    """Круг проверочных хостов одного демона. clock — настенные часы (time.time)."""

    cfg: Config
    clock: Callable[[], float] = time.time
    states: dict[str, HostState] = field(default_factory=dict)
    # Свой круг у каждого вида проб (сквозная проверка, сканы): с общим счётчиком сквозная
    # проверка, идущая через равное число сканов, попадала бы всегда на один и тот же хост.
    _turns: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for url in all_urls(self.cfg):
            self.states.setdefault(url, HostState())

    # --- выбор -----------------------------------------------------------------

    def active(self) -> list[str]:
        """Хосты, которые сейчас не на паузе, по порядку конфига."""
        now = self.clock()
        return [url for url in all_urls(self.cfg) if self.states[url].paused_until <= now]

    def next(self, avoid: str = "", stream: str = "probe") -> str:
        """Следующий хост по кругу своего вида проб stream (кроме avoid). Все на паузе — тот,
        чья пауза кончится раньше: проверять чем-то всё равно надо."""
        urls = all_urls(self.cfg)
        pool = [url for url in self.active() if url != avoid]
        if not pool:
            rest = [url for url in urls if url != avoid] or urls
            return min(rest, key=lambda url: self.states[url].paused_until)
        start = self._turns.get(stream, -1) + 1
        self._turns[stream] = start % len(urls)
        start %= len(urls)
        for shift in range(len(urls)):
            url = urls[(start + shift) % len(urls)]
            if url in pool:
                return url
        return pool[0]

    def primary(self) -> str:
        """Хост для проб самого ядра (burstObservatory): первый не на паузе; его меняют
        только вместе с конфигом Xray, поэтому не по кругу."""
        active = self.active()
        return active[0] if active else self.cfg.probe.url

    # --- итоги -----------------------------------------------------------------

    def answered(self, url: str) -> None:
        state = self.states.get(url)
        if state is None:
            return
        state.ok += 1
        state.last_ok = self.clock()
        state.paused_until = 0.0

    def failed(self, url: str, why: str) -> str:
        """Хост не ответил, а другой ответил (или сам хост вернул ошибку HTTP): пауза.
        Возвращает текст события, если пауза только что началась; иначе пусто."""
        state = self.states.get(url)
        if state is None:
            return ""
        now = self.clock()
        state.errors += 1
        state.last_error = why
        fresh = state.paused_until <= now
        state.paused_until = now + self.cfg.probe.host_pause_minutes * 60.0
        if not fresh:
            return ""
        others = [item for item in self.active() if item != url]
        tail = (
            f"пробы идут через {', '.join(host_of(item) for item in others)}"
            if others else "других доступных хостов сейчас нет"
        )
        return (
            f"проверочный хост {host_of(url)} не отвечает ({why}) — пропускаю его "
            f"{self.cfg.probe.host_pause_minutes} мин; {tail}"
        )

    # --- для базы, статуса и diag -----------------------------------------------

    def snapshot(self) -> dict:
        now = self.clock()
        return {
            "current": self.primary(),
            "hosts": [
                {
                    "url": url, "host": host_of(url), "ok": state.ok, "errors": state.errors,
                    "paused_until": state.paused_until if state.paused_until > now else None,
                    "last_error": state.last_error, "last_ok": state.last_ok or None,
                }
                for url in all_urls(self.cfg)
                for state in (self.states[url],)
            ],
        }

    def dumps(self) -> str:
        return json.dumps(self.snapshot(), ensure_ascii=False)

    def load(self, text: str | None) -> int:
        """Счётчики и паузы прошлого запуска демона (META). Адреса, которых в конфиге больше
        нет (probe.urls сменили), пропускаются молча; сколько записей не разобрано —
        возвращается (демон пишет об этом в журнал)."""
        try:
            saved = json.loads(text) if text else {}
        except ValueError:
            return 1
        items = saved.get("hosts") if isinstance(saved, dict) else None
        if not isinstance(items, list):
            return 0 if not saved else 1
        broken = 0
        for item in items:
            if not isinstance(item, dict):
                broken += 1
                continue
            if item.get("url") not in self.states:
                continue
            try:
                loaded = HostState(
                    ok=int(item.get("ok") or 0), errors=int(item.get("errors") or 0),
                    paused_until=float(item.get("paused_until") or 0.0),
                    last_error=str(item.get("last_error") or ""),
                    last_ok=float(item.get("last_ok") or 0.0),
                )
            except (TypeError, ValueError):
                broken += 1
                continue
            self.states[item["url"]] = loaded
        return broken


def host_specific(kind: str, status: int) -> bool:
    """Сбой пробы говорит о самом хосте, а не о сервере: хост ответил ошибкой HTTP (403,
    404, 5xx). Обрыв, таймаут и «заморозка» — это путь через сервер; их хост не объясняет."""
    return kind == "http" and status >= 400


def describe(snapshot: dict | None) -> list[str]:
    """Строки для `xgw status` и diag: активный хост и ошибки по каждому."""
    if not snapshot:
        return []
    now = time.time()
    lines = []
    for item in snapshot.get("hosts") or []:
        mark = " (активный)" if item.get("url") == snapshot.get("current") else ""
        text = (f"{item.get('host')}{mark}: удачно {item.get('ok', 0)}, "
                f"ошибок {item.get('errors', 0)}")
        paused = item.get("paused_until")
        if paused and paused > now:
            text += f", пропускается ещё {max(1, int((paused - now) // 60))} мин"
        if item.get("last_error"):
            text += f" — последняя ошибка: {item['last_error']}"
        lines.append(text)
    return lines
