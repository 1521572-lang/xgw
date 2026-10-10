"""CLI xgw. Этап 1: generate — подписки/ссылки → конфиг Xray + xray run -test.

Остальные команды добавляются на этапах 2–4 (apply, enable/disable, status,
probe, pin, diag, update-xray, logs, install/uninstall).
"""

from __future__ import annotations

import argparse
import contextlib
import ipaddress
import json
import os
import sys
from pathlib import Path

from . import __version__, config, fetch, log, marknet, masking
from .generator import builder, validate
from .model import raw_to_node
from .parsers.common import ParseError, parse_body, parse_links_text
from .paths import Paths
from .store import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="xgw", description="XGW — шлюз на Xray-core для Ubuntu 26.04"
    )
    parser.add_argument("--version", action="version", version=f"xgw {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="собрать конфиг Xray из подписок и ссылок")
    generate.add_argument("--config", default=None, help="путь к config.toml")
    generate.add_argument("--out", default=None, help="куда записать конфиг Xray")
    generate.add_argument("--no-validate", action="store_true", help="без xray run -test")
    generate.add_argument("--print", action="store_true", help="напечатать конфиг в stdout")

    args = parser.parse_args(argv)
    log.setup()
    if args.command == "generate":
        return _cmd_generate(args)
    parser.error(f"команда {args.command} ещё не реализована (этапы 2–4)")


def _cmd_generate(args: argparse.Namespace) -> int:
    paths = Paths.from_env()
    config_path = Path(args.config) if args.config else paths.config_file
    try:
        cfg, warnings = config.load(config_path)
    except config.ConfigError as exc:
        print(f"ошибка: {exc}", file=sys.stderr)
        return 2
    logger = log.get_logger("generate")
    for warning in warnings:
        logger.warning("%s", warning)

    mark = cfg.capture.mark_bypass if marknet.is_mark_supported() else None
    nodes = []
    for sub in cfg.subscriptions:
        try:
            result = fetch.fetch_subscription(
                sub.url, user_agent=sub.user_agent, headers=sub.headers, mark=mark
            )
            raws, _meta, sub_warnings = parse_body(result.body, sub.name)
        except (fetch.FetchError, ParseError) as exc:
            logger.error("подписка %s: %s", masking.mask_url(sub.url), exc)
            continue
        for warning in sub_warnings:
            logger.warning("%s", warning)
        nodes.extend(raw_to_node(raw, sub.name) for raw in raws)
    if cfg.manual.links:
        raws, _meta, manual_warnings = parse_links_text("\n".join(cfg.manual.links), "manual")
        for warning in manual_warnings:
            logger.warning("%s", warning)
        nodes.extend(raw_to_node(raw, "manual") for raw in raws)

    selection = builder.select_nodes(nodes, cfg)
    for warning in selection.warnings:
        logger.warning("%s", warning)
    if not selection.members:
        print("ошибка: после фильтров не осталось серверов", file=sys.stderr)
        return 1

    hosts = _resolve_hosts(selection, cfg, mark, logger)
    result = builder.build(cfg, selection, hosts=hosts)

    if args.no_validate:
        verdict, output = None, ""
    else:
        verdict, output = validate.validate_config(
            result.config, validate.find_xray(None, paths)
        )
        if verdict is False:
            print("конфиг не прошёл xray run -test:", file=sys.stderr)
            print(output, file=sys.stderr)
            return 1

    out_path = Path(args.out) if args.out else paths.xray_config_file
    _atomic_write_json(out_path, result.config)
    _persist(paths, result)

    if args.print:
        print(json.dumps(result.config, ensure_ascii=False, indent=2))
    members = ", ".join(info.tag for info in result.nodes if info.role == "proxy")
    spares = sum(1 for info in result.nodes if info.role == "spare")
    verdict_text = {
        True: "пройдена",
        None: "пропущена (xray не найден)",
        False: "провалена",
    }[verdict]
    summary = (
        f"участники: {members}; запасные: {spares}; цепочки: {len(result.chain_tags)}; "
        f"конфиг: {out_path}; проверка xray run -test: {verdict_text}"
    )
    print(summary)
    return 0


def _resolve_hosts(selection: builder.Selection, cfg: config.Config, mark, logger) -> dict:
    """Домены серверов разрешаются через bootstrap-резолверы и попадают в dns.hosts."""
    hosts: dict[str, list[str]] = {}
    for node in [*selection.members, *selection.spares]:
        if node.address in hosts:
            continue
        try:
            ipaddress.ip_address(node.address)
            continue
        except ValueError:
            pass
        try:
            hosts[node.address] = fetch.resolve_domain(node.address, cfg.dns.bootstrap, mark=mark)
        except fetch.ResolveError as exc:
            logger.warning("домен %s не разрешён: %s", node.address, exc)
    return hosts


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(tmp, 0o640)
    os.replace(tmp, path)


def _persist(paths: Paths, result: builder.BuildResult) -> None:
    try:
        store = Store(paths.db_file)
        store.upsert_nodes(
            [
                {
                    "fingerprint": info.fingerprint,
                    "tag": info.tag,
                    "role": info.role,
                    "name": "",
                    "source": "",
                    "address": "",
                    "port": 0,
                    "updated": 0,
                }
                for info in result.nodes
            ]
        )
        store.add_event("generate", f"участников: {len(result.nodes)}")
        store.close()
    except Exception as exc:  # состояние не критично для генерации
        log.get_logger("generate").error("не удалось записать состояние: %s", exc)


if __name__ == "__main__":
    raise SystemExit(main())
