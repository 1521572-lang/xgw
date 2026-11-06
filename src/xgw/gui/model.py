"""Логика окна XGW без Qt: смысл состояний шлюза, форматы чисел, расписание опроса, защита от
повторных действий, сеанс входа. Тексты и тона — те же, что у браузерной панели (ui/app.js),
чтобы окно и страница говорили об одном и том же одинаково.
"""

from __future__ import annotations

import contextlib
import json
import os
import random
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .. import masking

# Опрос /api/state: окно на экране — раз в POLL_VISIBLE, свёрнуто или скрыто — реже.
POLL_VISIBLE = 3.0
POLL_HIDDEN = 15.0
# Демон пишет состояние на каждом шаге (status.json); старше — «демон не отвечает» (app.js).
STALE_S = 90.0
REQUEST_TIMEOUT = 10.0  # секунд на ответ панели; дольше — сбой связи
# После сбоя связи — пауза BACKOFF_START, BACKOFF_START·2… до BACKOFF_MAX, ±JITTER.
BACKOFF_START = 2.0
BACKOFF_MAX = 60.0
JITTER = 0.2
SESSION_ENV = "XGW_GUI_SESSION"  # другой файл сеанса — демо и тесты
SESSION_FILE = Path(".config/xgw/gui.json")  # в домашнем каталоге человека
COOKIE = "xgw_panel"  # watch/panel.py COOKIE
HEADER = "X-XGW-Panel"  # watch/panel.py HEADER — без него панель не примет POST

# Тон (ok, warn, bad, off) и слово — как STATES в ui/app.js.
STATES = {
    "HEALTHY": ("ok", "Серверы в порядке"),
    "DEGRADED": ("warn", "Часть серверов недоступна"),
    "ALL_DEAD": ("bad", "Все серверы недоступны"),
    "WAN_DOWN": ("bad", "Нет связи с провайдером"),
    "XRAY_DOWN": ("bad", "Xray не отвечает"),
    "LEAK": ("bad", "Трафик идёт мимо VPN"),
    "PROBE_TARGET_UNREACHABLE": ("warn", "Адрес проверки недоступен"),
    "RESERVE": ("warn", "Работает резервный сервер"),
}
# Значок рядом с текстом: состояние видно и без цвета.
MARKS = {"ok": "✓", "warn": "!", "bad": "✕", "off": "–", "busy": "…"}
# Жизненный цикл перехвата (daemon.Lifecycle) — LIFECYCLE в ui/app.js.
LIFECYCLE = {
    "connected": ("ok", "работает", "трафик идёт через VPN"),
    "connecting": ("warn", "подключается", "трафик ждёт, мимо VPN ничего не уходит"),
    "blocked": ("bad", "заблокирован", "мимо VPN ничего не уходит"),
    "open": ("warn", "временно напрямую", "трафик идёт мимо VPN"),
    "off": ("off", "снят", "трафик идёт напрямую"),
}
FAIL_MODES = {
    "closed": "при сбое Xray интернет закрывается (fail-closed): мимо VPN ничего не уходит",
    "open": "при сбое Xray трафик временно идёт напрямую (fail-open)",
}


# --- состояние шлюза -------------------------------------------------------------------------


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def is_stale(state: dict | None) -> bool:
    """Состояние устарело: демон давно не писал его (панель отвечает, демон — нет)."""
    if not state:
        return True
    now, updated = state.get("now"), state.get("updated")
    if not isinstance(now, int | float) or not isinstance(updated, int | float):
        return False  # демон ещё запускается — это не «не отвечает» (health)
    return now - updated > STALE_S


def pool_house(state: dict) -> bool:
    """Весь дом через бесплатные серверы (free_pool.mode = on, М2б.2)."""
    return _dict(state.get("free_pool")).get("mode") == "on"


def pool_flow(state: dict) -> dict | None:
    flow = _dict(_dict(_dict(state.get("free_pool")).get("summary")).get("traffic"))
    return flow or None


def health(state: dict | None, stale: bool) -> tuple[str, str]:
    """(тон, текст) метки состояния — как health() в ui/app.js."""
    if state is None:
        return "bad", "Панель XGW не отвечает"
    if not state.get("updated"):
        return "off", "Запускается…"
    if stale:
        return "bad", "Демон XGW не отвечает"
    capture = _dict(state.get("capture"))
    name = str(state.get("state") or "")
    if pool_house(state):
        if name in ("WAN_DOWN", "XRAY_DOWN", "LEAK"):
            return STATES[name]
        if capture.get("mode") == "on" and capture.get("lan_problem"):
            return "bad", "Нет интернета в сети"
        flow = pool_flow(state)
        if not flow:
            return "warn", "Бесплатные серверы подключаются"
        return ("bad", "Бесплатных серверов нет") if flow.get("closed") else (
            "ok", "Через бесплатные серверы")
    if not _list(state.get("members")):
        return "off", "Серверов нет"
    if capture.get("mode") == "on" and capture.get("lan_problem"):
        return "bad", "Нет интернета в сети"
    return STATES.get(name, ("off", name or "Нет данных"))


def scope_text(capture: dict) -> str:
    """Что идёт через VPN — scopeText в ui/app.js."""
    docker = bool(capture.get("containers") and capture.get("docker"))
    lan_if = str(capture.get("lan_if") or "")
    if capture.get("lan") and capture.get("local"):
        machine = "Эта машина, контейнеры Docker" if docker else "Эта машина"
        return f"{machine} и сеть {lan_if} выходят через VPN"
    if capture.get("lan"):
        return (f"Сеть {lan_if} и контейнеры Docker выходят через VPN" if docker
                else f"Сеть {lan_if} выходит через VPN")
    return ("Эта машина и контейнеры Docker выходят через VPN" if docker
            else "Эта машина выходит через VPN")


@dataclass(frozen=True)
class Power:
    """Большой переключатель VPN: заголовок, пояснение, тон, нажат ли и можно ли нажать."""

    title: str
    sub: str
    tone: str
    pressed: bool
    enabled: bool
    why: str = ""


def power(state: dict | None, stale: bool, *, acting: bool = False) -> Power:
    """renderHero в ui/app.js. Нет ответа панели — нажимать нечего."""
    if state is None:
        return Power("Нет связи с панелью", "Окно ждёт ответа демона XGW", "bad", False, False)
    capture = _dict(state.get("capture"))
    allowed = _dict(state.get("power"))
    mode = capture.get("mode")
    tone = health(state, stale)[0]
    title, sub, hero = "VPN выключен", "Трафик идёт напрямую, мимо VPN", "off"
    if mode == "on":
        title, sub, hero = "VPN включён", scope_text(capture), ("bad" if tone == "bad" else "ok")
        if capture.get("inbound_missing"):
            title, hero = "VPN включается", "warn"
            sub = ("Xray перезапускается с новыми настройками — до этого интернет закрыт, мимо "
                   "VPN ничего не уходит" if capture.get("blocked") else
                   "Xray перезапускается с новыми настройками — до этого трафик идёт напрямую")
        elif capture.get("lan_problem"):
            hero, sub = "bad", f"Устройства сети без интернета: {capture['lan_problem']}"
        elif pool_house(state) and (pool_flow(state) or {}).get("closed"):
            sub = ("Бесплатных серверов нет — зарубежные сайты закрыты, российские открываются "
                   "напрямую")
        elif pool_house(state) and tone != "bad":
            sub = scope_text(capture).replace("через VPN", "через бесплатные серверы")
        elif tone == "bad":
            sub = f"VPN включён, но сейчас не работает: {state.get('action') or 'нет связи'}"
        elif capture.get("loaded") is False:
            hero, sub = "bad", "Правила сети не загружены — демон загрузит их заново"
    elif mode == "open":
        title, sub, hero = ("VPN временно снят",
                            "Xray недоступен — трафик идёт напрямую, пока он не вернётся", "warn")
    elif mode == "none":
        title = "Перехват не настроен"
        sub = "XGW только управляет Xray: в config.toml перехват выключен"
    pressed = mode in ("on", "open")
    enabled = not acting and not stale and bool(
        allowed.get("can_off") if pressed else allowed.get("can_on"))
    why = "" if pressed or allowed.get("can_on") else str(allowed.get("why") or "")
    return Power(title, sub, hero, pressed, enabled, capital(why))


def lifecycle(state: dict | None, stale: bool) -> tuple[str, str] | None:
    """(тон, строка «Перехват: …») или None — строки нет (демона нет или данные устарели)."""
    if state is None or stale:
        return None
    capture = _dict(state.get("capture"))
    known = LIFECYCLE.get(str(capture.get("lifecycle") or ""))
    if known is None:
        return None
    tone, word, tail = known
    reason = str(capture.get("lifecycle_reason") or "")
    text = f"Перехват: {word} — {reason or tail}"
    if reason and capture.get("lifecycle") == "blocked":
        text += f"; {tail}"
    return tone, text


@dataclass(frozen=True)
class MainServer:
    """Сервер, через который идёт трафик: основной (speed.sticky) или выбранный вручную."""

    name: str
    tag: str
    country: str
    pinned: bool
    core: str = ""
    profile: str = ""
    speed_mbps: float | None = None  # последний замер скорости
    rtt_ms: float | None = None  # время установления соединения (собственная проба шлюза)
    delay_ms: float | None = None  # полная проба ядра: запрос через сервер и ответ целиком
    basis: str = ""  # speed — выбран по замеру, иначе по задержке


def country_of(tag: str) -> str:
    """Страна по тегу сервера (proxy-nl-a1a1 → NL), как tray_state в панели."""
    parts = tag.split("-")
    return parts[1].upper() if len(parts) > 2 else ""


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def main_server(state: dict | None) -> MainServer | None:
    """Основной сервер или закреплённый вручную, со строкой из списка серверов."""
    if not state:
        return None
    rows = {str(row.get("tag") or ""): row for row in _list(state.get("servers"))
            if isinstance(row, dict)}
    pin = _dict(state.get("pin"))
    main = _dict(state.get("main"))
    tag, pinned = "", False
    if pin.get("tag") and not pin.get("down"):
        tag, pinned = str(pin["tag"]), True
    elif main.get("tag"):
        tag = str(main["tag"])
    if not tag:
        return None
    row = rows.get(tag) or {}
    name = str(row.get("name") or pin.get("name") or main.get("name") or tag)
    speed = _number(row.get("speed_mbps"))
    return MainServer(
        name=name, tag=tag, country=country_of(tag), pinned=pinned,
        core=str(row.get("core") or ""), profile=str(row.get("profile") or ""),
        speed_mbps=speed if speed is not None else _number(main.get("mbps")),
        rtt_ms=_number(row.get("rtt_ms")), delay_ms=_number(row.get("delay_ms")),
        basis=str(main.get("basis") or ""),
    )


def versions(state: dict | None) -> list[tuple[str, str]]:
    """(что, версия): XGW, Xray, sing-box — пустая версия: «нет»."""
    if not state:
        return []
    singbox = _dict(state.get("singbox"))
    box = str(singbox.get("version") or "")
    if not box and singbox.get("installed") is False:
        box = "не установлен"
    return [
        ("XGW", str(state.get("version") or "")),
        ("Xray", str(_dict(state.get("xray")).get("version") or "")),
        ("sing-box", box),
    ]


# --- форматы ----------------------------------------------------------------------------------


def capital(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _decimal(value: float, digits: int) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


def mbps_text(value: float | None) -> str:
    if value is None:
        return "—"
    if value >= 100:
        return f"{round(value)} Мбит/с"
    return f"{_decimal(value, 1)} Мбит/с"


def ms_text(value: float | None) -> str:
    return "—" if value is None else f"{round(value)} мс"


def bytes_text(value: float | None) -> str:
    """Байты — в КБ, МБ, ГБ (по 1024), с запятой: «1,5 ГБ»."""
    if value is None:
        return "—"
    size = float(value)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if abs(size) < 1024 or unit == "ГБ":
            return f"{round(size)} {unit}" if unit == "Б" else f"{_decimal(size, 1)} {unit}"
        size /= 1024
    return f"{_decimal(size, 1)} ТБ"


def ago_text(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = max(0.0, seconds)
    if seconds < 10:
        return "только что"
    if seconds < 60:
        return f"{int(seconds)} с назад"
    if seconds < 3600:
        return f"{int(seconds // 60)} мин назад"
    if seconds < 86400:
        return f"{int(seconds // 3600)} ч назад"
    return f"{int(seconds // 86400)} дн назад"


# --- опрос и действия --------------------------------------------------------------------------


class Backoff:
    """Паузы после сбоев связи: растут вдвое до BACKOFF_MAX, со случайным сдвигом ±JITTER,
    чтобы окно не било в демон ровными залпами."""

    def __init__(self, rng: Callable[[], float] = random.random) -> None:
        self.rng, self.failures = rng, 0

    def fail(self) -> float:
        base = min(BACKOFF_MAX, BACKOFF_START * (2 ** self.failures))
        self.failures += 1
        return base * (1 - JITTER + 2 * JITTER * self.rng())

    def reset(self) -> None:
        self.failures = 0


class PollGate:
    """Один запрос за раз и только свежие ответы: begin выдаёт номер запроса (None — прежний
    ещё идёт), finish — True, если ответ этого номера ещё новее применённого."""

    def __init__(self) -> None:
        self.issued = self.applied = 0
        self.busy = False

    def begin(self) -> int | None:
        if self.busy:
            return None
        self.busy = True
        self.issued += 1
        return self.issued

    def finish(self, number: int) -> bool:
        if number == self.issued:
            self.busy = False
        if number <= self.applied:
            return False
        self.applied = number
        return True

    def drop(self) -> None:
        """Ответа ждать не надо (сеанс сменился): следующий begin даст новый номер, а ответ
        прежнего запроса — уже не новее применённого."""
        self.busy = False
        self.applied = self.issued


class ActionGuard:
    """Действие с тем же ключом не уходит второй раз, пока панель не ответила на первое."""

    def __init__(self) -> None:
        self.running: set[str] = set()

    def begin(self, key: str) -> bool:
        if key in self.running:
            return False
        self.running.add(key)
        return True

    def end(self, key: str) -> None:
        self.running.discard(key)

    def busy(self, key: str) -> bool:
        return key in self.running


HTTP_TEXTS = {
    401: "Нужен вход: нажмите «Войти» — Ubuntu спросит пароль администратора",
    403: "Панель отклонила запрос",
    404: "Панель не знает такого действия — версия XGW старше окна?",
    413: "Запрос слишком большой",
    429: "Панель занята — повторите позже",
    500: "Ошибка панели XGW",
}


def error_text(code: int | None, body: str = "", network: str = "") -> str:
    """Почему запрос не удался — для человека и без секретов (ответ панели и ошибка сети
    маскируются, как в журнале XGW)."""
    detail = masking.mask_text((body or network or "").strip())[:300]
    if code is None or code == 0:
        return f"Нет связи с панелью XGW{': ' + detail if detail else ''}"
    base = HTTP_TEXTS.get(code) or (f"Ошибка панели XGW ({code})" if code >= 500
                                    else f"Панель ответила {code}")
    return f"{base}: {detail}" if detail and code != 401 else base


def parse_json(data: bytes) -> dict | None:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


# --- вход и сеанс -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Session:
    """Вход в панель: её порт на 127.0.0.1 и cookie (та же, что браузер получает по ссылке
    входа). Токен панели cookie не раскрывает: это HMAC от него."""

    port: int
    cookie: str

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def session_file(home: Path | None = None, environ: dict | None = None) -> Path:
    environ = os.environ if environ is None else environ
    override = environ.get(SESSION_ENV)
    if override:
        return Path(override)
    return (home or Path.home()) / SESSION_FILE


def _valid_port(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535


def _valid_cookie(value: object) -> bool:
    return isinstance(value, str) and 16 <= len(value) <= 128 and value.isalnum()


def load_session(path: Path) -> Session | None:
    """Сохранённый вход; None — его нет или файл испорчен (тогда просто войти заново)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    port, cookie = data.get("port"), data.get("cookie")
    if not _valid_port(port) or not _valid_cookie(cookie):
        return None
    return Session(port, cookie)


def save_session(path: Path, session: Session) -> None:
    """Файл сеанса — только человеку (0600), записью целиком: прервавшаяся запись не
    оставит половину cookie."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(path.parent, 0o700)
    fd, temp = tempfile.mkstemp(prefix=".gui-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump({"port": session.port, "cookie": session.cookie}, handle)
            handle.write("\n")
        os.replace(temp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp)
        raise


def clear_session(path: Path) -> None:
    with contextlib.suppress(FileNotFoundError):
        path.unlink()


def parse_login(output: str) -> tuple[int, str] | None:
    """Ответ `xgw panel --gui-login`: одна строка JSON {"port", "code"}; None — не он."""
    for line in reversed(output.strip().splitlines()):
        data = parse_json(line.encode("utf-8"))
        if data is None:
            continue
        port, code = data.get("port"), data.get("code")
        if _valid_port(port) and isinstance(code, str) and 16 <= len(code) <= 64 and all(
                ch.isalnum() or ch in "-_" for ch in code):
            return port, code
    return None


def cookie_from(headers: list[bytes]) -> str:
    """Значение cookie панели из заголовков Set-Cookie ответа на ссылку входа."""
    for raw in headers:
        # Qt склеивает несколько Set-Cookie одного ответа через перевод строки.
        for text in raw.decode("latin-1").splitlines():
            first = text.split(";", 1)[0].strip()
            name, sep, value = first.partition("=")
            if sep and name.strip() == COOKIE and _valid_cookie(value.strip()):
                return value.strip()
    return ""
