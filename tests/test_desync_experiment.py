"""Portable contracts only. Real packet/media acceptance is in the handoff."""

import copy
from pathlib import Path, PurePosixPath

import pytest

from docs.helpers import flowseal_lab, nfq_lab
from xgw import nfqws2
from xgw.config import Config
from xgw.desync import experiment as exp
from xgw.desync.schema import ENGINE_PROFILES


def spec(**changes):
    value = dict(url="https://r1.googlevideo.com/videoplayback?token=secret",
                 address="8.8.8.8", network="isp-a", policy_sha256="a" * 64,
                 client="curl-8", protocol="h2", candidate="fake-clone-md5",
                 family="fake-split", route="direct", round="r1")
    return exp.validate_spec(dict(value, **changes))


def test_context_isolation_and_prefix_is_only_a_grouping_hint():
    original = spec()
    ctx = exp.contexts(original, "b" * 64)
    for field, value in (("address", "8.8.8.9"), ("network", "isp-b"), ("protocol", "h3"),
                         ("policy_sha256", "c" * 64), ("client", "chrome"),
                         ("url", "https://r2.googlevideo.com/video")):
        changed = exp.contexts(dict(original, **{field: value}), "b" * 64)
        assert changed["context_id"] != ctx["context_id"]
    same_prefix = exp.contexts(dict(original, address="8.8.8.9"), "b" * 64)
    assert same_prefix["prefix_context_id"] == ctx["prefix_context_id"]
    assert exp.contexts(original, "d" * 64)["context_id"] != ctx["context_id"]
    ipv6 = dict(original, address="2001:4860:4860::8888")
    assert exp.contexts(ipv6, "b")["context_id"] != ctx["context_id"]


def test_private_url_stays_in_config_and_ipv6_resolve_is_bracketed():
    cfg = exp.curl_config(dict(spec(), address="2001:4860:4860::8888"), Path("body"))
    assert 'resolve = "r1.googlevideo.com:443:[2001:4860:4860::8888]"' in cfg
    assert 'noproxy = "*"' in cfg and 'proxy = ""' in cfg
    assert "location" not in cfg and "retry" not in cfg
    assert "token=secret" in cfg
    assert "%{json}" not in cfg and "%{url" not in cfg


@pytest.mark.parametrize("change", [
    {"url": "https://user:pass@example.com/video"}, {"url": "https://example.com/\nheader=x"},
    {"url": "http://example.com/video"}, {"url": "https://example.com:444/video"},
    {"address": "127.0.0.1"}, {"protocol": "auto"}, {"policy_sha256": "x"},
])
def test_invalid_experiment_rejected(change):
    with pytest.raises(ValueError):
        exp.validate_spec(dict(spec(), **change))


def measurement():
    samples = [(float(t), t * 65536) for t in range(46)]
    meta = dict(status="206", bytes=samples[-1][1], seconds=45, http_version="2",
                content_type="video/webm")
    return meta, samples


def test_sustained_requires_time_bytes_protocol_media_and_progress():
    meta, samples = measurement()
    assert exp.classify(meta, 28, samples, "h2") == "PASS_SUSTAINED"
    for change, rc, expected in (({"status": "403"}, 0, "HTTP_REFUSED_OR_STALE_URL"),
                                 ({"http_version": "1.1"}, 0, "PROTOCOL_MISMATCH"),
                                 ({"content_type": "text/html"}, 0, "NOT_MEDIA"),
                                 ({}, 56, "TRANSFER_INTERRUPTED"),
                                 ({"seconds": float("nan")}, 0, "INVALID_MEASUREMENT")):
        assert exp.classify(dict(meta, **change), rc, samples, "h2") == expected
    short = [(0.0, 0), (1.0, 2 * exp.MIN_BYTES)]
    assert exp.classify(dict(meta, bytes=2 * exp.MIN_BYTES, seconds=1), 0, short,
                        "h2") == "SHORT_TRANSFER"
    stalled = [(0.0, 0), (1.0, exp.MIN_BYTES), (45.0, exp.MIN_BYTES)]
    assert exp.classify(dict(meta, bytes=exp.MIN_BYTES), 28, stalled,
                        "h2") == "LATE_STALL_OBSERVED"


def record(candidate="a", family="split", stamp=99, round_id="r1", **extra):
    return dict(schema=1, context_id="a" * 64, created=stamp, candidate=candidate,
                family=family, route="direct", round=round_id, verdict="PASS_SUSTAINED", **extra)


def test_shortlist_needs_two_rounds_and_invalidates_newer_failure():
    a = record()
    b = record(stamp=100, round_id="r2")
    assert exp.select_candidates([a], "a" * 64, 101) == []
    assert exp.select_candidates([a, dict(b, round="r1")], "a" * 64, 101) == []
    assert len(exp.select_candidates([a, b], "a" * 64, 101)) == 1
    failure = dict(b, created=101, round="r3", verdict="LATE_STALL_OBSERVED")
    assert exp.select_candidates([a, b, failure], "a" * 64, 102) == []
    assert exp.select_candidates([a, b], "b" * 64, 101) == []
    assert exp.select_candidates([a, b], "a" * 64, 101 + exp.TTL) == []
    assert exp.select_candidates([dict(a, created=102), dict(b, created=103)],
                                 "a" * 64, 101) == []


def test_shortlist_preserves_family_diversity_and_rejects_vpn_control():
    rows = [record(name, family, stamp, round_id)
            for name, family in (("a", "split"), ("b", "split"), ("c", "disorder"),
                                 ("d", "fake"), ("e", "control"))
            for stamp, round_id in ((99, "r1"), (100, "r2"))]
    selected = exp.select_candidates(rows, "a" * 64, 101)
    assert {r["family"] for r in selected} == {"split", "disorder", "fake"}
    assert exp.select_candidates([dict(row, route="vpn") for row in rows], "a" * 64, 101) == []


def installation():
    return nfqws2.Installation(PurePosixPath("/opt/xgw/nfqws2"), PurePosixPath("/opt/xgw/lua"),
                              dict.fromkeys(nfqws2.BLOBS))


def test_matched_fake_pair_preserves_geometry_and_clone_is_optional():
    assert set(ENGINE_PROFILES) == set(nfqws2.PROFILES)
    for name in ("fake-static-md5", "fake-clone-md5"):
        args = nfqws2.arguments(Config(), installation(), name)
        stages = [a.removeprefix("--lua-desync=") for a in args[5:args.index("--new")]
                  if a.startswith("--lua-desync=")]
        assert stages == list(nfq_lab.STRATEGIES[name])
        assert "optional" in stages[-2] and "tcp_md5" in stages[-2]
        assert stages[-1] == "multisplit:pos=1,midsld"
    assert not any("altorder=" in arg for arg in
                   nfqws2.arguments(Config(), installation(), "hostfakesplit"))
    assert Config().zapret2.engine_profile == "seqovl"


@pytest.mark.parametrize("name", sorted(flowseal_lab.CHAINS))
def test_all_flowseal_chains_have_disjoint_http_tls_and_correct_youtube_scope(name, monkeypatch):
    monkeypatch.setattr(flowseal_lab, "secure_file", lambda *_a, **_kw: None)
    settings = dict(binary="/opt/xgw/nfqws2", strategy=name, data_dir="/opt/xgw/data",
                    reassembly="standard", debug=False, scope="youtube")
    source = copy.deepcopy(flowseal_lab.CHAINS[name])
    incoming = nfqws2.arguments(Config(), installation())[1:]
    for mode in ([], ["--intercept=0"]):
        args = flowseal_lab.build_arguments(incoming + mode, settings)
        assert (args[-1] == "--intercept=0") == bool(mode)
        assert args[1:5] == incoming[:4]
        for block in flowseal_lab._split_new(args):
            if "--payload=tls_client_hello" in block:
                assert "--filter-l7=tls" in block
            if "--payload=http_req" in block:
                assert "--filter-l7=http" in block and "--filter-l7=tls" not in block
            assert sum(a.startswith("--hostlist-domains=") for a in block) == 1
            assert not any(a.startswith(("--hostlist=", "--ipset=")) for a in block)
            assert not any("\\" in a for a in block)
    assert flowseal_lab.CHAINS[name] == source


def test_scope_replaces_all_positive_forms_and_preserves_excludes():
    block = ["--filter-tcp=443", "--hostlist=/a", "--hostlist=@/b", "--ipset=/c",
             "--ipset=@/d", "--hostlist-domains=old.example", "--hostlist-exclude=/e",
             "--ipset-exclude=/f", "--hostlist-exclude-domains=keep.example"]
    assert flowseal_lab.scope_swap(block, "source") == block
    scoped = flowseal_lab.scope_swap(block, "youtube")
    assert scoped[-3:] == block[-3:]
    assert sum(a.startswith("--hostlist-domains=") for a in scoped) == 1
