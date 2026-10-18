"""Бот Telegram: команды. Уведомления шлёт notify.py, здесь шлюз отвечает на вопросы
и выполняет те же действия, что кнопки панели и команды терминала.

Как это работает
  * Бот сам опрашивает Telegram (getUpdates, long polling): входящих соединений нет,
    порт наружу не открывается, адрес шлюза Telegram не нужен.
  * Запросы идут через http-in Xray, а если он не отвечает — напрямую сокетом с
    меткой мимо перехвата (как уведомления): без VPN Telegram может быть закрыт.
  * Слушаются только сообщения из чата notify.telegram_chat_id. Сообщения из других
    чатов не обрабатываются и ответа не получают. Читать состояние можно из любого
    такого чата, а управлять (/enable, /disable, /pin…) — только из личной
    переписки с ботом: в группе команду мог бы отправить любой её участник.
  * Команда старше двух минут не выполняется: Telegram хранит неполученные сообщения
    сутки, и «/disable» трёхчасовой давности не должен сработать после перезагрузки.
  * Чат подключается из панели: пользователь вставляет токен, панель показывает
    одноразовый код, и бот запоминает чат, из которого пришло «/start КОД».
"""

from __future__ import annotations

import hmac
import json
import secrets
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlencode

from .. import actions, cost, engine, fetch, log, managed, masking
from ..config import Config
from ..generator import profiles as profiling
from ..net import dnsmasq
from ..net.capture import Capture
from ..paths import Paths
from . import status

LONG_POLL = 25  # сколько секунд Telegram держит запрос, если сообщений нет
REQUEST_SLACK = 10.0  # запас на сеть сверх времени опроса
MAX_AGE = 120.0  # команды старше не выполняются
PAIR_TTL = 900.0
PAIR_TRIES = 5
BACKOFF = (5.0, 10.0, 20.0, 40.0, 60.0)
MAX_TEXT = 3900  # лимит Telegram — 4096 знаков
MAX_STRANGERS = 100
DEFAULT_PIN = "1h"
CONTROL = ("/enable", "/disable", "/pin", "/unpin", "/refresh", "/scan", "/speed")
READ_ONLY = ("/status", "/servers", "/devices")

HELP = """XGW — шлюз с VPN. Команды:
/status — состояние: VPN, основной сервер, квота
/servers — серверы по номерам
/devices — устройства в Wi-Fi
/enable — включить VPN
/disable — выключить VPN (интернет напрямую)
/pin НОМЕР [СРОК] — выбрать сервер вручную (СРОК: 10m, 1h, 6h, 24h; по умолчанию 1h)
/unpin — вернуть автовыбор
/refresh — обновить подписки
/scan — проверить запасные серверы
/speed — замерить скорость серверов в работе
Управление работает только в личной переписке с ботом."""

PRIVATE_ONLY = "Управлять шлюзом можно только из личной переписки с ботом, не из группы."


class TelegramError(Exception):
    """Telegram не принял запрос или ответил не так, как описано в Bot API."""


def parse_command(text: str, username: str = "") -> tuple[str, str] | None:
    """«/pin@xgw_bot 2 1h» → ("/pin", "2 1h"); None — это не команда или она адресована
    другому боту."""
    text = text.strip()
    if not text.startswith("/"):
        return None
    head, _, rest = text.partition(" ")
    name, _, addressee = head.partition("@")
    if addressee and username and addressee.lower() != username.lower():
        return None
    return name.lower()[:32], rest.strip()[:100]


def _core_note(entry: dict) -> str:
    """Протокол, ядро и профиль обхода сервера: « [vless, sb+frag]»."""
    profile = entry.get("profile")
    if not profile:
        return ""
    protocol = entry.get("protocol")
    return f" [{protocol + ', ' if protocol else ''}{profiling.label(profile)}]"


class Bot:
    def __init__(
        self,
        paths: Paths,
        config_path: Path,
        *,
        logger=None,
        post=fetch.fetch_url,
        root_problem: Callable[[], str | None] = actions.root_problem,
        capture_factory: Callable[..., Capture] = Capture,
        clock: Callable[[], float] = time.time,
        long_poll: int = LONG_POLL,
    ) -> None:
        self.paths = paths
        self.config_path = Path(config_path)
        self.log = logger or log.get_logger("telegram")
        self.post = post
        self.root_problem = root_problem
        self.capture_factory = capture_factory
        self.clock = clock
        self.long_poll = long_poll
        self.cfg = Config()
        self.daemon = None
        self.mark: int | None = None
        self.username = ""
        self.error = ""
        self._offset = 0
        self._pair: dict | None = None  # {"code", "until", "fails", "token"}
        # Чат уже подключён, а настройки с ним ещё не перечитаны: (токен, чат).
        self._paired: tuple[str, str] | None = None
        self._strangers: set[int] = set()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # --- настройки и состояние для панели ------------------------------------------

    def configure(self, cfg: Config, daemon=None, mark: int | None = None) -> None:
        """Новые настройки после перечитывания конфига.

        Перечитывание, начатое до сохранения токена, может прийти позже панели и
        принести настройки без него: поэтому код подключения привязан к токену, а не
        сбрасывается при его смене, и подключённый чат запоминается отдельно.
        """
        with self._lock:
            before = self.cfg.notify.telegram_bot_token
            token = cfg.notify.telegram_bot_token
            if self._paired is not None and token == self._paired[0]:
                if cfg.notify.telegram_chat_id:
                    self._paired = None  # настройки догнали: чат записан
                else:
                    cfg.notify.telegram_chat_id = self._paired[1]
            self.cfg, self.daemon, self.mark = cfg, daemon, mark
            if token != before:
                # Другой бот: его имя и очередь сообщений — не прежние.
                self.username, self.error, self._offset = "", "", 0
        self._wake.set()

    def info(self) -> dict:
        """Что показать в панели. Токен и чат наружу не отдаются."""
        with self._lock:
            cfg, pair = self.cfg, self._pair
            token, chat = cfg.notify.telegram_bot_token, cfg.notify.telegram_chat_id
            if not token:
                mode = "off"
            elif chat:
                mode = "connected" if cfg.notify.commands else "notify"
            else:
                mode = "pairing" if cfg.managed.telegram else "no_chat"
            live = pair is not None and pair["until"] > self.clock() and pair["token"] == token
            return {
                "mode": mode, "managed": cfg.managed.telegram, "username": self.username,
                "error": self.error, "code": pair["code"] if live and pair else "",
                "until": pair["until"] if live and pair else None,
                "commands": cfg.notify.commands,
            }

    def new_code(self, token: str = "") -> str:
        """Одноразовый код подключения чата для этого токена: 15 минут и пять попыток."""
        code = f"{secrets.randbelow(10**6):06d}"
        with self._lock:
            token = token or self.cfg.notify.telegram_bot_token
            self._pair = {
                "code": code, "until": self.clock() + PAIR_TTL, "fails": 0, "token": token,
            }
        self._wake.set()
        return code

    def drop_code(self) -> None:
        with self._lock:
            self._pair = None

    def forget(self) -> None:
        """Бот отключён в панели: код и запомненный чат больше не нужны."""
        with self._lock:
            self._pair = self._paired = None

    # --- поток --------------------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="xgw-telegram", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=2)  # опрос в пути не ждём: поток фоновый
            self._thread = None

    def _active(self, cfg: Config) -> bool:
        """Опрашивать Telegram есть смысл, если есть токен и либо команды включены,
        либо чат ещё не подключён (ждём «/start КОД»)."""
        return bool(
            cfg.notify.telegram_bot_token
            and (cfg.notify.commands or not cfg.notify.telegram_chat_id)
        )

    def _run(self) -> None:
        failures = 0
        while not self._stop.is_set():
            with self._lock:
                cfg = self.cfg
            if not self._active(cfg):
                self._wake.wait(2.0)
                self._wake.clear()
                failures = 0
                continue
            try:
                self.poll_once(cfg)
                failures = 0
                self._set_error("")
            except (TelegramError, fetch.FetchError, OSError, ValueError) as exc:
                failures += 1
                self._set_error(str(exc))
                self._wake.wait(BACKOFF[min(failures, len(BACKOFF)) - 1])
                self._wake.clear()
            except Exception:  # сбой в обработке команды не должен убить бота
                self.log.exception("бот Telegram: непредвиденная ошибка")
                failures += 1
                self._wake.wait(BACKOFF[min(failures, len(BACKOFF)) - 1])
                self._wake.clear()

    def _set_error(self, text: str) -> None:
        text = masking.mask_text(text)[:300]
        if text and text != self.error:
            self.log.error("бот Telegram: %s", text)
        elif not text and self.error:
            self.log.info("бот Telegram: связь восстановлена")
        self.error = text

    # --- обмен с Telegram ---------------------------------------------------------

    def poll_once(self, cfg: Config) -> None:
        """Один круг: узнать имя бота (первый раз), получить сообщения, обработать."""
        token = cfg.notify.telegram_bot_token
        if not self.username:
            me = self._call(cfg, "getMe", {}, timeout=15.0)
            username = me.get("username") if isinstance(me, dict) else None
            if not isinstance(username, str) or not username:
                raise TelegramError("Telegram не назвал имя бота")
            self.username = username
        updates = self._call(
            cfg, "getUpdates",
            {"offset": self._offset, "timeout": self.long_poll,
             "allowed_updates": json.dumps(["message"])},
            timeout=self.long_poll + REQUEST_SLACK,
        )
        if not isinstance(updates, list):
            raise TelegramError("Telegram вернул не список сообщений")
        for update in updates:
            # Настройки могли перечитаться, пока шёл опрос (до 25 с): сообщения
            # разбираются по свежим, иначе чат, подключённый в этом же опросе, пропал бы.
            with self._lock:
                cfg = self.cfg
            if token != cfg.notify.telegram_bot_token:
                return  # пока шёл опрос, бота сменили — эти сообщения чужого бота
            if isinstance(update, dict):
                self._handle(cfg, update)

    def _routes(self, cfg: Config) -> list[dict]:
        routes: list[dict] = []
        proxy = engine.healthy_http_in(cfg)
        if proxy is not None:
            routes.append({"proxy": proxy})
        routes.append({
            "mark": self.mark, "bootstrap": cfg.dns.bootstrap if self.mark is not None else None,
        })
        return routes

    def _call(self, cfg: Config, method: str, params: dict, *, timeout: float):
        """Метод Bot API → поле result. Сначала через Xray, затем напрямую."""
        url = f"{cfg.notify.telegram_api}/bot{cfg.notify.telegram_bot_token}/{method}"
        data = urlencode(params).encode("ascii")
        error: Exception | None = None
        for route in self._routes(cfg):
            try:
                reply = self.post(
                    url, data=data, timeout=timeout, retries=0,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}, **route,
                )
            except fetch.FetchError as exc:
                error = exc
                continue
            try:
                body = json.loads(reply.body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                error = TelegramError(f"Telegram ответил HTTP {reply.status} не по Bot API")
                continue
            if isinstance(body, dict) and body.get("ok") is True:
                return body.get("result")
            description = body.get("description") if isinstance(body, dict) else None
            if reply.status == 401:
                raise TelegramError("Telegram не принял токен бота — проверьте его у @BotFather")
            raise TelegramError(f"Telegram: {description or f'HTTP {reply.status}'}")
        raise error or TelegramError("Telegram недоступен")

    def _send(self, cfg: Config, chat_id: int, text: str) -> None:
        text = masking.mask_text(text)
        chunks = [text[i : i + MAX_TEXT] for i in range(0, len(text), MAX_TEXT)] or [""]
        for chunk in chunks:
            self._call(
                cfg, "sendMessage",
                {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": "true"},
                timeout=15.0,
            )

    # --- сообщения ----------------------------------------------------------------

    def _handle(self, cfg: Config, update: dict) -> None:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            self._offset = max(self._offset, update_id + 1)
        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat, text = message.get("chat"), message.get("text")
        if not isinstance(chat, dict) or not isinstance(text, str):
            return
        chat_id = chat.get("id")
        sent = message.get("date")
        if not isinstance(chat_id, int) or isinstance(chat_id, bool):
            return
        if not isinstance(sent, (int, float)) or self.clock() - sent > MAX_AGE:
            return  # старая команда: после перезагрузки или обрыва её не выполняем
        parsed = parse_command(text, self.username)
        if parsed is None:
            return
        name, argument = parsed
        private = chat.get("type") == "private"
        owner = cfg.notify.telegram_chat_id.strip()
        if not owner:
            if name == "/start":
                self._pair_chat(cfg, chat_id, private, argument)
            return
        if str(chat_id) != owner:
            self._stranger(chat_id)
            return
        if not cfg.notify.commands:
            return
        try:
            reply = self._command(cfg, name, argument, private)
        except Exception:
            self.log.exception("бот Telegram: команда %s не выполнена", name)
            reply = "Не получилось: внутренняя ошибка шлюза, подробности — в журнале XGW."
        self._send(cfg, chat_id, reply)

    def _stranger(self, chat_id: int) -> None:
        if chat_id not in self._strangers and len(self._strangers) < MAX_STRANGERS:
            self._strangers.add(chat_id)
            self.log.warning(
                "бот Telegram: сообщение из чужого чата %d проигнорировано (ответа нет)", chat_id
            )

    # --- подключение чата ----------------------------------------------------------

    def _pair_chat(self, cfg: Config, chat_id: int, private: bool, code: str) -> None:
        """«/start КОД» в личной переписке: чат запоминается в panel.json."""
        if not cfg.managed.telegram:
            return  # токен из config.toml: чат вписывают туда же, подключения нет
        if not private:
            self._send(cfg, chat_id, "Подключить шлюз можно только из личной переписки с ботом.")
            return
        with self._lock:
            pair = self._pair
        if pair is None or pair["until"] < self.clock() or (
            pair["token"] != cfg.notify.telegram_bot_token
        ):
            self._send(
                cfg, chat_id,
                "Код не запрашивался или истёк. Откройте панель XGW, раздел «Telegram», "
                "и получите новый код.",
            )
            return
        if not code or not hmac.compare_digest(code.encode("utf-8"), pair["code"].encode("ascii")):
            with self._lock:
                pair["fails"] += 1
                if pair["fails"] >= PAIR_TRIES:
                    self._pair = None  # перебор: этот код больше не годится
            self._send(
                cfg, chat_id,
                "Неверный код. Отправьте /start и шесть цифр из панели XGW." if code
                else "Отправьте /start и шесть цифр из панели XGW, например: /start 123456",
            )
            return
        try:
            managed.set_telegram(
                managed.path_for(self.config_path), cfg.notify.telegram_bot_token, str(chat_id)
            )
        except (managed.ManagedError, OSError) as exc:
            self._send(cfg, chat_id, f"Не получилось сохранить чат: {exc}")
            return
        with self._lock:
            self._pair = None
            self._paired = (cfg.notify.telegram_bot_token, str(chat_id))
            # Сразу, не дожидаясь перечитывания: и в этих настройках, и в текущих.
            cfg.notify.telegram_chat_id = str(chat_id)
            if self.cfg.notify.telegram_bot_token == cfg.notify.telegram_bot_token:
                self.cfg.notify.telegram_chat_id = str(chat_id)
        self._event("Telegram: чат подключён")
        if self.daemon is not None:
            self.daemon.poke.set()
        self._send(cfg, chat_id, "Готово: шлюз подключён к этому чату.\n\n" + HELP)

    # --- команды ------------------------------------------------------------------

    def _command(self, cfg: Config, name: str, argument: str, private: bool) -> str:
        if name in ("/start", "/help"):
            return HELP
        if name == "/status":
            return self._status(cfg)
        if name == "/servers":
            return self._servers(cfg)
        if name == "/devices":
            return self._devices(cfg)
        if name not in CONTROL:
            return "Не знаю такой команды. Список: /help"
        if not private:
            return PRIVATE_ONLY
        problem = self.root_problem()
        if problem:
            return f"Не получилось: {problem}"
        self._event(f"Telegram: команда {name}" + (f" {argument}" if argument else ""))
        return self._control(cfg, name, argument)

    def _snapshot(self, cfg: Config) -> dict | None:
        return status.read_status(self.paths, max(3.0 * cfg.watchdog.interval_s, 180.0))

    def _status(self, cfg: Config) -> str:
        snap = self._snapshot(cfg)
        if snap is None:
            return "Демон XGW не отвечает: состояние неизвестно. Проверьте службу xgw на шлюзе."
        lines = [f"Состояние: {snap.get('state') or 'нет данных'}"
                 + (f" — {snap['action']}" if snap.get("action") else "")]
        lines.append(status.render_xray(snap.get("xray") or {}))
        if snap.get("capture"):
            lines.append(status.render_capture(snap["capture"]))
        members = snap.get("members") or []
        selected = set(snap.get("selecting") or [])
        alive = sum(1 for member in members if member.get("alive"))
        lines.append(f"Серверов в работе: {alive} из {len(members)}; запасных: "
                     f"{len(snap.get('spares') or [])}")
        for member in members:
            if member["tag"] in selected or (member.get("main") and not snap.get("pin")):
                delay = member.get("delay_ms")
                details = [status.speed_text(float(member["speed_mbps"]))] if (
                    member.get("speed_mbps") is not None
                ) else []
                if delay is not None:
                    details.append(f"{delay} мс")
                head = "Основной" if member.get("main") and not snap.get("pin") else "Выбран"
                lines.append(f"{head}: {member.get('name') or member['tag']}"
                             + (f" ({', '.join(details)})" if details else "")
                             + _core_note(member))
                break
        pin = snap.get("pin")
        if pin:
            name = pin.get("name") or pin["tag"]
            lines.append(
                f"Выбран вручную: {name} — не отвечает, сейчас автовыбор" if pin.get("down")
                else f"Выбран вручную: {name}; вернуть автовыбор — /unpin"
            )
        reserve = snap.get("reserve")
        if reserve:
            price = cost.describe(float(reserve.get("cost") or 0.0))
            lines.append(f"Резервный: {reserve.get('name') or reserve['tag']} ({price})"
                         + (" — сейчас трафик идёт через него" if snap.get("state") == "RESERVE"
                            else ""))
        for name, quota in (snap.get("quota") or {}).items():
            used = quota.get("upload", 0) + quota.get("download", 0)
            text = f"Квота «{name}»: {used / 1e9:.1f} ГБ"
            if quota.get("total"):
                text += f" из {quota['total'] / 1e9:.1f} ГБ"
            else:
                text += ", безлимитная"
            lines.append(text)
        return "\n".join(lines)

    def _members(self, cfg: Config) -> list[dict]:
        snap = self._snapshot(cfg)
        return list((snap or {}).get("members") or [])

    def _servers(self, cfg: Config) -> str:
        snap = self._snapshot(cfg)
        if snap is None:
            return "Демон XGW не отвечает: список серверов неизвестен."
        selected = set(snap.get("selecting") or [])
        lines = ["Участники балансировщика (номер — для /pin):"]
        for number, member in enumerate(snap.get("members") or [], 1):
            if member.get("alive") is None:
                health = "нет данных"
            elif member["alive"]:
                health = "жив" + (f", {member['delay_ms']} мс" if member.get("delay_ms") else "")
            else:
                health = "НЕ ОТВЕЧАЕТ"
            if member.get("speed_mbps") is not None:
                health += f", {status.speed_text(float(member['speed_mbps']))}"
            mark = " ← выбран" if member["tag"] in selected else ""
            if member.get("main") and not snap.get("pin"):
                mark = " ← основной"
            lines.append(
                f"{number}. {member.get('name') or member['tag']} — {health}{mark}"
                f"{_core_note(member)}"
            )
        spares = snap.get("spares") or []
        if spares:
            on_singbox = sum(1 for spare in spares if spare.get("core") == "sing-box")
            lines.append(
                f"Запасных: {len(spares)} (подменят участника, если он откажет)"
                + (f"; из них через sing-box: {on_singbox}" if on_singbox else "")
            )
        return "\n".join(lines)

    def _devices(self, cfg: Config) -> str:
        snap = self._snapshot(cfg)
        capture = (snap or {}).get("capture") or {}
        if not cfg.network.lan_if:
            return "Сеть для устройств не настроена: шлюз работает только для этой машины."
        bypass = set(capture.get("bypass") or [])
        devices = dnsmasq.read_leases(self.paths)
        if not devices:
            return "Устройств пока нет: адреса выдаются, когда устройство подключается к Wi-Fi."
        lines = [f"Устройства в сети ({len(devices)}):"]
        for device in devices:
            where = "мимо VPN" if device["ip"] in bypass else "через VPN"
            lines.append(f"{device['ip']} — {device['name'] or 'без имени'} — {where}")
        return "\n".join(lines)

    def _control(self, cfg: Config, name: str, argument: str) -> str:
        paths = self.paths
        if name in ("/enable", "/disable"):
            capture = self.capture_factory(cfg, paths, logger=self.log)
            if name == "/enable":
                return self._outcome(actions.enable_checked(cfg, paths, capture))
            return self._outcome(actions.disable(cfg, paths, capture))
        if name == "/unpin":
            return self._outcome(actions.unpin(cfg, paths))
        if name == "/pin":
            return self._pin(cfg, argument)
        if self.daemon is None:
            return "Демон XGW ещё не готов — повторите через минуту."
        if name == "/refresh":
            if not engine.has_sources(cfg):
                return "Обновлять нечего: подписок нет."
            self.daemon.request_refresh()
            return "Обновляю подписки…"
        if name == "/speed":
            if not cfg.speed.sticky or not cfg.speed.every_hours:
                return ("Замер скорости выключен: основной сервер выключен в панели "
                        "или speed.every_hours = 0.")
            self.daemon.request_speed()
            return "Замеряю скорость серверов в работе — итог в /servers через минуту-другую."
        self.daemon.request_scan()
        return "Проверяю запасные серверы…"

    def _pin(self, cfg: Config, argument: str) -> str:
        parts = argument.split()
        if not parts or len(parts) > 2 or not parts[0].isdigit():
            return "Укажите номер сервера из /servers и, если нужно, срок: /pin 2 6h"
        members = self._members(cfg)
        number = int(parts[0])
        if not 1 <= number <= len(members):
            return f"Сервера с номером {number} нет: в работе их {len(members)} (см. /servers)."
        ttl = parts[1] if len(parts) == 2 else DEFAULT_PIN
        return self._outcome(actions.pin(cfg, self.paths, members[number - 1]["tag"], ttl))

    @staticmethod
    def _outcome(outcome: actions.Outcome) -> str:
        if not outcome.ok:
            return f"Не получилось: {outcome.text}"
        return "\n".join((outcome.text, *outcome.notes))

    def _event(self, text: str) -> None:
        try:
            with actions.open_store(self.paths) as store:
                store.add_event("telegram", text)
        except (OSError, sqlite3.Error) as exc:  # журнал не должен мешать команде
            self.log.error("событие не записано: %s", exc)
