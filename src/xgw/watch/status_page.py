"""Страница статуса для домашней сети: http://<lan_address>:8780/ (раздел 6.8).

Только чтение и только по токену. Показывает то же, что `xgw status`, и
устройства из аренд dnsmasq. Слушает один адрес — адрес шлюза в LAN; наружу, в
сторону провайдера, страница не видна.

Имена серверов приходят из подписки, имена устройств — от самих устройств: всё,
что попадает в HTML, экранируется.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import hmac
import html
import json
import secrets
import socket
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .. import cost, log
from ..config import Config
from ..generator import profiles as profiling
from ..net import dnsmasq, lan
from ..paths import Paths, atomic_write_text
from . import status
from .panel import SHUTDOWN_POLL

PORT = 8780
COOKIE = "xgw_token"
REFRESH_SECONDS = 20
_IP_FREEBIND = getattr(socket, "IP_FREEBIND", 15)  # Linux: привязка к адресу, которого ещё нет


def token_for(cfg: Config, paths: Paths) -> str:
    """Токен страницы: из config.toml, иначе созданный при установке."""
    if cfg.status.token:
        return cfg.status.token
    with contextlib.suppress(OSError):
        return paths.status_token_file.read_text(encoding="ascii").strip()
    return ""


def ensure_token(cfg: Config, paths: Paths) -> str:
    """Токен; если его нет ни в конфиге, ни в файле — создаётся."""
    token = token_for(cfg, paths)
    if not token:
        token = secrets.token_urlsafe(18)
        atomic_write_text(paths.status_token_file, token + "\n", mode=0o600)
    return token


# --- HTML ----------------------------------------------------------------------

_STYLE = """
body{font:15px/1.45 system-ui,sans-serif;margin:1.2em auto;max-width:60em;padding:0 1em;
color:#1c1c1c;background:#fafafa}
h1{font-size:1.3em}h2{font-size:1.05em;margin:1.4em 0 .4em}
table{border-collapse:collapse;width:100%}
td,th{padding:.3em .6em;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}
th{font-weight:600;color:#555}
.ok{color:#17692c}.bad{color:#b3261e;font-weight:600}.dim{color:#777}
.note{background:#fff3cd;padding:.5em .8em;border-radius:.3em}
"""


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _core(entry: dict) -> str:
    """Протокол, ядро и профиль обхода сервера: «vless · xray», «hysteria2 · sb»."""
    profile = entry.get("profile")
    if not profile:
        return "—"
    protocol = entry.get("protocol")
    return (f"{protocol} · " if protocol else "") + profiling.label(profile)


def _clock(ts: float | None) -> str:
    if not ts:
        return "—"
    return datetime.datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")


def _table(headers: list[str], rows: list[list[str]], empty: str) -> str:
    if not rows:
        return f'<p class="dim">{_esc(empty)}</p>'
    head = "".join(f"<th>{_esc(name)}</th>" for name in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def render_page(snapshot: dict | None, devices: list[dict], *, now: float | None = None) -> str:
    """HTML страницы. Ячейки таблиц — уже экранированный текст."""
    now = time.time() if now is None else now
    parts = [
        "<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\">",
        f"<meta http-equiv=\"refresh\" content=\"{REFRESH_SECONDS}\">",
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
        f"<title>XGW</title><style>{_STYLE}</style></head><body><h1>XGW — шлюз</h1>",
    ]
    if snapshot is None:
        parts.append('<p class="note">Демон XGW ещё не записал статус.</p>')
        snapshot = {}
    state = snapshot.get("state")
    if state:
        css = "ok" if state == "HEALTHY" else "bad"
        since, action = _clock(snapshot.get("since")), snapshot.get("action") or "ничего"
        parts.append(
            f'<p>Состояние: <span class="{css}">{_esc(state)}</span> '
            f"с {_esc(since)} — {_esc(action)}</p>"
        )
    xray = snapshot.get("xray") or {}
    if xray:
        answer = '<span class="ok">отвечает</span>' if xray.get("ok") else (
            '<span class="bad">не отвечает</span>')
        parts.append(f"<p>Xray {_esc(xray.get('version', ''))}: {answer}</p>")
    capture = snapshot.get("capture")
    if capture:
        parts.append(f"<p>{_esc(status.render_capture(capture))}</p>")
    if snapshot.get("probe_target"):
        # Не отвечает сам адрес проверки серверов: «мёртвыми» они только выглядят.
        parts.append(f'<p class="note">{_esc(snapshot["probe_target"])}</p>')
    nodes = status.render_nodes(snapshot.get("nodes") or {})
    if nodes:
        parts.append(f"<p>{_esc(nodes)}</p>")
    if snapshot.get("pin"):
        pin = snapshot["pin"]
        parts.append(
            f'<p class="note">Закреплён вручную: {_esc(pin.get("tag"))} до '
            f'{_esc(_clock(pin.get("until")))} — автопереключение отключено</p>'
        )
    age = now - float(snapshot.get("updated") or 0)
    if snapshot and age > 180:
        parts.append(f'<p class="note">Статус устарел: обновлён {int(age // 60)} мин назад.</p>')

    selecting = set(snapshot.get("selecting") or [])
    members = []
    for member in snapshot.get("members") or []:
        if member.get("alive") is None:
            health = '<span class="dim">нет данных</span>'
        elif member["alive"]:
            health = '<span class="ok">жив</span>'
        else:
            health = '<span class="bad">мёртв</span>'
        delay = member.get("delay_ms")
        members.append([
            _esc(member.get("tag")) + (" ←" if member.get("tag") in selecting else ""),
            _esc(member.get("name")), health,
            _esc(f"{delay} мс" if delay is not None else "—"), _esc(_core(member)),
        ])
    parts.append("<h2>Участники балансировщика</h2>")
    parts.append(_table(["Тег", "Сервер", "Состояние", "Задержка", "Ядро"], members,
                        "нет участников"))

    reserve = snapshot.get("reserve")
    if reserve:
        # Резервный выход: через него трафик идёт, только когда все участники мертвы.
        working = " — сейчас трафик идёт через него" if state == "RESERVE" else ""
        parts.append(
            f'<p class="note">Резервный выход: {_esc(reserve.get("name") or reserve.get("tag"))}'
            f' ({_esc(cost.describe(float(reserve.get("cost") or 0.0)))}){_esc(working)}</p>'
        )
    spares = [
        [
            _esc(spare.get("tag")) + (" (резервный)" if spare.get("reserve") else ""),
            _esc(spare.get("name")),
            _esc(spare.get("verdict") or "не проверялся"),
            _esc(f"{spare['bytes']} Б за {spare['seconds']} с" if spare.get("verdict") else "—"),
            _esc(_clock(spare.get("scanned"))), _esc(_core(spare)),
        ]
        for spare in snapshot.get("spares") or []
    ]
    parts.append("<h2>Запасные</h2>")
    parts.append(_table(["Тег", "Сервер", "Проверка", "Загрузка", "Когда", "Ядро"], spares,
                        "запасных нет"))

    bypass = set((capture or {}).get("bypass") or [])
    rows = [
        [
            _esc(device.get("ip")), _esc(device.get("name") or "—"), _esc(device.get("mac")),
            _esc("мимо VPN" if device.get("ip") in bypass else "через VPN"),
            _esc(_clock(device.get("expires")) if device.get("expires") else "бессрочно"),
        ]
        for device in devices
    ]
    parts.append("<h2>Устройства (аренды DHCP)</h2>")
    parts.append(_table(["Адрес", "Имя", "MAC", "Маршрут", "Аренда до"], rows,
                        "устройств нет"))

    budget = snapshot.get("budget") or {}
    if budget:
        parts.append("<h2>Трафик проверок</h2>")
        total, probes, scans = (budget.get(key) for key in ("total_mb", "probes_mb", "scans_mb"))
        parts.append(
            f"<p>~{_esc(total)} МБ в сутки: пробы {_esc(probes)}, сканы {_esc(scans)}; "
            f"лимит {_esc(budget.get('limit_mb'))} МБ. "
            f"Сквозная проверка — ещё ~{_esc(budget.get('e2e_mb'))} МБ.</p>"
        )
        if budget.get("month_gb") is not None:
            parts.append(
                f"<p>Всего ~{_esc(budget.get('all_mb'))} МБ в сутки, "
                f"~{_esc(budget.get('month_gb'))} ГБ в месяц.</p>"
            )
        for warning in budget.get("warnings") or []:
            parts.append(f'<p class="note">{_esc(warning)}</p>')
    for name, quota in (snapshot.get("quota") or {}).items():
        used = (quota.get("upload", 0) + quota.get("download", 0)) / 1e9
        total = quota.get("total", 0) / 1e9
        text = f"Квота «{name}»: израсходовано {used:.1f} ГБ" + (
            f" из {total:.1f} ГБ" if total else "")
        parts.append(f"<p>{_esc(text)}</p>")

    events = [
        [_esc(_clock(event.get("ts"))), _esc(event.get("kind")), _esc(event.get("detail"))]
        for event in snapshot.get("events") or []
    ]
    parts.append("<h2>События</h2>")
    parts.append(_table(["Когда", "Тип", "Что произошло"], events, "событий нет"))
    parts.append(
        f'<p class="dim">Страница обновляется раз в {REFRESH_SECONDS} с. Только чтение.</p>'
        "</body></html>"
    )
    return "".join(parts)


# --- сервер --------------------------------------------------------------------


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    log = None

    def handle_error(self, request, client_address) -> None:
        """Сбой одного запроса — строка в журнале, а не трассировка в stderr."""
        if self.log is not None:
            self.log.exception("страница статуса: запрос от %s не обработан", client_address[0])

    def server_bind(self) -> None:
        # Демон может стартовать раньше, чем LAN-карта получит адрес.
        with contextlib.suppress(OSError):
            self.socket.setsockopt(socket.IPPROTO_IP, _IP_FREEBIND, 1)
        super().server_bind()


class StatusPage:
    def __init__(
        self, paths: Paths, token: str, address: str, *, port: int = PORT, logger=None
    ) -> None:
        self.paths = paths
        self.token = token
        self.address = address
        self.port = port
        self.log = logger or log.get_logger("page")
        self._server: _Server | None = None
        self._thread: threading.Thread | None = None

    @classmethod
    def from_config(cls, cfg: Config, paths: Paths, *, logger=None) -> StatusPage | None:
        """Страница по config.toml; None — она выключена или LAN не настроен."""
        gateway = lan.gateway(cfg)
        if not cfg.status.lan_page or not lan.lan_interface(cfg) or gateway is None:
            return None
        return cls(paths, ensure_token(cfg, paths), str(gateway.ip), logger=logger)

    # Данные для страницы — отдельными методами: в тестах подменяются.

    def snapshot(self) -> dict | None:
        return status.read_status(self.paths, max_age=float("inf"))

    def devices(self) -> list[dict]:
        return dnsmasq.read_leases(self.paths)

    def start(self) -> None:
        page = self

        class Handler(BaseHTTPRequestHandler):
            timeout = 10  # медленный клиент не держит поток
            server_version = "xgw"
            sys_version = ""

            def log_message(self, *_args) -> None:
                """Запросы не журналируются: в адресе может быть токен."""

            def do_GET(self) -> None:
                page.handle(self)

            def do_HEAD(self) -> None:
                page.handle(self, body=False)

        self._server = _Server((self.address, self.port), Handler)
        self._server.log = self.log
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="xgw-status-page", daemon=True,
            kwargs={"poll_interval": SHUTDOWN_POLL},
        )
        self._thread.start()
        self.log.info("страница статуса слушает %s, порт %d (по токену)", self.address, self.port)

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    # --- обработка запроса ------------------------------------------------------

    def _cookie(self) -> str:
        """Значение cookie — производное от токена: сам токен в браузере не хранится,
        а в заголовок попадают только символы ASCII, каким бы ни был токен."""
        return hmac.new(self.token.encode("utf-8"), b"xgw-status-page", hashlib.sha256).hexdigest()

    def _authorized(self, handler: BaseHTTPRequestHandler, query: dict) -> tuple[bool, bool]:
        """(пущен ли, пришёл ли токен в адресе)."""
        given = (query.get("token") or [""])[0]
        if given:
            return hmac.compare_digest(given.encode("utf-8"), self.token.encode("utf-8")), True
        expected = self._cookie().encode("ascii")
        for part in (handler.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == COOKIE and hmac.compare_digest(value.encode("utf-8", "replace"), expected):
                return True, False
        return False, False

    def handle(self, handler: BaseHTTPRequestHandler, *, body: bool = True) -> None:
        url = urlsplit(handler.path)
        allowed, in_query = self._authorized(handler, parse_qs(url.query))
        if not self.token or not allowed:
            self._send(handler, HTTPStatus.FORBIDDEN, "text/plain; charset=utf-8",
                       "Нужен токен: откройте страницу по ссылке вида /?token=…\n", body)
            return
        if in_query:
            # Токен переезжает в cookie и уходит из адресной строки и истории.
            handler.send_response(HTTPStatus.SEE_OTHER)
            handler.send_header("Location", url.path or "/")
            handler.send_header(
                "Set-Cookie", f"{COOKIE}={self._cookie()}; Path=/; HttpOnly; SameSite=Strict; "
                "Max-Age=31536000",
            )
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        if url.path == "/":
            text = render_page(self.snapshot(), self.devices())
            self._send(handler, HTTPStatus.OK, "text/html; charset=utf-8", text, body)
        elif url.path == "/status.json":
            payload = {"status": self.snapshot(), "devices": self.devices()}
            self._send(handler, HTTPStatus.OK, "application/json; charset=utf-8",
                       json.dumps(payload, ensure_ascii=False, indent=2) + "\n", body)
        else:
            self._send(handler, HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                       "Нет такой страницы\n", body)

    @staticmethod
    def _send(handler, code: HTTPStatus, content_type: str, text: str, body: bool) -> None:
        data = text.encode("utf-8")
        handler.send_response(code)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Referrer-Policy", "no-referrer")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("X-Frame-Options", "DENY")
        handler.send_header(
            "Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'"
        )
        handler.end_headers()
        if body:
            handler.wfile.write(data)
