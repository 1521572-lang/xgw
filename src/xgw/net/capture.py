"""Перехват трафика целиком: правила nftables, маршрутизация по меткам, форвардинг.

Режимы:
  on   — перехват включён: LAN и (или) сама машина ходят через Xray;
  off  — снят командой `xgw disable`: сеть работает напрямую, шлюз остаётся роутером;
  open — снят демоном на время: Xray недоступен, а в конфиге fail_mode = "open";
  none — в конфиге перехват выключен (capture.lan = capture.local = false).

Трафик самой машины попадает в Xray либо через TPROXY на lo (по умолчанию), либо
через постоянный TUN-интерфейс (capture.method = "tun", см. net/tun.py); сеть LAN
всегда через TPROXY. Интерфейс создаётся при включении перехвата и убирается только
командой `net down`: `xgw disable` и fail_mode = open снимают лишь правило и маршрут,
иначе Xray остался бы с оборванным интерфейсом и потребовал перезапуска.

Выбор «включён/снят» хранится в /var/lib/xgw и переживает перезагрузку: по нему
правила загружает xgw-net.service. Временное снятие (open) — метка в /run.
Все операции идемпотентны и идут под файловой блокировкой.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
from pathlib import Path

from .. import log
from ..config import Config
from ..paths import Paths, atomic_write_json, file_lock
from . import cmd, iprule, lan, nft, sysctl, tun


class CaptureError(Exception):
    """Правила не загружены: нет прав, nft или ip, либо ядро их не приняло."""


# Тег inbound'а перехвата в конфиге Xray (генератор, builder.py); у IPv6 — tproxy-in6.
TPROXY_TAG = "tproxy-in"


def capture_for(cfg: Config, paths: Paths, **kwargs):
    """Управление перехватом для этой системы: правила ядра (Linux) либо, при
    capture.method = "sysproxy", системный прокси Windows — с тем же набором действий."""
    if cfg.capture.sysproxy:
        from .wincapture import WinCapture

        return WinCapture(cfg, paths, **kwargs)
    return Capture(cfg, paths, **kwargs)


class Capture:
    # Перехват на уровне сети: обычный сокет самой машины тоже идёт через Xray, и
    # утечку можно проверить запросом без метки.
    transparent = True
    reloaded_text = "правила сети не были загружены — загружены заново"

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
        # Перехват не загружен, потому что в применённом конфиге Xray нет inbound
        # TPROXY: см. _load.
        self.tproxy_missing = False

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

    def ipv6_usable(self) -> bool:
        return sysctl.ipv6_usable(self.proc_sys)

    def rules(self, mode: str | None = None) -> nft.Rules:
        """Параметры правил для режима (по умолчанию — текущего)."""
        rules, warnings = nft.build_rules(
            self.cfg, capture=(mode or self.mode()) == "on", time_uids=self.time_uids
        )
        if rules.capture6 and not self.ipv6_usable():
            # Нечего перехватывать: утечки через IPv6 быть не может, а команды ip -6
            # и таблица ip6 в таком ядре не работают и сломали бы загрузку IPv4.
            rules = dataclasses.replace(rules, capture6=False)
            warnings.append("network.ipv6 = proxy, но IPv6 в ядре выключен: проксировать нечего")
        for warning in warnings:
            if warning not in self._warned:  # демон собирает правила на каждом шаге
                self._warned.add(warning)
                self.log.warning("%s", warning)
        return rules

    # --- действия ---------------------------------------------------------------

    def _lock(self):
        return file_lock(self.paths.run / "net.lock", timeout=30.0)

    def _families(self) -> tuple[int, ...]:
        return (4, 6) if self.ipv6_usable() else (4,)

    @staticmethod
    def _wanted(rules: nft.Rules, family: int) -> tuple[bool, bool]:
        """(локальная доставка для TPROXY, маршрут в TUN) для семейства адресов."""
        tproxy = rules.prerouting if family == 4 else rules.prerouting6
        return tproxy, rules.tun and (family == 4 or rules.capture6)

    def _routes_up(self, rules: nft.Rules) -> None:
        """Интерфейс, правила `ip rule` и маршруты, которые нужны текущим правилам."""
        cap = self.cfg.capture
        if rules.tun:
            tun.ensure(rules.tun_name, self.runner, self.proc_sys)
        for family in self._families():
            tproxy, via_tun = self._wanted(rules, family)
            if tproxy:
                iprule.ensure(cap.mark_proxy, cap.route_table, self.runner, family)
            if via_tun:
                iprule.ensure_tun(
                    cap.mark_proxy, cap.tun_route_table, self.runner, family, rules.tun_name
                )

    def _routes_down(self, rules: nft.Rules) -> None:
        """Правила `ip rule` и маршруты, которые текущим правилам не нужны (остались от
        другого режима, от ipv6 = proxy или от снятого перехвата)."""
        cap = self.cfg.capture
        for family in self._families():
            tproxy, via_tun = self._wanted(rules, family)
            if not tproxy:
                iprule.remove(cap.mark_proxy, cap.route_table, self.runner, family)
            if not via_tun:
                iprule.remove_tun(
                    cap.mark_proxy, cap.tun_route_table, self.runner, family, cap.tun_name
                )

    def applied_has_tproxy(self) -> bool:
        """Есть ли inbound перехвата в применённом конфиге Xray.

        Именно в применённом (`paths.xray_config_file`), а не в собранном: правила
        перехвата отправляют пакеты на `capture.tproxy_port`, и слушать его будет
        только тот Xray, который запущен с этим конфигом.
        """
        try:
            config = json.loads(self.paths.xray_config_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        inbounds = config.get("inbounds")
        if not isinstance(inbounds, list):
            return False
        port = self.cfg.capture.tproxy_port
        for inbound in inbounds:
            if not isinstance(inbound, dict):
                continue
            # Порт обязан совпадать: правила отправляют пакеты именно на него.
            if inbound.get("port") != port:
                continue
            tag = str(inbound.get("tag", ""))
            if tag == TPROXY_TAG or tag.startswith(TPROXY_TAG + "6"):
                return True
            if inbound.get("protocol") == "tunnel":
                return True
        return False

    def _load(self, mode: str) -> str:
        if mode == "on" and not self.applied_has_tproxy():
            # Правила перехвата отправляют пакеты на tproxy_port. Если в применённом
            # конфиге Xray такого inbound нет (например, изменение настроек ждёт
            # перезапуска Xray в окне apply.restart_window), то включать перехват
            # нельзя: при fail_mode = "closed" машина осталась бы без интернета —
            # пакеты уходили бы на порт, который никто не слушает. Загружаем режим
            # «снят»: сеть работает напрямую, а перехват включится сам, когда
            # конфиг с inbound перехвата применится.
            self.tproxy_missing = True
            self.log.error(
                "перехват не включён: в применённом конфиге Xray (%s) нет inbound "
                "TPROXY на порту %s — трафик ушёл бы в никуда. Перехват включится "
                "после перезапуска Xray с новым конфигом",
                self.paths.xray_config_file,
                self.cfg.capture.tproxy_port,
            )
            mode = "off"
        else:
            self.tproxy_missing = False
        rules = self.rules(mode)
        try:
            if rules.lan_if:
                self._forwarding_on()
            if rules.capture:
                # Сначала интерфейс и маршрут для помеченных пакетов, потом правила,
                # которые метят; ненужное убирается уже после них.
                self._routes_up(rules)
                warnings = nft.apply(rules, self.runner)
                self._routes_down(rules)
            else:
                warnings = nft.apply(rules, self.runner)
                self._routes_down(rules)
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

    def down(self, *, remove_tun: bool = False) -> None:
        """Убирает всё, что XGW добавил в сеть: таблицы, правило, маршрут, форвардинг.

        TUN-интерфейс остаётся, если не сказано иное: его держит открытым работающий
        Xray, и без интерфейса его inbound пришлось бы перезапускать. Удаление
        (`xgw uninstall`) вызывает это уже после остановки служб."""
        with self._lock():
            try:
                nft.delete(self.runner)
                self._routes_down(self.rules("off"))  # перехвата нет: убирается всё
                if remove_tun:
                    tun.remove(self.cfg.capture.tun_name, self.runner)
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
            expected.add("loopback_guard")
        if rules.prerouting:
            expected.add("prerouting")
        if rules.capture_local:
            expected.add("output")
        if rules.lan_if:
            expected |= {"forward", "postrouting"}
        if not expected <= chains:
            return False
        if not rules.capture:
            return not chains & {"prerouting", "output", "loopback_guard"}
        if not rules.prerouting and "prerouting" in chains:
            return False  # остался TPROXY самой машины от capture.method = "tproxy"
        if rules.capture6 or self.ipv6_usable():
            chains6 = nft.loaded_chains(self.runner, "ip6", nft.TABLE6)
            if chains6 is None:
                return None
            captured6 = {"output", "loopback_guard"}
            if rules.prerouting6:
                captured6.add("prerouting")
            if rules.capture6 and not captured6 <= chains6:
                return False
            if not rules.capture6 and chains6 & {"prerouting", "output", "loopback_guard"}:
                return False  # остались правила от ipv6 = proxy
            if rules.capture6 and not rules.prerouting6 and "prerouting" in chains6:
                return False
        cap = self.cfg.capture
        with contextlib.suppress(cmd.CommandError):
            if rules.tun and not tun.present(rules.tun_name, self.runner):
                return False
            for family in self._families():
                tproxy, via_tun = self._wanted(rules, family)
                if tproxy and not iprule.present(
                    cap.mark_proxy, cap.route_table, self.runner, family
                ):
                    return False
                if via_tun and not iprule.present_tun(
                    cap.mark_proxy, cap.tun_route_table, self.runner, family, rules.tun_name
                ):
                    return False
                # Лишнее от другого режима: правило TUN после возврата на tproxy и наоборот.
                if not via_tun and iprule.has_rule(
                    cap.mark_proxy, cap.tun_route_table, self.runner, family, "lo"
                ):
                    return False
                if not tproxy and iprule.has_rule(
                    cap.mark_proxy, cap.route_table, self.runner, family
                ):
                    return False
            return True
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
            "ipv6": rules.capture6,
            "tun": rules.tun,
            "fail_mode": self.cfg.capture.fail_mode,
            "loaded": self.loaded() if check else None,
            # Перехват просили включить, но Xray работает без inbound'а перехвата:
            # правила не загружены, трафик идёт напрямую (см. _load).
            "tproxy_missing": self.tproxy_missing,
        }
