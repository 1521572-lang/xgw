"""Статус XGW: /run/xgw/status.json, вывод `xgw status` / `xgw servers`,
оценка суточного трафика проверок.

Статус собирает демон на каждом шаге watchdog; команды CLI читают готовый файл,
а если демон не запущен — собирают то же самое разово, без машины состояний.
"""

from __future__ import annotations

import datetime
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

from .. import cost, masking, priority, rating
from .. import pin as pinning
from ..apply.rotation import REPLACEABLE_VERDICTS
from ..config import Config, parse_seconds, probe_bytes
from ..generator import profiles as profiling
from ..generator.builder import NodeInfo, reserve_tag
from ..paths import Paths, atomic_write_json
from ..store import Store
from . import guard as speedguard
from . import hosts as probehosts
from . import resolvers as resolving
from .scan import CHEAP_SCAN_BYTES, DEVICE_CHECK, RESERVE_CANDIDATES, RESERVE_RECHECK, RTT_EVERY
from .speed import SKIP_PRICE, every_hours, size_mb

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
    speed: int = 0  # замеры скорости живых серверов (watch/speed.py), не больше
    # Дешёвые проверки своих серверов устройств и RTT участников (0.2.0).
    checks: int = 0
    # Период скана запасных, по которому посчитано scans, мин (scan_minutes, ДОП-4).
    scan_minutes: int = 60

    size: int = DEFAULT_PROBE_BYTES  # размер одной пробы, от которого всё посчитано
    measured: bool = False  # размер измерен сквозной проверкой, а не взят по умолчанию
    # Размер не известен ничем — ни измерением, ни URL, ни файлом по умолчанию — и взят
    # наугад (64 КиБ). Так бывает, пока probe.url не ответил ни разу: советовать по такой
    # цифре урезать проверки нельзя.
    guessed: bool = False

    @property
    def total(self) -> int:
        """Бюджет по формуле раздела 6.8: участники × проба × 86400 / interval плюс сканы и
        (0.2.0) проверки своих серверов устройств и RTT."""
        return self.probes + self.scans + self.checks

    @property
    def everything(self) -> int:
        """Весь трафик проверок за сутки: с ним сверяют квоту подписки."""
        return self.probes + self.scans + self.checks + self.e2e + self.speed


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


MAX_SCAN_MINUTES = 1440  # скан запасных растягивается не дальше раза в сутки


def checks_bytes(devices: int, members: int) -> int:
    """Байт в сутки на дешёвые проверки: свои серверы устройств (запасные) — раз в
    DEVICE_CHECK, RTT участников — раз в RTT_EVERY."""
    return int(CHEAP_SCAN_BYTES * 86400 * (devices / DEVICE_CHECK + members / RTT_EVERY))


def scan_minutes(
    cfg: Config, members: int, full: int, cheap: int, size: int, checks: int = 0, *,
    guessed: bool = False,
) -> int:
    """Период скана запасных, мин (ДОП-4 рекомендаций к аудиту 0.1.18): пробы ядра по
    участникам (members × size × 86400 / interval) и дешёвые проверки checks — первыми в
    лимите probe.max_daily_probe_mb, а скан full запасных загрузкой probe.url и cheap
    дешёвым запросом — в остатке. Помещается — probe.scan_spares_minutes; нет — реже, но не
    реже MAX_SCAN_MINUTES (остатка нет вовсе — тоже он: об этом предупредит budget_warnings).
    guessed — размер пробы взят наугад (probe.url не ответил ни разу): по такой цифре скан не
    растягивается, как и советов урезать проверки по ней нет."""
    base = max(1, cfg.probe.scan_spares_minutes)
    per_round = full * size + cheap * CHEAP_SCAN_BYTES
    if per_round <= 0 or guessed:
        return base
    interval = parse_seconds(cfg.probe.interval) or 30
    fixed = members * size * 86400 / max(1, interval) + checks
    room = cfg.probe.max_daily_probe_mb * MB - fixed
    if room <= per_round:
        return MAX_SCAN_MINUTES
    need = math.ceil(1440 * per_round / room)
    return min(MAX_SCAN_MINUTES, max(base, need))


def probe_budget(
    cfg: Config, members: int, spares: int, size: int | None = None, *,
    cheap: int = 0, candidates: int = 0, speed_mb: float = 0.0, checks: int = 0,
) -> Budget:
    """size — размер тела probe.url по последней сквозной проверке; без него берётся
    размер из URL (…?bytes=…) или известный размер файла по умолчанию, а для
    незнакомого адреса — 64 КиБ.

    spares — запасные, которых скан проверяет загрузкой probe.url; cheap — запасные
    лимитированных подписок, которых он проверяет дешёвым запросом (scan.cheap_url);
    candidates — кандидаты в резервный выход: их проверяют только раз в RESERVE_RECHECK;
    speed_mb — МБ замеров скорости в сутки (speed_daily_mb(); оценка сверху: каждый замер
    качается целиком, все серверы живы); checks — байт дешёвых проверок (checks_bytes).
    Скан — с периодом scan_minutes: он растягивается, чтобы всё уложилось в лимит."""
    speed_bytes = int(speed_mb * MB)
    measured = bool(size)
    known = size or probe_bytes(cfg.probe.url)
    size = known or DEFAULT_PROBE_BYTES
    interval = parse_seconds(cfg.probe.interval) or 30
    minutes = scan_minutes(cfg, members, spares, cheap, size, checks, guessed=not known)
    scans_per_day = 1440 / minutes
    return Budget(
        probes=int(members * size * 86400 / max(1, interval)),
        scans=int(
            spares * size * scans_per_day + cheap * CHEAP_SCAN_BYTES * scans_per_day
            + candidates * CHEAP_SCAN_BYTES * 86400 / RESERVE_RECHECK
        ),
        e2e=int(size * 86400 / max(1, cfg.watchdog.interval_s)),
        speed=speed_bytes,
        checks=checks,
        scan_minutes=minutes,
        size=size,
        measured=measured,
        guessed=not known,
    )


@dataclass(frozen=True)
class Plan:
    """Кого и как проверяют (для оценки трафика): участники — пробы ядра, запасные —
    скан probe.url или дешёвым запросом, кандидаты в резервный выход — изредка."""

    members: list[dict]
    full: list[dict]  # запасные, которых скан качает целиком (безлимитные)
    cheap: list[dict]  # запасные лимитированных подписок: скан — дешёвым запросом
    candidates: list[dict]  # кандидаты в резервный выход: раз в RESERVE_RECHECK


def scan_plan(cfg: Config, members: list[dict], spares: list[dict]) -> Plan:
    """Как демон проверяет серверы (daemon.Daemon._queue_scan, _reserve_step): записи
    статуса с полями fingerprint и cost. С 0.2.0 классов нет: безлимитные запасные
    сканируются загрузкой probe.url, лимитированные дешевле x100 — дешёвым запросом (они тоже
    могут встать в работу), x100 и дороже — только как кандидаты в резервный выход."""
    full, cheap, rest = [], [], []
    for entry in spares:
        price = entry.get("cost", 0.0)
        if price == 0:
            full.append(entry)
        elif price < rating.COST_SKIP:
            cheap.append(entry)
        else:
            rest.append(entry)
    rest.sort(key=lambda entry: (entry.get("cost", 0.0), not entry.get("reserve")))
    return Plan(members, full, cheap, rest[:RESERVE_CANDIDATES + 1])


def node_entries(
    cfg: Config, nodes: list[dict], quotas: dict, reserve: str = ""
) -> tuple[list[dict], list[dict]]:
    """Участники и запасные из записей базы (Store.all_nodes) с полями для scan_plan:
    стоимость (cost.py) и отметка резервного выхода. Для оценки трафика в `xgw diag`."""
    limited = cost.limited_sources(quotas)
    members, spares = [], []
    for node in nodes:
        factor = cost.multiplier(str(node.get("name") or ""), cfg.filters.multiplier_regex)
        price = factor if node.get("source") in limited else 0.0
        entry = {
            "fingerprint": str(node.get("fingerprint") or ""), "source": node.get("source"),
            "cost": price, "reserve": node.get("tag") == reserve,
        }
        (members if node.get("role") == "proxy" else spares).append(entry)
    return members, spares


def speed_note(
    cfg: Config, *, price: float | None, spare: bool, alive: bool | None,
    verdict: str | None, record: dict, waiting: bool, deferred: bool,
) -> str:
    """Почему у сервера нет цифры скорости — вместо пустого места в панели (issue #1).
    Пусто — цифра есть. alive — участник отвечает ядру (None — ядро его ещё не
    проверило), verdict — вердикт последнего скана запасного; waiting — сервер в очереди
    замера."""
    if isinstance(record.get("mbps"), (int, float)):
        return ""
    if not cfg.speed.sticky:
        return "скорость не замеряется: основной сервер выключен"
    if price is not None and price >= SKIP_PRICE:
        return "скорость серверов x100 не замеряется: они для LTE"
    if price is not None and not every_hours(cfg, price, spare=spare):
        key = "unlimited_hours" if price <= 0 else "limited_hours"
        return f"замер выключен: speed.{key} = 0"
    if waiting:
        return "замер отложен: канал занят" if deferred else "в очереди замера"
    if record.get("error"):
        return f"замер не удался: {record['error']}"
    if not spare and alive is False:
        return "скорость не замеряется: сервер не отвечает"
    if spare and verdict not in ("OK", "SLOW"):
        return (
            "скорость не замеряется: запасной ещё не проверен" if verdict is None
            else "скорость не замеряется: запасной не прошёл последнюю проверку"
        )
    return "ждёт замера"


def speed_entry_mb(cfg: Config, entry: dict, *, spare: bool = False) -> float:
    """МБ замеров сервера в сутки: загрузка (у лимитированных и запасных — меньше) раз в
    срок его класса (speed.every_hours)."""
    price = entry.get("cost", 0.0)
    hours = every_hours(cfg, price, spare=spare)
    if not (cfg.speed.sticky and hours):
        return 0.0
    return size_mb(cfg, price, spare=spare) * 24 / hours


def speed_daily_mb(cfg: Config, members: list[dict], spares: list[dict]) -> float:
    """МБ замеров скорости в сутки по участникам и запасным (оценка сверху)."""
    return sum(speed_entry_mb(cfg, entry) for entry in members) + sum(
        speed_entry_mb(cfg, entry, spare=True) for entry in spares
    )


def quota_spend(
    cfg: Config, plan: Plan, size: int, scan_period: int | None = None,
) -> dict[str, int]:
    """Сколько байт квоты в сутки проверки тратят у каждой лимитированной подписки — с
    множителями серверов: проба 57 КБ через сервер x100 уносит 5,7 МБ квоты. scan_period —
    период скана запасных, мин (Budget.scan_minutes); по умолчанию — из настроек."""
    interval = parse_seconds(cfg.probe.interval) or 30
    scans_per_day = 1440 / max(1, scan_period or cfg.probe.scan_spares_minutes)
    e2e = size * 86400 / max(1, cfg.watchdog.interval_s)
    spend: dict[str, float] = {}

    def add(entry: dict, amount: float) -> None:
        price = entry.get("cost", 0.0)
        if price > 0 and entry.get("source"):
            spend[entry["source"]] = spend.get(entry["source"], 0.0) + amount * price

    for entry in plan.members:
        # Сквозная проверка идёт через выбранного балансировщиком — делим поровну.
        add(entry, size * 86400 / max(1, interval) + e2e / len(plan.members)
            + speed_entry_mb(cfg, entry) * MB)
    for entry in plan.cheap:
        add(entry, CHEAP_SCAN_BYTES * scans_per_day + speed_entry_mb(cfg, entry, spare=True) * MB)
    for entry in plan.candidates:
        add(entry, CHEAP_SCAN_BYTES * 86400 / RESERVE_RECHECK
            + speed_entry_mb(cfg, entry, spare=True) * MB)
    return {name: int(value) for name, value in spend.items()}


def quota_share(
    budget: Budget, quotas: dict[str, dict[str, int]], spend: dict[str, int] | None = None
) -> dict[str, float]:
    """Какую долю полной квоты подписки (в процентах) проверки расходуют за месяц.
    spend — расход по подпискам с множителями (quota_spend); без него — весь трафик
    проверок относится к каждой подписке."""
    share: dict[str, float] = {}
    for name, quota in quotas.items():
        total = quota.get("total", 0) if isinstance(quota, dict) else 0
        daily = budget.everything if spend is None else spend.get(name, 0)
        if total > 0:
            share[name] = round(100.0 * daily * MONTH_DAYS / total, 1)
    return share


def budget_summary(cfg: Config, budget: Budget, quotas: dict[str, dict[str, int]],
                   members: int, spares: int, spend: dict[str, int] | None = None,
                   cheap: int = 0) -> dict:
    """Бюджет проб для status.json, `xgw status` и панели. cheap — сколько из spares
    проверяется дешёвым запросом (лимитированные подписки)."""
    return {
        "probes_mb": round(budget.probes / MB, 1),
        "scans_mb": round(budget.scans / MB, 1),
        "total_mb": round(budget.total / MB, 1),
        "e2e_mb": round(budget.e2e / MB, 1),
        "speed_mb": round(budget.speed / MB, 1),
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
        "cheap": cheap,
        "interval_s": parse_seconds(cfg.probe.interval) or 30,
        "scan_minutes": budget.scan_minutes,
        "checks_mb": round(budget.checks / MB, 1),
        "quota_share": quota_share(budget, quotas, spend),
        # Квота подписок, которую проверки тратят за сутки (с множителями), МБ.
        "quota_mb": {name: round(value / MB, 1) for name, value in (spend or {}).items()},
        "warnings": budget_warnings(cfg, budget, quotas, spend),
    }


def budget_warnings(
    cfg: Config, budget: Budget, quotas: dict[str, dict[str, int]],
    spend: dict[str, int] | None = None,
) -> list[str]:
    """Превышение max_daily_probe_mb или 10 % остатка квоты подписки, исчерпанная квота.

    spend — расход квоты по подпискам с множителями (quota_spend); без него с остатком
    каждой подписки сравнивается весь трафик проверок.

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
        daily = budget.total if spend is None else spend.get(name, 0)
        if left <= 0:
            warnings.append(f"квота подписки «{name}» исчерпана")
        elif daily > left * 0.10 and not budget.guessed:
            text = "трафик проверок" if spend is None else "расход квоты на проверки"
            warnings.append(
                f"{text} ~{daily / MB:.0f} МБ/сут — больше 10 % остатка квоты "
                f"подписки «{name}» ({left / MB:.0f} МБ)"
            )
    return warnings


def class_warning(
    cfg: Config, members: list[dict], spares: list[dict], pin: dict | None, now: float,
) -> str:
    """Лимитированные серверы в работе только из-за ручного приоритета: живые безлимитные
    стоят уровнем ниже, а приоритет важнее стоимости (cost.py) — трафик тратит квоту, хотя
    мог бы не тратить. Испытание 24.10.2026: «высокий» стоял у четырёх серверов x10, живых
    безлимитных «средних» было 34 (ASSUMPTIONS п. 235). Живой запасной — со свежим сканом OK
    или SLOW, как у замены участников (daemon._fresh_scans)."""
    if not members:
        return ""

    def klass(entry: dict) -> cost.Klass:
        level = entry.get("priority") or priority.DEFAULT
        rank = priority.LEVELS.index(level) if level in priority.LEVELS else 1
        return cost.Klass(rank, float(entry.get("cost") or 0.0))

    tier = min(klass(entry) for entry in members)
    if tier.cost == 0:
        return ""
    fresh_after = now - max(1, cfg.probe.scan_spares_minutes) * 120.0 - 120.0
    alive = [
        entry for entry in spares
        if not entry.get("cost") and entry.get("verdict") in REPLACEABLE_VERDICTS
        and (entry.get("scanned") or 0) >= fresh_after and klass(entry).rank > tier.rank
    ]
    if not alive:
        return ""
    lower = priority.level_name(min(klass(entry).rank for entry in alive))
    advice = (
        "верните серверам в работе уровень «средний»" if tier.rank == 0
        else f"поставьте безлимитным уровень «{priority.level_name(tier.rank)}»"
    )
    text = (
        f"в работе — {cost.class_name(tier, True)}, а живые безлимитные серверы "
        f"({len(alive)}) стоят уровнем ниже, «{lower}»: приоритет важнее стоимости, и трафик "
        f"тратит квоту подписки ({cost.label(tier.cost)}). Если так не задумано, {advice}"
    )
    if pin and not pin.get("down"):
        text += (
            " и нажмите «Автовыбор»: пока сервер выбран вручную, шлюз серверы в работе на "
            "другой класс не меняет"
        )
    return text + "."


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
    singbox: dict | None = None,
    speeding: dict | None = None,
    stranded: str = "",
    probe_hosts: dict | None = None,
    tailscale_via_vpn: bool = False,
    whitelist: dict | None = None,
    free_pool: dict | None = None,
    guard: dict | None = None,
) -> dict:
    """Снимок состояния для status.json. observatory=None — метрики недоступны.
    probe_target — предупреждение «не отвечает сам probe.url» (пусто — отвечает).
    singbox — состояние второго ядра (daemon._singbox_status); speeding — очередь и
    прогресс замеров скорости (daemon.Daemon.speed_progress); stranded — мёртвого участника
    заменить некем (daemon.stranded_note), пусто — есть кем. probe_hosts — проверочные хосты
    и их счётчики (watch/hosts.py); tailscale_via_vpn — tailscaled идёт через VPN по
    аварийному маршруту (DERP напрямую не отвечает)."""
    now = time.time()
    names: dict[str, str] = {}
    origins: dict[str, str] = {}
    sub_errors: dict = {}
    scans: dict[str, dict] = {}
    quotas: dict[str, dict[str, int]] = {}
    events: list[dict] = []
    pin: dict | None = None
    main: dict | None = None
    speeds: dict[str, dict] = {}
    protocols = _protocols(paths)
    summary: dict = {}
    probe_size: int | None = None
    resolver_check: dict = {}
    passive: dict[str, dict] = {}
    trials: dict = {}
    rtts: dict = {}
    scores: dict = {}
    try:
        store = Store(paths.db_file)
        try:
            for node in store.all_nodes():
                names[node["tag"]] = node["name"]
                origins[node["tag"]] = node["source"]
            sub_errors = _load_json(store.get_meta("sub_errors")) or {}
            scans = store.scans()
            quotas = _load_json(store.get_meta("quota")) or {}
            pin = pinning.read(store.get_meta(pinning.META), now)
            main = _load_json(store.get_meta("main")) or None
            speeds = _load_json(store.get_meta("speed")) or {}
            summary = _load_json(store.get_meta("nodes_summary")) or {}
            probe_size = measured_probe_size(store, cfg.probe.url)
            resolver_check = resolving.loads(store.get_meta(resolving.META))
            passive = _load_json(store.get_meta(speedguard.META_PASSIVE)) or {}
            trials = _load_json(store.get_meta(profiling.TRIALS_META)) or {}
            rtts = _load_json(store.get_meta("rtt")) or {}
            scores = _load_json(store.get_meta("rating")) or {}
            events = store.recent_events(10)
        finally:
            store.close()
    except Exception:  # статус показываем и без базы
        pass

    limited = cost.limited_sources(quotas)
    pattern = cfg.filters.multiplier_regex

    def price(tag: str) -> dict:
        """Множитель и стоимость сервера (cost.py)."""
        factor = cost.multiplier(names.get(tag, ""), pattern)
        paid = origins.get(tag, "") in limited
        return {"multiplier": factor, "limited": paid, "cost": factor if paid else 0.0}

    def measured(info: NodeInfo) -> dict:
        """Последний замер скорости сервера (watch/speed.py), ключ — как у демона."""
        key = info.fingerprint if len(info.fingerprint) >= 8 else info.tag
        record = speeds.get(key)
        return record if isinstance(record, dict) else {}

    learned = trials.get("escalated") if isinstance(trials.get("escalated"), dict) else {}
    unstable = trials.get("unstable") if isinstance(trials.get("unstable"), dict) else {}
    closed = trials.get("closed") if isinstance(trials.get("closed"), dict) else {}

    def extra(info: NodeInfo, measure: dict) -> dict:
        """Поля 0.1.18: пассивная оценка скорости (ТЗ R5, «из трафика»), сумма замера (сам
        замер и трафик клиентов), выученный обход (ТЗ R1: «xray+frag после
        STALL_BEFORE_BODY») и отметка «нестабилен по ТСПУ»."""
        key = info.fingerprint if len(info.fingerprint) >= 8 else info.tag
        seen = passive.get(key) if isinstance(passive.get(key), dict) else {}
        record = learned.get(info.fingerprint)
        escalation = None
        if isinstance(record, dict) and record.get("profile") == info.profile:
            escalation = {
                "profile": info.profile, "label": profiling.label(info.profile),
                "verdict": record.get("verdict") or "", "ts": record.get("ts"),
            }
        until = unstable.get(info.fingerprint)
        rtt = rtts.get(info.fingerprint) if isinstance(rtts.get(info.fingerprint), dict) else {}
        fresh_rtt = isinstance(rtt.get("ts"), (int, float)) and now - rtt["ts"] <= 86400
        return {
            # Сетевая задержка (RTT, п. 2.3): HEAD в открытом соединении — без рукопожатий и
            # загрузки файла; delay_ms — время пробы целиком.
            "rtt_ms": rtt.get("ms") if fresh_rtt else None,
            "rtt_ts": rtt.get("ts") if fresh_rtt else None,
            # Рейтинг (rating.py) по последнему шагу демона; None — демон его ещё не считал.
            "score": scores.get(info.fingerprint)
            if isinstance(scores.get(info.fingerprint), (int, float)) else None,
            "speed_passive_mbps": seen.get("mbps"), "speed_passive_ts": seen.get("ts"),
            "speed_test_mbps": measure.get("test_mbps"), "speed_bg_mbps": measure.get("bg_mbps"),
            "escalation": escalation,
            "unstable_until": until if isinstance(until, (int, float)) and until > now else None,
            # Адрес закрыт целиком: TCP к нему напрямую не открылся (анти-ТСПУ 2.0) — когда.
            "closed_ts": closed.get(info.fingerprint)
            if isinstance(closed.get(info.fingerprint), (int, float)) else None,
        }

    reserve = reserve_tag(_load_json_file(paths.xray_config_file))
    main_tag = (main or {}).get("tag") if cfg.speed.sticky else None
    speeding = speeding or {}
    speed_queue = set(speeding.get("queue") or ())

    def note(info: NodeInfo, measure: dict, alive: bool | None, verdict: str | None) -> str:
        return speed_note(
            cfg, price=price(info.tag)["cost"], spare=info.role == "spare", alive=alive,
            verdict=verdict, record=measure, waiting=info.probe_tag in speed_queue,
            deferred=bool(speeding.get("deferred")),
        )

    members, spares = [], []
    for info in view:
        measure = measured(info)
        if info.role == "proxy":
            entry = (observatory or {}).get(info.tag)
            dead_at = (dead_since or {}).get(info.tag)
            members.append(
                {
                    "tag": info.tag,
                    "fingerprint": info.fingerprint,
                    "name": names.get(info.tag, ""),
                    "source": origins.get(info.tag, ""),
                    **price(info.tag),
                    # None — ядро ещё не завершило по узлу ни одной пробы
                    "alive": entry["alive"] if entry else None,
                    "delay_ms": round(entry["delay"] * 1000)
                    if entry and entry.get("delay") is not None
                    else None,
                    "dead_since": dead_at,
                    "priority": priority.level_of(cfg.managed.priority, info.fingerprint),
                    # Соединение идёт через дробление ClientHello (generator/fragment.py).
                    "fragment": info.fragment,
                    # Профиль обхода и ядро, которое ведёт сервер (generator/profiles.py).
                    "profile": info.profile,
                    "core": profiling.core_of(info.profile),
                    "protocol": protocols.get(info.fingerprint, ""),
                    # Основной сервер (watch/speed.py) и последний замер скорости.
                    "main": info.tag == main_tag,
                    "speed_mbps": measure.get("mbps"),
                    "speed_error": measure.get("error") or "",
                    "speed_ts": measure.get("ts"),
                    "speed_busy": bool(measure.get("busy")),
                    "speed_note": note(info, measure, entry["alive"] if entry else None, None),
                    # Сервер ждёт замера (кнопка у его строки в панели занята).
                    "speed_queued": info.probe_tag in speed_queue,
                    **extra(info, measure),
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
                    **price(info.tag),
                    # Резервный выход балансировщика: через него идёт трафик, когда все
                    # участники мертвы (builder.select_nodes).
                    "reserve": info.tag == reserve,
                    "verdict": scan["verdict"] if scan else None,
                    # Задержка по последней проверке: запасного ядро не пробует, а проверка —
                    # та же загрузка файла пробы через сервер, что и у проб ядра.
                    "delay_ms": round(scan["seconds"] * 1000)
                    if scan and scan["verdict"] in ("OK", "SLOW") and scan["seconds"] is not None
                    else None,
                    "bytes": scan["bytes"] if scan else None,
                    "seconds": scan["seconds"] if scan else None,
                    "scanned": scan["ts"] if scan else None,
                    "priority": priority.level_of(cfg.managed.priority, info.fingerprint),
                    "fragment": info.fragment,
                    "profile": info.profile,
                    "core": profiling.core_of(info.profile),
                    "protocol": protocols.get(info.fingerprint, ""),
                    # Запасные замеряются, как и участники (меньшей загрузкой); результат
                    # хранится неделю (daemon.SPEED_KEEP).
                    "speed_mbps": measure.get("mbps"),
                    "speed_error": measure.get("error") or "",
                    "speed_ts": measure.get("ts"),
                    "speed_busy": bool(measure.get("busy")),
                    "speed_note": note(info, measure, None, scan["verdict"] if scan else None),
                    "speed_queued": info.probe_tag in speed_queue,
                    **extra(info, measure),
                }
            )

    plan = scan_plan(cfg, members, spares)
    servers = set(cfg.managed.routes.values())
    devices = sum(1 for entry in spares if entry.get("fingerprint") in servers)
    budget = probe_budget(
        cfg, len(members), len(plan.full), probe_size,
        cheap=len(plan.cheap), candidates=len(plan.candidates),
        speed_mb=speed_daily_mb(cfg, members, spares),
        checks=checks_bytes(devices, len(members)),
    )
    spend = quota_spend(cfg, plan, budget.size, budget.scan_minutes)
    backup = next((entry for entry in spares if entry["reserve"]), None)
    chosen = next((entry for entry in members if entry["main"]), None)
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
        # Мёртвого участника заменить некем (daemon.stranded_note) и «лимитированные в работе
        # из-за приоритета, хотя живы безлимитные» (class_warning); пусто — всё в порядке.
        "stranded": stranded,
        "class_warning": class_warning(cfg, members, spares, pin, now),
        # Резервный выход балансировщика (запасной класса хуже) — None, если его нет.
        "reserve": {
            key: backup[key] for key in ("tag", "name", "source", "multiplier", "cost")
        } if backup else None,
        # Подписки: с лимитом трафика или безлимитные (cost.limited_sources).
        "subscriptions": [
            {"name": sub.name, "limited": sub.name in limited}
            for sub in cfg.subscriptions if sub.url
        ],
        "selecting": list(selecting),
        # Ручной выбор сервера (pin.py): until — null, если бессрочный; down — выбранный не
        # отвечает, и трафик ведёт автовыбор.
        "pin": pin,
        # Основной сервер: через него идёт весь трафик (speed.sticky); None — его нет
        # (выключен, ещё не выбран или трафик сейчас ведёт ядро).
        "sticky": cfg.speed.sticky,
        "main": {
            "tag": chosen["tag"], "name": chosen["name"], "mbps": chosen["speed_mbps"],
            "since": (main or {}).get("since"), "basis": (main or {}).get("basis"),
        } if chosen else None,
        "quota": quotas,
        "sub_errors": sub_errors,
        "budget": budget_summary(
            cfg, budget, quotas, len(members), len(plan.full) + len(plan.cheap), spend,
            cheap=len(plan.cheap),
        ),
        # Сводка разбора подписок: сколько серверов отброшено и сколько дублей схлопнуто.
        "nodes": summary,
        "probe_target": probe_target,
        # Проверочные хосты (ТЗ R3): активный и счётчики удач и ошибок по каждому.
        "probe_hosts": probe_hosts or {},
        # Итог последней проверки резолверов bootstrap-DNS (ТЗ R4a): {"ts", "results"}.
        "resolvers": resolver_check,
        "tailscale_via_vpn": tailscale_via_vpn,
        # Белые списки (анти-ТСПУ 2.0): {"since", "offer": {"tag", "name", "multiplier",
        # "answered"} | None}; None — их нет. Шлюз сам ничего не меняет.
        "whitelist": whitelist,
        # Бесплатный пул (docs/FREEPOOL-PLAN.md): сводка наблюдения; None — режим off.
        "free_pool": free_pool,
        # Контроль скорости участников (ТЗ R5–R8, watch/guard.py): подозрения, идущий поиск
        # замены, пауза после «глобальной просадки», трафик поисков за сутки.
        "guard": guard or {},
        "pending_restart": paths.pending_config_file.exists(),
        # Второе ядро: режим [core], установлен ли sing-box, отвечает ли, сколько серверов он
        # ведёт; singbox_pending — его конфиг ждёт окна перезапуска (перечитывание рвёт
        # соединения через него).
        "singbox": singbox or {},
        # Замеры скорости: сколько серверов в этом заходе и сколько уже замерено.
        "speed": {key: speeding.get(key) for key in ("total", "done", "deferred")},
        "singbox_pending": paths.singbox_pending_file.exists(),
        "events": events,
    }
    masked = masking.mask_obj(status)
    assert isinstance(masked, dict)
    return masked


def render_tspu(status: dict) -> list[str]:
    """Строки 0.1.18 для `xgw status`: поиск замены придушенному и пауза после глобальной
    просадки (ТЗ R6–R7), Tailscale через VPN (R4b), отказавшие резолверы (R4a), проверочные
    хосты с ошибками (R3)."""
    lines: list[str] = []
    guard = status.get("guard") or {}
    episode = guard.get("episode")
    if episode:
        lines.append(
            f"Контроль скорости: «{episode.get('name')}» придушен — ищу замену, замерено "
            f"{episode.get('tried', 0)} из {episode.get('total', 0)} кандидатов"
        )
    elif guard.get("cooldown_until"):
        lines.append(
            "Контроль скорости: глобальная просадка канала — новые поиски замены после "
            f"{_clock(guard['cooldown_until'])}"
        )
    if status.get("tailscale_via_vpn"):
        lines.append("Tailscale: временно через VPN — серверы DERP напрямую не отвечают")
    results = (status.get("resolvers") or {}).get("results") or []
    dead = [item for item in results if not item.get("ok")]
    if dead:
        lines.append(
            f"bootstrap-DNS: не отвечают {len(dead)} из {len(results)}: "
            + ", ".join(str(item.get("entry")) for item in dead)
        )
    hosts = (status.get("probe_hosts") or {}).get("hosts") or []
    if any(item.get("errors") for item in hosts):
        lines.append("Проверочные хосты:")
        lines.extend(f"  {line}" for line in probehosts.describe(status.get("probe_hosts")))
    return lines


def _protocols(paths: Paths) -> dict[str, str]:
    """Отпечаток → протокол сервера из списка серверов подписок (engine.save_inventory)."""
    loaded = _load_json_file(paths.var / "inventory.json") or {}
    servers = loaded.get("servers")
    return {
        str(item.get("fingerprint")): str(item.get("protocol") or "")
        for item in servers if isinstance(item, dict)
    } if isinstance(servers, list) else {}


def _tier(cfg: Config, members: list[dict]) -> str | None:
    rank = priority.best(cfg.managed.priority, [member["fingerprint"] for member in members])
    return None if rank is None else priority.LEVELS[rank]


def _load_json_file(path: Path) -> dict | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


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


def _fragment(entry: dict) -> str:
    """Ядро и профиль обхода сервера: [xray], [xray+frag], [sb], [sb+frag], [sb+mux]."""
    profile = entry.get("profile")
    if not profile:  # статус старого демона
        profile = profiling.XRAY_FRAGMENT if entry.get("fragment") else profiling.XRAY_DEFAULT
    return f" [{profiling.label(profile)}]"


def _price(entry: dict) -> str:
    """Отметка множителя у сервера лимитированной подписки: « [x10]»."""
    if not entry.get("limited"):
        return ""
    return f" [{cost.label(float(entry.get('multiplier', 1.0)))}]"


def render_servers(status: dict) -> str:
    lines: list[str] = []
    members = status.get("members") or []
    spares = status.get("spares") or []
    header = f"Участники балансировщика ({len(members)}):"
    if any(_level(entry) for entry in [*members, *spares]):
        header = (f"Участники балансировщика ({len(members)}) — лучшие по рейтингу, приоритет "
                  "в нём — вес:")
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
        if member.get("speed_mbps") is not None:
            health += f", {speed_text(float(member['speed_mbps']))}"
        mark = "  ← выбран" if member["tag"] in (status.get("selecting") or []) else ""
        if member.get("main"):
            mark = "  ← основной"
        lines.append(
            f"  {member['tag']:<20} {health:<30} {member.get('name', '')}{_level(member)}"
            f"{_price(member)}{_fragment(member)}{mark}"
        )
    lines.append(f"Запасные ({len(spares)}):")
    for spare in spares:
        if spare["verdict"] is None:
            scan = "не проверялся"
        else:
            scan = f"{spare['verdict']}, {spare['bytes']} Б за {spare['seconds']} с"
            scan += f" ({_clock(spare.get('scanned'))})"
        mark = "  ← резервный выход" if spare.get("reserve") else ""
        lines.append(
            f"  {spare['tag']:<20} {scan:<40} {spare.get('name', '')}{_level(spare)}"
            f"{_price(spare)}{_fragment(spare)}{mark}"
        )
    reserve = status.get("reserve")
    if reserve:
        lines.append(
            f"Резервный выход: {reserve['tag']} «{reserve.get('name', '')}» "
            f"({cost.describe(float(reserve.get('cost', 0.0)))}) — через него идёт трафик, "
            "только когда все участники не отвечают; ядро его не пробует"
        )
    return "\n".join(lines)


def speed_text(value: float) -> str:
    """85 Мбит/с; 8,5 Мбит/с (как watch/speed.mbps_text)."""
    if value >= 10:
        return f"{value:.0f} Мбит/с"
    return f"{value:.1f}".replace(".", ",") + " Мбит/с"


def render_pin(pin: dict) -> str:
    """Строка о ручном выборе сервера (pin.py)."""
    name = pin.get("name") or pin["tag"]
    if pin.get("down"):
        return (
            f"Выбран вручную: «{name}» ({pin['tag']}) — не отвечает, трафик ведёт автовыбор; "
            "шлюз вернётся к нему, когда он ответит"
        )
    until = f" до {_clock(pin['until'])}" if pin.get("until") else ""
    return (
        f"Выбран вручную{until}: «{name}» ({pin['tag']}) — весь трафик через него; "
        "автовыбор: xgw unpin"
    )


def render_main(status: dict) -> str:
    """Строка об основном сервере; пусто — показывать нечего."""
    main = status.get("main")
    if not status.get("sticky", True):
        return ("Основной сервер: выключен (speed.sticky = false) — сервер выбирает ядро "
                "по задержке и меняет выбор после каждой пробы")
    if not main:
        return ""
    name = f"«{main['name']}»" if main.get("name") else main["tag"]
    speed = f" — {speed_text(float(main['mbps']))}" if main.get("mbps") is not None else ""
    basis = "" if main.get("basis") == "speed" else (
        " (выбран по задержке, скорость ещё не замерена)"
    )
    since = f", с {_clock(main['since'])}" if main.get("since") else ""
    return (f"Основной сервер: {main['tag']} {name}{speed}{since}{basis}; весь трафик через "
            "него, другие участники наготове")


def join_ru(items: list[str]) -> str:
    """«a», «a и b», «a, b и c»."""
    if len(items) <= 2:
        return " и ".join(items)
    return ", ".join(items[:-1]) + " и " + items[-1]


# Жизненный цикл перехвата (daemon.Lifecycle): слово после «Перехват:» и что это значит,
# когда причины нет.
LIFECYCLE_WORDS = {
    "connected": ("работает", "трафик идёт через VPN"),
    "connecting": ("подключается", "трафик ждёт, мимо VPN ничего не уходит"),
    "blocked": ("заблокирован", "мимо VPN ничего не уходит"),
    "open": ("временно напрямую", "трафик идёт мимо VPN"),
    "off": ("снят", "трафик идёт напрямую"),
}


def render_lifecycle(capture: dict) -> str:
    """Строка «Сейчас: перехват работает — …» по итогам последнего шага демона; пусто —
    демон её не писал."""
    known = LIFECYCLE_WORDS.get(str(capture.get("lifecycle") or ""))
    if known is None:
        return ""
    word, tail = known
    reason = str(capture.get("lifecycle_reason") or "")
    text = f"Сейчас: перехват {word} — {reason or tail}"
    if reason and capture.get("lifecycle") == "blocked":
        text += f"; {tail}"
    return text


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
        # не загружены (иначе трафик ушёл бы в никуда) — он заблокирован или идёт напрямую.
        held = (
            "трафик заблокирован, мимо VPN ничего не уходит (capture.hold = block)"
            if capture.get("blocked") else "трафик идёт напрямую"
        )
        return (
            "Перехват: НЕ ВКЛЮЧЁН (ожидание применения inbound в Xray) — "
            f"{capture['inbound_missing']}; {held}, перехват включится сам "
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
    elif capture.get("lan_problem"):
        text += f" — НЕТ ИНТЕРНЕТА У УСТРОЙСТВ СЕТИ: {capture['lan_problem']} (sudo xgw diag)"
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


def render_singbox(info: dict, *, pending: bool = False) -> str:
    """Строка о втором ядре («sing-box 1.14.3: работает, серверов через него: 3»); пусто — о
    нём сказать нечего (статус снят без демона либо ядро выключено и не нужно)."""
    if not info:
        return ""
    if info.get("mode") == "xray":
        return "sing-box: выключен ([core] mode = xray)"
    if not info.get("installed"):
        return ("sing-box: не установлен — серверы hysteria2, TUIC и т. п. пропускаются "
                "(sudo xgw update-singbox)")
    version = f" {info['version']}" if info.get("version") else ""
    if info.get("failed"):
        text = "НЕ ОТВЕЧАЕТ — серверы, которые умеет и Xray, переведены на него"
    elif not info.get("expected"):
        text = "установлен, серверов для него пока нет"
    elif info.get("alive") is False:
        text = "НЕ ОТВЕЧАЕТ — демон перезапускает службу"
    else:
        text = f"работает, серверов через него: {info.get('bridged', 0)}"
    if pending:
        text += "; новый конфиг ждёт окна перезапуска (перечитывание рвёт соединения через него)"
    return f"sing-box{version}: {text}"


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
        + (f", замер скорости — до ~{budget['speed_mb']:.0f} МБ/сут"
           if budget.get("speed_mb") else "")
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
        if budget.get("cheap"):
            lines.append(
                f"  из запасных {budget['cheap']} — лимитированные: скан коротким запросом"
            )
        for name, share in (budget.get("quota_share") or {}).items():
            daily = (budget.get("quota_mb") or {}).get(name)
            spent = f" (~{daily:.0f} МБ квоты в сутки с множителями)" if daily else ""
            lines.append(f"  за месяц это ~{share:.0f} % квоты подписки «{name}»{spent}")
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
    singbox_line = render_singbox(
        status.get("singbox") or {}, pending=bool(status.get("singbox_pending")),
    )
    if singbox_line:
        lines.append(singbox_line)
    if status.get("probe_target"):
        lines.append(status["probe_target"])
    pool = status.get("free_pool")
    if isinstance(pool, dict):
        regions = ", ".join(f"{name} {count}" for name, count in sorted(
            (pool.get("by_region") or {}).items()))
        lines.append(
            f"Бесплатный пул ({'наблюдение' if pool.get('mode') == 'observe' else pool.get('mode')}"
            f", регион {pool.get('region')}): найдено {pool.get('found', 0)}, проверено "
            f"{pool.get('checked', 0)}, пригодно {pool.get('ready', 0)}"
            + (f" ({regions})" if regions else "")
            + f"; трафик проверок {pool.get('spent_mb', 0)} из {pool.get('budget_mb', 0)} МБ"
        )
        if isinstance(pool.get("traffic"), dict):
            from ..freepool import traffic as fptraffic

            lines.append(fptraffic.text(pool["traffic"]))
    whitelist = status.get("whitelist")
    if isinstance(whitelist, dict):
        offer = whitelist.get("offer") if isinstance(whitelist.get("offer"), dict) else None
        lines.append(
            "Белые списки: российские адреса открываются, зарубежные — нет; шлюз сам ничего не "
            "меняет" + (f" — сервер для белых списков «{offer.get('name')}» можно включить в "
                        "панели" if offer else " (серверов для белых списков нет)")
        )
    if status.get("capture"):
        lines.append(render_capture(status["capture"]))
        lifecycle = render_lifecycle(status["capture"])
        if lifecycle:
            lines.append(lifecycle)
    pin = status.get("pin")
    if pin:
        lines.append(render_pin(pin))
    main = render_main(status)
    if main and not (pin and not pin.get("down")):
        lines.append(main)
    if status.get("pending_restart"):
        lines.append("Ожидает окна перезапуска: новый конфиг требует перезапуска Xray")
    if status.get("class_warning"):
        lines.append(f"Внимание: {status['class_warning']}")
    lines.extend(render_tspu(status))
    nodes = render_nodes(status.get("nodes") or {})
    if nodes:
        lines.append(nodes)
    lines.append(render_servers(status))
    quotas = status.get("quota") or {}
    for name, quota in quotas.items():
        total = quota.get("total", 0)
        used = quota.get("upload", 0) + quota.get("download", 0)
        text = f"Квота «{name}»: израсходовано {used / 1e9:.1f} ГБ"
        if total:
            text += f" из {total / 1e9:.1f} ГБ, осталось {max(0, total - used) / 1e9:.1f} ГБ"
        else:
            text += ", лимита нет — безлимитная"
        if quota.get("expire"):
            text += f", действует до {_clock(quota['expire'])}"
        lines.append(text)
    for sub in status.get("subscriptions") or []:
        if sub.get("name") not in quotas and not sub.get("limited"):
            lines.append(f"Подписка «{sub['name']}»: безлимитная (лимит трафика не сообщает)")
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
