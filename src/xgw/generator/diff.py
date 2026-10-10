"""Сравнение конфигов Xray: что применяется через API, что требует перезапуск.

Правило раздела 6.7: если изменились только outbounds, probe-inbounds и routing —
меняем работающее ядро через API в порядке adi/ado → adrules → rmo/rmi.
Изменились dns, burstObservatory, policy, api/metrics или основные inbounds —
полный перезапуск (по правилам restart_window / состояний ALL_DEAD и XRAY_DOWN).
"""

from __future__ import annotations

from dataclasses import dataclass, field

RESTART_SECTIONS = ("log", "api", "metrics", "stats", "policy", "dns", "burstObservatory")


@dataclass
class ApiPlan:
    add_outbounds: list[dict] = field(default_factory=list)
    remove_outbound_tags: list[str] = field(default_factory=list)
    add_inbounds: list[dict] = field(default_factory=list)
    remove_inbound_tags: list[str] = field(default_factory=list)
    routing: dict | None = None  # новая секция routing целиком для adrules


@dataclass
class DiffResult:
    plan: ApiPlan | None  # None — нужен полный перезапуск Xray
    restart_reasons: list[str] = field(default_factory=list)
    changed: bool = False


def _by_tag(items: list[dict]) -> dict[str, dict]:
    return {item["tag"]: item for item in items if "tag" in item}


def _main_inbounds(config: dict) -> list[dict]:
    """Основные inbounds (всё, кроме probe-*): их изменение требует перезапуска."""
    return [
        item
        for item in config.get("inbounds", [])
        if not str(item.get("tag", "")).startswith("probe-")
    ]


def diff_configs(old: dict, new: dict) -> DiffResult:
    reasons: list[str] = []
    for section in RESTART_SECTIONS:
        if old.get(section) != new.get(section):
            reasons.append(f"секция {section}")
    if _main_inbounds(old) != _main_inbounds(new):
        reasons.append("основные inbounds")

    old_outbounds = _by_tag(old.get("outbounds", []))
    new_outbounds = _by_tag(new.get("outbounds", []))
    old_inbounds = _by_tag(old.get("inbounds", []))
    new_inbounds = _by_tag(new.get("inbounds", []))
    routing_changed = old.get("routing") != new.get("routing")

    plan = ApiPlan(
        add_outbounds=[new_outbounds[tag] for tag in new_outbounds if tag not in old_outbounds],
        remove_outbound_tags=[tag for tag in old_outbounds if tag not in new_outbounds],
        add_inbounds=[new_inbounds[tag] for tag in new_inbounds if tag not in old_inbounds],
        remove_inbound_tags=[tag for tag in old_inbounds if tag not in new_inbounds],
        routing=new.get("routing") if routing_changed else None,
    )
    changed = bool(
        plan.add_outbounds
        or plan.remove_outbound_tags
        or plan.add_inbounds
        or plan.remove_inbound_tags
        or routing_changed
        or reasons  # изменилась секция, требующая перезапуска, — это тоже изменение
    )
    if reasons:
        return DiffResult(plan=None, restart_reasons=reasons, changed=changed)
    return DiffResult(plan=plan, restart_reasons=[], changed=changed)


def apply_plan(client, plan: ApiPlan) -> list[str]:
    """Применяет план через API в порядке из ТЗ 6.7: adi/ado → adrules → rmo/rmi.

    Возвращает список выполненных операций (для лога).
    """
    done: list[str] = []
    if plan.add_inbounds:
        client.add_inbounds(plan.add_inbounds)
        done.append(f"adi: {', '.join(i['tag'] for i in plan.add_inbounds)}")
    if plan.add_outbounds:
        client.add_outbounds(plan.add_outbounds)
        done.append(f"ado: {', '.join(o['tag'] for o in plan.add_outbounds)}")
    if plan.routing is not None:
        client.replace_routing(plan.routing)
        done.append("adrules: routing")
    for tag in plan.remove_outbound_tags:
        client.remove_outbound(tag)
        done.append(f"rmo: {tag}")
    for tag in plan.remove_inbound_tags:
        client.remove_inbound(tag)
        done.append(f"rmi: {tag}")
    return done
