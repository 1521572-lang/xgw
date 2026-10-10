"""Перехват трафика целиком: правила nftables, маршрутизация по меткам, форвардинг.

Режимы:
  on   — перехват включён: LAN и (или) сама машина ходят через Xray;
  off  — снят командой `xgw disable`: сеть работает напрямую, шлюз остаётся роутером;
  open — снят демоном на время: Xray недоступен, а в конфиге fail_mode = "open";
  none — в конфиге перехват выключен (capture.lan = capture.local = false).

Выбор «включён/снят» хранится в /var/lib/xgw и переживает перезагрузку: по нему
правила загружает xgw-net.service. Временное снятие (open) — метка в /run.
Все операции идемпотентны и идут под файловой блокировкой.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

from .. import log
from ..config import Config
from ..paths import Paths, atomic_write_json, file_lock
from . import cmd, iprule, lan, nft, sysctl


class CaptureError(Exception):
    """Правила не загружены: нет прав, nft или ip, либо ядро их не приняло."""


class Capture:
    def __init__(
        self,
        cfg: Config,
        paths: Paths,
        *,
        runner: cmd.Runner = cmd.run,
        logger=None,
        proc_sys: Path = sysctl.PROC_SYS,
        time_uids: tuple[int, ...] | None = None,
    ) -> None:
        self.cfg = cfg
        self.paths = paths
        self.runner = runner
        self.log = logger or log.get_logger("net")
        self.proc_sys = proc_sys
        self.time_uids = time_uids
        self.state_file = paths.var / "capture.json"
        self.open_marker = paths.run / "capture-open"
        self._warned: set[str] = set()

    # --- что настроено ----------------------------------------------------------

    @property
    def lan_if(self) -> str:
        return lan.lan_interface(self.cfg)

    @property
    def capturing(self) -> bool:
        """В конфиге есть что перехватывать."""
        return self.cfg.capture.local or (self.cfg.capture.lan and bool(self.lan_if))

    @property
    def configured(self) -> bool:
        """Есть что загружать: перехват либо хотя бы LAN (шлюз как роутер)."""
        return self.capturing or bool(self.lan_if)

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
        """Явный выбор пользователя; None — ни enable, ни disable ещё не выполнялись."""
        value = self._state().get("enabled")
        return value if isinstance(value, bool) else None

    def wanted(self) -> bool:
        """Выбор пользователя: `xgw enable` (по умолчанию) или `xgw disable`."""
        return bool(self._state().get("enabled", True))

    def mode(self) -> str:
        if not self.capturing:
            return "none"
        if not self.wanted():
            return "off"
        return "open" if self.open_marker.exists() else "on"

    def rules(self, mode: str | None = None) -> nft.Rules:
        """Параметры правил для режима (по умолчанию — текущего)."""
        rules, warnings = nft.build_rules(
            self.cfg, capture=(mode or self.mode()) == "on", time_uids=self.time_uids
        )
        for warning in warnings:
            if warning not in self._warned:  # демон собирает правила на каждом шаге
                self._warned.add(warning)
                self.log.warning("%s", warning)
        return rules

    # --- действия ---------------------------------------------------------------

    def _lock(self):
        return file_lock(self.paths.run / "net.lock", timeout=30.0)

    def _load(self, mode: str) -> str:
        rules = self.rules(mode)
        mark, table = self.cfg.capture.mark_proxy, self.cfg.capture.route_table
        try:
            if rules.lan_if:
                self._forwarding_on()
            if rules.capture:
                # Сначала маршрут для помеченных пакетов, потом правила, которые метят.
                iprule.ensure(mark, table, self.runner)
                warnings = nft.apply(rules, self.runner)
            else:
                warnings = nft.apply(rules, self.runner)
                iprule.remove(mark, table, self.runner)
        except (cmd.CommandError, OSError) as exc:
            raise CaptureError(str(exc)) from exc
        for warning in warnings:
            self.log.warning("%s", warning)
        return mode

    def up(self) -> str:
        """Загружает правила текущего режима (после перезагрузки, после сбоя)."""
        with self._lock():
            return self._load(self.mode())

    def enable(self) -> str:
        with self._lock():
            mode = self._load("on" if self.capturing else "none")
            # Выбор запоминается, только когда правила действительно загружены.
            self._save(enabled=True)
            self.open_marker.unlink(missing_ok=True)
            return mode

    def disable(self) -> str:
        """Снимает перехват (prerouting, output, ip rule); форвардинг с
        маскарадингом остаётся — сеть работает напрямую."""
        with self._lock():
            mode = self._load("off" if self.capturing else "none")
            self._save(enabled=False)
            self.open_marker.unlink(missing_ok=True)
            return mode

    def open(self) -> str:
        """fail_mode = "open": временно снять перехват, выбор пользователя не трогая."""
        with self._lock():
            self.open_marker.parent.mkdir(parents=True, exist_ok=True)
            self.open_marker.touch()
            return self._load(self.mode())

    def close(self) -> str:
        """Вернуть перехват после временного снятия."""
        with self._lock():
            self.open_marker.unlink(missing_ok=True)
            return self._load(self.mode())

    def down(self) -> None:
        """Убирает всё, что XGW добавил в сеть: таблицы, правило, маршрут, форвардинг."""
        with self._lock():
            try:
                nft.delete(self.runner)
                iprule.remove(
                    self.cfg.capture.mark_proxy, self.cfg.capture.route_table, self.runner
                )
                self._forwarding_restore()
            except (cmd.CommandError, OSError) as exc:
                raise CaptureError(str(exc)) from exc
            self.open_marker.unlink(missing_ok=True)

    def _forwarding_on(self) -> None:
        before = sysctl.read(sysctl.IP_FORWARD, self.proc_sys)
        if before == "1":
            return
        if "ip_forward_before" not in self._state():
            self._save(ip_forward_before=before or "0")
        sysctl.write(sysctl.IP_FORWARD, "1", self.proc_sys)

    def _forwarding_restore(self) -> None:
        before = self._state().get("ip_forward_before")
        if before is None:
            return
        sysctl.write(sysctl.IP_FORWARD, str(before), self.proc_sys)
        self._save(ip_forward_before=None)

    # --- проверка ---------------------------------------------------------------

    def loaded(self) -> bool | None:
        """Соответствует ли ядро текущему режиму. None — узнать нельзя (нет прав)."""
        rules = self.rules()
        chains = nft.loaded_chains(self.runner)
        if chains is None:
            return None
        expected: set[str] = set()
        if rules.capture:
            expected.add("prerouting")
        if rules.capture_local:
            expected.add("output")
        if rules.lan_if:
            expected |= {"forward", "postrouting"}
        if not expected <= chains:
            return False
        if not rules.capture:
            return not chains & {"prerouting", "output"}
        with contextlib.suppress(cmd.CommandError):
            return iprule.present(
                self.cfg.capture.mark_proxy, self.cfg.capture.route_table, self.runner
            )
        return None

    def describe(self, *, check: bool = True) -> dict:
        """Сведения для `xgw status`."""
        rules = self.rules("on")
        return {
            "mode": self.mode(),
            "lan_if": rules.lan_if,
            "lan": rules.capture_lan,
            "local": rules.capture_local,
            "bypass": list(rules.bypass),
            "fail_mode": self.cfg.capture.fail_mode,
            "loaded": self.loaded() if check else None,
        }
