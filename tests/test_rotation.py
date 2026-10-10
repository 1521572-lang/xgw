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
