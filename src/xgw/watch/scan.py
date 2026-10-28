"""Скан запасных серверов: probe.url через probe-inbound каждого spare-*.

Классы (раздел 6.8): OK, SLOW, FROZEN (часть тела, затем тишина — фиксируем
число байт), STALL_BEFORE_BODY, CONNECT_FAIL, TIMEOUT. Служебный CANCELLED — проба
прервана остановкой демона; в базу он не попадает.

Запасные лимитированных подписок проверяются дешёвым запросом (cheap_url, обычно
probe.trace_url — сотни байт вместо 57 КБ): каждый байт через такой сервер тратит квоту,
да ещё с множителем (cost.py). «Заморозку» такой запрос не ловит — её поймает первая
проверка сервера, когда он станет участником (daemon.Daemon._queue_members).
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from ..config import Config, probe_bytes
from ..generator.builder import PROBE_USER, NodeInfo
from .checks import DownloadResult, http_get_via_proxy

SLOW_SECONDS = 3.0  # эмпирический порог «медленно, но живо»
# Сколько трафика уходит на одну дешёвую проверку: ответ trace_url — несколько сотен
# байт, остальное — рукопожатие TLS (цепочка сертификатов) и заголовки. Оценка сверху.
CHEAP_SCAN_BYTES = 8_000
# Резервный выход балансировщика и лучшие кандидаты на его место (запасные лимитированных
# подписок классом хуже участников) проверяются дешёвым запросом раз в RESERVE_RECHECK —
# по RESERVE_CANDIDATES лучших (daemon.Daemon._reserve_step).
RESERVE_RECHECK = 6 * 3600.0
RESERVE_CANDIDATES = 3
# Свой сервер устройства — запасной — проверяется дешёвым запросом раз в DEVICE_CHECK, а RTT
# участников — раз в RTT_EVERY (daemon.Daemon._device_step, _rtt_step; 0.2.0). Здесь — чтобы
# их учитывал и бюджет проверок (status.probe_budget).
DEVICE_CHECK = 30.0
RTT_EVERY = 600.0
# Пробы без шаблона (анти-ТСПУ 2.0): собственная проба статическим файлом известного размера
# просит случайную его часть (Range) — от RANDOM_MIN байт до целого. Снаружи туннеля видна
# только длина всплеска, а одинаковые всплески по 57 КБ раз в несколько минут — заметный шаблон.
# RANDOM_MIN больше двух записей TLS (~32,7 КБ): «заморозка» по объёму на 16–32 КБ ловится и
# так (стенд phase_lab: обрыв видится кратно ~16,3 КБ).
RANDOM_MIN = 40_000


def cheap_url(cfg: Config) -> str:
    """Адрес дешёвой проверки: probe.trace_url, а без него — probe.url."""
    return cfg.probe.trace_url.strip() or cfg.probe.url


@dataclass
class ScanResult:
    tag: str
    verdict: str          # OK | SLOW | FROZEN | STALL_BEFORE_BODY | CONNECT_FAIL | TIMEOUT
    bytes_read: int       # байт тела до остановки
    seconds: float
    error: str = ""
    # Этап сбоя и код ответа HTTP (см. checks.DownloadResult): по ним отличают «не
    # отвечает сам адрес пробы» от «не работает сервер» (watch/target.py).
    kind: str = ""
    status: int = 0
    rtt_ms: float | None = None  # сетевая задержка (checks.DownloadResult.rtt_ms)


def classify(result: DownloadResult, seconds: float, slow: float = SLOW_SECONDS) -> str:
    if result.kind == "cancelled":
        return "CANCELLED"
    if result.ok:
        return "SLOW" if seconds > slow else "OK"
    if result.frozen:
        return "FROZEN"
    if result.stalled:  # тишина до первого байта тела
        return "STALL_BEFORE_BODY"
    if result.kind == "timeout":
        return "TIMEOUT"
    # Не открылся туннель, оборвалось соединение, сервер ответил ошибкой,
    # прокси отклонил запрос — узел для замены непригоден; причина — в error.
    return "CONNECT_FAIL"


def scan_node(
    node: NodeInfo,
    cfg: Config,
    *,
    probe_pass: str,
    probe_user: str = PROBE_USER,
    url: str | None = None,
    silence: float = 5.0,
    cancel: threading.Event | None = None,
    random_size: bool = False,
) -> ScanResult:
    """Проба одного узла через его probe-inbound (127.0.0.1:<probe_port>).

    random_size — для статического файла известного размера просить случайную его часть
    (range_size); у прочих адресов (trace, ?bytes=…) — как раньше, целиком.

    probe_pass — пароль из применённого конфига (builder.probe_state): у
    работающего Xray действует именно он. cancel — демон останавливается: проба
    прерывается, вердикт CANCELLED (о сервере он ничего не говорит, не записывается).
    """
    started = time.monotonic()
    target = url or cfg.probe.url
    result = http_get_via_proxy(
        "127.0.0.1",
        node.probe_port,
        target,
        timeout=max(silence + 5.0, 15.0),
        silence=silence,
        proxy_user=probe_user,
        proxy_pass=probe_pass,
        user_agent=cfg.probe.user_agent,
        cancel=cancel,
        rtt=True,
        range_end=range_size(target) if random_size else 0,
    )
    seconds = time.monotonic() - started
    return ScanResult(
        tag=node.tag,
        verdict=classify(result, seconds),
        bytes_read=result.downloaded,
        seconds=round(seconds, 2),
        error=result.error,
        kind=result.kind,
        status=result.status,
        rtt_ms=result.rtt_ms,
    )


def range_size(url: str) -> int:
    """Случайная длина тела пробы url: от RANDOM_MIN до размера файла; 0 — просить целиком
    (размер неизвестен, адрес с параметрами или файл меньше RANDOM_MIN)."""
    size = probe_bytes(url)
    if not size or size <= RANDOM_MIN or urlsplit(url).query:
        return 0
    return random.randint(RANDOM_MIN, size)


def scan_spares(
    spares: list[NodeInfo],
    cfg: Config,
    *,
    probe_pass: str,
    probe_user: str = PROBE_USER,
) -> list[ScanResult]:
    """Скан всех запасных подряд, в случайном порядке и со случайными паузами:
    строго периодические одинаковые серии запросов заметны со стороны."""
    order = list(spares)
    random.shuffle(order)
    results: list[ScanResult] = []
    for index, node in enumerate(order):
        if index:
            time.sleep(random.uniform(0.2, 1.5))
        results.append(scan_node(node, cfg, probe_pass=probe_pass, probe_user=probe_user))
    return results
