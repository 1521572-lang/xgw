"""Замена «мёртвых» участников балансировщика запасными (раздел 6.7).

Участник с alive = false дольше rotate_after_min меняется на лучший запасной,
прошедший последний скан (OK, затем SLOW по возрастанию времени). Тег узла
включает роль, поэтому замена — это ado нового тега, adrules и rmo старого:
ровно то, что делает Applier через diff_configs при пересборке конфига.

Порядок работы: plan_rotation → preferred_members → select_nodes(prefer=…) →
build → Applier.apply. Состав участников хранится в самом применённом конфиге
(теги proxy-*), поэтому следующая сборка замену не откатит.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Config
from ..generator.builder import NodeInfo
from ..model import ServerNode

REPLACEABLE_VERDICTS = ("OK", "SLOW")


@dataclass
class Rotation:
    replacements: list[tuple[str, ServerNode]]  # (тег мёртвого участника, запасной)


def plan_rotation(
    alive: dict[str, bool],
    dead_since: dict[str, float],
    scans: dict[str, str],  # текущий тег spare → вердикт скана
    scan_seconds: dict[str, float],
    members: list[NodeInfo],
    spares: list[tuple[NodeInfo, ServerNode]],  # (тег из конфига, узел)
    cfg: Config,
    now: float,
) -> Rotation | None:
    """alive — только по участникам с известным состоянием: узел, которого ещё
    нет в observatory (ядро только что запущено), мёртвым не считается."""
    rotate_after = cfg.filters.rotate_after_min * 60
    dead_members = [
        info.tag
        for info in members
        if alive.get(info.tag) is False
        and info.tag in dead_since
        and (now - dead_since[info.tag]) >= rotate_after
    ]
    if not dead_members:
        return None
    candidates = sorted(
        ((info, node) for info, node in spares if scans.get(info.tag) in REPLACEABLE_VERDICTS),
        key=lambda pair: (
            0 if scans[pair[0].tag] == "OK" else 1,
            scan_seconds.get(pair[0].tag, float("inf")),
        ),
    )
    replacements = [
        (dead_tag, node) for dead_tag, (_info, node) in zip(dead_members, candidates, strict=False)
    ]
    return Rotation(replacements=replacements) if replacements else None


def preferred_members(members: list[NodeInfo], rotation: Rotation | None) -> list[str]:
    """Отпечатки участников после замены — аргумент prefer для select_nodes.

    Замена встаёт на место выбывшего, остальные сохраняют порядок; выбывший
    в списке не остаётся и при сборке становится запасным.
    """
    swap = {tag: node.fingerprint for tag, node in (rotation.replacements if rotation else [])}
    return [swap.get(info.tag, info.fingerprint) for info in members]
