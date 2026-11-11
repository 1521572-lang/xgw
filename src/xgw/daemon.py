"""Демон XGW (xgw.service): watchdog, подписки, сканы запасных, замена участников.

Переключением серверов управляет только Xray. Демон раз в interval_s (±20 %)
собирает сигналы — метрики observatory, сквозную загрузку через http-in и
доступность провайдера, — ведёт машину состояний и делает то, что ядро само
не умеет: обновляет подписки, применяет изменения, сканирует запасные и
меняет «мёртвых» участников (раздел 6.8). С 0.2.0 серверы не делятся на классы: у каждого
рейтинг (rating.py — скорость, задержка, стабильность, стоимость и приоритет), участники —
лучшие по нему из всех подписок, а мёртвого меняет лучший годный запасной (issue #2).
Демон подбирает балансировщику резервный выход — лимитированный сервер, через который
трафик идёт, пока участники мертвы (_reserve_step), и держит «основной» сервер — лучший по
рейтингу — закреплённым в ядре, чтобы выход не скакал между серверами (_main_step,
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
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

from . import cores, cost, engine, fetch, log, managed, priority, rating, usage, zapret2
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
from .config import Config, parse_seconds, probe_bytes
from .freepool import stats as poolstats
from .freepool import traffic
from .freepool.pool import FreePool
from .generator import builder
from .generator import fragment as fragmenting
from .generator import profiles as profiling
from .generator import singbox as singboxing
from .generator.builder import BALANCER_TAG, POOL_BALANCER, NodeInfo
from .model import ServerNode
from .net import cmd, conncheck, tun
from .net.capture import capture_inbounds
from .paths import Paths, atomic_write_json
from .store import Store, SubscriptionCache
from .watch import checks, scan, shadow, speed, status, target, youtube
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
# Плановые сканы запасных при исправном рабочем пути (HEALTHY) — не серией подряд, а с паузой
# SCAN_GAP секунд перед каждой следующей пробой шага (PR-4 ТЗ TS-ANTI-TSPU-HARDENING, п. 330).
# Пауза входит в SCAN_BUDGET: не помещается — проба ждёт следующего шага. Участники, аварийные
# состояния (DEGRADED, ALL_DEAD, RESERVE), срочные и ручные проверки паузы не ждут.
SCAN_GAP = (0.2, 1.5)
SCAN_PACE_KEEP = 40  # сколько последних проб скана помнить для status.json (scan_pacing)
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
# Пробы этой перепроверки (_diagnose_target): не больше DIAG_WORKERS одновременно (было 8 сразу —
# восемь одинаковых TLS-сессий, PR-4) и все вместе не дольше DIAG_BUDGET за шаг. DIAG_BUDGET не
# короче самой долгой пробы (scan_node: 15 с), иначе таймауты не доходили бы до итога. Не успели
# все — итоги держатся DIAG_KEEP и доделываются на следующих шагах; до итога выводов нет: ни «адрес
# отвечает», ни «серверы мертвы» (сканы и замены ждут). п. 332.
DIAG_WORKERS = 2
DIAG_BUDGET = 16.0
DIAG_KEEP = 180.0
# Перестановка по рейтингу (_rebalance): лучший годный запасной встаёт на место слабейшего
# живого участника, если его рейтинг выше хотя бы на MEMBER_GAIN, — не чаще REBALANCE_EVERY:
# не каждые полминуты, но и не мёртвой хваткой (решение заказчика 20.10.2026).
REBALANCE_EVERY = 900.0
MEMBER_GAIN = 0.25
# Доля сбоев за сутки для рейтинга (rating.Facts.fail_rate): итоги проверок по часам,
# HEALTH_HOURS часов; меньше HEALTH_MIN проверок — судить рано, доля 0. Участника ядро
# пробует постоянно — его итог берётся не чаще раза в HEALTH_SAMPLE.
HEALTH_HOURS = 24
HEALTH_MIN = 3
HEALTH_SAMPLE = 60.0
HEALTH_META = "health"
# Трафик несёт резервный (RESERVE) — участников меняют не раньше, чем через столько секунд:
# после короткого сбоя (провайдер моргнул) ядро само вернёт трафик участникам за цикл проб, а
# замена поставила бы в работу лимитированные серверы и тратила бы квоту. Трафик не идёт
# вовсе (ALL_DEAD) — без ожидания.
RESERVE_GRACE = 120.0
# Выбранный вручную запасной перестал отвечать — собственная проба не чаще этого: трафик
# тем временем ведёт автовыбор (_manual_step). Участника пробует само ядро.
PIN_RECHECK = 120.0
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
# Опрос подписок идёт в фоновом потоке (_refresh): отчёты audit6b и audit6c — шаг с
# обновлением подписки длился 90–135 с, из них опрос 37–68 с, и всё это время watchdog не
# замечал упавших серверов. Шаг, начавший опрос, ждёт его не дольше REFRESH_WAIT: быстрый
# опрос (файл, кэш) применяется в том же шаге, долгий — первым шагом после его конца.
REFRESH_WAIT = 2.0
BUILD_WAIT = 0.1  # быстрый конфиг применится сразу; долгий не задерживает watchdog
# Основной сервер (_main_step). С сервера, ушедшего в отказ, основной уходит сразу, и
# снова основным он не берётся MAIN_COOLDOWN, пока есть другие живые участники.
MAIN_COOLDOWN = 1800.0
# Загрузка не прошла через основной, и через новый — тоже, не позже MAIN_CAROUSEL после
# смены: дело, видимо, не в серверах (не отвечает адрес проверки, сбой у провайдера).
# Перебирать участников по кругу незачем — закрепление снимается, сервер выбирает ядро,
# как до 0.1.9, пока загрузка снова не пройдёт.
MAIN_CAROUSEL = 120.0
SPEED_FRESH = 2  # замер годен 2 срока замера своего класса (speed.every_hours)
LIMITED_BRIDGE_LAST = 1.0  # лимитный сервер проверяет поколение sing-box после безлимитных
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
# Фаза отказа (анти-ТСПУ 2.0). Через Xray проба не отличает «адрес сервера закрыт» (SYN без
# ответа, отказ) от «рукопожатие режет DPI»: CONNECT открывается локально сразу, а дальше —
# сброс или тишина на TLS (стенд phase_lab, Xray 26.10.21). Прямое TCP-соединение с адресом
# сервера, мимо VPN, их различает: не открылось — у всех профилей тот же адрес и порт, ни
# дробление, ни другое ядро не помогут; лестница не запускается, а сервер в работе меняется
# сразу. Отметка «адрес закрыт» держится CLOSED_RECHECK или до первого ответа сервера.
CLOSED_RECHECK = PROFILE_RETRY
# Бесплатный пул: шаг наблюдения не чаще (опрос источников — по своим интервалам внутри).
FREEPOOL_EVERY = 60.0
# Белые списки (анти-ТСПУ 2.0): провайдер пускает только на российские адреса. Признак: VPN не
# работает (ALL_DEAD, RESERVE), российские адреса напрямую открываются (watchdog.wan_check и
# wan_checks — provider_ok), а из зарубежных проверочных хостов (probe.url, probe.urls) напрямую
# не открывается ни один — WHITELIST_CONFIRM раз подряд, с паузой WHITELIST_EVERY. Сам шлюз
# ничего не меняет (решение заказчика 28.10.2026): событие и предупреждение в панели, где можно
# включить сервер для белых списков (x100 — «для LTE»). Пока режим держится — проверка раз в
# WHITELIST_EVERY; открылся зарубежный хост — событие «сняты».
WHITELIST_EVERY = 120.0
WHITELIST_CONFIRM = 2
WHITELIST_MULTIPLIER = 100.0  # серверы x100 и дороже — для LTE и белых списков (rating.py)
REACH_TIMEOUT = 4.0
# Протоколы и транспорты поверх TCP: у UDP (hysteria2, TUIC, WireGuard, mKCP, QUIC, XHTTP по
# HTTP/3) прямое TCP-соединение ничего не говорит.
TCP_PROTOCOLS = frozenset(("vless", "vmess", "trojan", "shadowsocks", "anytls"))
TCP_NETWORKS = frozenset(("tcp", "raw", "ws", "grpc", "httpupgrade", "xhttp", "splithttp", "h2",
                          "http"))
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
# Свой сервер устройства (Ф4, 0.2.0): запасной проверяется дешёвым запросом (scan.cheap_url)
# не чаще раза в DEVICE_CHECK, участника — по пробам ядра. DEVICE_STREAK проверок подряд
# без ответа — устройство идёт через основной; столько же с ответом — снова через свой.
# Расход: ~8 КБ × 2 в минуту ≈ 23 МБ в сутки на сервер (status.probe_budget, devices).
DEVICE_CHECK = scan.DEVICE_CHECK
DEVICE_STREAK = 2
# Устройства через бесплатный пул (М2б.1, _pool_step): допущенные серверы пула проверяются раз
# в POOL_CHECK; пересборка ради них — не чаще POOL_OPEN, если у устройств закрыто, а допущенные
# есть (сборка могла их не принять — без паузы она шла бы каждую минуту), иначе не чаще
# POOL_REBUILD. Умерший закреплённый сменяется сразу — закреплением другого живого, без сборки.
POOL_CHECK = 60.0
POOL_OPEN = 180.0
POOL_REBUILD = 600.0
# Пересборка для пула впереди или ядро ещё не пробовало его серверы — «подключаются», а не
# «закрыто», но не дольше POOL_WAIT (первые пробы ядра — за интервал probe.interval).
POOL_WAIT = 120.0
# Восстановление пула (М3, _pool_silence): сервер «pool» молчит у проб ядра дольше POOL_SILENT —
# пулу на перепроверку вне очереди (истёкший ключ, ушедший сервер выбывает с первой неудачей, а
# не через часы); пул закрыт — списки серверов обновляются вне расписания, не чаще POOL_REFRESH.
POOL_SILENT = 300.0
POOL_REFRESH = 1800.0
# Шаг watchdog дольше TICK_SLOW — строка в журнале: что в нём шло и на что ушло время — части шага
# не короче TICK_PART (Daemon.run, _tick_work, _spent).
TICK_SLOW = 60.0
TICK_PART = 5.0
# Скорость серверов «pool» (_pool_speed_step) — обычным замером (speed.measure, speed.max_mb):
# экономия их трафика не нужна (решение заказчика 5). Живой сервер без замера — сразу, по одному
# за шаг; повторный замер — раз в speed.unlimited_hours, при занятом канале пула (больше
# SPEED_BUSY_BPS) ждёт, но не дольше SPEED_FORCE_AFTER. Замеры — в meta POOL_SPEED_META: id
# варианта → {"mbps", "bytes", "seconds", "error", "ts"}, хранятся SPEED_KEEP.
POOL_SPEED_META = "pool_speed"
# Сервер «pool», закреплённый последним (полный id варианта; пусто — пул закрыт или выключен):
# после перезапуска демона тот же сервер не объявляется заново (отчёт freepool-recovery2,
# дефект 1: «весь дом идёт через» дважды без смены и без причины).
POOL_PINNED_META = "pool_pinned"
# YouTube через сервер (М3, watch/youtube.py, _youtube_step): итоги — в meta YOUTUBE_META, ключ —
# отпечаток сервера подписки или полный id варианта пула → {"state", "fails", "mbps", "client",
# "error", "ts"}. Сервер, который несёт трафик, проверяется раз в speed.youtube_minutes, после
# неудачи — снова через YOUTUBE_RETRY; остальные живые (безлимитные) — раз в YOUTUBE_OTHERS, после
# неудачи — через YOUTUBE_SUSPECT, и не чаще одного раза в YOUTUBE_GAP. Плох — YOUTUBE_CONFIRM
# неудач подряд, и итог не старше YOUTUBE_STALE. Смен из-за YouTube YOUTUBE_CAROUSEL_COUNT за
# YOUTUBE_CAROUSEL — дело, похоже, не в серверах: смены приостанавливаются на YOUTUBE_PAUSE.
YOUTUBE_META = "youtube"
YOUTUBE_RETRY = 60.0
YOUTUBE_OTHERS = 6 * 3600.0
YOUTUBE_SUSPECT = 600.0
YOUTUBE_GAP = 120.0
YOUTUBE_CONFIRM = 2
YOUTUBE_STALE = 24 * 3600.0
YOUTUBE_KEEP = 7 * 86400.0
YOUTUBE_CAROUSEL = 3600.0
YOUTUBE_CAROUSEL_COUNT = 3
YOUTUBE_PAUSE = 2 * 3600.0
# Выход для видео (п. 348): повтор сборки, если план не применился, и чтения его балансировщика.
MEDIA_RETRY = 300.0
MEDIA_VERIFY = 60.0
# Дополнительные проверки кандидатов в выход видео (п. 353): разброс сроков, предел паузы после
# неудач (от YOUTUBE_GAP, удваивается) и запись суточного расхода трафика.
MEDIA_SPREAD = 0.2
MEDIA_BACKOFF_MAX = 1800.0
MEDIA_BUDGET_META = "youtube_media_budget"
# Рабочий конфиг Xray расходится с режимом «весь дом» (_house_sync) — срочная сборка не чаще
# HOUSE_SYNC: отклонённый или откаченный конфиг не пересобирается на каждом шаге.
HOUSE_SYNC = 300.0
# Сетевая задержка (RTT, п. 2.3): у запасных — по их сканам, у участников — дешёвым запросом
# через probe-inbound раз в RTT_EVERY (по одному за шаг; ~8 КБ на проверку). Замер старше
# RTT_KEEP в рейтинге не учитывается (meta «rtt»: отпечаток → {"ms", "ts"}).
RTT_EVERY = scan.RTT_EVERY
RTT_KEEP = 24 * 3600.0
RTT_META = "rtt"

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
    """tcp или udp: физический путь до сервера. UDP — протоколы на QUIC и WireGuard, а у Xray
    ещё транспорт mKCP, QUIC и XHTTP по HTTP/3 (fragment.over_udp, правило самого Xray). Одно
    правило для выбора запасного «по другому пути» (_alternatives) и прямой TCP-проверки
    (_over_tcp): раньше первое смотрело только на протокол, и VLESS по mKCP или XHTTP-h3
    считался TCP, а второе — нет (C07 кросс-аудита 4cc96b9)."""
    if node.protocol in UDP_PROTOCOLS:
        return "udp"
    stream = node.outbound.get("streamSettings") if node.outbound else None
    return "udp" if isinstance(stream, dict) and fragmenting.over_udp(stream) else "tcp"


def _ipv4(text: str) -> bool:
    try:
        return ipaddress.ip_address(text).version == 4
    except ValueError:
        return False


def _over_tcp(node: ServerNode) -> bool:
    """Сервер работает поверх TCP и напрямую (не цепочкой через другой сервер): путь по
    _transport — TCP, а протокол и транспорт из известных TCP-шных."""
    if node.protocol not in TCP_PROTOCOLS or node.keep_tag or _transport(node) != "tcp":
        return False
    stream = node.outbound.get("streamSettings") if node.outbound else None
    if not isinstance(stream, dict):
        return True  # только sing-box (AnyTLS) или без streamSettings — обычный TCP
    if str(stream.get("network") or "tcp").lower() not in TCP_NETWORKS:
        return False
    sockopt = stream.get("sockopt") if isinstance(stream.get("sockopt"), dict) else {}
    return not sockopt.get("dialerProxy")


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


def stranded_action() -> str:
    """Текст DEGRADED, когда мёртвого участника заменить некем (Daemon._stranded): «замена на
    запасные» была бы неправдой (разбор 24.10.2026, ASSUMPTIONS п. 235)."""
    return (
        "часть серверов недоступна, а заменить их некем: ни один запасной не прошёл "
        "последнюю проверку; шлюз проверяет их снова"
    )


def stranded_note(dead: list[str]) -> str:
    """Событие и пояснение в панели: кто не отвечает и почему его не меняют."""
    who = ", ".join(f"«{name}»" for name in dead)
    head = f"не отвечает сервер в работе {who}" if len(dead) == 1 else (
        f"не отвечают серверы в работе {who}"
    )
    return (
        f"{head}, а заменить некем: ни один запасной (кроме x100 и подписок с исчерпанной "
        "квотой) не прошёл последнюю проверку. Шлюз проверяет запасные снова; если так долго, "
        "включите отключённые серверы или добавьте подписку."
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


class _PoolCancel:
    """Отмена проверок бесплатного пула (FreePool.check_some): демон останавливается или
    наблюдение выключили — начатый шаг пула не проверяет следующие серверы (отчёт m2b2fix2:
    проверки шли и после «Выключить»). Настройки пул получает при каждом перечитывании."""

    def __init__(self, stop: threading.Event, pool: FreePool) -> None:
        self.stop, self.pool = stop, pool

    def is_set(self) -> bool:
        return self.stop.is_set() or self.pool.cfg.free_pool.mode == "off"


class _FetchCancel:
    """Отмена фонового опроса подписок (_Fetch): демон останавливается либо источники
    серверов в настройках сменились (adopt) — опрос прежних больше не нужен."""

    def __init__(self, stop: threading.Event) -> None:
        self.stop, self.dropped = stop, threading.Event()

    def is_set(self) -> bool:
        return self.stop.is_set() or self.dropped.is_set()

    def wait(self, seconds: float) -> bool:
        """Как threading.Event.wait — пауза перед повтором запроса (fetch._pause)."""
        deadline = time.monotonic() + seconds
        while not self.is_set():
            left = deadline - time.monotonic()
            if left <= 0:
                return False
            self.stop.wait(min(left, fetch.CANCEL_SLICE))
        return True


@dataclasses.dataclass
class _Fetch:
    """Опрос подписок в фоновом потоке (Daemon._refresh) и его итог."""

    via_xray: bool
    urgent: bool
    cancel: _FetchCancel
    done: threading.Event = dataclasses.field(default_factory=threading.Event)
    waiting: bool = False  # шаг ждёт конца опроса сам — будить демон незачем
    lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)  # done и waiting
    inventory: engine.Inventory | None = None
    error: Exception | None = None
    spent: float = 0.0  # секунд на опрос
    asked: bool = False  # подписку обновили кнопкой: новые серверы — сразу (_hold_new)


@dataclasses.dataclass
class _BuildRequest:
    prefer: list[str] | None
    urgent: bool
    reason: str
    reserve: str | None = None
    profiles: dict[str, str] = dataclasses.field(default_factory=dict)
    callbacks: dict = dataclasses.field(default_factory=dict)

    def key(self) -> tuple:
        return (tuple(self.prefer) if self.prefer is not None else None,
                self.urgent, self.reserve, tuple(sorted(self.profiles.items())))


@dataclasses.dataclass
class _Build:
    request: _BuildRequest
    cfg: Config
    inventory: engine.Inventory
    inputs: tuple
    stamp: tuple
    reload: bool | None
    wake: threading.Event
    dead: frozenset
    began: float = dataclasses.field(default_factory=time.monotonic)
    done: threading.Event = dataclasses.field(default_factory=threading.Event)
    assembly: engine.Assembly | None = None
    error: Exception | None = None
    spent: float = 0.0
    discard: bool = False
    preparation_started: bool = False
    generation: object = None
    generation_core: object = None


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
        # Бесплатный пул (веха М1, наблюдение): опрос источников через несущий канал и проверки —
        # в отдельном потоке, не дольше шага watchdog; сводка — из него же (кэш).
        self.freepool = FreePool(cfg, paths, logger=self.log)
        self._freepool_next = 0.0
        self._freepool_thread: threading.Thread | None = None
        self._freepool_summary: dict | None = None
        self._freepool_force = False
        # Учёт расхода трафика по устройствам и подпискам (usage.py): nftables — только у
        # настоящего шлюза (с перехватом), счётчики Xray — всегда.
        self.meter = usage.Meter(cfg, paths, runner=cmd.run if capture is not None else None,
                                 logger=self.log)
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
        self._selection: dict | None = None  # последняя замена участника: когда и почему эта
        self.scan_queue: deque[str] = deque()  # probe-теги узлов, ждущих скана
        # Теги очереди, поставленные срочно (_queue_first(urgent=True): аварийный круг резерва,
        # белые списки) — без паузы SCAN_GAP; отметка снимается вместе с тегом из очереди.
        self._scan_urgent: set[str] = set()
        # Последние пробы скана: [начало, конец, плановая ли, пауза перед ней или None — первая
        # в шаге] по часам демона — для status.json (scan_pacing).
        self._scan_pace: deque[list] = deque(maxlen=SCAN_PACE_KEEP)
        # С запуска демона, для ТЗ на машине: фактические паузы перед плановыми пробами (число,
        # наименьшая, наибольшая, вне SCAN_GAP), наибольший промежуток от конца прошлой пробы
        # шага (пауза плюс обработка её итога) и срочные пробы (число, сколько ждали паузы — 0).
        self._pace_stats: dict = {"planned": 0, "planned_min": None, "planned_max": None,
                                  "planned_outside": 0, "idle_max": None, "urgent": 0,
                                  "urgent_waited": 0}
        # Неполная проверка адреса проб (_diagnose_target): тег → (итог пробы, когда снят).
        self._diag_partial: dict[str, tuple[scan.ScanResult, float]] = {}
        self._diag_cut: object | None = None  # отмена проб этой проверки (target.Cutoff)
        self._diag_last: dict = {}  # итог последней проверки — для status.json (scan_pacing)
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
        # Адрес сервера закрыт целиком (TCP напрямую не открылся): отпечаток → когда проверено.
        self._closed: dict[str, float] = {}
        # Память профилей (п. 336, generator/profiles.remembered), в базе вместе с пробами:
        # на каком профиле сервер ответил после пробы (отпечаток → {"profile", "ts", "key"}) и
        # на каких проба не помогла (отпечаток → {"key", "verdict", "steps": {профиль: ts}}).
        self._worked: dict[str, dict] = {}
        self._failed_steps: dict[str, dict] = {}
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
        # Свой сервер устройства (_device_step): отпечаток → (последний итог, сколько подряд),
        # когда проверен, и отпечатки серверов, которые сейчас считаются мёртвыми.
        self._device_streak: dict[str, tuple[bool, int]] = {}
        self._device_checked: dict[str, float] = {}
        self._device_dead: set[str] = set()
        # Устройства через бесплатный пул (_pool_step): закреплённый тег «pool» и по какому
        # применённому конфигу он закреплён (время файла: перезапуск и смена routing снимают
        # закрепление), когда проверены допущенные и пересобран конфиг ради них, имена
        # серверов пула по тегу, сводка для состояния и с какого времени пул «подключается».
        self._pool_pinned = ""
        self._pool_pin_key = 0.0
        self._pool_checked_at = 0.0
        self._pool_rebuilt_at = 0.0
        self._pool_names: dict[str, tuple[str, str]] = {}
        self._pool_traffic: dict | None = None
        self._pool_wait_since = 0.0
        # Скорость серверов «pool» (_pool_speed_step): полный id варианта по тегу, замеры (meta
        # POOL_SPEED_META), когда и по чему выбран закреплённый ("speed" — по замеру, когда
        # замерены все живые; "delay" — предварительно), с какого шага повторный замер ждёт
        # свободного канала, прошлый отсчёт трафика серверов пула и байты своего замера.
        self._pool_ids: dict[str, str] = {}
        self._pool_speed: dict[str, dict] | None = None
        self._pool_since = 0.0
        self._pool_basis = ""
        self._pool_deferred_since: float | None = None
        self._pool_bytes: tuple[float, int] | None = None
        self._pool_own = 0
        self._speed_ran = False  # на этом шаге шёл замер серверов подписки
        # Закреплённый «мёртв» по пробам ядра, а трафик через него идёт (_pool_spared): прошлые
        # счётчики downlink серверов пула, последний свой замер (тег, байты) и кого уже щадили.
        self._pool_downlinks: dict[str, tuple[float, int]] = {}
        self._pool_measured: tuple[str, int] = ("", 0)
        self._pool_spared_tag = ""
        # Восстановление (_pool_silence): с какого времени молчит у проб ядра каждый сервер
        # «pool» и когда списки обновлялись вне расписания из-за закрытого пула.
        self._pool_silent: dict[str, float] = {}
        self._pool_refreshed_at = 0.0
        self._pool_tags: set[str] = set()  # состав «pool» прошлого шага — для «выбыло» дневника
        self.diary = poolstats.Diary(self.store, clock=self.wall)  # дневник пула (М3)
        # Сервер «pool», закреплённый до запуска демона (POOL_PINNED_META): с ним сверяется только
        # первое закрепление после запуска.
        self._pool_boot = self._pool_saved = self.store.get_meta(POOL_PINNED_META) or ""
        self._pool_speed_ran = False  # на этом шаге шёл замер сервера «pool»
        self._youtube_ran = False  # на этом шаге шла проверка YouTube
        self._tick_spent: dict[str, float] = {}  # части шага → секунды (_spent)
        self._rebuild_spent = (0.0, 0.0)  # последняя сборка: (сборка, применение), секунды
        # YouTube через сервер (_youtube_step): итоги (meta YOUTUBE_META), счётчики downlink по
        # тегам на прошлом шаге и трафик клиентов с тех пор (Мбит/с), своя проверка прошлого шага
        # (тег, байты), шёл ли замер скорости шагом раньше (тогда счётчики им испорчены), когда
        # была фоновая проверка, смены из-за YouTube за YOUTUBE_CAROUSEL, до каких пор смены
        # приостановлены и о каком выбранном вручную плохом сервере уже сообщено.
        self._youtube: dict[str, dict] | None = None
        self._youtube_down: tuple[float, dict[str, int]] | None = None
        self._youtube_rates: dict[str, float] = {}
        self._youtube_own: tuple[str, int] = ("", 0)
        self._youtube_tainted = False
        self._youtube_bg_at = 0.0
        self._youtube_switches: list[float] = []
        self._youtube_paused_until = 0.0
        self._youtube_noted: set[str] = set()
        # Выход для видео (_media_step): когда менялся план, когда повторять сборку и проверку
        # балансировщика, какой план подтверждён, что показывать в статусе.
        self._media_changed_at = 0.0
        self._media_retry_at = 0.0
        self._media_verify_at = 0.0
        self._media_verified: tuple[str, ...] = ()
        self._media_view: dict = {"state": "off"}
        self._zapret2 = zapret2.Controller(self.store)
        self._media_spent: dict[str, int] | None = None  # суточный расход (_media_budget)
        self._house_synced_at: float | None = None  # срочная сборка по расхождению (_house_sync)
        self._rtt: dict[str, dict] | None = None  # сетевая задержка серверов (_rtts)
        # Период скана запасных, мин (_scan_period): probe.scan_spares_minutes или больше,
        # чтобы все проверки уложились в probe.max_daily_probe_mb (ДОП-4).
        self._scan_minutes = max(1, cfg.probe.scan_spares_minutes)
        self.next_refresh = 0.0
        self.next_scan = 0.0
        self.next_leak = 0.0
        self.next_conncheck = 0.0  # адрес проверки связности NetworkManager (net/conncheck.py)
        # Итог фонового conncheck.lookup: (найдено,) — применить в основном потоке.
        self._conncheck_found: tuple | None = None
        # Один поток за раз; результат старого поколения не публикуется (п. 347, A-09).
        self._conncheck_lock = threading.Lock()
        self._conncheck_busy = False
        self._conncheck_generation = 0
        self.next_all_dead = 0.0
        self.next_rescan = 0.0
        # Рейтинг (rating.py): итоги проверок по часам (отпечаток → {час: [удачи, сбои]}),
        # когда участник учтён последний раз, последняя перестановка по рейтингу и что из
        # рейтинга записано в базу (engine.load_scores, status.py).
        self._health: dict[str, dict[str, list[int]]] | None = None
        self._health_saved = 0.0
        self._health_dirty = False
        self._observed: dict[str, float] = {}
        self._rebalance_at = self.wall()  # первая перестановка — когда накопятся замеры
        self._published: dict[str, float] = {}
        # Резервный выход: когда перепроверять (по self.clock), идущая перепроверка
        # (начало — time.time(), probe-теги кандидатов), о чём уже сообщили.
        self.next_reserve_check = 0.0
        self.reserve_round: tuple[float, list[str]] | None = None
        self.reserve_round_at = float("-inf")  # когда началась последняя (time.time())
        self._urgent_round_for: float | None = None  # для какого ALL_DEAD (state_since)
        self._reserve_note = ""
        # DEGRADED, а заменить мёртвого участника некем (_stranded): о каких участниках уже
        # записано событие. Предупреждение «лимитированные в работе из-за
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
        # Белые списки: с какого момента (time.time()); сколько проверок подряд их показали и
        # когда следующая (часы демона).
        self.whitelist_since: float | None = None
        self._whitelist_hits = 0
        self._whitelist_next = 0.0
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
        self._fetch: _Fetch | None = None  # опрос подписок в фоне: идёт или ждёт применения
        # Сколько шаг ждёт начатого им опроса подписок (REFRESH_WAIT); None — до конца
        # (`xgw run --once`: шаг один, применить итог позже некому).
        self.refresh_wait: float | None = REFRESH_WAIT
        self._rebuild_asked = False
        self._build: _Build | None = None
        self._build_next: _BuildRequest | None = None
        self._build_applied = False
        self._build_discarded = 0
        self._build_count = 0
        self._build_last = (0.0, 0.0)
        # Состав прошлой смены поколения sing-box: отпечатки списка подписок и пула — для
        # строки журнала о том, откуда смена состава (singbox_generation.composition).
        self._sb_seen: tuple[set[str], set[str]] | None = None
        # Новые серверы подписки, ждущие пачки (_hold_new), и когда пачка входила последней.
        self._new_waiting: set[str] = set()
        self._new_admitted_at: float | None = None
        self._inventory_full: engine.Inventory | None = None  # с ждущими — для панели
        # Отпечатки, которые sing-box вёл за последние сутки (wall): вернувшаяся запись
        # подписки отличается в строке состава от нового сервера.
        self._sb_history: dict[str, float] = {}
        self._build_outcome: str | None = None
        self._loop_step_s = 0.0
        self._health_observed: float | None = None

    # --- цикл ------------------------------------------------------------------

    def run(self, stop: threading.Event, changed=lambda: False) -> None:
        """Цикл watchdog до остановки либо до изменения config.toml (changed)."""
        self.log.info("демон XGW запущен, шаг watchdog %d с", self.cfg.watchdog.interval_s)
        self._stop = stop
        while not stop.is_set() and not changed():
            started = time.monotonic()
            self._loop_progress("tick", started=started)
            try:
                state = self.tick()
            except Exception:  # сбой одного шага не должен ронять демон
                self.log.exception("шаг watchdog завершился ошибкой")
                state = self.machine.state
            spent = time.monotonic() - started
            self._loop_step_s = spent
            if spent >= TICK_SLOW:
                # Состояние пишется в конце шага: долгий шаг — и сводка в панели отстаёт (отчёты
                # freepool-recovery, youtube: режим «весь дом» не появлялся в ней 3 минуты).
                self.log.warning("шаг watchdog занял %d с — состояние обновлено с опозданием (%s)",
                                 spent, self._tick_work())
            pause = WAN_DOWN_INTERVAL if state is State.WAN_DOWN else self.cfg.watchdog.interval_s
            if self._build is not None or self._build_next is not None:
                pause = min(pause, 5)  # сводка продолжает обновляться во время сборки
            if self._manual_scan and self.scan_queue:
                pause = MANUAL_SCAN_PAUSE
            period = jitter(pause)
            # Нормальный интервал — от начала шага. Иначе работа 8 с + ожидание
            # 20–24 с дают 28–32 с без нового статуса даже без долгой сборки.
            # WAN_DOWN и ручной скан сохраняют прежнюю паузу ПОСЛЕ работы.
            relative = state is not State.WAN_DOWN and not (self._manual_scan and self.scan_queue)
            deadline = (started if relative else time.monotonic()) + period
            self._loop_progress("sleep", started=started, deadline=deadline,
                                period=period, step_s=spent)
            self._sleep(stop, changed, max(0.0, deadline - time.monotonic()))
        with contextlib.suppress(OSError, cmd.CommandError):
            self._zapret2.close()
        self.diary.flush(force=True)
        self.store.close()
        self.log.info("демон XGW остановлен" if stop.is_set() else "настройки изменены")

    def _loop_progress(self, phase: str, **details) -> None:
        """Отдельная запись работы цикла для конечного помощника проверки.

        Не переписывает status.json и не выдаёт старое состояние за свежее.
        Ни имён серверов, ни адресов, ни настроек подключения здесь нет.
        """
        try:
            atomic_write_json(self.paths.run / "watchdog-step.json", {
                "phase": phase, "at": time.monotonic(), "interval_s": self.cfg.watchdog.interval_s,
                "previous_step_s": self._loop_step_s, **details,
            }, mode=0o600)
        except OSError as exc:
            self.log.debug("ход цикла не записан: %s", exc)

    def _tick_work(self) -> str:
        """Что из долгого шло в последнем шаге и на что ушло время — для строки о долгом шаге
        (run). Отчёт youtube2: шаги по 93–120 с после установки, запуска демона и обновления
        подписки шли «без проверок и замеров» — части шага скажут, где время."""
        parts = [name for name, done in (
            ("скан", self._scanned), ("замер скорости подписки", self._speed_ran),
            ("замер сервера пула", self._pool_speed_ran), ("проверка YouTube", self._youtube_ran),
        ) if done]
        longest = sorted(((spent, name) for name, spent in self._tick_spent.items()
                          if spent >= TICK_PART), reverse=True)
        text = ", ".join(parts) or "без проверок и замеров"
        if longest:
            text += "; дольше всего — " + ", ".join(
                f"{name} {spent:.0f} с" for spent, name in longest[:3])
        return text

    def _spent(self, name: str, since: float) -> float:
        """Часть шага name шла с since до сейчас (для _tick_work); сейчас — начало следующей."""
        moment = time.monotonic()
        self._tick_spent[name] = self._tick_spent.get(name, 0.0) + moment - since
        return moment

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

    def _usage_step(self, applied: dict | None) -> None:
        """Учёт расхода трафика (usage.py): раз в минуту — разницы счётчиков nftables и Xray в
        базу. Счётчики Xray — из ответа /debug/vars этого шага (_read_observatory)."""
        try:
            self.meter.step(self.store, self._metrics, applied,
                            self.inventory.nodes if self.inventory is not None else ())
        except Exception as exc:  # учёт не должен останавливать шлюз
            self.log.error("учёт трафика: шаг не выполнен: %s", exc)

    def request_freepool_refresh(self) -> None:
        """Панель: опросить источники бесплатного пула сейчас."""
        self._freepool_force = True
        self._freepool_next = 0.0
        self.poke.set()

    def _freepool_step(self, now: float, applied: dict) -> None:
        """Шаг бесплатного пула: раз в FREEPOOL_EVERY — фоновый поток с опросом источников,
        которым пора, и проверками нескольких кандидатов. Режим off — ничего. Состав «pool»
        рабочего конфига пул получает до запуска потока: его серверы проверяются раньше прочих
        (FreePool.next_checks) и после запуска демона — с первой же пачки (отчёт
        freepool-recovery: в первую пачку после запуска вклинился посторонний сервер)."""
        if self.cfg.free_pool.mode == "off":
            self._freepool_summary = None
            return
        self.freepool.members = frozenset(
            info.fingerprint for info in builder.applied_pool(applied)
        ) if traffic.pool_active(self.cfg) else frozenset()
        busy = self._freepool_thread is not None and self._freepool_thread.is_alive()
        if busy or now < self._freepool_next:
            return
        self._freepool_next = now + FREEPOOL_EVERY
        force, self._freepool_force = self._freepool_force, False
        via = engine.healthy_http_in(self.cfg)
        from .generator import validate

        xray_bin = validate.find_xray(None, self.paths)
        cancel = _PoolCancel(self._stop, self.freepool)

        def work() -> None:
            try:
                if self._freepool_summary is None:  # после запуска — сразу то, что сохранено
                    self._freepool_summary = self.freepool.summary()
                self.freepool.refresh_due(via=via, mark=self.mark, force=force)
                self.freepool.check_some(mark=self.mark, xray_bin=xray_bin, via=via,
                                         cancel=cancel)
                self._freepool_summary = self.freepool.summary()
            except Exception:  # опытный режим не должен останавливать шлюз — в журнал целиком
                self.log.exception("бесплатный пул: шаг не выполнен")

        self._freepool_thread = threading.Thread(target=work, name="xgw-freepool", daemon=True)
        self._freepool_thread.start()

    def request_refresh(self) -> None:
        """Панель: обновить подписки сейчас, не дожидаясь refresh_minutes. Заодно заново
        проверяются домены, отложенные как несуществующие."""
        engine.forget_quarantine()
        self._refresh_asked = True
        self.poke.set()

    def adopt(self, previous: Daemon) -> None:
        """Настройки перечитаны. Если источники серверов прежние, подписки заново
        не запрашиваются: конфиг пересобирается из уже полученного списка — так
        отключение сервера в панели не стоит запроса к каждой подписке. Опрос подписок, который
        прежний демон начал в фоне, доводит и применяет новый; источники сменились — опрос
        прежних отменяется."""
        self._resume(previous)
        if self.cfg.zapret2.mode == "compare" and self.cfg.zapret2 == previous.cfg.zapret2:
            self._zapret2.comparison = previous._zapret2.comparison
            self._zapret2.comparison_trace = previous._zapret2.comparison_trace
            self._zapret2.view = previous._zapret2.view
            self._zapret2.ready = previous._zapret2.ready
        if previous._build is not None:
            # Поток не трогаем и второй параллельно не запускаем. Старый результат
            # отбросим; настройкам нового экземпляра нужен собственный снимок.
            self._build = previous._build
            self._build.discard = True
            self._build.wake = self.poke
            previous._build = None
        same = engine.sources_key(previous.cfg) == engine.sources_key(self.cfg)
        if previous._fetch is not None and same:
            self._fetch = previous._fetch
            self.next_refresh = previous.next_refresh
        elif previous._fetch is not None:
            previous._fetch.cancel.dropped.set()
        if previous.inventory is None or not same:
            return
        self.inventory = previous.inventory
        self.next_refresh = previous.next_refresh
        self._new_waiting = set(previous._new_waiting)
        self._new_admitted_at = previous._new_admitted_at
        self._inventory_full = previous._inventory_full
        self._rebuild_asked = True
        if previous.cfg.managed.routes != self.cfg.managed.routes:
            # Свой сервер устройства (Ф4) выбран в панели — его ждут сразу. С 0.2.0 это только
            # правило маршрутизации: применяется через API ядра, без перезапуска Xray.
            self._urgent_rebuild = "свой сервер устройства"
        modes = (previous.cfg.free_pool.mode, self.cfg.free_pool.mode)
        if modes[0] != modes[1] and "on" in modes:
            # Весь дом через пул (М2б.2) включили или выключили в панели — ждут сразу. Пробы ядра
            # для пула (burstObservatory) могут потребовать перезапуска Xray.
            self._urgent_rebuild = ("бесплатный пул: весь дом" if modes[1] == "on"
                                    else "бесплатный пул: режим подписок")
        if (previous.cfg.managed.free_pool_pin != self.cfg.managed.free_pool_pin
                and traffic.pool_active(self.cfg)):
            # Сервер пула выбран вручную в панели — в состав «pool» он должен попасть сразу
            # (engine.assemble ставит его первым), а закрепит его _pool_step.
            self._urgent_rebuild = (self._urgent_rebuild
                                    or "бесплатный пул: выбранный вручную сервер")
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
        self._selection = previous._selection
        self.down_ticks = previous.down_ticks
        self.rolled_back = previous.rolled_back
        self.xray_down_since = previous.xray_down_since
        self.next_all_dead = previous.next_all_dead
        self._inbound_missing = previous._inbound_missing
        self.probe_target = previous.probe_target
        self.next_target_check = previous.next_target_check
        self._urgent_rebuild = previous._urgent_rebuild
        self._device_streak = dict(previous._device_streak)
        self._device_checked = dict(previous._device_checked)
        self._device_dead = set(previous._device_dead)
        self._pool_pinned = previous._pool_pinned
        self._pool_pin_key = previous._pool_pin_key
        self._pool_checked_at = previous._pool_checked_at
        self._pool_rebuilt_at = previous._pool_rebuilt_at
        self._pool_names = dict(previous._pool_names)
        self._pool_traffic = previous._pool_traffic
        self._pool_wait_since = previous._pool_wait_since
        self._pool_ids = dict(previous._pool_ids)
        self._pool_speed = previous._pool_speed
        self._pool_since, self._pool_basis = previous._pool_since, previous._pool_basis
        self._pool_deferred_since = previous._pool_deferred_since
        self._pool_bytes, self._pool_own = previous._pool_bytes, previous._pool_own
        self._pool_downlinks = dict(previous._pool_downlinks)
        self._pool_measured = previous._pool_measured
        self._pool_spared_tag = previous._pool_spared_tag
        self._pool_silent = dict(previous._pool_silent)
        self._pool_refreshed_at = previous._pool_refreshed_at
        self._pool_tags = set(previous._pool_tags)
        self._pool_boot, self._pool_saved = previous._pool_boot, previous._pool_saved
        self._youtube = previous._youtube
        self._youtube_down = previous._youtube_down
        self._youtube_rates = dict(previous._youtube_rates)
        self._youtube_own = previous._youtube_own
        self._youtube_tainted = previous._youtube_tainted
        self._youtube_bg_at = previous._youtube_bg_at
        self._youtube_switches = list(previous._youtube_switches)
        self._youtube_paused_until = previous._youtube_paused_until
        self._youtube_noted = set(previous._youtube_noted)
        self._media_changed_at = previous._media_changed_at
        self._media_retry_at = previous._media_retry_at
        self._media_verify_at = previous._media_verify_at
        self._media_verified = previous._media_verified
        self._media_view = previous._media_view
        self._media_spent = previous._media_spent
        self.diary = previous.diary
        self.diary.store = self.store
        self._house_synced_at = previous._house_synced_at
        self._health = previous._health
        self._observed = dict(previous._observed)
        self._rebalance_at = previous._rebalance_at
        self._published = dict(previous._published)
        self.next_reserve_check = previous.next_reserve_check
        self.reserve_round = previous.reserve_round
        self.reserve_round_at = previous.reserve_round_at
        self._urgent_round_for = previous._urgent_round_for
        self._reserve_used = previous._reserve_used
        self._reserve_noted = previous._reserve_noted
        self.whitelist_since = previous.whitelist_since
        self._whitelist_hits = previous._whitelist_hits
        self._whitelist_next = previous._whitelist_next
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
        self._closed = dict(previous._closed)
        self._worked = dict(previous._worked)
        self._failed_steps = dict(previous._failed_steps)
        self.freepool = previous.freepool
        self.freepool.cfg = self.cfg
        self._freepool_next = previous._freepool_next
        self._freepool_thread = previous._freepool_thread
        self._freepool_summary = previous._freepool_summary
        self._freepool_force = previous._freepool_force
        self.meter = previous.meter
        self.meter.cfg = self.cfg
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
        return self._refresh_asked or self._fetch is not None

    @property
    def scan_pending(self) -> bool:
        return self._scan_asked or (self._manual_scan and bool(self.scan_queue))

    def tick(self) -> State:
        """Один шаг watchdog. За шаг применяется не больше одного изменения конфига."""
        now = self.clock()
        self._scanned = self._speed_ran = self._pool_speed_ran = self._youtube_ran = False
        self._tick_spent = {}
        self._build_applied = False
        at = time.monotonic()
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
        if self.cfg.zapret2.mode == "standalone" or zapret2.standalone(applied):
            from .watch import standalone

            return standalone.tick(self, applied, now)
        if applied is None:
            # Блокировку ставим до ожидания сети даже на первом шаге и при повреждении
            # конфига. Состояние процесса Xray по одному файлу определить нельзя.
            if self.cfg.capture.hold_blocks:
                self._guard_capture(self.xray_down_since is None, now)
            # Первый запуск: рабочего конфига ещё нет — собрать и запустить Xray.
            if now >= self.next_refresh or refresh_asked or self._rebuild_asked:
                self._refresh(now, via_xray=False, urgent=True, background=False)
            at = self._spent("первая сборка конфига", at)
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
        self._health_observed = time.monotonic()
        at = self._spent("сигналы ядра", at)
        previous = self.machine.state
        decision = self.machine.update(signals)
        state = decision.state
        self.action = decision.action
        if state is State.DEGRADED:
            self.action = self._degraded_action(self._stranded(view))
        self._observe(view, observatory or {})
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
            # (решение пользователя после испытаний 0.1.9). Шлюз сам ставит в работу лучшие
            # живые запасные (_rotate) и вернёт лучших по рейтингу, когда они ответят.
            self._reserve_noted = True
            minutes = int((self.wall() - self.state_since) // 60)
            self.notifier.event(
                "reserve",
                f"уже {minutes} мин трафик идёт через резервный сервер{self._reserve_used}: "
                "серверы в работе не отвечают; шлюз ищет живые серверы среди запасных, "
                "в том числе лимитированных",
            )
        self._whitelist_step(view, signals, state, now)
        at = self._spent("белый список", at)
        self._freepool_step(now, applied)
        at = self._spent("списки бесплатного пула", at)
        self._usage_step(applied)

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

        # Новые сигналы и сверка перехвата уже получены. Не задерживаем их
        # публикацию до конца сканов, замеров и применения готовой сборки.
        self._write_status(view, observatory, signals.xray_ok, checkpoint=True)
        if not changed and state is not State.XRAY_DOWN and not self.core_job:
            changed = self._finish_build()
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
        at = self._spent("перехват и конфиг", at)
        if signals.xray_ok:
            self._device_step(view, applied, observatory)
            self._pool_step(applied, observatory or {})
            self._house_sync(applied, now)
            self._rtt_step(view, applied, observatory)
        at = self._spent("устройства и сервер пула", at)
        if not changed and self._urgent_rebuild and self.inventory is not None:
            # Срочно, без окна перезапуска: пока ядро пробует недоступный probe.url, оно
            # считает мёртвыми всех участников; без inbound TUN контейнеры без интернета.
            reason, self._urgent_rebuild = self._urgent_rebuild, ""
            if self._rebuild_asked:  # сборка ниже уже учитывает новые настройки
                self._rebuild_asked = False
                self._save_inventory(self.inventory)
            changed = self._rebuild(None, urgent=True, reason=reason)
        if not changed and self._fetch is not None and self._fetch.done.is_set():
            # Опрос подписок шёл в фоне (_refresh) и закончился — его итог в работу.
            changed = self._refresh_done(now, urgent)
        elif not changed and state is State.ALL_DEAD and now >= self.next_all_dead:
            # Внеочередное обновление подписки напрямую и скан всех запасных.
            self.next_all_dead = now + ALL_DEAD_RETRY
            changed = self._refresh(now, via_xray=False, urgent=True)
            self._queue_scan(view, now, everything=True)
        elif not changed and state is State.RESERVE and now >= self.next_all_dead:
            # Трафик несёт резервный выход и тратит квоту: подписка могла сменить серверы —
            # обновить её напрямую (через Xray запрос шёл бы через тот же резервный) и
            # проверить запасные, чтобы поскорее заменить мёртвых участников.
            self.next_all_dead = now + RESERVE_RETRY
            changed = self._refresh(now, via_xray=False, urgent=False)
            self._queue_scan(view, now)
        elif not changed and (
            refresh_asked or (state is not State.WAN_DOWN and now >= self.next_refresh)
        ):
            changed = self._refresh(now, via_xray=signals.xray_ok, urgent=urgent,
                                    asked=refresh_asked)
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
        at = self._spent("подписка и сборка конфига", at)

        # Пока не отвечает сам probe.url, сканы только испортили бы вердикты запасных
        # (все «недоступны»), а замена участников шла бы по кругу: и то, и другое ждёт.
        # Решает сам признак, а не имя состояния: утечка (LEAK) стоит в машине состояний
        # выше и его заслоняет, а сканам и замене от этого не легче.
        # Проверка адреса проб не закончена (_diagnose_target, неполный итог) — тоже ждут: до её
        # итога отказ серверов не доказан.
        probing = not self.probe_target and not self._diag_partial
        if scan_asked and probing:
            self._manual_scan = True
            self._queue_scan(view, now, everything=True)
        elif resumed and probing:
            # После сна вердикты запасных устарели: проверить их сейчас, не дожидаясь
            # scan_spares_minutes. Лимитированные класса хуже — как обычно, только когда
            # трафик не идёт (их проверка тратит квоту).
            self.next_scan = now + jitter(self._scan_period(view) * 60.0)
            self._queue_scan(view, now)
        elif scan_asked:
            self.notifier.event("probe", "проверка запасных отложена: " + (
                "не отвечает probe.url" if self.probe_target else
                "не закончена проверка адреса проб"))
        if not changed and probing and signals.xray_ok and signals.provider_ok:
            # Подписка после запуска демона ещё не получена (опрос в фоне): цены запасных
            # неизвестны, _queue_scan их пропустил бы — круг ждёт её, а не следующего срока.
            if now >= self.next_scan and self.inventory is not None:
                self.next_scan = now + jitter(self._scan_period(view) * 60.0)
                self._queue_scan(view, now)
            self._queue_members(view)
            self._scan_step(view, applied)
            if self.stopping:
                # Остановка пришла во время сканов: замены и смены класса не начинаем.
                self._write_status(view, observatory, signals.xray_ok)
                return state
            if state in (State.DEGRADED, State.ALL_DEAD, State.RESERVE) or (
                state is State.HEALTHY and self.bad_members
            ) or (state is State.LEAK and self._home_members(view)) or (
                # LEAK снялся, потому что трафик ушёл на другой сервер: выходящий в домашнюю
                # страну остаётся среди участников и меняется, как только появится замена.
                state is State.HEALTHY and self._home_members(view)
                and not self._manual_active()
            ):
                changed = self._rotate(view, observatory or {}, state, now)
            if not changed:
                changed = self._rebalance(view, observatory or {}, state)
            if not changed:
                changed = self._reserve_step(view, applied, state, now)
            if not changed:
                self._member_profiles(view, observatory or {})
                changed = self._profile_step(view)

        if not self.scan_queue or not probing:
            self._manual_scan = False
        at = self._spent("сканы и замены", at)
        if not changed and signals.xray_ok and not self.stopping and not self.core_job:
            allowed = (self.cfg.zapret2.probe_enabled and self.capture is not None
                       and self.capture.mode() == "on")
            vpn_probe_port = 0
            if self.cfg.zapret2.mode == "compare" and observatory:
                # Один живой участник для обеих проб, через его штатный служебный вход.
                vpn_probe_port = next((info.probe_port for info in view if info.role == "proxy"
                                       and info.probe_port
                                       and (observatory.get(info.tag) or {}).get("alive")), 0)
            previous = self._zapret2.view.get("state")
            changed = self._zapret2.step(
                self.cfg, applied, self.clock(), self._zapret2_apply,
                allowed=allowed, vpn_probe_port=vpn_probe_port, cancel=self._stop,
            )
            if previous != self._zapret2.view.get("state"):
                self.notifier.event("zapret2", "zapret2: " + self._zapret2.view["state"])
        if not changed and signals.xray_ok and not self.stopping and not self.core_job:
            changed = self._media_apply(now)
        if changed:
            applied = engine.read_json(self.paths.xray_config_file)
            view = builder.applied_nodes(applied, self.inventory.nodes if self.inventory else ())
        if self.stopping:
            self._write_status(view, observatory, signals.xray_ok)
            return state
        self._manual_step(view, applied, observatory or {}, signals)
        self._main_step(view, applied, observatory or {}, state, signals, now)
        at = self._spent("основной сервер и замеры подписки", at)
        if signals.xray_ok and not changed:  # после перезапуска Xray пробы ядра устарели
            self._pool_speed_step(applied, observatory or {}, now)
            self._youtube_step(view, applied, observatory or {}, now)
            self._media_step(view, applied, observatory or {}, now)
        at = self._spent("замер пула и YouTube", at)
        if state is not State.WAN_DOWN:
            self._cores_step()
            self._netmon_step(signals.xray_ok)
        at = self._spent("ядра и сеть", at)
        self._publish_scores(view, observatory or {})
        self._write_status(view, observatory, signals.xray_ok)
        self._spent("запись состояния", at)
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

        self._conncheck_step(now)

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

    def _conncheck_step(self, now: float) -> None:
        """Забрать готовый итог и, если пора и прежний поток закончил, запустить новый."""
        generation = None
        with self._conncheck_lock:
            found, self._conncheck_found = self._conncheck_found, None
            if (now >= self.next_conncheck and self.capture is not None
                    and not self._conncheck_busy):
                self.next_conncheck = now + conncheck.REFRESH
                self._conncheck_busy = True
                self._conncheck_generation += 1
                generation = self._conncheck_generation
        if found is not None:
            self._conncheck_apply(found[0])
        if generation is not None:
            try:
                threading.Thread(target=self._conncheck_lookup, args=(generation,),
                                 name="xgw-conncheck", daemon=True).start()
            except RuntimeError as exc:  # потоков нет — не повод застрять на «занято»
                self.log.error("проверка связности не запущена: %s", exc)
                with self._conncheck_lock:
                    self._conncheck_busy = False

    def _conncheck_lookup(self, generation: int) -> None:
        """Фоном: адрес проверки связности NetworkManager (busctl, свои резолверы мимо
        перехвата). Итог применяет основной поток (_conncheck_apply)."""
        def resolve(host: str) -> list[str]:
            return fetch.resolve_domain(host, list(self.cfg.dns.resolvers), mark=self.mark,
                                        cancel=self._stop, public_only=True)

        try:
            found = conncheck.lookup(resolve)  # DNS и busctl — вне блокировки
            with self._conncheck_lock:
                if (found is not False and generation == self._conncheck_generation
                        and not self._stop.is_set()):
                    self._conncheck_found = (found,)
        except Exception as exc:  # значок — не повод мешать шагу демона
            self.log.debug("адрес проверки связности не узнан: %s", exc)
        finally:
            with self._conncheck_lock:
                self._conncheck_busy = False

    def _conncheck_apply(self, found: dict | None) -> None:
        """/run/xgw/conncheck.json и сразу правила: барьер пропускает проверку связности, и
        значок шлюза не пишет «ограниченное подключение». Файл и загрузка — в одном шаге:
        иначе до следующего шага сверка видела бы барьер «не загруженным» (отчёт 7949034 —
        health сразу после установки попал в это окно, сработал откат)."""
        try:
            if not conncheck.store(self.paths, found):
                return
            self.log.info("адреса проверки связности NetworkManager обновлены")
            if self.capture is not None and not self._capture_waits():
                self.capture.up()
        except Exception as exc:  # значок — не повод мешать шагу демона
            self.log.error("исключение для проверки связности не применено: %s", exc)

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
        """Тело читается не дальше известного размера адреса или scan.SCAN_CAP_BYTES (C06);
        байты — в журнал проверок (назначение e2e, без подписки: идёт через основной)."""
        result = checks.http_get_via_proxy(
            "127.0.0.1", self.cfg.xray.http_port, url, silence=5.0,
            max_total=30.0, user_agent=self.cfg.probe.user_agent,
            max_bytes=scan.body_cap(url),
        )
        self.store.record_scan_body("", result.downloaded, "daemon", None, self.wall(),
                                    purpose="e2e")
        return result

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
            self._diag_partial = {}  # повода нет — неполная проверка больше не нужна
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
        if not suspect:
            self._diag_partial = {}
        if suspect and now >= self.next_target_check and not self.stopping:
            self.next_target_check = now + PROBE_TARGET_RECHECK
            diagnosis = self._diagnose_target(view, applied)
            if self.stopping:
                # Пробы прерваны остановкой: ошибка у всех одна, но о probe.url она ничего
                # не говорит.
                self.next_target_check = 0.0
                return signals
            if not diagnosis.complete:
                # Дедлайн шага вышел раньше, чем пробы дали итог: это не «адрес отвечает» и не
                # «серверы мертвы». Доделать на следующем шаге; сканы и замены ждут (_diag_partial).
                self.next_target_check = now
                if self.probe_target:
                    return dataclasses.replace(signals, probe_target_ok=False)
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
            if target.answers_via(self.cfg, members, password, url, user=builder.PROBE_USER,
                                  cancel=self._stop):
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
        """Пробы участников и выборки запасных (target.sample) — не больше DIAG_WORKERS
        одновременно и не дольше DIAG_BUDGET за шаг (PR-4). Не успели все — итог неполный
        (Diagnosis.complete = False), снятые пробы держатся DIAG_KEEP и не повторяются на
        следующем шаге; смена состава (тега нет в выборке) их снимает. Неполный итог годится,
        только если хоть одна проба получила probe.url: тогда адрес отвечает, что бы ни
        показали остальные."""
        password, _ports = builder.probe_state(applied)
        verdicts = {tag: entry["verdict"] for tag, entry in self.store.scans().items()}
        nodes = target.sample(view, verdicts, skip=self._costly_spares(view))
        if not password or not nodes:
            self._diag_partial = {}
            return target.Diagnosis(False)
        now = self.clock()
        tags = {info.tag for info in nodes}
        kept = {tag: item for tag, item in self._diag_partial.items()
                if tag in tags and 0.0 <= now - item[1] < DIAG_KEEP}
        todo = target.diagnosis_order(
            [info for info in nodes if info.tag not in kept], verdicts)
        self._diag_cut = target.Cutoff(self._stop, self.clock() + DIAG_BUDGET, self.clock)
        try:
            fresh, parallel = target.probe_sample(
                todo, lambda info: self._scan(info, password), workers=DIAG_WORKERS,
                cut=self._diag_cut,
            )
        finally:
            self._diag_cut = None
        done = self.clock()
        merged = {tag: result for tag, (result, _at) in kept.items()}
        merged.update((result.tag, result) for result in fresh)
        results = [merged[info.tag] for info in nodes if info.tag in merged]
        complete = len(results) == len(nodes)
        answered = any(not target.signature(result) for result in results)
        self._diag_last = {
            "complete": complete or answered, "probed": len(results), "of": len(nodes),
            "max_parallel": parallel, "seconds": round(done - now, 1), "ts": self.wall(),
        }
        if not complete and not answered:
            self._diag_partial = {
                **kept, **{result.tag: (result, done) for result in fresh},
            }
            self.log.info(
                "проверка адреса проб не закончена за %.0f с: итог у %d из %d серверов — "
                "продолжу на следующем шаге, выводов пока нет", done - now, len(results),
                len(nodes),
            )
            return target.Diagnosis(False, complete=False)
        self._diag_partial = {}
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
        others = [url for url in probehosts.all_urls(self.cfg) if url != self.cfg.probe.url]
        return target.base_ping(
            self.cfg, members, password, user=builder.PROBE_USER, extra_urls=others,
        )

    def _direct_probe(self) -> str:
        """probe.url напрямую, мимо VPN: пусто — отдаётся, иначе класс сбоя."""
        return target.direct_signature(self.cfg, self.mark)

    # --- действия --------------------------------------------------------------

    def _handle_xray_down(self) -> bool:
        """systemd перезапускает службу сам; после двух неудач — откат на last-good. Идут
        сутки наблюдения после обновления Xray, а он не отвечает и после отката — возврат
        прежней версии (cores.py)."""
        self.down_ticks += 1
        # Упавший Xray systemd поднимет сам через RestartSec — не мешать ему лишним start.
        if not self.service.is_active() and not self.service.restart_pending():
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
                if self.capture is not None and self.capture.loaded() is not True:
                    raise RuntimeError("загрузка правил не подтверждена")
            except Exception as exc:  # сбой сети не должен ронять шаг watchdog
                self.log.error("правила перехвата не переприменены: %s", exc)
                # Текст без причины: он сравнивается с прежним, а причина есть в журнале.
                text = (f"выход в {home} мимо Xray при включённом перехвате — устранение не "
                        "подтверждено: правила перехвата не загрузились")
            else:
                text = (f"выход в {home} мимо Xray при включённом перехвате — правила "
                        "загружены заново и проверены")
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
        mode = (self.capture_info or {}).get("mode")
        checking_rules = True
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
            reloaded = loaded is False or (
                loaded is None and bool((self.capture_info or {}).get("capture_failed"))
            )
            cause = ""
            if reloaded:
                # Правила пропали (чужой flush ruleset, перезапуск nftables), ещё не
                # загружались либо не соответствуют режиму: без них трафик пошёл бы
                # мимо VPN. Либо интерфейс TUN без адреса — его создал сам Xray.
                tun_problem = getattr(capture, "tun_problem", None)
                cause = tun_problem() if tun_problem is not None else ""
                capture.up()
                loaded = capture.loaded()
            checking_rules = False
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
            if checking_rules:
                guard = "unknown"
                restore = getattr(capture, "restore_guard", None)
                try:
                    if restore is not None:
                        guard = restore()
                except Exception as guard_exc:
                    guard = "failed"
                    text += f"; ошибка восстановления барьера: {guard_exc}"
                reason = {
                    "restored": "независимый барьер восстановлен отдельно",
                    "present": "независимый барьер соответствует политике",
                    "not_required": "выбранный режим не требует восстановления барьера",
                    "unknown": "состояние независимого барьера не подтверждено",
                    "failed": "защита независимым барьером не подтверждена",
                }[guard]
                text += f"; {reason}"
                self.capture_info = {
                    **(self.capture_info or {}), "mode": mode, "loaded": False,
                    "capture_failed": True, "guard_recovery": guard, "failure_reason": reason,
                }
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

    def _refresh(
        self, now: float, *, via_xray: bool, urgent: bool, background: bool = True,
        asked: bool = False,
    ) -> bool:
        """Опрос подписок и применение изменений. Опрос — в фоновом потоке (REFRESH_WAIT):
        шаг ждёт его не дольше refresh_wait (background=False — до конца: первый запуск,
        рабочего конфига ещё нет), не дождался — итог применит первый шаг после конца опроса
        (_refresh_done). Опрос уже идёт — второй не начинается, срочность переходит к нему."""
        if self.stopping:
            return False
        job = self._fetch if self._fetch is not None else self._start_fetch(now, via_xray)
        job.urgent = job.urgent or urgent
        job.asked = job.asked or asked
        with job.lock:
            job.waiting = True
        job.done.wait(self.refresh_wait if background else None)
        with job.lock:
            job.waiting = False
            finished = job.done.is_set()
        if not finished:
            return False
        return self._refresh_done(now, urgent)

    def _start_fetch(self, now: float, via_xray: bool) -> _Fetch:
        minutes = min((sub.refresh_minutes for sub in self.cfg.subscriptions), default=60)
        self.next_refresh = now + jitter(max(1, minutes) * 60.0)
        # Начавший опрос шаг его ждёт (_refresh) — и тогда, когда поток кончил раньше, чем шаг
        # начал ждать.
        job = self._fetch = _Fetch(via_xray, False, _FetchCancel(self._stop), waiting=True)
        self.log.info("опрос подписок начат — идёт в фоне, шаги демона не ждут")

        def work() -> None:
            began = time.monotonic()
            try:
                job.inventory = self._collect(via_xray)
            except Exception as exc:  # итог — шагу (_refresh_done), как при опросе в нём самом
                job.error = exc
            job.spent = time.monotonic() - began
            with job.lock:
                job.done.set()
                wake = not job.waiting
            if wake:
                self.poke.set()  # итог — в работу сразу, не дожидаясь очередного шага

        threading.Thread(target=work, name="xgw-subscriptions", daemon=True).start()
        return job

    def _refresh_done(self, now: float, urgent: bool) -> bool:
        """Итог опроса подписок (_refresh) — в работу: ошибки для панели, список серверов и
        сборка конфига (срочная, если срочным был опрос или шаг, который его применяет)."""
        job, self._fetch = self._fetch, None
        assert job is not None
        if isinstance(job.error, fetch.Cancelled):
            # Остановка прервала опрос: о подписках он ничего не говорит — ни сбоя, ни
            # ошибок для панели, ни неполного списка серверов.
            self.log.info("опрос подписок прерван: демон останавливается")
            return False
        if job.error is not None:
            raise job.error
        inventory = job.inventory
        assert inventory is not None
        self._rebuild_spent = (0.0, 0.0)
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
        self.inventory = self._hold_new(inventory, admit=job.urgent or urgent or job.asked)
        if inventory.complete:
            self._sub_failing_since, self._sub_alerted = None, False
        self._rebuild_asked = False  # сборка ниже уже учитывает новые настройки
        changed = self._rebuild(None, urgent=job.urgent or urgent, reason="обновление подписки")
        # Отчёты youtube3 и audit6: шаг с обновлением подписки длится 80–110 с — где именно время.
        # Опрос с 0.2.0 — в фоне, вне шага; сборка и применение — в шаге.
        self.log.info("обновление подписки: опрос %.0f с; сборка запрошена отдельно", job.spent)
        return changed

    def _hold_new(self, inventory: engine.Inventory, *, admit: bool) -> engine.Inventory:
        """Новые серверы подписки (отпечатков не было в прошлом списке) — в работу пачкой,
        не чаще раза в filters.new_hold_hours: каждый новый сервер — новое поколение sing-box
        (прежнее 5 минут доотдаёт соединения, долгие рвутся), а подписка добавляет по 1–2
        почти в каждом опросе (отчёт group-hold 07.11.2026). Пока сервер ждёт, его нет в
        списке, по которому собирается конфиг; в списке для панели он есть. Пачка входит
        сразу, когда состав меняется и так (подписка убрала серверы), шлюз не в порядке
        (новые серверы нужны), опрос срочный или подписку обновили кнопкой; без серверов в
        работе (первый опрос) ждать некому."""
        wall = self.wall()
        hours = self.cfg.filters.new_hold_hours
        self._inventory_full = None
        found = {node.fingerprint for node in inventory.nodes}
        if self.inventory is None or self._new_admitted_at is None or not hours:
            self._new_waiting, self._new_admitted_at = set(), wall
            return inventory
        before = {node.fingerprint for node in self.inventory.nodes}
        waiting = (self._new_waiting | (found - before)) & found
        if not waiting:
            self._new_waiting = set()
            return inventory
        if admit:
            reason = "срочный опрос или кнопка «Обновить»"
        elif self.machine.state is not State.HEALTHY:
            reason = f"шлюз в состоянии {self.machine.state}"
        elif before - found:
            reason = "подписка убрала серверы — состав меняется и так"
        elif wall - self._new_admitted_at >= hours * 3600.0:
            reason = f"прошло {hours} ч с прошлой пачки"
        else:
            self._new_waiting = waiting
            due = time.strftime("%H:%M", time.localtime(self._new_admitted_at + hours * 3600.0))
            self.log.info("новых серверов подписки ждут пачки: %d — в работу не позже %s "
                          "или раньше, со сменой состава", len(waiting), due)
            self._inventory_full = inventory
            return dataclasses.replace(inventory, nodes=[
                node for node in inventory.nodes if node.fingerprint not in waiting])
        self.log.info("новые серверы подписки в работу: %d (%s)", len(waiting), reason)
        self._new_waiting, self._new_admitted_at = set(), wall
        return inventory

    def _log_composition(self, generation, assembly) -> None:
        """Строка журнала: сколько серверов sing-box добавилось и убыло и откуда."""
        from .apply import singbox_generation as generations

        inventory = {node.fingerprint for node in (self.inventory.nodes if self.inventory
                                                   else [])}
        pool = {item.node.fingerprint for item in assembly.pool or []}
        before, old_pool = self._sb_seen if self._sb_seen is not None else (None, set())
        wall = self.wall()
        for fp in generations.served(generation.old):
            self._sb_history[fp] = wall
        self._sb_history = {fp: ts for fp, ts in self._sb_history.items() if wall - ts < 86400}
        counts = generations.composition(generation.old, generation.config, inventory=inventory,
                                         before=before, pool=pool | old_pool,
                                         history=set(self._sb_history))
        for fp in generations.served(generation.config):
            self._sb_history[fp] = wall
        self._sb_seen = (inventory, pool)
        if any(counts.values()):
            self.log.info("%s", generations.describe_composition(counts))

    def _assembly_stamp(self) -> tuple:
        """Версии входных файлов и допуска к трафику, не счётчиков и рейтинга."""
        files = (self.paths.config_file, managed.path_for(self.paths.config_file),
                 self.paths.xray_config_file, self.paths.singbox_config_file,
                 self.paths.devices_down_file, self.paths.var / "probe-fallback.json",
                 engine.media_file(self.paths),
                 self.xray_bin, singboxing.find_binary(None, self.paths))
        def version(path):
            if path is None:
                return None
            try:
                info = path.stat()
            except FileNotFoundError:
                return None
            return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        applied = engine.read_json(self.paths.xray_config_file)
        members = {info.fingerprint for info in builder.applied_pool(applied)}
        pool = ()
        if traffic.pool_active(self.cfg):
            admitted = traffic.admitted(self.cfg, self.paths, self.wall(), members=members)
            pool = tuple(sorted(item.node.fingerprint for item in admitted))
        pin = self._manual_pin()
        choice = tuple(pin.get(key) for key in ("tag", "until", "since", "down")) if pin else ()
        return (tuple(version(path) for path in files), self._singbox_failed,
                self._singbox_window(),
                tuple(sorted(engine._carrying_tags(self.paths, applied))), pool, choice)

    def _rebuild(
        self, prefer: list[str] | None, *, urgent: bool, reason: str,
        reserve: str | None = None, profiles: dict[str, str] | None = None,
        complete=None,
    ) -> bool:
        """Запрос сборки: один поток и один объединённый следующий запрос.

        Только готовый, ещё актуальный результат применяется в шаге демона.
        Быстрая сборка укладывается в BUILD_WAIT. Без рабочего конфига/при --once
        первый запуск ждёт результат, как прежде; рабочий watchdog этого не делает.
        """
        assert self.inventory is not None
        if self.stopping:
            return False
        request = _BuildRequest(copy.deepcopy(prefer), urgent, reason, reserve,
                                dict(profiles or {}))
        request.callbacks.update(complete or {})
        job = self._build
        base = self._build_next
        if (base is None and job is not None
                and job.cfg is self.cfg and job.inventory is self.inventory):
            base = job.request
        if base is not None:
            callbacks = dict(base.callbacks)
            for key, callback in request.callbacks.items():
                callbacks.pop(key, None)
                callbacks[key] = callback
            request = _BuildRequest(
                request.prefer if request.prefer is not None else base.prefer,
                base.urgent or request.urgent, reason,
                request.reserve if request.reserve is not None else base.reserve,
                {**base.profiles, **request.profiles}, callbacks,
            )
        if job is not None:
            if not job.discard and request.key() == job.request.key():
                job.request.callbacks = request.callbacks
                return False
            self._build_next = request
            job.discard = True
            return False
        if self._build_applied:
            self._build_next = request
            self.poke.set()
            return False
        self._build_next = None
        job = self._start_build(request)
        wait = (None if self.refresh_wait is None or not self.paths.xray_config_file.exists()
                else BUILD_WAIT)
        job.done.wait(wait)
        return self._finish_build()

    def _start_build(self, request: _BuildRequest) -> _Build:
        assert self.inventory is not None and self._build is None
        # Поток не получает соединение SQLite шага и не читает изменяемые поля Daemon.
        # Рейтинг — последний опубликованный снимок; при его отсутствии engine читает
        # сохранённый рейтинг собственным соединением.
        inputs = (copy.deepcopy(self.cfg), copy.deepcopy(self.inventory),
                  self._scores_now(), self._singbox_failed)
        reload = True if request.urgent or self._singbox_window() else None
        job = self._build = _Build(request, self.cfg, self.inventory, inputs,
                                   self._assembly_stamp(), reload, self.poke, engine.quarantined())
        self.log.info("сборка конфига начата — идёт в фоне, шаги демона не ждут")
        self._build_count += 1
        def work():
            try:
                job.assembly = self._assemble(request.prefer, request.reserve, request.profiles,
                                              reload, snapshot=inputs)
            except Exception as exc:
                job.error = exc
            finally:
                job.spent = time.monotonic() - job.began
                job.done.set()
                job.wake.set()
        threading.Thread(target=work, name="xgw-config-build", daemon=True).start()
        return job

    def _finish_build(self) -> bool:
        """Вызывается только шагом: проверка актуальности, применение, учёт и продолжения."""
        if self.stopping or self._build_applied:
            return False
        job = self._build
        if job is None:
            if self._build_next is not None and self.inventory is not None:
                request, self._build_next = self._build_next, None
                self._start_build(request)
            return False
        if not job.done.is_set():
            return False
        self._build = None
        if engine.quarantined() != job.dead and self.inventory is not None:
            self._save_inventory(self.inventory)
        stamp = self._assembly_stamp()
        current = (job.cfg is self.cfg and job.inventory is self.inventory
                   and job.inputs[0] == self.cfg and job.inputs[1] == self.inventory
                   and job.stamp == stamp)
        if job.discard or not current:
            if job.generation is not None:
                from .apply import singbox_generation as generations

                generations.abort(job.generation_core, job.generation)
            self._build_discarded += 1
            self.log.info("устаревшая сборка конфига отброшена без применения")
            if self._build_next is None and not job.discard:
                # Файл поменялся без нового запроса: пересобрать, а не применить старое.
                self._build_next = (job.request if job.stamp[-1] == stamp[-1] else
                                    _BuildRequest(None, job.request.urgent, "изменён ручной выбор"))
            if self._build_next is not None and self.inventory is not None:
                request, self._build_next = self._build_next, None
                self._start_build(request)
            return False
        if job.error is not None:
            if isinstance(job.error, engine.EngineError):
                self.notifier.event("config", f"{job.request.reason}: {job.error}", notify=True)
                return False
            raise job.error
        assembly = job.assembly
        assert assembly is not None
        from .apply import singbox_generation as generations

        if (not job.preparation_started and assembly.singbox is not None
                and generations.needed(self.singbox, assembly.singbox.config)):
            if not generations.available(self.singbox):
                self._build = job
                return False
            job.preparation_started = True
            job.generation_core = self.singbox
            job.done.clear()
            self._build = job
            # В шаге: поток подготовки к счётчикам и подписке не ходит.
            rank, usable = self._bridge_rank(), self._bridge_usable()

            def prepare_generation():
                try:
                    job.generation = generations.prepare(
                        job.generation_core, assembly.singbox.config, assembly.result.config,
                        rank=rank, usable=usable)
                except Exception as exc:
                    self.log.warning("подготовка поколения sing-box не выполнена: %s", exc)
                    job.error = engine.EngineError(
                        "поколение sing-box не подготовлено; прежнее сохранено")
                finally:
                    job.spent = time.monotonic() - job.began
                    job.done.set()
                    job.wake.set()
            threading.Thread(
                target=prepare_generation, name="xgw-singbox-prepare", daemon=True).start()
            return False
        began = time.monotonic()
        if job.generation is not None:
            outcome = generations.finish(self.singbox, self.applier, job.generation)
            if outcome.mode == "api":
                assembly.result.config.clear()
                assembly.result.config.update(job.generation.xray)
                fields = job.generation.fields
                self.log.info("поколение sing-box сменено: изменились %s%s",
                              ", ".join(job.generation.parts) or "только порты",
                              f" (поля: {', '.join(fields)})" if fields else "")
                self._log_composition(job.generation, assembly)
        else:
            outcome = self._apply(assembly.result.config, urgent=job.request.urgent,
                                  singbox=assembly.singbox)
        self._rebuild_spent = (job.spent, time.monotonic() - began)
        self._build_last = self._rebuild_spent
        self._build_outcome = outcome.mode
        if outcome.mode in ("api", "restart", "unchanged"):
            engine.persist(self.paths, assembly, self.inventory.quotas, record_event=False)
        changed = self._report(outcome, job.request.reason)
        self._build_applied = True
        for callback in job.request.callbacks.values():
            callback(changed)
        self.log.info("конфиг собран в фоне за %.1f с, применён в шаге за %.1f с",
                      *self._rebuild_spent)
        return changed

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
        if inventory is self.inventory and self._inventory_full is not None:
            inventory = self._inventory_full  # серверы, ждущие пачки (_hold_new), панель видит
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

    def _subscription_status(self, snapshot: dict) -> None:
        """Подписки в status.json (п. 342, новые поля — прежние потребители JSON их не
        замечают): last_ok_ts — когда подписку в последний раз удалось получить (кэш пишется
        только с удачного ответа), set_age_s — возраст сохранённого набора, cache_reason —
        почему последний опрос оставил прежний набор (текст маскирован), его время."""
        entries = snapshot.get("subscriptions")
        if not isinstance(entries, list) or not entries:
            return
        try:
            errors = json.loads(self.store.get_meta("sub_errors") or "{}")
        except Exception:  # битая запись или база недоступна — без причины
            errors = {}
        errors = errors if isinstance(errors, dict) else {}
        cache = SubscriptionCache(self.paths.cache_dir)
        now = self.wall()
        for entry in entries:
            name = entry.get("name") if isinstance(entry, dict) else None
            if not isinstance(name, str):
                continue
            saved = cache.saved_at(name)
            entry["last_ok_ts"] = saved or None
            entry["set_age_s"] = round(max(0.0, now - saved)) if saved else None
            problem = errors.get(name) if isinstance(errors.get(name), dict) else {}
            entry["cache_reason"] = str(problem.get("error") or "") or None
            entry["cache_reason_ts"] = problem.get("ts") if problem else None

    def _collect(self, via_xray: bool) -> engine.Inventory:
        """Опрос подписок; идёт в фоновом потоке (_start_fetch)."""
        job = self._fetch
        return engine.collect(
            self.cfg, self.paths, mark=self.mark, logger=self.log, via_xray=via_xray,
            cancel=job.cancel if job is not None else self._stop,
        )

    def _assemble(
        self, prefer: list[str] | None, reserve: str | None = None,
        profiles: dict[str, str] | None = None, reload_singbox: bool | None = None,
        *, snapshot: tuple | None = None,
    ) -> engine.Assembly:
        assert self.inventory is not None
        cfg, inventory, scores, failed = snapshot if snapshot is not None else (
            self.cfg, self.inventory, self._scores_now(), self._singbox_failed,
        )
        return engine.assemble(
            cfg, self.paths, inventory, mark=self.mark, logger=self.log,
            xray_bin=self.xray_bin, prefer=prefer, scores=scores,
            reserve=reserve,
            profiles=profiles, reload_singbox=reload_singbox,
            singbox_ok=False if failed else None,
        )

    def _apply(
        self, config: dict, *, urgent: bool, singbox: engine.SingboxChange | None = None,
    ) -> ApplyOutcome:
        """Сначала sing-box (мосты должны слушать), затем Xray."""
        if singbox is not None and singbox.config is None and self.singbox.read() is not None:
            from .apply import singbox_generation as generations

            outcome = self.applier.apply(config, urgent=urgent)
            if outcome.mode in ("api", "restart", "unchanged"):
                generations.retire(self.singbox)
            return outcome
        rejected = self._apply_singbox(singbox)
        if rejected is not None:
            return rejected
        return self.applier.apply(config, urgent=urgent)

    # --- сканы и замена участников ---------------------------------------------

    def _queue_scan(self, view: list[NodeInfo], now: float, *, everything: bool = False) -> None:
        """Запасные — в очередь скана; лучшие по рейтингу — первыми (лимитированные проверяются
        дешёвым запросом, _scan_url).

        Серверы с рейтингом 0 (x100, квота подписки на исходе) участниками не становятся и
        сюда не попадают: это кандидаты в резервный выход, их редко и дешёвым запросом
        проверяет _reserve_step. everything — проверить и их: по кнопке «Проверить
        запасные» и когда трафик не идёт вовсе (ALL_DEAD)."""
        prices = self._prices()
        # Трафик не идёт (ALL_DEAD, RESERVE): внутри класса первыми проверяются серверы на другом
        # ядре и другом транспорте, чем у упавших участников, — блокировка, которая срезала TCP
        # через Xray, может пропустить QUIC через sing-box, и наоборот.
        emergency = self.machine.state in (State.ALL_DEAD, State.RESERVE)
        other = self._alternatives(view) if emergency else set()
        # Порядок перемешивается только внутри равного приоритета (тот же рейтинг и «другой
        # путь»): одинаковых серий проб в одном и том же порядке каждый круг нет (PR-4).
        shuffle = {info.probe_tag: random.random() for info in view}
        spares = sorted(
            (info for info in view if info.role == "spare"),
            key=lambda info: (-self._score(info), info.fingerprint not in other,
                              shuffle[info.probe_tag]),
        )
        wanted = [
            info.probe_tag for info in spares
            if everything or (
                info.fingerprint in prices  # не сопоставлен с подпиской: цена неизвестна
                and self._score(info) > 0
            )
        ]
        if emergency or everything:
            # Аварийная или ручная проверка: плановые записи, уже стоящие в очереди, встают в её
            # порядок (приоритет выше), без дубликатов; участники и пробы профилей — впереди.
            order = set(wanted)
            self.scan_queue = deque(
                [tag for tag in self.scan_queue if tag not in order] + wanted)
        else:
            queued = set(self.scan_queue)
            self.scan_queue.extend(tag for tag in wanted if tag not in queued)
        self.next_rescan = now + RESCAN_PAUSE

    def _routes(self) -> dict[str, tuple[str, str]]:
        """Отпечаток → (адрес, физический путь tcp/udp) серверов подписки. Адрес — наименьший
        IPv4 из dns.hosts применённого конфига (домены с одним набором адресов совпадут), иначе
        как в подписке. Ни запросов DNS, ни баз операторов и стран здесь нет."""
        if self.inventory is None:
            return {}
        applied = engine.read_json(self.paths.xray_config_file) or {}
        hosts = (applied.get("dns") or {}).get("hosts")
        hosts = hosts if isinstance(hosts, dict) else {}

        def address(node: ServerNode) -> str:
            found = hosts.get(node.address)
            found = [found] if isinstance(found, str) else found or []
            return min((ip for ip in found if isinstance(ip, str) and _ipv4(ip)),
                       default=node.address)

        return {node.fingerprint: (address(node), _transport(node))
                for node in self.inventory.nodes}

    def _selection_status(self, view: list[NodeInfo]) -> dict:
        """Для status.json (п. 341): сколько запасных годятся в замену (те же условия, что в
        _rotate) и сколько среди них разных путей — пар (адрес, tcp/udp), которых нет у
        участников; два имени на одном адресе запаса не прибавляют. Пусто — почему."""
        routes = self._routes()
        scans = self._fresh_scans()
        members = {routes[info.fingerprint] for info in view
                   if info.role == "proxy" and info.fingerprint in routes}
        spares = [info for info in view if info.role == "spare" and info.fingerprint in routes]
        good = [
            info for info in spares
            if info.fingerprint not in self.home_exits and self._score(info) > 0
            and not self._is_unstable(info.fingerprint)
            and (scans.get(info.probe_tag) or {}).get("verdict") in REPLACEABLE_VERDICTS
        ]
        paths = {routes[info.fingerprint] for info in good}
        other = paths - members
        if not spares:
            note = "запасных нет"
        elif not good:
            note = "годных запасных нет: свежего удачного скана нет ни у одного"
        elif not other:
            note = "годные запасные — на тех же адресах и путях, что участники: другого пути нет"
        else:
            note = ""
        return {"spares_ok": len(good), "paths": len(paths), "other_paths": len(other),
                "note": note, "last": self._selection}

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

    # --- рейтинг (rating.py) ------------------------------------------------------------

    def _low_quota(self) -> set[str]:
        """Подписки, чья квота на исходе (rating.quota_low)."""
        quotas = self.inventory.quotas if self.inventory is not None else {}
        return {name for name, quota in (quotas or {}).items() if rating.quota_low(quota)}

    def _facts(self, info: NodeInfo, observatory: dict | None = None) -> rating.Facts:
        """Что известно о сервере для рейтинга: приоритет, стоимость, свежий замер скорости
        (или полоса из трафика клиентов), сетевая задержка, сбои за сутки, штраф ТСПУ (1 —
        нестабилен, 0.5 — отвечает только на профиле обхода), квота подписки."""
        fingerprint = info.fingerprint
        node = self._node(info)
        tspu = 1.0 if self._is_unstable(fingerprint) else (
            0.5 if fingerprint in self._escalated else 0.0)
        return rating.Facts(
            level=priority.level_of(self.cfg.managed.priority, fingerprint),
            price=self._prices().get(fingerprint, 1.0),
            mbps=self._mbps(info),
            rtt_ms=self.rtt_ms(fingerprint),
            fail_rate=self._fail_rate(fingerprint),
            tspu=tspu,
            quota_low=node is not None and node.source in self._low_quota(),
        )

    def _score(self, info: NodeInfo, observatory: dict | None = None) -> float:
        return rating.score(self._facts(info, observatory))

    def _scores_now(self) -> dict[str, float] | None:
        """Рейтинг серверов применённого конфига — для сборки (engine.assemble); None —
        конфига ещё нет: сборка возьмёт записанный в базу."""
        applied = engine.read_json(self.paths.xray_config_file)
        if applied is None or self.inventory is None:
            return None
        view = builder.applied_nodes(applied, self.inventory.nodes)
        return {info.fingerprint: self._score(info) for info in view
                if len(info.fingerprint) >= 8}

    def _publish_scores(self, view: list[NodeInfo], observatory: dict) -> None:
        """Рейтинг — в базу (meta «rating»): по нему собирают конфиг CLI и панель, его
        показывает статус. Пишется, только когда изменился; заодно — итоги проверок."""
        scores = {info.fingerprint: self._score(info, observatory) for info in view
                  if len(info.fingerprint) >= 8}
        if scores and scores != self._published:
            try:
                self.store.set_meta(engine.RATING_META, json.dumps(scores, sort_keys=True))
                self._published = scores
            except Exception as exc:  # рейтинг в базе нужен панели и CLI, не шлюзу
                self.log.error("рейтинг серверов не записан: %s", exc)
        if self._health_dirty and self.wall() - self._health_saved >= HEALTH_SAMPLE:
            try:
                self.store.set_meta(HEALTH_META, json.dumps(self._healths(), sort_keys=True))
                self._health_dirty, self._health_saved = False, self.wall()
            except Exception as exc:
                self.log.error("итоги проверок серверов не записаны: %s", exc)

    def _healths(self) -> dict[str, dict[str, list[int]]]:
        if self._health is None:
            try:
                loaded = json.loads(self.store.get_meta(HEALTH_META) or "{}")
            except ValueError:
                loaded = {}
            self._health = loaded if isinstance(loaded, dict) else {}
        return self._health

    def _note_health(self, fingerprint: str, ok: bool) -> None:
        """Итог проверки сервера — в счёт сбоев за сутки (часовые корзины)."""
        if len(fingerprint) < 8:
            return
        hour = int(self.wall() // 3600)
        records = self._healths()
        buckets = records.setdefault(fingerprint, {})
        counts = buckets.setdefault(str(hour), [0, 0])
        counts[0 if ok else 1] += 1
        for key in [key for key in buckets if not key.isdigit()
                    or int(key) <= hour - HEALTH_HOURS]:
            del buckets[key]
        self._health_dirty = True

    def _bridge_rank(self) -> dict[str, float]:
        """Порядок проверки мостов нового поколения sing-box (generations.bridge_check):
        участники, что ведут трафик сейчас, — первыми (меньше сбоев — раньше), затем прочие по
        доле сбоев за сутки; без счёта — UNKNOWN_RANK, между надёжными и ненадёжными."""
        from .apply.singbox_generation import UNKNOWN_RANK

        hour, rank = int(self.wall() // 3600), {}
        for fingerprint, buckets in self._healths().items():
            good = bad = 0
            for key, counts in (buckets or {}).items():
                if key.isdigit() and int(key) > hour - HEALTH_HOURS and isinstance(counts, list):
                    good, bad = good + int(counts[0]), bad + int(counts[1])
            if good + bad >= HEALTH_MIN:
                rank[fingerprint] = bad / (good + bad)
        applied = engine.read_json(self.paths.xray_config_file)
        if applied is not None and self.inventory is not None:
            for info in builder.applied_nodes(applied, self.inventory.nodes):
                if info.role == "proxy":
                    rank[info.fingerprint] = rank.get(info.fingerprint, UNKNOWN_RANK) - 2.0
        return rank

    def _bridge_usable(self) -> dict[str, float]:
        """Какими серверами можно проверить новое поколение sing-box, если все его мосты у Xray
        запасные (п. 351, 352): заведённые в работающем ядре безлимитные и лимитные с нормальной
        скоростью — свежий замер не ниже speed.min_mbps. Значение — надбавка к порядку проверки:
        лимитные после безлимитных. Стоимость неизвестного сервера считается как у лимитного."""
        applied = engine.read_json(self.paths.xray_config_file)
        if applied is None or self.inventory is None:
            return {}
        prices, usable = self._prices(), {}
        for info in builder.applied_nodes(applied, self.inventory.nodes):
            if prices.get(info.fingerprint, 1.0) <= 0:
                usable[info.fingerprint] = 0.0
                continue
            mbps = self._mbps(info)
            if mbps is not None and mbps >= self.cfg.speed.min_mbps:
                usable[info.fingerprint] = LIMITED_BRIDGE_LAST
        return usable

    def _fail_rate(self, fingerprint: str) -> float:
        hour = int(self.wall() // 3600)
        good = bad = 0
        for key, counts in (self._healths().get(fingerprint) or {}).items():
            if key.isdigit() and int(key) > hour - HEALTH_HOURS and isinstance(counts, list):
                good, bad = good + int(counts[0]), bad + int(counts[1])
        total = good + bad
        return bad / total if total >= HEALTH_MIN else 0.0

    def _observe(self, view: list[NodeInfo], observatory: dict) -> None:
        """Итоги проб ядра по участникам — в счёт сбоев, не чаще HEALTH_SAMPLE на сервер."""
        now = self.wall()
        for info in view:
            entry = observatory.get(info.tag)
            if info.role != "proxy" or entry is None:
                continue
            if now - self._observed.get(info.fingerprint, 0.0) >= HEALTH_SAMPLE:
                self._observed[info.fingerprint] = now
                self._note_health(info.fingerprint, bool(entry.get("alive")))

    def _rebalance(self, view: list[NodeInfo], observatory: dict, state: State) -> bool:
        """Перестановка по рейтингу (issue #2): лучший годный запасной (свежий скан OK) с
        рейтингом выше слабейшего живого участника хотя бы на MEMBER_GAIN встаёт на его
        место. Не чаще REBALANCE_EVERY и только когда трафик идёт (HEALTHY, DEGRADED); основной
        и выбранный вручную не выводятся. Так, например, «высокий» сервер, снова прошедший
        проверку, возвращается в работу, а «средние» уступают ему место."""
        if self.inventory is None or state not in (State.HEALTHY, State.DEGRADED):
            return False
        if self.wall() - self._rebalance_at < REBALANCE_EVERY:
            return False
        known = {node.fingerprint: node for node in self.inventory.nodes}
        members = [info for info in view if info.role == "proxy"]
        if not members or any(info.fingerprint not in known for info in members):
            return False
        main = (self.main or {}).get("tag")
        pin = self._manual_pin()
        movable = [
            info for info in members
            if (observatory.get(info.tag) or {}).get("alive") and info.tag != main
            and not (pin is not None and pinning.same_server(pin["tag"], info.tag))
            and not self._escalating(info.fingerprint)
        ]
        scans = self._fresh_scans()
        spares = [
            info for info in view
            if info.role == "spare" and info.fingerprint in known
            and info.fingerprint not in self.home_exits
            and not self._is_unstable(info.fingerprint)
            and (scans.get(info.probe_tag) or {}).get("verdict") == "OK"
        ]
        if not movable or not spares:
            return False
        best = max(spares, key=lambda info: (self._score(info), info.fingerprint))
        weakest = min(movable, key=lambda info: (self._score(info, observatory), info.tag))
        high, low = self._score(best), self._score(weakest, observatory)
        if high <= 0 or high < low * (1.0 + MEMBER_GAIN):
            return False
        current = next((info for info in members if info.tag == main), None)
        if current is not None and self._mbps(best) is not None and high >= self._score(
                current, observatory) * (1.0 + self.cfg.speed.gain_pct / 100.0):
            return False  # лучше и основного — его в работу и в основные ставит _promote
        self._rebalance_at = self.wall()
        newcomer, leaving = known[best.fingerprint], known[weakest.fingerprint]
        self.notifier.event(
            "rotation",
            f"в работу — «{newcomer.name}» (рейтинг {high:.2f}) вместо «{leaving.name}» "
            f"(рейтинг {low:.2f})",
        )
        if self._prices().get(best.fingerprint, 1.0) == 0:
            self.vetted.add(best.fingerprint)
        prefer = preferred_members(members, Rotation(replacements=[(weakest.tag, newcomer)]))
        return self._rebuild(prefer, urgent=False, reason="перестановка по рейтингу")

    def _scan_url(self, info: NodeInfo) -> str | None:
        """Чем проверять узел: запасной лимитированной подписки — дешёвым запросом
        (scan.cheap_url), остальные — проверочным хостом (None: _probe_scan берёт его по
        кругу). Запасной на пробе профиля обхода — проверочным хостом и при квоте: ответ в
        сотни байт «заморозку» не покажет, а по нему решалось бы, выучен ли профиль (T05)."""
        if (info.role == "spare" and self._prices().get(info.fingerprint, 1.0) > 0
                and info.fingerprint not in self._profile_trial):
            return scan.cheap_url(self.cfg)
        return None

    def _probe_scan(self, info: NodeInfo, password: str) -> scan.ScanResult:
        """Собственная проба сервера. Хост — по кругу (watch/hosts.py); хост ответил ошибкой
        HTTP (403, 404, 5xx) или сбросил соединение, не начав ответа, — та же проба другим
        хостом: ответил тот — пауза хосту, вердикт по второй пробе. Обрыв посреди ответа и
        «заморозку» хост не объясняет — это вердикт о сервере (hosts.host_specific)."""
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
        """Сканирует узлы из очереди, пока не истёк бюджет времени шага.

        Плановые сканы запасных при исправном рабочем пути (HEALTHY, не по кнопке, не срочные)
        идут с паузой SCAN_GAP перед каждой следующей пробой шага (PR-4); пауза считается в
        SCAN_BUDGET, и проба, которой не хватит бюджета вместе с паузой, ждёт следующего шага.
        Бюджет вышел — новая проба не начинается (начатая доводится до своего таймаута).
        Остановка во время паузы или пробы — тег остаётся в очереди; тег сервера, которого нет
        в применённом конфиге (состав сменился), снимается."""
        if not self.scan_queue:
            return
        password, _ports = builder.probe_state(applied)
        nodes = {info.probe_tag: info for info in view}
        started = self.clock()
        calm = self.machine.state is State.HEALTHY and not self._manual_scan
        self._scan_urgent &= set(self.scan_queue)  # отметки ушедших из очереди не копятся
        previous: list | None = None  # прошлая проба этого шага
        while self.scan_queue and self.clock() - started < SCAN_BUDGET and not self.stopping:
            probe_tag = self.scan_queue[0]
            info = nodes.get(probe_tag)
            if info is None or not password:
                self.scan_queue.popleft()
                self._scan_urgent.discard(probe_tag)
                continue
            planned = calm and info.role == "spare" and probe_tag not in self._scan_urgent
            waited = 0.0
            if planned and previous is not None:
                pause = random.uniform(*SCAN_GAP)
                if SCAN_BUDGET - (self.clock() - started) <= pause:
                    break  # с паузой не помещается — следующим шагом
                before = self.clock()
                if self._scan_gap(pause) or self.clock() - started >= SCAN_BUDGET:
                    break  # остановка демона (тег в очереди) или бюджет вышел за паузу
                waited = self.clock() - before
            self.scan_queue.popleft()
            urgent = probe_tag in self._scan_urgent
            self._scan_urgent.discard(probe_tag)
            pace = [self.clock(), None, planned, None]
            if previous is not None:
                pace[3] = round(waited, 3)
                self._pace_note(planned, waited, pace[0] - previous[1])
            previous = pace
            self._scan_pace.append(pace)
            self._scanned = True
            result = self._probe_scan(info, password)
            pace[1] = self.clock()
            if result.kind == "cancelled":
                self.scan_queue.appendleft(probe_tag)  # скан не состоялся
                if urgent:
                    self._scan_urgent.add(probe_tag)
                break
            self._note_health(info.fingerprint, result.verdict in REPLACEABLE_VERDICTS)
            if result.verdict in REPLACEABLE_VERDICTS and self._closed.pop(
                    info.fingerprint, None) is not None:
                self._save_profiles()
            self.store.save_scan(
                info.probe_tag, result.verdict, result.bytes_read, result.seconds, result.error,
                ts=self.wall(),
            )
            self._note_rtt(info, result)
            self._profile_note(info, result.verdict)
            if info.role == "proxy":
                self.vetted.add(info.fingerprint)
                if info.tag in self.dead_since:
                    self._dead_scanned[info.tag] = self.dead_since[info.tag]
                held = self._member_note(info, result.verdict, view)
                if result.verdict in REPLACE_NOW_VERDICTS and not held:
                    self.bad_members[info.tag] = result.verdict
                elif result.verdict in REPLACEABLE_VERDICTS or held:
                    self.bad_members.pop(info.tag, None)
            self.log.info(
                "скан %s: %s, %d байт за %.1f с", info.tag, result.verdict,
                result.bytes_read, result.seconds,
            )

    def _scan_gap(self, seconds: float) -> bool:
        """Пауза между плановыми пробами (событие остановки, монотонные часы); True — демон
        останавливается."""
        return self._stop.wait(seconds)

    def _pace_note(self, planned: bool, waited: float, idle: float) -> None:
        """Проба шага не первая: waited — сколько длилась пауза перед ней, idle — промежуток
        от конца прошлой пробы (пауза плюс обработка итога прошлой)."""
        stats, waited = self._pace_stats, round(max(0.0, waited), 3)
        stats["idle_max"] = round(max(idle, stats["idle_max"] or 0.0), 3)
        if not planned:
            stats["urgent"] += 1
            stats["urgent_waited"] += waited > 0
            return
        stats["planned"] += 1
        stats["planned_max"] = max(waited, stats["planned_max"] or 0.0)
        low = stats["planned_min"]
        stats["planned_min"] = waited if low is None else min(low, waited)
        # Допуск 0,1 с сверху: ожидание события просыпается чуть позже срока.
        stats["planned_outside"] += not SCAN_GAP[0] - 0.01 <= waited <= SCAN_GAP[1] + 0.1

    def _pacing(self) -> dict:
        """Для status.json: фактические паузы перед последними плановыми пробами скана
        (секунды), сколько из последних SCAN_PACE_KEEP проб были плановыми и срочными, итоги с
        запуска демона (totals) и через сколько секунд следующий плановый круг. Ни тегов, ни
        адресов. Пробы скана идут по одной (одновременных нет)."""
        gaps = [round(item[3], 2) for item in self._scan_pace if item[2] and item[3] is not None]
        return {
            "gap_s": list(SCAN_GAP), "planned_gaps_s": gaps[-20:],
            "planned": sum(1 for item in self._scan_pace if item[2]),
            "urgent": sum(1 for item in self._scan_pace if not item[2]),
            "totals": dict(self._pace_stats),
            "next_planned_in_s": round(max(0.0, self.next_scan - self.clock())),
            # Проверка адреса проб (п. 332): предел, срок, ждёт ли доделки, итог последней.
            "diagnosis": {"workers": DIAG_WORKERS, "budget_s": DIAG_BUDGET,
                          "pending": len(self._diag_partial), **self._diag_last},
        }

    def _scan(self, info: NodeInfo, password: str, url: str | None = None) -> scan.ScanResult:
        """url — адрес проверки; None — probe.url. Сервер на пробе профиля обхода — файлом
        целиком: по итогу решается, выучен ли профиль, а случайная часть файла короче порога
        «заморозки» дала бы OK и выучила бы негодный профиль (T05 кросс-аудита 4cc96b9)."""
        # Проба проверки адреса (_diagnose_target) прерывается и общим дедлайном этой проверки.
        cancel = self._diag_cut if self._diag_cut is not None else self._stop
        result = scan.scan_node(
            info, self.cfg, probe_pass=password, url=url, cancel=cancel,  # type: ignore[arg-type]
            random_size=info.fingerprint not in self._profile_trial,
        )
        self.store.record_scan_body(info.tag, result.bytes_read, "daemon",
                                    self.cfg.filters.multiplier_regex, self.wall())
        return result

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
        # Замена — лучшим по рейтингу годным запасным из всех подписок (issue #2): без класса,
        # кроме серверов с рейтингом 0 (x100, квота подписки на исходе).
        prices = self._prices()
        scores = {info.fingerprint: self._score(info) for info in view if info.role == "spare"}
        pairs = [
            (info, by_fingerprint[info.fingerprint])
            for info in view
            if info.role == "spare" and info.fingerprint in by_fingerprint
            and info.fingerprint not in self.home_exits  # тоже выходит в домашнюю страну
            and scores.get(info.fingerprint, 0.0) > 0
            and not self._is_unstable(info.fingerprint)
        ]
        # Участник на пробе дробления (ТЗ R1) не меняется, пока проба не кончится.
        held = {info.tag for info in members if self._escalating(info.fingerprint)}
        dead_since = {tag: since for tag, since in self.dead_since.items() if tag not in held}
        scans = self._fresh_scans()
        verdicts = {i.tag: scans[i.probe_tag]["verdict"] for i, _ in pairs if i.probe_tag in scans}
        seconds = {i.tag: scans[i.probe_tag]["seconds"] for i, _ in pairs if i.probe_tag in scans}
        cfg = self.cfg
        if state is State.RESERVE and self.wall() - self.state_since < RESERVE_GRACE:
            return False  # сбой может быть коротким: ядро вернёт трафик участникам само
        if state in (State.ALL_DEAD, State.RESERVE):
            # Живых нет вовсе (или трафик несёт резервный и тратит квоту) — ждать
            # rotate_after_min незачем.
            cfg = copy.copy(self.cfg)
            cfg.filters = copy.copy(self.cfg.filters)
            cfg.filters.rotate_after_min = 0
        alive = {tag: entry["alive"] for tag, entry in observatory.items()}
        # Замена — лучшая по рейтингу, той же страны, если такая не намного хуже (п. 224).
        origins = {
            node.fingerprint: (node.country, node.source) for node in self.inventory.nodes
        }
        rotation = plan_rotation(
            alive, dead_since, verdicts, seconds, members, pairs, cfg, self.wall(),
            urgent=(set(self.bad_members) | set(home)) - held, origins=origins, scores=scores,
            routes=self._routes(),
        )
        if rotation is None:
            overdue = cfg.filters.rotate_after_min * 60.0
            # При HEALTHY внеочередных сканов ради такой замены нет: она ждёт обычного круга.
            waiting = bool(
                set(self.bad_members) - held or (home and state is not State.HEALTHY)
            ) or any(self.wall() - since >= overdue for since in dead_since.values())
            if waiting and pairs and not self.scan_queue and now >= self.next_rescan:
                self._queue_scan(view, now)  # менять пора, а свежих сканов нет
            return False
        names = ", ".join(
            f"{tag} → «{node.name}»" + (f" ({rotation.reasons[tag]})" if tag in rotation.reasons
                                       else "")
            for tag, node in rotation.replacements)
        self._selection = {"ts": self.wall(), "reasons": sorted(set(rotation.reasons.values()))}
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

    # --- свой сервер устройства (Ф4) ------------------------------------------------

    def _device_step(self, view: list[NodeInfo], applied: dict, observatory: dict) -> None:
        """Жив ли свой сервер устройства. Участника проверяет ядро (observatory), запасного —
        демон дешёвым запросом через его probe-inbound, не чаще раза в DEVICE_CHECK и за шаг
        не больше одного. DEVICE_STREAK неудач подряд — устройство идёт через основной (его
        правило убирается из конфига), столько же удач — снова через свой. Изменение —
        срочная сборка: это только routing, он меняется через API ядра без перезапуска Xray."""
        routes = self.cfg.managed.routes
        servers = {fingerprint for fingerprint in routes.values()}
        by_fingerprint = {info.fingerprint: info for info in view if info.fingerprint in servers}
        dead = {fingerprint for fingerprint in self._device_dead if fingerprint in by_fingerprint}
        password, _ports = builder.probe_state(applied)
        now = self.wall()
        due = sorted(
            (info for info in by_fingerprint.values() if info.role != "proxy"),
            key=lambda info: self._device_checked.get(info.fingerprint, 0.0),
        )
        results: dict[str, bool] = {}
        for info in by_fingerprint.values():
            if info.role == "proxy":
                entry = observatory.get(info.tag)
                if entry is not None:
                    results[info.fingerprint] = bool(entry.get("alive"))
        if due and password and now - self._device_checked.get(due[0].fingerprint, 0.0) >= (
                DEVICE_CHECK):
            info = due[0]
            self._device_checked[info.fingerprint] = now
            result = self._scan(info, password, scan.cheap_url(self.cfg))
            if result.kind != "cancelled":
                results[info.fingerprint] = result.verdict in REPLACEABLE_VERDICTS
                self._note_rtt(info, result)
                self._note_health(info.fingerprint, results[info.fingerprint])
        for fingerprint, ok in results.items():
            last, count = self._device_streak.get(fingerprint, (ok, 0))
            count = count + 1 if last == ok else 1
            self._device_streak[fingerprint] = (ok, count)
            proxy = by_fingerprint[fingerprint].role == "proxy"  # ядро уже сгладило сбои
            if not ok and fingerprint not in dead and (proxy or count >= DEVICE_STREAK):
                dead.add(fingerprint)
            elif ok and fingerprint in dead and (proxy or count >= DEVICE_STREAK):
                dead.discard(fingerprint)
        for fingerprint in list(self._device_streak):
            if fingerprint not in by_fingerprint:
                self._device_streak.pop(fingerprint, None)
                self._device_checked.pop(fingerprint, None)
        if dead == self._device_dead:
            return
        for fingerprint in sorted(dead ^ self._device_dead):
            info = by_fingerprint.get(fingerprint)
            name = _server_text(self._node_name(info), info.tag) if info else fingerprint[:8]
            ips = ", ".join(sorted(ip for ip, fp in routes.items() if fp == fingerprint))
            if fingerprint in dead:
                text = (f"свой сервер устройства {ips} — {name} — не отвечает: устройство идёт "
                        "через основной, пока он не ответит")
            else:
                text = (f"свой сервер устройства {ips} — {name} — снова отвечает: устройство "
                        "снова через него")
            self.notifier.event("device", text)
        self._device_dead = dead
        down = sorted(ip for ip, fingerprint in routes.items() if fingerprint in dead)
        try:
            atomic_write_json(self.paths.devices_down_file, {"ips": down}, mode=0o644)
        except OSError as exc:
            self.log.error("не записан %s: %s", self.paths.devices_down_file, exc)
            return
        self._urgent_rebuild = self._urgent_rebuild or "свой сервер устройства: проверка сервера"

    # --- устройства через бесплатный пул (М2б.1) --------------------------------------

    def _pool_step(self, applied: dict, observatory: dict) -> None:
        """Устройства через бесплатный пул (freepool/traffic.py). Закреплённый сервер
        балансировщика «pool» — самый быстрый живой по замеру (_pool_speed_step), пока замеров
        нет — с меньшей задержкой по пробам ядра; держится, пока жив, и сменяется более быстрым
        без прыжков, как основной сервер подписки (_pool_choice); умер — лучший живой той же
        страны; живых нет — закрепление снято, и балансировщик ведёт в block: у устройств
        закрыто (R05)."""
        devices = traffic.pool_devices(self.cfg)
        whole = traffic.whole_house(self.cfg)  # весь дом через пул (М2б.2)
        who = "весь дом" if whole else ", ".join(devices)
        now = self.wall()
        if (devices or whole) and now - self._pool_checked_at >= POOL_CHECK:
            self._pool_checked_at = now
            self._pool_due(applied, now)
        pool = builder.applied_pool(applied)
        self._house_mark(whole)
        if not (devices or whole):
            self._pool_pinned, self._pool_traffic, self._pool_boot = "", None, ""
            self._pool_remember("")
            self._pool_silence([], set(), now)
            self._pool_tags = set()
            self.diary.idle()
            return
        # Выбывшие из состава — по самому составу, кто бы его ни пересобрал (_pool_due, запуск
        # демона, смена подписок): отчёт freepool-recovery, дневник отставал от событий.
        tags = {info.tag for info in pool}
        if self._pool_tags - tags:
            self.diary.count("dropped", len(self._pool_tags - tags))
        self._pool_tags = tags
        try:
            key = self.paths.xray_config_file.stat().st_mtime
        except OSError:
            key = 0.0
        was_closed = self._pool_traffic.get("closed") if self._pool_traffic else None
        # Шаг идёт раньше срочной пересборки: при включении режима он видел старый конфиг без
        # серверов пула и писал «допущенных серверов нет — закрыто» (отчёт М2б.2, дефект 1).
        # Пока пересборка впереди, а после перезапуска Xray (сборкой, установкой, самим ядром) —
        # до первых проб ядра (не опробован ещё не мёртв), это «подключаются»: сводка без
        # «traffic», без события и без снятия закрепления — не дольше POOL_WAIT от начала
        # ожидания (отчёт m2b2fix, дефект 3). Уже закрытое так и остаётся закрытым.
        waiting = (not pool and bool(self._urgent_rebuild)) or (
            bool(pool) and not any(info.tag in observatory for info in pool))
        if not waiting or was_closed is True:
            self._pool_wait_since = 0.0
        elif now - (self._pool_wait_since or now) < POOL_WAIT:
            self._pool_wait_since = self._pool_wait_since or now
            self._pool_traffic = None
            self.diary.tick(closed=False, mbps=None)
            return
        alive = [info for info in pool if (observatory.get(info.tag) or {}).get("alive")]
        spared = self._pool_spared(pool, observatory, now)
        if spared is not None:
            alive.append(spared)
        live = {info.tag for info in alive}
        self._pool_silence(pool, live, now)
        if not self._pool_pinned and self._pool_boot:
            # Демон только запущен: закреплённый до запуска сервер (POOL_PINNED_META) — нынешний.
            # Жив — закрепляется снова без смены и без события (отчёт freepool-recovery2, дефект 1:
            # «весь дом идёт через» второй раз и выбор лучшего заново); молчит — смена с причиной.
            self._pool_pinned = next((info.tag for info in pool
                                      if self._pool_ids.get(info.tag) == self._pool_boot), "")
            self._pool_boot = ""
            if self._pool_pinned in live:
                self._pool_since = now
                self.log.info("бесплатный пул после запуска демона — через прежний %s",
                              self._pool_pinned)
        candidates = [self._pool_candidate(info, observatory) for info in alive]
        # YouTube (_youtube_step): сервер, через который YouTube не проходит или тормозит, не
        # выбирается, пока есть другие живые; плохи все — выбор как без проверки.
        fine = [item for item in candidates if not self._youtube_bad(item.key)]
        why = ""
        if fine and len(fine) < len(candidates) and self._pool_pinned in live:
            why = self._youtube_bad(self._pool_ids.get(self._pool_pinned, ""))
        # Выбранный вручную на вкладке «Бесплатные серверы» — пока жив; молчит или ещё не в
        # составе — сервер выбирает шлюз, как у выбранного вручную сервера подписки.
        pin = self.cfg.managed.free_pool_pin
        wanted = traffic.pinned(alive, pin)
        manual = "on" if wanted is not None else "down" if pin else ""
        current, slower, basis = self._pool_choice(
            fine or candidates, wanted.tag if wanted is not None else "", now)
        if current != self._pool_pinned or (current and key != self._pool_pin_key):
            try:
                if current:
                    self.api.pin(POOL_BALANCER, current)
                elif self._pool_pinned and pool:  # без серверов нет и балансировщика «pool»
                    self.api.unpin(POOL_BALANCER)
            except ApiError as exc:
                self.log.warning("сервер бесплатного пула не закреплён: %s", exc)
                return
            if current != self._pool_pinned:
                self._pool_since = now
                chosen = next((item for item in candidates if item.tag == current), None)
                lost = self._pool_pinned if current and manual != "on" and slower is None else ""
                gone = "" if not lost else "youtube" if why else (
                    "dead" if any(info.tag == lost for info in pool) else "left")
                self.notifier.event("freepool", self._pool_change_text(
                    current, pool, who, manual, chosen=chosen, slower=slower,
                    lost="" if manual else lost, gone=gone, why=why))
                if current:
                    self.diary.count("switch_" + (
                        "manual" if manual == "on" else "speed" if slower is not None
                        else gone or "first"))
                if gone == "youtube":
                    self._youtube_switched()
                self._pool_remember(self._pool_ids.get(current, ""))
            self._pool_pinned, self._pool_pin_key = current, key
        elif not alive and was_closed is not True:
            self.notifier.event("freepool", self._pool_change_text("", pool, who))
        if not alive and was_closed is not True:
            self.diary.count("closures")
        if not alive and now - self._pool_refreshed_at >= POOL_REFRESH:
            # Закрыто: списки — вне расписания (у источников могли смениться ключи и серверы).
            self._pool_refreshed_at = now
            self._freepool_force = True
            self.diary.count("refreshed")
            self.log.info("бесплатный пул закрыт — списки серверов обновляются вне расписания")
        self._pool_basis = basis
        name, country = self._pool_names.get(current, ("", ""))
        mbps = next((item.mbps for item in candidates if item.tag == current), None)
        self.diary.tick(closed=not alive, mbps=mbps)
        self._pool_traffic = {
            "devices": devices, "all": whole, "members": len(pool), "alive": len(alive),
            "closed": not alive, "server": name, "country": country, "tag": current,
            "delay_ms": round(((observatory.get(current) or {}).get("delay") or 0) * 1000)
            if current else 0,
            "mbps": mbps,
            # Сервер выбран вручную: "on" — он и ведёт трафик, "down" — молчит или ещё не в
            # составе (ведёт выбранный шлюзом), "" — выбирает шлюз.
            "manual": manual,
            # Серверы балансировщика «pool» для строк вкладки «Бесплатные серверы»: id — начало
            # id варианта из тега pool-<страна>-<начало>, задержка — по пробам ядра, скорость —
            # по свежему замеру (_pool_speed_step), YouTube — по последней проверке (_youtube_step).
            "servers": [{
                "id": info.fingerprint, "tag": info.tag, "alive": info.tag in live,
                "delay_ms": round(((observatory.get(info.tag) or {}).get("delay") or 0) * 1000),
                **self._pool_speed_view(info),
                **self._youtube_view(self._pool_ids.get(info.tag, "")),
            } for info in pool],
        }

    def _pool_silence(self, pool: list[NodeInfo], live: set[str], now: float) -> None:
        """Серверы «pool», что молчат у проб ядра дольше POOL_SILENT, — пулу (FreePool.urgent):
        их проверка — вне очереди, и с неудачей сервер выбывает из допущенных (_pool_due), а не
        держит место до traffic.FRESH (восстановление, М3: истёкшие ключи, ушедшие серверы)."""
        silent = {info.tag: self._pool_silent.get(info.tag, now) for info in pool
                  if info.tag not in live}
        self._pool_silent = silent
        urgent = {info.fingerprint for info in pool
                  if info.tag in silent and now - silent[info.tag] >= POOL_SILENT}
        for info in pool:
            if info.fingerprint in urgent and info.fingerprint not in self.freepool.urgent:
                self.diary.count("rechecked")
                self.log.info("сервер пула %s молчит у проб ядра %d мин — перепроверка вне "
                              "очереди", info.tag, (now - silent[info.tag]) // 60)
        self.freepool.urgent = frozenset(urgent)

    def _pool_candidate(self, info: NodeInfo, observatory: dict) -> speed.Candidate:
        name, country = self._pool_names.get(info.tag, ("", ""))
        delay = (observatory.get(info.tag) or {}).get("delay")
        return speed.Candidate(
            tag=info.tag, key=self._pool_ids.get(info.tag, info.fingerprint), name=name,
            mbps=self._pool_mbps(info), country=country,
            delay_ms=delay * 1000.0 if isinstance(delay, (int, float)) else None,
        )

    def _pool_choice(self, candidates: list[speed.Candidate], wanted: str,
                     now: float) -> tuple[str, speed.Candidate | None, str]:
        """Закреплённый сервер «pool»: (тег, нынешний, если его сменил более быстрый, основание
        выбора). Выбранный вручную (wanted) — пока жив. Нынешний держится, пока жив, и уступает
        только замеренному, который быстрее на speed.gain_pct: сразу, если нынешний выбран
        предварительно (основание "delay": замерены не все живые), иначе — продержавшись
        speed.hold_minutes (без прыжков, как основной сервер подписки). Нынешнего нет —
        лучший живой той же страны, иначе просто лучший (speed.best_like): замеренные — по
        скорости, остальные — по задержке."""
        if wanted:
            return wanted, None, "manual"
        pending = any(item.mbps is None for item in candidates)
        held = next((item for item in candidates if item.tag == self._pool_pinned), None)
        if held is None:
            lost = self._pool_names.get(self._pool_pinned, ("", ""))[1]
            pick = speed.best_like(candidates, lost, "")
            if pick is None:
                return "", None, ""
            return pick.tag, None, "speed" if pick.mbps is not None and not pending else "delay"
        by_delay = self._pool_basis == "delay"
        rival = speed.best([item for item in candidates if item.tag != held.tag])
        if rival is not None and speed.faster(rival, held, self.cfg.speed.gain_pct) and (
                by_delay or now - self._pool_since >= self.cfg.speed.hold_minutes * 60.0):
            return rival.tag, held, "delay" if pending else "speed"
        # Замерены все живые — выбор окончательный, дальше нынешний держится hold_minutes.
        return held.tag, None, "speed" if by_delay and not pending else self._pool_basis

    def _pool_speeds(self) -> dict[str, dict]:
        if self._pool_speed is None:
            try:
                loaded = json.loads(self.store.get_meta(POOL_SPEED_META) or "{}")
            except ValueError:
                loaded = {}
            self._pool_speed = loaded if isinstance(loaded, dict) else {}
        return self._pool_speed

    def _pool_record(self, info: NodeInfo) -> dict | None:
        """Последний замер сервера «pool» — по полному id варианта (_pool_due)."""
        record = self._pool_speeds().get(self._pool_ids.get(info.tag, ""))
        return record if isinstance(record, dict) else None

    def _pool_mbps(self, info: NodeInfo) -> float | None:
        """Свежий удачный замер сервера «pool», Мбит/с: не старше SPEED_FRESH сроков
        speed.unlimited_hours; None — замера нет, он не удался или устарел, замеры выключены."""
        hours = speed.every_hours(self.cfg, 0.0)
        record = self._pool_record(info) or {}
        mbps = record.get("mbps")
        if not hours or not isinstance(mbps, (int, float)):
            return None
        if self.wall() - float(record.get("ts") or 0) > SPEED_FRESH * hours * 3600.0:
            return None
        return float(mbps)

    def _pool_speed_view(self, info: NodeInfo) -> dict:
        """Скорость сервера «pool» для строки вкладки: свежий замер, когда он был и шёл ли при
        занятом канале (цифра может быть занижена)."""
        mbps = self._pool_mbps(info)
        if mbps is None:
            return {"mbps": None}
        record = self._pool_record(info) or {}
        return {"mbps": mbps, "speed_at": record.get("ts"),
                **({"speed_busy": True} if record.get("busy") else {})}

    def _pool_busy(self, now: float) -> bool:
        """Идёт ли через серверы пула заметный трафик: байт/с с прошлого шага больше
        SPEED_BUSY_BPS без своего замера прошлого шага (как _traffic_busy у подписки)."""
        counters = usage.outbound_counters(self._metrics)
        total = sum(up + down for tag, (up, down) in counters.items()
                    if tag.startswith(builder.POOL_PREFIX)) if counters else None
        previous, self._pool_bytes = self._pool_bytes, (now, total) if total is not None else None
        own, self._pool_own = self._pool_own, 0
        if total is None or previous is None or now <= previous[0]:
            return False
        return (total - previous[1] - own) / (now - previous[0]) > SPEED_BUSY_BPS

    def _pool_spared(self, pool: list[NodeInfo], observatory: dict,
                     now: float) -> NodeInfo | None:
        """Закреплённый сервер «pool», которого пробы ядра сочли мёртвым, хотя через него с
        прошлого шага идёт трафик (не меньше watchdog.busy_bytes за busy_window_s): проба
        опоздала в забитом канале, а сервер жив (как _dead_but_busy у подписки). Отчёт
        freepool-speed, дефект 1: закреплённый дважды сменился за 4 минуты, пока замеры других
        серверов занимали канал, а задержки бесплатных серверов — 1,6–3,9 с при пределе пробы
        8 с. Свой замер через него из счётчика вычитается."""
        downlinks = {
            tag: (now, down) for tag, (_up, down) in usage.outbound_counters(self._metrics).items()
            if tag.startswith(builder.POOL_PREFIX)
        }
        previous, self._pool_downlinks = self._pool_downlinks, downlinks
        (measured, own), self._pool_measured = self._pool_measured, ("", 0)
        tag = self._pool_pinned
        info = next((item for item in pool if item.tag == tag), None)
        entry = observatory.get(tag)
        got = None
        if info is not None and entry is not None and not entry.get("alive"):
            got = self._carried(previous.get(tag), downlinks.get(tag),
                                own if measured == tag else 0)
        if got is None:
            self._pool_spared_tag = ""
            return None
        if self._pool_spared_tag != tag:
            self._pool_spared_tag = tag
            self.diary.count("spared")
            self.log.info(
                "проба ядра опоздала под нагрузкой: %.1f МБ за %d с через %s — сервер пула жив",
                got / 1e6, self.cfg.watchdog.busy_window_s, tag)
        return info

    def _pool_speed_step(self, applied: dict, observatory: dict, now: float) -> None:
        """Замер скорости серверов «pool» — в конце шага, по одному и не в шаге, где уже шёл
        замер серверов подписки. Живой сервер без замера — сразу: сначала закреплённый (по нему
        решается, менять ли), затем по задержке; повторный — раз в speed.unlimited_hours, при
        занятом канале пула ждёт, но не дольше SPEED_FORCE_AFTER. С новым замером закреплённый
        сверяется на следующем шаге (_pool_choice). Пока через закреплённый пора проверить
        YouTube, другие ждут (_youtube_waits)."""
        busy = self._pool_busy(now)
        hours = speed.every_hours(self.cfg, 0.0)
        if not hours or self._speed_ran or self.stopping or not traffic.pool_active(self.cfg):
            return
        password, _ports = builder.probe_state(applied)
        wall = self.wall()
        never: list[NodeInfo] = []
        stale: list[NodeInfo] = []
        for info in builder.applied_pool(applied):
            if not (info.probe_port and info.tag in self._pool_ids
                    and (observatory.get(info.tag) or {}).get("alive")):
                continue
            record = self._pool_record(info)
            if record is None:
                never.append(info)
            elif wall - float(record.get("ts") or 0) >= hours * 3600.0:
                stale.append(info)
        if not stale:
            self._pool_deferred_since = None
        elif not never and busy:
            if self._pool_deferred_since is None:
                self._pool_deferred_since = now
            if now - self._pool_deferred_since < SPEED_FORCE_AFTER:
                return
        targets = never or stale
        if not targets or not password:
            return
        info = min(targets, key=lambda item: (
            item.tag != self._pool_pinned,
            (observatory.get(item.tag) or {}).get("delay") or 1e9, item.tag))
        if info.tag != self._pool_pinned and self._youtube_waits():
            return
        result = speed.measure(info, self.cfg, probe_pass=password,
                               max_mb=speed.size_mb(self.cfg, 0.0), cancel=self._stop)
        self.store.record_scan_body(info.tag, result.bytes_read, "daemon", None, self.wall(),
                                    purpose="speed")
        self._pool_speed_ran = True
        self._pool_own += result.bytes_read
        self._pool_measured = (info.tag, result.bytes_read)
        if result.mbps is None and self.stopping:
            return  # замер прервала остановка демона: это не неудача сервера
        self.diary.count("measured")
        if result.mbps is None:
            self.diary.count("failed")
        records = self._pool_speeds()
        records[self._pool_ids[info.tag]] = {
            "mbps": result.mbps, "bytes": result.bytes_read, "seconds": result.seconds,
            "error": result.error, "ts": self.wall(), **({"busy": True} if busy else {}),
        }
        oldest = self.wall() - SPEED_KEEP
        for key in [key for key, value in records.items()
                    if not isinstance(value, dict) or float(value.get("ts") or 0) < oldest]:
            del records[key]
        self.store.set_meta(POOL_SPEED_META, json.dumps(records, sort_keys=True))
        if result.mbps is None:
            self.log.info("замер скорости %s не удался: %s", info.tag, result.error)
        else:
            self.log.info("замер скорости %s: %s, %d байт за %.1f с", info.tag,
                          speed.mbps_text(result.mbps), result.bytes_read, result.seconds)

    def _pool_remember(self, variant: str) -> None:
        """Закреплённый сервер «pool» — в базу (POOL_PINNED_META), когда он сменился."""
        if variant != self._pool_saved:
            self._pool_saved = variant
            self.store.set_meta(POOL_PINNED_META, variant)

    # --- YouTube через сервер (М3, watch/youtube.py) -----------------------------------

    def _youtube_records(self) -> dict[str, dict]:
        if self._youtube is None:
            try:
                loaded = json.loads(self.store.get_meta(YOUTUBE_META) or "{}")
            except ValueError:
                loaded = {}
            self._youtube = {
                str(key): value for key, value in loaded.items() if isinstance(value, dict)
            } if isinstance(loaded, dict) else {}
        return self._youtube

    def _youtube_record(self, key: str) -> dict | None:
        """Итог последней проверки сервера, если он не старше YOUTUBE_STALE."""
        record = self._youtube_records().get(key) if key else None
        if record is None or self.wall() - float(record.get("ts") or 0) > YOUTUBE_STALE:
            return None
        return record

    def _youtube_bad(self, key: str) -> str:
        """Чем сервер плох для YouTube (youtube.problem): YOUTUBE_CONFIRM неудач подряд, итог не
        старше YOUTUBE_STALE. Пусто — годен, не проверялся, проверка выключена или смены из-за
        YouTube приостановлены (_youtube_switched)."""
        if not self.cfg.speed.youtube or self.wall() < self._youtube_paused_until:
            return ""
        record = self._youtube_record(key)
        if record is None or int(record.get("fails") or 0) < YOUTUBE_CONFIRM:
            return ""
        return youtube.problem(record)

    def _youtube_view(self, key: str) -> dict:
        """YouTube через сервер для сводки: итог последней проверки и скорость с серверов Google."""
        record = self._youtube_record(key)
        if record is None:
            return {}
        mbps = record.get("mbps")
        return {"youtube": record.get("state"),
                **({"youtube_mbps": mbps} if isinstance(mbps, (int, float)) else {})}

    def _youtube_switched(self) -> None:
        """Смена сервера из-за YouTube. YOUTUBE_CAROUSEL_COUNT смен за YOUTUBE_CAROUSEL — YouTube
        плох через все серверы подряд, дело не в них (сбой у Google, сеть самой машины): смены из-за
        YouTube приостанавливаются на YOUTUBE_PAUSE, проверки идут как шли."""
        wall = self.wall()
        self._youtube_switches = [
            at for at in self._youtube_switches if wall - at < YOUTUBE_CAROUSEL
        ] + [wall]
        if len(self._youtube_switches) < YOUTUBE_CAROUSEL_COUNT:
            return
        self._youtube_switches = []
        self._youtube_paused_until = wall + YOUTUBE_PAUSE
        self.notifier.event(
            "youtube",
            f"YouTube плох через {YOUTUBE_CAROUSEL_COUNT} сервера подряд за час — дело, похоже, "
            f"не в серверах; смены из-за YouTube приостановлены на {YOUTUBE_PAUSE / 3600:.0f} ч",
        )

    def _youtube_traffic(self, now: float) -> None:
        """Трафик клиентов через каждый сервер с прошлого шага, Мбит/с: по счётчикам downlink
        Xray, без своей проверки YouTube прошлого шага."""
        counters = {
            tag: down for tag, (_up, down) in usage.outbound_counters(self._metrics).items()
        }
        previous, self._youtube_down = self._youtube_down, (now, counters)
        (own_tag, own), self._youtube_own = self._youtube_own, ("", 0)
        self._youtube_rates = {}
        if previous is None or now <= previous[0]:
            return
        seconds = now - previous[0]
        for tag, down in counters.items():
            delta = down - previous[1].get(tag, down) - (own if tag == own_tag else 0)
            self._youtube_rates[tag] = max(delta, 0) * 8 / seconds / speed.MB

    def _youtube_main_tag(self, view: list[NodeInfo]) -> str:
        """Через какой сервер подписки идёт трафик: выбранный вручную (пока отвечает) или
        основной."""
        pin = self._manual_pin()
        if pin is not None and not pin.get("down"):
            node = pinning.resolve(pin, view)
            return node.tag if node is not None else ""
        return self.main["tag"] if self.main is not None else ""

    def _youtube_targets(
        self, view: list[NodeInfo], applied: dict, observatory: dict,
    ) -> list[tuple[NodeInfo, str, bool, bool, bool]]:
        """Кого можно проверить: (узел, ключ итога, несёт ли трафик, замерять ли скорость, сервер
        пула). Серверы «pool» — пока через пул идёт трафик: живые и закреплённый. Серверы подписки —
        кроме режима «весь дом» (подписка тогда лишь несущий канал): тот, через кого идёт трафик
        (лимитированный — без замера скорости: квота), и живые безлимитные участники. x100 и
        дороже не проверяются: это серверы для LTE, и каждый байт через них — сотня байт квоты."""
        def alive(info: NodeInfo) -> bool:
            return bool((observatory.get(info.tag) or {}).get("alive"))

        targets = []
        if traffic.pool_active(self.cfg):
            for info in builder.applied_pool(applied):
                key = self._pool_ids.get(info.tag, "")
                carries = info.tag == self._pool_pinned
                if key and info.probe_port and (alive(info) or carries):
                    targets.append((info, key, carries, True, True))
        if traffic.whole_house(self.cfg):
            return targets
        current = self._youtube_main_tag(view)
        media = set(builder.applied_media(applied))  # выход видео несёт видео, хоть и не основной
        prices = self._prices()
        for info in view:
            price = prices.get(info.fingerprint)
            if (len(info.fingerprint) < 8 or not info.probe_port or price is None
                    or price >= speed.SKIP_PRICE):
                continue
            carries = info.tag == current or info.tag in media
            if carries or (info.role == "proxy" and price <= 0 and alive(info)):
                targets.append((info, info.fingerprint, carries, price <= 0, False))
        return targets

    def _youtube_due(self, key: str, carries: bool) -> bool:
        """Пора ли проверять: сервер, через который идёт трафик, — раз в speed.youtube_minutes,
        остальные — раз в YOUTUBE_OTHERS; первая неудача подтверждается раньше (YOUTUBE_RETRY и
        YOUTUBE_SUSPECT): плохим сервер считается после YOUTUBE_CONFIRM неудач подряд."""
        record = self._youtube_records().get(key)
        if record is None:
            return True
        age = self.wall() - float(record.get("ts") or 0)
        confirm = int(record.get("fails") or 0) == 1
        if carries:
            return age >= (YOUTUBE_RETRY if confirm else self.cfg.speed.youtube_minutes * 60.0)
        return age >= (YOUTUBE_SUSPECT if confirm else YOUTUBE_OTHERS)

    def _youtube_waits(self) -> bool:
        """Через закреплённый сервер «pool» пора проверить YouTube: замеры других серверов пула
        (_pool_speed_step) ждут. Проверка не идёт ни в шаге с замером, ни в следующем, а замеры
        после включения идут подряд по шагу на сервер — отчёт youtube2, наблюдение 4: первая
        проверка ведущего через ~15 мин после включения «весь дом» (было 8 серверов без замера)."""
        key = self._pool_ids.get(self._pool_pinned, "")
        return bool(self.cfg.speed.youtube and key and not self.probe_target
                    and self._youtube_due(key, True))

    def _media_budget(self, wall: float) -> dict[str, int]:
        """Расход дополнительных проверок за сутки (UTC): запись переживает перезапуск демона."""
        day = int(wall // 86400)
        if self._media_spent is None:
            try:
                loaded = json.loads(self.store.get_meta(MEDIA_BUDGET_META) or "{}")
            except ValueError:
                loaded = {}
            self._media_spent = loaded if isinstance(loaded, dict) else {}
        if (self._media_spent.get("day") != day
                or not isinstance(self._media_spent.get("bytes"), int)):
            self._media_spent = {"day": day, "bytes": 0}
        return self._media_spent

    def _media_due(self, key: str, wall: float) -> bool:
        """Пора ли дополнительно проверить кандидата: раз в media.youtube_check_minutes, после
        неудачи — с паузой, что удваивается от YOUTUBE_GAP до MEDIA_BACKOFF_MAX. Разброс ±20 %
        выводится из сервера и времени его проверки: срок один и тот же на всех шагах и после
        перезапуска, а серверы не совпадают между собой."""
        record = self._youtube_records().get(key) or {}
        stamp, fails = float(record.get("ts") or 0), int(record.get("fails") or 0)
        wait = (min(YOUTUBE_GAP * 2 ** min(fails - 1, 10), MEDIA_BACKOFF_MAX) if fails
                else self.cfg.media.youtube_check_minutes * 60.0)
        shift = random.Random(f"{key}:{stamp}").uniform(1.0 - MEDIA_SPREAD, 1.0 + MEDIA_SPREAD)
        return wall - stamp >= wait * shift

    def _media_extras(
        self, possible: list[tuple[NodeInfo, str, bool, bool, bool]], wall: float,
    ) -> list[tuple[NodeInfo, str, bool, bool, bool]]:
        """Кого проверить сверх обычных сроков, чтобы у выхода видео были свежие замеры (п. 353):
        живых безлимитных участников, только в режиме best и в пределах суточного лимита. Не
        начинается, если проверка могла бы его превысить."""
        measuring = self.cfg.speed
        if (self.cfg.media.youtube_mode != "best" or traffic.whole_house(self.cfg)
                or not measuring.youtube or not measuring.youtube_mbps):
            return []
        limit = self.cfg.media.youtube_daily_probe_mb * speed.MB
        if self._media_budget(wall)["bytes"] + youtube.CHECK_MAX_BYTES > limit:
            return []
        return [item for item in possible
                if not item[2] and item[3] and not item[4] and self._media_due(item[1], wall)]

    def _media_status(self) -> dict:
        """Сводка выхода видео для статуса: вид и расход дополнительных проверок за сутки."""
        if self._media_view.get("state") in (None, "off"):
            return self._media_view
        spent = self._media_budget(self.wall())["bytes"]
        return {**self._media_view, "probe_mb": round(spent / speed.MB, 1),
                "probe_limit_mb": self.cfg.media.youtube_daily_probe_mb}

    def _media_candidates(
        self, view: list[NodeInfo], observatory: dict, wall: float, *, sign: str = "",
    ) -> list[tuple[NodeInfo, float]]:
        return youtube.media_candidates(
            view, self._youtube_records(), observatory, self._prices(), wall,
            min_mbps=self.cfg.speed.youtube_mbps,
            sample_ttl=self.cfg.media.youtube_sample_ttl_minutes * 60.0, sign=sign,
        )

    def _youtube_sign_step(
        self, view: list[NodeInfo], applied: dict, observatory: dict, password: str, wall: float,
    ) -> bool:
        """Одна фоновая проверка допуска вместо обычной проверки запасного сервера."""
        media = self.cfg.media
        key = youtube.sign_key(media.youtube_sign_url)
        if (not key or media.youtube_mode != "best" or not self.cfg.speed.youtube_mbps
                or traffic.whole_house(self.cfg)):
            return False
        budget = self._media_budget(wall)
        if budget["bytes"] + youtube.SIGN_MAX_BYTES > media.youtube_daily_probe_mb * speed.MB:
            return False
        candidates = self._media_candidates(view, observatory, wall)
        current = builder.applied_media(applied)
        ordered = [info for info, _ in candidates if info.tag in current]
        ordered.extend(info for info, _ in candidates[:youtube.SIGN_TOP] if info.tag not in current)
        records = self._youtube_records()
        info = next((info for info in ordered
                     if youtube.sign_sample(records[info.fingerprint], key, wall) is None), None)
        if info is None:
            return False
        verdict, used = youtube.check_sign(info, self.cfg, probe_pass=password, cancel=self._stop)
        self._youtube_ran = True
        self._youtube_bg_at = wall
        self._youtube_own = (info.tag, used)
        budget["bytes"] += used
        self.store.set_meta(MEDIA_BUDGET_META, json.dumps(budget, sort_keys=True))
        if verdict != youtube.CANCELLED:
            records[info.fingerprint]["sign"] = {"state": verdict, "ts": wall, "key": key}
            self.store.set_meta(YOUTUBE_META, json.dumps(records, sort_keys=True))
        return True

    def _youtube_step(
        self, view: list[NodeInfo], applied: dict, observatory: dict, now: float,
    ) -> None:
        """Проверка YouTube через сервер (watch/youtube.py) — в конце шага, одна за шаг и не в
        шаге с замером скорости или сразу после него (счётчики трафика им испорчены). Сначала —
        серверы, через которые идёт трафик (пула, затем подписки); затем фоном остальные живые,
        не чаще раза в YOUTUBE_GAP: на замену должен быть известен годный. Решают итоги
        _pool_step (сервер пула) и _main_candidate, _choose_main (основной сервер подписки)."""
        measured = self._speed_ran or self._pool_speed_ran
        tainted, self._youtube_tainted = self._youtube_tainted, measured
        self._youtube_traffic(now)
        if (not self.cfg.speed.youtube or measured or tainted or self.stopping
                or self.probe_target):
            return
        password, _ports = builder.probe_state(applied)
        if not password:
            return
        records = self._youtube_records()
        possible = self._youtube_targets(view, applied, observatory)
        targets = [item for item in possible if self._youtube_due(item[1], item[2])]
        current = [item for item in targets if item[2]]
        wall = self.wall()

        def oldest(item: tuple) -> tuple[float, str]:
            return float((records.get(item[1]) or {}).get("ts") or 0), item[0].tag

        extra = False
        if current:
            target = current[0]
        elif (wall - self._youtube_bg_at < YOUTUBE_GAP
              or self._youtube_sign_step(view, applied, observatory, password, wall)):
            return
        elif targets:
            target = min(targets, key=oldest)
        else:
            extras = self._media_extras(possible, wall)
            if not extras:
                return
            target, extra = min(extras, key=oldest), True
        info, key, carries, measure, pooled = target
        client = self._youtube_rates.get(info.tag, 0.0) if carries else 0.0
        verdict = self._youtube_check(info, password, client=client, measure=measure)
        self._youtube_ran = True
        if extra:  # в том числе прерванная проверка: её трафик уже потрачен
            budget = self._media_budget(wall)
            budget["bytes"] += verdict.bytes_used
            self.store.set_meta(MEDIA_BUDGET_META, json.dumps(budget, sort_keys=True))
        if verdict.state == youtube.CANCELLED:
            return  # проверку прервала остановка демона: о сервере она ничего не говорит
        self._youtube_own = (info.tag, verdict.bytes_used)
        if pooled:  # свой трафик — не нагрузка канала пула и не трафик закреплённого
            self._pool_own += verdict.bytes_used
            self._pool_measured = (info.tag, verdict.bytes_used)
        if not carries:
            self._youtube_bg_at = wall
        fails = 0 if verdict.state == youtube.OK else int(
            (records.get(key) or {}).get("fails") or 0) + 1
        record = {"state": verdict.state, "fails": fails, "mbps": verdict.mbps,
                  "error": verdict.error, "ts": wall}
        sign = (records.get(key) or {}).get("sign")
        if sign is not None:
            record["sign"] = sign
        if client >= 0.1:
            record["client"] = round(client, 1)
        records[key] = record
        for old in [item for item, value in records.items()
                    if wall - float(value.get("ts") or 0) > YOUTUBE_KEEP]:
            del records[old]
        self.store.set_meta(YOUTUBE_META, json.dumps(records, sort_keys=True))
        label = " (несёт трафик)" if carries else " (дополнительно для видео)" if extra else ""
        self.log.info("YouTube через %s%s: %s", info.tag, label, youtube.summary(verdict))
        if pooled:
            self.diary.count("youtube_checked")
            if verdict.state != youtube.OK:
                self.diary.count("youtube_" + verdict.state)
        self._youtube_manual(view, info, key, pooled)

    def _media_wanted(
        self, view: list[NodeInfo], observatory: dict, saved: tuple[str, ...], wall: float,
    ) -> tuple[str, tuple[str, ...]]:
        """Состояние выхода для видео и его теги (п. 348, 349). Режим «весь дом» главнее: правила
        нет, видео идёт вместе с остальным. Ручной выбор не мешает: остальной трафик идёт через
        выбранный сервер, видео — через лучший. Нет данных — нет правила, а не прямой выход мимо
        VPN."""
        media, measuring = self.cfg.media, self.cfg.speed
        if media.youtube_mode == "off":
            return "off", ()
        if traffic.whole_house(self.cfg):
            return "pool_all", ()
        if not measuring.youtube or not measuring.youtube_mbps:
            return "disabled_no_measurements", ()
        sign = youtube.sign_key(media.youtube_sign_url)
        candidates = self._media_candidates(view, observatory, wall, sign=sign)
        if not candidates and sign and self._media_candidates(view, observatory, wall):
            return "waiting_for_acceptance", ()
        plan = youtube.media_plan(candidates, saved, gain_pct=measuring.gain_pct)
        # Лучший нашёлся, а прежний годен: плановая смена — не чаще hold. Негодный уходит сразу.
        held = (saved and plan != saved
                and set(saved) <= {info.tag for info, _total in candidates}
                and wall - self._media_changed_at < media.youtube_hold_minutes * 60.0)
        tags = saved if held else plan
        return ("best" if tags else "waiting_for_samples"), tags

    def _media_step(
        self, view: list[NodeInfo], applied: dict, observatory: dict, now: float,
    ) -> None:
        """Выход для видео: план → файл (его читают сборки), само правило ставит _media_apply на
        следующем шаге. Основной сервер не трогает."""
        saved = engine.media_tags(self.paths)
        current = builder.applied_media(applied)
        if self.cfg.media.youtube_mode == "off" and not saved and not current:
            self._media_view = {"state": "off"}
            return
        wall = self.wall()
        state, wanted = self._media_wanted(view, observatory, saved, wall)
        if wanted != saved:
            try:
                engine.save_media(self.paths, wanted)
            except OSError as exc:
                self.log.error("выход для видео не записан: %s", exc)
                self._media_view = {"state": "degraded", "tags": list(current), "samples": []}
                return
            self._media_changed_at = wall
            self._media_retry_at = 0.0
            message = (f"новые соединения видео YouTube идут через {wanted[0]}" if wanted
                       else "видео YouTube идёт общим маршрутом")
            sign = youtube.sign_key(self.cfg.media.youtube_sign_url)
            if sign and state in ("best", "waiting_for_acceptance") and any(
                info.tag in saved and info.tag not in wanted
                and youtube.sign_sample(self._youtube_records().get(info.fingerprint) or {},
                                        sign, wall) == youtube.REFUSE for info in view
            ):
                message = "На прежнем выходе YouTube потребовал вход. " + message
            self.notifier.event("youtube", message)
        if current != wanted:
            state = "degraded" if wall - self._media_changed_at > MEDIA_RETRY else "applying"
        elif wanted and not self._media_confirmed(wanted, now):
            state = "degraded"
        self._media_view = {"state": state, "tags": list(wanted), "samples": self._media_samples(
            view, wanted, wall)}

    def _zapret2_apply(self, patched: dict, base: dict) -> bool:
        return self._report(self.applier.apply_api_only(patched, base=base), "zapret2: маршрут")

    def _media_apply(self, now: float) -> bool:
        """Правило видео — прямо в работающее ядро, только через API (п. 350). Через общую сборку
        нельзя: она ждёт новое поколение sing-box, и пока его мосты не проходят проверку, правило
        не применялось вовсе (отчёт youtube-journal), хотя sing-box оно не касается. Идёт до
        _manual_step: adrules сбрасывает закрепление в ядре, и тот вернёт его на этом же шаге."""
        if now < self._media_retry_at:
            return False
        applied = engine.read_json(self.paths.xray_config_file)
        wanted = engine.media_tags(self.paths)
        domains = tuple(self.cfg.media.youtube_domains)
        if applied is None or (builder.applied_media(applied) == wanted and (
                not wanted or builder.applied_media_domains(applied) == domains)):
            return False
        self._media_retry_at = now + MEDIA_RETRY
        patched = builder.with_media(
            applied, builder.MediaPlan(wanted, domains), self.cfg.routing.proxy_domains)
        if patched is None or patched == applied:
            self.log.warning("правило видео не встроить в рабочий конфиг")
            return False
        return self._report(self.applier.apply_api_only(patched, base=applied),
                            "YouTube: выход для видео")

    def _media_confirmed(self, wanted: tuple[str, ...], now: float) -> bool:
        """Ядро знает этот балансировщик и выбирает только его серверы (проверка — один раз на
        план; не вышло — снова через MEDIA_VERIFY)."""
        if self._media_verified == wanted:
            return True
        if now < self._media_verify_at:
            return False
        self._media_verify_at = now + MEDIA_VERIFY
        try:
            info = self.api.balancer_state(builder.YOUTUBE_BALANCER)
        except ApiError as exc:
            self.log.warning("выход для видео не подтверждён: %s", exc)
            return False
        if not set(info.selects) <= set(wanted):
            self.log.warning("выход для видео: ядро выбирает другие серверы")
            return False
        self._media_verified = wanted
        return True

    def _media_samples(
        self, view: list[NodeInfo], tags: tuple[str, ...], wall: float,
    ) -> list[dict]:
        """Откуда взят выбор — для статуса: косвенный замер файла Google, а не скорость видео."""
        records = self._youtube_records()
        sign = youtube.sign_key(self.cfg.media.youtube_sign_url)
        samples = []
        for info in view:
            record = records.get(info.fingerprint)
            if info.tag in tags and record is not None:
                samples.append({"tag": info.tag, "mbps": record.get("mbps"),
                                "age_s": round(max(0.0, wall - float(record.get("ts") or 0)))})
                if sign:
                    samples[-1]["sign"] = youtube.sign_sample(record, sign, wall) or youtube.UNKNOWN
        return samples

    def _youtube_check(self, info: NodeInfo, password: str, *, client: float,
                       measure: bool) -> youtube.Verdict:
        return youtube.check(info, self.cfg, probe_pass=password, client_mbps=client,
                             speed=measure, cancel=self._stop)

    def _youtube_manual(self, view: list[NodeInfo], info: NodeInfo, key: str,
                        pooled: bool) -> None:
        """Выбранный вручную сервер плох для YouTube — событие, раз на сервер, пока он плох: ручной
        выбор главнее, шлюз его не меняет (как с выходом в домашнюю страну)."""
        why = self._youtube_bad(key)
        if not why:
            self._youtube_noted.discard(key)
            return
        if key in self._youtube_noted:
            return
        if pooled:
            if self.cfg.managed.free_pool_pin != key or info.tag != self._pool_pinned:
                return
            name = self._pool_names.get(info.tag, ("", ""))[0] or info.tag
            text = (f"бесплатный пул: выбранный вручную сервер «{name}» {why} — выберите другой на "
                    "вкладке «Бесплатные серверы» или верните автовыбор")
        else:
            pin = self._manual_pin()
            node = pinning.resolve(pin, view) if pin is not None and not pin.get("down") else None
            if node is None or node.tag != info.tag:
                return
            exits = self._media_view.get("tags") or ()
            if exits and node.tag not in exits:
                return  # видео идёт через другой выход (п. 349): менять выбранный незачем
            name = self._node_name(info) or info.tag
            text = (f"выбранный вручную сервер «{name}» {why} — выберите другой или верните "
                    "автовыбор: xgw unpin")
        self._youtube_noted.add(key)
        self.notifier.event("youtube", text)

    def _house_sync(self, applied: dict, now: float) -> None:
        """Рабочий конфиг Xray против режима «весь дом». После перезагрузки `xgw run` снимал
        режим, а сборка без пула ждала окна перезапуска: до 04:00 весь дом шёл через бесплатные
        серверы при панели «выключено», и смены режима этого не меняли (отчёт m2b2fix2,
        дефект 1). Расхождение — срочная сборка, кто бы ни сменил режим."""
        whole = traffic.whole_house(self.cfg)
        if builder.applied_whole(applied) == whole or self._urgent_rebuild:
            return
        if self._house_synced_at is not None and now - self._house_synced_at < HOUSE_SYNC:
            return
        self._house_synced_at = now
        self._urgent_rebuild = ("бесплатный пул: весь дом" if whole
                                else "бесплатный пул: режим подписок")

    def _house_mark(self, whole: bool) -> None:
        """Метка «весь дом действует в этой загрузке» (Paths.house_file): без неё после
        перезагрузки `xgw run` возвращает режим подписок (actions.house_after_boot)."""
        marked = self.paths.house_file.exists()
        if whole == marked:
            return
        try:
            if whole:
                self.paths.house_file.touch(mode=0o644)
            else:
                self.paths.house_file.unlink(missing_ok=True)
        except OSError as exc:
            self.log.error("метка всего дома через пул не записана: %s", exc)

    def _pool_change_text(self, current: str, pool: list[NodeInfo], who: str,
                          manual: str = "", *, chosen: speed.Candidate | None = None,
                          slower: speed.Candidate | None = None, lost: str = "",
                          gone: str = "", why: str = "") -> str:
        """who — адреса устройств через пул или «весь дом» (М2б.2); manual — как у сводки
        пула: "on" — сервер выбран вручную, "down" — выбранный вручную молчит; chosen — новый
        закреплённый (скорость по замеру), slower — прежний, если новый его быстрее; lost —
        тег прежнего, если его сменили не по скорости: gone "dead" — он не отвечает, "left" —
        его больше нет в составе «pool» (отчёт freepool-speed, дефект 1: смена без причины),
        "youtube" — через него плох YouTube, why — чем (youtube.problem)."""
        whole = who == "весь дом"
        subject = "весь дом идёт" if whole else f"устройства {who} идут"
        target = "у всего дома" if whole else f"у устройств {who}"
        if current:
            name, country = self._pool_names.get(current, (current, ""))
            note = {
                "on": " — выбран вручную",
                "down": ": выбранный вручную не отвечает — сервер выбирает шлюз",
            }.get(manual, "")
            if slower is not None:
                note = f" — быстрее, чем {speed.describe(slower)}" + note
            elif lost:
                was = self._pool_names.get(lost, (lost, ""))[0]
                note = (f" — «{was}» {why}" if gone == "youtube"
                        else f" — «{was}» не отвечает" if gone == "dead"
                        else f" — «{was}» больше не в работе") + note
            mbps = chosen.mbps if chosen is not None else None
            return (f"бесплатный пул: {subject} через «{name}»"
                    + (f" ({country})" if country else "")
                    + (f", {speed.mbps_text(mbps)}" if mbps is not None else "") + note)
        if not pool:
            return f"бесплатный пул: допущенных серверов нет — {target} закрыто"
        return f"бесплатный пул: все серверы пула молчат — {target} закрыто"

    def _pool_due(self, applied: dict, now: float) -> None:
        """Допущенные серверы пула против применённого состава «pool»: у устройств закрыто, а
        допущенные есть, или выбранного вручную допущенного сервера нет в составе — сборка не
        чаще POOL_OPEN; сервер выпал из допущенных или есть место для новых — не чаще
        POOL_REBUILD. Состав выбирает engine.assemble; стоящие в «pool» допущены со старой удачной
        проверкой до traffic.KEEP (восстановление, М3)."""
        members = {info.fingerprint for info in builder.applied_pool(applied)}
        try:
            found = traffic.admitted(self.cfg, self.paths, now, members=members)
        except (OSError, ValueError) as exc:
            self.log.error("бесплатный пул: допущенные серверы не прочитаны: %s", exc)
            return
        infos = builder.applied_pool(applied, [item.node for item in found])
        names = {item.node.fingerprint: (item.node.name, item.node.country.upper())
                 for item in found}
        for info in infos:
            if info.fingerprint in names:
                self._pool_names[info.tag] = names[info.fingerprint]
                self._pool_ids[info.tag] = info.fingerprint
        applied_fps = {info.fingerprint for info in infos}
        lost = [info for info in infos if info.fingerprint not in names]
        room = len(infos) < traffic.MEMBERS and bool(set(names) - applied_fps)
        pin = self.cfg.managed.free_pool_pin
        if pin and pin not in names and self._drop_pool_pin(pin):
            pin = ""
        if not infos and found:
            reason, pause = "бесплатный пул: состав серверов для устройств", POOL_OPEN
        elif pin in names and pin not in applied_fps:
            reason, pause = "бесплатный пул: выбранный вручную сервер", POOL_OPEN
        elif lost or room:
            reason, pause = "бесплатный пул: обновление серверов для устройств", POOL_REBUILD
        else:
            return
        if now - self._pool_rebuilt_at < pause:
            return
        self._pool_rebuilt_at = now
        self._urgent_rebuild = self._urgent_rebuild or reason

    def _drop_pool_pin(self, pin: str) -> bool:
        """Выбранный вручную сервер пула больше не допущен навсегда (traffic.pin_gone: ушёл из
        списков, не прошёл проверку) — выбор снимается с событием, как у подписки, когда сервер
        убран (отчёт freepool-recovery, наблюдение 3: выбор держался на выбывшем, и каждая смена
        шла с «выбранный вручную не отвечает»). Старая проверка — не повод. True — снят."""
        try:
            why = traffic.pin_gone(self.cfg, self.paths, pin)
        except (OSError, ValueError) as exc:
            self.log.error("бесплатный пул: выбранный вручную сервер не проверен: %s", exc)
            return False
        if not why:
            return False
        try:
            managed.set_free_pool_pin(managed.path_for(self.paths.config_file), "")
        except (managed.ManagedError, OSError) as exc:
            self.log.warning("бесплатный пул: выбор вручную не снят: %s", exc)
            return False
        tag = next((tag for tag, full in self._pool_ids.items() if full == pin), "")
        name = self._pool_names.get(tag, ("", ""))[0] or pin[:8]
        self.notifier.event("freepool", f"бесплатный пул: выбранный вручную сервер «{name}» "
                            f"больше не допущен ({why}) — сервер снова выбирает шлюз")
        return True

    def _pool_summary(self) -> dict | None:
        """Сводка пула для состояния и панели; с устройствами через пул — и их «traffic»."""
        if self.cfg.free_pool.mode == "off" or self._freepool_summary is None:
            return None
        # Сводку пересчитывает фоновый шаг пула после своих проверок — режим в ней отставал от
        # настроек на минуты (отчёт m2b2fix2, наблюдение 7): режим и регион — из настроек.
        pool = self.cfg.free_pool
        summary = {**self._freepool_summary, "mode": pool.mode, "region": pool.region,
                   "region_policy": pool.region_policy}
        if self._pool_traffic is None:
            return summary
        return {**summary, "traffic": self._pool_traffic}

    # --- сетевая задержка (RTT, п. 2.3) ----------------------------------------------

    def _rtts(self) -> dict[str, dict]:
        if self._rtt is None:
            try:
                loaded = json.loads(self.store.get_meta(RTT_META) or "{}")
            except ValueError:
                loaded = {}
            self._rtt = loaded if isinstance(loaded, dict) else {}
        return self._rtt

    def _note_rtt(self, info: NodeInfo, result: scan.ScanResult) -> None:
        """RTT из проверки (scan.ScanResult.rtt_ms) — в meta «rtt» по отпечатку."""
        if result.rtt_ms is None or len(info.fingerprint) < 8:
            return
        records = self._rtts()
        records[info.fingerprint] = {"ms": round(result.rtt_ms), "ts": self.wall()}
        now = self.wall()
        for key in [key for key, value in records.items()
                    if now - float((value or {}).get("ts") or 0) > RTT_KEEP]:
            del records[key]
        self.store.set_meta(RTT_META, json.dumps(records, sort_keys=True))

    def rtt_ms(self, fingerprint: str) -> float | None:
        """Свежая сетевая задержка сервера, мс; None — не замерялась за RTT_KEEP."""
        record = self._rtts().get(fingerprint) or {}
        ms, ts = record.get("ms"), record.get("ts")
        if isinstance(ms, (int, float)) and isinstance(ts, (int, float)) and (
                self.wall() - ts <= RTT_KEEP):
            return float(ms)
        return None

    def _rtt_step(self, view: list[NodeInfo], applied: dict, observatory: dict) -> None:
        """RTT участников: живого участника с самым старым замером (старше RTT_EVERY) — дешёвым
        запросом через его probe-inbound; за шаг — один."""
        password, _ports = builder.probe_state(applied)
        if not password:
            return
        now = self.wall()
        due = [
            info for info in view
            if info.role == "proxy" and (observatory.get(info.tag) or {}).get("alive")
            and len(info.fingerprint) >= 8
            and now - float((self._rtts().get(info.fingerprint) or {}).get("ts") or 0) >= RTT_EVERY
        ]
        if not due:
            return
        info = min(due, key=lambda item: float(
            (self._rtts().get(item.fingerprint) or {}).get("ts") or 0))
        result = self._scan(info, password, scan.cheap_url(self.cfg))
        if result.kind != "cancelled":
            self._note_rtt(info, result)

    def _scan_period(self, view: list[NodeInfo]) -> int:
        """Период скана запасных, мин (ДОП-4): пробы ядра по участникам, проверки своих
        серверов устройств и RTT — первыми в суточном лимите probe.max_daily_probe_mb, а скан
        запасных — в остатке; не помещается в probe.scan_spares_minutes — реже (не реже
        раза в сутки). Изменение — событие «трафик проверок»."""
        prices = self._prices()
        members = [info for info in view if info.role == "proxy"]
        spares = [info for info in view if info.role == "spare"]
        full = sum(1 for info in spares if prices.get(info.fingerprint, 1.0) == 0)
        cheap = sum(1 for info in spares if 0 < prices.get(info.fingerprint, 1.0) < 100)
        servers = set(self.cfg.managed.routes.values())
        devices = sum(1 for info in spares if info.fingerprint in servers)
        known = (status.measured_probe_size(self.store, self.cfg.probe.url)
                 or probe_bytes(self.cfg.probe.url))
        minutes = status.scan_minutes(
            self.cfg, len(members), full, cheap, known or status.DEFAULT_PROBE_BYTES,
            status.checks_bytes(devices, len(members)), guessed=not known,
        )
        if known:
            # Прогноз проверяется журналом (C06): сканы за 24 ч, включая срочные, против
            # остатка лимита после проб ядра и дешёвых проверок.
            try:
                ledger = self.store.scan_bodies_24h(self.wall())
                spent = float((ledger["by_purpose"].get("scan") or {}).get("bytes") or 0)
            except Exception as exc:  # журнал — уточнение прогноза, не условие скана
                self.log.debug("журнал проверок не прочитан: %s", exc)
            else:
                room = status.scan_room(self.cfg, len(members), known,
                                        status.checks_bytes(devices, len(members)))
                minutes = status.ledger_minutes(minutes, self._scan_minutes, spent, room)
        base = max(1, self.cfg.probe.scan_spares_minutes)
        if minutes != self._scan_minutes:
            text = (
                f"скан запасных — раз в {minutes} мин вместо {base}: так все проверки "
                f"укладываются в probe.max_daily_probe_mb = {self.cfg.probe.max_daily_probe_mb} "
                "МБ в сутки" if minutes > base
                else f"скан запасных — снова раз в {base} мин"
            )
            self.notifier.event("budget", text)
        self._scan_minutes = minutes
        return minutes

    def _fresh_scans(self) -> dict[str, dict]:
        """Сканы по probe-тегам. «Прошедший последний скан»: результат старше двух
        периодов скана не в счёт."""
        fresh_after = self.wall() - self._scan_minutes * 120.0 - 120.0
        # Скан сервера, который сейчас проверяется в другом профиле обхода, получен ещё в
        # прежнем профиле — по нему сервер не ставится ни участником, ни резервным выходом.
        trial = {item.probe_tag for item in self._profile_trial.values()}
        return {
            tag: entry for tag, entry in self.store.scans().items()
            if entry["ts"] >= fresh_after and tag not in trial
        }

    def _stranded(self, view: list[NodeInfo]) -> bool:
        """Мёртвого участника заменить некем: ни один запасной с рейтингом выше 0 не годен
        (нет свежего скана OK/SLOW), не выходит в домашнюю страну и не «нестабилен по ТСПУ».
        Классов с 0.2.0 нет — пока есть хоть один годный запасной, замена идёт через
        rotate_after_min (issue #2). False — есть кем, мёртвых нет или состав не
        сопоставлен с подпиской."""
        members = [info for info in view if info.role == "proxy"]
        if self.inventory is None or not members or not set(self.dead_since) & {
            info.tag for info in members
        }:
            return False
        known = {node.fingerprint for node in self.inventory.nodes}
        if any(info.fingerprint not in known for info in members):
            return False
        scans = self._fresh_scans()
        return not any(
            info.role == "spare" and info.fingerprint in known
            and info.fingerprint not in self.home_exits
            and not self._is_unstable(info.fingerprint)
            and self._score(info) > 0
            and (scans.get(info.probe_tag) or {}).get("verdict") in REPLACEABLE_VERDICTS
            for info in view
        )

    def _degraded_action(self, stranded: bool) -> str:
        """Текст DEGRADED; stranded — заменить мёртвых некем (_stranded)."""
        if stranded:
            return stranded_action()
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
        stranded = self._stranded(view) if state is State.DEGRADED else False
        if state is State.DEGRADED:
            self.action = self._degraded_action(stranded)
        if not stranded:
            self._stranded_for = ""
            return ""
        dead = sorted(
            info.tag for info in view if info.role == "proxy" and info.tag in self.dead_since
        )
        names = [
            node.name if (node := self._node(info)) is not None else info.tag
            for info in view if info.tag in dead
        ]
        note = stranded_note(names)
        key = ",".join(dead)
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
                if not profiling.fresh(trial.since, now, PROFILE_RETRY):
                    del self._profile_trial[fingerprint]
                    self._forget_trial(fingerprint)
                return
            if good:
                del self._profile_trial[fingerprint]
                self._forget_trial(fingerprint)
                self._learned(fingerprint, trial)
                self._profile_event(trial.prev, trial.profile, f"{name} {_keep_text(trial)}")
                return
            self._trial_failed(node, trial)
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
                self._recheck_base(info, default, name)
        elif verdict in profiling.TRIGGER_VERDICTS and not profiling.fresh(
            last, now, PROFILE_RETRY,  # отметка из будущего (часы ушли назад) — не запрет
        ):
            steps = self._remembered(node, profiling.ladder(verdict, info.profile, default, avail))
            if steps and verdict in profiling.REFUSED_VERDICTS and self._address_closed(node, name):
                return  # адрес закрыт целиком — обход не поможет (CLOSED_RECHECK)
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
        # Проба дробления у участника — сразу: он не отвечает, и трафик ждёт (через API ядра,
        # без перезапуска Xray).
        urgent = any(wish.escalate for wish in wanted.values())
        def complete(changed, wanted):
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

        return self._rebuild(
            None, urgent=urgent, reason="профиль обхода", profiles=changes,
            complete={key: lambda changed, key=key: complete(changed, {key: wanted[key]})
                      for key in wanted},
        )

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
        return self._remembered(node, [
            step for step in profiling.ladder(verdict, info.profile, default, avail)
            if profiling.core_of(step) == "xray" and step != info.profile
            and (step in profiling.XRAY_FRAGMENTS or info.profile in profiling.XRAY_FRAGMENTS)
        ])

    def _remembered(self, node: ServerNode, steps: list[str]) -> list[str]:
        """Ступени лестницы в порядке памяти профилей (profiles.remembered)."""
        if len(steps) < 2:
            return steps
        return profiling.remembered(
            steps, key=profiling.params_key(node), now=self.wall(),
            worked=self._worked.get(node.fingerprint),
            failed=self._failed_steps.get(node.fingerprint),
        )

    def _trial_failed(self, node: ServerNode | None, trial: ProfileTrial) -> None:
        """Проба профиля не помогла — профиль в конец следующей лестницы на FAILED_KEEP.
        Возврат на базу (recheck) сюда не пишется: база — не ступень обхода."""
        if node is None or trial.recheck:
            return
        key, now = profiling.params_key(node), self.wall()
        record = self._failed_steps.get(node.fingerprint)
        if not isinstance(record, dict) or record.get("key") != key:
            record = {"key": key, "steps": {}}
        record["steps"][trial.profile] = now
        record["verdict"] = trial.verdict  # почему шла лестница — отдельно от итога ступени
        self._failed_steps[node.fingerprint] = record
        self._save_profiles()

    def _escalating(self, fingerprint: str) -> bool:
        """Сервер в работе сейчас на пробе дробления (или её ждёт) — замена подождёт."""
        trial = self._profile_trial.get(fingerprint)
        wish = self._profile_wanted.get(fingerprint)
        return bool((trial is not None and trial.escalate) or (wish is not None and wish.escalate))

    def _is_unstable(self, fingerprint: str) -> bool:
        """Отметка «нестабилен по ТСПУ» действует до своего срока, но не дольше окна
        fragment.escalation_hours от сейчас: часы ушли назад — не вечный запрет."""
        until, now = self._unstable.get(fingerprint, 0.0), self.wall()
        return now < until <= now + self.cfg.fragment.escalation_hours * 3600.0

    def _may_escalate(self, fingerprint: str, server: str) -> bool:
        """Можно ли перевести сервер на тяжёлый профиль ещё раз: не больше
        fragment.escalations переводов за fragment.escalation_hours. Иначе он «нестабилен по
        ТСПУ» до конца этого окна — в работу шлюз его сам не ставит (событие одно на отметку).
        server — сервер в тексте события (_server_text)."""
        now = self.wall()
        window = self.cfg.fragment.escalation_hours * 3600.0
        times = [when for when in self._escalations.get(fingerprint, [])
                 if profiling.fresh(when, now, window)]
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
        node = self._node_of(fingerprint)
        if node is not None:
            # Память профилей: этот профиль — первым в следующей лестнице (WORKED_KEEP), пока
            # параметры сервера те же; запись о нём как о не помогшем снимается.
            key = profiling.params_key(node)
            self._worked[fingerprint] = {"profile": trial.profile, "ts": self.wall(), "key": key}
            steps = (self._failed_steps.get(fingerprint) or {}).get("steps")
            if isinstance(steps, dict):
                steps.pop(trial.profile, None)
        self._save_profiles()

    def _node_of(self, fingerprint: str) -> ServerNode | None:
        if self.inventory is None:
            return None
        return next((node for node in self.inventory.nodes if node.fingerprint == fingerprint),
                    None)

    def _calm_due(self, fingerprint: str, profile: str, since: float) -> bool:
        """Пора ли пробовать сервер на базовом профиле. Дробление в Xray — после
        fragment.calm_probes проверок подряд без сбоя и не раньше fragment.calm_hours (ТЗ R1.3:
        дробление тратит процессор сервера и чуть скорости, держим его только по
        необходимости); профили sing-box — раз в PROFILE_RECHECK, как до 0.1.18."""
        elapsed = self.wall() - since
        if elapsed < 0:  # отметка из будущего (часы ушли назад): отсчёт — с сейчас
            self._profile_switched[fingerprint] = self.wall()
            return False
        if profile in profiling.XRAY_FRAGMENTS:
            return (
                self._calm.get(fingerprint, 0) >= self.cfg.fragment.calm_probes
                and elapsed >= self.cfg.fragment.calm_hours * 3600.0
            )
        return elapsed >= PROFILE_RECHECK

    def _member_note(
        self, info: NodeInfo, verdict: str, view: list[NodeInfo] | None = None,
    ) -> bool:
        """Итог собственной пробы участника. True — участник на пробе дробления (замена ждёт).

        Отказал он один, а другие участники работают, и есть проверенный запасной — замена
        сразу (анти-ТСПУ 2.0): трафик не ждёт ступеней дробления, а обход проверяется на нём,
        когда он станет запасным (_profile_note). Отказали больше половины участников —
        глушение по всей сети, замена не поможет: участник проверяется на ступенях дробления в
        Xray на месте (ТЗ R1, 0.1.18), заменяют его, только если не ответил и там. Отказ при
        закрытом адресе (TCP напрямую не открывается) — замена сразу: обход не поможет."""
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
            self._trial_failed(node, trial)
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
        if verdict in profiling.REFUSED_VERDICTS and self._address_closed(node, name):
            self.bad_members[info.tag] = verdict
            return False
        if view is not None and self._isolated_failure(info, view):
            self.bad_members[info.tag] = verdict
            self.log.info(
                "%s в работе не отвечает (%s), а другие участники работают — меняю его на "
                "проверенный запасной сразу; обход проверю на нём, когда он станет запасным",
                name, verdict,
            )
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

    # --- белые списки (анти-ТСПУ 2.0) ----------------------------------------------------

    def _whitelist_step(
        self, view: list[NodeInfo], signals: Signals, state: State, now: float,
    ) -> None:
        """Распознаёт белые списки и их снятие; сам ничего не переключает."""
        broken = state in (State.ALL_DEAD, State.RESERVE)
        if self.whitelist_since is None and not (broken and signals.provider_ok):
            self._whitelist_hits = 0
            return
        if now < self._whitelist_next:
            return
        self._whitelist_next = now + WHITELIST_EVERY
        closed = self._foreign_closed()
        if closed is None:
            return
        if not closed:
            self._whitelist_hits = 0
            if self.whitelist_since is not None:
                self.whitelist_since = None
                back = " — можно вернуть автовыбор" if self._manual_pin() is not None else ""
                self.notifier.event(
                    "whitelist", "белые списки сняты: зарубежные адреса снова открываются "
                    f"напрямую{back}", notify=True,
                )
            return
        if self.whitelist_since is not None or not signals.provider_ok:
            return
        self._whitelist_hits += 1
        if self._whitelist_hits < WHITELIST_CONFIRM:
            return
        self.whitelist_since = self.wall()
        offer = self._whitelist_offer(view)
        for info in self._whitelist_servers(view):
            self._queue_first(info.probe_tag, urgent=True)  # первыми — для предложения
        hint = (f" Можно включить сервер для белых списков «{offer['name']}» в панели — он "
                f"тратит квоту в {offer['multiplier']:g} раз быстрее." if offer else
                " Серверов для белых списков (x100) в подписках нет.")
        self.notifier.event(
            "whitelist",
            "похоже, провайдер включил белые списки: российские адреса открываются напрямую, "
            "а зарубежные — нет, и серверы VPN не отвечают. Шлюз сам ничего не меняет." + hint,
            notify=True,
        )

    def _foreign_closed(self) -> bool | None:
        """True — ни один зарубежный проверочный хост (probe.url, probe.urls) не открывается
        напрямую, мимо VPN (TCP сокетом с меткой mark_bypass); False — открылся хоть один;
        None — проверить нечем (нет метки, имена не разрешились)."""
        if self.mark is None:
            return None
        tried = 0
        for url in probehosts.all_urls(self.cfg):
            parts = urlsplit(url)
            if not parts.hostname:
                continue
            address = self._provider_address(parts.hostname)
            if address is None:
                continue
            tried += 1
            port = parts.port or (443 if parts.scheme == "https" else 80)
            if checks.tcp_check(address, port, timeout=REACH_TIMEOUT, mark=self.mark):
                return False
        return True if tried else None

    def _whitelist_servers(self, view: list[NodeInfo]) -> list[NodeInfo]:
        """Серверы для белых списков: множитель x100 и выше в имени («для LTE»)."""
        if self.inventory is None:
            return []
        names = {node.fingerprint: node.name for node in self.inventory.nodes}
        pattern = self.cfg.filters.multiplier_regex
        return [
            info for info in view if info.role in ("proxy", "spare")
            and cost.multiplier(names.get(info.fingerprint, ""), pattern) >= WHITELIST_MULTIPLIER
        ]

    def _whitelist_offer(self, view: list[NodeInfo]) -> dict | None:
        """Сервер для белых списков, который предложить заказчику: ответивший последний скан
        — первым, затем быстрее ответивший; None — таких серверов нет."""
        servers = self._whitelist_servers(view)
        if not servers or self.inventory is None:
            return None
        scans = self._fresh_scans()
        nodes = {node.fingerprint: node for node in self.inventory.nodes}

        def rank(info: NodeInfo) -> tuple:
            entry = scans.get(info.probe_tag) or {}
            good = entry.get("verdict") in REPLACEABLE_VERDICTS
            return (not good, float(entry.get("seconds") or 99.0), info.tag)

        best = min(servers, key=rank)
        node = nodes.get(best.fingerprint)
        name = node.name if node is not None else best.tag
        answered = (scans.get(best.probe_tag) or {}).get("verdict") in REPLACEABLE_VERDICTS
        return {
            "tag": best.tag, "name": name, "answered": answered,
            "multiplier": cost.multiplier(name, self.cfg.filters.multiplier_regex),
        }

    def _isolated_failure(self, info: NodeInfo, view: list[NodeInfo]) -> bool:
        """Отказал этот участник, а не почти все сразу, и заменить его есть кем.

        Другие участники «работают», если ядро не считает их мёртвыми (dead_since — по пробам
        самого Xray, от порядка сканов не зависит) и они прошли первую проверку. Отказавших —
        не больше половины. Ручной выбор не меняется. Запасной — со свежим удачным сканом,
        рейтингом выше нуля, не «нестабильный по ТСПУ» и не с закрытым адресом."""
        pin = self._manual_pin()
        if pin is not None and pinning.same_server(str(pin.get("tag") or ""), info.tag):
            return False
        members = [item for item in view if item.role == "proxy"]
        working = [
            item for item in members
            if item.tag != info.tag and item.tag not in self.dead_since
            and item.tag not in self.bad_members
        ]
        if not working or (len(members) - len(working)) * 2 > len(members):
            return False
        scans = self._fresh_scans()
        return any(
            item.role == "spare" and scans.get(item.probe_tag, {}).get("verdict")
            in REPLACEABLE_VERDICTS and not self._is_unstable(item.fingerprint)
            and item.fingerprint not in self._closed and self._score(item) > 0
            for item in view
        )

    def _address_closed(self, node: ServerNode, name: str) -> bool:
        """Адрес сервера закрыт целиком: TCP к нему напрямую не открывается (проверено не
        раньше CLOSED_RECHECK назад или сейчас). Новая отметка — строка в журнале."""
        now = self.wall()
        if profiling.fresh(self._closed.get(node.fingerprint), now, CLOSED_RECHECK):
            return True  # отметка из будущего (часы ушли назад) не держит — проверить заново
        if self._server_reachable(node) is not False:
            if self._closed.pop(node.fingerprint, None) is not None:
                self._save_profiles()
            return False
        self._closed[node.fingerprint] = now
        self._save_profiles()
        self.log.info(
            "%s: TCP к адресу сервера напрямую не открывается — адрес закрыт целиком, обход не "
            "поможет; профили не перебираю", name,
        )
        return True

    def _server_reachable(self, node: ServerNode) -> bool | None:
        """Открывается ли TCP к адресу сервера напрямую, мимо VPN (сокет с меткой
        mark_bypass). None — проверить нечем: нет метки, протокол или транспорт не TCP,
        цепочка (соединение идёт через другой сервер), домен без адреса в применённом конфиге."""
        if self.mark is None or not _over_tcp(node):
            return None
        address = node.address
        if not _ipv4(address):
            applied = engine.read_json(self.paths.xray_config_file) or {}
            hosts = (applied.get("dns") or {}).get("hosts")
            found = hosts.get(address) if isinstance(hosts, dict) else None
            found = [found] if isinstance(found, str) else found or []
            address = next((ip for ip in found if isinstance(ip, str) and _ipv4(ip)), "")
            if not address:
                return None
        return checks.tcp_check(address, node.port, timeout=REACH_TIMEOUT, mark=self.mark)

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
            if key in self._profile_trial or key in self._profile_wanted:
                continue
            node = self._node(info)
            last = self._profile_switched.get(key)
            if node is None or last is None or not self._calm_due(key, info.profile, last):
                continue
            avail = profiling.available(node, self.cfg, ())
            default = profiling.base(self.cfg, avail)
            if default == info.profile:
                continue
            # Основной и выбранный вручную на месте не проверяются (неудача оборвала бы весь
            # трафик) — только теневой пробой (_recheck_base); нечем — ждут, пока уступят место.
            live = info.tag == main or (
                pin is not None and pinning.same_server(pin["tag"], info.tag))
            self._recheck_base(info, default, _server_text(node.name, info.tag), live=live)

    def _shadow_verdict(self, info: NodeInfo) -> str | None:
        """Вердикт теневой пробы сервера на базовом профиле Xray (watch/shadow.py): отдельный
        процесс Xray, рабочий не трогается. None — так проверить нельзя (база не Xray, выход
        с цепочкой, Xray не установлен, процесс не запустился, остановка демона)."""
        node = self._node(info)
        if node is None or not node.outbound or self.xray_bin is None:
            return None
        avail = profiling.available(node, self.cfg, self._bridged_letters(info.fingerprint))
        if profiling.base(self.cfg, avail) != profiling.XRAY_DEFAULT:
            return None
        outbound = shadow.outbound_for(node.outbound, self.cfg)
        if outbound is None or not Path(self.xray_bin).exists():
            return None
        try:
            result = shadow.probe(
                outbound, self.cfg, Path(self.xray_bin), url=self.hosts.next(stream="scan"),
                run_dir=self.paths.run, cancel=self._stop,
            )
        except (shadow.ShadowError, OSError) as exc:
            self.log.warning("теневая проба %s не сделана: %s", info.tag, exc)
            return None
        if result.kind == "cancelled":
            return None
        self.log.info("теневая проба %s на базовом профиле: %s", info.tag, result.verdict)
        return result.verdict

    def _recheck_base(self, info: NodeInfo, default: str, name: str, *, live: bool = False) -> None:
        """Пора проверить сервер на тяжёлом профиле без обхода (ДОП-3). Сначала — теневой
        пробой (_shadow_verdict): ответил — профиль сразу базовый, без пробы на рабочем
        трафике; не ответил — обход остаётся, отсчёт до следующей перепроверки заново.
        Теневой пробы нет — как до 0.2.0: проба на месте (кроме live — основного и
        выбранного вручную: у них неудача оборвала бы весь трафик)."""
        fingerprint = info.fingerprint
        verdict = self._shadow_verdict(info)
        if verdict is None:
            if not live:
                self._profile_wanted[fingerprint] = ProfileWish(
                    default, True, [], info.profile, recheck=True,
                )
            return
        if verdict in REPLACEABLE_VERDICTS:
            self._profile_wanted[fingerprint] = ProfileWish(default, False, [], info.profile)
            self._escalated.pop(fingerprint, None)
            self._profile_event(
                info.profile, default,
                f"{name} отвечает и без обхода (теневая проба отдельным Xray, трафик клиентов не "
                f"затронут) — профиль «{profiling.NAMES[default]}»",
            )
        else:
            self._profile_switched[fingerprint] = self.wall()  # следующая перепроверка — позже
            self._calm[fingerprint] = 0
            self.log.info("%s без обхода пока не отвечает (%s) — обход остаётся", name, verdict)
        self._save_profiles()

    def _queue_first(self, probe_tag: str, *, urgent: bool = False) -> None:
        """В начало очереди скана, без дубликата. urgent — без паузы SCAN_GAP (аварийная
        проверка): плановая запись, ставшая срочной, повышает приоритет здесь же."""
        if probe_tag in self.scan_queue:
            self.scan_queue.remove(probe_tag)
        self.scan_queue.appendleft(probe_tag)
        if urgent:
            self._scan_urgent.add(probe_tag)

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
        closed = saved.get("closed")
        for key, when in (closed.items() if isinstance(closed, dict) else ()):
            if isinstance(when, (int, float)) and not isinstance(when, bool):
                self._closed[str(key)] = float(when)
            else:
                skipped += 1
        # Память профилей (п. 336): битая запись пропускается, свежесть проверяется при
        # использовании (profiles.fresh) — истёкшая и «из будущего» не действуют.
        worked = saved.get("worked")
        for key, record in (worked.items() if isinstance(worked, dict) else ()):
            if (isinstance(record, dict) and record.get("profile") in profiling.ALL
                    and isinstance(record.get("key"), str)
                    and isinstance(record.get("ts"), (int, float))
                    and not isinstance(record.get("ts"), bool)):
                self._worked[str(key)] = {"profile": record["profile"], "key": record["key"],
                                          "ts": float(record["ts"])}
            else:
                skipped += 1
        failed = saved.get("failed")
        for key, record in (failed.items() if isinstance(failed, dict) else ()):
            steps = record.get("steps") if isinstance(record, dict) else None
            if isinstance(steps, dict) and isinstance(record.get("key"), str) and all(
                    step in profiling.ALL and isinstance(when, (int, float))
                    and not isinstance(when, bool) for step, when in steps.items()):
                self._failed_steps[str(key)] = {
                    "key": record["key"], "verdict": str(record.get("verdict") or ""),
                    "steps": {step: float(when) for step, when in steps.items()},
                }
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
        # Истёкшие отметки и отметки «из будущего» (часы ушли назад) не хранятся: иначе запрет
        # держался бы, пока часы их не догонят.
        self._escalations = {
            key: [when for when in times if profiling.fresh(when, now, window)]
            for key, times in self._escalations.items()
        }
        self._escalations = {key: times for key, times in self._escalations.items() if times}
        self._unstable = {key: until for key, until in self._unstable.items()
                          if now < until <= now + window}
        self._closed = {
            key: when for key, when in self._closed.items()
            if profiling.fresh(when, now, CLOSED_RECHECK)
        }
        self._worked = {key: record for key, record in self._worked.items()
                        if profiling.fresh(record.get("ts"), now, profiling.WORKED_KEEP)}
        failed: dict[str, dict] = {}
        for key, record in self._failed_steps.items():
            steps = {step: when for step, when in (record.get("steps") or {}).items()
                     if profiling.fresh(when, now, profiling.FAILED_KEEP)}
            if steps:
                failed[key] = {**record, "steps": steps}
        self._failed_steps = failed
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
                "unstable": self._unstable, "closed": self._closed,
                "worked": self._worked, "failed": self._failed_steps,
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
        from .apply import singbox_generation as generations

        generations.recover(self.singbox)
        self.singbox.sync_generation()
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
        from .apply import singbox_process as generations

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
            "generations": generations.summary(self.paths),
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
        if outcome.mode == "deferred":
            self._rebuild_asked = True
            return ApplyOutcome("rejected", detail="sing-box ждёт подготовки отдельного поколения")
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

    # --- резервный выход -------------------------------------------------------

    def _reserve_step(
        self, view: list[NodeInfo], applied: dict, state: State, now: float
    ) -> bool:
        """Резервный выход балансировщика (fallbackTag) — лимитированный запасной, обычно с
        наименьшим множителем. Через него трафик идёт, только
        когда observatory считает мёртвыми всех участников; сам он observatory не
        пробуется и квоту зря не тратит.

        Его и лучших кандидатов на его место демон проверяет дешёвым запросом: раз в
        RESERVE_RECHECK по RESERVE_CANDIDATES лучших, а когда трафик не идёт и через
        резервный (ALL_DEAD), — сразу и всех. Резервным становится лучший прошедший
        проверку: дешевле, затем нынешний резервный, затем OK быстрее SLOW."""
        if self.inventory is None:
            return False
        prices = self._prices()
        known = {node.fingerprint for node in self.inventory.nodes}
        if not any(info.role == "proxy" for info in view) or any(
                info.fingerprint not in known for info in view):
            return False  # состав ядра не сопоставлен с подпиской
        current = builder.reserve_tag(applied)
        floor = min(
            (prices.get(info.fingerprint, 1.0) for info in view if info.role == "proxy"),
            default=0.0,
        )
        candidates = sorted(
            (
                info for info in view
                if info.role == "spare" and info.fingerprint not in self.home_exits
                and builder.reserve_price(prices.get(info.fingerprint, 1.0), floor)
                and not self._is_unstable(info.fingerprint)
            ),
            key=lambda info: (prices.get(info.fingerprint, 1.0), info.tag != current),
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
            if state is State.ALL_DEAD:
                # Аварийный круг: и те, что уже ждали планового скана, — вперёд и без паузы.
                for tag in reversed(tags):
                    self._queue_first(tag, urgent=True)
            else:
                queued = set(self.scan_queue)
                self.scan_queue.extend(tag for tag in tags if tag not in queued)
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
            note = ("резервного сервера нет: ни один из проверенных лимитированных запасных "
                    "не ответил")
            if note != self._reserve_note:
                self._reserve_note = note
                self.notifier.event("reserve", note)
            return False
        best = min(passed, key=lambda info: (
            prices.get(info.fingerprint, 1.0), info.tag != current,
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
        панели, а итоги замеров основной сверит, когда выбор снимут. Так же и при
        выключенном основном сервере (speed.sticky = false, решение заказчика 07.11.2026):
        сервер выбирает ядро по задержке, а плановые замеры идут, как обычно, — без них
        скорость в панели застывала на днях давности."""
        members = [info for info in view if info.role == "proxy"]
        if not signals.xray_ok:
            # Снимать нечего: перезапуск Xray закрепление сбросит сам.
            if self.main is not None:
                self._set_main(None)
            self._main_pinned = None
            return
        ready = not self.probe_target and state in (State.HEALTHY, State.DEGRADED) and members
        if not (self.cfg.speed.sticky and ready):
            self._release_main()
            if ready:
                # Основной выключен: только замеры, без выбора и контроля основного.
                self._speed_step(view, applied, observatory, now)
            elif members:
                self._speed_manual(view, applied)
            return
        # Весь дом через пул (М2б.2): подписка — только несущий канал, трафика клиентов через
        # неё нет — ни пассивной оценки, ни контроля скорости; плановых замеров тоже (_speed_step).
        carrier = traffic.whole_house(self.cfg)
        if self.cfg.speed.guard and not carrier:
            # Пассивная оценка — до замеров: участнику, через которого и так качают, замер не
            # нужен (ТЗ R5.2).
            self._passive_step(view)
        measured = self._speed_step(view, applied, observatory, now)
        if carrier:
            self.guard.episode = None
        else:
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
        # YouTube через основной плох (_youtube_step), а есть живой участник, через которого — нет.
        youtube_why = "" if reason else self._youtube_bad(record["key"])
        if youtube_why and any(
            info.tag != member.tag and (observatory.get(info.tag) or {}).get("alive")
            and not self._youtube_bad(self._speed_key(info)) for info in members
        ):
            reason = youtube_why
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
        if youtube_why and reason == youtube_why:
            self.notifier.event("main", f"основной сервер {name} {reason} — выбираю другой")
            self._youtube_switched()
            return None
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

    def _mbps(self, info: NodeInfo) -> float | None:
        """Свежий замер скорости сервера (не старше SPEED_FRESH сроков его класса) или полоса,
        которую показал трафик клиентов (ТЗ R5); None — ни того, ни другого."""
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
        return value

    def _candidate(self, info: NodeInfo, observatory: dict) -> speed.Candidate:
        key = self._speed_key(info)
        value = self._mbps(info)
        delay = (observatory.get(info.tag) or {}).get("delay")
        node = self._node(info)
        return speed.Candidate(
            tag=info.tag, key=key, name=node.name if node is not None else "",
            mbps=value, score=self._score(info, observatory),
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
        # Через кого плох YouTube (_youtube_step) — основным, только если других нет.
        candidates = [item for item in candidates if not self._youtube_bad(item.key)] or candidates
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
        """Запасные, которые могут стать основным: рейтинг выше 0, прошли последний скан, не
        выходят в домашнюю страну и замерены недавно."""
        scans = self._fresh_scans()
        result = []
        for info in view:
            if (
                info.role != "spare" or info.fingerprint in self.home_exits
                or self._score(info) <= 0 or self._youtube_bad(info.fingerprint)
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
            and not self._youtube_bad(item.key)
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
        def complete(changed):
            if not changed:
                return
            self._promoted = {
                "key": node.fingerprint, "name": node.name, "since": self.wall(),
                "was": current.name or current.tag,
            }
        self._rebuild(prefer, urgent=False, reason="перевод запасного в работу",
                      complete={"promotion": complete})

    def _weakness(self, info: NodeInfo, observatory: dict) -> tuple:
        """Кого из участников выводить первым: мёртвого, потом с наименьшим рейтингом."""
        alive = bool((observatory.get(info.tag) or {}).get("alive"))
        return (alive, self._score(info, observatory), info.tag)

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
        if record is None:
            return True
        stamp = float(record.get("ts") or 0)
        return self.wall() - stamp >= hours * 3600.0 * speed.due_factor(key, stamp)

    def _speed_step(
        self, view: list[NodeInfo], applied: dict | None, observatory: dict, now: float
    ) -> bool:
        """Замеры скорости всех живых серверов: каждый — раз в срок своего класса
        (безлимитные — speed.unlimited_hours, лимитированные — speed.limited_hours) и все
        сразу — по кнопке. Не в шаге со сканом; при занятом канале фоновый замер ждёт, но
        не дольше SPEED_FORCE_AFTER. True — появился новый замер (сравнить с основным)."""
        if not (self.cfg.speed.unlimited_hours or self.cfg.speed.limited_hours):
            # Плановых замеров нет; по кнопке у сервера — как обычно (_speed_manual).
            self._speed_asked = False
            return self._speed_manual(view, applied)
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
        elif not traffic.whole_house(self.cfg):
            # Весь дом через пул (М2б.2) — плановых замеров серверов подписки нет: она только
            # несущий канал, и квоту тратить незачем. По кнопке — как обычно.
            prices = self._prices()
            for info in targets:
                if info.probe_tag not in queued and self._speed_due(info, prices):
                    self.speed_queue.append(info.probe_tag)
                    self.speed_total += 1
        if not traffic.whole_house(self.cfg):
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

    def _speed_manual(self, view: list[NodeInfo], applied: dict | None) -> bool:
        """Кнопка у сервера без плановых замеров: сроки замеров 0, нет HEALTHY/DEGRADED или
        идёт проверка цели проб. Замеряются только
        заказанные серверы, по одному запросу; True — появился новый замер."""
        if not (self._speed_one or self._speed_any):
            self.speed_queue.clear()
            self._speed_forced.clear()
            self.speed_total = self.speed_done = 0
            return False
        targets: list[NodeInfo] = []
        self._speed_one_step(view, targets)
        self.speed_queue = deque(tag for tag in self.speed_queue if tag in self._speed_any)
        self._speed_forced &= set(self.speed_queue)
        if not self.speed_queue:
            self._speed_any.clear()
            self.speed_total = self.speed_done = 0
            return False
        if self.stopping:
            return False
        measured = self._measure_queue(targets, applied, busy=self._busy) > 0
        self._speed_any &= set(self.speed_queue)
        if not self.speed_queue:
            self.speed_total = self.speed_done = 0
        return measured

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
            if info.role == "spare" and probe_tag in self._speed_any:
                self._ping_spare(info, password)
            background = 0.0
            span = max(elapsed, result.seconds)
            if before is not None and result.mbps is not None and span > 0:
                after = self._traffic_now(info.tag)
                if after is not None and after >= before:
                    # Трафик клиентов через этот же сервер за время замера (ТЗ R5.3).
                    extra = max(0, after - before - result.bytes_read)
                    background = round(extra * 8 / span / speedguard.MB, 3)
            total = result.mbps if result.mbps is None else round(result.mbps + background, 3)
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
            self._speed_ran = True
            if result.mbps is None:
                self.log.info("замер скорости %s не удался: %s", info.tag, result.error)
            else:
                self.log.info(
                    "замер скорости %s: %s, %d байт за %.1f с", info.tag,
                    speed.mbps_text(result.mbps), result.bytes_read, result.seconds,
                )
        return count

    def _ping_spare(self, info: NodeInfo, password: str) -> None:
        """Кнопка замера у запасного: заодно его проверка. Задержку участника панель берёт у
        проб ядра, а запасного ядро не пробует — его задержка в панели по этой проверке
        (status.py), и без неё после замера в строке была только скорость."""
        result = self._probe_scan(info, password)
        if result.kind == "cancelled":
            return
        self._note_rtt(info, result)
        self.store.save_scan(
            info.probe_tag, result.verdict, result.bytes_read, result.seconds, result.error,
            ts=self.wall(),
        )
        self.log.info(
            "скан %s: %s, %d байт за %.1f с", info.tag, result.verdict, result.bytes_read,
            result.seconds,
        )

    def _speed(self, info: NodeInfo, password: str, *, small: bool = False) -> speed.SpeedResult:
        """Замер сервера; small — короткий (не больше speed.spare_mb): повторные замеры
        подозрительного участника и замеры кандидатов на его место (ТЗ R6)."""
        price = self._prices().get(info.fingerprint, 1.0)
        size = speed.size_mb(self.cfg, price, spare=small or info.role == "spare")
        result = speed.measure(
            info, self.cfg, probe_pass=password, max_mb=size, cancel=self._stop,
        )
        self.store.record_scan_body(info.tag, result.bytes_read, "daemon",
                                    self.cfg.filters.multiplier_regex, self.wall(), purpose="speed")
        return result

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
        OK — из общего пула всех подписок (issue #2), не x100, не из подписки с исчерпанной
        квотой, не «нестабильные по ТСПУ», не выходящие в домашнюю страну. Сначала — лучшие по
        рейтингу; не больше speed.candidates."""
        if self.inventory is None:
            return []
        prices = self._prices()
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
                or self.main_cooldown.get(key, 0.0) > wall
                or key in self.guard.throttled
            ):
                continue
            if info.role == "proxy":
                if role == "member" or not (observatory.get(info.tag) or {}).get("alive"):
                    continue
            elif (scans.get(info.probe_tag) or {}).get("verdict") != "OK":
                continue
            found.append((info, self._score(info, observatory)))
        found.sort(key=lambda item: (-item[1], item[0].role != "proxy"))
        return [info for info, _score in found[: self.cfg.speed.candidates]]

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
            <= self._scan_minutes * 60.0
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
        if info.get("capture_failed"):
            protected = info.get("guard_recovery") in ("restored", "present")
            return (Lifecycle.BLOCKED if protected else Lifecycle.OPEN), info["failure_reason"]
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
        if self.cfg.zapret2.mode == "standalone":
            return (Lifecycle.CONNECTED,
                    "Прямой интернет без VPN; состояние zapret2 показано отдельно")
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
        self, view: list[NodeInfo], observatory: dict | None, xray_ok: bool, *, checkpoint=False,
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
            whitelist={"since": self.whitelist_since, "offer": self._whitelist_offer(view)}
            if self.whitelist_since is not None else None,
            free_pool=self._pool_summary(),
        )
        snapshot["watchdog"] = {
            "health_observed": self._health_observed,
            "phase": "checks" if checkpoint else "complete",
        }
        snapshot["scan_pacing"] = self._pacing()  # PR-4: паузы плановых проб (п. 330)
        snapshot["selection"] = self._selection_status(view)  # разные пути запаса (п. 341)
        snapshot["media"] = self._media_status()  # выход для видео YouTube (п. 348, 353)
        snapshot["zapret2"] = {
            **self._zapret2.view, "config_key": zapret2.config_key(self.cfg),
            "without_vpn": xray_ok and not self.paths.api_dirty_file.exists()
            and zapret2.standalone(engine.read_json(self.paths.xray_config_file)),
        }
        self._subscription_status(snapshot)  # время успеха и причина кэша подписок (п. 342)
        job = self._build
        snapshot["assembly"] = {
            "state": ("queued" if job.discard else "ready" if job.done.is_set() else "building")
            if job is not None else "queued" if self._build_next is not None else "idle",
            "elapsed_s": round(time.monotonic() - job.began, 1) if job else 0,
            "builds": self._build_count, "discarded": self._build_discarded,
            "build_s": round(self._build_last[0], 3),
            "apply_s": round(self._build_last[1], 3),
            "outcome": self._build_outcome,
        }
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
