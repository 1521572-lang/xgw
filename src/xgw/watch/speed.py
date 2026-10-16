"""Замер скорости серверов в работе и выбор основного сервера (0.1.9).

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
Лимитированные серверы не замеряются: 10 МБ через сервер x10 — это 100 МБ квоты.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Config
from ..generator.builder import PROBE_USER, NodeInfo
from .checks import http_get_via_proxy

MB = 1_000_000
# Тело короче этого (файл замера мал) скорость не показывает: TCP не успевает разогнаться.
MIN_BYTES = 256 * 1024


@dataclass(frozen=True)
class SpeedResult:
    mbps: float | None  # None — замер не удался (error)
    bytes_read: int = 0
    seconds: float = 0.0
    error: str = ""


def measure(
    node: NodeInfo, cfg: Config, *, probe_pass: str, probe_user: str = PROBE_USER
) -> SpeedResult:
    """Замер через probe-inbound узла. Основной адрес ответил ошибкой HTTP (например, 403
    выходу этого сервера) — пробуется запасной speed.url_fallback."""
    urls = [url for url in (cfg.speed.url, cfg.speed.url_fallback) if url]
    result = None
    for index, url in enumerate(urls):
        result = http_get_via_proxy(
            "127.0.0.1", node.probe_port, url,
            timeout=15.0, silence=5.0, proxy_user=probe_user, proxy_pass=probe_pass,
            max_total=cfg.speed.max_seconds + 20.0, user_agent=cfg.probe.user_agent,
            max_bytes=cfg.speed.max_mb * MB, max_body_seconds=float(cfg.speed.max_seconds),
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


def best(candidates: list[Candidate]) -> Candidate | None:
    """Лучший кандидат: с замером — самый быстрый; без замеров — с наименьшей задержкой."""
    if not candidates:
        return None
    return min(candidates, key=lambda item: (
        item.mbps is None, -(item.mbps or 0.0),
        item.delay_ms is None, item.delay_ms or 0.0, item.tag,
    ))


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
