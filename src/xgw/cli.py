"""CLI xgw.

Этап 1: generate — подписки/ссылки → конфиг Xray + xray run -test.
Этап 2: apply, status, servers, probe, pin/unpin и run (демон xgw.service).
Этап 3: enable, disable и net — перехват трафика (nftables, ip rule).
Этап 4: install, uninstall, diag, update-xray и logs — установка на машину.
Сверх ТЗ: panel — ссылка на панель управления (графический интерфейс в браузере).
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
import webbrowser
from pathlib import Path

from . import __version__, actions, config, desktop, engine, log, managed, priority
from . import pin as pinning
from .generator import builder, validate
from .generator.builder import BALANCER_TAG
from .net import cmd, dnsmasq, nft, tun
from .net.capture import Capture, CaptureError, capture_for
from .paths import LockTimeout, Paths, atomic_write_json
from .store import Store
from .watch import scan, status, target
from .xraycore import binary, metrics
from .xraycore.api import ApiError

MAX_PIN_SECONDS = actions.MAX_PIN_SECONDS
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
        "pin", parents=[common],
        help="выбрать сервер вручную: весь трафик через него (как в клиентах VPN)",
    )
    pin.add_argument("tag", help="тег сервера в работе (proxy-…) или запасного (spare-…)")
    pin.add_argument(
        "--ttl", default="10m",
        help=f"срок: 30s, 10m, 2h, не больше 24h, или {pinning.FOREVER} — бессрочно "
        "(по умолчанию 10m)",
    )
    subparsers.add_parser("unpin", parents=[common], help="автовыбор: снять ручной выбор сервера")
    prio = subparsers.add_parser(
        "priority", parents=[common],
        help="приоритет сервера: high, medium (по умолчанию) или low; в работе — серверы "
        "самого высокого уровня, на котором есть живые",
    )
    prio.add_argument("server", help="тег (proxy-…, spare-…), отпечаток или имя сервера")
    prio.add_argument("level", choices=priority.LEVELS)

    subparsers.add_parser(
        "enable", parents=[common], help="включить перехват: трафик идёт через Xray"
    )
    subparsers.add_parser(
        "disable", parents=[common], help="снять перехват: сеть работает напрямую"
    )
    net = subparsers.add_parser(
        "net", parents=[common],
        help="правила сети: загрузить (up, служба xgw-net), убрать (down), показать (show); "
        "tun — вернуть интерфейс TUN и маршруты в него после запуска Xray (xgw-xray.service)",
    )
    net.add_argument("action", choices=("up", "down", "show", "tun"))
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
    subparsers.add_parser(
        "update-singbox", parents=[common],
        help="установить или обновить sing-box (проверенная версия, SHA-256, sing-box check)",
    )
    cores_parser = subparsers.add_parser(
        "cores", parents=[common],
        help="ядра Xray и sing-box: выпуски на GitHub, обновление с проверкой, возврат прежней",
    )
    cores_sub = cores_parser.add_subparsers(dest="cores_action")
    cores_sub.add_parser("status", help="что стоит, что есть на GitHub, к чему можно вернуться")
    cores_sub.add_parser("check", help="проверить выпуски на GitHub сейчас")
    cores_update = cores_sub.add_parser(
        "update", help="обновить ядро: проверка на рабочем конфиге, при сбое — возврат прежнего",
    )
    cores_update.add_argument("core", choices=("xray", "sing-box"))
    cores_update.add_argument(
        "--version", default="", help="какую версию (по умолчанию — новейшую с GitHub)",
    )
    cores_back = cores_sub.add_parser("rollback", help="вернуть прежнюю рабочую версию ядра")
    cores_back.add_argument("core", choices=("xray", "sing-box"))
    # Задание от панели — его выполняет служба xgw-core.service.
    cores_sub.add_parser("run-job", help=argparse.SUPPRESS)
    core = subparsers.add_parser(
        "core", parents=[common],
        help="закрепить за сервером ядро: xray, sing-box или auto (выбирает шлюз)",
    )
    core.add_argument("server", help="тег (proxy-…, spare-…), отпечаток или имя сервера")
    core.add_argument("core", choices=("auto", "xray", "sing-box"))
    logs = subparsers.add_parser("logs", parents=[common], help="журнал служб XGW")
    logs.add_argument("-n", "--lines", type=int, default=200, help="сколько строк показать")
    logs.add_argument("-f", "--follow", action="store_true", help="следить за журналом")
    logs.add_argument("--export", action="store_true", help="собрать архив без секретов")
    logs.add_argument("--out", default=None, help="куда записать архив (с --export)")
    panel = subparsers.add_parser(
        "panel", parents=[common], help="ссылка на панель управления (открывается в браузере)"
    )
    panel.add_argument("--open", action="store_true", help="сразу открыть панель в браузере")
    panel.add_argument(
        "--login", action="store_true",
        help="войти заново: спросить пароль администратора и открыть панель (Ubuntu)",
    )

    args = parser.parse_args(argv)
    paths = Paths.from_env()
    if args.command == "panel" and args.login and not desktop.is_root():
        # Пункт «Войти заново» у ярлыка: от человека, которому config.toml (0600) не
        # прочитать, — та же команда от root через pkexec.
        return _panel_login_hop(paths)
    log.setup()
    config_path = Path(args.config) if args.config else paths.config_file
    args.config_path, args.config_error = config_path, ""
    try:
        cfg, warnings = config.load(config_path)
    except config.ConfigError as exc:
        if args.command not in NO_CONFIG:
            return _fail(str(exc), 2)
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
        "priority": _cmd_priority,
        "enable": _cmd_enable,
        "disable": _cmd_disable,
        "net": _cmd_net,
        "run": _cmd_run,
        "install": _cmd_install,
        "uninstall": _cmd_uninstall,
        "diag": _cmd_diag,
        "update-xray": _cmd_update_xray,
        "update-singbox": _cmd_update_singbox,
        "cores": _cmd_cores,
        "core": _cmd_core,
        "logs": _cmd_logs,
        "panel": _cmd_panel,
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
    engine.persist(paths, assembly, inventory.quotas, applied=False)

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
    change = assembly.singbox
    if change is not None and change.config is not None:
        sb_path = out_path.with_name(out_path.stem + ".singbox.json")
        atomic_write_json(sb_path, change.config)
        sb_verdict = {True: "пройдена", False: "не пройдена", None: "пропущена"}[change.verdict]
        print(
            f"sing-box: серверов с мостами {change.bridged} в работе Xray; конфиг: {sb_path}; "
            f"проверка sing-box check: {sb_verdict}"
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
            cfg, paths, inventory, mark=mark, logger=logger, xray_bin=xray_bin,
            reload_singbox=True if args.now else None,
        )
    except engine.EngineError as exc:
        return _fail(str(exc))
    applier = engine.make_applier(cfg, paths, xray_bin)
    outcome, singbox_outcome = engine.apply_all(
        cfg, paths, assembly, applier, force_now=args.now,
    )
    if singbox_outcome is not None and singbox_outcome.mode != "unchanged":
        with _store(paths) as store:
            store.add_event("singbox", engine.describe_singbox(singbox_outcome))
        print(engine.describe_singbox(singbox_outcome))
    if outcome is None:
        return 1  # sing-box конфиг не принял — Xray не менялся
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
    if _root_problem(cfg) or not paths.journal_file.exists():
        return
    done, problems = actions.apply_network(
        cfg, paths, capture_for(cfg, paths, logger=logger), logger=logger, runner=cmd.run
    )
    for line in done:
        print(line)
    for problem in problems:
        print(f"внимание: {problem}", file=sys.stderr)


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
            raw = store.get_meta(pinning.META)
    except (OSError, sqlite3.Error):
        return None  # нет доступа к состоянию (запуск без root) — статус покажем и так
    return pinning.read(raw, time.time())


def _restore_pin(paths: Paths, api, logger) -> None:
    """adrules и перезапуск сбрасывают закрепление в ядре — возвращаем ручной выбор, пока
    он действует и выбранный отвечает. Тег — по новому конфигу (pin.resolve): запасной мог
    стать участником, а закрепление на тег, которого нет, остановило бы весь трафик."""
    pin = _active_pin(paths)
    if pin is None or pin.get("down"):
        return
    info = pinning.resolve(pin, builder.applied_nodes(engine.read_json(paths.xray_config_file)))
    if info is None:
        return  # сервера больше нет — выбор снимет демон, с уведомлением
    try:
        api.pin(BALANCER_TAG, info.tag)
    except ApiError as exc:
        logger.error("выбранный вручную сервер %s не закреплён: %s", info.tag, exc)


# --- status / servers ----------------------------------------------------------


DAEMON_DOWN_EXIT = 3  # как у `systemctl is-active` и LSB status: служба не работает


def _daemon_down(paths: Paths, runner: cmd.Runner | None = None) -> bool:
    """Демон установлен службой systemd, но она не работает: watchdog, замена серверов,
    события и уведомления стоят. Без установки спрашивать некого — False."""
    if not (paths.systemd_dir / "xgw.service").exists():
        return False
    try:
        state = (runner or cmd.run)(
            ["systemctl", "is-active", "xgw.service"], check=False, timeout=10.0
        )
    except cmd.CommandError as exc:
        log.get_logger("cli").debug("состояние службы xgw не узнать: %s", exc)
        return False
    return state.strip() not in ("active", "activating", "reloading")


def _snapshot(cfg: config.Config, paths: Paths) -> dict | None:
    """Статус демона, если он свежий; иначе разовый снимок без машины состояний.

    Служба демона остановлена — файл статуса не в счёт, даже свежий: он описывает
    наблюдение, которого больше нет."""
    max_age = max(3.0 * cfg.watchdog.interval_s, 180.0)
    down = _daemon_down(paths)
    snapshot = None if down else status.read_status(paths, max_age)
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
    snapshot["daemon_down"] = down
    # Закрепление, перехват и текущий выбор балансировщика — на момент вывода, а
    # не последнего шага демона.
    snapshot["pin"] = _active_pin(paths)
    capture = capture_for(cfg, paths)
    if capture.configured:
        written = snapshot.get("capture") or {}
        snapshot["capture"] = capture.describe()
        snapshot["capture"]["lan_problem"] = capture.lan_path()
        if not down:
            # Жизненный цикл перехвата знает только демон (по итогам своего шага).
            for key in ("lifecycle", "lifecycle_reason"):
                if written.get(key):
                    snapshot["capture"][key] = written[key]
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
        return 0
    else:
        print(status.render_status(snapshot))
    return DAEMON_DOWN_EXIT if snapshot.get("daemon_down") else 0


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

    results: list[scan.ScanResult] = []
    with _store(paths) as store:
        for info in view:
            result = scan.scan_node(info, cfg, probe_pass=password)
            store.save_scan(
                info.probe_tag, result.verdict, result.bytes_read, result.seconds, result.error
            )
            results.append(result)
            detail = f"  {result.error}" if result.error else ""
            print(
                f"{info.tag:<20} {result.verdict:<18} "
                f"{result.bytes_read:>7} Б за {result.seconds:>5.1f} с{detail}"
            )
    if len(view) == 1:
        return 0 if results[0].verdict in ("OK", "SLOW") else 1
    common = target.dominant(results)
    if common:
        # Ни один сервер не получил probe.url, и почти у всех одна ошибка — чаще это адрес
        # пробы, чем все серверы разом.
        print(
            f"Внимание: {target.WARNING} ({common}). "
            "Что именно не отвечает, покажет sudo xgw diag",
            file=sys.stderr,
        )
    return 0


# --- pin / unpin ---------------------------------------------------------------


def _emit(outcome: actions.Outcome) -> int:
    """Итог действия — в терминал: текст и примечания либо ошибка с кодом возврата."""
    if not outcome.ok:
        code = _fail(outcome.text, outcome.code)
        for line in outcome.hints:  # что делать дальше — и при отказе тоже
            print(line, file=sys.stderr)
        return code
    print(outcome.text)
    for line in (*outcome.notes, *outcome.hints):
        print(line)
    return 0


def _cmd_pin(args, cfg: config.Config, paths: Paths, logger) -> int:
    return _emit(actions.pin(cfg, paths, args.tag, args.ttl))


def _cmd_unpin(args, cfg: config.Config, paths: Paths, logger) -> int:
    return _emit(actions.unpin(cfg, paths))


def _cmd_priority(args, cfg: config.Config, paths: Paths, logger) -> int:
    """Приоритет сервера — то же, что выбор в панели (panel.json); демон перечитает
    настройки и применит их на ближайшем шаге."""
    listing = engine.load_inventory(paths)
    wanted = args.server.strip()
    match = builder.TAG_RE.match(wanted)
    if match:
        found = [item for item in listing if str(item.get("fingerprint", "")).startswith(
            match.group(3))]
    else:
        found = [item for item in listing if wanted in (item.get("fingerprint"), item.get("name"))]
    fingerprints = {str(item.get("fingerprint")) for item in found}
    if not fingerprints:
        return _fail(f"сервер «{wanted}» не найден: его нет в списке серверов подписок "
                     "(xgw servers — теги, панель — имена)", 2)
    if len(fingerprints) > 1:
        return _fail(f"«{wanted}» подходит нескольким серверам — укажите тег или отпечаток", 2)
    (fingerprint,) = fingerprints
    try:
        changed = managed.set_priority(
            managed.path_for(args.config_path), [fingerprint], args.level
        )
    except managed.ManagedError as exc:
        return _fail(str(exc))
    except OSError as exc:
        return _fail(f"приоритет не записан: {exc} — запустите команду через sudo")
    name = found[0].get("name") or fingerprint
    word = priority.NAMES[args.level]
    if not changed:
        print(f"приоритет сервера «{name}» уже {word}")
        return 0
    logger.info("приоритет сервера «%s»: %s", name, word)
    print(f"приоритет сервера «{name}»: {word}. Демон применит его на ближайшем шаге; в "
          "работе — серверы самого высокого уровня, на котором есть живые")
    return 0


# --- enable / disable / net ----------------------------------------------------


def _root_problem(cfg: config.Config | None = None) -> str | None:
    """Почему сетью управлять нельзя; None — можно."""
    return actions.root_problem(cfg)


def _cmd_enable(args, cfg: config.Config, paths: Paths, logger) -> int:
    problem = _root_problem(cfg)
    if problem:
        return _fail(problem)
    return _emit(actions.enable(cfg, paths, capture_for(cfg, paths, logger=logger)))


def _cmd_disable(args, cfg: config.Config, paths: Paths, logger) -> int:
    problem = _root_problem(cfg)
    if problem:
        return _fail(problem)
    return _emit(actions.disable(cfg, paths, capture_for(cfg, paths, logger=logger)))


def _cmd_net(args, cfg: config.Config, paths: Paths, logger) -> int:
    capture = capture_for(cfg, paths, logger=logger)
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
    # Правилам нужны только /var/lib/xgw (capture.json) и /run/xgw (блокировка). Больше
    # xgw-net.service писать и не может (ProtectSystem=strict): каталог в /etc, которого
    # ещё нет, paths.ensure не создал бы, и правила не загрузились бы.
    for directory in (paths.var, paths.run):
        directory.mkdir(parents=True, exist_ok=True)
    try:
        if args.action == "tun":
            done = capture.restore_tun()
            if done:
                print(done)
                logger.info("%s", done)
            return 0
        if args.action == "down":
            capture.down()
            print("правила XGW убраны: таблицы nftables, ip rule и маршрут")
            if tun.present(cfg.capture.tun_name, capture.runner):
                print(
                    f"интерфейс TUN {cfg.capture.tun_name} оставлен: его держит открытым Xray; "
                    "убирает его `xgw uninstall` (после перезагрузки его нет)"
                )
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


def _stamp(config_path: Path) -> tuple[float, float]:
    """Отметка настроек: config.toml и то, что добавлено из панели (panel.json)."""
    return _mtime(config_path), _mtime(managed.path_for(config_path))


def _sync_panel(panel, cfg: config.Config, paths: Paths, config_path: Path, daemon, logger):
    """Панель живёт дольше одного демона: перечитывание настроек её не перезапускает."""
    from .watch.panel import Panel

    if panel is not None and (not cfg.panel.enabled or panel.port != cfg.panel.port):
        panel.stop()
        panel = None
    if panel is None and cfg.panel.enabled:
        try:
            panel = Panel.from_config(
                cfg, paths, config_path,
                capture_factory=lambda *args, **kwargs: capture_for(*args, **kwargs),
            )
            panel.root_problem = lambda panel=panel: _root_problem(panel.cfg)
            panel.start()
        except OSError as exc:
            logger.error("панель управления не запущена (порт %d): %s", cfg.panel.port, exc)
            return None
    if panel is not None:
        panel.configure(cfg, daemon)
    return panel


def _cmd_run(args, cfg: config.Config, paths: Paths, logger) -> int:
    from .daemon import Daemon
    from .watch import notify
    from .watch.events import NetEvents
    from .watch.status_page import StatusPage

    xray_bin = _require_xray(paths)
    if xray_bin is None:
        return 1
    paths.ensure()
    stop = threading.Event()
    for name in ("SIGTERM", "SIGINT"):
        with contextlib.suppress(ValueError, AttributeError):  # не главный поток / нет сигнала
            signal.signal(getattr(signal, name), lambda *_args: stop.set())

    with contextlib.suppress(managed.ManagedError, OSError):
        if managed.drop_telegram(managed.path_for(args.config_path)):
            logger.info("бот Telegram убран из panel.json: Telegram в XGW больше нет")
    reloaded = False
    previous = None
    panel = None
    events = None
    current: list = [None]  # демон, которого будят события (после перечитывания — новый)
    try:
        while True:
            stamp = _stamp(args.config_path)
            capture = capture_for(cfg, paths)
            if not capture.configured or _root_problem(cfg):
                capture = None  # следить не за чем либо нечем: правила меняет только root
            elif reloaded and capture.mode() == "on" and getattr(
                capture, "inbound_problem", lambda: ""
            )():
                # Новым правилам нужен inbound, которого у работающего Xray ещё нет
                # (сменили способ перехвата, порт, имя TUN). Прежние правила и прежний
                # Xray согласованы — их и оставляем: демон первым шагом перезапустит
                # Xray с новым конфигом и сразу после этого загрузит новые правила.
                logger.info("правила перехвата обновятся после перезапуска Xray")
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
            if previous is not None:
                daemon.adopt(previous)
            previous = daemon
            current[0] = daemon
            if events is None and capture is not None:
                # События сети, сна и правил будят демон раньше очередного шага
                # (watch/events.py). Только от root: nft monitor без прав не работает, а
                # без перехвата следить не за чем.
                events = NetEvents(
                    lambda reason: current[0].wake(reason), quiet_rules=Capture.rules_quiet,
                    tun_name=cfg.capture.tun_name, logger=log.get_logger("events"),
                )
                events.start()
            panel = _sync_panel(panel, cfg, paths, args.config_path, daemon, logger)
            page = None
            try:
                page = StatusPage.from_config(cfg, paths)
                if page is not None:
                    page.start()
            except OSError as exc:
                logger.error("страница статуса не запущена: %s", exc)
                page = None
            try:
                daemon.run(stop, changed=lambda stamp=stamp: _stamp(args.config_path) != stamp)
            finally:
                if page is not None:
                    page.stop()
            if stop.is_set():
                return 0
            # Настройки изменены (config.toml либо панель): перечитываем, не перезапуская
            # процесс. Иначе демон при следующем обновлении подписки вернул бы ядро к прежним.
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
    finally:
        if events is not None:
            events.stop()
        if panel is not None:
            panel.stop()


# --- install / uninstall / diag / update-xray / logs ----------------------------


def _system_root_problem(paths: Paths) -> str | None:
    """Для команд, меняющих систему. С XGW_ROOT (тесты) root не нужен."""
    return _root_problem() if paths.root == Path("/") else None


def _run_diag(
    args, cfg: config.Config, paths: Paths, logger, *, net: bool = True, preinstall: bool = False
) -> list:
    from .diag import Diag

    return Diag(
        cfg, paths, logger=logger, net=net,
        config_error=args.config_error, config_warnings=args.config_warnings,
        preinstall=preinstall,
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
    from .install import SOURCE_ROOT, Installer, choose_lan, set_lan_if

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
        print(f"Создан {paths.config_file} (права 0600) из примера.")
        if args.yes or not sys.stdin.isatty():
            print(
                "Если Wi-Fi-роутер подключён ко второй сетевой карте, впишите её имя в "
                "network.lan_if; без этого XGW защищает только эту машину.\n"
                "Подписку можно вписать туда же ([[subscriptions]], поле url) или добавить "
                "после установки в панели.\n"
                # До первой установки команды xgw в системе ещё нет.
                "Затем запустите установку ещё раз той же командой "
                "(из каталога проекта — sudo sh packaging/install.sh)"
            )
            return 1
        # Запуск человеком в терминале: спросить про роутер и продолжить без правки файла.
        lan_if = choose_lan()
        if lan_if and not set_lan_if(paths.config_file, lan_if):
            print(f"Не удалось вписать network.lan_if — впишите {lan_if} сами и повторите.")
            return 1
        try:
            cfg, args.config_warnings = config.load(paths.config_file)
        except config.ConfigError as exc:
            return _fail(str(exc), 2)
        args.config_error = ""
        print()
    # Службы и правила прежней установки установка исправит сама — они не повод для --force.
    checks = _run_diag(args, cfg, paths, logger, preinstall=True)
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


def _cmd_update_singbox(args, cfg: config.Config, paths: Paths, logger) -> int:
    from .sbcore.update import update_singbox

    problem = _system_root_problem(paths)
    if problem:
        return _fail(problem)
    return update_singbox(cfg, paths, logger=logger)


def _cmd_cores(args, cfg: config.Config, paths: Paths, logger) -> int:
    """`xgw cores` — то же, что карточка «Ядра» в панели (cores.py)."""
    from . import cores

    action = args.cores_action or "status"
    if action == "status":
        print(_cores_text(paths))
        return 0
    problem = _system_root_problem(paths)
    if problem:
        return _fail(problem)
    if action == "run-job":
        return cores.run_request(cfg, paths, logger=logger)
    installed = {
        core: cores.read_version(core, cores.core_bin(paths, core)) for core in cores.CORES
    }
    if action == "check" or (action == "update" and not args.version):
        record, events = cores.check(cfg, paths, installed, mark=engine.bypass_mark(cfg, logger))
        from .watch.notify import Notifier

        notifier = Notifier(paths.db_file, cfg.notify.min_interval_min, logger=logger)
        for text, notify in events:
            notifier.event("cores", text, notify=notify)
        if action == "check":
            print(_cores_text(paths))
            return 1 if record.get("error") else 0
        latest = (record.get(args.core) or {}).get("latest") or {}
        if not latest.get("version"):
            error = (record.get(args.core) or {}).get("error")
            return _fail(f"не удалось узнать выпуски на GitHub: {error}" if error
                         else f"на GitHub нет {cores.TITLES[args.core]} новее установленного")
        args.version = latest["version"]
    if cores.job_active(paths, time.time()):
        return _fail("уже идёт обновление или возврат ядра — дождитесь итога (xgw cores)")
    job = cores.Job(cfg, paths, logger=logger)
    if action == "update":
        return job.run(args.core, "update", args.version, reason="cli")
    return job.run(args.core, "rollback", reason="cli")


def _cores_text(paths: Paths) -> str:
    from . import cores

    installed = {
        core: cores.version_text(cores.read_version(core, cores.core_bin(paths, core)))
        for core in cores.CORES
    }
    card = cores.panel_state(paths, installed, singbox_shown=True, now=time.time())
    lines = []
    for row in card["rows"]:
        title, core = row["title"], row["core"]
        if not row["installed"]:
            lines.append(f"{title}: не установлен")
            continue
        origin = ("принята шлюзом после обновления из панели" if row["accepted"]
                  else "проверена XGW" if row["installed"] == row["baseline"]
                  else f"не та версия: XGW проверен на {row['baseline']}")
        lines.append(f"{title} {row['installed']} — {origin}")
        if row["withdrawn"]:
            lines.append("  убрана с GitHub разработчиками — обновите ядро")
        latest = row["latest"]
        if latest:
            kind = ", предварительный выпуск" if latest.get("prerelease") else ""
            lines.append(f"  на GitHub: {latest['version']}{kind} — sudo xgw cores update {core}")
        if row["previous"]:
            lines.append(f"  прежняя версия {row['previous']} — sudo xgw cores rollback {core}")
        if row["watch_until"]:
            lines.append("  наблюдение до " + time.strftime(
                "%d.%m %H:%M", time.localtime(float(row["watch_until"]))))
        rejected = row["rejected"]
        if rejected:
            lines.append(
                f"  не прошла проверку: {rejected.get('version')} — {rejected.get('reason')}"
            )
    if card["checked"]:
        when = time.strftime("%d.%m.%Y %H:%M", time.localtime(float(card["checked"])))
        lines.append(f"Выпуски на GitHub проверены {when}"
                     + (f", ошибка: {card['error']}" if card["error"] else ""))
    else:
        lines.append("Выпуски на GitHub ещё не проверялись: sudo xgw cores check")
    job = card["job"]
    if job:
        words = {"running": "идёт", "ok": "готово", "failed": "не удалось"}
        state = words.get(job.get("state"), "")
        lines.append(f"Последнее задание ({state}): {job.get('text') or job.get('stage') or ''}")
    return "\n".join(lines)


def _cmd_core(args, cfg: config.Config, paths: Paths, logger) -> int:
    """Ядро сервера — то же, что переключатель в панели (panel.json)."""
    outcome = actions.set_core(paths, managed.path_for(args.config_path), args.server, args.core)
    if not outcome.ok:
        return _fail(outcome.text, outcome.code)
    logger.info("%s", outcome.text)
    print(outcome.text)
    return 0


PANEL_WAIT = 15.0  # сколько ждать, пока только что запущенный демон откроет панель


def _panel_answers(port: int) -> bool:
    from .watch import panel

    return panel.wait_ready(port, PANEL_WAIT)


def _panel_silent(port: int) -> str:
    return (
        f"панель не отвечает (127.0.0.1:{port}): демон XGW не запущен или порт занят другой "
        "программой — см. xgw diag"
    )


def _panel_login_hop(paths: Paths) -> int:
    """`xgw panel --login` от имени человека (пункт «Войти заново» у ярлыка «XGW»):
    pkexec спрашивает пароль администратора окном Ubuntu и запускает эту же команду от
    root — она и откроет панель."""
    try:
        code = desktop.as_admin([str(paths.launcher), "panel", "--login"])
    except desktop.DesktopError as exc:
        desktop.notify(None, str(exc))
        return _fail(str(exc))
    if code == desktop.PKEXEC_DISMISSED:
        return 1  # окно пароля закрыли — человек передумал, сообщать не о чем
    if code == desktop.PKEXEC_REFUSED:
        text = "вход в панель не выполнен: пароль администратора не принят"
        desktop.notify(None, text)
        return _fail(text)
    return code  # о прочих сбоях команда от root сообщила сама


def _panel_login(cfg: config.Config, paths: Paths) -> int:
    """`xgw panel --login` от root (через pkexec или sudo): одноразовая ссылка входа
    открывается в браузере того, кто запустил команду, в его сеансе."""
    from .watch import panel

    user = desktop.invoking_user()

    def fail(text: str) -> int:
        desktop.notify(user, text)
        return _fail(text)

    if user is None:
        return fail(
            "не видно, кто запустил команду: войдите пунктом «Войти заново» у ярлыка «XGW» "
            "или откройте ссылку, которую печатает sudo xgw panel"
        )
    if not _panel_answers(cfg.panel.port):
        return fail(_panel_silent(cfg.panel.port))
    if not desktop.graphical(user):
        return fail(
            f"у пользователя {user.name} нет графического сеанса — откройте ссылку, которую "
            "печатает sudo xgw panel"
        )
    try:
        desktop.open_url(user, panel.login_address(cfg, panel.new_login(paths)))
    except (desktop.DesktopError, OSError) as exc:
        return fail(str(exc))
    print(f"Панель открыта в браузере пользователя {user.name}, вход выполнен.")
    return 0


def _open_panel(cfg: config.Config, paths: Paths, url: str) -> int:
    """`xgw panel --open` — открыть панель в браузере этой машины."""
    if not _panel_answers(cfg.panel.port):
        return _fail(_panel_silent(cfg.panel.port))
    if not webbrowser.open(url):
        return _fail(f"браузер не открылся — откройте сами: {url}")
    return 0


def _cmd_panel(args, cfg: config.Config, paths: Paths, logger) -> int:
    from .watch import panel

    if not cfg.panel.enabled:
        return _fail("панель выключена: [panel] enabled = false в config.toml", 2)
    if args.login:
        return _panel_login(cfg, paths)
    token = panel.read_token(paths)
    if not token:
        problem = _system_root_problem(paths)
        if problem:
            return _fail(problem)
        token = panel.ensure_token(paths)
    url = f"{panel.address(cfg)}?token={token}"
    if args.open:
        return _open_panel(cfg, paths, url)
    print(f"Панель XGW: {url}")
    print(
        "Откройте ссылку в браузере на этой машине. Браузер запомнит вход: дальше панель "
        "открывается ярлыком «XGW» или адресом без токена."
    )
    return 0


def _cmd_logs(args, cfg: config.Config, paths: Paths, logger) -> int:
    from . import diag, logs

    if not args.export:
        return logs.show(max(1, args.lines), args.follow, paths)
    out_path = Path(args.out) if args.out else (
        Path.cwd() / time.strftime("xgw-logs-%Y%m%d-%H%M%S.tar.gz")
    )
    try:
        names = logs.export(
            None if args.config_error else cfg, paths, out_path, config_path=args.config_path,
            diag_text=lambda: diag.render(_run_diag(args, cfg, paths, logger, net=False)),
            owner=logs.sudo_owner(),  # под sudo архив — тому, кто вызвал, а не root
        )
    except FileExistsError:
        return _fail(f"архив не записан: файл {out_path} уже существует — укажите другое имя")
    except OSError as exc:
        return _fail(f"архив не записан: {exc}")
    print(f"архив без секретов: {out_path}")
    print("в нём: " + ", ".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
