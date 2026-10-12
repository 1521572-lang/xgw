"""«Перехват» на Windows: системный прокси пользователя вместо правил ядра.

Тот же набор действий и режимов, что у net.capture.Capture (on, off, open, none), —
поэтому панель, бот, демон и команды `xgw enable` / `xgw disable` работают с ним без
изменений. Отличия по существу:

  * через Xray идут только программы, которые смотрят на системный прокси (браузеры и
    большинство обычных программ); остальные ходят напрямую, и запретить им это XGW на
    Windows не может;
  * прежние настройки прокси запоминаются при включении и возвращаются при выключении
    (в том числе PAC-файл: он сильнее ручного прокси и на время включения убирается);
  * пока VPN включён, прокси принадлежит XGW: изменённый кем-то ещё, он возвращается на
    ближайшем шаге демона. Выключают VPN кнопкой в панели, а не в настройках Windows;
  * fail-closed здесь означает «прокси по-прежнему указывает на Xray»: пока Xray не
    отвечает, программы, идущие через прокси, остаются без интернета, а не идут мимо.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from .. import log
from ..config import Config
from ..paths import Paths, atomic_write_json, file_lock
from . import winproxy
from .capture import CaptureError


class WinCapture:
    # Перехвата на уровне сети нет: обычный сокет самой машины идёт мимо прокси, и
    # проверка утечки таким сокетом всегда показывала бы «утечку».
    transparent = False
    reloaded_text = "системный прокси был изменён не XGW — возвращён"

    def __init__(
        self,
        cfg: Config,
        paths: Paths,
        *,
        logger=None,
        registry: winproxy.Registry | None = None,
        notify: Callable[[], None] | None = None,
        runner=None,
        **_linux_only: object,
    ) -> None:
        self.cfg = cfg
        self.paths = paths
        self.log = logger or log.get_logger("net")
        self._registry = registry
        self._notify = notify
        self.runner = runner
        self.state_file = paths.var / "capture.json"
        self.open_marker = paths.run / "capture-open"

    # --- что настроено ----------------------------------------------------------

    lan_if = ""  # сети за этой машиной нет: XGW на Windows защищает только её

    @property
    def capturing(self) -> bool:
        return self.cfg.capture.local

    @property
    def configured(self) -> bool:
        return self.capturing

    @property
    def port(self) -> int:
        return self.cfg.xray.http_port

    def _bind(self) -> None:
        """Реестр берётся при первом обращении: объект создают и там, где прокси не
        трогают (панель читает только режим), а отказ в доступе — ошибка действия."""
        if self._registry is None:
            self._registry, default_notify = winproxy.default_registry()
            self._notify = self._notify or default_notify
        elif self._notify is None:
            self._notify = lambda: None

    @property
    def registry(self) -> winproxy.Registry:
        self._bind()
        assert self._registry is not None
        return self._registry

    def notify(self) -> None:
        self._bind()
        assert self._notify is not None
        self._notify()

    # --- состояние --------------------------------------------------------------

    def _state(self) -> dict:
        try:
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return state if isinstance(state, dict) else {}

    def _save(self, **changes: object) -> None:
        state = self._state()
        for key, value in changes.items():
            if value is None:
                state.pop(key, None)
            else:
                state[key] = value
        atomic_write_json(self.state_file, state, mode=0o644)

    def choice(self) -> bool | None:
        value = self._state().get("enabled")
        return value if isinstance(value, bool) else None

    def wanted(self) -> bool:
        """Выбор пользователя. В отличие от шлюза, по умолчанию VPN выключен: прокси
        машины XGW меняет только после нажатия кнопки или `xgw enable`."""
        return self._state().get("enabled") is True

    def mode(self) -> str:
        if not self.capturing:
            return "none"
        if not self.wanted():
            return "off"
        return "open" if self.open_marker.exists() else "on"

    # --- действия ---------------------------------------------------------------

    def _lock(self):
        return file_lock(self.paths.run / "net.lock", timeout=30.0)

    def _our_address(self, current: winproxy.Settings, state: dict) -> bool:
        """В настройках стоит адрес XGW — нынешний или тот, что XGW записал раньше (порт
        могли сменить), — и нет PAC-файла. Включён ли при этом прокси, здесь не важно."""
        ours = (winproxy.target(self.port).server, state.get("proxy_server"))
        return not current.autoconfig and current.server in ours

    def _mine(self, current: winproxy.Settings, state: dict) -> bool:
        """Действует ли сейчас прокси, который поставил XGW."""
        return current.enable and self._our_address(current, state)

    def _apply(self, settings: winproxy.Settings) -> None:
        winproxy.write(self.registry, settings)
        try:
            self.notify()
        except winproxy.ProxyError as exc:
            # Настройки записаны; программы увидят их при следующем запуске.
            self.log.warning("программы не уведомлены о смене прокси: %s", exc)

    def _load(self, mode: str) -> str:
        try:
            current = winproxy.read(self.registry)
            state = self._state()
            if mode == "on":
                wanted = winproxy.target(self.port)
                if current != wanted:
                    if not self._our_address(current, state):
                        # Чужие настройки запоминаются — их вернёт выключение. Наш же
                        # адрес, выключенный в настройках Windows или с изменённым
                        # списком исключений, — не «прежние настройки»: запомненное
                        # до первого включения остаётся как было.
                        self._save(proxy_before=current.to_dict())
                    self._apply(wanted)
                    self._save(proxy_server=wanted.server)
            elif self._mine(current, state) or (
                "proxy_server" in state and self._our_address(current, state)
            ):
                before = winproxy.Settings.from_dict(state.get("proxy_before"))
                if self._mine(before, state):
                    before = winproxy.Settings()
                self._apply(before)
                self._save(proxy_before=None, proxy_server=None)
            elif "proxy_before" in state or "proxy_server" in state:
                # Прокси уже не наш (его сменили вручную) — возвращать нечего.
                self._save(proxy_before=None, proxy_server=None)
        except (winproxy.ProxyError, OSError) as exc:
            raise CaptureError(str(exc)) from exc
        return mode

    def up(self) -> str:
        with self._lock():
            return self._load(self.mode())

    def enable(self) -> str:
        with self._lock():
            mode = self._load("on" if self.capturing else "none")
            self._save(enabled=True)
            self.open_marker.unlink(missing_ok=True)
            return mode

    def disable(self) -> str:
        with self._lock():
            mode = self._load("off" if self.capturing else "none")
            self._save(enabled=False)
            self.open_marker.unlink(missing_ok=True)
            return mode

    def open(self) -> str:
        """fail_mode = "open": Xray недоступен — временно вернуть прежние настройки."""
        with self._lock():
            self.open_marker.parent.mkdir(parents=True, exist_ok=True)
            self.open_marker.touch()
            return self._load(self.mode())

    def close(self) -> str:
        with self._lock():
            self.open_marker.unlink(missing_ok=True)
            return self._load(self.mode())

    def down(self, **_linux_only: object) -> None:
        """Возвращает настройки прокси, какими они были до XGW (удаление программы).
        Выбор пользователя не меняется."""
        with self._lock():
            self._load("off")
            self.open_marker.unlink(missing_ok=True)

    # --- проверка ---------------------------------------------------------------

    def loaded(self) -> bool | None:
        """Соответствует ли системный прокси режиму. None — реестр не читается."""
        try:
            current = winproxy.read(self.registry)
        except winproxy.ProxyError:
            return None
        if self.mode() == "on":
            return current == winproxy.target(self.port)
        return not self._mine(current, self._state())

    def describe(self, *, check: bool = True) -> dict:
        return {
            "mode": self.mode(),
            "lan_if": "",
            "lan": False,
            "local": self.capturing,
            "bypass": [],
            "ipv6": False,
            "tun": False,
            "sysproxy": True,
            "proxy": winproxy.target(self.port).server,
            "fail_mode": self.cfg.capture.fail_mode,
            "loaded": self.loaded() if check else None,
        }
