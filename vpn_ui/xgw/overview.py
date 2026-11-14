"""Сводка главного экрана из подтверждённого API; без сетевых действий и Qt."""
from dataclasses import dataclass

from xgw.gui import model


@dataclass(frozen=True)
class Status:
    text: str
    detail: str
    tone: str = "off"


def zapret_status(state: dict, stale: bool) -> Status:
    if stale:
        return Status("Нет связи", "Состояние zapret2 не подтверждено свежими данными.", "warn")
    view = state.get("zapret2") or {}
    if not view:
        return Status("Нет данных", "Панель не передаёт состояние zapret2.")
    phase = view.get("state")
    detail = str(view.get("detail") or view.get("title") or "Состояние ещё не подтверждено.")
    if phase == "active":
        text = "Без VPN" if view.get("without_vpn") else "Обработчик готов"
        # Готовность процесса/маршрута не подтверждает просмотр конкретного видео.
        return Status(text, detail + " Готовность обработчика не подтверждает "
                      "воспроизведение YouTube.", "ok")
    text, tone = {
        "off": ("Выключен", "off"), "fallback": ("Возврат на VPN", "warn"),
        "blocked": ("Ошибка", "bad"), "pending": ("Применяется", "busy"),
        "preparing": ("Запускается", "busy"), "unknown": ("Не подтверждён", "warn"),
        "compared": ("Сравнение завершено", "off"),
    }.get(phase, ("Не подтверждён", "warn"))
    if phase == "off" and view.get("mode", "off") != "off":
        text, tone = "Не используется", "warn"
    return Status(text, detail, tone)


def guard_status(state: dict, stale: bool) -> Status:
    if stale:
        return Status("Нет данных", "Ожидается свежее состояние шлюза.", "warn")
    capture = state.get("capture") or {}
    if capture.get("blocked"):
        return Status("Трафик закрыт", "Шлюз сообщает об активной блокировке трафика.", "bad")
    if capture.get("mode") in ("off", "open"):
        return Status("Прямой доступ", "Перехват выключен или временно снят.", "warn")
    if capture.get("mode") != "on":
        return Status("Не настроена", "Перехват трафика не настроен.")
    if capture.get("fail_mode") == "closed":
        return Status("Закрывать доступ", "При отказе шлюз закрывает доступ в интернет.")
    if capture.get("fail_mode") == "open":
        return Status("Напрямую", "При отказе допускается прямой интернет.", "warn")
    return Status("Нет данных", "Панель не передаёт политику при отказе.")


@dataclass(frozen=True)
class Overview:
    status: str
    tone: str
    server: str
    source: str
    speed: str = "—"
    rtt: str = "—"
    core: str = "—"


def overview(state: dict, stale: bool, busy: bool = False) -> Overview:
    tone, status = model.shield(state or None, stale, acting=busy)
    if stale or not state:
        return Overview(status, tone, "Соединение не подтверждено",
                        "Ждём свежие данные от шлюза")
    capture = state.get("capture") or {}
    zapret = state.get("zapret2") or {}
    if capture.get("mode") in ("off", "open"):
        return Overview(status, tone, "Прямое подключение", "VPN-сервер не используется")
    if zapret.get("without_vpn"):
        ready = zapret_status(state, False)
        if busy:
            ready = Status("Ожидается подтверждение режима", "", "busy")
        elif capture.get("blocked") or zapret.get("state") == "blocked":
            ready = Status("Выбранные домены заблокированы", "", "bad")
        elif capture.get("loaded") is False or capture.get("inbound_missing"):
            ready = Status("Обработчик не подтверждён", "", "warn")
        elif zapret.get("state") == "active":
            ready = Status("Обработчик готов · доступность сайтов проверяется отдельно", "", "ok")
        return Overview(status, ready.tone, "Домашний адрес · без VPN", ready.text)
    if (busy or zapret.get("mode") == "standalone" or capture.get("mode") != "on"
            or capture.get("blocked") or capture.get("loaded") is False
            or capture.get("inbound_missing") or tone != "ok"):
        return Overview(status, tone, "Маршрут не подтверждён",
                        "Сведения появятся после подтверждения шлюзом")
    if model.pool_house(state):
        flow = model.pool_flow(state) or {}
        return Overview(status, tone, str(flow.get("server") or "Бесплатный пул"),
                        "Бесплатный пул · автовыбор XGW")
    main = model.main_server(state)
    if main is None:
        return Overview(status, tone, "Автовыбор XGW", "Единый активный сервер не указан")
    row = next((row for row in state.get("servers", []) if row.get("tag") == main.tag), {})
    source = str(row.get("source") or "")
    source = "Отдельная ссылка" if source == "manual" else source
    selection = "Выбран вручную" if main.pinned else "Автовыбор XGW"
    return Overview(status, tone, model.split_flag(main.name)[1],
                    " · ".join(filter(None, (source, selection))),
                    model.mbps_text(main.speed_mbps), model.ms_text(main.rtt_ms),
                    main.core or "—")
