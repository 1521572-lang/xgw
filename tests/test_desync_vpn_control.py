import hashlib
import json

import pytest

from xgw import config, zapret2
from xgw.desync import vpn_control
from xgw.generator import singbox
from xgw.paths import Paths
from xgw.watch.checks import DownloadResult

NATIVE = "proxy-nl-aabb"
BRIDGE = "proxy-de-ccdd"
TRACE = "https://trace.example.test/cdn-cgi/trace"


def applied_config():
    return {
        "inbounds": [
            {"tag": "http-in", "protocol": "http", "listen": "127.0.0.1", "port": 17001},
            *({"tag": "probe-" + tag[6:], "port": port, "protocol": "http",
               "listen": "127.0.0.1",
               "settings": {"accounts": [{"user": "xgw", "pass": "secret-pass"}]}}
              for tag, port in ((NATIVE, 17002), (BRIDGE, 17003))),
        ],
        "outbounds": [{"tag": NATIVE, "protocol": "vless"},
                      {"tag": BRIDGE, **singbox.bridge_outbound(18001, "d", "secret-bridge")}],
        "routing": {"rules": [
            {"type": "field", "inboundTag": [zapret2.PROBE], "outboundTag": "block"},
            *({"type": "field", "inboundTag": ["probe-" + tag[6:]], "outboundTag": tag}
              for tag in (NATIVE, BRIDGE)),
        ]},
    }


def test_vpn_control_only_uses_unambiguous_pinned_listeners():
    applied = applied_config()
    assert list(vpn_control._targets(applied)) == ["http_in", "xray", "sing-box"]
    applied["inbounds"][2]["listen"] = "0.0.0.0"
    assert list(vpn_control._targets(applied)) == ["http_in", "xray"]
    applied["routing"]["rules"].insert(0, {"type": "field", "outboundTag": "direct"})
    assert list(vpn_control._targets(applied)) == ["http_in"]
    applied["outbounds"].append({"tag": zapret2.DIRECT, "protocol": "freedom"})
    assert not vpn_control._targets(applied)


@pytest.mark.parametrize("body", [b"no trace", b"ip=127.0.0.1", b"ip=224.0.0.1", b"ip=\xff",
                                  b"ip=fe80::1%eth0", b"ip=1.1.1.1\nip=8.8.8.8"])
def test_vpn_control_requires_one_public_address(body):
    assert vpn_control._exit_address(body) is None


@pytest.fixture
def rig(tmp_path, monkeypatch):
    raw = json.dumps(applied_config()).encode()
    cfg = config.Config()
    cfg.probe.trace_url = TRACE

    def snapshot(stamp, counter, epoch="same-epoch"):
        return {"monotonic_ns": stamp, "xray_epoch": epoch, "client_zapret2_rule": False,
                "config_sha256": hashlib.sha256(raw).hexdigest(),
                "tags": {
                    NATIVE: {"group": "xray", "uplink": counter, "downlink": counter},
                    BRIDGE: {"group": "sing-box", "uplink": counter, "downlink": counter},
                }}

    replies = iter((snapshot(1000, 0), snapshot(2000, 327)))
    monkeypatch.setattr(vpn_control.evidence, "snapshot", lambda *_a, **_kw: next(replies))
    monkeypatch.setattr(vpn_control.evidence, "_read_config", lambda _path: raw)
    monkeypatch.setattr(vpn_control.config, "load", lambda _path: (cfg, []))
    return Paths(tmp_path), cfg, snapshot


def test_vpn_control_preview_sends_no_requests(rig, monkeypatch):
    def forbidden(*_a, **_kw):
        pytest.fail("network request in preview")

    monkeypatch.setattr(vpn_control.checks, "http_get_via_proxy", forbidden)
    result = vpn_control.observe(rig[0])
    assert not result["live"]
    assert all(row == {"result": "available"} for row in result["paths"].values())


def test_vpn_control_runs_bounded_separate_requests_and_redacts_results(rig, monkeypatch):
    ports = []

    def probe(host, port, url, **kwargs):
        ports.append(port)
        assert (host, url) == ("127.0.0.1", TRACE)
        assert (kwargs["max_total"], kwargs["max_bytes"], kwargs["keep_body"]) == (8, 4096, 4096)
        assert kwargs["proxy_pass"] == ("" if port == 17001 else "secret-pass")
        body = b"ip=2606:4700::1111\n" if port == 17003 else b"ip=8.8.4.4\nprivate=token\n"
        return DownloadResult(True, status=200, body=body, downloaded=len(body))

    monkeypatch.setattr(vpn_control.checks, "http_get_via_proxy", probe)
    result = vpn_control.observe(rig[0], live=True)
    assert ports == [17001, 17002, 17003]
    assert result["paths"]["http_in"]["result"] == "https_with_exit"
    assert result["paths"]["http_in"]["pinned_outbound_counters_increased"] is None
    assert result["paths"]["xray"]["exit_matches_http_in"] is True
    assert result["paths"]["xray"]["pinned_outbound_counters_increased"] is True
    assert result["paths"]["sing-box"]["exit_matches_http_in"] is False
    assert result["paths"]["sing-box"]["exit_family"] == 6
    published = json.dumps(result)
    assert all(value not in published for value in (TRACE, NATIVE, BRIDGE, "8.8.4.4", "secret"))


def test_vpn_control_does_not_accept_response_cut_at_limit(monkeypatch):
    result = DownloadResult(True, status=200, body=b"ip=8.8.4.4\n", downloaded=4096)
    monkeypatch.setattr(vpn_control.checks, "http_get_via_proxy", lambda *_a, **_kw: result)
    summary, address = vpn_control._probe(vpn_control._Target(17001), TRACE, "")
    assert summary["result"] == "failed" and address is None


def test_vpn_control_drops_results_if_xray_changes(rig, monkeypatch):
    paths, _, snapshot = rig
    replies = iter((snapshot(1000, 0), snapshot(2000, 0, epoch="restarted")))
    monkeypatch.setattr(vpn_control.evidence, "snapshot", lambda *_a, **_kw: next(replies))
    monkeypatch.setattr(vpn_control.checks, "http_get_via_proxy",
                        lambda *_a, **_kw: DownloadResult(False, error="private failure"))
    with pytest.raises(vpn_control.evidence.EvidenceError, match="incomparable_snapshots"):
        vpn_control.observe(paths, live=True)
