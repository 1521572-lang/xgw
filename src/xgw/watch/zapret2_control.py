"""Состояние и команды zapret2 для окна через общий API панели."""

from __future__ import annotations

import copy
import time
from pathlib import Path

from .. import actions, config, managed, zapret2

TITLES = {
    "off": "Выключен", "preparing": "Подготовка и проверка",
    "active": "Работает для выбранных доменов", "fallback": "Возврат на VPN",
    "blocked": "Возврат на VPN не подтверждён", "compared": "Сравнение завершено",
    "pending": "Применение настроек", "unknown": "Нет свежего подтверждения",
}
REASONS = {
    "off": "Прямой маршрут zapret2 выключен.",
    "probe_inbound": "Готовится отдельный вход для проверки.",
    "nfqueue": "Запущен обработчик. Ожидается проверка очереди и доступности адресов.",
    "probes_ok": "Проверки прошли. Выбранные HTTPS-домены идут через домашний IP.",
    "waiting_for_probe_urls": "Нужны адреса проверок страницы и видео в настройках zapret2.",
    "retry_wait": "Ожидается следующий круг проверок.",
    "queue_busy": "Очередь занята другим процессом.",
    "unsafe_files": "Проверьте владельца и права файлов zapret2.",
    "unsafe_directory": "Проверьте владельца и права каталогов zapret2.",
    "worker_down": "Обработчик пакетов остановился или очередь недоступна.",
    "probe_budget": "Суточный бюджет проверок исчерпан или его учёт повреждён.",
    "probe_failed": "Один из адресов проверки не ответил успешно. Будет повторная попытка.",
    "apply_failed": "Не удалось применить маршрут через API Xray.",
    "dependency_missing": "Не найдены необходимые файлы или команды zapret2.",
    "runtime_failed": "Ошибка запуска или выполнения zapret2. Проверьте диагностику шлюза.",
    "stop_failed": "Остановка обработчика не подтверждена.",
    "comparison_done": "Круг сравнения завершён. Результат каждого запроса показан ниже.",
    "comparison_incomplete": "Круг сравнения не завершён полностью.",
    "comparison_cleanup_failed": "Завершение сравнения и возврат маршрута не подтверждены.",
    "worker_ready": "Без VPN. Обработчик готов. Выбранные HTTPS-домены идут через zapret2, "
                    "остальные напрямую. Это ещё не подтверждает воспроизведение YouTube.",
    "vpn_requested": "Запрошен возврат к VPN. Ожидается конфиг с серверами.",
    "capture_failed": "Не удалось включить перехват для режима без VPN.",
    "vpn_stopping": "Прямой конфиг применён. Ожидается завершение прежних проверок и VPN-мостов.",
    "invalid_config": "Проверьте настройки zapret2. Переход в режим без VPN не подтверждён.",
}

VERDICTS = {
    "ok": "Проверка пройдена", "empty_body": "Ответ 204 без тела не подходит для проверки видео",
    "short_body": "Тело ответа меньше необходимых 16 КиБ", "redirect": "Получено перенаправление",
    "http_error": "Сервер ответил HTTP-ошибкой", "timeout": "Истекло время ожидания",
    "stall": "Передача остановилась", "truncated": "Ответ оборвался до завершения",
    "reset": "Соединение сброшено", "tls": "Ошибка TLS", "connect": "Ошибка соединения",
    "proxy": "Ошибка служебного прокси", "cancelled": "Проверка прервана",
    "io": "Ошибка ввода-вывода", "unknown": "Причина не уточнена",
    "not_run": "Не запускалась после отказа предыдущей проверки",
}


def prerequisites(cfg, mode: str) -> list[str]:
    candidate = copy.deepcopy(cfg)
    candidate.zapret2.mode = mode
    problems = zapret2.validate(candidate)
    if not problems and mode != "standalone" and not zapret2.configured(candidate):
        problems.append("Задайте адреса проверок страницы и видео в настройках zapret2.")
    paths = (cfg.zapret2.binary, f"{cfg.zapret2.lua_dir}/zapret-lib.lua",
             f"{cfg.zapret2.lua_dir}/zapret-antidpi.lua")
    if not all(Path(path).is_file() for path in paths):
        problems.append("Файлы zapret2 не найдены по путям из настроек шлюза.")
    return problems


def card(cfg, snapshot: dict, capture: dict, daemon_ready: bool) -> dict:
    raw = snapshot.get("zapret2") or {}
    key = zapret2.config_key(cfg)
    fresh = (daemon_ready and isinstance(snapshot.get("updated"), int | float)
             and 0 <= time.time() - snapshot["updated"] <= 90)
    pending = raw.get("config_key") != key
    state = raw.get("state", "unknown")
    reason = raw.get("reason", "")
    detail = REASONS.get(reason, "Состояние ещё не подтверждено демоном.")
    if not fresh:
        state, detail = "unknown", "Демон не передал свежие данные. Управление недоступно."
    elif pending:
        state, detail = "pending", "Режим сохранён. Ожидается подтверждение демона."
    elif state == "active" and raw.get("valid_until", 0) <= time.time():
        state, detail = "unknown", "Срок последней успешной проверки истёк."
    elif state == "off" and cfg.zapret2.mode != "off":
        detail = "Режим выбран, но прямой маршрут сейчас не используется. Проверьте VPN и пул."
    blockers = {}
    for mode in ("standalone", "compare", "selective"):
        problems = prerequisites(cfg, mode)
        if not fresh:
            problems.insert(0, "Нет свежих данных демона.")
        elif pending:
            problems.insert(0, "Дождитесь применения предыдущих настроек.")
        elif cfg.zapret2.mode != "off":
            problems.insert(0, "Сначала выключите текущий режим zapret2.")
        elif state != "off":
            problems.insert(0, "Дождитесь подтверждённого выключения zapret2.")
        if mode != "standalone" and (
                capture.get("mode") != "on" or not (snapshot.get("xray") or {}).get("ok")):
            problems.insert(0, "Сначала включите VPN и дождитесь работающего Xray.")
        if mode == "standalone" and not (cfg.capture.local or cfg.capture.lan):
            problems.insert(0, "Сначала настройте перехват трафика шлюза.")
        if mode != "standalone" and cfg.free_pool.mode == "on":
            problems.insert(0, "Режим всего дома через бесплатный пул имеет приоритет.")
        if state == "blocked":
            problems.insert(0, "Сначала устраните ошибку возврата на VPN.")
        blockers[mode] = problems
    probes = []
    for row in raw.get("probes", []) if not pending and fresh else []:
        if not isinstance(row, dict) or row.get("path") not in ("vpn", "zapret2"):
            continue
        probes.append({
            **{k: row.get(k, 0) if type(row.get(k, 0)) is int else 0
               for k in ("probe", "http", "connect_http", "bytes", "redirects", "checked_at")},
            "path": row["path"], "ok": row.get("ok") is True,
            "verdict": row.get("verdict") if row.get("verdict") in VERDICTS else "unknown",
            "detail": VERDICTS.get(row.get("verdict"), ""),
        })
    title = TITLES.get(state, TITLES["unknown"])
    if raw.get("without_vpn"):
        if state == "active":
            title = "Обработчик готов · без VPN"
        elif state == "blocked":
            title = "Выбранные домены заблокированы · без VPN"
        elif state == "off":
            title = "Перехват выключен · без VPN"
            detail = "Прямой интернет без обработки zapret2. Включите перехват кнопкой питания."
    elif cfg.zapret2.mode == "standalone" and state == "blocked":
        title = "Режим без VPN не подтверждён"
    return {
        "mode": cfg.zapret2.mode, "strategy": cfg.zapret2.strategy,
        "domains": list(cfg.zapret2.domains), "probe_count": len(cfg.zapret2.probe_urls),
        "config_key": key, "state": state, "title": title,
        "without_vpn": bool(raw.get("without_vpn")) if fresh else False,
        "detail": detail, "blockers": blockers, "probes": probes,
        "can_off": fresh and (cfg.zapret2.mode != "off" or state == "blocked"),
        "can_edit": fresh and not pending and cfg.zapret2.mode == "off" and state == "off",
        "check_seconds": cfg.zapret2.check_seconds, "retry_seconds": cfg.zapret2.retry_seconds,
        "daily_probe_mb": cfg.zapret2.daily_probe_mb,
        "probe_expiry": [{"probe": n, "expires_at": zapret2.expiry(url)}
                         for n, url in enumerate(cfg.zapret2.probe_urls, 1)],
    }


def change(panel, name: str, body: dict) -> actions.Outcome:
    # Перечитать файл перед действием, в том числе после правки другим клиентом.
    try:
        cfg, _ = config.load(panel.config_path)
    except config.ConfigError:
        return actions.Outcome(1, "Не удалось прочитать настройки шлюза. Проверьте config.toml.")
    snapshot = panel._core(time.time())[0]
    view = card(cfg, snapshot, panel._capture().describe(check=False), panel.daemon is not None)
    if name == "zapret2/mode" and body.get("mode") == "off":
        settings = {"mode": "off"}  # выключение не зависит от пригодности адресов и файлов
        done = "Выключение zapret2 запрошено. Дождитесь подтверждения состояния."
    else:
        if body.get("expected") != view["config_key"]:
            return actions.Outcome(2, "Настройки zapret2 изменились. Обновите окно и повторите.")
        if name == "zapret2/mode":
            mode = body.get("mode")
            if not isinstance(mode, str) or mode not in view["blockers"]:
                return actions.Outcome(2, "Неизвестный режим zapret2")
            if view["blockers"][mode]:
                return actions.Outcome(2, view["blockers"][mode][0])
            settings = {"mode": mode}
            done = "Режим zapret2 сохранён. Дождитесь проверки и подтверждения состояния."
        else:
            if not view["can_edit"]:
                return actions.Outcome(2, "Для настройки сначала выключите zapret2.")
            settings = managed.zapret2_settings(body.get("settings"))
            if "mode" in settings:
                return actions.Outcome(2, "Режим включается отдельной кнопкой.")
            candidate = copy.deepcopy(cfg)
            for field, value in settings.items():
                setattr(candidate.zapret2, field, value)
            problems = zapret2.validate(candidate)
            if problems:
                return actions.Outcome(2, problems[0])
            done = "Настройки zapret2 сохранены. Режим выключен."
    managed.set_zapret2(managed.path_for(panel.config_path), settings)
    panel._wake()
    panel._event(done)  # ни адреса проб, ни домены сюда не попадают
    return actions.Outcome(0, done)
