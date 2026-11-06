"""Новые серверы подписки — в работу пачкой (filters.new_hold_hours, отчёт group-hold)."""

import links
import pytest
from test_daemon import _inventory
from test_daemon_main import _make, _start, _step

from xgw import engine


@pytest.fixture()
def gateway(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    from xgw.paths import Paths

    paths = Paths.from_env()
    paths.ensure()
    instance = _make(paths, source=_inventory(links.FULL_LINKS[:3]))
    yield instance
    instance.store.close()


def _fps(inventory):
    return {node.fingerprint for node in inventory.nodes}


def _refresh(daemon, source, *, asked=False):
    daemon.source = source
    if asked:
        daemon.request_refresh()
    else:
        daemon.next_refresh = 0.0
    _step(daemon)
    _step(daemon)


def _new_one(daemon):
    full = _inventory(links.FULL_LINKS)
    new = (_fps(full) - _fps(daemon.inventory)).pop()
    return full, new


def test_new_server_waits_for_the_batch_and_comes_in_after_the_hold(gateway):
    _start(gateway)
    full, new = _new_one(gateway)
    _refresh(gateway, full)
    assert new not in _fps(gateway.inventory)
    assert new in {item.get("fingerprint") for item in engine.load_inventory(gateway.paths)}
    gateway.t += 5 * 3600
    _refresh(gateway, full)
    assert new not in _fps(gateway.inventory)
    gateway.t += 3600
    _refresh(gateway, full)
    assert new in _fps(gateway.inventory)


def test_batch_comes_in_at_once_when_servers_go_or_on_the_button(gateway):
    _start(gateway)
    full, new = _new_one(gateway)
    _refresh(gateway, full)
    assert new not in _fps(gateway.inventory)
    _refresh(gateway, full, asked=True)
    assert new in _fps(gateway.inventory)
    smaller = _inventory(links.FULL_LINKS[:2])
    _refresh(gateway, smaller)
    gone_and_new = _inventory(links.FULL_LINKS[1:])
    fresh = _fps(gone_and_new) - _fps(gateway.inventory)
    _refresh(gateway, gone_and_new)
    assert fresh and fresh <= _fps(gateway.inventory)


def test_zero_hours_lets_new_servers_in_at_once(gateway):
    gateway.cfg.filters.new_hold_hours = 0
    _start(gateway)
    full, new = _new_one(gateway)
    _refresh(gateway, full)
    assert new in _fps(gateway.inventory)
