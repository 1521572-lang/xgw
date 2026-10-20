"""Панель управления: http://127.0.0.1:8781/ — графический интерфейс XGW в браузере.

Что умеет: включить и выключить VPN (то же, что `xgw enable` и `xgw disable`),
показать серверы каждой подписки с задержками, закрепить один из них, отключить
сервер или убрать его из списка, добавить и убрать подписку или ссылку сервера,
обновить подписки и проверить запасные серверы, пустить устройство из Wi-Fi-сети
мимо VPN и вернуть его обратно. Карточка «Tailscale» (Т2): вход в tailnet, Tailscale SSH,
панель по tailnet (Serve) и маршрут самого Tailscale. Карточка «Телефоны» (А1
`ANDROID_APP_PLAN.md`): привязка приложения XGW для Android по QR-коду, список телефонов;
рядом с панелью работает API приложения (appapi.py), наружу — через Tailscale Funnel.

Безопасность:
  * слушает только 127.0.0.1 — из сети панель не открыть; по tailnet её открывает
    Tailscale Serve (https://<шлюз>.<tailnet>.ts.net:8443/, только устройства tailnet), и
    этот адрес принимается, только пока Serve включён из панели;
  * без токена не отдаёт ничего, кроме страницы входа; токен из ссылки сразу
    переезжает в cookie (HttpOnly, SameSite=Strict);
  * запрос с чужим заголовком Host отклоняется — это защита от подмены DNS
    (rebinding), когда сторонний сайт выдаёт себя за 127.0.0.1;
  * менять что-либо можно только запросом POST с заголовком X-XGW-Panel: чужая
    страница в том же браузере такой запрос отправить не может;
  * адреса подписок и ссылки серверов наружу не отдаются — только домен и имя;
  * всё, что приходит из подписок и от устройств, страница вставляет как текст.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import shutil
import socket
import sqlite3
import threading
import time
from collections import Counter
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .. import __version__, actions, config, cost, engine, log, managed, masking, priority, qr
from .. import pin as pinning
from .. import tailscale as ts
from ..config import Config
from ..generator import validate
from ..generator.builder import BALANCER_TAG
from ..net import cmd, dnsmasq, lan
from ..net.capture import Capture
from ..parsers.common import parse_links_text
from ..paths import Paths, atomic_write_text
from ..phones import Phones
from ..store import SubscriptionCache
from . import status
from .appapi import AppApi

COOKIE = "xgw_panel"
HEADER = "X-XGW-Panel"
MAX_BODY = 65536
MAX_DRAIN = 1 << 20  # сколько лишнего дочитать, прежде чем отказать
SELECT_TTL = 3.0  # как долго помнить ответ ядра о выбранном сервере
EVENTS = 30
LOGIN_TTL = 60.0  # сколько живёт одноразовый код входа, секунд
LINK_TTL = 900.0  # код в ссылке бота (/panel): человеку нужно время дойти до устройства
TS_TTL = 10.0  # как долго помнить, что ответил CLI tailscale (страница опрашивает часто)
TS_WAIT = 10.0  # сколько действие карточки ждёт ссылку входа или итог Serve
PIN_TTLS = ("10m", "1h", "6h", "24h")
MANUAL = "manual"  # источник серверов, заданных отдельными ссылками
# Как часто сервер проверяет, не пора ли остановиться: столько самое большее ждёт
# остановка демона (по умолчанию в http.server — 0,5 с).
SHUTDOWN_POLL = 0.1
_ORDER = {"member": 0, "spare": 1, "waiting": 2, "disabled": 3, "skipped": 4}
_VERDICTS = {"OK": 0, "SLOW": 1, None: 2}  # запасные: сначала пригодные к замене
_SERVER_WORDS = {
    "enabled": ("включён", "включено"),
    "disabled": ("отключён", "отключено"),
    "removed": ("убран из списка", "убрано из списка"),
}
UI_DIR = Path(__file__).resolve().parent.parent / "ui"
_STATIC = {
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/icon.svg": ("icon.svg", "image/svg+xml"),
}
_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)
_LINK_SCHEMES = ("vless://", "vmess://", "trojan://", "ss://", "hysteria2://", "hy2://")


def token_file(paths: Paths) -> Path:
    return paths.panel_token_file


def read_token(paths: Paths) -> str:
    with contextlib.suppress(OSError):
        return token_file(paths).read_text(encoding="ascii").strip()
    return ""


def ensure_token(paths: Paths) -> str:
    """Токен панели; создаётся при первой надобности, лежит в /var/lib/xgw (0600)."""
    token = read_token(paths)
    if not token:
        token = secrets.token_urlsafe(24)
        atomic_write_text(token_file(paths), token + "\n", mode=0o600)
    return token


def address(cfg: Config) -> str:
    return f"http://127.0.0.1:{cfg.panel.port}/"


def login_dir(paths: Paths) -> Path:
    return paths.run / "panel-login"


def _login_digest(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _login_ttl(path: Path) -> float:
    """Срок кода: записан в файле (LINK_TTL у ссылки бота); пусто — LOGIN_TTL."""
    try:
        ttl = float(path.read_text(encoding="ascii").strip() or LOGIN_TTL)
    except (OSError, ValueError):
        return LOGIN_TTL
    return min(max(ttl, 0.0), LINK_TTL)


def new_login(
    paths: Paths, now: Callable[[], float] | None = None, *, ttl: float = LOGIN_TTL
) -> str:
    """Одноразовый код входа для ссылки, которую открывает сам XGW (установка, ярлык
    «XGW» → «Войти заново») или присылает бот (/panel, ttl = LINK_TTL). Постоянный токен в
    адрес не попадает: адрес виден в списке процессов, журнале и переписке, а код годится
    один раз и только ttl секунд. На диске — не код, а его SHA-256 (и срок), в каталоге,
    который читает только root."""
    now = now or time.time
    directory = login_dir(paths)
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    for stale in directory.iterdir():
        with contextlib.suppress(OSError):  # другой процесс мог убрать его сам
            if now() - stale.stat().st_mtime > _login_ttl(stale):
                stale.unlink()
    code = secrets.token_urlsafe(24)
    fd = os.open(directory / _login_digest(code), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        if ttl != LOGIN_TTL:
            os.write(fd, f"{min(ttl, LINK_TTL):g}\n".encode("ascii"))
    finally:
        os.close(fd)
    return code


def use_login(paths: Paths, code: str, now: Callable[[], float] | None = None) -> bool:
    """Код входа годен: есть, не старше своего срока. Проверенный код гасится сразу."""
    if not code or len(code) > 64:
        return False
    now = now or time.time
    path = login_dir(paths) / _login_digest(code)
    try:
        age = now() - path.stat().st_mtime
        ttl = _login_ttl(path)
        path.unlink()
    except OSError:  # кода нет: уже использован, устарел и убран либо выдуман
        return False
    # Часы файловой системы грубее, чем time.time(): только что выданный код не должен
    # оказаться «из будущего».
    return -1.0 <= age <= ttl


def login_address(cfg: Config, code: str) -> str:
    return f"{address(cfg)}?login={code}"


def tailnet_address(name: str) -> str:
    """Панель по tailnet (Tailscale Serve): имя шлюза в tailnet и порт SERVE_PORT."""
    return f"https://{name}:{ts.SERVE_PORT}/"


def wait_ready(port: int, wait: float = 15.0) -> bool:
    """Панель принимает соединения; только что запущенному демону даётся wait секунд."""
    deadline = time.monotonic() + wait
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.3)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    log = None

    def handle_error(self, request, client_address) -> None:
        if self.log is not None:
            self.log.exception("панель: запрос не обработан")


class Refused(Exception):
    """Запрос отклонён; code — статус HTTP, текст — для человека."""

    def __init__(self, code: HTTPStatus, text: str) -> None:
        super().__init__(text)
        self.code = code


class Panel:
    def __init__(
        self,
        paths: Paths,
        config_path: Path,
        token: str,
        *,
        port: int,
        logger=None,
        root_problem: Callable[[], str | None] = actions.root_problem,
        capture_factory: Callable[..., Capture] = Capture,
        runner: Callable[..., str] = cmd.run,
        which: Callable[[str], str | None] = shutil.which,
        spawn: ts.Spawn = ts.spawn,
        sys_net: Path | None = None,
        app_port: int | None = None,
    ) -> None:
        self.paths = paths
        self.config_path = Path(config_path)
        self.token = token
        self.port = port
        self.log = logger or log.get_logger("panel")
        self.root_problem = root_problem
        self.capture_factory = capture_factory
        self.runner = runner
        self.which = which
        self.spawn = spawn
        self.sys_net = sys_net
        self.ts_wait = TS_WAIT
        self.cfg = Config()
        self.daemon = None
        self.bot = None
        self._lock = threading.Lock()  # одно действие за раз
        self._selecting: tuple[float, list[str]] = (0.0, [])
        self._labels: dict[str, str] = {}
        self._server: _Server | None = None
        self._thread: threading.Thread | None = None
        self._ts_card: tuple[float, dict | None] = (0.0, None)
        self._ts_jobs: dict[str, ts.Job] = {}  # «login», «serve», «funnel» — фоновые команды
        self.phones = Phones(paths)
        self.app_port = app_port  # None — API приложения не запускается (тесты панели)
        self.app_api: AppApi | None = None

    @classmethod
    def from_config(cls, cfg: Config, paths: Paths, config_path: Path, **kwargs) -> Panel | None:
        """Панель по config.toml; None — она выключена ([panel] enabled = false)."""
        if not cfg.panel.enabled:
            return None
        kwargs.setdefault("app_port", cfg.panel.app_port)
        panel = cls(paths, config_path, ensure_token(paths), port=cfg.panel.port, **kwargs)
        panel.configure(cfg)
        return panel

    def configure(self, cfg: Config, daemon=None, bot=None) -> None:
        """Новые настройки, новый демон и бот Telegram после перечитывания конфига."""
        self.cfg = cfg
        self.daemon = daemon
        self.bot = bot

    # --- запуск ------------------------------------------------------------------

    def start(self) -> None:
        panel = self

        class Handler(BaseHTTPRequestHandler):
            timeout = 15
            server_version = "xgw"
            sys_version = ""

            def log_message(self, *_args) -> None:
                """Запросы не журналируются: в адресе может быть токен."""

            def do_GET(self) -> None:
                panel.handle(self, "GET")

            def do_HEAD(self) -> None:
                panel.handle(self, "HEAD")

            def do_POST(self) -> None:
                panel.handle(self, "POST")

        self._server = _Server(("127.0.0.1", self.port), Handler)
        self._server.log = self.log
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="xgw-panel", daemon=True,
            kwargs={"poll_interval": SHUTDOWN_POLL},
        )
        self._thread.start()
        self.log.info("панель управления слушает 127.0.0.1, порт %d (по токену)", self.port)
        if self.app_port is not None:
            api = AppApi(self, self.phones, port=self.app_port, logger=self.log)
            try:
                api.start()
            except OSError as exc:  # панель работает и без API приложения
                self.log.error("API приложения не запущен (порт %d): %s", self.app_port, exc)
            else:
                self.app_api = api

    def stop(self) -> None:
        if self.app_api is not None:
            self.app_api.stop()
            self.app_api = None
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    # --- что показать -------------------------------------------------------------

    def _capture(self) -> Capture:
        return self.capture_factory(self.cfg, self.paths, logger=self.log)

    def _db(self, query: str, args: tuple = ()) -> list[sqlite3.Row]:
        """Чтение состояния отдельным соединением только для чтения."""
        try:
            conn = sqlite3.connect(
                f"{self.paths.db_file.as_uri()}?mode=ro", uri=True, timeout=2
            )
        except sqlite3.Error:
            return []
        try:
            conn.row_factory = sqlite3.Row
            return conn.execute(query, args).fetchall()
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    def _pin(self, now: float) -> dict | None:
        """Ручной выбор сервера (pin.py): until — null, если бессрочный; down — выбранный
        не отвечает, трафик ведёт автовыбор."""
        rows = self._db("SELECT value FROM meta WHERE key = ?", (pinning.META,))
        pin = pinning.read(rows[0]["value"] if rows else None, now)
        if pin is None:
            return None
        return {
            "tag": str(pin["tag"]), "name": str(pin.get("name") or ""),
            "until": None if pin.get("until") is None else float(pin["until"]),
            "down": pin.get("down") or None,
        }

    def _selected(self, xray_ok: bool, now: float) -> list[str]:
        """Какой сервер сейчас выбран ядром (или закреплён)."""
        if not xray_ok:
            return []
        stamp, tags = self._selecting
        if now - stamp < SELECT_TTL:
            return tags
        tags = []
        xray_bin = validate.find_xray(None, self.paths)
        if xray_bin is not None:
            with contextlib.suppress(Exception):
                info = engine.make_api(self.cfg, xray_bin).balancer_state(BALANCER_TAG)
                tags = [info.override] if info.override else list(info.selects)
        self._selecting = (now, tags)
        return tags

    def _link_label(self, link: str) -> str:
        label = self._labels.get(link)
        if label is None:
            raws, _meta, _warnings = parse_links_text(link, "manual")
            label = f"{raws[0].protocol} · {raws[0].name}" if raws else "не разобрана"
            label = masking.mask_text(label)
            if len(self._labels) > 1000:
                self._labels.clear()
            self._labels[link] = label
        return label

    def _power(self, mode: str, xray_ok: bool, has_servers: bool) -> dict:
        """Можно ли нажать кнопку и, если нет, почему."""
        problem = self.root_problem()
        if problem:
            return {"can_on": False, "can_off": False, "why": problem}
        if mode == "none":
            return {
                "can_on": False, "can_off": False,
                "why": "перехват выключен в config.toml: capture.local = false и не задан "
                       "network.lan_if",
            }
        if mode in ("on", "open"):
            return {"can_on": False, "can_off": True, "why": ""}
        if not has_servers:
            return {"can_on": False, "can_off": False,
                    "why": "сначала добавьте подписку или ссылку сервера"}
        if not xray_ok:
            return {
                "can_on": False, "can_off": False,
                "why": "Xray не отвечает — с включённым VPN машина осталась бы без интернета",
            }
        return {"can_on": True, "can_off": False, "why": ""}

    def _servers(
        self, members: list[dict], spares: list[dict], quotas: dict | None = None
    ) -> tuple[list[dict], list[dict]]:
        """Все серверы подписок и отдельно — убранные из списка.

        Список ведёт демон (inventory.json): в нём и серверы, которых в конфиге
        Xray нет, — отключённые, отсеянные фильтрами, ещё не применённые.
        quotas — квоты подписок (subscription-userinfo): у серверов подписок с лимитом
        трафика показывается множитель расхода (cost.py).
        """
        disabled, removed = set(self.cfg.managed.disabled), set(self.cfg.managed.removed)
        limited = cost.limited_sources(quotas or {})
        listing = engine.load_inventory(self.paths)
        listed = {item.get("fingerprint") for item in listing}
        live: dict[str, tuple[str, dict]] = {}
        for role, entries in (("member", members), ("spare", spares)):
            for entry in entries:
                fingerprint = str(entry.get("fingerprint") or entry.get("tag") or "")
                if len(fingerprint) < 8:
                    # Демон ещё не сопоставил узел с подпиской: в статусе только
                    # начало отпечатка (оно есть в теге). Ищем полный в списке.
                    found = [item for item in listed if str(item).startswith(fingerprint)]
                    if fingerprint and len(found) == 1:
                        fingerprint = found[0]
                if fingerprint:
                    live[fingerprint] = (role, entry)
        # Сервер работает в ядре, а в списке его нет (список устарел) — показать всё равно.
        for fingerprint, (_role, entry) in live.items():
            if fingerprint not in listed:
                listing.append({
                    "fingerprint": fingerprint, "name": entry.get("name") or "",
                    "source": entry.get("source") or "", "protocol": "", "skip": "",
                })
        rows: list[dict] = []
        gone: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for item in listing:
            fingerprint, source = item.get("fingerprint"), item.get("source") or ""
            if not isinstance(fingerprint, str) or (source, fingerprint) in seen:
                continue
            seen.add((source, fingerprint))
            role, entry = live.get(fingerprint, ("", {}))
            row = {
                "fingerprint": fingerprint,
                "name": item.get("name") or entry.get("name") or entry.get("tag") or fingerprint,
                "source": source,
                "protocol": item.get("protocol") or "",
                "priority": priority.level_of(self.cfg.managed.priority, fingerprint),
                # Какое ядро умеет сервер (dual, xray, singbox) и что закреплено вручную.
                "capability": item.get("core") or "dual",
                "core_pin": self.cfg.managed.core.get(fingerprint, "auto"),
            }
            if source in limited and not item.get("skip"):
                # Подписка с лимитом трафика: столько байт квоты уходит на байт трафика.
                # У служебных записей («Осталось 5 ГБ») множителя нет — это не серверы.
                row["multiplier"] = cost.multiplier(row["name"], self.cfg.filters.multiplier_regex)
            if fingerprint in removed:
                gone.append(row)
                continue
            if fingerprint in disabled:
                # pending — в ядре он ещё есть: демон уберёт его на ближайшем шаге.
                row.update(status="disabled", pending=bool(role))
            elif role == "member":
                row.update(
                    status="member", tag=entry.get("tag"), alive=entry.get("alive"),
                    delay_ms=entry.get("delay_ms"), dead_since=entry.get("dead_since"),
                    selected=bool(entry.get("selected")),
                    # Основной сервер и последний замер скорости (watch/speed.py).
                    main=bool(entry.get("main")), speed_mbps=entry.get("speed_mbps"),
                    speed_error=entry.get("speed_error") or "", speed_ts=entry.get("speed_ts"),
                    fragment=bool(entry.get("fragment")),
                    profile=entry.get("profile") or "", core=entry.get("core") or "",
                )
            elif role == "spare":
                row.update(
                    status="spare", tag=entry.get("tag"), verdict=entry.get("verdict"),
                    scanned=entry.get("scanned"), reserve=bool(entry.get("reserve")),
                    speed_mbps=entry.get("speed_mbps"), speed_ts=entry.get("speed_ts"),
                    fragment=bool(entry.get("fragment")),
                    profile=entry.get("profile") or "", core=entry.get("core") or "",
                )
            elif item.get("skip"):
                row.update(status="skipped", skip=item["skip"])
            else:
                row.update(status="waiting")
            rows.append(row)
        rows.sort(key=lambda row: (
            _ORDER[row["status"]], not row.get("selected"),
            row.get("delay_ms") if row.get("delay_ms") is not None else 10**9,
            _VERDICTS.get(row.get("verdict"), 3), row["name"],
        ))
        return rows, gone

    def _core(self, now: float) -> tuple[dict, bool, list[dict], list[dict]]:
        """Последний статус демона: сам снимок, отвечает ли Xray, участники
        (с отметкой, кто выбран сейчас) и запасные."""
        snapshot = status.read_status(self.paths, max_age=float("inf")) or {}
        xray_ok = bool((snapshot.get("xray") or {}).get("ok")) and (
            now - float(snapshot.get("updated") or 0) < 180
        )
        members = [dict(member) for member in snapshot.get("members") or []]
        spares = [dict(spare) for spare in snapshot.get("spares") or []]
        selected = self._selected(xray_ok, now)
        for member in members:
            member["selected"] = member.get("tag") in selected
            # Основной сервер выключен переключателем — демон снимет его на ближайшем шаге,
            # а панель уже не показывает его основным.
            member["main"] = bool(member.get("main")) and self.cfg.speed.sticky
        return snapshot, xray_ok, members, spares

    def state(self) -> dict:
        cfg, now = self.cfg, time.time()
        snapshot, xray_ok, members, spares = self._core(now)
        xray = snapshot.get("xray") or {}
        capture = self._capture()
        info = capture.describe(check=False)
        written = snapshot.get("capture") or {}
        loaded = written.get("loaded")
        # Жизненный цикл перехвата считает демон (daemon.Lifecycle): панель его только
        # показывает строкой «Перехват: …». Демона нет — строки нет.
        lifecycle = {
            "lifecycle": written.get("lifecycle") or "",
            "lifecycle_reason": written.get("lifecycle_reason") or "",
        }

        quotas, errors = snapshot.get("quota") or {}, snapshot.get("sub_errors") or {}
        servers, gone = self._servers(members, spares, quotas)
        limited = cost.limited_sources(quotas)
        # Сколько серверов дала подписка: вместе с отключёнными, без служебных записей.
        per_source = Counter(row["source"] for row in servers if row["status"] != "skipped")
        cache = SubscriptionCache(self.paths.cache_dir)
        subscriptions = []
        for sub in cfg.subscriptions:
            if not sub.url:
                continue
            error = errors.get(sub.name) or {}
            subscriptions.append({
                "name": sub.name,
                "host": masking.mask_url(sub.url),
                "secure": sub.url.startswith("https://"),
                "managed": sub.name in cfg.managed.subscriptions,
                "servers": per_source.get(sub.name, 0),
                "fetched": cache.saved_at(sub.name) or None,
                "error": error.get("error") or "",
                "quota": quotas.get(sub.name),
                # Лимит трафика есть (total в subscription-userinfo); иначе — безлимитная.
                "limited": sub.name in limited,
                "user_agent": sub.user_agent,
                "headers": sub.headers,
            })
        links = [
            {
                "id": managed.link_id(link),
                "label": self._link_label(link),
                "managed": link in cfg.managed.links,
            }
            for link in cfg.manual.links
        ]

        devices = self._devices(info)
        gateway = lan.gateway(cfg)
        events = [
            {"ts": row["ts"], "kind": row["kind"], "detail": row["detail"]}
            for row in self._db(
                "SELECT ts, kind, detail FROM events ORDER BY id DESC LIMIT ?", (EVENTS,)
            )
        ]
        daemon = self.daemon
        sources = [sub.name for sub in cfg.subscriptions if sub.url]
        if cfg.manual.links or any(row["source"] == MANUAL for row in servers):
            sources.append(MANUAL)
        result = {
            "version": __version__,
            "now": now,
            "updated": snapshot.get("updated"),
            "state": snapshot.get("state"),
            "action": snapshot.get("action") or "",
            "since": snapshot.get("since"),
            "xray": {"ok": xray_ok, "version": xray.get("version") or ""},
            "capture": {**info, "loaded": loaded, **lifecycle},
            "power": self._power(info["mode"], xray_ok, bool(members)),
            "members": members,
            "spares": spares,
            # Уровень приоритета серверов, что сейчас в работе (priority.py).
            "tier": snapshot.get("tier"),
            # Резервный выход балансировщика (запасной класса хуже, cost.py).
            "reserve": snapshot.get("reserve"),
            # Основной сервер (speed.sticky): весь трафик через него, остальные наготове.
            "main": snapshot.get("main") if cfg.speed.sticky else None,
            "sticky": {
                "on": cfg.speed.sticky,
                # Замеры скорости: 0 — выключены, основной выбирается по задержке.
                "every_hours": cfg.speed.every_hours,
                "gain_pct": cfg.speed.gain_pct,
                "hold_minutes": cfg.speed.hold_minutes,
            },
            "servers": servers,
            "removed": gone,
            "sources": sources,
            "pin": self._pin(now),
            "subscriptions": subscriptions,
            "links": links,
            "lan": {
                "interface": info["lan_if"],
                "gateway": str(gateway.ip) if gateway and info["lan_if"] else "",
            },
            "devices": devices,
            "telegram": self.bot.info() if self.bot is not None else {"mode": "unavailable"},
            "events": events,
            "budget": snapshot.get("budget") or {},
            # Сводка разбора подписок и предупреждение «не отвечает сам probe.url».
            "nodes": snapshot.get("nodes") or {},
            "probe_target": snapshot.get("probe_target") or "",
            "pending_restart": bool(snapshot.get("pending_restart")),
            # Второе ядро (sing-box): режим [core], установлен ли, отвечает ли, сколько
            # серверов ведёт; singbox_pending — конфиг ждёт окна перезапуска.
            "singbox": snapshot.get("singbox") or {},
            "singbox_pending": bool(snapshot.get("singbox_pending")),
            "busy": {
                "refresh": bool(daemon is not None and daemon.refresh_pending),
                "scan": bool(daemon is not None and daemon.scan_pending),
                "speed": bool(daemon is not None and daemon.speed_pending),
            },
        }
        masked = masking.mask_obj(result)
        assert isinstance(masked, dict)
        # Карточка — мимо маскирования: ссылка входа в Tailscale нужна целиком, а имя и
        # адрес шлюза в tailnet — не секреты для того, кто вошёл в панель.
        masked["tailscale"] = self._tailscale_card()
        # Карточка «Телефоны» — тоже мимо маскирования: в QR — адрес и одноразовый код.
        masked["phones"] = self._phones_card()
        return masked

    def _devices(self, info: dict) -> list[dict]:
        """Устройства сети: аренды dnsmasq плюс пущенные мимо VPN в панели, которых
        сейчас нет в сети (аренда истекла). managed — переключатель работает;
        иначе устройство задано в config.toml, и панель его не меняет."""
        if not info["lan_if"]:
            return []
        bypass = set(info["bypass"])
        mine = set(self.cfg.managed.devices)
        devices = [
            {**device, "bypass": device.get("ip") in bypass, "managed": device["mac"] in mine}
            for device in dnsmasq.read_leases(self.paths)
        ]
        online = {device["mac"] for device in devices}
        leases, _warnings = lan.parse_leases(self.cfg)
        for lease in leases:
            if lease.mac in mine and lease.mac not in online:
                devices.append({
                    "mac": lease.mac, "ip": lease.ip, "name": lease.name, "expires": 0,
                    "bypass": lease.ip in bypass, "managed": True, "offline": True,
                })
        return devices

    # --- Tailscale (Т2) --------------------------------------------------------------

    def _tailscale_card(self, *, fresh: bool = False) -> dict:
        """Карточка «Tailscale». Ответ CLI помнится TS_TTL секунд: страница спрашивает
        состояние каждые несколько секунд, а это пять команд. Фоновые задания (вход, Serve)
        проверяются каждый раз — они дешёвые."""
        stamp, card = self._ts_card
        if fresh or card is None or time.monotonic() - stamp >= TS_TTL:
            card = self._tailscale_read()
            self._ts_card = (time.monotonic(), card)
        card = dict(card)
        login = self._ts_job("login")
        card["login_pending"] = login is not None and login.code() is None
        if card["state"] == "login" and not card["auth_url"] and card["login_pending"]:
            card["auth_url"] = ts.find_url(login.text())  # status ещё не обновился
        card["auth_qr"] = qr.encode(card["auth_url"]) if card["auth_url"] else []
        for kind in ("serve", "funnel"):
            job = self._ts_job(kind)
            pending = job is not None and job.code() is None
            card[kind] = {
                **card[kind], "pending": pending,
                # Serve ждёт, пока в tailnet включат HTTPS, Funnel — пока его разрешат в
                # правилах tailnet: CLI напечатал, где это сделать.
                "enable_url": ts.find_url(job.text()) if pending and job is not None else "",
            }
        return card

    def _ts_job(self, name: str) -> ts.Job | None:
        return self._ts_jobs.get(name)

    def _tailscale_read(self) -> dict:
        cfg = self.cfg
        serving = cfg.managed.tailscale_serve
        public = cfg.managed.tailscale_funnel
        card: dict = {
            "state": "absent", "backend": "", "name": "", "address": "", "auth_url": "",
            "ssh": None, "route": cfg.tailscale.route,
            "route_panel": cfg.managed.tailscale_route is not None,
            "serve": {"on": bool(serving), "live": None, "url": ""},
            "funnel": {"on": bool(public), "live": None, "url": ""},
            "cgnat": [], "netfilter_off": None, "override_dns": None,
        }
        if self.which("tailscale") is None:
            return card
        if not ts.present(self.paths, self.sys_net):
            card["state"] = "stopped"
            return card
        state = ts.status(self.runner)
        if state is None:
            card["state"] = "unknown"
            return card
        card["backend"] = state.backend
        card["state"] = {"Running": "running", "NeedsLogin": "login"}.get(state.backend, "other")
        card["name"] = state.dns_name
        card["address"] = next((item for item in state.addresses if ":" not in item), "")
        if state.backend != "Running" and state.auth_url.startswith("https://"):
            card["auth_url"] = state.auth_url
        prefs = ts.prefs(self.runner)
        if prefs is not None:
            card["ssh"] = prefs.ssh
            card["netfilter_off"] = (
                None if prefs.netfilter is None else prefs.netfilter == ts.NETFILTER_OFF)
        if state.backend == "Running":
            card["serve"]["live"] = ts.serve_status(self.port, self.runner)
            if self.app_api is not None:
                card["funnel"]["live"] = ts.funnel_status(self.app_api.port, self.runner)
            if public and state.dns_name and state.dns_name != public:
                with contextlib.suppress(managed.ManagedError, OSError):
                    managed.set_tailscale_funnel(
                        managed.path_for(self.config_path), state.dns_name)
                    self._wake()
                public = state.dns_name
            if serving and state.dns_name and state.dns_name != serving:
                # Шлюз переименовали в консоли tailnet: Serve отвечает уже по новому имени.
                with contextlib.suppress(managed.ManagedError, OSError):
                    managed.set_tailscale_serve(managed.path_for(self.config_path), state.dns_name)
                    self._wake()
                serving = state.dns_name
        if serving:
            card["serve"]["url"] = tailnet_address(serving)
        elif state.dns_name:
            card["serve"]["url"] = tailnet_address(state.dns_name)
        if public or state.dns_name:
            card["funnel"]["url"] = f"https://{public or state.dns_name}/"
        if card["netfilter_off"] is not True:
            card["cgnat"] = ts.provider_cgnat(cfg, self.runner, skip=(lan.lan_interface(cfg),))
        card["override_dns"] = ts.override_dns(self.runner)
        return card

    def _tailscale(self, step: str, body: dict, store_path: Path) -> actions.Outcome:
        """Кнопки карточки «Tailscale»: каждая меняет одну настройку и только по нажатию."""
        problem = self.root_problem()
        if problem:
            return actions.Outcome(1, problem)
        if step == "route":
            # Маршрут — настройка XGW, а не Tailscale: правила перезагрузит демон.
            route = body.get("route")
            if route not in ts.ROUTES:
                return actions.Outcome(2, "ожидается route: direct или vpn")
            if managed.set_tailscale_route(store_path, route):
                way = "напрямую" if route == "direct" else "через VPN"
                self._event(f"маршрут Tailscale: {way}")
                self._wake()
            self._ts_card = (0.0, None)
            if route == "direct":
                return actions.Outcome(0, "Tailscale идёт напрямую, мимо VPN", (
                    "Провайдер видит, что на шлюзе работает Tailscale, но не видит, что внутри",))
            return actions.Outcome(0, "Tailscale идёт через VPN, пока Xray отвечает", (
                "Когда Xray не отвечает или VPN заблокирован — напрямую, чтобы шлюз остался "
                "доступен",))
        if self.which("tailscale") is None:
            return actions.Outcome(2, "Tailscale не установлен")
        if not ts.present(self.paths, self.sys_net):
            return actions.Outcome(2, "tailscaled не запущен: sudo systemctl start tailscaled")
        try:
            outcome = self._tailscale_step(step, body, store_path)
        except cmd.CommandError as exc:
            outcome = actions.Outcome(1, f"Tailscale не принял команду: {exc}")
        self._ts_card = (0.0, None)
        return outcome

    def _tailscale_step(self, step: str, body: dict, store_path: Path) -> actions.Outcome:
        if step == "login":
            return self._tailscale_login()
        if step == "fix":
            name = body.get("name")
            if name not in ts.FIXES:
                return actions.Outcome(2, "ожидается name: netfilter или dns")
            ts.fix(name, self.runner)
            if name == "netfilter":
                self._event("Tailscale: фаервол Tailscale выключен (netfilter-mode=off)")
                return actions.Outcome(0, "Фаервол Tailscale выключен: правила держит XGW", (
                    "Адреса провайдера из 100.64.0.0/10 больше не отбрасываются",))
            self._event("Tailscale: DNS из tailnet не принимается (accept-dns=false)")
            return actions.Outcome(0, "DNS шлюза снова идёт через VPN", (
                "Имена MagicDNS на самом шлюзе больше не разрешаются; на других устройствах "
                "tailnet всё по-прежнему",))
        state = ts.status(self.runner)
        if state is None or state.backend != "Running":
            return actions.Outcome(2, "сначала войдите в Tailscale")
        if step == "ssh":
            if not isinstance(body.get("on"), bool):
                return actions.Outcome(2, "ожидается on: true или false")
            ts.set_ssh(body["on"], self.runner)
            self._event("Tailscale SSH " + ("включён" if body["on"] else "выключен"))
            if body["on"]:
                return actions.Outcome(0, "SSH через Tailscale включён", (
                    "Вход — по учётной записи tailnet, кто и под каким пользователем — правила "
                    "в консоли tailnet. Порт SSH в интернет не открывается",))
            return actions.Outcome(0, "SSH через Tailscale выключен")
        if step == "serve":
            if not isinstance(body.get("on"), bool):
                return actions.Outcome(2, "ожидается on: true или false")
            return self._tailscale_serve(body["on"], state.dns_name, store_path)
        if step == "funnel":
            if not isinstance(body.get("on"), bool):
                return actions.Outcome(2, "ожидается on: true или false")
            return self._tailscale_funnel(body["on"], state.dns_name, store_path)
        return actions.Outcome(2, "нет такого действия")

    def _wait_job(self, job: ts.Job, done: Callable[[], bool]) -> None:
        deadline = time.monotonic() + self.ts_wait
        while job.code() is None and not done() and time.monotonic() < deadline:
            time.sleep(0.3)

    def _tailscale_login(self) -> actions.Outcome:
        """`tailscale login` в фоне: CLI ждёт входа в браузере, а ссылка (AuthURL) уже в
        `status --json` — её карточка показывает кнопкой и QR-кодом."""
        state = ts.status(self.runner)
        if state is not None and state.backend == "Running":
            # `tailscale login` начал бы вход в новый, пустой профиль — с другими настройками.
            return actions.Outcome(0, "Шлюз уже в tailnet")
        job = self._ts_job("login")
        if job is not None and job.code() is None:
            return actions.Outcome(0, "Вход уже начат: откройте ссылку в карточке")
        job = ts.Job(ts.login_command(), self.paths.run / "tailscale-login.log", self.spawn)
        self._ts_jobs["login"] = job
        self._event("Tailscale: вход начат из панели")

        def ready() -> bool:
            state = ts.status(self.runner)
            return state is not None and (bool(state.auth_url) or state.backend == "Running")

        self._wait_job(job, ready)
        code, state = job.code(), ts.status(self.runner)
        if state is not None and state.backend == "Running":
            return actions.Outcome(0, "Шлюз в tailnet")
        if code not in (None, 0):
            lines = [line for line in job.text().splitlines() if line.strip()]
            return actions.Outcome(
                1, "tailscale login: " + (lines[-1] if lines else f"код {code}"))
        return actions.Outcome(0, "Откройте ссылку входа — кнопка и QR-код в карточке", (
            "Войдите в учётную запись tailnet; карточка обновится сама",))

    def _tailscale_serve(self, on: bool, name: str, store_path: Path) -> actions.Outcome:
        """Панель по tailnet: `tailscale serve --bg --https=8443 http://127.0.0.1:ПОРТ`.
        Флаг в panel.json — что Serve включил XGW: только тогда панель принимает Host
        «имя:8443», и только такой Serve снимает `xgw uninstall`."""
        job = self._ts_job("serve")
        if not on:
            if job is not None:
                job.stop()
            failed = ""
            try:
                ts.serve_off(self.runner)
            except cmd.CommandError as exc:
                failed = str(exc)
            managed.set_tailscale_serve(store_path, "")
            self._wake()
            self._event("Tailscale: панель по tailnet выключена")
            if failed:
                return actions.Outcome(1, f"панель по tailnet больше не принимается, но Serve "
                                          f"не снят: {failed}")
            return actions.Outcome(0, "Панель по tailnet выключена")
        if not name:
            return actions.Outcome(1, "Tailscale не назвал имя шлюза в tailnet — повторите")
        if job is not None and job.code() is None:
            return actions.Outcome(0, "Serve уже ждёт: разрешите HTTPS в tailnet по кнопке")
        job = ts.Job(ts.serve_command(self.port), self.paths.run / "tailscale-serve.log",
                     self.spawn)
        self._ts_jobs["serve"] = job
        self._wait_job(job, lambda: False)
        code = job.code()
        if code not in (None, 0):
            lines = [line for line in job.text().splitlines() if line.strip()]
            return actions.Outcome(1, "tailscale serve: " + (lines[-1] if lines else f"код {code}"))
        managed.set_tailscale_serve(store_path, name)
        self._wake()
        self._event("Tailscale: панель по tailnet включена")
        if code is None:
            return actions.Outcome(0, "Осталось разрешить HTTPS в tailnet", (
                "Нажмите «Разрешить HTTPS в tailnet» и подтвердите в консоли Tailscale — "
                "панель по tailnet заработает сама",))
        return actions.Outcome(0, "Панель по tailnet включена — адрес в карточке", (
            "Открывается только на устройствах, где включён Tailscale",))

    def _tailscale_funnel(self, on: bool, name: str, store_path: Path) -> actions.Outcome:
        """API приложения в интернет: `tailscale funnel --bg --https=443 http://127.0.0.1:
        <порт API>`. Флаг в panel.json — что Funnel включил XGW: только тогда API
        принимает Host с именем шлюза, и только такой Funnel снимает `xgw uninstall`."""
        job = self._ts_job("funnel")
        if not on:
            if job is not None:
                job.stop()
            self.phones.cancel()
            failed = ""
            try:
                ts.funnel_off(self.runner)
            except cmd.CommandError as exc:
                failed = str(exc)
            managed.set_tailscale_funnel(store_path, "")
            self._wake()
            self._event("Tailscale: приложение на телефоне — Funnel выключен")
            if failed:
                return actions.Outcome(1, f"приложение больше не принимается, но Funnel не "
                                          f"снят: {failed}")
            return actions.Outcome(0, "Funnel выключен: приложение на телефоне до шлюза не "
                                      "достучится, пока его не включить")
        if self.app_api is None:
            return actions.Outcome(1, "API приложения не запущен — подробности в журнале XGW")
        if not name:
            return actions.Outcome(1, "Tailscale не назвал имя шлюза в tailnet — повторите")
        if job is not None and job.code() is None:
            return actions.Outcome(0, "Funnel уже ждёт: разрешите его в tailnet по кнопке")
        job = ts.Job(ts.funnel_command(self.app_api.port), self.paths.run / "tailscale-funnel.log",
                     self.spawn)
        self._ts_jobs["funnel"] = job
        self._wait_job(job, lambda: False)
        code = job.code()
        if code not in (None, 0):
            lines = [line for line in job.text().splitlines() if line.strip()]
            return actions.Outcome(
                1, "tailscale funnel: " + (lines[-1] if lines else f"код {code}"))
        managed.set_tailscale_funnel(store_path, name)
        self._wake()
        self._event("Tailscale: приложение на телефоне — Funnel включён")
        if code is None:
            return actions.Outcome(0, "Осталось разрешить Funnel в tailnet", (
                "Нажмите «Разрешить Funnel в tailnet» и подтвердите в консоли Tailscale — "
                "дальше всё заработает само",))
        return actions.Outcome(0, "Funnel включён: приложение на телефоне достучится до шлюза", (
            "Адрес открыт в интернет, но войти можно только с привязанного телефона",))

    # --- телефоны (А1) --------------------------------------------------------------

    def _phones_card(self) -> dict:
        public = self.cfg.managed.tailscale_funnel
        pairing = self.phones.pairing()
        listing = self.phones.listing()
        names = {phone.id: phone.name for phone in listing}
        job = self._ts_job("funnel")
        waiting = job is not None and job.code() is None
        link = (f"xgw://pair?u=https://{public}&c={pairing['code']}"
                if pairing["code"] and public and not waiting else "")
        return {
            "funnel": bool(public), "waiting": waiting,
            "enable_url": ts.find_url(job.text()) if waiting and job is not None else "",
            "available": self.app_api is not None,
            "pairing": {
                # Ссылка — та же, что в QR: её же берут стенд и программа испытаний.
                "link": link, "qr": qr.encode(link) if link else [],
                "until": pairing["until"] if link else None,
                "paired": names.get(pairing["paired"], ""),
            },
            "list": [
                {"id": phone.id, "name": phone.name, "paired": phone.paired, "seen": phone.seen}
                for phone in listing
            ],
        }

    def _phone_action(self, step: str, body: dict, store_path: Path) -> actions.Outcome:
        if step == "pair":
            if self.app_api is None:
                return actions.Outcome(1, "API приложения не запущен — подробности в журнале XGW")
            if not self.cfg.managed.tailscale_funnel:
                # Одна кнопка для заказчика: Funnel включается тут же.
                outcome = self._tailscale("funnel", {"on": True}, store_path)
                if not outcome.ok:
                    return outcome
            self.phones.new_code()
            job = self._ts_job("funnel")
            if job is not None and job.code() is None:
                return actions.Outcome(0, "Осталось разрешить Funnel в tailnet", (
                    "Нажмите «Разрешить Funnel в tailnet» и подтвердите в консоли Tailscale — "
                    "QR-код появится сам",))
            return actions.Outcome(0, "Наведите камеру приложения XGW на QR-код", (
                "Код действует 10 минут и подходит один раз",))
        if step == "cancel":
            self.phones.cancel()
            return actions.Outcome(0, "QR-код убран")
        identifier = body.get("id")
        if not isinstance(identifier, str):
            return actions.Outcome(2, "ожидается id телефона")
        names = {phone.id: phone.name for phone in self.phones.listing()}
        if identifier not in names:
            return actions.Outcome(2, "такого телефона нет — обновите страницу")
        if step == "rename":
            name = body.get("name")
            if not isinstance(name, str) or not name.strip():
                return actions.Outcome(2, "ожидается имя телефона")
            self.phones.rename(identifier, name)
            return actions.Outcome(0, "Телефон переименован")
        if step == "revoke":
            self.phones.revoke(identifier)
            self._event(f"телефон «{names[identifier]}» отвязан")
            return actions.Outcome(0, f"Телефон «{names[identifier]}» отвязан", (
                "Приложение на нём больше не войдёт: привяжите заново, если нужно",))
        return actions.Outcome(2, "нет такого действия")

    # --- действия -----------------------------------------------------------------

    def _wake(self) -> None:
        """Настройки изменены: панель показывает их сразу, а демон перечитает, как
        только закончит текущий шаг."""
        try:
            self.cfg, _warnings = config.load(self.config_path)
        except config.ConfigError as exc:
            self.log.error("%s — панель показывает прежние настройки", exc)
        if self.daemon is not None:
            self.daemon.poke.set()

    def _set_servers(self, body: dict, store_path: Path) -> actions.Outcome:
        """Включить, отключить или убрать серверы — по отпечаткам."""
        chosen, mode = body.get("fingerprints"), body.get("mode")
        if (
            mode not in managed.SERVER_MODES or not isinstance(chosen, list) or not chosen
            or len(chosen) > managed.MAX_SERVERS
            or not all(isinstance(item, str) for item in chosen)
        ):
            return actions.Outcome(2, "ожидается список серверов и действие")
        _snapshot, _xray_ok, members, spares = self._core(time.time())
        rows, gone = self._servers(members, spares)
        names = {row["fingerprint"]: row["name"] for row in [*rows, *gone]}
        if any(item not in names for item in chosen):
            return actions.Outcome(2, "такого сервера в списке нет — обновите страницу")
        notes: tuple[str, ...] = ()
        active = [row for row in rows if row["status"] in ("member", "spare", "waiting")]
        if mode != "enabled" and all(row["fingerprint"] in chosen for row in active):
            # Без единого сервера собрать конфиг нельзя, и ядро осталось бы на прежних.
            if len(chosen) == 1 or not active:
                return actions.Outcome(
                    2, "так не останется ни одного включённого сервера, и VPN работать не "
                       "сможет. Оставьте хотя бы один либо сначала добавьте другую подписку",
                )
            kept = next((row for row in active if row.get("selected")), active[0])
            chosen = [item for item in chosen if item != kept["fingerprint"]]
            notes = (
                f"«{kept['name']}» оставлен включённым, чтобы VPN не остался без серверов. "
                "Включите нужные — и отключите его отдельно",
            )
        if not managed.set_servers(store_path, chosen, mode):
            return actions.Outcome(0, "Ничего не изменилось")
        one, many = _SERVER_WORDS[mode]
        returned = {row["fingerprint"] for row in gone}
        if mode == "enabled" and all(item in returned for item in chosen):
            one, many = "возвращён в список", "возвращено в список"
        if len(chosen) == 1:
            text = f"сервер «{names[chosen[0]]}» {one}"
        else:
            text = f"серверов {many}: {len(chosen)}"
        self._event(text)
        self._wake()
        return actions.Outcome(0, text, notes)

    def _set_core(self, body: dict, store_path: Path) -> actions.Outcome:
        """Ядро сервера: Авто, только Xray или только sing-box — по отпечатку."""
        fingerprint, core = body.get("fingerprint"), body.get("core")
        if not isinstance(fingerprint, str) or core not in ("auto", "xray", "sing-box"):
            return actions.Outcome(2, "ожидается сервер и ядро: auto, xray или sing-box")
        outcome = actions.set_core(self.paths, store_path, fingerprint, core)
        if outcome.ok:
            self._event(outcome.text.split(". ")[0])
            self._wake()
        return outcome

    def _set_priority(self, body: dict, store_path: Path) -> actions.Outcome:
        """Приоритет серверов — высокий, средний или низкий — по отпечаткам."""
        chosen, level = body.get("fingerprints"), body.get("level")
        if (
            level not in priority.LEVELS or not isinstance(chosen, list) or not chosen
            or len(chosen) > managed.MAX_SERVERS
            or not all(isinstance(item, str) for item in chosen)
        ):
            return actions.Outcome(2, "ожидается список серверов и уровень: high, medium или low")
        _snapshot, _xray_ok, members, spares = self._core(time.time())
        rows, _gone = self._servers(members, spares)
        names = {row["fingerprint"]: row["name"] for row in rows}
        if any(item not in names for item in chosen):
            return actions.Outcome(2, "такого сервера в списке нет — обновите страницу")
        if not managed.set_priority(store_path, chosen, level):
            return actions.Outcome(0, "Ничего не изменилось")
        word = priority.NAMES[level]
        if len(chosen) == 1:
            text = f"приоритет сервера «{names[chosen[0]]}»: {word}"
        else:
            text = f"приоритет серверов ({len(chosen)}): {word}"
        self._event(text)
        self._wake()
        return actions.Outcome(0, text[:1].upper() + text[1:], (
            "В работе — серверы самого высокого уровня, на котором есть живые; "
            "уровнем ниже шлюз пользуется, только когда живых выше нет",
        ))

    def _set_device(self, body: dict, store_path: Path) -> actions.Outcome:
        """Пустить устройство мимо VPN (bypass: true) или вернуть в VPN (false).

        Шлюз узнаёт устройство по адресу, поэтому его адрес закрепляется статической
        арендой DHCP. Сеть меняется кодом `xgw apply` — правила проверяются до
        загрузки; если сеть изменение не приняла, прежний список возвращается."""
        mac, bypass = managed.normalize_mac(body.get("mac")), body.get("bypass")
        if mac is None or not isinstance(bypass, bool):
            return actions.Outcome(2, "ожидается устройство и bypass: true или false")
        problem = self.root_problem()
        if problem:
            return actions.Outcome(1, problem)
        cfg = self.cfg
        gateway = lan.gateway(cfg)
        if not lan.lan_interface(cfg) or gateway is None:
            return actions.Outcome(2, "сеть для устройств не настроена (network.lan_if)")
        mine = mac in cfg.managed.devices
        listed = [host.strip().lower().replace("-", ":") for host in cfg.network.bypass_hosts]
        if not bypass:
            if not mine:
                if mac in listed:
                    return actions.Outcome(
                        2, "Это устройство мимо VPN по config.toml: уберите его из "
                           "network.bypass_hosts там",
                    )
                return actions.Outcome(0, "Ничего не изменилось")
            leases = {lease.mac: lease for lease in lan.parse_leases(cfg)[0]}
            label = (leases[mac].name if mac in leases else "") or mac
            return self._apply_devices(
                store_path,
                lambda: managed.set_device(store_path, mac, "", "", bypass=False),
                f"Устройство «{label}» снова идёт через VPN", (),
            )
        if mine:
            return actions.Outcome(0, "Ничего не изменилось")
        found = {device["mac"]: device for device in dnsmasq.read_leases(self.paths)}.get(mac)
        if found is None:
            return actions.Outcome(2, "такого устройства в сети нет — обновите страницу")
        if mac in listed or found["ip"] in lan.bypass_addresses(cfg)[0]:
            return actions.Outcome(0, "Это устройство уже мимо VPN: так задано в config.toml")
        try:
            address = ipaddress.IPv4Address(found["ip"])
        except ValueError:
            return actions.Outcome(2, "у устройства нет адреса IPv4")
        if address not in gateway.network or address == gateway.ip:
            return actions.Outcome(2, "адрес устройства вне сети шлюза")
        name = found["name"] if lan.valid_hostname(found["name"]) else ""
        return self._apply_devices(
            store_path,
            lambda: managed.set_device(store_path, mac, found["ip"], name, bypass=True),
            f"Устройство «{found['name'] or mac}» идёт мимо VPN",
            ("Его трафик не защищён VPN: если Xray остановится, оно по-прежнему выходит в "
             "интернет напрямую",),
        )

    def _apply_devices(
        self, store_path: Path, change: Callable[[], bool], done: str, notes: tuple[str, ...]
    ) -> actions.Outcome:
        previous = managed.load(store_path)[0]["devices"]
        if not change():
            return actions.Outcome(0, "Ничего не изменилось")
        problems: list[str] = []
        try:
            new_cfg, _warnings = config.load(self.config_path)
        except config.ConfigError as exc:
            new_cfg, problems = None, [str(exc)]
        if new_cfg is not None:
            _done, problems = actions.apply_network(
                new_cfg, self.paths, self.capture_factory(new_cfg, self.paths, logger=self.log),
                logger=self.log, runner=self.runner,
            )
        if problems:
            managed.replace_devices(store_path, previous)
            with contextlib.suppress(config.ConfigError):
                old_cfg, _warnings = config.load(self.config_path)
                actions.apply_network(
                    old_cfg, self.paths,
                    self.capture_factory(old_cfg, self.paths, logger=self.log),
                    logger=self.log, runner=self.runner,
                )
            return actions.Outcome(
                1, "Сеть не приняла изменение, прежние настройки возвращены: " + "; ".join(problems)
            )
        self._event(done)
        self._wake()
        return actions.Outcome(0, done, notes)

    def _telegram(self, step: str, body: dict, store_path: Path) -> actions.Outcome:
        """Подключение бота: токен → код → «/start КОД» в Telegram; отключение."""
        bot, cfg = self.bot, self.cfg
        if bot is None:
            return actions.Outcome(1, "бот Telegram ещё не запущен — повторите через минуту")
        if cfg.notify.telegram_bot_token and not cfg.managed.telegram:
            return actions.Outcome(
                2, "Бот задан в config.toml: менять его можно только там "
                   "(notify.telegram_bot_token)",
            )
        if step == "connect":
            token = managed.check_bot_token(body.get("token"))
            managed.set_telegram(store_path, token)  # прежний чат при смене бота не нужен
            self._wake()
            bot.configure(self.cfg, self.daemon, bot.mark)
            bot.new_code(token)
            self._event("бот Telegram: токен сохранён, жду подключения чата")
            return actions.Outcome(0, "Токен сохранён. Откройте бота в Telegram и отправьте код")
        if step == "code":
            if not cfg.managed.telegram or cfg.notify.telegram_chat_id:
                return actions.Outcome(2, "чат уже подключён — сначала отключите бота")
            bot.new_code(cfg.notify.telegram_bot_token)
            return actions.Outcome(0, "Новый код готов")
        if step == "disconnect":
            managed.set_telegram(store_path, "")
            bot.forget()
            self._wake()
            bot.configure(self.cfg, self.daemon, bot.mark)
            self._event("бот Telegram отключён")
            return actions.Outcome(0, "Бот отключён")
        return actions.Outcome(2, "нет такого действия")

    def _config_names(self) -> set[str]:
        """Имена подписок, вписанных в config.toml: панель их не трогает."""
        mine = set(self.cfg.managed.subscriptions)
        return {sub.name for sub in self.cfg.subscriptions if sub.name not in mine}

    def act(self, name: str, body: dict) -> dict:
        """Выполняет действие и возвращает {"ok", "text", "notes"}."""
        with self._lock:
            try:
                outcome = self._act(name, body)
            except managed.ManagedError as exc:
                outcome = actions.Outcome(2, str(exc))
            except OSError as exc:
                outcome = actions.Outcome(1, f"не удалось записать настройки: {exc}")
        self._selecting = (0.0, [])
        return {
            "ok": outcome.ok,
            "text": masking.mask_text(outcome.text),
            "notes": [masking.mask_text(note) for note in outcome.notes],
        }

    def _act(self, name: str, body: dict) -> actions.Outcome:
        cfg, paths = self.cfg, self.paths
        store_path = managed.path_for(self.config_path)
        if name == "power":
            problem = self.root_problem()
            if problem:
                return actions.Outcome(1, problem)
            if body.get("on") is True:
                return actions.enable_checked(cfg, paths, self._capture())
            if body.get("on") is False:
                return actions.disable(cfg, paths, self._capture())
            return actions.Outcome(2, "ожидается on: true или false")
        if name == "pin":
            # Панель выбирает сервер бессрочно, как клиенты VPN; срок — для совместимости.
            tag, ttl = body.get("tag"), body.get("ttl", pinning.FOREVER)
            if not isinstance(tag, str) or ttl not in (pinning.FOREVER, *PIN_TTLS):
                return actions.Outcome(
                    2, "ожидается тег сервера и срок: " + ", ".join((pinning.FOREVER, *PIN_TTLS)),
                )
            return actions.pin(cfg, paths, tag, ttl)
        if name == "unpin":
            return actions.unpin(cfg, paths)
        if name == "add":
            return self._add(body, store_path)
        if name == "servers":
            return self._set_servers(body, store_path)
        if name == "priority":
            return self._set_priority(body, store_path)
        if name == "core":
            return self._set_core(body, store_path)
        if name == "device":
            return self._set_device(body, store_path)
        if name.startswith("telegram/"):
            return self._telegram(name.removeprefix("telegram/"), body, store_path)
        if name.startswith("tailscale/"):
            return self._tailscale(name.removeprefix("tailscale/"), body, store_path)
        if name.startswith("phones/"):
            return self._phone_action(name.removeprefix("phones/"), body, store_path)
        if name == "subscription/remove":
            sub = body.get("name")
            if not isinstance(sub, str) or sub not in cfg.managed.subscriptions:
                return actions.Outcome(
                    2, "эту подписку панель убрать не может: она вписана в config.toml"
                )
            managed.remove_subscription(store_path, sub)
            SubscriptionCache(paths.cache_dir).forget(sub)
            self._event(f"подписка «{sub}» убрана из панели")
            self._wake()
            return actions.Outcome(0, f"Подписка «{sub}» убрана")
        if name == "subscription/edit":
            sub = body.get("name")
            if not isinstance(sub, str) or sub not in cfg.managed.subscriptions:
                return actions.Outcome(
                    2, "эту подписку панель изменить не может: она вписана в config.toml"
                )
            user_agent = body.get("user_agent")
            headers = body.get("headers")
            if user_agent is not None and not isinstance(user_agent, str):
                return actions.Outcome(2, "user_agent должен быть строкой")
            if headers is not None and not isinstance(headers, dict):
                return actions.Outcome(2, "headers должен быть объектом")
            managed.update_subscription(
                store_path, sub,
                user_agent=user_agent if user_agent is not None else None,
                headers=headers if headers is not None else None,
            )
            SubscriptionCache(paths.cache_dir).forget(sub)
            self._event(f"подписка «{sub}» изменена в панели")
            self._wake()
            return actions.Outcome(0, f"Подписка «{sub}» изменена — получаю серверы…")
        if name == "link/remove":
            identifier = body.get("id")
            if not isinstance(identifier, str) or not managed.remove_link(store_path, identifier):
                return actions.Outcome(
                    2, "эту ссылку панель убрать не может: она вписана в config.toml"
                )
            self._event("ссылка сервера убрана из панели")
            self._wake()
            return actions.Outcome(0, "Ссылка сервера убрана")
        if name == "sticky":
            if not isinstance(body.get("on"), bool):
                return actions.Outcome(2, "ожидается on: true или false")
            if managed.set_sticky(store_path, body["on"]):
                self._event(
                    "основной сервер включён в панели" if body["on"]
                    else "основной сервер выключен в панели: сервер выбирает ядро по задержке"
                )
                self._wake()
            if body["on"]:
                return actions.Outcome(
                    0, "Основной сервер включён: весь трафик пойдёт через самый быстрый"
                )
            return actions.Outcome(0, "Основной сервер выключен: сервер выбирает ядро")
        if name in ("refresh", "scan", "speed"):
            if self.daemon is None:
                return actions.Outcome(1, "демон XGW ещё не готов — повторите через минуту")
            if name == "speed":
                if not cfg.speed.sticky:
                    return actions.Outcome(2, "замер скорости выключен: включите основной сервер")
                if not cfg.speed.every_hours:
                    return actions.Outcome(2, "замер скорости выключен: speed.every_hours = 0")
                self.daemon.request_speed()
                return actions.Outcome(0, "Замеряю скорость серверов в работе…")
            if name == "refresh":
                if not engine.has_sources(cfg):
                    return actions.Outcome(2, "обновлять нечего: подписок нет")
                self.daemon.request_refresh()
                return actions.Outcome(0, "Обновляю подписки…")
            self.daemon.request_scan()
            return actions.Outcome(0, "Проверяю запасные серверы…")
        return actions.Outcome(2, "нет такого действия")

    def _add(self, body: dict, store_path: Path) -> actions.Outcome:
        """Вставленный текст: адрес подписки либо ссылки серверов."""
        text = body.get("text")
        name = body.get("name") or ""
        if not isinstance(text, str) or not isinstance(name, str) or not text.strip():
            return actions.Outcome(2, "вставьте адрес подписки или ссылку сервера")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) == 1 and lines[0].lower().startswith(("http://", "https://")):
            user_agent = body.get("user_agent") if isinstance(body.get("user_agent"), str) else ""
            headers = body.get("headers") if isinstance(body.get("headers"), dict) else {}
            added = managed.add_subscription(
                store_path, lines[0], name, taken=self._config_names(),
                user_agent=user_agent, headers=headers,
            )
            self._event(f"подписка «{added}» добавлена из панели")
            self._wake()
            return actions.Outcome(0, f"Подписка «{added}» добавлена — получаю серверы…")
        if any(line.lower().startswith(_LINK_SCHEMES) for line in lines):
            mine = set(self.cfg.managed.links)
            taken = {link for link in self.cfg.manual.links if link not in mine}
            count = managed.add_links(store_path, "\n".join(lines), taken=taken)
            if not count:
                return actions.Outcome(2, "эти ссылки уже добавлены")
            self._event(f"ссылок серверов добавлено из панели: {count}")
            self._wake()
            return actions.Outcome(0, f"Добавлено серверов: {count}")
        return actions.Outcome(
            2, "не похоже ни на адрес подписки (https://…), ни на ссылку сервера "
               "(vless://, vmess://, trojan://, ss://)",
        )

    def _event(self, text: str) -> None:
        try:
            with actions.open_store(self.paths) as store:
                store.add_event("panel", text)
        except (OSError, sqlite3.Error) as exc:
            self.log.error("событие не записано: %s", exc)

    # --- HTTP ---------------------------------------------------------------------

    def _cookie(self) -> str:
        return hmac.new(self.token.encode("utf-8"), b"xgw-panel", hashlib.sha256).hexdigest()

    def _tailnet_host(self) -> str:
        """Host панели по tailnet: только пока Serve включён из панели (флаг в panel.json).
        Serve приходит на 127.0.0.1 и передаёт Host, с которым открыта страница."""
        name = self.cfg.managed.tailscale_serve
        return f"{name}:{ts.SERVE_PORT}" if name else ""

    def _hosts(self) -> set[str]:
        hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        tailnet = self._tailnet_host()
        if tailnet:
            hosts.add(tailnet)
        return hosts

    def _authorized(self, handler: BaseHTTPRequestHandler) -> bool:
        expected = self._cookie().encode("ascii")
        for part in (handler.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == COOKIE and hmac.compare_digest(value.encode("utf-8", "replace"), expected):
                return True
        return False

    def handle(self, handler: BaseHTTPRequestHandler, method: str) -> None:
        body = method != "HEAD"
        try:
            self._route(handler, method, body)
        except Refused as exc:
            self._text(handler, exc.code, str(exc) + "\n", body)

    def _route(self, handler: BaseHTTPRequestHandler, method: str, body: bool) -> None:
        host = (handler.headers.get("Host") or "").strip().lower()
        if host not in self._hosts():
            raise Refused(
                HTTPStatus.FORBIDDEN,
                f"Панель открывается только по адресу http://127.0.0.1:{self.port}/",
            )
        url = urlsplit(handler.path)
        if method == "POST":
            self._post(handler, url.path, host)
            return
        if url.path in _STATIC:
            name, content_type = _STATIC[url.path]
            self._file(handler, name, content_type, body)
            return
        query = parse_qs(url.query)
        given = (query.get("token") or [""])[0]
        once = (query.get("login") or [""])[0]  # одноразовый код (new_login)
        if given or once:
            if not self.token or not (
                hmac.compare_digest(given.encode("utf-8"), self.token.encode("utf-8"))
                if given else use_login(self.paths, once)
            ):
                time.sleep(0.5)  # перебор токена не должен быть быстрым
                self._file(handler, "login.html", "text/html; charset=utf-8", body,
                           code=HTTPStatus.FORBIDDEN)
                return
            # Вход переезжает в cookie, токен или код уходит из адресной строки и истории.
            # По tailnet страница открыта по https — cookie туда же и только по https.
            secure = "; Secure" if host == self._tailnet_host() else ""
            handler.send_response(HTTPStatus.SEE_OTHER)
            handler.send_header("Location", "/")
            handler.send_header(
                "Set-Cookie",
                f"{COOKIE}={self._cookie()}; Path=/; HttpOnly; SameSite=Strict; "
                f"Max-Age=31536000{secure}",
            )
            handler.send_header("Cache-Control", "no-store")
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        authorized = bool(self.token) and self._authorized(handler)
        if url.path == "/":
            self._file(
                handler, "index.html" if authorized else "login.html",
                "text/html; charset=utf-8", body,
            )
        elif url.path == "/api/state":
            if not authorized:
                raise Refused(HTTPStatus.UNAUTHORIZED, "Нужен вход по токену")
            self._json(handler, HTTPStatus.OK, self.state(), body)
        else:
            raise Refused(HTTPStatus.NOT_FOUND, "Нет такой страницы")

    @staticmethod
    def _read_body(handler: BaseHTTPRequestHandler) -> bytes | None:
        """Тело запроса; None — оно больше допустимого.

        Читается до любых проверок: если ответить отказом, не дочитав запрос,
        соединение оборвётся раньше, чем браузер получит ответ.
        """
        try:
            length = int(handler.headers.get("Content-Length") or "0")
        except ValueError as exc:
            raise Refused(HTTPStatus.BAD_REQUEST, "Неверная длина запроса") from exc
        if length < 0:
            raise Refused(HTTPStatus.BAD_REQUEST, "Неверная длина запроса")
        if length <= MAX_BODY:
            return handler.rfile.read(length)
        left = min(length, MAX_DRAIN)
        while left > 0:
            chunk = handler.rfile.read(min(left, 65536))
            if not chunk:
                break
            left -= len(chunk)
        handler.close_connection = True
        return None

    def _post(self, handler: BaseHTTPRequestHandler, path: str, host: str) -> None:
        data = self._read_body(handler)
        if not self.token or not self._authorized(handler):
            raise Refused(HTTPStatus.UNAUTHORIZED, "Нужен вход по токену")
        # Запрос должен прийти со страницы самой панели: заголовок, которого у
        # формы на чужом сайте быть не может, и источник — тот же адрес.
        origin = handler.headers.get("Origin")
        site = handler.headers.get("Sec-Fetch-Site")
        scheme = "https" if host == self._tailnet_host() else "http"
        if (
            handler.headers.get(HEADER) != "1"
            or (origin is not None and origin.lower() != f"{scheme}://{host}")
            or (site is not None and site.lower() != "same-origin")
        ):
            raise Refused(HTTPStatus.FORBIDDEN, "Запрос не со страницы панели")
        if not path.startswith("/api/"):
            raise Refused(HTTPStatus.NOT_FOUND, "Нет такого действия")
        if data is None:
            raise Refused(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Запрос слишком большой")
        try:
            payload = json.loads(data or b"{}")
        except (ValueError, UnicodeDecodeError) as exc:
            raise Refused(HTTPStatus.BAD_REQUEST, "Ожидается JSON") from exc
        if not isinstance(payload, dict):
            raise Refused(HTTPStatus.BAD_REQUEST, "Ожидается объект JSON")
        self._json(handler, HTTPStatus.OK, self.act(path[len("/api/"):], payload), True)

    # --- ответы -------------------------------------------------------------------

    def _file(
        self, handler, name: str, content_type: str, body: bool,
        *, code: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        try:
            data = (UI_DIR / name).read_bytes()
        except OSError as exc:
            raise Refused(HTTPStatus.INTERNAL_SERVER_ERROR, f"нет файла панели {name}") from exc
        self._send(handler, code, content_type, data, body)

    def _text(self, handler, code: HTTPStatus, text: str, body: bool) -> None:
        self._send(handler, code, "text/plain; charset=utf-8", text.encode("utf-8"), body)

    def _json(self, handler, code: HTTPStatus, payload: dict, body: bool) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(handler, code, "application/json; charset=utf-8", data, body)

    @staticmethod
    def _send(handler, code: HTTPStatus, content_type: str, data: bytes, body: bool) -> None:
        handler.send_response(code)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Referrer-Policy", "no-referrer")
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("X-Frame-Options", "DENY")
        handler.send_header("Content-Security-Policy", _CSP)
        handler.end_headers()
        if body:
            handler.wfile.write(data)
