"""Демон: шаг watchdog на подменённых сигналах — состояния, обновление подписки,
сканы, замена участников, откат, отложенный перезапуск, закрепление."""

import datetime
import json
import threading
import time
from pathlib import Path

import links
import pytest

from xgw import engine, fetch
from xgw.apply.applier import ApplyOutcome
from xgw.apply.singbox import SingboxOutcome
from xgw.config import Config, Subscription
from xgw.daemon import Daemon
from xgw.generator import builder
from xgw.model import raw_to_node
from xgw.parsers.common import parse_links_text
from xgw.paths import Paths, atomic_write_json
from xgw.store import Store
from xgw.watch.scan import ScanResult
from xgw.watch.speed import SpeedResult
from xgw.watch.states import State
from xgw.xraycore.api import ApiError, BalancerInfo

ALL_LINKS = [*links.FULL_LINKS, links.TROJAN_INSECURE]


def _inventory(link_list=ALL_LINKS, complete=True) -> engine.Inventory:
    raws, _, _ = parse_links_text("\n".join(link_list), "main")
    quotas = {"main": {"upload": 0, "download": 10**9, "total": 10**12}}
    return engine.Inventory([raw_to_node(raw, "main") for raw in raws], quotas, complete)


class FakeApi:
    def __init__(self):
        self.down = False
        self.calls: list[tuple] = []
        self.state = BalancerInfo(override=None, selects=())

    def balancer_info(self, *balancers):
        if self.down:
            raise ApiError("нет связи")
        return ""

    def balancer_state(self, balancer):
        if self.down:
            raise ApiError("нет связи")
        return self.state

    def pin(self, balancer, tag):
        self.calls.append(("pin", tag))
        self.state = BalancerInfo(override=tag, selects=self.state.selects)

    def unpin(self, balancer):
        self.calls.append(("unpin",))
        self.state = BalancerInfo(override=None, selects=self.state.selects)


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


class FakeSingbox:
    """Второе ядро без процесса: конфиг лежит в файле, служба — флаги."""

    def __init__(self, paths: Paths):
        self.paths = paths
        self.is_alive = True
        self.restart_error: str | None = None
        self.restarts = 0
        self.rollbacks: list[str] = []
        self.rollback_mode = "rollback"
        self.reject = ""
        self.applied: list[tuple[dict | None, bool]] = []

    def read(self):
        return engine.read_json(self.paths.singbox_config_file)

    def expected(self):
        return self.read() is not None

    def alive(self):
        return self.is_alive

    def restart(self):
        self.restarts += 1
        if self.restart_error is None:
            self.is_alive = True
        return self.restart_error

    def rollback(self, reason):
        self.rollbacks.append(reason)
        return SingboxOutcome(self.rollback_mode, reason)

    def apply(self, config, *, reload):
        self.applied.append((config, reload))
        current = self.read()
        if config is None:
            if current is None:
                return SingboxOutcome("unchanged")
            if not reload:
                return SingboxOutcome("deferred")
            self.paths.singbox_config_file.unlink()
            return SingboxOutcome("removed")
        if config == current:
            self.paths.singbox_pending_file.unlink(missing_ok=True)
            return SingboxOutcome("unchanged")
        if not reload:
            self.paths.singbox_config_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_json(self.paths.singbox_pending_file, config)
            return SingboxOutcome("deferred")
        if self.reject:
            return SingboxOutcome("rejected", self.reject)
        self.paths.singbox_config_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.paths.singbox_config_file, config)
        self.paths.singbox_pending_file.unlink(missing_ok=True)
        return SingboxOutcome("started" if current is None else "reloaded")


class Harness(Daemon):
    """Демон, у которого всё внешнее — метрики, проверки, подписки, ядро — подменено."""

    def __init__(self, cfg: Config, paths: Paths, *, fragment: str = "off", **kwargs):
        self.t = time.time()  # и «монотонные», и настенные часы демона; двигаются вручную
        # Дробление ClientHello (0.1.11) проверяют отдельные тесты (fragment="auto"): в
        # остальных запасные с TLS и REALITY, которые не отвечают, иначе проверялись бы ещё
        # и в другом режиме, и сборок конфига было бы больше, чем ждут эти тесты.
        cfg.fragment.mode = fragment
        super().__init__(
            cfg, paths, xray_bin=Path("no-such-xray"),
            clock=lambda: self.t, wall=lambda: self.t, **kwargs,
        )
        self.api = FakeApi()
        self.service = FakeService()
        self.applier = FakeApplier()
        self.singbox = FakeSingbox(paths)
        self.singbox_ok = False  # sing-box в тестах включают отдельные тесты (dual-core)
        self.now_time = lambda: datetime.time(12, 0)
        self.observatory: dict | None = {}  # None — метрики недоступны
        self.provider = True
        self.e2e = True
        self.location: str | None = None
        self.via_location: str | None = None  # страна выхода явно через http-in Xray
        self.source = _inventory()
        self.collected: list[bool] = []  # значения via_xray
        self.applied: list[tuple[dict, bool]] = []
        self.apply_mode = "api"
        self.verdicts: dict[str, str] = {}  # probe-тег → вердикт скана
        self.default_verdict = "OK"
        self.scanned: list[str] = []
        self.scan_urls: dict[str, str] = {}  # тег → адрес последней проверки
        self.e2e_checks = 0
        self.base_ping = False  # базовый запрос через VPN (проверка «не отвечает probe.url»)
        self.direct = ""  # probe.url напрямую: пусто — отдаётся, иначе класс сбоя
        self.failures: dict[str, ScanResult] = {}  # probe-тег → результат пробы с ошибкой
        self.speeds: dict[str, float | None] = {}  # тег → скорость замера (None — не удался)
        self.default_speed: float | None = 50.0
        self.measured: list[str] = []
        self.traffic: int | None = None  # байт через серверы (счётчик Xray); None — нет
        self.downlinks: dict[str, int] = {}  # downlink участников (тег → байт, счётчик Xray)

    def _read_observatory(self):
        if self.observatory is None:
            raise OSError("metrics down")
        outbound = {tag: {"downlink": value, "uplink": 0} for tag, value in self.downlinks.items()}
        if self.traffic is not None:
            outbound["proxy-x"] = {"downlink": self.traffic, "uplink": 0}
        self._metrics = {"stats": {"outbound": outbound}} if outbound else {}
        return self.observatory

    def _downlink_now(self, tag):
        return self.downlinks.get(tag)

    def _check_provider(self):
        return self.provider

    def _check_e2e(self):
        self.e2e_checks += 1
        return self.e2e

    def _check_leak(self):
        return self.location

    def _exit_via_xray(self):
        return self.via_location

    def _collect(self, via_xray):
        self.collected.append(via_xray)
        return self.source

    def _assemble(self, prefer, tier=None, reserve=None, profiles=None, reload_singbox=None):
        return engine.assemble(
            self.cfg, self.paths, self.inventory, mark=None, logger=self.log,
            xray_bin=None, check=False, prefer=prefer, tier=tier, reserve=reserve,
            profiles=profiles, reload_singbox=reload_singbox,
            singbox_ok=self.singbox_ok and not self._singbox_failed,
        )

    def _apply(self, config, *, urgent, singbox=None):
        rejected = self._apply_singbox(singbox)
        if rejected is not None:
            return rejected
        if config == engine.read_json(self.paths.xray_config_file):
            return ApplyOutcome("unchanged")
        self.applied.append((config, urgent))
        if self.apply_mode in ("api", "restart"):
            atomic_write_json(self.paths.xray_config_file, config)
            self.paths.pending_config_file.unlink(missing_ok=True)
        return ApplyOutcome(self.apply_mode)

    def _scan(self, info, password, url=None):
        self.scanned.append(info.tag)
        self.scan_urls[info.tag] = url or self.cfg.probe.url
        if "*" in self.failures or info.probe_tag in self.failures:
            failure = self.failures.get(info.probe_tag) or self.failures["*"]
            return ScanResult(info.tag, failure.verdict, failure.bytes_read, failure.seconds,
                              failure.error, failure.kind, failure.status)
        verdict = self.verdicts.get(info.probe_tag, self.default_verdict)
        return ScanResult(info.tag, verdict, 65536 if verdict == "OK" else 16384, 0.5)

    def _base_ping(self, members=(), password=""):
        return self.base_ping

    def _speed(self, info, password):
        self.measured.append(info.tag)
        mbps = self.speeds.get(info.tag, self.default_speed)
        if mbps is None:
            return SpeedResult(None, 16384, 5.0, "тишина 5 с после 16384 байт тела")
        return SpeedResult(mbps, 10_000_000, round(80.0 / mbps, 2))

    def _direct_probe(self):
        return self.direct

    # --- удобства для тестов ---

    def tags(self, role: str) -> list[str]:
        config = engine.read_json(self.paths.xray_config_file)
        return [o["tag"] for o in config["outbounds"] if o["tag"].startswith(role + "-")]

    def view(self) -> list:
        return builder.applied_nodes(
            engine.read_json(self.paths.xray_config_file),
            self.inventory.nodes if self.inventory else (),
        )

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
    # Основной сервер (0.1.9) проверяется отдельно (test_daemon_main.py): здесь ядро само
    # выбирает сервер, как до него, и вызовы API в тестах прежние.
    cfg.speed.sticky = False
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
    # Первый скан — сразу; вместе с запасными один раз проверяются и сами участники.
    assert sorted(daemon.scanned) == sorted(daemon.tags("proxy") + daemon.tags("spare"))
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

    def slow(info, password, url=None):
        daemon.t += 5.0  # каждый скан «занимает» 5 с
        return original(info, password, url)

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


def _fingerprint(daemon: Harness, tag: str) -> str:
    return next(info.fingerprint for info in daemon.view() if info.tag == tag)


def _by_level(daemon: Harness) -> tuple[str, list[str]]:
    """Первый тик с одним сервером высокого уровня (обычно он был бы запасным):
    его отпечаток и отпечатки остальных (средних) серверов."""
    nodes = sorted(node.fingerprint for node in _inventory().nodes if not node.keep_tag)
    high = nodes[-1]
    daemon.cfg.managed.priority = {high: "high"}
    _started(daemon)
    return high, [fp for fp in nodes if fp != high]


def test_only_servers_of_the_highest_level_work(daemon):
    high, _others = _by_level(daemon)
    members = daemon.tags("proxy")
    assert len(members) == 1 and _fingerprint(daemon, members[0]) == high  # max_members = 2
    assert daemon.status()["tier"] == "high"
    assert {m["priority"] for m in daemon.status()["members"]} == {"high"}


def test_all_dead_on_a_level_goes_down_and_comes_back_when_it_answers(daemon):
    high, others = _by_level(daemon)
    daemon.next_refresh = daemon.t + 3600
    (member,) = daemon.tags("proxy")
    daemon.set_alive(**{member.replace("-", "_"): False})
    # Трафик сразу несёт резервный выход балансировщика — сервер среднего уровня (0.1.8):
    # не ALL_DEAD, а RESERVE.
    assert daemon.tick() is State.RESERVE
    # Живых высокого уровня нет — в работе средние, сразу и с правом перезапуска.
    members = daemon.tags("proxy")
    assert {_fingerprint(daemon, tag) for tag in members} <= set(others) and len(members) == 2
    assert daemon.applied[-1][1] is True
    assert any("на уровне «высокий» живых серверов нет — в работе серверы уровня «средний»"
               in event for event in daemon.events())
    assert daemon.status()["tier"] == "medium"

    # Сервер высокого уровня пока не отвечает: проверяется чаще (TIER_RESCAN), но не берётся.
    daemon.set_alive()
    spare = member.replace("proxy-", "spare-")
    daemon.verdicts[spare.replace("spare-", "probe-")] = "CONNECT_FAIL"
    daemon.applied.clear()
    daemon.scanned.clear()
    for _ in range(3):
        daemon.t += 301
        daemon.tick()
    assert spare in daemon.scanned and daemon.applied == []
    # Ответил — возвращаемся к нему.
    daemon.verdicts.clear()
    daemon.t += 301
    daemon.tick()
    daemon.tick()
    assert [_fingerprint(daemon, tag) for tag in daemon.tags("proxy")] == [high]
    assert any("сервер уровня «высокий» снова отвечает — в работе серверы уровня «высокий»"
               in event for event in daemon.events())


def test_dead_member_is_replaced_only_by_a_spare_of_its_level(daemon):
    """Участник умер, а живые запасные — только уровня ниже: участники разных уровней
    вместе не работают, поэтому замены нет (живой участник того же уровня ещё есть)."""
    daemon.cfg.filters.rotate_after_min = 0
    nodes = sorted(node.fingerprint for node in _inventory().nodes if not node.keep_tag)
    daemon.cfg.managed.priority = dict.fromkeys(nodes[2:], "low")
    _started(daemon)
    victim, _survivor = daemon.tags("proxy")
    daemon.set_alive(**{victim.replace("-", "_"): False})
    for _ in range(3):
        assert daemon.tick() is State.DEGRADED
    assert daemon.applied == [] and victim in daemon.tags("proxy")


def test_chosen_server_keeps_its_level_while_it_answers(daemon):
    """Пока трафик ведёт сервер, выбранный вручную, уровень не меняется; выбранный умер —
    трафик на автовыборе, и уровень меняется, как обычно."""
    high, others = _by_level(daemon)
    (member,) = daemon.tags("proxy")
    daemon.store.set_meta("pin", json.dumps({"tag": member, "until": None}))
    daemon.next_refresh = daemon.t + 3600
    for _ in range(3):
        daemon.t += 20
        daemon.tick()
    assert [_fingerprint(daemon, tag) for tag in daemon.tags("proxy")] == [high]
    daemon.set_alive(**{member.replace("-", "_"): False})
    daemon.tick()
    assert json.loads(daemon.store.get_meta("pin"))["down"]  # трафик — автовыбору
    daemon.tick()
    assert {_fingerprint(daemon, tag) for tag in daemon.tags("proxy")} <= set(others)
    assert any("на уровне «высокий» живых серверов нет" in event for event in daemon.events())


def test_levels_follow_the_real_machine_plan(daemon):
    """Сценарий программы испытаний 0.1.7 (REAL-31…REAL-35): уровни меняют из панели, а
    «мёртвый высокий уровень» — ненастоящий сервер, который проверку не проходит."""
    daemon.tick()
    spare_tags = daemon.tags("spare")
    live, dead, low = (_fingerprint(daemon, tag) for tag in spare_tags)
    verdicts = {spare_tags[1].replace("spare-", "probe-"): "CONNECT_FAIL"}
    daemon.verdicts = dict(verdicts)
    _started(daemon)

    def levels(mapping):
        def change(cfg):
            cfg.managed.priority = dict(mapping)
        return change

    def members(d):
        return sorted(_fingerprint(d, tag) for tag in d.tags("proxy"))

    def step(d, dead_tag=None):
        d.t += 20
        state = d.tick()
        alive = {dead_tag.replace("-", "_"): False} if dead_tag in d.tags("proxy") else {}
        d.set_alive(**alive)
        return state

    # REAL-31: живой запасной — высокий: он один в работе.
    d = _second(daemon, levels({live: "high"}))
    d.tick()  # пересборка после смены настроек; уровень меняет следующий шаг
    d.set_alive()
    d.tick()
    d.set_alive()
    assert members(d) == [live] and d.status()["tier"] == "high"
    # REAL-32, REAL-33: другой — низкий, ненастоящий — высокий: в работе живой и мёртвый.
    d = _second(d, levels({live: "high", low: "low", dead: "high"}))
    d.verdicts = dict(verdicts)
    d.tick()
    dead_tag = next(tag for tag in d.tags("proxy") if _fingerprint(d, tag) == dead)
    d.set_alive(**{dead_tag.replace("-", "_"): False})
    assert d.tick() is State.DEGRADED and members(d) == sorted([live, dead])
    # REAL-34: живой — средний: высокий уровень весь мёртв — в работе средние.
    d = _second(d, levels({low: "low", dead: "high"}))
    d.verdicts = dict(verdicts)
    d.tick()
    assert members(d) == [dead]
    d.set_alive(**{dead_tag.replace("-", "_"): False})
    states = [step(d, dead_tag) for _ in range(3)]
    # Трафик несёт резервный выход — сервер среднего уровня (0.1.8): RESERVE, не ALL_DEAD.
    assert State.RESERVE in states and d.status()["tier"] == "medium"
    assert dead not in members(d) and low not in members(d)
    assert any("на уровне «высокий» живых серверов нет — в работе серверы уровня «средний»"
               in event for event in d.events())
    d.scanned.clear()
    d.applied.clear()
    for _ in range(40):  # 13 минут: мёртвый высокий проверяется, но не берётся
        step(d)
    assert sum(_fingerprint(d, tag) == dead for tag in d.scanned) >= 2 and d.applied == []
    # REAL-35: пока сервер закреплён, уровень не меняется; сняли — снова высокий.
    d.store.set_meta("pin", json.dumps({"tag": d.tags("proxy")[0], "until": d.t + 600}))
    d = _second(d, levels({live: "high", low: "low", dead: "high"}))
    d.verdicts = dict(verdicts)
    for _ in range(9):
        step(d)
    assert d.status()["tier"] == "medium"
    d.store.set_meta("pin", "")
    for _ in range(3):
        step(d)
    assert d.status()["tier"] == "high" and members(d) == sorted([live, dead])
    assert any("сервер уровня «высокий» снова отвечает" in event for event in d.events())


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
    daemon.cfg.probe.interval = "10s"  # 2 участника × 57 620 Б × 8640 ≈ 1 ГБ в сутки
    daemon.cfg.probe.max_daily_probe_mb = 900
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
    assert daemon.api.calls == []  # закреплять нечего: такого сервера нет
    assert daemon.store.get_meta("pin") == ""
    assert any("больше нет среди серверов" in event for event in daemon.events())


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


# --- перехват: слежение за правилами, fail_mode = open, утечка -------------------


class FakeCapture:
    """Перехват на подменённом ядре: режим, загружены ли правила, история вызовов."""

    def __init__(self):
        self.state = "on"
        self.is_loaded = True
        self.fail = False
        self.calls: list[str] = []
        self.problem = ""  # какого inbound'а нет в применённом конфиге Xray
        self.blocked = False  # при problem: hold = "block" — трафик заблокирован
        self.tun_issue = ""  # что не так с интерфейсом TUN
        self.lan_issue = ""  # пакеты устройств сети не доходят до Xray (Capture.lan_path)
        self.lan_fixed_by_up = True  # загрузка правил заново это чинит

    def mode(self):
        return self.state

    def loaded(self):
        self.calls.append("loaded?")
        return self.is_loaded

    def up(self):
        self.calls.append("up")
        if self.fail:
            raise RuntimeError("nft: программа не найдена")
        self.is_loaded = True
        self.tun_issue = ""
        if self.lan_fixed_by_up:
            self.lan_issue = ""
        return self.state

    def tun_problem(self):
        self.calls.append("tun?")
        return self.tun_issue

    def actions(self) -> list[str]:
        """Что демон делал с правилами (без чтений состояния)."""
        return [call for call in self.calls if not call.endswith("?")]

    def open(self):
        self.calls.append("open")
        self.state = "open"
        return self.state

    def close(self):
        self.calls.append("close")
        self.state = "on"
        return self.state

    def describe(self, *, check=True):
        return {"mode": self.state, "lan_if": "lan0", "lan": True, "local": True,
                "bypass": [], "fail_mode": "closed", "loaded": None,
                "inbound_missing": self.problem if self.state == "on" else "",
                "blocked": bool(self.problem) and self.blocked and self.state == "on"}

    def inbound_problem(self):
        self.calls.append("problem?")
        return self.problem

    def lan_path(self):
        self.calls.append("lan?")
        return self.lan_issue


@pytest.fixture()
def guarded(tmp_path, monkeypatch):
    """Демон шлюза с перехватом; возвращает (демон, перехват)."""
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.filters.max_members = 2
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []
    capture = FakeCapture()
    instance = Harness(cfg, paths, capture=capture)
    _started(instance)
    yield instance, capture
    instance.store.close()


def test_daemon_reloads_missing_rules(guarded):
    """Чужой flush ruleset или перезапуск nftables: правила пропали — демон их возвращает."""
    daemon, capture = guarded
    assert capture.actions() == [] and daemon.status()["capture"]["loaded"] is True
    capture.is_loaded = False
    daemon.tick()
    assert capture.actions() == ["up"]
    assert any("загружены заново" in event for event in daemon.events())
    assert daemon.status()["capture"]["mode"] == "on"
    daemon.tick()
    assert capture.actions() == ["up"]  # правила на месте — больше ничего не делает


def test_daemon_names_the_tun_without_an_address(guarded):
    """Интерфейс TUN без адреса (его пересоздал сам Xray, отчёт 0.1.4, G7): демон загружает
    правила заново — это готовит интерфейс — и называет причину, а не «правила пропали»."""
    daemon, capture = guarded
    capture.is_loaded = False
    capture.tun_issue = "у интерфейса xgwtun0 нет адреса 169.254.10.1/32 или он не поднят"
    daemon.tick()
    assert capture.actions() == ["up"]
    assert any(
        "нет адреса 169.254.10.1/32" in event and "подготовлен заново" in event
        for event in daemon.events()
    )
    assert not any("загружены заново" in event for event in daemon.events())


def test_daemon_repairs_lan_path(guarded):
    """Issue #1: правила на месте, а пакеты устройств сети гибнут до Xray — демон загружает
    правила заново (маршрут throw) в том же шаге и пишет событие без уведомления."""
    daemon, capture = guarded
    capture.lan_issue = "пакеты устройств сети lan0 не доходят до Xray"
    daemon.tick()
    assert capture.actions() == ["up"]
    assert any("интернет в сети снова есть" in event for event in daemon.events())
    assert daemon.status()["capture"]["lan_problem"] == ""
    assert daemon.status()["capture"]["lifecycle"] == "connected"


def test_daemon_reports_dead_lan_path(guarded):
    """Загрузка заново не помогла: событие с уведомлением — одно на причину, причина в
    статусе (панель и `xgw status` не показывают «всё в порядке»), перехват — «закрыт»."""
    daemon, capture = guarded
    problem = "пакеты устройств сети lan0 не доходят до Xray: ядро их отбрасывает"
    capture.lan_issue, capture.lan_fixed_by_up = problem, False
    for _ in range(3):
        daemon.tick()
    alerts = [event for event in daemon.events() if "нет интернета у устройств сети" in event]
    assert len(alerts) == 1 and problem in alerts[0]
    snapshot = daemon.status()["capture"]
    assert snapshot["lan_problem"] == problem
    assert snapshot["lifecycle"] == "blocked" and snapshot["lifecycle_reason"] == problem
    capture.lan_issue = ""
    daemon.tick()
    assert any("снова выходят в интернет" in event for event in daemon.events())
    assert daemon.status()["capture"]["lan_problem"] == ""


def test_rules_failure_is_reported_once(guarded):
    daemon, capture = guarded
    capture.is_loaded, capture.fail = False, True
    for _ in range(3):
        assert daemon.tick() is State.HEALTHY  # сбой сети шаг watchdog не роняет
    assert capture.actions() == ["up"] * 3  # попытки продолжаются
    failures = [event for event in daemon.events() if "не загружены" in event]
    assert len(failures) == 1 and "nft" in failures[0]  # а событие — одно на причину


def test_fail_open_removes_capture_while_xray_is_down(guarded):
    daemon, capture = guarded
    daemon.cfg.capture.fail_mode = "open"
    daemon.observatory, daemon.api.down = None, True  # Xray не отвечает
    daemon.tick()
    daemon.t += 30
    daemon.tick()
    assert "open" not in capture.calls  # меньше минуты — перехват держится
    daemon.t += 31
    daemon.tick()
    assert capture.calls.count("open") == 1 and capture.state == "open"
    daemon.t += 20
    daemon.tick()
    assert capture.calls.count("open") == 1  # уже снят
    assert daemon.status()["capture"]["mode"] == "open"

    daemon.api.down = False
    daemon.set_alive()
    daemon.tick()
    assert capture.actions()[-1] == "close" and capture.state == "on"
    events = daemon.events()
    assert any("временно снят" in event for event in events)
    assert any("перехват возвращён" in event for event in events)


def test_fail_closed_keeps_capture_while_xray_is_down(guarded):
    daemon, capture = guarded
    daemon.observatory, daemon.api.down = None, True
    for _ in range(5):
        daemon.t += 60
        assert daemon.tick() is State.XRAY_DOWN
    assert capture.actions() == [] and capture.state == "on"  # трафик никуда не уходит


def test_short_xray_outage_does_not_open_capture(guarded):
    daemon, capture = guarded
    daemon.cfg.capture.fail_mode = "open"
    daemon.observatory, daemon.api.down = None, True
    daemon.tick()
    daemon.t += 40
    daemon.api.down = False
    daemon.set_alive()
    daemon.tick()  # Xray вернулся — отсчёт сброшен
    daemon.observatory, daemon.api.down = None, True
    daemon.t += 40
    daemon.tick()
    assert "open" not in capture.calls


def test_tailscale_goes_direct_while_xray_is_down(guarded):
    """tailscale.route = "vpn" (Т1): шаг сообщает перехвату, отвечает ли Xray, — с первого
    же шага без Xray, не дожидаясь минуты fail_mode; перекладка — событие в журнале."""
    daemon, capture = guarded
    moves: list[bool] = []

    def tailscale_direct(xray_down: bool) -> str:
        changed = bool(moves) and moves[-1] != xray_down
        moves.append(xray_down)
        if not changed:
            return ""
        return ("Xray не отвечает — Tailscale идёт напрямую, мимо VPN" if xray_down
                else "Xray отвечает — Tailscale снова идёт через VPN")

    capture.tailscale_direct = tailscale_direct
    daemon.tick()
    assert moves == [False]
    daemon.observatory, daemon.api.down = None, True
    daemon.tick()
    assert moves == [False, True] and capture.actions() == []  # правила не перезагружались
    daemon.api.down = False
    daemon.set_alive()
    daemon.tick()
    assert moves[-1] is False
    events = daemon.events()
    assert any("Tailscale идёт напрямую" in event for event in events)
    assert any("Tailscale снова идёт через VPN" in event for event in events)


def test_leak_reloads_rules_only_when_own_traffic_is_captured(guarded):
    daemon, capture = guarded
    daemon.location = "RU"
    daemon.t += 400
    assert daemon.tick() is State.LEAK
    assert capture.actions() == ["up"]
    assert any(event.startswith("leak:") for event in daemon.events())

    # capture.local = false: обычный сокет шлюза ходит напрямую по праву — это не утечка.
    daemon.cfg.capture.local = False
    daemon.t += 400
    assert daemon.tick() is State.HEALTHY
    assert capture.actions() == ["up"]


# --- уведомления и перечитывание конфига (этап 4) ---


def test_state_change_reaches_the_sinks_once_per_kind(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.filters.max_members = 2
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []
    sent: list[tuple[str, str]] = []
    instance = Harness(cfg, paths, sinks=[lambda kind, text: sent.append((kind, text))])
    try:
        _started(instance)
        assert sent == []  # в HEALTHY уведомлять не о чем
        instance.observatory, instance.api.down = None, True
        assert instance.tick() is State.XRAY_DOWN
        assert [kind for kind, _ in sent] == ["XRAY_DOWN"]
        assert "HEALTHY → XRAY_DOWN" in sent[0][1]
        instance.tick()
        assert len([kind for kind, _ in sent if kind == "XRAY_DOWN"]) == 1
    finally:
        instance.store.close()


def test_run_returns_when_the_config_file_changes(daemon):
    import threading

    stop = threading.Event()
    ticks: list[int] = []
    daemon.tick = lambda: ticks.append(1) or State.HEALTHY
    daemon.cfg.watchdog.interval_s = 0
    daemon.store = type("Closed", (), {"close": lambda self: ticks.append(-1)})()
    daemon.run(stop, changed=lambda: len(ticks) >= 2)
    assert ticks == [1, 1, -1] and not stop.is_set()


# --- запросы из панели ---------------------------------------------------------


def test_refresh_request_is_served_on_the_next_tick(daemon):
    _started(daemon)
    daemon.tick()
    assert daemon.collected == []  # до срока обычный шаг подписки не трогает
    daemon.request_refresh()
    assert daemon.refresh_pending and daemon.poke.is_set()
    daemon.tick()
    assert daemon.collected == [True] and not daemon.refresh_pending


def test_scan_request_checks_the_spares_now(daemon):
    _started(daemon)
    daemon.tick()
    assert daemon.scanned == []
    daemon.request_scan()
    assert daemon.scan_pending
    daemon.tick()
    assert sorted(daemon.scanned) == sorted(daemon.tags("spare")) and not daemon.scan_pending


def test_pause_between_ticks_ends_on_a_request_a_change_or_a_stop(daemon):
    stop = threading.Event()
    started = time.monotonic()
    daemon.poke.set()
    daemon._sleep(stop, lambda: False, 60.0)
    assert not daemon.poke.is_set()
    daemon._sleep(stop, lambda: True, 60.0)
    stop.set()
    daemon._sleep(stop, lambda: False, 60.0)
    assert time.monotonic() - started < 5


# --- остановка посреди шага (отчёт 0.1.15, Д2) ---------------------------------------


def _run_once(daemon: Harness, stop: threading.Event) -> list[int]:
    """run до остановки; сколько шагов он успел. Хранилище run закрывает — открыть снова."""
    ticks: list[int] = []
    tick = daemon.tick
    daemon.tick = lambda: ticks.append(1) or tick()
    daemon.run(stop)
    daemon.store = Store(daemon.paths.db_file)
    return ticks


def test_stop_during_scans_ends_the_step_at_once(daemon):
    """SIGTERM посреди сканов: прерванный скан не записывается, следующие не начинаются,
    run возвращается сразу после этого шага (на машине шаг доделывался 79 с)."""
    _started(daemon)
    stop = threading.Event()
    original = daemon._scan

    def scan(info, password, url=None):
        if not daemon.scanned:
            return original(info, password, url)
        stop.set()  # остановка приходит во время второго скана
        daemon.scanned.append(info.tag)
        return ScanResult(info.tag, "CANCELLED", 0, 0.3, "прервано", "cancelled")

    daemon._scan = scan
    daemon.next_scan = 0.0
    assert _run_once(daemon, stop) == [1]
    assert len(daemon.scanned) == 2  # третий запасной не сканировался
    assert "CANCELLED" not in {entry["verdict"] for entry in daemon.store.scans().values()}


def test_stop_during_a_refresh_does_not_start_an_apply(daemon):
    """Остановка пришла, пока опрашивались подписки: новый конфиг не применяется — начатое
    применение не прерывается, а systemd ждать его не обязан."""
    _started(daemon)
    stop = threading.Event()
    before = engine.read_json(daemon.paths.xray_config_file)
    daemon.source = _inventory(links.FULL_LINKS)  # один сервер пропал из подписки
    collect = daemon._collect
    daemon._collect = lambda via_xray: stop.set() or collect(via_xray)
    daemon.next_refresh = 0.0
    assert _run_once(daemon, stop) == [1]
    assert daemon.collected == [True] and daemon.applied == []
    assert engine.read_json(daemon.paths.xray_config_file) == before


def test_stop_during_a_subscription_poll_ends_it_at_once(daemon, monkeypatch):
    """SIGTERM, пока подписка ждёт ответа: ожидание прерывается, следующая подписка не
    запрашивается, и прерванный опрос — не сбой подписки (ни события, ни ошибки в панели,
    ни нового списка серверов). На машине такая остановка ждала таймаутов запроса."""
    _started(daemon)
    daemon.cfg.subscriptions = [Subscription(name="main", url="https://subs.example.org/a"),
                                Subscription(name="second", url="https://subs.example.org/b")]
    daemon._collect = lambda via_xray: Daemon._collect(daemon, via_xray)
    monkeypatch.setattr(engine, "healthy_http_in", lambda _cfg: None)
    stop = threading.Event()
    asked: list[str] = []

    def fake(url, **kwargs):
        asked.append(url)
        stop.set()  # SIGTERM пришёл, пока ждали ответа
        cancel = kwargs.get("cancel")
        if cancel is not None and cancel.wait(5):
            raise fetch.Cancelled
        raise fetch.FetchError("timed out")

    monkeypatch.setattr(engine.fetch, "fetch_subscription", fake)
    inventory_before = engine.inventory_file(daemon.paths).read_bytes()
    daemon.next_refresh = 0.0
    started = time.monotonic()
    assert _run_once(daemon, stop) == [1]
    assert time.monotonic() - started < 2
    assert asked == ["https://subs.example.org/a"]
    assert daemon.applied == [] and daemon._sub_failing_since is None
    assert daemon.store.get_meta("sub_errors") in (None, "", "{}")
    assert not any(event.startswith("subscription") for event in daemon.events())
    assert engine.inventory_file(daemon.paths).read_bytes() == inventory_before


def test_stop_leaves_a_pending_config_for_the_next_start(daemon):
    """Отложенный конфиг в окне перезапуска, а демон останавливается: Xray не
    перезапускается, файл ждёт следующего запуска."""
    _started(daemon)
    pending = engine.read_json(daemon.paths.xray_config_file)
    pending["policy"]["levels"]["0"]["connIdle"] = 999
    atomic_write_json(daemon.paths.pending_config_file, pending)
    daemon.apply_mode = "restart"
    daemon.now_time = lambda: datetime.time(4, 30)
    stop = threading.Event()
    daemon.tick = lambda tick=daemon.tick: stop.set() or tick()  # SIGTERM в начале шага
    daemon.run(stop)
    daemon.store = Store(daemon.paths.db_file)
    assert daemon.applied == [] and daemon.paths.pending_config_file.exists()


def test_probes_get_the_stop_event(daemon, monkeypatch):
    """Сканы и замеры скорости получают событие остановки: их ожидание сети прерывается
    (watch/checks.py), а не тянется до таймаута."""
    from xgw.watch import scan, speed

    _started(daemon)
    info = daemon.view()[0]
    seen: dict[str, object] = {}
    monkeypatch.setattr(scan, "scan_node", lambda *_a, **kw: seen.setdefault("scan", kw["cancel"]))
    monkeypatch.setattr(speed, "measure", lambda *_a, **kw: seen.setdefault("speed", kw["cancel"]))
    stop = threading.Event()
    daemon.tick = lambda: stop.set() or State.HEALTHY
    daemon.run(stop)
    daemon.store = Store(daemon.paths.db_file)
    Daemon._scan(daemon, info, "secret")
    Daemon._speed(daemon, info, "secret")
    assert seen == {"scan": stop, "speed": stop}


def test_server_list_is_saved_for_the_panel_without_keys(daemon):
    _started(daemon)
    servers = engine.load_inventory(daemon.paths)
    assert len(servers) == len(ALL_LINKS)
    assert {server["source"] for server in servers} == {"main"}
    assert all(set(server) == {"fingerprint", "name", "source", "protocol", "core", "skip"}
               for server in servers)
    text = engine.inventory_file(daemon.paths).read_text(encoding="utf-8")
    assert links.FAKE_PBK not in text and "203.0.113." not in text  # ни ключей, ни адресов
    status = daemon.status()
    known = {server["fingerprint"] for server in servers}
    assert {node["fingerprint"] for node in [*status["members"], *status["spares"]]} == known


def _second(daemon: Harness, change) -> Harness:
    """Демон после перечитывания настроек: тот же каталог, изменённый конфиг."""
    import copy

    cfg = copy.deepcopy(daemon.cfg)
    change(cfg)
    second = Harness(cfg, daemon.paths)
    second.t = daemon.t
    second.adopt(daemon)
    return second


def test_disabled_server_leaves_the_core_without_asking_subscriptions_again(daemon):
    _started(daemon)
    from xgw.generator import builder

    applied = engine.read_json(daemon.paths.xray_config_file)
    member = next(
        info for info in builder.applied_nodes(applied, daemon.inventory.nodes)
        if info.role == "proxy"
    )
    assert len(member.fingerprint) == 8
    second = _second(daemon, lambda cfg: cfg.managed.disabled.append(member.fingerprint))
    try:
        second.tick()
        assert second.collected == []  # подписки заново не запрашивались
        assert len(second.applied) == 1
        tags = [*second.tags("proxy"), *second.tags("spare")]
        assert member.tag not in tags and len(tags) == len(ALL_LINKS) - 1
        assert len(second.tags("proxy")) == 2  # его место занял другой сервер
        listed = {server["fingerprint"] for server in engine.load_inventory(second.paths)}
        assert member.fingerprint in listed  # в списке панели он остаётся — отключённым
        assert any("изменение настроек" in event for event in second.events())
        second.tick()
        assert len(second.applied) == 1  # второй раз пересобирать нечего
    finally:
        second.store.close()


def test_new_subscription_is_fetched_at_once(daemon):
    _started(daemon)
    second = _second(daemon, lambda cfg: cfg.manual.links.append(links.SS_PLAIN))
    try:
        second.tick()
        assert second.collected == [True]  # источники изменились — опрос сразу
    finally:
        second.store.close()


def test_subscription_errors_reach_the_status(daemon):
    _started(daemon)
    daemon.source.errors = {"main": "HTTP 403"}
    daemon.request_refresh()
    daemon.tick()
    assert daemon.status()["sub_errors"]["main"]["error"] == "HTTP 403"
    daemon.source.errors = {}
    daemon.request_refresh()
    daemon.tick()
    assert daemon.status()["sub_errors"] == {}


def test_no_subscriptions_yet_is_not_an_error(daemon):
    """Установка без подписок: их добавят в панели, уведомлять не о чем."""
    daemon.source = engine.Inventory([], {}, True)
    assert daemon.tick() is State.HEALTHY
    daemon.t += 1000
    daemon.tick()
    assert daemon.applied == [] and daemon.events() == []
    assert daemon.status()["members"] == []


# --- перехват ждёт inbound в Xray --------------------------------------------------


def test_capture_waiting_for_the_inbound_is_reported_once_and_then_turns_on(guarded):
    """Перехват включён, но Xray работает без нужного inbound'а: вместо правил перехвата
    загружен режим «снят». Демон говорит об этом один раз и включает перехват сам, как
    только конфиг применён."""
    daemon, capture = guarded
    capture.problem = "в применённом конфиге Xray нет inbound tun-in для интерфейса xgwtun0"
    for _ in range(3):
        daemon.tick()
    told = [event for event in daemon.events() if "перехват не включён" in event]
    assert len(told) == 1 and "tun-in" in told[0] and "трафик идёт напрямую" in told[0]
    assert capture.actions() == []  # загружено то, что и должно быть: перезагружать нечего
    assert daemon.status()["capture"]["inbound_missing"] == capture.problem

    capture.problem, capture.is_loaded = "", False  # Xray перезапущен с inbound'ом
    daemon.tick()
    assert capture.actions() == ["up"]
    assert any("Xray перезапущен с inbound'ом перехвата — перехват включён" in event
               for event in daemon.events())
    assert not any("загружены заново" in event for event in daemon.events())
    assert daemon.status()["capture"]["inbound_missing"] == ""


def test_blocked_notification_is_sent(guarded):
    """capture.hold = "block": об этом уведомление (оно уходит и в blocked — через http-in
    Xray либо напрямую с меткой 2), и текст честный: трафик не идёт напрямую, он закрыт."""
    daemon, capture = guarded
    capture.problem = "в применённом конфиге Xray нет inbound tproxy-in на порту 12345"
    capture.blocked = True
    daemon.tick()
    daemon.tick()
    told = [event for event in daemon.events() if "перехват не включён" in event]
    assert len(told) == 1 and "tproxy-in" in told[0]
    assert "трафик заблокирован" in told[0] and "напрямую" not in told[0]
    assert daemon.status()["capture"]["blocked"] is True


def test_capture_that_keeps_failing_to_load_is_reported_once(guarded):
    """Причина не уходит (интерфейс TUN так и не появился): демон пробует на каждом
    шаге, а событие — одно, без «правила загружены заново» вдогонку."""
    daemon, capture = guarded
    capture.problem = "TUN-интерфейса xgwtun0 нет в системе"
    capture.is_loaded = False
    capture.up = lambda: capture.calls.append("up") or "off"  # загрузка не помогает
    for _ in range(3):
        daemon.tick()
    assert capture.actions() == ["up"] * 3
    told = [event for event in daemon.events() if event.startswith("capture:")]
    assert len(told) == 1 and "перехват не включён: TUN-интерфейса" in told[0]


def test_new_config_is_applied_before_the_rules_when_capture_waits_for_it(guarded):
    """Настройки изменились так, что правилам нужен inbound, которого у Xray ещё нет.
    Сначала применяется конфиг (Xray перезапускается), и только потом проверяются
    правила: загрузи демон их первым, перехват на это время был бы снят."""
    daemon, capture = guarded
    order: list[str] = []
    original_apply, original_loaded = daemon._apply, capture.loaded

    def apply(config, *, urgent, singbox=None):
        order.append("apply")
        capture.problem = ""  # Xray перезапущен с новым конфигом
        return original_apply(config, urgent=urgent, singbox=singbox)

    def loaded():
        order.append("rules")
        return original_loaded()

    daemon._apply, capture.loaded = apply, loaded
    capture.problem = "в применённом конфиге Xray нет inbound tproxy-in на порту 12346"
    daemon.cfg.filters.max_members = 3  # собранный конфиг отличается от применённого
    daemon._rebuild_asked = True
    daemon.tick()
    assert order[:2] == ["apply", "rules"], order

    # Обычный шаг: правила проверяются первыми, а после применения — ещё раз.
    order.clear()
    daemon.cfg.filters.max_members = 2
    daemon._rebuild_asked = True
    daemon.tick()
    assert order == ["rules", "apply", "rules"], order
    order.clear()
    daemon.tick()
    assert order == ["rules"]  # применять нечего — одна проверка за шаг


def test_switched_capture_is_reported_as_turned_on_not_as_lost_rules(guarded):
    """Смена способа перехвата на TUN на живом шлюзе (WIN-03, Ubuntu 24.04): Xray сразу
    перезапущен с новым inbound'ом, правила нового режима загружены. Событие — «перехват
    включён», а не «правила сети не были загружены», будто их кто-то стёр."""
    daemon, capture = guarded
    original_apply = daemon._apply

    def apply(config, *, urgent, singbox=None):
        capture.problem = ""  # Xray перезапущен с новым конфигом
        return original_apply(config, urgent=urgent, singbox=singbox)

    daemon._apply = apply
    capture.problem = "в применённом конфиге Xray нет inbound tun-in для интерфейса xgwtun0"
    capture.is_loaded = False  # правила нового режима ещё не загружены
    daemon.cfg.filters.max_members = 3  # собранный конфиг отличается от применённого
    daemon._rebuild_asked = True
    daemon.tick()
    assert capture.actions() == ["up"]
    told = [event for event in daemon.events() if event.startswith("capture:")]
    assert told == ["capture: Xray перезапущен с inbound'ом перехвата — перехват включён"]


def test_pending_config_with_a_new_capture_inbound_does_not_wait_for_the_window(daemon):
    """Отложенный конфиг меняет inbound перехвата (здесь появляется tun-in): ждать окна
    04:00–05:00 нельзя — трафик уходил бы в интерфейс, из которого Xray не читает."""
    _started(daemon)
    pending = engine.read_json(daemon.paths.xray_config_file)
    pending["inbounds"].insert(
        0, {"tag": "tun-in", "protocol": "tun", "settings": {"name": "xgwtun0", "mtu": 1500}})
    atomic_write_json(daemon.paths.pending_config_file, pending)
    daemon.apply_mode = "restart"
    daemon.tick()  # 12:00 — вне окна
    assert daemon.applied == [(pending, True)]
    assert not daemon.paths.pending_config_file.exists()


# --- не отвечает сам probe.url ------------------------------------------------------


def _http_403() -> ScanResult:
    return ScanResult("", "CONNECT_FAIL", 0, 0.3, "HTTP 403", "http", 403)


def test_dead_probe_url_is_told_apart_from_dead_servers(daemon):
    """Адрес пробы отвечает 403 всем: сквозная проверка не проходит, собственные пробы
    падают у участников и запасных одинаково, напрямую — тот же ответ. Серверы при этом
    живы: менять их и внеочередно обновлять подписку незачем."""
    daemon.cfg.filters.rotate_after_min = 0
    _started(daemon)
    daemon.next_refresh = daemon.t + 3600
    daemon.e2e = False
    daemon.failures["*"] = _http_403()
    daemon.direct = "HTTP 403"
    # Ядро тоже считает всех мёртвыми: его пробы идут на тот же адрес.
    daemon.set_alive(**{tag.replace("-", "_"): False for tag in daemon.tags("proxy")})
    members = daemon.tags("proxy")

    # Все участники «мертвы» — проверка сразу, не дожидаясь fail_threshold: иначе шаг
    # ушёл бы в ALL_DEAD со сканом запасных и внеочередным обновлением подписки.
    assert daemon.tick() is State.PROBE_TARGET_UNREACHABLE
    assert sorted(daemon.scanned) == sorted([*members, *daemon.tags("spare")])  # диагностика
    # Ядро переведено на запасной адрес проб — срочно, без окна перезапуска; состав прежний.
    assert len(daemon.applied) == 1 and daemon.applied[0][1] is True
    probes = daemon.applied[0][0]["burstObservatory"]["pingConfig"]["destination"]
    assert probes == daemon.cfg.probe.trace_url and daemon.tags("proxy") == members
    assert daemon.collected == []
    assert any("ядро пробует серверы по" in event for event in daemon.events())
    daemon.applied.clear()
    daemon.scanned.clear()
    for _ in range(4):
        assert daemon.tick() is State.PROBE_TARGET_UNREACHABLE
    assert daemon.applied == [] and daemon.tags("proxy") == members  # замен нет
    assert daemon.collected == []  # подписка не обновляется внеочередно
    assert daemon.scanned == []  # сканы и повторная диагностика — не на каждом шаге

    status = daemon.status()
    assert status["state"] == "PROBE_TARGET_UNREACHABLE"
    warning = "Внимание: пробы всех серверов падают — вероятно, недоступен сам probe.url"
    assert status["probe_target"].startswith(warning) and "HTTP 403" in status["probe_target"]
    events = [event for event in daemon.events() if event.startswith("PROBE_TARGET_UNREACHABLE:")]
    assert len(events) == 1 and warning in events[0]
    assert "Замена серверов приостановлена" in events[0]
    # Вердикты запасных не затёрты: после возврата адреса замены будут из кого выбирать.
    assert {spare["verdict"] for spare in status["spares"]} == {"OK"}
    text = __import__("xgw.watch.status", fromlist=["render_status"]).render_status(status)
    assert warning in text

    # Проверка запасных по кнопке в это время откладывается — и говорит почему.
    daemon.request_scan()
    daemon.tick()
    assert daemon.scanned == [] and not daemon.scan_pending
    assert any("проверка запасных отложена" in event for event in daemon.events())

    # Раз в пять минут диагностика повторяется: адрес мог вернуться не для всех.
    daemon.t += 301
    daemon.tick()
    assert len(daemon.scanned) == 5  # два участника и три запасных

    daemon.e2e = True
    daemon.failures.clear()
    daemon.set_alive()
    daemon.applied.clear()
    assert daemon.tick() is State.HEALTHY
    assert daemon.status()["probe_target"] == ""
    assert any("probe.url снова отвечает" in event for event in daemon.events())
    # Ядро вернулось к probe.url.
    assert len(daemon.applied) == 1 and daemon.applied[0][1] is True
    probes = daemon.applied[0][0]["burstObservatory"]["pingConfig"]["destination"]
    assert probes == daemon.cfg.probe.url


def test_leak_does_not_hide_a_dead_probe_url(tmp_path, monkeypatch):
    """Живая машина, 14.10: балансировщик выбрал сервер с выходом в RU (LEAK), и тут же
    перестал отвечать probe.url. LEAK стоит в машине состояний выше и заслонял признак:
    пятнадцать минут шли сканы, вердикты запасных портились, а потом шаг ушёл в ALL_DEAD и
    начал менять живые серверы. Теперь сканы и замена ждут по самому признаку."""
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.dns.bootstrap = []
    cfg.filters.exclude_regex = ""
    cfg.filters.max_members = 2
    cfg.filters.rotate_after_min = 0
    daemon = Harness(cfg, paths, capture_active=lambda: True, reapply_capture=lambda: None)
    try:
        _started(daemon)
        members = daemon.tags("proxy")
        daemon.next_refresh = daemon.t + 3600
        daemon.location = daemon.via_location = "RU"  # сервер сам выходит в RU
        daemon.e2e = False
        daemon.failures["*"] = ScanResult("", "CONNECT_FAIL", 0, 0.3, "обрыв", "io", 0)
        daemon.base_ping = True
        daemon.direct = "нет ответа"
        daemon.set_alive(**{tag.replace("-", "_"): False for tag in members})
        daemon.t += 400  # очередная проверка утечки
        assert daemon.tick() is State.LEAK
        assert daemon.probe_target  # признак виден, хоть состояние и LEAK
        daemon.scanned.clear()
        for _ in range(6):
            daemon.t += 20
            assert daemon.tick() is State.LEAK
        assert daemon.scanned == []  # ни сканов, ни повторной диагностики на каждом шаге
        rotations = [event for event in daemon.events() if event.startswith("rotation:")]
        assert rotations == [] and daemon.tags("proxy") == members
        # Утечка прошла, а probe.url всё так же не отвечает: не ALL_DEAD, а
        # PROBE_TARGET_UNREACHABLE — и замен по-прежнему нет.
        daemon.location = daemon.via_location = "NL"
        daemon.t += 400
        assert daemon.tick() is State.PROBE_TARGET_UNREACHABLE
        daemon.t += 301  # перепроверка: ошибки разные, файл не получил никто
        first = next(info.probe_tag for info in daemon.view() if info.role == "proxy")
        daemon.failures = {
            first: ScanResult("", "TIMEOUT", 0, 15.0, "таймаут", "timeout", 0),
            "*": ScanResult("", "CONNECT_FAIL", 0, 0.3, "обрыв", "io", 0),
        }
        assert daemon.tick() is State.PROBE_TARGET_UNREACHABLE
        assert daemon.tags("proxy") == members
    finally:
        daemon.store.close()


def test_server_exiting_at_home_is_replaced_and_not_taken_back(tmp_path, monkeypatch):
    """Самый быстрый сервер подписки сам выходит в RU (у заказчика — на 186 мс): обычный
    сокет и запрос через Xray выходят в RU. Это не пропавшие правила: сервер меняют на
    запасной и обратно не берут. Сообщение — одно на причину, а не каждые 20 секунд."""
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.dns.bootstrap = []
    cfg.filters.exclude_regex = ""
    cfg.filters.max_members = 2
    reapplied = []
    daemon = Harness(
        cfg, paths, capture_active=lambda: True, reapply_capture=lambda: reapplied.append(1)
    )
    try:
        _started(daemon)
        members = daemon.tags("proxy")
        leaking = members[0]
        daemon.api.state = BalancerInfo(override=None, selects=(leaking,))
        daemon.location = daemon.via_location = "RU"
        daemon.t += 400
        assert daemon.tick() is State.LEAK
        assert reapplied == []  # правила тут ни при чём
        assert leaking not in daemon.tags("proxy") and len(daemon.tags("proxy")) == 2
        rotation = [event for event in daemon.events() if event.startswith("rotation:")]
        assert len(rotation) == 1 and f"сами выходят в RU: {leaking}" in rotation[0]
        leaks = [event for event in daemon.events() if event.startswith("leak:")]
        expected = f"leak: выход в RU: сервер {leaking} сам выходит в RU — меняю его на запасной"
        assert leaks == [expected]
        # Выход в RU держится до следующей проверки утечки: событий на каждом шаге нет.
        for _ in range(5):
            daemon.t += 20
            daemon.tick()
        assert len([e for e in daemon.events() if e.startswith("leak:")]) == 1
        # Выбывший сервер стал запасным, но назад его не возьмут ни при какой замене.
        fingerprint = next(iter(daemon.home_exits))
        assert fingerprint not in [
            info.fingerprint for info in daemon.view() if info.role == "proxy"
        ]
        daemon.location = daemon.via_location = "NL"
        daemon.t += 400
        assert daemon.tick() is State.HEALTHY

        # Выход в RU мимо Xray (через Xray — NL): виноваты правила, их грузят заново.
        daemon.location = "RU"
        daemon.t += 400
        assert daemon.tick() is State.LEAK and reapplied == [1]
        assert any("мимо Xray" in event for event in daemon.events())

        # Закреплённый вручную сервер не меняется — человеку говорят снять закрепление.
        pinned = daemon.tags("proxy")[0]
        daemon.api.state = BalancerInfo(override=pinned, selects=())
        daemon.via_location = "RU"
        daemon.t += 400
        assert daemon.tick() is State.LEAK and pinned in daemon.tags("proxy")
        assert any("xgw unpin" in event for event in daemon.events())
    finally:
        daemon.store.close()


def test_probe_url_check_waits_for_the_threshold_while_the_core_sees_members_alive(daemon):
    """Ядро ещё считает участников живыми (его пробы реже): один сбой сквозной
    проверки — не повод, ждём fail_threshold шагов подряд."""
    _started(daemon)
    daemon.e2e = False
    daemon.failures["*"] = _http_403()
    daemon.direct = "HTTP 403"
    states = [daemon.tick() for _ in range(3)]
    assert states == [State.HEALTHY, State.HEALTHY, State.PROBE_TARGET_UNREACHABLE]


def test_base_request_through_vpn_confirms_a_dead_probe_url(daemon):
    """Одинаковые таймауты — ещё не довод: так выглядят и мёртвые серверы. Решает
    базовый запрос через VPN: он проходит — значит, не отвечает именно probe.url (а
    напрямую его может и не быть видно вовсе)."""
    _started(daemon)
    daemon.e2e = False
    daemon.failures["*"] = ScanResult("", "TIMEOUT", 0, 15.0, "таймаут", "timeout", 0)
    daemon.direct = "нет ответа"
    daemon.base_ping = True
    states = [daemon.tick() for _ in range(3)]
    assert states[-1] is State.PROBE_TARGET_UNREACHABLE
    target = daemon.status()["probe_target"]
    assert "таймаут" in target and "через VPN другие адреса открываются" in target


def test_dead_servers_are_not_blamed_on_the_probe_url(daemon):
    """Те же таймауты, но через VPN не проходит ничего — это серверы."""
    _started(daemon)
    daemon.e2e = False
    daemon.failures["*"] = ScanResult("", "TIMEOUT", 0, 15.0, "таймаут", "timeout", 0)
    daemon.direct = "нет ответа"  # probe.url напрямую закрыт — на вывод это не влияет
    daemon.base_ping = False
    states = [daemon.tick() for _ in range(3)]
    assert states[-1] is State.ALL_DEAD and daemon.status()["probe_target"] == ""


def test_freeze_is_never_blamed_on_the_probe_url(daemon):
    """Часть тела пришла, затем тишина — адрес пробы отвечает, «заморожены» серверы."""
    _started(daemon)
    daemon.e2e = False
    daemon.failures["*"] = ScanResult(
        "", "FROZEN", 19451, 5.4, "тишина 5 с после 19451 байт тела", "stall", 200)
    daemon.base_ping = True  # мелкие запросы «замороженный» сервер пропускает
    states = [daemon.tick() for _ in range(3)]
    assert states[-1] is State.ALL_DEAD and daemon.status()["probe_target"] == ""


def test_one_working_server_means_the_probe_url_is_fine(daemon):
    _started(daemon)
    daemon.e2e = False
    spare = daemon.tags("spare")[0].replace("spare-", "probe-")
    for info_tag in [*daemon.tags("proxy"), *daemon.tags("spare")]:
        probe_tag = "probe-" + info_tag.split("-", 1)[1]
        if probe_tag != spare:
            daemon.failures[probe_tag] = _http_403()
    daemon.direct, daemon.base_ping = "HTTP 403", True
    states = [daemon.tick() for _ in range(3)]
    assert states[-1] is State.ALL_DEAD  # ошибки не у всех — значит, дело в серверах


# --- первая проверка участников ----------------------------------------------------


def _fail_first_member(daemon: Harness, verdict: str = "FROZEN") -> tuple[dict, dict]:
    """Первый же участник, которого проверит шлюз, получает этот вердикт; остальные
    участники проходят, запасные получают вердикт из второго словаря (ключ spares)."""
    bad: dict[str, bool] = {}
    other = {"spares": "OK"}

    def scan(info, password, url=None):
        daemon.scanned.append(info.tag)
        if info.role == "proxy" and (not bad or info.tag in bad):
            bad[info.tag] = True
            if verdict == "FROZEN":
                return ScanResult(info.tag, verdict, 19451, 5.4,
                                  "тишина 5 с после 19451 байт тела", "stall", 200)
            return ScanResult(info.tag, verdict, 0, 0.4, "TLS: connection reset", "tls", 0)
        if info.role == "spare" and other["spares"] != "OK":
            return ScanResult(info.tag, other["spares"], 16384, 5.0)
        return ScanResult(info.tag, "OK", 65536, 0.5)

    daemon._scan = scan
    return bad, other


@pytest.mark.parametrize("limited", [True, False])
@pytest.mark.parametrize("verdict", ["FROZEN", "CONNECT_FAIL"])
def test_member_failing_the_first_check_is_replaced_at_once(daemon, verdict, limited):
    """Первый состав балансировщика берётся из подписки наугад. Участник, у которого
    собственная проба шлюза показала «заморозку» или отказ в соединении, меняется на
    проверенный запасной сразу — без ожидания rotate_after_min (15 минут) и раньше,
    чем ядро само объявит его мёртвым."""
    if not limited:
        daemon.source.quotas = {}  # подписка о лимите не сообщает — безлимитная
    bad, _other = _fail_first_member(daemon, verdict)
    assert daemon.tick() is State.HEALTHY  # по ядру сведений ещё нет
    (victim,) = bad
    # Первый шаг: участники проверены раньше запасных, замена — в тот же шаг.
    assert daemon.scanned[:2] == [victim, daemon.scanned[1]] and len(daemon.scanned) == 5
    assert len(daemon.applied) == 2 and daemon.applied[1][1] is False  # через API, не срочно
    members = daemon.tags("proxy")
    assert victim not in members and len(members) == 2
    assert victim.replace("proxy-", "spare-") in daemon.tags("spare")
    rotation = [event for event in daemon.events() if event.startswith("rotation:")]
    assert len(rotation) == 1 and f"не прошли первую проверку: {victim} — {verdict}" in rotation[0]

    # Дальше — тишина: замена уже прошла скан, заново никого не проверяют и не меняют.
    # Кроме одного: у подписки с лимитом запасные проверяются дешёвым запросом, а он
    # «заморозку» не ловит — новый участник один раз проходит первую проверку probe.url.
    replacement = next(tag for tag in members if tag not in daemon.scanned[:2])
    daemon.scanned.clear()
    daemon.applied.clear()
    daemon.set_alive()
    for _ in range(3):
        assert daemon.tick() is State.HEALTHY
    assert daemon.scanned == ([replacement] if limited else []) and daemon.applied == []
    # Выбывший стал запасным со своим вердиктом — обратно его не возьмут.
    spares = {spare["tag"]: spare["verdict"] for spare in daemon.status()["spares"]}
    assert spares[victim.replace("proxy-", "spare-")] == verdict


def test_first_check_waits_for_a_spare_that_passed_the_scan(daemon):
    """Менять не на кого — участник остаётся; появился проверенный запасной — меняется."""
    bad, other = _fail_first_member(daemon)
    other["spares"] = "FROZEN"  # все запасные «заморожены»
    daemon.tick()
    (victim,) = bad
    assert len(daemon.applied) == 1 and victim in daemon.tags("proxy")
    daemon.set_alive(**{victim.replace("-", "_"): False})  # ядро тоже видит, что он мёртв
    assert daemon.tick() is State.DEGRADED and len(daemon.applied) == 1
    other["spares"] = "OK"
    daemon.t += 61  # внеочередной скан — не чаще раза в минуту
    daemon.tick()  # заказан скан запасных
    daemon.tick()  # скан и замена
    assert victim not in daemon.tags("proxy")


def test_first_check_is_forgotten_when_the_core_reports_the_member_alive(daemon):
    """Сбой первой проверки оказался разовым: ядро считает участника живым."""
    bad, other = _fail_first_member(daemon, "CONNECT_FAIL")
    other["spares"] = "FROZEN"  # менять не на кого
    daemon.tick()
    (victim,) = bad
    assert daemon.bad_members == {victim: "CONNECT_FAIL"}
    daemon.set_alive()
    daemon.tick()
    assert daemon.bad_members == {} and victim in daemon.tags("proxy")


def test_timeout_at_the_first_check_goes_the_usual_way(daemon):
    """Таймаут бывает разовым: такой участник сразу не меняется — за ним следит ядро."""
    bad, _other = _fail_first_member(daemon, "TIMEOUT")
    daemon.tick()
    (victim,) = bad
    assert daemon.bad_members == {} and victim in daemon.tags("proxy")
    assert len(daemon.applied) == 1


def test_reloaded_settings_keep_the_first_check_results(daemon):
    """Настройки перечитаны (новый демон на тех же серверах): участников заново не
    проверяют."""
    _started(daemon)
    successor = Harness(daemon.cfg, daemon.paths)
    try:
        successor.adopt(daemon)
        assert successor.vetted == daemon.vetted and len(successor.vetted) == 2
        successor.set_alive()
        successor.tick()
        assert not [tag for tag in successor.scanned if tag.startswith("proxy-")]
    finally:
        successor.store.close()


def test_reloaded_settings_keep_the_watchdog_state(daemon):
    """Правка настроек посреди ALL_DEAD: новый демон продолжает с того же состояния —
    статус не показывает на шаг HEALTHY, и повторного события ALL_DEAD нет."""
    _started(daemon)
    dead = {tag.replace("-", "_"): False for tag in daemon.tags("proxy")}
    daemon.set_alive(**dead)
    assert daemon.tick() is State.ALL_DEAD
    since = daemon.state_since
    successor = _second(daemon, lambda cfg: setattr(cfg.notify, "min_interval_min", 7))
    try:
        assert successor.machine.state is State.ALL_DEAD and successor.state_since == since
        assert successor.dead_since == daemon.dead_since
        successor.set_alive(**{tag.replace("-", "_"): False for tag in successor.tags("proxy")})
        assert successor.tick() is State.ALL_DEAD
        assert successor.collected == []  # внеочередное обновление уже было — не повторяется
        events = [event for event in successor.events() if event.startswith("ALL_DEAD:")]
        assert len(events) == 1 and "HEALTHY → ALL_DEAD" in events[0]
        assert successor.status()["state"] == "ALL_DEAD"
    finally:
        successor.store.close()


def test_new_probe_url_is_checked_at_once_after_reload(daemon):
    """Не отвечал probe.url, человек вписал другой: новый демон помнит предупреждение и
    на первом же шаге проверяет новый адрес — он отвечает, проверки возобновлены."""
    _started(daemon)
    daemon.e2e = False
    daemon.failures["*"] = _http_403()
    daemon.direct = "HTTP 403"
    daemon.set_alive(**{tag.replace("-", "_"): False for tag in daemon.tags("proxy")})
    assert daemon.tick() is State.PROBE_TARGET_UNREACHABLE
    successor = _second(daemon, lambda cfg: setattr(cfg.probe, "url", "https://example.org/a.woff"))
    try:
        assert successor.machine.state is State.PROBE_TARGET_UNREACHABLE
        assert successor.probe_target == daemon.probe_target and successor.next_target_check == 0
        successor.set_alive()
        assert successor.tick() is State.HEALTHY
        assert successor.probe_target == ""
        texts = successor.events()
        assert any("probe.url снова отвечает" in event for event in texts)
        assert any("PROBE_TARGET_UNREACHABLE → HEALTHY" in event for event in texts)
    finally:
        successor.store.close()


def test_panel_list_names_a_server_whose_domain_is_gone(daemon, monkeypatch):
    """Подписку сохраняют для панели до сборки, а домен уходит в карантин во время неё:
    список перезаписывается — сервер с таким доменом не значится «включённым»."""
    from xgw import fetch

    gone = (
        "vless://11111111-2222-4333-8444-5555555555a1@gone.example.net:443?"
        "type=tcp&security=none#ghost"
    )

    def resolve(name, bootstrap, mark):
        if name == "gone.example.net":
            raise fetch.NoSuchDomain(f"домен {name} не разрешается: такого имени нет (NXDOMAIN)")
        raise fetch.ResolveError(f"тесты не ходят в DNS ({name})")

    monkeypatch.setattr(engine, "resolve_domain", resolve)
    daemon.source = _inventory([*ALL_LINKS, gone])
    daemon.tick()
    listed = {item["name"]: item["skip"] for item in engine.load_inventory(daemon.paths)}
    assert listed["ghost"] == "dns"
    assert [skip for name, skip in listed.items() if name != "ghost"] == [""] * len(ALL_LINKS)


# --- 0.1.8: лимиты подписок, множители и резервный выход ---------------------------

PAID = {"upload": 0, "download": 10**9, "total": 10**12}
MIXED = [("free", "Безлимит 1"), ("free", "Безлимит 2"), ("paid", "x1 Финляндия"),
         ("paid", "x10 🛜 Германия"), ("paid", "x100 LTE")]


def _priced(layout=MIXED) -> engine.Inventory:
    """Серверы ALL_LINKS по возрастанию отпечатка: подписка и имя — из layout. «paid» —
    подписка с лимитом трафика, «free» — без него (заголовка subscription-userinfo нет)."""
    raws, _, _ = parse_links_text("\n".join(ALL_LINKS), "main")
    nodes = sorted((raw_to_node(raw, "main") for raw in raws), key=lambda node: node.fingerprint)
    for node, (source, name) in zip(nodes, layout, strict=True):
        node.source, node.name = source, name
    return engine.Inventory(nodes, {"paid": dict(PAID)}, True)


def _named(daemon: Harness) -> dict[str, str]:
    """Имя сервера → его тег в применённом конфиге."""
    names = {node.fingerprint: node.name for node in daemon.inventory.nodes}
    return {names[info.fingerprint]: info.tag for info in daemon.view()}


def _probe(tag: str) -> str:
    return "probe-" + tag.split("-", 1)[1]


def _fallback(daemon: Harness) -> str:
    config = engine.read_json(daemon.paths.xray_config_file)
    return config["routing"]["balancers"][0]["fallbackTag"]


def _reserve_started(daemon: Harness, layout=MIXED) -> Harness:
    """Первые шаги: конфиг собран, участники проверены, резервный выход перепроверен."""
    daemon.source = _priced(layout)
    _started(daemon)
    daemon.tick()  # перепроверка резервного выхода и кандидатов — дешёвым запросом
    daemon.applied.clear()
    daemon.scanned.clear()
    daemon.next_refresh = daemon.t + 3600
    return daemon


def test_unlimited_servers_work_and_the_cheapest_limited_one_waits_as_the_reserve(daemon):
    daemon.source = _priced()
    _started(daemon)
    named = _named(daemon)
    assert sorted(daemon.tags("proxy")) == sorted([named["Безлимит 1"], named["Безлимит 2"]])
    # Резервный выход — лимитированный x1; observatory пробует только участников.
    config = engine.read_json(daemon.paths.xray_config_file)
    assert _fallback(daemon) == named["x1 Финляндия"]
    assert config["burstObservatory"]["subjectSelector"] == ["proxy-"]
    paid = [named[name] for name in ("x1 Финляндия", "x10 🛜 Германия", "x100 LTE")]
    # Лимитированные запасные проверяются только как кандидаты в резервный — один раз
    # после запуска и коротким запросом (probe.trace_url), а не загрузкой probe.url.
    daemon.tick()
    assert sorted(daemon.scanned) == sorted(paid)
    assert {daemon.scan_urls[tag] for tag in paid} == {daemon.cfg.probe.trace_url}
    assert daemon.applied == []  # резервный прошёл проверку — менять нечего
    # По расписанию скана (scan_spares_minutes) их больше не трогают.
    daemon.scanned.clear()
    for _ in range(3):
        daemon.t += daemon.cfg.probe.scan_spares_minutes * 60 * 1.3
        daemon.next_refresh = daemon.t + 3600
        daemon.tick()
    assert daemon.scanned == []
    status = daemon.status()
    assert status["reserve"]["name"] == "x1 Финляндия" and status["reserve"]["cost"] == 1.0
    costs = {spare["name"]: spare["cost"] for spare in status["spares"]}
    assert costs == {"x1 Финляндия": 1.0, "x10 🛜 Германия": 10.0, "x100 LTE": 100.0}
    assert {member["cost"] for member in status["members"]} == {0.0}
    # Раз в RESERVE_RECHECK (6 ч) — перепроверка: снова коротким запросом.
    daemon.t += 6 * 3600 * 1.3
    daemon.next_refresh = daemon.t + 3600
    daemon.tick()
    daemon.tick()
    assert sorted(daemon.scanned) == sorted(paid)


def test_dead_unlimited_servers_give_way_to_the_cheapest_limited_ones_and_come_back(daemon):
    """Безлимитные мертвы — трафик сразу несёт резервный x1 (Xray сам, через fallbackTag),
    а шлюз ставит в работу живые лимитированные, сначала самые дешёвые (решение
    пользователя после испытаний 0.1.9). x10 и x100 участниками не становятся: их пробы
    съели бы квоту (MEMBER_COST_MAX). Безлимитный снова ответил — в работе безлимитные."""
    _reserve_started(daemon)
    unlimited = daemon.tags("proxy")
    for tag in unlimited:
        daemon.verdicts[_probe(tag)] = "CONNECT_FAIL"
    daemon.set_alive(**{tag.replace("-", "_"): False for tag in unlimited})
    assert daemon.tick() is State.RESERVE
    entered = [event for event in daemon.events() if event.startswith("RESERVE:")]
    assert len(entered) == 1 and "HEALTHY → RESERVE" in entered[0]
    assert "трафик идёт через резервный сервер «x1 Финляндия» (x1)" in entered[0]
    assert daemon.collected == [False]  # подписка — напрямую: через Xray пошла бы через x1
    # Сбой может быть коротким (ядро само вернёт трафик безлимитным) — COSTLIER_AFTER ждём.
    assert daemon.tags("proxy") == unlimited and daemon.applied == []
    daemon.t += 130
    assert daemon.tick() is State.RESERVE
    named = _named(daemon)
    assert daemon.tags("proxy") == [named["x1 Финляндия"]]
    assert daemon.applied[-1][1] is True  # срочно: участники мертвы
    assert any(
        "живых серверов нет — в работе лимитированные серверы x1 (были — безлимитные "
        "серверы)" in event for event in daemon.events()
    )
    daemon.set_alive()
    daemon.applied.clear()
    for _ in range(3):
        daemon.t += 120
        assert daemon.tick() is State.HEALTHY
    assert daemon.applied == []
    assert named["x10 🛜 Германия"] not in daemon.tags("proxy")
    # Безлимитные ответили на перепроверку (TIER_RESCAN) — они снова в работе.
    daemon.verdicts.clear()
    for _ in range(3):
        daemon.t += 120
        daemon.tick()
    named = _named(daemon)
    assert sorted(daemon.tags("proxy")) == sorted([named["Безлимит 1"], named["Безлимит 2"]])
    # Резервным снова становится x1 — после перепроверки кандидатов дешёвым запросом.
    for _ in range(3):
        daemon.t += 20
        daemon.tick()
    assert _fallback(daemon) == _named(daemon)["x1 Финляндия"]


def test_brief_outage_of_the_unlimited_servers_does_not_bring_in_limited_ones(daemon):
    """Провайдер моргнул: ядро сочло безлимитных мёртвыми, трафик ненадолго понёс
    резервный, затем безлимитные снова ответили на пробу — лимитированных в работу не
    ставили, конфиг не менялся."""
    _reserve_started(daemon)
    unlimited = daemon.tags("proxy")
    daemon.set_alive(**{tag.replace("-", "_"): False for tag in unlimited})
    assert daemon.tick() is State.RESERVE
    daemon.t += 60
    assert daemon.tick() is State.RESERVE
    daemon.set_alive()
    daemon.t += 20
    assert daemon.tick() is State.HEALTHY
    daemon.t += 120
    daemon.tick()
    assert daemon.tags("proxy") == unlimited and daemon.applied == []


def test_limited_servers_without_a_fresh_check_are_checked_cheaply_first(daemon):
    """Свежих вердиктов у лимитированных x1 нет — шлюз сначала проверяет их дешёвым
    запросом и только потом ставит в работу; в класс дороже по старым вердиктам не идёт."""
    layout = [("free", "Безлимит 1"), ("free", "Безлимит 2"), ("paid", "x1 A"),
              ("paid", "x1 B"), ("paid", "x10 C")]
    _reserve_started(daemon, layout)
    named = _named(daemon)
    # Прошло больше двух периодов скана: вердикты x1 устарели.
    daemon.t += daemon.cfg.probe.scan_spares_minutes * 120 + 600
    daemon.next_refresh = daemon.t + 3600
    daemon.tick()
    daemon.scanned.clear()
    daemon.applied.clear()
    unlimited = daemon.tags("proxy")
    for tag in unlimited:
        daemon.verdicts[_probe(tag)] = "CONNECT_FAIL"
    daemon.set_alive(**{tag.replace("-", "_"): False for tag in unlimited})
    assert daemon.tick() is State.RESERVE
    daemon.t += 130
    daemon.tick()
    assert daemon.applied == []  # сначала проверка
    daemon.t += 20
    daemon.tick()
    x1 = {named["x1 A"], named["x1 B"]}
    assert x1 <= set(daemon.scanned)
    assert {daemon.scan_urls[tag] for tag in x1} == {daemon.cfg.probe.trace_url}
    assert named["x10 C"] not in daemon.scanned
    named = _named(daemon)
    assert sorted(daemon.tags("proxy")) == sorted([named["x1 A"], named["x1 B"]])


def test_dead_unlimited_member_is_replaced_by_an_unlimited_spare_while_the_reserve_works(daemon):
    """Пока трафик несёт резервный (и тратит квоту), мёртвых безлимитных меняют на живых
    безлимитных запасных сразу, не дожидаясь rotate_after_min."""
    layout = [("free", "Безлимит 1"), ("free", "Безлимит 2"), ("free", "Безлимит 3"),
              ("paid", "x1 Финляндия"), ("paid", "x10 🛜 Германия")]
    _reserve_started(daemon, layout)
    members = daemon.tags("proxy")
    daemon.set_alive(**{tag.replace("-", "_"): False for tag in members})
    assert daemon.tick() is State.RESERVE
    daemon.tick()
    named = _named(daemon)
    assert named["Безлимит 3"] in daemon.tags("proxy")
    assert all(not tag.startswith("proxy-") for name, tag in named.items() if name.startswith("x"))


def test_reserve_that_stops_answering_is_replaced_by_the_next_cheapest(daemon):
    daemon.source = _priced()
    daemon.tick()
    named = _named(daemon)
    x1, x10, x100 = (named[name] for name in ("x1 Финляндия", "x10 🛜 Германия", "x100 LTE"))
    daemon.verdicts[_probe(x1)] = "CONNECT_FAIL"
    daemon.set_alive()
    daemon.applied.clear()
    daemon.tick()  # перепроверка: x1 не ответил — резервным становится x10
    assert _fallback(daemon) == x10.replace("proxy-", "spare-")
    assert len(daemon.applied) == 1 and daemon.applied[0][1] is False  # через API, не срочно
    assert any("резервный сервер — «x10 🛜 Германия» (x10)" in event for event in daemon.events())
    # Безлимитные мертвы, и через резервный трафик не идёт: ALL_DEAD — сразу перепроверка
    # всех кандидатов, x10 тоже не отвечает — резервным становится x100, срочно.
    daemon.next_refresh = daemon.t + 3600
    daemon.verdicts[_probe(x10)] = "TIMEOUT"
    daemon.applied.clear()
    daemon.e2e = False
    daemon.set_alive(**{tag.replace("-", "_"): False for tag in daemon.tags("proxy")})
    assert daemon.tick() is State.ALL_DEAD
    daemon.t += 20
    daemon.tick()
    assert _fallback(daemon) == x100.replace("proxy-", "spare-")
    assert daemon.applied[-1][1] is True
    assert any("резервный сервер — «x100 LTE» (x100)" in event for event in daemon.events())
    names = {node.fingerprint: node.name for node in daemon.inventory.nodes}
    # Лимитированных в балансировщик не взяли: участники — по-прежнему безлимитные.
    assert all(names[_fingerprint(daemon, tag)].startswith("Безлимит")
               for tag in daemon.tags("proxy"))
    # Через x100 трафик пошёл — RESERVE.
    daemon.e2e = True
    daemon.t += 20
    assert daemon.tick() is State.RESERVE
    # Ни один кандидат не отвечает — об этом одно событие, резервный остаётся прежним.
    daemon.verdicts[_probe(x100)] = "CONNECT_FAIL"
    daemon.e2e = False
    for _ in range(4):
        daemon.t += 20
        daemon.tick()
    daemon.t += 301
    daemon.tick()
    daemon.tick()
    notes = [event for event in daemon.events() if "резервного сервера нет" in event]
    assert len(notes) == 1 and _fallback(daemon) == x100.replace("proxy-", "spare-")


def test_without_unlimited_servers_limited_ones_work_as_before(daemon):
    """Безлимитных нет: в балансировщике x1 (как в 0.1.7), резервный — x10. Запасные x1
    сканируются по расписанию, но коротким запросом; заменивший мёртвого участника x1
    один раз проходит первую проверку probe.url."""
    daemon.cfg.filters.rotate_after_min = 0
    layout = [("paid", "x1 A"), ("paid", "x1 B"), ("paid", "x1 C"), ("paid", "x10 D"),
              ("paid", "x10 E")]
    _reserve_started(daemon, layout)
    named = _named(daemon)
    assert sorted(daemon.tags("proxy")) == sorted([named["x1 A"], named["x1 B"]])
    assert _fallback(daemon) == named["x10 D"]
    daemon.t += daemon.cfg.probe.scan_spares_minutes * 60 * 1.3
    daemon.next_refresh = daemon.t + 3600
    daemon.tick()
    assert daemon.scanned == [named["x1 C"]]
    assert daemon.scan_urls[named["x1 C"]] == daemon.cfg.probe.trace_url
    victim = named["x1 A"]
    daemon.set_alive(**{victim.replace("-", "_"): False})
    daemon.scanned.clear()
    assert daemon.tick() is State.DEGRADED
    named = _named(daemon)
    assert named["x1 C"] in daemon.tags("proxy") and named["x10 D"] not in daemon.tags("proxy")
    daemon.set_alive()
    daemon.tick()
    assert daemon.scanned == [named["x1 C"]]  # первая проверка нового участника
    assert daemon.scan_urls[named["x1 C"]] == daemon.cfg.probe.url


def test_unlimited_servers_that_appear_take_over_from_limited_ones(daemon):
    limited = [("paid", "x1 A"), ("paid", "x1 B"), ("paid", "x10 C"), ("paid", "x10 D"),
               ("paid", "x10 E")]
    _reserve_started(daemon, limited)
    before = sorted(daemon.tags("proxy"))
    # Подписка обновилась: D и E теперь безлимитные (другая подписка).
    daemon.source = _priced([*limited[:3], ("free", "Безлимит D"), ("free", "Безлимит E")])
    daemon.next_refresh = 0.0
    daemon.tick()
    daemon.next_refresh = daemon.t + 3600
    for _ in range(4):
        daemon.t += 20
        daemon.tick()
    assert sorted(daemon.tags("proxy")) != before
    named = _named(daemon)
    assert sorted(daemon.tags("proxy")) == sorted([named["Безлимит D"], named["Безлимит E"]])
    assert any(
        "снова отвечают серверы лучшего класса — в работе безлимитные серверы (были — "
        "лимитированные серверы x1)" in event for event in daemon.events()
    )
    assert _fallback(daemon) == named["x1 A"]  # x1 — теперь резервный


def test_dead_probe_url_is_found_while_the_reserve_carries_the_traffic(daemon):
    """probe.url перестал отвечать: ядро считает мёртвыми всех безлимитных, и трафик
    уходит на резервный — сквозная проверка (коротким запросом) при этом проходит. Демон
    всё равно опрашивает участников и, узнав, что не отвечает сам адрес пробы, переводит
    ядро на запасной адрес: трафик возвращается на безлимитные."""
    _reserve_started(daemon)
    daemon.failures["*"] = _http_403()
    daemon.direct = "HTTP 403"
    members = daemon.tags("proxy")
    daemon.set_alive(**{tag.replace("-", "_"): False for tag in members})
    assert daemon.tick() is State.PROBE_TARGET_UNREACHABLE
    # Опрошены только участники: лимитированных запасных пробовать probe.url дорого.
    assert sorted(daemon.scanned) == sorted(members)
    probes = daemon.applied[-1][0]["burstObservatory"]["pingConfig"]["destination"]
    assert probes == daemon.cfg.probe.trace_url and daemon.tags("proxy") == members


def test_member_based_base_ping_ignores_the_reserve(daemon, monkeypatch):
    """Базовый запрос «носят ли серверы трафик» идёт через probe-inbound участников, а не
    через http-in: тот при мёртвых участниках понёс бы его через резервный."""
    from xgw.watch import checks

    _reserve_started(daemon)
    seen: list[int] = []

    def get(host, port, url, **kwargs):
        seen.append(port)
        return checks.DownloadResult(ok=False)

    monkeypatch.setattr(checks, "http_get_via_proxy", get)
    members = [info for info in daemon.view() if info.role == "proxy"]
    assert Daemon._base_ping(daemon, members, "pass") is False
    assert seen == [info.probe_port for info in members]
    assert daemon.cfg.xray.http_port not in seen


# --- уведомления: только когда нужно действие человека ------------------------------


def _with_sink(tmp_path, monkeypatch) -> tuple[Harness, list[tuple[str, str]]]:
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.filters.max_members = 2
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []
    cfg.notify.min_interval_min = 0  # придержка по типу не мешает считать уведомления
    sent: list[tuple[str, str]] = []
    return Harness(cfg, paths, sinks=[lambda kind, text: sent.append((kind, text))]), sent


def test_servers_the_gateway_fixes_itself_are_not_notified(tmp_path, monkeypatch):
    """«Часть серверов недоступна», замена сервера, смена уровня — шлюз справляется сам:
    это события в журнале, без уведомления. «Все серверы недоступны» — уведомление."""
    daemon, sent = _with_sink(tmp_path, monkeypatch)
    try:
        daemon.cfg.filters.rotate_after_min = 0
        _started(daemon)
        victim = daemon.tags("proxy")[0]
        daemon.set_alive(**{victim.replace("-", "_"): False})
        assert daemon.tick() is State.DEGRADED
        daemon.tick()
        events = daemon.events()
        assert any(event.startswith("DEGRADED:") for event in events)
        assert any(event.startswith("rotation:") for event in events)
        assert sent == []
        daemon.set_alive(**{tag.replace("-", "_"): False for tag in daemon.tags("proxy")})
        daemon.next_refresh = daemon.t + 3600
        assert daemon.tick() is State.ALL_DEAD
        assert [kind for kind, _text in sent] == ["ALL_DEAD"]
    finally:
        daemon.store.close()


def test_limited_servers_and_long_work_through_the_reserve_are_not_notified(
    tmp_path, monkeypatch
):
    """Переход на лимитированные и долгая работа через резервный — молча: интернет
    работает, действий от человека не нужно (решение пользователя после испытаний 0.1.9).
    О долгой работе через резервный — одно событие в журнале на заход."""
    daemon, sent = _with_sink(tmp_path, monkeypatch)
    try:
        _reserve_started(daemon)
        unlimited = daemon.tags("proxy")
        for tag in unlimited:
            daemon.verdicts[_probe(tag)] = "CONNECT_FAIL"
        daemon.set_alive(**{tag.replace("-", "_"): False for tag in unlimited})
        assert daemon.tick() is State.RESERVE
        daemon.t += 130
        daemon.tick()
        assert daemon.tags("proxy") == [_named(daemon)["x1 Финляндия"]]
        daemon.set_alive()
        daemon.t += 20
        assert daemon.tick() is State.HEALTHY
        assert sent == []
    finally:
        daemon.store.close()
    # Лимитированные только дороже x1: участниками они не становятся, трафик долго несёт
    # резервный — тоже без уведомлений.
    daemon, sent = _with_sink(tmp_path / "expensive", monkeypatch)
    try:
        layout = [("free", "Безлимит 1"), ("free", "Безлимит 2"), ("paid", "x10 A"),
                  ("paid", "x10 B"), ("paid", "x100 C")]
        _reserve_started(daemon, layout)
        members = daemon.tags("proxy")
        daemon.set_alive(**{tag.replace("-", "_"): False for tag in members})
        assert daemon.tick() is State.RESERVE
        for _ in range(32):  # 10 минут с лишним
            daemon.t += 20
            assert daemon.tick() is State.RESERVE
        assert daemon.tags("proxy") == members and sent == []
        long = [event for event in daemon.events() if event.startswith("reserve: уже")]
        assert len(long) == 1 and "«x10 A» (x10)" in long[0]
        daemon.set_alive()
        daemon.t += 20
        assert daemon.tick() is State.HEALTHY
        assert sent == []
        assert any("снова отвечают" in event for event in daemon.events())
    finally:
        daemon.store.close()


def test_subscription_failure_is_notified_only_when_it_lasts(tmp_path, monkeypatch):
    daemon, sent = _with_sink(tmp_path, monkeypatch)
    try:
        _started(daemon)
        daemon.source = _inventory(complete=False)
        for _ in range(3):
            daemon.next_refresh = 0.0
            daemon.t += 600
            daemon.tick()
        assert sent == []  # 20 минут без подписки — ещё не повод
        assert any("подписки получить не удалось" in event for event in daemon.events())
        for _ in range(5):
            daemon.next_refresh = 0.0
            daemon.t += 600
            daemon.tick()
        texts = [text for kind, text in sent if kind == "subscription"]
        assert len(texts) == 1 and "не обновляются уже 1 ч" in texts[0]
        # Подписка снова получена — следующий долгий сбой уведомит заново.
        daemon.source = _inventory()
        daemon.next_refresh = 0.0
        daemon.tick()
        assert daemon._sub_failing_since is None and not daemon._sub_alerted
    finally:
        daemon.store.close()


def test_xray_version_follows_binary_replacement(daemon, tmp_path, monkeypatch):
    """`xgw update-xray` подменяет бинарник (os.replace) и перезапускает только xgw-xray:
    статус показывает новую версию без перезапуска демона, а `xray version` не
    запускается на каждом шаге (замечание D1 отчёта 0.1.9)."""
    calls: list[str] = []

    def installed_version(path):
        calls.append(str(path))
        text = Path(path).read_text(encoding="utf-8").strip()
        return tuple(int(part) for part in text.split(".")) if text else None

    monkeypatch.setattr("xgw.daemon.binary.installed_version", installed_version)
    xray = tmp_path / "xray"
    xray.write_text("26.3.27", encoding="utf-8")
    daemon.xray_bin = xray
    _started(daemon)
    assert daemon.status()["xray"]["version"] == "26.3.27"
    daemon.tick()
    daemon.tick()
    assert len(calls) == 1
    fresh = tmp_path / "xray.new"
    fresh.write_text("26.10.10", encoding="utf-8")
    fresh.replace(xray)
    daemon.tick()
    assert daemon.status()["xray"]["version"] == "26.10.10"
    assert len(calls) == 2
    # Версию узнать не удалось — спрашиваем снова на следующем шаге, а не запоминаем пустую.
    broken = tmp_path / "xray.broken"
    broken.write_text("", encoding="utf-8")
    broken.replace(xray)
    daemon.tick()
    daemon.tick()
    assert daemon.status()["xray"]["version"] == ""
    assert len(calls) == 4
    xray.unlink()
    daemon.tick()
    assert daemon.status()["xray"]["version"] == ""
    assert len(calls) == 4


# --- 0.1.10: ручной выбор сервера, как в клиентах VPN --------------------------------


def _choose(daemon: Harness, tag: str, until: float | None = None) -> None:
    daemon.store.set_meta("pin", json.dumps(
        {"tag": tag, "name": f"сервер {tag}", "until": until, "since": daemon.t, "down": None}
    ))


def test_a_spare_can_be_chosen_and_the_choice_follows_the_server(daemon):
    """Выбрать можно и запасной: ядро закрепляется на нём, хотя его нет в selector
    балансировщика. Бессрочный выбор не снимается сам; тег в записи сверяется по серверу —
    закрепление на тег, которого нет, остановило бы весь трафик."""
    _started(daemon)
    spare = daemon.tags("spare")[0]
    _choose(daemon, "proxy-" + spare.split("-", 1)[1])  # роль в записи устарела
    daemon.tick()
    assert daemon.api.state.override == spare
    assert json.loads(daemon.store.get_meta("pin"))["tag"] == spare
    assert daemon.status()["pin"]["tag"] == spare and daemon.status()["pin"]["until"] is None
    daemon.t += 10 * 86400
    daemon.api.state = BalancerInfo(override=None, selects=())  # Xray перезапустился
    daemon.tick()
    assert daemon.api.state.override == spare and daemon.store.get_meta("pin")


def test_chosen_server_that_stops_answering_hands_over_to_auto_and_comes_back(
    tmp_path, monkeypatch
):
    """Выбранный запасной не пропускает трафик (сквозная проверка идёт через него) —
    закрепление снимается, трафик ведёт автовыбор; раз в PIN_RECHECK его проверяет
    собственная проба, и когда он ответил, трафик снова через него. И то и другое —
    уведомления: выбор делал человек. В ALL_DEAD шлюз не уходит."""
    daemon, sent = _with_sink(tmp_path, monkeypatch)
    try:
        daemon.cfg.speed.sticky = False
        _started(daemon)
        spare = daemon.tags("spare")[0]
        _choose(daemon, spare)
        daemon.tick()
        assert daemon.api.state.override == spare
        daemon.e2e = False
        daemon.verdicts[_probe(spare)] = "CONNECT_FAIL"
        states = []
        for _ in range(2):
            daemon.t += 20
            states.append(daemon.tick())
        assert State.ALL_DEAD not in states
        pin = json.loads(daemon.store.get_meta("pin"))
        assert pin["down"] and daemon.api.state.override is None
        assert [kind for kind, _text in sent] == ["pin"] and "не отвечает" in sent[0][1]
        daemon.e2e = True  # автовыбор носит трафик
        daemon.scanned.clear()
        for _ in range(8):  # 160 с: проба раз в PIN_RECHECK, сервер всё ещё молчит
            daemon.t += 20
            assert daemon.tick() is State.HEALTHY
        assert daemon.scanned.count(spare) >= 1  # Harness пишет теги серверов
        assert daemon.api.state.override is None and len(sent) == 1
        daemon.verdicts.clear()
        for _ in range(8):
            daemon.t += 20
            daemon.tick()
        assert daemon.api.state.override == spare
        assert not json.loads(daemon.store.get_meta("pin"))["down"]
        assert [kind for kind, _text in sent] == ["pin", "pin"] and "снова отвечает" in sent[1][1]
    finally:
        daemon.store.close()


def test_chosen_member_that_the_core_sees_dead_hands_over_at_once(daemon):
    """Выбранного участника пробует ядро: умер — автовыбор сразу, ожил — снова он."""
    _started(daemon)
    member = daemon.tags("proxy")[0]
    _choose(daemon, member)
    daemon.tick()
    assert daemon.api.state.override == member
    daemon.set_alive(**{member.replace("-", "_"): False})
    daemon.tick()
    assert daemon.api.state.override is None
    assert json.loads(daemon.store.get_meta("pin"))["down"]
    assert daemon.status()["pin"]["down"]  # статус и панель знают: трафик на автовыборе
    daemon.set_alive()
    daemon.tick()
    assert daemon.api.state.override == member
    assert not json.loads(daemon.store.get_meta("pin"))["down"]


# --- события и жизненный цикл перехвата (Ф2) -------------------------------------------


def test_rules_event_restores_rules_right_away(guarded):
    """Чужой flush (событие nft monitor): правила сверяются сразу, посреди паузы — без
    сквозной пробы и прочего шага, а пауза не прерывается."""
    daemon, capture = guarded
    checks = daemon.e2e_checks
    capture.calls.clear()
    capture.is_loaded = False
    daemon.wake("rules")
    began = time.monotonic()
    daemon._sleep(threading.Event(), lambda: False, 0.6)
    assert time.monotonic() - began >= 0.55
    assert capture.actions() == ["up"] and daemon.e2e_checks == checks
    assert any("загружены заново" in event for event in daemon.events())
    # status.json — сразу с итогом: панель и `xgw status` не ждут очередного шага.
    assert any("загружены заново" in row["detail"] for row in daemon.status()["events"])


def test_net_event_starts_the_step_early_but_not_too_often(daemon):
    _started(daemon)
    stop = threading.Event()
    daemon.wake("net")
    began = time.monotonic()
    daemon._sleep(stop, lambda: False, 30)
    assert time.monotonic() - began < 1.0
    daemon.tick()
    daemon.wake("net")  # следующее — не раньше NET_WAKE_PAUSE после шага по событию
    began = time.monotonic()
    daemon._sleep(stop, lambda: False, 30)
    assert 1.5 <= time.monotonic() - began < 5.0


def test_wake_after_resume_reloads_rules_and_scans(guarded):
    """Пробуждение после сна: правила и маршруты загружаются заново, запасные
    проверяются сразу, а опрос подписки, срок которого прошёл во сне, — на этом же шаге
    (монотонные часы во сне стоят)."""
    daemon, capture = guarded
    capture.calls.clear()
    daemon.scanned.clear()
    daemon.collected.clear()
    slept = 3 * 3600
    daemon.wall = lambda: daemon.t + slept
    daemon.wake("sleep")
    began = time.monotonic()
    daemon._sleep(threading.Event(), lambda: False, 30)
    assert time.monotonic() - began < 1.0
    daemon.tick()
    assert "up" in capture.actions()
    assert daemon.scanned  # запасные — без ожидания scan_spares_minutes
    assert daemon.collected == [True]  # подписка — через Xray, как в обычный срок


def test_late_probe_under_load_is_not_a_failure(daemon):
    """Канал забит: проба не успела, а через выбранный сервер за 10 с прошло 5 МБ —
    провал не засчитывается, счётчик не растёт."""
    _started(daemon)
    tag = daemon.tags("proxy")[0]
    daemon.api.state = BalancerInfo(override=None, selects=(tag,))
    daemon.downlinks[tag] = 10_000_000

    def late():
        daemon.e2e_checks += 1
        daemon.t += 10  # проба ждала ответа 10 с…
        daemon.downlinks[tag] += 5_000_000  # …а трафик LAN через сервер шёл
        return False

    daemon._check_e2e = late
    for _ in range(4):
        assert daemon.tick() is State.HEALTHY
        daemon.t += 20
    assert daemon.e2e_streak == 0 and daemon.e2e_checks == 5


def test_late_probe_without_traffic_still_counts(daemon):
    _started(daemon)
    tag = daemon.tags("proxy")[0]
    daemon.api.state = BalancerInfo(override=None, selects=(tag,))
    daemon.downlinks[tag] = 10_000_000

    def late():
        daemon.t += 10
        daemon.downlinks[tag] += 100_000  # меньше busy_bytes за окно
        return False

    daemon._check_e2e = late
    for _ in range(3):
        daemon.tick()
        daemon.t += 20
    assert daemon.e2e_streak == 3 and daemon.machine.state is State.ALL_DEAD


def test_dead_member_carrying_traffic_is_not_counted_dead(daemon):
    """Ядро сочло выбранного участника мёртвым (его проба опоздала в очереди), а через
    него с прошлого шага идёт трафик: он жив, DEGRADED не ставится."""
    _started(daemon)
    tag = daemon.tags("proxy")[0]
    daemon.api.state = BalancerInfo(override=None, selects=(tag,))
    daemon.downlinks[tag] = 1_000_000
    daemon.tick()
    daemon.t += 20
    daemon.downlinks[tag] += 20_000_000
    daemon.set_alive(**{tag.replace("-", "_"): False})
    assert daemon.tick() is State.HEALTHY
    assert tag not in daemon.dead_since
    daemon.t += 20  # трафик кончился — мёртв как мёртв
    assert daemon.tick() is State.DEGRADED


def test_lifecycle_follows_capture_and_xray(guarded):
    daemon, capture = guarded
    life = lambda: daemon.status()["capture"]["lifecycle"]  # noqa: E731
    assert life() == "connecting"  # первый шаг: ядро ещё не проверило ни одного сервера
    daemon.tick()
    assert life() == "connected"

    daemon.observatory, daemon.api.down = None, True  # Xray не отвечает: fail_mode = closed
    daemon.tick()
    written = daemon.status()["capture"]
    assert written["lifecycle"] == "blocked" and written["lifecycle_reason"] == "Xray не отвечает"
    assert any(
        event.startswith("lifecycle: перехват: работает → заблокирован")
        for event in daemon.events()
    )

    daemon.api.down = False
    daemon.observatory = {}  # Xray перезапущен и ещё не проверил ни одного сервера
    daemon.tick()
    assert life() == "connecting"
    daemon.set_alive()
    daemon.tick()
    assert life() == "connected"

    capture.problem, capture.blocked = "в применённом конфиге Xray нет inbound tproxy-in", True
    daemon.tick()
    written = daemon.status()["capture"]
    assert written["lifecycle"] == "blocked" and "tproxy-in" in written["lifecycle_reason"]
    capture.problem = ""
    capture.state = "off"  # xgw disable
    daemon.tick()
    assert life() == "off"
    kinds = [event.split(":")[0] for event in daemon.events()]
    # В журнал событий — только когда трафик перестаёт или снова начинает идти через VPN:
    # «подключается → работает» после перезапуска Xray туда не пишется.
    assert not any("подключается → работает" in event for event in daemon.events())
    assert kinds.count("lifecycle") == 4


def test_members_dead_during_the_outage_are_unknown_right_after_wan_returns(daemon):
    """Шаг по событию сети идёт сразу, как WAN вернулся, а ядро ещё помнит пробы, которые
    не прошли без связи: исправные серверы не меняются, отсчёт смерти начинается заново."""
    _started(daemon)
    daemon.cfg.filters.rotate_after_min = 0
    tag = daemon.tags("proxy")[0]
    daemon.provider = False
    daemon.set_alive(**{tag.replace("-", "_"): False})
    assert daemon.tick() is State.WAN_DOWN
    daemon.t += 600
    daemon.provider = True  # WAN вернулся, ядро ещё не повторило пробу
    assert daemon.tick() is State.HEALTHY
    assert daemon.applied == [] and tag not in daemon.dead_since
    daemon.t += 20
    assert daemon.tick() is State.DEGRADED  # мёртв и после возврата — уже по-настоящему
