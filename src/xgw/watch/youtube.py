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
   узлы Google, что отдают видео; Range понимает, проверено 31.10.2026; с части адресов он
   отдаётся переадресацией на узел кэша *.gvt1.com — она проходится): хватает ли скорости на
   видео без буферизации — не меньше speed.youtube_mbps вместе с трафиком клиентов через этот
   же сервер за прошлый шаг (сервер, через который клиенты уже качают, своей загрузкой не
   разогнать). Файл не отдан с ошибкой HTTP — то же с запасным SPARE_URL; не отдан и он —
   «скорость не узнать» (UNKNOWN): неудача, как «тормозит» (отчёт youtube2, ASSUMPTIONS п. 279).

Решения по итогам (смена сервера, подтверждение двумя проверками подряд, приостановка смен) —
в daemon.Daemon._youtube_step, _youtube_bad.
"""

from __future__ import annotations

import hashlib
import re
import threading
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from ..config import Config
from ..generator.builder import PROBE_USER, NodeInfo
from .checks import DownloadResult, http_get_via_proxy
from .speed import MB, MIN_BYTES, mbps_text

OK, BLOCKED, SLOW, UNKNOWN, CANCELLED = "ok", "blocked", "slow", "unknown", "cancelled"
SPEED_MB = 4.0  # загрузка с серверов Google не больше…
SPEED_SECONDS = 8.0  # …и не дольше
# Переадресации файла замера: dl.google.com → redirector.gvt1.com → rN---sn-….gvt1.com (узел кэша
# Google рядом с выходом сервера; отчёт youtube 01.11.2026: у 7 серверов пула из 8 скорость не
# замерялась — переадресацию клиент проб считал ошибкой). Только https и только к доменам Google.
REDIRECTS = 4
GOOGLE = ("google.com", "gvt1.com", "gvt2.com", "googleapis.com", "googlevideo.com",
          "gstatic.com", "googleusercontent.com", "ggpht.com", "youtube.com", "ytimg.com")
# Запасной файл замера — когда speed.youtube_speed_url не отдан с ошибкой HTTP (отчёт youtube2
# 01.11.2026: у 2 серверов пула из 8 архив Go — «HTTP 404», а YouTube отвечал). Chrome для Linux —
# самый ходовой файл dl.google.com, он есть на каждом узле кэша; ~110 МБ, Range понимает (206,
# проверено 01.11.2026). Адрес постоянный, содержимое меняется с выпусками — для замера неважно.
SPARE_URL = "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"
# Трафик одного запроса без тела: рукопожатие TLS (цепочка сертификатов Google) и заголовки.
# Оценка сверху — для счётчиков своего трафика (daemon.Daemon._youtube_rates).
HANDSHAKE_BYTES = 8_000
# Больше одна проверка потратить не может: файл замера, запасной файл и служебные запросы.
# По этой оценке суточный лимит дополнительных проверок не превышается (п. 353).
CHECK_MAX_BYTES = int(2 * SPEED_MB * MB) + 16 * HANDSHAKE_BYTES
# Признак допуска — отдельная проба в том же бюджете. Запас на последний блок чтения
# и заголовки: клиент останавливается после получения блока, а не посреди него.
SIGN_BODY_BYTES = 2 * 1024 * 1024
SIGN_MAX_BYTES = SIGN_BODY_BYTES + 2 * 65536 + HANDSHAKE_BYTES
SIGN_TTL = 6 * 3600
SIGN_TOP = 3
ACCEPT, REFUSE = "accept", "refuse"
_PLAYER_STATUS = re.compile(rb'"playabilityStatus"\s*:\s*\{\s*"status"\s*:\s*"([A-Z_]+)"\s*[,}]')


@dataclass(frozen=True)
class Verdict:
    state: str  # OK | BLOCKED | SLOW | UNKNOWN | CANCELLED
    mbps: float | None = None  # своя загрузка с серверов Google; None — не замерялась
    bytes_used: int = 0
    error: str = ""


def sign_key(url: str) -> str:
    """Запись допуска относится к одному адресу пробы, который в базе не сохраняется."""
    return hashlib.sha256(url.encode()).hexdigest() if url else ""


def sign_sample(record: dict, key: str, now: float) -> str | None:
    """Свежий итог допуска; None — для этого адреса пора проверить снова."""
    sample = record.get("sign")
    if key and isinstance(sample, dict) and sample.get("key") == key:
        stamp, state = sample.get("ts"), sample.get("state")
        if (isinstance(stamp, (float, int)) and 0 <= now - stamp < SIGN_TTL
                and state in (ACCEPT, REFUSE, UNKNOWN)):
            return state
    return None


def check_sign(node: NodeInfo, cfg: Config, *, probe_pass: str,
               cancel: threading.Event | None = None) -> tuple[str, int]:
    """Допуск по странице ролика через служебный вход: итог и оценка расхода."""
    result = http_get_via_proxy(
        "127.0.0.1", node.probe_port, cfg.media.youtube_sign_url, timeout=8, max_total=8,
        proxy_user=PROBE_USER, proxy_pass=probe_pass, user_agent=cfg.probe.user_agent,
        keep_body=SIGN_BODY_BYTES, max_bytes=SIGN_BODY_BYTES, accept_gzip=True, cancel=cancel,
    )
    used = result.downloaded + HANDSHAKE_BYTES
    if result.kind == "cancelled":
        return CANCELLED, used
    if result.status != 200:
        return UNKNOWN, used
    body = result.body
    if body.startswith(b"\x1f\x8b"):
        try:
            body = zlib.decompressobj(31).decompress(body, SIGN_BODY_BYTES)
        except zlib.error:
            return UNKNOWN, used
    match = _PLAYER_STATUS.search(body)
    state = match[1] if match else b""
    return {b"OK": ACCEPT, b"LOGIN_REQUIRED": REFUSE}.get(state, UNKNOWN), used


def google(url: str) -> bool:
    """https-адрес на домене Google — по нему переадресацию файла замера можно пройти."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(
        host == domain or host.endswith("." + domain) for domain in GOOGLE)


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
    result, spent, why = _speed_file(node, cfg, url, probe_pass=probe_pass, cancel=cancel)
    used += spent
    note = ""
    if why and url != SPARE_URL:
        spare, spent, spare_why = _speed_file(node, cfg, SPARE_URL, probe_pass=probe_pass,
                                              cancel=cancel)
        used += spent
        if spare.kind == "cancelled" or not spare_why:
            result, note, why = spare, f"основной файл замера: {why}; замер по запасному", ""
        else:
            why = f"{why}; запасной: {spare_why}"
    if result.kind == "cancelled":
        return Verdict(CANCELLED, bytes_used=used, error=result.error)
    if why:
        return Verdict(UNKNOWN, bytes_used=used, error=f"файл замера Google: {why}")
    # Тишина, обрыв, таймаут — сколько успело прийти за время тела (ничего — 0).
    mbps = round(result.downloaded * 8 / max(result.body_seconds, 0.05) / MB, 1)
    error = "; ".join(item for item in (
        note, "" if result.ok else f"файл замера Google: {result.error}") if item)
    if mbps + max(client_mbps, 0.0) < cfg.speed.youtube_mbps:
        return Verdict(SLOW, mbps, used, error)
    return Verdict(OK, mbps, used, error)


def _speed_file(
    node: NodeInfo, cfg: Config, url: str, *, probe_pass: str, cancel: threading.Event | None,
) -> tuple[DownloadResult, int, str]:
    """Загрузка файла замера через probe-inbound, с переадресациями к Google: (итог, байт
    трафика, почему скорость по нему не узнать — пусто, если узнать можно)."""
    size = int(SPEED_MB * MB)
    used = hops = 0
    target = ""
    for _hop in range(REDIRECTS + 1):
        result = http_get_via_proxy(
            "127.0.0.1", node.probe_port, url, timeout=15.0, silence=5.0,
            proxy_user=PROBE_USER, proxy_pass=probe_pass, max_total=SPEED_SECONDS + 20.0,
            user_agent=cfg.probe.user_agent, max_bytes=size, max_body_seconds=SPEED_SECONDS,
            range_end=size, cancel=cancel,
        )
        used += HANDSHAKE_BYTES + result.downloaded
        target = urljoin(url, result.location) if result.location else ""
        if not (result.kind == "http" and target and google(target)):
            break
        url = target  # dl.google.com отдаёт файл с узлов кэша Google (*.gvt1.com) переадресацией
        hops += 1
    if result.kind == "cancelled":
        return result, used, ""
    if not result.ok and result.kind in ("http", "proxy"):
        if result.location and not google(target):
            return result, used, "переадресация не к Google"
        if result.location:
            return result, used, "слишком много переадресаций"
        # Где именно ошибка — по нему видно, отказал ли сам адрес или узел кэша (отчёт youtube2).
        where = f" от {_host_label(url)}" + (f" после переадресаций: {hops}" if hops else "")
        return result, used, result.error + (where if result.kind == "http" else "")
    capped = result.body_seconds >= SPEED_SECONDS - 0.5  # тело оборвано по времени, а не кончилось
    if result.ok and result.downloaded < MIN_BYTES and not capped:
        return result, used, f"слишком мал: {result.downloaded} байт"
    return result, used, ""


def _host_label(url: str) -> str:
    """Кто ответил: имя узла, а узел кэша Google (rN---sn-….gvt1.com) — словами: в его имени
    закодировано место выхода сервера."""
    host = urlsplit(url).hostname or ""
    return "узла кэша Google" if "---sn-" in host else host


def media_candidates(
    nodes: Sequence[NodeInfo], records: Mapping[str, dict], observatory: Mapping[str, dict],
    prices: Mapping[str, float], now: float, *, min_mbps: float, sample_ttl: float,
    sign: str = "",
) -> list[tuple[NodeInfo, float]]:
    """Кто может быть выходом видео (п. 348), лучшие первыми: (узел, скорость). Только живой
    безлимитный участник с полным отпечатком и со свежим удачным замером; нет данных — не
    кандидат. Скорость — вместе с трафиком клиентов, как в check: сервер, через который уже идёт
    видео, своей загрузкой не разогнать, и выбывать из-за этого он не должен."""
    found: list[tuple[NodeInfo, float, float]] = []
    for info in nodes:
        entry = observatory.get(info.tag) or {}
        record = records.get(info.fingerprint) or {}
        price = prices.get(info.fingerprint)
        mbps, client = record.get("mbps"), record.get("client")
        if (info.role != "proxy" or len(info.fingerprint) < 8 or not info.probe_port
                or not entry.get("alive") or price is None or price > 0
                or record.get("state") != OK or record.get("fails")
                or not isinstance(mbps, int | float) or isinstance(mbps, bool)
                or now - float(record.get("ts") or 0) > sample_ttl
                or sign_sample(record, sign, now) == REFUSE):
            continue
        total = mbps + (client if isinstance(client, int | float) and client > 0 else 0.0)
        if total >= min_mbps:
            found.append((info, total, float(entry.get("delay") or 0.0)))
    found.sort(key=lambda item: (-item[1], item[2], item[0].tag))
    return [(info, total) for info, total, _delay in found]


def media_plan(
    candidates: Sequence[tuple[NodeInfo, float]], previous: tuple[str, ...], *, gain_pct: float,
) -> tuple[str, ...]:
    """Выход видео из кандидатов: лучший, но прежний годный остаётся, если лучший быстрее него
    меньше чем на gain_pct."""
    if not candidates:
        return ()
    best, top = candidates[0]
    kept = next((total for info, total in candidates if info.tag in previous), None)
    if kept is not None and top < kept * (1 + gain_pct / 100):
        return next(((info.tag,) for info, _total in candidates if info.tag in previous))
    return (best.tag,)


def problem(record: dict) -> str:
    """Чем сервер плох для YouTube — для событий: «не пропускает YouTube», «не даёт замерить
    скорость YouTube» или «тормозит на YouTube (1,8 Мбит/с с серверов Google)»."""
    if record.get("state") == BLOCKED:
        return "не пропускает YouTube"
    if record.get("state") == UNKNOWN:
        return "не даёт замерить скорость YouTube (файлы Google через него не скачать)"
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
    if verdict.state == UNKNOWN:
        return f"скорость не узнать ({verdict.error})"
    speed = f", {mbps_text(verdict.mbps)} с серверов Google" if verdict.mbps is not None else ""
    word = "тормозит" if verdict.state == SLOW else "проходит"
    note = f" ({verdict.error})" if verdict.error else ""
    return f"{word}{speed}{note}"
