"""Недоступен сам адрес пробы (probe.url), а не серверы.

Проба — загрузка probe.url через сервер. Если адрес перестал отвечать (403 от CDN,
404, сайт лёг), пробы падают у всех серверов сразу, и без этой проверки шлюз считал бы
мёртвыми живые серверы и без конца менял участников балансировщика.

Признак: ни один из опрошенных серверов — участников и нескольких запасных — не
получил probe.url (ни тела, ни его начала). Ошибки при этом бывают и разными: на живой
машине из 67 серверов 64 давали обрыв и 3 — таймаут, и требовать у всех одну и ту же
ошибку значило бы этого не заметить. Дальше решают контрольные запросы:

  * базовый запрос через VPN (probe.trace_url через http-in): отвечает — значит,
    серверы трафик носят, а не отвечает именно probe.url (базовый запрос идёт через
    одного из участников, а его проба тоже не прошла);
  * probe.url напрямую, мимо VPN: тот же код HTTP у всех — отвечает так сам адрес.

«Заморозка» (часть тела пришла, затем тишина) сюда не относится никогда: это и есть
поломка сервера, ради которой пробы существуют. Таймауты и обрывы без ответа через
VPN — тоже не сюда: так выглядят мёртвые серверы.

Пока probe.url не отвечает, ядро (burstObservatory) пробует серверы по запасному адресу
(probe.url_fallback, без него — probe.trace_url): иначе оно считало бы мёртвыми всех
участников, и весь трафик ушёл бы на один fallbackTag балансировщика — живой он или нет.
Сквозная проверка демона по-прежнему качает сам probe.url: по ней видно, что он ожил, и
ядро возвращается к нему. Выбор хранится в /var/lib/xgw (переживает перезагрузку) и
действует, только пока probe.url в конфиге тот же.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .. import fetch
from ..config import Config
from ..generator.builder import NodeInfo
from ..paths import Paths, atomic_write_json
from . import checks
from .scan import ScanResult

SAMPLE_SPARES = 3  # сколько запасных опрашивать вместе с участниками
# `xgw probe --all`: столько серверов с одной ошибкой и ни одного удачного — уже повод
# сказать, что дело, скорее всего, в адресе пробы (решение — за `xgw diag`).
DOMINANT_SHARE = 0.8
WARNING = "пробы всех серверов падают — вероятно, недоступен сам probe.url"
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


def failure(results: Iterable[ScanResult]) -> tuple[str, int, int]:
    """(самая частая ошибка, сколько раз, сколько проб). Ошибки нет (пусто) — проб нет
    либо хоть одна получила probe.url: адрес отвечает."""
    found = [signature(result) for result in results]
    if not found or "" in found:
        return "", 0, len(found)
    common, count = Counter(found).most_common(1)[0]
    return common, count, len(found)


def failure_text(common: str, count: int, total: int) -> str:
    """«HTTP 403» — у всех; «обрыв соединения у 64 из 67» — у большинства."""
    return common if count == total else f"{common} у {count} из {total}"


def dominant(results: Sequence[ScanResult]) -> str:
    """Описание ошибки, если она у DOMINANT_SHARE проб и ни одна проба не прошла;
    иначе пусто. Для подсказки в `xgw probe --all`."""
    common, count, total = failure(results)
    if not common or count < DOMINANT_SHARE * total:
        return ""
    return failure_text(common, count, total)


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
    common, count, total = failure(results)
    if not common:
        return Diagnosis(False)
    label = failure_text(common, count, total)
    straight: str | None = None
    if common.startswith("HTTP") and count == total:
        straight = direct()
        if straight == common:
            return Diagnosis(True, label, f"напрямую, мимо VPN, ответ тот же — {straight}")
    if not base_ping():
        # Через VPN не проходит ничего: это серверы, а не адрес пробы. Прямой запрос при
        # таймаутах даже не делается — когда серверы и правда мертвы, шаг должен быстрее
        # перейти к их замене.
        return Diagnosis(False, label)
    if straight is None:
        straight = direct()  # только для пояснения в тексте
    if not straight:
        detail = "через VPN другие адреса открываются, а probe.url — нет, хотя напрямую отдаётся"
    else:
        detail = f"через VPN другие адреса открываются, а probe.url — нет; напрямую — {straight}"
    return Diagnosis(True, label, detail)


# --- запасной адрес проб ядра ------------------------------------------------------


def _fallback_file(paths: Paths) -> Path:
    return paths.var / "probe-fallback.json"


def fallback_target(cfg: Config) -> str:
    """Куда пробовать ядру, пока probe.url не отвечает: probe.url_fallback, а без него —
    probe.trace_url (что он через серверы отвечает, только что показал базовый запрос).
    Пусто — подменять нечем."""
    for url in (cfg.probe.url_fallback.strip(), cfg.probe.trace_url.strip()):
        if url.startswith(("http://", "https://")) and url != cfg.probe.url:
            return url
    return ""


def _fallback_state(paths: Paths) -> dict:
    try:
        state = json.loads(_fallback_file(paths).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return state if isinstance(state, dict) else {}


def observatory_url(cfg: Config, paths: Paths) -> str:
    """Адрес проб ядра (pingConfig.destination): probe.url, а пока он не отвечает —
    запасной (fallback_target). Запись о запасном относится к своему probe.url: адрес в
    конфиге сменили — она не действует."""
    if _fallback_state(paths).get("url") == cfg.probe.url:
        fallback = fallback_target(cfg)
        if fallback:
            return fallback
    return cfg.probe.url


def use_fallback(cfg: Config, paths: Paths, on: bool) -> bool:
    """Включает (on) или снимает запасной адрес проб ядра. True — адрес проб изменился,
    конфиг Xray нужно собрать заново."""
    before = observatory_url(cfg, paths)
    if on and fallback_target(cfg):
        atomic_write_json(
            _fallback_file(paths), {"url": cfg.probe.url, "since": time.time()}, mode=0o644
        )
    else:
        _fallback_file(paths).unlink(missing_ok=True)
    return observatory_url(cfg, paths) != before
