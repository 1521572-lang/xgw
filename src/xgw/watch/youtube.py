"""Проверка YouTube через сервер (М3, отчёт freepool-recovery2, решение заказчика 31.10.2026:
«если сервер не пропускает трафик YouTube, надо менять его на другой»).

Сервер может отвечать пробам ядра и показывать хорошую скорость замера (Cloudflare), а YouTube
через него не открывается или буферизуется: у сервера пула (LT) было 93 Мбит/с по замеру, а
видео у заказчика шло с буферизацией, и он сам сменил сервер. Провайдер сервера может резать
YouTube, у Google — плохая связность с его сетью или ограничения его адресу.

Проверка — через probe-inbound сервера, как замер скорости:

1. адреса speed.youtube_urls — www.youtube.com и видеосеть redirector.googlevideo.com, ответ
   204 без тела (проверены 31.10.2026): пропускает ли сервер YouTube вообще. Ответ с
   переадресацией (3xx) — тоже ответ YouTube через сервер; ошибка соединения, TLS, тишина или
   код 4xx/5xx — «не пропускает»;
2. загрузка до SPEED_MB из speed.youtube_speed_url — неизменяемый файл на dl.google.com (те же
   узлы Google, что отдают видео; Range понимает, проверено 31.10.2026): хватает ли скорости на
   видео без буферизации — не меньше speed.youtube_mbps вместе с трафиком клиентов через этот
   же сервер за прошлый шаг (сервер, через который клиенты уже качают, своей загрузкой не
   разогнать). Файл не отдан с ошибкой HTTP — скорость не узнать, но YouTube отвечает: годен.

Решения по итогам (смена сервера, подтверждение двумя проверками подряд, приостановка смен) —
в daemon.Daemon._youtube_step, _youtube_bad.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from urllib.parse import urlsplit

from ..config import Config
from ..generator.builder import PROBE_USER, NodeInfo
from .checks import DownloadResult, http_get_via_proxy
from .speed import MB, MIN_BYTES, mbps_text

OK, BLOCKED, SLOW, CANCELLED = "ok", "blocked", "slow", "cancelled"
SPEED_MB = 4.0  # загрузка с серверов Google не больше…
SPEED_SECONDS = 8.0  # …и не дольше
# Трафик одного запроса без тела: рукопожатие TLS (цепочка сертификатов Google) и заголовки.
# Оценка сверху — для счётчиков своего трафика (daemon.Daemon._youtube_rates).
HANDSHAKE_BYTES = 8_000


@dataclass(frozen=True)
class Verdict:
    state: str  # OK | BLOCKED | SLOW | CANCELLED
    mbps: float | None = None  # своя загрузка с серверов Google; None — не замерялась
    bytes_used: int = 0
    error: str = ""


def reached(result: DownloadResult) -> bool:
    """YouTube ответил через сервер: 2xx или переадресация."""
    return result.ok or (result.kind == "http" and 300 <= result.status < 400)


def check(
    node: NodeInfo, cfg: Config, *, probe_pass: str, client_mbps: float = 0.0,
    speed: bool = True, cancel: threading.Event | None = None,
) -> Verdict:
    """Проверка YouTube через probe-inbound узла. speed — замерять ли скорость с серверов
    Google (лимитированные серверы — только доступность: каждый байт тратит квоту);
    client_mbps — трафик клиентов через этот сервер, Мбит/с: он складывается со своей
    загрузкой. cancel — демон останавливается: итог CANCELLED, записывать его не нужно."""
    used = 0
    for url in cfg.speed.youtube_urls:
        result = http_get_via_proxy(
            "127.0.0.1", node.probe_port, url, timeout=10.0, silence=8.0,
            proxy_user=PROBE_USER, proxy_pass=probe_pass, max_total=20.0,
            user_agent=cfg.probe.user_agent, cancel=cancel,
        )
        used += HANDSHAKE_BYTES + result.downloaded
        if result.kind == "cancelled":
            return Verdict(CANCELLED, bytes_used=used, error=result.error)
        if not reached(result):
            return Verdict(BLOCKED, bytes_used=used,
                           error=f"{urlsplit(url).hostname}: {result.error}")
    url = cfg.speed.youtube_speed_url
    if not speed or not cfg.speed.youtube_mbps or not url:
        return Verdict(OK, bytes_used=used)
    size = int(SPEED_MB * MB)
    result = http_get_via_proxy(
        "127.0.0.1", node.probe_port, url, timeout=15.0, silence=5.0,
        proxy_user=PROBE_USER, proxy_pass=probe_pass, max_total=SPEED_SECONDS + 20.0,
        user_agent=cfg.probe.user_agent, max_bytes=size, max_body_seconds=SPEED_SECONDS,
        range_end=size, cancel=cancel,
    )
    used += HANDSHAKE_BYTES + result.downloaded
    if result.kind == "cancelled":
        return Verdict(CANCELLED, bytes_used=used, error=result.error)
    if not result.ok and result.kind in ("http", "proxy"):
        return Verdict(OK, bytes_used=used, error=f"файл замера Google: {result.error}")
    if result.ok and result.downloaded < MIN_BYTES:
        return Verdict(OK, bytes_used=used,
                       error=f"файл замера Google слишком мал: {result.downloaded} байт")
    # Тишина, обрыв, таймаут — сколько успело прийти за время тела (ничего — 0).
    mbps = round(result.downloaded * 8 / max(result.body_seconds, 0.05) / MB, 1)
    error = "" if result.ok else f"файл замера Google: {result.error}"
    if mbps + max(client_mbps, 0.0) < cfg.speed.youtube_mbps:
        return Verdict(SLOW, mbps, used, error)
    return Verdict(OK, mbps, used, error)


def problem(record: dict) -> str:
    """Чем сервер плох для YouTube — для событий: «не пропускает YouTube» или «тормозит на
    YouTube (1,8 Мбит/с с серверов Google)»."""
    if record.get("state") == BLOCKED:
        return "не пропускает YouTube"
    mbps = record.get("mbps")
    total = mbps if isinstance(mbps, (int, float)) else 0.0
    client = record.get("client")
    if isinstance(client, (int, float)) and client > 0:
        return (f"тормозит на YouTube ({mbps_text(total)} с серверов Google и "
                f"{mbps_text(client)} у клиентов)")
    return f"тормозит на YouTube ({mbps_text(total)} с серверов Google)"


def summary(verdict: Verdict) -> str:
    """Итог для журнала демона: «проходит, 23 Мбит/с с серверов Google»."""
    if verdict.state == BLOCKED:
        return f"не пропускает ({verdict.error})"
    speed = f", {mbps_text(verdict.mbps)} с серверов Google" if verdict.mbps is not None else ""
    word = "тормозит" if verdict.state == SLOW else "проходит"
    note = f" ({verdict.error})" if verdict.error else ""
    return f"{word}{speed}{note}"
