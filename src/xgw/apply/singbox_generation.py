"""Подготовка sing-box в фоне, затем API-переключение в шаге; максимум два процесса."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass

from ..config import probe_bytes, service_ports
from ..generator import singbox as sb
from ..generator.diff import diff_configs
from ..paths import atomic_write_json, atomic_write_text, file_lock
from ..watch import checks
from ..xraycore.service import SystemdXrayService
from . import singbox_process as processes
from .applier import ApplyOutcome


def digest(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


@dataclass
class Prepared:
    token: str
    slot: str
    old: dict
    config: dict
    xray: dict
    previous_xray: dict
    parts: tuple[str, ...] = ()
    fields: tuple[str, ...] = ()


HISTORY_SECONDS = 86400


def _by_tag(config, key):
    return {str(item.get("tag")): item for item in config.get(key) or [] if isinstance(item, dict)}


def changed_parts(old, new):
    """Что изменилось в конфиге sing-box, ради чего нужно новое поколение («карусель» из
    отчёта g1-c06): servers — состав серверов или вариантов; server_settings — параметры
    серверов; dns_hosts — адреса доменов серверов; endpoints, route — прочее. Порты мостов
    и порт Clash API подбирает remap — их смена не причина. Пусто — конфиг тот же
    (штатный rotate)."""
    old, new = old or {}, new or {}
    parts = []
    old_in, new_in = _by_tag(old, "inbounds"), _by_tag(new, "inbounds")
    old_out, new_out = _by_tag(old, "outbounds"), _by_tag(new, "outbounds")
    if set(old_in) != set(new_in) or set(old_out) != set(new_out):
        parts.append("servers")
    elif any(old_out[tag] != new_out[tag] for tag in new_out):
        parts.append("server_settings")
    if old.get("dns") != new.get("dns"):
        parts.append("dns_hosts")
    for key in ("endpoints", "route"):
        if old.get(key) != new.get(key):
            parts.append(key)
    return tuple(parts)


def _paths(old, new, prefix="", depth=0):
    if isinstance(old, dict) and isinstance(new, dict) and depth < 3:
        found = []
        for key in sorted(set(old) | set(new), key=str):
            if old.get(key) != new.get(key):
                found += _paths(old.get(key), new.get(key), f"{prefix}{key}.", depth + 1)
        return found
    return [prefix.rstrip(".") or "*"]


def changed_fields(old, new):
    """Какие поля серверов изменились (server_settings): имена вроде tls.reality.short_id и
    число серверов в конце ("servers=3"), без значений — по ним видно, что меняет
    подписка от загрузки к загрузке («карусель» поколений, отчёт conncheck-generations-r2:
    4 смены за 2 часа). Не больше 12 имён."""
    old_out, new_out = _by_tag(old or {}, "outbounds"), _by_tag(new or {}, "outbounds")
    names, servers = set(), 0
    for tag in set(old_out) & set(new_out):
        if old_out[tag] != new_out[tag]:
            servers += 1
            names.update(_paths(old_out[tag], new_out[tag]))
    if not servers:
        return ()
    return (*sorted(names)[:12], f"servers={servers}")


def served(config) -> dict[str, set[str]]:
    """Серверы, которые ведёт конфиг sing-box: отпечаток → буквы вариантов (теги sb-in-…)."""
    found: dict[str, set[str]] = {}
    for item in (config or {}).get("inbounds") or []:
        match = sb._IN_TAG.match(str(item.get("tag") or "")) if isinstance(item, dict) else None
        if match:
            found.setdefault(match.group(1), set()).add(match.group(2))
    return found


COMPOSITION = ("new", "back", "again", "gone", "dropped", "pool_in", "pool_out", "variants")


def composition(old, new, *, inventory, before, pool, history=()):
    """Откуда смена состава (часть servers в changed_parts; отчёт reality-pin-r3: 4 смены за
    2 часа — servers и route). Добавленные: new — отпечатка не было в списке подписок прошлой
    смены и sing-box его не вёл за сутки (новый сервер или новый отпечаток), back — не было в
    списке прошлой смены, но sing-box его уже вёл (запись пропала из подписки и вернулась:
    мигание, а не новый сервер; history — отпечатки, которые sing-box вёл за сутки), again —
    был в списке, но sing-box его не вёл (снова отобран); убранные: gone — отпечатка нет в
    нынешнем списке подписок, dropped — в списке есть, но не отобран (мёртв, домен не
    разрешился, фильтры); pool_in / pool_out — серверы бесплатного пула; variants — тот же
    сервер с другим набором вариантов. inventory — отпечатки нынешнего списка подписок,
    before — прошлой смены (None — неизвестно: первая смена после запуска), pool — отпечатки
    пула, нынешние и прошлые."""
    old_fps, new_fps = served(old), served(new)
    counts = dict.fromkeys(COMPOSITION, 0)
    for fp in new_fps.keys() - old_fps.keys():
        if fp in pool:
            counts["pool_in"] += 1
        elif before is not None and fp in before:
            counts["again"] += 1
        elif fp in history:
            counts["back"] += 1
        else:
            counts["new"] += 1
    for fp in old_fps.keys() - new_fps.keys():
        if fp in pool:
            counts["pool_out"] += 1
        elif fp in inventory:
            counts["dropped"] += 1
        else:
            counts["gone"] += 1
    counts["variants"] = sum(1 for fp in old_fps.keys() & new_fps.keys()
                             if old_fps[fp] != new_fps[fp])
    return counts


def describe_composition(counts) -> str:
    """Строка журнала о составе: только числа."""
    added = counts["new"] + counts["back"] + counts["again"] + counts["pool_in"]
    removed = counts["gone"] + counts["dropped"] + counts["pool_out"]
    return (f"состав sing-box: +{added} −{removed} (подписка: новые +{counts['new']}, "
            f"вернулись +{counts['back']}, снова отобраны +{counts['again']}, пропали "
            f"−{counts['gone']}, не отобраны −{counts['dropped']}; пул +{counts['pool_in']} "
            f"−{counts['pool_out']}; сменили набор вариантов {counts['variants']})")


def needed(core, config):
    return config is not None and core.read() is not None and config != core.read()


def available(core):
    with file_lock(core.paths.lock_file):
        state = processes.reap(core)
        return not (state["pending"] or state["draining"] or core.paths.api_dirty_file.exists())


def remap(core, config, xray, old):
    candidate, routed = copy.deepcopy(config), copy.deepcopy(xray)
    used = set(service_ports(core.cfg).values()) | processes.ports(old)
    used.add(sb.clash_port(old, core.cfg.core.api_port))
    replacement = {}
    next_port = core.cfg.core.port_base
    for inbound in candidate["inbounds"]:
        while next_port in used and next_port <= 65535:
            next_port += 1
        if next_port > 65535:
            raise ValueError("нет портов для нового поколения sing-box")
        replacement[inbound["listen_port"]] = next_port
        inbound.update(type="mixed", listen_port=next_port)
        used.add(next_port)
    api_port = core.cfg.core.api_port
    while api_port in used and api_port <= 65535:
        api_port += 1
    if api_port > 65535:
        raise ValueError("нет порта API нового поколения sing-box")
    candidate["experimental"]["clash_api"]["external_controller"] = f"{sb.LOCAL}:{api_port}"
    for outbound in routed.get("outbounds", []):
        if sb.bridge_variant(outbound):
            server = outbound["settings"]["servers"][0]
            server["port"] = replacement[server["port"]]
    return candidate, routed


BRIDGE_BUDGET = 90.0
BRIDGE_EACH = 20.0  # на мост: мёртвый сервер не съедает весь срок — успеть 4–5 мостов
UNKNOWN_RANK = 0.5  # сервер без счёта сбоев — после надёжных, до часто отказывающих


@dataclass
class BridgeCheck:
    """Итог проверки мостов: ok и сводка для журнала — только числа и виды отказов."""
    ok: bool
    summary: str = ""

    def __bool__(self) -> bool:
        return self.ok


def bridge_check(core, config, routed, rank=None):
    """Полный GET через хотя бы один используемый мост; плохие отдельные серверы допустимы.

    rank — отпечаток → порядок (меньше — раньше): участники, что ведут трафик, затем по
    доле сбоев за сутки (Daemon._bridge_rank). Без порядка мосты шли как в конфиге, и при
    мёртвых первых серверах (возврат подписки после паузы) срок кончался раньше живых —
    поколение не менялось ни разу подряд (отчёт sub-remove, 08.11.2026)."""
    wanted = processes.xray_ports(routed)
    rank = rank or {}
    candidates = []
    for index, inbound in enumerate(config["inbounds"]):
        if inbound["listen_port"] not in wanted:
            continue
        match = sb._IN_TAG.match(str(inbound.get("tag") or ""))
        place = rank.get(match.group(1), UNKNOWN_RANK) if match else UNKNOWN_RANK
        candidates.append((place, index, inbound))
    candidates.sort(key=lambda item: (item[0], item[1]))
    if not candidates:
        # Xray не ведёт трафик ни через один мост: все серверы на профилях Xray, а sing-box
        # держит заготовленные варианты для лестницы. Проверять нечего и рисковать нечем —
        # процесс уже ответил (_wait_ready). Раньше это был отказ «0 из 0», и вместе с ним
        # отклонялась вся сборка: новые запасные не применялись (отчёт bridge-order, п. 339).
        return BridgeCheck(True, "мостов в работе нет")
    deadline = time.monotonic() + BRIDGE_BUDGET
    kinds: dict[str, int] = {}
    tried = 0
    for _place, _index, inbound in candidates:
        left = deadline - time.monotonic()
        if left <= 0:
            break
        user = inbound["users"][0]
        tried += 1
        reply = checks.http_get_via_proxy(
            sb.LOCAL, inbound["listen_port"], core.cfg.probe.url,
            proxy_user=user["username"], proxy_pass=user["password"],
            max_total=min(BRIDGE_EACH, left), min_body=probe_bytes(core.cfg.probe.url) or 1,
            user_agent=core.cfg.probe.user_agent,
        )
        if reply.ok:
            return BridgeCheck(True, f"мост {tried} из {len(candidates)}")
        kind = str(getattr(reply, "kind", "") or "error")
        kinds[kind] = kinds.get(kind, 0) + 1
    outcomes = ", ".join(f"{kind} {count}" for kind, count in sorted(kinds.items()))
    return BridgeCheck(False, f"мостов проверено {tried} из {len(candidates)}"
                              + (f": {outcomes}" if outcomes else ""))


def prepare(core, config, xray, rank=None):
    """Никаких API-записей Xray. Кандидат не получает пользовательский трафик. rank —
    порядок проверки мостов (bridge_check)."""
    with file_lock(core.paths.lock_file):
        state = processes.reap(core)
        if state["pending"] or state["draining"] or core.paths.api_dirty_file.exists():
            raise ValueError("предыдущее поколение ещё завершается или API требует восстановления")
        old = core.read()
        if old is None:
            raise ValueError("нет исходного поколения sing-box")
        # Параллельные WireGuard peers с тем же ключом могут перетянуть endpoint друг у друга.
        # Отказ до старта: даже проверка кандидата не должна мешать текущему туннелю.
        if any(body.get("endpoints") or any(o.get("type") == "wireguard"
               for o in body.get("outbounds", [])) for body in (old, config)):
            raise ValueError(
                "параллельная смена WireGuard не поддерживается; прежний туннель сохранён")
        previous_xray = json.loads(core.paths.xray_config_file.read_text(encoding="utf-8"))
        candidate, routed = remap(core, config, xray, old)
        diff = diff_configs(previous_xray, routed)
        if diff.restart_reasons:
            raise ValueError("смена поколения потребовала бы перезапуска Xray")
        if core.validator(candidate)[0] is not True:
            raise ValueError("новый sing-box не прошёл check")
        slot = next(slot for slot in processes.SLOTS if slot != state["active"])
        prepared = Prepared(secrets.token_hex(16), slot, old, candidate, routed, previous_xray,
                            changed_parts(old, config), changed_fields(old, config))
        processes.config_write(core.paths, slot, candidate)
        atomic_write_json(core.paths.singbox_last_good_file, old)
        state["pending"] = {"slot": slot, "token": prepared.token,
                            "owner": os.getpid(), "phase": "preparing",
                            "owner_start": processes.owner_start(os.getpid()),
                            "xray_sha": digest(routed), "old_ports": sorted(processes.ports(old)),
                            "parts": list(prepared.parts), "fields": list(prepared.fields)}
        processes.write(core.paths, state)
    try:
        processes.start(core, slot, candidate)
        error = core._wait_ready(candidate)
        if error:
            raise ValueError("новое поколение не прошло настоящий запрос через мост: "
                             "sing-box не готов")
        checked = bridge_check(core, candidate, routed, rank)
        if not checked:
            summary = getattr(checked, "summary", "")
            raise ValueError("новое поколение не прошло настоящий запрос через мост"
                             + (f" ({summary})" if summary else ""))
        problem = processes.identity(core, slot)
        if problem:
            raise ValueError(problem)
        with file_lock(core.paths.lock_file):
            state = processes.read(core.paths)
            if (state["pending"] or {}).get("token") != prepared.token:
                raise ValueError("подготовка поколения была отменена")
            state["pending"]["phase"] = "ready"
            processes.write(core.paths, state)
        return prepared
    except BaseException:
        abort(core, prepared)
        raise


def abort(core, prepared):
    with file_lock(core.paths.lock_file):
        _abort_locked(core, prepared)


def _abort_locked(core, prepared):
    state = processes.read(core.paths)
    pending = state["pending"] or {}
    if pending.get("token") == prepared.token and pending.get("phase") != "uncertain":
        state["pending"]["phase"] = "aborting"
        processes.write(core.paths, state)
        processes.stop(prepared.slot)
        if processes.stopped(prepared.slot):
            state["pending"] = None
        processes.write(core.paths, state)


def finish(core, applier, prepared):
    with file_lock(core.paths.lock_file):
        state = processes.read(core.paths)
        pending = state["pending"] or {}
        actual = json.loads(core.paths.xray_config_file.read_text(encoding="utf-8"))
        if (pending.get("token") != prepared.token or pending.get("phase") != "ready"
                or core.read() != prepared.old or actual != prepared.previous_xray):
            _abort_locked(core, prepared)
            return ApplyOutcome("rejected", detail="исходный конфиг изменился во время проверки")
        if applier.validator(prepared.xray)[0] is not True:
            _abort_locked(core, prepared)
            return ApplyOutcome("rejected", detail="Xray не принял новые мосты")
        if (not SystemdXrayService(processes.unit(prepared.slot)).is_active()
                or core._wait_ready(prepared.config) is not None):
            _abort_locked(core, prepared)
            return ApplyOutcome("rejected", detail="подготовленное поколение перестало отвечать")
        # Оба процесса уже работают; при неопределённом исходе не убивать их.
        state["pending"]["phase"] = "uncertain"
        processes.write(core.paths, state)
        outcome = applier._apply_locked(prepared.xray, restart_now=False, api_only=True)
        if outcome.mode not in ("api", "unchanged"):
            if not core.paths.api_dirty_file.exists():
                state["pending"]["phase"] = "ready"
                processes.write(core.paths, state)
                _abort_locked(core, prepared)
            return outcome
        _promote(core, state, prepared.config)
        core.paths.singbox_pending_file.unlink(missing_ok=True)
        return outcome


def _promote(core, state, config):
    pending = state["pending"]
    atomic_write_text(processes.marker_path(core.paths), "managed\n", mode=0o644)
    atomic_write_json(core.paths.singbox_config_file, config)
    os.chown(core.paths.singbox_config_file, 0, core.paths.singbox_config_dir.stat().st_gid)
    state["identity"] = {"slot": pending["slot"], "ts": time.time()}
    now = time.time()
    history = [item for item in state.get("history") or []
               if isinstance(item, dict) and now - float(item.get("ts") or 0) < HISTORY_SECONDS]
    history.append({"ts": now, "parts": list(pending.get("parts") or []),
                    "fields": list(pending.get("fields") or [])})
    state["history"] = history[-200:]
    state.update(active=pending["slot"], pending=None,
                 draining={"slot": state["active"], "until": time.monotonic()
                           + processes.DRAIN_SECONDS, "ports": pending["old_ports"]})
    processes.write(core.paths, state)
    core.sync_generation()


def recover(core):
    """После перезапуска демона не оставить кандидата и не остановить уже выбранный API-процесс."""
    with file_lock(core.paths.lock_file):
        state = processes.reap(core)
        pending = state["pending"]
        if not pending:
            return
        if pending["phase"] == "aborting":
            processes.stop(pending["slot"])
            if processes.stopped(pending["slot"]):
                state["pending"] = None
                processes.write(core.paths, state)
            return
        if pending["phase"] == "uncertain":
            actual = json.loads(core.paths.xray_config_file.read_text(encoding="utf-8"))
            if not core.paths.api_dirty_file.exists() and digest(actual) == pending["xray_sha"]:
                config = json.loads(processes.config_path(core.paths, pending["slot"]).read_text())
                _promote(core, state, config)
            elif not core.paths.api_dirty_file.exists():
                config = json.loads(processes.config_path(core.paths, pending["slot"]).read_text())
                if not processes.xray_ports(actual).intersection(processes.ports(config)):
                    state["pending"]["phase"] = "aborting"
                    processes.write(core.paths, state)
            return
        try:
            alive = processes.owner_start(pending["owner"]) == pending["owner_start"]
        except FileNotFoundError:
            alive = False
        if not alive:
            processes.stop(pending["slot"])
            if processes.stopped(pending["slot"]):
                state["pending"] = None
                processes.write(core.paths, state)


def legacy(core, applier):
    """Явный штатный возврат перед откатом ПО: прерывает соединения sing-box, требует согласия."""
    recover(core)
    with file_lock(core.paths.lock_file):
        state = processes.read(core.paths)
        pending = state["pending"]
        if pending and pending["phase"] != "uncertain":
            raise ValueError("подготовка ещё идёт; дождитесь результата перед возвратом")
        if pending:
            actual = json.loads(core.paths.xray_config_file.read_text(encoding="utf-8"))
            if digest(actual) == pending["xray_sha"]:
                config = json.loads(processes.config_path(core.paths, pending["slot"]).read_text())
                atomic_write_json(core.paths.singbox_config_file, config)
                os.chown(core.paths.singbox_config_file, 0,
                         core.paths.singbox_config_dir.stat().st_gid)
        for slot in processes.SLOTS:
            service = SystemdXrayService(processes.unit(slot))
            if service.is_active():
                service.stop()
        original = SystemdXrayService(processes.LEGACY)
        processes.write(core.paths, {"active": "legacy", "draining": None, "pending": None})
        processes.marker_path(core.paths).unlink(missing_ok=True)
        original.restart()
        if core._wait_ready(core.read() or {}) is not None:
            raise ValueError("обычная служба sing-box не готова")
        if core.paths.api_dirty_file.exists():
            error = applier._restart_and_wait()
            if error:
                raise ValueError("штатное восстановление Xray не завершено")
        processes.state_path(core.paths).unlink(missing_ok=True)
        core.service = original


def retire(core):
    """Xray уже применил конфиг без мостов: дать последним соединениям срок drain."""
    with file_lock(core.paths.lock_file):
        state = processes.reap(core)
        if state["pending"] or state["draining"]:
            raise ValueError("предыдущее поколение ещё завершается")
        current = core.read()
        state["draining"] = {"slot": state["active"], "until": time.monotonic()
                             + processes.DRAIN_SECONDS, "ports": sorted(processes.ports(current))}
        state["active"] = "legacy"
        processes.write(core.paths, state)
        core.paths.singbox_config_file.unlink(missing_ok=True)
