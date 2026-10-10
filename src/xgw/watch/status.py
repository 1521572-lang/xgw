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

from .. import masking
from ..config import Config, parse_seconds, probe_bytes
from ..generator.builder import NodeInfo
from ..paths import Paths, atomic_write_json
from ..store import Store

DEFAULT_PROBE_BYTES = 65536
MB = 1_000_000  # ТЗ считает в десятичных единицах: 5 × 64 КиБ × 2880 ≈ 0,94 ГБ


@dataclass(frozen=True)
class Budget:
    """Суточный трафик проверок, байт."""

    probes: int  # GET-пробы ядра по участникам (burstObservatory)
    scans: int  # сканы запасных
    e2e: int  # сквозная проверка watchdog через http-in

    @property
    def total(self) -> int:
        """Бюджет по формуле раздела 6.8: участники × проба × 86400 / interval плюс сканы."""
        return self.probes + self.scans


def probe_budget(cfg: Config, members: int, spares: int) -> Budget:
    size = probe_bytes(cfg.probe.url) or DEFAULT_PROBE_BYTES
    interval = parse_seconds(cfg.probe.interval) or 30
    scans_per_day = 1440 / max(1, cfg.probe.scan_spares_minutes)
    return Budget(
        probes=int(members * size * 86400 / max(1, interval)),
        scans=int(spares * size * scans_per_day),
        e2e=int(size * 86400 / max(1, cfg.watchdog.interval_s)),
    )


def budget_warnings(cfg: Config, budget: Budget, quotas: dict[str, dict[str, int]]) -> list[str]:
    """Превышение max_daily_probe_mb или 10 % остатка квоты подписки."""
    warnings: list[str] = []
    daily_mb = budget.total / MB
    if daily_mb > cfg.probe.max_daily_probe_mb:
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
        elif budget.total > left * 0.10:
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
) -> dict:
    """Снимок состояния для status.json. observatory=None — метрики недоступны."""
    now = time.time()
    names: dict[str, str] = {}
    origins: dict[str, str] = {}
    sub_errors: dict = {}
    scans: dict[str, dict] = {}
    quotas: dict[str, dict[str, int]] = {}
    events: list[dict] = []
    pin: dict | None = None
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
                }
            )

    budget = probe_budget(cfg, len(members), len(spares))
    status = {
        "updated": now,
        "daemon": daemon,
        "state": state,
        "action": action,
        "since": since,
        "xray": {"ok": xray_ok, "version": xray_version},
        "capture": capture,
        "members": members,
        "spares": spares,
        "selecting": list(selecting),
        "pin": pin if pin and pin.get("until", 0) > now else None,
        "quota": quotas,
        "sub_errors": sub_errors,
        "budget": {
            "probes_mb": round(budget.probes / MB, 1),
            "scans_mb": round(budget.scans / MB, 1),
            "total_mb": round(budget.total / MB, 1),
            "e2e_mb": round(budget.e2e / MB, 1),
            "limit_mb": cfg.probe.max_daily_probe_mb,
            "warnings": budget_warnings(cfg, budget, quotas),
        },
        "pending_restart": paths.pending_config_file.exists(),
        "events": events,
    }
    masked = masking.mask_obj(status)
    assert isinstance(masked, dict)
    return masked


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


def render_servers(status: dict) -> str:
    lines: list[str] = []
    members = status.get("members") or []
    lines.append(f"Участники балансировщика ({len(members)}):")
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
        lines.append(f"  {member['tag']:<20} {health:<18} {member.get('name', '')}{mark}")
    spares = status.get("spares") or []
    lines.append(f"Запасные ({len(spares)}):")
    for spare in spares:
        if spare["verdict"] is None:
            scan = "не проверялся"
        else:
            scan = f"{spare['verdict']}, {spare['bytes']} Б за {spare['seconds']} с"
            scan += f" ({_clock(spare.get('scanned'))})"
        lines.append(f"  {spare['tag']:<20} {scan:<40} {spare.get('name', '')}")
    return "\n".join(lines)


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
    scope = [f"сеть {capture['lan_if']}"] if capture.get("lan") else []
    if capture.get("local"):
        scope.append("эта машина")
    text = "Перехват: включён — " + " и ".join(scope)
    if capture.get("bypass"):
        text += "; мимо VPN: " + ", ".join(capture["bypass"])
    if capture.get("loaded") is False:
        text += " — ПРАВИЛА НЕ ЗАГРУЖЕНЫ (sudo xgw enable)"
    return text


def render_status(status: dict) -> str:
    lines: list[str] = []
    if status.get("daemon") and status.get("state"):
        since = status.get("since")
        tail = f" с {_clock(since)}" if since else ""
        lines.append(f"Состояние: {status['state']}{tail} — {status.get('action') or 'ничего'}")
    else:
        lines.append("Состояние: демон XGW не запущен — показаны разовые данные")
    xray = status.get("xray") or {}
    version = f" {xray['version']}" if xray.get("version") else ""
    lines.append(f"Xray{version}: " + ("отвечает" if xray.get("ok") else "НЕ ОТВЕЧАЕТ"))
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
        lines.append(
            f"Трафик проверок: ~{budget['total_mb']:.0f} МБ/сут "
            f"(пробы {budget['probes_mb']:.0f}, сканы {budget['scans_mb']:.0f}; "
            f"лимит {budget['limit_mb']}); сквозная проверка ещё ~{budget['e2e_mb']:.0f} МБ/сут"
        )
        lines.extend(f"  ! {warning}" for warning in budget.get("warnings") or [])
    events = status.get("events") or []
    if events:
        lines.append("Последние события:")
        lines.extend(
            f"  {_clock(event['ts'])}  {event['kind']}: {event['detail']}" for event in events[:8]
        )
    return "\n".join(lines)
