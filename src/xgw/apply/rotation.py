"""Замена «мёртвых» участников балансировщика запасными (раздел 6.7).

Участник с alive = false дольше rotate_after_min меняется на лучший запасной,
прошедший последний скан (OK, затем SLOW по возрастанию времени). Тег узла
включает роль, поэтому замена — это ado нового тега, adrules и rmo старого:
ровно то, что делает Applier через diff_configs при пересборке конфига.

Теги запасных берутся из текущего BuildResult (как их построил генератор),
а не вычисляются заново — иначе коллизии тегов дадут расхождение с ядром.
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
    rotate_after = cfg.filters.rotate_after_min * 60
    dead_members = [
        info.tag
        for info in members
        if not alive.get(info.tag, True)
        and (now - dead_since.get(info.tag, now)) >= rotate_after
    ]
    if not dead_members:
        return None
    candidates = sorted(
        (node for info, node in spares if scans.get(info.tag) in REPLACEABLE_VERDICTS),
        key=lambda node: (
            0 if scans.get(_current_tag(spares, node)) == "OK" else 1,
            scan_seconds.get(_current_tag(spares, node), float("inf")),
        ),
    )
    replacements = list(zip(dead_members, candidates, strict=False))
    return Rotation(replacements=replacements) if replacements else None


def _current_tag(spares: list[tuple[NodeInfo, ServerNode]], node: ServerNode) -> str:
    for info, candidate in spares:
        if candidate.fingerprint == node.fingerprint:
            return info.tag
    return ""
