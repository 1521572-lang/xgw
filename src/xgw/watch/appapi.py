"""API приложения XGW для Android: http://127.0.0.1:8782/, наружу — через Tailscale Funnel
(https://<шлюз>.<tailnet>.ts.net/, порт 443). А1 `ANDROID_APP_PLAN.md`.

    GET  /api/hello          без входа: «XGW» — проверка, что Funnel доходит до шлюза
    POST /api/pair           код из QR панели → id телефона и ключ (phones.py)
    GET  /api/state          подписано: состояние шлюза для экрана «Шлюз»
    POST /api/act            подписано: действие из белого списка (то же, что кнопки панели)
    GET  /api/phone-config   подписано: конфиг Xray для VPN телефона (generator/phone.py)

Защита:
  * слушает только 127.0.0.1; Host должен быть именем шлюза в Funnel — и только пока
    Funnel включён из панели (флаг tailscale.funnel в panel.json), иначе 421;
  * всё, кроме hello и pair, — с подписью HMAC-SHA256 ключом телефона (время ±60 с,
    случайное число один раз); неудачи — общий ответ, пауза 0,5 с, не больше FAILS_MAX в
    минуту на весь шлюз (дальше 429 на минуту);
  * не больше RATE запросов в минуту с телефона; тело запроса — до MAX_BODY, только JSON;
  * действия — белый список ACTIONS: подписки, ссылки, удаление серверов,
    установка, логи и настройки Tailscale через приложение недоступны;
  * адреса подписок и ссылки серверов в ответах не бывают; серверы с ключами уходят только в
    /api/phone-config — привязанному телефону, которому они и нужны для VPN.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import __version__, engine, log, masking
from ..generator import phone as phoning
from ..phones import Phone, PhoneError, Phones

MAX_BODY = 8192
RATE = 30  # запросов в минуту с одного телефона
FAILS_MAX = 10  # неудачных входов в минуту на весь шлюз
LOCKOUT = 60.0
FAIL_PAUSE = 0.5
SHUTDOWN_POLL = 0.1
ACTIONS = ("power", "pin", "unpin", "refresh", "scan", "speed", "device")
_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    log = None

    def handle_error(self, request, client_address) -> None:
        if self.log is not None:
            self.log.exception("API приложения: запрос не обработан")


class _Reply(Exception):
    def __init__(self, code: HTTPStatus, payload: dict) -> None:
        super().__init__(code)
        self.code = code
        self.payload = payload


def phone_state(state: dict) -> dict:
    """Что из состояния панели (уже маскированного) нужно экрану «Шлюз» приложения."""
    members = [
        {key: member.get(key) for key in (
            "tag", "name", "alive", "delay_ms", "speed_mbps", "main", "selected", "profile")}
        for member in state.get("members") or []
    ]
    devices = [
        {key: device.get(key) for key in ("mac", "ip", "name", "bypass", "managed", "offline")}
        for device in state.get("devices") or []
    ]
    capture = state.get("capture") or {}
    return {
        "version": state.get("version"), "now": state.get("now"), "state": state.get("state"),
        "action": state.get("action"), "xray": state.get("xray"),
        "capture": {key: capture.get(key) for key in ("mode", "lifecycle", "lifecycle_reason")},
        "power": state.get("power"), "main": state.get("main"), "pin": state.get("pin"),
        "members": members, "spares": len(state.get("spares") or []),
        "sticky": {"on": (state.get("sticky") or {}).get("on")},
        "devices": devices, "busy": state.get("busy"),
    }


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
        self._lock = threading.Lock()
        self._server: _Server | None = None
        self._thread: threading.Thread | None = None

    # --- запуск ------------------------------------------------------------------

    def start(self) -> None:
        api = self

        class Handler(BaseHTTPRequestHandler):
            timeout = 15
            server_version = "xgw"
            sys_version = ""

            def log_message(self, *_args) -> None:
                """Запросы не журналируются."""

            def do_GET(self) -> None:
                api.handle(self, "GET")

            def do_POST(self) -> None:
                api.handle(self, "POST")

        self._server = _Server(("127.0.0.1", self.port), Handler)
        self._server.log = self.log
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
        try:
            self._route(handler, method)
        except _Reply as reply:
            self._send(handler, reply.code, reply.payload)

    def _route(self, handler: BaseHTTPRequestHandler, method: str) -> None:
        host = (handler.headers.get("Host") or "").strip().lower()
        body = self._read_body(handler)
        if host not in self.hosts():
            raise _Reply(HTTPStatus.MISDIRECTED_REQUEST, {"error": "не тот адрес"})
        path = handler.path.split("?", 1)[0]
        if method == "GET" and path == "/api/hello":
            raise _Reply(HTTPStatus.OK, {"app": "XGW"})
        if self._locked():
            raise _Reply(HTTPStatus.TOO_MANY_REQUESTS, {"error": "слишком много неудач, подождите"})
        if method == "POST" and path == "/api/pair":
            self._pair(body)
        try:
            phone = self.phones.verify(handler.headers, method, handler.path, body)
        except PhoneError as exc:
            self._fail(f"запрос отклонён: {exc}")
        if not self._rate_ok(phone.id):
            raise _Reply(HTTPStatus.TOO_MANY_REQUESTS, {"error": "слишком часто"})
        if method == "GET" and path == "/api/state":
            raise _Reply(HTTPStatus.OK, phone_state(self.panel.state()))
        if method == "GET" and path == "/api/phone-config":
            self._phone_config()
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
                                  "вход закрыт на минуту")
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
        name = payload.pop("name", None)
        if name not in ACTIONS:
            raise _Reply(HTTPStatus.FORBIDDEN, {"error": "это действие в приложении недоступно"})
        result = self.panel.act(name, payload)
        if result.get("ok"):
            self.panel._event(f"с телефона «{phone.name}»: {masking.mask_text(result['text'])}")
        raise _Reply(HTTPStatus.OK, result)

    @staticmethod
    def _send(handler, code: HTTPStatus, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response(code)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(data)))
        for name, value in _HEADERS.items():
            handler.send_header(name, value)
        handler.end_headers()
        handler.wfile.write(data)
