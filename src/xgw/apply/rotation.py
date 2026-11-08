"""Замена «мёртвых» участников балансировщика запасными (раздел 6.7).

Участник с alive = false дольше rotate_after_min меняется на лучший по рейтингу запасной
(rating.py, 0.2.0), прошедший последний скан, из всех подписок: той же страны (сначала — из
другой подписки: подписку целиком могли заблокировать), если его рейтинг не ниже
SAME_COUNTRY доли лучшего, — чтобы адрес выхода не прыгал по странам (ASSUMPTIONS п. 224);
затем OK раньше SLOW, затем по времени скана. Участник, который не
прошёл первую собственную проверку шлюза (соединение не устанавливается либо
«замораживается»), меняется сразу: первый состав балансировщика берётся из подписки
наугад, и ждать rotate_after_min с заведомо негодным сервером незачем. Тег узла
включает роль, поэтому замена — это ado нового тега, adrules и rmo старого:
ровно то, что делает Applier через diff_configs при пересборке конфига.

Порядок работы: plan_rotation → preferred_members → select_nodes(prefer=…) →
build → Applier.apply. Состав участников хранится в самом применённом конфиге
(теги proxy-*), поэтому следующая сборка замену не откатит.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field

from ..config import Config
from ..generator.builder import NodeInfo
from ..model import ServerNode

REPLACEABLE_VERDICTS = ("OK", "SLOW")
# Замена той же страны берётся, пока её рейтинг не ниже этой доли лучшего из годных: иначе
# медленный сервер той же страны вытеснил бы втрое лучший соседней.
SAME_COUNTRY = 0.7
# Вердикты первой проверки участника, при которых он меняется без ожидания
# rotate_after_min. Таймаут сюда не входит: он бывает разовым, и такой узел идёт
# обычным путём — через alive = false от самого Xray.
REPLACE_NOW_VERDICTS = ("CONNECT_FAIL", "FROZEN", "BODY_RESET")
# Разные пути (п. 341): среди годных замен одной группы (страна и подписка), чей рейтинг не ниже
# этой доли лучшего в группе, первой берётся та, что отличается от отказавшего участника адресом
# и физическим путём (TCP/UDP), затем — чем-то одним. Два имени на одном адресе — не другой путь.
# Регион, ручной выбор, квота и политика владельца отсеяны раньше; единственного годного сервера
# недостаток разнообразия не исключает.
DIVERSE_SHARE = 0.85


def diversity(mine: tuple[str, str] | None, theirs: tuple[str, str] | None) -> int:
    """2 — другой адрес и другой путь, 1 — что-то одно, 0 — то же самое или сведений нет."""
    if mine is None or theirs is None:
        return 0
    return int(mine[0] != theirs[0]) + int(mine[1] != theirs[1])


def diversity_text(mine: tuple[str, str] | None, theirs: tuple[str, str] | None) -> str:
    """Краткая причина выбора замены — без адресов и имён."""
    if mine is None or theirs is None:
        return "лучший по рейтингу (путь не известен)"
    path = theirs[1].upper() or "?"
    level = diversity(mine, theirs)
    if level == 2:
        return f"другой адрес и другой путь ({path})"
    if level == 1:
        return (f"другой адрес, тот же путь ({path})" if mine[0] != theirs[0]
                else f"тот же адрес, другой путь ({path}) — частичное разнообразие")
    return f"тот же адрес и путь ({path}) — другого сопоставимого нет"


@dataclass
class Rotation:
    replacements: list[tuple[str, ServerNode]]  # (тег мёртвого участника, запасной)
    reasons: dict[str, str] = field(default_factory=dict)  # тег мёртвого → причина выбора


def plan_rotation(
    alive: dict[str, bool],
    dead_since: dict[str, float],
    scans: dict[str, str],  # текущий тег spare → вердикт скана
    scan_seconds: dict[str, float],
    members: list[NodeInfo],
    spares: list[tuple[NodeInfo, ServerNode]],  # (тег из конфига, узел)
    cfg: Config,
    now: float,
    urgent: Collection[str] = (),
    origins: dict[str, tuple[str, str]] | None = None,
    scores: dict[str, float] | None = None,
    routes: dict[str, tuple[str, str]] | None = None,
) -> Rotation | None:
    """alive — только по участникам с известным состоянием: узел, которого ещё
    нет в observatory (ядро только что запущено), мёртвым не считается.

    urgent — теги участников, не прошедших первую проверку шлюза: их меняют сразу,
    не дожидаясь ни rotate_after_min, ни вердикта observatory. origins — отпечаток →
    (страна, подписка) участников и запасных; scores — отпечаток → рейтинг (rating.py);
    routes — отпечаток → (адрес, путь tcp/udp) для выбора другого пути (DIVERSE_SHARE)."""
    routes = routes or {}
    rotate_after = cfg.filters.rotate_after_min * 60
    dead_members = [
        info.tag
        for info in members
        if info.tag in urgent
        or (
            alive.get(info.tag) is False
            and info.tag in dead_since
            and (now - dead_since[info.tag]) >= rotate_after
        )
    ]
    if not dead_members:
        return None
    origins = origins or {}
    scores = scores or {}
    candidates = [
        (info, node) for info, node in spares if scans.get(info.tag) in REPLACEABLE_VERDICTS
    ]
    fingerprints = {info.tag: info.fingerprint for info in members}
    replacements = []
    reasons: dict[str, str] = {}
    for dead_tag in dead_members:
        if not candidates:
            break
        country, source = origins.get(fingerprints.get(dead_tag, ""), ("", ""))
        top = max((scores.get(node.fingerprint, 0.0) for _info, node in candidates), default=0.0)
        mine = routes.get(fingerprints.get(dead_tag, ""))

        def place_of(node, country=country, source=source, top=top):
            score = scores.get(node.fingerprint, 0.0)
            if country and node.country == country and score >= top * SAME_COUNTRY:
                return 0 if node.source != source else 1
            return 2

        best: dict[int, float] = {}
        for _info, node in candidates:
            place = place_of(node)
            best[place] = max(best.get(place, 0.0), scores.get(node.fingerprint, 0.0))

        def rank(pair, mine=mine, best=best, place_of=place_of):
            info, node = pair
            score = scores.get(node.fingerprint, 0.0)
            place = place_of(node)
            comparable = score >= best[place] * DIVERSE_SHARE
            spread = -diversity(mine, routes.get(node.fingerprint)) if comparable else 1
            return (
                place, spread, -score, 0 if scans[info.tag] == "OK" else 1,
                scan_seconds.get(info.tag, float("inf")),
            )

        chosen = min(candidates, key=rank)
        candidates.remove(chosen)
        replacements.append((dead_tag, chosen[1]))
        if mine is not None:
            reasons[dead_tag] = diversity_text(mine, routes.get(chosen[1].fingerprint))
    return Rotation(replacements=replacements, reasons=reasons) if replacements else None


def preferred_members(members: list[NodeInfo], rotation: Rotation | None) -> list[str]:
    """Отпечатки участников после замены — аргумент prefer для select_nodes.

    Замена встаёт на место выбывшего, остальные сохраняют порядок; выбывший
    в списке не остаётся и при сборке становится запасным.
    """
    swap = {tag: node.fingerprint for tag, node in (rotation.replacements if rotation else [])}
    return [swap.get(info.tag, info.fingerprint) for info in members]
