"""API приложения XGW для Android: http://127.0.0.1:8782/, наружу — через Tailscale Funnel
(https://<шлюз>.<tailnet>.ts.net/, порт 443). А1 `ANDROID_APP_PLAN.md`.

    GET  /api/hello          без входа: «XGW» — проверка, что Funnel доходит до шлюза
    POST /api/pair           код из QR панели → id телефона и ключ (phones.py)
    GET  /api/state          подписано: состояние шлюза — то же, что видит панель (phone_state)
    POST /api/act            подписано: действие — то же, что кнопки панели (белый список ACTIONS)
    GET  /api/phone-config   подписано: конфиг Xray для VPN телефона (generator/phone.py)
    GET  /api/records/<имя>  подписано: файл записи трафика устройства (.pcap)

Защита:
  * слушает только 127.0.0.1; Host должен быть именем шлюза в Funnel — и только пока
    Funnel включён из панели (флаг tailscale.funnel в panel.json), иначе 421;
  * всё, кроме hello и pair, — с подписью HMAC-SHA256 ключом телефона (время ±60 с,
    случайное число один раз); неудачи — общий ответ, пауза 0,5 с, не больше FAILS_MAX в
    минуту на весь шлюз (дальше 429 на минуту);
  * не больше RATE запросов в минуту с телефона; тело запроса — до MAX_BODY, только JSON;
  * действия — белый список ACTIONS: всё, чем панель управляет серверами, подписками,
    устройствами и выходом в интернет через шлюз (ASSUMPTIONS п. 232). Недоступны доступ к
    самому шлюзу — вход в Tailscale, SSH, панель по tailnet, Funnel (выключив его, телефон
    отрезал бы себя), правила Tailscale на шлюзе — и привязка телефонов;
  * в состоянии — то же, что видит панель, уже маскированное: подписки — только именем
    сервера, ссылки — подписью, без ключей; серверы с ключами уходят только в
    /api/phone-config — привязанному телефону, которому они и нужны для VPN.
"""

from __future__ import annotations

import base64
import gzip
import json
import threading
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler

from .. import __version__, engine, log
from ..generator import phone as phoning
from ..phones import NonceStoreError, Phone, PhoneBusy, PhoneError, Phones
from . import httpbound
from . import record as recording

MAX_BODY = 65536  # вставленные ссылки серверов — десятки строк по полкилобайта
RATE = 60  # запросов в минуту с одного телефона: опрос раз в 6 с и кнопки
# Неудачных входов в минуту на весь шлюз — после них на минуту закрыты привязка и запросы без
# верной подписи. Запросы привязанных телефонов идут и тогда: подпись HMAC не подобрать, а
# код привязки — 32 случайных символа (192 бита). Иначе десяток чужих запросов
# через Funnel (адрес *.ts.net публичен) раз в минуту закрывал бы вход владельцу (четвёртый
# аудит 0.2.0, ASSUMPTIONS п. 253).
FAILS_MAX = 10
LOCKOUT = 60.0
FAIL_PAUSE = 0.5
# Funnel открыт всему интернету: одновременных соединений — не больше MAX_CONNECTIONS (лишние
# закрываются сразу), а на весь запрос — заголовки и тело — READ_DEADLINE секунд, а не
# Handler.timeout на каждое чтение (медленный отправитель держал бы поток сколько угодно).
MAX_CONNECTIONS = 16
READ_DEADLINE = 20.0
NONCE_FAILED = "шлюз не смог сохранить отметку запроса — повторите позже"
NONCE_WARN_EVERY = 600.0
BUSY = "слишком много неудач, подождите"
# Состояние — как у панели, десятки килобайт раз в 6 с: по мобильной сети — сжатым. Android
# сам просит gzip (Accept-Encoding) и сам распаковывает.
GZIP_FROM = 2048
SHUTDOWN_POLL = 0.1
ACTIONS = (
    "power", "pin", "unpin", "refresh", "scan", "speed", "speed/one", "sticky",
    "add", "servers", "priority", "core", "subscription/edit", "subscription/remove", "link/remove",
    "device", "record/start", "record/stop", "record/remove",
    "tailscale/exit", "tailscale/direct", "tailscale/route",
)
# Из карточки «Tailscale» телефону — выход в интернет через шлюз, устройства tailnet и маршрут.
TAILSCALE_KEYS = ("state", "route", "exit", "peers")
RECORDS = "/api/records/"
_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


class _Done(Exception):
    """Ответ уже отправлен (файл записи)."""


class _Reply(Exception):
    def __init__(self, code: HTTPStatus, payload: dict) -> None:
        super().__init__(code)
        self.code = code
        self.payload = payload


def phone_state(state: dict) -> dict:
    """Состояние для приложения — то же, что у панели (уже маскированное), кроме карточек
    доступа к шлюзу: из «Tailscale» — только TAILSCALE_KEYS, «Телефонов» нет вовсе."""
    result = {key: value for key, value in state.items() if key not in ("tailscale", "phones")}
    card = state.get("tailscale") or {}
    result["tailscale"] = {key: card.get(key) for key in TAILSCALE_KEYS}
    return result


class AppApi:
    def __init__(self, panel, phones: Phones, *, port: int, logger=None,
                 clock=time.monotonic) -> None:
        self.panel = panel
        self.phones = phones
        self.port = port
        self.log = logger or log.get_logger("appapi")
        self.clock = clock
        self._fails: deque[float] = deque()
        self._locked_until = 0.0
        self._rates: dict[str, deque[float]] = {}
        self._nonce_warned = float("-inf")
        self._lock = threading.Lock()
        self._server: httpbound.BoundedServer | None = None
        self._thread: threading.Thread | None = None

    # --- запуск ------------------------------------------------------------------

    def start(self) -> None:
        api = self

        class Handler(httpbound.DeadlineHandler):
            timeout = 15
            # Срок на чтение всего запроса — заголовков и тела (AppApi._route снимает его, когда
            # тело прочитано; ответ им не ограничен — запись трафика по мобильной сети дольше).
            read_deadline = READ_DEADLINE
            server_version = "xgw"
            sys_version = ""

            def log_message(self, *_args) -> None:
                """Запросы не журналируются."""

            def do_GET(self) -> None:
                api.handle(self, "GET")

            def do_POST(self) -> None:
                api.handle(self, "POST")

        self._server = httpbound.BoundedServer(
            ("127.0.0.1", self.port), Handler, slots=MAX_CONNECTIONS, label="API приложения",
            log=self.log,
        )
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="xgw-appapi", daemon=True,
            kwargs={"poll_interval": SHUTDOWN_POLL},
        )
        self._thread.start()
        self.log.info("API приложения слушает 127.0.0.1, порт %d (через Funnel)", self.port)

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    # --- запрос ------------------------------------------------------------------

    def hosts(self) -> set[str]:
        """Funnel приходит на 127.0.0.1 и передаёт Host, с которым открыт адрес."""
        name = self.panel.cfg.managed.tailscale_funnel
        return {name, f"{name}:443"} if name else set()

    def handle(self, handler: BaseHTTPRequestHandler, method: str) -> None:
        if getattr(handler, "cut", False):
            # Срок READ_DEADLINE истёк, соединение уже закрыто: запрос не дочитан, отвечать
            # некому (отчёт 0.2.0-audit4: проба медленного запроса получала ответ 421).
            handler.close_connection = True
            return
        try:
            self._route(handler, method)
        except _Reply as reply:
            self._send(handler, reply.code, reply.payload)
        except _Done:
            pass

    def _route(self, handler: BaseHTTPRequestHandler, method: str) -> None:
        host = (handler.headers.get("Host") or "").strip().lower()
        body = self._read_body(handler)
        httpbound.request_read(handler)
        if host not in self.hosts():
            raise _Reply(HTTPStatus.MISDIRECTED_REQUEST, {"error": "не тот адрес"})
        path = handler.path.split("?", 1)[0]
        if method == "GET" and path == "/api/hello":
            raise _Reply(HTTPStatus.OK, {"app": "XGW"})
        if method == "POST" and path == "/api/pair":
            if self._locked():
                raise _Reply(HTTPStatus.TOO_MANY_REQUESTS, {"error": BUSY})
            self._pair(body)
        try:
            # Предел запросов телефона — до записи отметки: запросы сверх него не пишут её на
            # каждый раз (пятый аудит, A6).
            phone = self.phones.verify(
                handler.headers, method, handler.path, body, admit=self._rate_ok,
            )
        except PhoneBusy as exc:
            raise _Reply(HTTPStatus.TOO_MANY_REQUESTS, {"error": "слишком часто"}) from exc
        except NonceStoreError as exc:
            # Подпись верна, но отметка запроса не записана в /run/xgw: команду, которая меняет
            # состояние, не выполнять — после перезапуска демона её повтор прошёл бы (пятый
            # аудит, A4). Чтение состояния — можно: его повтор ничего не меняет.
            self._nonce_failed(exc)
            if method != "GET":
                raise _Reply(HTTPStatus.SERVICE_UNAVAILABLE, {"error": NONCE_FAILED}) from exc
            phone = exc.phone
        except PhoneError as exc:
            if self._locked():  # без паузы: поток не держится, пока дверь закрыта
                raise _Reply(HTTPStatus.TOO_MANY_REQUESTS, {"error": BUSY}) from exc
            self._fail(f"запрос отклонён: {exc}")
        if method == "GET" and path == "/api/state":
            raise _Reply(HTTPStatus.OK, phone_state(self.panel.state()))
        if method == "GET" and path == "/api/phone-config":
            self._phone_config()
        if method == "GET" and path.startswith(RECORDS):
            self._record_file(handler, path.removeprefix(RECORDS))
        if method == "POST" and path == "/api/act":
            self._act(phone, self._json(body))
        raise _Reply(HTTPStatus.NOT_FOUND, {"error": "нет такого запроса"})

    @staticmethod
    def _read_body(handler: BaseHTTPRequestHandler) -> bytes:
        try:
            length = int(handler.headers.get("Content-Length") or "0")
        except ValueError as exc:
            raise _Reply(HTTPStatus.BAD_REQUEST, {"error": "неверная длина"}) from exc
        if length < 0 or length > MAX_BODY:
            handler.close_connection = True
            raise _Reply(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "запрос слишком большой"})
        return handler.rfile.read(length) if length else b""

    @staticmethod
    def _json(body: bytes) -> dict:
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, UnicodeDecodeError) as exc:
            raise _Reply(HTTPStatus.BAD_REQUEST, {"error": "ожидается JSON"}) from exc
        if not isinstance(payload, dict):
            raise _Reply(HTTPStatus.BAD_REQUEST, {"error": "ожидается объект JSON"})
        return payload

    # --- неудачи и лимиты -----------------------------------------------------------

    def _locked(self) -> bool:
        with self._lock:
            return self.clock() < self._locked_until

    def _nonce_failed(self, exc: NonceStoreError) -> None:
        now = self.clock()
        with self._lock:
            if now - self._nonce_warned < NONCE_WARN_EVERY:
                return  # телефон спрашивает состояние каждые несколько секунд
            self._nonce_warned = now
        self.log.warning("API приложения: отметка запроса телефона не сохранена (%s) — "
                         "команды не выполняются, пока запись не пойдёт", exc)

    def _fail(self, text: str):
        """Неудачный вход: в журнал — причина, телефону — общий ответ после паузы."""
        self.log.warning("API приложения: %s", text)
        with self._lock:
            now = self.clock()
            self._fails.append(now)
            while self._fails and now - self._fails[0] > 60:
                self._fails.popleft()
            if len(self._fails) >= FAILS_MAX:
                self._locked_until = now + LOCKOUT
                self._fails.clear()
                self.panel._event(f"приложение: {FAILS_MAX} неудачных входов за минуту — "
                                  "привязка закрыта на минуту, привязанные телефоны работают")
        time.sleep(FAIL_PAUSE)
        raise _Reply(HTTPStatus.FORBIDDEN, {"error": "не принято"})

    def _rate_ok(self, phone_id: str) -> bool:
        with self._lock:
            now = self.clock()
            window = self._rates.setdefault(phone_id, deque())
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= RATE:
                return False
            window.append(now)
            return True

    # --- ответы -----------------------------------------------------------------

    def _pair(self, body: bytes):
        payload = self._json(body)
        try:
            phone_id, key = self.phones.pair(payload.get("code"), payload.get("name"))
        except PhoneError as exc:
            self._fail(f"привязка не удалась: {exc}")
        name = next((phone.name for phone in self.phones.listing() if phone.id == phone_id), "")
        self.panel._event(f"телефон «{name}» привязан")
        raise _Reply(HTTPStatus.OK, {
            "phone": phone_id, "key": base64.b64encode(key).decode("ascii"), "name": name,
        })

    def _phone_config(self):
        applied = engine.read_json(self.panel.paths.xray_config_file)
        try:
            config = phoning.build(applied)
        except phoning.PhoneConfigError as exc:
            raise _Reply(HTTPStatus.CONFLICT, {"error": str(exc)}) from exc
        raise _Reply(HTTPStatus.OK, {
            "config": config, "servers": phoning.servers(config), "version": __version__,
        })

    def _act(self, phone: Phone, payload: dict):
        """{"name": действие, "body": {поля}} — поля отдельно: у подписки своё поле name.
        Приложение до А3.2 присылало поля рядом с name — так тоже можно."""
        name = payload.pop("name", None)
        if name not in ACTIONS:
            raise _Reply(HTTPStatus.FORBIDDEN, {"error": "это действие в приложении недоступно"})
        body = payload.get("body", payload)
        if not isinstance(body, dict):
            raise _Reply(HTTPStatus.BAD_REQUEST, {"error": "ожидается объект body"})
        # Событие о действии — одно, «с телефона «…»: итог» (его пишет panel.act).
        result = self.panel.act(name, body, origin=f"с телефона «{phone.name}»")
        raise _Reply(HTTPStatus.OK, result)

    def _record_file(self, handler: BaseHTTPRequestHandler, name: str):
        """Запись трафика устройства — как «Скачать» в панели (record.py проверяет имя)."""
        path = self.panel.recorder.path(name)
        if path is None:
            raise _Reply(HTTPStatus.NOT_FOUND, {"error": "такой записи нет"})
        try:
            with recording.download_slot():
                size = path.stat().st_size
                handler.send_response(HTTPStatus.OK)
                handler.send_header("Content-Type", "application/vnd.tcpdump.pcap")
                handler.send_header("Content-Length", str(size))
                for header, value in _HEADERS.items():
                    handler.send_header(header, value)
                handler.end_headers()
                if not recording.send_file(path, size, handler.wfile):
                    handler.close_connection = True
                    self.log.info("API приложения: скачивание записи прервано — дольше %.0f с",
                                  recording.SEND_DEADLINE)
        except recording.Busy as exc:
            raise _Reply(HTTPStatus.TOO_MANY_REQUESTS, {"error": str(exc)}) from exc
        raise _Done

    @staticmethod
    def _send(handler, code: HTTPStatus, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        packed = len(data) >= GZIP_FROM and "gzip" in (handler.headers.get("Accept-Encoding") or "")
        if packed:
            data = gzip.compress(data, compresslevel=6)
        handler.send_response(code)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        if packed:
            handler.send_header("Content-Encoding", "gzip")
            handler.send_header("Vary", "Accept-Encoding")
        handler.send_header("Content-Length", str(len(data)))
        for name, value in _HEADERS.items():
            handler.send_header(name, value)
        handler.end_headers()
        handler.wfile.write(data)
