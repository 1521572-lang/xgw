"""CLI xgw. Этап 1: generate — подписки/ссылки → конфиг Xray + xray run -test.

Остальные команды добавляются на этапах 2–4 (apply, enable/disable, status,
probe, pin, diag, update-xray, logs, install/uninstall).
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import sys
import time
from pathlib import Path

from . import __version__, config, fetch, log, marknet, masking
from .generator import builder, validate
from .model import ServerNode, raw_to_node
from .parsers.common import ParseError, RawServer, parse_body, parse_links_text
from .paths import Paths, atomic_write_json
from .store import Store, SubscriptionCache


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="xgw", description="XGW — шлюз на Xray-core для Ubuntu 26.04"
    )
    parser.add_argument("--version", action="version", version=f"xgw {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="собрать конфиг Xray из подписок и ссылок")
    generate.add_argument("--config", default=None, help="путь к config.toml")
    generate.add_argument(
        "--out",
        default=None,
        help="куда записать конфиг Xray (по умолчанию — config.generated.json рядом с рабочим)",
    )
    generate.add_argument("--no-validate", action="store_true", help="без xray run -test")
    generate.add_argument("--print", action="store_true", help="напечатать конфиг в stdout")

    args = parser.parse_args(argv)
    log.setup()
    return _cmd_generate(args)


def _cmd_generate(args: argparse.Namespace) -> int:
    paths = Paths.from_env()
    config_path = Path(args.config) if args.config else paths.config_file
    try:
        cfg, warnings = config.load(config_path)
    except config.ConfigError as exc:
        print(f"ошибка: {exc}", file=sys.stderr)
        return 2
    logger = log.get_logger("generate")
    log.add_secrets(_config_secrets(cfg))
    for warning in warnings:
        logger.warning("%s", warning)

    mark = _bypass_mark(cfg, logger)
    remote = any(sub.url and not sub.url.startswith("file://") for sub in cfg.subscriptions)
    proxy = _healthy_http_in(cfg) if remote else None
    cache = SubscriptionCache(paths.cache_dir)
    nodes: list[ServerNode] = []
    quotas: dict[str, dict[str, int]] = {}
    for sub in cfg.subscriptions:
        raws, userinfo = _load_subscription(sub, cfg, cache, mark, proxy, logger)
        if userinfo:
            quotas[sub.name] = userinfo
        nodes.extend(raw_to_node(raw, sub.name) for raw in raws)
    if cfg.manual.links:
        raws, _meta, manual_warnings = parse_links_text("\n".join(cfg.manual.links), "manual")
        for warning in manual_warnings:
            logger.warning("%s", warning)
        nodes.extend(raw_to_node(raw, "manual") for raw in raws)
    log.add_secrets(masking.collect_secrets([node.outbound for node in nodes]))

    # Состав участников, порты и пароль проб берём из применённого конфига:
    # обновление подписки не должно перетасовывать то, что уже работает в ядре.
    applied = _read_json(paths.xray_config_file)
    probe_password, probe_ports = builder.probe_state(applied)
    prefer = builder.member_fingerprints(applied, nodes)
    xray_bin = None if args.no_validate else validate.find_xray(None, paths)

    rejected: set[str] = set()
    while True:
        usable = [node for node in nodes if node.fingerprint not in rejected]
        selection = builder.select_nodes(usable, cfg, prefer=prefer)
        if not rejected:
            for warning in selection.warnings:
                logger.warning("%s", warning)
        if not selection.members:
            print("ошибка: после фильтров не осталось серверов", file=sys.stderr)
            return 1
        hosts = _resolve_hosts(selection, cfg, mark, logger)
        try:
            result = builder.build(
                cfg, selection, hosts=hosts,
                probe_password=probe_password, probe_ports=probe_ports,
            )
        except builder.BuildError as exc:
            print(f"ошибка: {exc}", file=sys.stderr)
            return 1
        if args.no_validate:
            verdict: bool | None = None
            break
        verdict, output = validate.validate_config(result.config, xray_bin)
        if verdict is not False:
            break
        # Конфиг не прошёл: ищем серверы, которые установленный Xray не принимает
        # (снятый транспорт, неизвестный шифр), и собираем конфиг без них.
        newly = _reject_invalid(result, xray_bin, logger) - rejected
        if not newly:
            print("конфиг не прошёл xray run -test:", file=sys.stderr)
            print(output, file=sys.stderr)
            return 1
        rejected |= newly

    out_path = Path(args.out) if args.out else paths.generated_config_file
    atomic_write_json(out_path, result.config)
    _persist(paths, result, [*selection.members, *selection.spares], quotas)

    if args.print:
        print(json.dumps(result.config, ensure_ascii=False, indent=2))
    members = ", ".join(info.tag for info in result.nodes if info.role == "proxy")
    spares = sum(1 for info in result.nodes if info.role == "spare")
    if args.no_validate:
        verdict_text = "не запускалась (--no-validate)"
    else:
        verdict_text = "пройдена" if verdict else "пропущена (xray не найден)"
    summary = (
        f"участники: {members}; запасные: {spares}; цепочки: {len(result.chain_tags)}; "
        f"конфиг: {out_path}; проверка xray run -test: {verdict_text}"
    )
    print(summary)
    return 0


def _config_secrets(cfg: config.Config) -> list[str]:
    """Секреты из config.toml, которые регулярками не распознать."""
    values = [cfg.notify.telegram_bot_token, cfg.status.token]
    for sub in cfg.subscriptions:
        values.extend(sub.headers.values())
    return [value for value in values if value]


def _bypass_mark(cfg: config.Config, logger) -> int | None:
    """Метка для прямых запросов. Без CAP_NET_ADMIN (запуск не от root) SO_MARK
    недоступен — работаем без метки и предупреждаем: при включённом перехвате
    такие запросы пойдут через Xray."""
    if not marknet.is_mark_supported():
        return None
    if marknet.mark_usable(cfg.capture.mark_bypass):
        return cfg.capture.mark_bypass
    logger.warning("нет прав на SO_MARK (нужен root) — прямые запросы идут без метки")
    return None


def _healthy_http_in(cfg: config.Config) -> tuple[str, int] | None:
    """http-in работающего Xray: при здоровом ядре подписка запрашивается через него."""
    address = ("127.0.0.1", cfg.xray.http_port)
    try:
        with socket.create_connection(address, timeout=1.0):
            return address
    except OSError:
        return None


def _load_subscription(
    sub: config.Subscription,
    cfg: config.Config,
    cache: SubscriptionCache,
    mark: int | None,
    proxy: tuple[str, int] | None,
    logger,
) -> tuple[list[RawServer], dict[str, int]]:
    """Серверы подписки и её квота. Ответ без серверов считается сбоем: тогда
    берётся последняя удачная версия из кэша, а кэш не перезаписывается."""
    label = f"{sub.name} ({masking.mask_url(sub.url)})"
    if not sub.url:
        return [], {}
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
        return raws, userinfo

    cached = cache.load(sub.name)
    if cached is None:
        logger.error("подписка %s: получить не удалось, кэша нет", label)
        return [], {}
    try:
        raws, _meta, _warnings = parse_body(cached.body, sub.name)
    except ParseError as exc:
        logger.error("подписка %s: кэш не читается: %s", label, exc)
        return [], {}
    age_min = max(0, int((time.time() - cached.saved_at) // 60)) if cached.saved_at else 0
    logger.warning(
        "подписка %s: используется кэш (%d серверов, сохранён %d мин назад)",
        label, len(raws), age_min,
    )
    return raws, cached.userinfo


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


def _resolve_hosts(selection: builder.Selection, cfg: config.Config, mark, logger) -> dict:
    """Домены серверов разрешаются через bootstrap-резолверы и попадают в dns.hosts."""
    hosts: dict[str, list[str]] = {}
    failed: set[str] = set()
    for node in [*selection.members, *selection.spares, *selection.chains]:
        if not node.address or node.address in hosts or node.address in failed:
            continue
        try:
            ipaddress.ip_address(node.address)
            continue
        except ValueError:
            pass
        try:
            hosts[node.address] = fetch.resolve_domain(node.address, cfg.dns.bootstrap, mark=mark)
        except fetch.ResolveError as exc:
            failed.add(node.address)
            logger.warning("домен %s не разрешён: %s", node.address, exc)
    return hosts


def _read_json(path: Path) -> dict | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _persist(
    paths: Paths,
    result: builder.BuildResult,
    nodes: list[ServerNode],
    quotas: dict[str, dict[str, int]],
) -> None:
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
            store.set_meta("quota", json.dumps(quotas, ensure_ascii=False))
            store.add_event(
                "generate", f"участников: {members}, запасных: {len(entries) - members}"
            )
        finally:
            store.close()
    except Exception as exc:  # состояние не критично для генерации
        log.get_logger("generate").error("не удалось записать состояние: %s", exc)


if __name__ == "__main__":
    raise SystemExit(main())
