"""Конфиг Xray для телефона (А1 `ANDROID_APP_PLAN.md`): тот же набор серверов, что работает
на шлюзе, но для Xray внутри приложения XGW на Android.

Собирается из применённого конфига шлюза, а не заново из подписок: на телефоне — ровно то,
что шлюз уже проверил (участники балансировщика, их профиль обхода, цепочки, DNS, правила
«напрямую»). Что меняется:

- вход — `tun` (`tun-in`): интерфейс создаёт VpnService Android, Xray получает его
  дескриптор через XRAY_TUN_FD; входы шлюза (TPROXY, socks, http, пробы) не нужны;
- метки `sockopt.mark` убираются: на Android соединения самого Xray идут мимо VPN, потому
  что приложение исключено из своего VPN;
- серверы, которые шлюз ведёт через мосты sing-box (outbound socks на 127.0.0.1), на телефон
  не попадают: sing-box в приложении нет;
- проверка серверов — лёгкая: HEAD к generate_204 раз в 3 минуты, а не скачивание файла
  каждые 30 с, как на шлюзе (на мобильной сети это сотни мегабайт в сутки);
- API, статистики и метрик нет.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping

from .builder import BALANCER_TAG

TUN_TAG = "tun-in"
TUN_NAME = "xgw0"
TUN_MTU = 1500
PROBE_URL = "https://www.gstatic.com/generate_204"
PROBE_INTERVAL = "3m"
_GATEWAY_INBOUNDS = ("tproxy-in", "tproxy-in6", "tun-in")
_SERVICE = ("direct", "block", "dns-out")


class PhoneConfigError(ValueError):
    """Собрать конфиг для телефона нельзя; текст — для приложения и панели."""


def _bridge(outbound: Mapping) -> bool:
    """Outbound к мосту sing-box на самом шлюзе."""
    if outbound.get("protocol") != "socks":
        return False
    servers = (outbound.get("settings") or {}).get("servers") or []
    return any(str(item.get("address")) in ("127.0.0.1", "::1", "localhost")
               for item in servers if isinstance(item, dict))


def _dialer(outbound: Mapping) -> str:
    sockopt = ((outbound.get("streamSettings") or {}).get("sockopt") or {})
    return str(sockopt.get("dialerProxy") or "") if isinstance(sockopt, dict) else ""


def _strip_mark(outbound: dict) -> None:
    stream = outbound.get("streamSettings")
    sockopt = stream.get("sockopt") if isinstance(stream, dict) else None
    if not isinstance(sockopt, dict):
        return
    sockopt.pop("mark", None)
    if not sockopt:
        del stream["sockopt"]
    if not stream:
        del outbound["streamSettings"]


def build(applied: Mapping | None) -> dict:
    """Применённый конфиг шлюза → конфиг для телефона; PhoneConfigError — нельзя."""
    if not isinstance(applied, Mapping) or not isinstance(applied.get("outbounds"), list):
        raise PhoneConfigError("на шлюзе ещё нет применённого конфига Xray")
    by_tag = {str(item.get("tag")): item for item in applied["outbounds"]
              if isinstance(item, Mapping) and item.get("tag")}
    members = [tag for tag in by_tag if tag.startswith("proxy-") and not _bridge(by_tag[tag])]
    if not members:
        raise PhoneConfigError("на шлюзе нет серверов в работе, которые умеет Xray телефона")
    balancers = ((applied.get("routing") or {}).get("balancers") or [])
    balancer = next((dict(item) for item in balancers
                     if isinstance(item, Mapping) and item.get("tag") == BALANCER_TAG), {})
    fallback = str(balancer.get("fallbackTag") or "")
    if fallback not in by_tag or _bridge(by_tag[fallback]):
        fallback = members[0]
    wanted = [*members, *([fallback] if fallback not in members else [])]
    queue = [_dialer(by_tag[tag]) for tag in wanted]
    while queue:
        tag = queue.pop()
        if tag and tag in by_tag and tag not in wanted:
            wanted.append(tag)
            queue.append(_dialer(by_tag[tag]))
    outbounds = []
    for tag in [*wanted, *(tag for tag in _SERVICE if tag in by_tag)]:
        outbound = copy.deepcopy(dict(by_tag[tag]))
        _strip_mark(outbound)
        outbounds.append(outbound)
    known = {outbound["tag"] for outbound in outbounds}

    rules = []
    for rule in ((applied.get("routing") or {}).get("rules") or []):
        if not isinstance(rule, Mapping):
            continue
        rule = copy.deepcopy(dict(rule))
        inbound = rule.get("inboundTag")
        if inbound is not None:
            tags = [tag for tag in inbound if tag in _GATEWAY_INBOUNDS]
            if not tags:
                continue  # пробы шлюза и прочие его входы
            rule["inboundTag"] = [TUN_TAG]
        if rule.get("outboundTag") and rule["outboundTag"] not in known:
            continue
        if rule not in rules:
            rules.append(rule)
    balancer.update(tag=BALANCER_TAG, selector=["proxy-"], fallbackTag=fallback)
    balancer.setdefault("strategy", {"type": "leastPing"})
    routing = {
        "domainStrategy": (applied.get("routing") or {}).get("domainStrategy") or "IPIfNonMatch",
        "rules": rules,
        "balancers": [balancer],
    }
    config: dict = {
        "log": {"loglevel": "warning"},
        "inbounds": [{
            "tag": TUN_TAG, "port": 0, "protocol": "tun",
            "settings": {"name": TUN_NAME, "mtu": TUN_MTU},
            "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
        }],
        "outbounds": outbounds,
        "routing": routing,
        "burstObservatory": {
            "subjectSelector": ["proxy-"],
            "pingConfig": {
                "destination": PROBE_URL, "connectivity": "", "interval": PROBE_INTERVAL,
                "sampling": 1, "timeout": "5s", "httpMethod": "HEAD",
            },
        },
    }
    if isinstance(applied.get("dns"), Mapping):
        config["dns"] = copy.deepcopy(dict(applied["dns"]))
    return config


def servers(config: Mapping) -> list[str]:
    """Теги серверов в конфиге телефона — для панели и ответа приложению."""
    return [str(item.get("tag")) for item in config.get("outbounds") or []
            if str(item.get("tag", "")).startswith("proxy-")]
