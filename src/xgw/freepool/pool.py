"""Бесплатный пул в режиме наблюдения (веха М1): сбор каталогов через несущий канал, проверки
кандидатов, сводка для состояния и панели. Трафик пользователей идёт через подписку.

Несущий канал — http-in работающего Xray (engine.healthy_http_in): серверы подписки. Сайты со
списками бесплатных серверов доступны только через VPN (решение заказчика 28.10.2026). Xray не
отвечает — запрос напрямую (сокетом с меткой обхода и своими резолверами), источник может быть
закрыт — тогда UNAVAILABLE, прежний снимок остаётся.

Каждый ответ: хост после перенаправлений — из списка доверенных у источника (providers.ORIGINS),
тело — не больше 8 МиБ (R11), между запросами к источнику — не меньше 2 с. Интервалы опроса —
free_pool.*_refresh_min со сдвигом ±20 % (R12); после ошибки — пауза 1, 2, 4… 60 минут.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from .. import fetch, log, masking
from ..config import Config
from ..net import cmd
from ..paths import Paths
from . import backend as backending
from . import ovpn, ovpnconf, providers, regions
from . import probe as probing
from .models import Access, Backend, ProviderResult, Status, Variant
from .store import PoolStore

MAX_DOCUMENT = 8 * 1024 * 1024
REQUEST_SPACING = 2.0
BACKOFF_MAX = 3600.0
JITTER = 0.2
CHECK_EVERY = 6 * 3600.0  # проверенный вариант снова — не раньше
DAY = 86400.0
HOUR = 3600.0
PROFILE_TTL = DAY  # профиль VPNBook скачивается заново раз в сутки
SOURCE_LEASE = DAY  # вариант, которого нет в каталоге дольше суток, новым не назначается (R13)

Fetcher = Callable[..., fetch.FetchResult]


class PoolError(Exception):
    """Ответ источника не принят (чужой хост, слишком большой)."""


def _due(seconds: float) -> float:
    return seconds * random.uniform(1.0 - JITTER, 1.0 + JITTER)


class FreePool:
    """Состояние наблюдения: расписание опросов и проверок (в памяти), снимки и итоги
    проверок — в PoolStore."""

    def __init__(self, cfg: Config, paths: Paths, *, logger=None, clock=time.time,
                 fetcher: Fetcher = fetch.fetch_url, sleep=time.sleep,
                 runtime: backending.Backend | None = None,
                 runner: cmd.Runner = cmd.run) -> None:
        self.cfg = cfg
        self.paths = paths
        self.store = PoolStore(paths)
        self.runner = runner
        self.runtime = runtime or backending.Backend(paths, runner=runner, logger=logger)
        self.backend_problem = "ещё не проверялся"
        self._reconciled = False
        self.log = logger or log.get_logger("freepool")
        self.clock = clock
        self.fetcher = fetcher
        self.sleep = sleep
        self.next_refresh: dict[str, float] = {}
        self.failures: dict[str, int] = {}
        self._lock = threading.Lock()
        self._remember_secrets()
        self._prune_retired()

    def _prune_retired(self) -> None:
        """Снимки источников, которых в XGW больше нет (VPNJantit убран 28.10.2026 по отчёту
        вехи М1), удаляются с диска."""
        try:
            removed = self.store.prune(providers.PROVIDERS)
        except OSError as exc:
            self.log.warning("бесплатный пул: снимки убранных источников не удалены: %s", exc)
            return
        if removed:
            self.log.info("бесплатный пул: удалены снимки убранных источников — %s",
                          ", ".join(removed))

    def _remember_secrets(self) -> None:
        """Общие учётки источников (пароль VPNBook) коротки для регулярок маскировки — их
        значения регистрируются явно (log.add_secrets)."""
        shared = self.store.secrets().get("shared") or {}
        log.add_secrets(str(value) for record in shared.values() if isinstance(record, dict)
                        for key, value in record.items() if key == "password")

    # --- источники ------------------------------------------------------------------------

    def _get(self, provider: str, url: str, via, mark: int | None) -> fetch.FetchResult:
        result = self.fetcher(
            url, headers={"User-Agent": self.cfg.probe.user_agent}, timeout=30.0, retries=1,
            proxy=via, mark=None if via else mark,
            bootstrap=None if via or mark is None else self.cfg.dns.resolvers,
        )
        host = (urlsplit(result.url or url).hostname or "").lower()
        if host not in providers.ORIGINS[provider]:
            raise PoolError(f"ответ с чужого хоста {host}")
        if len(result.body) > MAX_DOCUMENT:
            raise PoolError("ответ больше 8 МиБ")
        return result

    def _fetch_text(self, provider: str, url: str, via, mark) -> tuple[str | None, Status, str]:
        try:
            result = self._get(provider, url, via, mark)
        except fetch.FetchError as exc:
            return None, Status.UNAVAILABLE, masking.mask_text(str(exc))[:200]
        except PoolError as exc:
            return None, Status.SCHEMA_CHANGED, str(exc)
        if result.status == 429:
            return None, Status.RATE_LIMITED, "429 — источник просит реже"
        if result.status != 200:
            return None, Status.UNAVAILABLE, f"HTTP {result.status}"
        return result.body.decode("utf-8", "replace"), Status.SUCCESS, ""

    def poll(self, provider: str, *, via, mark: int | None) -> ProviderResult:
        """Один опрос источника (без учёта расписания)."""
        now = self.clock()
        if provider == providers.VPNGATE:
            text, status, detail = self._fetch_text(provider, providers.VPNGATE_URL, via, mark)
            if text is None:
                return ProviderResult(provider, status, retrieved_at=now, detail=detail)
            return providers.parse_vpngate(text, now=now)
        if provider == providers.VPNBOOK:
            text, status, detail = self._fetch_text(
                provider, providers.VPNBOOK_OPENVPN_URL, via, mark)
            if text is None:
                return ProviderResult(provider, status, retrieved_at=now, detail=detail)
            result = providers.parse_vpnbook_openvpn(text, now=now)
            self.sleep(REQUEST_SPACING)
            text, status, detail = self._fetch_text(
                provider, providers.VPNBOOK_OUTLINE_URL, via, mark)
            outline = (providers.parse_vpnbook_outline(text, now=now) if text is not None
                       else ProviderResult(provider, status, detail=detail))
            if outline.status is Status.SUCCESS:
                result.variants.extend(outline.variants)
            elif result.status is Status.SUCCESS:
                result.status = Status.PARTIAL
                result.complete_response = False
                result.detail = f"страница Outline: {outline.detail or outline.status}"
            return result
        return ProviderResult(provider, Status.DISABLED, retrieved_at=now)

    def _interval(self, provider: str) -> float:
        minutes = {
            providers.VPNGATE: self.cfg.free_pool.vpngate_refresh_min,
            providers.VPNBOOK: self.cfg.free_pool.vpnbook_refresh_min,
        }[provider]
        return minutes * 60.0

    def refresh_due(self, *, via, mark: int | None, force: bool = False) -> list[ProviderResult]:
        """Опросить источники, которым пора; между ними — REQUEST_SPACING."""
        results: list[ProviderResult] = []
        now = self.clock()
        way = "через подписку" if via else "напрямую"
        for provider in self.cfg.free_pool.providers:
            if not force and now < self.next_refresh.get(provider, 0.0):
                continue
            if results:
                self.sleep(REQUEST_SPACING)
            result = self.poll(provider, via=via, mark=mark)
            accepted = self.store.commit(result)
            if accepted and result.credentials:
                self._remember_secrets()
            if result.status in (Status.SUCCESS, Status.PARTIAL):
                self.failures.pop(provider, None)
                self.next_refresh[provider] = now + _due(self._interval(provider))
                self.log.info("бесплатный пул: %s — %s (%s), вариантов %d, отклонено %d%s",
                              provider, result.status, way, len(result.variants),
                              result.rejected, "" if accepted else " (снимок не заменён)")
            else:
                failures = self.failures.get(provider, 0) + 1
                self.failures[provider] = failures
                pause = min(BACKOFF_MAX, 60.0 * 2 ** (failures - 1))
                self.next_refresh[provider] = now + _due(pause)
                self.log.warning("бесплатный пул: %s — %s (%s): %s; прежний снимок остаётся, "
                                 "следующая попытка через %d мин", provider, result.status, way,
                                 result.detail or "-", int(pause // 60))
            results.append(result)
        return results

    # --- кандидаты и проверки -------------------------------------------------------------

    def variants(self) -> list[Variant]:
        found: list[Variant] = []
        for provider in self.cfg.free_pool.providers:
            found.extend(self.store.variants(provider))
        return [variant for variant in found if variant.access == Access.FREE]

    def wanted_regions(self) -> list[str]:
        pool = self.cfg.free_pool
        extra = pool.fallback_regions if pool.region_policy == "preferred" else []
        return [pool.region, *[item for item in extra if item != pool.region]]

    def _in_region(self, country: str) -> bool:
        return any(regions.allowed(country, region) for region in self.wanted_regions())

    def next_checks(self, limit: int | None, *, tunnels: bool = False) -> list[Variant]:
        """Кого проверить сейчас (None — всех по порядку): сначала с подсказкой нужного
        региона, ещё не проверенных и давно проверенных; варианты, которым нужен профиль, —
        только туннелем. Сервер OpenVPN, у которого проверяли только адрес (REACHABLE, без
        бэкенда), туннелем проверяется сразу, а не через 6 часов."""
        now = self.clock()
        state = self.store.candidates()
        ready: list[tuple[tuple, Variant]] = []
        for variant in self.variants():
            if variant.needs == "profile" and not tunnels:
                continue  # профиль VPNBook нужен только туннелю
            record = state.get(variant.variant_id, {})
            checked = float(record.get("checked_at") or 0.0)
            if tunnels and variant.backend == Backend.OPENVPN \
                    and record.get("verdict") == "REACHABLE":
                checked = 0.0
            if now - checked < CHECK_EVERY:
                continue
            hint_ok = self._in_region(variant.country_hint)
            ready.append(((not hint_ok, checked, variant.backend != Backend.XRAY,
                           variant.variant_id), variant))
        ready.sort(key=lambda item: item[0])
        return [variant for _key, variant in ready[:limit]]

    def spent_today(self) -> int:
        ledger = self.store.candidates().get("_ledger") or {}
        now = self.clock()
        return sum(int(item[1]) for item in ledger.get("items", [])
                   if isinstance(item, list) and now - float(item[0]) < DAY)

    def refresh_backend(self) -> str:
        """Годится ли бэкенд OpenVPN сейчас (backend.unavailable); при первой проверке —
        убрать следы поколений прошлого запуска демона."""
        self.backend_problem = backending.unavailable(self.paths, self.runner)
        if not self.backend_problem and not self._reconciled:
            removed = self.runtime.reconcile()
            self._reconciled = True
            if removed:
                self.log.info("бесплатный пул: убраны поколения прошлого запуска — %d", removed)
        return self.backend_problem

    def handshakes(self) -> list[list]:
        data = self.store.candidates().get("_handshakes") or {}
        now = self.clock()
        return [item for item in data.get("items", [])
                if isinstance(item, list) and len(item) == 2 and now - float(item[0]) < DAY]

    def handshake_allowed(self, provider: str) -> bool:
        """Пределы новых подключений OpenVPN (R29): в час, в сутки, в час на источник."""
        pool = self.cfg.free_pool
        now = self.clock()
        items = self.handshakes()
        hour = [item for item in items if now - float(item[0]) < HOUR]
        return (len(hour) < pool.handshakes_per_hour and len(items) < pool.handshakes_per_day
                and len([item for item in hour if item[1] == provider])
                < pool.provider_handshakes_per_hour)

    def _note_handshake(self, provider: str) -> None:
        state = self.store.candidates()
        state["_handshakes"] = {"items": [*self.handshakes(), [self.clock(), provider]]}
        self.store.save_candidates(state)

    def openvpn_material(self, variant: Variant, *, via, mark: int | None,
                         ) -> tuple[ovpn.OvpnProfile | None, str, str]:
        """Профиль и учётка для туннеля: (профиль, auth-текст, почему нельзя). VPNBook —
        профиль официальной кнопкой «Download» через несущий канал (раз в сутки) и общая
        учётка со страницы."""
        profile = variant.profile
        if variant.needs == "profile":
            text, fetched = self.store.profile(variant.variant_id)
            if not text or self.clock() - fetched > PROFILE_TTL:
                url = vpnbook_profile_url(variant)
                fetched_text, status, detail = self._fetch_text(variant.provider, url, via, mark)
                if fetched_text is None:
                    return None, "", f"профиль не скачан: {status} {detail}".strip()
                text = fetched_text
                self.store.save_profile(variant.variant_id, text)
            try:
                profile = ovpn.parse(text)
            except ovpn.OvpnRejected as exc:
                return None, "", f"профиль отклонён: {exc}"
        if profile is None:
            return None, "", "нет профиля"
        auth = ""
        if profile.needs_password:
            account = (self.store.secrets().get("shared") or {}).get(
                variant.credential_scope or variant.provider) or {}
            if variant.provider == providers.VPNGATE and not account:
                account = {"username": "vpn", "password": "vpn"}  # общий логин VPN Gate
            try:
                auth = ovpnconf.auth_text(str(account.get("username") or ""),
                                          str(account.get("password") or ""))
            except ovpn.OvpnRejected:
                return None, "", "нет учётки источника"
        return profile, auth, ""

    def _lan(self) -> tuple[str, ...]:
        from ..net import lan

        gateway = lan.gateway(self.cfg)
        return (str(gateway.network),) if gateway is not None else ()

    def check_some(self, *, mark: int | None, xray_bin: Path | None, via=None,
                   cancel=None) -> int:
        """Проверить до free_pool.checks_per_step вариантов в пределах бюджета суток; туннелем
        OpenVPN — не больше одного за шаг и в пределах рукопожатий (R26, R29)."""
        budget = (self.cfg.free_pool.budget_mb - self.cfg.free_pool.health_reserved_mb) * 1_048_576
        if self.spent_today() >= budget:
            return 0
        tunnels = not self.refresh_backend() and xray_bin is not None
        limit = self.cfg.free_pool.checks_per_step
        checked = tunnel_checks = 0
        # Все кандидаты по порядку: у источника исчерпан предел подключений — проверяются
        # следующие, а не только первые несколько.
        for variant in self.next_checks(None, tunnels=tunnels):
            if checked >= limit:
                break
            if variant.backend == Backend.XRAY:
                if xray_bin is None:
                    continue
                outcome = probing.check_xray(variant, self.cfg, xray_bin,
                                             self.paths.run / "freepool")
            elif not tunnels:
                if variant.needs:
                    continue
                outcome = probing.check_openvpn_reach(variant, mark)
            else:
                if tunnel_checks or not self.handshake_allowed(variant.provider):
                    continue
                profile, auth, why = self.openvpn_material(variant, via=via, mark=mark)
                if profile is not None and not probing.openvpn_peer(variant, profile):
                    # Без публичного IPv4 подключаться не к чему — и предел не тратится.
                    profile, why = None, "у сервера нет публичного IPv4"
                if profile is None:
                    outcome = probing.Outcome("UNTESTED", error=why[:160])
                else:
                    self._note_handshake(variant.provider)
                    tunnel_checks += 1
                    outcome = probing.check_openvpn(
                        replace(variant, profile=profile), profile, runtime=self.runtime,
                        cfg=self.cfg, xray_bin=xray_bin, run_dir=self.paths.run / "freepool",
                        auth=auth, lan=self._lan(), cancel=cancel,
                    )
            self._record(variant, outcome)
            checked += 1
        return checked

    def _record(self, variant: Variant, outcome: probing.Outcome) -> None:
        now = self.clock()
        state = self.store.candidates()
        ledger = state.get("_ledger") or {"items": []}
        ledger["items"] = [item for item in ledger.get("items", [])
                           if isinstance(item, list) and now - float(item[0]) < DAY]
        if outcome.bytes_used:
            ledger["items"].append([now, outcome.bytes_used])
        state["_ledger"] = ledger
        state[variant.variant_id] = {
            "checked_at": now, "verdict": outcome.verdict, "seconds": outcome.seconds,
            "egress_country": outcome.egress_country, "error": outcome.error[:160],
            "provider": variant.provider, "backend": variant.backend,
            "connect_seconds": outcome.connect_seconds, "bytes": outcome.bytes_used,
            "tunnel_up": outcome.tunnel_up,
        }
        self.store.save_candidates(state)
        self.log.info("бесплатный пул: проверка %s (%s, %s) — %s%s", variant.name[:48],
                      variant.backend, variant.transport, outcome.verdict,
                      f", выход {outcome.egress_country}" if outcome.egress_country else "")

    # --- сводка ---------------------------------------------------------------------------

    def summary(self) -> dict:
        """Для status.json и панели: «найдено / поддерживается / проверено / пригодно» (R51),
        по источникам — итог опроса и время, по регионам — пригодные."""
        now = self.clock()
        state = self.store.candidates()
        variants = self.variants()
        sources = []
        for provider in self.cfg.free_pool.providers:
            snap = self.store.snapshot(provider)
            attempt = snap.get("last_attempt") or {}
            sources.append({
                "id": provider, "status": attempt.get("status") or "—",
                "retrieved_at": snap.get("retrieved_at"), "attempted_at": attempt.get(
                    "retrieved_at"), "detail": attempt.get("detail") or "",
                "variants": len(snap.get("variants") or []),
                "stale": bool(snap.get("retrieved_at"))
                and now - float(snap["retrieved_at"]) > SOURCE_LEASE,
            })
        checked = [state[v.variant_id] for v in variants if v.variant_id in state]
        ready = [
            record for record in checked
            if record.get("verdict") in ("OK", "SLOW") and self._in_region(
                record.get("egress_country") or "")
        ]
        by_region: dict[str, int] = {}
        wanted = self.wanted_regions()
        for record in ready:  # Кипр — и EU, и ASIA: показываются только нужные группы
            for region in regions.regions_of(record.get("egress_country") or ""):
                if "auto" in wanted or region in wanted:
                    by_region[region] = by_region.get(region, 0) + 1
        openvpn_checked = [r for r in checked if r.get("backend") == Backend.OPENVPN]
        failures: dict[str, int] = {}
        for record in openvpn_checked:
            verdict = str(record.get("verdict") or "")
            if not record.get("tunnel_up") and verdict not in ("REACHABLE", "CLOSED",
                                                               "UNTESTED"):
                failures[verdict] = failures.get(verdict, 0) + 1
        hour = [item for item in self.handshakes() if now - float(item[0]) < HOUR]
        return {
            "openvpn_backend": self.backend_problem,
            "tunnels_up": len([r for r in openvpn_checked if r.get("tunnel_up")]),
            "tunnel_failures": failures,
            "handshakes_hour": len(hour), "handshakes_day": len(self.handshakes()),
            "mode": self.cfg.free_pool.mode, "region": self.cfg.free_pool.region,
            "region_policy": self.cfg.free_pool.region_policy,
            "found": len(variants),
            "supported_now": len([v for v in variants if v.backend == Backend.XRAY]),
            "openvpn": len([v for v in variants if v.backend == Backend.OPENVPN]),
            "checked": len(checked), "ready": len(ready), "by_region": by_region,
            "reachable_openvpn": len([r for r in checked if r.get("verdict") == "REACHABLE"]),
            "closed": len([r for r in checked if r.get("verdict") == "CLOSED"]),
            "spent_mb": round(self.spent_today() / 1_048_576, 1),
            "budget_mb": self.cfg.free_pool.budget_mb,
            "sources": sources,
        }


POOL_SOURCES = {providers.VPNGATE: "VPN Gate", providers.VPNBOOK: "VPNBook"}
POOL_STATUS = {
    "SUCCESS": "ок", "PARTIAL": "частично", "UNAVAILABLE": "недоступен",
    "RATE_LIMITED": "просит реже", "SCHEMA_CHANGED": "формат изменился",
    "DISABLED": "выключен",
    "RESOURCE_LIMIT": "слишком большой ответ",
}


def render(summary: dict, now: float) -> str:
    """`xgw pool status`: сводка наблюдения текстом."""
    mode = {"off": "выключен", "observe": "наблюдение (трафик через подписку)"}.get(
        str(summary.get("mode")), str(summary.get("mode")))
    lines = [f"Бесплатный пул: {mode}; регион {summary.get('region')} "
             f"({'строго' if summary.get('region_policy') == 'strict' else 'с запасными'})"]
    regions_text = ", ".join(f"{name} {count}" for name, count in sorted(
        (summary.get("by_region") or {}).items()))
    problem = summary.get("openvpn_backend") or ""
    lines.append(
        f"Найдено {summary.get('found', 0)}: Outline {summary.get('supported_now', 0)}"
        f", OpenVPN {summary.get('openvpn', 0)}"
        + (f" (проверка туннелем недоступна: {problem})" if problem else ""))
    if not problem:
        failures = ", ".join(f"{code} {count}" for code, count in sorted(
            (summary.get("tunnel_failures") or {}).items()))
        lines.append(
            f"OpenVPN туннелем: поднялось {summary.get('tunnels_up', 0)}"
            + (f", отказы: {failures}" if failures else "")
            + f"; подключений за час {summary.get('handshakes_hour', 0)}, за сутки "
            f"{summary.get('handshakes_day', 0)}")
    lines.append(
        f"Проверено {summary.get('checked', 0)}, пригодно {summary.get('ready', 0)}"
        + (f" ({regions_text})" if regions_text else "")
        + f"; OpenVPN с открытым адресом {summary.get('reachable_openvpn', 0)}, адрес закрыт "
        f"{summary.get('closed', 0)}")
    lines.append(f"Трафик проверок за сутки: {summary.get('spent_mb', 0)} из "
                 f"{summary.get('budget_mb', 0)} МБ")
    for source in summary.get("sources") or []:
        when = source.get("retrieved_at")
        age = f"список {int((now - float(when)) // 60)} мин назад" if when else "списка ещё нет"
        extra = [age]
        if source.get("variants"):
            extra.append(f"вариантов {source['variants']}")
        if source.get("stale"):
            extra.append("список устарел")
        if source.get("detail"):
            extra.append(str(source["detail"]))
        name = POOL_SOURCES.get(source.get("id"), source.get("id"))
        status_text = POOL_STATUS.get(source.get("status"), source.get("status"))
        lines.append(f"  {name}: {status_text} · " + " · ".join(extra))
    return "\n".join(lines)


def vpnbook_profile_url(variant: Variant) -> str:
    """Адрес официальной кнопки «Download» для профиля варианта VPNBook (М2)."""
    return providers.VPNBOOK_PROFILE_URL + "?" + urlencode(providers.vpnbook_profile_query(variant))


def run_dir(paths: Paths) -> Path:
    return paths.run / "freepool"
