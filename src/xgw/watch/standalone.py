"""Шаг шлюза без VPN: локальный Xray и nfqws2, без подписок и проб серверов."""

from __future__ import annotations

import contextlib

from .. import engine, zapret2
from ..generator import builder
from ..net import cmd
from ..net.capture import CaptureError
from ..paths import file_lock
from ..xraycore.service import XrayServiceError
from .states import State

FAILURE = "zapret2_standalone_apply_failure"


def apply_blocked(d) -> State:
    d._zapret2.view = {"state": "blocked", "reason": "apply_failed"}
    d.machine.state = State.DEGRADED
    d.action = ("Переключение без VPN остановлено после ошибки. Автоповторы отключены. "
                "Для повторной попытки выключите режим zapret2 и включите заново.")
    d._write_status([], None, False)
    return d.machine.state


def tick(daemon, applied: dict | None, now: float) -> State:
    d = daemon
    if d.cfg.zapret2.mode != "standalone":
        if d.store.get_meta(FAILURE):
            d.store.set_meta(FAILURE, "")
        return _return_to_vpn(d, now)
    if d.stopping:
        return d.machine.state
    if d.store.get_meta(FAILURE):
        return apply_blocked(d)
    if zapret2.validate(d.cfg):
        with contextlib.suppress(OSError, cmd.CommandError):
            d._zapret2.close()
        d._zapret2.view = {"state": "blocked", "reason": "invalid_config"}
        d.machine.state = State.DEGRADED
        d.action = "Настройки zapret2 без VPN отклонены. Смена маршрута не подтверждена."
        d._write_status([], None, False)
        return d.machine.state
    if d._fetch is not None:
        d._fetch.cancel.dropped.set()
        if d._fetch.done.is_set():
            d._fetch = None
    d._build_next = None
    if d._build is not None:
        d._build.discard = True
        d._finish_build()
    entering = not zapret2.standalone(applied)
    if entering:
        d._standalone_enable_pending = True
    target = builder.build(d.cfg, builder.Selection(), hosts={},
                           containers_tun=engine.containers_tun(d.cfg),
                           api_listen=str(d.paths.xray_api_socket)).config
    if target != applied:
        # До рестарта: падение демона посреди применения тоже не запускает цикл повторов.
        d.store.set_meta(FAILURE, "pending")
        outcome = d._apply(target, urgent=True)
        d._report(outcome, "Режим zapret2 без VPN")
        applied = engine.read_json(d.paths.xray_config_file)
        if outcome.mode not in ("api", "restart", "unchanged") or applied != target:
            d.store.set_meta(FAILURE, outcome.mode)
            return apply_blocked(d)
        d.store.set_meta(FAILURE, "")
    # Не переносим отложенную VPN-сборку в самостоятельный режим.
    d._rebuild_asked = False
    d._refresh_asked = d._scan_asked = d._speed_asked = False
    bridges_stopped = False
    if d._build is None and (d._fetch is None or d._fetch.done.is_set()):
        with contextlib.suppress(OSError, ValueError, cmd.CommandError):
            bridges_stopped = stop_bridges(d)
    try:
        d._read_observatory()  # Только локальные метрики, никаких HTTP-проб наружу.
        xray_ok = True
        d.down_ticks = 0
    except (OSError, ValueError, RuntimeError):
        xray_ok = False
        d.down_ticks += 1
        # Не откатываем на last-good: он может содержать VPN-серверы.
        try:
            if not d.service.is_active() and not d.service.restart_pending():
                d.service.start()
            elif d.down_ticks == 2:
                d.service.restart()
        except XrayServiceError:
            pass
    if getattr(d, "_standalone_enable_pending", False) and xray_ok and d.capture is not None:
        try:
            d.capture.enable()
            d._standalone_enable_pending = False
        except CaptureError:
            d._zapret2.view = {"state": "blocked", "reason": "capture_failed"}
    d._guard_capture(xray_ok, now)
    capture = d.capture_info or {}
    allowed = (xray_ok and bridges_stopped and d.capture is not None and d.capture.mode() == "on"
               and capture.get("loaded") is True and not capture.get("capture_failed")
               and not capture.get("inbound_missing"))
    previous = d._zapret2.view.get("state")
    d._zapret2.step(d.cfg, applied, now, d._zapret2_apply, allowed=allowed)
    if not allowed and d.capture is not None and d.capture.mode() == "on":
        d._zapret2.view = {"state": "blocked", "reason": "capture_failed"}
    if not bridges_stopped:
        d._zapret2.view = {"state": "blocked", "reason": "vpn_stopping"}
    if previous != d._zapret2.view.get("state"):
        d.notifier.event("zapret2", "zapret2 без VPN: " + d._zapret2.view["state"])
    d.machine.state = (State.XRAY_DOWN if not xray_ok else
                       State.DEGRADED if d._zapret2.view["state"] == "blocked" else State.HEALTHY)
    d.action = ("Без VPN. Обработчик zapret2 готов; доступность сайтов проверяется в браузере."
                if allowed and d._zapret2.view["state"] == "active" else
                "Без VPN. zapret2 не пропускает выбранные домены; проверьте состояние обработчика."
                if d.capture is not None and d.capture.mode() == "on" else
                "Без VPN. Перехват выключен, трафик идёт напрямую без обработки zapret2.")
    d._health_observed = now
    d._usage_step(applied)
    d._write_status([], {}, xray_ok)
    return d.machine.state


def stop_bridges(d) -> bool:
    """После применения прямого конфига закрыть собственные VPN-мосты XGW."""
    from ..apply import singbox_process as processes

    if getattr(d, "_standalone_bridges_stopped", False):
        return True
    with file_lock(d.paths.lock_file):
        current = engine.read_json(d.paths.xray_config_file)
        if not zapret2.standalone(current) or d.paths.api_dirty_file.exists():
            return False
        for slot in (*processes.SLOTS, "legacy"):
            if not processes.stopped(slot):
                processes.stop(slot)
            if not processes.stopped(slot):
                return False
        d.paths.singbox_config_file.unlink(missing_ok=True)
        d.paths.singbox_pending_file.unlink(missing_ok=True)
        state = processes.read(d.paths)
        state.update(active="legacy", pending=None, draining=None)
        processes.write(d.paths, state)
        processes.marker_path(d.paths).unlink(missing_ok=True)
    d._standalone_bridges_stopped = True
    return True


def _return_to_vpn(d, now: float) -> State:
    """Только явная смена режима возвращает VPN; фоновые отказы сюда не ведут."""
    if not getattr(d, "_standalone_vpn_requested", False):
        d._standalone_vpn_requested = True
        d.next_refresh = 0
    try:
        d._zapret2.close()
    except (OSError, cmd.CommandError):
        d._zapret2.view = {"state": "blocked", "reason": "stop_failed"}
    else:
        d._zapret2.view = {"state": "preparing", "reason": "vpn_requested"}
        if not d.stopping:
            changed = d._finish_build()
            if not changed and d._build is None and d._build_next is None:
                if d.inventory is not None and d.inventory.nodes:
                    d._rebuild(None, urgent=True, reason="Возврат в режим VPN")
                elif now >= d.next_refresh or d._fetch is not None:
                    d._refresh(now, via_xray=False, urgent=True)
    d.machine.state = State.DEGRADED
    d.action = "Запрошен VPN. Ожидается применение конфига с серверами."
    d._write_status([], None, False)
    return d.machine.state
