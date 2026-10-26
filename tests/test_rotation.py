"""Замена участников: мёртвый дольше rotate_after_min → лучший запасной."""

from xgw.apply.rotation import plan_rotation
from xgw.config import Config
from xgw.generator.builder import NodeInfo
from xgw.model import ServerNode


def _node(fp: str, name: str) -> ServerNode:
    return ServerNode(fp, name, "xx", "vless", "203.0.113.1", 443, {}, "test")


def _info(tag: str, fp: str, role: str = "proxy") -> NodeInfo:
    return NodeInfo(fingerprint=fp, tag=tag, probe_tag=f"probe-{tag.split('-',1)[1]}",
                    probe_port=20001, role=role)


def test_no_rotation_when_alive():
    cfg = Config()
    members = [_info("proxy-a-1111", "a"), _info("proxy-b-2222", "b")]
    rotation = plan_rotation(
        alive={"proxy-a-1111": True, "proxy-b-2222": True},
        dead_since={},
        scans={},
        scan_seconds={},
        members=members,
        spares=[],
        cfg=cfg,
        now=1000.0,
    )
    assert rotation is None


def test_dead_too_recently_not_rotated():
    cfg = Config()  # rotate_after_min = 15
    members = [_info("proxy-a-1111", "a")]
    rotation = plan_rotation(
        alive={"proxy-a-1111": False},
        dead_since={"proxy-a-1111": 1000.0},
        scans={},
        scan_seconds={},
        members=members,
        spares=[],
        cfg=cfg,
        now=1000.0 + 14 * 60,
    )
    assert rotation is None


def test_rotation_picks_ok_before_slow():
    cfg = Config()
    members = [_info("proxy-a-1111", "a")]
    spares = [(_info("spare-c-3333", "c", "spare"), _node("33333333", "C")),
              (_info("spare-d-4444", "d", "spare"), _node("44444444", "D")),
              (_info("spare-e-5555", "e", "spare"), _node("55555555", "E"))]
    rotation = plan_rotation(
        alive={"proxy-a-1111": False},
        dead_since={"proxy-a-1111": 1000.0},
        scans={"spare-c-3333": "SLOW", "spare-d-4444": "OK", "spare-e-5555": "FROZEN"},
        scan_seconds={"spare-c-3333": 2.0, "spare-d-4444": 1.5, "spare-e-5555": 9.0},
        members=members,
        spares=spares,
        cfg=cfg,
        now=1000.0 + 16 * 60,
    )
    assert rotation is not None
    assert len(rotation.replacements) == 1
    dead_tag, replacement = rotation.replacements[0]
    assert dead_tag == "proxy-a-1111"
    assert replacement.fingerprint == "44444444"  # OK быстрее SLOW; FROZEN не берём


def test_no_candidates_no_rotation():
    cfg = Config()
    members = [_info("proxy-a-1111", "a")]
    rotation = plan_rotation(
        alive={"proxy-a-1111": False},
        dead_since={"proxy-a-1111": 0.0},
        scans={"spare-c-3333": "FROZEN"},
        scan_seconds={},
        members=members,
        spares=[(_info("spare-c-3333", "c", "spare"), _node("33333333", "C"))],
        cfg=cfg,
        now=1000.0,
    )
    assert rotation is None


def test_node_without_observation_is_not_rotated():
    """Участника нет в observatory (ядро только что запущено) — не мёртвый."""
    members = [_info("proxy-a-1111", "a")]
    spares = [(_info("spare-c-3333", "c", "spare"), _node("33333333", "C"))]
    rotation = plan_rotation(
        alive={}, dead_since={"proxy-a-1111": 0.0}, scans={"spare-c-3333": "OK"},
        scan_seconds={}, members=members, spares=spares, cfg=Config(), now=10_000.0,
    )
    assert rotation is None


def test_rotation_survives_rebuild():
    """plan_rotation → preferred_members → select_nodes: замена закрепляется в составе."""
    from xgw.apply.rotation import preferred_members
    from xgw.generator.builder import build, select_nodes

    cfg = Config()
    cfg.filters.max_members = 2
    nodes = [_node("aaaa0000", "A"), _node("bbbb0000", "B"), _node("cccc0000", "C")]
    for node in nodes:
        node.outbound = {"protocol": "vless", "settings": {}}
    first = build(cfg, select_nodes(nodes, cfg), hosts={}, probe_password="p" * 32)
    members = [info for info in first.nodes if info.role == "proxy"]
    spares = [(info, nodes[2]) for info in first.nodes if info.role == "spare"]
    assert [info.tag for info in members] == ["proxy-xx-aaaa", "proxy-xx-bbbb"]

    rotation = plan_rotation(
        alive={"proxy-xx-aaaa": False, "proxy-xx-bbbb": True},
        dead_since={"proxy-xx-aaaa": 0.0},
        scans={"spare-xx-cccc": "OK"},
        scan_seconds={"spare-xx-cccc": 0.4},
        members=members, spares=spares, cfg=cfg, now=16 * 60.0,
    )
    prefer = preferred_members(members, rotation)
    assert prefer == ["cccc0000", "bbbb0000"]
    second = build(cfg, select_nodes(nodes, cfg, prefer=prefer), hosts={},
                   probe_password="p" * 32)
    assert [info.tag for info in second.nodes] == [
        "proxy-xx-cccc", "proxy-xx-bbbb", "spare-xx-aaaa",
    ]
    # probe-inbounds и их порты при смене ролей не трогаются
    assert {i.probe_tag: i.probe_port for i in first.nodes} == {
        i.probe_tag: i.probe_port
        for i in build(cfg, select_nodes(nodes, cfg, prefer=prefer), hosts={},
                       probe_password="p" * 32,
                       probe_ports={i.probe_tag: i.probe_port for i in first.nodes}).nodes
    }


def test_rotation_keeps_the_country_and_takes_the_faster():
    """Замена мёртвому участнику — той же страны из другой подписки (подписку целиком могли
    заблокировать), потом той же страны; среди равных — лучше по рейтингу (0.2.0). Сервер
    той же страны намного хуже лучшего (меньше SAME_COUNTRY) — берётся лучший."""
    cfg = Config()
    members = [_info("proxy-de-1111", "a")]
    spares = [(_info("spare-nl-3333", "c", "spare"), _node("33333333", "NL")),
              (_info("spare-de-4444", "d", "spare"), _node("44444444", "DE-1")),
              (_info("spare-de-5555", "e", "spare"), _node("55555555", "DE-2")),
              (_info("spare-de-6666", "f", "spare"), _node("66666666", "DE-3"))]
    for _spare, node in spares:
        node.country = "NL" if node.name == "NL" else "DE"
        node.source = "b" if node.name in ("DE-2", "DE-3") else "a"
    common = dict(
        alive={"proxy-de-1111": False}, dead_since={"proxy-de-1111": 1000.0},
        scans={tag: "OK" for tag in ("spare-nl-3333", "spare-de-4444", "spare-de-5555",
                                     "spare-de-6666")},
        scan_seconds={"spare-nl-3333": 0.5, "spare-de-4444": 1.0, "spare-de-5555": 2.0,
                      "spare-de-6666": 3.0},
        members=members, spares=spares, cfg=cfg, now=1000.0 + 16 * 60,
        origins={"a": ("DE", "a")},
    )
    scores = {"33333333": 0.5, "44444444": 0.5, "55555555": 0.4, "66666666": 0.6}
    rotation = plan_rotation(**common, scores=scores)
    assert rotation is not None and rotation.replacements[0][1].name == "DE-3"
    # Без рейтинга — по времени скана, но страна та же и подписка другая.
    assert plan_rotation(**common).replacements[0][1].name == "DE-2"
    # Своя страна втрое хуже соседней — берётся лучший по рейтингу.
    far = {"33333333": 0.9, "44444444": 0.2, "55555555": 0.2, "66666666": 0.2}
    assert plan_rotation(**common, scores=far).replacements[0][1].name == "NL"
