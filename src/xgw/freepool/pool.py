"""Бесплатный пул в режиме наблюдения (веха М1): сбор каталогов через несущий канал, проверки
кандидатов, сводка для состояния и панели. Трафик пользователей идёт через подписку.

Несущий канал — http-in работающего Xray (engine.healthy_http_in): серверы подписки. Сайты со
списками бесплатных серверов доступны только через VPN (решение заказчика 28.10.2026). Xray не
отвечает — запрос напрямую (сокетом с меткой обхода и своими резолверами), источник может быть
закрыт — тогда UNAVAILABLE, прежний снимок остаётся.

Каждый ответ: хост после перенаправлений — из списка доверенных у источника (providers.ORIGINS),
тело — не больше 8 МиБ (R11), между запросами к источнику — не меньше 2 с. Интервалы опроса —
free_pool.*_refresh_min со сдвигом ±20 % (R12); после ошибки — пауза 1, 2, 4… 60 минут.

Списки GitHub (providers.LIST_PROVIDERS) — так же через несущий канал (файлы — десятки КБ, раз в
free_pool.lists_refresh_min), а проверки их серверов — без бюджета трафика суток, своим числом
за шаг (free_pool.list_checks_per_step) и чаще (LIST_CHECK_EVERY): решение заказчика 28.10.2026.

Туннели — с вехи М2в серверы SSTP VPN Gate (OpenVPN убран 29.10.2026 по решению заказчика):
пределы подключений R29 и порядок проверки — прежние, вход — общий «vpn»/«vpn».
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from .. import fetch, log, masking
from ..config import Config
from ..net import cmd
from ..paths import Paths
from . import backend as backending
from . import probe as probing
from . import providers, regions
from . import traffic as trafficking
from .models import Access, Backend, ProviderResult, Status, Variant
from .store import PoolStore

MAX_DOCUMENT = 8 * 1024 * 1024
REQUEST_SPACING = 2.0
BACKOFF_MAX = 3600.0
JITTER = 0.2
CHECK_EVERY = 6 * 3600.0  # проверенный вариант снова — не раньше
# Сервер списка GitHub — чаще: списки обновляются раз в 2–4 часа, серверы живут недолго, а
# трафик их проверок не бережётся (решение заказчика 28.10.2026).
LIST_CHECK_EVERY = 2 * 3600.0
DAY = 86400.0
HOUR = 3600.0
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
        self.resolve: probing.Resolver = fetch.resolve_domain  # имена серверов (server_hosts)
        self.log = logger or log.get_logger("freepool")
        self.clock = clock
        self.fetcher = fetcher
        self.sleep = sleep
        self.next_refresh: dict[str, float] = {}
        self.failures: dict[str, int] = {}
        self._lock = threading.Lock()
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
        try:
            retired = self.store.retire_openvpn()
        except OSError as exc:
            self.log.warning("бесплатный пул: остатки OpenVPN не удалены: %s", exc)
            return
        if retired:
            self.log.info("бесплатный пул: OpenVPN убран (веха М2в) — удалены %s",
                          ", ".join(retired))

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
            # С вехи М2в — только ключи Outline (страница OpenVPN и её учётка не нужны).
            text, status, detail = self._fetch_text(
                provider, providers.VPNBOOK_OUTLINE_URL, via, mark)
            if text is None:
                return ProviderResult(provider, status, retrieved_at=now, detail=detail)
            return providers.parse_vpnbook_outline(text, now=now)
        if provider in providers.LIST_URLS:
            return self._poll_list(provider, via=via, mark=mark, now=now)
        return ProviderResult(provider, Status.DISABLED, retrieved_at=now)

    def _poll_list(self, provider: str, *, via, mark: int | None, now: float) -> ProviderResult:
        """Список GitHub: все его файлы (через несущий канал, как каталоги); не скачался
        один — PARTIAL, ни одного — итог первой ошибки (прежний снимок остаётся)."""
        documents: list[tuple[str, str]] = []
        problems: list[tuple[Status, str]] = []
        for index, url in enumerate(providers.LIST_URLS[provider]):
            if index:
                self.sleep(REQUEST_SPACING)
            text, status, detail = self._fetch_text(provider, url, via, mark)
            if text is None:
                problems.append((status, detail))
            else:
                documents.append((url, text))
        if not documents:
            status, detail = problems[0]
            return ProviderResult(provider, status, retrieved_at=now, detail=detail)
        result = providers.parse_link_list(provider, documents, now=now)
        if problems and result.status is Status.SUCCESS:
            result.status = Status.PARTIAL
            result.complete_response = False
            result.detail = f"файл списка не скачан: {problems[0][0]} {problems[0][1]}".strip()
        return result

    def _interval(self, provider: str) -> float:
        if provider in providers.LIST_PROVIDERS:
            return self.cfg.free_pool.lists_refresh_min * 60.0
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
        if any(result.status in (Status.SUCCESS, Status.PARTIAL) for result in results):
            self._prune_candidates()
        return results

    def _prune_candidates(self) -> None:
        """Итоги проверок вариантов, которых нет ни в одном снимке, — убрать: списки GitHub
        меняются каждые несколько часов, и candidates.json рос бы без конца."""
        state = self.store.candidates()
        current = {variant.variant_id for variant in self.variants()}
        kept = {key: value for key, value in state.items()
                if key.startswith("_") or key in current}
        if len(kept) < len(state):
            self.store.save_candidates(kept)

    # --- кандидаты и проверки -------------------------------------------------------------

    def variants(self) -> list[Variant]:
        found: list[Variant] = []
        for provider in self.cfg.free_pool.providers:
            found.extend(self.store.variants(provider))
        return [variant for variant in found if variant.access == Access.FREE]

    def wanted_regions(self) -> list[str]:
        return trafficking.wanted_regions(self.cfg)

    def _in_region(self, country: str) -> bool:
        return any(regions.allowed(country, region) for region in self.wanted_regions())

    def next_checks(self, limit: int | None, *, tunnels: bool = False) -> list[Variant]:
        """Кого проверить сейчас (None — всех по порядку): сначала с подсказкой нужного
        региона, ещё не проверенных и давно проверенных. Сервер SSTP, у которого проверяли
        только адрес (REACHABLE, без бэкенда), туннелем проверяется сразу, а не через 6 часов."""
        now = self.clock()
        state = self.store.candidates()
        ready: list[tuple[tuple, Variant]] = []
        for variant in self.variants():
            record = state.get(variant.variant_id, {})
            checked = float(record.get("checked_at") or 0.0)
            if tunnels and variant.backend == Backend.SSTP \
                    and record.get("verdict") == "REACHABLE":
                checked = 0.0
            every = LIST_CHECK_EVERY if variant.provider in providers.LIST_PROVIDERS \
                else CHECK_EVERY
            if now - checked < every:
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
        """Годится ли бэкенд туннелей сейчас (backend.unavailable); при первой проверке —
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
        """Пределы новых подключений туннелей (R29): в час, в сутки, в час на источник."""
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

    def _lan(self) -> tuple[str, ...]:
        from ..net import lan

        gateway = lan.gateway(self.cfg)
        return (str(gateway.network),) if gateway is not None else ()

    def check_some(self, *, mark: int | None, xray_bin: Path | None, via=None,
                   cancel=None) -> int:
        """Проверить до free_pool.checks_per_step вариантов каталогов в пределах бюджета
        суток; туннелем SSTP — не больше одного за шаг и в пределах рукопожатий (R26, R29).
        Серверы списков GitHub — сверх этого, до free_pool.list_checks_per_step за шаг и без
        бюджета (решение заказчика 28.10.2026: экономия трафика для них не нужна)."""
        budget = (self.cfg.free_pool.budget_mb - self.cfg.free_pool.health_reserved_mb) * 1_048_576
        limits = {
            "catalog": self.cfg.free_pool.checks_per_step if self.spent_today() < budget else 0,
            "list": self.cfg.free_pool.list_checks_per_step,
        }
        if not any(limits.values()):
            return 0
        tunnels = not self.refresh_backend() and xray_bin is not None
        done = {"catalog": 0, "list": 0}
        tunnel_checks = 0
        # Все кандидаты по порядку: у источника исчерпан предел подключений — проверяются
        # следующие, а не только первые несколько.
        for variant in self.next_checks(None, tunnels=tunnels):
            if all(done[kind] >= limits[kind] for kind in done):
                break
            if cancel is not None and cancel.is_set():
                break
            kind = "list" if variant.provider in providers.LIST_PROVIDERS else "catalog"
            if done[kind] >= limits[kind]:
                continue
            tunnel = False
            if variant.backend in (Backend.XRAY, Backend.SINGBOX):
                proxied = self._check_proxy(variant, mark=mark, xray_bin=xray_bin)
                if proxied is None:
                    continue
                outcome = proxied
            elif not tunnels:
                outcome = probing.check_tunnel_reach(variant, mark)
            else:
                if tunnel_checks or not self.handshake_allowed(variant.provider):
                    continue
                if not probing.tunnel_peer(variant):
                    # Без публичного IPv4 подключаться не к чему — и предел не тратится.
                    outcome = probing.Outcome("UNTESTED", error="у сервера нет публичного IPv4")
                else:
                    self._note_handshake(variant.provider)
                    tunnel_checks += 1
                    tunnel = True
                    assert xray_bin is not None
                    outcome = probing.check_tunnel(
                        variant, runtime=self.runtime, cfg=self.cfg, xray_bin=xray_bin,
                        run_dir=self.paths.run / "freepool", user=providers.VPNGATE_USER,
                        password=providers.VPNGATE_PASSWORD, lan=self._lan(), cancel=cancel,
                    )
            self._record(variant, outcome, tunnel=tunnel)
            done[kind] += 1
        return sum(done.values())

    def _check_proxy(self, variant: Variant, *, mark: int | None,
                     xray_bin: Path | None) -> probing.Outcome | None:
        """Сервер Xray или sing-box временным процессом; адрес — только публичный
        (server_hosts). None — проверить сейчас нечем (нет Xray): вариант ждёт."""
        if variant.backend == Backend.XRAY and xray_bin is None:
            return None
        hosts, why = probing.server_hosts(variant, self.cfg, mark, resolve=self.resolve)
        if why:
            return probing.Outcome("UNTESTED", error=why[:160])
        run = self.paths.run / "freepool"
        if variant.backend == Backend.XRAY:
            assert xray_bin is not None
            return probing.check_xray(variant, self.cfg, xray_bin, run, hosts=hosts)
        from ..generator import singbox

        singbox_bin = singbox.find_binary(paths=self.paths)
        if singbox_bin is None:
            return probing.Outcome("UNTESTED", error="нет sing-box (ставит xgw install)")
        return probing.check_singbox(variant, self.cfg, singbox_bin, run, hosts=hosts)

    def _record(self, variant: Variant, outcome: probing.Outcome, *, tunnel: bool = False) -> None:
        """Итог проверки варианта. tunnel — это было подключение туннеля: оно идёт и в журнал
        туннелей за сутки (_tunnels), который, в отличие от итогов по вариантам, не теряет
        записи серверов, ушедших из списка VPN Gate (отчёт М2в.1: сводка показывала 2–3 попытки
        при 18 настоящих)."""
        now = self.clock()
        state = self.store.candidates()
        # Трафик проверок серверов списков — отдельно: в бюджет суток он не входит.
        key = "_list_ledger" if variant.provider in providers.LIST_PROVIDERS else "_ledger"
        ledger = state.get(key) or {"items": []}
        ledger["items"] = [item for item in ledger.get("items", [])
                           if isinstance(item, list) and now - float(item[0]) < DAY]
        if outcome.bytes_used:
            ledger["items"].append([now, outcome.bytes_used])
        state[key] = ledger
        if tunnel:
            state["_tunnels"] = {"items": [
                *self._tunnels(state), [now, outcome.verdict, 1 if outcome.tunnel_up else 0]]}
        state[variant.variant_id] = {
            "checked_at": now, "verdict": outcome.verdict, "seconds": outcome.seconds,
            "egress_country": outcome.egress_country, "error": outcome.error[:160],
            "provider": variant.provider, "backend": variant.backend,
            "connect_seconds": outcome.connect_seconds, "bytes": outcome.bytes_used,
            "tunnel_up": outcome.tunnel_up,
            "diagnosis": outcome.diagnosis[:probing.DIAGNOSIS_MAX],
        }
        self.store.save_candidates(state)
        self.log.info("бесплатный пул: проверка %s (%s, %s) — %s%s%s", variant.name[:48],
                      variant.backend, variant.transport, outcome.verdict,
                      f", выход {outcome.egress_country}" if outcome.egress_country else "",
                      f"; изнутри: {outcome.diagnosis}" if outcome.diagnosis else "")

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
        # Подключения туннелей за сутки — по журналу, а не по итогам вариантов из снимков.
        tunnels = self._tunnels(state)
        failures: dict[str, int] = {}
        for _when, verdict, up in tunnels:
            if not up:
                failures[verdict] = failures.get(verdict, 0) + 1
        day_items = self.handshakes()
        day_limit = self.cfg.free_pool.handshakes_per_day
        hour = [item for item in day_items if now - float(item[0]) < HOUR]
        ready_by_source: dict[str, int] = {}
        for record in ready:
            source = str(record.get("provider") or "")
            ready_by_source[source] = ready_by_source.get(source, 0) + 1
        listed = [v for v in variants if v.provider in providers.LIST_PROVIDERS]
        return {
            # Когда сводка посчитана: по нему панель берёт заново список серверов (/api/pool).
            "computed_at": now,
            "tunnel_backend": self.backend_problem,
            "tunnel_attempts": len(tunnels),
            "tunnels_up": len([item for item in tunnels if item[2]]),
            "tunnel_failures": failures,
            "handshakes_hour": len(hour), "handshakes_day": len(day_items),
            "handshakes_day_limit": day_limit,
            # Суточный предел занят (отчёт М2а.3: ночное наблюдение исчерпало его к утру) —
            # когда освободится следующее подключение: окно скользящее, 24 ч от самого старого.
            "handshakes_free_at": (min(float(item[0]) for item in day_items) + DAY
                                   if day_items and len(day_items) >= day_limit else 0.0),
            "mode": self.cfg.free_pool.mode, "region": self.cfg.free_pool.region,
            "region_policy": self.cfg.free_pool.region_policy,
            "found": len(variants),
            "supported_now": len([v for v in variants
                                  if v.backend in (Backend.XRAY, Backend.SINGBOX)]),
            "lists": len(listed),
            "lists_singbox": len([v for v in listed if v.backend == Backend.SINGBOX]),
            "outline": len([v for v in variants if v.backend == Backend.XRAY
                            and v.provider not in providers.LIST_PROVIDERS]),
            "sstp": len([v for v in variants if v.backend == Backend.SSTP]),
            "checked": len(checked), "ready": len(ready), "by_region": by_region,
            "ready_by_source": ready_by_source,
            "reachable_tunnel": len([r for r in checked if r.get("verdict") == "REACHABLE"]),
            "closed": len([r for r in checked if r.get("verdict") == "CLOSED"]),
            "spent_mb": round(self.spent_today() / 1_048_576, 1),
            "budget_mb": self.cfg.free_pool.budget_mb,
            "lists_spent_mb": round(self._spent(state, "_list_ledger") / 1_048_576, 1),
            "sources": sources,
        }

    def _tunnels(self, state: dict) -> list[list]:
        """Подключения туннелей за сутки: [время, вердикт, 1 — туннель поднимался]."""
        now = self.clock()
        return [item for item in (state.get("_tunnels") or {}).get("items", [])
                if isinstance(item, list) and len(item) == 3 and now - float(item[0]) < DAY]

    def _spent(self, state: dict, key: str) -> int:
        now = self.clock()
        return sum(int(item[1]) for item in (state.get(key) or {}).get("items", [])
                   if isinstance(item, list) and now - float(item[0]) < DAY)


def server_rows(cfg: Config, paths: Paths, now: float, *,
                store: PoolStore | None = None) -> list[dict]:
    """Серверы пула для панели — вкладка «Бесплатные серверы», как серверы подписок: по строке
    на вариант — страна, протокол, итог последней проверки шлюза, когда перепроверка и почему
    сервер не допущен к трафику устройств (traffic.refusal). Ссылки, ключи и outbound'ы сюда не
    попадают. Наблюдение выключено — пусто: пул тогда серверы не проверяет."""
    if cfg.free_pool.mode == "off":
        return []
    store = store or PoolStore(paths)
    records = store.candidates()
    rows: list[dict] = []
    seen: set[str] = set()
    for provider in cfg.free_pool.providers:
        every = LIST_CHECK_EVERY if provider in providers.LIST_PROVIDERS else CHECK_EVERY
        for variant in store.variants(provider):
            key = variant.variant_id
            if variant.access != Access.FREE or key in seen:
                continue
            seen.add(key)
            found = records.get(key)
            record = found if isinstance(found, dict) else {}
            checked = float(record.get("checked_at") or 0.0)
            verdict = str(record.get("verdict") or "") if checked else ""
            egress = str(record.get("egress_country") or "").upper() if checked else ""
            seconds = float(record.get("seconds") or 0.0)
            connect = float(record.get("connect_seconds") or 0.0)
            rows.append({
                "id": key, "source": provider,
                "name": (variant.name or f"{variant.host or variant.address}:{variant.port}")[:80],
                "protocol": variant.protocol, "backend": variant.backend,
                # Страна выхода — по проверке шлюза; пока её нет — подсказка каталога.
                "country": egress or variant.country_hint.upper(), "egress": bool(egress),
                "verdict": verdict, "checked_at": checked or None,
                "next_at": checked + every if checked else None,
                # Проба целиком (рукопожатия и файл), как задержка запасных серверов подписки.
                "delay_ms": round(seconds * 1000) if verdict in ("OK", "SLOW") and seconds
                else None,
                "tunnel_up": bool(record.get("tunnel_up")),
                "connect_s": round(connect, 1) if connect else None,
                "error": str(record.get("error") or "")[:160] if checked else "",
                "why": trafficking.refusal(cfg, variant, found, now),
            })
    return rows


POOL_SOURCES = {
    providers.VPNGATE: "VPN Gate", providers.VPNBOOK: "VPNBook",
    providers.IGARECK: "GitHub igareck (проверены в России)",
    providers.MAHDIBLAND: "GitHub mahdibland",
}
POOL_STATUS = {
    "SUCCESS": "ок", "PARTIAL": "частично", "UNAVAILABLE": "недоступен",
    "RATE_LIMITED": "просит реже", "SCHEMA_CHANGED": "формат изменился",
    "DISABLED": "выключен",
    "RESOURCE_LIMIT": "слишком большой ответ",
}


def _quota_text(free_at: float) -> str:
    """Суточный предел подключений туннелей занят — с какого времени снова можно."""
    if not free_at:
        return ""
    return (" — суточный предел занят, следующее после "
            + time.strftime("%d.%m %H:%M", time.localtime(free_at)))


def render(summary: dict, now: float) -> str:
    """`xgw pool status`: сводка наблюдения текстом."""
    mode = {"off": "выключен", "observe": "наблюдение (трафик через подписку)"}.get(
        str(summary.get("mode")), str(summary.get("mode")))
    lines = [f"Бесплатный пул: {mode}; регион {summary.get('region')} "
             f"({'строго' if summary.get('region_policy') == 'strict' else 'с запасными'})"]
    regions_text = ", ".join(f"{name} {count}" for name, count in sorted(
        (summary.get("by_region") or {}).items()))
    problem = summary.get("tunnel_backend") or ""
    lines.append(
        f"Найдено {summary.get('found', 0)}: из списков GitHub {summary.get('lists', 0)}"
        f" (из них только sing-box {summary.get('lists_singbox', 0)}), Outline "
        f"{summary.get('outline', 0)}, SSTP (VPN Gate) {summary.get('sstp', 0)}"
        + (f" (проверка туннелем недоступна: {problem})" if problem else ""))
    if not problem:
        failures = ", ".join(f"{code} {count}" for code, count in sorted(
            (summary.get("tunnel_failures") or {}).items()))
        lines.append(
            f"SSTP туннелем за сутки: попыток {summary.get('tunnel_attempts', 0)}, поднялось "
            f"{summary.get('tunnels_up', 0)}"
            + (f", отказы: {failures}" if failures else "")
            + f"; подключений за час {summary.get('handshakes_hour', 0)}, за сутки "
            f"{summary.get('handshakes_day', 0)} из {summary.get('handshakes_day_limit', '?')}"
            + _quota_text(float(summary.get("handshakes_free_at") or 0)))
    lines.append(
        f"Проверено {summary.get('checked', 0)}, пригодно {summary.get('ready', 0)}"
        + (f" ({regions_text})" if regions_text else "")
        + f"; SSTP с открытым адресом {summary.get('reachable_tunnel', 0)}, адрес закрыт "
        f"{summary.get('closed', 0)}")
    by_source = ", ".join(f"{POOL_SOURCES.get(name, name)} {count}" for name, count in sorted(
        (summary.get("ready_by_source") or {}).items()))
    if by_source:
        lines.append(f"Пригодные по источникам: {by_source}")
    lines.append(f"Трафик проверок за сутки: {summary.get('spent_mb', 0)} из "
                 f"{summary.get('budget_mb', 0)} МБ; серверы списков GitHub — "
                 f"{summary.get('lists_spent_mb', 0)} МБ (без предела)")
    flow = summary.get("traffic")
    if isinstance(flow, dict):
        lines.append(trafficking.text(flow))
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


def run_dir(paths: Paths) -> Path:
    return paths.run / "freepool"
