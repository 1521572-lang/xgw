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
import dataclasses
import datetime
import ipaddress
import json
import random
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import engine, fetch, log
from .apply.applier import ApplyOutcome, in_restart_window
from .apply.rotation import REPLACE_NOW_VERDICTS, plan_rotation, preferred_members
from .config import Config
from .generator import builder
from .generator.builder import BALANCER_TAG, NodeInfo
from .net import tun
from .net.capture import capture_inbounds
from .paths import Paths
from .store import Store
from .watch import checks, scan, status, target
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
FAIL_OPEN_AFTER = 60.0  # fail_mode = "open": Xray недоступен дольше — снять перехват
WAIT_SLICE = 1.0  # как часто пауза между шагами смотрит, не пора ли проснуться
MANUAL_SCAN_PAUSE = 1.0  # проверка по кнопке идёт подряд, не дожидаясь шага watchdog
PROBE_TARGET_RECHECK = 300.0  # как часто перепроверять, отвечает ли сам probe.url
PROBE_WORKERS = 8  # пробы для этой перепроверки идут одновременно: шаг не должен зависать


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
        capture=None,
        capture_active=lambda: False,
        reapply_capture=lambda: None,
        sinks=(),
        clock=time.monotonic,
        wall=time.time,
    ) -> None:
        self.cfg = cfg
        self.paths = paths
        self.xray_bin = xray_bin
        self.log = logger or log.get_logger("daemon")
        # capture — управление перехватом (net.capture.Capture); None — перехвата нет
        # (стенд этапа 2, запуск не от root): тогда и утечку проверять не на чем.
        self.capture = capture
        if capture is not None:
            # Утечку ищет обычный сокет самой машины, поэтому проверка имеет смысл,
            # только когда перехватывается и её трафик (capture.local).
            capture_active = lambda: (  # noqa: E731
                capture.mode() == "on" and cfg.capture.local
            )
            reapply_capture = capture.up
        self.capture_active = capture_active
        self.reapply_capture = reapply_capture
        self.capture_info: dict | None = None
        self._capture_error = ""
        # О чём уже сообщили: перехват не включён, потому что Xray работает без нужного
        # inbound'а (текст причины).
        self._inbound_missing = ""
        self.xray_down_since: float | None = None
        self.clock = clock
        self.wall = wall

        self.applier = engine.make_applier(cfg, paths, xray_bin)
        self.api = self.applier.api
        self.service = self.applier.service
        self.mark = engine.bypass_mark(cfg, self.log)
        self.machine = StateMachine(cfg.watchdog.fail_threshold)
        # sinks — куда доставлять уведомления (рабочий стол, Telegram); их собирает
        # `xgw run`, в тестах и на стенде получателей нет.
        self.notifier = Notifier(
            paths.db_file, cfg.notify.min_interval_min, sinks=sinks, logger=self.log
        )
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
        self.leak_fresh = False  # на этом шаге утечку проверяли заново
        self._leak_note = ""  # о какой утечке уже сообщили (текст события)
        # Отпечатки серверов, которые сами выходят в домашнюю страну: участник с таким
        # отпечатком меняется, запасной на его место не ставится.
        self.home_exits: set[str] = set()
        self.scan_queue: deque[str] = deque()  # probe-теги узлов, ждущих скана
        # Первая проверка участников собственной пробой шлюза: отпечатки уже проверенных
        # и теги тех, кто её не прошёл (тег → вердикт) — их меняют без ожидания
        # rotate_after_min.
        self.vetted: set[str] = set()
        self.bad_members: dict[str, str] = {}
        # Не отвечает сам probe.url (текст предупреждения); пусто — отвечает.
        self.probe_target = ""
        self.next_target_check = 0.0
        # Конфиг Xray нужно собрать заново срочно, без окна перезапуска (причина); пусто —
        # не нужно. Так бывает, когда сменился адрес проб ядра (запасной ↔ probe.url) или
        # на машине появился Docker и контейнерам нужен inbound TUN.
        self._urgent_rebuild = ""
        self.next_refresh = 0.0
        self.next_scan = 0.0
        self.next_leak = 0.0
        self.next_all_dead = 0.0
        self.next_rescan = 0.0
        self._provider_ip: tuple[float, str] | None = None
        self._budget_warnings: tuple[str, ...] = ()
        # Запросы из панели: другой поток только ставит отметку, выполняет её шаг watchdog.
        self.poke = threading.Event()
        self._refresh_asked = False
        self._scan_asked = False
        self._manual_scan = False
        self._refreshing = False
        self._rebuild_asked = False

    # --- цикл ------------------------------------------------------------------

    def run(self, stop: threading.Event, changed=lambda: False) -> None:
        """Цикл watchdog до остановки либо до изменения config.toml (changed)."""
        self.log.info("демон XGW запущен, шаг watchdog %d с", self.cfg.watchdog.interval_s)
        while not stop.is_set() and not changed():
            try:
                state = self.tick()
            except Exception:  # сбой одного шага не должен ронять демон
                self.log.exception("шаг watchdog завершился ошибкой")
                state = self.machine.state
            pause = WAN_DOWN_INTERVAL if state is State.WAN_DOWN else self.cfg.watchdog.interval_s
            if self._manual_scan and self.scan_queue:
                pause = MANUAL_SCAN_PAUSE
            self._sleep(stop, changed, jitter(pause))
        self.store.close()
        self.log.info("демон XGW остановлен" if stop.is_set() else "настройки изменены")

    def _sleep(self, stop: threading.Event, changed, seconds: float) -> None:
        """Пауза между шагами. Её прерывают остановка, правка настроек и запрос из панели."""
        deadline = time.monotonic() + seconds
        while not self.poke.is_set() and not changed():
            left = deadline - time.monotonic()
            if left <= 0 or stop.wait(min(left, WAIT_SLICE)):
                break
        self.poke.clear()

    def request_refresh(self) -> None:
        """Панель: обновить подписки сейчас, не дожидаясь refresh_minutes. Заодно заново
        проверяются домены, отложенные как несуществующие."""
        engine.forget_quarantine()
        self._refresh_asked = True
        self.poke.set()

    def adopt(self, previous: Daemon) -> None:
        """Настройки перечитаны. Если источники серверов прежние, подписки заново
        не запрашиваются: конфиг пересобирается из уже полученного списка — так
        отключение сервера в панели не стоит запроса к каждой подписке."""
        self._resume(previous)
        if previous.inventory is None or (
            engine.sources_key(previous.cfg) != engine.sources_key(self.cfg)
        ):
            return
        self.inventory = previous.inventory
        self.next_refresh = previous.next_refresh
        self._rebuild_asked = True
        # Серверы те же — заново проверять участников незачем.
        self.vetted = set(previous.vetted)
        self.bad_members = dict(previous.bad_members)

    def _resume(self, previous: Daemon) -> None:
        """Состояние watchdog переходит к новому демону как есть. Иначе каждая правка
        config.toml и каждое действие в панели молча сбрасывали бы его в HEALTHY: статус
        на шаг показывал бы, что всё в порядке, а следующее событие начиналось бы с
        «HEALTHY →», хотя до правки было, например, ALL_DEAD."""
        self.machine.state = previous.machine.state
        self.state_since = previous.state_since
        self.action = previous.action
        self.e2e_streak = previous.e2e_streak
        self.dead_since = dict(previous.dead_since)
        self.leak, self.next_leak = previous.leak, previous.next_leak
        self._leak_note = previous._leak_note
        self.home_exits = set(previous.home_exits)
        self.down_ticks = previous.down_ticks
        self.rolled_back = previous.rolled_back
        self.xray_down_since = previous.xray_down_since
        self.next_all_dead = previous.next_all_dead
        self._inbound_missing = previous._inbound_missing
        self.probe_target = previous.probe_target
        self.next_target_check = previous.next_target_check
        self._urgent_rebuild = previous._urgent_rebuild
        if previous.cfg.probe.url != self.cfg.probe.url:
            self.next_target_check = 0.0  # адрес пробы сменили — проверить новый сразу

    def request_scan(self) -> None:
        """Панель: проверить запасные серверы сейчас."""
        self._scan_asked = True
        self.poke.set()

    @property
    def refresh_pending(self) -> bool:
        return self._refresh_asked or self._refreshing

    @property
    def scan_pending(self) -> bool:
        return self._scan_asked or (self._manual_scan and bool(self.scan_queue))

    def tick(self) -> State:
        """Один шаг watchdog. За шаг применяется не больше одного изменения конфига."""
        now = self.clock()
        refresh_asked, self._refresh_asked = self._refresh_asked, False
        scan_asked, self._scan_asked = self._scan_asked, False
        applied = engine.read_json(self.paths.xray_config_file)
        if applied is None:
            # Первый запуск: рабочего конфига ещё нет — собрать и запустить Xray.
            if now >= self.next_refresh or refresh_asked or self._rebuild_asked:
                self._refresh(now, via_xray=False, urgent=True)
            applied = engine.read_json(self.paths.xray_config_file)
            if applied is None:
                self._write_status([], None, False)
                return self.machine.state

        view = builder.applied_nodes(applied, self.inventory.nodes if self.inventory else ())
        members = [info for info in view if info.role == "proxy"]
        signals, observatory = self._signals(members, now)
        signals = self._probe_target(view, applied, signals, now)
        previous = self.machine.state
        decision = self.machine.update(signals)
        state = decision.state
        self.action = decision.action
        if state is not previous:
            self.state_since = self.wall()
            detail = decision.action
            if state is State.PROBE_TARGET_UNREACHABLE:
                detail = f"{self.probe_target}. Замена серверов приостановлена: {target.ADVICE}"
            # Тип события — само состояние: уведомление об ALL_DEAD не должно
            # придерживаться из-за недавнего уведомления о DEGRADED.
            self.notifier.event(
                str(state), f"{previous} → {state}: {detail}",
                notify=state is not State.HEALTHY,
            )

        urgent = state in (State.ALL_DEAD, State.XRAY_DOWN)
        changed = False
        if state is State.XRAY_DOWN:
            changed = self._handle_xray_down()
        else:
            self.down_ticks = 0
            self.rolled_back = False
        if not self.leak:
            self._leak_note = ""
        elif state is State.LEAK and self.leak_fresh:
            self._handle_leak()
        # Правила перехвата. Обычно они проверяются до применения конфига: пропавшие
        # нужно вернуть как можно скорее. Но если правилам нужен inbound, которого у
        # работающего Xray ещё нет (настройки только что изменились), сначала
        # применяется конфиг: прежние правила и прежний Xray согласованы и трафик
        # через VPN носят, а загрузка «новых» правил сейчас сняла бы перехват.
        waiting = self._capture_waits()
        if not waiting:
            self._guard_capture(signals.xray_ok, now)

        if not changed and self.paths.pending_config_file.exists():
            changed = self._apply_pending(urgent)
        self._containers_appeared(applied)
        if not changed and self._urgent_rebuild and self.inventory is not None:
            # Срочно, без окна перезапуска: пока ядро пробует недоступный probe.url, оно
            # считает мёртвыми всех участников; без inbound TUN контейнеры без интернета.
            reason, self._urgent_rebuild = self._urgent_rebuild, ""
            changed = self._rebuild(None, urgent=True, reason=reason)
        if not changed and state is State.ALL_DEAD and now >= self.next_all_dead:
            # Внеочередное обновление подписки напрямую и скан всех запасных.
            self.next_all_dead = now + ALL_DEAD_RETRY
            changed = self._refresh(now, via_xray=False, urgent=True)
            self._queue_scan(view, now)
        elif not changed and (
            refresh_asked or (state is not State.WAN_DOWN and now >= self.next_refresh)
        ):
            changed = self._refresh(now, via_xray=signals.xray_ok, urgent=urgent)
        elif not changed and self._rebuild_asked and self.inventory is not None:
            self._rebuild_asked = False
            self._save_inventory(self.inventory)
            changed = self._rebuild(None, urgent=urgent, reason="изменение настроек")
        if waiting or changed:
            # Xray перезапущен с новым конфигом (или не перезапущен — тогда вместо
            # перехвата загрузится режим «снят»): правила доводятся сразу, а не через шаг.
            self._guard_capture(signals.xray_ok, now, switched=waiting)

        # Пока не отвечает сам probe.url, сканы только испортили бы вердикты запасных
        # (все «недоступны»), а замена участников шла бы по кругу: и то, и другое ждёт.
        # Решает сам признак, а не имя состояния: утечка (LEAK) стоит в машине состояний
        # выше и его заслоняет, а сканам и замене от этого не легче.
        probing = not self.probe_target
        if scan_asked and probing:
            self._manual_scan = True
            self._queue_scan(view, now)
        elif scan_asked:
            self.notifier.event("probe", "проверка запасных отложена: не отвечает probe.url")
        if not changed and probing and signals.xray_ok and signals.provider_ok:
            if now >= self.next_scan:
                self.next_scan = now + jitter(self.cfg.probe.scan_spares_minutes * 60.0)
                self._queue_scan(view, now)
            self._queue_members(view)
            self._scan_step(view, applied)
            if state in (State.DEGRADED, State.ALL_DEAD) or (
                state is State.HEALTHY and self.bad_members
            ) or (state is State.LEAK and self._home_members(view)):
                changed = self._rotate(view, observatory or {}, state, now)

        if not self.scan_queue or not probing:
            self._manual_scan = False
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

        self.leak_fresh = False
        if not self.capture_active():
            self.leak = False
        elif xray_ok and provider_ok and now >= self.next_leak:
            self.next_leak = now + jitter(LEAK_INTERVAL)
            self.leak_fresh = True
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
        # Не прошедший первую проверку участник: ядро считает его живым — значит,
        # сбой был разовым; вышел из участников — запись больше не нужна.
        for tag in list(self.bad_members):
            entry = (observatory or {}).get(tag)
            if tag not in tags or (entry is not None and entry["alive"]):
                del self.bad_members[tag]

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
            "127.0.0.1", self.cfg.xray.http_port, self.cfg.probe.url, silence=5.0,
            max_total=30.0, user_agent=self.cfg.probe.user_agent,
        )
        if not result.ok:
            self.log.info("сквозная проверка не прошла: %s", result.error)
            return False
        # Размер тела — мера расхода трафика на пробы (status.probe_budget).
        try:
            status.remember_probe_size(self.store, self.cfg.probe.url, result.downloaded)
        except Exception as exc:  # оценка трафика не важнее самой проверки
            self.log.debug("размер пробы не записан: %s", exc)
        return True

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
        return checks.trace_location(
            self.cfg.probe.trace_url, user_agent=self.cfg.probe.user_agent
        )

    def _exit_via_xray(self) -> str | None:
        """Страна выхода явно через http-in Xray — через сервер, выбранный балансировщиком."""
        return checks.trace_location(
            self.cfg.probe.trace_url, via=("127.0.0.1", self.cfg.xray.http_port),
            user_agent=self.cfg.probe.user_agent,
        )

    def _selected(self) -> tuple[str, bool] | None:
        """(тег сервера, через который сейчас идёт трафик; закреплён ли он вручную)."""
        try:
            info = self.api.balancer_state(BALANCER_TAG)
        except ApiError as exc:
            self.log.info("выбор балансировщика не узнать: %s", exc)
            return None
        if info.override:
            return info.override, True
        return (info.selects[0], False) if info.selects else None

    # --- не отвечает сам probe.url -----------------------------------------------

    def _probe_target(
        self, view: list[NodeInfo], applied: dict, signals: Signals, now: float
    ) -> Signals:
        """Отличает «не отвечает адрес пробы» от «не работают серверы» (watch/target.py).

        Повод для проверки — сквозная загрузка probe.url не проходит, и это длится
        fail_threshold шагов либо ядро уже объявило мёртвыми всех участников (его пробы
        идут на тот же адрес, и без этого шаг ушёл бы в ALL_DEAD: скан испортил бы
        вердикты запасных). Тогда собственной пробой опрашиваются все участники и
        несколько запасных; если ошибка у всех одна и контрольные запросы это
        подтверждают, состояние — PROBE_TARGET_UNREACHABLE, и серверы остаются как есть.
        """
        reachable = signals.xray_ok and signals.provider_ok
        if reachable and signals.e2e_ok:
            if self.probe_target:
                self.probe_target = ""
                self.next_target_check = 0.0
                self.next_scan = now  # вердикты запасных могли устареть — проверить заново
                self.notifier.event(
                    "probe", "probe.url снова отвечает — проверки серверов возобновлены",
                    notify=True,
                )
            # И после перезапуска демона: запись о запасном адресе могла остаться с прошлого раза.
            self._observatory_fallback(False)
            return signals
        dead = signals.total_members - signals.alive_members - signals.unknown_members
        suspect = reachable and not signals.e2e_ok and (
            signals.e2e_fail_streak >= self.cfg.watchdog.fail_threshold
            or (signals.total_members > 0 and dead >= signals.total_members)
        )
        if suspect and now >= self.next_target_check:
            self.next_target_check = now + PROBE_TARGET_RECHECK
            diagnosis = self._diagnose_target(view, applied)
            if diagnosis.down and diagnosis.text != self.probe_target:
                self.log.warning("%s", diagnosis.text)
                # Вердикты первой проверки сняты, пока адрес не отвечал: они ни о чём.
                self.bad_members.clear()
                self.vetted.clear()
            self.probe_target = diagnosis.text if diagnosis.down else ""
            self._observatory_fallback(diagnosis.down)
        if self.probe_target:
            return dataclasses.replace(signals, probe_target_ok=False)
        return signals

    def _observatory_fallback(self, on: bool) -> None:
        """Переводит пробы ядра на запасной адрес (on) или возвращает их на probe.url."""
        try:
            switched = target.use_fallback(self.cfg, self.paths, on)
        except OSError as exc:
            self.log.error("адрес проб ядра не переключён: %s", exc)
            return
        if not switched:
            return
        self._urgent_rebuild = "смена адреса проб ядра"
        if on:
            text = (
                f"ядро пробует серверы по {target.fallback_target(self.cfg)}, пока probe.url "
                "не ответит: иначе оно сочло бы мёртвыми всех участников"
            )
        else:
            text = "ядро снова пробует серверы по probe.url"
        self.notifier.event("probe", text, notify=on)

    def _containers_appeared(self, applied: dict) -> None:
        """На машине появился Docker, а Xray запущен без inbound'а TUN: контейнерам он
        нужен (их трафик идёт в TUN по метке), до тех пор они без интернета."""
        if self._urgent_rebuild or not engine.containers_tun(self.cfg):
            return
        if tun.inbound_name(applied) == self.cfg.capture.tun_name:
            return
        self._urgent_rebuild = "появился Docker: контейнерам нужен inbound TUN"
        self.notifier.event(
            "capture", "появился Docker — контейнеры пойдут через VPN, Xray перезапускается"
        )

    def _diagnose_target(self, view: list[NodeInfo], applied: dict) -> target.Diagnosis:
        password, _ports = builder.probe_state(applied)
        verdicts = {tag: entry["verdict"] for tag, entry in self.store.scans().items()}
        nodes = target.sample(view, verdicts)
        if not password or not nodes:
            return target.Diagnosis(False)
        with ThreadPoolExecutor(max_workers=min(PROBE_WORKERS, len(nodes))) as pool:
            results = list(pool.map(lambda info: self._scan(info, password), nodes))
        return target.diagnose(results, base_ping=self._base_ping, direct=self._direct_probe)

    def _base_ping(self) -> bool:
        """Базовый запрос через VPN: носят ли серверы трафик вообще."""
        return target.base_ping(self.cfg)

    def _direct_probe(self) -> str:
        """probe.url напрямую, мимо VPN: пусто — отдаётся, иначе класс сбоя."""
        return target.direct_signature(self.cfg, self.mark)

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
        """Выход в домашнюю страну при включённом перехвате — раз на проверку утечки, а не
        на каждом шаге. Причин две: сервер, выбранный балансировщиком, сам выходит в эту
        страну (тогда его меняют запасным), либо трафик идёт мимо Xray (тогда правила
        перехвата загружаются заново). Событие — только когда меняется его текст."""
        home = self.cfg.routing.home_country.upper()
        selected = self._selected() if self._exit_via_xray() == home else None
        if selected is not None:
            tag, pinned = selected
            member = self._member_by_tag(tag)
            if pinned:
                text = (
                    f"выход в {home}: закреплённый вручную сервер {tag} сам выходит в {home} — "
                    "снимите закрепление: xgw unpin"
                )
            elif member is not None and len(member.fingerprint) >= 8:
                self.home_exits.add(member.fingerprint)
                text = f"выход в {home}: сервер {tag} сам выходит в {home} — меняю его на запасной"
            else:
                text = f"выход в {home}: сервер {tag} сам выходит в {home}"
        else:
            try:
                self.reapply_capture()
            except Exception as exc:  # сбой сети не должен ронять шаг watchdog
                self.log.error("правила перехвата не переприменены: %s", exc)
            text = f"выход в {home} мимо Xray при включённом перехвате — правила загружены заново"
        if text != self._leak_note:
            self._leak_note = text
            self.notifier.event("leak", text, notify=True)

    def _member_by_tag(self, tag: str) -> NodeInfo | None:
        applied = engine.read_json(self.paths.xray_config_file)
        view = builder.applied_nodes(applied, self.inventory.nodes if self.inventory else ())
        return next((info for info in view if info.role == "proxy" and info.tag == tag), None)

    def _home_members(self, view: list[NodeInfo]) -> list[str]:
        """Теги участников, которые сами выходят в домашнюю страну."""
        return [
            info.tag for info in view
            if info.role == "proxy" and info.fingerprint in self.home_exits
        ]

    def _capture_waits(self) -> bool:
        """Перехват включён, но правилам нужен inbound, которого в применённом конфиге
        Xray ещё нет."""
        capture = self.capture
        problem = getattr(capture, "inbound_problem", None)
        try:
            return bool(problem is not None and capture.mode() == "on" and problem())
        except Exception as exc:  # сбой сети не должен ронять шаг watchdog
            self.log.debug("состояние перехвата не прочитано: %s", exc)
            return False

    def _guard_capture(self, xray_ok: bool, now: float, *, switched: bool = False) -> None:
        """Следит за правилами перехвата: возвращает пропавшие, а при
        fail_mode = "open" снимает перехват, пока Xray недоступен дольше минуты.
        switched — правила ждали нового inbound'а и Xray только что перезапущен с ним:
        их загрузка — не возврат пропавших, а включение перехвата по новым настройкам."""
        capture = self.capture
        if capture is None:
            return
        if xray_ok:
            self.xray_down_since = None
        elif self.xray_down_since is None:
            self.xray_down_since = now
        try:
            mode = capture.mode()
            if self.cfg.capture.fail_mode == "open":
                down_for = now - self.xray_down_since if self.xray_down_since is not None else 0.0
                if mode == "on" and down_for >= FAIL_OPEN_AFTER:
                    mode = capture.open()
                    self.notifier.event(
                        "capture",
                        "Xray недоступен дольше минуты — перехват временно снят "
                        "(fail_mode = open), трафик идёт напрямую",
                        notify=True,
                    )
                elif mode == "open" and xray_ok:
                    mode = capture.close()
                    self.notifier.event(
                        "capture", "Xray снова отвечает — перехват возвращён", notify=True
                    )
            elif mode == "open":
                mode = capture.close()  # fail_mode сменили на closed, а метка осталась
            loaded = capture.loaded()
            reloaded = loaded is False
            cause = ""
            if reloaded:
                # Правила пропали (чужой flush ruleset, перезапуск nftables), ещё не
                # загружались либо не соответствуют режиму: без них трафик пошёл бы
                # мимо VPN. Либо интерфейс TUN без адреса — его создал сам Xray.
                tun_problem = getattr(capture, "tun_problem", None)
                cause = tun_problem() if tun_problem is not None else ""
                capture.up()
                loaded = capture.loaded()
            info = capture.describe(check=False)
            self.capture_info = {**info, "loaded": loaded}
            missing = str(info.get("inbound_missing") or "")
            if missing:
                if missing != self._inbound_missing:  # одно событие на причину
                    self.notifier.event(
                        "capture",
                        f"перехват не включён: {missing} — трафик идёт напрямую; "
                        "включится сам после перезапуска Xray с новым конфигом",
                        notify=True,
                    )
            elif reloaded and (self._inbound_missing or switched):
                self.notifier.event(
                    "capture", "Xray перезапущен с inbound'ом перехвата — перехват включён",
                    notify=True,
                )
            elif reloaded:
                text = getattr(
                    capture, "reloaded_text", "правила сети не были загружены — загружены заново"
                )
                if cause:
                    text = f"{cause} — интерфейс подготовлен заново"
                self.notifier.event("capture", text, notify=True)
            self._inbound_missing = missing
            self._capture_error = ""
            tidy = getattr(capture, "tidy", None)  # у подставного перехвата в тестах — нет
            tidied = tidy() if tidy is not None else ""
            if tidied:
                self.notifier.event("capture", tidied)
        except Exception as exc:  # сбой сети не должен ронять шаг watchdog
            text = f"правила перехвата не загружены: {exc}"
            self.log.error("%s", text)
            if text != self._capture_error:  # одно событие на причину, а не на каждый шаг
                self._capture_error = text
                self.notifier.event("capture", text, notify=True)

    def _apply_pending(self, urgent: bool) -> bool:
        """Конфиг, ждущий перезапуска: в окне restart_window либо срочно."""
        pending = engine.read_json(self.paths.pending_config_file)
        if pending is None:
            self.paths.pending_config_file.unlink(missing_ok=True)
            return False
        if not urgent:
            applied = engine.read_json(self.paths.xray_config_file) or {}
            if capture_inbounds(pending) != capture_inbounds(applied):
                # Меняется inbound перехвата: правила сети следуют новым настройкам, и
                # ждать окна нельзя — трафик уходил бы на порт или в интерфейс, которых
                # у работающего Xray нет (fail-closed = нет интернета).
                self.log.warning(
                    "применяю конфиг вне окна %s: меняется inbound перехвата",
                    self.cfg.apply.restart_window,
                )
                urgent = True
            elif not in_restart_window(self.cfg.apply.restart_window, self.now_time()):
                return False
        outcome = self._apply(pending, urgent=urgent)
        if outcome.mode == "rejected":
            # Отклонённый конфиг не перепроверяем на каждом шаге: следующее
            # обновление подписки соберёт новый.
            self.paths.pending_config_file.unlink(missing_ok=True)
        return self._report(outcome, "отложенный перезапуск")

    def _refresh(self, now: float, *, via_xray: bool, urgent: bool) -> bool:
        """Опрос подписок и применение изменений."""
        self._refreshing = True
        try:
            return self._refresh_now(now, via_xray=via_xray, urgent=urgent)
        finally:
            self._refreshing = False

    def _refresh_now(self, now: float, *, via_xray: bool, urgent: bool) -> bool:
        minutes = min((sub.refresh_minutes for sub in self.cfg.subscriptions), default=60)
        self.next_refresh = now + jitter(max(1, minutes) * 60.0)
        inventory = self._collect(via_xray)
        self._save_errors(inventory)
        if inventory.nodes:
            self._save_inventory(inventory)
        first_start = not self.paths.xray_config_file.exists()
        if not inventory.nodes and not engine.has_sources(self.cfg):
            # Подписок и ссылок нет вовсе — это не сбой: их добавят в панели. Ядро,
            # если оно уже работало, остаётся на прежних серверах.
            self.next_refresh = now + jitter(SUBSCRIPTION_RETRY)
            return False
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
        self._rebuild_asked = False  # сборка ниже уже учитывает новые настройки
        return self._rebuild(None, urgent=urgent, reason="обновление подписки")

    def _rebuild(self, prefer: list[str] | None, *, urgent: bool, reason: str) -> bool:
        assert self.inventory is not None
        dead = engine.quarantined()
        try:
            assembly = self._assemble(prefer)
        except engine.EngineError as exc:
            self.notifier.event("config", f"{reason}: {exc}", notify=True)
            return False
        finally:
            if engine.quarantined() != dead:
                # Сборка отложила домены, которых нет в DNS. Список для панели записан до
                # неё — иначе там такой сервер значился бы «включён, сейчас возьмёт в работу».
                self._save_inventory(self.inventory)
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

    def _save_inventory(self, inventory: engine.Inventory) -> None:
        try:
            engine.save_inventory(self.paths, self.cfg, inventory)
        except OSError as exc:  # список нужен только панели
            self.log.error("список серверов не записан: %s", exc)

    def _save_errors(self, inventory: engine.Inventory) -> None:
        """Почему подписка не обновилась — чтобы панель показала это рядом с ней."""
        errors = {
            name: {"error": text, "ts": self.wall()} for name, text in inventory.errors.items()
        }
        try:
            if errors or self.store.get_meta("sub_errors") not in (None, "", "{}"):
                self.store.set_meta("sub_errors", json.dumps(errors, ensure_ascii=False))
        except Exception as exc:  # состояние не критично для работы шлюза
            self.log.error("ошибки подписок не записаны: %s", exc)

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

    def _queue_members(self, view: list[NodeInfo]) -> None:
        """Первая проверка участников собственной пробой шлюза — в начало очереди.

        Первый состав балансировщика берётся из подписки без всяких сведений о
        серверах; observatory ядра скажет лишь «жив или нет», и то не сразу. Своя проба
        отличает «заморозку» и отказ в соединении, и такой участник меняется сразу.
        Проверяется каждый участник один раз: дальше за ним следит само ядро.
        """
        queued = set(self.scan_queue)
        for info in reversed([item for item in view if item.role == "proxy"]):
            if len(info.fingerprint) < 8:
                continue  # узел не сопоставлен с подпиской — заменить его всё равно нельзя
            if info.fingerprint not in self.vetted and info.probe_tag not in queued:
                self.scan_queue.appendleft(info.probe_tag)

    def _scan_step(self, view: list[NodeInfo], applied: dict) -> None:
        """Сканирует узлы из очереди, пока не истёк бюджет времени шага."""
        if not self.scan_queue:
            return
        password, _ports = builder.probe_state(applied)
        nodes = {info.probe_tag: info for info in view}
        started = self.clock()
        while self.scan_queue and self.clock() - started < SCAN_BUDGET:
            info = nodes.get(self.scan_queue.popleft())
            if info is None or not password:
                continue
            result = self._scan(info, password)
            self.store.save_scan(
                info.probe_tag, result.verdict, result.bytes_read, result.seconds, result.error,
                ts=self.wall(),
            )
            if info.role == "proxy":
                self.vetted.add(info.fingerprint)
                if result.verdict in REPLACE_NOW_VERDICTS:
                    self.bad_members[info.tag] = result.verdict
                else:
                    self.bad_members.pop(info.tag, None)
            self.log.info(
                "скан %s: %s, %d байт за %.1f с", info.tag, result.verdict,
                result.bytes_read, result.seconds,
            )

    def _scan(self, info: NodeInfo, password: str) -> scan.ScanResult:
        return scan.scan_node(info, self.cfg, probe_pass=password)

    def _rotate(self, view: list[NodeInfo], observatory: dict, state: State, now: float) -> bool:
        """Меняет участников, мёртвых дольше rotate_after_min, на проверенные запасные;
        не прошедших первую проверку (bad_members) — сразу."""
        home = self._home_members(view)
        if self.inventory is None or not (self.dead_since or self.bad_members or home):
            return False
        by_fingerprint = {node.fingerprint: node for node in self.inventory.nodes}
        members = [info for info in view if info.role == "proxy"]
        if any(info.fingerprint not in by_fingerprint for info in members):
            return False  # состав ядра не сопоставлен с подпиской — менять вслепую нельзя
        pairs = [
            (info, by_fingerprint[info.fingerprint])
            for info in view
            if info.role == "spare" and info.fingerprint in by_fingerprint
            and info.fingerprint not in self.home_exits  # тоже выходит в домашнюю страну
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
            alive, self.dead_since, verdicts, seconds, members, pairs, cfg, self.wall(),
            urgent=set(self.bad_members) | set(home),
        )
        if rotation is None:
            overdue = cfg.filters.rotate_after_min * 60.0
            waiting = bool(self.bad_members or home) or any(
                self.wall() - since >= overdue for since in self.dead_since.values()
            )
            if waiting and pairs and not self.scan_queue and now >= self.next_rescan:
                self._queue_scan(view, now)  # менять пора, а свежих сканов нет
            return False
        names = ", ".join(f"{tag} → «{node.name}»" for tag, node in rotation.replacements)
        failed = [
            f"{tag} — {self.bad_members[tag]}"
            for tag, _node in rotation.replacements if tag in self.bad_members
        ]
        leaking = [tag for tag, _node in rotation.replacements if tag in home]
        text = f"замена участников: {names}"
        if failed:
            text += f" (не прошли первую проверку: {', '.join(failed)})"
        if leaking:
            text += (
                f" (сами выходят в {self.cfg.routing.home_country.upper()}: "
                f"{', '.join(leaking)})"
            )
        self.notifier.event("rotation", text, notify=True)
        # Замены пришли из запасных, прошедших скан, — проверять их заново незачем.
        self.vetted.update(node.fingerprint for _tag, node in rotation.replacements)
        for tag, _node in rotation.replacements:
            self.bad_members.pop(tag, None)
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
            capture=self.capture_info, probe_target=self.probe_target,
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
