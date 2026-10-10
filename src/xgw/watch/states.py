"""Машина состояний watchdog (раздел 6.8). Переключением серверов не управляет
— это делает Xray; watchdog собирает сигналы, меняет состояние и решает,
какое действие выполнить (обновить подписку, переприменить правила, уведомить).

Приоритет состояний (что важнее при одновременных сбоях):
XRAY_DOWN > WAN_DOWN > LEAK > ALL_DEAD > DEGRADED > HEALTHY.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class State(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    ALL_DEAD = "ALL_DEAD"
    WAN_DOWN = "WAN_DOWN"
    XRAY_DOWN = "XRAY_DOWN"
    LEAK = "LEAK"


@dataclass(frozen=True)
class Signals:
    provider_ok: bool = True       # TCP к wan_check напрямую (метка 2)
    xray_ok: bool = True           # API и метрики отвечают
    alive_members: int = 0
    total_members: int = 0
    # Участники, по которым observatory ещё ничего не сообщил (ядро только что
    # запущено, первая проба не завершилась). Это не «мёртвые»: иначе каждый
    # перезапуск Xray давал бы ложный ALL_DEAD с обновлением подписки и уведомлением.
    unknown_members: int = 0
    e2e_ok: bool = True            # сквозная загрузка probe.url через http-in
    e2e_fail_streak: int = 0
    leak: bool = False             # trace_url вышел в home_country


@dataclass(frozen=True)
class StateDecision:
    state: State
    action: str                    # что делает watchdog при этом состоянии


_ACTIONS = {
    State.HEALTHY: "ничего",
    State.DEGRADED: "замена участников по 6.7, уведомление не чаще min_interval_min",
    State.ALL_DEAD: "внеочередное обновление подписки напрямую, скан запасных, "
    "замена участников, уведомление",
    State.WAN_DOWN: "тишина, проверки раз в 60 с",
    State.XRAY_DOWN: "systemd перезапускает службу; после двух неудач — откат на last-good",
    State.LEAK: "переприменить правила nftables, уведомление",
}


class StateMachine:
    def __init__(self, fail_threshold: int = 3) -> None:
        self.fail_threshold = max(1, fail_threshold)
        self.state: State = State.HEALTHY

    def update(self, signals: Signals) -> StateDecision:
        dead_members = signals.total_members - signals.alive_members - signals.unknown_members
        all_dead = signals.total_members > 0 and dead_members >= signals.total_members
        if not signals.xray_ok:
            self.state = State.XRAY_DOWN
        elif not signals.provider_ok:
            self.state = State.WAN_DOWN
        elif signals.leak:
            self.state = State.LEAK
        elif all_dead or (
            signals.e2e_fail_streak >= self.fail_threshold and not signals.e2e_ok
        ):
            self.state = State.ALL_DEAD
        elif dead_members > 0:
            self.state = State.DEGRADED
        else:
            self.state = State.HEALTHY
        return StateDecision(self.state, _ACTIONS[self.state])
