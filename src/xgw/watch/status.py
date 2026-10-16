"""Статус XGW: /run/xgw/status.json, вывод `xgw status` / `xgw servers`,
оценка суточного трафика проверок.

Статус собирает демон на каждом шаге watchdog; команды CLI читают готовый файл,
а если демон не запущен — собирают то же самое разово, без машины состояний.
"""

from __future__ import annotations

import datetime
import json
import time
from dataclasses import dataclass
from pathlib import Path

from .. import masking, priority
from ..config import Config, parse_seconds, probe_bytes
from ..generator.builder import NodeInfo
from ..paths import Paths, atomic_write_json
from ..store import Store

DEFAULT_PROBE_BYTES = 65536
MB = 1_000_000  # ТЗ считает в десятичных единицах: 5 × 64 КиБ × 2880 ≈ 0,94 ГБ
GB = 1_000_000_000
MONTH_DAYS = 30
PROBE_SIZE_META = "probe_size"  # ключ в базе: размер тела probe.url по сквозной проверке


@dataclass(frozen=True)
class Budget:
    """Суточный трафик проверок, байт."""

    probes: int  # GET-пробы ядра по участникам (burstObservatory)
    scans: int  # сканы запасных
    e2e: int  # сквозная проверка watchdog через http-in

    size: int = DEFAULT_PROBE_BYTES  # размер одной пробы, от которого всё посчитано
    measured: bool = False  # размер измерен сквозной проверкой, а не взят по умолчанию
    # Размер не известен ничем — ни измерением, ни URL, ни файлом по умолчанию — и взят
    # наугад (64 КиБ). Так бывает, пока probe.url не ответил ни разу: советовать по такой
    # цифре урезать проверки нельзя.
    guessed: bool = False

    @property
    def total(self) -> int:
        """Бюджет по формуле раздела 6.8: участники × проба × 86400 / interval плюс сканы."""
        return self.probes + self.scans

    @property
    def everything(self) -> int:
        """Весь трафик проверок за сутки: с ним сверяют квоту подписки."""
        return self.probes + self.scans + self.e2e


def remember_probe_size(store: Store, url: str, size: int) -> None:
    """Размер тела probe.url, который только что скачала сквозная проверка."""
    current = _load_json(store.get_meta(PROBE_SIZE_META)) or {}
    if size > 0 and (current.get("url") != url or current.get("bytes") != size):
        store.set_meta(PROBE_SIZE_META, json.dumps({"url": url, "bytes": size}))


def measured_probe_size(store: Store, url: str) -> int | None:
    """Измеренный размер пробы, если он относится к нынешнему probe.url."""
    saved = _load_json(store.get_meta(PROBE_SIZE_META)) or {}
    size = saved.get("bytes")
    if saved.get("url") == url and isinstance(size, int) and size > 0:
        return size
    return None


def probe_budget(cfg: Config, members: int, spares: int, size: int | None = None) -> Budget:
    """size — размер тела probe.url по последней сквозной проверке; без него берётся
    размер из URL (…?bytes=…) или известный размер файла по умолчанию, а для
    незнакомого адреса — 64 КиБ."""
    measured = bool(size)
    known = size or probe_bytes(cfg.probe.url)
    size = known or DEFAULT_PROBE_BYTES
    interval = parse_seconds(cfg.probe.interval) or 30
    scans_per_day = 1440 / max(1, cfg.probe.scan_spares_minutes)
    return Budget(
        probes=int(members * size * 86400 / max(1, interval)),
        scans=int(spares * size * scans_per_day),
        e2e=int(size * 86400 / max(1, cfg.watchdog.interval_s)),
        size=size,
        measured=measured,
        guessed=not known,
    )


def quota_share(budget: Budget, quotas: dict[str, dict[str, int]]) -> dict[str, float]:
    """Какую долю полной квоты подписки (в процентах) проверки расходуют за месяц."""
    share: dict[str, float] = {}
    monthly = budget.everything * MONTH_DAYS
    for name, quota in quotas.items():
        total = quota.get("total", 0) if isinstance(quota, dict) else 0
        if total > 0:
            share[name] = round(100.0 * monthly / total, 1)
    return share


def budget_summary(cfg: Config, budget: Budget, quotas: dict[str, dict[str, int]],
                   members: int, spares: int) -> dict:
    """Бюджет проб для status.json, `xgw status` и панели."""
    return {
        "probes_mb": round(budget.probes / MB, 1),
        "scans_mb": round(budget.scans / MB, 1),
        "total_mb": round(budget.total / MB, 1),
        "e2e_mb": round(budget.e2e / MB, 1),
        "limit_mb": cfg.probe.max_daily_probe_mb,
        # Всё вместе, со сквозной проверкой: столько уходит из квоты подписки.
        "all_mb": round(budget.everything / MB, 1),
        "month_gb": round(budget.everything * MONTH_DAYS / GB, 1),
        "over": budget.total / MB > cfg.probe.max_daily_probe_mb,
        "probe_bytes": budget.size,
        "measured": budget.measured,
        "guessed": budget.guessed,
        "members": members,
        "spares": spares,
        "interval_s": parse_seconds(cfg.probe.interval) or 30,
        "scan_minutes": max(1, cfg.probe.scan_spares_minutes),
        "quota_share": quota_share(budget, quotas),
        "warnings": budget_warnings(cfg, budget, quotas),
    }


def budget_warnings(cfg: Config, budget: Budget, quotas: dict[str, dict[str, int]]) -> list[str]:
    """Превышение max_daily_probe_mb или 10 % остатка квоты подписки, исчерпанная квота.

    Размер пробы взят наугад (budget.guessed) — о расходе не предупреждаем: цифра ни о
    чём не говорит, а совет урезать проверки, пока probe.url не ответил, только навредил
    бы. Исчерпанная квота от размера пробы не зависит — о ней сказано всегда."""
    warnings: list[str] = []
    daily_mb = budget.total / MB
    if daily_mb > cfg.probe.max_daily_probe_mb and not budget.guessed:
        warnings.append(
            f"трафик проверок ~{daily_mb:.0f} МБ/сут больше лимита "
            f"{cfg.probe.max_daily_probe_mb} МБ — уменьшите max_members или увеличьте interval"
        )
    for name, quota in quotas.items():
        total = quota.get("total", 0)
        if total <= 0:
            continue
        left = total - quota.get("upload", 0) - quota.get("download", 0)
        if left <= 0:
            warnings.append(f"квота подписки «{name}» исчерпана")
        elif budget.total > left * 0.10 and not budget.guessed:
            warnings.append(
                f"трафик проверок ~{daily_mb:.0f} МБ/сут — больше 10 % остатка квоты "
                f"подписки «{name}» ({left / MB:.0f} МБ)"
            )
    return warnings


def collect_status(
    cfg: Config,
    paths: Paths,
    view: list[NodeInfo],
    *,
    observatory: dict[str, dict] | None,
    xray_ok: bool,
    state: str | None = None,
    action: str = "",
    since: float | None = None,
    dead_since: dict[str, float] | None = None,
    selecting: tuple[str, ...] = (),
    xray_version: str = "",
    daemon: bool = False,
    capture: dict | None = None,
    probe_target: str = "",
) -> dict:
    """Снимок состояния для status.json. observatory=None — метрики недоступны.
    probe_target — предупреждение «не отвечает сам probe.url» (пусто — отвечает)."""
    now = time.time()
    names: dict[str, str] = {}
    origins: dict[str, str] = {}
    sub_errors: dict = {}
    scans: dict[str, dict] = {}
    quotas: dict[str, dict[str, int]] = {}
    events: list[dict] = []
    pin: dict | None = None
    summary: dict = {}
    probe_size: int | None = None
    try:
        store = Store(paths.db_file)
        try:
            for node in store.all_nodes():
                names[node["tag"]] = node["name"]
                origins[node["tag"]] = node["source"]
            sub_errors = _load_json(store.get_meta("sub_errors")) or {}
            scans = store.scans()
            quotas = _load_json(store.get_meta("quota")) or {}
            pin = _load_json(store.get_meta("pin")) or None
            summary = _load_json(store.get_meta("nodes_summary")) or {}
            probe_size = measured_probe_size(store, cfg.probe.url)
            events = store.recent_events(10)
        finally:
            store.close()
    except Exception:  # статус показываем и без базы
        pass

    members, spares = [], []
    for info in view:
        if info.role == "proxy":
            entry = (observatory or {}).get(info.tag)
            dead_at = (dead_since or {}).get(info.tag)
            members.append(
                {
                    "tag": info.tag,
                    "fingerprint": info.fingerprint,
                    "name": names.get(info.tag, ""),
                    "source": origins.get(info.tag, ""),
                    # None — ядро ещё не завершило по узлу ни одной пробы
                    "alive": entry["alive"] if entry else None,
                    "delay_ms": round(entry["delay"] * 1000)
                    if entry and entry.get("delay") is not None
                    else None,
                    "dead_since": dead_at,
                    "priority": priority.level_of(cfg.managed.priority, info.fingerprint),
                }
            )
        else:
            scan = scans.get(info.probe_tag)
            spares.append(
                {
                    "tag": info.tag,
                    "fingerprint": info.fingerprint,
                    "name": names.get(info.tag, ""),
                    "source": origins.get(info.tag, ""),
                    "verdict": scan["verdict"] if scan else None,
                    "bytes": scan["bytes"] if scan else None,
                    "seconds": scan["seconds"] if scan else None,
                    "scanned": scan["ts"] if scan else None,
                    "priority": priority.level_of(cfg.managed.priority, info.fingerprint),
                }
            )

    budget = probe_budget(cfg, len(members), len(spares), probe_size)
    status = {
        "updated": now,
        "daemon": daemon,
        "state": state,
        "action": action,
        "since": since,
        # configured = False — рабочего конфига ещё нет: Xray не запускался, потому что
        # серверов пока не добавляли (это не сбой).
        "xray": {
            "ok": xray_ok, "version": xray_version,
            "configured": paths.xray_config_file.exists(),
        },
        "capture": capture,
        "members": members,
        "spares": spares,
        # Уровень приоритета, серверы которого сейчас в работе (priority.py).
        "tier": _tier(cfg, members),
        "selecting": list(selecting),
        "pin": pin if pin and pin.get("until", 0) > now else None,
        "quota": quotas,
        "sub_errors": sub_errors,
        "budget": budget_summary(cfg, budget, quotas, len(members), len(spares)),
        # Сводка разбора подписок: сколько серверов отброшено и сколько дублей схлопнуто.
        "nodes": summary,
        "probe_target": probe_target,
        "pending_restart": paths.pending_config_file.exists(),
        "events": events,
    }
    masked = masking.mask_obj(status)
    assert isinstance(masked, dict)
    return masked


def _tier(cfg: Config, members: list[dict]) -> str | None:
    rank = priority.best(cfg.managed.priority, [member["fingerprint"] for member in members])
    return None if rank is None else priority.LEVELS[rank]


def write_status(paths: Paths, status: dict) -> None:
    atomic_write_json(paths.status_file, status, mode=0o644)


def read_status(paths: Paths, max_age: float) -> dict | None:
    """Статус, записанный демоном, если он свежий; иначе None (демон не запущен)."""
    return _fresh(paths.status_file, max_age)


def _fresh(path: Path, max_age: float) -> dict | None:
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(status, dict) or time.time() - float(status.get("updated", 0)) > max_age:
        return None
    return status


def _load_json(text: str | None) -> dict | None:
    if not text:
        return None
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


# --- вывод ---------------------------------------------------------------------


def _clock(ts: float | None) -> str:
    if not ts:
        return "—"
    return datetime.datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")


def _ago(ts: float | None) -> str:
    if not ts:
        return ""
    minutes = max(0, int((time.time() - ts) // 60))
    return f"{minutes} мин" if minutes < 120 else f"{minutes // 60} ч"


def _level(entry: dict) -> str:
    """Отметка уровня приоритета у сервера; у среднего (по умолчанию) — пусто."""
    level = entry.get("priority") or priority.DEFAULT
    return "" if level == priority.DEFAULT else f" [{priority.NAMES.get(level, level)}]"


def render_servers(status: dict) -> str:
    lines: list[str] = []
    members = status.get("members") or []
    spares = status.get("spares") or []
    header = f"Участники балансировщика ({len(members)}):"
    tier = status.get("tier")
    if tier and any(_level(entry) for entry in [*members, *spares]):
        header = (f"Участники балансировщика ({len(members)}), уровень приоритета "
                  f"«{priority.NAMES.get(tier, tier)}»:")
    lines.append(header)
    for member in members:
        if member["alive"] is None:
            health = "нет данных"
        elif member["alive"]:
            delay = member.get("delay_ms")
            health = "жив" + (f", {delay} мс" if delay is not None else "")
        else:
            dead = _ago(member.get("dead_since"))
            health = "МЁРТВ" + (f" уже {dead}" if dead else "")
        mark = "  ← выбран" if member["tag"] in (status.get("selecting") or []) else ""
        lines.append(
            f"  {member['tag']:<20} {health:<18} {member.get('name', '')}{_level(member)}{mark}"
        )
    lines.append(f"Запасные ({len(spares)}):")
    for spare in spares:
        if spare["verdict"] is None:
            scan = "не проверялся"
        else:
            scan = f"{spare['verdict']}, {spare['bytes']} Б за {spare['seconds']} с"
            scan += f" ({_clock(spare.get('scanned'))})"
        lines.append(f"  {spare['tag']:<20} {scan:<40} {spare.get('name', '')}{_level(spare)}")
    return "\n".join(lines)


def join_ru(items: list[str]) -> str:
    """«a», «a и b», «a, b и c»."""
    if len(items) <= 2:
        return " и ".join(items)
    return ", ".join(items[:-1]) + " и " + items[-1]


def render_capture(capture: dict) -> str:
    """Строка о перехвате: что через Xray, что мимо, загружены ли правила."""
    mode = capture.get("mode")
    if mode == "none":
        return "Перехват: выключен в конфиге — XGW только управляет Xray"
    if mode == "off":
        return "Перехват: СНЯТ (xgw disable) — трафик идёт напрямую, мимо VPN"
    if mode == "open":
        return (
            "Перехват: ВРЕМЕННО СНЯТ — Xray недоступен, fail_mode = open; "
            "трафик идёт напрямую, мимо VPN"
        )
    if capture.get("inbound_missing"):
        # Перехват включён, но Xray работает без нужного inbound'а: правила перехвата
        # не загружены, трафик идёт напрямую (иначе он ушёл бы в никуда).
        return (
            "Перехват: НЕ ВКЛЮЧЁН (ожидание применения inbound в Xray) — "
            f"{capture['inbound_missing']}; трафик идёт напрямую, перехват включится сам "
            "после перезапуска Xray (сразу: sudo xgw apply --now)"
        )
    scope = [f"сеть {capture['lan_if']}"] if capture.get("lan") else []
    if capture.get("local"):
        scope.append(
            "эта машина" + (" через TUN" if capture.get("tun") else "")
            + (" с IPv6" if capture.get("ipv6") else "")
        )
    if capture.get("containers") and capture.get("docker"):
        scope.append("контейнеры Docker")
    text = "Перехват: включён — " + join_ru(scope)
    if capture.get("bypass"):
        text += "; мимо VPN: " + ", ".join(capture["bypass"])
    if capture.get("loaded") is False and capture.get("tun_problem"):
        text += f" — ИНТЕРФЕЙС TUN НЕ ГОТОВ: {capture['tun_problem']} (sudo xgw net up)"
    elif capture.get("loaded") is False:
        text += " — ПРАВИЛА НЕ ЗАГРУЖЕНЫ (sudo xgw enable)"
    return text


def render_xray(xray: dict) -> str:
    version = f" {xray['version']}" if xray.get("version") else ""
    if xray.get("ok"):
        state = "отвечает"
    elif xray.get("configured") is False:
        state = "ещё не запускался — рабочий конфиг появится с первым сервером из подписки"
    else:
        state = "НЕ ОТВЕЧАЕТ"
    return f"Xray{version}: {state}"


def _thousands(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def render_nodes(summary: dict) -> str:
    """«Узлов: 5 активных, 65 запасных (отброшено 4 недоступных/служебных, схлопнуто
    12 дублей)»; пусто — сводки ещё нет."""
    if not summary:
        return ""
    text = (
        f"Узлов: {summary.get('members', 0)} активных, {summary.get('spares', 0)} запасных "
        f"(отброшено {summary.get('dropped', 0)} недоступных/служебных, "
        f"схлопнуто {summary.get('duplicates', 0)} дублей)"
    )
    if summary.get("dns"):
        text += f"; из отброшенных {summary['dns']} — домен не разрешается"
    if summary.get("excluded"):
        text += f"; отключено или убрано в панели: {summary['excluded']}"
    return text


def render_budget(budget: dict) -> list[str]:
    """Трафик проверок: в сутки и в месяц, из чего складывается и какая это доля квоты."""
    lines = [
        f"Трафик проверок: ~{budget['total_mb']:.0f} МБ/сут "
        f"(пробы {budget['probes_mb']:.0f}, сканы {budget['scans_mb']:.0f}; "
        f"лимит {budget['limit_mb']}); сквозная проверка ещё ~{budget['e2e_mb']:.0f} МБ/сут"
    ]
    if "month_gb" in budget:
        size = _thousands(int(budget.get("probe_bytes") or 0))
        origin = "измерено" if budget.get("measured") else "по оценке"
        if budget.get("guessed"):
            origin = "наугад: probe.url ещё не ответил ни разу"
        lines.append(
            f"  всего ~{budget['all_mb']:.0f} МБ/сут, ~{budget['month_gb']:.1f} ГБ/мес: проба "
            f"{size} Б ({origin}); участников — {budget.get('members', 0)}, проба раз в "
            f"{budget.get('interval_s', 30)} с; запасных — {budget.get('spares', 0)}, скан раз в "
            f"{budget.get('scan_minutes', 60)} мин"
        )
        for name, share in (budget.get("quota_share") or {}).items():
            lines.append(f"  за месяц это ~{share:.0f} % квоты подписки «{name}»")
    lines.extend(f"  ! {warning}" for warning in budget.get("warnings") or [])
    return lines


def render_status(status: dict) -> str:
    lines: list[str] = []
    if status.get("daemon_down"):
        lines.append(
            "Состояние: СЛУЖБА xgw НЕ РАБОТАЕТ — наблюдение остановлено: серверы не "
            "меняются, событий и уведомлений нет (запустить: sudo systemctl start xgw); "
            "ниже — разовые данные"
        )
    elif status.get("daemon") and status.get("state"):
        since = status.get("since")
        tail = f" с {_clock(since)}" if since else ""
        lines.append(f"Состояние: {status['state']}{tail} — {status.get('action') or 'ничего'}")
    else:
        lines.append("Состояние: демон XGW не запущен — показаны разовые данные")
    lines.append(render_xray(status.get("xray") or {}))
    if status.get("probe_target"):
        lines.append(status["probe_target"])
    if status.get("capture"):
        lines.append(render_capture(status["capture"]))
    pin = status.get("pin")
    if pin:
        lines.append(
            f"Закреплён вручную: {pin['tag']} до {_clock(pin['until'])} — "
            "автопереключение на это время отключено"
        )
    if status.get("pending_restart"):
        lines.append("Ожидает окна перезапуска: новый конфиг требует перезапуска Xray")
    nodes = render_nodes(status.get("nodes") or {})
    if nodes:
        lines.append(nodes)
    lines.append(render_servers(status))
    for name, quota in (status.get("quota") or {}).items():
        total = quota.get("total", 0)
        used = quota.get("upload", 0) + quota.get("download", 0)
        text = f"Квота «{name}»: израсходовано {used / 1e9:.1f} ГБ"
        if total:
            text += f" из {total / 1e9:.1f} ГБ"
        if quota.get("expire"):
            text += f", действует до {_clock(quota['expire'])}"
        lines.append(text)
    budget = status.get("budget") or {}
    if budget:
        lines.extend(render_budget(budget))
    events = status.get("events") or []
    if events:
        lines.append("Последние события:")
        lines.extend(
            f"  {_clock(event['ts'])}  {event['kind']}: {event['detail']}" for event in events[:8]
        )
    return "\n".join(lines)
