"""Машина состояний watchdog (раздел 6.8). Переключением серверов не управляет
— это делает Xray; watchdog собирает сигналы, меняет состояние и решает,
какое действие выполнить (обновить подписку, переприменить правила, уведомить).

Приоритет состояний (что важнее при одновременных сбоях):
XRAY_DOWN > WAN_DOWN > LEAK > PROBE_TARGET_UNREACHABLE > ALL_DEAD > DEGRADED > HEALTHY.

PROBE_TARGET_UNREACHABLE — не отвечает сам адрес пробы (probe.url), а не серверы:
пробы падают у всех одинаково, хотя трафик через VPN идёт (watch/target.py). Оно важнее
ALL_DEAD и DEGRADED, потому что «мёртвыми» серверы в этот момент только выглядят:
менять участников и внеочередно обновлять подписку незачем.
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
    PROBE_TARGET_UNREACHABLE = "PROBE_TARGET_UNREACHABLE"


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
    probe_target_ok: bool = True   # False — не отвечает сам probe.url, а не серверы


@dataclass(frozen=True)
class StateDecision:
    state: State
    action: str                    # что делает watchdog при этом состоянии


# Текст виден пользователю в `xgw status` и уведомлениях.
_ACTIONS = {
    State.HEALTHY: "вмешательство не требуется",
    State.DEGRADED: "часть серверов недоступна — замена на запасные",
    State.ALL_DEAD: "живых серверов нет — обновление подписки напрямую, скан запасных, замена",
    State.WAN_DOWN: "нет связи с провайдером — тишина, проверки раз в 60 с",
    State.XRAY_DOWN: "Xray не отвечает — перезапуск службы, после двух неудач откат на last-good",
    State.LEAK: "выход в домашнюю страну при включённом перехвате — "
    "правила nftables переприменяются",
    State.PROBE_TARGET_UNREACHABLE: "пробы всех серверов падают — вероятно, недоступен "
    "сам probe.url; замена серверов приостановлена, ядро пробует серверы по запасному адресу",
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
        elif not signals.probe_target_ok:
            self.state = State.PROBE_TARGET_UNREACHABLE
        elif all_dead or (
            signals.e2e_fail_streak >= self.fail_threshold and not signals.e2e_ok
        ):
            self.state = State.ALL_DEAD
        elif dead_members > 0:
            self.state = State.DEGRADED
        else:
            self.state = State.HEALTHY
        return StateDecision(self.state, _ACTIONS[self.state])
