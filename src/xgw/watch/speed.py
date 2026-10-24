"""Замер скорости серверов и выбор основного сервера (0.1.9; все серверы — 0.1.18).

Ядро само (leastPing) берёт сервер с наименьшей задержкой и меняет выбор после каждой
пробы, если задержки близки (ASSUMPTIONS, п. 49): адрес выхода скачет каждые 30 с, сайты
и CDN видят то одну страну, то другую. Задержка к тому же — не скорость: проба 57 КБ
укладывается в несколько обменов с сервером и о ширине канала почти ничего не говорит.

Поэтому демон держит один «основной» сервер — самый быстрый по замеру — и закрепляет его в
ядре (`xray api bo`, как ручное закрепление). Остальные участники остаются наготове: ядро
пробует их как раньше, и при отказе основного демон сразу передаёт трафик живому
(daemon.Daemon._main_step). Здесь — сам замер и правила выбора.

Замер — загрузка speed.url через probe-inbound сервера, не больше speed.max_mb и не дольше
speed.max_seconds; скорость считается по телу ответа, без рукопожатий туннеля и TLS.
Лимитированные серверы замеряются меньшей загрузкой (size_mb): 10 МБ через сервер x10 —
это 100 МБ квоты.

Замеряются все живые серверы, не только в работе (ASSUMPTIONS п. 224): безлимитные — раз в
speed.unlimited_hours, лимитированные — раз в speed.limited_hours (every_hours). Иначе
самый живой сервер мог годами лежать в запасных, а основной выбирался бы из нескольких
участников, которых ТСПУ может отрезать в любой момент. Запасные качают меньше
(speed.spare_mb): их десятки.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from ..config import Config
from ..generator.builder import PROBE_USER, NodeInfo
from .checks import http_get_via_proxy

MB = 1_000_000
# Тело короче этого (файл замера мал) скорость не показывает: TCP не успевает разогнаться.
MIN_BYTES = 256 * 1024
# Загрузка через лимитированный сервер не короче этого: на меньшей скорость занижена.
LIMITED_MIN_MB = 1.0
# Серверы x100 и дороже не замеряются: это серверы для LTE (обход белых списков), их
# скорость для выбора основного не нужна, а замер стоил бы 100 МБ квоты.
SKIP_PRICE = 100.0


@dataclass(frozen=True)
class SpeedResult:
    mbps: float | None  # None — замер не удался (error)
    bytes_read: int = 0
    seconds: float = 0.0
    error: str = ""


def size_mb(cfg: Config, price: float, *, spare: bool = False) -> float:
    """Сколько МБ качать при замере сервера стоимостью price (cost.py: 0 — безлимитный).
    Квоты на замер лимитированного уходит не больше speed.max_mb: x10 — 1 МБ загрузки
    (10 МБ квоты), но загрузка не короче LIMITED_MIN_MB. Запасной качает не больше
    speed.spare_mb. 0 — сервер не замеряется."""
    if price >= SKIP_PRICE:
        return 0.0
    base = float(min(cfg.speed.max_mb, cfg.speed.spare_mb) if spare else cfg.speed.max_mb)
    if price <= 1.0:
        return base
    return max(min(LIMITED_MIN_MB, base), base / price)


def every_hours(cfg: Config, price: float, *, spare: bool = False) -> int:
    """Как часто замерять фоном сервер стоимостью price: безлимитный — раз в
    speed.unlimited_hours, лимитированный — раз в speed.limited_hours, запасной — не чаще раза
    в speed.spare_hours (0.1.18); 0 — не замерять (x100 и дороже либо замеры выключены)."""
    if price >= SKIP_PRICE:
        return 0
    hours = cfg.speed.unlimited_hours if price <= 0 else cfg.speed.limited_hours
    if spare and hours and cfg.speed.spare_hours:
        return max(hours, cfg.speed.spare_hours)
    return hours


def measure(
    node: NodeInfo, cfg: Config, *, probe_pass: str, probe_user: str = PROBE_USER,
    max_mb: float | None = None, cancel: threading.Event | None = None,
) -> SpeedResult:
    """Замер через probe-inbound узла. Основной адрес ответил ошибкой HTTP (например, 403
    выходу этого сервера) — пробуется запасной speed.url_fallback. max_mb — предел загрузки
    (size_mb); по умолчанию speed.max_mb. cancel — демон останавливается: замер прерывается
    (ошибка, mbps None), записывать его не нужно."""
    limit = cfg.speed.max_mb if max_mb is None else max_mb
    urls = [url for url in (cfg.speed.url, cfg.speed.url_fallback) if url]
    result = None
    for index, url in enumerate(urls):
        result = http_get_via_proxy(
            "127.0.0.1", node.probe_port, url,
            timeout=15.0, silence=5.0, proxy_user=probe_user, proxy_pass=probe_pass,
            max_total=cfg.speed.max_seconds + 20.0, user_agent=cfg.probe.user_agent,
            max_bytes=int(limit * MB), max_body_seconds=float(cfg.speed.max_seconds),
            cancel=cancel,
        )
        if result.ok or result.kind != "http" or index == len(urls) - 1:
            break
    assert result is not None  # speed.url пустым не бывает (config._validate_speed)
    seconds = round(result.body_seconds, 2)
    if not result.ok:
        return SpeedResult(None, result.downloaded, seconds, result.error)
    if result.downloaded < MIN_BYTES:
        return SpeedResult(
            None, result.downloaded, seconds,
            f"файл замера слишком мал: {result.downloaded} байт — укажите speed.url побольше",
        )
    mbps = result.downloaded * 8 / max(result.body_seconds, 0.05) / MB
    return SpeedResult(round(mbps, 1), result.downloaded, seconds)


@dataclass(frozen=True)
class Candidate:
    """Живой участник, который может стать основным."""

    tag: str
    key: str  # отпечаток (или тег, если узел не сопоставлен с подпиской)
    name: str = ""
    mbps: float | None = None  # свежий удачный замер; None — замера нет или он не удался
    delay_ms: float | None = None  # задержка по пробам ядра
    country: str = ""  # страна сервера (по подписке) и подписка — для замены без прыжков
    source: str = ""
    spare: bool = False  # запасной: основным станет, только встав в работу


def best(candidates: list[Candidate]) -> Candidate | None:
    """Лучший кандидат: с замером — самый быстрый; без замеров — с наименьшей задержкой."""
    if not candidates:
        return None
    return min(candidates, key=lambda item: (
        item.mbps is None, -(item.mbps or 0.0),
        item.delay_ms is None, item.delay_ms or 0.0, item.tag,
    ))


def best_like(candidates: list[Candidate], country: str, source: str) -> Candidate | None:
    """Замена отказавшему основному: лучший той же страны из другой подписки, иначе той
    же страны, иначе просто лучший — чтобы адрес выхода не прыгал по странам (подписка
    отказавшего могла попасть под блокировку целиком)."""
    if country:
        same = [item for item in candidates if item.country == country]
        other = [item for item in same if item.source != source]
        for group in (other, same):
            if group:
                return best(group)
    return best(candidates)


def faster(rival: Candidate, main: Candidate, gain_pct: int) -> bool:
    """rival быстрее основного хотя бы на gain_pct процентов. У основного нет удачного
    замера (файл не скачался, «заморозка» посреди тела) — любой замеренный быстрее."""
    if rival.mbps is None:
        return False
    if main.mbps is None:
        return True
    return rival.mbps >= main.mbps * (1.0 + gain_pct / 100.0) and rival.mbps > main.mbps


def mbps_text(value: float) -> str:
    """85 Мбит/с; 8,5 Мбит/с — ниже 10 с одним знаком после запятой."""
    if value >= 10:
        return f"{value:.0f} Мбит/с"
    return f"{value:.1f}".replace(".", ",") + " Мбит/с"


def describe(candidate: Candidate) -> str:
    """«имя» (85 Мбит/с) — для событий."""
    name = f"«{candidate.name}»" if candidate.name else candidate.tag
    if candidate.mbps is not None:
        return f"{name} ({mbps_text(candidate.mbps)})"
    if candidate.delay_ms is not None:
        return f"{name} (задержка {candidate.delay_ms:.0f} мс)"
    return name
