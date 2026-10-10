"""Сравнение конфигов Xray: что применяется через API, что требует перезапуск.

Правило раздела 6.7: если изменились только outbounds, probe-inbounds и routing —
меняем работающее ядро через API в порядке adi/ado → adrules → rmo/rmi.
Изменились dns, burstObservatory, policy, api/metrics или основные inbounds —
полный перезапуск (по правилам restart_window / состояний ALL_DEAD и XRAY_DOWN).

Исключение — dns.hosts: по разделу 6.4 домен сервера, добавленного через API,
Xray разрешает через общие DNS-серверы, а в hosts он попадает при следующем
полном перезапуске. Поэтому изменение одних только hosts перезапуска не требует —
иначе любой новый сервер с доменным адресом откладывался бы до окна перезапуска.
"""

from __future__ import annotations

from dataclasses import dataclass, field

RESTART_SECTIONS = ("log", "api", "metrics", "stats", "policy", "burstObservatory")
# Outbounds с этими префиксами тегов меняются на лету; остальные (direct, block,
# dns-out) — часть каркаса: через них идёт служебный трафик самого ядра.
API_OUTBOUND_PREFIXES = ("proxy-", "spare-", "chain-")
API_INBOUND_PREFIX = "probe-"


@dataclass
class ApiPlan:
    add_outbounds: list[dict] = field(default_factory=list)
    remove_outbound_tags: list[str] = field(default_factory=list)
    add_inbounds: list[dict] = field(default_factory=list)
    remove_inbound_tags: list[str] = field(default_factory=list)
    routing: dict | None = None  # новая секция routing целиком для adrules
    # Тег тот же, содержимое другое (в подписке сменили sni, путь, ключ…):
    # старый обработчик снимается и тут же ставится новый.
    replace_outbounds: list[dict] = field(default_factory=list)
    replace_inbounds: list[dict] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (
            self.add_outbounds
            or self.remove_outbound_tags
            or self.add_inbounds
            or self.remove_inbound_tags
            or self.replace_outbounds
            or self.replace_inbounds
            or self.routing is not None
        )


@dataclass
class DiffResult:
    plan: ApiPlan | None  # None — нужен полный перезапуск Xray
    restart_reasons: list[str] = field(default_factory=list)
    changed: bool = False
    # Изменения, которые вступят в силу при следующем перезапуске и сами его не требуют.
    deferred: list[str] = field(default_factory=list)


def _by_tag(items: list[dict]) -> dict[str, dict]:
    return {item["tag"]: item for item in items if "tag" in item}


def _dns_without_hosts(config: dict) -> dict:
    dns = config.get("dns")
    if not isinstance(dns, dict):
        return {}
    return {key: value for key, value in dns.items() if key != "hosts"}


def _dns_hosts(config: dict) -> object:
    dns = config.get("dns")
    return dns.get("hosts") if isinstance(dns, dict) else None


def diff_configs(old: dict, new: dict) -> DiffResult:
    reasons: list[str] = []
    for section in RESTART_SECTIONS:
        if old.get(section) != new.get(section):
            reasons.append(f"секция {section}")
    if _dns_without_hosts(old) != _dns_without_hosts(new):
        reasons.append("секция dns")

    old_outbounds = _by_tag(old.get("outbounds", []))
    new_outbounds = _by_tag(new.get("outbounds", []))
    old_inbounds = _by_tag(old.get("inbounds", []))
    new_inbounds = _by_tag(new.get("inbounds", []))

    def static(items: dict[str, dict], prefixes: tuple[str, ...] | str) -> dict[str, dict]:
        return {tag: item for tag, item in items.items() if not tag.startswith(prefixes)}

    if static(old_inbounds, API_INBOUND_PREFIX) != static(new_inbounds, API_INBOUND_PREFIX):
        reasons.append("основные inbounds")
    if static(old_outbounds, API_OUTBOUND_PREFIXES) != static(new_outbounds, API_OUTBOUND_PREFIXES):
        reasons.append("основные outbounds")

    routing_changed = old.get("routing") != new.get("routing")
    plan = ApiPlan(
        add_outbounds=[new_outbounds[tag] for tag in new_outbounds if tag not in old_outbounds],
        remove_outbound_tags=[tag for tag in old_outbounds if tag not in new_outbounds],
        add_inbounds=[new_inbounds[tag] for tag in new_inbounds if tag not in old_inbounds],
        remove_inbound_tags=[tag for tag in old_inbounds if tag not in new_inbounds],
        routing=new.get("routing") if routing_changed else None,
        replace_outbounds=[
            item
            for tag, item in new_outbounds.items()
            if tag in old_outbounds and old_outbounds[tag] != item
        ],
        replace_inbounds=[
            item
            for tag, item in new_inbounds.items()
            if tag in old_inbounds and old_inbounds[tag] != item
        ],
    )
    deferred: list[str] = []
    if _dns_hosts(old) != _dns_hosts(new):
        deferred.append("dns.hosts — вступит в силу при следующем перезапуске Xray")
    changed = bool(not plan.empty or reasons or deferred)
    if reasons:
        return DiffResult(plan=None, restart_reasons=reasons, changed=changed, deferred=deferred)
    return DiffResult(plan=plan, restart_reasons=[], changed=changed, deferred=deferred)


def apply_plan(client, plan: ApiPlan) -> list[str]:
    """Применяет план через API в порядке из ТЗ 6.7: adi/ado → adrules → rmo/rmi.

    Замена изменившихся обработчиков идёт до adrules, чтобы новые правила уже
    ссылались на актуальные outbounds. Возвращает список операций (для лога).
    """
    done: list[str] = []
    if plan.add_inbounds:
        client.add_inbounds(plan.add_inbounds)
        done.append(f"adi: {', '.join(i['tag'] for i in plan.add_inbounds)}")
    if plan.add_outbounds:
        client.add_outbounds(plan.add_outbounds)
        done.append(f"ado: {', '.join(o['tag'] for o in plan.add_outbounds)}")
    for inbound in plan.replace_inbounds:
        client.remove_inbound(inbound["tag"])
        client.add_inbounds([inbound])
        done.append(f"rmi+adi: {inbound['tag']}")
    for outbound in plan.replace_outbounds:
        client.remove_outbound(outbound["tag"])
        client.add_outbounds([outbound])
        done.append(f"rmo+ado: {outbound['tag']}")
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
