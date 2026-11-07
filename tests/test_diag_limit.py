"""Волна 1б (ASSUMPTIONS п. 332): проверка адреса проб — не больше двух запросов сразу, общий
дедлайн; неполный итог — без выводов «адрес отвечает» и «серверы мертвы», доделка на следующем
шаге без повторных проб."""

import threading
import time

import pytest
from test_daemon import Harness, _started

from xgw import engine
from xgw.config import Config
from xgw.daemon import DIAG_BUDGET
from xgw.generator.builder import NodeInfo
from xgw.paths import Paths
from xgw.watch import target
from xgw.watch.scan import ScanResult

TIMEOUT = ScanResult("x", "TIMEOUT", 0, 15.0, "таймаут", "timeout")


@pytest.fixture()
def daemon(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.filters.max_members = 2
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []
    cfg.speed.sticky = False
    cfg.speed.unlimited_hours = cfg.speed.limited_hours = 0
    instance = Harness(cfg, paths)
    yield instance
    instance.store.close()


def _nodes(count: int) -> list[NodeInfo]:
    return [NodeInfo(f"fp{i}", f"proxy-{i}", f"probe-{i}", 20000 + i, "proxy")
            for i in range(count)]


def _probe(pause: float, top: list[int]):
    lock, now = threading.Lock(), [0]

    def probe(info):
        with lock:
            now[0] += 1
            top[0] = max(top[0], now[0])
        time.sleep(pause)
        with lock:
            now[0] -= 1
        return ScanResult(info.tag, "TIMEOUT", 0, pause, kind="timeout")
    return probe


def test_probe_sample_runs_two_at_a_time():
    top = [0]
    cut = target.Cutoff(None, time.monotonic() + 30.0)
    results, parallel = target.probe_sample(_nodes(6), _probe(0.05, top), workers=2, cut=cut)
    assert len(results) == 6 and parallel == 2 and top[0] == 2


def test_deadline_and_stop_leave_probes_unstarted():
    top = [0]
    cut = target.Cutoff(None, time.monotonic() + 0.3)
    results, _parallel = target.probe_sample(_nodes(6), _probe(0.2, top), workers=2, cut=cut)
    assert 0 < len(results) < 6  # начатые доведены, новые после дедлайна не начаты
    stop = threading.Event()
    stop.set()
    results, parallel = target.probe_sample(
        _nodes(4), _probe(0.01, top), workers=2, cut=target.Cutoff(stop, time.monotonic() + 30))
    assert results == [] and parallel == 0
    assert target.Cutoff(stop, time.monotonic() + 30).wait(0.01) is True


def test_expired_deadline_is_neither_target_ok_nor_dead_servers(daemon):
    _started(daemon)
    daemon.failures["*"] = TIMEOUT
    original = daemon._scan
    probed = []

    def slow(info, password, url=None):
        probed.append(info.tag)
        daemon.t += DIAG_BUDGET * 0.6  # две пробы съедают дедлайн проверки
        return original(info, password, url)

    daemon._scan = slow
    applied = engine.read_json(daemon.paths.xray_config_file)
    first = daemon._diagnose_target(daemon.view(), applied)
    assert first.complete is False and first.down is False
    assert 0 < len(daemon._diag_partial) < daemon._diag_last["of"]
    assert daemon._diag_last["max_parallel"] <= 2
    kept, probed[:] = set(daemon._diag_partial), []
    daemon._scan = lambda info, password, url=None: (probed.append(info.tag),
                                                     original(info, password, url))[1]
    daemon.base_ping = False  # через VPN не проходит ничего — это серверы
    second = daemon._diagnose_target(daemon.view(), applied)
    assert second.complete is True and second.down is False and not daemon._diag_partial
    assert probed and not kept & set(probed)  # снятые на прошлом шаге пробы не повторяются


def test_one_answer_settles_an_incomplete_check(daemon):
    _started(daemon)
    daemon.failures["*"] = TIMEOUT
    original = daemon._scan

    def answering(info, password, url=None):
        daemon.t += DIAG_BUDGET  # после первых проб дедлайн вышел
        if info.role == "spare":  # запасные с удачным прошлым сканом идут первыми и отвечают
            return ScanResult(info.tag, "OK", 65536, 0.5)
        return original(info, password, url)

    daemon._scan = answering
    result = daemon._diagnose_target(daemon.view(), engine.read_json(daemon.paths.xray_config_file))
    assert result.complete is True and result.down is False and not daemon._diag_partial


def test_incomplete_check_holds_scans_and_replacements(daemon):
    _started(daemon)
    daemon.failures["*"] = TIMEOUT
    daemon.e2e = False
    daemon.set_alive(**{tag.replace("-", "_"): False for tag in daemon.tags("proxy")})
    original = daemon._scan

    def slow(info, password, url=None):
        daemon.t += DIAG_BUDGET * 0.6
        return original(info, password, url)

    daemon._scan = slow
    daemon.next_target_check = 0.0
    daemon.applied.clear()
    daemon.tick()
    assert daemon._diag_partial and daemon.probe_target == ""
    assert daemon.applied == []  # ни замены участников, ни «адрес не отвечает»
    assert daemon.status()["scan_pacing"]["diagnosis"]["pending"] > 0
