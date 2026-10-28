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
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from . import config, cost, fetch, log, marknet, masking, rating
from . import pin as pinning
from .apply import singbox as singbox_apply
from .apply.applier import Applier, ApplyOutcome
from .generator import builder, validate
from .generator import profiles as profiling
from .generator import singbox as singboxing
from .model import ServerNode, raw_to_node, split_variants
from .net import lan, nft
from .parsers.common import ParseError, RawServer, parse_body, parse_links_text
from .paths import Paths, atomic_write_json
from .store import HOST_CHECK_EVERY, HOST_CHECK_RETRY, HostCache, Store, SubscriptionCache
from .watch import target
from .xraycore.api import ApiClient, server_address
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
class SingboxChange:
    """Что сборка требует от sing-box (apply/singbox.py)."""

    config: dict | None  # желаемый конфиг; None — вести через sing-box некого
    reload: bool  # применить сейчас; иначе отложить: через sing-box идёт трафик (перечитывание
    # конфига рвёт его соединения), пока не наступит окно перезапуска или не станет срочно
    bridged: int = 0  # сколько серверов в новом конфиге Xray ведёт sing-box
    verdict: bool | None = None  # итог sing-box check; None — проверка не выполнялась


@dataclass
class Assembly:
    result: builder.BuildResult
    selection: builder.Selection
    verdict: bool | None  # итог xray run -test; None — проверка не выполнялась
    invalid: int = 0  # сколько серверов отброшено: их конфиг установленный Xray не принимает
    singbox: SingboxChange | None = None
    # Настройки ядра, по которым собран конфиг (profiles.core_settings): persist пишет их в
    # базу, следующая сборка по ним отличает выученный обычный sing-box от закреплённого.
    core: dict = field(default_factory=dict)


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


def singbox_available(cfg: config.Config, paths: Paths) -> bool:
    """Можно ли вести серверы через sing-box: он включён настройками и установлен."""
    return cfg.core.mode != "xray" and singboxing.find_binary(None, paths) is not None


def inventory_file(paths: Paths) -> Path:
    return paths.var / "inventory.json"


def save_inventory(paths: Paths, cfg: config.Config, inventory: Inventory) -> None:
    """Список всех серверов подписок — для панели: и тех, что в конфиг не попали.

    В нём только то, что видно и так (имя, протокол, источник); ключей нет.
    """
    servers = []
    served = {node.fingerprint for node in inventory.nodes if node.singbox is not None}
    if not singbox_available(cfg, paths):
        served = set()
    for node in inventory.nodes:
        if node.keep_tag:
            continue  # звенья цепочек — не самостоятельные серверы
        reason = builder.skip_reason(node, cfg, dead=quarantined(), served=served)
        servers.append({
            "fingerprint": node.fingerprint,
            "name": node.name,
            "source": node.source,
            "protocol": node.protocol,
            "core": node.capability,
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
    values = [cfg.status.token]
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
    cancel: threading.Event | None = None,
) -> Inventory:
    """Опрос всех подписок и ручных ссылок.

    via_xray=False — запрашивать только напрямую (внеочередное обновление в
    ALL_DEAD: через мёртвые серверы подписку не получить).
    cancel — демон останавливается: опрос прерывается (fetch.Cancelled) перед следующей
    подпиской, маршрутом и попыткой и посреди ожидания сети. Кэш подписок прерванный
    опрос не трогает, а неполного списка вызывающий не получает.
    """
    remote = any(sub.url and not sub.url.startswith("file://") for sub in cfg.subscriptions)
    proxy = healthy_http_in(cfg) if via_xray and remote else None
    cache = SubscriptionCache(paths.cache_dir)
    hosts = HostCache(paths.cache_dir)
    inventory = Inventory()
    for sub in cfg.subscriptions:
        if not sub.url:
            continue
        if cancel is not None and cancel.is_set():
            raise fetch.Cancelled
        raws, userinfo, error = _load_subscription(
            sub, cfg, cache, mark, proxy, logger, cancel, hosts=hosts,
        )
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
    split = split_variants(inventory.nodes)
    if split:
        logger.info("серверов с одним адресом и ключом, но разными путём, SNI или режимом: %d "
                    "— это разные серверы, не дубли", split)
    log.add_secrets(masking.collect_secrets([node.outbound for node in inventory.nodes]))
    return inventory


# Имя сервера подписки → когда (time.time()) его прямой адрес не удалось проверить: следующая
# попытка — не раньше HOST_CHECK_RETRY (в памяти процесса; новый демон пробует сразу).
_direct_failed: dict[str, float] = {}


def _check_direct(
    url: str,
    result: fetch.FetchResult,
    cfg: config.Config,
    hosts: HostCache,
    mark: int,
    label: str,
    logger,
    cancel: threading.Event | None,
) -> None:
    """Прямой адрес сервера подписки — в кэш адресов (store.HostCache), если подписка пришла
    без прямого соединения с ним: через Xray (при живом Xray так всегда, и без этого кэш не
    появился бы никогда — отчёт 0.2.0, дефект 1) или через перенаправление с другого имени.
    Не чаще раза в сутки на имя; без метки (не root) прямой путь не проверить — соединение
    ушло бы в перехват, и такой проверки нет вовсе."""
    now = time.time()
    names: list[tuple[str, int]] = []
    for address in (url, result.url):
        parts = urlsplit(address)
        host = parts.hostname or ""
        if parts.scheme != "https" or not host or _is_ip(host):
            continue
        if host == result.host and result.address:
            continue  # только что подтверждён прямым запросом
        if (host, parts.port or 443) not in names:
            names.append((host, parts.port or 443))
    for host, port in names:
        age = hosts.age(host)
        if age is not None and age < HOST_CHECK_EVERY:
            continue
        if now - _direct_failed.get(host, -HOST_CHECK_RETRY) < HOST_CHECK_RETRY:
            continue
        try:
            address = fetch.check_direct(
                host, port, bootstrap=cfg.dns.resolvers, mark=mark, cancel=cancel)
        except fetch.Cancelled:
            raise
        except (fetch.ResolveError, OSError, ValueError) as exc:
            _direct_failed[host] = now
            logger.warning(
                "подписка %s: прямой путь к её серверу не проверен (%s) — если Xray перестанет "
                "отвечать, а шифрованные резолверы будут недоступны, подписку напрямую получить "
                "не удастся; следующая проверка — через %d ч",
                label, masking.mask_text(str(exc))[:200], int(HOST_CHECK_RETRY // 3600),
            )
            continue
        _direct_failed.pop(host, None)
        try:
            hosts.remember(host, address)
        except OSError as exc:
            logger.error("подписка %s: адрес не записан в %s: %s", label, hosts.path, exc)
            continue
        logger.info(
            "подписка %s: прямой адрес её сервера проверен (TLS) и записан в кэш адресов",
            label,
        )


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _drop_junk(raws: list[RawServer]) -> list[RawServer]:
    """Без служебных адресов (0.0.0.0, loopback, порт вне диапазона).

    Провайдеры отмечают заглушку («Приложение не поддерживается!») сервером
    0.0.0.0:1: без отсева такой ответ выглядит удачным и затирает кэш."""
    return [raw for raw in raws if not builder.is_junk(raw.address, raw.port)]


def _load_subscription(
    sub: config.Subscription,
    cfg: config.Config,
    cache: SubscriptionCache,
    mark: int | None,
    proxy: tuple[str, int] | None,
    logger,
    cancel: threading.Event | None = None,
    *,
    hosts: HostCache | None = None,
) -> tuple[list[RawServer], dict[str, int], str]:
    """Серверы подписки, её квота и причина сбоя (пустая, если запрос удался).
    Ответ без серверов считается сбоем — в том числе заглушка из одних служебных
    адресов: тогда берётся последняя удачная версия из кэша, а кэш не перезаписывается.

    hosts — адреса доменов подписок (store.HostCache): прямой запрос, не дождавшийся
    шифрованных резолверов, идёт по прежнему проверенному адресу, а удачный — записывает
    свой адрес туда."""
    label = f"{sub.name} ({masking.mask_url(sub.url)})"
    error = ""
    routes: list[tuple[str, tuple[str, int] | None]] = [("напрямую", None)]
    if proxy is not None and not sub.url.startswith("file://"):
        routes.insert(0, ("через Xray", proxy))
    for route, via in routes:
        if cancel is not None and cancel.is_set():
            raise fetch.Cancelled
        try:
            result = fetch.fetch_subscription(
                sub.url, user_agent=sub.user_agent, headers=sub.headers, proxy=via,
                # Напрямую — меткой мимо перехвата и со своим резолвером: системный
                # DNS при упавшем Xray не отвечает. Через Xray хватит одного повтора:
                # если серверы мертвы, быстрее перейти к прямому запросу.
                mark=None if via else mark,
                bootstrap=None if via or mark is None else cfg.dns.resolvers,
                retries=1 if via else 3,
                cancel=cancel,
                fallback=hosts.addresses() if hosts is not None and via is None else None,
            )
            raws, meta, sub_warnings = parse_body(result.body, sub.name)
            raws = _drop_junk(raws)
            if not raws:
                raise ParseError("в ответе нет серверов")
        except (fetch.FetchError, ParseError) as exc:
            logger.error("подписка %s, запрос %s: %s", label, route, exc)
            error = masking.mask_text(str(exc))[:300]
            continue
        if result.from_fallback:
            logger.warning(
                "подписка %s: резолверы не ответили — получена по прежнему адресу %s",
                label, result.address,
            )
        # Только https: по http ни сертификата, ни подлинности ответа нет — адрес, с которого
        # пришёл ответ, ничем не подтверждён (пятый аудит, D3).
        if hosts is not None and result.host and result.address and urlsplit(
                result.url).scheme == "https":
            try:
                if hosts.remember(result.host, result.address):
                    # Новый адрес (или имя) — одна строка; тот же адрес каждый час — молча.
                    logger.info(
                        "подписка %s: получена напрямую, адрес её сервера записан в кэш адресов",
                        label,
                    )
            except OSError as exc:
                logger.error("подписка %s: адрес не записан в %s: %s", label, hosts.path, exc)
        if hosts is not None and mark is not None:
            _check_direct(sub.url, result, cfg, hosts, mark, label, logger, cancel)
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
    raws = _drop_junk(raws)
    if not raws:
        logger.error("подписка %s: в кэше только служебные адреса", label)
        return [], {}, error
    age_min = max(0, int((time.time() - cached.saved_at) // 60)) if cached.saved_at else 0
    logger.warning(
        "подписка %s: используется кэш (%d серверов, сохранён %d мин назад)",
        label, len(raws), age_min,
    )
    return raws, cached.userinfo, error


def containers_tun(cfg: config.Config) -> bool:
    """Нужен ли в конфиге Xray inbound TUN для контейнеров Docker: их перехват включён, и
    Docker на машине есть (его мост уже создан). Без Docker интерфейса TUN не будет вовсе."""
    return nft.containers_wanted(cfg) and bool(lan.container_links(nft.CONTAINER_IFS))


def devices_down(paths: Paths) -> frozenset[str]:
    """Адреса устройств, чей свой сервер сейчас не отвечает (Daemon._device_step): их ведёт
    основной. Файла нет или он битый — таких нет."""
    loaded = read_json(paths.devices_down_file) or {}
    ips = loaded.get("ips")
    return frozenset(str(ip) for ip in ips) if isinstance(ips, list) else frozenset()


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
    scores: dict[str, float] | None = None,
    reserve: str | None = None,
    fragment: set[str] | None = None,
    profiles: dict[str, str] | None = None,
    singbox_ok: bool | None = None,
    reload_singbox: bool | None = None,
) -> Assembly:
    """Конфиг Xray и конфиг sing-box из известных серверов.

    Состав участников, резервный выход, порты и пароль проб берутся из применённого
    конфига: обновление подписки не должно перетасовывать то, что уже работает в ядре.
    prefer — явный состав участников (замена «мёртвого» при ротации).
    scores — рейтинг серверов (rating.py); по умолчанию — последний, что записал демон
    (meta «rating», load_scores): обновление подписки и `xgw generate` отбирают участников
    так же, как демон.
    reserve — отпечаток резервного выхода (его выбирает демон по дешёвой проверке).
    profiles — решения демона о профилях обхода (generator/profiles.py): отпечаток →
    профиль. У остальных серверов профиль — как в применённом конфиге, если сервер обучен
    блокировкой (дробление, sing-box; обычный sing-box у сервера с базой Xray — если его ядро
    в настройках не менялось с прошлой сборки), иначе по настройкам. fragment — то же для дробления
    ClientHello (xray:fragment) в прежней записи: набор отпечатков.
    singbox_ok — доступен ли sing-box (по умолчанию: включён в [core] и установлен).
    reload_singbox — перечитать ли конфиг sing-box сейчас. Перечитывание рвёт все
    соединения через sing-box, поэтому по умолчанию (None) оно сейчас, только если через
    него никто не идёт; иначе конфиг откладывается (SingboxChange.reload = False), а Xray
    собирается по тому, что sing-box уже ведёт.
    Сервер, конфиг которого установленный Xray или sing-box не принимает, отбрасывается.
    """
    applied = read_json(paths.xray_config_file)
    applied_sb = read_json(paths.singbox_config_file)
    probe_password, probe_ports = builder.probe_state(applied)
    prices = node_costs(cfg, inventory)
    if prefer is None:
        prefer = builder.member_fingerprints(applied, inventory.nodes)
    if scores is None:
        scores = load_scores(paths)
    low = low_quota(inventory)
    if reserve is None:
        reserve = builder.reserve_fingerprint(applied, inventory.nodes)
    current = builder.applied_profiles(applied, inventory.nodes)
    saved_core = _saved_core(paths)
    decided = dict(profiles or {})
    for fingerprint in fragment or ():
        decided.setdefault(fingerprint, profiling.XRAY_FRAGMENT)

    enabled = singbox_available(cfg, paths) if singbox_ok is None else (
        singbox_ok and cfg.core.mode != "xray"
    )
    sb_bin = singboxing.find_binary(None, paths) if check and enabled else None
    applied_ports = singboxing.bridge_ports(applied_sb)
    carried = _carrying_tags(paths, applied)
    bridged_now = any(
        singboxing.bridge_variant(outbound)
        for outbound in (applied or {}).get("outbounds") or []
        if isinstance(outbound, dict) and outbound.get("tag") in carried
    )
    reload_now = (not bridged_now) if reload_singbox is None else reload_singbox
    if not enabled:
        served: set[str] = set()
    elif reload_now:
        served = {node.fingerprint for node in inventory.nodes if node.singbox is not None}
    else:
        served = {fingerprint for fingerprint, _letter in applied_ports}

    rejected: set[str] = set()
    nosb: set[str] = set()
    dead = quarantined()
    first = True
    while True:
        usable = [node for node in inventory.nodes if node.fingerprint not in rejected]
        selection = builder.select_nodes(
            usable, cfg, prefer=prefer, dead=dead, scores=scores, costs=prices,
            reserve=reserve, served=served, quota_low=low,
        )
        if first:
            first = False
            for warning in selection.warnings:
                logger.warning("%s", warning)
            if selection.stats.get("core"):
                logger.warning(
                    "серверов, которые умеет только sing-box, отложено: %d — %s",
                    selection.stats["core"],
                    "sing-box выключен или не установлен" if not enabled
                    else "они ещё не заведены в работающий sing-box",
                )
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
        ordered = [*selection.members, *selection.spares]
        plan = None
        if enabled:
            try:
                plan = singboxing.build(
                    cfg, ordered, hosts, previous=applied_sb, skip=nosb,
                    avoid=set(probe_ports.values()),
                )
            except ValueError as exc:
                raise EngineError(str(exc)) from exc
        # Xray ссылается только на то, что sing-box уже ведёт: пока новый конфиг отложен, это
        # варианты из работающего sing-box.
        effective = None
        if plan is not None and reload_now:
            effective = plan
        elif plan is not None and applied_ports:
            effective = singboxing.Plan(
                config=applied_sb or {}, ports=applied_ports,
                password=singboxing.bridge_password(applied_sb),
            )
        profile_of = {
            node.fingerprint: profiling.resolve(
                node, cfg, effective.letters(node.fingerprint) if effective else (),
                current=current.get(node.fingerprint), override=decided.get(node.fingerprint),
                same_pin=profiling.pin_unchanged(cfg, saved_core, node.fingerprint),
            )
            for node in ordered
        }
        try:
            result = builder.build(
                cfg, selection, hosts=hosts,
                probe_password=probe_password, probe_ports=probe_ports,
                probe_url=target.observatory_url(cfg, paths),
                containers_tun=containers_tun(cfg),
                profile_of=profile_of, bridge=effective,
                devices_down=devices_down(paths),
                # Входы sing-box — и работающего, и новой сборки, если её перезапуск отложен.
                avoid_ports={*(plan.ports.values() if plan is not None else ()),
                             *(applied_ports or {}).values()},
                api_listen=str(paths.xray_api_socket),
            )
        except builder.BuildError as exc:
            raise EngineError(str(exc)) from exc
        change = SingboxChange(
            config=plan.config if plan is not None else None, reload=reload_now,
            bridged=sum(
                1 for info in result.nodes if profiling.core_of(info.profile) == "sing-box"
            ),
        )
        core = profiling.core_settings(cfg)
        if not check:
            return Assembly(result, selection, None, len(rejected), change, core)
        if plan is not None and sb_bin is not None:
            change.verdict, sb_output = singboxing.validate_config(plan.config, sb_bin)
            if change.verdict is False:
                # Конфиг sing-box не прошёл: ищем серверы, которые он не принимает, и
                # собираем без них. Умеющие Xray остаются в нём, остальные отбрасываются.
                bad = singboxing.find_invalid(ordered, cfg, sb_bin)
                newly_bad = set(bad) - nosb - rejected
                if not newly_bad:
                    raise EngineError(f"конфиг не прошёл sing-box check:\n{sb_output}")
                by_fingerprint = {node.fingerprint: node for node in ordered}
                for fingerprint in newly_bad:
                    logger.warning(
                        "узел %s отброшен: sing-box не принимает его конфиг (%s)",
                        by_fingerprint[fingerprint].name, bad[fingerprint],
                    )
                    if by_fingerprint[fingerprint].outbound:
                        nosb.add(fingerprint)
                    else:
                        rejected.add(fingerprint)
                continue
        verdict, output = validate.validate_config(result.config, xray_bin)
        if verdict is not False:
            return Assembly(result, selection, verdict, len(rejected), change, core)
        # Конфиг не прошёл: ищем серверы, которые установленный Xray не принимает
        # (снятый транспорт, неизвестный шифр), и собираем конфиг без них.
        newly = _reject_invalid(result, xray_bin, logger) - rejected
        if not newly:
            raise EngineError(f"конфиг не прошёл xray run -test:\n{output}")
        rejected |= newly


def _carrying_tags(paths: Paths, applied: dict | None) -> set[str]:
    """Теги серверов, через которые сейчас идёт настоящий трафик: участники балансировщика,
    резервный выход и выбранный вручную сервер. Запасные его не несут (только короткие пробы),
    поэтому перечитывание sing-box им не мешает."""
    tags = {
        str(outbound.get("tag")) for outbound in (applied or {}).get("outbounds") or []
        if isinstance(outbound, dict) and str(outbound.get("tag", "")).startswith("proxy-")
    }
    tags.add(builder.reserve_tag(applied))
    try:
        store = Store(paths.db_file)
        try:
            chosen = pinning.read(store.get_meta(pinning.META), time.time())
        finally:
            store.close()
    except Exception:  # базы нет или она не читается — выбор вручную неизвестен
        chosen = None
    if chosen:
        # Роль в теге меняется (запасной стал участником), страна и отпечаток — нет.
        tags.update(
            str(outbound.get("tag")) for outbound in (applied or {}).get("outbounds") or []
            if isinstance(outbound, dict)
            and pinning.same_server(str(outbound.get("tag") or ""), str(chosen.get("tag") or ""))
        )
    return {tag for tag in tags if tag}


def _saved_core(paths: Paths) -> dict | None:
    """Настройки ядра, по которым собран применённый конфиг (persist); None — их нет."""
    try:
        store = Store(paths.db_file)
        try:
            raw = store.get_meta(profiling.CORE_META)
        finally:
            store.close()
    except Exception:  # базы нет или она не читается — считаем, что настройки сменились
        return None
    try:
        saved = json.loads(raw) if raw else None
    except ValueError:
        return None
    return saved if isinstance(saved, dict) else None


RATING_META = "rating"  # рейтинг серверов (rating.py): отпечаток → число; пишет демон


def load_scores(paths: Paths) -> dict[str, float]:
    """Последний рейтинг серверов, что записал демон; базы нет — пусто (тогда рейтинг —
    по приоритету и стоимости, rating.static)."""
    if not paths.db_file.exists():
        return {}
    try:
        store = Store(paths.db_file)
    except Exception:  # без базы рейтинг — по приоритету и стоимости (rating.static)
        return {}
    try:
        loaded = json.loads(store.get_meta(RATING_META) or "{}")
    except ValueError:
        return {}
    finally:
        store.close()
    if not isinstance(loaded, dict):
        return {}
    return {str(key): float(value) for key, value in loaded.items()
            if isinstance(value, (int, float))}


def low_quota(inventory: Inventory) -> set[str]:
    """Отпечатки серверов подписок, чья квота на исходе (rating.quota_low)."""
    low = {name for name, quota in inventory.quotas.items() if rating.quota_low(quota)}
    return {node.fingerprint for node in inventory.nodes if node.source in low}


def node_costs(cfg: config.Config, inventory: Inventory) -> dict[str, float]:
    """Стоимость серверов: 0 — безлимитная подписка, иначе множитель из имени (cost.py)."""
    return cost.costs(inventory.nodes, inventory.quotas, cfg.filters.multiplier_regex)


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
            ips = resolve_domain(node.address, cfg.dns.resolvers, mark)
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
        "dropped": sum(stats.get(key, 0) for key in ("junk", "ipv6", "filter", "dns", "core"))
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
    applied: bool = True,
) -> None:
    """Записывает в SQLite состав узлов последней сборки и квоты подписок. applied — конфиг
    стал рабочим: тогда и снимок настроек ядра, по которым он собран (`xgw generate` пишет
    конфиг в отдельный файл — снимок у него не пишется)."""
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
            if applied and assembly.core:
                store.set_meta(profiling.CORE_META, json.dumps(assembly.core))
            if record_event:
                store.add_event(
                    "generate", f"участников: {members}, запасных: {len(entries) - members}"
                )
        finally:
            store.close()
    except Exception as exc:  # состояние не критично для генерации
        log.get_logger("engine").error("не удалось записать состояние: %s", exc)


# --- доступ к работающему ядру -------------------------------------------------


def make_api(paths: Paths, xray_bin: Path) -> ApiClient:
    """Клиент API Xray: адрес — из применённого конфига (ApiClient.address), до первого конфига —
    сокет paths.xray_api_socket."""
    return ApiClient(
        xray_bin, server=server_address(str(paths.xray_api_socket)),
        config_file=paths.xray_config_file,
    )


def make_service(paths: Paths, xray_bin: Path | None) -> XrayService:
    """systemd-юнит xgw-xray.service; там, где юнита нет (стенд до этапа 4 —
    XGW_XRAY_SERVICE=process), — обычный процесс с pid-файлом."""
    if os.environ.get("XGW_XRAY_SERVICE") == "process":
        return PidfileXrayService(
            xray_bin or paths.xray_bin, paths.xray_config_file, paths.run / "xray.pid"
        )
    return SystemdXrayService()


def make_applier(cfg: config.Config, paths: Paths, xray_bin: Path) -> Applier:
    return Applier(
        cfg, paths, make_api(paths, xray_bin), make_service(paths, xray_bin), xray_bin=xray_bin
    )


def make_singbox(cfg: config.Config, paths: Paths) -> singbox_apply.SingboxCore:
    """Применение и слежение за sing-box (второе ядро, apply/singbox.py)."""
    bin_path = singboxing.find_binary(None, paths)
    return singbox_apply.SingboxCore(
        cfg, paths, singbox_apply.make_service(paths, bin_path), bin_path=bin_path,
    )


def describe_singbox(outcome: singbox_apply.SingboxOutcome) -> str:
    """Итог применения конфига sing-box одной строкой — для вывода команд."""
    text = {
        "unchanged": "sing-box: изменений нет",
        "deferred": "sing-box: перечитывание отложено — через него идёт трафик, и оно оборвало "
                    "бы соединения (применить сейчас: xgw apply --now)",
        "started": "sing-box запущен",
        "reloaded": "конфиг sing-box перечитан",
        "removed": "sing-box остановлен: серверов для него нет",
        "rejected": "конфиг sing-box отклонён, sing-box работает на прежнем",
        "rollback": "sing-box не принял новый конфиг — выполнен откат на last-good",
        "failed": "sing-box не поднялся, откат на last-good не помог",
    }.get(outcome.mode, outcome.mode)
    if outcome.detail and outcome.mode not in ("unchanged", "deferred"):
        text += f" ({outcome.detail})"
    return text


def apply_all(
    cfg: config.Config, paths: Paths, assembly: Assembly, applier: Applier, *,
    force_now: bool = False,
) -> tuple[ApplyOutcome | None, singbox_apply.SingboxOutcome | None]:
    """Применяет сборку: сначала sing-box (мосты должны слушать), затем Xray. Если sing-box
    конфиг не принял, Xray не применяется (он собран под него): вернётся только итог sing-box."""
    outcome = None
    if assembly.singbox is not None:
        outcome = make_singbox(cfg, paths).apply(
            assembly.singbox.config, reload=assembly.singbox.reload,
        )
        if outcome.mode in ("rejected", "rollback", "failed"):
            return None, outcome
    return applier.apply(assembly.result.config, force_now=force_now), outcome


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
