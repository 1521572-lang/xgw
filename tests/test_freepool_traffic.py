"""Веха М2б.1: устройство через бесплатный пул — допуск серверов пула, балансировщик «pool» в
рабочем конфиге, «закрыто» без серверов, выбор в панели и закреплённый сервер у демона."""

import json
import logging
import threading
from types import SimpleNamespace

import pytest

from xgw import actions, engine, managed
from xgw.config import Config
from xgw.freepool import pool, providers, traffic
from xgw.freepool import stats as poolstats
from xgw.freepool.models import ProviderResult, Status
from xgw.freepool.store import PoolStore
from xgw.generator import builder, diff
from xgw.model import raw_to_node
from xgw.parsers.common import parse_links_text
from xgw.paths import Paths, atomic_write_json

LOG = logging.getLogger("test")
NOW = 1_800_000_000.0
DEVICE = "192.168.50.120"
UUID = "0b6a2a3c-1d2e-4f50-8a9b-0c1d2e3f4a5b"


def _link(host: str, name: str) -> str:
    return (f"vless://{UUID}@{host}:443?security=tls&sni=a.example.com&type=tcp"
            f"#{name}")


LINKS = {
    "fast": _link("198.51.100.21", "fast"),
    "slow": _link("198.51.100.22", "slow"),
    "ok": _link("198.51.100.23", "ok"),
    "named": _link("srv.example.com", "named"),
    "stale": _link("198.51.100.24", "stale"),
    "us": _link("198.51.100.25", "us"),
    "dead": _link("198.51.100.26", "dead"),
}


@pytest.fixture()
def paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    found = Paths.from_env()
    found.ensure()
    return found


def _cfg(mode: str = "observe") -> Config:
    cfg = Config()
    cfg.free_pool.mode = mode
    cfg.free_pool.providers = [providers.MAHDIBLAND]
    cfg.managed.routes = {DEVICE: managed.POOL_ROUTE}
    return cfg


def _pool(paths) -> dict[str, str]:
    """Снимок списка и итоги проверок: имя → id варианта."""
    result = providers.parse_link_list(providers.MAHDIBLAND, [("u", "\n".join(LINKS.values()))],
                                       now=NOW)
    store = PoolStore(paths)
    store.commit(ProviderResult(providers.MAHDIBLAND, Status.SUCCESS, variants=result.variants,
                                retrieved_at=NOW, complete_response=True))
    ids = {variant.name.split()[-1]: variant.variant_id for variant in result.variants}
    record = {"checked_at": NOW - 600, "verdict": "OK", "seconds": 1.0, "bytes": 100_000,
              "egress_country": "DE", "backend": "xray", "provider": providers.MAHDIBLAND}
    store.save_candidates({
        ids["fast"]: {**record, "bytes": 900_000},
        ids["slow"]: {**record, "verdict": "SLOW", "bytes": 2_000_000},
        ids["ok"]: record,
        ids["named"]: record,
        ids["stale"]: {**record, "checked_at": NOW - traffic.FRESH - 1},
        ids["us"]: {**record, "egress_country": "US"},
        ids["dead"]: {**record, "verdict": "TIMEOUT"},
    })
    return ids


def test_admitted_are_fresh_working_servers_of_the_region_with_an_address(paths):
    """Допуск — только по своей свежей проверке шлюза и стране выхода в регионе; сервер с
    именем вместо адреса пока не допускается (его имя Xray до перезапуска разрешал бы своим
    DNS). Порядок — OK раньше SLOW, затем скорость проверки."""
    ids = _pool(paths)
    found = traffic.admitted(_cfg(), paths, NOW)
    assert [item.node.fingerprint for item in found] == [ids["fast"], ids["ok"], ids["slow"]]
    node = found[0].node
    assert (node.country, node.source, node.address) == ("de", "pool:mahdibland",
                                                         "198.51.100.21")
    assert traffic.admitted(_cfg("off"), paths, NOW) == []


def test_panel_rows_tell_why_a_pool_server_is_not_admitted(paths):
    """Вкладка «Бесплатные серверы»: строка на каждый сервер пула с итогом проверки и причиной,
    по которой он не допущен; допущенные — те же, что у admitted; ссылок и ключей в строках нет."""
    ids = _pool(paths)
    rows = {row["id"]: row for row in pool.server_rows(_cfg(), paths, NOW)}
    assert set(rows) == set(ids.values())
    admitted = {item.node.fingerprint for item in traffic.admitted(_cfg(), paths, NOW)}
    assert {key for key, row in rows.items() if not row["why"]} == admitted
    why = {name: rows[key]["why"] for name, key in ids.items()}
    assert "имя" in why["named"] and "старше 3 ч" in why["stale"]
    assert "US" in why["us"] and why["dead"] == "последняя проверка не прошла"
    fast = rows[ids["fast"]]
    assert (fast["country"], fast["egress"], fast["verdict"], fast["delay_ms"]) == ("DE", True,
                                                                                   "OK", 1000)
    assert fast["next_at"] == NOW - 600 + pool.LIST_CHECK_EVERY
    assert rows[ids["dead"]]["delay_ms"] is None
    assert UUID not in str(rows) and "outbound" not in str(rows)
    assert pool.server_rows(_cfg("off"), paths, NOW) == []


def test_pool_member_keeps_its_place_with_an_old_check(paths):
    """Восстановление (М3): сервер, уже стоящий в «pool», допущен со старой удачной проверкой до
    traffic.KEEP — после сна шлюза устройства не закрываются, пока проверки догоняют; новый
    сервер с такой же проверкой — нет."""
    ids = _pool(paths)
    member = ids["stale"][:8]
    assert ids["stale"] not in {item.node.fingerprint
                                for item in traffic.admitted(_cfg(), paths, NOW)}
    kept = traffic.admitted(_cfg(), paths, NOW, members={member})
    assert ids["stale"] in {item.node.fingerprint for item in kept}
    later = NOW - traffic.FRESH - 1 + traffic.KEEP + 1
    assert ids["stale"] not in {item.node.fingerprint for item in traffic.admitted(
        _cfg(), paths, later, members={member})}
    variant = next(item for item in PoolStore(paths).variants(providers.MAHDIBLAND)
                   if item.variant_id == ids["stale"])
    record = PoolStore(paths).candidates()[ids["stale"]]
    assert traffic.refusal(_cfg(), variant, record, later, member=True) == (
        "проверка старше 24 ч — ждёт новой")


def test_pool_checks_its_servers_and_former_good_ones_first(paths):
    """Восстановление (М3): сервер «pool», который молчит у проб ядра, проверяется вне
    расписания, но не чаще URGENT_GAP; когда пора, остальные серверы «pool» и прежде пригодные
    идут раньше прочих — после перерыва допуск возвращается с них."""
    ids = _pool(paths)
    names = {key: name for name, key in ids.items()}
    clock = [NOW + 600]
    checker = pool.FreePool(_cfg(), paths, clock=lambda: clock[0])
    checker.members = frozenset({ids["fast"][:8], ids["ok"][:8]})
    checker.urgent = frozenset({ids["ok"][:8]})

    def order() -> list[str]:
        return [names[variant.variant_id] for variant in checker.next_checks(None)]

    assert order() == ["ok", "stale"]  # прочим ещё рано, «stale» — проверка старше 2 ч
    clock[0] = NOW - 600 + pool.URGENT_GAP - 1
    assert order() == ["stale"]
    clock[0] = NOW + pool.LIST_CHECK_EVERY
    found = order()
    assert found[:3] == ["ok", "fast", "stale"]
    assert set(found[3:5]) == {"slow", "named"} and set(found[5:]) == {"us", "dead"}


def test_pool_composition_keeps_applied_servers_first():
    """Сборка не перетасовывает «pool»: применённые и ещё допущенные — первыми; сервер,
    совпавший с сервером подписки, — не в пуле."""
    found = [SimpleNamespace(node=SimpleNamespace(fingerprint=name)) for name in "abcd"]
    chosen = traffic.choose(found, {"c"}, exclude={"b"}, limit=2)
    assert [item.node.fingerprint for item in chosen] == ["c", "a"]


def test_pool_server_chosen_by_hand(paths, tmp_path):
    """П. 272: сервер пула, выбранный вручную на вкладке, — только из допущенных (по id или его
    началу); в состав «pool» он идёт первым, демон держит его, пока жив, а умер — сервер выбирает
    шлюз; нет его в составе — срочная сборка; «auto» — снова выбирает шлюз."""
    ids = _pool(paths)
    cfg = _cfg("on")
    cfg.managed.routes = {}
    store = tmp_path / "panel.json"
    assert actions.set_pool_pin(paths, store, cfg, ids["dead"]).code == 2  # не допущен
    assert actions.set_pool_pin(paths, store, cfg, ids["fast"][:4]).code == 2  # короткое начало
    done = actions.set_pool_pin(paths, store, cfg, ids["slow"][:8])
    assert done.ok and "slow» (DE)" in done.text
    assert managed.load(store)[0]["free_pool_pin"] == ids["slow"]
    found = traffic.admitted(cfg, paths, NOW)
    chosen = traffic.choose(found, {ids["fast"]}, exclude=set(), limit=2, prefer=ids["slow"])
    assert [item.node.fingerprint for item in chosen] == [ids["slow"], ids["fast"]]
    # Демон: выбранный держится, хотя другой быстрее; умер — выбирает шлюз, с пометкой.
    fast, slow = f"pool-de-{ids['fast'][:8]}", f"pool-de-{ids['slow'][:8]}"
    applied = {"outbounds": [{"tag": fast}, {"tag": slow}]}
    paths.xray_config_file.write_text("{}", encoding="utf-8")
    daemon = _daemon(paths)
    daemon.cfg = cfg
    cfg.managed.free_pool_pin = ids["slow"]
    daemon._pool_step(applied, {fast: {"alive": True, "delay": 0.1},
                                slow: {"alive": True, "delay": 0.4}})
    assert daemon.api.calls == [("pin", "pool", slow)]
    assert daemon._pool_traffic["manual"] == "on" and "выбран вручную" in daemon.events[-1]
    daemon._pool_step(applied, {fast: {"alive": True, "delay": 0.1}, slow: {"alive": False}})
    assert daemon.api.calls[-1] == ("pin", "pool", fast)
    assert daemon._pool_traffic["manual"] == "down" and "не отвечает" in daemon.events[-1]
    # Выбранного нет в составе «pool» — срочная сборка (engine.assemble поставит его первым).
    daemon._pool_due({"outbounds": [{"tag": fast}]}, NOW)
    assert daemon._urgent_rebuild == "бесплатный пул: выбранный вручную сервер"
    back = actions.set_pool_pin(paths, store, cfg, "auto")
    assert back.ok and managed.load(store)[0]["free_pool_pin"] == ""
    with actions.open_store(paths) as db:
        texts = [row["detail"] for row in db.recent_events(2)]
    assert texts[0] == "бесплатный пул: выбор сервера вручную снят — сервер выбирает шлюз"
    assert texts[1].startswith("бесплатный пул: сервер «")
    assert texts[1].endswith("slow» (DE) выбран вручную")


def _selection(*links_text: str) -> builder.Selection:
    raws, _meta, _warnings = parse_links_text("\n".join(links_text), "main")
    return builder.Selection(members=[raw_to_node(raw, "main") for raw in raws])


SUBSCRIPTION = _link("203.0.113.10", "DE%20sub")


def test_pool_devices_go_through_the_pool_balancer_after_direct_domains(paths):
    """Устройство через пул — балансировщиком «pool» (все мертвы — block), правило после
    прямых доменов (российские сайты — напрямую); подписка серверов пула не получает."""
    _pool(paths)
    cfg = _cfg()
    pool = [item.node for item in traffic.admitted(cfg, paths, NOW)]
    result = builder.build(cfg, _selection(SUBSCRIPTION), hosts={}, pool=pool,
                           pool_devices=[DEVICE])
    config = result.config
    tags = [outbound["tag"] for outbound in config["outbounds"]]
    assert [info.tag for info in result.pool] == [tag for tag in tags if tag.startswith("pool-")]
    assert len(result.pool) == 3 and len(result.nodes) == 1
    balancers = {item["tag"]: item for item in config["routing"]["balancers"]}
    assert balancers["auto"]["selector"] == ["proxy-"]
    assert balancers["pool"] == {"tag": "pool", "selector": ["pool-"],
                                 "strategy": {"type": "leastPing"}, "fallbackTag": "block"}
    assert config["burstObservatory"]["subjectSelector"] == ["proxy-", "pool-"]
    rules = config["routing"]["rules"]
    device = next(i for i, rule in enumerate(rules) if rule.get("source") == [DEVICE])
    direct = next(i for i, rule in enumerate(rules) if "domain:ru" in (rule.get("domain") or []))
    assert direct < device and rules[device]["balancerTag"] == "pool"
    inbounds = {inbound["tag"] for inbound in config["inbounds"]}
    assert {info.probe_tag for info in result.pool} <= inbounds
    applied = builder.applied_pool(config, pool)
    assert {info.fingerprint for info in applied} == {node.fingerprint for node in pool}


def test_pool_device_is_closed_without_pool_servers_and_xray_is_not_restarted(paths):
    """Серверов пула нет — у устройства закрыто (block), а не подписка. Пробы ядра для пула
    остаются по наличию устройства: секция burstObservatory меняется только перезапуском Xray,
    а состав пула (outbounds pool-*) — через API."""
    _pool(paths)
    cfg = _cfg()
    pool = [item.node for item in traffic.admitted(cfg, paths, NOW)]
    full = builder.build(cfg, _selection(SUBSCRIPTION), hosts={}, pool=pool,
                         pool_devices=[DEVICE]).config
    empty = builder.build(cfg, _selection(SUBSCRIPTION), hosts={}, pool=[],
                          pool_devices=[DEVICE]).config
    rule = next(rule for rule in empty["routing"]["rules"] if rule.get("source") == [DEVICE])
    assert rule["outboundTag"] == "block"
    assert [item["tag"] for item in empty["routing"]["balancers"]] == ["auto"]
    assert empty["burstObservatory"] == full["burstObservatory"]
    change = diff.diff_configs(full, empty)
    assert change.plan is not None and change.restart_reasons == []
    removed = sorted(change.plan.remove_outbound_tags)
    assert removed == sorted(info.tag for info in builder.applied_pool(full))


def test_whole_house_goes_through_the_pool_and_the_subscription_carries_the_daemon(paths):
    """Весь дом через пул (М2б.2): прочий трафик и DNS Xray — в «pool» (пуст — block), прямые
    домены — напрямую раньше; серверы подписки — только входам демона (несущий канал); свои
    серверы устройств (Ф4) и правило устройств пула не нужны; пробы ядра для пула — по режиму."""
    _pool(paths)
    cfg = _cfg("on")
    pool = [item.node for item in traffic.admitted(cfg, paths, NOW)]
    selection = _selection(SUBSCRIPTION)
    cfg.managed.routes = {DEVICE: managed.POOL_ROUTE,
                          "192.168.50.130": selection.members[0].fingerprint}
    usual = builder.build(cfg, selection, hosts={}, pool=pool, pool_devices=[DEVICE]).config
    assert [rule["source"] for rule in usual["routing"]["rules"] if rule.get("source")] \
        == [["192.168.50.130"], [DEVICE]]
    config = builder.build(cfg, selection, hosts={}, pool=pool, pool_devices=[DEVICE],
                           pool_all=True).config
    rules = config["routing"]["rules"]
    assert not [rule for rule in rules if rule.get("source")]
    carrier = rules.index({"type": "field", "inboundTag": ["http-in", "socks-in"],
                           "balancerTag": "auto"})
    direct = next(i for i, rule in enumerate(rules) if "domain:ru" in (rule.get("domain") or []))
    assert direct < carrier < len(rules) - 1
    assert rules[-1] == {"type": "field", "network": "tcp,udp", "balancerTag": "pool"}
    assert config["burstObservatory"]["subjectSelector"] == ["proxy-", "pool-"]
    # Управление и DERP Tailscale — через подписку, а их имена — прямыми серверами DNS: без них
    # удалённый доступ к шлюзу терялся (отчёт m2b2fix, дефект 1). В режиме подписок — как было.
    tailscale = rules.index({"type": "field", "domain": list(builder.TS_CONTROL),
                             "balancerTag": "auto"})
    assert carrier < tailscale < len(rules) - 1
    assert not [rule for rule in usual["routing"]["rules"]
                if rule.get("domain") == list(builder.TS_CONTROL)]
    direct_dns = [entry for entry in config["dns"]["servers"] if isinstance(entry, dict)]
    assert direct_dns and all(set(builder.TS_CONTROL) <= set(entry["domains"])
                              for entry in direct_dns)
    assert not [entry for entry in usual["dns"]["servers"] if isinstance(entry, dict)
                and set(builder.TS_CONTROL) & set(entry["domains"])]
    # DNS через пул — по TCP: бесплатный сервер может не пропускать UDP.
    assert usual["dns"]["servers"][-2:] == ["1.1.1.1", "8.8.8.8"]
    assert config["dns"]["servers"][-2:] == ["tcp://1.1.1.1", "tcp://8.8.8.8"]
    # xgw diag: весь дом — в «pool», входы демона и Tailscale — через подписку; правила
    # Tailscale нет — FAIL (удалённый доступ к шлюзу может пропасть).
    from xgw.diag import FAIL, OK, Diag

    atomic_write_json(paths.xray_config_file, config)
    check = Diag(cfg, paths, net=False)._pool_house()[0]
    assert check.level == OK and "Tailscale" in check.text
    atomic_write_json(paths.xray_config_file, {
        **config, "routing": {**config["routing"],
                              "rules": [rule for i, rule in enumerate(rules) if i != tailscale]}})
    assert Diag(cfg, paths, net=False)._pool_house()[0].level == FAIL
    empty = builder.build(cfg, selection, hosts={}, pool=[], pool_all=True).config
    assert empty["routing"]["rules"][-1] == {"type": "field", "network": "tcp,udp",
                                             "outboundTag": "block"}
    assert empty["burstObservatory"] == config["burstObservatory"]
    # Режим включён без устройств через пул — сборка всё равно берёт допущенных.
    raws, _meta, _warnings = parse_links_text(SUBSCRIPTION, "main")
    inventory = engine.Inventory([raw_to_node(raw, "main") for raw in raws])
    cfg.managed.routes = {}
    assembly = engine.assemble(cfg, paths, inventory, mark=None, logger=LOG, xray_bin=None,
                               check=False)
    assert assembly.result.pool and assembly.pool_devices == []
    assert assembly.result.config["routing"]["rules"][-1]["balancerTag"] == "pool"


def test_whole_house_is_not_switched_on_without_admitted_servers(paths, tmp_path):
    """Панель не включает весь дом без допущенных серверов (закрылось бы всё), команда
    включает и предупреждает; возврат в режим подписок — своим событием."""
    store = tmp_path / "panel.json"
    refused = actions.set_pool_mode(paths, store, "on", refuse_closing=True, ready=0)
    assert refused.code == 2 and "Допущенных" in refused.text
    done = actions.set_pool_mode(paths, store, "on", ready=0)
    assert done.ok and "сейчас нет" in done.text
    assert managed.load(store)[0]["free_pool_mode"] == "on"
    assert actions.set_pool_mode(paths, store, "observe", refuse_closing=True).ok
    with actions.open_store(paths) as db:
        texts = [row["detail"] for row in db.recent_events(10)]
    assert texts[:2] == ["бесплатный пул: режим подписок возвращён, наблюдение продолжается",
                         "бесплатный пул: весь дом через бесплатные серверы"]


def test_whole_house_does_not_survive_a_reboot(paths, tmp_path):
    """Отчёт m2b2fix, дефект 1: весь дом вернулся сам после перезагрузки, а снять его без
    удалённого доступа было нечем. Метки этой загрузки нет — режим подписок (observe) и событие;
    метка есть (перезапуск службы, установка) — весь дом остаётся."""
    store = tmp_path / "panel.json"
    assert managed.set_free_pool_mode(store, "on")
    paths.house_file.touch()
    assert not actions.house_after_boot(paths, store)
    assert managed.load(store)[0]["free_pool_mode"] == "on"
    paths.house_file.unlink()
    assert actions.house_after_boot(paths, store)
    assert managed.load(store)[0]["free_pool_mode"] == "observe"
    with actions.open_store(paths) as db:
        assert db.recent_events(1)[0]["detail"] == actions.HOUSE_BOOT_EVENT


def test_the_working_config_follows_the_mode(paths):
    """Отчёт m2b2fix2, дефект 1: после перезагрузки режим снят, а рабочий конфиг Xray — «весь
    дом», и сборка без пула ждала окна перезапуска (смены режима этого не меняли). Расхождение
    режима и рабочего конфига — срочная сборка, не чаще HOUSE_SYNC; xgw diag — FAIL. Сводка
    пула — с режимом из настроек; проверки пула выключение останавливает."""
    import threading

    from xgw.daemon import HOUSE_SYNC, _PoolCancel
    from xgw.diag import FAIL, Diag

    _pool(paths)
    selection = _selection(SUBSCRIPTION)
    pool = [item.node for item in traffic.admitted(_cfg("on"), paths, NOW)]
    house = builder.build(_cfg("on"), selection, hosts={}, pool=pool, pool_all=True).config
    usual = builder.build(_cfg(), selection, hosts={}, pool=pool, pool_devices=[DEVICE]).config
    assert builder.applied_whole(house) and not builder.applied_whole(usual)
    assert not builder.applied_whole(None) and not builder.applied_whole({"routing": {}})
    daemon = _daemon(paths)  # режим observe
    daemon._house_sync(usual, 100.0)
    assert daemon._urgent_rebuild == ""
    daemon._house_sync(house, 100.0)
    assert daemon._urgent_rebuild == "бесплатный пул: режим подписок"
    daemon._urgent_rebuild = ""  # сборку отклонили — снова не раньше HOUSE_SYNC
    daemon._house_sync(house, 100.0 + HOUSE_SYNC - 1)
    assert daemon._urgent_rebuild == ""
    daemon._house_sync(house, 100.0 + HOUSE_SYNC)
    assert daemon._urgent_rebuild == "бесплатный пул: режим подписок"
    daemon.cfg, daemon._urgent_rebuild = _cfg("on"), ""
    daemon._house_sync(usual, 100.0 + 2 * HOUSE_SYNC)
    assert daemon._urgent_rebuild == "бесплатный пул: весь дом"
    atomic_write_json(paths.xray_config_file, house)
    check = Diag(_cfg(), paths, net=False)._pool_traffic()[0]
    assert check.level == FAIL and "всё ещё ведёт весь дом" in check.text
    # Фоновый шаг пула пересчитывает сводку после проверок — режим в ней из настроек.
    daemon.cfg, daemon._freepool_summary = _cfg(), {"mode": "on", "region": "EU", "found": 3}
    assert daemon._pool_summary() == {"mode": "observe", "region": "EU",
                                      "region_policy": "strict", "found": 3}
    holder = SimpleNamespace(cfg=_cfg())
    cancel = _PoolCancel(threading.Event(), holder)
    assert not cancel.is_set()
    holder.cfg = _cfg("off")
    assert cancel.is_set()


def test_assemble_puts_admitted_pool_servers_into_the_config(paths):
    """engine.assemble берёт допущенные серверы пула сам — каждая сборка демона, CLI и
    установки одинаково ведёт устройство через пул."""
    _pool(paths)
    raws, _meta, _warnings = parse_links_text(SUBSCRIPTION, "main")
    inventory = engine.Inventory([raw_to_node(raw, "main") for raw in raws])
    assembly = engine.assemble(_cfg(), paths, inventory, mark=None, logger=LOG, xray_bin=None,
                               check=False)
    assert len(assembly.result.pool) == len(assembly.pool) >= 1
    assert assembly.pool_devices == [DEVICE]


def test_panel_route_to_the_pool_and_turning_the_pool_off(paths, tmp_path):
    """В панели у устройства — «Бесплатные серверы»; выключить пул панель тогда не даёт
    (у устройства закрылись бы зарубежные сайты), команда выключает и говорит об этом."""
    store = tmp_path / "panel.json"
    assert managed.set_route(store, "aa:bb:cc:00:11:22", DEVICE, "tv", managed.POOL_ROUTE)
    assert managed.load(store)[0]["routes"][0]["server"] == managed.POOL_ROUTE
    with pytest.raises(managed.ManagedError):
        managed.set_route(store, "aa:bb:cc:00:11:33", "192.168.50.130", "", "pool2")
    refused = actions.set_pool_mode(paths, store, "off", refuse_closing=True)
    assert refused.code == 2 and "«tv»" in refused.text
    done = actions.set_pool_mode(paths, store, "off")
    assert done.ok and "без зарубежных сайтов" in done.text


class _Api:
    def __init__(self):
        self.calls: list[tuple] = []

    def pin(self, balancer, tag):
        self.calls.append(("pin", balancer, tag))

    def unpin(self, balancer):
        self.calls.append(("unpin", balancer))


class _Meta:
    """meta базы в памяти — для дневника пула."""

    def __init__(self):
        self.meta = {}

    def get_meta(self, key):
        return self.meta.get(key)

    def set_meta(self, key, value):
        self.meta[key] = value


def _daemon(paths):
    from xgw.daemon import Daemon

    daemon = Daemon.__new__(Daemon)
    daemon.cfg, daemon.paths = _cfg(), paths
    daemon.api, daemon.log = _Api(), LOG
    daemon.events = []
    daemon.notifier = SimpleNamespace(event=lambda kind, text, **_k: daemon.events.append(text))
    daemon.wall = lambda: NOW
    daemon._urgent_rebuild = ""
    for name, value in (("_pool_pinned", ""), ("_pool_pin_key", 0.0),
                        ("_pool_checked_at", NOW), ("_pool_rebuilt_at", 0.0),
                        ("_pool_names", {}), ("_pool_traffic", None),
                        ("_pool_wait_since", 0.0), ("_house_synced_at", None),
                        ("_pool_ids", {}), ("_pool_speed", {}), ("_pool_since", 0.0),
                        ("_pool_basis", ""), ("_pool_deferred_since", None),
                        ("_pool_bytes", None), ("_pool_own", 0), ("_speed_ran", False),
                        ("_metrics", {}), ("_pool_downlinks", {}), ("_pool_measured", ("", 0)),
                        ("_pool_spared_tag", ""), ("_pool_silent", {}),
                        ("_pool_refreshed_at", 0.0), ("_freepool_force", False),
                        ("_pool_tags", set())):
        setattr(daemon, name, value)
    daemon.freepool = SimpleNamespace(members=frozenset(), urgent=frozenset())
    daemon.diary = poolstats.Diary(_Meta(), clock=lambda: daemon.wall())
    return daemon


def test_daemon_pins_a_live_pool_server_without_jumping(paths):
    """Закреплён живой с меньшей задержкой; более быстрый позже — не повод прыгать; закреплённый
    умер — следующий живой; живых нет — закрепление снято, у устройства закрыто."""
    applied = {"outbounds": [{"tag": "pool-de-aaaa"}, {"tag": "pool-de-bbbb"}]}
    paths.xray_config_file.write_text("{}", encoding="utf-8")
    daemon = _daemon(paths)
    daemon._pool_step(applied, {"pool-de-aaaa": {"alive": True, "delay": 0.3},
                                "pool-de-bbbb": {"alive": True, "delay": 0.1}})
    assert daemon.api.calls == [("pin", "pool", "pool-de-bbbb")]
    # Строкам вкладки «Бесплатные серверы» — весь состав «pool» с задержкой по пробам ядра.
    assert daemon._pool_traffic["servers"] == [
        {"id": "aaaa", "tag": "pool-de-aaaa", "alive": True, "delay_ms": 300, "mbps": None},
        {"id": "bbbb", "tag": "pool-de-bbbb", "alive": True, "delay_ms": 100, "mbps": None}]
    daemon._pool_step(applied, {"pool-de-aaaa": {"alive": True, "delay": 0.05},
                                "pool-de-bbbb": {"alive": True, "delay": 0.2}})
    assert daemon.api.calls == [("pin", "pool", "pool-de-bbbb")]
    daemon._pool_step(applied, {"pool-de-aaaa": {"alive": True, "delay": 0.05},
                                "pool-de-bbbb": {"alive": False, "delay": None}})
    assert daemon.api.calls[-1] == ("pin", "pool", "pool-de-aaaa")
    daemon._pool_step(applied, {"pool-de-aaaa": {"alive": False}, "pool-de-bbbb": {}})
    assert daemon.api.calls[-1] == ("unpin", "pool")
    assert daemon._pool_traffic["closed"] and "закрыто" in daemon.events[-1]
    assert len(daemon.events) == 3


def test_daemon_keeps_the_whole_house_on_a_live_pool_server(paths):
    """Весь дом через пул (М2б.2) — тот же закреплённый сервер «pool», и без устройств."""
    applied = {"outbounds": [{"tag": "pool-de-aaaa"}]}
    paths.xray_config_file.write_text("{}", encoding="utf-8")
    daemon = _daemon(paths)
    daemon.cfg = _cfg("on")
    daemon.cfg.managed.routes = {}
    daemon._pool_step(applied, {"pool-de-aaaa": {"alive": True, "delay": 0.2}})
    assert daemon.api.calls == [("pin", "pool", "pool-de-aaaa")]
    flow = daemon._pool_traffic
    assert flow["all"] and flow["devices"] == [] and "весь дом идёт через" in daemon.events[-1]
    assert traffic.text(flow).startswith("Весь дом через бесплатные серверы — сервер")
    daemon._pool_step(applied, {"pool-de-aaaa": {"alive": False}})
    assert "у всего дома закрыто" in daemon.events[-1]


def test_daemon_moves_the_pool_to_a_faster_server_without_jumping(paths):
    """Закреплённый сервер «pool» — по замеру: выбранный по задержке (замерены не все живые)
    уступает замеренному более быстрому сразу, выбранный по скорости — только продержавшись
    speed.hold_minutes; умер — лучший той же страны, а не самый быстрый вообще."""
    a, b, c = "pool-de-aaaa", "pool-nl-bbbb", "pool-nl-cccc"
    applied = {"outbounds": [{"tag": a}, {"tag": b}, {"tag": c}]}
    paths.xray_config_file.write_text("{}", encoding="utf-8")
    clock = [NOW]
    daemon = _daemon(paths)
    daemon.wall = lambda: clock[0]
    daemon._pool_names = {a: ("A", "DE"), b: ("B", "NL"), c: ("C", "NL")}
    daemon._pool_ids = {tag: tag[-4:] * 8 for tag in (a, b, c)}

    def speeds(values):
        daemon._pool_speed = {daemon._pool_ids[tag]: {"mbps": value, "ts": NOW}
                              for tag, value in values.items()}

    alive = {a: {"alive": True, "delay": 0.3}, b: {"alive": True, "delay": 0.1},
             c: {"alive": True, "delay": 0.5}}
    daemon._pool_step(applied, alive)
    assert daemon.api.calls[-1] == ("pin", "pool", b)  # замеров нет — по задержке
    speeds({a: 40.0, b: 10.0})
    daemon._pool_step(applied, alive)
    assert daemon.api.calls[-1] == ("pin", "pool", a)
    assert daemon.events[-1] == (f"бесплатный пул: устройства {DEVICE} идут через «A» (DE), "
                                 "40 Мбит/с — быстрее, чем «B» (10 Мбит/с)")
    speeds({a: 40.0, b: 10.0, c: 20.0})  # замерены все живые — выбор окончательный
    daemon._pool_step(applied, alive)
    assert daemon.api.calls[-1] == ("pin", "pool", a) and daemon._pool_basis == "speed"
    speeds({a: 40.0, b: 100.0, c: 20.0})
    daemon._pool_step(applied, alive)
    assert daemon.api.calls[-1] == ("pin", "pool", a)  # держится speed.hold_minutes
    clock[0] += daemon.cfg.speed.hold_minutes * 60
    daemon._pool_step(applied, alive)
    assert daemon.api.calls[-1] == ("pin", "pool", b)
    flow = daemon._pool_traffic
    assert flow["mbps"] == 100.0 and "(NL), 100 Мбит/с, задержка 100 мс" in traffic.text(flow)
    assert flow["servers"][1] == {"id": "bbbb", "tag": b, "alive": True, "delay_ms": 100,
                                  "mbps": 100.0, "speed_at": NOW}
    daemon._pool_step(applied, {**alive, b: {"alive": False}})
    assert daemon.api.calls[-1] == ("pin", "pool", c)  # той же страны, хотя A быстрее
    # Отчёт freepool-speed, дефект 1: смена не по скорости — с причиной.
    assert daemon.events[-1].endswith("через «C» (NL), 20 Мбит/с — «B» не отвечает")
    assert len(daemon.events) == 4
    today = daemon.diary.days()[poolstats.day_of(clock[0])]
    assert (today["switch_first"], today["switch_speed"], today["switch_dead"]) == (1, 2, 1)


def test_pinned_pool_server_carrying_traffic_is_not_dead(paths):
    """Отчёт freepool-speed, дефект 1: пробы ядра сочли закреплённый мёртвым, а через него идёт
    трафик (проба опоздала в забитом канале) — он остаётся; свой замер через него — не трафик
    клиентов: без трафика он сменяется, и событие называет причину."""
    a, b = "pool-de-aaaa", "pool-de-bbbb"
    applied = {"outbounds": [{"tag": a}, {"tag": b}]}
    paths.xray_config_file.write_text("{}", encoding="utf-8")
    clock = [NOW]
    daemon = _daemon(paths)
    daemon.wall = lambda: clock[0]

    def load(downlink):
        daemon._metrics = {"stats": {"outbound": {a: {"uplink": 0, "downlink": downlink}}}}

    load(0)
    daemon._pool_step(applied, {a: {"alive": True, "delay": 0.1},
                                b: {"alive": True, "delay": 0.3}})
    assert daemon.api.calls == [("pin", "pool", a)]
    dead = {a: {"alive": False}, b: {"alive": True, "delay": 0.3}}
    clock[0] += 20
    load(5_000_000)  # 2,5 МБ за 10 с — больше watchdog.busy_bytes
    daemon._pool_step(applied, dead)
    assert daemon.api.calls == [("pin", "pool", a)]
    assert daemon._pool_traffic["alive"] == 2 and daemon._pool_traffic["servers"][0]["alive"]
    daemon._pool_measured = (a, 5_000_000)  # весь прирост — свой замер
    clock[0] += 20
    load(10_000_000)
    daemon._pool_step(applied, dead)
    assert daemon.api.calls[-1] == ("pin", "pool", b)
    assert daemon.events[-1].endswith("через «pool-de-bbbb» — «pool-de-aaaa» не отвечает")
    daemon._pool_step(applied, {a: {"alive": False}, b: {"alive": False}})
    today = daemon.diary.days()[poolstats.day_of(clock[0])]
    assert (today["spared"], today["switch_dead"], today["closures"]) == (1, 1, 1)
    assert today["active_s"] == 40 and "closed_s" not in today


def test_silent_pool_server_is_rechecked_out_of_turn(paths):
    """Восстановление (М3): сервер «pool», молчащий у проб ядра дольше POOL_SILENT, — на
    перепроверку вне очереди (один раз за эпизод в дневник); ответил — снят. Пул закрыт —
    списки обновляются вне расписания, не чаще POOL_REFRESH. Выбывшие из состава дневник
    считает по самому составу."""
    from xgw.daemon import POOL_REFRESH, POOL_SILENT

    a, b = "pool-de-aaaa", "pool-de-bbbb"
    applied = {"outbounds": [{"tag": a}, {"tag": b}]}
    paths.xray_config_file.write_text("{}", encoding="utf-8")
    clock = [NOW]
    daemon = _daemon(paths)
    daemon.wall = lambda: clock[0]
    silent = {a: {"alive": True, "delay": 0.1}, b: {"alive": False}}
    daemon._pool_step(applied, silent)
    assert daemon.freepool.urgent == set()
    clock[0] += POOL_SILENT
    daemon._pool_step(applied, silent)
    assert daemon.freepool.urgent == {"bbbb"}
    clock[0] += 60
    daemon._pool_step(applied, silent)
    assert daemon.freepool.urgent == {"bbbb"}
    daemon._pool_step(applied, {a: {"alive": True, "delay": 0.1}, b: {"alive": True}})
    assert daemon.freepool.urgent == set() and daemon._pool_silent == {}
    assert not daemon._freepool_force
    closed = {a: {"alive": False}, b: {"alive": False}}
    daemon._pool_step(applied, closed)
    assert daemon._freepool_force and daemon._pool_traffic["closed"]
    daemon._freepool_force = False
    clock[0] += POOL_REFRESH - 1
    daemon._pool_step(applied, closed)
    assert not daemon._freepool_force
    clock[0] += 1
    daemon._pool_step(applied, closed)
    assert daemon._freepool_force
    daemon._pool_step({"outbounds": [{"tag": a}]}, {a: {"alive": True, "delay": 0.1}})
    today = daemon.diary.days()[poolstats.day_of(clock[0])]
    assert (today["rechecked"], today["refreshed"]) == (3, 2)  # b, затем a и b у закрытого
    assert today["dropped"] == 1 and daemon.freepool.urgent == set()
    daemon.cfg.managed.routes = {}
    daemon._pool_step(applied, closed)  # через пул никто: выключение режима — не «выбыло»
    assert daemon.freepool.urgent == set() and daemon._pool_tags == set()
    assert daemon.diary.days()[poolstats.day_of(clock[0])]["dropped"] == 1


def test_pool_gets_its_members_before_the_check_thread_starts(paths):
    """Отчёт freepool-recovery: после запуска демона в первую пачку проверок вклинился
    посторонний сервер — состав «pool» пул получал только в _pool_step, после запуска потока.
    Теперь — в _freepool_step, до него; через пул никто не идёт — состав пуст."""
    daemon = _daemon(paths)
    daemon._freepool_thread, daemon._freepool_next = None, NOW + 3600
    applied = {"outbounds": [{"tag": "pool-de-aaaa"}, {"tag": "pool-nl-bbbb"}]}
    daemon._freepool_step(NOW, applied)
    assert daemon.freepool.members == {"aaaa", "bbbb"}
    daemon.cfg.managed.routes = {}
    daemon._freepool_step(NOW, applied)
    assert daemon.freepool.members == set()


def test_pinned_pool_server_that_is_gone_is_released(paths):
    """Отчёт freepool-recovery, наблюдение 3: выбор вручную держался на выбывшем сервере. Как у
    подписки: выбранный сервер ушёл из списков или не прошёл проверку — выбор снимается с
    событием; проверка лишь устарела — нет (её освежит очередь)."""
    ids = _pool(paths)
    store = managed.path_for(paths.config_file)
    daemon = _daemon(paths)
    for pin, kept in ((ids["stale"], True), (ids["dead"], False), ("f" * 32, False)):
        managed.set_free_pool_pin(store, pin)
        daemon.cfg.managed.free_pool_pin = pin
        daemon._pool_due({}, NOW)
        assert (managed.load(store)[0]["free_pool_pin"] == pin) is kept
    assert daemon.events == [
        f"бесплатный пул: выбранный вручную сервер «{ids['dead'][:8]}» больше не допущен "
        "(последняя проверка не прошла) — сервер снова выбирает шлюз",
        "бесплатный пул: выбранный вручную сервер «ffffffff» больше не допущен (его больше нет "
        "в списках источников) — сервер снова выбирает шлюз"]


def test_pool_server_checks_spend_the_health_reserve(paths):
    """R28: прочие проверки каталогов — в бюджете без резерва здоровья, серверы «pool» — с
    резервом, молчащий сервер «pool» — и с аварийным запасом сверху."""
    checker = pool.FreePool(_cfg(), paths)
    budget = checker.cfg.free_pool
    budget.budget_mb, budget.health_reserved_mb, budget.emergency_mb = 512, 128, 64
    checker.members, checker.urgent = frozenset({"aaaa", "bbbb"}), frozenset({"bbbb"})
    assert checker._ceiling("c" * 32) == 384 * 1_048_576
    assert checker._ceiling("a" * 32) == 512 * 1_048_576
    assert checker._ceiling("b" * 32) == 576 * 1_048_576


def test_pool_servers_are_measured_one_per_step(paths, monkeypatch):
    """Замер серверов «pool» — по одному за шаг через их probe-inbound: сначала незамеренные
    (закреплённый первым) — и при занятом канале; повторный — через speed.unlimited_hours, при
    занятом канале ждёт, но не дольше SPEED_FORCE_AFTER; в шаге, где уже замеряли серверы
    подписки, — нет."""
    from xgw import daemon as daemon_module
    from xgw.watch import speed

    a, b = "pool-de-aaaa", "pool-de-bbbb"
    applied = {"outbounds": [{"tag": a}, {"tag": b}], "inbounds": [
        {"tag": f"probe-de-{name}", "port": port,
         "settings": {"accounts": [{"user": "probe", "pass": "secret"}]}}
        for name, port in (("aaaa", 20001), ("bbbb", 20002))]}
    measured = []

    def measure(info, cfg, *, probe_pass, max_mb, cancel):
        measured.append((info.tag, info.probe_port, probe_pass, max_mb))
        return speed.SpeedResult(25.0, 10_000_000, 3.2)

    monkeypatch.setattr(speed, "measure", measure)
    clock = [NOW]
    saved = {}
    daemon = _daemon(paths)
    daemon.wall = lambda: clock[0]
    daemon._stop = threading.Event()
    daemon.store = SimpleNamespace(set_meta=saved.__setitem__)
    daemon._pool_ids = {a: "a" * 32, b: "b" * 32}
    daemon._pool_pinned = b

    def load(downlink):
        daemon._metrics = {"stats": {"outbound": {a: {"uplink": 0, "downlink": downlink}}}}

    alive = {a: {"alive": True, "delay": 0.1}, b: {"alive": True, "delay": 0.3}}
    load(0)
    daemon._pool_speed_step(applied, alive, 100.0)
    assert measured == [(b, 20002, "secret", 10.0)]
    load(100_000_000)  # канал занят, но у «a» замера нет вовсе
    daemon._pool_speed_step(applied, alive, 120.0)
    assert [item[0] for item in measured] == [b, a]
    record = json.loads(saved[daemon_module.POOL_SPEED_META])["a" * 32]
    assert record["mbps"] == 25.0 and record["busy"] is True
    daemon._pool_speed_step(applied, alive, 140.0)
    assert len(measured) == 2  # оба замерены недавно
    clock[0] += daemon.cfg.speed.unlimited_hours * 3600
    load(200_000_000)
    daemon._pool_speed_step(applied, alive, 160.0)
    assert len(measured) == 2 and daemon._pool_deferred_since == 160.0
    load(3_000_000_000)
    daemon._pool_speed_step(applied, alive, 160.0 + daemon_module.SPEED_FORCE_AFTER)
    assert [item[0] for item in measured] == [b, a, b]
    daemon._speed_ran = True
    daemon._pool_speed_step(applied, alive, 4000.0)
    assert len(measured) == 3


def test_switching_the_whole_house_on_is_connecting_not_closed(paths):
    """Отчёт М2б.2, дефект 1: шаг до пересборки видел старый конфиг без серверов пула и писал
    «допущенных серверов нет — закрыто». Пока пересборка впереди и пока ядро после перезапуска
    (сборкой или установкой — отчёт m2b2fix, дефект 3) не опробовало серверы пула —
    «подключаются» (traffic нет, события нет), но не дольше POOL_WAIT; дольше — закрыто, как
    прежде. Пока весь дом действует — метка этой загрузки (Paths.house_file)."""
    from xgw.daemon import POOL_WAIT

    paths.xray_config_file.write_text("{}", encoding="utf-8")
    daemon = _daemon(paths)
    daemon.cfg = _cfg("on")
    daemon.cfg.managed.routes = {}
    daemon._pool_checked_at = NOW + 10_000  # допущенные здесь не перепроверяются
    daemon._urgent_rebuild = "бесплатный пул: весь дом"
    daemon._pool_step({"outbounds": [{"tag": "proxy-de-0001"}]}, {"proxy-de-0001": {"alive": True}})
    assert daemon._pool_traffic is None and daemon.events == [] and daemon.api.calls == []
    assert paths.house_file.exists()
    daemon._urgent_rebuild = ""
    applied = {"outbounds": [{"tag": "pool-de-aaaa"}]}
    daemon.wall = lambda: NOW + 20  # сборка перезапустила Xray: проб ещё не было
    daemon._pool_step(applied, {})
    assert daemon._pool_traffic is None and daemon.events == [] and daemon.api.calls == []
    daemon._pool_step(applied, {"pool-de-aaaa": {"alive": True, "delay": 0.2}})
    assert daemon.api.calls == [("pin", "pool", "pool-de-aaaa")]
    assert len(daemon.events) == 1 and "весь дом идёт через" in daemon.events[0]
    # Xray перезапустила установка (конфиг прежний): снова ждём проб — не дольше POOL_WAIT.
    daemon._pool_step(applied, {})
    assert daemon._pool_traffic is None and len(daemon.events) == 1
    daemon.wall = lambda: NOW + 21 + POOL_WAIT
    daemon._pool_step(applied, {})
    assert daemon._pool_traffic["closed"] and "все серверы пула молчат" in daemon.events[-1]
    daemon.cfg = _cfg("observe")
    daemon.cfg.managed.routes = {}
    daemon._pool_step(applied, {})
    assert not paths.house_file.exists()
