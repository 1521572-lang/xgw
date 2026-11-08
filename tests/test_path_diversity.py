"""Волна 3 (ASSUMPTIONS п. 341): замена с другим адресом и TCP/UDP при сопоставимом качестве,
дубликаты не дают ложного запаса, пустой запас объясняется."""

from types import SimpleNamespace

import pytest
from test_daemon import Harness, _started

from xgw import engine
from xgw.apply.rotation import DIVERSE_SHARE, diversity_text, plan_rotation
from xgw.config import Config
from xgw.generator.builder import NodeInfo
from xgw.model import ServerNode
from xgw.paths import Paths
from xgw.watch.states import State
from xgw.watch.status import render_status


@pytest.fixture()
def daemon(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.filters.max_members = 2
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []
    cfg.speed.sticky = False
    cfg.speed.unlimited_hours = cfg.speed.limited_hours = 0
    instance = Harness(cfg, paths)
    yield instance
    instance.store.close()


def _node(fp: str, country: str = "de") -> ServerNode:
    return ServerNode(fp, f"{country.upper()} {fp}", country, "vless", "203.0.113.1", 443, {}, "s")


def _info(tag: str, fp: str, role: str) -> NodeInfo:
    return NodeInfo(fingerprint=fp, tag=tag, probe_tag=f"probe-{tag}", probe_port=1, role=role)


def _rotate(routes, scores, countries=None):
    countries = countries or {}
    member = _info("proxy-m", "m", "proxy")
    spares = [(_info(f"spare-{fp}", fp, "spare"), _node(fp, countries.get(fp, "de")))
              for fp in scores if fp != "m"]
    return plan_rotation(
        {"proxy-m": False}, {}, {info.tag: "OK" for info, _ in spares}, {},
        [member], spares, Config(), 0.0, urgent={"proxy-m"},
        origins={"m": ("de", "s")}, scores=scores, routes=routes,
    )


def test_other_address_wins_among_comparable_and_names_are_not_paths():
    routes = {"m": ("10.0.0.1", "tcp"), "twin": ("10.0.0.1", "tcp"), "far": ("10.0.0.2", "tcp")}
    rotation = _rotate(routes, {"m": 1.0, "twin": 1.0, "far": 0.95})
    assert rotation.replacements[0][1].fingerprint == "far"
    assert rotation.reasons["proxy-m"] == "другой адрес, тот же путь (TCP)"
    routes = {"m": ("10.0.0.1", "tcp"), "twin": ("10.0.0.1", "tcp"), "quic": ("10.0.0.1", "udp")}
    rotation = _rotate(routes, {"m": 1.0, "twin": 1.0, "quic": 0.9})
    assert rotation.replacements[0][1].fingerprint == "quic"
    assert "частичное" in rotation.reasons["proxy-m"]
    routes["both"] = ("10.0.0.3", "udp")
    routes["far"] = ("10.0.0.2", "tcp")
    rotation = _rotate(routes, {"m": 1.0, "far": 1.0, "both": 0.9})
    assert rotation.replacements[0][1].fingerprint == "both"  # различие по обоим — первым
    assert rotation.reasons["proxy-m"] == "другой адрес и другой путь (UDP)"


def test_quality_and_region_stay_ahead_of_diversity():
    routes = {"m": ("10.0.0.1", "tcp"), "twin": ("10.0.0.1", "tcp"), "far": ("10.0.0.2", "udp")}
    weak = _rotate(routes, {"m": 1.0, "twin": 1.0, "far": DIVERSE_SHARE - 0.1})
    assert weak.replacements[0][1].fingerprint == "twin"  # заметно хуже — не берётся
    abroad = _rotate(routes, {"m": 1.0, "twin": 1.0, "far": 1.0}, countries={"far": "nl"})
    assert abroad.replacements[0][1].fingerprint == "twin"  # своя страна раньше разнообразия
    only = _rotate({"m": ("10.0.0.1", "tcp"), "twin": ("10.0.0.1", "tcp")}, {"m": 1, "twin": 1})
    assert only.replacements[0][1].fingerprint == "twin"  # единственный годный не исключается
    assert "другого сопоставимого нет" in only.reasons["proxy-m"]
    assert diversity_text(None, None).startswith("лучший по рейтингу")


def test_routes_use_applied_addresses_without_guessing(daemon, monkeypatch):
    nodes = [
        ServerNode("a", "A", "de", "vless", "one.example.net", 443, {}, "s"),
        ServerNode("b", "B", "de", "vless", "two.example.net", 443, {}, "s"),
        ServerNode("c", "C", "de", "vless", "three.example.net", 443, {}, "s"),
    ]
    hosts = {"one.example.net": ["203.0.113.9", "203.0.113.5"],
             "two.example.net": ["203.0.113.5", "203.0.113.9", "2001:db8::1"]}
    daemon.inventory = SimpleNamespace(nodes=nodes)
    monkeypatch.setattr(engine, "read_json", lambda _path: {"dns": {"hosts": hosts}})
    routes = daemon._routes()
    assert routes["a"] == routes["b"] == ("203.0.113.5", "tcp")  # два имени — один адрес
    assert routes["c"] == ("three.example.net", "tcp")  # адрес не известен — как в подписке


def test_selection_status_explains_an_empty_or_duplicate_reserve(daemon):
    _started(daemon)
    view = daemon.view()
    same = {node.fingerprint: ("10.0.0.1", "tcp") for node in daemon.inventory.nodes}
    daemon._routes = lambda: same
    summary = daemon._selection_status(view)
    assert summary["spares_ok"] == 3 and summary["paths"] == 1 and summary["other_paths"] == 0
    assert "тех же адресах" in summary["note"]
    spare = next(info for info in view if info.role == "spare")
    daemon.home_exits.add(spare.fingerprint)  # не годится в замену — и в запасе не считается
    assert daemon._selection_status(view)["spares_ok"] == 2
    daemon._fresh_scans = lambda: {}
    assert "годных запасных нет" in daemon._selection_status(view)["note"]
    assert daemon._selection_status([])["note"] == "запасных нет"


def test_replacement_says_why_in_status_and_events_without_addresses(daemon):
    _started(daemon)
    members = daemon.tags("proxy")
    view = daemon.view()
    mine = next(info.fingerprint for info in view if info.tag == members[0])
    routes = {node.fingerprint: ("10.0.0.1", "tcp") for node in daemon.inventory.nodes}
    far = next(info.fingerprint for info in view if info.role == "spare")
    routes[far] = ("10.0.0.9", "udp")
    assert mine in routes
    daemon._routes = lambda: routes
    daemon.home_exits.add(mine)  # замена без ожидания — как у сервера с выходом в свою страну
    daemon.next_refresh = daemon.t + 86400
    daemon.t += 20
    assert daemon.tick() is State.HEALTHY and members[0] not in daemon.tags("proxy")
    rotation = [event for event in daemon.events() if event.startswith("rotation:")]
    assert len(rotation) == 1 and "другой адрес и другой путь (UDP)" in rotation[0]
    assert "10.0.0." not in rotation[0]
    status = daemon.status()
    assert status["selection"]["last"]["reasons"] == ["другой адрес и другой путь (UDP)"]
    text = render_status(status)
    assert "Запас:" in text and "другой адрес и другой путь (UDP)" in text
    assert "10.0.0." not in str(status["selection"])
