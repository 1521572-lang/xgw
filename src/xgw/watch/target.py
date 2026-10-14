"""Недоступен сам адрес пробы (probe.url), а не серверы.

Проба — загрузка probe.url через сервер. Если адрес перестал отвечать (403 от CDN,
404, сайт лёг), пробы падают у всех серверов сразу, и без этой проверки шлюз считал бы
мёртвыми живые серверы и без конца менял участников балансировщика.

Признак: все опрошенные серверы — участники и несколько запасных — падают с одной и
той же ошибкой. Дальше контрольные запросы:

  * базовый запрос через VPN (probe.trace_url через http-in): отвечает — значит,
    серверы трафик носят, а не отвечает именно probe.url;
  * probe.url напрямую, мимо VPN: тот же код HTTP — отвечает так сам адрес.

«Заморозка» (часть тела пришла, затем тишина) сюда не относится никогда: это и есть
поломка сервера, ради которой пробы существуют. Одинаковые таймауты и обрывы без
ответа через VPN — тоже не сюда: так выглядят мёртвые серверы.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from .. import fetch
from ..config import Config
from ..generator.builder import NodeInfo
from . import checks
from .scan import ScanResult

SAMPLE_SPARES = 3  # сколько запасных опрашивать вместе с участниками
WARNING = "все пробы падают с одинаковой ошибкой — вероятно, недоступен сам probe.url"
ADVICE = "задайте в config.toml другой probe.url — файл 50–65 КБ, который отдаётся без входа"

_GOOD = ("OK", "SLOW")
TIMEOUT = "таймаут"
BROKEN = "обрыв соединения"
NO_REPLY = "нет ответа"


@dataclass(frozen=True)
class Diagnosis:
    down: bool  # не отвечает сам probe.url: серверы трогать не нужно
    signature: str = ""  # общая ошибка проб («HTTP 403», «таймаут»); пусто — ошибки разные
    detail: str = ""  # что показали контрольные запросы

    @property
    def text(self) -> str:
        """Предупреждение для журнала, статуса и панели."""
        parts = [part for part in (self.signature, self.detail) if part]
        return f"Внимание: {WARNING}" + (f" ({'; '.join(parts)})" if parts else "")


def signature(result: ScanResult) -> str:
    """Класс сбоя пробы: «HTTP 403», «таймаут», «обрыв соединения».

    Пусто — проба прошла либо это «заморозка»: и то, и другое значит, что адрес
    пробы отвечает.
    """
    if result.verdict in _GOOD or result.verdict == "FROZEN" or result.bytes_read > 0:
        return ""
    if result.status and not 200 <= result.status < 300:
        return f"HTTP {result.status}"
    if result.error.startswith("HTTP ") and result.error[5:8].isdigit():
        return result.error[:8]  # результат без кода ответа (старый формат)
    if result.verdict in ("TIMEOUT", "STALL_BEFORE_BODY") or result.kind in ("timeout", "stall"):
        return TIMEOUT
    return BROKEN


def uniform(results: Iterable[ScanResult]) -> str:
    """Общая ошибка всех проб; пусто — проб нет, ошибки разные или хоть одна прошла."""
    found = {signature(result) for result in results}
    return found.pop() if len(found) == 1 else ""


def sample(view: Sequence[NodeInfo], verdicts: dict[str, str]) -> list[NodeInfo]:
    """Кого опрашивать: все участники и несколько запасных — сначала те, что прошли
    последний скан (их отказ весомее всего)."""
    members = [info for info in view if info.role == "proxy" and info.probe_port]
    spares = [info for info in view if info.role == "spare" and info.probe_port]
    spares.sort(key=lambda info: 0 if verdicts.get(info.probe_tag) in _GOOD else 1)
    return [*members, *spares[:SAMPLE_SPARES]]


def base_ping(cfg: Config) -> bool:
    """Базовый запрос через VPN — probe.trace_url через http-in: проходит ли через
    серверы хоть что-то. Без trace_url проверить нечем — считаем, что не проходит."""
    if not cfg.probe.trace_url:
        return False
    return checks.http_get_via_proxy(
        "127.0.0.1", cfg.xray.http_port, cfg.probe.trace_url,
        timeout=10.0, silence=5.0, max_total=15.0, user_agent=cfg.probe.user_agent,
    ).ok


def direct_signature(cfg: Config, mark: int | None) -> str:
    """probe.url напрямую, мимо VPN (сокетом с меткой mark_bypass). Пусто — отдаётся,
    иначе «HTTP <код>» либо «нет ответа»."""
    try:
        reply = fetch.fetch_url(
            cfg.probe.url, mark=mark, timeout=10.0, retries=0,
            bootstrap=cfg.dns.bootstrap if mark is not None else None,
            headers={"User-Agent": cfg.probe.user_agent},
        )
    except fetch.FetchError:
        return NO_REPLY
    return "" if 200 <= reply.status < 300 else f"HTTP {reply.status}"


def diagnose(
    results: Sequence[ScanResult],
    *,
    base_ping: Callable[[], bool],
    direct: Callable[[], str],
) -> Diagnosis:
    """results — свежие пробы участников и выборки запасных; base_ping — базовый запрос
    через VPN (True — прошёл); direct — probe.url напрямую: пусто — отдаётся, иначе класс
    сбоя в том же виде, что и signature()."""
    common = uniform(results)
    if not common:
        return Diagnosis(False)
    straight: str | None = None
    if common.startswith("HTTP"):
        straight = direct()
        if straight == common:
            return Diagnosis(True, common, f"напрямую, мимо VPN, ответ тот же — {straight}")
    if not base_ping():
        # Через VPN не проходит ничего: это серверы, а не адрес пробы. Прямой запрос при
        # таймаутах даже не делается — когда серверы и правда мертвы, шаг должен быстрее
        # перейти к их замене.
        return Diagnosis(False, common)
    if straight is None:
        straight = direct()  # только для пояснения в тексте
    if not straight:
        detail = "через VPN другие адреса открываются, а probe.url — нет, хотя напрямую отдаётся"
    else:
        detail = f"через VPN другие адреса открываются, а probe.url — нет; напрямую — {straight}"
    return Diagnosis(True, common, detail)
