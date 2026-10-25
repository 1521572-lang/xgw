"""Монитор bootstrap-DNS (0.1.18, ТЗ R4a).

Bootstrap-DNS разрешает имена мимо VPN: адреса подписок, доменов серверов, GitHub для
обновления ядер, проверку провайдера. До 0.1.18 резолверов было три, и об их отказе шлюз
молчал, пока не переставали обновляться подписки. Теперь к dns.bootstrap добавлены
dns.bootstrap_extra — шифрованные DoH у других операторов и на нестандартном порту, — а
демон раз в dns.bootstrap_check_minutes проверяет каждый резолвер отдельно. Не отвечает
часть — событие-предупреждение; не отвечает ни один — событие с уведомлением; итог
последней проверки видят `xgw diag` и `xgw status`.

Сам резолвер (fetch.resolve_domain) недавно не ответивший адрес пробует последним — монитор
лишь говорит об этом человеку. Путь и формат запроса DoH лежат внутри TLS: DPI видит только
адрес и порт (имени сайта у DoH по IP нет вовсе), поэтому разнообразие даёт именно другой
оператор, другой адрес и другой порт (ASSUMPTIONS, п. о 0.1.18).
"""

from __future__ import annotations

import json
import threading
import time
from urllib.parse import urlsplit

from .. import fetch, masking
from ..config import Config

META = "bootstrap_health"  # ключ в базе состояния: итог последней проверки


def name_to_check(cfg: Config) -> str:
    """Имя для проверки резолверов — из адресов конфигурации (probe.url, подписки): лишних
    запросов к чужим именам XGW не делает."""
    candidates = [cfg.probe.url, *(sub.url for sub in cfg.subscriptions)]
    for url in candidates:
        host = urlsplit(url).hostname or ""
        if host and not host.replace(".", "").isdigit() and ":" not in host:
            return host
    return ""


def label(entry: str) -> str:
    """Резолвер для журнала и diag: схема, адрес и порт, без пути (в пути DoH у некоторых
    служб — личный идентификатор)."""
    parts = urlsplit(entry)
    if parts.scheme == "https" and parts.netloc:
        return f"https://{parts.netloc}"
    if parts.scheme == "udp":
        return entry  # адрес и порт обычного DNS — ничего личного
    return masking.mask_url(entry)


def check_all(
    cfg: Config, *, mark: int | None, cancel: threading.Event | None = None,
    clock=time.monotonic,
) -> list[dict]:
    """Каждый резолвер по отдельности: {"entry", "ok", "ms", "error"}. Остановка демона
    (cancel) прерывает проверку — непроверенные резолверы в итог не попадают."""
    name = name_to_check(cfg)
    if not name:
        return []
    results: list[dict] = []
    for entry in cfg.dns.resolvers:
        if cancel is not None and cancel.is_set():
            break
        started = clock()
        try:
            fetch.resolve_domain(name, [entry], mark=mark, cancel=cancel)
            ok, error = True, ""
        except fetch.Cancelled:
            break
        except fetch.NoSuchDomain:
            ok, error = True, ""  # ответил, и ответил определённо
        except fetch.ResolveError as exc:
            ok, error = False, str(exc).split(": ", 1)[-1]
        results.append({
            "entry": label(entry), "ok": ok,
            "ms": round((clock() - started) * 1000), "error": error,
        })
    return results


def verdict(results: list[dict]) -> str:
    """ok — отвечают все, partial — часть, down — ни один, "" — проверять было нечего."""
    if not results:
        return ""
    good = sum(1 for item in results if item["ok"])
    if good == len(results):
        return "ok"
    return "partial" if good else "down"


def event_text(results: list[dict]) -> str:
    """Текст события о смене итога проверки."""
    state = verdict(results)
    bad = [f"{item['entry']} ({item['error']})" for item in results if not item["ok"]]
    if state == "ok":
        return f"bootstrap-DNS: снова отвечают все резолверы ({len(results)})"
    if state == "down":
        return (
            "bootstrap-DNS: не отвечает ни один резолвер — адреса подписок и серверов мимо VPN "
            "не разрешаются; проверьте dns.bootstrap: " + "; ".join(bad)
        )
    good = len(results) - len(bad)
    return (
        f"bootstrap-DNS: отвечают {good} из {len(results)}; не отвечают: " + "; ".join(bad)
        + " — резолвер пробует их последними"
    )


def dumps(results: list[dict], when: float) -> str:
    return json.dumps({"ts": when, "results": results}, ensure_ascii=False)


def loads(text: str | None) -> dict:
    try:
        saved = json.loads(text) if text else {}
    except ValueError:
        return {}
    if not isinstance(saved, dict) or not isinstance(saved.get("results"), list):
        return {}
    return saved
