"""Постоянные SNI и short_id REALITY между опросами подписки (xgw.reality, отчёт tspu-audit)."""

import logging

import links
import pytest

from xgw import engine, reality
from xgw.config import Config
from xgw.model import raw_to_node
from xgw.parsers.common import parse_link
from xgw.paths import Paths

LOG = logging.getLogger("test")


@pytest.fixture()
def paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    found = Paths.from_env()
    found.ensure()
    return found


def _link(sni, sid, port=443):
    return (f"vless://11111111-2222-3333-4455-666666666661@203.0.113.10:{port}?encryption=none"
            f"&flow=xtls-rprx-vision&security=reality&sni={sni}&fp=chrome"
            f"&pbk={links.FAKE_PBK}&sid={sid}&type=tcp#NL-1")


def _node(sni="a.example.org", sid="aa11", port=443):
    return raw_to_node(parse_link(_link(sni, sid, port)), "main")


def _both(node):
    xray = node.outbound["streamSettings"]["realitySettings"]
    tls = node.singbox.main["tls"]
    return (xray["serverName"], xray["shortId"]), (tls["server_name"], tls["reality"]["short_id"])


def test_changed_pair_is_held_in_xray_and_singbox():
    known = {}
    held, _tracked = reality.stabilize([_node()], known, now=1000.0)
    assert held == 0
    node = _node("b.example.org", "bb22")
    held, tracked = reality.stabilize([node], known, now=4600.0)
    assert held == 1 and tracked[0][1] is node
    assert _both(node) == (("a.example.org", "aa11"), ("a.example.org", "aa11"))


def test_pair_expires_after_a_day_and_then_is_held_again():
    known = {}
    reality.stabilize([_node()], known, now=0.0)
    late = _node("b.example.org", "bb22")
    assert reality.stabilize([late], known, now=reality.KEEP_SECONDS)[0] == 0
    assert _both(late)[0] == ("b.example.org", "bb22")
    again = _node("c.example.org", "cc33")
    assert reality.stabilize([again], known, now=reality.KEEP_SECONDS + 3600)[0] == 1
    assert _both(again)[1] == ("b.example.org", "bb22")


def test_dead_server_takes_the_fresh_pair_sooner():
    known = {}
    _held, tracked = reality.stabilize([_node()], known, now=0.0)
    reality.remember(known, tracked, 0.0)
    fp = tracked[0][1].fingerprint
    status = {"members": [{"fingerprint": fp, "alive": False}], "spares": []}
    dead = reality.dead_fingerprints(status)
    assert dead == {fp}
    early = _node("b.example.org", "bb22")
    assert reality.stabilize([early], known, now=3600.0, dead=dead)[0] == 1
    fresh = _node("b.example.org", "bb22")
    assert reality.stabilize([fresh], known, now=reality.DEAD_SECONDS, dead=dead)[0] == 0
    assert _both(fresh)[0] == ("b.example.org", "bb22")


def test_unchecked_spare_is_not_dead():
    status = {"members": [{"fingerprint": "m1", "alive": True}],
              "spares": [{"fingerprint": "s1", "verdict": None},
                         {"fingerprint": "s2", "verdict": "SLOW"},
                         {"fingerprint": "s3", "verdict": "TIMEOUT"}]}
    assert reality.dead_fingerprints(status) == {"s3"}
    assert reality.dead_fingerprints(None) == frozenset()


def test_variants_and_other_servers_are_untouched():
    known = {}
    reality.stabilize([_node("a.example.org"), _node("b.example.org")], known, now=0.0)
    one, two = _node("c.example.org"), _node("d.example.org")
    assert reality.stabilize([one, two], known, now=60.0)[0] == 0
    assert (_both(one)[0][0], _both(two)[0][0]) == ("c.example.org", "d.example.org")
    other = raw_to_node(parse_link(links.VLESS_WS), "main")
    before = repr(other.outbound)
    assert reality.stabilize([other], known, now=60.0) == (0, [])
    assert repr(other.outbound) == before


def test_unseen_entries_are_forgotten():
    known = {}
    _held, tracked = reality.stabilize([_node()], known, now=0.0)
    reality.remember(known, tracked, 0.0)
    assert len(known) == 1
    reality.remember(known, [], reality.KEEP_UNSEEN)
    assert known == {}


def test_collect_keeps_pair_and_fingerprint_across_fetches(paths, caplog):
    cfg = Config()
    caplog.set_level(logging.INFO, logger="test")

    def collect(sni, sid):
        cfg.manual.links = [_link(sni, sid)]
        return engine.collect(cfg, paths, mark=None, logger=LOG).nodes[0]

    first = collect("a.example.org", "aa11")
    second = collect("b.example.org", "bb22")
    assert second.fingerprint == first.fingerprint
    assert second.outbound == first.outbound
    assert second.singbox.main == first.singbox.main
    assert any("оставлены прежние" in r.getMessage() for r in caplog.records)
    path = reality.reality_file(paths)
    assert oct(path.stat().st_mode & 0o777) == "0o600"
