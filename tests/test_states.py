"""Машина состояний watchdog на синтетических данных (раздел 9 ТЗ)."""

import pytest

from xgw.watch.states import Signals, State, StateMachine


def test_healthy_when_all_good():
    machine = StateMachine()
    decision = machine.update(Signals(alive_members=3, total_members=3))
    assert decision.state is State.HEALTHY


def test_degraded_when_part_dead():
    machine = StateMachine()
    decision = machine.update(Signals(alive_members=1, total_members=3))
    assert decision.state is State.DEGRADED
    assert "замена" in decision.action


def test_all_dead_when_no_alive_members():
    machine = StateMachine()
    decision = machine.update(Signals(alive_members=0, total_members=3))
    assert decision.state is State.ALL_DEAD


def test_all_dead_after_e2e_fail_streak():
    machine = StateMachine(fail_threshold=3)
    base = dict(alive_members=2, total_members=3, e2e_ok=False, e2e_fail_streak=3)
    assert machine.update(Signals(**base)).state is State.ALL_DEAD
    # меньше порога подряд — ещё DEGRADED (участники живы, сквозная падает)
    assert machine.update(Signals(**{**base, "e2e_fail_streak": 2})).state is State.DEGRADED


def test_wan_down_wins_over_dead_members():
    machine = StateMachine()
    decision = machine.update(
        Signals(alive_members=0, total_members=3, provider_ok=False)
    )
    assert decision.state is State.WAN_DOWN
    assert "тишина" in decision.action


def test_xray_down_wins_over_everything():
    machine = StateMachine()
    decision = machine.update(
        Signals(alive_members=0, total_members=3, provider_ok=False, xray_ok=False)
    )
    assert decision.state is State.XRAY_DOWN


def test_leak_detected():
    machine = StateMachine()
    decision = machine.update(Signals(alive_members=3, total_members=3, leak=True))
    assert decision.state is State.LEAK
    assert "nftables" in decision.action


def test_state_kept_between_updates():
    machine = StateMachine()
    machine.update(Signals(alive_members=0, total_members=3))
    assert machine.state is State.ALL_DEAD
    machine.update(Signals(alive_members=3, total_members=3))
    assert machine.state is State.HEALTHY


@pytest.mark.parametrize(
    "signals,expected",
    [
        (Signals(alive_members=5, total_members=5), State.HEALTHY),
        (Signals(alive_members=4, total_members=5), State.DEGRADED),
        (Signals(alive_members=0, total_members=5), State.ALL_DEAD),
        (Signals(alive_members=1, total_members=1, provider_ok=False), State.WAN_DOWN),
        (Signals(alive_members=1, total_members=1, xray_ok=False), State.XRAY_DOWN),
        (Signals(alive_members=1, total_members=1, leak=True), State.LEAK),
    ],
)
def test_table_from_tz(signals, expected):
    assert StateMachine().update(signals).state is expected


def test_unknown_members_are_not_dead():
    """Сразу после запуска Xray observatory пуст: это не ALL_DEAD и не DEGRADED."""
    machine = StateMachine()
    assert machine.update(Signals(alive_members=0, total_members=3, unknown_members=3)).state \
        is State.HEALTHY
    assert machine.update(Signals(alive_members=1, total_members=3, unknown_members=2)).state \
        is State.HEALTHY
    assert machine.update(Signals(alive_members=1, total_members=3, unknown_members=1)).state \
        is State.DEGRADED
    assert machine.update(Signals(alive_members=0, total_members=3, unknown_members=0)).state \
        is State.ALL_DEAD
    # сквозная проверка важнее «неизвестно»: поток не идёт fail_threshold раз подряд
    assert machine.update(
        Signals(alive_members=0, total_members=3, unknown_members=3,
                e2e_ok=False, e2e_fail_streak=3)
    ).state is State.ALL_DEAD


def test_no_members_is_not_all_dead():
    assert StateMachine().update(Signals()).state is State.HEALTHY
