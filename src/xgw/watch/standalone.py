"""Standalone lifecycle: local Xray for routing and one selected NFQUEUE worker."""

from __future__ import annotations

from .. import cores, engine, fetch, zapret2
from ..apply import singbox_generation as generations
from ..apply import singbox_process as processes
from ..generator import builder
from ..net import cmd
from ..paths import LockTimeout, file_lock
from ..xraycore.service import XrayServiceError
from .states import State


def tick(d, applied: dict | None, now: float) -> State:
    if d.cfg.zapret2.mode != "standalone":
        return _return_to_vpn(d, now)
    if d.stopping:
        return d.machine.state

    # A build from the previous policy may still be holding a prepared sing-box slot.
    if d._fetch is not None:
        d._fetch.cancel.dropped.set()
        if d._fetch.done.is_set():
            d._fetch = None
    d._build_next = None
    if d._build is not None:
        d._build.discard = True
        d._finish_build()

    if cores.job_active(d.paths, d.wall()):
        return _publish(d, "core_busy" if _stop_selected(d) else "stop_failed")

    target = builder.build(d.cfg, builder.Selection(), hosts={},
                           containers_tun=engine.containers_tun(d.cfg),
                           api_listen=str(d.paths.xray_api_socket)).config
    expected_open = zapret2.standalone_route(target, enabled=True)
    if applied not in (target, expected_open):
        if now < d._standalone_retry_at:
            return _publish(d, "apply_failed")
        if not _stop_selected(d):
            return _publish(d, "stop_failed")
        # Put the closed route on disk first. A failed apply leaves no permission to open the gate.
        outcome = d._apply(target, urgent=True)
        d._report(outcome, "zapret2 без VPN")
        applied = engine.read_json(d.paths.xray_config_file)
        if outcome.mode not in ("api", "restart", "unchanged") or applied != target:
            d._standalone_retry_at = now + d.cfg.zapret2.retry_seconds
            return _publish(d, "apply_failed")

    if d.paths.api_dirty_file.exists():
        # With uncertain Xray routing, withdraw the gate before restoring a known config.
        if not _stop_selected(d):
            return _publish(d, "stop_failed")
        if now >= d._standalone_retry_at:
            d._standalone_retry_at = now + d.cfg.zapret2.retry_seconds
            outcome = d.applier.recover_current(target, base=applied)
            d._report(outcome, "Восстановление маршрута zapret2")
        return _publish(d, "apply_failed")

    xray_ok = _local_xray(d)
    d._guard_capture(xray_ok, now)
    capture = d.capture_info or {}
    loaded = (capture.get("mode") == "on" and capture.get("loaded") is True
              and not capture.get("inbound_missing") and not capture.get("capture_failed"))
    bridges_down = xray_ok and loaded and d._build is None and _stop_bridges(d)
    reason = "xray_down" if not xray_ok else "capture_not_ready" if not loaded else "vpn_stopping"
    d._zapret2.step_standalone(d.cfg, applied, d.clock(), d._zapret2_apply,
                              allowed=xray_ok and loaded and bridges_down,
                              blocked_reason=reason, cancel=d._stop)
    d._health_observed = d.clock()
    d._usage_step(engine.read_json(d.paths.xray_config_file))
    return _publish(d, xray_ok=xray_ok)


def _local_xray(d) -> bool:
    try:
        d._read_observatory()
        d.down_ticks = 0
        return True
    except (OSError, ValueError, RuntimeError, fetch.FetchError):
        d.down_ticks += 1
    # Restart only the currently applied local config.
    try:
        if not d.service.is_active() and not d.service.restart_pending():
            d.service.start()
        elif d.down_ticks == 2 and d.service.is_active():
            d.service.restart()
    except XrayServiceError as exc:
        d.log.warning("локальный Xray не запущен: %s", exc)
    return False


def _stop_bridges(d) -> bool:
    """After committing a serverless Xray config, stop XGW's own VPN services."""
    try:
        if processes.read(d.paths)["pending"]:
            generations.recover(d.singbox)
        with file_lock(d.paths.lock_file):
            if (d.paths.api_dirty_file.exists()
                    or not zapret2.standalone(engine.read_json(d.paths.xray_config_file))):
                return False
            state = processes.read(d.paths)
            if state["pending"]:
                return False
            remaining = [slot for slot in (*processes.SLOTS, "legacy")
                         if not processes.stopped(slot)]
            for slot in remaining:
                processes.stop(slot)
            if remaining:
                return False
            cleared = {**state, "active": "legacy", "pending": None, "draining": None}
            if state["active"] in processes.SLOTS:
                cleared["resume_managed"] = True
            if state != cleared:
                processes.write(d.paths, cleared)
            d.paths.singbox_config_file.unlink(missing_ok=True)
            d.paths.singbox_pending_file.unlink(missing_ok=True)
            processes.marker_path(d.paths).unlink(missing_ok=True)
            return True
    except (OSError, ValueError, cmd.CommandError, LockTimeout):
        return False


def _stop_selected(d) -> bool:
    try:
        d._zapret2.close()
    except (OSError, cmd.CommandError):
        return False
    return True


def _return_to_vpn(d, now: float) -> State:
    if not _stop_selected(d):
        return _publish(d, "stop_failed")
    if not d._standalone_exiting:
        d._standalone_exiting = True
        d.singbox.sync_generation()
        d._singbox_resume_at = 0.0
        d.next_refresh = 0
    if not d.stopping:
        changed = d._finish_build()
        if not changed and d._build is None and d._build_next is None:
            if d._fetch is None and d.inventory is not None and d.inventory.nodes:
                if now < d.next_refresh:
                    return _publish(d, "vpn_requested")
                d.next_refresh = now + d.cfg.zapret2.retry_seconds
                d._rebuild(None, urgent=True, reason="Возврат к VPN")
            elif now >= d.next_refresh or d._fetch is not None:
                d._refresh(now, via_xray=False, urgent=True)
    return _publish(d, "vpn_requested")


def _publish(d, reason: str | None = None, *, xray_ok: bool = False) -> State:
    if reason is not None:
        d._zapret2.view = {"state": "preparing" if reason == "vpn_requested" else "blocked",
                          "reason": reason}
    ready = d._zapret2.view["state"] == "active"
    d.machine.state = State.HEALTHY if ready else State.DEGRADED
    d.action = ("Прямой режим zapret2 · без VPN"
                if ready else "Запрошен VPN. Ожидается применение конфига с серверами."
                if reason == "vpn_requested" else "Ожидается готовность прямого пути zapret2")
    d._write_status([], {}, xray_ok)
    return d.machine.state
