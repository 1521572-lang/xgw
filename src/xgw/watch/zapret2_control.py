"""Read-only compatibility card for both legacy controllers. No OS calls or probes."""

from __future__ import annotations

import math
import time

from ..desync import schema, worker

FRESH_SECONDS = 90
REASONS = {
    "off": "Обработка выключена.",
    "disabled": "Обработка выключена в настройках.",
    "inactive": "Перехват не включён.",
    "not_found": "Не найден бинарник nfqws2 или обязательные библиотеки Lua.",
    "worker_down": "Обработчик или очередь недоступны.",
    "worker_start_timeout": "Обработчик не подтвердил готовность вовремя.",
    "queue_busy": "Номер очереди занят.",
    "worker_unit_busy": "Служба обработчика уже занята.",
    "worker_handoff_pending": "Предыдущий обработчик ещё освобождает очередь.",
    "unsafe_files": "Файлы обработчика не прошли проверку прав.",
    "unsafe_directory": "Каталог обработчика не прошёл проверку прав.",
    "runtime_failed": "Ошибка обработчика. Подробности доступны в журнале шлюза.",
    "worker_stop_failed": "Остановка обработчика не подтверждена.",
    "stop_failed": "Остановка обработчика не подтверждена.",
    "offload_restore": "Восстановление настроек сетевого интерфейса не подтверждено.",
    "offload_apply": "Не удалось изменить настройки сетевого интерфейса.",
    "probe_failed": "Проверка прямого пути не прошла.",
    "probe_budget": "Исчерпан бюджет проверок прямого пути.",
    "probes_ok": "Пробы прямого пути прошли; воспроизведение проверяется отдельно.",
    "retry_wait": "Ожидается повтор проверки прямого пути.",
    "apply_failed": "Применение маршрута не подтверждено.",
    "dependency_missing": "Не найдены зависимости обработчика.",
    "comparison_done": "Сравнение завершено.",
    "comparison_incomplete": "Сравнение завершено не полностью.",
    "comparison_cleanup_failed": "Возврат после сравнения не подтверждён.",
    "worker_ready": "Обработчик готов; доступность сайтов проверяется отдельно.",
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


def card(cfg, snapshot: dict, capture: dict, daemon_ready: bool, *, now=None) -> dict:
    """Always return a card; a worker fault never means that VPN was restored.

Only allowlisted public fields leave the snapshot. A revision is published by the daemon
from its effective settings; a newer panel configuration cannot relabel old observations.
The card exposes state only. Mode-changing commands belong to T11.
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
            phase, reason, detail = "unknown", "expired", "Подтверждение прямого пути истекло."
    if phase == "active" and (capture.get("mode") != "on"
                              or _record(snapshot.get("capture")).get("loaded") is not True):
        phase, reason, detail = "unknown", "capture_unconfirmed", "Перехват не подтверждён."
    if phase == "fallback":
        detail += " Контроллер снял прямой маршрут; доступность VPN проверяется отдельно."
        if selected.get("gate_closed") is not True:
            phase = "blocked"
    if not isinstance(phase, str) or phase not in TITLES:
        phase = "unknown"
    without_vpn = (fresh and matched and settings["mode"] == "standalone"
                   and selected.get("without_vpn") is True)
    profile = raw.get("profile") if source == "engine" else settings["strategy"]
    allowed = schema.ENGINE_PROFILES if source == "engine" else schema.SELECTED_PROFILES
    profile = profile if isinstance(profile, str) and profile in allowed else None
    queue = raw.get("queue") if source == "engine" else settings["queue_num"]
    queue = queue if type(queue) is int and 1 <= queue <= 65535 else None
    trusted = fresh and matched and not invalid
    unavailable = ["Управление режимами пока недоступно в этой версии панели."]
    return {
        "schema_version": schema.VERSION, "mode": settings["mode"], "source": source,
        "engine_mode": settings["engine"], "state": phase, "reason": reason,
        "title": TITLES[phase], "detail": detail, "fresh": bool(fresh),
        "observed_at": observed if _number(observed) else None, "config_key": key,
        "policy_matched": bool(matched), "without_vpn": bool(without_vpn),
        "strategy": profile if trusted and phase == "active" else None,
        "configured_strategy": (settings["engine_profile"] if source == "engine"
                                else settings["strategy"]),
        "strategies": [], "domains": settings["domains"],
        "worker": {"profile": profile if trusted else None,
                   "queue": queue if trusted else None},
        "counters": {"queued_original": None, "queued_reply": None,
                     "queue_dropped": None, "strategy_switches": None},
        "evidence": {"transport": "unknown", "playback": "not_tested"},
        "can_off": False, "can_edit": False,
        "capabilities": {"status": True, "change_mode": False, "edit_policy": False},
        "blockers": {mode: list(unavailable) for mode in schema.MODES},
        "probe_count": len(settings["probe_urls"]), "probes": [], "probe_expiry": [],
        "check_seconds": settings["check_seconds"], "retry_seconds": settings["retry_seconds"],
        "daily_probe_mb": settings["daily_probe_mb"],
    }
