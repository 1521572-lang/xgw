"""Панель управления: http://127.0.0.1:8781/ — графический интерфейс XGW в браузере.

Что умеет: включить и выключить VPN (то же, что `xgw enable` и `xgw disable`),
показать серверы каждой подписки с задержками, закрепить один из них, отключить
сервер или убрать его из списка, добавить и убрать подписку или ссылку сервера,
обновить подписки и проверить запасные серверы.

Безопасность:
  * слушает только 127.0.0.1 — из сети панель не открыть;
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
import json
import secrets
import sqlite3
import threading
import time
from collections import Counter
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .. import __version__, actions, config, engine, log, managed, masking
from ..config import Config
from ..generator import validate
from ..generator.builder import BALANCER_TAG
from ..net import dnsmasq, lan
from ..net.capture import Capture
from ..parsers.common import parse_links_text
from ..paths import Paths, atomic_write_text
from ..store import SubscriptionCache
from . import status

COOKIE = "xgw_panel"
HEADER = "X-XGW-Panel"
MAX_BODY = 65536
MAX_DRAIN = 1 << 20  # сколько лишнего дочитать, прежде чем отказать
SELECT_TTL = 3.0  # как долго помнить ответ ядра о выбранном сервере
EVENTS = 30
PIN_TTLS = ("10m", "1h", "6h", "24h")
MANUAL = "manual"  # источник серверов, заданных отдельными ссылками
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
    ) -> None:
        self.paths = paths
        self.config_path = Path(config_path)
        self.token = token
        self.port = port
        self.log = logger or log.get_logger("panel")
        self.root_problem = root_problem
        self.capture_factory = capture_factory
        self.cfg = Config()
        self.daemon = None
        self._lock = threading.Lock()  # одно действие за раз
        self._selecting: tuple[float, list[str]] = (0.0, [])
        self._labels: dict[str, str] = {}
        self._server: _Server | None = None
        self._thread: threading.Thread | None = None

    @classmethod
    def from_config(cls, cfg: Config, paths: Paths, config_path: Path, **kwargs) -> Panel | None:
        """Панель по config.toml; None — она выключена ([panel] enabled = false)."""
        if not cfg.panel.enabled:
            return None
        panel = cls(paths, config_path, ensure_token(paths), port=cfg.panel.port, **kwargs)
        panel.configure(cfg)
        return panel

    def configure(self, cfg: Config, daemon=None) -> None:
        """Новые настройки и новый демон после перечитывания конфига."""
        self.cfg = cfg
        self.daemon = daemon

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
            target=self._server.serve_forever, name="xgw-panel", daemon=True
        )
        self._thread.start()
        self.log.info("панель управления слушает 127.0.0.1, порт %d (по токену)", self.port)

    def stop(self) -> None:
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
        rows = self._db("SELECT value FROM meta WHERE key = 'pin'")
        try:
            pin = json.loads(rows[0]["value"] or "null") if rows else None
        except json.JSONDecodeError:
            return None
        if isinstance(pin, dict) and pin.get("tag") and pin.get("until", 0) > now:
            return {"tag": str(pin["tag"]), "until": float(pin["until"])}
        return None

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

    def _servers(self, members: list[dict], spares: list[dict]) -> tuple[list[dict], list[dict]]:
        """Все серверы подписок и отдельно — убранные из списка.

        Список ведёт демон (inventory.json): в нём и серверы, которых в конфиге
        Xray нет, — отключённые, отсеянные фильтрами, ещё не применённые.
        """
        disabled, removed = set(self.cfg.managed.disabled), set(self.cfg.managed.removed)
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
            }
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
                )
            elif role == "spare":
                row.update(
                    status="spare", tag=entry.get("tag"), verdict=entry.get("verdict"),
                    scanned=entry.get("scanned"),
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
        return snapshot, xray_ok, members, spares

    def state(self) -> dict:
        cfg, now = self.cfg, time.time()
        snapshot, xray_ok, members, spares = self._core(now)
        xray = snapshot.get("xray") or {}
        capture = self._capture()
        info = capture.describe(check=False)
        loaded = (snapshot.get("capture") or {}).get("loaded")

        servers, gone = self._servers(members, spares)
        # Сколько серверов дала подписка: вместе с отключёнными, без служебных записей.
        per_source = Counter(row["source"] for row in servers if row["status"] != "skipped")
        quotas, errors = snapshot.get("quota") or {}, snapshot.get("sub_errors") or {}
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
            })
        links = [
            {
                "id": managed.link_id(link),
                "label": self._link_label(link),
                "managed": link in cfg.managed.links,
            }
            for link in cfg.manual.links
        ]

        bypass = set(info["bypass"])
        devices = []
        if info["lan_if"]:
            for device in dnsmasq.read_leases(self.paths):
                devices.append({**device, "bypass": device.get("ip") in bypass})
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
            "capture": {**info, "loaded": loaded},
            "power": self._power(info["mode"], xray_ok, bool(members)),
            "members": members,
            "spares": spares,
            "servers": servers,
            "removed": gone,
            "sources": sources,
            "pin": self._pin(now),
            "pin_ttls": list(PIN_TTLS),
            "subscriptions": subscriptions,
            "links": links,
            "lan": {
                "interface": info["lan_if"],
                "gateway": str(gateway.ip) if gateway and info["lan_if"] else "",
            },
            "devices": devices,
            "events": events,
            "budget": snapshot.get("budget") or {},
            "pending_restart": bool(snapshot.get("pending_restart")),
            "busy": {
                "refresh": bool(daemon is not None and daemon.refresh_pending),
                "scan": bool(daemon is not None and daemon.scan_pending),
            },
        }
        masked = masking.mask_obj(result)
        assert isinstance(masked, dict)
        return masked

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
                if engine.healthy_http_in(cfg) is None:
                    return actions.Outcome(
                        1, "Xray не отвечает — VPN не включён: иначе машина осталась бы "
                           "без интернета. Проверьте подписку и серверы",
                    )
                return actions.enable(cfg, paths, self._capture())
            if body.get("on") is False:
                return actions.disable(cfg, paths, self._capture())
            return actions.Outcome(2, "ожидается on: true или false")
        if name == "pin":
            tag, ttl = body.get("tag"), body.get("ttl")
            if not isinstance(tag, str) or ttl not in PIN_TTLS:
                return actions.Outcome(2, "ожидается тег сервера и срок: " + ", ".join(PIN_TTLS))
            return actions.pin(cfg, paths, tag, ttl)
        if name == "unpin":
            return actions.unpin(cfg, paths)
        if name == "add":
            return self._add(body, store_path)
        if name == "servers":
            return self._set_servers(body, store_path)
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
        if name == "link/remove":
            identifier = body.get("id")
            if not isinstance(identifier, str) or not managed.remove_link(store_path, identifier):
                return actions.Outcome(
                    2, "эту ссылку панель убрать не может: она вписана в config.toml"
                )
            self._event("ссылка сервера убрана из панели")
            self._wake()
            return actions.Outcome(0, "Ссылка сервера убрана")
        if name in ("refresh", "scan"):
            if self.daemon is None:
                return actions.Outcome(1, "демон XGW ещё не готов — повторите через минуту")
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
            added = managed.add_subscription(
                store_path, lines[0], name, taken=self._config_names()
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

    def _hosts(self) -> set[str]:
        return {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

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
        given = (parse_qs(url.query).get("token") or [""])[0]
        if given:
            if not self.token or not hmac.compare_digest(
                given.encode("utf-8"), self.token.encode("utf-8")
            ):
                time.sleep(0.5)  # перебор токена не должен быть быстрым
                self._file(handler, "login.html", "text/html; charset=utf-8", body,
                           code=HTTPStatus.FORBIDDEN)
                return
            # Токен переезжает в cookie и уходит из адресной строки и истории.
            handler.send_response(HTTPStatus.SEE_OTHER)
            handler.send_header("Location", "/")
            handler.send_header(
                "Set-Cookie",
                f"{COOKIE}={self._cookie()}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000",
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
        if (
            handler.headers.get(HEADER) != "1"
            or (origin is not None and origin.lower() != f"http://{host}")
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
