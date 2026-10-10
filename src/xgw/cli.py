"""CLI xgw.

Этап 1: generate — подписки/ссылки → конфиг Xray + xray run -test.
Этап 2: apply, status, servers, probe, pin/unpin и run (демон xgw.service).
Этап 3: enable, disable и net — перехват трафика (nftables, ip rule).
Этап 4: install, uninstall, diag, update-xray и logs — установка на машину.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import os
import shutil
import signal
import sqlite3
import sys
import threading
import time
from pathlib import Path

from . import __version__, config, engine, log
from .generator import builder, validate
from .generator.builder import BALANCER_TAG
from .net import cmd, dnsmasq, nft
from .net.capture import Capture, CaptureError
from .paths import LockTimeout, Paths, atomic_write_json
from .store import Store
from .watch import scan, status
from .xraycore import binary, metrics
from .xraycore.api import ApiError

MAX_PIN_SECONDS = 24 * 3600
# Команды, которые работают и без читаемого config.toml.
NO_CONFIG = frozenset({"install", "uninstall", "diag", "logs"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="xgw", description="XGW — шлюз на Xray-core для Ubuntu 26.04"
    )
    parser.add_argument("--version", action="version", version=f"xgw {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=None, help="путь к config.toml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser(
        "generate", parents=[common], help="собрать конфиг Xray из подписок и ссылок"
    )
    generate.add_argument(
        "--out",
        default=None,
        help="куда записать конфиг Xray (по умолчанию — config.generated.json рядом с рабочим)",
    )
    generate.add_argument("--no-validate", action="store_true", help="без xray run -test")
    generate.add_argument("--print", action="store_true", help="напечатать конфиг в stdout")

    apply = subparsers.add_parser(
        "apply", parents=[common], help="обновить подписки и применить изменения"
    )
    apply.add_argument(
        "--now", action="store_true",
        help="если нужен перезапуск Xray — выполнить сразу, не дожидаясь restart_window",
    )

    for name, text in (("status", "состояние шлюза"), ("servers", "участники и запасные")):
        sub = subparsers.add_parser(name, parents=[common], help=text)
        sub.add_argument("--json", action="store_true", help="вывести JSON")

    probe = subparsers.add_parser(
        "probe", parents=[common], help="проверить серверы загрузкой через probe-inbounds"
    )
    probe.add_argument("tag", nargs="?", help="тег узла (proxy-…, spare-…); без тега — все")
    probe.add_argument("--all", action="store_true", help="все участники и запасные")

    pin = subparsers.add_parser(
        "pin", parents=[common], help="закрепить узел вручную на ограниченный срок"
    )
    pin.add_argument("tag", help="тег участника (proxy-…)")
    pin.add_argument("--ttl", default="10m", help="срок: 30s, 10m, 2h (по умолчанию 10m)")
    subparsers.add_parser("unpin", parents=[common], help="снять ручное закрепление")

    subparsers.add_parser(
        "enable", parents=[common], help="включить перехват: трафик идёт через Xray"
    )
    subparsers.add_parser(
        "disable", parents=[common], help="снять перехват: сеть работает напрямую"
    )
    net = subparsers.add_parser(
        "net", parents=[common],
        help="правила сети: загрузить (up, служба xgw-net), убрать (down), показать (show)",
    )
    net.add_argument("action", choices=("up", "down", "show"))
    net.add_argument(
        "what", nargs="?", choices=("nft", "dnsmasq"), default="nft",
        help="что показать: правила nftables (по умолчанию) или конфиг dnsmasq",
    )

    run = subparsers.add_parser("run", parents=[common], help="демон XGW (служба xgw.service)")
    run.add_argument("--once", action="store_true", help="выполнить один шаг watchdog и выйти")

    install = subparsers.add_parser(
        "install", parents=[common],
        help="установить XGW на эту машину: службы, сеть, Xray (покажет план и спросит)",
    )
    install.add_argument("-y", "--yes", action="store_true", help="не спрашивать подтверждения")
    install.add_argument(
        "--force", action="store_true", help="продолжить, даже если проверки дали FAIL"
    )
    uninstall = subparsers.add_parser(
        "uninstall", parents=[common], help="удалить XGW и вернуть сеть в исходное состояние"
    )
    uninstall.add_argument("-y", "--yes", action="store_true", help="не спрашивать подтверждения")
    uninstall.add_argument(
        "--purge", action="store_true", help="удалить и /etc/xgw вместе с config.toml"
    )
    diag = subparsers.add_parser(
        "diag", parents=[common], help="проверить машину: OK, WARN или FAIL с советом"
    )
    diag.add_argument("--json", action="store_true", help="вывести JSON")
    diag.add_argument(
        "--no-net", action="store_true", help="без запросов наружу (probe.url, bootstrap DNS)"
    )
    subparsers.add_parser(
        "update-xray", parents=[common],
        help="обновить Xray с проверкой SHA-256 и xray run -test",
    )
    logs = subparsers.add_parser("logs", parents=[common], help="журнал служб XGW")
    logs.add_argument("-n", "--lines", type=int, default=200, help="сколько строк показать")
    logs.add_argument("-f", "--follow", action="store_true", help="следить за журналом")
    logs.add_argument("--export", action="store_true", help="собрать архив без секретов")
    logs.add_argument("--out", default=None, help="куда записать архив (с --export)")

    args = parser.parse_args(argv)
    log.setup()
    paths = Paths.from_env()
    config_path = Path(args.config) if args.config else paths.config_file
    args.config_path, args.config_error = config_path, ""
    try:
        cfg, warnings = config.load(config_path)
    except config.ConfigError as exc:
        if args.command not in NO_CONFIG:
            print(f"ошибка: {exc}", file=sys.stderr)
            return 2
        cfg, warnings, args.config_error = config.Config(), [], str(exc)
    args.config_warnings = warnings
    logger = log.get_logger(args.command)
    log.add_secrets(engine.config_secrets(cfg))
    if args.command != "diag":  # diag показывает их сам, среди проверок
        for warning in warnings:
            logger.warning("%s", warning)

    handler = {
        "generate": _cmd_generate,
        "apply": _cmd_apply,
        "status": _cmd_status,
        "servers": _cmd_status,
        "probe": _cmd_probe,
        "pin": _cmd_pin,
        "unpin": _cmd_unpin,
        "enable": _cmd_enable,
        "disable": _cmd_disable,
        "net": _cmd_net,
        "run": _cmd_run,
        "install": _cmd_install,
        "uninstall": _cmd_uninstall,
        "diag": _cmd_diag,
        "update-xray": _cmd_update_xray,
        "logs": _cmd_logs,
    }[args.command]
    try:
        return handler(args, cfg, paths, logger)
    except LockTimeout as exc:
        print(f"ошибка: {exc} — идёт другое применение конфига", file=sys.stderr)
        return 1


def _fail(message: str, code: int = 1) -> int:
    print(f"ошибка: {message}", file=sys.stderr)
    return code


def _require_xray(paths: Paths) -> Path | None:
    xray_bin = validate.find_xray(None, paths)
    if xray_bin is None:
        _fail(f"xray не найден (ожидается {paths.xray_bin} либо XGW_XRAY_BIN)")
    return xray_bin


# --- generate / apply ----------------------------------------------------------


def _cmd_generate(args, cfg: config.Config, paths: Paths, logger) -> int:
    mark = engine.bypass_mark(cfg, logger)
    inventory = engine.collect(cfg, paths, mark=mark, logger=logger)
    xray_bin = None if args.no_validate else validate.find_xray(None, paths)
    try:
        assembly = engine.assemble(
            cfg, paths, inventory, mark=mark, logger=logger,
            xray_bin=xray_bin, check=not args.no_validate,
        )
    except engine.EngineError as exc:
        return _fail(str(exc))
    result = assembly.result

    out_path = Path(args.out) if args.out else paths.generated_config_file
    atomic_write_json(out_path, result.config)
    engine.persist(paths, assembly, inventory.quotas)

    if args.print:
        print(json.dumps(result.config, ensure_ascii=False, indent=2))
    members = ", ".join(info.tag for info in result.nodes if info.role == "proxy")
    spares = sum(1 for info in result.nodes if info.role == "spare")
    if args.no_validate:
        verdict_text = "не запускалась (--no-validate)"
    else:
        verdict_text = "пройдена" if assembly.verdict else "пропущена (xray не найден)"
    print(
        f"участники: {members}; запасные: {spares}; цепочки: {len(result.chain_tags)}; "
        f"конфиг: {out_path}; проверка xray run -test: {verdict_text}"
    )
    return 0


def _cmd_apply(args, cfg: config.Config, paths: Paths, logger) -> int:
    xray_bin = _require_xray(paths)
    if xray_bin is None:
        return 1
    mark = engine.bypass_mark(cfg, logger)
    inventory = engine.collect(cfg, paths, mark=mark, logger=logger)
    if not inventory.complete and paths.xray_config_file.exists():
        # Иначе из работающего ядра пропали бы серверы подписки, которую сейчас
        # не удалось получить.
        return _fail("не все подписки получены — рабочий конфиг не меняется")
    try:
        assembly = engine.assemble(
            cfg, paths, inventory, mark=mark, logger=logger, xray_bin=xray_bin
        )
    except engine.EngineError as exc:
        return _fail(str(exc))
    applier = engine.make_applier(cfg, paths, xray_bin)
    outcome = applier.apply(assembly.result.config, force_now=args.now)
    if outcome.mode in ("api", "restart", "unchanged"):
        engine.persist(paths, assembly, inventory.quotas, record_event=False)
    if outcome.mode in ("api", "restart"):
        _restore_pin(paths, applier.api, logger)
    if outcome.mode != "unchanged":
        with _store(paths) as store:
            store.add_event("apply", engine.describe(outcome))
    print(engine.describe(outcome))
    if outcome.mode == "restart_deferred":
        print("чтобы применить сейчас (соединения оборвутся): xgw apply --now")
    _sync_network(cfg, paths, logger)
    return 0 if outcome.mode in ("api", "restart", "unchanged", "restart_deferred") else 1


def _sync_network(cfg: config.Config, paths: Paths, logger) -> None:
    """На установленном шлюзе `xgw apply` доводит до конфига и сеть: правила
    nftables (bypass_hosts, exclude_cidrs) и DHCP (dhcp_range, static_leases)."""
    if _root_problem() or not paths.journal_file.exists():
        return
    capture = Capture(cfg, paths, logger=logger)
    if capture.configured:
        try:
            capture.up()
        except CaptureError as exc:
            print(f"внимание: правила сети не обновлены: {exc}", file=sys.stderr)
    if not capture.lan_if:
        return
    changed, warnings = dnsmasq.write_conf(cfg, paths)
    for warning in warnings:
        logger.warning("%s", warning)
    if changed:
        try:
            cmd.run(["systemctl", "restart", dnsmasq.UNIT], timeout=60.0)
            print("dnsmasq: настройки DHCP обновлены")
        except cmd.CommandError as exc:
            print(f"внимание: dnsmasq не перезапущен: {exc}", file=sys.stderr)


@contextlib.contextmanager
def _store(paths: Paths):
    store = Store(paths.db_file)
    try:
        yield store
    finally:
        store.close()


def _active_pin(paths: Paths) -> dict | None:
    try:
        with _store(paths) as store:
            raw = store.get_meta("pin")
        pin = json.loads(raw or "null")
    except (json.JSONDecodeError, OSError, sqlite3.Error):
        return None  # нет доступа к состоянию (запуск без root) — статус покажем и так
    if isinstance(pin, dict) and pin.get("tag") and pin.get("until", 0) > time.time():
        return pin
    return None


def _restore_pin(paths: Paths, api, logger) -> None:
    """adrules и перезапуск сбрасывают закрепление в ядре — возвращаем, пока срок не вышел."""
    pin = _active_pin(paths)
    if pin is None:
        return
    try:
        api.pin(BALANCER_TAG, pin["tag"])
    except ApiError as exc:
        logger.error("закрепление %s не восстановлено: %s", pin["tag"], exc)


# --- status / servers ----------------------------------------------------------


def _snapshot(cfg: config.Config, paths: Paths) -> dict | None:
    """Статус демона, если он свежий; иначе разовый снимок без машины состояний."""
    max_age = max(3.0 * cfg.watchdog.interval_s, 180.0)
    snapshot = status.read_status(paths, max_age)
    applied = engine.read_json(paths.xray_config_file)
    if snapshot is None:
        if applied is None:
            return None
        observatory: dict | None = None
        with contextlib.suppress(Exception):
            observatory = metrics.parse_observatory(metrics.fetch_metrics(cfg.xray.metrics_port))
        xray_bin = validate.find_xray(None, paths)
        version = binary.installed_version(xray_bin) if xray_bin else None
        snapshot = status.collect_status(
            cfg, paths, builder.applied_nodes(applied),
            observatory=observatory, xray_ok=observatory is not None,
            xray_version=".".join(map(str, version or ())),
        )
    # Закрепление, перехват и текущий выбор балансировщика — на момент вывода, а
    # не последнего шага демона.
    snapshot["pin"] = _active_pin(paths)
    capture = Capture(cfg, paths)
    if capture.configured:
        snapshot["capture"] = capture.describe()
    xray_bin = validate.find_xray(None, paths)
    if xray_bin is not None and snapshot["xray"]["ok"]:
        with contextlib.suppress(ApiError):
            info = engine.make_api(cfg, xray_bin).balancer_state(BALANCER_TAG)
            snapshot["selecting"] = [info.override] if info.override else list(info.selects)
    return snapshot


def _cmd_status(args, cfg: config.Config, paths: Paths, logger) -> int:
    snapshot = _snapshot(cfg, paths)
    if snapshot is None:
        return _fail(f"рабочего конфига нет ({paths.xray_config_file}) — выполните xgw apply")
    if args.json:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    elif args.command == "servers":
        print(status.render_servers(snapshot))
    else:
        print(status.render_status(snapshot))
    return 0


# --- probe ---------------------------------------------------------------------


def _cmd_probe(args, cfg: config.Config, paths: Paths, logger) -> int:
    applied = engine.read_json(paths.xray_config_file)
    if applied is None:
        return _fail(f"рабочего конфига нет ({paths.xray_config_file}) — выполните xgw apply")
    password, _ports = builder.probe_state(applied)
    view = builder.applied_nodes(applied)
    if args.tag and not args.all:
        suffix = args.tag.split("-", 1)[-1]
        view = [info for info in view if args.tag in (info.tag, info.probe_tag, suffix)]
        if not view:
            return _fail(f"узла {args.tag} нет в рабочем конфиге (см. xgw servers)", 2)
    if not password or not view:
        return _fail("в рабочем конфиге нет probe-inbounds")

    verdicts: list[str] = []
    with _store(paths) as store:
        for info in view:
            result = scan.scan_node(info, cfg, probe_pass=password)
            store.save_scan(
                info.probe_tag, result.verdict, result.bytes_read, result.seconds, result.error
            )
            verdicts.append(result.verdict)
            detail = f"  {result.error}" if result.error else ""
            print(
                f"{info.tag:<20} {result.verdict:<18} "
                f"{result.bytes_read:>7} Б за {result.seconds:>5.1f} с{detail}"
            )
    if len(view) == 1:
        return 0 if verdicts[0] in ("OK", "SLOW") else 1
    return 0


# --- pin / unpin ---------------------------------------------------------------


def _cmd_pin(args, cfg: config.Config, paths: Paths, logger) -> int:
    xray_bin = _require_xray(paths)
    if xray_bin is None:
        return 1
    ttl = config.parse_seconds(args.ttl)
    if ttl is None or not 0 < ttl <= MAX_PIN_SECONDS:
        return _fail("--ttl: ожидается срок вида 30s, 10m или 2h, не больше 24h", 2)
    members = [
        info.tag
        for info in builder.applied_nodes(engine.read_json(paths.xray_config_file))
        if info.role == "proxy"
    ]
    if args.tag not in members:
        return _fail(
            f"{args.tag} — не участник балансировщика; участники: {', '.join(members) or 'нет'}", 2
        )
    try:
        engine.make_api(cfg, xray_bin).pin(BALANCER_TAG, args.tag)
    except ApiError as exc:
        return _fail(str(exc))
    until = time.time() + ttl
    with _store(paths) as store:
        store.set_meta("pin", json.dumps({"tag": args.tag, "until": until}))
        store.add_event("pin", f"{args.tag} закреплён вручную на {args.ttl}")
    print(
        f"{args.tag} закреплён на {args.ttl}. Автопереключение на это время отключено: "
        "если узел «заморозят», трафик встанет. Снять раньше: xgw unpin"
    )
    if status.read_status(paths, max(3.0 * cfg.watchdog.interval_s, 180.0)) is None:
        print("внимание: демон XGW не запущен — по истечении срока снимите закрепление сами")
    return 0


def _cmd_unpin(args, cfg: config.Config, paths: Paths, logger) -> int:
    xray_bin = _require_xray(paths)
    if xray_bin is None:
        return 1
    try:
        engine.make_api(cfg, xray_bin).unpin(BALANCER_TAG)
    except ApiError as exc:
        return _fail(str(exc))
    with _store(paths) as store:
        store.set_meta("pin", "")
        store.add_event("pin", "закрепление снято вручную")
    print("закрепление снято, выбором узла снова управляет Xray")
    return 0


# --- enable / disable / net ----------------------------------------------------


def _root_problem() -> str | None:
    """Почему сетью управлять нельзя; None — можно."""
    if not sys.platform.startswith("linux"):
        return "управление сетью работает только в Linux"
    if os.geteuid() != 0:
        return "нужны права root: sudo xgw …"
    return None


def _scope(info: dict) -> str:
    parts = [f"сеть {info['lan_if']}"] if info["lan"] else []
    if info["local"]:
        parts.append("эта машина")
    return " и ".join(parts)


def _cmd_enable(args, cfg: config.Config, paths: Paths, logger) -> int:
    problem = _root_problem()
    if problem:
        return _fail(problem)
    capture = Capture(cfg, paths, logger=logger)
    if not capture.capturing:
        return _fail(
            "в конфиге нечего перехватывать: capture.local = false, а для capture.lan "
            "нужен network.lan_if",
            2,
        )
    paths.ensure()
    try:
        capture.enable()
    except CaptureError as exc:
        return _fail(f"перехват не включён: {exc}")
    info = capture.describe(check=False)
    text = f"перехват включён: {_scope(info)} — через Xray"
    if info["bypass"]:
        text += "; мимо VPN: " + ", ".join(info["bypass"])
    with _store(paths) as store:
        store.add_event("capture", text)
    print(text)
    if engine.healthy_http_in(cfg) is None:
        print(
            "внимание: Xray не отвечает — пока он не запущен, перехваченный трафик "
            "никуда не уходит. Вернуть прямой интернет: sudo xgw disable"
        )
    return 0


def _cmd_disable(args, cfg: config.Config, paths: Paths, logger) -> int:
    problem = _root_problem()
    if problem:
        return _fail(problem)
    capture = Capture(cfg, paths, logger=logger)
    paths.ensure()
    try:
        capture.disable()
    except CaptureError as exc:
        return _fail(f"перехват не снят: {exc}")
    text = "перехват снят: трафик идёт напрямую, мимо VPN"
    if capture.lan_if:
        text += f"; шлюз остаётся роутером для сети {capture.lan_if}"
    with _store(paths) as store:
        store.add_event("capture", text)
    print(text)
    print("вернуть перехват: sudo xgw enable")
    return 0


def _cmd_net(args, cfg: config.Config, paths: Paths, logger) -> int:
    capture = Capture(cfg, paths, logger=logger)
    if args.action == "show":
        if args.what == "dnsmasq":
            text, warnings = dnsmasq.render(cfg)
            for warning in warnings:
                logger.warning("%s", warning)
            print(text.rstrip("\n") or "# LAN не настроен (network.lan_if пуст): dnsmasq не нужен")
            return 0
        rules = capture.rules()
        text = nft.render(rules) + nft.render6(rules)
        print(text.rstrip("\n") or "# правил нет: перехват выключен и network.lan_if не задан")
        return 0

    problem = _root_problem()
    if problem:
        return _fail(problem)
    paths.ensure()
    try:
        if args.action == "down":
            capture.down()
            print("правила XGW убраны: таблицы nftables, ip rule и маршрут")
            return 0
        mode = capture.up()
    except CaptureError as exc:
        return _fail(f"правила сети не загружены: {exc}")
    print(status.render_capture(capture.describe(check=False)) if capture.configured else
          "правил нет: перехват выключен и network.lan_if не задан")
    logger.info("правила сети загружены, режим %s", mode)
    return 0


# --- run -----------------------------------------------------------------------


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _cmd_run(args, cfg: config.Config, paths: Paths, logger) -> int:
    from .daemon import Daemon
    from .watch import notify
    from .watch.status_page import StatusPage

    xray_bin = _require_xray(paths)
    if xray_bin is None:
        return 1
    paths.ensure()
    stop = threading.Event()
    for name in ("SIGTERM", "SIGINT"):
        with contextlib.suppress(ValueError, AttributeError):  # не главный поток / нет сигнала
            signal.signal(getattr(signal, name), lambda *_args: stop.set())

    reloaded = False
    while True:
        stamp = _mtime(args.config_path)
        capture = Capture(cfg, paths)
        if not capture.configured or _root_problem():
            capture = None  # следить не за чем либо нечем: правила меняет только root
        elif reloaded:
            # Настройки изменились — правила (обход, исключения) загружаются заново.
            try:
                capture.up()
            except CaptureError as exc:
                logger.error("правила сети не обновлены: %s", exc)
        sinks = notify.build_sinks(cfg, mark=engine.bypass_mark(cfg, logger))
        daemon = Daemon(cfg, paths, xray_bin=xray_bin, capture=capture, sinks=sinks)
        if args.once:
            print(daemon.tick())
            daemon.store.close()
            return 0
        page = None
        try:
            page = StatusPage.from_config(cfg, paths)
            if page is not None:
                page.start()
        except OSError as exc:
            logger.error("страница статуса не запущена: %s", exc)
            page = None
        try:
            daemon.run(stop, changed=lambda stamp=stamp: _mtime(args.config_path) != stamp)
        finally:
            if page is not None:
                page.stop()
        if stop.is_set():
            return 0
        # config.toml изменён: перечитываем, не перезапуская процесс. Иначе демон
        # при следующем обновлении подписки вернул бы ядро к прежним настройкам.
        try:
            cfg, warnings = config.load(args.config_path)
        except config.ConfigError as exc:
            logger.error("%s — работаю с прежними настройками", exc)
            continue
        log.add_secrets(engine.config_secrets(cfg))
        for warning in warnings:
            logger.warning("%s", warning)
        logger.info("настройки перечитаны из %s", args.config_path)
        reloaded = True


# --- install / uninstall / diag / update-xray / logs ----------------------------


def _system_root_problem(paths: Paths) -> str | None:
    """Для команд, меняющих систему. С XGW_ROOT (тесты) root не нужен."""
    return _root_problem() if paths.root == Path("/") else None


def _run_diag(args, cfg: config.Config, paths: Paths, logger, *, net: bool = True) -> list:
    from .diag import Diag

    return Diag(
        cfg, paths, logger=logger, net=net,
        config_error=args.config_error, config_warnings=args.config_warnings,
    ).run()


def _cmd_diag(args, cfg: config.Config, paths: Paths, logger) -> int:
    from . import diag

    checks = _run_diag(args, cfg, paths, logger, net=not args.no_net)
    if args.json:
        print(json.dumps([dataclasses.asdict(check) for check in checks],
                         ensure_ascii=False, indent=2))
    else:
        print(diag.render(checks))
    return 1 if any(check.level == diag.FAIL for check in checks) else 0


def _cmd_install(args, cfg: config.Config, paths: Paths, logger) -> int:
    from . import diag
    from .install import SOURCE_ROOT, Installer

    problem = _root_problem()
    if problem:
        return _fail(problem)
    if args.config:
        return _fail(f"установка читает только {paths.config_file} — положите конфиг туда", 2)
    if args.config_error:
        if paths.config_file.exists():
            return _fail(args.config_error, 2)
        example = SOURCE_ROOT / "config.example.toml"
        try:
            paths.etc.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(example, paths.config_file)
            os.chmod(paths.config_file, 0o600)
        except OSError as exc:
            return _fail(f"не удалось создать {paths.config_file} из {example}: {exc}")
        print(
            f"Создан {paths.config_file} (права 0600) из примера.\n"
            "Впишите в него подписку ([[subscriptions]], поле url), а если Wi-Fi-роутер "
            "подключён ко второй сетевой карте — её имя в network.lan_if.\n"
            "Затем запустите установку ещё раз: sudo xgw install"
        )
        return 1
    checks = _run_diag(args, cfg, paths, logger)
    print(diag.render(checks))
    print()
    return Installer(cfg, paths, logger=logger, checks=lambda: checks).run(
        assume_yes=args.yes, force=args.force
    )


def _cmd_uninstall(args, cfg: config.Config, paths: Paths, logger) -> int:
    from .install import default_ask
    from .uninstall import Uninstaller

    problem = _root_problem()
    if problem:
        return _fail(problem)
    if not args.yes and not default_ask(
        "Удалить XGW и вернуть сеть в состояние до установки?"
    ):
        print("Отменено.")
        return 1
    return Uninstaller(None if args.config_error else cfg, paths, logger=logger).run(
        purge=args.purge
    )


def _cmd_update_xray(args, cfg: config.Config, paths: Paths, logger) -> int:
    from .xraycore.update import update_xray

    problem = _system_root_problem(paths)
    if problem:
        return _fail(problem)
    return update_xray(cfg, paths, logger=logger)


def _cmd_logs(args, cfg: config.Config, paths: Paths, logger) -> int:
    from . import diag, logs

    if not args.export:
        return logs.show(max(1, args.lines), args.follow)
    out_path = Path(args.out) if args.out else (
        Path.cwd() / time.strftime("xgw-logs-%Y%m%d-%H%M%S.tar.gz")
    )
    try:
        names = logs.export(
            None if args.config_error else cfg, paths, out_path, config_path=args.config_path,
            diag_text=lambda: diag.render(_run_diag(args, cfg, paths, logger, net=False)),
        )
    except OSError as exc:
        return _fail(f"архив не записан: {exc}")
    print(f"архив без секретов: {out_path}")
    print("в нём: " + ", ".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
