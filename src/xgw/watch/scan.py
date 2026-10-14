"""Скан запасных серверов: probe.url через probe-inbound каждого spare-*.

Классы (раздел 6.8): OK, SLOW, FROZEN (часть тела, затем тишина — фиксируем
число байт), STALL_BEFORE_BODY, CONNECT_FAIL, TIMEOUT.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from ..config import Config
from ..generator.builder import PROBE_USER, NodeInfo
from .checks import DownloadResult, http_get_via_proxy

SLOW_SECONDS = 3.0  # эмпирический порог «медленно, но живо»


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


def classify(result: DownloadResult, seconds: float, slow: float = SLOW_SECONDS) -> str:
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
) -> ScanResult:
    """Проба одного узла через его probe-inbound (127.0.0.1:<probe_port>).

    probe_pass — пароль из применённого конфига (builder.probe_state): у
    работающего Xray действует именно он.
    """
    started = time.monotonic()
    result = http_get_via_proxy(
        "127.0.0.1",
        node.probe_port,
        url or cfg.probe.url,
        timeout=max(silence + 5.0, 15.0),
        silence=silence,
        proxy_user=probe_user,
        proxy_pass=probe_pass,
        user_agent=cfg.probe.user_agent,
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
    )


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
