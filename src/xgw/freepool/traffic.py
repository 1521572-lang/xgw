"""Трафик устройств через бесплатный пул (веха М2б.1): кого из проверенных серверов пула
допустить к трафику и в каком порядке, какие устройства идут через пул.

Решение заказчика 29.10.2026: сначала одно устройство — у него в панели «Бесплатные серверы»
(managed.routes[адрес] = POOL_ROUTE), остальной дом идёт через подписку. Серверы пула ведёт
обычный движок XGW: балансировщик «pool» в рабочем конфиге Xray (generator/builder.py), пробы
ядра, закреплённый основной (демон). Пул пуст — у устройства закрыто (R05), а не подписка.

Допуск (часть R30): своя свежая проверка шлюзом — OK или SLOW не старше FRESH; страна по
фактическому выходу — в регионе пула (strict — только он); ядро — Xray или sing-box; адрес
сервера — IPv4 в ссылке, а не имя (до закрепления имён в работающем ядре). Туннели (SSTP
VPN Gate, до М2в — OpenVPN) — отдельным шагом М2б.3 (решение заказчика 29.10.2026). Показатели
каталога и имя сервера в
допуске и порядке не участвуют: порядок — OK раньше SLOW, затем скорость проверки шлюза."""

from __future__ import annotations

import copy
from dataclasses import dataclass

from .. import managed
from ..config import Config
from ..model import ServerNode
from ..parsers.common import SingboxSpec
from ..paths import Paths
from ..watch import speed
from . import regions
from .models import Access, Backend, Variant
from .store import PoolStore

POOL_ROUTE = managed.POOL_ROUTE  # managed.routes[адрес] — устройство через бесплатные серверы
# Серверы списков перепроверяются раз в 2 часа (pool.LIST_CHECK_EVERY): час — запас на очередь.
FRESH = 3 * 3600.0
MEMBERS = 8  # серверов пула в балансировщике «pool» (живых выбирают пробы ядра)
SOURCE_PREFIX = "pool:"  # ServerNode.source серверов пула: «pool:<источник>»


@dataclass(frozen=True)
class TrafficServer:
    """Допущенный к трафику сервер пула: узел для сборки, вариант (закрепление адреса —
    probe.server_hosts) и скорость последней проверки шлюза, байт/с."""

    node: ServerNode
    variant: Variant
    verdict: str
    speed: float


def pool_devices(cfg: Config) -> list[str]:
    """Адреса устройств, которые идут через бесплатные серверы."""
    return sorted(ip for ip, server in cfg.managed.routes.items() if server == POOL_ROUTE)


def whole_house(cfg: Config) -> bool:
    """Весь дом через бесплатные серверы (free_pool.mode = on, веха М2б.2): подписка — только
    несущий канал входов демона (generator/builder.py, pool_all)."""
    return cfg.free_pool.mode == "on"


def pool_active(cfg: Config) -> bool:
    """Через пул идёт трафик: весь дом или хотя бы одно устройство."""
    return whole_house(cfg) or bool(pool_devices(cfg))


def wanted_regions(cfg: Config) -> list[str]:
    """Регион пула и, при region_policy = preferred, запасные регионы."""
    pool = cfg.free_pool
    extra = pool.fallback_regions if pool.region_policy == "preferred" else []
    return [pool.region, *[item for item in extra if item != pool.region]]


def _node(variant: Variant, country: str) -> ServerNode:
    singbox = None
    if variant.singbox is not None:
        singbox = SingboxSpec(
            main=copy.deepcopy(variant.singbox.get("main") or {}),
            endpoint=bool(variant.singbox.get("endpoint")),
            extra=copy.deepcopy(list(variant.singbox.get("extra") or [])),
        )
    return ServerNode(
        # Отпечаток — id варианта (32 hex): с 8-значными отпечатками подписки не совпадает.
        fingerprint=variant.variant_id,
        name=variant.name or f"{variant.provider} {variant.host or variant.address}",
        country=country.lower() if len(country) == 2 and country.isalpha() else "xx",
        protocol=variant.protocol,
        address=variant.host or variant.address,
        port=variant.port,
        outbound=copy.deepcopy(variant.outbound) if variant.outbound is not None else {},
        source=f"{SOURCE_PREFIX}{variant.provider}",
        singbox=singbox,
    )


def refusal(cfg: Config, variant: Variant, record: object, now: float) -> str:
    """Почему сервер пула не допущен к трафику устройств; пусто — допущен. record — итог его
    проверки из candidates.json. Причину показывает панель в строке сервера."""
    if variant.backend not in (Backend.XRAY, Backend.SINGBOX):
        return "туннели SSTP к трафику устройств — следующим шагом"
    # Только адрес-литерал (публичный IPv4 — разбор списка): сервер добавляется в работающий
    # Xray через API, а имя такого сервера Xray до перезапуска разрешает своим DNS, мимо
    # закрепления публичными адресами (generator/diff.py, dns.hosts). Серверы с именем —
    # следующим шагом.
    if not variant.address:
        return "адрес сервера — имя, а не IPv4: к трафику — следующим шагом"
    if not isinstance(record, dict) or not record.get("checked_at"):
        return "ещё не проверялся"
    if str(record.get("verdict") or "") not in ("OK", "SLOW"):
        return "последняя проверка не прошла"
    if now - float(record.get("checked_at") or 0) > FRESH:
        return f"проверка старше {int(FRESH // 3600)} ч — ждёт новой"
    country = str(record.get("egress_country") or "").upper()
    wanted = wanted_regions(cfg)
    if not any(regions.allowed(country, region) for region in wanted):
        return f"выход {country or 'не определён'} — не в регионе {', '.join(wanted)}"
    return ""


def admitted(cfg: Config, paths: Paths, now: float, *,
             store: PoolStore | None = None) -> list[TrafficServer]:
    """Допущенные к трафику серверы пула по порядку выбора (лучшие первыми). Наблюдение
    выключено — никого: пул тогда не проверяет серверы, и свежих итогов нет."""
    if cfg.free_pool.mode == "off":
        return []
    store = store or PoolStore(paths)
    records = store.candidates()
    found: list[TrafficServer] = []
    seen: set[str] = set()
    for provider in cfg.free_pool.providers:
        for variant in store.variants(provider):
            if variant.access != Access.FREE:
                continue
            key = variant.variant_id
            record = records.get(key)
            if key in seen or refusal(cfg, variant, record, now):
                continue
            assert isinstance(record, dict)
            verdict = str(record.get("verdict") or "")
            country = str(record.get("egress_country") or "").upper()
            seconds = float(record.get("seconds") or 0)
            speed = float(record.get("bytes") or 0) / seconds if seconds > 0 else 0.0
            seen.add(key)
            found.append(TrafficServer(_node(variant, country), variant, verdict, speed))
    found.sort(key=lambda item: (item.verdict != "OK", -item.speed))
    return found


def text(flow: dict) -> str:
    """Устройства через бесплатные серверы одной строкой (`xgw pool`, `xgw status`): flow —
    сводка демона free_pool.traffic (Daemon._pool_step)."""
    devices = ", ".join(str(item) for item in flow.get("devices") or [])
    head = ("Весь дом через бесплатные серверы" if flow.get("all")
            else f"Через бесплатные серверы: {devices}")
    if flow.get("closed"):
        why = ("допущенных серверов нет" if not flow.get("members")
               else "все серверы пула молчат")
        return f"{head} — закрыто: {why}"
    country = f" ({flow['country']})" if flow.get("country") else ""
    mbps = flow.get("mbps")
    rate = f", {speed.mbps_text(float(mbps))}" if isinstance(mbps, (int, float)) else ""
    return (f"{head} — сервер «{flow.get('server') or '?'}»{country}{rate}, задержка "
            f"{flow.get('delay_ms', 0)} мс; живых {flow.get('alive', 0)} из "
            f"{flow.get('members', 0)}")


def choose(servers: list[TrafficServer], applied: set[str], *, exclude: set[str],
           limit: int = MEMBERS, prefer: str = "") -> list[TrafficServer]:
    """Состав балансировщика «pool»: сервер, выбранный вручную (prefer — id варианта), если он
    допущен; затем те, что уже в применённом конфиге (applied — их отпечатки), если ещё
    допущены, — состав не перетасовывается при каждой сборке; затем лучшие из остальных до
    limit. exclude — отпечатки серверов подписки в той же сборке."""
    usable = [item for item in servers if item.node.fingerprint not in exclude]
    first = [item for item in usable if prefer and item.node.fingerprint == prefer]
    others = [item for item in usable if not first or item.node.fingerprint != prefer]
    kept = [item for item in others if item.node.fingerprint in applied]
    rest = [item for item in others if item.node.fingerprint not in applied]
    return (first + kept + rest)[:limit]


def pinned(pool: list, pin: str) -> object | None:
    """Сервер «pool», выбранный вручную: pin — id варианта, у NodeInfo из применённого конфига
    отпечаток — полный или начало id из тега pool-<страна>-<начало>."""
    if not pin:
        return None
    return next((info for info in pool if info.fingerprint and pin.startswith(info.fingerprint)),
                None)
