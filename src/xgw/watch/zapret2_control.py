"""Read-only compatibility card for both legacy controllers. No OS calls or probes."""

from __future__ import annotations

import math
import time
from dataclasses import replace
from urllib.parse import urlsplit

from .. import zapret2
from ..desync import schema, worker
from . import zapret2_management as management

FRESH_SECONDS = 90
VPN_CONTROL_REASONS = {
    "not_run": frozenset({"gate_not_closed", "route_not_restored", "worker_not_stopped",
                          "cancelled", "no_probe_url", "no_vpn_probe_port", "no_probe_credentials",
                          "budget_unavailable", zapret2.CDN_EXPIRED}),
    "pass": frozenset({"ok"}),
    "fail": frozenset({"request_failed", "cdn_redirect_unconfirmed"}),
}
CDN_REDIRECT_STATES = frozenset({
    "followed", "blocked", "loop", "expired", "cancelled", "time_limit",
    "budget_unavailable", "hop_limit",
})
REASONS = {
    "off": "Обработка выключена.",
    "disabled": "Обработка выключена в настройках.",
    "inactive": "Перехват не включён.",
    "not_found": "Не найден бинарник nfqws2 или обязательные библиотеки Lua.",
    "worker_down": "Обработчик или очередь недоступны.",
    "conntrack_accounting_required": "Очередь Engine требует учёта пакетов (nf_conntrack_acct=1).",
    "worker_start_timeout": "Обработчик не подтвердил готовность вовремя.",
    "queue_busy": "Номер очереди занят.",
    "worker_unit_busy": "Служба обработчика уже занята.",
    "worker_handoff_pending": "Предыдущий обработчик ещё освобождает очередь.",
    "unsafe_files": "Файлы обработчика не прошли проверку прав.",
    "unsafe_directory": "Каталог обработчика не прошёл проверку прав.",
    "bundle_mismatch": "Версия или контрольная сумма штатного комплекта zapret2 отличается.",
    "bad_worker_options": "nfqws2 отклонил параметры запуска.",
    "lua_init_failed": "nfqws2 не смог загрузить библиотеки Lua.",
    "runtime_failed": "Ошибка обработчика. Подробности доступны в журнале шлюза.",
    "worker_stop_failed": "Остановка обработчика не подтверждена.",
    "stop_failed": "Остановка обработчика не подтверждена.",
    "offload_restore": "Восстановление настроек сетевого интерфейса не подтверждено.",
    "offload_apply": "Не удалось изменить настройки сетевого интерфейса.",
    "probe_failed": "Проверка прямого пути не прошла.",
    "probe_budget": "Недостаточно бюджета для прямых проб и резерва проверки VPN "
                    "или учёт бюджета недоступен.",
    "probes_ok": "Пробы прямого пути прошли; воспроизведение проверяется отдельно.",
    "youtube_transport_ok": "HTTPS до страницы YouTube и CDN работает. Видео не проверялось.",
    "youtube_page_probe_failed": "HTTPS-проверка страницы YouTube не прошла.",
    "youtube_cdn_probe_failed": "HTTPS-проверка CDN YouTube не прошла.",
    zapret2.CDN_EXPIRED: "Истёк срок адреса CDN. Сохраните свежий адрес видео.",
    "expired": "Подтверждение прямого пути истекло.",
    "retry_wait": "Ожидается повтор проверки прямого пути.",
    "apply_failed": "Применение маршрута не подтверждено.",
    "dependency_missing": "Не найдены зависимости обработчика.",
    "comparison_done": "Сравнение завершено.",
    "comparison_incomplete": "Сравнение завершено не полностью.",
    "comparison_cleanup_failed": "Возврат после сравнения не подтверждён.",
    "worker_ready": "Обработчик готов; доступность сайтов проверяется отдельно.",
    "nfqueue": "Ожидается привязка обработчика к очереди.",
    "probe_inbound": "Применён служебный вход для HTTPS-проб.",
    "route_reconcile": "Ожидается применение клиентского правила Selective.",
    "route_unconfirmed": "Клиентское правило Selective не подтверждено в Xray.",
    "capture_not_ready": "Правила перехвата ещё не подтверждены.",
    "core_busy": "Ожидается завершение операции с ядром.",
    "xray_down": "Локальный маршрутизатор Xray не отвечает.",
    "vpn_stopping": "Ожидается остановка прежних VPN-мостов XGW.",
    "vpn_requested": "Ожидается применение настроек VPN.",
}
TITLES = {
    "off": "Выключен", "active": "Обработчик готов", "absent": "Не установлен",
    "error": "Ошибка обработчика", "unknown": "Нет свежего подтверждения",
    "pending": "Ожидается применение", "preparing": "Обработчик запускается",
    "blocked": "Маршрут не подтверждён", "fallback": "Прямой путь отключён",
    "compared": "Сравнение завершено",
}


def _record(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


PAGE_KINDS = ("terms", "watch", "other")


def _probe_metrics(row: dict) -> dict:
    fields = {}
    for name, accepted in (
        ("phase", ("connect", "tls", "request", "headers", "body")),
        ("kind", ("ok", "http", "range", "proxy", "connect", "tls", "timeout", "stall",
                  "truncated", "reset", "io", "cancelled")),
    ):
        item = row.get(name)
        fields[name] = item if isinstance(item, str) and item in accepted else None
    for name, limit in (("http", 599), ("connect_http", 599),
                        ("bytes", zapret2.PROBE_BYTES), ("elapsed_ms", 60_000)):
        item = row.get(name)
        fields[name] = item if type(item) is int and 0 <= item <= limit else None
    return fields


def _range_verified(row: dict, metrics: dict, successful: bool) -> bool | None:
    evidence = row.get("range_verified")
    if type(evidence) is not bool:
        return None
    return (evidence and successful and metrics["phase"] == "body"
            and (metrics["http"], metrics["bytes"]) == (206, zapret2.PROBE_BYTES))


def _vpn_attempts(value: object, *, now: float, target: str) -> list[dict]:
    if not isinstance(value, list):
        return []
    attempts = []
    for item in value[:2]:
        row = _record(item)
        verdict, reason, at = row.get("verdict"), row.get("reason"), row.get("at")
        if (not isinstance(verdict, str) or verdict not in VPN_CONTROL_REASONS
                or not isinstance(reason, str) or reason not in VPN_CONTROL_REASONS[verdict]
                or not _number(at) or not 0 <= at <= now):
            continue
        attempt = {"verdict": verdict, "reason": reason, "at": at, **_probe_metrics(row)}
        if target == "cdn":
            proof = _range_verified(row, attempt, verdict == "pass")
            if proof is not None:
                attempt["range_verified"] = proof
        redirect = _record(row.get("redirect"))
        state, http = redirect.get("state"), redirect.get("http")
        if (isinstance(state, str) and state in CDN_REDIRECT_STATES
                and type(http) is int and http in zapret2.REDIRECT_CODES):
            changed = redirect.get("host_changed")
            attempt["redirect"] = {
                "http": http, "state": state,
                "host_changed": changed if type(changed) is bool else None,
            }
        attempts.append(attempt)
    return attempts


def transport_probes(value: object, *, now: float) -> dict:
    probes = {}
    source = _record(value)
    for target in ("page", "cdn"):
        row = _record(source.get(target))
        if type(row.get("ok")) is not bool:
            continue
        fields = {"ok": row["ok"], **_probe_metrics(row)}
        started = row.get("started_at")
        fields["started_at"] = started if _number(started) and 0 < started <= now else None
        if target == "page":
            kind = row.get("page_kind")
            fields["page_kind"] = kind if kind in PAGE_KINDS else None
        else:
            proof = _range_verified(row, fields, row["ok"])
            if proof is not None:
                fields["range_verified"] = proof
            first = row.get("first_tls_timeout_ms")
            elapsed = fields["elapsed_ms"]
            if type(first) is int and elapsed is not None and 0 <= first <= elapsed:
                fields["first_tls_timeout_ms"] = first
        probes[target] = fields
    # The CDN is reached only after a successful page probe.
    if not probes.get("page", {}).get("ok"):
        probes.pop("cdn", None)
    return probes


def transport_failure_detail(reason: str, probes: dict) -> str:
    target = "page" if reason == "youtube_page_probe_failed" else "cdn"
    row = probes.get(target) or {}
    if row.get("ok") is not False:
        return REASONS[reason]
    if row.get("phase") == "tls" and row.get("kind") == "timeout":
        if target == "page":
            return "Таймаут TLS страницы YouTube на прямом пути. Проба CDN не запускалась."
        if row.get("first_tls_timeout_ms") is not None:
            return "Таймаут TLS до CDN на прямом пути. Повтор тоже завершился таймаутом."
        return "Таймаут TLS до CDN на прямом пути."
    if (target == "cdn" and row.get("phase") == "headers" and row.get("kind") == "http"
            and row.get("http") in (403, 410)):
        return f"CDN вернул HTTP {row['http']}. Сохраните свежий адрес из плеера."
    if target == "cdn" and (row.get("kind") == "range" or (
            row.get("http") == 206 and row.get("kind") in ("truncated", "stall", "timeout", "reset")
    )):
        return "Прямая проба CDN не подтвердила полный диапазон видео."
    return REASONS[reason]


def _queue_sample(snapshot: dict, unit: str, queue: int | None, key: str, now: float) -> dict | None:
    journal = snapshot.get("zapret2_worker_events")
    sample = worker.current_queue_counters(journal, now)
    reservation = _record(snapshot.get("zapret2_reservation"))
    if (sample is None or sample["unit"] != unit or sample["queue"] != queue
            or reservation.get("unit") != unit
            or type(reservation.get("queue")) is not int or reservation["queue"] != queue
            or type(reservation.get("generation")) is not int
            or reservation["generation"] != sample["generation"]
            or journal["events"][-1].get("policy_key") != key):
        return None
    return {**sample, "epoch": journal.get("epoch"), "series": journal.get("queue_series")}


def card(cfg, snapshot: dict, capture: dict, daemon_ready: bool, *, now=None,
         probe_budget: dict | None = None) -> dict:
    """Always return a card; a worker fault never means that VPN was restored.

Only allowlisted public fields leave the snapshot. A revision is published by the daemon
from its effective settings; a newer panel configuration cannot relabel old observations.
Commands use the same validation as this card; observations remain revision-bound.
"""
    now = time.time() if now is None else now
    observed = snapshot.get("updated")
    fresh = (daemon_ready and snapshot.get("daemon") is not False and _number(observed)
             and 0 <= now - observed <= FRESH_SECONDS)
    invalid = False
    try:
        policy = schema.migrate(cfg.desync or vars(cfg.zapret2))
    except schema.PolicyError:
        policy, invalid = schema.migrate({}), True
    settings = schema.flatten(policy)
    key = schema.fingerprint(policy)
    selected = _record(snapshot.get("zapret2"))
    engine = _record(_record(snapshot.get("capture")).get("nfqws2"))
    reservation = _record(snapshot.get("zapret2_reservation")).get("unit")
    source = "selected" if settings["mode"] != "off" else "engine"
    enabled = settings["mode"] != "off" or settings["engine"] == "auto"
    raw = selected if source == "selected" else engine
    phase = raw.get("state", "unknown")
    reason = raw.get("reason", "")
    reason = reason if isinstance(reason, str) and reason in REASONS else "unconfirmed"
    detail = REASONS.get(reason, "Состояние ещё не подтверждено демоном.")
    matched = snapshot.get("zapret2_policy_key") == key
    if invalid:
        phase, reason, detail = "error", "invalid_policy", "Политика zapret2 некорректна."
    elif not fresh:
        phase, reason, detail = "unknown", "stale", "Демон не передал свежий снимок состояния."
    elif not snapshot.get("zapret2_policy_key"):
        phase, reason, detail = "unknown", "legacy_snapshot", (
            "Снимок старого демона не содержит ревизию политики. Обновите backend.")
    elif not matched:
        phase, reason, detail = "pending", "policy_changed", (
            "Настройки изменились. Ожидается снимок демона с новой ревизией.")
    elif not enabled:
        if reservation in (worker.SELECTED_UNIT, worker.ENGINE_UNIT) or any(
                r.get("state") not in (None, "off") for r in (selected, engine)):
            phase, reason, detail = "pending", "stopping", "Выключение ещё не подтверждено."
        else:
            phase, reason, detail = "off", "off", REASONS["off"]
    elif source == "engine":
        if reservation == worker.SELECTED_UNIT:
            phase, reason = "pending", "worker_handoff_pending"
            detail = REASONS[reason]
        elif phase == "fallback":
            phase = "error"
            detail += " Возврат трафика на VPN этим состоянием не подтверждается."
        elif phase == "off" and reason == "not_found":
            phase = "absent"
    elif reservation == worker.ENGINE_UNIT:
        phase, reason = "pending", "worker_handoff_pending"
        detail = REASONS[reason]
    elif phase == "active":
        until = raw.get("valid_until")
        if not _number(until) or until <= now:
            phase, reason, detail = "unknown", "expired", REASONS["expired"]
    if phase == "active" and (capture.get("mode") != "on"
                              or _record(snapshot.get("capture")).get("loaded") is not True):
        phase, reason, detail = "unknown", "capture_unconfirmed", "Перехват не подтверждён."
    if phase == "fallback" and selected.get("gate_closed") is not True:
        phase = "blocked"
    if not isinstance(phase, str) or phase not in TITLES:
        phase = "unknown"
    without_vpn = (fresh and matched and phase == "active" and settings["mode"] == "standalone"
                   and selected.get("without_vpn") is True)
    vpn_control, vpn_control_reason, vpn_control_at = "not_run", None, None
    vpn_control_target = None
    vpn_control_attempts = []
    vpn_control_retry_pending = False
    if (fresh and matched and not invalid and settings["mode"] == "selective"
            and phase in ("fallback", "blocked")):
        verdict = selected.get("vpn_control")
        if phase == "fallback" and verdict in ("pass", "fail"):
            vpn_control = verdict
        why = selected.get("vpn_control_reason")
        at = selected.get("vpn_control_at")
        if (verdict == vpn_control and isinstance(why, str)
                and why in VPN_CONTROL_REASONS[vpn_control] and _number(at) and 0 <= at <= now):
            vpn_control_reason, vpn_control_at = why, at
            target = selected.get("vpn_control_target")
            if target in ("page", "cdn"):
                vpn_control_target = target
                vpn_control_attempts = _vpn_attempts(
                    selected.get("vpn_control_attempts"), now=now, target=target,
                )
                vpn_control_retry_pending = (
                    target == "cdn" and phase == "fallback" and vpn_control == "fail"
                    and selected.get("vpn_control_retry_pending") is True
                )
    profile = raw.get("profile") if source == "engine" else settings["strategy"]
    allowed = schema.ENGINE_PROFILES if source == "engine" else schema.SELECTED_PROFILES
    profile = profile if isinstance(profile, str) and profile in allowed else None
    queue = raw.get("queue") if source == "engine" else settings["queue_num"]
    queue = queue if type(queue) is int and 1 <= queue <= 65535 else None
    trusted = fresh and matched and not invalid
    urls = settings["probe_urls"]
    cdn_path = (urlsplit(urls[1]).path if settings.get("youtube_transport_probe")
                and len(urls) == 2 else None)
    counters = {"queued_original": None, "queued_reply": None, "queue_dropped": None,
                "queue_overflow": None, "queue_netlink_dropped": None, "strategy_switches": None}
    worker_start_ms = None
    queue_loss_sample = None
    if trusted and phase == "active":
        unit = worker.SELECTED_UNIT if source == "selected" else worker.ENGINE_UNIT
        if sample := _queue_sample(snapshot, unit, queue, key, now):
            counters.update(queue_overflow=sample["overflow"], queue_netlink_dropped=sample["netlink"],
                            queue_dropped=sample["overflow"] + sample["netlink"])
            queue_loss_sample = worker.monitor_queue_sample(sample, now)
        worker_start_ms = worker.startup_duration(
            snapshot.get("zapret2_worker_events"), snapshot.get("zapret2_reservation"),
            unit, queue, key,
        )
    transport = ("https_reachable"
                 if trusted and phase == "active" and reason == "youtube_transport_ok"
                 and settings.get("youtube_transport_probe") is True else "unknown")
    transport_failed = (phase in ("fallback", "blocked")
                        and reason in ("youtube_page_probe_failed", "youtube_cdn_probe_failed"))
    transport_rows = {}
    if (trusted and settings["mode"] == "selective" and settings.get("youtube_transport_probe")
            and (transport == "https_reachable" or transport_failed)):
        transport_rows = transport_probes(selected.get("transport_probes"), now=now)
        if cdn_path != "/videoplayback":
            transport_rows.get("cdn", {}).pop("range_verified", None)
        if transport_failed:
            detail = transport_failure_detail(reason, transport_rows)
        elif cdn_path == "/videoplayback" and transport_rows.get("cdn", {}).get("range_verified"):
            detail = ("CDN передал проверочный диапазон 65 536 байт. "
                      "Воспроизведение проверяется отдельно.")
        elif cdn_path == "/generate_204":
            detail = ("Страница и служебный адрес CDN доступны по HTTPS. "
                      "Воспроизведение проверяется отдельно.")
    if phase == "fallback":
        detail += " Контроллер снял прямой маршрут."
        control_fresh = vpn_control_at is not None and now - vpn_control_at <= FRESH_SECONDS
        latest = next((row for row in reversed(vpn_control_attempts)
                       if row["at"] == vpn_control_at), {})
        if control_fresh and vpn_control_target == "cdn" and vpn_control == "pass":
            if latest.get("range_verified") is True:
                if "redirect" in latest:
                    detail += " Диапазон CDN через VPN подтверждён после перенаправления."
                elif len(vpn_control_attempts) == 2:
                    detail += " Повторная проба через VPN подтвердила диапазон CDN."
                else:
                    detail += " Диапазон того же CDN через VPN подтверждён."
            elif "redirect" in latest:
                detail += " CDN ответил через VPN после перенаправления."
            elif len(vpn_control_attempts) == 2:
                detail += " Повторная проба того же URL CDN через VPN прошла."
            else:
                detail += " Тот же пробный URL CDN ответил через VPN."
        elif control_fresh and vpn_control_target == "cdn" and vpn_control == "fail":
            if vpn_control_reason == "cdn_redirect_unconfirmed":
                detail += " CDN перенаправил запрос через VPN. Диапазон видео не подтверждён."
            elif latest.get("http") == 403:
                detail += " CDN вернул HTTP 403 через VPN."
            else:
                detail += " Проба URL CDN через VPN тоже не прошла."
            if vpn_control_retry_pending:
                detail += " Ожидается один повтор через VPN."
        elif control_fresh and vpn_control_reason == zapret2.CDN_EXPIRED:
            detail += " Срок пробного адреса CDN истёк."
        elif control_fresh and vpn_control == "pass" and vpn_control_reason == "ok":
            detail += " Свежая контрольная проба через VPN прошла."
        else:
            detail += " Доступность VPN проверяется отдельно."
    elif phase == "blocked" and settings["mode"] == "selective":
        detail += " Возврат маршрута не подтверждён."
    last_transport_ok_at = selected.get("last_transport_ok_at")
    if (not trusted or settings["mode"] != "selective"
            or not settings.get("youtube_transport_probe")
            or not _number(last_transport_ok_at) or not 0 < last_transport_ok_at <= now):
        last_transport_ok_at = None
    page_kind = (zapret2.youtube_probe_page_kind(urls[0])
                 if settings.get("youtube_transport_probe") and urls else None)
    blockers = {mode: management.reasons(cfg, mode, ready=fresh, capture=capture)
                for mode in schema.MODES} if not invalid else {
                    mode: ["Политика zapret2 некорректна."] for mode in schema.MODES}
    if not invalid and urls:
        problem = zapret2.probe_admission(
            replace(cfg.zapret2, mode="selective"),
            probe_budget.get("remaining_bytes") if probe_budget is not None else None)
        if problem:
            blockers["selective"].append(
                "Учёт бюджета проб недоступен." if problem == "budget_unavailable" else
                "Недостаточно остатка для прямых проб и контрольной проверки VPN.")
    return {
        "schema_version": schema.VERSION, "mode": settings["mode"], "source": source,
        "engine_mode": settings["engine"], "state": phase, "reason": reason,
        "title": TITLES[phase], "detail": detail, "fresh": bool(fresh),
        "observed_at": observed if _number(observed) else None, "config_key": key,
        "policy_matched": bool(matched), "without_vpn": bool(without_vpn),
        "strategy": profile if trusted and phase == "active" else None,
        "configured_strategy": (settings["engine_profile"] if source == "engine"
                                else settings["strategy"]),
        "selected_strategy": settings["strategy"],
        "strategies": list(management.PROFILES), "domains": settings["domains"],
        "flowseal_exclude_domains": settings.get("flowseal_exclude_domains", []),
        "can_edit_flowseal_exclusions": not invalid and settings["mode"] == "off",
        "worker": {"profile": profile if trusted else None,
                   "queue": queue if trusted else None},
        "counters": counters,
        "evidence": {"transport": transport, "playback": "not_tested",
                     "worker_start_ms": worker_start_ms,
                     "queue_loss_sample": queue_loss_sample,
                     "transport_probes": transport_rows,
                     "last_transport_ok_at": last_transport_ok_at,
                     "vpn_control": vpn_control, "vpn_control_reason": vpn_control_reason,
                     "vpn_control_target": vpn_control_target, "vpn_control_at": vpn_control_at,
                     "vpn_control_attempts": vpn_control_attempts,
                     "vpn_control_retry_pending": vpn_control_retry_pending},
        "can_off": not invalid, "can_edit": not invalid,
        "can_replace_cdn_probe": not invalid and management.can_replace_cdn_probe(cfg.zapret2),
        "capabilities": {"status": True, "change_mode": not invalid, "edit_policy": not invalid},
        "blockers": blockers,
        "youtube_transport_probe": settings.get("youtube_transport_probe", False),
        "youtube_domains": list(schema.YOUTUBE_DOMAINS),
        "youtube_probe_page_kind": page_kind,
        "probe_count": len(settings["probe_urls"]), "probes": [],
        "probe_expiry": [{"probe": 2, "expires_at": schema.youtube_cdn_expiry(urls[1])}]
        if settings.get("youtube_transport_probe") and len(urls) == 2 else [],
        "check_seconds": settings["check_seconds"], "retry_seconds": settings["retry_seconds"],
        "daily_probe_mb": settings["daily_probe_mb"],
        "probe_budget": probe_budget,
    }
