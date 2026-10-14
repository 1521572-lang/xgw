"""Общий конвейер XGW: подписки → узлы → конфиг Xray → применение.

Им пользуются и команды CLI (`generate`, `apply`), и демон: получить серверы
(через Xray или напрямую, с кэшем), собрать конфиг с сохранением состава
участников, проверить его установленным Xray и отдать Applier.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import config, fetch, log, marknet, masking
from .apply.applier import Applier, ApplyOutcome
from .generator import builder, validate
from .model import ServerNode, raw_to_node
from .parsers.common import ParseError, RawServer, parse_body, parse_links_text
from .paths import Paths, atomic_write_json
from .store import Store, SubscriptionCache
from .xraycore.api import ApiClient
from .xraycore.service import PidfileXrayService, SystemdXrayService, XrayService


class EngineError(Exception):
    """Конфиг собрать не удалось: нет серверов или Xray его не принимает."""


@dataclass
class Inventory:
    """Все серверы, известные на момент последнего опроса подписок."""

    nodes: list[ServerNode] = field(default_factory=list)
    quotas: dict[str, dict[str, int]] = field(default_factory=dict)
    # False — хотя бы одна подписка не дала серверов даже из кэша: применять такой
    # список нельзя, из работающего конфига пропали бы её серверы.
    complete: bool = True
    # Подписки, которые сейчас получить не удалось: имя → причина (без секретов).
    errors: dict[str, str] = field(default_factory=dict)


@dataclass
class Assembly:
    result: builder.BuildResult
    selection: builder.Selection
    verdict: bool | None  # итог xray run -test; None — проверка не выполнялась
    invalid: int = 0  # сколько серверов отброшено: их конфиг установленный Xray не принимает


def bypass_mark(cfg: config.Config, logger) -> int | None:
    """Метка для прямых запросов. Без CAP_NET_ADMIN (запуск не от root) SO_MARK
    недоступен — работаем без метки и предупреждаем: при включённом перехвате
    такие запросы пойдут через Xray."""
    if not marknet.is_mark_supported():
        return None
    if marknet.mark_usable(cfg.capture.mark_bypass):
        return cfg.capture.mark_bypass
    logger.warning("нет прав на SO_MARK (нужен root) — прямые запросы идут без метки")
    return None


def healthy_http_in(cfg: config.Config) -> tuple[str, int] | None:
    """http-in работающего Xray: при здоровом ядре подписка запрашивается через него."""
    address = ("127.0.0.1", cfg.xray.http_port)
    try:
        with socket.create_connection(address, timeout=1.0):
            return address
    except OSError:
        return None


def has_sources(cfg: config.Config) -> bool:
    """Есть ли откуда брать серверы: хотя бы одна подписка или ссылка."""
    return any(sub.url for sub in cfg.subscriptions) or bool(cfg.manual.links)


def sources_key(cfg: config.Config) -> tuple:
    """Откуда берутся серверы: пока это не меняется, подписки заново не запрашиваются."""
    subs = tuple(
        (sub.name, sub.url, sub.user_agent, tuple(sorted(sub.headers.items())))
        for sub in cfg.subscriptions
    )
    return subs, tuple(cfg.manual.links)


def inventory_file(paths: Paths) -> Path:
    return paths.var / "inventory.json"


def save_inventory(paths: Paths, cfg: config.Config, inventory: Inventory) -> None:
    """Список всех серверов подписок — для панели: и тех, что в конфиг не попали.

    В нём только то, что видно и так (имя, протокол, источник); ключей нет.
    """
    servers = []
    for node in inventory.nodes:
        if node.keep_tag:
            continue  # звенья цепочек — не самостоятельные серверы
        reason = builder.skip_reason(node, cfg, dead=quarantined())
        servers.append({
            "fingerprint": node.fingerprint,
            "name": node.name,
            "source": node.source,
            "protocol": node.protocol,
            "skip": "" if reason == "excluded" else reason,
        })
    atomic_write_json(
        inventory_file(paths), {"saved": time.time(), "servers": servers}, mode=0o600
    )


def load_inventory(paths: Paths) -> list[dict]:
    loaded = read_json(inventory_file(paths)) or {}
    servers = loaded.get("servers")
    return [item for item in servers if isinstance(item, dict)] if isinstance(servers, list) else []


def config_secrets(cfg: config.Config) -> list[str]:
    """Секреты из config.toml, которые регулярками не распознать."""
    values = [cfg.notify.telegram_bot_token, cfg.status.token]
    for sub in cfg.subscriptions:
        values.extend(sub.headers.values())
    return [value for value in values if value]


def collect(
    cfg: config.Config,
    paths: Paths,
    *,
    mark: int | None,
    logger,
    via_xray: bool = True,
) -> Inventory:
    """Опрос всех подписок и ручных ссылок.

    via_xray=False — запрашивать только напрямую (внеочередное обновление в
    ALL_DEAD: через мёртвые серверы подписку не получить).
    """
    remote = any(sub.url and not sub.url.startswith("file://") for sub in cfg.subscriptions)
    proxy = healthy_http_in(cfg) if via_xray and remote else None
    cache = SubscriptionCache(paths.cache_dir)
    inventory = Inventory()
    for sub in cfg.subscriptions:
        if not sub.url:
            continue
        raws, userinfo, error = _load_subscription(sub, cfg, cache, mark, proxy, logger)
        if not raws:
            inventory.complete = False
        if error:
            inventory.errors[sub.name] = error
        if userinfo:
            inventory.quotas[sub.name] = userinfo
        inventory.nodes.extend(raw_to_node(raw, sub.name) for raw in raws)
    if cfg.manual.links:
        raws, _meta, manual_warnings = parse_links_text("\n".join(cfg.manual.links), "manual")
        for warning in manual_warnings:
            logger.warning("%s", warning)
        inventory.nodes.extend(raw_to_node(raw, "manual") for raw in raws)
    log.add_secrets(masking.collect_secrets([node.outbound for node in inventory.nodes]))
    return inventory


def _load_subscription(
    sub: config.Subscription,
    cfg: config.Config,
    cache: SubscriptionCache,
    mark: int | None,
    proxy: tuple[str, int] | None,
    logger,
) -> tuple[list[RawServer], dict[str, int], str]:
    """Серверы подписки, её квота и причина сбоя (пустая, если запрос удался).
    Ответ без серверов считается сбоем: тогда берётся последняя удачная версия из
    кэша, а кэш не перезаписывается."""
    label = f"{sub.name} ({masking.mask_url(sub.url)})"
    error = ""
    routes: list[tuple[str, tuple[str, int] | None]] = [("напрямую", None)]
    if proxy is not None and not sub.url.startswith("file://"):
        routes.insert(0, ("через Xray", proxy))
    for route, via in routes:
        try:
            result = fetch.fetch_subscription(
                sub.url, user_agent=sub.user_agent, headers=sub.headers, proxy=via,
                # Напрямую — меткой мимо перехвата и со своим резолвером: системный
                # DNS при упавшем Xray не отвечает. Через Xray хватит одного повтора:
                # если серверы мертвы, быстрее перейти к прямому запросу.
                mark=None if via else mark,
                bootstrap=None if via or mark is None else cfg.dns.bootstrap,
                retries=1 if via else 3,
            )
            raws, meta, sub_warnings = parse_body(result.body, sub.name)
            if not raws:
                raise ParseError("в ответе нет серверов")
        except (fetch.FetchError, ParseError) as exc:
            logger.error("подписка %s, запрос %s: %s", label, route, exc)
            error = masking.mask_text(str(exc))[:300]
            continue
        for warning in sub_warnings:
            logger.warning("%s", warning)
        userinfo = fetch.parse_userinfo(
            result.headers.get("subscription-userinfo") or meta.get("subscription-userinfo", "")
        )
        try:
            cache.save(sub.name, result.body, userinfo)
        except OSError as exc:
            logger.error("подписка %s: кэш не записан: %s", label, exc)
        return raws, userinfo, ""

    error = error or "получить не удалось"
    cached = cache.load(sub.name)
    if cached is None:
        logger.error("подписка %s: получить не удалось, кэша нет", label)
        return [], {}, error
    try:
        raws, _meta, _warnings = parse_body(cached.body, sub.name)
    except ParseError as exc:
        logger.error("подписка %s: кэш не читается: %s", label, exc)
        return [], {}, error
    age_min = max(0, int((time.time() - cached.saved_at) // 60)) if cached.saved_at else 0
    logger.warning(
        "подписка %s: используется кэш (%d серверов, сохранён %d мин назад)",
        label, len(raws), age_min,
    )
    return raws, cached.userinfo, error


def read_json(path: Path) -> dict | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def assemble(
    cfg: config.Config,
    paths: Paths,
    inventory: Inventory,
    *,
    mark: int | None,
    logger,
    xray_bin: Path | None,
    check: bool = True,
    prefer: list[str] | None = None,
) -> Assembly:
    """Конфиг Xray из известных серверов.

    Состав участников, порты и пароль проб берутся из применённого конфига:
    обновление подписки не должно перетасовывать то, что уже работает в ядре.
    prefer — явный состав участников (замена «мёртвого» при ротации).
    Сервер, конфиг которого установленный Xray не принимает, отбрасывается.
    """
    applied = read_json(paths.xray_config_file)
    probe_password, probe_ports = builder.probe_state(applied)
    if prefer is None:
        prefer = builder.member_fingerprints(applied, inventory.nodes)

    rejected: set[str] = set()
    dead = quarantined()
    first = True
    while True:
        usable = [node for node in inventory.nodes if node.fingerprint not in rejected]
        selection = builder.select_nodes(usable, cfg, prefer=prefer, dead=dead)
        if first:
            first = False
            for warning in selection.warnings:
                logger.warning("%s", warning)
        if not selection.members:
            if selection.stats.get("dns") and not any(
                selection.stats.get(key) for key in ("junk", "ipv6", "filter", "excluded")
            ):
                raise EngineError(
                    "ни один сервер не подходит: домены серверов не разрешаются "
                    "(проверьте подписку и dns.bootstrap)"
                )
            raise EngineError("после фильтров не осталось серверов")
        hosts, gone = _resolve_hosts(selection, cfg, mark, logger)
        if gone:
            # Домена нет в DNS — серверы с ним из конфига убираются, а на их место в
            # балансировщике встают следующие: собираем состав заново.
            dead = dead | gone
            continue
        try:
            result = builder.build(
                cfg, selection, hosts=hosts,
                probe_password=probe_password, probe_ports=probe_ports,
            )
        except builder.BuildError as exc:
            raise EngineError(str(exc)) from exc
        if not check:
            return Assembly(result, selection, None, len(rejected))
        verdict, output = validate.validate_config(result.config, xray_bin)
        if verdict is not False:
            return Assembly(result, selection, verdict, len(rejected))
        # Конфиг не прошёл: ищем серверы, которые установленный Xray не принимает
        # (снятый транспорт, неизвестный шифр), и собираем конфиг без них.
        newly = _reject_invalid(result, xray_bin, logger) - rejected
        if not newly:
            raise EngineError(f"конфиг не прошёл xray run -test:\n{output}")
        rejected |= newly


def _reject_invalid(result: builder.BuildResult, xray_bin: Path | None, logger) -> set[str]:
    """Отпечатки серверов, чьи outbounds установленный Xray не принимает."""
    if xray_bin is None:
        return set()
    by_tag = {info.tag: info.fingerprint for info in result.nodes}
    candidates = [o for o in result.config["outbounds"] if o.get("tag") in by_tag]
    invalid = validate.find_invalid_outbounds(candidates, xray_bin)
    for tag, reason in invalid.items():
        logger.warning("узел %s отброшен: Xray не принимает его конфиг (%s)", tag, reason)
    return {by_tag[tag] for tag in invalid if tag in by_tag}


# Домены серверов меняют адреса редко, а резолвить их приходится при каждой
# сборке: держим ответы в памяти процесса (демона) четверть часа.
_HOSTS_TTL = 900.0
_hosts_cache: dict[str, tuple[float, list[str]]] = {}
# Карантин: домены, про которые резолвер ответил определённо «такого имени нет».
# Серверы с такими адресами в конфиг Xray не попадают — иначе они занимали бы места в
# запасных и тратили пробы впустую. Повторная проверка — раз в шесть часов: владелец
# подписки мог вернуть домен. Сбой самих резолверов (нет сети, таймаут) в карантин не
# отправляет никого: иначе при отключении интернета из конфига пропали бы все серверы.
_DEAD_TTL = 6 * 3600.0
_dead_hosts: dict[str, tuple[float, str]] = {}


def resolve_domain(name: str, bootstrap: list[str], mark: int | None) -> list[str]:
    """Отдельная функция, чтобы тесты не ходили в настоящий DNS."""
    return fetch.resolve_domain(name, bootstrap, mark=mark)


def forget_quarantine() -> None:
    """Проверить отложенные домены заново при ближайшей сборке (кнопка «Обновить»)."""
    _dead_hosts.clear()


def quarantined() -> frozenset[str]:
    """Домены в карантине на этот момент (срок не вышел)."""
    now = time.monotonic()
    for name in [name for name, (since, _why) in _dead_hosts.items() if now - since >= _DEAD_TTL]:
        del _dead_hosts[name]
    return frozenset(_dead_hosts)


def _resolve_hosts(
    selection: builder.Selection, cfg: config.Config, mark, logger
) -> tuple[dict, frozenset[str]]:
    """Домены серверов разрешаются через bootstrap-резолверы и попадают в dns.hosts.
    Второе значение — домены, которых в DNS нет: они только что ушли в карантин."""
    hosts: dict[str, list[str]] = {}
    failed: set[str] = set()
    gone: set[str] = set()
    now = time.monotonic()
    for node in [*selection.members, *selection.spares, *selection.chains]:
        if not node.address or node.address in hosts or node.address in failed:
            continue
        try:
            ipaddress.ip_address(node.address)
            continue
        except ValueError:
            pass
        cached = _hosts_cache.get(node.address)
        if cached and now - cached[0] < _HOSTS_TTL:
            hosts[node.address] = cached[1]
            continue
        try:
            ips = resolve_domain(node.address, cfg.dns.bootstrap, mark)
        except fetch.NoSuchDomain as exc:
            failed.add(node.address)
            if node.keep_tag:
                # Звено цепочки не выбросить отдельно от серверов, которые на него
                # ссылаются: оставляем как есть, имя попробует разрешить сам Xray.
                logger.warning("домен %s не разрешён: %s", node.address, exc)
                continue
            _dead_hosts[node.address] = (now, str(exc))
            _hosts_cache.pop(node.address, None)
            gone.add(node.address)
            logger.warning(
                "%s — серверы с этим адресом отложены, повторная проверка через %d ч",
                exc, int(_DEAD_TTL // 3600),
            )
            continue
        except fetch.ResolveError as exc:
            failed.add(node.address)
            if cached:  # резолверы недоступны — лучше прежний адрес, чем никакого
                hosts[node.address] = cached[1]
            logger.warning("домен %s не разрешён: %s", node.address, exc)
            continue
        hosts[node.address] = ips
        _hosts_cache[node.address] = (now, ips)
    return hosts, frozenset(gone)


def summary(assembly: Assembly) -> dict[str, int]:
    """Сводка разбора подписок: сколько серверов в работе и сколько отброшено."""
    stats = assembly.selection.stats
    return {
        "members": len(assembly.selection.members),
        "spares": len(assembly.selection.spares),
        # недоступные и служебные: служебные адреса, IPv6 при ipv6 = off, отсеянные
        # фильтром имён, домены без адреса и серверы, чей конфиг Xray не принимает
        "dropped": sum(stats.get(key, 0) for key in ("junk", "ipv6", "filter", "dns"))
        + assembly.invalid,
        "duplicates": stats.get("duplicates", 0),
        "excluded": stats.get("excluded", 0),
        "dns": stats.get("dns", 0),
    }


def persist(
    paths: Paths,
    assembly: Assembly,
    quotas: dict[str, dict[str, int]],
    *,
    record_event: bool = True,
) -> None:
    """Записывает в SQLite состав узлов последней сборки и квоты подписок."""
    result = assembly.result
    nodes = [*assembly.selection.members, *assembly.selection.spares]
    by_fingerprint = {node.fingerprint: node for node in nodes}
    now = int(time.time())
    entries = []
    for info in result.nodes:
        node = by_fingerprint[info.fingerprint]
        entries.append(
            {
                "fingerprint": info.fingerprint,
                "tag": info.tag,
                "role": info.role,
                "name": node.name,
                "source": node.source,
                "address": node.address,
                "port": node.port,
                "updated": now,
            }
        )
    members = sum(1 for info in result.nodes if info.role == "proxy")
    try:
        store = Store(paths.db_file)
        try:
            store.replace_nodes(entries)
            store.prune_scans({info.probe_tag for info in result.nodes})
            store.set_meta("quota", json.dumps(quotas, ensure_ascii=False))
            store.set_meta("nodes_summary", json.dumps(summary(assembly)))
            if record_event:
                store.add_event(
                    "generate", f"участников: {members}, запасных: {len(entries) - members}"
                )
        finally:
            store.close()
    except Exception as exc:  # состояние не критично для генерации
        log.get_logger("engine").error("не удалось записать состояние: %s", exc)


# --- доступ к работающему ядру -------------------------------------------------


def make_api(cfg: config.Config, xray_bin: Path) -> ApiClient:
    return ApiClient(xray_bin, server=f"127.0.0.1:{cfg.xray.api_port}")


def make_service(paths: Paths, xray_bin: Path | None) -> XrayService:
    """systemd-юнит xgw-xray.service; там, где юнита нет (стенд до этапа 4 —
    XGW_XRAY_SERVICE=process — и Windows), — обычный процесс с pid-файлом."""
    if os.environ.get("XGW_XRAY_SERVICE") == "process" or os.name == "nt":
        return PidfileXrayService(
            xray_bin or paths.xray_bin, paths.xray_config_file, paths.run / "xray.pid"
        )
    return SystemdXrayService()


def make_applier(cfg: config.Config, paths: Paths, xray_bin: Path) -> Applier:
    return Applier(
        cfg, paths, make_api(cfg, xray_bin), make_service(paths, xray_bin), xray_bin=xray_bin
    )


def describe(outcome: ApplyOutcome) -> str:
    """Итог применения одной строкой — для лога и вывода команд."""
    text = {
        "api": "применено через API без перезапуска",
        "restart": "применено с перезапуском Xray",
        "restart_deferred": "нужен перезапуск Xray — отложен",
        "unchanged": "изменений нет",
        "rejected": "конфиг отклонён, Xray работает на прежнем",
        "rollback": "Xray не поднялся с новым конфигом — выполнен откат на last-good",
        "failed": "Xray не поднялся, откат на last-good не помог",
    }.get(outcome.mode, outcome.mode)
    if outcome.ops:
        text += ": " + "; ".join(outcome.ops)
    if outcome.detail:
        text += f" ({outcome.detail})"
    return text
