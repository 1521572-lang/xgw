"""Демон: шаг watchdog на подменённых сигналах — состояния, обновление подписки,
сканы, замена участников, откат, отложенный перезапуск, закрепление."""

import datetime
import json
import threading
import time
from pathlib import Path

import links
import pytest

from xgw import engine
from xgw.apply.applier import ApplyOutcome
from xgw.config import Config
from xgw.daemon import Daemon
from xgw.model import raw_to_node
from xgw.parsers.common import parse_links_text
from xgw.paths import Paths, atomic_write_json
from xgw.store import Store
from xgw.watch.scan import ScanResult
from xgw.watch.states import State
from xgw.xraycore.api import ApiError

ALL_LINKS = [*links.FULL_LINKS, links.TROJAN_INSECURE]


def _inventory(link_list=ALL_LINKS, complete=True) -> engine.Inventory:
    raws, _, _ = parse_links_text("\n".join(link_list), "main")
    quotas = {"main": {"upload": 0, "download": 10**9, "total": 10**12}}
    return engine.Inventory([raw_to_node(raw, "main") for raw in raws], quotas, complete)


class FakeApi:
    def __init__(self):
        self.down = False
        self.calls: list[tuple] = []

    def balancer_info(self, *balancers):
        if self.down:
            raise ApiError("нет связи")
        return ""

    def pin(self, balancer, tag):
        self.calls.append(("pin", tag))

    def unpin(self, balancer):
        self.calls.append(("unpin",))


class FakeService:
    def __init__(self):
        self.active = True
        self.starts = 0

    def is_active(self):
        return self.active

    def start(self):
        self.starts += 1

    def restart(self):
        self.restarts = getattr(self, "restarts", 0) + 1


class FakeApplier:
    def __init__(self):
        self.rollbacks: list[str] = []
        self.rollback_mode = "rollback"

    def rollback(self, reason):
        self.rollbacks.append(reason)
        return ApplyOutcome(self.rollback_mode, detail=reason)


class Harness(Daemon):
    """Демон, у которого всё внешнее — метрики, проверки, подписки, ядро — подменено."""

    def __init__(self, cfg: Config, paths: Paths, **kwargs):
        self.t = time.time()  # и «монотонные», и настенные часы демона; двигаются вручную
        super().__init__(
            cfg, paths, xray_bin=Path("no-such-xray"),
            clock=lambda: self.t, wall=lambda: self.t, **kwargs,
        )
        self.api = FakeApi()
        self.service = FakeService()
        self.applier = FakeApplier()
        self.now_time = lambda: datetime.time(12, 0)
        self.observatory: dict | None = {}  # None — метрики недоступны
        self.provider = True
        self.e2e = True
        self.location: str | None = None
        self.source = _inventory()
        self.collected: list[bool] = []  # значения via_xray
        self.applied: list[tuple[dict, bool]] = []
        self.apply_mode = "api"
        self.verdicts: dict[str, str] = {}  # probe-тег → вердикт скана
        self.default_verdict = "OK"
        self.scanned: list[str] = []
        self.e2e_checks = 0

    def _read_observatory(self):
        if self.observatory is None:
            raise OSError("metrics down")
        return self.observatory

    def _check_provider(self):
        return self.provider

    def _check_e2e(self):
        self.e2e_checks += 1
        return self.e2e

    def _check_leak(self):
        return self.location

    def _collect(self, via_xray):
        self.collected.append(via_xray)
        return self.source

    def _assemble(self, prefer):
        return engine.assemble(
            self.cfg, self.paths, self.inventory, mark=None, logger=self.log,
            xray_bin=None, check=False, prefer=prefer,
        )

    def _apply(self, config, *, urgent):
        if config == engine.read_json(self.paths.xray_config_file):
            return ApplyOutcome("unchanged")
        self.applied.append((config, urgent))
        if self.apply_mode in ("api", "restart"):
            atomic_write_json(self.paths.xray_config_file, config)
            self.paths.pending_config_file.unlink(missing_ok=True)
        return ApplyOutcome(self.apply_mode)

    def _scan(self, info, password):
        self.scanned.append(info.tag)
        verdict = self.verdicts.get(info.probe_tag, self.default_verdict)
        return ScanResult(info.tag, verdict, 65536 if verdict == "OK" else 16384, 0.5)

    # --- удобства для тестов ---

    def tags(self, role: str) -> list[str]:
        config = engine.read_json(self.paths.xray_config_file)
        return [o["tag"] for o in config["outbounds"] if o["tag"].startswith(role + "-")]

    def set_alive(self, **overrides: bool) -> None:
        """Все участники живы, кроме перечисленных (тег с «_» вместо «-»)."""
        dead = {tag.replace("_", "-") for tag, alive in overrides.items() if not alive}
        self.observatory = {
            tag: {"alive": tag not in dead, "delay": 0.05} for tag in self.tags("proxy")
        }

    def events(self) -> list[str]:
        store = Store(self.paths.db_file)
        try:
            return [f"{e['kind']}: {e['detail']}" for e in store.recent_events(50)]
        finally:
            store.close()

    def status(self) -> dict:
        return json.loads(self.paths.status_file.read_text(encoding="utf-8"))


@pytest.fixture()
def daemon(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.filters.max_members = 2
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []  # без сети: домены серверов в тестах не резолвим
    instance = Harness(cfg, paths)
    yield instance
    instance.store.close()


def _started(daemon: Harness) -> Harness:
    """Демон после первого шага: конфиг собран и применён, запасные проверены,
    участники живы."""
    daemon.tick()
    daemon.set_alive()
    daemon.applied.clear()
    daemon.collected.clear()
    daemon.scanned.clear()
    return daemon


def test_first_tick_builds_and_starts(daemon):
    assert daemon.tick() is State.HEALTHY
    assert len(daemon.applied) == 1 and daemon.applied[0][1] is True  # первый запуск — срочно
    assert daemon.collected == [False]  # Xray ещё нет — подписка напрямую
    assert len(daemon.tags("proxy")) == 2 and len(daemon.tags("spare")) == 3
    status = daemon.status()
    assert status["daemon"] is True and status["state"] == "HEALTHY"
    assert [member["alive"] for member in status["members"]] == [None, None]  # проб ещё не было
    assert all(member["name"] for member in status["members"])


def test_healthy_tick_scans_spares_and_writes_status(daemon):
    daemon.tick()
    assert sorted(daemon.scanned) == sorted(daemon.tags("spare"))  # первый скан — сразу
    _started(daemon)
    assert daemon.tick() is State.HEALTHY
    assert daemon.applied == []  # подписка не изменилась — применять нечего
    assert daemon.scanned == []  # следующий скан — только через scan_spares_minutes
    status = daemon.status()
    assert {spare["verdict"] for spare in status["spares"]} == {"OK"}
    assert all(member["alive"] for member in status["members"])
    assert status["quota"]["main"]["total"] == 10**12
    daemon.t += daemon.cfg.probe.scan_spares_minutes * 60 * 1.3
    daemon.next_refresh = daemon.t + 3600
    daemon.tick()
    assert len(daemon.scanned) == 3


def test_scan_does_not_block_watchdog(daemon):
    """Скан идёт порциями в пределах бюджета времени шага."""
    _started(daemon)
    original = daemon._scan

    def slow(info, password):
        daemon.t += 5.0  # каждый скан «занимает» 5 с
        return original(info, password)

    daemon._scan = slow
    daemon.next_scan = 0.0  # пора сканировать заново
    daemon.tick()
    assert len(daemon.scanned) == 2  # бюджет 8 с: два скана, третий — на следующем шаге
    daemon.tick()
    assert len(daemon.scanned) == 3


def test_dead_member_is_replaced_after_rotate_after_min(daemon):
    _started(daemon)
    victim, survivor = daemon.tags("proxy")
    daemon.set_alive(**{victim.replace("-", "_"): False})

    assert daemon.tick() is State.DEGRADED
    assert daemon.applied == []  # мёртв меньше rotate_after_min (15 мин) — ждём
    daemon.t += 14 * 60
    daemon.tick()
    assert daemon.applied == []
    daemon.t += 2 * 60
    daemon.tick()
    daemon.tick()
    assert len(daemon.applied) == 1 and daemon.applied[0][1] is False
    members = daemon.tags("proxy")
    assert victim not in members and survivor in members
    assert victim.replace("proxy-", "spare-") in daemon.tags("spare")
    assert any(event.startswith("rotation:") for event in daemon.events())


def test_frozen_spares_are_not_promoted(daemon):
    daemon.cfg.filters.rotate_after_min = 0
    daemon.default_verdict = "FROZEN"
    _started(daemon)
    victim = daemon.tags("proxy")[0]
    daemon.set_alive(**{victim.replace("-", "_"): False})
    for _ in range(3):
        assert daemon.tick() is State.DEGRADED
    assert daemon.applied == []  # менять не на кого
    assert victim in daemon.tags("proxy")


def test_stale_scans_trigger_rescan_before_rotation(daemon):
    """Менять пора, а сканы устарели: сначала внеочередной скан, потом замена."""
    daemon.cfg.filters.rotate_after_min = 0
    _started(daemon)
    daemon.t += 3 * 3600  # сканы трёхчасовой давности не в счёт
    daemon.next_scan = daemon.t + 3600  # и плановый скан не скоро
    daemon.next_refresh = daemon.t + 3600
    daemon.scanned.clear()
    victim = daemon.tags("proxy")[0]
    daemon.set_alive(**{victim.replace("-", "_"): False})
    daemon.tick()
    assert daemon.applied == [] and daemon.scanned == []  # на этом шаге скан только заказан
    daemon.tick()
    assert len(daemon.scanned) == 3
    assert len(daemon.applied) == 1 and victim not in daemon.tags("proxy")


def test_all_dead_refreshes_directly_and_rotates_at_once(daemon):
    _started(daemon)
    daemon.next_refresh = daemon.t + 3600
    old_members = daemon.tags("proxy")
    daemon.set_alive(**{tag.replace("-", "_"): False for tag in old_members})

    assert daemon.tick() is State.ALL_DEAD
    assert daemon.collected == [False]  # внеочередное обновление — напрямую, мимо Xray
    assert len(daemon.scanned) == 3  # и внеочередной скан запасных
    # замена сразу, без ожидания rotate_after_min (15 мин); перезапуск разрешён
    assert len(daemon.applied) == 1 and daemon.applied[0][1] is True
    daemon.tick()
    daemon.tick()
    assert not set(old_members) & set(daemon.tags("proxy"))
    assert any(event.startswith("ALL_DEAD:") for event in daemon.events())
    # пока все мертвы, подписка не опрашивается на каждом шаге
    assert len(daemon.collected) == 1


def test_e2e_failures_lead_to_all_dead(daemon):
    """Участники по метрикам живы, но загрузка через http-in не идёт."""
    _started(daemon)
    daemon.e2e = False
    states = [daemon.tick() for _ in range(3)]
    assert states == [State.HEALTHY, State.HEALTHY, State.ALL_DEAD]  # fail_threshold = 3
    daemon.e2e = True
    assert daemon.tick() is State.HEALTHY


def test_xray_down_restarts_then_rolls_back_once(daemon):
    _started(daemon)
    daemon.observatory = None
    daemon.api.down = True
    daemon.service.active = False

    assert daemon.tick() is State.XRAY_DOWN
    assert daemon.service.starts == 1 and daemon.applier.rollbacks == []
    assert daemon.e2e_checks == 1  # при лежащем Xray сквозная проверка не запускается
    assert daemon.tick() is State.XRAY_DOWN
    assert len(daemon.applier.rollbacks) == 1  # после двух неудач — откат на last-good
    daemon.tick()
    assert len(daemon.applier.rollbacks) == 1  # один откат на инцидент
    assert any(event.startswith("rollback:") for event in daemon.events())

    daemon.api.down = False  # метрик нет, но API отвечает — ядро живо
    assert daemon.tick() is State.HEALTHY
    daemon.api.down = True
    daemon.tick()
    daemon.tick()
    assert len(daemon.applier.rollbacks) == 2  # новый инцидент — новый отсчёт


def test_wan_down_keeps_quiet(daemon):
    _started(daemon)
    daemon.provider = False
    daemon.next_refresh = 0.0
    checks_before = daemon.e2e_checks
    assert daemon.tick() is State.WAN_DOWN
    assert daemon.collected == [] and daemon.scanned == []  # ни подписок, ни сканов
    assert daemon.e2e_checks == checks_before


def test_incomplete_subscription_is_not_applied(daemon):
    """Подписку получить не удалось даже из кэша — её серверы из ядра не убираем."""
    _started(daemon)
    before = daemon.tags("proxy") + daemon.tags("spare")
    daemon.source = _inventory(links.FULL_LINKS[:1], complete=False)
    daemon.next_refresh = 0.0
    daemon.tick()
    assert daemon.applied == []
    assert daemon.tags("proxy") + daemon.tags("spare") == before
    assert any(event.startswith("subscription:") for event in daemon.events())


def test_subscription_change_is_applied_on_refresh(daemon):
    _started(daemon)
    daemon.source = _inventory(links.FULL_LINKS)  # один сервер пропал из подписки
    daemon.next_refresh = 0.0
    daemon.tick()
    assert len(daemon.applied) == 1 and daemon.collected == [True]  # Xray жив — через него
    assert len(daemon.tags("proxy")) + len(daemon.tags("spare")) == 4


def test_rejected_config_raises_event(daemon):
    _started(daemon)
    daemon.source = _inventory(links.FULL_LINKS)
    daemon.next_refresh = 0.0
    daemon.apply_mode = "rejected"
    daemon.tick()
    assert any("apply:" in event and "отклонён" in event for event in daemon.events())


def test_pending_restart_waits_for_window(daemon):
    _started(daemon)
    pending = engine.read_json(daemon.paths.xray_config_file)
    pending["policy"]["levels"]["0"]["connIdle"] = 999
    atomic_write_json(daemon.paths.pending_config_file, pending)
    daemon.apply_mode = "restart"

    daemon.tick()
    assert daemon.applied == []  # 12:00 — вне окна 04:00–05:00
    assert daemon.status()["pending_restart"] is True
    daemon.now_time = lambda: datetime.time(4, 30)
    daemon.tick()
    assert [config for config, _urgent in daemon.applied] == [pending]
    assert not daemon.paths.pending_config_file.exists()


def test_pending_restart_is_urgent_when_all_dead(daemon):
    _started(daemon)
    pending = engine.read_json(daemon.paths.xray_config_file)
    pending["policy"]["levels"]["0"]["connIdle"] = 999
    atomic_write_json(daemon.paths.pending_config_file, pending)
    daemon.apply_mode = "restart"
    daemon.set_alive(**{tag.replace("-", "_"): False for tag in daemon.tags("proxy")})
    daemon.tick()
    assert daemon.applied == [(pending, True)]  # ALL_DEAD — перезапуск сразу, окна не ждём


def test_rejected_pending_is_dropped(daemon):
    _started(daemon)
    atomic_write_json(daemon.paths.pending_config_file, {"broken": True})
    daemon.apply_mode = "rejected"
    daemon.now_time = lambda: datetime.time(4, 30)
    daemon.tick()
    assert not daemon.paths.pending_config_file.exists()
    daemon.applied.clear()
    daemon.tick()
    assert daemon.applied == []  # отклонённый конфиг не перепроверяется на каждом шаге


def test_pin_expires_and_is_restored_after_apply(daemon):
    _started(daemon)
    target = daemon.tags("proxy")[0]
    daemon.store.set_meta("pin", json.dumps({"tag": target, "until": daemon.t + 60}))

    pending = engine.read_json(daemon.paths.xray_config_file)
    pending["policy"]["levels"]["0"]["connIdle"] = 999
    atomic_write_json(daemon.paths.pending_config_file, pending)
    daemon.apply_mode = "restart"  # перезапуск сбросит закрепление в ядре
    daemon.now_time = lambda: datetime.time(4, 30)
    daemon.tick()
    assert daemon.api.calls == [("pin", target)]  # …поэтому оно выставляется заново
    assert daemon.status()["pin"]["tag"] == target

    daemon.t += 61
    daemon.tick()
    assert daemon.api.calls[-1] == ("unpin",)
    assert daemon.store.get_meta("pin") == ""
    assert daemon.status()["pin"] is None
    daemon.tick()
    assert daemon.api.calls.count(("unpin",)) == 1


def test_leak_is_checked_only_with_capture(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.dns.bootstrap = []
    cfg.filters.exclude_regex = ""
    capture = {"on": False, "reapplied": 0}

    def reapply():
        capture["reapplied"] += 1

    daemon = Harness(cfg, paths, capture_active=lambda: capture["on"], reapply_capture=reapply)
    try:
        _started(daemon)
        daemon.location = "RU"
        assert daemon.tick() is State.HEALTHY  # перехват выключен — выход в RU не утечка
        capture["on"] = True
        assert daemon.tick() is State.LEAK
        assert capture["reapplied"] == 1
        daemon.location = "NL"
        daemon.t += 400  # следующая проверка утечки — через 5 минут
        assert daemon.tick() is State.HEALTHY
    finally:
        daemon.store.close()


def test_budget_warning_is_reported_once(daemon):
    daemon.cfg.probe.interval = "10s"  # 2 участника × 64 КиБ × 8640 ≈ 1,1 ГБ > лимита 1024 МБ
    _started(daemon)
    daemon.tick()
    daemon.tick()
    budget_events = [event for event in daemon.events() if event.startswith("budget:")]
    assert len(budget_events) == 1 and "лимита" in budget_events[0]
    assert daemon.status()["budget"]["warnings"]


def test_run_survives_failing_tick(daemon):
    """Исключение в одном шаге не останавливает демон."""
    stop = threading.Event()
    calls = {"count": 0}

    def tick():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("сбой шага")
        stop.set()
        return State.HEALTHY

    daemon.tick = tick
    daemon.cfg.watchdog.interval_s = 0
    daemon.run(stop)
    assert calls["count"] == 2
    daemon.store = Store(daemon.paths.db_file)  # run() закрыл хранилище — для teardown


def test_pin_is_dropped_when_node_leaves_balancer(daemon):
    _started(daemon)
    daemon.store.set_meta("pin", json.dumps({"tag": "proxy-zz-0000", "until": daemon.t + 600}))
    daemon.source = _inventory(links.FULL_LINKS)
    daemon.next_refresh = 0.0
    daemon.tick()
    assert daemon.api.calls == []  # закреплять нечего: такого участника нет
    assert daemon.store.get_meta("pin") == ""
    assert any("больше не участник" in event for event in daemon.events())


def test_hung_xray_is_restarted_when_nothing_to_roll_back(daemon):
    """Служба числится запущенной, но не отвечает, а last-good совпадает с текущим
    конфигом: откат ничего не даст — демон перезапускает службу сам."""
    _started(daemon)
    daemon.observatory = None
    daemon.api.down = True
    daemon.applier.rollback_mode = "unchanged"
    daemon.tick()
    assert daemon.service.starts == 0  # служба «активна» — запускать нечего
    daemon.tick()
    assert daemon.service.restarts == 1
    daemon.tick()
    assert daemon.service.restarts == 1  # один раз на инцидент
    assert any("служба перезапущена" in event for event in daemon.events())


def test_failed_subscription_is_retried_sooner_but_not_every_tick(daemon):
    daemon.source = engine.Inventory([], {}, False)  # ни серверов, ни кэша
    daemon.tick()
    daemon.tick()
    daemon.tick()
    assert daemon.collected == [False]  # один опрос, а не на каждом шаге
    daemon.t += 150  # повтор — через пару минут, а не через refresh_minutes (час)
    daemon.source = _inventory()
    assert daemon.tick() is State.HEALTHY
    assert len(daemon.collected) == 2 and len(daemon.applied) == 1
