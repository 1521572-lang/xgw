"""Панель XGW на выдуманных данных — чтобы посмотреть на неё без шлюза и без root.

    python tests/panel_demo.py [--port 8791] [--scene work|empty|trouble|hostile|probe|
                                                      budget|waiting|reserve]

Сеть не трогается: «включение VPN» меняет только состояние в памяти. Подписки,
ссылки и список серверов меняются по-настоящему — в panel.json во временном
каталоге. Сцена hostile подставляет имена сервера и устройства с HTML: в
браузере они должны остаться текстом. Сцена probe — не отвечает
сам адрес проверки (probe.url), budget — проверки расходуют больше суточного лимита,
waiting — VPN включён, но Xray ещё не перезапущен с новыми настройками, reserve —
безлимитные серверы не отвечают, и трафик несёт резервный лимитированный (x1).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from xgw import actions, config, engine
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
    ("d4d4d4d4", "proxy-se-d4d4", "🇸🇪 Швеция · Стокгольм", "main", "member"),
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
SPEEDS = {
    "a1a1a1a1": {"mbps": 87.3, "error": ""},
    "b2b2b2b2": {"mbps": 41.0, "error": ""},
    "c3c3c3c3": {"mbps": None, "error": "тишина 5 с после 1 048 576 байт тела"},
}

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


def _servers(scene: str) -> list[tuple]:
    if scene == "reserve":
        return RESERVE_SERVERS
    if scene != "hostile":
        return SERVERS
    return [(key, tag, HOSTILE.get(key, name), source, role)
            for key, tag, name, source, role in SERVERS]


def snapshot(scene: str, now: float, excluded: set[str]) -> dict:
    members, spares = [], []
    for fingerprint, tag, name, source, role in _servers(scene):
        if fingerprint in excluded or role not in ("member", "spare"):
            continue  # демон убрал бы отключённый сервер из ядра
        live = (RESERVE_LIVE if scene == "reserve" else LIVE)[fingerprint]
        base = {"tag": tag, "fingerprint": fingerprint, "name": name, "source": source}
        if role == "member":
            measure = SPEEDS.get(fingerprint) if scene != "reserve" else None
            members.append({
                **base, "alive": live["alive"], "delay_ms": live["delay_ms"],
                "dead_since": now - live["dead"] if live.get("dead") else None,
                "main": scene not in ("reserve", "trouble") and fingerprint == MAIN_FP,
                "speed_mbps": measure["mbps"] if measure else None,
                "speed_error": measure["error"] if measure else "",
                "speed_ts": now - 2 * 3600 if measure else None,
            })
        else:
            verdict = live["verdict"]
            spares.append({
                **base, "verdict": verdict, "seconds": live["seconds"],
                "bytes": 65536 if verdict in ("OK", "SLOW") else 16384,
                "scanned": now - 1500 if verdict else None,
                "reserve": scene == "reserve" and fingerprint == RESERVE_FP,
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
    measured = sum(1 for member in members if member["speed_mbps"] or member["speed_error"])
    budget = status.probe_budget(probe_cfg, len(members), len(spares), speed_members=measured)
    return {
        "updated": now, "daemon": True, "state": state, "action": action, "since": now - 900,
        "xray": {"ok": scene != "trouble", "version": "26.3.27"},
        "capture": {"loaded": True},
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
        "pending_restart": False, "events": [],
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
                if DemoCapture.mode_now == "on" else ""}


class DemoDaemon:
    def __init__(self) -> None:
        self.poke = threading.Event()
        self._until = {"refresh": 0.0, "scan": 0.0, "speed": 0.0}

    def request_refresh(self) -> None:
        self._until["refresh"] = time.time() + 4

    def request_scan(self) -> None:
        self._until["scan"] = time.time() + 6

    def request_speed(self) -> None:
        self._until["speed"] = time.time() + 8

    refresh_pending = property(lambda self: time.time() < self._until["refresh"])
    scan_pending = property(lambda self: time.time() < self._until["scan"])
    speed_pending = property(lambda self: time.time() < self._until["speed"])


class DemoBot:
    """Бот, который ничего не отправляет: токен → код → через 12 секунд «чат подключён»."""

    mark = None

    def __init__(self) -> None:
        self.mode, self.code, self.since = "off", "", 0.0

    def info(self) -> dict:
        if self.mode == "pairing" and time.time() - self.since > 12:
            self.mode, self.code = "connected", ""  # «пользователь отправил /start КОД»
        return {"mode": self.mode, "managed": True, "username": "xgw_demo_bot", "error": "",
                "code": self.code, "until": self.since + 900 if self.code else None,
                "commands": True}

    def new_code(self) -> str:
        self.mode, self.code, self.since = "pairing", "482915", time.time()
        return self.code

    def drop_code(self) -> None:
        self.mode, self.code = "off", ""

    def configure(self, *_args, **_kwargs) -> None:
        pass


class DemoPanel(Panel):
    def _telegram(self, step: str, body: dict, store_path) -> actions.Outcome:
        bot = self.bot
        if step == "connect":
            bot.new_code()
            return actions.Outcome(0, "Токен сохранён. Откройте бота в Telegram и отправьте код")
        if step == "code":
            bot.new_code()
            return actions.Outcome(0, "Новый код готов")
        bot.drop_code()
        return actions.Outcome(0, "Бот отключён")

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
        return super()._act(name, body)


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
            {"fingerprint": fingerprint, "name": name, "source": source, "protocol": "vless",
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
    cfg, _warnings = config.load(config_path)
    panel = DemoPanel(paths, config_path, TOKEN, port=port, root_problem=lambda: None,
                      capture_factory=DemoCapture, runner=lambda *_args, **_kwargs: "")
    panel.configure(cfg, DemoDaemon(), DemoBot())
    return panel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument(
        "--scene", default="work",
        choices=("work", "empty", "trouble", "hostile", "probe", "budget", "waiting",
                 "reserve"))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="xgw-panel-demo-") as root:
        panel = build(Path(root), args.port, args.scene)
        panel.start()
        print(f"Панель: http://127.0.0.1:{panel.port}/?token={TOKEN}", flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            panel.stop()


if __name__ == "__main__":
    main()
