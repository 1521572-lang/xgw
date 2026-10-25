"""Демон XGW (xgw.service): watchdog, подписки, сканы запасных, замена участников.

Переключением серверов управляет только Xray. Демон раз в interval_s (±20 %)
собирает сигналы — метрики observatory, сквозную загрузку через http-in и
доступность провайдера, — ведёт машину состояний и делает то, что ядро само
не умеет: обновляет подписки, применяет изменения, сканирует запасные и
меняет «мёртвых» участников (раздел 6.8). Ещё он ведёт классы серверов (cost.py:
ручной приоритет, затем стоимость — безлимитные, лимитированные x1, x10…): переходит на
класс хуже, когда на нынешнем живых нет (на лимитированные — не дороже x1, MEMBER_COST_MAX),
возвращается выше, когда сервер того класса снова проходит проверку, и подбирает балансировщику
резервный выход — лимитированный сервер, через который трафик идёт, пока участники
мертвы (_reserve_step). С 0.1.9 он же держит «основной» сервер — самый быстрый по замеру
скорости — и закрепляет его в ядре, чтобы выход не скакал между серверами (_main_step,
watch/speed.py); при отказе основного трафик сразу получает другой живой участник.

Один поток, один шаг за раз: применение конфига идёт под файловой блокировкой
и не пересекается с командами CLI. Каждое обращение наружу — отдельный метод
(`_read_observatory`, `_check_e2e`, …): в тестах они подменяются.
"""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import datetime
import ipaddress
import json
import os
import random
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from enum import StrEnum
from pathlib import Path

from . import cores, cost, engine, fetch, log, priority
from . import pin as pinning
from . import tailscale as ts
from .apply.applier import ApplyOutcome, in_restart_window
from .apply.rotation import (
    REPLACE_NOW_VERDICTS,
    REPLACEABLE_VERDICTS,
    Rotation,
    plan_rotation,
    preferred_members,
)
from .config import Config, parse_seconds
from .generator import builder
from .generator import profiles as profiling
from .generator import singbox as singboxing
from .generator.builder import BALANCER_TAG, NodeInfo
from .net import tun
from .net.capture import capture_inbounds
from .paths import Paths
from .store import Store
from .watch import checks, scan, speed, status, target
from .watch import guard as speedguard
from .watch import hosts as probehosts
from .watch import resolvers as resolving
from .watch.notify import Notifier
from .watch.scan import RESERVE_CANDIDATES, RESERVE_RECHECK
from .watch.states import Signals, State, StateMachine, action_text
from .xraycore import binary, metrics
from .xraycore.api import ApiError
from .xraycore.service import XrayServiceError

LEAK_INTERVAL = 300.0  # проверка утечки — раз в 5 минут
WAN_DOWN_INTERVAL = 60.0  # при недоступном провайдере проверки раз в 60 с
ALL_DEAD_RETRY = 300.0  # как часто повторять внеочередное обновление, пока все мертвы
SCAN_BUDGET = 8.0  # секунд на сканы за один шаг: watchdog не должен надолго замирать
RESCAN_PAUSE = 60.0  # внеочередной скан запасных — не чаще
SUBSCRIPTION_RETRY = 120.0  # повтор опроса подписок после неудачи
PROVIDER_DNS_TTL = 600.0
ROLLBACK_AFTER = 2  # «после двух неудач — откат на last-good»
FAIL_OPEN_AFTER = 60.0  # fail_mode = "open": Xray недоступен дольше — снять перехват
WAIT_SLICE = 0.25  # как часто пауза между шагами смотрит, не пора ли проснуться
# Событие сети (watch/events.py) будит полный шаг не чаще этого: смена Wi-Fi или
# переподключение WAN дают десятки строк `ip monitor` за несколько секунд, а у шага есть
# сквозная проба. Ранние события не теряются — шаг лишь ждёт конца паузы. Дольше нельзя:
# WAN вернулся через секунды после падения — шаг нужен сразу, а не через паузу.
NET_WAKE_PAUSE = 2.0
MANUAL_SCAN_PAUSE = 1.0  # проверка по кнопке идёт подряд, не дожидаясь шага watchdog
PROBE_TARGET_RECHECK = 300.0  # как часто перепроверять, отвечает ли сам probe.url
PROBE_WORKERS = 8  # пробы для этой перепроверки идут одновременно: шаг не должен зависать
# Работают серверы класса хуже лучшего — запасные классов лучше проверяются не реже
# этого: вернуться к ним нужно скоро после того, как они снова заработают.
TIER_RESCAN = 300.0
# Дороже этого множителя лимитированные участниками не становятся, когда безлимитные
# мертвы (_switch_tier): участников ядро пробует probe.url каждые probe.interval, и проба
# 57 КБ раз в 30 с через x100 — ~16 ГБ квоты в сутки на сервер. Такие остаются резервным
# выходом: через него идёт только сам трафик.
MEMBER_COST_MAX = 1.0
# Выбранный вручную запасной перестал отвечать — собственная проба не чаще этого: трафик
# тем временем ведёт автовыбор (_manual_step). Участника пробует само ядро.
PIN_RECHECK = 120.0
# В класс дороже нынешнего (с безлимитных на лимитированные) — не раньше, чем трафик
# столько несёт резервный: после короткого сбоя (провайдер моргнул) ядро само вернёт
# трафик безлимитным за один цикл проб, а с лимитированных назад — только перепроверка
# безлимитных (TIER_RESCAN). Трафик не идёт вовсе (ALL_DEAD) — без ожидания.
COSTLIER_AFTER = 120.0
# Резервный выход и кандидаты на его место проверяются дешёвым запросом раз в
# RESERVE_RECHECK (по RESERVE_CANDIDATES лучших, см. watch/scan.py), а когда трафик не
# идёт и через резервный (ALL_DEAD) — сразу и все. Итог перепроверки ждём не дольше
# RESERVE_ROUND_WAIT.
RESERVE_ROUND_WAIT = 600.0
RESERVE_RETRY = 1800.0  # пока трафик несёт резервный, подписка опрашивается внеочередно не чаще
# Уведомления (рабочий стол) — только когда от человека нужно действие или
# трафик идёт не так, как он ждёт. Остальное шлюз чинит сам: замены серверов, смена
# уровня, «часть серверов недоступна», «снова отвечает» — это события в журнале (панель,
# `xgw status`, /status бота), без уведомления.
ALERT_STATES = frozenset({
    State.ALL_DEAD, State.XRAY_DOWN, State.WAN_DOWN, State.LEAK,
    State.PROBE_TARGET_UNREACHABLE,
})
# Трафик несёт резервный дольше этого — событие в журнале (без уведомления: интернет
# работает, действий от человека не нужно); короткий переход (секунды, пока ядро не
# увидит, что участник ожил) не стоит и события.
RESERVE_NOTE_AFTER = 300.0
# Подписка не обновляется дольше этого — уведомить: разовый сбой провайдера подписки
# повода не даёт, а долгий — значит, что-то с ней не так (истекла, сменился адрес).
SUBSCRIPTION_ALERT_AFTER = 3600.0
# Основной сервер (_main_step). С сервера, ушедшего в отказ, основной уходит сразу, и
# снова основным он не берётся MAIN_COOLDOWN, пока есть другие живые участники.
MAIN_COOLDOWN = 1800.0
# Загрузка не прошла через основной, и через новый — тоже, не позже MAIN_CAROUSEL после
# смены: дело, видимо, не в серверах (не отвечает адрес проверки, сбой у провайдера).
# Перебирать участников по кругу незачем — закрепление снимается, сервер выбирает ядро,
# как до 0.1.9, пока загрузка снова не пройдёт.
MAIN_CAROUSEL = 120.0
SPEED_FRESH = 2  # замер годен 2 срока замера своего класса (speed.every_hours)
SPEED_KEEP = 7 * 86400.0  # результаты замеров старше не хранятся
# Канал занят: через серверы идёт больше этого (байт/с, ~2 Мбит/с) — фоновый замер отложен
# до следующего шага: чужая загрузка исказила бы его, а замер — мешал бы ей. Но не дольше
# SPEED_FORCE_AFTER: на домашнем шлюзе фоновый трафик идёт почти всегда, и иначе замеров
# не было бы вовсе (issue #1). Замер по кнопке занятость канала не ждёт.
SPEED_BUSY_BPS = 250_000
SPEED_FORCE_AFTER = 3600.0
# Фоновые замеры — по одному за шаг: шаг watchdog не должен затягиваться (по нему
# замечают отказы), а круг по 70 серверам и так укладывается в полчаса. По кнопке — подряд,
# пока шаг не займёт столько секунд (один — всегда).
SPEED_STEP_SECONDS = 10.0
# Шаг, в котором уже шёл скан, берёт не больше одного замера: заказанный (кнопкой, контролем
# скорости) — сразу, фоновый — если шага без скана не было столько секунд. Пробы профилей
# бывают на каждом шаге: испытание 0.1.18 (25.10.2026) — кнопка ↻ «крутится, но не
# обновляется», фоновых замеров не было вовсе.
SPEED_SCAN_WAIT = 600.0
# Запасной, который быстрее основного, переводится в работу и становится основным; если
# за это время он так и не встал в работу (конфиг ждёт окна перезапуска и т. п.) — отбой.
PROMOTE_WAIT = 3600.0
# Профили обхода (generator/profiles.py, fragment.mode = "auto"). Запасной, который не отвечает
# так, как не отвечают при блокировке ТСПУ, проверяется в других профилях по лестнице: Xray с
# дроблением ClientHello, обычный sing-box (0.1.13), sing-box с дроблением TLS, sing-box с
# мультиплексированием и паддингом (при «заморозке»). Помогло — профиль закрепляется, нет —
# возвращается прежний, а следующая попытка для этого сервера — не раньше PROFILE_RETRY. Сервер
# на обученном профиле, который отвечает, раз в PROFILE_RECHECK пробуется на базовом: профили
# тяжелее (дробление удлиняет рукопожатие, мост к sing-box — лишнее звено), и, если провайдер
# перестал блокировать, они лишние.
PROFILE_RETRY = 6 * 3600.0
PROFILE_RECHECK = 24 * 3600.0
# Незавершённые пробы профилей и время последней смены профиля — в базе (ключ meta), а не только
# в памяти: иначе после перезапуска демона посреди пробы пробный профиль принимался за выученный
# (отчёт 0.1.13, наблюдения 2–3), а отсчёт PROFILE_RETRY и PROFILE_RECHECK начинался заново.
TRIALS_META = profiling.TRIALS_META
SINGBOX_RETRY = 1800.0  # sing-box не поднялся и серверы ушли на Xray — пробовать снова так часто
# Обновление ядер из панели (cores.py): первая проверка выпусков на GitHub — через 5 минут после
# запуска демона (сам срок, раз в сутки, хранится в cores-check.json и переживает перезапуски),
# дальше демон сверяется с ним раз в 10 минут. В сутки наблюдения после обновления ядро,
# которое не отвечает и после отката конфига на last-good ещё CORE_BACK_AFTER шагов, заменяется
# прежним; sing-box после такого возврата демон пробует поднять через CORE_RECOVER секунд.
CORES_FIRST_CHECK = 300.0
CORES_RECHECK = 600.0
# Фоновые проверки сети (0.1.18, ТЗ R4): bootstrap-DNS — раз в dns.bootstrap_check_minutes
# (первая — через NETMON_FIRST после запуска), серверы DERP Tailscale напрямую — раз в
# DERP_CHECK. Обратно на прямой путь tailscaled идёт после DERP_BACK удачных проверок подряд.
NETMON_FIRST = 120.0
DERP_CHECK = 300.0
DERP_BACK = 2
CORE_BACK_AFTER = 2
CORE_RECOVER = 120.0


@dataclasses.dataclass
class ProfileTrial:
    """Профиль, в котором сервер проверяется сейчас."""

    profile: str
    rest: list[str]  # ступени лестницы, которые проверятся, если эта не поможет
    prev: str  # профиль до проверки: если не помог ни один, сервер возвращается в него
    probe_tag: str
    since: float
    recheck: bool = False  # возврат на базовый профиль, а не проба новой ступени
    verdict: str = ""  # вердикт скана, из-за которого сервер перевели (для события и панели)
    # Сервер в работе проверяется на ступенях дробления на месте, без замены (ТЗ R1): пока
    # проба идёт, замена его ждёт; не ответил ни на одной — заменяется.
    escalate: bool = False


@dataclasses.dataclass
class ProfileWish:
    """Решение о профиле сервера, ждущее применения (_profile_step)."""

    profile: str
    trial: bool
    rest: list[str]
    prev: str
    recheck: bool = False
    verdict: str = ""
    escalate: bool = False


UDP_PROTOCOLS = ("hysteria2", "hysteria", "tuic", "wireguard")


def _transport(node) -> str:
    """tcp или udp: по чему сервер связывается с клиентом (QUIC и WireGuard — по UDP)."""
    return "udp" if node.protocol in UDP_PROTOCOLS else "tcp"


def _server_text(name: str, tag: str) -> str:
    """Сервер в событиях обхода — имя и тег. Имя бывает одним на десяток серверов подписки, а
    его хвост маскируется: перепроверка 0.1.18 (25.10.2026) — двенадцать «🚀Авто | Лучший
    сервер» по очереди выглядели как один сервер, эскалация которого идёт каждую минуту."""
    return f"«{name}» ({tag})"


def _keep_text(trial: ProfileTrial) -> str:
    new, old = trial.profile, trial.prev
    if new == profiling.XRAY_FRAGMENT and old == profiling.XRAY_DEFAULT:
        return "отвечает только с дроблением ClientHello — оно включено"
    if new == profiling.XRAY_SPLIT and old == profiling.XRAY_DEFAULT:
        return "отвечает только с нарезкой первых пакетов — она включена"
    if new == profiling.XRAY_DEFAULT and old == profiling.XRAY_FRAGMENT:
        return "отвечает и без дробления ClientHello — оно выключено"
    if new == profiling.XRAY_DEFAULT and old == profiling.XRAY_SPLIT:
        return "отвечает и без нарезки первых пакетов — она выключена"
    if trial.recheck:
        return (f"отвечает и на профиле «{profiling.NAMES[new]}» — он возвращён "
                f"(был «{profiling.NAMES[old]}»)")
    return (f"отвечает на профиле «{profiling.NAMES[new]}» — он закреплён "
            f"(был «{profiling.NAMES[old]}»)")


def _fail_text(trial: ProfileTrial) -> str:
    new, old = trial.profile, trial.prev
    if new in profiling.XRAY_FRAGMENTS and old == profiling.XRAY_DEFAULT:
        return "не отвечает и с дроблением ClientHello — оно выключено"
    if new == profiling.XRAY_DEFAULT and old == profiling.XRAY_FRAGMENT:
        return "без дробления ClientHello не отвечает — оно включено снова"
    if new == profiling.XRAY_DEFAULT and old == profiling.XRAY_SPLIT:
        return "без нарезки первых пакетов не отвечает — она включена снова"
    if trial.recheck:
        return (f"на профиле «{profiling.NAMES[new]}» не отвечает — возвращён "
                f"«{profiling.NAMES[old]}»")
    return (f"не отвечает ни на одном профиле — возвращён «{profiling.NAMES[old]}», следующая "
            "попытка через 6 ч")


def checks_interval(cfg: Config) -> int:
    """probe.interval в секундах (как часто ядро пробует участников); не разобрать — 30."""
    return parse_seconds(cfg.probe.interval) or 30


def jitter(seconds: float, spread: float = 0.2) -> float:
    """Интервал со сдвигом ±20 %: строго периодические запросы заметны со стороны."""
    return seconds * random.uniform(1.0 - spread, 1.0 + spread)


def tier_text(old: cost.Klass, new: cost.Klass, *, up: bool) -> str:
    """Событие о смене класса участников. Классы с одной стоимостью различаются только
    уровнем приоритета — тогда и говорится об уровнях, как в 0.1.7."""
    if old.cost == new.cost:
        was, now = priority.level_name(old.rank), priority.level_name(new.rank)
        head = f"сервер уровня «{now}» снова отвечает" if up else (
            f"на уровне «{was}» живых серверов нет"
        )
        return f"{head} — в работе серверы уровня «{now}» (были — «{was}»)"
    ranked = old.rank != new.rank
    head = "снова отвечают серверы лучшего класса" if up else "живых серверов нет"
    return (
        f"{head} — в работе {cost.class_name(new, ranked)} "
        f"(были — {cost.class_name(old, ranked)})"
    )


def stranded_action(tier: cost.Klass, ranked: bool) -> str:
    """Текст DEGRADED, когда мёртвого участника заменить некем (Daemon._stranded): «замена на
    запасные» была бы неправдой (разбор 24.10.2026, ASSUMPTIONS п. 235)."""
    return (
        "часть серверов недоступна, а заменить их некем: среди запасных нет серверов того же "
        f"класса ({cost.class_name(tier, ranked)}); серверы другого класса шлюз ставит в "
        "работу, только когда не отвечает ни один из работающих"
    )


def stranded_note(dead: list[str], tier: cost.Klass, ranked: bool) -> str:
    """Событие и пояснение в панели: кто не отвечает, почему его не меняют и что делать."""
    who = ", ".join(f"«{name}»" for name in dead)
    head = f"не отвечает сервер в работе {who}" if len(dead) == 1 else (
        f"не отвечают серверы в работе {who}"
    )
    if tier.rank != priority.LEVELS.index(priority.DEFAULT):
        level = priority.level_name(tier.rank)
        advice = (
            f"поставьте уровень «{level}» ещё нескольким серверам (лучше той же страны) или "
            "верните серверам в работе уровень «средний»"
        )
    else:
        advice = "включите отключённые серверы этого класса или добавьте подписку"
    return (
        f"{head}, а заменить некем: среди запасных нет серверов того же класса "
        f"({cost.class_name(tier, ranked)}); серверы другого класса шлюз ставит в работу, "
        f"только когда не отвечает ни один из работающих. Чтобы было из кого менять, {advice}."
    )


class Lifecycle(StrEnum):
    """Жизненный цикл перехвата (VPN_IMPROVEMENT_PLAN §2.3) — поверх State: State говорит о
    здоровье выходов, Lifecycle — о том, что сейчас с трафиком LAN и машины."""

    OFF = "off"                # xgw disable либо перехват не настроен: сеть напрямую
    CONNECTING = "connecting"  # правила on, Xray запущен, но ещё не проверил ни одного сервера
    CONNECTED = "connected"    # правила on, Xray отвечает: трафик через VPN
    BLOCKED = "blocked"        # мимо VPN ничего: Xray не отвечает либо ждёт inbound (hold)
    OPEN = "open"              # временно напрямую: fail_mode = open, hold = direct, сбой правил


# Переходы, которые попадают в журнал событий (панель, /status бота). Остальные — только в
# журнал демона: «подключается → работает» бывает при каждом перезапуске Xray.
LIFECYCLE_EVENTS = frozenset({Lifecycle.BLOCKED, Lifecycle.OPEN, Lifecycle.OFF})
LIFECYCLE_TEXT = {life: status.LIFECYCLE_WORDS[str(life)][0] for life in Lifecycle}


class Daemon:
    def __init__(
        self,
        cfg: Config,
        paths: Paths,
        *,
        xray_bin: Path,
        logger=None,
        capture=None,
        capture_active=lambda: False,
        reapply_capture=lambda: None,
        sinks=(),
        clock=time.monotonic,
        wall=time.time,
    ) -> None:
        self.cfg = cfg
        self.paths = paths
        self.xray_bin = xray_bin
        self.log = logger or log.get_logger("daemon")
        # capture — управление перехватом (net.capture.Capture); None — перехвата нет
        # (стенд этапа 2, запуск не от root): тогда и утечку проверять не на чем.
        self.capture = capture
        if capture is not None:
            # Утечку ищет обычный сокет самой машины, поэтому проверка имеет смысл,
            # только когда перехватывается и её трафик (capture.local).
            capture_active = lambda: (  # noqa: E731
                capture.mode() == "on" and cfg.capture.local
            )
            reapply_capture = capture.up
        self.capture_active = capture_active
        self.reapply_capture = reapply_capture
        self.capture_info: dict | None = None
        self._capture_error = ""
        # О чём уже сообщили: перехват не включён, потому что Xray работает без нужного
        # inbound'а (текст причины).
        self._inbound_missing = ""
        # Пакеты устройств сети не доходят до Xray (Capture.lan_path): о чём уже сообщили.
        self._lan_problem = ""
        self.xray_down_since: float | None = None
        self.clock = clock
        self.wall = wall

        self.applier = engine.make_applier(cfg, paths, xray_bin)
        self.api = self.applier.api
        self.service = self.applier.service
        self.singbox = engine.make_singbox(cfg, paths)
        self.mark = engine.bypass_mark(cfg, self.log)
        self.machine = StateMachine(cfg.watchdog.fail_threshold)
        # sinks — куда доставлять уведомления (рабочий стол); их собирает
        # `xgw run`, в тестах и на стенде получателей нет.
        self.notifier = Notifier(
            paths.db_file, cfg.notify.min_interval_min, sinks=sinks, logger=self.log
        )
        self.store = Store(paths.db_file)
        # Проверочные хосты (0.1.18, ТЗ R3): собственные пробы шлюза ходят по кругу —
        # probe.url и probe.urls; счётчики и паузы переживают перезапуск демона (META).
        self.hosts = probehosts.ProbeHosts(cfg, clock=wall)
        broken = self.hosts.load(self.store.get_meta(probehosts.META))
        if broken:
            self.log.warning("записей о проверочных хостах в базе не разобрано: %d — пропущены",
                             broken)
        self._hosts_saved = ""
        # Версия Xray для статуса. `xgw update-xray` меняет бинарник и перезапускает только
        # xgw-xray, поэтому версия перечитывается, когда меняется файл (_xray_version).
        self.xray_version = ""
        self._xray_stamp: tuple[int, int, int] | None = None
        self._xray_version()

        self.inventory: engine.Inventory | None = None
        self.action = ""
        self.now_time = lambda: datetime.datetime.now().time()
        self.state_since = self.wall()
        self.dead_since: dict[str, float] = {}  # тег участника → когда замечен мёртвым
        self.e2e_streak = 0
        self.down_ticks = 0
        self.rolled_back = False
        self.leak = False
        self.leak_fresh = False  # на этом шаге утечку проверяли заново
        self._leak_note = ""  # о какой утечке уже сообщили (текст события)
        # Отпечатки серверов, которые сами выходят в домашнюю страну: участник с таким
        # отпечатком меняется, запасной на его место не ставится.
        self.home_exits: set[str] = set()
        self.scan_queue: deque[str] = deque()  # probe-теги узлов, ждущих скана
        # Первая проверка участников собственной пробой шлюза: отпечатки уже проверенных
        # и теги тех, кто её не прошёл (тег → вердикт) — их меняют без ожидания
        # rotate_after_min.
        self.vetted: set[str] = set()
        self.bad_members: dict[str, str] = {}
        # Профили обхода (PROFILE_*): когда демон последний раз переключал профиль сервера
        # (отпечаток → time.time()), какой профиль сервера сейчас проверяется и что ждёт
        # применения (отпечаток → решение).
        self._profile_switched: dict[str, float] = {}
        self._profile_trial: dict[str, ProfileTrial] = {}
        self._profile_wanted: dict[str, ProfileWish] = {}
        # Пробы, записанные в базе (TRIALS_META): отпечаток → {"profile", "rest", "prev",
        # "recheck"}. Запись живёт, пока сервер на пробном профиле: её снимает итог пробы, когда
        # он применён, — а если демон перезапущен раньше, проба продолжается (_resume_trials).
        self._trial_saved: dict[str, dict] = {}
        # Обход блокировок у серверов (0.1.18, ТЗ R1), в базе вместе с пробами: когда сервер
        # переводили на тяжёлый профиль из-за сбоя (отпечаток → [time.time()]), какой обход он
        # выучил и после какого вердикта (отпечаток → {"profile", "verdict", "ts"}) и до каких
        # пор он «нестабилен по ТСПУ» (отпечаток → time.time()). Сколько проверок подряд сервер
        # на дроблении прошёл (для возврата без него) — только в памяти.
        self._escalations: dict[str, list[float]] = {}
        self._escalated: dict[str, dict] = {}
        self._unstable: dict[str, float] = {}
        self._calm: dict[str, int] = {}
        self._calm_seen: dict[str, float] = {}
        # Мёртвый участник проверяется собственной пробой раз за «смерть» (тег → dead_since,
        # для которого проверка уже была): по вердикту решают, переводить ли его на дробление.
        self._dead_scanned: dict[str, float] = {}
        self._load_profiles()
        # sing-box: сколько шагов подряд не отвечает, откатывали ли его на last-good, и
        # ушли ли серверы на Xray, потому что он не поднимается (когда пробовать снова).
        self._singbox_down = 0
        self._singbox_rolled_back = False
        self._singbox_failed = False
        self._singbox_retry_at = 0.0
        self._singbox_alive = True
        self._singbox_version_cache: tuple[float, str] | None = None
        # Обновление ядер (cores.py): фоновая проверка выпусков на GitHub, когда смотреть
        # снова, просьба панели «проверить сейчас», для каких ядер уже запущен возврат в сутки
        # наблюдения (один раз на запуск демона) и меняет ли ядро сейчас служба xgw-core.
        self._cores_thread: threading.Thread | None = None
        # Фоновые проверки сети (ТЗ R4): поток, когда проверять резолверы и DERP, итоги потока
        # (их забирает шаг watchdog: база и события — из его потока) и счётчики DERP.
        self._netmon_thread: threading.Thread | None = None
        self._resolvers_next = clock() + NETMON_FIRST
        self._derp_next = clock() + NETMON_FIRST
        self._netmon_result: dict = {}
        self._derp_fails = 0
        self._derp_oks = 0
        self._derp_note = ""
        self._cores_next = clock() + CORES_FIRST_CHECK
        self._cores_asked = False
        self._core_back_asked: set[str] = set()
        self.core_job = False
        # Не отвечает сам probe.url (текст предупреждения); пусто — отвечает.
        self.probe_target = ""
        self.next_target_check = 0.0
        # Конфиг Xray нужно собрать заново срочно, без окна перезапуска (причина); пусто —
        # не нужно. Так бывает, когда сменился адрес проб ядра (запасной ↔ probe.url) или
        # на машине появился Docker и контейнерам нужен inbound TUN.
        self._urgent_rebuild = ""
        self.next_refresh = 0.0
        self.next_scan = 0.0
        self.next_leak = 0.0
        self.next_all_dead = 0.0
        self.next_rescan = 0.0
        # Когда демон последний раз сменил класс участников (time.time()): вернуться выше
        # можно только по скану, сделанному после этого.
        self.tier_changed = 0.0
        # Резервный выход: когда перепроверять (по self.clock), идущая перепроверка
        # (начало — time.time(), probe-теги кандидатов), о чём уже сообщили.
        self.next_reserve_check = 0.0
        self.reserve_round: tuple[float, list[str]] | None = None
        self.reserve_round_at = float("-inf")  # когда началась последняя (time.time())
        self._urgent_round_for: float | None = None  # для какого ALL_DEAD (state_since)
        self._reserve_note = ""
        # DEGRADED, а заменить мёртвого участника некем (_stranded): о каком классе и каких
        # участниках уже записано событие. Предупреждение «лимитированные в работе из-за
        # приоритета» (status.class_warning): записано ли событие.
        self._stranded_for = ""
        self._class_warning = ""
        # Какой резервный нёс трафик, когда шлюз перешёл в RESERVE (« «имя» (x1)»): к
        # возврату с него состав мог смениться, а сообщить нужно о том, что работал.
        self._reserve_used = ""
        self._price_cache: tuple | None = None
        # На этом шаге участники мертвы и трафик несёт резервный выход: сквозная проверка
        # идёт дешёвым запросом — через лимитированный сервер каждый байт тратит квоту.
        self.reserve_mode = False
        # Записано ли событие о долгой работе через резервный (на этот заход в RESERVE).
        self._reserve_noted = False
        # С какого момента подписки не обновляются (time.time()) и уведомили ли об этом.
        self._sub_failing_since: float | None = None
        self._sub_alerted = False
        # Основной сервер (_main_step): запись {"tag", "key", "name", "since", "basis"}
        # хранится в базе — переживает перезапуск демона. Очередь замеров скорости —
        # probe-теги живых серверов, участников и запасных, чей замер устарел; _compare_due
        # — замер прошёл при ручном выборе: сравнить с основным, когда выбор снимут.
        self.main: dict | None = self._load_main()
        self.speed_queue: deque[str] = deque()
        self._compare_due = False
        # Контроль скорости участников (0.1.18, ТЗ R5–R8; watch/guard.py): пассивные оценки,
        # подозрения, идущий поиск замены, пауза после «глобальной просадки», трафик поисков
        # за сутки. Собственный трафик шлюза через участников (замеры, пробы) с прошлой
        # пассивной оценки — его не считать трафиком клиентов. Короткие (повторные) замеры.
        self.guard = speedguard.Guard(cfg, wall)
        self.guard.load_spent(self.store.get_meta(speedguard.META_SPENT))
        self._own_by_tag: dict[str, int] = {}
        self._speed_small: set[str] = set()
        self._passive_saved = ""
        self._guard_note = ""
        self._speed_asked = False
        # Замер по кнопке: эти probe-теги замеряются и при занятом канале; total/done —
        # сколько серверов в этом заходе и сколько уже замерено (прогресс в панели).
        self._speed_forced: set[str] = set()
        # Кнопка у одного сервера (пожелание заказчика 24.10.2026): теги или отпечатки,
        # ждущие шага watchdog, и probe-теги, которые замеряются, даже если сервер в фоновый
        # замер не попал бы (запасной без свежего скана, участник, которого ядро сочло мёртвым).
        self._speed_one: set[str] = set()
        self._speed_any: set[str] = set()
        self.speed_total = 0
        self.speed_done = 0
        # С какого момента очередь замеров ждёт, пока канал освободится (monotonic; до
        # опустевшей очереди), и ждала ли она на этом шаге.
        self._speed_deferred_since: float | None = None
        self._speed_waiting = False
        # С какого момента фоновый замер ждёт шага без скана (SPEED_SCAN_WAIT).
        self._speed_scanned_since: float | None = None
        # Запасной, переведённый в работу, чтобы стать основным: {"key", "name", "since",
        # "was"}; _lost_main — страна и подписка отказавшего основного, для замены.
        self._promoted: dict | None = None
        self._lost_main: dict | None = None
        self.main_cooldown: dict[str, float] = {}  # ключ сервера → до когда (time.time())
        self._main_failed_at = float("-inf")  # последняя смена из-за непрошедшей загрузки
        self._main_suspended = False  # «карусель»: выбор отдан ядру до удачной загрузки
        # Закреплён ли основной в ядре нами; None — не знаем (демон только запущен).
        self._main_pinned: bool | None = None
        # Когда снова пробовать выбранный вручную запасной, который перестал отвечать.
        self._pin_recheck_at = 0.0
        self._metrics: dict = {}  # последний ответ /debug/vars — по нему видно нагрузку
        self._traffic: tuple[float, int] | None = None  # (clock, байт через серверы)
        self._own_traffic = 0  # сколько из них — собственные замеры скорости
        self._busy = False
        self._scanned = False  # на этом шаге шёл скан: замер скорости подождёт
        self._provider_ips: dict[str, tuple[float, str]] = {}  # хост wan_check → (clock, адрес)
        self._budget_warnings: tuple[str, ...] = ()
        # Запросы из панели: другой поток только ставит отметку, выполняет её шаг watchdog.
        self.poke = threading.Event()
        # События сети, сна и правил (watch/events.py, другой поток): причины ждут шага
        # watchdog в _wakes, _woken прерывает паузу. wake_reason — последняя причина.
        self._woken = threading.Event()
        self._wakes: set[str] = set()
        self._wake_lock = threading.Lock()
        self.wake_reason = ""
        self._net_tick_at = float("-inf")  # когда был последний шаг по событию сети
        self._resumed = False  # машина проснулась после сна: шаг доделает своё (_after_sleep)
        self._net_event = False  # шаг по событию сети: поднять TUN и маршруты в него
        self._marks: tuple[float, float] | None = None  # (clock, wall) прошлого шага
        self.lifecycle: Lifecycle | None = None
        # Проверка с учётом трафика: downlink серверов в работе на прошлом шаге
        # (тег → (clock, байт)) и сколько скачала сама сквозная проба этого шага.
        self._downlinks: dict[str, tuple[float, int]] = {}
        self._e2e_bytes = 0
        self._last_status: tuple | None = None  # (view, observatory, xray_ok) прошлой записи
        # Остановка демона (SIGTERM): её выставляет run. Шаг, который она застала, не
        # доделывается: сканы и замеры прерываются, новое применение конфига не начинается —
        # systemd ждёт остановки не дольше TimeoutStopSec, а установка — перезапуска демона.
        self._stop = threading.Event()
        self._refresh_asked = False
        self._scan_asked = False
        self._manual_scan = False
        self._refreshing = False
        self._rebuild_asked = False

    # --- цикл ------------------------------------------------------------------

    def run(self, stop: threading.Event, changed=lambda: False) -> None:
        """Цикл watchdog до остановки либо до изменения config.toml (changed)."""
        self.log.info("демон XGW запущен, шаг watchdog %d с", self.cfg.watchdog.interval_s)
        self._stop = stop
        while not stop.is_set() and not changed():
            try:
                state = self.tick()
            except Exception:  # сбой одного шага не должен ронять демон
                self.log.exception("шаг watchdog завершился ошибкой")
                state = self.machine.state
            pause = WAN_DOWN_INTERVAL if state is State.WAN_DOWN else self.cfg.watchdog.interval_s
            if self._manual_scan and self.scan_queue:
                pause = MANUAL_SCAN_PAUSE
            self._sleep(stop, changed, jitter(pause))
        self.store.close()
        self.log.info("демон XGW остановлен" if stop.is_set() else "настройки изменены")

    @property
    def stopping(self) -> bool:
        """Демон останавливается: новой работы не начинать. Применение конфига, которое
        уже идёт, доводится до конца — Xray, sing-box и правила не остаются наполовину
        переключёнными."""
        return self._stop.is_set()

    def _sleep(self, stop: threading.Event, changed, seconds: float) -> None:
        """Пауза между шагами. Её прерывают остановка, правка настроек, запрос из панели и
        события (wake): чужое изменение правил сверяется сразу, не прерывая паузу, а
        событие сети и пробуждение после сна начинают шаг раньше."""
        deadline = time.monotonic() + seconds
        while not self.poke.is_set() and not changed():
            if self._woken.is_set():
                deadline = self._on_wake(deadline)
            left = deadline - time.monotonic()
            if left <= 0 or stop.wait(min(left, WAIT_SLICE)):
                break
        self.poke.clear()

    def wake(self, reason: str) -> None:
        """NetEvents (другой поток): «net» — событие сети, «sleep» — машина проснулась,
        «rules» — кто-то убрал правила XGW. Здесь только отметка: всё делает шаг watchdog."""
        with self._wake_lock:
            self._wakes.add(reason)
            self.wake_reason = reason
        self._woken.set()

    def _on_wake(self, deadline: float) -> float:
        """Разбирает причины пробуждения во время паузы; возвращает новый её конец."""
        with self._wake_lock:
            self._woken.clear()
            reasons, self._wakes = self._wakes, set()
        if "rules" in reasons:
            self._guard_now()
        now = time.monotonic()
        if "sleep" in reasons:
            self._resumed = True
            self.log.info("внеочередной шаг: машина проснулась после сна")
            return now
        if "net" in reasons:
            self._net_event = True
            at = max(now, self._net_tick_at + NET_WAKE_PAUSE)
            if at < deadline:
                self.log.info("внеочередной шаг: событие сети")
                return at
        return deadline

    def _guard_now(self) -> None:
        """Событие `nft monitor`: из таблиц XGW что-то убрали (чужой flush ruleset, flush
        table, delete chain). Правила сверяются сразу — без проб и остального шага: окно,
        пока трафик мог уйти мимо VPN, — доли секунды, а не interval_s."""
        if self.capture is None or self.stopping:
            return
        self.log.info("внеочередная проверка правил перехвата: изменились таблицы nftables")
        self._guard_capture(self.xray_down_since is None, self.clock())
        if self._last_status is not None:
            # status.json — с итогом сверки (правила, жизненный цикл, событие о возврате):
            # его читают панель и `xgw status`, а до очередного шага может быть минута.
            self._write_status(*self._last_status)

    def _after_sleep(self, now: float) -> None:
        """Машина проснулась после сна. Монотонные часы демона во сне стоят, а настенные
        идут: сроки, которые прошли во сне (опрос подписок), наступают на этом шаге. Правила
        и маршруты TUN загружаются заново — сеть после сна поднималась без XGW, — а утечка
        проверяется сразу. Запасные проверяет сам шаг (tick)."""
        if self._marks is not None:
            slept = (self.wall() - self._marks[1]) - (now - self._marks[0])
            if slept > 0:
                self.next_refresh -= slept
        self.next_leak = now
        if self.capture is None or self._capture_waits():
            return
        try:
            self.capture.up()
        except Exception as exc:  # сбой сети не должен ронять шаг watchdog
            self.log.error("правила перехвата после сна не загружены: %s", exc)

    def _restore_tun(self) -> None:
        """Событие сети: интерфейс TUN и маршруты в него на месте (ядро убирает маршруты
        через интерфейс, который опускали). Правила сверяет сам шаг (_guard_capture)."""
        restore = getattr(self.capture, "restore_tun", None)
        if restore is None:
            return
        try:
            done = restore()
        except Exception as exc:  # сбой сети не должен ронять шаг watchdog
            self.log.error("интерфейс TUN после события сети не проверен: %s", exc)
            return
        if done:
            self.log.info("%s", done)

    def request_refresh(self) -> None:
        """Панель: обновить подписки сейчас, не дожидаясь refresh_minutes. Заодно заново
        проверяются домены, отложенные как несуществующие."""
        engine.forget_quarantine()
        self._refresh_asked = True
        self.poke.set()

    def adopt(self, previous: Daemon) -> None:
        """Настройки перечитаны. Если источники серверов прежние, подписки заново
        не запрашиваются: конфиг пересобирается из уже полученного списка — так
        отключение сервера в панели не стоит запроса к каждой подписке."""
        self._resume(previous)
        if previous.inventory is None or (
            engine.sources_key(previous.cfg) != engine.sources_key(self.cfg)
        ):
            return
        self.inventory = previous.inventory
        self.next_refresh = previous.next_refresh
        self._rebuild_asked = True
        # Серверы те же — заново проверять участников незачем.
        self.vetted = set(previous.vetted)
        self.bad_members = dict(previous.bad_members)

    def _resume(self, previous: Daemon) -> None:
        """Состояние watchdog переходит к новому демону как есть. Иначе каждая правка
        config.toml и каждое действие в панели молча сбрасывали бы его в HEALTHY: статус
        на шаг показывал бы, что всё в порядке, а следующее событие начиналось бы с
        «HEALTHY →», хотя до правки было, например, ALL_DEAD."""
        self.machine.state = previous.machine.state
        self.state_since = previous.state_since
        self.action = previous.action
        self.e2e_streak = previous.e2e_streak
        self.dead_since = dict(previous.dead_since)
        self.leak, self.next_leak = previous.leak, previous.next_leak
        self._leak_note = previous._leak_note
        self.home_exits = set(previous.home_exits)
        self.down_ticks = previous.down_ticks
        self.rolled_back = previous.rolled_back
        self.xray_down_since = previous.xray_down_since
        self.next_all_dead = previous.next_all_dead
        self._inbound_missing = previous._inbound_missing
        self.probe_target = previous.probe_target
        self.next_target_check = previous.next_target_check
        self._urgent_rebuild = previous._urgent_rebuild
        self.tier_changed = previous.tier_changed
        self.next_reserve_check = previous.next_reserve_check
        self.reserve_round = previous.reserve_round
        self.reserve_round_at = previous.reserve_round_at
        self._urgent_round_for = previous._urgent_round_for
        self._reserve_used = previous._reserve_used
        self._reserve_noted = previous._reserve_noted
        self._sub_failing_since = previous._sub_failing_since
        self._sub_alerted = previous._sub_alerted
        self._reserve_note = previous._reserve_note
        self._stranded_for = previous._stranded_for
        self._class_warning = previous._class_warning
        self.main = previous.main
        self.speed_queue = deque(previous.speed_queue)
        self._speed_forced = set(previous._speed_forced)
        self._speed_one = set(previous._speed_one)
        self._speed_any = set(previous._speed_any)
        self.speed_total, self.speed_done = previous.speed_total, previous.speed_done
        self._speed_deferred_since = previous._speed_deferred_since
        self._speed_waiting = previous._speed_waiting
        self._speed_scanned_since = previous._speed_scanned_since
        self._promoted, self._lost_main = previous._promoted, previous._lost_main
        self._compare_due = previous._compare_due
        self.guard = previous.guard
        self.guard.cfg = self.cfg
        self._own_by_tag = dict(previous._own_by_tag)
        self._speed_small = set(previous._speed_small)
        self._passive_saved = previous._passive_saved
        self._guard_note = previous._guard_note
        self.main_cooldown = dict(previous.main_cooldown)
        self._main_failed_at = previous._main_failed_at
        self._main_suspended = previous._main_suspended
        self._main_pinned = previous._main_pinned
        self._pin_recheck_at = previous._pin_recheck_at
        self._profile_switched = dict(previous._profile_switched)
        self._profile_trial = dict(previous._profile_trial)
        self._profile_wanted = dict(previous._profile_wanted)
        self._trial_saved = dict(previous._trial_saved)
        self._escalations = {key: list(value) for key, value in previous._escalations.items()}
        self._escalated = dict(previous._escalated)
        self._unstable = dict(previous._unstable)
        self._calm = dict(previous._calm)
        self._calm_seen = dict(previous._calm_seen)
        self._dead_scanned = dict(previous._dead_scanned)
        self._singbox_down = previous._singbox_down
        self._singbox_rolled_back = previous._singbox_rolled_back
        self._singbox_failed = previous._singbox_failed
        self._singbox_retry_at = previous._singbox_retry_at
        self._cores_thread = previous._cores_thread
        self._netmon_thread = previous._netmon_thread
        self._resolvers_next = previous._resolvers_next
        self._derp_next = previous._derp_next
        self._netmon_result = previous._netmon_result
        self._derp_fails, self._derp_oks = previous._derp_fails, previous._derp_oks
        self._derp_note = previous._derp_note
        self._cores_next = previous._cores_next
        self._cores_asked = previous._cores_asked
        self._core_back_asked = set(previous._core_back_asked)
        self._traffic = previous._traffic
        self.lifecycle = previous.lifecycle
        self._downlinks = dict(previous._downlinks)
        self._marks = previous._marks
        for url, state in previous.hosts.states.items():
            if url in self.hosts.states:
                self.hosts.states[url] = state
        if previous.cfg.probe.url != self.cfg.probe.url:
            self.next_target_check = 0.0  # адрес пробы сменили — проверить новый сразу

    def request_scan(self) -> None:
        """Панель: проверить запасные серверы сейчас."""
        self._scan_asked = True
        self.poke.set()

    def request_speed(self) -> None:
        """Панель, приложение: замерить скорость всех живых серверов сейчас."""
        self._speed_asked = True
        self.poke.set()

    def request_speed_one(self, key: str) -> None:
        """Панель, приложение: замерить скорость одного сервера сейчас (тег или отпечаток),
        без общего замера всех. Сервер встаёт первым в очередь замеров."""
        self._speed_one.add(key)
        self.poke.set()

    def request_core_check(self) -> None:
        """Панель: проверить выпуски ядер на GitHub сейчас."""
        self._cores_asked = True
        self.poke.set()

    @property
    def cores_pending(self) -> bool:
        thread = self._cores_thread
        return self._cores_asked or (thread is not None and thread.is_alive())

    @property
    def speed_pending(self) -> bool:
        """Идёт общий замер (кнопка «Замерить скорость») — без замеров одного сервера: они
        видны у своих строк, а кнопка общего замера из-за них занятой не выглядит."""
        return self._speed_asked or bool(set(self.speed_queue) - self._speed_any)

    def speed_one_pending(self) -> list[str]:
        """Кнопки у серверов: что ещё ждёт замера (теги и отпечатки из запроса и probe-теги
        в очереди)."""
        return sorted(self._speed_one | (set(self.speed_queue) & self._speed_any))

    @property
    def refresh_pending(self) -> bool:
        return self._refresh_asked or self._refreshing

    @property
    def scan_pending(self) -> bool:
        return self._scan_asked or (self._manual_scan and bool(self.scan_queue))

    def tick(self) -> State:
        """Один шаг watchdog. За шаг применяется не больше одного изменения конфига."""
        now = self.clock()
        self._scanned = False
        resumed, self._resumed = self._resumed, False
        net_event, self._net_event = self._net_event, False
        if resumed or net_event:
            self._net_tick_at = time.monotonic()
        if resumed:
            self._after_sleep(now)
        elif net_event:
            self._restore_tun()
        self._marks = (now, self.wall())
        refresh_asked, self._refresh_asked = self._refresh_asked, False
        scan_asked, self._scan_asked = self._scan_asked, False
        applied = engine.read_json(self.paths.xray_config_file)
        if applied is None:
            # Первый запуск: рабочего конфига ещё нет — собрать и запустить Xray.
            if now >= self.next_refresh or refresh_asked or self._rebuild_asked:
                self._refresh(now, via_xray=False, urgent=True)
            applied = engine.read_json(self.paths.xray_config_file)
            if applied is None:
                self._write_status([], None, False)
                return self.machine.state

        mapped = self.inventory is not None
        view = builder.applied_nodes(applied, self.inventory.nodes if self.inventory else ())
        members = [info for info in view if info.role == "proxy"]
        reserve = builder.reserve_tag(applied)
        signals, observatory = self._signals(members, now, reserve=bool(reserve))
        signals = self._probe_target(view, applied, signals, now)
        previous = self.machine.state
        decision = self.machine.update(signals)
        state = decision.state
        self.action = decision.action
        if state is State.DEGRADED:
            self.action = self._degraded_action(self._stranded(view))
        if state is State.RESERVE:
            if previous is not State.RESERVE:
                self._reserve_used = self._reserve_label(applied)
            self.action = self._reserve_action(self._reserve_used)
        if state is not previous:
            self.state_since = self.wall()
            detail = self.action
            if state is State.PROBE_TARGET_UNREACHABLE:
                detail = f"{self.probe_target}. Замена серверов приостановлена: {target.ADVICE}"
            # Тип события — само состояние: уведомление об ALL_DEAD не должно
            # придерживаться из-за недавнего уведомления о другом состоянии. Уведомляют
            # только состояния, при которых нужно действие человека (ALERT_STATES).
            self.notifier.event(
                str(state), f"{previous} → {state}: {detail}", notify=state in ALERT_STATES,
            )
            if previous is State.RESERVE and state in (State.HEALTHY, State.DEGRADED):
                self.notifier.event(
                    "reserve",
                    f"серверы в работе снова отвечают — Xray вернул на них трафик с резервного"
                    f"{self._reserve_used}",
                )
            if state is not State.RESERVE:
                self._reserve_noted = False
        if (
            state is State.RESERVE and not self._reserve_noted
            and self.wall() - self.state_since >= RESERVE_NOTE_AFTER
        ):
            # Без уведомления: интернет работает, а лимитированные серверы — не беда
            # (решение пользователя после испытаний 0.1.9). Шлюз сам ставит в работу живые
            # лимитированные (_switch_tier) и вернётся к безлимитным, когда они ответят.
            self._reserve_noted = True
            minutes = int((self.wall() - self.state_since) // 60)
            self.notifier.event(
                "reserve",
                f"уже {minutes} мин трафик идёт через резервный сервер{self._reserve_used}: "
                "серверы в работе не отвечают; шлюз ищет живые серверы среди запасных, "
                "в том числе лимитированных",
            )

        urgent = state in (State.ALL_DEAD, State.XRAY_DOWN)
        changed = False
        # Служба xgw-core меняет ядро и сама его перезапускает (и при сбое возвращает
        # прежнее): откат конфига и перезапуски watchdog ей бы только помешали.
        self.core_job = cores.job_active(self.paths, self.wall())
        if state is State.XRAY_DOWN and not self.core_job:
            changed = self._handle_xray_down()
        elif state is not State.XRAY_DOWN:
            self.down_ticks = 0
            self.rolled_back = False
        if not self.leak:
            self._leak_note = ""
        elif state is State.LEAK and self.leak_fresh:
            self._handle_leak()
        # Правила перехвата. Обычно они проверяются до применения конфига: пропавшие
        # нужно вернуть как можно скорее. Но если правилам нужен inbound, которого у
        # работающего Xray ещё нет (настройки только что изменились), сначала
        # применяется конфиг: прежние правила и прежний Xray согласованы и трафик
        # через VPN носят, а загрузка «новых» правил сейчас сняла бы перехват.
        waiting = self._capture_waits()
        if not waiting:
            self._guard_capture(signals.xray_ok, now)
        if self.stopping:
            # Правила и Xray согласованы: правила, которым нужен новый inbound, загрузятся
            # после применения конфига, а его начнёт уже следующий запуск демона.
            self._write_status(view, observatory, signals.xray_ok)
            return state

        if not changed and state is not State.XRAY_DOWN and not self.core_job:
            changed = self._singbox_step(now)
        if (
            not changed and self.inventory is not None and not self._singbox_failed
            and self.paths.singbox_pending_file.exists() and self._singbox_window()
        ):
            # Конфиг sing-box ждал окна: перечитывание рвёт соединения через него.
            changed = self._rebuild(None, urgent=False, reason="конфиг sing-box (окно перезапуска)")
        if not changed and self.paths.pending_config_file.exists():
            changed = self._apply_pending(urgent)
        self._containers_appeared(applied)
        if not changed and self._urgent_rebuild and self.inventory is not None:
            # Срочно, без окна перезапуска: пока ядро пробует недоступный probe.url, оно
            # считает мёртвыми всех участников; без inbound TUN контейнеры без интернета.
            reason, self._urgent_rebuild = self._urgent_rebuild, ""
            changed = self._rebuild(None, urgent=True, reason=reason)
        if not changed and state is State.ALL_DEAD and now >= self.next_all_dead:
            # Внеочередное обновление подписки напрямую и скан всех запасных.
            self.next_all_dead = now + ALL_DEAD_RETRY
            changed = self._refresh(now, via_xray=False, urgent=True)
            self._queue_scan(view, now, everything=True)
        elif not changed and state is State.RESERVE and now >= self.next_all_dead:
            # Трафик несёт резервный выход и тратит квоту: подписка могла сменить серверы —
            # обновить её напрямую (через Xray запрос шёл бы через тот же резервный) и
            # проверить запасные, чтобы поскорее заменить мёртвых участников. Запасные
            # классом хуже (лимитированные) проверяет _switch_tier — когда живых этого
            # класса не осталось и пора переходить на них.
            self.next_all_dead = now + RESERVE_RETRY
            changed = self._refresh(now, via_xray=False, urgent=False)
            self._queue_scan(view, now)
        elif not changed and (
            refresh_asked or (state is not State.WAN_DOWN and now >= self.next_refresh)
        ):
            changed = self._refresh(now, via_xray=signals.xray_ok, urgent=urgent)
        elif not changed and self._rebuild_asked and self.inventory is not None:
            self._rebuild_asked = False
            self._save_inventory(self.inventory)
            changed = self._rebuild(None, urgent=urgent, reason="изменение настроек")
        if not changed and not mapped and self.inventory is not None:
            # Подписка получена только на этом шаге (демон запущен заново): узлы ядра теперь
            # сопоставлены с ней — без этого сканы ниже не знали бы классов и стоимости.
            view = builder.applied_nodes(applied, self.inventory.nodes)
        if waiting or changed:
            # Xray перезапущен с новым конфигом (или не перезапущен — тогда вместо
            # перехвата загрузится режим «снят»): правила доводятся сразу, а не через шаг.
            self._guard_capture(signals.xray_ok, now, switched=waiting)
        # Проба профиля, которую прервал перезапуск демона (или итог которой не применился), —
        # снова в памяти до сканов: иначе скан принял бы пробный профиль за выученный.
        self._resume_trials()

        # Пока не отвечает сам probe.url, сканы только испортили бы вердикты запасных
        # (все «недоступны»), а замена участников шла бы по кругу: и то, и другое ждёт.
        # Решает сам признак, а не имя состояния: утечка (LEAK) стоит в машине состояний
        # выше и его заслоняет, а сканам и замене от этого не легче.
        probing = not self.probe_target
        if scan_asked and probing:
            self._manual_scan = True
            self._queue_scan(view, now, everything=True)
        elif resumed and probing:
            # После сна вердикты запасных устарели: проверить их сейчас, не дожидаясь
            # scan_spares_minutes. Лимитированные класса хуже — как обычно, только когда
            # трафик не идёт (их проверка тратит квоту).
            self.next_scan = now + jitter(self.cfg.probe.scan_spares_minutes * 60.0)
            self._queue_scan(view, now)
        elif scan_asked:
            self.notifier.event("probe", "проверка запасных отложена: не отвечает probe.url")
        if not changed and probing and signals.xray_ok and signals.provider_ok:
            if now >= self.next_scan:
                self.next_scan = now + jitter(self.cfg.probe.scan_spares_minutes * 60.0)
                self._queue_scan(view, now)
            self._queue_members(view)
            self._scan_step(view, applied)
            if self.stopping:
                # Остановка пришла во время сканов: замены и смены класса не начинаем.
                self._write_status(view, observatory, signals.xray_ok)
                return state
            if state in (State.DEGRADED, State.ALL_DEAD, State.RESERVE) or (
                state is State.HEALTHY and self.bad_members
            ) or (state is State.LEAK and self._home_members(view)):
                changed = self._rotate(view, observatory or {}, state, now)
            if not changed:
                changed = self._switch_tier(view, state, now)
            if not changed:
                changed = self._reserve_step(view, applied, state, now)
            if not changed:
                self._member_profiles(view, observatory or {})
                changed = self._profile_step(view)

        if not self.scan_queue or not probing:
            self._manual_scan = False
        if changed:
            applied = engine.read_json(self.paths.xray_config_file)
            view = builder.applied_nodes(applied, self.inventory.nodes if self.inventory else ())
        if self.stopping:
            self._write_status(view, observatory, signals.xray_ok)
            return state
        self._manual_step(view, applied, observatory or {}, signals)
        self._main_step(view, applied, observatory or {}, state, signals, now)
        if state is not State.WAN_DOWN:
            self._cores_step()
            self._netmon_step(signals.xray_ok)
        self._write_status(view, observatory, signals.xray_ok)
        return state

    # --- сигналы ---------------------------------------------------------------

    def _signals(
        self, members: list[NodeInfo], now: float, *, reserve: bool = False
    ) -> tuple[Signals, dict | None]:
        """reserve — у балансировщика есть резервный выход (builder.reserve_tag)."""
        observatory: dict | None = None
        try:
            observatory = self._read_observatory()
            xray_ok = True
        except Exception as exc:
            self.log.debug("метрики недоступны: %s", exc)
            # XRAY_DOWN — когда недоступны и метрики, и API.
            try:
                self.api.balancer_info(BALANCER_TAG)
                xray_ok, observatory = True, {}
            except ApiError:
                xray_ok = False

        tags = [info.tag for info in members]
        self._busy = self._traffic_busy(now)
        provider_ok = self._check_provider()
        if provider_ok and observatory and self.machine.state is State.WAN_DOWN:
            # WAN только что вернулся (шаг по событию сети идёт сразу): «мёртвых» ядро
            # насчитало, пока связи не было, а повторить пробы ещё не успело. На этом шаге
            # они не мертвы, а неизвестны, и отсчёт rotate_after_min начинается заново —
            # иначе шлюз менял бы исправные серверы после каждого обрыва провайдера.
            observatory = {tag: entry for tag, entry in observatory.items() if entry["alive"]}
            self.dead_since.clear()
        alive, dead, unknown = metrics.count_members(observatory or {}, tags)
        downlinks = {
            tag: (now, value)
            for tag, value in metrics.outbound_downlinks(self._metrics).items()
        }
        # Участник, через который сейчас идёт трафик, ядро сочло мёртвым, а трафик через него
        # идёт (его проба опоздала в очереди): он жив.
        spared = self._dead_but_busy(observatory or {}, tags, downlinks) if dead else None
        if spared is not None:
            alive, dead = alive + 1, dead - 1
        # Все участники мертвы, а у балансировщика есть резервный выход: трафик идёт через
        # него, и сквозная проверка — тоже (дешёвым запросом, см. _check_e2e).
        self.reserve_mode = reserve and bool(tags) and dead >= len(tags)
        e2e_ok = True
        if xray_ok and provider_ok:
            self._e2e_bytes = 0
            e2e_ok = self._check_e2e()
            if not e2e_ok and not self.reserve_mode and self._late_under_load(now, downlinks):
                # Туннель заведомо жив: провал не засчитывается, но и счётчик не обнуляется.
                e2e_ok = True
            else:
                self.e2e_streak = 0 if e2e_ok else self.e2e_streak + 1
        self._downlinks = downlinks

        self.leak_fresh = False
        if not self.capture_active():
            self.leak = False
        elif xray_ok and provider_ok and now >= self.next_leak:
            self.next_leak = now + jitter(LEAK_INTERVAL)
            self.leak_fresh = True
            location = self._check_leak()
            self.leak = (
                location is not None and location == self.cfg.routing.home_country.upper()
            )

        for tag in tags:
            entry = (observatory or {}).get(tag)
            if entry is not None and not entry["alive"] and tag != spared:
                self.dead_since.setdefault(tag, self.wall())
            else:
                self.dead_since.pop(tag, None)
        for tag in set(self.dead_since) - set(tags):
            del self.dead_since[tag]
        # Не прошедший первую проверку участник: ядро считает его живым — значит,
        # сбой был разовым; вышел из участников — запись больше не нужна.
        for tag in list(self.bad_members):
            entry = (observatory or {}).get(tag)
            if tag not in tags or (entry is not None and entry["alive"]):
                del self.bad_members[tag]

        return (
            Signals(
                provider_ok=provider_ok,
                xray_ok=xray_ok,
                alive_members=alive,
                total_members=len(tags),
                unknown_members=unknown,
                e2e_ok=e2e_ok,
                e2e_fail_streak=self.e2e_streak,
                leak=self.leak,
                reserve=reserve,
            ),
            observatory,
        )

    def _read_observatory(self) -> dict[str, dict]:
        self._metrics = metrics.fetch_metrics(self.cfg.xray.metrics_port)
        return metrics.parse_observatory(self._metrics)

    def _traffic_busy(self, now: float) -> bool:
        """Идёт ли через серверы заметный трафик (байт/с с прошлого шага > SPEED_BUSY_BPS).

        Счётчики — из того же ответа /debug/vars, что и observatory. Собственный замер
        скорости прошлого шага из них вычитается (_own_traffic)."""
        total = metrics.proxy_traffic(self._metrics)
        previous, self._traffic = self._traffic, (now, total) if total is not None else None
        own, self._own_traffic = self._own_traffic, 0
        if total is None or previous is None or now <= previous[0]:
            return False
        return (total - previous[1] - own) / (now - previous[0]) > SPEED_BUSY_BPS

    # --- проверка с учётом трафика ---------------------------------------------------

    def _downlink_now(self, tag: str) -> int | None:
        """Счётчик downlink сервера сейчас (свежий ответ /debug/vars, без сброса)."""
        try:
            fresh = metrics.fetch_metrics(self.cfg.xray.metrics_port)
        except Exception as exc:
            self.log.debug("счётчики трафика недоступны: %s", exc)
            return None
        return metrics.outbound_downlinks(fresh).get(tag)

    def _carried(
        self, earlier: tuple[float, int] | None, later: tuple[float, int] | None, own: int = 0
    ) -> float | None:
        """Сколько байт пришло через сервер между двумя отсчётами downlink, в пересчёте на
        watchdog.busy_window_s, если это не меньше busy_bytes; иначе None. Отсчёты ближе
        секунды друг к другу ничего не говорят. own — байты самой пробы: её трафик идёт
        через тот же сервер."""
        if earlier is None or later is None or later[0] - earlier[0] < 1.0:
            return None
        window = float(self.cfg.watchdog.busy_window_s)
        got = max(0, later[1] - earlier[1] - own) * window / (later[0] - earlier[0])
        return got if got >= self.cfg.watchdog.busy_bytes else None

    def _late_under_load(self, now: float, downlinks: dict[str, tuple[float, int]]) -> bool:
        """Сквозная проба не прошла, а через сервер, выбранный сейчас, идёт трафик LAN —
        не меньше busy_bytes за busy_window_s. Канал забит, проба опоздала в очереди, а
        туннель жив: провал не засчитывается (VPN_IMPROVEMENT_PLAN §2.3)."""
        selected = self._selected()
        if selected is None:
            return False
        tag = selected[0]
        start = downlinks.get(tag)
        after = self._downlink_now(tag)
        later = (self.clock(), after) if after is not None else None
        got = self._carried(start, later, self._e2e_bytes)
        if got is None:
            got = self._carried(self._downlinks.get(tag), start)
        if got is None:
            return False
        self.log.debug(
            "проба опоздала под нагрузкой: %.1f МБ за %d с через %s",
            got / 1e6, self.cfg.watchdog.busy_window_s, tag,
        )
        return True

    def _dead_but_busy(
        self, observatory: dict, tags: list[str], downlinks: dict[str, tuple[float, int]]
    ) -> str | None:
        """Тег выбранного сейчас участника, которого observatory считает мёртвым, хотя
        через него с прошлого шага идёт трафик (не меньше busy_bytes за busy_window_s)."""
        selected = self._selected()
        if selected is None:
            return None
        tag = selected[0]
        entry = observatory.get(tag)
        if tag not in tags or entry is None or entry["alive"]:
            return None
        got = self._carried(self._downlinks.get(tag), downlinks.get(tag))
        if got is None:
            return None
        self.log.debug(
            "проба ядра опоздала под нагрузкой: %.1f МБ за %d с через %s — участник жив",
            got / 1e6, self.cfg.watchdog.busy_window_s, tag,
        )
        return tag

    def _check_e2e(self) -> bool:
        """Сквозная загрузка проверочного хоста через http-in с детектором «тишины».

        Хосты — по кругу (watch/hosts.py). Хост не ответил — та же загрузка другим хостом:
        ответил он — значит, не отвечает хост, а туннель жив; хост уходит на паузу (событие),
        проверка засчитана. Не ответили оба — проверка не прошла.

        Пока трафик несёт резервный выход (reserve_mode), запрос дешёвый — scan.cheap_url:
        каждые interval_s по 57 КБ через лимитированный сервер тратили бы его квоту, а
        вопрос один — идёт ли через него трафик. Работает ли сам probe.url, тогда решает
        _probe_target по пробам участников."""
        if self.reserve_mode:
            result = self._e2e_get(scan.cheap_url(self.cfg))
            if not result.ok:
                self._e2e_bytes = result.downloaded
                self.log.info("сквозная проверка не прошла: %s", result.error)
            return result.ok
        url = self.hosts.next(stream="e2e")
        result = self._e2e_get(url)
        if not result.ok:
            other = self.hosts.next(avoid=url, stream="e2e")
            second = self._e2e_get(other) if other != url else None
            if second is None or not second.ok:
                downloaded = result.downloaded + (second.downloaded if second else 0)
                self._e2e_bytes = downloaded  # их не считать трафиком LAN (_late_under_load)
                self.log.info("сквозная проверка не прошла: %s", result.error)
                return False
            self._host_failed(url, result.error)
            url, result = other, second
        self.hosts.answered(url)
        if url == self.cfg.probe.url:
            # Размер тела — мера расхода трафика на пробы (status.probe_budget).
            try:
                status.remember_probe_size(self.store, self.cfg.probe.url, result.downloaded)
            except Exception as exc:  # оценка трафика не важнее самой проверки
                self.log.debug("размер пробы не записан: %s", exc)
        return True

    def _e2e_get(self, url: str) -> checks.DownloadResult:
        return checks.http_get_via_proxy(
            "127.0.0.1", self.cfg.xray.http_port, url, silence=5.0,
            max_total=30.0, user_agent=self.cfg.probe.user_agent,
        )

    def _host_failed(self, url: str, why: str) -> None:
        """Проверочный хост не ответил, а другой ответил: пауза и событие (одно на паузу)."""
        text = self.hosts.failed(url, why)
        if text:
            self.notifier.event("probe", text)

    def _check_provider(self) -> bool:
        """TCP-подключение напрямую, сокетом с меткой mark_bypass, к wan_check, а не ответил
        он — к адресам watchdog.wan_checks по очереди (0.1.18, ТЗ R3): «нет провайдера» —
        только когда не отвечает ни один."""
        targets = [
            entry for entry in (self.cfg.watchdog.wan_check, *self.cfg.watchdog.wan_checks)
            if entry.rpartition(":")[0] and entry.rpartition(":")[2].isdigit()
        ]
        if not targets:
            return True  # проверять нечем — провайдера считаем доступным
        for entry in targets:
            host, _, port_text = entry.rpartition(":")
            address = self._provider_address(host)
            if address is not None and checks.tcp_check(address, int(port_text), mark=self.mark):
                return True
        return False

    def _provider_address(self, host: str) -> str | None:
        with contextlib.suppress(ValueError):
            ipaddress.ip_address(host)
            return host
        if self.mark is None:
            return host  # без метки системный резолвер и так ходит напрямую
        now = self.clock()
        cached = self._provider_ips.get(host)
        if cached and now - cached[0] < PROVIDER_DNS_TTL:
            return cached[1]
        try:
            # Свой резолвер с меткой: системный ходит через перехват и при
            # упавшем Xray не ответит — WAN_DOWN получился бы вместо XRAY_DOWN.
            address = fetch.resolve_domain(host, self.cfg.dns.resolvers, mark=self.mark)[0]
        except fetch.ResolveError:
            return cached[1] if cached else None
        self._provider_ips[host] = (now, address)
        return address

    def _check_leak(self) -> str | None:
        """Страна выхода обычным сокетом без метки — то есть через перехват."""
        return checks.trace_location(
            self.cfg.probe.trace_url, user_agent=self.cfg.probe.user_agent
        )

    def _exit_via_xray(self) -> str | None:
        """Страна выхода явно через http-in Xray — через сервер, выбранный балансировщиком."""
        return checks.trace_location(
            self.cfg.probe.trace_url, via=("127.0.0.1", self.cfg.xray.http_port),
            user_agent=self.cfg.probe.user_agent,
        )

    def _selected(self) -> tuple[str, bool] | None:
        """(тег сервера, через который сейчас идёт трафик; закреплён ли он вручную)."""
        try:
            info = self.api.balancer_state(BALANCER_TAG)
        except ApiError as exc:
            self.log.info("выбор балансировщика не узнать: %s", exc)
            return None
        if info.override:
            # Закрепление основного сервера (_main_step) — не ручное: такой сервер, если он
            # сам выходит в домашнюю страну, меняется на запасной, как и выбранный ядром.
            main = (self.main or {}).get("tag")
            return info.override, self._manual_active() or info.override != main
        return (info.selects[0], False) if info.selects else None

    # --- не отвечает сам probe.url -----------------------------------------------

    def _probe_target(
        self, view: list[NodeInfo], applied: dict, signals: Signals, now: float
    ) -> Signals:
        """Отличает «не отвечает адрес пробы» от «не работают серверы» (watch/target.py).

        Повод для проверки — сквозная загрузка probe.url не проходит, и это длится
        fail_threshold шагов либо ядро уже объявило мёртвыми всех участников (его пробы
        идут на тот же адрес, и без этого шаг ушёл бы в ALL_DEAD: скан испортил бы
        вердикты запасных). Тогда собственной пробой опрашиваются все участники и
        несколько запасных; если ошибка у всех одна и контрольные запросы это
        подтверждают, состояние — PROBE_TARGET_UNREACHABLE, и серверы остаются как есть.

        Пока трафик несёт резервный выход (reserve_mode), сквозная проверка идёт дешёвым
        запросом и о probe.url ничего не говорит: тогда участников опрашивают и без её
        сбоев — иначе при недоступном probe.url весь трафик так и шёл бы через
        лимитированный резервный, хотя участники живы.
        """
        reachable = signals.xray_ok and signals.provider_ok
        dead = signals.total_members - signals.alive_members - signals.unknown_members
        all_dead = signals.total_members > 0 and dead >= signals.total_members
        # Сквозная проверка ходит по разным хостам (0.1.18) и может пройти, когда ядро, которое
        # пробует один probe.url, сочло мёртвыми всех участников: это тоже повод проверить адрес.
        if reachable and signals.e2e_ok and not self.reserve_mode and not all_dead:
            self._target_answers(now)
            # И после перезапуска демона: запись о запасном адресе могла остаться с прошлого
            # раза. Сквозная проверка проходит и через другие хосты (0.1.18) — ядро возвращается
            # на probe.url, только когда он сам снова ответил.
            if self._probe_url_answers():
                self._observatory_fallback(False)
            return signals
        suspect = reachable and (self.reserve_mode or all_dead or (
            not signals.e2e_ok and signals.e2e_fail_streak >= self.cfg.watchdog.fail_threshold
        ))
        if suspect and now >= self.next_target_check and not self.stopping:
            self.next_target_check = now + PROBE_TARGET_RECHECK
            diagnosis = self._diagnose_target(view, applied)
            if self.stopping:
                # Пробы прерваны остановкой: ошибка у всех одна, но о probe.url она ничего
                # не говорит.
                self.next_target_check = 0.0
                return signals
            alternate = self._alternate_host(view, applied) if diagnosis.down else ""
            if alternate:
                # Не отвечает только probe.url, а другой проверочный хост через те же серверы
                # открывается: это наблюдение, а не состояние (ТЗ R3) — ядро пробует серверы по
                # этому хосту, замена серверов идёт как обычно.
                self._host_failed(self.cfg.probe.url, diagnosis.signature or "не отвечает")
                self._target_answers(now)
                self._observatory_fallback(True, alternate)
                # «Мёртвыми» участников сделали пробы ядра по неотвечающему probe.url: на этом
                # шаге их состояние не известно (ядро сейчас перейдёт на другой хост), и ни
                # ALL_DEAD, ни отсчёта rotate_after_min из-за адреса проверки быть не должно.
                self.dead_since.clear()
                return dataclasses.replace(
                    signals, alive_members=0, unknown_members=signals.total_members,
                )
            if diagnosis.down and diagnosis.text != self.probe_target:
                self.log.warning("%s", diagnosis.text)
                # Вердикты первой проверки сняты, пока адрес не отвечал: они ни о чём.
                self.bad_members.clear()
                self.vetted.clear()
            if diagnosis.down:
                self.probe_target = diagnosis.text
            else:
                self._target_answers(now)
            self._observatory_fallback(diagnosis.down)
        if self.probe_target:
            return dataclasses.replace(signals, probe_target_ok=False)
        return signals

    def _target_answers(self, now: float) -> None:
        """probe.url отвечает: снять предупреждение, если оно было."""
        if not self.probe_target:
            return
        self.probe_target = ""
        self.next_target_check = 0.0
        self.next_scan = now  # вердикты запасных могли устареть — проверить заново
        # Уведомляли о недоступном адресе — уведомить и о том, что он снова отвечает.
        self.notifier.event(
            "probe", "probe.url снова отвечает — проверки серверов возобновлены",
            notify=self.machine.state is State.PROBE_TARGET_UNREACHABLE,
        )

    def _observatory_fallback(self, on: bool, url: str = "") -> None:
        """Переводит пробы ядра на запасной адрес (on; url — проверочный хост, который только
        что ответил через серверы) или возвращает их на probe.url."""
        try:
            switched = target.use_fallback(self.cfg, self.paths, on, url)
        except OSError as exc:
            self.log.error("адрес проб ядра не переключён: %s", exc)
            return
        if not switched:
            return
        self._urgent_rebuild = "смена адреса проб ядра"
        if on:
            text = (
                f"ядро пробует серверы по {target.observatory_url(self.cfg, self.paths)}, пока "
                "probe.url не ответит: иначе оно сочло бы мёртвыми всех участников"
            )
        else:
            text = "ядро снова пробует серверы по probe.url"
        self.notifier.event("probe", text)  # о самой причине уведомляет PROBE_TARGET_UNREACHABLE

    def _probe_url_answers(self) -> bool:
        """probe.url сам отвечал после того, как ядро перевели на запасной адрес (или
        запасного нет вовсе)."""
        since = target.fallback_since(self.paths)
        if since is None:
            return True
        return self.hosts.states[self.cfg.probe.url].last_ok >= since

    def _alternate_host(self, view: list[NodeInfo], applied: dict) -> str:
        """Другой проверочный хост, который открывается через серверы в работе, пока probe.url
        не отвечает; пусто — не открывается ни один (тогда не отвечают все хосты)."""
        others = [url for url in probehosts.all_urls(self.cfg) if url != self.cfg.probe.url]
        if not others:
            return ""
        password, _ports = builder.probe_state(applied)
        members = [info for info in view if info.role == "proxy" and info.probe_port]
        if not password or not members:
            return ""
        for url in others:
            if self.stopping:
                return ""
            if target.answers_via(self.cfg, members, password, url, user=builder.PROBE_USER):
                self.hosts.answered(url)
                return url
        return ""

    def _containers_appeared(self, applied: dict) -> None:
        """На машине появился Docker, а Xray запущен без inbound'а TUN: контейнерам он
        нужен (их трафик идёт в TUN по метке), до тех пор они без интернета."""
        if self._urgent_rebuild or not engine.containers_tun(self.cfg):
            return
        if tun.inbound_name(applied) == self.cfg.capture.tun_name:
            return
        self._urgent_rebuild = "появился Docker: контейнерам нужен inbound TUN"
        self.notifier.event(
            "capture", "появился Docker — контейнеры пойдут через VPN, Xray перезапускается"
        )

    def _diagnose_target(self, view: list[NodeInfo], applied: dict) -> target.Diagnosis:
        password, _ports = builder.probe_state(applied)
        verdicts = {tag: entry["verdict"] for tag, entry in self.store.scans().items()}
        nodes = target.sample(view, verdicts, skip=self._costly_spares(view))
        if not password or not nodes:
            return target.Diagnosis(False)
        with ThreadPoolExecutor(max_workers=min(PROBE_WORKERS, len(nodes))) as pool:
            results = list(pool.map(lambda info: self._scan(info, password), nodes))
        members = [info for info in view if info.role == "proxy"]
        return target.diagnose(
            results, base_ping=lambda: self._base_ping(members, password),
            direct=self._direct_probe,
        )

    def _costly_spares(self, view: list[NodeInfo]) -> list[str]:
        """Теги запасных, пробовать которые дороже, чем участников: лимитированные, когда
        участники безлимитные. Проба probe.url — 57 КБ, да ещё с множителем."""
        prices = self._prices()
        members = [prices.get(info.fingerprint, 1.0) for info in view if info.role == "proxy"]
        ceiling = min(members, default=0.0)
        return [
            info.tag for info in view
            if info.role == "spare" and prices.get(info.fingerprint, 1.0) > ceiling
        ]

    def _base_ping(self, members: list[NodeInfo], password: str) -> bool:
        """Базовый запрос через VPN — через самих участников: носят ли они трафик вообще.
        Через http-in его понёс бы резервный выход, когда пробы ядра падают у всех."""
        return target.base_ping(self.cfg, members, password, user=builder.PROBE_USER)

    def _direct_probe(self) -> str:
        """probe.url напрямую, мимо VPN: пусто — отдаётся, иначе класс сбоя."""
        return target.direct_signature(self.cfg, self.mark)

    # --- действия --------------------------------------------------------------

    def _handle_xray_down(self) -> bool:
        """systemd перезапускает службу сам; после двух неудач — откат на last-good. Идут
        сутки наблюдения после обновления Xray, а он не отвечает и после отката — возврат
        прежней версии (cores.py)."""
        self.down_ticks += 1
        if not self.service.is_active():
            try:
                self.service.start()
            except XrayServiceError as exc:
                self.log.error("Xray не запускается: %s", exc)
        if self.rolled_back and self.down_ticks >= ROLLBACK_AFTER + CORE_BACK_AFTER:
            self._core_back("xray", "Xray не отвечает и после отката конфига на last-good")
        if self.down_ticks < ROLLBACK_AFTER or self.rolled_back:
            return False
        self.rolled_back = True
        outcome = self.applier.rollback("Xray не отвечает после перезапуска")
        if outcome.mode == "unchanged":
            # Откатывать нечего (last-good нет или он и есть текущий конфиг):
            # служба может числиться запущенной и при этом висеть — перезапускаем сами.
            try:
                self.service.restart()
                self.notifier.event("xray", "Xray не отвечал — служба перезапущена")
            except XrayServiceError as exc:
                self.notifier.event("xray", f"Xray не перезапускается: {exc}", notify=True)
            return False
        self.notifier.event("rollback", engine.describe(outcome), notify=True)
        return outcome.mode == "rollback"

    def _handle_leak(self) -> None:
        """Выход в домашнюю страну при включённом перехвате — раз на проверку утечки, а не
        на каждом шаге. Причин две: сервер, выбранный балансировщиком, сам выходит в эту
        страну (тогда его меняют запасным), либо трафик идёт мимо Xray (тогда правила
        перехвата загружаются заново). Событие — только когда меняется его текст."""
        home = self.cfg.routing.home_country.upper()
        selected = self._selected() if self._exit_via_xray() == home else None
        if selected is not None:
            tag, pinned = selected
            member = self._member_by_tag(tag)
            if pinned:
                text = (
                    f"выход в {home}: выбранный вручную сервер {tag} сам выходит в {home} — "
                    "выберите другой или верните автовыбор: xgw unpin"
                )
            elif member is not None and len(member.fingerprint) >= 8:
                self.home_exits.add(member.fingerprint)
                text = f"выход в {home}: сервер {tag} сам выходит в {home} — меняю его на запасной"
            else:
                text = f"выход в {home}: сервер {tag} сам выходит в {home}"
        else:
            try:
                self.reapply_capture()
            except Exception as exc:  # сбой сети не должен ронять шаг watchdog
                self.log.error("правила перехвата не переприменены: %s", exc)
            text = f"выход в {home} мимо Xray при включённом перехвате — правила загружены заново"
        if text != self._leak_note:
            self._leak_note = text
            self.notifier.event("leak", text, notify=True)

    def _member_by_tag(self, tag: str) -> NodeInfo | None:
        applied = engine.read_json(self.paths.xray_config_file)
        view = builder.applied_nodes(applied, self.inventory.nodes if self.inventory else ())
        return next((info for info in view if info.role == "proxy" and info.tag == tag), None)

    def _home_members(self, view: list[NodeInfo]) -> list[str]:
        """Теги участников, которые сами выходят в домашнюю страну."""
        return [
            info.tag for info in view
            if info.role == "proxy" and info.fingerprint in self.home_exits
        ]

    def _capture_waits(self) -> bool:
        """Перехват включён, но правилам нужен inbound, которого в применённом конфиге
        Xray ещё нет."""
        capture = self.capture
        problem = getattr(capture, "inbound_problem", None)
        try:
            return bool(problem is not None and capture.mode() == "on" and problem())
        except Exception as exc:  # сбой сети не должен ронять шаг watchdog
            self.log.debug("состояние перехвата не прочитано: %s", exc)
            return False

    def _guard_capture(self, xray_ok: bool, now: float, *, switched: bool = False) -> None:
        """Следит за правилами перехвата: возвращает пропавшие, а при
        fail_mode = "open" снимает перехват, пока Xray недоступен дольше минуты.
        switched — правила ждали нового inbound'а и Xray только что перезапущен с ним:
        их загрузка — не возврат пропавших, а включение перехвата по новым настройкам."""
        capture = self.capture
        if capture is None:
            return
        if xray_ok:
            self.xray_down_since = None
        elif self.xray_down_since is None:
            self.xray_down_since = now
        try:
            mode = capture.mode()
            if self.cfg.capture.fail_mode == "open":
                down_for = now - self.xray_down_since if self.xray_down_since is not None else 0.0
                if mode == "on" and down_for >= FAIL_OPEN_AFTER:
                    mode = capture.open()
                    self.notifier.event(
                        "capture",
                        "Xray недоступен дольше минуты — перехват временно снят "
                        "(fail_mode = open), трафик идёт напрямую",
                        notify=True,
                    )
                elif mode == "open" and xray_ok:
                    mode = capture.close()
                    self.notifier.event("capture", "Xray снова отвечает — перехват возвращён")
            elif mode == "open":
                mode = capture.close()  # fail_mode сменили на closed, а метка осталась
            # tailscale.route = "vpn": пока Xray не отвечает, Tailscale идёт напрямую — иначе
            # удалённый доступ к шлюзу пропал бы вместе с VPN (Т1).
            tailscale_direct = getattr(capture, "tailscale_direct", None)
            moved = tailscale_direct(not xray_ok) if tailscale_direct is not None else ""
            if moved:
                self.notifier.event("capture", moved)
            loaded = capture.loaded()
            reloaded = loaded is False
            cause = ""
            if reloaded:
                # Правила пропали (чужой flush ruleset, перезапуск nftables), ещё не
                # загружались либо не соответствуют режиму: без них трафик пошёл бы
                # мимо VPN. Либо интерфейс TUN без адреса — его создал сам Xray.
                tun_problem = getattr(capture, "tun_problem", None)
                cause = tun_problem() if tun_problem is not None else ""
                capture.up()
                loaded = capture.loaded()
            lan_problem = self._lan_path(capture, mode, loaded, reloaded)
            info = capture.describe(check=False)
            self.capture_info = {**info, "loaded": loaded, "lan_problem": lan_problem}
            missing = str(info.get("inbound_missing") or "")
            if missing:
                if missing != self._inbound_missing:  # одно событие на причину
                    held = (
                        "трафик заблокирован, мимо VPN ничего не уходит (capture.hold = block)"
                        if info.get("blocked") else "трафик идёт напрямую"
                    )
                    self.notifier.event(
                        "capture",
                        f"перехват не включён: {missing} — {held}; "
                        "включится сам после перезапуска Xray с новым конфигом",
                        notify=True,
                    )
            elif reloaded and (self._inbound_missing or switched):
                self.notifier.event(
                    "capture", "Xray перезапущен с inbound'ом перехвата — перехват включён",
                )
            elif reloaded:
                # Правила вернулись сами: делать человеку нечего — только событие в журнале.
                text = getattr(
                    capture, "reloaded_text", "правила сети не были загружены — загружены заново"
                )
                if cause:
                    text = f"{cause} — интерфейс подготовлен заново"
                self.notifier.event("capture", text)
            self._inbound_missing = missing
            self._capture_error = ""
            tidy = getattr(capture, "tidy", None)  # у подставного перехвата в тестах — нет
            tidied = tidy() if tidy is not None else ""
            if tidied:
                self.notifier.event("capture", tidied)
        except Exception as exc:  # сбой сети не должен ронять шаг watchdog
            text = f"правила перехвата не загружены: {exc}"
            self.log.error("%s", text)
            if text != self._capture_error:  # одно событие на причину, а не на каждый шаг
                self._capture_error = text
                self.notifier.event("capture", text, notify=True)

    def _lan_path(self, capture, mode: str, loaded: bool | None, reloaded: bool) -> str:
        """Доходят ли пакеты устройств сети до Xray. Правила на месте, а пакеты гибнут —
        правила загружаются заново (маршрут throw, iprule.py); не помогло — событие с
        уведомлением, панель и `xgw status` показывают причину: «серверы в порядке» ещё не
        значит, что у устройств сети есть интернет."""
        lan_path = getattr(capture, "lan_path", None)  # у подставного перехвата — нет
        if lan_path is None or mode != "on" or loaded is not True:
            problem = ""
        else:
            problem = lan_path()
            if problem and not reloaded:
                capture.up()
                problem = lan_path()
                if not problem:
                    self.notifier.event(
                        "capture", "пакеты устройств сети не доходили до Xray — правила "
                        "маршрутизации загружены заново, интернет в сети снова есть",
                    )
        if problem and problem != self._lan_problem:
            self.log.error("%s", problem)
            self.notifier.event("lan", f"нет интернета у устройств сети: {problem}", notify=True)
        elif not problem and self._lan_problem:
            self.notifier.event("lan", "устройства сети снова выходят в интернет через Xray")
        self._lan_problem = problem
        return problem

    def _apply_pending(self, urgent: bool) -> bool:
        """Конфиг, ждущий перезапуска: в окне restart_window либо срочно."""
        if self.stopping:
            return False  # файл остаётся: применит следующий запуск демона
        pending = engine.read_json(self.paths.pending_config_file)
        if pending is None:
            self.paths.pending_config_file.unlink(missing_ok=True)
            return False
        if not urgent:
            applied = engine.read_json(self.paths.xray_config_file) or {}
            if capture_inbounds(pending) != capture_inbounds(applied):
                # Меняется inbound перехвата: правила сети следуют новым настройкам, и
                # ждать окна нельзя — трафик уходил бы на порт или в интерфейс, которых
                # у работающего Xray нет (fail-closed = нет интернета).
                self.log.warning(
                    "применяю конфиг вне окна %s: меняется inbound перехвата",
                    self.cfg.apply.restart_window,
                )
                urgent = True
            elif not in_restart_window(self.cfg.apply.restart_window, self.now_time()):
                return False
        outcome = self._apply(pending, urgent=urgent)
        if outcome.mode == "rejected":
            # Отклонённый конфиг не перепроверяем на каждом шаге: следующее
            # обновление подписки соберёт новый.
            self.paths.pending_config_file.unlink(missing_ok=True)
        return self._report(outcome, "отложенный перезапуск")

    def _refresh(self, now: float, *, via_xray: bool, urgent: bool) -> bool:
        """Опрос подписок и применение изменений."""
        if self.stopping:
            return False
        self._refreshing = True
        try:
            return self._refresh_now(now, via_xray=via_xray, urgent=urgent)
        finally:
            self._refreshing = False

    def _refresh_now(self, now: float, *, via_xray: bool, urgent: bool) -> bool:
        minutes = min((sub.refresh_minutes for sub in self.cfg.subscriptions), default=60)
        self.next_refresh = now + jitter(max(1, minutes) * 60.0)
        try:
            inventory = self._collect(via_xray)
        except fetch.Cancelled:
            # Остановка прервала опрос: о подписках он ничего не говорит — ни сбоя, ни
            # ошибок для панели, ни неполного списка серверов.
            self.log.info("опрос подписок прерван: демон останавливается")
            return False
        self._save_errors(inventory)
        if inventory.nodes:
            self._save_inventory(inventory)
        first_start = not self.paths.xray_config_file.exists()
        if not inventory.nodes and not engine.has_sources(self.cfg):
            # Подписок и ссылок нет вовсе — это не сбой: их добавят в панели. Ядро,
            # если оно уже работало, остаётся на прежних серверах.
            self.next_refresh = now + jitter(SUBSCRIPTION_RETRY)
            return False
        if not inventory.nodes or not (inventory.complete or first_start):
            # Неполный список применять нельзя: из ядра пропали бы серверы подписки,
            # которую сейчас не удалось получить.
            self._subscription_failed()
            if self.inventory is None and inventory.nodes:
                self.inventory = inventory  # хотя бы сопоставить узлы с тегами
            # Повторить скорее, чем через refresh_minutes, но не на каждом шаге:
            # у запроса подписки и так три повтора с паузами.
            self.next_refresh = min(self.next_refresh, now + jitter(SUBSCRIPTION_RETRY))
            return False
        self.inventory = inventory
        if inventory.complete:
            self._sub_failing_since, self._sub_alerted = None, False
        self._rebuild_asked = False  # сборка ниже уже учитывает новые настройки
        return self._rebuild(None, urgent=urgent, reason="обновление подписки")

    def _rebuild(
        self, prefer: list[str] | None, *, urgent: bool, reason: str,
        tier: cost.Klass | None = None, reserve: str | None = None,
        profiles: dict[str, str] | None = None,
    ) -> bool:
        assert self.inventory is not None
        if self.stopping:
            # Остановка пришла, пока шёл опрос подписок или сканы: новое применение не
            # начинаем — прерывать его на середине нельзя, а ждать его systemd не обязан.
            self.log.info("%s: не применяется — демон останавливается", reason)
            return False
        dead = engine.quarantined()
        # Перечитывание sing-box рвёт соединения через него: сразу — при аварии и в окне
        # перезапуска, иначе — только если через него никто не идёт (engine.assemble).
        reload = True if urgent or self._singbox_window() else None
        try:
            assembly = self._assemble(prefer, tier, reserve, profiles, reload)
        except engine.EngineError as exc:
            self.notifier.event("config", f"{reason}: {exc}", notify=True)
            return False
        finally:
            if engine.quarantined() != dead:
                # Сборка отложила домены, которых нет в DNS. Список для панели записан до
                # неё — иначе там такой сервер значился бы «включён, сейчас возьмёт в работу».
                self._save_inventory(self.inventory)
        outcome = self._apply(assembly.result.config, urgent=urgent, singbox=assembly.singbox)
        if outcome.mode in ("api", "restart", "unchanged"):
            engine.persist(self.paths, assembly, self.inventory.quotas, record_event=False)
        return self._report(outcome, reason)

    def _report(self, outcome: ApplyOutcome, reason: str) -> bool:
        """Событие по итогу применения; True — рабочий конфиг изменился."""
        if outcome.mode == "unchanged":
            return False
        bad = outcome.mode in ("rejected", "rollback", "failed")
        self.notifier.event("apply", f"{reason}: {engine.describe(outcome)}", notify=bad)
        if outcome.mode in ("api", "restart"):
            return True  # ручной выбор ядро забыло — вернёт _manual_step на этом же шаге
        return outcome.mode == "rollback"

    def _subscription_failed(self) -> None:
        """Подписки не получены: событие в журнал; уведомление — только если это длится
        дольше SUBSCRIPTION_ALERT_AFTER (разовый сбой провайдера повода не даёт)."""
        now = self.wall()
        if self._sub_failing_since is None:
            self._sub_failing_since = now
        alert = not self._sub_alerted and now - self._sub_failing_since >= SUBSCRIPTION_ALERT_AFTER
        text = "подписки получить не удалось — конфиг не меняется"
        if alert:
            self._sub_alerted = True
            hours = max(1, int((now - self._sub_failing_since) // 3600))
            text = (f"подписки не обновляются уже {hours} ч — конфиг не меняется; проверьте "
                    "адрес и срок подписки (панель, раздел «Подписки»)")
        self.notifier.event("subscription", text, notify=alert)

    def _save_inventory(self, inventory: engine.Inventory) -> None:
        try:
            engine.save_inventory(self.paths, self.cfg, inventory)
        except OSError as exc:  # список нужен только панели
            self.log.error("список серверов не записан: %s", exc)

    def _save_errors(self, inventory: engine.Inventory) -> None:
        """Почему подписка не обновилась — чтобы панель показала это рядом с ней."""
        errors = {
            name: {"error": text, "ts": self.wall()} for name, text in inventory.errors.items()
        }
        try:
            if errors or self.store.get_meta("sub_errors") not in (None, "", "{}"):
                self.store.set_meta("sub_errors", json.dumps(errors, ensure_ascii=False))
        except Exception as exc:  # состояние не критично для работы шлюза
            self.log.error("ошибки подписок не записаны: %s", exc)

    def _collect(self, via_xray: bool) -> engine.Inventory:
        return engine.collect(
            self.cfg, self.paths, mark=self.mark, logger=self.log, via_xray=via_xray,
            cancel=self._stop,
        )

    def _assemble(
        self, prefer: list[str] | None, tier: cost.Klass | None = None,
        reserve: str | None = None, profiles: dict[str, str] | None = None,
        reload_singbox: bool | None = None,
    ) -> engine.Assembly:
        assert self.inventory is not None
        return engine.assemble(
            self.cfg, self.paths, self.inventory, mark=self.mark, logger=self.log,
            xray_bin=self.xray_bin, prefer=prefer, tier=tier, reserve=reserve,
            profiles=profiles, reload_singbox=reload_singbox,
            singbox_ok=False if self._singbox_failed else None,
        )

    def _apply(
        self, config: dict, *, urgent: bool, singbox: engine.SingboxChange | None = None,
    ) -> ApplyOutcome:
        """Сначала sing-box (мосты должны слушать), затем Xray."""
        rejected = self._apply_singbox(singbox)
        if rejected is not None:
            return rejected
        return self.applier.apply(config, urgent=urgent)

    # --- сканы и замена участников ---------------------------------------------

    def _queue_scan(self, view: list[NodeInfo], now: float, *, everything: bool = False) -> None:
        """Запасные — в очередь скана; серверы классов лучше — первыми.

        Лимитированные запасные класса хуже, чем у участников, сюда не попадают: это
        кандидаты в резервный выход, их редко и дешёвым запросом проверяет _reserve_step.
        everything — проверить и их: по кнопке «Проверить запасные» и когда трафик не
        идёт вовсе (ALL_DEAD)."""
        queued = set(self.scan_queue)
        tier = self._tier(view)
        prices = self._prices()
        # Трафик не идёт (ALL_DEAD, RESERVE): внутри класса первыми проверяются серверы на другом
        # ядре и другом транспорте, чем у упавших участников, — блокировка, которая срезала TCP
        # через Xray, может пропустить QUIC через sing-box, и наоборот.
        other = self._alternatives(view) if self.machine.state in (
            State.ALL_DEAD, State.RESERVE) else set()
        spares = sorted(
            (info for info in view if info.role == "spare"),
            key=lambda info: (self._klass(info.fingerprint), info.fingerprint not in other),
        )
        for info in spares:
            klass = self._klass(info.fingerprint)
            if not everything and (
                info.fingerprint not in prices  # не сопоставлен с подпиской: цена неизвестна
                or (tier is not None and klass > tier and klass.cost > 0)
            ):
                continue
            if info.probe_tag not in queued:
                self.scan_queue.append(info.probe_tag)
        self.next_rescan = now + RESCAN_PAUSE

    def _alternatives(self, view: list[NodeInfo]) -> set[str]:
        """Отпечатки запасных, чьи ядро или транспорт отличаются от всех участников: при
        массовой блокировке они проверяются первыми."""
        if self.inventory is None:
            return set()
        nodes = {node.fingerprint: node for node in self.inventory.nodes}
        members = [info for info in view if info.role == "proxy" and info.fingerprint in nodes]
        if not members:
            return set()
        used = {(profiling.core_of(info.profile), _transport(nodes[info.fingerprint]))
                for info in members}
        return {
            info.fingerprint for info in view
            if info.role == "spare" and info.fingerprint in nodes
            and (profiling.core_of(info.profile), _transport(nodes[info.fingerprint])) not in used
        }

    def _prices(self) -> dict[str, float]:
        """Стоимость серверов по отпечаткам (cost.py); подписки ещё нет — пусто. Считается
        заново, только когда сменился список серверов или настройки."""
        if self.inventory is None:
            return {}
        cached = self._price_cache
        if cached is not None and cached[0] is self.inventory and cached[1] is self.cfg:
            return cached[2]
        prices = engine.node_costs(self.cfg, self.inventory)
        self._price_cache = (self.inventory, self.cfg, prices)
        return prices

    def _klass(self, fingerprint: str, prices: dict[str, float] | None = None) -> cost.Klass:
        return cost.klass(
            self.cfg.managed.priority, self._prices() if prices is None else prices, fingerprint
        )

    def _tier(self, view: list[NodeInfo]) -> cost.Klass | None:
        """Класс участников: лучший среди них (все участники — одного класса)."""
        return cost.best(
            self.cfg.managed.priority, self._prices(),
            [info.fingerprint for info in view if info.role == "proxy"],
        )

    def _scan_url(self, info: NodeInfo) -> str | None:
        """Чем проверять узел: запасной лимитированной подписки — дешёвым запросом
        (scan.cheap_url), остальные — проверочным хостом (None: _probe_scan берёт его по
        кругу)."""
        if info.role == "spare" and self._prices().get(info.fingerprint, 1.0) > 0:
            return scan.cheap_url(self.cfg)
        return None

    def _probe_scan(self, info: NodeInfo, password: str) -> scan.ScanResult:
        """Собственная проба сервера. Хост — по кругу (watch/hosts.py); хост ответил ошибкой
        HTTP (403, 404, 5xx) — та же проба другим хостом: ответил тот — пауза хосту, вердикт
        по второй пробе. Обрыв и «заморозку» хост не объясняет — это вердикт о сервере."""
        cheap = self._scan_url(info)
        if cheap is not None:
            return self._scan(info, password, cheap)
        url = self.hosts.next(stream="scan")
        result = self._scan(info, password, url)
        if result.verdict in REPLACEABLE_VERDICTS:
            self.hosts.answered(url)
            return result
        if result.kind == "cancelled" or not probehosts.host_specific(result.kind, result.status):
            return result
        other = self.hosts.next(avoid=url, stream="scan")
        if other == url:
            return result
        second = self._scan(info, password, other)
        if second.verdict in REPLACEABLE_VERDICTS:
            self._host_failed(url, result.error)
            self.hosts.answered(other)
        return second

    def _queue_members(self, view: list[NodeInfo]) -> None:
        """Первая проверка участников собственной пробой шлюза — в начало очереди.

        Первый состав балансировщика берётся из подписки без всяких сведений о
        серверах; observatory ядра скажет лишь «жив или нет», и то не сразу. Своя проба
        отличает «заморозку» и отказ в соединении, и такой участник меняется сразу.
        Проверяется каждый участник один раз: дальше за ним следит само ядро.
        """
        queued = set(self.scan_queue)
        for info in reversed([item for item in view if item.role == "proxy"]):
            if len(info.fingerprint) < 8:
                continue  # узел не сопоставлен с подпиской — заменить его всё равно нельзя
            dead_at = self.dead_since.get(info.tag)
            # Ядро сочло участника мёртвым — своя проба скажет, «заморозка» это или отказ: тогда
            # его сначала проверяют с дроблением, а не меняют (ТЗ R1). Раз за «смерть».
            recheck = (
                dead_at is not None and self._dead_scanned.get(info.tag) != dead_at
                and bool(self._escalation_steps(info, "STALL_BEFORE_BODY"))
            )
            if (info.fingerprint not in self.vetted or recheck) and info.probe_tag not in queued:
                self.scan_queue.appendleft(info.probe_tag)

    def _scan_step(self, view: list[NodeInfo], applied: dict) -> None:
        """Сканирует узлы из очереди, пока не истёк бюджет времени шага."""
        if not self.scan_queue:
            return
        password, _ports = builder.probe_state(applied)
        nodes = {info.probe_tag: info for info in view}
        started = self.clock()
        while self.scan_queue and self.clock() - started < SCAN_BUDGET and not self.stopping:
            probe_tag = self.scan_queue.popleft()
            info = nodes.get(probe_tag)
            if info is None or not password:
                continue
            self._scanned = True
            result = self._probe_scan(info, password)
            if result.kind == "cancelled":
                self.scan_queue.appendleft(probe_tag)  # скан не состоялся
                break
            self.store.save_scan(
                info.probe_tag, result.verdict, result.bytes_read, result.seconds, result.error,
                ts=self.wall(),
            )
            self._profile_note(info, result.verdict)
            if info.role == "proxy":
                self.vetted.add(info.fingerprint)
                if info.tag in self.dead_since:
                    self._dead_scanned[info.tag] = self.dead_since[info.tag]
                held = self._member_note(info, result.verdict)
                if result.verdict in REPLACE_NOW_VERDICTS and not held:
                    self.bad_members[info.tag] = result.verdict
                elif result.verdict in REPLACEABLE_VERDICTS or held:
                    self.bad_members.pop(info.tag, None)
            self.log.info(
                "скан %s: %s, %d байт за %.1f с", info.tag, result.verdict,
                result.bytes_read, result.seconds,
            )

    def _scan(self, info: NodeInfo, password: str, url: str | None = None) -> scan.ScanResult:
        """url — адрес проверки; None — probe.url."""
        return scan.scan_node(info, self.cfg, probe_pass=password, url=url, cancel=self._stop)

    def _rotate(self, view: list[NodeInfo], observatory: dict, state: State, now: float) -> bool:
        """Меняет участников, мёртвых дольше rotate_after_min, на проверенные запасные;
        не прошедших первую проверку (bad_members) — сразу."""
        home = self._home_members(view)
        if self.inventory is None or not (self.dead_since or self.bad_members or home):
            return False
        by_fingerprint = {node.fingerprint: node for node in self.inventory.nodes}
        members = [info for info in view if info.role == "proxy"]
        if any(info.fingerprint not in by_fingerprint for info in members):
            return False  # состав ядра не сопоставлен с подпиской — менять вслепую нельзя
        # Замена — только запасным того же класса (приоритет и стоимость): на класс хуже
        # переходит _switch_tier, когда живых на этом не осталось.
        prices = self._prices()
        tier = self._tier(view)
        pairs = [
            (info, by_fingerprint[info.fingerprint])
            for info in view
            if info.role == "spare" and info.fingerprint in by_fingerprint
            and info.fingerprint not in self.home_exits  # тоже выходит в домашнюю страну
            and self._klass(info.fingerprint, prices) == tier
            and not self._is_unstable(info.fingerprint)
        ]
        # Участник на пробе дробления (ТЗ R1) не меняется, пока проба не кончится.
        held = {info.tag for info in members if self._escalating(info.fingerprint)}
        dead_since = {tag: since for tag, since in self.dead_since.items() if tag not in held}
        scans = self._fresh_scans()
        verdicts = {i.tag: scans[i.probe_tag]["verdict"] for i, _ in pairs if i.probe_tag in scans}
        seconds = {i.tag: scans[i.probe_tag]["seconds"] for i, _ in pairs if i.probe_tag in scans}
        cfg = self.cfg
        if state in (State.ALL_DEAD, State.RESERVE):
            # Живых нет вовсе (или трафик несёт резервный и тратит квоту) — ждать
            # rotate_after_min незачем.
            cfg = copy.copy(self.cfg)
            cfg.filters = copy.copy(self.cfg.filters)
            cfg.filters.rotate_after_min = 0
        alive = {tag: entry["alive"] for tag, entry in observatory.items()}
        # Замена — той же страны и быстрее по замеру, если такая есть (ASSUMPTIONS п. 224).
        origins = {
            node.fingerprint: (node.country, node.source) for node in self.inventory.nodes
        }
        speeds = {
            info.fingerprint: candidate.mbps for info, _node in pairs
            if (candidate := self._candidate(info, {})).mbps is not None
        }
        rotation = plan_rotation(
            alive, dead_since, verdicts, seconds, members, pairs, cfg, self.wall(),
            urgent=(set(self.bad_members) | set(home)) - held, origins=origins, speeds=speeds,
        )
        if rotation is None:
            overdue = cfg.filters.rotate_after_min * 60.0
            waiting = bool(set(self.bad_members) - held or home) or any(
                self.wall() - since >= overdue for since in dead_since.values()
            )
            if waiting and pairs and not self.scan_queue and now >= self.next_rescan:
                self._queue_scan(view, now)  # менять пора, а свежих сканов нет
            return False
        names = ", ".join(f"{tag} → «{node.name}»" for tag, node in rotation.replacements)
        failed = [
            f"{tag} — {self.bad_members[tag]}"
            for tag, _node in rotation.replacements if tag in self.bad_members
        ]
        leaking = [tag for tag, _node in rotation.replacements if tag in home]
        text = f"замена участников: {names}"
        if failed:
            text += f" (не прошли первую проверку: {', '.join(failed)})"
        if leaking:
            text += (
                f" (сами выходят в {self.cfg.routing.home_country.upper()}: "
                f"{', '.join(leaking)})"
            )
        self.notifier.event("rotation", text)  # шлюз справился сам — уведомлять незачем
        # Замены пришли из запасных, прошедших скан, — проверять их заново незачем. Кроме
        # лимитированных: их проверяли дешёвым запросом, «заморозку» он не ловит.
        self.vetted.update(
            node.fingerprint for _tag, node in rotation.replacements
            if prices.get(node.fingerprint, 1.0) == 0
        )
        for tag, _node in rotation.replacements:
            self.bad_members.pop(tag, None)
        return self._rebuild(
            preferred_members(members, rotation),
            urgent=state is State.ALL_DEAD,
            reason="замена участника",
        )

    def _fresh_scans(self) -> dict[str, dict]:
        """Сканы по probe-тегам. «Прошедший последний скан»: результат старше двух
        периодов скана не в счёт."""
        fresh_after = self.wall() - self.cfg.probe.scan_spares_minutes * 120.0 - 120.0
        # Скан сервера, который сейчас проверяется в другом профиле обхода, получен ещё в
        # прежнем профиле — по нему сервер не ставится ни участником, ни резервным выходом.
        trial = {item.probe_tag for item in self._profile_trial.values()}
        return {
            tag: entry for tag, entry in self.store.scans().items()
            if entry["ts"] >= fresh_after and tag not in trial
        }

    def _stranded(self, view: list[NodeInfo]) -> cost.Klass | None:
        """Класс участников, если мёртвого участника заменить некем: среди запасных нет ни
        одного сервера этого класса. _rotate меняет только внутри класса, а на класс хуже
        _switch_tier переходит, лишь когда живых участников нет, — так что DEGRADED держится,
        пока мёртвый не оживёт (испытание 24.10.2026: четыре сервера «высокий» x10, все в
        работе). None — есть кем, мёртвых нет или состав не сопоставлен с подпиской."""
        members = [info for info in view if info.role == "proxy"]
        if self.inventory is None or not members or not set(self.dead_since) & {
            info.tag for info in members
        }:
            return None
        known = {node.fingerprint for node in self.inventory.nodes}
        if any(info.fingerprint not in known for info in members):
            return None
        prices = self._prices()
        tier = self._tier(view)
        if any(
            info.role == "spare" and info.fingerprint in known
            and info.fingerprint not in self.home_exits
            and self._klass(info.fingerprint, prices) == tier
            for info in view
        ):
            return None
        return tier

    def _degraded_action(self, tier: cost.Klass | None) -> str:
        """Текст DEGRADED; tier — класс, который нашёл _stranded (None — заменить есть кем)."""
        if tier is not None:
            return stranded_action(tier, bool(self.cfg.managed.priority))
        if self.inventory is None:
            # Демон только запущен, подписка ещё не получена: есть ли кем заменить, не
            # известно — «замена на запасные» могла бы оказаться неправдой.
            return "часть серверов недоступна"
        return action_text(State.DEGRADED)

    def _stranded_step(self, view: list[NodeInfo], state: State) -> str:
        """Текст DEGRADED — по составу на конец шага (подписка могла обновиться), и одно
        событие на каждый новый набор мёртвых, которых заменить некем. Возвращает пояснение
        для панели; пусто — замена возможна или состояние другое."""
        if not view:
            return ""  # конфига ещё нет: судить не по чему, отметку не трогаем
        tier = self._stranded(view) if state is State.DEGRADED else None
        if state is State.DEGRADED:
            self.action = self._degraded_action(tier)
        if tier is None:
            self._stranded_for = ""
            return ""
        dead = sorted(
            info.tag for info in view if info.role == "proxy" and info.tag in self.dead_since
        )
        names = [
            node.name if (node := self._node(info)) is not None else info.tag
            for info in view if info.tag in dead
        ]
        note = stranded_note(names, tier, bool(self.cfg.managed.priority))
        key = f"{tier.rank}:{tier.cost}:{','.join(dead)}"
        if key != self._stranded_for:
            self._stranded_for = key
            self.notifier.event("rotation", note)
        return note

    # --- профили обхода --------------------------------------------------------

    def _bridged_letters(self, fingerprint: str) -> set[str]:
        """Варианты sing-box, заведённые серверу в работающем sing-box."""
        ports = singboxing.bridge_ports(self.singbox.read())
        return {letter for fp, letter in ports if fp == fingerprint}

    def _profile_event(self, old: str, new: str, text: str) -> None:
        # События про дробление в Xray (0.1.11) — прежнего вида; остальные — «профиль».
        xray_only = {old, new} <= {profiling.XRAY_DEFAULT, *profiling.XRAY_FRAGMENTS}
        self.notifier.event("fragment" if xray_only else "profile", text)

    def _profile_note(self, info: NodeInfo, verdict: str) -> None:
        """Итог скана запасного: решить, не проверить ли его в другом профиле обхода
        (generator/profiles.py), и подвести итог такой проверки. Участников не трогает:
        их трафик профилем не рискует — не прошедший проверку участник становится запасным,
        а там до него дойдёт очередь. Работает при fragment.mode = "auto"."""
        if self.cfg.fragment.mode != "auto" or info.role != "spare" or self.inventory is None:
            return
        node = next(
            (node for node in self.inventory.nodes if node.fingerprint == info.fingerprint), None,
        )
        if node is None:
            return
        fingerprint, now = info.fingerprint, self.wall()
        limited = self._prices().get(fingerprint, 1.0) > 0
        avail = profiling.available(node, self.cfg, self._bridged_letters(fingerprint))
        default = profiling.base(self.cfg, avail)
        good = verdict in REPLACEABLE_VERDICTS
        name = _server_text(node.name, info.tag)
        trial = self._profile_trial.get(fingerprint)
        if trial is not None:
            if info.profile != trial.profile:
                # Профиль ещё не применён (конфиг ждёт перезапуска): скан — о прежнем.
                if now - trial.since >= PROFILE_RETRY:
                    del self._profile_trial[fingerprint]
                    self._forget_trial(fingerprint)
                return
            if good:
                del self._profile_trial[fingerprint]
                self._forget_trial(fingerprint)
                self._learned(fingerprint, trial)
                self._profile_event(trial.prev, trial.profile, f"{name} {_keep_text(trial)}")
                return
            # Следующая ступень и возврат меняют конфиг: запись о пробе в базе остаётся до их
            # применения (_profile_step) — перезапуск демона до него продолжит эту же пробу.
            if trial.rest:
                following = trial.rest[0]
                self._profile_wanted[fingerprint] = ProfileWish(
                    following, True, trial.rest[1:], trial.prev, verdict=trial.verdict,
                )
                self._profile_event(
                    trial.profile, following,
                    f"{name} не отвечает на профиле «{profiling.NAMES[trial.profile]}» — пробую "
                    f"«{profiling.NAMES[following]}»",
                )
                del self._profile_trial[fingerprint]
                return
            del self._profile_trial[fingerprint]
            self._profile_wanted[fingerprint] = ProfileWish(trial.prev, False, [], trial.prev)
            self._profile_event(trial.prev, trial.profile, f"{name} {_fail_text(trial)}")
            return
        last = self._profile_switched.get(fingerprint)
        heavy = info.profile != default
        self._calm[fingerprint] = self._calm.get(fingerprint, 0) + 1 if good else 0
        if good and heavy:
            if last is None:
                self._profile_switched[fingerprint] = now  # отсчёт до перепроверки — с сейчас
                self._save_profiles()
            elif self._calm_due(fingerprint, info.profile, last):
                self._profile_wanted[fingerprint] = ProfileWish(
                    default, True, [], info.profile, recheck=True,
                )
        elif verdict in profiling.TRIGGER_VERDICTS and (
            last is None or now - last >= PROFILE_RETRY
        ):
            steps = profiling.ladder(verdict, info.profile, default, avail)
            if limited:
                # Квота подписки: на другое ядро сервер в фоне не переводится — каждая проба
                # тратит квоту, а перебор ядер без нужды — пустая трата (дробление в том же
                # ядре остаётся, как в 0.1.11).
                steps = [step for step in steps
                         if profiling.core_of(step) == profiling.core_of(default)]
            if steps and self._may_escalate(fingerprint, name):
                self._profile_wanted[fingerprint] = ProfileWish(
                    steps[0], True, steps[1:], info.profile, verdict=verdict,
                )

    def _profile_step(self, view: list[NodeInfo]) -> bool:
        """Применяет решения _profile_note одной сборкой конфига: outbounds серверов меняются
        через API Xray (профили sing-box заведены в нём заранее), без перезапуска Xray и без
        перечитывания sing-box. Проверяемые серверы — в начало очереди скана."""
        wanted, self._profile_wanted = self._profile_wanted, {}
        if not wanted or self.inventory is None or self.cfg.fragment.mode != "auto":
            return False
        # Запасные и — для проб дробления на месте (ТЗ R1) — участники.
        by_fingerprint = {
            info.fingerprint: info for info in view if info.role in ("spare", "proxy")
        }
        wanted = {key: wish for key, wish in wanted.items() if key in by_fingerprint}
        changes = {
            key: wish.profile for key, wish in wanted.items()
            if by_fingerprint[key].profile != wish.profile
        }
        if not changes:
            return False
        names = ", ".join(sorted(by_fingerprint[key].tag for key in wanted))
        # Проба дробления у участника — сразу: он не отвечает, и трафик ждёт (через API ядра,
        # без перезапуска Xray).
        urgent = any(wish.escalate for wish in wanted.values())
        changed = self._rebuild(
            None, urgent=urgent, reason=f"профиль обхода ({names})", profiles=changes,
        )
        applied = engine.read_json(self.paths.xray_config_file)
        now_profiles = builder.applied_profiles(applied, self.inventory.nodes)
        now = self.wall()
        for key, wish in wanted.items():
            if now_profiles.get(key) != wish.profile:
                # Не применилось: решение примет следующий скан. Сервер, который так и остался
                # на пробном профиле, снова на пробе (_resume_trials) — запись о ней в базе.
                continue
            self._profile_switched[key] = now
            if wish.trial:
                info = by_fingerprint[key]
                self._profile_trial[key] = ProfileTrial(
                    wish.profile, list(wish.rest), wish.prev, info.probe_tag, now, wish.recheck,
                    wish.verdict, wish.escalate,
                )
                self._trial_saved[key] = {
                    "profile": wish.profile, "rest": list(wish.rest), "prev": wish.prev,
                    "recheck": wish.recheck, "verdict": wish.verdict, "escalate": wish.escalate,
                }
                self._queue_first(info.probe_tag)
            else:
                self._trial_saved.pop(key, None)  # возврат применён — проба окончена
        self._save_profiles()
        return changed

    # --- эскалация у серверов в работе (ТЗ R1) -------------------------------------

    def _escalation_steps(self, info: NodeInfo, verdict: str) -> list[str]:
        """Ступени дробления в Xray, которые стоит проверить участнику с таким вердиктом
        (лестница profiles.ladder без sing-box: ядро у сервера в работе на ходу не меняется).
        Пусто — пробовать нечего: дробление выключено, сервер не на Xray, не TLS/REALITY."""
        if self.cfg.fragment.mode != "auto" or self.inventory is None:
            return []
        if profiling.core_of(info.profile) != "xray":
            return []
        node = self._node(info)
        if node is None:
            return []
        avail = profiling.available(node, self.cfg, ())
        default = profiling.base(self.cfg, avail)
        return [
            step for step in profiling.ladder(verdict, info.profile, default, avail)
            if profiling.core_of(step) == "xray" and step != info.profile
            and (step in profiling.XRAY_FRAGMENTS or info.profile in profiling.XRAY_FRAGMENTS)
        ]

    def _escalating(self, fingerprint: str) -> bool:
        """Сервер в работе сейчас на пробе дробления (или её ждёт) — замена подождёт."""
        trial = self._profile_trial.get(fingerprint)
        wish = self._profile_wanted.get(fingerprint)
        return bool((trial is not None and trial.escalate) or (wish is not None and wish.escalate))

    def _is_unstable(self, fingerprint: str) -> bool:
        return self._unstable.get(fingerprint, 0.0) > self.wall()

    def _may_escalate(self, fingerprint: str, server: str) -> bool:
        """Можно ли перевести сервер на тяжёлый профиль ещё раз: не больше
        fragment.escalations переводов за fragment.escalation_hours. Иначе он «нестабилен по
        ТСПУ» до конца этого окна — в работу шлюз его сам не ставит (событие одно на отметку).
        server — сервер в тексте события (_server_text)."""
        now = self.wall()
        window = self.cfg.fragment.escalation_hours * 3600.0
        times = [when for when in self._escalations.get(fingerprint, []) if now - when < window]
        if len(times) < self.cfg.fragment.escalations:
            self._escalations[fingerprint] = [*times, now]
            self._save_profiles()
            return True
        if not self._is_unstable(fingerprint):
            until = min(times) + window
            self._unstable[fingerprint] = until
            self._save_profiles()
            clock = datetime.datetime.fromtimestamp(until).strftime("%H:%M")
            self.notifier.event(
                "profile",
                f"{server} нестабилен по ТСПУ: {len(times)} перевода на обход за "
                f"{self.cfg.fragment.escalation_hours} ч — в работу шлюз его сам не ставит до "
                f"{clock}",
            )
        return False

    def _learned(self, fingerprint: str, trial: ProfileTrial) -> None:
        """Проба помогла: сервер выучил обход — для панели «обход: … после …» (ТЗ R1.2).
        Вернулся на базовый профиль — отметка снимается."""
        if trial.recheck:
            if self._escalated.pop(fingerprint, None) is not None:
                self._save_profiles()
            return
        self._escalated[fingerprint] = {
            "profile": trial.profile, "verdict": trial.verdict, "ts": self.wall(),
        }
        self._save_profiles()

    def _calm_due(self, fingerprint: str, profile: str, since: float) -> bool:
        """Пора ли пробовать сервер на базовом профиле. Дробление в Xray — после
        fragment.calm_probes проверок подряд без сбоя и не раньше fragment.calm_hours (ТЗ R1.3:
        дробление тратит процессор сервера и чуть скорости, держим его только по
        необходимости); профили sing-box — раз в PROFILE_RECHECK, как до 0.1.18."""
        elapsed = self.wall() - since
        if profile in profiling.XRAY_FRAGMENTS:
            return (
                self._calm.get(fingerprint, 0) >= self.cfg.fragment.calm_probes
                and elapsed >= self.cfg.fragment.calm_hours * 3600.0
            )
        return elapsed >= PROFILE_RECHECK

    def _member_note(self, info: NodeInfo, verdict: str) -> bool:
        """Итог собственной пробы участника (ТЗ R1). «Заморозка» или отказ — не повод сразу
        менять сервер: он проверяется на ступенях дробления в Xray на месте; заменяют его,
        только если не ответил и там. True — участник на пробе дробления (замена ждёт)."""
        node = self._node(info)
        if self.cfg.fragment.mode != "auto" or node is None:
            return False
        fingerprint, name = info.fingerprint, _server_text(node.name, info.tag)
        good = verdict in REPLACEABLE_VERDICTS
        self._calm[fingerprint] = self._calm.get(fingerprint, 0) + 1 if good else 0
        trial = self._profile_trial.get(fingerprint)
        if trial is not None:
            if info.profile != trial.profile:
                return trial.escalate  # профиль ещё не применён — проба впереди
            del self._profile_trial[fingerprint]
            if good:
                self._forget_trial(fingerprint)
                self._learned(fingerprint, trial)
                self._profile_event(trial.prev, trial.profile, f"{name} {_keep_text(trial)}")
                return False
            if trial.rest:
                following = trial.rest[0]
                self._profile_wanted[fingerprint] = ProfileWish(
                    following, True, trial.rest[1:], trial.prev, verdict=trial.verdict,
                    escalate=True,
                )
                self._profile_event(
                    trial.profile, following,
                    f"{name} в работе не отвечает и на профиле «{profiling.NAMES[trial.profile]}» "
                    f"— пробую «{profiling.NAMES[following]}»",
                )
                return True
            self._profile_wanted[fingerprint] = ProfileWish(trial.prev, False, [], trial.prev)
            if trial.recheck:
                # Без дробления не отвечает — снова на нём, сразу (это тоже перевод на обход).
                self._may_escalate(fingerprint, name)
                self._profile_event(trial.prev, trial.profile, f"{name} {_fail_text(trial)}")
                return True
            self.bad_members[info.tag] = verdict
            self._profile_event(
                trial.prev, trial.profile,
                f"{name} в работе не отвечает ни на одной ступени дробления в Xray ({verdict}) — "
                "меняю его на запасной",
            )
            return False
        if good or verdict not in profiling.ESCALATE_VERDICTS:
            return False
        steps = self._escalation_steps(info, verdict)
        if not steps:
            return False
        if not self._may_escalate(fingerprint, name):
            self.bad_members[info.tag] = verdict  # «нестабилен по ТСПУ» — на замену
            return False
        self._profile_wanted[fingerprint] = ProfileWish(
            steps[0], True, steps[1:], info.profile, verdict=verdict, escalate=True,
        )
        self._profile_event(
            info.profile, steps[0],
            f"{name} в работе не отвечает ({verdict}) — не меняю его, а пробую "
            f"«{profiling.NAMES[steps[0]]}»",
        )
        return True

    def _member_profiles(self, view: list[NodeInfo], observatory: dict) -> None:
        """Участники на дроблении (ТЗ R1.3): каждая проба ядра без сбоя — плюс к счёту
        проверок подряд (не чаще probe.interval), сбой — счёт заново. Набрал fragment.calm_probes
        за fragment.calm_hours — проба без дробления, на месте. Основной и выбранный вручную так
        не проверяются: неудача оборвала бы весь трафик (их проверят, когда они уступят место)."""
        if self.cfg.fragment.mode != "auto" or self.inventory is None:
            return
        now = self.wall()
        every = float(max(checks_interval(self.cfg), self.cfg.watchdog.interval_s))
        main = (self.main or {}).get("tag")
        pin = self._manual_pin()
        for info in view:
            if info.role != "proxy" or info.profile not in profiling.XRAY_FRAGMENTS:
                continue
            key = info.fingerprint
            entry = observatory.get(info.tag)
            if entry is None:
                continue
            if not entry.get("alive"):
                self._calm[key] = 0
                continue
            if now - self._calm_seen.get(key, 0.0) >= every:
                self._calm_seen[key] = now
                self._calm[key] = self._calm.get(key, 0) + 1
            if (
                info.tag == main or (pin is not None and pinning.same_server(pin["tag"], info.tag))
                or key in self._profile_trial or key in self._profile_wanted
            ):
                continue
            node = self._node(info)
            last = self._profile_switched.get(key)
            if node is None or last is None or not self._calm_due(key, info.profile, last):
                continue
            avail = profiling.available(node, self.cfg, ())
            default = profiling.base(self.cfg, avail)
            if default != info.profile:
                self._profile_wanted[key] = ProfileWish(
                    default, True, [], info.profile, recheck=True,
                )

    def _queue_first(self, probe_tag: str) -> None:
        if probe_tag in self.scan_queue:
            self.scan_queue.remove(probe_tag)
        self.scan_queue.appendleft(probe_tag)

    def _load_profiles(self) -> None:
        """Пробы профилей и время смены профиля из базы (TRIALS_META): прошлый запуск демона
        оставил их там. Записи, которые не разобрать, пропускаются."""
        raw = self.store.get_meta(TRIALS_META)
        try:
            saved = json.loads(raw) if raw else {}
        except ValueError:
            self.log.warning("записи о пробах профилей в базе не разобраны — пропущены")
            return
        if not isinstance(saved, dict):
            self.log.warning("записи о пробах профилей в базе не разобраны — пропущены")
            return
        skipped = 0
        trials = saved.get("trials")
        for key, record in (trials.items() if isinstance(trials, dict) else ()):
            rest = record.get("rest") if isinstance(record, dict) else None
            if not isinstance(rest, list) or not all(
                step in profiling.ALL for step in (record.get("profile"), record.get("prev"), *rest)
            ):
                skipped += 1
                continue
            self._trial_saved[str(key)] = {
                "profile": record["profile"], "rest": list(rest), "prev": record["prev"],
                "recheck": bool(record.get("recheck")),
                "verdict": str(record.get("verdict") or ""),
                "escalate": bool(record.get("escalate")),
            }
        switched = saved.get("switched")
        for key, when in (switched.items() if isinstance(switched, dict) else ()):
            if isinstance(when, (int, float)) and not isinstance(when, bool):
                self._profile_switched[str(key)] = float(when)
            else:
                skipped += 1
        escalations = saved.get("escalations")
        for key, times in (escalations.items() if isinstance(escalations, dict) else ()):
            if isinstance(times, list) and all(
                isinstance(item, (int, float)) and not isinstance(item, bool) for item in times
            ):
                self._escalations[str(key)] = [float(item) for item in times]
            else:
                skipped += 1
        learned = saved.get("escalated")
        for key, record in (learned.items() if isinstance(learned, dict) else ()):
            if (
                isinstance(record, dict) and record.get("profile") in profiling.ALL
                and isinstance(record.get("ts"), (int, float))
            ):
                self._escalated[str(key)] = {
                    "profile": record["profile"], "verdict": str(record.get("verdict") or ""),
                    "ts": float(record["ts"]),
                }
            else:
                skipped += 1
        unstable = saved.get("unstable")
        for key, until in (unstable.items() if isinstance(unstable, dict) else ()):
            if isinstance(until, (int, float)) and not isinstance(until, bool):
                self._unstable[str(key)] = float(until)
            else:
                skipped += 1
        if skipped:
            self.log.warning("записей о пробах профилей в базе не разобрано: %d — пропущены",
                             skipped)

    def _save_profiles(self) -> None:
        """Записывает пробы и время смены профиля в базу. Серверов, которых нет в подписке,
        время смены не держит: с подпиской уходят и они."""
        switched = self._profile_switched
        now = self.wall()
        window = self.cfg.fragment.escalation_hours * 3600.0
        self._escalations = {
            key: [when for when in times if now - when < window]
            for key, times in self._escalations.items()
        }
        self._escalations = {key: times for key, times in self._escalations.items() if times}
        self._unstable = {key: until for key, until in self._unstable.items() if until > now}
        if self.inventory is not None:
            known = {node.fingerprint for node in self.inventory.nodes}
            switched = {key: when for key, when in switched.items() if key in known}
            self._profile_switched = dict(switched)
            self._escalated = {
                key: value for key, value in self._escalated.items() if key in known
            }
        self.store.set_meta(
            TRIALS_META, json.dumps({
                "trials": self._trial_saved, "switched": switched,
                "escalations": self._escalations, "escalated": self._escalated,
                "unstable": self._unstable,
            }),
        )

    def _forget_trial(self, fingerprint: str) -> None:
        if self._trial_saved.pop(fingerprint, None) is not None:
            self._save_profiles()

    def _resume_trials(self) -> None:
        """Пробы из базы, которых нет в памяти: демон перезапущен посреди пробы или итог пробы
        не применился. Сервер всё ещё на пробном профиле — проба продолжается с той же ступени
        (отсчёт заново, скан — первым); ушёл с него (настройки ядра сменились, пока демон
        стоял, сервер пропал из конфига) — запись снимается."""
        waiting = [
            key for key in self._trial_saved
            if key not in self._profile_trial and key not in self._profile_wanted
        ]
        if not waiting or self.inventory is None or self.cfg.fragment.mode != "auto":
            return
        applied = engine.read_json(self.paths.xray_config_file)
        if applied is None:
            return
        spares = {
            info.fingerprint: info for info in builder.applied_nodes(applied, self.inventory.nodes)
            if info.role in ("spare", "proxy")
        }
        names = {node.fingerprint: node.name for node in self.inventory.nodes}
        now, dropped = self.wall(), False
        for key in waiting:
            record, info = self._trial_saved[key], spares.get(key)
            if info is None or info.profile != record["profile"]:
                del self._trial_saved[key]
                dropped = True
                self.log.info(
                    "проба профиля «%s» сервера «%s» снята: сервер уже не на нём",
                    profiling.NAMES[record["profile"]], names.get(key, key[:12]),
                )
                continue
            self._profile_trial[key] = ProfileTrial(
                record["profile"], list(record["rest"]), record["prev"], info.probe_tag, now,
                record["recheck"], record.get("verdict", ""), record.get("escalate", False),
            )
            self._queue_first(info.probe_tag)
            self.log.info(
                "проба профиля «%s» сервера «%s» продолжается (до неё был «%s»)",
                profiling.NAMES[record["profile"]], names.get(key, info.tag),
                profiling.NAMES[record["prev"]],
            )
        if dropped:
            self._save_profiles()

    # --- sing-box --------------------------------------------------------------

    def _singbox_step(self, now: float) -> bool:
        """Слежение за sing-box (ТЗ 5.3): не отвечает — перезапуск, после двух неудач — откат
        на last-good, дальше — серверы переводятся на Xray. True — конфиг Xray пересобран."""
        if self.stopping:
            return False
        if self._singbox_failed:
            return self._singbox_recover(now)
        if not self.singbox.expected():
            self._singbox_down = 0
            self._singbox_alive = True
            return False
        self._singbox_alive = self.singbox.alive()
        if self._singbox_alive:
            self._singbox_down = 0
            self._singbox_rolled_back = False
            return False
        self._singbox_down += 1
        self.log.warning("sing-box не отвечает (шаг %d)", self._singbox_down)
        error = self.singbox.restart()
        if error is None and self.singbox.alive():
            self.notifier.event("singbox", "sing-box не отвечал — служба перезапущена")
            self._singbox_down = 0
            return False
        if self._singbox_down < ROLLBACK_AFTER:
            return False
        if not self._singbox_rolled_back:
            self._singbox_rolled_back = True
            outcome = self.singbox.rollback("sing-box не отвечает после перезапуска")
            if outcome.mode == "rollback":
                self.notifier.event(
                    "singbox", f"sing-box откатил конфиг на last-good: {outcome.detail}",
                    notify=True,
                )
                return False
        # Не поднимается ни с новым, ни с прежним конфигом: серверы, которые умеет и Xray,
        # переводятся на него — интернет важнее профиля.
        self._singbox_failed = True
        self._singbox_retry_at = now + SINGBOX_RETRY
        if self._core_back("sing-box", "sing-box не поднимается ни с новым, ни с прежним конфигом"):
            # Прежняя версия скоро встанет на место: поднять sing-box снова, не дожидаясь
            # SINGBOX_RETRY.
            self._singbox_retry_at = now + CORE_RECOVER
        self.notifier.event(
            "singbox",
            "sing-box не поднимается — серверы переведены на Xray; серверы только для sing-box "
            "(hysteria2, TUIC…) недоступны, пока он не заработает",
            notify=True,
        )
        if self.inventory is None:
            return False
        return self._rebuild(None, urgent=True, reason="sing-box не поднимается")

    # --- обновление ядер (cores.py) ----------------------------------------------

    def _core_back(self, core: str, why: str) -> bool:
        """Сутки наблюдения после обновления ядра: оно перестало работать — служба xgw-core
        возвращает прежнюю версию. Один раз на запуск демона; True — возврат запущен."""
        if core in self._core_back_asked or not cores.watching(self.paths, core, self.wall()):
            return False
        self._core_back_asked.add(core)
        title, previous = cores.TITLES[core], cores.previous(self.paths, core)
        error = self._start_core_job(core, "rollback", reason="watch")
        if error:
            self.notifier.event(
                "cores", f"{why}, но вернуть прежний {title} {previous} не удалось: {error}",
                notify=True,
            )
            return False
        self.notifier.event(
            "cores",
            f"{why} — идут сутки наблюдения после обновления {title}: шлюз возвращает прежнюю "
            f"версию {previous}",
            notify=True,
        )
        return True

    def _start_core_job(self, core: str, action: str, *, reason: str) -> str:
        return cores.start(self.paths, core, action, reason=reason)

    def _cores_step(self) -> None:
        """Раз в сутки (и по кнопке «Проверить сейчас») — выпуски ядер на GitHub. Запросы идут
        в отдельном потоке: шаг watchdog не должен ждать GitHub."""
        thread = self._cores_thread
        if thread is not None and thread.is_alive():
            return
        asked, self._cores_asked = self._cores_asked, False
        now = self.clock()
        if not asked and (now < self._cores_next or not cores.check_due(self.paths, self.wall())):
            return
        self._cores_next = now + CORES_RECHECK
        singbox = self._singbox_version()
        installed = {
            "xray": cores.parse(self.xray_version) if self.xray_version else None,
            "sing-box": cores.parse(singbox) if singbox else None,
        }
        self._cores_thread = threading.Thread(
            target=self._check_cores, args=(installed,), name="xgw-cores", daemon=True,
        )
        self._cores_thread.start()

    def _check_cores(self, installed: dict) -> None:
        try:
            _record, events = cores.check(self.cfg, self.paths, installed, mark=self.mark)
        except Exception as exc:  # проверка обновлений не должна ронять демон
            self.log.error("выпуски ядер на GitHub не проверены: %s", exc)
            return
        for text, notify in events:
            self.notifier.event("cores", text, notify=notify)

    # --- фоновые проверки сети (ТЗ R4) ---------------------------------------------

    def _netmon_step(self, xray_ok: bool) -> None:
        """Итоги фоновых проверок — в базу и события; пора — новая проверка в своём потоке:
        мёртвый резолвер или сервер DERP отвечает таймаутом, и шаг watchdog его ждать не
        должен."""
        result, self._netmon_result = self._netmon_result, {}
        if "resolvers" in result:
            self._resolvers_done(*result["resolvers"])
        if "derp" in result:
            self._derp_done(result["derp"], xray_ok)
        thread = self._netmon_thread
        if thread is not None and thread.is_alive():
            return
        now = self.clock()
        jobs: list[str] = []
        if now >= self._resolvers_next:
            self._resolvers_next = now + jitter(self.cfg.dns.bootstrap_check_minutes * 60.0)
            jobs.append("resolvers")
        if now >= self._derp_next and self._derp_wanted():
            self._derp_next = now + jitter(DERP_CHECK)
            jobs.append("derp")
        if not jobs:
            return
        self._netmon_thread = threading.Thread(
            target=self._netmon_run, args=(jobs,), name="xgw-netmon", daemon=True,
        )
        self._netmon_thread.start()

    def _netmon_run(self, jobs: list[str]) -> None:
        """Поток проверок: только сеть, без базы (её соединение принадлежит шагу watchdog)."""
        result: dict = {}
        try:
            if "resolvers" in jobs:
                result["resolvers"] = (self.wall(), self._check_resolvers())
            if "derp" in jobs:
                result["derp"] = self._check_derp()
        except Exception as exc:  # проверка сети не должна ронять демон
            self.log.error("фоновая проверка сети не выполнена: %s", exc)
        self._netmon_result = result

    def _check_resolvers(self) -> list[dict]:
        return resolving.check_all(self.cfg, mark=self.mark, cancel=self._stop)

    def _resolvers_done(self, when: float, results: list[dict]) -> None:
        """Итог проверки резолверов: в базу; изменился (все → часть → ни один) — событие."""
        if not results:
            return
        before = resolving.verdict(
            resolving.loads(self.store.get_meta(resolving.META)).get("results") or []
        )
        self.store.set_meta(resolving.META, resolving.dumps(results, when))
        now = resolving.verdict(results)
        if now == before or (now == "ok" and not before):
            return
        self.notifier.event("dns", resolving.event_text(results), notify=now == "down")

    def _derp_wanted(self) -> bool:
        """Проверять DERP есть смысл: tailscaled работает, его сокеты по настройке идут
        напрямую (route = "direct"), аварийный маршрут разрешён, машина перехватывается."""
        return (
            self.capture is not None and self.cfg.capture.local
            and self.cfg.tailscale.route == "direct" and self.cfg.tailscale.derp_fallback
            and ts.present(self.paths)
        )

    def _check_derp(self) -> str | None:
        """Сервер DERP домашнего региона напрямую, сокетом мимо VPN: пусто — отвечает, иначе
        причина; None — проверять нечем (карту DERP не получить)."""
        hosts = ts.derp_hosts()
        if not hosts:
            return None
        errors: list[str] = []
        for host in hosts[:2]:
            if self.stopping:
                return None
            try:
                reply = fetch.fetch_url(
                    f"https://{host}/derp/probe", mark=self.mark, timeout=10.0, retries=0,
                    bootstrap=self.cfg.dns.resolvers if self.mark is not None else None,
                    cancel=self._stop,
                )
            except fetch.Cancelled:
                return None
            except fetch.FetchError as exc:
                errors.append(f"{host}: {exc}")
                continue
            if reply.status == 200:
                return ""
            errors.append(f"{host}: HTTP {reply.status}")
        return "; ".join(errors)

    def _derp_done(self, error: str | None, xray_ok: bool) -> None:
        """DERP напрямую не отвечает derp_fails проверок подряд, а Xray жив — tailscaled
        временно через VPN; отвечает DERP_BACK раз подряд — снова напрямую. Петли нет:
        Xray ходит к серверам сокетами mark_bypass, мимо перехвата (net/nft.py)."""
        capture = self.capture
        if error is None or capture is None:
            return
        via_vpn = capture.tailscale_via_vpn()
        if error:
            self._derp_oks = 0
            self._derp_fails += 1
            self.log.info("DERP напрямую не отвечает (%d): %s", self._derp_fails, error)
            if via_vpn or self._derp_fails < self.cfg.tailscale.derp_fails or not xray_ok:
                return
            text = capture.tailscale_fallback(True)
            if text:
                self.notifier.event(
                    "tailscale", f"{text} (не отвечает: {error}); вернётся напрямую сам, "
                    "когда DERP снова ответит", notify=True,
                )
            return
        self._derp_fails = 0
        if not via_vpn:
            return
        self._derp_oks += 1
        if self._derp_oks < DERP_BACK:
            return
        self._derp_oks = 0
        text = capture.tailscale_fallback(False)
        if text:
            self.notifier.event("tailscale", text)

    def _singbox_recover(self, now: float) -> bool:
        """sing-box отказал и серверы ушли на Xray: раз в SINGBOX_RETRY пробуем его поднять."""
        if now < self._singbox_retry_at:
            return False
        self._singbox_retry_at = now + SINGBOX_RETRY
        if not self.singbox.expected():
            self._singbox_failed = False
            return False
        if self.singbox.restart() is not None or not self.singbox.alive():
            return False
        self._singbox_failed = False
        self._singbox_down = 0
        self._singbox_rolled_back = False
        self.notifier.event("singbox", "sing-box снова работает — серверы возвращаются на него")
        if self.inventory is None:
            return False
        return self._rebuild(None, urgent=False, reason="sing-box снова работает")

    def _singbox_status(self, view: list[NodeInfo]) -> dict:
        """Второе ядро для статуса: режим, установлен ли, отвечает ли, сколько серверов ведёт."""
        installed = singboxing.find_binary(None, self.paths) is not None
        bridged = sum(1 for info in view if profiling.core_of(info.profile) == "sing-box")
        expected = installed and self.singbox.expected()
        return {
            "mode": self.cfg.core.mode,
            "installed": installed,
            "version": self._singbox_version() if installed else "",
            "expected": expected,
            "alive": (not self._singbox_failed and self._singbox_alive) if expected else None,
            "failed": self._singbox_failed,
            "bridged": bridged,
        }

    def _singbox_version(self) -> str:
        """Версия sing-box; перечитывается, когда меняется файл (`xgw update-singbox`)."""
        binary_path = singboxing.find_binary(None, self.paths)
        if binary_path is None:
            return ""
        try:
            stamp = binary_path.stat().st_mtime
        except OSError:
            return ""
        cached = self._singbox_version_cache
        if cached is not None and cached[0] == stamp:
            return cached[1]
        version = singboxing.installed_version(binary_path)
        text = ".".join(map(str, version)) if version else ""
        self._singbox_version_cache = (stamp, text)
        return text

    def _singbox_window(self) -> bool:
        return in_restart_window(self.cfg.apply.restart_window, self.now_time())

    def _apply_singbox(self, change: engine.SingboxChange | None) -> ApplyOutcome | None:
        """Применяет конфиг sing-box раньше конфига Xray (мосты должны слушать до того, как
        Xray на них сошлётся). None — всё в порядке, можно применять Xray."""
        if change is None or self._singbox_failed:
            return None
        outcome = self.singbox.apply(change.config, reload=change.reload)
        if outcome.mode in ("started", "reloaded", "removed"):
            count = 0 if change.config is None else len(change.config.get("inbounds") or [])
            self.notifier.event("singbox", {
                "started": f"sing-box запущен: мостов {count}",
                "reloaded": f"конфиг sing-box перечитан: мостов {count}",
                "removed": "sing-box больше не нужен — остановлен",
            }[outcome.mode])
            return None
        if outcome.mode == "rejected":
            self.notifier.event(
                "config", f"конфиг sing-box отклонён: {outcome.detail}", notify=True,
            )
            return ApplyOutcome("rejected", detail=f"sing-box check: {outcome.detail}")
        if outcome.mode in ("rollback", "failed"):
            self.notifier.event(
                "singbox", f"sing-box не принял новый конфиг ({outcome.mode}): {outcome.detail}",
                notify=True,
            )
            # Xray собран под отвергнутый конфиг: применять его нельзя, соберётся заново.
            self._rebuild_asked = True
            return ApplyOutcome("rejected", detail=f"sing-box: {outcome.detail}")
        return None  # unchanged, deferred

    def _switch_tier(self, view: list[NodeInfo], state: State, now: float) -> bool:
        """Классы серверов (cost.py): ручной приоритет, затем стоимость.

        Вверх: запасной класса лучше нынешнего прошёл скан (OK), сделанный уже после
        последней смены класса, — участниками становятся серверы того класса. Скан
        «после смены» не даёт вернуться к серверу по старому результату, полученному ещё
        до того, как он перестал отвечать. Пока работают серверы класса хуже лучшего,
        запасные классов лучше проверяются раз в TIER_RESCAN.

        Вниз: живых участников нет (ALL_DEAD или трафик несёт резервный выход — RESERVE)
        и живых запасных того же класса тоже — участниками становятся проверенные
        запасные ближайшего класса хуже, у которого они есть, в том числе лимитированные:
        безлимитные в приоритете, но когда они мертвы, работают лимитированные, сначала
        самые дешёвые (решение пользователя после испытаний 0.1.9; до того трафик в таком
        случае нёс один резервный выход). Классы дороже MEMBER_COST_MAX (и дороже нынешнего)
        пропускаются: их постоянные пробы съели бы квоту, трафик через них несёт резервный
        выход. Ждать rotate_after_min незачем: трафику идти больше некуда; только в класс
        дороже — не раньше COSTLIER_AFTER работы через резервный.
        Если у ближайшего класса хуже есть запасные без свежего скана, они
        сначала проверяются (лимитированные — дешёвым запросом, _scan_url): иначе шлюз
        ушёл бы в класс дороже по старым вердиктам. Назад — как вверх: безлимитные
        запасные проверяются раз в TIER_RESCAN, ответивший возвращает безлимитных в работу.

        Пока трафик ведёт сервер, выбранный вручную (xgw pin, панель), класс не меняется;
        выбранный не отвечает — меняется, как обычно: трафик тогда на автовыборе."""
        if self.inventory is None or self._manual_active():
            return False
        prices = self._prices()
        known = {node.fingerprint for node in self.inventory.nodes}
        members = [info for info in view if info.role == "proxy"]
        if not members or any(info.fingerprint not in known for info in members):
            return False  # состав ядра не сопоставлен с подпиской — менять вслепую нельзя
        tier = self._tier(view)
        assert tier is not None
        spares = [
            info for info in view
            if info.role == "spare" and info.fingerprint in known
            and info.fingerprint not in self.home_exits
            and not self._is_unstable(info.fingerprint)
        ]
        classes = sorted({self._klass(info.fingerprint, prices) for info in spares})
        scans = self._fresh_scans()

        def ready(klass: cost.Klass, verdicts: tuple[str, ...], after: float = 0.0):
            found = [
                info for info in spares
                if self._klass(info.fingerprint, prices) == klass
                and info.probe_tag in scans and scans[info.probe_tag]["verdict"] in verdicts
                and scans[info.probe_tag]["ts"] > after
            ]
            return sorted(found, key=lambda info: (
                scans[info.probe_tag]["verdict"] != "OK", scans[info.probe_tag]["seconds"],
            ))

        for klass in (item for item in classes if item < tier):
            better = ready(klass, ("OK",), after=self.tier_changed)
            if better:
                return self._change_tier(
                    tier, klass, better, urgent=state is State.ALL_DEAD, up=True,
                )
        self._queue_higher(spares, tier, scans)
        if state not in (State.ALL_DEAD, State.RESERVE) or ready(tier, REPLACEABLE_VERDICTS):
            return False  # живые есть — или их заменит _rotate тем же классом
        for klass in (item for item in classes if item > tier):
            if klass.cost > max(tier.cost, MEMBER_COST_MAX):
                continue  # дорого пробовать постоянно: трафик несёт резервный (_reserve_step)
            if (
                klass.cost > tier.cost and state is State.RESERVE
                and self.wall() - self.state_since < COSTLIER_AFTER
            ):
                return False  # пока трафик несёт резервный: сбой может быть коротким
            lower = ready(klass, REPLACEABLE_VERDICTS)
            if lower:
                return self._change_tier(tier, klass, lower, urgent=True, up=False)
            unchecked = [
                info.probe_tag for info in spares
                if self._klass(info.fingerprint, prices) == klass and info.probe_tag not in scans
            ]
            if unchecked:
                queued = set(self.scan_queue)
                self.scan_queue.extend(tag for tag in unchecked if tag not in queued)
                return False  # класс дороже — только когда в этом живых точно нет
        return False

    def _queue_higher(
        self, spares: list[NodeInfo], tier: cost.Klass, scans: dict[str, dict]
    ) -> None:
        """Запасные классов лучше нынешнего, давно не проверенные, — в начало очереди."""
        prices = self._prices()
        due = max(self.tier_changed, self.wall() - TIER_RESCAN)
        queued = set(self.scan_queue)
        for info in reversed(spares):
            if (
                self._klass(info.fingerprint, prices) < tier and info.probe_tag not in queued
                and (info.probe_tag not in scans or scans[info.probe_tag]["ts"] <= due)
            ):
                self.scan_queue.appendleft(info.probe_tag)

    def _change_tier(
        self, old: cost.Klass, new: cost.Klass, ready: list[NodeInfo], *, urgent: bool, up: bool
    ) -> bool:
        self.notifier.event("priority", tier_text(old, new, up=up))
        self.tier_changed = self.wall()
        # Класс участников сменился — и кандидаты в резервный выход другие: перепроверить.
        self.next_reserve_check = 0.0
        # Серверы пришли из запасных, прошедших скан, — проверять их заново незачем (кроме
        # лимитированных: их проверяли дешёвым запросом).
        self.vetted.update(info.fingerprint for info in ready if new.cost == 0)
        if new.cost == old.cost:
            reason = f"смена уровня приоритета: «{priority.level_name(new.rank)}»"
        else:
            reason = f"смена класса серверов: {cost.class_name(new, new.rank != old.rank)}"
        return self._rebuild(
            [info.fingerprint for info in ready], urgent=urgent, tier=new, reason=reason,
        )

    # --- резервный выход -------------------------------------------------------

    def _reserve_step(
        self, view: list[NodeInfo], applied: dict, state: State, now: float
    ) -> bool:
        """Резервный выход балансировщика (fallbackTag) — запасной класса хуже участников,
        обычно лимитированный с наименьшим множителем. Через него трафик идёт, только
        когда observatory считает мёртвыми всех участников; сам он observatory не
        пробуется и квоту зря не тратит.

        Его и лучших кандидатов на его место демон проверяет дешёвым запросом: раз в
        RESERVE_RECHECK по RESERVE_CANDIDATES лучших, а когда трафик не идёт и через
        резервный (ALL_DEAD), — сразу и всех. Резервным становится лучший прошедший
        проверку: класс лучше, затем нынешний резервный, затем OK быстрее SLOW."""
        if self.inventory is None:
            return False
        prices = self._prices()
        known = {node.fingerprint for node in self.inventory.nodes}
        tier = self._tier(view)
        if tier is None or any(info.fingerprint not in known for info in view):
            return False  # состав ядра не сопоставлен с подпиской
        current = builder.reserve_tag(applied)
        candidates = sorted(
            (
                info for info in view
                if info.role == "spare" and info.fingerprint not in self.home_exits
                and self._klass(info.fingerprint, prices) > tier
                and not self._is_unstable(info.fingerprint)
            ),
            key=lambda info: (self._klass(info.fingerprint, prices), info.tag != current),
        )
        if not candidates:
            self.reserve_round = None
            return False
        if self.reserve_round is None:
            # Трафик не идёт и через резервный: перепроверить сразу, как только наступил
            # ALL_DEAD, и дальше не реже ALL_DEAD_RETRY.
            urgent = state is State.ALL_DEAD and (
                self._urgent_round_for != self.state_since
                or self.wall() - self.reserve_round_at >= ALL_DEAD_RETRY
            )
            if now < self.next_reserve_check and not urgent:
                return False
            self.reserve_round_at = self.wall()
            if state is State.ALL_DEAD:
                self._urgent_round_for = self.state_since
            chosen = candidates if state is State.ALL_DEAD else candidates[:RESERVE_CANDIDATES]
            tags = [info.probe_tag for info in chosen]
            current_info = next((info for info in candidates if info.tag == current), None)
            if current_info is not None and current_info.probe_tag not in tags:
                tags.append(current_info.probe_tag)
            self.reserve_round = (self.wall(), tags)
            self.next_reserve_check = now + jitter(RESERVE_RECHECK)
            queued = set(self.scan_queue)
            fresh = [tag for tag in tags if tag not in queued]
            if state is State.ALL_DEAD:
                self.scan_queue.extendleft(reversed(fresh))
            else:
                self.scan_queue.extend(fresh)
            return False
        started, tags = self.reserve_round
        waiting = set(tags) & set(self.scan_queue)
        if waiting and self.wall() - started < RESERVE_ROUND_WAIT:
            return False
        self.reserve_round = None
        scans = self.store.scans()
        passed = [
            info for info in candidates
            if info.probe_tag in tags and info.probe_tag in scans
            and scans[info.probe_tag]["ts"] >= started
            and scans[info.probe_tag]["verdict"] in REPLACEABLE_VERDICTS
        ]
        if not passed:
            note = "резервного сервера нет: ни один из проверенных запасных классом хуже не ответил"
            if note != self._reserve_note:
                self._reserve_note = note
                self.notifier.event("reserve", note)
            return False
        best = min(passed, key=lambda info: (
            self._klass(info.fingerprint, prices), info.tag != current,
            scans[info.probe_tag]["verdict"] != "OK", scans[info.probe_tag]["seconds"],
        ))
        self._reserve_note = ""
        if best.tag == current:
            return False
        node = next(node for node in self.inventory.nodes if node.fingerprint == best.fingerprint)
        price = cost.describe(prices.get(best.fingerprint, 1.0))
        self.notifier.event(
            "reserve",
            f"резервный сервер — «{node.name}» ({price}): через него пойдёт трафик, если "
            "серверы в работе перестанут отвечать",
        )
        return self._rebuild(
            None, urgent=state is State.ALL_DEAD, reason="смена резервного сервера",
            reserve=best.fingerprint,
        )

    def _reserve_node(self, applied: dict | None):
        if self.inventory is None:
            return None
        fingerprint = builder.reserve_fingerprint(applied, self.inventory.nodes)
        return next(
            (node for node in self.inventory.nodes if node.fingerprint == fingerprint), None
        )

    def _reserve_label(self, applied: dict | None) -> str:
        """« «имя» (x1)» — для событий; резервный не опознан — пусто."""
        node = self._reserve_node(applied)
        if node is None:
            return ""
        price = self._prices().get(node.fingerprint, 1.0)
        return f" «{node.name}» ({cost.describe(price)})"

    def _reserve_action(self, label: str) -> str:
        """Текст состояния RESERVE: через какой сервер идёт трафик (_reserve_label)."""
        return (
            f"серверы в работе не отвечают — трафик идёт через резервный сервер{label}; "
            "Xray вернётся к ним сам, как только они ответят; поиск замены среди запасных"
        )

    # --- ручной выбор сервера (pin.py) ------------------------------------------

    def _pin(self) -> dict | None:
        """Запись ручного выбора — действующая или с вышедшим сроком."""
        return pinning.parse(self.store.get_meta(pinning.META))

    def _manual_pin(self) -> dict | None:
        """Ручной выбор, срок которого не вышел (бессрочный — всегда); выбранный сервер при
        этом может и не отвечать — тогда трафик ведёт автовыбор (_manual_active)."""
        pin = self._pin()
        return pin if pinning.active(pin, self.wall()) else None

    def _manual_active(self) -> bool:
        """Трафик сейчас ведёт ручной выбор: он действует, и выбранный сервер отвечает."""
        pin = self._manual_pin()
        return pin is not None and not pin.get("down")

    def _save_pin(self, pin: dict | None) -> None:
        self.store.set_meta(pinning.META, pinning.dumps(pin) if pin else "")

    def _manual_step(
        self, view: list[NodeInfo], applied: dict | None, observatory: dict, signals: Signals,
    ) -> None:
        """Ручной выбор сервера — как в клиентах VPN, но так, чтобы интернет не пропал.

        Пока выбранный отвечает, он закреплён в ядре (`xray api bo`; перезапуск Xray и
        adrules закрепление сбрасывают — оно сверяется на каждом шаге). Тег сверяется по
        серверу (pin.resolve): запасной, ставший участником, меняет `spare-…` на `proxy-…`,
        а закрепление на тег, которого в конфиге нет, остановило бы весь трафик.

        Перестал отвечать (ядро сочло участника мёртвым или подряд не прошли сквозные
        проверки, а они идут через него) — закрепление снимается, трафик ведёт автовыбор, а
        выбор ждёт (`down`): участника снова оживит ядро, запасного раз в PIN_RECHECK
        проверяет собственная проба. Ответил — трафик снова через него. Об уходе и
        возврате уведомляем: выбор делал человек. Сервера больше нет в конфиге (убран из
        подписки, отключён) — выбор снимается, тоже с уведомлением."""
        pin = self._pin()
        if pin is None:
            return
        name = pin.get("name") or pin["tag"]
        if not pinning.active(pin, self.wall()):
            if self._release_pin(pin["tag"]):
                self._save_pin(None)
                self.notifier.event("pin", f"ручной выбор «{name}» снят по истечении срока")
            return
        if not signals.xray_ok:
            return  # перезапуск Xray закрепление сбросит сам — вернём, когда ядро ответит
        info = pinning.resolve(pin, view)
        if info is None:
            if self._release_pin(pin["tag"]):
                self._save_pin(None)
                self.notifier.event(
                    "pin",
                    f"выбранного вручную сервера «{name}» больше нет среди серверов (убран из "
                    "подписки или отключён) — сервер снова выбирает шлюз",
                    notify=True,
                )
            return
        if info.tag != pin["tag"]:
            pin["tag"] = info.tag
            self._save_pin(pin)
        if pin.get("down"):
            if self._manual_answers(info, applied, observatory):
                pin["down"] = None
                self._save_pin(pin)
                self._hold_pin(info.tag)
                self.notifier.event(
                    "pin", f"выбранный вручную сервер «{name}» снова отвечает — трафик опять "
                    "идёт через него", notify=True,
                )
            return
        entry = observatory.get(info.tag)
        failed_e2e = not signals.e2e_ok and not self.probe_target and (
            signals.e2e_fail_streak >= max(1, min(2, self.cfg.watchdog.fail_threshold - 1))
        )
        if (entry is not None and entry["alive"] is False) or failed_e2e:
            pin["down"] = self.wall()
            self._save_pin(pin)
            self._pin_recheck_at = self.clock() + PIN_RECHECK
            self._release_pin(info.tag)
            self.notifier.event(
                "pin",
                f"выбранный вручную сервер «{name}» не отвечает — трафик идёт через серверы, "
                "выбранные автоматически; когда он снова ответит, шлюз вернётся к нему",
                notify=True,
            )
            return
        self._hold_pin(info.tag)

    def _manual_answers(
        self, info: NodeInfo, applied: dict | None, observatory: dict
    ) -> bool:
        """Снова ли отвечает выбранный: участника пробует ядро, запасного — раз в
        PIN_RECHECK собственная проба (лимитированного — дешёвым запросом, _scan_url)."""
        entry = observatory.get(info.tag)
        if info.role == "proxy" and entry is not None:
            return bool(entry["alive"])
        if self.clock() < self._pin_recheck_at:
            return False
        self._pin_recheck_at = self.clock() + PIN_RECHECK
        password, _ports = builder.probe_state(applied)
        if not password or not info.probe_port:
            return False
        self._scanned = True
        result = self._probe_scan(info, password)
        if result.kind == "cancelled":
            self._pin_recheck_at = 0.0  # проверка не состоялась — повторить сразу
            return False
        self.store.save_scan(
            info.probe_tag, result.verdict, result.bytes_read, result.seconds, result.error,
            ts=self.wall(),
        )
        return result.verdict in REPLACEABLE_VERDICTS

    def _hold_pin(self, tag: str) -> None:
        """Закрепляет выбранный в ядре, если закрепление сбросилось или указывает не на него."""
        try:
            if self.api.balancer_state(BALANCER_TAG).override != tag:
                self.api.pin(BALANCER_TAG, tag)
        except ApiError as exc:
            self.log.error("выбранный вручную сервер %s не закреплён: %s", tag, exc)

    def _release_pin(self, tag: str) -> bool:
        """Снимает закрепление ядра, если оно — на этом сервере; False — ядро не ответило."""
        try:
            override = self.api.balancer_state(BALANCER_TAG).override
            if override and pinning.same_server(override, tag):
                self.api.unpin(BALANCER_TAG)
        except ApiError as exc:
            self.log.error("закрепление сервера %s не снято: %s", tag, exc)
            return False
        return True

    # --- основной сервер (watch/speed.py) -------------------------------------------

    def _main_step(
        self, view: list[NodeInfo], applied: dict | None, observatory: dict,
        state: State, signals: Signals, now: float,
    ) -> None:
        """Основной сервер: выбрать, закрепить в ядре, при отказе сразу сменить, после
        очередного замера — сменить на заметно более быстрый, в том числе запасной (его
        сначала переводят в работу).

        Закрепление в ядре не смотрит на здоровье сервера, поэтому снимается во всех
        состояниях, кроме HEALTHY и DEGRADED: без живых участников трафик должен уйти на
        резервный выход (fallbackTag), а при XRAY_DOWN и прочем выбирать не из чего.
        Ручное закрепление (xgw pin, панель) главнее: пока оно действует, демон его не
        трогает и основной не выбирает, но серверы замеряет, как обычно, — скорость видна в
        панели, а итоги замеров основной сверит, когда выбор снимут."""
        members = [info for info in view if info.role == "proxy"]
        if not signals.xray_ok:
            # Снимать нечего: перезапуск Xray закрепление сбросит сам.
            if self.main is not None:
                self._set_main(None)
            self._main_pinned = None
            return
        if not (
            self.cfg.speed.sticky and not self.probe_target
            and state in (State.HEALTHY, State.DEGRADED) and members
        ):
            self._release_main()
            return
        if self.cfg.speed.guard:
            # Пассивная оценка — до замеров: участнику, через которого и так качают, замер не
            # нужен (ТЗ R5.2).
            self._passive_step(view)
        measured = self._speed_step(view, applied, observatory, now)
        self._guard_step(view, applied, observatory)
        alive = [
            info for info in members if (observatory.get(info.tag) or {}).get("alive")
        ]
        candidates = [self._candidate(info, observatory) for info in alive]
        if self._manual_active():
            if measured:
                self._compare_due = True
            return
        if self._main_suspended:
            if not signals.e2e_ok:
                return
            self._main_suspended = False
            self.notifier.event(
                "main", "загрузка снова проходит — основной сервер выбирается заново"
            )
        current = self._main_candidate(members, observatory, signals)
        if current is None and self._main_suspended:
            return
        if current is None:
            self._choose_main(candidates)
        elif self._promoted is not None:
            self._take_promoted(members, observatory)
        elif measured or self._compare_due:
            self._compare_due = False
            self._compare_main(view, observatory)
        if self.main is not None:
            self._pin_main(self.main["tag"])

    def _main_candidate(
        self, members: list[NodeInfo], observatory: dict, signals: Signals
    ) -> speed.Candidate | None:
        """Нынешний основной, если он годен; иначе запись о нём убирается (с событием).
        Ядро ещё не пробовало сервер (только что перезапущено) — это не отказ."""
        record = self.main
        if record is None:
            return None
        member = next((info for info in members if info.tag == record["tag"]), None)
        name = f"«{record['name']}»" if record.get("name") else record["tag"]
        if member is None:
            self._set_main(None)
            self.notifier.event("main", f"основной сервер {name} больше не в работе")
            return None
        entry = observatory.get(member.tag)
        dead = entry is not None and not entry.get("alive")
        reason = ""
        if dead:
            reason = "не отвечает пробам ядра"
        elif not signals.e2e_ok:
            reason = "загрузка через него не прошла"
        if not reason:
            return self._candidate(member, observatory)
        wall = self.wall()
        self.main_cooldown[record["key"]] = wall + MAIN_COOLDOWN
        # Замену ищут той же страны: сайты не видят прыжка между странами (_choose_main).
        node = self._node(member)
        self._lost_main = {
            "country": record.get("country") or (node.country if node else ""),
            "source": record.get("source") or (node.source if node else ""),
        }
        self._set_main(None)
        if not dead:  # пробы ядра проходят, а загрузка — нет
            carousel = wall - self._main_failed_at < MAIN_CAROUSEL
            self._main_failed_at = wall
            if carousel:
                self._main_suspended = True
                self._release_main()
                self.notifier.event(
                    "main",
                    f"загрузка не прошла и через новый основной сервер {name} — дело, похоже, "
                    "не в серверах; пока она не пройдёт, сервер выбирает ядро",
                )
                return None
        self.notifier.event("main", f"основной сервер {name} {reason} — выбираю другой")
        return None

    def _node(self, info: NodeInfo):
        """Узел подписки (имя, страна, подписка) по отпечатку; None — не сопоставлен."""
        nodes = self.inventory.nodes if self.inventory is not None else ()
        return next((node for node in nodes if node.fingerprint == info.fingerprint), None)

    @staticmethod
    def _speed_key(info: NodeInfo) -> str:
        return info.fingerprint if len(info.fingerprint) >= 8 else info.tag

    def _candidate(self, info: NodeInfo, observatory: dict) -> speed.Candidate:
        key = self._speed_key(info)
        record = self._speeds().get(key) or {}
        mbps = record.get("mbps")
        hours = speed.every_hours(
            self.cfg, self._prices().get(info.fingerprint, 1.0), spare=info.role == "spare",
        )
        fresh = hours > 0 and (
            self.wall() - float(record.get("ts") or 0) <= SPEED_FRESH * hours * 3600.0
        )
        value = float(mbps) if fresh and isinstance(mbps, (int, float)) else None
        if value is None and hours > 0 and self.cfg.speed.guard:
            # Замер устарел, но трафик клиентов через сервер сам показал полосу (ТЗ R5).
            value = self.guard.healthy(key, SPEED_FRESH * hours * 3600.0)
        delay = (observatory.get(info.tag) or {}).get("delay")
        node = self._node(info)
        return speed.Candidate(
            tag=info.tag, key=key, name=node.name if node is not None else "",
            mbps=value,
            delay_ms=delay * 1000.0 if isinstance(delay, (int, float)) else None,
            country=node.country if node is not None else "",
            source=node.source if node is not None else "",
            spare=info.role == "spare",
        )

    def _node_name(self, info: NodeInfo) -> str:
        node = self._node(info)
        return node.name if node is not None else ""

    def _choose_main(self, candidates: list[speed.Candidate]) -> None:
        """Новый основной: лучший из живых, кроме недавно отказавших (если есть другие).
        Прежний основной отказал — сначала ищется той же страны из другой подписки, потом
        той же страны: без прыжка по странам (ASSUMPTIONS п. 224)."""
        wall = self.wall()
        rested = [item for item in candidates if self.main_cooldown.get(item.key, 0.0) <= wall]
        lost, self._lost_main = self._lost_main, None
        pool = rested or candidates
        pick = (
            speed.best_like(pool, lost["country"], lost["source"]) if lost else speed.best(pool)
        )
        if pick is None:
            self._release_main()  # живых нет: выбирает ядро (и резервный выход)
            return
        # Кто-то из живых ещё не замерен — выбор предварительный (basis «delay»): его замер
        # может сменить основной сразу, без hold_minutes.
        pending = any(item.mbps is None for item in candidates)
        self._set_main(pick, final=not pending)
        basis = "по задержке, скорость ещё не замерена" if pick.mbps is None else (
            "по скорости, остальные ещё замеряются" if pending else "по скорости"
        )
        if lost and lost["country"] and pick.country == lost["country"]:
            basis += ", той же страны"
        self.notifier.event("main", f"основной сервер — {speed.describe(pick)}, {basis}")

    def _spare_candidates(self, view: list[NodeInfo]) -> list[speed.Candidate]:
        """Запасные, которые могут стать основным: того же класса, что участники, прошли
        последний скан, не выходят в домашнюю страну и замерены недавно."""
        prices = self._prices()
        tier = self._tier(view)
        scans = self._fresh_scans()
        result = []
        for info in view:
            if (
                info.role != "spare" or info.fingerprint in self.home_exits
                or self._klass(info.fingerprint, prices) != tier
                or (scans.get(info.probe_tag) or {}).get("verdict") not in REPLACEABLE_VERDICTS
                or self._is_unstable(info.fingerprint)
            ):
                continue
            candidate = self._candidate(info, {})
            if candidate.mbps is not None:
                result.append(candidate)
        return result

    def _compare_main(self, view: list[NodeInfo], observatory: dict) -> None:
        """Есть свежий замер: сменить основной, если другой живой сервер — участник или
        запасной — быстрее на speed.gain_pct и основной продержался speed.hold_minutes
        (выбранный по задержке, до первого замера, держится без этого срока). Не каждые
        полминуты, как leastPing до 0.1.9, но и не мёртвой хваткой (ASSUMPTIONS п. 224)."""
        record = self.main
        assert record is not None
        alive = [
            self._candidate(info, observatory) for info in view
            if info.role == "proxy" and (observatory.get(info.tag) or {}).get("alive")
        ]
        current = next((item for item in alive if item.tag == record["tag"]), None)
        if current is None:
            return
        wall = self.wall()
        pool = [
            item for item in [*alive, *self._spare_candidates(view)]
            if item.key != current.key and self.main_cooldown.get(item.key, 0.0) <= wall
        ]
        rival = speed.best(pool)
        by_delay = record.get("basis") != "speed"
        held = wall - float(record.get("since") or 0)
        if (
            rival is not None and speed.faster(rival, current, self.cfg.speed.gain_pct)
            and (by_delay or held >= self.cfg.speed.hold_minutes * 60.0)
        ):
            if rival.spare:
                self._promote(view, observatory, rival, current)
                return
            self._set_main(rival, final=all(item.mbps is not None for item in alive))
            self.notifier.event(
                "main",
                f"основной сервер сменён: {speed.describe(rival)} быстрее, чем "
                f"{speed.describe(current)}",
            )
        elif by_delay and all(item.mbps is not None for item in alive):
            # Замерены все живые участники — выбор окончательный, дальше держится hold_minutes.
            self._set_main(current, since=float(record.get("since") or self.wall()))

    def _promote(
        self, view: list[NodeInfo], observatory: dict, rival: speed.Candidate,
        current: speed.Candidate,
    ) -> None:
        """Запасной быстрее основного: встаёт в работу вместо слабейшего участника (не
        основного) и становится основным, как только ядро его проверит (_take_promoted)."""
        if self.inventory is None:
            return
        by_fingerprint = {node.fingerprint: node for node in self.inventory.nodes}
        members = [info for info in view if info.role == "proxy"]
        node = by_fingerprint.get(rival.key)
        if node is None or any(info.fingerprint not in by_fingerprint for info in members):
            return  # состав ядра не сопоставлен с подпиской — менять вслепую нельзя
        weakest = [
            info for info in members if self._speed_key(info) != current.key
        ]
        if not weakest:
            return
        drop = min(weakest, key=lambda info: self._weakness(info, observatory))
        dropped = self._node_name(drop) or drop.tag
        self.notifier.event(
            "main",
            f"запасной {speed.describe(rival)} быстрее основного {speed.describe(current)} — "
            f"встаёт в работу вместо «{dropped}» и станет основным",
        )
        prefer = preferred_members(members, Rotation(replacements=[(drop.tag, node)]))
        if self._rebuild(prefer, urgent=False, reason="перевод запасного в работу"):
            self._promoted = {
                "key": node.fingerprint, "name": node.name, "since": self.wall(),
                "was": current.name or current.tag,
            }

    def _weakness(self, info: NodeInfo, observatory: dict) -> tuple:
        """Кого из участников выводить первым: мёртвого, потом медленного по замеру, потом
        с наибольшей задержкой; незамеренного — последним (о нём ещё ничего не известно)."""
        candidate = self._candidate(info, observatory)
        alive = bool((observatory.get(info.tag) or {}).get("alive"))
        return (
            alive, candidate.mbps is None, candidate.mbps or 0.0, -(candidate.delay_ms or 0.0),
        )

    def _take_promoted(self, members: list[NodeInfo], observatory: dict) -> None:
        """Переведённый в работу запасной проверен ядром — он основной; не ответил или так и
        не встал в работу за PROMOTE_WAIT — основной прежний."""
        promoted = self._promoted
        assert promoted is not None
        name = f"«{promoted['name']}»" if promoted.get("name") else promoted["key"]
        member = next((info for info in members if info.fingerprint == promoted["key"]), None)
        entry = observatory.get(member.tag) if member is not None else None
        if entry is None:
            if self.wall() - float(promoted["since"]) > PROMOTE_WAIT:
                self._promoted = None
                self.notifier.event(
                    "main", f"{name} так и не встал в работу — основной сервер прежний"
                )
            return  # ещё не в работе или ядро его не проверило
        self._promoted = None
        if not entry.get("alive"):
            self.main_cooldown[promoted["key"]] = self.wall() + MAIN_COOLDOWN
            self.notifier.event(
                "main", f"{name} не ответил ядру после перевода в работу — основной прежний"
            )
            return
        assert member is not None
        pick = self._candidate(member, observatory)
        self._set_main(pick)
        self.notifier.event(
            "main", f"основной сервер сменён: {speed.describe(pick)} из запасных быстрее, "
            f"чем «{promoted['was']}»",
        )

    # --- замеры скорости ---------------------------------------------------------------

    def _speed_targets(self, view: list[NodeInfo], observatory: dict) -> list[NodeInfo]:
        """Кого замерять: живые участники и запасные, прошедшие последний скан (OK, SLOW),
        сначала участники. Не замеряются x100 и дороже, серверы с неизвестной ценой (не
        из чего выбрать размер загрузки) и выходящие в домашнюю страну."""
        prices = self._prices()
        scans = self._fresh_scans()
        targets = []
        for info in view:
            price = prices.get(info.fingerprint)
            if price is None or not speed.every_hours(self.cfg, price):
                continue
            if info.fingerprint in self.home_exits:
                continue
            if info.role == "proxy":
                if not (observatory.get(info.tag) or {}).get("alive"):
                    continue
            elif (scans.get(info.probe_tag) or {}).get("verdict") not in REPLACEABLE_VERDICTS:
                continue
            targets.append(info)
        return sorted(targets, key=lambda info: info.role != "proxy")

    def _speed_due(self, info: NodeInfo, prices: dict[str, float]) -> bool:
        """Замер сервера устарел: старше срока его класса (speed.every_hours). Участник, через
        который клиенты качают не меньше speed.passive_mbps, исправен и без замера (ТЗ R5)."""
        hours = speed.every_hours(
            self.cfg, prices.get(info.fingerprint, 1.0), spare=info.role == "spare",
        )
        key = self._speed_key(info)
        if (
            info.role == "proxy" and self.cfg.speed.guard
            and self.guard.healthy(key, hours * 3600.0) is not None
        ):
            return False
        record = self._speeds().get(key)
        return record is None or self.wall() - float(record.get("ts") or 0) >= hours * 3600.0

    def _speed_step(
        self, view: list[NodeInfo], applied: dict | None, observatory: dict, now: float
    ) -> bool:
        """Замеры скорости всех живых серверов: каждый — раз в срок своего класса
        (безлимитные — speed.unlimited_hours, лимитированные — speed.limited_hours) и все
        сразу — по кнопке. Не в шаге со сканом; при занятом канале фоновый замер ждёт, но
        не дольше SPEED_FORCE_AFTER. True — появился новый замер (сравнить с основным)."""
        if not (self.cfg.speed.unlimited_hours or self.cfg.speed.limited_hours):
            self.speed_queue.clear()
            self._speed_forced.clear()
            self._speed_one.clear()
            self._speed_any.clear()
            self._speed_asked = False
            self.speed_total = self.speed_done = 0
            return False
        targets = self._speed_targets(view, observatory)
        self._speed_one_step(view, targets)
        live = {info.probe_tag for info in targets}
        # Сервер перестал отвечать или ушёл из списка, пока ждал замера.
        self.speed_queue = deque(tag for tag in self.speed_queue if tag in live)
        self._speed_forced &= set(self.speed_queue)
        self._speed_any &= set(self.speed_queue)
        queued = set(self.speed_queue)
        if self._speed_asked:
            self._speed_asked = False
            single = [tag for tag in self.speed_queue if tag in self._speed_any]
            self.speed_queue = deque(
                single + [info.probe_tag for info in targets if info.probe_tag not in single]
            )
            self._speed_forced = set(self.speed_queue)
            self.speed_total, self.speed_done = len(self.speed_queue), 0
        else:
            prices = self._prices()
            for info in targets:
                if info.probe_tag not in queued and self._speed_due(info, prices):
                    self.speed_queue.append(info.probe_tag)
                    self.speed_total += 1
        self._guard_queue(targets)
        self._speed_waiting = False
        if not self.speed_queue:
            self.speed_total = self.speed_done = 0
            self._speed_deferred_since = self._speed_scanned_since = None
            return False
        # Кнопка у сервера — первой, затем участники: по ним выбирают основной (порядок внутри
        # групп сохраняется).
        members = {info.probe_tag for info in targets if info.role == "proxy"}
        self.speed_queue = deque(sorted(
            self.speed_queue,
            key=lambda tag: (
                tag not in self._speed_any, tag not in self._speed_small, tag not in members,
            ),
        ))
        if self.stopping:
            return False
        forced = self.speed_queue[0] in self._speed_forced
        single = self._scanned
        if not self._scanned:
            self._speed_scanned_since = None
        elif not forced:
            # Шаг уже занят сканом: фоновый замер ждёт шага без скана, но не дольше
            # SPEED_SCAN_WAIT; заказанный идёт и в таком шаге (SPEED_SCAN_WAIT).
            if self._speed_scanned_since is None:
                self._speed_scanned_since = now
            if now - self._speed_scanned_since < SPEED_SCAN_WAIT:
                return False
        if self._busy and not forced:
            # Ждать — с первого занятого шага и до конца очереди: прождав час, очередь
            # дорабатывает и при занятом канале, а не ждёт снова после каждого сервера.
            if self._speed_deferred_since is None:
                self._speed_deferred_since = now
            if now - self._speed_deferred_since < SPEED_FORCE_AFTER:
                self._speed_waiting = True
                return False
        self._speed_scanned_since = None
        return self._measure_queue(targets, applied, busy=self._busy, single=single) > 0

    def _speed_one_step(self, view: list[NodeInfo], targets: list[NodeInfo]) -> None:
        """Кнопка у одного сервера: он — первым в очередь, замер не ждёт свободного канала.
        Сервер, которого фоновый замер не взял бы (запасной без свежего скана, участник,
        которого ядро сочло мёртвым), всё равно замеряется — его просил человек; x100 и
        дороже — нет (панель такую кнопку не показывает). Запрос на сервер, которого уже
        нет в конфиге, снимается."""
        asked, self._speed_one = self._speed_one, set()
        if not asked and not self._speed_any:
            return
        prices = self._prices()
        present = {info.probe_tag for info in targets}
        for info in view:
            wanted = bool({info.tag, info.fingerprint} & asked)
            if not (wanted or info.probe_tag in self._speed_any) or not info.probe_port:
                continue
            if prices.get(info.fingerprint, 1.0) >= speed.SKIP_PRICE:
                continue
            if info.probe_tag not in present:
                # И на следующих шагах, пока замер ждёт своей очереди (шаг со сканом).
                targets.append(info)
                present.add(info.probe_tag)
            if not wanted:
                continue
            if info.probe_tag in self.speed_queue:
                self.speed_queue.remove(info.probe_tag)
            else:
                self.speed_total += 1
            self.speed_queue.appendleft(info.probe_tag)
            self._speed_forced.add(info.probe_tag)
            self._speed_any.add(info.probe_tag)

    def _measure_queue(
        self, targets: list[NodeInfo], applied: dict | None, *, busy: bool, single: bool = False,
    ) -> int:
        """Замеры из очереди: фоновый — один за шаг, по кнопке — подряд, пока шаг не занял
        SPEED_STEP_SECONDS (single — один: в шаге уже шёл скан); сколько серверов замерено."""
        password, _ports = builder.probe_state(applied or {})
        by_probe = {info.probe_tag: info for info in targets}
        started = time.monotonic()
        count = 0
        while self.speed_queue and not self.stopping:
            if count and (
                single or self.speed_queue[0] not in self._speed_forced
                or time.monotonic() - started >= SPEED_STEP_SECONDS
            ):
                break
            probe_tag = self.speed_queue.popleft()
            self._speed_forced.discard(probe_tag)
            info = by_probe.get(probe_tag)
            if info is None or not password:
                continue
            small = probe_tag in self._speed_small
            self._speed_small.discard(probe_tag)
            before = self._traffic_now(info.tag) if info.role == "proxy" else None
            clock = time.monotonic()
            result = self._speed(info, password, small=small)
            elapsed = time.monotonic() - clock
            self._own_traffic += result.bytes_read
            self._own_by_tag[info.tag] = self._own_by_tag.get(info.tag, 0) + result.bytes_read
            if small:
                self.guard.spend(result.bytes_read)
            if result.mbps is None and self.stopping:
                # Замер прервала остановка демона: это не неудача сервера.
                self.speed_queue.appendleft(probe_tag)
                break
            background = 0.0
            span = max(elapsed, result.seconds)
            if before is not None and result.mbps is not None and span > 0:
                after = self._traffic_now(info.tag)
                if after is not None and after >= before:
                    # Трафик клиентов через этот же сервер за время замера (ТЗ R5.3).
                    extra = max(0, after - before - result.bytes_read)
                    background = round(extra * 8 / span / speedguard.MB, 1)
            total = result.mbps if result.mbps is None else round(result.mbps + background, 1)
            records = self._speeds()
            records[self._speed_key(info)] = {
                "mbps": total, "bytes": result.bytes_read, "seconds": result.seconds,
                "error": result.error, "ts": self.wall(),
                # Замер при занятом канале (фоновый ждал дольше SPEED_FORCE_AFTER либо по
                # кнопке): цифра может быть занижена чужой загрузкой.
                **({"busy": True} if busy else {}),
                # Сумма (ТЗ R5.3): сам замер и трафик клиентов через сервер за это время.
                **({"test_mbps": result.mbps, "bg_mbps": background} if background else {}),
            }
            self._save_speeds(records)
            if info.role == "proxy" and self.cfg.speed.guard:
                self.guard.note_total(self._speed_key(info), total)
            self.speed_done += 1
            count += 1
            if result.mbps is None:
                self.log.info("замер скорости %s не удался: %s", info.tag, result.error)
            else:
                self.log.info(
                    "замер скорости %s: %s, %d байт за %.1f с", info.tag,
                    speed.mbps_text(result.mbps), result.bytes_read, result.seconds,
                )
        return count

    def _speed(self, info: NodeInfo, password: str, *, small: bool = False) -> speed.SpeedResult:
        """Замер сервера; small — короткий (не больше speed.spare_mb): повторные замеры
        подозрительного участника и замеры кандидатов на его место (ТЗ R6)."""
        price = self._prices().get(info.fingerprint, 1.0)
        size = speed.size_mb(self.cfg, price, spare=small or info.role == "spare")
        return speed.measure(
            info, self.cfg, probe_pass=password, max_mb=size, cancel=self._stop,
        )

    def _traffic_now(self, tag: str) -> int | None:
        """Счётчик трафика сервера сейчас (uplink + downlink, свежий /debug/vars)."""
        try:
            fresh = metrics.fetch_metrics(self.cfg.xray.metrics_port)
        except Exception as exc:
            self.log.debug("счётчики трафика недоступны: %s", exc)
            return None
        return metrics.outbound_totals(fresh).get(tag)

    # --- контроль скорости участников (ТЗ R5–R8, watch/guard.py) ----------------------

    def _guard_queue(self, targets: list[NodeInfo]) -> None:
        """Подозрительных участников (низкая оценка, трафик через них идёт медленно) —
        замерить снова, коротко и не дожидаясь свободного канала: сумма с трафиком клиентов
        и так учитывает занятый канал."""
        if not self.cfg.speed.guard:
            return
        due = set(self.guard.due())
        if not due:
            return
        window = self.cfg.speed.low_minutes * 60.0 / self.cfg.speed.low_count
        for info in targets:
            key = self._speed_key(info)
            if info.role != "proxy" or key not in due:
                continue
            # Следующий раз — после этого замера (guard.note_total), а пока не ставить снова.
            self.guard.recheck_at[key] = self.wall() + window
            if info.probe_tag in self.speed_queue:
                continue
            if not self.guard.can_spend(int(self.cfg.speed.spare_mb * speedguard.MB)):
                continue
            self.speed_queue.appendleft(info.probe_tag)
            self._speed_forced.add(info.probe_tag)
            self._speed_small.add(info.probe_tag)
            self.speed_total += 1

    def _passive_step(self, view: list[NodeInfo]) -> None:
        """Пассивная оценка (ТЗ R5): скорость реального трафика каждого участника по
        счётчикам ядра — раз в speed.passive_seconds, без лишнего трафика."""
        members = {info.tag: self._speed_key(info) for info in view if info.role == "proxy"}
        counters = {
            tag: value for tag, value in metrics.outbound_totals(self._metrics).items()
            if tag in members
        }
        if not counters:
            return
        sampled = self.guard.sample(counters, self._own_by_tag, members)
        if sampled is None:
            return
        self._own_by_tag = {}
        records = self.guard.passive_records()
        text = json.dumps(records, sort_keys=True)
        if text != self._passive_saved:
            self._passive_saved = text
            self.store.set_meta(speedguard.META_PASSIVE, text)

    def _guard_step(self, view: list[NodeInfo], applied: dict | None, observatory: dict) -> None:
        """Уход с «придушенного» участника (ТЗ R6–R8): поиск замены среди кандидатов —
        по одному замеру за шаг, ранняя остановка, гистерезис, пауза после глобальной
        просадки, бюджет трафика."""
        if not self.cfg.speed.guard:
            self.guard.episode = None
            return
        if self.guard.episode is not None:
            self._guard_episode(view, applied, observatory)
            return
        if not self.guard.throttled:
            return
        if self.guard.cooling():
            self.guard.throttled.clear()  # после паузы замеры покажут заново, если не прошло
            return
        members = {
            self._speed_key(info): info for info in view
            if info.role == "proxy" and (observatory.get(info.tag) or {}).get("alive")
        }
        key = next((item for item in sorted(self.guard.throttled) if item in members), None)
        if key is None:
            self.guard.throttled.clear()  # придушенный уже не в работе (замена, отказ)
            return
        mbps = self.guard.throttled.pop(key)
        current = members[key]
        name = self._node_name(current) or current.tag
        role = self._guard_role(current)
        candidates = self._guard_candidates(view, observatory, current, role)
        low = (f"{self.cfg.speed.low_count} оценки подряд ниже {self.cfg.speed.low_mbps} Мбит/с "
               f"за {self.cfg.speed.low_minutes} мин (последняя — {speed.mbps_text(mbps)})")
        if not candidates:
            self._guard_event(f"«{name}» придушен: {low}, а заменить некем — нет живых "
                              "кандидатов со свежей проверкой")
            self.guard.cool_down()
            return
        size = int(self.cfg.speed.spare_mb * speedguard.MB)
        if not self.guard.can_spend(size):
            self._guard_event(
                f"«{name}» придушен: {low}, но суточный лимит трафика на поиск замены "
                f"(speed.guard_daily_mb = {self.cfg.speed.guard_daily_mb} МБ) исчерпан"
            )
            return
        self.guard.episode = {
            "key": key, "tag": current.tag, "name": name, "role": role, "mbps": mbps,
            "queue": [info.probe_tag for info in candidates], "results": {}, "spent": 0,
            "tried": 0, "total": len(candidates),
        }
        self._guard_event(
            f"«{name}» придушен: {low} — ищу замену среди {len(candidates)} кандидатов, "
            "замеряю по одному"
        )

    def _guard_role(self, info: NodeInfo) -> str:
        """Чем был придушенный: выбранный вручную (pin), основной (main) или участник."""
        pin = self._manual_pin()
        if pin is not None and not pin.get("down") and pinning.same_server(pin["tag"], info.tag):
            return "pin"
        if self.main is not None and self.main.get("tag") == info.tag:
            return "main"
        return "member"

    def _guard_candidates(
        self, view: list[NodeInfo], observatory: dict, current: NodeInfo, role: str,
    ) -> list[NodeInfo]:
        """Кандидаты на место придушенного (ТЗ R6.2): живые участники (для основного и
        выбранного вручную — переход без перестройки конфига) и запасные со свежей проверкой
        OK — того же класса, что участники (общий пул всех подписок — issue #2), не x100, не
        из подписки с исчерпанной квотой, не «нестабильные по ТСПУ», не выходящие в домашнюю
        страну. Сначала — быстрые по прошлым замерам; не больше speed.candidates."""
        if self.inventory is None:
            return []
        prices = self._prices()
        tier = self._tier(view)
        scans = self._fresh_scans()
        exhausted = {
            name for name, quota in (self.inventory.quotas or {}).items()
            if isinstance(quota, dict) and quota.get("total", 0) > 0
            and quota.get("total", 0) - quota.get("upload", 0) - quota.get("download", 0) <= 0
        }
        wall = self.wall()
        found: list[tuple[NodeInfo, float | None]] = []
        for info in view:
            node = self._node(info)
            key = self._speed_key(info)
            if info.fingerprint == current.fingerprint or node is None:
                continue
            if (
                prices.get(info.fingerprint, 1.0) >= speed.SKIP_PRICE
                or node.source in exhausted or self._is_unstable(info.fingerprint)
                or info.fingerprint in self.home_exits
                or self._klass(info.fingerprint, prices) != tier
                or self.main_cooldown.get(key, 0.0) > wall
                or key in self.guard.throttled
            ):
                continue
            if info.role == "proxy":
                if role == "member" or not (observatory.get(info.tag) or {}).get("alive"):
                    continue
            elif (scans.get(info.probe_tag) or {}).get("verdict") != "OK":
                continue
            found.append((info, self._candidate(info, observatory).mbps))
        found.sort(key=lambda item: (item[1] is None, -(item[1] or 0.0), item[0].role != "proxy"))
        return [info for info, _mbps in found[: self.cfg.speed.candidates]]

    def _guard_episode(self, view: list[NodeInfo], applied: dict | None, observatory: dict) -> None:
        """Шаг поиска: один кандидат за шаг (параллельные замеры положили бы домашний канал).
        Первый не медленнее speed.switch_mbps — переход сразу; кандидаты кончились — лучший,
        если он стоит перехода, иначе «глобальная просадка»."""
        episode = self.guard.episode
        assert episode is not None
        current = next(
            (info for info in view if info.role == "proxy" and info.tag == episode["tag"]), None,
        )
        if current is None:
            self.guard.episode = None  # придушенный ушёл из работы сам (замена, отказ)
            return
        if self.stopping:
            return
        # И в шаге со сканом: кандидат — один за шаг, а сервер придушен сейчас (сканы бывают на
        # каждом шаге, SPEED_SCAN_WAIT).
        by_probe = {info.probe_tag: info for info in view}
        size = int(self.cfg.speed.spare_mb * speedguard.MB)
        password, _ports = builder.probe_state(applied or {})
        while episode["queue"]:
            if (
                episode["spent"] + size > self.cfg.speed.episode_mb * speedguard.MB
                or not self.guard.can_spend(size)
            ):
                episode["queue"].clear()  # бюджет поиска исчерпан — решаем по тому, что есть
                break
            info = by_probe.get(episode["queue"].pop(0))
            if info is None or not password:
                continue
            if info.role == "spare" and not self._guard_fresh(info, password):
                continue
            result = self._speed(info, password, small=True)
            episode["spent"] += result.bytes_read
            episode["tried"] += 1
            self.guard.spend(result.bytes_read)
            self._own_traffic += result.bytes_read
            self._own_by_tag[info.tag] = self._own_by_tag.get(info.tag, 0) + result.bytes_read
            records = self._speeds()
            records[self._speed_key(info)] = {
                "mbps": result.mbps, "bytes": result.bytes_read, "seconds": result.seconds,
                "error": result.error, "ts": self.wall(),
            }
            self._save_speeds(records)
            episode["results"][info.probe_tag] = result.mbps
            if self.guard.early(result.mbps, episode["mbps"]):
                self._guard_switch(view, observatory, current, info, result.mbps)
                return
            return  # следующий кандидат — на следующем шаге
        best = max(
            (
                (tag, mbps) for tag, mbps in episode["results"].items()
                if self.guard.better(mbps, episode["mbps"]) and tag in by_probe
            ),
            key=lambda item: item[1], default=None,
        )
        if best is not None:
            self._guard_switch(view, observatory, current, by_probe[best[0]], best[1])
            return
        self.guard.episode = None
        until = datetime.datetime.fromtimestamp(self.guard.cool_down()).strftime("%H:%M")
        self._guard_event(
            f"глобальная просадка канала: ни один из {episode['tried']} кандидатов не быстрее "
            f"«{episode['name']}» ({speed.mbps_text(episode['mbps'])}) на "
            f"{self.cfg.speed.gain_pct} % — остаюсь на нём; новых поисков до {until}"
        )

    def _guard_fresh(self, info: NodeInfo, password: str) -> bool:
        """Свежая быстрая GET-проба кандидата (57 КБ): старше одного периода сканов —
        проверить сейчас (ТЗ R6.2)."""
        scan_entry = self.store.scans().get(info.probe_tag) or {}
        if (
            scan_entry.get("verdict") == "OK"
            and self.wall() - float(scan_entry.get("ts") or 0)
            <= self.cfg.probe.scan_spares_minutes * 60.0
        ):
            return True
        self._scanned = True
        result = self._probe_scan(info, password)
        if result.kind == "cancelled":
            return False
        self.store.save_scan(
            info.probe_tag, result.verdict, result.bytes_read, result.seconds, result.error,
            ts=self.wall(),
        )
        return result.verdict == "OK"

    def _guard_switch(
        self, view: list[NodeInfo], observatory: dict, current: NodeInfo, chosen: NodeInfo,
        mbps: float | None,
    ) -> None:
        """Переход (ТЗ R8): основной — на кандидата (запасной сначала встаёт в работу);
        выбранный вручную — «лучший пин» с пометкой, что он автоматический; другой участник
        выводится из работы тихо, с подстановкой кандидата."""
        episode = self.guard.episode or {}
        self.guard.episode = None
        node = self._node(chosen)
        name = node.name if node is not None else chosen.tag
        was = f"«{episode.get('name')}» ({speed.mbps_text(float(episode.get('mbps') or 0))})"
        now_text = f"«{name}» ({speed.mbps_text(mbps)})" if mbps is not None else f"«{name}»"
        role = episode.get("role")
        if role == "pin":
            pin = self._pin() or {}
            self._save_pin({
                **pin, "tag": chosen.tag, "name": name, "since": self.wall(), "down": None,
                "auto": True, "was": episode.get("name") or "",
            })
            self._hold_pin(chosen.tag)
            self.notifier.event(
                "pin", f"выбранный вручную {was} придушен — выбор перенесён на {now_text} "
                "автоматически («лучший пин»); вернуть прежний можно в панели", notify=True,
            )
            return
        if role == "main":
            rival = self._candidate(chosen, observatory)
            rival = dataclasses.replace(rival, mbps=mbps)
            if chosen.role == "spare":
                self._promote(view, observatory, rival, self._candidate(current, observatory))
                return
            self._set_main(rival)
            self.notifier.event(
                "main", f"основной сервер {was} придушен — основной теперь {now_text}",
            )
            return
        if chosen.role != "spare" or node is None or self.inventory is None:
            return
        members = [info for info in view if info.role == "proxy"]
        prefer = preferred_members(members, Rotation(replacements=[(current.tag, node)]))
        self.notifier.event("guard", f"участник {was} придушен — вместо него в работе {now_text}")
        self._rebuild(prefer, urgent=False, reason="замена придушенного участника")

    def _guard_event(self, text: str) -> None:
        """Событие контроля скорости — одно на текст: шаги поиска не плодят дублей."""
        if text != self._guard_note:
            self._guard_note = text
            self.notifier.event("guard", text)

    def speed_progress(self) -> dict:
        """Для статуса и панели: кто ждёт замера, сколько замерено из скольких и ждёт ли
        фоновый замер, пока освободится канал."""
        return {
            "queue": list(self.speed_queue), "total": self.speed_total,
            "done": self.speed_done, "deferred": self._speed_waiting,
        }

    def _speeds(self) -> dict[str, dict]:
        try:
            records = json.loads(self.store.get_meta("speed") or "{}")
        except json.JSONDecodeError:
            return {}
        return records if isinstance(records, dict) else {}

    def _save_speeds(self, records: dict[str, dict]) -> None:
        oldest = self.wall() - SPEED_KEEP
        kept = {
            key: value for key, value in records.items()
            if isinstance(value, dict) and float(value.get("ts") or 0) >= oldest
        }
        self.store.set_meta("speed", json.dumps(kept))

    def _load_main(self) -> dict | None:
        try:
            record = json.loads(self.store.get_meta("main") or "null")
        except json.JSONDecodeError:
            return None
        return record if isinstance(record, dict) and record.get("tag") else None

    def _set_main(
        self, pick: speed.Candidate | None, *, since: float | None = None, final: bool = True
    ) -> None:
        if pick is None:
            self.main = None
        else:
            self.main = {
                "tag": pick.tag, "key": pick.key, "name": pick.name,
                "since": self.wall() if since is None else since,
                "basis": "speed" if pick.mbps is not None and final else "delay",
                "country": pick.country, "source": pick.source,
            }
        self.store.set_meta("main", json.dumps(self.main) if self.main else "")

    def _pin_main(self, tag: str) -> None:
        """Закрепляет основной в ядре, если там закреплено не оно: перезапуск Xray и adrules
        закрепление сбрасывают."""
        try:
            if self.api.balancer_state(BALANCER_TAG).override != tag:
                self.api.pin(BALANCER_TAG, tag)
            self._main_pinned = True
        except ApiError as exc:
            self.log.error("основной сервер %s не закреплён: %s", tag, exc)

    def _release_main(self) -> None:
        """Снимает закрепление основного (не ручное) и забывает основной. Демон только
        запущен — сначала узнать у ядра, не осталось ли закрепления от прошлого запуска."""
        if self.main is not None:
            self._set_main(None)
        if self._main_pinned is False or self._manual_active():
            return
        try:
            if self._main_pinned or self.api.balancer_state(BALANCER_TAG).override:
                self.api.unpin(BALANCER_TAG)
            self._main_pinned = False
        except ApiError as exc:
            self.log.error("закрепление основного сервера не снято: %s", exc)

    # --- статус ----------------------------------------------------------------

    def _xray_version(self) -> None:
        """Перечитывает версию Xray, если файл бинарника сменился (inode, mtime, размер).

        `xray version` запускается только после смены файла, а не на каждом шаге. Версию
        узнать не удалось — отпечаток не запоминается, и на следующем шаге спросим снова."""
        try:
            info = os.stat(self.xray_bin)
        except OSError as exc:
            if self._xray_stamp is not None or self.xray_version:
                self.log.info("бинарник Xray недоступен: %s", exc)
            self.xray_version, self._xray_stamp = "", None
            return
        stamp = (info.st_ino, info.st_mtime_ns, info.st_size)
        if stamp == self._xray_stamp:
            return
        version = binary.installed_version(self.xray_bin)
        self.xray_version = ".".join(map(str, version or ()))
        self._xray_stamp = stamp if version else None

    def _lifecycle(
        self, view: list[NodeInfo], observatory: dict | None, xray_ok: bool
    ) -> tuple[Lifecycle, str] | None:
        """Жизненный цикл перехвата по итогам шага и почему он такой (пусто — причина не
        нужна). None — перехвата нет (не root, не настроен) либо правила ещё не сверялись."""
        info = self.capture_info
        if self.capture is None or info is None:
            return None
        mode = info.get("mode")
        if mode in ("none", "off"):
            return Lifecycle.OFF, ""
        if mode == "open":
            return Lifecycle.OPEN, "Xray недоступен дольше минуты (capture.fail_mode = open)"
        missing = str(info.get("inbound_missing") or "")
        if missing:
            return (Lifecycle.BLOCKED if info.get("blocked") else Lifecycle.OPEN), missing
        if info.get("loaded") is False:
            return Lifecycle.OPEN, "правила сети не загружены — трафик может идти мимо VPN"
        if not xray_ok:
            return Lifecycle.BLOCKED, "Xray не отвечает"
        if info.get("lan_problem"):
            # Пакеты устройств сети гибнут до Xray: мимо VPN они не уходят, но и не идут.
            return Lifecycle.BLOCKED, str(info["lan_problem"])
        tags = [info.tag for info in view if info.role == "proxy"]
        _alive, _dead, unknown = metrics.count_members(observatory or {}, tags)
        if tags and unknown >= len(tags):
            return Lifecycle.CONNECTING, "Xray ещё не проверил ни одного сервера"
        return Lifecycle.CONNECTED, ""

    def _lifecycle_changed(self, life: Lifecycle, why: str) -> None:
        """Переход — в журнал демона, а в журнал событий — когда трафик перестаёт идти
        через VPN или снова идёт (LIFECYCLE_EVENTS). Уведомлений здесь нет: о причине
        (Xray не отвечает, перехват снят, нет inbound'а) уведомляет её собственное событие."""
        previous, self.lifecycle = self.lifecycle, life
        if previous is None or previous is life:
            return
        text = f"перехват: {LIFECYCLE_TEXT[previous]} → {LIFECYCLE_TEXT[life]}"
        if why:
            text += f" ({why})"
        if previous in LIFECYCLE_EVENTS or life in LIFECYCLE_EVENTS:
            self.notifier.event("lifecycle", text)
        else:
            self.log.info("%s", text)

    def _write_status(
        self, view: list[NodeInfo], observatory: dict | None, xray_ok: bool
    ) -> None:
        self._last_status = (view, observatory, xray_ok)
        state = self.machine.state
        stranded = self._stranded_step(view, state)
        self._xray_version()
        capture = self.capture_info
        current = self._lifecycle(view, observatory, xray_ok)
        if current is not None and capture is not None:
            life, why = current
            self._lifecycle_changed(life, why)
            capture = {**capture, "lifecycle": str(life), "lifecycle_reason": why}
        snapshot = status.collect_status(
            self.cfg, self.paths, view,
            observatory=observatory, xray_ok=xray_ok, state=str(state),
            action=self.action, since=self.state_since,
            dead_since=self.dead_since, xray_version=self.xray_version, daemon=True,
            capture=capture, probe_target=self.probe_target,
            singbox=self._singbox_status(view),
            speeding=self.speed_progress(),
            stranded=stranded,
            probe_hosts=self.hosts.snapshot(),
            guard=self.guard.snapshot(),
            tailscale_via_vpn=bool(
                self.capture is not None
                and getattr(self.capture, "tailscale_via_vpn", lambda: False)()
            ),
        )
        spent = json.dumps(self.guard.spent, sort_keys=True)
        if spent != self.store.get_meta(speedguard.META_SPENT):
            self.store.set_meta(speedguard.META_SPENT, spent)
        hosts_text = self.hosts.dumps()
        if hosts_text != self._hosts_saved:
            # Счётчики проверочных хостов — для diag и следующего запуска демона.
            self._hosts_saved = hosts_text
            self.store.set_meta(probehosts.META, hosts_text)
        warnings = tuple(snapshot["budget"]["warnings"])
        if warnings != self._budget_warnings:
            self._budget_warnings = warnings
            for warning in warnings:
                self.notifier.event("budget", warning, notify=True)
        # Без уведомления: интернет работает, а решать, нарочно ли так стоят приоритеты, —
        # человеку; предупреждение висит в панели, пока его причина не уйдёт.
        warning = snapshot.get("class_warning") or ""
        if warning and not self._class_warning:
            self.notifier.event("priority", warning)
        self._class_warning = warning
        try:
            status.write_status(self.paths, snapshot)
        except OSError as exc:
            self.log.error("status.json не записан: %s", exc)
