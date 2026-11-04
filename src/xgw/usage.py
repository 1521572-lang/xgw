"""Учёт расхода трафика по устройствам и подпискам (0.2.0, пожелание заказчика 31.10.2026).

**Устройства сети** — счётчиками nftables в своей таблице `ip xgw_acct`. Полная замена
таблицы `ip xgw` при каждой перезагрузке правил перехвата (net/nft.py) её не трогает. Наборы
dev_up и dev_down — динамические, со счётчиком на адрес (`update @dev_up { ip saddr counter }`):
в prerouting — всё, что пришло из LAN от устройства, в postrouting — всё, что ушло в LAN к нему.
Считается и трафик через Xray (TPROXY), и напрямую (российские адреса, обход VPN). Устройство
ключуется по MAC из аренд DHCP, без аренды — по адресу.

**WAN** — именованные счётчики wan_in и wan_out: всего через провайдера, вместе с накладными
расходами VPN. Разница между WAN и суммой устройств — сам шлюз, проверки серверов, обновления
подписок и служебный трафик VPN.

**Подписки** — счётчики outbound'ов Xray (/debug/vars, stats.outbound, при
policy.system.statsOutbound*): тег → сервер → его подписка (ServerNode.source). Серверы pool-* —
бесплатные серверы, direct — напрямую мимо VPN. «Учтено подпиской» — байты, умноженные на
множитель сервера (x10 — вдесятеро): так считает провайдер с квотой.

Счётчики накопительные — с запуска Xray или с появления элемента набора. Демон берёт разницу с
прошлым отсчётом: у Xray — каждый шаг (счётчик убранного outbound'а пропадает вместе с ним), у
nftables — раз в USAGE_EVERY, тогда же накопленное пишется в базу. Значение меньше прошлого
означает сброс (перезапуск Xray, истёкший элемент набора), и тогда разница — само значение.
Первый отсчёт Xray после запуска демона — только база: счётчики копились и до него, а
записанное прошлым запуском повторять нельзя; таблицу учёта новый демон ставит заново, и её
счётчики идут с нуля. Теряется не больше USAGE_EVERY — незаписанное к остановке демона. В базу
состояния (state.db, таблица usage) пишутся суммы по дням: день, вид, ключ, байт вверх и вниз,
учтено подпиской. Хранятся USAGE_DAYS дней.
"""

from __future__ import annotations

import datetime
import json
import time
from collections.abc import Callable, Mapping, Sequence

from . import cost
from .config import Config
from .generator import builder
from .net import cmd, dnsmasq, lan
from .paths import Paths
from .store import Store

TABLE = "xgw_acct"
UP_SET, DOWN_SET = "dev_up", "dev_down"
WAN_IN, WAN_OUT = "wan_in", "wan_out"
SET_SIZE = 4096
SET_TIMEOUT = "1d"  # устройство молчит сутки — его элемент уходит (разница уже записана)
USAGE_EVERY = 60.0
USAGE_DAYS = 400
LABELS_META = "usage_labels"  # ключ устройства → {"name", "ip"} последнего отсчёта
# Виды строк таблицы usage.
DEVICE, SUB, POOL, DIRECT, WAN = "device", "sub", "pool", "direct", "wan"
POOL_PREFIX = "pool-"


def render(lan_if: str, lan_net: str, wan_if: str) -> str:
    """Таблица учёта для `nft -f` — полной заменой; пусто — считать нечего (нет ни LAN, ни
    WAN). Счётчики пересозданной таблицы начинаются заново — Meter это видит как сброс."""
    blocks: list[list[str]] = []
    pre: list[str] = []
    post: list[str] = []
    if lan_if and lan_net:
        for name in (UP_SET, DOWN_SET):
            blocks.append([f"set {name} {{", "    type ipv4_addr", f"    size {SET_SIZE}",
                           "    flags dynamic,timeout", f"    timeout {SET_TIMEOUT}", "}"])
        pre.append(f'iifname "{lan_if}" ip saddr {lan_net} update @{UP_SET} {{ ip saddr counter }}')
        post.append(
            f'oifname "{lan_if}" ip daddr {lan_net} update @{DOWN_SET} {{ ip daddr counter }}')
    if wan_if:
        for name in (WAN_IN, WAN_OUT):
            blocks.append([f"counter {name} {{", "    packets 0 bytes 0", "}"])
        pre.append(f'iifname "{wan_if}" counter name "{WAN_IN}"')
        post.append(f'oifname "{wan_if}" counter name "{WAN_OUT}"')
    if not pre:
        return ""
    # Учёт — раньше всех (raw) на входе и позже всех на выходе; политика accept: таблица
    # только считает и ничего не меняет.
    blocks.append(["chain pre {", "    type filter hook prerouting priority -300; policy accept;",
                   *(f"    {rule}" for rule in pre), "}"])
    blocks.append(["chain post {", "    type filter hook postrouting priority 300; policy accept;",
                   *(f"    {rule}" for rule in post), "}"])
    lines = [f"table ip {TABLE}", f"delete table ip {TABLE}", f"table ip {TABLE} {{"]
    for index, block in enumerate(blocks):
        if index:
            lines.append("")
        lines.extend(f"    {line}" for line in block)
    lines.append("}")
    return "\n".join(lines) + "\n"


def remove(runner: cmd.Runner) -> None:
    """Убрать таблицу учёта (`xgw uninstall`); её нет — не ошибка."""
    runner(["nft", "-f", "-"], input=f"table ip {TABLE}\ndelete table ip {TABLE}\n")


def parse(listing: str) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    """`nft -j list table ip xgw_acct` → байт по адресам от устройств, к устройствам и
    именованные счётчики. Элемент набора со счётчиком в JSON nft — {"elem": {"val": адрес,
    "counter": {"packets", "bytes"}, …}}; без счётчика элемент пропускается."""
    sets: dict[str, dict[str, int]] = {UP_SET: {}, DOWN_SET: {}}
    named: dict[str, int] = {}
    data = json.loads(listing)
    items = data.get("nftables") if isinstance(data, dict) else None
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        found = item.get("set")
        if isinstance(found, dict) and found.get("name") in sets:
            for elem in found.get("elem") or []:
                body = elem.get("elem") if isinstance(elem, dict) else None
                counter = body.get("counter") if isinstance(body, dict) else None
                if isinstance(counter, dict) and isinstance(body.get("val"), str):
                    sets[str(found["name"])][body["val"]] = int(counter.get("bytes") or 0)
        counter = item.get("counter")
        if isinstance(counter, dict) and counter.get("name"):
            named[str(counter["name"])] = int(counter.get("bytes") or 0)
    return sets[UP_SET], sets[DOWN_SET], named


def outbound_counters(metrics: Mapping) -> dict[str, tuple[int, int]]:
    """Счётчики outbound'ов Xray: тег → (uplink, downlink) байт с запуска ядра."""
    section = metrics.get("stats") if isinstance(metrics, Mapping) else None
    outbound = section.get("outbound") if isinstance(section, Mapping) else None
    if not isinstance(outbound, Mapping):
        return {}
    result: dict[str, tuple[int, int]] = {}
    for tag, counters in outbound.items():
        if isinstance(counters, Mapping):
            up, down = counters.get("uplink"), counters.get("downlink")
            result[str(tag)] = (up if isinstance(up, int) else 0,
                                down if isinstance(down, int) else 0)
    return result


def today(clock: Callable[[], float] = time.time) -> str:
    return datetime.date.fromtimestamp(clock()).isoformat()


class Meter:
    """Отсчёты счётчиков и запись разниц в базу (Daemon._usage_step). Переходит к новому
    демону при перечитывании настроек (Daemon._resume) вместе с прошлыми отсчётами и
    накопленным, но ещё не записанным."""

    def __init__(self, cfg: Config, paths: Paths, *, runner: cmd.Runner | None = cmd.run,
                 clock: Callable[[], float] = time.time, logger=None) -> None:
        """runner None — без nftables (демон без перехвата, тесты): только счётчики Xray."""
        self.cfg, self.paths, self.runner, self.clock, self.log = cfg, paths, runner, clock, logger
        self._table = ""  # текст таблицы учёта, которую поставил этот демон
        # Прошлые отсчёты (id счётчика → байт); None — отсчётов ещё не было (первый — база).
        self._xray_last: dict[str, int] | None = None
        self._nft_last: dict[str, int] | None = None
        self._pending: dict[tuple[str, str], list[int]] = {}  # (вид, ключ) → вверх, вниз, учтено
        self._next = 0.0
        self._pruned = ""
        self._warned = ""

    def step(self, store: Store, metrics: Mapping, applied: Mapping | None,
             nodes: Sequence) -> bool:
        """Счётчики Xray — на каждом шаге демона: outbound пересобранного или убранного сервера
        пропадает вместе со счётчиком, и чем реже отсчёт, тем больше его трафика теряется (отчёт
        usage: 26,8 МБ из 30 у подписки). nftables и запись накопленного в базу — раз в
        USAGE_EVERY. True — записано."""
        readings, owners = self._xray(metrics, applied, nodes)
        self._add(self._xray_last, readings, owners)
        self._xray_last = readings
        now = self.clock()
        if now < self._next:
            return False
        self._next = now + USAGE_EVERY
        labels: dict[str, dict] = {}
        counted = self._devices()
        if counted is not None:
            readings, owners, labels = counted
            self._add(self._nft_last, readings, owners)
            self._nft_last = readings
        day = today(self.clock)
        rows = [(kind, key, *row) for (kind, key), row in sorted(self._pending.items())]
        self._pending = {}
        if rows:
            store.add_usage(day, rows)
        if labels:
            self._save_labels(store, labels)
        if self._pruned != day:
            self._pruned = day
            before = datetime.date.fromisoformat(day) - datetime.timedelta(days=USAGE_DAYS)
            store.prune_usage(before.isoformat())
        return bool(rows)

    def _add(self, last: dict[str, int] | None, readings: dict[str, int],
             owners: dict[str, tuple[str, str, str, float]]) -> None:
        """Разницы с прошлым отсчётом — в накопленное; прошлого нет — это база."""
        if last is None:
            return
        for ident, value in readings.items():
            before = last.get(ident, 0)
            delta = value - before if value >= before else value
            if delta <= 0:
                continue
            kind, key, direction, factor = owners[ident]
            row = self._pending.setdefault((kind, key), [0, 0, 0])
            row[0 if direction == "up" else 1] += delta
            row[2] += round(delta * factor)

    def _xray(self, metrics: Mapping, applied: Mapping | None, nodes: Sequence):
        """Счётчики outbound'ов Xray: id → байт, id → (вид, ключ, направление, множитель)."""
        readings: dict[str, int] = {}
        owners: dict[str, tuple[str, str, str, float]] = {}
        infos = {info.tag: info for info in builder.applied_nodes(applied, nodes)}
        by_fingerprint = {node.fingerprint: node for node in nodes}
        pattern = self.cfg.filters.multiplier_regex
        for tag, (up, down) in outbound_counters(metrics).items():
            if tag == "direct":
                kind, key, factor = DIRECT, DIRECT, 0.0
            elif tag.startswith(POOL_PREFIX):
                kind, key, factor = POOL, POOL, 0.0
            elif tag in infos:
                node = by_fingerprint.get(infos[tag].fingerprint)
                kind, key = SUB, (node.source if node is not None else "") or "?"
                factor = cost.multiplier(node.name, pattern) if node is not None else 1.0
            else:
                continue  # dns-out, block, api — не трафик пользователей
            for direction, value in (("up", up), ("down", down)):
                ident = f"xray:{tag}:{direction}"
                readings[ident], owners[ident] = value, (kind, key, direction, factor)
        return readings, owners

    def _devices(self):
        """Счётчики nftables: id → байт, id → (вид, ключ, направление, 0), подписи устройств;
        None — в этом отсчёте их нет."""
        readings: dict[str, int] = {}
        owners: dict[str, tuple[str, str, str, float]] = {}
        labels: dict[str, dict] = {}
        counted = self._nft()
        if counted is not None:
            ups, downs, named = counted
            macs = {device["ip"]: device for device in dnsmasq.read_leases(self.paths)}
            for direction, found in (("up", ups), ("down", downs)):
                for ip, value in found.items():
                    device = macs.get(ip)
                    key = device["mac"] if device else f"ip:{ip}"
                    labels[key] = {"name": device["name"] if device else "", "ip": ip}
                    ident = f"nft:{direction}:{ip}"
                    readings[ident], owners[ident] = value, (DEVICE, key, direction, 0.0)
            for name, direction in ((WAN_OUT, "up"), (WAN_IN, "down")):
                if name in named:
                    ident = f"nft:{name}"
                    readings[ident], owners[ident] = named[name], (WAN, WAN, direction, 0.0)
            return readings, owners, labels
        return None

    def _nft(self) -> tuple[dict[str, int], dict[str, int], dict[str, int]] | None:
        """Счётчики таблицы учёта; таблицы нет или она устарела (сменились LAN или WAN) —
        поставить заново. None — устройств и WAN в этом отсчёте нет."""
        if self.runner is None:
            return None
        gateway = lan.gateway(self.cfg)
        lan_net = str(gateway.network) if gateway is not None and self.cfg.network.lan_if else ""
        try:
            wan_if = lan.effective_wan(self.cfg, self.runner)
        except (cmd.CommandError, OSError):
            wan_if = ""
        wanted = render(self.cfg.network.lan_if, lan_net, wan_if)
        if not wanted:
            return None
        try:
            if wanted != self._table:
                self.runner(["nft", "-f", "-"], input=wanted)
                self._table = wanted
                # Таблица новая — её счётчики с нуля: следующий отсчёт считается целиком.
                self._nft_last = {}
                return None
            return parse(self.runner(["nft", "-j", "list", "table", "ip", TABLE]))
        except (cmd.CommandError, OSError, ValueError) as exc:
            self._table = ""  # таблица пропала или не встала — поставить снова в следующий раз
            text = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
            if text != self._warned and self.log is not None:
                self.log.warning("учёт трафика устройств: %s", text)
            self._warned = text
            return None

    def _save_labels(self, store: Store, labels: dict[str, dict]) -> None:
        try:
            saved = json.loads(store.get_meta(LABELS_META) or "{}")
        except ValueError:
            saved = {}
        merged = {**(saved if isinstance(saved, dict) else {}), **labels}
        if merged != saved:
            store.set_meta(LABELS_META, json.dumps(merged, ensure_ascii=False, sort_keys=True))


def summary(rows: Sequence[Mapping], labels: Mapping[str, Mapping], quotas: Mapping,
            devices: Sequence[Mapping], *, days: int, since: str) -> dict:
    """Сводка для панели и `xgw traffic` из сумм usage_since. Подписи устройств — из аренд
    сейчас, иначе из последнего отсчёта. «Шлюз и служебное» — WAN минус устройства (не меньше
    нуля): в WAN ещё и накладные расходы VPN, проверки серверов, обновления."""
    names = {str(device.get("mac")): device for device in devices}
    by_kind: dict[str, list[Mapping]] = {}
    for row in rows:
        by_kind.setdefault(str(row["kind"]), []).append(row)

    def pair(row: Mapping | None) -> dict:
        return {"up": int((row or {}).get("up") or 0), "down": int((row or {}).get("down") or 0)}

    device_rows = []
    for row in by_kind.get(DEVICE, []):
        key = str(row["key"])
        label = labels.get(key) or {}
        lease = names.get(key) or {}
        device_rows.append({"key": key, "name": lease.get("name") or label.get("name") or "",
                            "ip": lease.get("ip") or label.get("ip") or key.removeprefix("ip:"),
                            **pair(row)})
    device_rows.sort(key=lambda item: -(item["up"] + item["down"]))
    subs = []
    for row in by_kind.get(SUB, []):
        name = str(row["key"])
        quota = quotas.get(name) if isinstance(quotas.get(name), Mapping) else {}
        total = int(quota.get("total") or 0)
        subs.append({"name": name, **pair(row), "billed": int(row.get("billed") or 0),
                     "quota": {"used": int(quota.get("upload") or 0)
                               + int(quota.get("download") or 0),
                               "total": total, "expire": int(quota.get("expire") or 0)}
                     if total else None})
    subs.sort(key=lambda item: -(item["up"] + item["down"]))
    total = {"up": sum(item["up"] for item in device_rows),
             "down": sum(item["down"] for item in device_rows)}
    wan_rows = by_kind.get(WAN, [])
    wan = pair(wan_rows[0]) if wan_rows else None
    gateway = ({"up": max(0, wan["up"] - total["up"]), "down": max(0, wan["down"] - total["down"])}
               if wan else None)
    return {"days": days, "since": since, "devices": device_rows, "devices_total": total,
            "subscriptions": subs, "pool": pair((by_kind.get(POOL) or [None])[0]),
            "direct": pair((by_kind.get(DIRECT) or [None])[0]), "wan": wan, "gateway": gateway}


def report(cfg: Config, paths: Paths, days: int, *, clock: Callable[[], float] = time.time,
           store: Store | None = None) -> dict:
    """Сводка за последние days дней, включая сегодня (1 — только сегодня)."""
    since = (datetime.date.fromtimestamp(clock()) - datetime.timedelta(days=days - 1)).isoformat()
    own = store is None
    store = store or Store(paths.db_file)
    try:
        rows = store.usage_since(since)
        try:
            labels = json.loads(store.get_meta(LABELS_META) or "{}")
            quotas = json.loads(store.get_meta("quota") or "{}")
        except ValueError:
            labels, quotas = {}, {}
    finally:
        if own:
            store.close()
    return summary(rows, labels if isinstance(labels, dict) else {},
                   quotas if isinstance(quotas, dict) else {}, dnsmasq.read_leases(paths),
                   days=days, since=since)


def size(value: int) -> str:
    """Байты по-русски: 850 КБ, 12,4 МБ, 3,1 ГБ."""
    if value < 1_000_000:
        return f"{max(0, round(value / 1000))} КБ"
    if value < 1_000_000_000:
        number, unit = value / 1_000_000, "МБ"
    else:
        number, unit = value / 1_000_000_000, "ГБ"
    text = f"{number:.0f}" if number >= 100 else f"{number:.1f}"
    return f"{text.replace('.', ',')} {unit}"


def text(found: Mapping) -> str:
    """`xgw traffic`: сводка строками."""
    days = int(found["days"])
    head = "сегодня" if days == 1 else f"за {days} дн. (с {found['since']})"
    lines = [f"Трафик {head}: ↓ получено, ↑ отправлено.", "", "Устройства:"]
    for item in found["devices"]:
        name = item["name"] or "без имени"
        lines.append(f"  {name} ({item['ip']}): ↓ {size(item['down'])}, ↑ {size(item['up'])}")
    if not found["devices"]:
        lines.append("  данных нет (нет сети LAN или учёт ещё не начался)")
    lines += ["", "Подписки и выходы:"]
    for item in found["subscriptions"]:
        line = f"  {item['name']}: ↓ {size(item['down'])}, ↑ {size(item['up'])}"
        if item["quota"]:
            quota = item["quota"]
            line += (f"; учтено подпиской ≈ {size(item['billed'])}; по данным подписки — "
                     f"{size(quota['used'])} из {size(quota['total'])}")
        lines.append(line)
    pool, direct = found["pool"], found["direct"]
    if pool["up"] or pool["down"]:
        lines.append(f"  бесплатные серверы: ↓ {size(pool['down'])}, ↑ {size(pool['up'])}")
    lines.append(f"  напрямую (мимо VPN): ↓ {size(direct['down'])}, ↑ {size(direct['up'])}")
    if found["wan"]:
        wan, gateway = found["wan"], found["gateway"]
        lines += ["", f"Всего через провайдера (WAN): ↓ {size(wan['down'])}, ↑ {size(wan['up'])}",
                  f"Шлюз и служебное (WAN минус устройства): ↓ {size(gateway['down'])}, "
                  f"↑ {size(gateway['up'])}"]
    return "\n".join(lines)
