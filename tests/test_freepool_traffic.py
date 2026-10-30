"""Веха М2б.1: устройство через бесплатный пул — допуск серверов пула, балансировщик «pool» в
рабочем конфиге, «закрыто» без серверов, выбор в панели и закреплённый сервер у демона."""

import logging
from types import SimpleNamespace

import pytest

from xgw import actions, engine, managed
from xgw.config import Config
from xgw.freepool import pool, providers, traffic
from xgw.freepool.models import ProviderResult, Status
from xgw.freepool.store import PoolStore
from xgw.generator import builder, diff
from xgw.model import raw_to_node
from xgw.parsers.common import parse_links_text
from xgw.paths import Paths

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


def test_pool_composition_keeps_applied_servers_first():
    """Сборка не перетасовывает «pool»: применённые и ещё допущенные — первыми; сервер,
    совпавший с сервером подписки, — не в пуле."""
    found = [SimpleNamespace(node=SimpleNamespace(fingerprint=name)) for name in "abcd"]
    chosen = traffic.choose(found, {"c"}, exclude={"b"}, limit=2)
    assert [item.node.fingerprint for item in chosen] == ["c", "a"]


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
                        ("_pool_names", {}), ("_pool_traffic", None)):
        setattr(daemon, name, value)
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
        {"id": "aaaa", "tag": "pool-de-aaaa", "alive": True, "delay_ms": 300},
        {"id": "bbbb", "tag": "pool-de-bbbb", "alive": True, "delay_ms": 100}]
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
