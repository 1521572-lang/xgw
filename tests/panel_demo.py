"""Панель XGW на выдуманных данных — чтобы посмотреть на неё без шлюза и без root.

    python tests/panel_demo.py [--port 8791] [--scene work|empty|trouble|hostile|probe|
                                                      budget|waiting|reserve|tailscale|stranded|
                                                      cores|tspu]
                               [--app-port 8792] [--phone-server ХОСТ:ПОРТ:UUID]

Сеть не трогается: «включение VPN» меняет только состояние в памяти. Подписки,
ссылки и список серверов меняются по-настоящему — в panel.json во временном
каталоге. Сцена hostile подставляет имена сервера и устройства с HTML: в
браузере они должны остаться текстом. Сцена probe — не отвечает
сам адрес проверки (probe.url), budget — проверки расходуют больше суточного лимита,
waiting — VPN включён, но Xray ещё не перезапущен с новыми настройками, reserve —
безлимитные серверы не отвечают, и трафик несёт резервный лимитированный (x1),
cores — на GitHub есть новые Xray и sing-box (карточка «Ядра»: «Обновить» и «Вернуть …» идут
по этапам за несколько секунд, обновление sing-box «не проходит проверку»),
tailscale — шлюз ещё не в tailnet (вход через 12 секунд после нажатия), провайдер выдаёт
адрес CGNAT (К5), включён Override local DNS (К6), HTTPS в tailnet разрешается через
10 секунд, Funnel — тоже через 10 секунд. В остальных сценах Tailscale работает, в empty —
не установлен. «Привязать телефон»: через 10 секунд после QR-кода «телефон» привязывается сам.
Сцена stranded — мёртвого участника заменить некем, а «высокий» стоит у лимитированных x10,
хотя безлимитные живы (пояснения под «Серверами», ASSUMPTIONS п. 235).
Сцена tspu (0.1.18) — выученный обход у Германии («xray+split после STALL_BEFORE_BODY»),
Латвия «нестабильна по ТСПУ», скорость основного «из трафика», идёт поиск замены придушенному
серверу, один проверочный хост на паузе, один резолвер bootstrap-DNS не отвечает, Tailscale
временно через VPN. Иконка ↻ у скорости — замер одного сервера (5 секунд) — во всех сценах.

--app-port — для приложения XGW на эмуляторе Android (сборка debug): API приложения открыт на
0.0.0.0:ПОРТ без TLS, имя шлюза в Host подставляется, как это делает Funnel. «Телефон» сам
не привязывается: на каждый новый код печатается ссылка для эмулятора
xgw://pair?u=http://10.0.2.2:ПОРТ&c=КОД (adb shell am start -a android.intent.action.VIEW -d …).

--phone-server — для VPN приложения на эмуляторе (А3): «применённый конфиг шлюза» — эталонный
(tests/fixtures/golden/full_config.json) с одним сервером VLESS без TLS на ХОСТ:ПОРТ (для
эмулятора — 10.0.2.2), и /api/phone-config собирает из него конфиг телефона настоящим кодом
(generator/phone.py).
"""

from __future__ import annotations

import argparse
import http.client
import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_tailscale import FakeTailscale

from xgw import actions, config, cores, cost, engine, tailscale
from xgw.daemon import stranded_action, stranded_note
from xgw.net import dnsmasq, lan
from xgw.paths import Paths, atomic_write_json
from xgw.store import Store, SubscriptionCache
from xgw.watch import status
from xgw.watch.panel import Panel

TOKEN = "demo"
CONFIG = """
[network]
lan_if = "enp4s0"
bypass_hosts = ["192.168.50.23"]

[[subscriptions]]
name = "main"
url = "https://sub.example.com/api/sub/FAKE-TOKEN"

[panel]
port = {port}
"""
MANAGED = {
    "subscriptions": [
        {"name": "запасная", "url": "http://backup.example.net/s/FAKE", "user_agent": "",
         "refresh_minutes": 60},
    ],
    "links": ["trojan://fake-password@203.0.113.20:443?sni=t.example.com#Trojan-1"],
    "disabled": ["0d15ab1e"],
    "removed": ["0de1e7ed"],
}
# Отпечаток, тег, имя, подписка, роль.
SERVERS = [
    ("a1a1a1a1", "proxy-nl-a1a1", "🇳🇱 Нидерланды · Амстердам 1", "main", "member"),
    ("b2b2b2b2", "proxy-de-b2b2", "🇩🇪 Германия · Франкфурт", "main", "member"),
    ("c3c3c3c3", "proxy-fi-c3c3", "🇫🇮 Финляндия · Хельсинки", "запасная", "member"),
    ("d4d4d4d4", "proxy-se-d4d4", "🇸🇪 x100 Швеция · Стокгольм", "main", "member"),
    ("e5e5e5e5", "proxy-xx-e5e5", "Trojan-1", "manual", "member"),
    ("f6f6f6f6", "spare-pl-f6f6", "🇵🇱 Польша · Варшава", "main", "spare"),
    ("a7a7a7a7", "spare-lv-a7a7", "🇱🇻 Латвия · Рига", "main", "spare"),
    ("b8b8b8b8", "spare-tr-b8b8", "🇹🇷 Турция · Стамбул", "запасная", "spare"),
    ("c9c9c9c9", "spare-us-c9c9", "🇺🇸 США · Нью-Йорк", "запасная", "spare"),
    ("0d15ab1e", "", "🇰🇿 Казахстан · Алматы", "main", ""),
    ("0de1e7ed", "", "🇮🇳 Индия · Мумбаи", "main", ""),
    ("0f117e4d", "", "Осталось 35.5 ГБ трафика", "main", "filter"),
    ("0d05dead", "", "🇸🇬 Сингапур · sg.gone.example.net", "main", "dns"),
]
LIVE = {
    "a1a1a1a1": {"alive": True, "delay_ms": 84},
    "b2b2b2b2": {"alive": True, "delay_ms": 131},
    "c3c3c3c3": {"alive": True, "delay_ms": 412},
    "d4d4d4d4": {"alive": False, "delay_ms": None, "dead": 540},
    "e5e5e5e5": {"alive": None, "delay_ms": None},
    "f6f6f6f6": {"verdict": "OK", "seconds": 0.8},
    "a7a7a7a7": {"verdict": "SLOW", "seconds": 4.1},
    "b8b8b8b8": {"verdict": "FROZEN", "seconds": 5.0},
    "c9c9c9c9": {"verdict": None, "seconds": None},
}


# Основной сервер (0.1.9) и замеры скорости: у Финляндии замер не удался.
MAIN_FP = "a1a1a1a1"
# Запасной, которому шлюз включил дробление ClientHello (0.1.11): метка «дробление».
FRAGMENT_FP = "f6f6f6f6"
SPEEDS = {
    "a1a1a1a1": {"mbps": 87.3, "error": ""},
    "b2b2b2b2": {"mbps": 41.0, "error": ""},
    "c3c3c3c3": {"mbps": None, "error": "тишина 5 с после 1 048 576 байт тела"},
    # Запасной, который раньше был в работе: замер сохранился.
    "f6f6f6f6": {"mbps": 63.4, "error": ""},
}

# Профиль обхода и протокол сервера (0.1.12): ядро, которое ведёт сервер. Остальные — Xray.
PROFILES = {
    "b2b2b2b2": ("singbox:default", "vless"),       # закреплён за sing-box
    "d4d4d4d4": ("singbox:default", "hysteria2"),   # только sing-box
    "f6f6f6f6": ("xray:fragment", "vless"),
    "a7a7a7a7": ("singbox:tls_fragment", "trojan"),  # шлюз перевёл сам при блокировке
    "b8b8b8b8": ("singbox:mux_padded", "vmess"),
}
# Что умеет сервер: оба ядра («dual») по умолчанию.
CAPABILITY = {"d4d4d4d4": "singbox", "c3c3c3c3": "xray", "a7a7a7a7": "dual"}
HOSTILE = {"d4d4d4d4": "<img src=x onerror=alert(1)> Стокгольм"}
# Сцена reserve: «запасная» и ручная ссылка — безлимитные (лимита они не сообщают), «main»
# — с лимитом, у её серверов множители в имени; резервный выход — x1.
RESERVE_FP = "f6f6f6f6"
RESERVE_SERVERS = [
    ("c3c3c3c3", "proxy-fi-c3c3", "🇫🇮 Финляндия · Хельсинки", "запасная", "member"),
    ("e5e5e5e5", "proxy-xx-e5e5", "Trojan-1", "manual", "member"),
    ("f6f6f6f6", "spare-pl-f6f6", "🇵🇱 x1 Польша · Варшава", "main", "spare"),
    ("a1a1a1a1", "spare-nl-a1a1", "🇳🇱 x10📶🛜 Нидерланды 🚀🚀 | AI", "main", "spare"),
    ("b2b2b2b2", "spare-de-b2b2", "x10 🛜 Германия 🚀🚀 АВТО", "main", "spare"),
    ("d4d4d4d4", "spare-se-d4d4", "🇸🇪 x100 Швеция · обход белых списков", "main", "spare"),
    ("0f117e4d", "", "Осталось 35.5 ГБ трафика", "main", "filter"),
]
RESERVE_LIVE = {
    "c3c3c3c3": {"alive": False, "delay_ms": None, "dead": 420},
    "e5e5e5e5": {"alive": False, "delay_ms": None, "dead": 420},
    "f6f6f6f6": {"verdict": "OK", "seconds": 0.3},
    "a1a1a1a1": {"verdict": "OK", "seconds": 0.4},
    "b2b2b2b2": {"verdict": None, "seconds": None},
    "d4d4d4d4": {"verdict": None, "seconds": None},
}


# Версии ядер «на шлюзе»: их меняют кнопки карточки «Ядра» (DemoPanel._core_demo).
VERSIONS = {"xray": "26.3.27", "sing-box": "1.14.3"}


def _servers(scene: str) -> list[tuple]:
    if scene == "reserve":
        return RESERVE_SERVERS
    if scene != "hostile":
        return SERVERS
    return [(key, tag, HOSTILE.get(key, name), source, role)
            for key, tag, name, source, role in SERVERS]


def _tspu_fields(scene: str, fingerprint: str, now: float) -> dict:
    """Сцена tspu: выученный обход, «нестабилен по ТСПУ», скорость из трафика и сумма замера
    (сам замер + трафик клиентов) — поля, которые 0.1.18 добавила в строку сервера."""
    if scene != "tspu":
        return {}
    fields: dict = {}
    if fingerprint == MAIN_FP:
        fields.update(speed_passive_mbps=54.2, speed_passive_ts=now - 120,
                      speed_test_mbps=61.0, speed_bg_mbps=26.3)
    if fingerprint == "b2b2b2b2":
        fields.update(profile="xray:split", core="xray", escalation={
            "profile": "xray:split", "label": "xray+split", "verdict": "STALL_BEFORE_BODY",
            "ts": now - 3 * 3600})
    if fingerprint == "a7a7a7a7":
        fields["unstable_until"] = now + 4 * 3600
    return fields


def snapshot(scene: str, now: float, excluded: set[str]) -> dict:
    members, spares = [], []
    for fingerprint, tag, name, source, role in _servers(scene):
        if fingerprint in excluded or role not in ("member", "spare"):
            continue  # демон убрал бы отключённый сервер из ядра
        live = (RESERVE_LIVE if scene == "reserve" else LIVE)[fingerprint]
        profile, protocol = PROFILES.get(fingerprint, ("xray:default", "vless"))
        base = {
            "tag": tag, "fingerprint": fingerprint, "name": name, "source": source,
            "profile": profile, "core": "sing-box" if profile.startswith("singbox") else "xray",
            "protocol": protocol,
        }
        if role == "member":
            measure = SPEEDS.get(fingerprint) if scene != "reserve" else None
            members.append({
                **base, **_tspu_fields(scene, fingerprint, now),
                "alive": live["alive"], "delay_ms": live["delay_ms"],
                "dead_since": now - live["dead"] if live.get("dead") else None,
                "main": scene not in ("reserve", "trouble") and fingerprint == MAIN_FP,
                "speed_mbps": measure["mbps"] if measure else None,
                "speed_error": measure["error"] if measure else "",
                "speed_ts": now - 2 * 3600 if measure else None,
                # Почему цифры нет — как status.speed_note.
                "speed_note": "" if measure and measure["mbps"] is not None else (
                    f"замер не удался: {measure['error']}" if measure
                    else "скорость не замеряется: сервер не отвечает" if not live["alive"]
                    else "в очереди замера"),
            })
        else:
            verdict = live["verdict"]
            measure = SPEEDS.get(fingerprint) if scene != "reserve" else None
            spares.append({
                **base, **_tspu_fields(scene, fingerprint, now),
                "verdict": verdict, "seconds": live["seconds"],
                "bytes": 65536 if verdict in ("OK", "SLOW") else 16384,
                "scanned": now - 1500 if verdict else None,
                "reserve": scene == "reserve" and fingerprint == RESERVE_FP,
                "fragment": fingerprint == FRAGMENT_FP,
                "speed_mbps": measure["mbps"] if measure else None,
                "speed_ts": now - 40 * 60 if measure else None,
                "speed_note": "" if measure else (
                    "в очереди замера" if verdict in ("OK", "SLOW")
                    else "скорость не замеряется: запасной ещё не проверен" if verdict is None
                    else "скорость не замеряется: запасной не прошёл последнюю проверку"),
            })
    state, action = "DEGRADED", "часть серверов недоступна — замена на запасные"
    if scene == "empty":
        members, spares, state, action = [], [], "HEALTHY", "вмешательство не требуется"
    elif scene == "trouble":
        state = "XRAY_DOWN"
        action = "Xray не отвечает — перезапуск службы, после двух неудач откат на last-good"
    reserve = None
    if scene == "reserve":
        state = "RESERVE"
        action = ("серверы в работе не отвечают — трафик идёт через резервный сервер "
                  "«🇵🇱 x1 Польша · Варшава» (x1); Xray вернётся к ним сам, как только они "
                  "ответят; поиск замены среди запасных")
        reserve = {"tag": "spare-pl-f6f6", "name": "🇵🇱 x1 Польша · Варшава", "source": "main",
                   "multiplier": 1.0, "cost": 1.0}
    probe_target = ""
    if scene == "probe":
        state = "PROBE_TARGET_UNREACHABLE"
        action = ("пробы всех серверов падают — вероятно, недоступен сам probe.url; "
                  "замена серверов приостановлена, ядро пробует серверы по запасному адресу")
        probe_target = ("Внимание: пробы всех серверов падают — вероятно, недоступен сам "
                        "probe.url (HTTP 403; напрямую, мимо VPN, ответ тот же — HTTP 403)")
    quotas = {} if scene == "empty" else {
        "main": {"upload": 3_100_000_000, "download": 61_400_000_000,
                 "total": 100_000_000_000, "expire": int(now) + 86400 * 23},
    }
    chosen = next((member for member in members if member.get("main")), None)
    probe_cfg = config.Config()
    if scene == "budget":
        probe_cfg.probe.interval = "10s"  # пробы втрое чаще — заведомо больше лимита
    stranded = class_note = ""
    if scene == "stranded":
        # Как на шлюзе 24.10.2026: четыре сервера «высокий» x10 в работе, один мёртв, живые
        # безлимитные — «средние», сервер выбран вручную. Тексты — из кода шлюза.
        tier = cost.Klass(0, 10.0)
        action = stranded_action(tier, True)
        stranded = stranded_note(["🇹🇷 x10 Турция"], tier, True)
        unlimited = {"priority": "medium", "cost": 0.0, "verdict": "OK", "scanned": now}
        class_note = status.class_warning(
            probe_cfg, [{"priority": "high", "cost": 10.0}], [unlimited] * 34,
            {"tag": "proxy-pl-0000"}, now,
        )
    budget = status.probe_budget(
        probe_cfg, len(members), len(spares),
        speed_mb=status.speed_daily_mb(probe_cfg, members, spares),
    )
    return {
        "updated": now, "daemon": True, "state": state, "action": action, "since": now - 900,
        "xray": {"ok": scene != "trouble", "version": VERSIONS["xray"]},
        # Жизненный цикл перехвата пишет демон (daemon.Lifecycle); панель — строкой под кнопкой.
        "capture": {
            "loaded": True,
            "lifecycle": {"trouble": "blocked", "waiting": "blocked"}.get(scene, "connected"),
            "lifecycle_reason": {
                "trouble": "Xray не отвечает",
                "waiting": "в применённом конфиге Xray нет inbound tun-in для интерфейса xgwtun0",
            }.get(scene, ""),
        },
        "members": members, "spares": spares, "selecting": [], "pin": None,
        "reserve": reserve,
        "sticky": True,
        "main": {
            "tag": chosen["tag"], "name": chosen["name"], "mbps": chosen["speed_mbps"],
            "since": now - 5 * 3600, "basis": "speed",
        } if chosen else None,
        "quota": quotas,
        "sub_errors": {} if scene == "empty" else {
            "запасная": {"error": "HTTP 403 от сервера подписки", "ts": now - 300},
        },
        "budget": status.budget_summary(probe_cfg, budget, quotas, len(members), len(spares)),
        "nodes": {} if scene == "empty" else {
            "members": len(members), "spares": len(spares), "dropped": 2, "duplicates": 12,
            "excluded": len(excluded), "dns": 1,
        },
        "probe_target": probe_target,
        "stranded": stranded, "class_warning": class_note,
        **_tspu_status(scene, now),
        "pending_restart": False, "events": [],
        "singbox": {"mode": "auto", "installed": True, "version": VERSIONS["sing-box"],
                    "expected": True,
                    "alive": True, "failed": False,
                    "bridged": sum(
                        1 for item in (*members, *spares) if item["core"] == "sing-box")},
        "singbox_pending": False,
    }


def _tspu_status(scene: str, now: float) -> dict:
    """Сцена tspu: проверочные хосты (R3), bootstrap-DNS (R4a), Tailscale через VPN (R4b) и
    поиск замены придушенному серверу (R6)."""
    if scene != "tspu":
        return {}
    hosts = [
        {"host": "cdn.jsdelivr.net", "url": "https://cdn.jsdelivr.net/a.woff", "ok": 812,
         "errors": 0},
        {"host": "code.jquery.com", "url": "https://code.jquery.com/b.js", "ok": 40,
         "errors": 3, "paused_until": now + 22 * 60, "last_error": "STALL_BEFORE_BODY"},
        {"host": "ajax.aspnetcdn.com", "url": "https://ajax.aspnetcdn.com/c.ttf", "ok": 77,
         "errors": 0},
    ]
    resolvers = [
        {"entry": "https://1.1.1.1", "ok": True, "ms": 41, "error": ""},
        {"entry": "https://8.8.8.8", "ok": True, "ms": 41, "error": ""},
        {"entry": "https://9.9.9.9:5053", "ok": False, "ms": 5000, "error": "тайм-аут"},
    ]
    return {
        "probe_hosts": {"current": hosts[0]["url"], "hosts": hosts},
        "resolvers": {"ts": now - 600, "results": resolvers},
        "tailscale_via_vpn": True,
        "guard": {"on": True, "throttled": ["c3c3c3c3"], "suspects": [],
                  "episode": {"name": "🇫🇮 Финляндия · Хельсинки", "role": "member",
                              "mbps": 6.4, "tried": 2, "total": 5},
                  "cooldown_until": None, "spent_mb": 34.0, "daily_mb": 300},
    }


class DemoCapture:
    """Перехват, который помнит только «включён или нет»."""

    mode_now = "on"
    inbound_missing = ""  # сцена waiting: Xray ещё без inbound'а перехвата

    def __init__(self, cfg, paths, **_kwargs) -> None:
        self.cfg = cfg
        self.lan_if = cfg.network.lan_if
        self.capturing = self.configured = True

    def up(self) -> str:  # правила в демо не загружаются
        return DemoCapture.mode_now

    def describe(self, *, check: bool = True) -> dict:
        return {"mode": DemoCapture.mode_now, "lan_if": self.lan_if, "lan": True, "local": True,
                "bypass": lan.bypass_addresses(self.cfg)[0], "fail_mode": "closed",
                "loaded": None,
                "inbound_missing": DemoCapture.inbound_missing
                if DemoCapture.mode_now == "on" else "",
                # capture.hold = "block" (по умолчанию): пока ждём inbound, трафик закрыт.
                "blocked": bool(DemoCapture.inbound_missing) and DemoCapture.mode_now == "on"}


class DemoDaemon:
    def __init__(self) -> None:
        self.poke = threading.Event()
        self._until = {"refresh": 0.0, "scan": 0.0, "speed": 0.0}
        self._one: dict[str, float] = {}

    def request_refresh(self) -> None:
        self._until["refresh"] = time.time() + 4

    def request_scan(self) -> None:
        self._until["scan"] = time.time() + 6

    def request_speed(self) -> None:
        self._until["speed"] = time.time() + 8

    def request_core_check(self) -> None:
        self._until["cores"] = time.time() + 3

    def request_speed_one(self, key: str) -> None:
        self._one[key] = time.time() + 5  # «замер» одного сервера идёт 5 с

    def speed_one_pending(self) -> list[str]:
        return sorted(key for key, until in self._one.items() if time.time() < until)

    refresh_pending = property(lambda self: time.time() < self._until["refresh"])
    scan_pending = property(lambda self: time.time() < self._until["scan"])
    speed_pending = property(lambda self: time.time() < self._until["speed"])
    cores_pending = property(lambda self: time.time() < self._until.get("cores", 0.0))


class DemoPanel(Panel):
    demo_phone = True  # «телефон» привязывается сам; с --app-port — настоящее приложение

    def _selected(self, xray_ok: bool, now: float) -> list[str]:
        return ["proxy-nl-a1a1"] if xray_ok else []

    def _act(self, name: str, body: dict) -> actions.Outcome:
        if name == "power":
            DemoCapture.mode_now = "on" if body.get("on") else "off"
            text = ("перехват включён: сеть enp4s0 и эта машина — через Xray" if body.get("on")
                    else "перехват снят: трафик идёт напрямую, мимо VPN")
            with actions.open_store(self.paths) as store:
                store.add_event("capture", text)
            return actions.Outcome(0, text)
        if name in ("pin", "unpin"):
            # Как actions.pin: панель выбирает бессрочно (pin.py), имя — из списка серверов.
            pin = None
            if name == "pin":
                with actions.open_store(self.paths) as store:
                    names = {row["tag"]: row["name"] for row in store.all_nodes()}
                pin = {"tag": body["tag"], "name": names.get(body["tag"], body["tag"]),
                       "until": None, "since": time.time(), "down": None}
            with actions.open_store(self.paths) as store:
                store.set_meta("pin", json.dumps(pin, ensure_ascii=False) if pin else "")
            return actions.Outcome(
                0, f"«{pin['name']}» выбран вручную: весь трафик идёт через него, пока не "
                "вернёте автовыбор" if pin else "автовыбор: ручной выбор сервера снят"
            )
        if name in ("tailscale/login", "tailscale/serve", "tailscale/funnel", "phones/pair"):
            # Как человек по ту сторону ссылки: входит, разрешает HTTPS и Funnel в консоли
            # tailnet, наводит камеру телефона на QR-код.
            fake = self.runner
            later = {"tailscale/login": fake.complete_login, "tailscale/serve": fake.enable_https,
                     "tailscale/funnel": fake.allow_funnel, "phones/pair": fake.allow_funnel}[name]
            threading.Timer(12 if name == "tailscale/login" else 10, later).start()
        if name in ("cores/update", "cores/rollback"):
            return self._core_demo(name.removeprefix("cores/"), body)
        outcome = super()._act(name, body)
        if name == "phones/pair" and outcome.ok and self.demo_phone:
            threading.Timer(20, self._demo_phone).start()
        return outcome

    def _core_demo(self, action: str, body: dict) -> actions.Outcome:
        """Как служба xgw-core, но за секунды: этапы в cores.json, затем итог и событие. Обновление
        sing-box «не проходит» сквозную проверку — видно, как шлюз возвращает прежний."""
        core = body.get("core")
        if core not in cores.CORES:
            return actions.Outcome(2, "ожидается ядро: xray или sing-box")
        title, paths = cores.TITLES[core], self.paths
        old = VERSIONS[core]
        target = body.get("version") if action == "update" else cores.previous(paths, core)
        if not target:
            return actions.Outcome(2, f"прежней версии {title} нет — возвращаться не к чему")

        def stage(step: str, **job) -> None:
            state = cores.load_state(paths)
            state["job"] = {**(state.get("job") or {}), "stage": step, **job}
            cores.save_state(paths, state)

        def run() -> None:
            now = time.time()
            stage("", core=core, action=action, version=target, state="running", started=now,
                  text="", finished=None)
            steps = [f"скачиваю {title} {target} с GitHub", f"проверяю {title} {target} на рабочем "
                     "конфиге", f"ставлю {title} {target} и перезапускаю",
                     f"проверяю запрос через серверы с {title} {target}"]
            if action == "rollback":
                steps = [f"проверяю прежний {title} {target} на рабочем конфиге",
                         f"возвращаю {title} {target}"]
            for text in steps:
                stage(text)
                time.sleep(2)
            state = cores.load_state(paths)
            if action == "update" and core == "sing-box":
                reason = "ни один из серверов, что отвечали через прежнюю версию, не отвечает 45 с"
                state[core] = {**(state.get(core) or {}),
                               "rejected": {"version": target, "reason": reason,
                                            "at": time.time(), "kind": "check"}}
                text, result = (f"{title} {target} не прошёл проверку: {reason} — возвращён "
                                f"прежний {old}", "failed")
            elif action == "update":
                VERSIONS[core] = target
                prev = cores.prev_dir(paths, core)
                prev.mkdir(parents=True, exist_ok=True)
                (prev / cores.core_bin(paths, core).name).write_text(old, encoding="utf-8")
                state[core] = {"accepted": target, "previous": old, "updated": time.time(),
                               "watch_until": time.time() + cores.WATCH_SECONDS, "rejected": None}
                text = (f"{title} обновлён: {old} → {target}, проверки пройдены. Сутки шлюз "
                        f"следит за ним и вернёт {old} сам, если ядро перестанет отвечать. "
                        f"Вернуть {old} — кнопка «Вернуть {old}» в панели")
                result = "ok"
            else:
                VERSIONS[core] = target
                cores.forget(paths, core)
                state = cores.load_state(paths)
                state[core] = {"accepted": target, "previous": "", "watch_until": 0,
                               "rejected": {"version": old, "reason": "возвращена прежняя версия",
                                            "kind": "rollback",
                                            "at": time.time()}}
                text, result = f"{title} {old} убран, возвращён прежний {target}", "ok"
            state["job"] = {**state["job"], "state": result, "stage": "", "text": text,
                            "finished": time.time()}
            cores.save_state(paths, state)
            with actions.open_store(paths) as store:
                store.add_event("cores", text)

        threading.Thread(target=run, daemon=True).start()
        if action == "update":
            return actions.Outcome(0, f"Обновляю {title} до {target}: скачиваю и проверяю — итог "
                                      "появится в карточке «Ядра» и в событиях")
        return actions.Outcome(0, f"Возвращаю {title} {target}…")

    def _demo_phone(self) -> None:
        code = self.phones.pairing()["code"]
        if code:
            self.phones.pair(code, "Galaxy S25 Ultra")


def app_forwarder(panel: DemoPanel, port: int) -> ThreadingHTTPServer:
    """Как Funnel: снаружи (эмулятор, 10.0.2.2) — на API приложения, Host — имя шлюза."""

    class Forward(BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            pass

        def _forward(self) -> None:
            length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(length) if length else b""
            headers = {name: value for name, value in self.headers.items()
                       if name.lower() not in ("host", "connection")}
            headers["Host"] = panel.cfg.managed.tailscale_funnel or "funnel-off"
            upstream = http.client.HTTPConnection("127.0.0.1", panel.app_api.port, timeout=20)
            try:
                upstream.request(self.command, self.path, body=body or None, headers=headers)
                response = upstream.getresponse()
                data = response.read()
            finally:
                upstream.close()
            self.send_response_only(response.status)
            for name, value in response.getheaders():
                if name.lower() not in ("connection", "transfer-encoding", "server"):
                    self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = _forward

    server = ThreadingHTTPServer(("0.0.0.0", port), Forward)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def links() -> None:
        shown = ""
        while True:
            code = panel.phones.pairing()["code"] or ""
            if code and code != shown and panel.cfg.managed.tailscale_funnel:
                print(f"Приложение (эмулятор): xgw://pair?u=http://10.0.2.2:{port}&c={code}",
                      flush=True)
                shown = code
            time.sleep(1)

    threading.Thread(target=links, daemon=True).start()
    return server


def build(root: Path, port: int, scene: str) -> DemoPanel:
    paths = Paths(root=root)
    paths.ensure()
    config_path = paths.config_file
    lines = CONFIG.format(port=port)
    if scene == "empty":
        lines = f'[network]\nlan_if = "enp4s0"\n[panel]\nport = {port}\n'
    config_path.write_text(lines, encoding="utf-8")
    now = time.time()
    if scene != "empty":
        atomic_write_json(config_path.with_name("panel.json"), MANAGED, mode=0o600)
        SubscriptionCache(paths.cache_dir).save("main", b"demo")
        atomic_write_json(engine.inventory_file(paths), {"saved": now, "servers": [
            {"fingerprint": fingerprint, "name": name, "source": source,
             "protocol": PROFILES.get(fingerprint, ("", "vless"))[1],
             "core": CAPABILITY.get(fingerprint, "dual"),
             "skip": role if role in ("filter", "dns") else ""}
            for fingerprint, _tag, name, source, role in _servers(scene)
        ]})
        device = "<script>alert(1)</script>" if scene == "hostile" else "smart-tv"
        leases = dnsmasq.leases_path(paths)
        leases.parent.mkdir(parents=True, exist_ok=True)
        leases.write_text(
            f"{int(now) + 30000} aa:bb:cc:00:11:22 192.168.50.101 pixel-8 *\n"
            f"{int(now) + 20000} aa:bb:cc:00:11:23 192.168.50.23 {device} *\n"
            f"{int(now) + 10000} aa:bb:cc:00:11:24 192.168.50.140 * *\n",
            encoding="utf-8",
        )
    store = Store(paths.db_file)
    if scene != "empty":
        store.add_event("apply", "обновление подписки: применено через API без перезапуска: "
                                 "ado: spare-us-c9c9")
        store.add_event("DEGRADED", "HEALTHY → DEGRADED: часть серверов недоступна — замена "
                                    "на запасные")
        store.add_event("rotation", "замена участников: proxy-tr-0000 → «🇫🇮 Финляндия · Хельсинки»")
    store.add_event("capture", "перехват включён: сеть enp4s0 и эта машина — через Xray")
    store.close()
    if scene == "cores":
        VERSIONS["xray"] = "26.10.21"
        atomic_write_json(paths.cores_check_file, {
            "at": now - 2 * 3600, "error": "",
            "xray": {"installed": "26.10.21", "withdrawn": False, "error": "", "latest": {
                "version": "26.10.30", "prerelease": True, "published": "2026-10-23T09:12:00Z"}},
            "sing-box": {"installed": "1.14.3", "withdrawn": False, "error": "", "latest": {
                "version": "1.14.4", "prerelease": False, "published": "2026-10-22T18:40:00Z"}},
        }, mode=0o644)

    def keep_fresh() -> None:  # как демон: статус переписывается на каждом шаге
        while True:
            cfg, _warnings = config.load(config_path)
            excluded = {*cfg.managed.disabled, *cfg.managed.removed}
            atomic_write_json(
                paths.status_file, snapshot(scene, time.time(), excluded), mode=0o644
            )
            time.sleep(2)

    threading.Thread(target=keep_fresh, daemon=True).start()
    if scene == "empty":
        DemoCapture.mode_now = "off"
    if scene == "waiting":
        DemoCapture.inbound_missing = (
            "в применённом конфиге Xray нет inbound tun-in для интерфейса xgwtun0")
    fake = FakeTailscale(backend="NeedsLogin" if scene == "tailscale" else "Running")
    fake.peers = [  # «Устройства tailnet» в карточке (выходной узел)
        {"HostName": "galaxy-s25-ultra", "TailscaleIPs": ["100.101.2.3"], "OS": "android",
         "Online": True},
        {"HostName": "laptop", "TailscaleIPs": ["100.101.2.9"], "OS": "windows", "Online": False},
    ]
    if scene == "tailscale":
        fake.cgnat_wan = fake.override_dns = True
        fake.https_enabled = False
        fake.funnel_allowed = False
    socket = tailscale.socket_path(paths)
    socket.parent.mkdir(parents=True, exist_ok=True)
    socket.write_text("", encoding="ascii")
    cfg, _warnings = config.load(config_path)
    panel = DemoPanel(paths, config_path, TOKEN, port=port, root_problem=lambda: None,
                      capture_factory=DemoCapture, runner=fake,
                      which=lambda name: None if scene == "empty" else f"/usr/bin/{name}",
                      spawn=fake.spawn, sys_net=root / "sys-class-net", app_port=0)
    panel.ts_wait = 1.0
    panel.recorder.opener = DemoSniffer  # «Записать трафик»: кадры выдумывает демо
    panel.configure(cfg, DemoDaemon())
    return panel


class DemoSniffer:
    """Сокет записи трафика без root: кадр устройства раз в 0,05 с (watch/record.py)."""

    def __init__(self, _interface: str, mac: str) -> None:
        self.frame = bytes.fromhex(mac.replace(":", "")) + bytes(6) + b"\x08\x00" + bytes(200)

    def settimeout(self, _value) -> None:
        pass

    def recv_into(self, buffer, size, _flags) -> int:
        time.sleep(0.05)
        buffer[:len(self.frame)] = self.frame
        return len(self.frame)

    def close(self) -> None:
        pass


def phone_gateway(spec: str) -> dict:
    """Применённый конфиг «шлюза» с одним сервером VLESS ХОСТ:ПОРТ:UUID (--phone-server)."""
    host, port, uuid = spec.rsplit(":", 2)
    golden = Path(__file__).resolve().parent / "fixtures/golden/full_config.json"
    applied = json.loads(golden.read_text(encoding="utf-8"))
    members = [item for item in applied["outbounds"]
               if item["tag"].startswith(("proxy-", "spare-"))]
    keep = members[0]
    keep.update(protocol="vless", settings={"vnext": [{
        "address": host, "port": int(port), "users": [{"id": uuid, "encryption": "none"}],
    }]}, streamSettings={"network": "tcp", "sockopt": {"mark": 2}})
    applied["outbounds"] = [item for item in applied["outbounds"] if item not in members[1:]]
    applied["dns"].pop("hosts", None)
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument(
        "--scene", default="work",
        choices=("work", "empty", "trouble", "hostile", "probe", "budget", "waiting",
                 "reserve", "tailscale", "cores", "stranded", "tspu"))
    parser.add_argument("--app-port", type=int, default=0)
    parser.add_argument("--phone-server", default="")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="xgw-panel-demo-") as root:
        panel = build(Path(root), args.port, args.scene)
        panel.demo_phone = not args.app_port
        if args.phone_server:
            atomic_write_json(panel.paths.xray_config_file, phone_gateway(args.phone_server))
        panel.start()
        print(f"Панель: http://127.0.0.1:{panel.port}/?token={TOKEN}", flush=True)
        if args.app_port:
            app_forwarder(panel, args.app_port)
            print(f"API приложения для эмулятора: http://10.0.2.2:{args.app_port}", flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            panel.stop()


if __name__ == "__main__":
    main()
