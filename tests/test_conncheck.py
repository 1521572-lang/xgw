"""Адрес проверки связности NetworkManager для исключения в барьере (net/conncheck.py)."""

import json
import logging
import threading
import time
from types import SimpleNamespace

import pytest

from xgw.net import cmd, conncheck
from xgw.paths import Paths


def _run(enabled="b true", uri='s "http://connectivity-check.ubuntu.com./"'):
    def run(argv, **_kwargs):
        if argv[-1] == "ConnectivityCheckEnabled":
            return enabled + chr(10)
        return uri + chr(10)
    return run


def _missing(argv, **_kwargs):
    raise cmd.CommandError("busctl: программа не найдена")


def test_uri_from_busctl_and_plain_text():
    assert conncheck.parse_uri('s "http://connectivity-check.ubuntu.com./"') == (
        "connectivity-check.ubuntu.com", 80)
    assert conncheck.parse_uri("https://check.example.org:8443/x") == ("check.example.org", 8443)
    assert conncheck.parse_uri('s ""') is None
    assert conncheck.nm_target(_run(enabled="b false")) is None
    assert conncheck.nm_target(_missing) is None


def test_refresh_writes_public_ipv4_only_and_removes_when_check_is_off(tmp_path):
    paths = Paths(tmp_path)
    paths.run.mkdir(parents=True)
    answers = ["91.189.91.49", "10.0.0.1", "2001:db8::1", "185.125.190.17", "91.189.91.49"]
    assert conncheck.refresh(paths, lambda host: answers, run=_run())
    data = json.loads(conncheck.path(paths).read_text())
    assert data == {"host": "connectivity-check.ubuntu.com", "port": 80,
                    "ips": ["185.125.190.17", "91.189.91.49"]}
    assert conncheck.read(paths) == (("185.125.190.17", "91.189.91.49"), 80)
    assert not conncheck.refresh(paths, lambda host: answers, run=_run())
    assert not conncheck.refresh(paths, lambda host: [], run=_run())  # не разрешился — прежнее
    assert conncheck.read(paths)[0]
    assert conncheck.refresh(paths, lambda host: answers, run=_run(enabled="b false"))
    assert conncheck.read(paths) == ((), 80)
    conncheck.path(paths).write_text('{"ips": ["10.0.0.1"], "port": 80}')
    assert conncheck.read(paths) == ((), 80)


def test_daemon_writes_file_and_reloads_rules_in_one_step(tmp_path):
    """Отчёт 7949034: файл адресов, записанный фоном, делал барьер «не загруженным» до
    следующего шага, и health сразу после установки откатил её. Теперь файл и загрузка правил —
    в основном потоке и вместе; без изменений правила не трогаются."""
    from xgw.daemon import Daemon

    paths = Paths(tmp_path)
    paths.run.mkdir(parents=True)
    ups = []
    fake = SimpleNamespace(paths=paths, log=logging.getLogger("t"),
                           capture=SimpleNamespace(up=lambda: ups.append(1)),
                           _capture_waits=lambda: False)
    found = {"host": "check.example.org", "port": 80, "ips": ["91.189.91.49"]}
    Daemon._conncheck_apply(fake, found)
    assert ups == [1] and conncheck.read(paths) == (("91.189.91.49",), 80)
    Daemon._conncheck_apply(fake, found)
    assert ups == [1]
    Daemon._conncheck_apply(fake, None)
    assert ups == [1, 1] and conncheck.read(paths) == ((), 80)
    assert conncheck.lookup(lambda host: [], run=_run()) is False


# --- п. 347, A-09: один поток и только свежий итог -------------------------------------------


def _scheduler(monkeypatch, lookup):
    from xgw import daemon as daemon_module
    from xgw.daemon import Daemon

    monkeypatch.setattr(daemon_module.conncheck, "lookup", lookup)
    applied: list = []
    fake = SimpleNamespace(
        _conncheck_lock=threading.Lock(), _conncheck_busy=False, _conncheck_generation=0,
        _conncheck_found=None, next_conncheck=0.0, capture=object(), log=logging.getLogger("t"),
        cfg=SimpleNamespace(dns=SimpleNamespace(resolvers=[])), mark=1, _stop=threading.Event(),
        _conncheck_apply=applied.append,
    )
    fake._conncheck_lookup = lambda generation: Daemon._conncheck_lookup(fake, generation)
    fake.step = lambda now: Daemon._conncheck_step(fake, now)
    fake.applied = applied
    return fake


def _wait(check):
    deadline = time.monotonic() + 5
    while not check() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert check()


def test_slow_lookup_is_not_doubled(monkeypatch):
    gate, started = threading.Event(), []

    def lookup(_resolve):
        started.append(1)
        gate.wait(5)
        return {"host": "a"}

    fake = _scheduler(monkeypatch, lookup)
    fake.step(10_000.0)
    _wait(lambda: started)
    for now in (20_000.0, 30_000.0):
        fake.step(now)
    assert len(started) == 1 and fake._conncheck_busy
    gate.set()
    _wait(lambda: fake._conncheck_found is not None and not fake._conncheck_busy)
    fake.step(10_000.0)
    assert fake.applied == [{"host": "a"}]


def test_old_generation_is_not_published(monkeypatch):
    fake = _scheduler(monkeypatch, lambda _resolve: {"host": "old"})
    fake._conncheck_generation = 2
    fake._conncheck_lookup(1)
    assert fake._conncheck_found is None
    fake._conncheck_generation = 1
    fake._conncheck_lookup(1)
    assert fake._conncheck_found == ({"host": "old"},)


@pytest.mark.parametrize("failure", ["error", "stop"])
def test_failed_or_stopped_lookup_releases_the_guard(monkeypatch, failure):
    def lookup(_resolve):
        if failure == "error":
            raise RuntimeError("сбой")
        return {"host": "a"}

    fake = _scheduler(monkeypatch, lookup)
    if failure == "stop":
        fake._stop.set()
    fake._conncheck_busy, fake._conncheck_generation = True, 1
    fake._conncheck_lookup(1)
    assert fake._conncheck_busy is False and fake._conncheck_found is None
