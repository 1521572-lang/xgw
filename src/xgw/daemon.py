"""Демон XGW (xgw.service): watchdog, подписки, сканы запасных, замена участников.

Переключением серверов управляет только Xray. Демон раз в interval_s (±20 %)
собирает сигналы — метрики observatory, сквозную загрузку через http-in и
доступность провайдера, — ведёт машину состояний и делает то, что ядро само
не умеет: обновляет подписки, применяет изменения, сканирует запасные и
меняет «мёртвых» участников (раздел 6.8).

Один поток, один шаг за раз: применение конфига идёт под файловой блокировкой
и не пересекается с командами CLI. Каждое обращение наружу — отдельный метод
(`_read_observatory`, `_check_e2e`, …): в тестах они подменяются.
"""

from __future__ import annotations

import contextlib
import copy
import datetime
import ipaddress
import json
import random
import threading
import time
from collections import deque
from pathlib import Path

from . import engine, fetch, log
from .apply.applier import ApplyOutcome, in_restart_window
from .apply.rotation import plan_rotation, preferred_members
from .config import Config
from .generator import builder
from .generator.builder import BALANCER_TAG, NodeInfo
from .paths import Paths
from .store import Store
from .watch import checks, scan, status
from .watch.notify import Notifier
from .watch.states import Signals, State, StateMachine
from .xraycore import binary, metrics
from .xraycore.api import ApiError
from .xraycore.service import XrayServiceError

LEAK_INTERVAL = 300.0  # проверка утечки — раз в 5 минут
WAN_DOWN_INTERVAL = 60.0  # при недоступном провайдере проверки раз в 60 с
ALL_DEAD_RETRY = 300.0  # как часто повторять внеочередное обновление, пока все мертвы
SCAN_BUDGET = 8.0  # секунд на сканы за один шаг: watchdog не должен надолго замирать
RESCAN_PAUSE = 60.0  # внеочередной скан запасных — не чаще
SUBSCRIPTION_RETRY = 120.0  # повтор опроса подписок после неудачи
PROVIDER_DNS_TTL = 600.0
ROLLBACK_AFTER = 2  # «после двух неудач — откат на last-good»


def jitter(seconds: float, spread: float = 0.2) -> float:
    """Интервал со сдвигом ±20 %: строго периодические запросы заметны со стороны."""
    return seconds * random.uniform(1.0 - spread, 1.0 + spread)


class Daemon:
    def __init__(
        self,
        cfg: Config,
        paths: Paths,
        *,
        xray_bin: Path,
        logger=None,
        capture_active=lambda: False,
        reapply_capture=lambda: None,
        clock=time.monotonic,
        wall=time.time,
    ) -> None:
        self.cfg = cfg
        self.paths = paths
        self.xray_bin = xray_bin
        self.log = logger or log.get_logger("daemon")
        # Перехват появляется на этапе 3: до тех пор утечку проверять не на чем.
        self.capture_active = capture_active
        self.reapply_capture = reapply_capture
        self.clock = clock
        self.wall = wall

        self.applier = engine.make_applier(cfg, paths, xray_bin)
        self.api = self.applier.api
        self.service = self.applier.service
        self.mark = engine.bypass_mark(cfg, self.log)
        self.machine = StateMachine(cfg.watchdog.fail_threshold)
        self.notifier = Notifier(paths.db_file, cfg.notify.min_interval_min, logger=self.log)
        self.store = Store(paths.db_file)
        self.xray_version = ".".join(map(str, binary.installed_version(xray_bin) or ()))

        self.inventory: engine.Inventory | None = None
        self.action = ""
        self.now_time = lambda: datetime.datetime.now().time()
        self.state_since = self.wall()
        self.dead_since: dict[str, float] = {}  # тег участника → когда замечен мёртвым
        self.e2e_streak = 0
        self.down_ticks = 0
        self.rolled_back = False
        self.leak = False
        self.scan_queue: deque[str] = deque()  # probe-теги запасных, ждущих скана
        self.next_refresh = 0.0
        self.next_scan = 0.0
        self.next_leak = 0.0
        self.next_all_dead = 0.0
        self.next_rescan = 0.0
        self._provider_ip: tuple[float, str] | None = None
        self._budget_warnings: tuple[str, ...] = ()

    # --- цикл ------------------------------------------------------------------

    def run(self, stop: threading.Event) -> None:
        self.log.info("демон XGW запущен, шаг watchdog %d с", self.cfg.watchdog.interval_s)
        while not stop.is_set():
            try:
                state = self.tick()
            except Exception:  # сбой одного шага не должен ронять демон
                self.log.exception("шаг watchdog завершился ошибкой")
                state = self.machine.state
            pause = WAN_DOWN_INTERVAL if state is State.WAN_DOWN else self.cfg.watchdog.interval_s
            stop.wait(jitter(pause))
        self.store.close()
        self.log.info("демон XGW остановлен")

    def tick(self) -> State:
        """Один шаг watchdog. За шаг применяется не больше одного изменения конфига."""
        now = self.clock()
        applied = engine.read_json(self.paths.xray_config_file)
        if applied is None:
            # Первый запуск: рабочего конфига ещё нет — собрать и запустить Xray.
            if now >= self.next_refresh:
                self._refresh(now, via_xray=False, urgent=True)
            applied = engine.read_json(self.paths.xray_config_file)
            if applied is None:
                self._write_status([], None, False)
                return self.machine.state

        view = builder.applied_nodes(applied, self.inventory.nodes if self.inventory else ())
        members = [info for info in view if info.role == "proxy"]
        signals, observatory = self._signals(members, now)
        previous = self.machine.state
        decision = self.machine.update(signals)
        state = decision.state
        self.action = decision.action
        if state is not previous:
            self.state_since = self.wall()
            # Тип события — само состояние: уведомление об ALL_DEAD не должно
            # придерживаться из-за недавнего уведомления о DEGRADED.
            self.notifier.event(
                str(state), f"{previous} → {state}: {decision.action}",
                notify=state is not State.HEALTHY,
            )

        urgent = state in (State.ALL_DEAD, State.XRAY_DOWN)
        changed = False
        if state is State.XRAY_DOWN:
            changed = self._handle_xray_down()
        else:
            self.down_ticks = 0
            self.rolled_back = False
        if state is State.LEAK:
            self._handle_leak()

        if not changed and self.paths.pending_config_file.exists():
            changed = self._apply_pending(urgent)
        if not changed and state is State.ALL_DEAD and now >= self.next_all_dead:
            # Внеочередное обновление подписки напрямую и скан всех запасных.
            self.next_all_dead = now + ALL_DEAD_RETRY
            changed = self._refresh(now, via_xray=False, urgent=True)
            self._queue_scan(view, now)
        elif not changed and state is not State.WAN_DOWN and now >= self.next_refresh:
            changed = self._refresh(now, via_xray=signals.xray_ok, urgent=urgent)

        if not changed and signals.xray_ok and signals.provider_ok:
            if now >= self.next_scan:
                self.next_scan = now + jitter(self.cfg.probe.scan_spares_minutes * 60.0)
                self._queue_scan(view, now)
            self._scan_step(view, applied)
            if state in (State.DEGRADED, State.ALL_DEAD):
                changed = self._rotate(view, observatory or {}, state, now)

        self._check_pin()
        if changed:
            applied = engine.read_json(self.paths.xray_config_file)
            view = builder.applied_nodes(applied, self.inventory.nodes if self.inventory else ())
        self._write_status(view, observatory, signals.xray_ok)
        return state

    # --- сигналы ---------------------------------------------------------------

    def _signals(self, members: list[NodeInfo], now: float) -> tuple[Signals, dict | None]:
        observatory: dict | None = None
        try:
            observatory = self._read_observatory()
            xray_ok = True
        except Exception as exc:
            self.log.debug("метрики недоступны: %s", exc)
            # XRAY_DOWN — когда недоступны и метрики, и API.
            try:
                self.api.balancer_info(BALANCER_TAG)
                xray_ok, observatory = True, {}
            except ApiError:
                xray_ok = False

        provider_ok = self._check_provider()
        e2e_ok = True
        if xray_ok and provider_ok:
            e2e_ok = self._check_e2e()
            self.e2e_streak = 0 if e2e_ok else self.e2e_streak + 1

        if not self.capture_active():
            self.leak = False
        elif xray_ok and provider_ok and now >= self.next_leak:
            self.next_leak = now + jitter(LEAK_INTERVAL)
            location = self._check_leak()
            self.leak = (
                location is not None and location == self.cfg.routing.home_country.upper()
            )

        tags = [info.tag for info in members]
        alive, _dead, unknown = metrics.count_members(observatory or {}, tags)
        for tag in tags:
            entry = (observatory or {}).get(tag)
            if entry is not None and not entry["alive"]:
                self.dead_since.setdefault(tag, self.wall())
            else:
                self.dead_since.pop(tag, None)
        for tag in set(self.dead_since) - set(tags):
            del self.dead_since[tag]

        return (
            Signals(
                provider_ok=provider_ok,
                xray_ok=xray_ok,
                alive_members=alive,
                total_members=len(tags),
                unknown_members=unknown,
                e2e_ok=e2e_ok,
                e2e_fail_streak=self.e2e_streak,
                leak=self.leak,
            ),
            observatory,
        )

    def _read_observatory(self) -> dict[str, dict]:
        return metrics.parse_observatory(metrics.fetch_metrics(self.cfg.xray.metrics_port))

    def _check_e2e(self) -> bool:
        """Сквозная загрузка probe.url через http-in с детектором «тишины»."""
        result = checks.http_get_via_proxy(
            "127.0.0.1", self.cfg.xray.http_port, self.cfg.probe.url, silence=5.0, max_total=30.0
        )
        if not result.ok:
            self.log.info("сквозная проверка не прошла: %s", result.error)
        return result.ok

    def _check_provider(self) -> bool:
        """TCP-подключение к wan_check напрямую, сокетом с меткой mark_bypass."""
        host, _, port_text = self.cfg.watchdog.wan_check.rpartition(":")
        if not host or not port_text.isdigit():
            return True  # проверять нечем — провайдера считаем доступным
        address = self._provider_address(host)
        if address is None:
            return False
        return checks.tcp_check(address, int(port_text), mark=self.mark)

    def _provider_address(self, host: str) -> str | None:
        with contextlib.suppress(ValueError):
            ipaddress.ip_address(host)
            return host
        if self.mark is None:
            return host  # без метки системный резолвер и так ходит напрямую
        now = self.clock()
        if self._provider_ip and now - self._provider_ip[0] < PROVIDER_DNS_TTL:
            return self._provider_ip[1]
        try:
            # Свой резолвер с меткой: системный ходит через перехват и при
            # упавшем Xray не ответит — WAN_DOWN получился бы вместо XRAY_DOWN.
            address = fetch.resolve_domain(host, self.cfg.dns.bootstrap, mark=self.mark)[0]
        except fetch.ResolveError:
            return self._provider_ip[1] if self._provider_ip else None
        self._provider_ip = (now, address)
        return address

    def _check_leak(self) -> str | None:
        """Страна выхода обычным сокетом без метки — то есть через перехват."""
        return checks.trace_location(self.cfg.probe.trace_url)

    # --- действия --------------------------------------------------------------

    def _handle_xray_down(self) -> bool:
        """systemd перезапускает службу сам; после двух неудач — откат на last-good."""
        self.down_ticks += 1
        if not self.service.is_active():
            try:
                self.service.start()
            except XrayServiceError as exc:
                self.log.error("Xray не запускается: %s", exc)
        if self.down_ticks < ROLLBACK_AFTER or self.rolled_back:
            return False
        self.rolled_back = True
        outcome = self.applier.rollback("Xray не отвечает после перезапуска")
        if outcome.mode == "unchanged":
            # Откатывать нечего (last-good нет или он и есть текущий конфиг):
            # служба может числиться запущенной и при этом висеть — перезапускаем сами.
            try:
                self.service.restart()
                self.notifier.event("xray", "Xray не отвечал — служба перезапущена", notify=True)
            except XrayServiceError as exc:
                self.notifier.event("xray", f"Xray не перезапускается: {exc}", notify=True)
            return False
        self.notifier.event("rollback", engine.describe(outcome), notify=True)
        return outcome.mode == "rollback"

    def _handle_leak(self) -> None:
        try:
            self.reapply_capture()
        except Exception as exc:
            self.log.error("правила перехвата не переприменены: %s", exc)
        self.notifier.event(
            "leak", f"выход в {self.cfg.routing.home_country} при включённом перехвате",
            notify=True,
        )

    def _apply_pending(self, urgent: bool) -> bool:
        """Конфиг, ждущий перезапуска: в окне restart_window либо срочно."""
        if not urgent and not in_restart_window(self.cfg.apply.restart_window, self.now_time()):
            return False
        pending = engine.read_json(self.paths.pending_config_file)
        if pending is None:
            self.paths.pending_config_file.unlink(missing_ok=True)
            return False
        outcome = self._apply(pending, urgent=urgent)
        if outcome.mode == "rejected":
            # Отклонённый конфиг не перепроверяем на каждом шаге: следующее
            # обновление подписки соберёт новый.
            self.paths.pending_config_file.unlink(missing_ok=True)
        return self._report(outcome, "отложенный перезапуск")

    def _refresh(self, now: float, *, via_xray: bool, urgent: bool) -> bool:
        """Опрос подписок и применение изменений."""
        minutes = min((sub.refresh_minutes for sub in self.cfg.subscriptions), default=60)
        self.next_refresh = now + jitter(max(1, minutes) * 60.0)
        inventory = self._collect(via_xray)
        first_start = not self.paths.xray_config_file.exists()
        if not inventory.nodes or not (inventory.complete or first_start):
            # Неполный список применять нельзя: из ядра пропали бы серверы подписки,
            # которую сейчас не удалось получить.
            self.notifier.event(
                "subscription", "подписки получить не удалось — конфиг не меняется", notify=True
            )
            if self.inventory is None and inventory.nodes:
                self.inventory = inventory  # хотя бы сопоставить узлы с тегами
            # Повторить скорее, чем через refresh_minutes, но не на каждом шаге:
            # у запроса подписки и так три повтора с паузами.
            self.next_refresh = min(self.next_refresh, now + jitter(SUBSCRIPTION_RETRY))
            return False
        self.inventory = inventory
        return self._rebuild(None, urgent=urgent, reason="обновление подписки")

    def _rebuild(self, prefer: list[str] | None, *, urgent: bool, reason: str) -> bool:
        assert self.inventory is not None
        try:
            assembly = self._assemble(prefer)
        except engine.EngineError as exc:
            self.notifier.event("config", f"{reason}: {exc}", notify=True)
            return False
        outcome = self._apply(assembly.result.config, urgent=urgent)
        if outcome.mode in ("api", "restart", "unchanged"):
            engine.persist(self.paths, assembly, self.inventory.quotas, record_event=False)
        return self._report(outcome, reason)

    def _report(self, outcome: ApplyOutcome, reason: str) -> bool:
        """Событие по итогу применения; True — рабочий конфиг изменился."""
        if outcome.mode == "unchanged":
            return False
        bad = outcome.mode in ("rejected", "rollback", "failed")
        self.notifier.event("apply", f"{reason}: {engine.describe(outcome)}", notify=bad)
        if outcome.mode in ("api", "restart"):
            self._repin()
            return True
        return outcome.mode == "rollback"

    def _collect(self, via_xray: bool) -> engine.Inventory:
        return engine.collect(
            self.cfg, self.paths, mark=self.mark, logger=self.log, via_xray=via_xray
        )

    def _assemble(self, prefer: list[str] | None) -> engine.Assembly:
        assert self.inventory is not None
        return engine.assemble(
            self.cfg, self.paths, self.inventory, mark=self.mark, logger=self.log,
            xray_bin=self.xray_bin, prefer=prefer,
        )

    def _apply(self, config: dict, *, urgent: bool) -> ApplyOutcome:
        return self.applier.apply(config, urgent=urgent)

    # --- сканы и замена участников ---------------------------------------------

    def _queue_scan(self, view: list[NodeInfo], now: float) -> None:
        queued = set(self.scan_queue)
        for info in view:
            if info.role == "spare" and info.probe_tag not in queued:
                self.scan_queue.append(info.probe_tag)
        self.next_rescan = now + RESCAN_PAUSE

    def _scan_step(self, view: list[NodeInfo], applied: dict) -> None:
        """Сканирует запасные из очереди, пока не истёк бюджет времени шага."""
        if not self.scan_queue:
            return
        password, _ports = builder.probe_state(applied)
        spares = {info.probe_tag: info for info in view if info.role == "spare"}
        started = self.clock()
        while self.scan_queue and self.clock() - started < SCAN_BUDGET:
            info = spares.get(self.scan_queue.popleft())
            if info is None or not password:
                continue
            result = self._scan(info, password)
            self.store.save_scan(
                info.probe_tag, result.verdict, result.bytes_read, result.seconds, result.error,
                ts=self.wall(),
            )
            self.log.info(
                "скан %s: %s, %d байт за %.1f с", info.tag, result.verdict,
                result.bytes_read, result.seconds,
            )

    def _scan(self, info: NodeInfo, password: str) -> scan.ScanResult:
        return scan.scan_node(info, self.cfg, probe_pass=password)

    def _rotate(self, view: list[NodeInfo], observatory: dict, state: State, now: float) -> bool:
        """Меняет участников, мёртвых дольше rotate_after_min, на проверенные запасные."""
        if self.inventory is None or not self.dead_since:
            return False
        by_fingerprint = {node.fingerprint: node for node in self.inventory.nodes}
        members = [info for info in view if info.role == "proxy"]
        if any(info.fingerprint not in by_fingerprint for info in members):
            return False  # состав ядра не сопоставлен с подпиской — менять вслепую нельзя
        pairs = [
            (info, by_fingerprint[info.fingerprint])
            for info in view
            if info.role == "spare" and info.fingerprint in by_fingerprint
        ]
        # «Прошедший последний скан»: результат старше двух периодов скана не в счёт.
        fresh_after = self.wall() - self.cfg.probe.scan_spares_minutes * 120.0 - 120.0
        scans = {
            tag: entry for tag, entry in self.store.scans().items() if entry["ts"] >= fresh_after
        }
        verdicts = {i.tag: scans[i.probe_tag]["verdict"] for i, _ in pairs if i.probe_tag in scans}
        seconds = {i.tag: scans[i.probe_tag]["seconds"] for i, _ in pairs if i.probe_tag in scans}
        cfg = self.cfg
        if state is State.ALL_DEAD:
            # Живых нет вовсе — ждать rotate_after_min незачем.
            cfg = copy.copy(self.cfg)
            cfg.filters = copy.copy(self.cfg.filters)
            cfg.filters.rotate_after_min = 0
        alive = {tag: entry["alive"] for tag, entry in observatory.items()}
        rotation = plan_rotation(
            alive, self.dead_since, verdicts, seconds, members, pairs, cfg, self.wall()
        )
        if rotation is None:
            overdue = cfg.filters.rotate_after_min * 60.0
            waiting = any(self.wall() - since >= overdue for since in self.dead_since.values())
            if waiting and pairs and not self.scan_queue and now >= self.next_rescan:
                self._queue_scan(view, now)  # менять пора, а свежих сканов нет
            return False
        names = ", ".join(f"{tag} → «{node.name}»" for tag, node in rotation.replacements)
        self.notifier.event("rotation", f"замена участников: {names}", notify=True)
        return self._rebuild(
            preferred_members(members, rotation),
            urgent=state is State.ALL_DEAD,
            reason="замена участника",
        )

    # --- ручное закрепление ----------------------------------------------------

    def _pin(self) -> dict | None:
        try:
            pin = json.loads(self.store.get_meta("pin") or "null")
        except json.JSONDecodeError:
            return None
        return pin if isinstance(pin, dict) and pin.get("tag") else None

    def _check_pin(self) -> None:
        """Снимает закрепление по истечении срока (bo -r)."""
        pin = self._pin()
        if pin is None or pin.get("until", 0) > self.wall():
            return
        try:
            self.api.unpin(BALANCER_TAG)
        except ApiError as exc:
            self.log.error("закрепление %s не снято: %s", pin["tag"], exc)
            return
        self.store.set_meta("pin", "")
        self.notifier.event("pin", f"закрепление {pin['tag']} снято по истечении срока")

    def _repin(self) -> None:
        """adrules и перезапуск сбрасывают закрепление в ядре — возвращаем, пока срок не вышел."""
        pin = self._pin()
        if pin is None or pin.get("until", 0) <= self.wall():
            return
        view = builder.applied_nodes(engine.read_json(self.paths.xray_config_file))
        if pin["tag"] not in [info.tag for info in view if info.role == "proxy"]:
            self.store.set_meta("pin", "")
            self.notifier.event(
                "pin", f"закрепление {pin['tag']} снято: узел больше не участник балансировщика"
            )
            return
        try:
            self.api.pin(BALANCER_TAG, pin["tag"])
        except ApiError as exc:
            self.log.error("закрепление %s не восстановлено: %s", pin["tag"], exc)

    # --- статус ----------------------------------------------------------------

    def _write_status(
        self, view: list[NodeInfo], observatory: dict | None, xray_ok: bool
    ) -> None:
        state = self.machine.state
        snapshot = status.collect_status(
            self.cfg, self.paths, view,
            observatory=observatory, xray_ok=xray_ok, state=str(state),
            action=self.action, since=self.state_since,
            dead_since=self.dead_since, xray_version=self.xray_version, daemon=True,
        )
        warnings = tuple(snapshot["budget"]["warnings"])
        if warnings != self._budget_warnings:
            self._budget_warnings = warnings
            for warning in warnings:
                self.notifier.event("budget", warning, notify=True)
        try:
            status.write_status(self.paths, snapshot)
        except OSError as exc:
            self.log.error("status.json не записан: %s", exc)
