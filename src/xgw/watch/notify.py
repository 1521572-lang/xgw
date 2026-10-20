"""События и уведомления демона.

Каждое событие пишется в журнал и в SQLite (его видно в `xgw status`).
Уведомление наружу — одно на тип события не чаще min_interval_min. Канал
доставки — получатели `sinks`: рабочий стол активного пользователя. Без
получателей уведомление — запись в журнале уровня WARNING.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from .. import log, masking
from ..config import Config
from ..net import cmd
from ..store import Store

Sink = Callable[[str, str], None]  # (тип события, текст)

RUN_USER = Path("/run/user")
_GRAPHICAL = ("wayland", "x11", "mir")
# Заголовок уведомления по типу события.
TITLES = {
    "DEGRADED": "часть серверов недоступна",
    "ALL_DEAD": "все серверы недоступны",
    "WAN_DOWN": "нет связи с провайдером",
    "XRAY_DOWN": "Xray не отвечает",
    "LEAK": "трафик идёт мимо VPN",
    "leak": "трафик идёт мимо VPN",
    "PROBE_TARGET_UNREACHABLE": "не отвечает адрес проверки серверов (probe.url)",
    "probe": "адрес проверки серверов",
    "capture": "перехват трафика",
    "rotation": "замена сервера",
    "rollback": "откат конфига Xray",
    "apply": "применение конфига",
    "subscription": "подписка",
    "config": "конфиг",
    "budget": "трафик проверок",
    "xray": "Xray",
    "pin": "закрепление сервера",
    "priority": "серверы в работе",
    "RESERVE": "трафик идёт через резервный сервер",
    "reserve": "резервный сервер",
    "main": "основной сервер",
}
_URGENT = frozenset({"ALL_DEAD", "XRAY_DOWN", "LEAK", "leak", "capture", "rollback"})


def title(kind: str) -> str:
    return f"XGW: {TITLES.get(kind, kind)}"


def find_desktop_user(
    runner: cmd.Runner = cmd.run, run_user: Path = RUN_USER
) -> tuple[str, int] | None:
    """Пользователь графической сессии (из loginctl), предпочтительно активной.

    None — показывать некому: никто не вошёл либо сессии только текстовые и
    удалённые (у них нет службы уведомлений).
    """
    try:
        sessions = json.loads(runner(["loginctl", "list-sessions", "--json=short"]) or "[]")
    except (cmd.CommandError, json.JSONDecodeError):
        return None
    found: list[tuple[bool, str, int]] = []
    for session in sessions if isinstance(sessions, list) else []:
        if not isinstance(session, dict) or session.get("class", "user") != "user":
            continue  # экран входа, служебные сессии
        ident, user, uid = str(session.get("session", "")), session.get("user"), session.get("uid")
        if not ident or not isinstance(user, str) or not isinstance(uid, int):
            continue
        try:
            text = runner(["loginctl", "show-session", ident,
                           "-p", "Type", "-p", "Active", "-p", "Remote"])
        except cmd.CommandError:
            continue
        props = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
        if props.get("Type") not in _GRAPHICAL or props.get("Remote") == "yes":
            continue
        if not (run_user / str(uid) / "bus").exists():
            continue
        found.append((props.get("Active") == "yes", user, uid))
    if not found:
        return None
    _active, user, uid = max(found, key=lambda item: item[0])
    return user, uid


def desktop_sink(runner: cmd.Runner = cmd.run, run_user: Path = RUN_USER) -> Sink:
    """Уведомление на рабочий стол: notify-send от имени пользователя сессии."""

    def send(kind: str, text: str) -> None:
        found = find_desktop_user(runner, run_user)
        if found is None:
            return
        user, uid = found
        runner(
            [
                "runuser", "-u", user, "--", "env",
                f"DBUS_SESSION_BUS_ADDRESS=unix:path={(run_user / str(uid) / 'bus').as_posix()}",
                "notify-send", "--app-name=XGW", "--icon=network-vpn",
                f"--urgency={'critical' if kind in _URGENT else 'normal'}",
                title(kind), text,
            ],
            timeout=10.0,
        )

    return send


def build_sinks(cfg: Config, *, mark: int | None, runner: cmd.Runner = cmd.run) -> list[Sink]:
    sinks: list[Sink] = []
    if cfg.notify.desktop:
        sinks.append(desktop_sink(runner))
    return sinks


class Notifier:
    def __init__(
        self,
        db_file: Path,
        min_interval_min: int,
        *,
        sinks: Sequence[Sink] = (),
        logger=None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.db_file = db_file
        self.min_interval = max(0, min_interval_min) * 60.0
        self.sinks = list(sinks)
        self.log = logger or log.get_logger("notify")
        self.clock = clock
        self._last_sent: dict[str, float] = {}

    def event(self, kind: str, text: str, *, notify: bool = False) -> bool:
        """Записывает событие; при notify=True ещё и уведомляет. Возвращает True,
        если уведомление ушло (а не было придержано ограничителем частоты)."""
        text = masking.mask_text(text)
        send = notify and self._allowed(kind)
        (self.log.warning if send else self.log.info)("%s: %s", kind, text)
        try:
            store = Store(self.db_file)
            try:
                store.add_event(kind, text)
            finally:
                store.close()
        except Exception as exc:  # событие не должно ронять демон
            self.log.error("событие %s не записано: %s", kind, exc)
        if not send:
            return False
        for sink in self.sinks:
            try:
                sink(kind, text)
            except Exception as exc:
                self.log.error("уведомление %s не доставлено: %s", kind, exc)
        return True

    def _allowed(self, kind: str) -> bool:
        now = self.clock()
        last = self._last_sent.get(kind)
        if last is not None and now - last < self.min_interval:
            return False
        self._last_sent[kind] = now
        return True
