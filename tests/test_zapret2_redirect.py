import json

import pytest
from test_zapret2 import Harness

from xgw import zapret2 as z
from xgw.watch.checks import DownloadResult


def test_redirect_resolves_on_vpn_and_direct_uses_same_final_url(monkeypatch):
    h = Harness()
    h.cfg.zapret2.mode = "compare"
    calls = []

    def request(url, port, *args, **kwargs):
        calls.append((url, port, kwargs.get("max_total", 8)))
        if url.endswith("/video"):
            return DownloadResult(False, status=302, phase="headers", kind="http",
                                  location="/final?private=token")
        return DownloadResult(True, status=206, phase="body", downloaded=32768)

    monkeypatch.setattr(h.controller, "_request", request)
    rows = h.controller._compare(h.cfg, h.current, 1234, None)
    assert [port for _, port, _ in calls] == [1234, h.cfg.zapret2.probe_port,
                                            1234, 1234, h.cfg.zapret2.probe_port]
    assert calls[-1][0] == calls[-2][0]
    assert all(0 < timeout <= 8 for _, _, timeout in calls)
    assert rows[2]["redirects"] == 1 and rows[2]["redirect"] == "followed"
    assert all(row["ok"] for row in rows)
    assert "private" not in json.dumps(rows) and "token" not in json.dumps(rows)


@pytest.mark.parametrize("location", ["http://cdn.googlevideo.com/v", "https://outside.test/v",
    "https://u:p@cdn.googlevideo.com/v", "https://cdn.googlevideo.com:444/v", "/v#fragment",
    "\r\n/v", "", "https://[broken", "https://127.0.0.1/v"])
def test_disallowed_redirect_is_never_requested(location):
    h = Harness()
    calls = []

    def request(url, *args, **kwargs):
        calls.append(url)
        return DownloadResult(False, status=302, kind="http", phase="headers", location=location)

    h.controller._request = request
    result, url, hops, reason = h.controller._control(
        h.cfg, h.cfg.zapret2.probe_urls[1], 1234, "secret", "agent", None)
    assert len(calls) == 1 and hops == 0 and reason == "blocked"
    assert result.status == 302 and url == calls[0]


@pytest.mark.parametrize("loop", [True, False])
def test_loop_and_hop_limit_are_bounded(loop):
    h = Harness()
    calls = []

    def request(url, *args, **kwargs):
        calls.append(url)
        return DownloadResult(False, status=307, kind="http", phase="headers",
                              location=url if loop else f"/next{len(calls)}")

    h.controller._request = request
    _, url, hops, reason = h.controller._control(
        h.cfg, h.cfg.zapret2.probe_urls[1], 1234, "secret", "agent", None)
    assert len(calls) == (1 if loop else 6)
    assert hops == (0 if loop else 5) and reason == ("loop" if loop else "hop_limit")
    assert url == calls[-1]


def test_redirects_share_one_time_budget(monkeypatch):
    h = Harness()
    times = iter([10, 10, 17, 17, 19])
    monkeypatch.setattr(z.time, "monotonic", lambda: next(times))
    limits = []

    def request(url, *args, **kwargs):
        limits.append(kwargs["max_total"])
        return DownloadResult(False, status=302, kind="http", phase="headers",
                              location=f"/next{len(limits)}")

    h.controller._request = request
    result, url, hops, reason = h.controller._control(
        h.cfg, h.cfg.zapret2.probe_urls[1], 1234, "secret", "agent", None)
    assert limits == [8, 1] and result.status == 302
    assert url.endswith("/next1") and hops == 1 and reason == "time_limit"


def test_fifth_redirect_can_load_body_and_is_shared_with_direct():
    h = Harness()
    h.cfg.zapret2.probe_urls = [h.cfg.zapret2.probe_urls[1]]
    calls = []

    def request(url, port, *args, **kwargs):
        calls.append((url, port))
        if len(calls) <= 5:
            return DownloadResult(False, status=302, kind="http", phase="headers",
                                  location=f"/next{len(calls)}")
        return DownloadResult(True, status=200, phase="body", downloaded=32768)

    h.controller._request = request
    rows = h.controller._compare(h.cfg, h.current, 1234, None)
    assert len(calls) == 7 and calls[-1][0] == calls[-2][0]
    assert rows[0]["redirects"] == 5 and rows[0]["redirect"] == "followed"
    assert all(row["ok"] for row in rows)


def test_full_chain_reservation_precedes_requests():
    h = Harness()
    h.cfg.zapret2.mode = "compare"
    h.cfg.zapret2.daily_probe_mb = 3
    assert not h.controller._budget(h.cfg)
    assert h.controller.store.get_meta(z.BUDGET) is None
    h.cfg.zapret2.daily_probe_mb = 4
    assert h.controller._budget(h.cfg)
    assert json.loads(h.controller.store.get_meta(z.BUDGET))["bytes"] == 14 * z.PROBE_CHARGE


@pytest.mark.parametrize(("location", "final_http", "limit_mb", "redirect_state", "verdict"), [
    ("https://r2.googlevideo.com/videoplayback?sig=private", 206, 2, "followed", "pass"),
    ("?sig=private", 403, 2, "followed", "fail"),
    ("?sig=private", 302, 2, "hop_limit", "fail"),
    ("?sig=private", None, 1, "budget_unavailable", "fail"),
    ("?expire=1", None, 2, "expired", "fail"),
    ("/videoplayback", None, 2, "loop", "fail"),
    ("https://outside.test/videoplayback", None, 2, "blocked", "fail"),
    ("https://r2.googlevideo.com:bad/videoplayback", None, 2, "blocked", "fail"),
    ("https://r2.googlevideo.com/generate_204", None, 2, "blocked", "fail"),
])
def test_cdn_range_vpn_control_follows_only_one_in_scope_redirect(
    location, final_http, limit_mb, redirect_state, verdict,
):
    h = Harness()
    cdn = "https://r1.googlevideo.com/videoplayback"
    h.cfg.zapret2.probe_urls[1] = cdn
    h.cfg.zapret2.youtube_transport_probe = True
    h.cfg.zapret2.daily_probe_mb = limit_mb
    calls = []

    def request(url, port, *_args, **kwargs):
        calls.append(url)
        assert port == 20011
        assert kwargs["range_end"] == kwargs["min_body"] == z.PROBE_BYTES
        if len(calls) == 1:
            return DownloadResult(False, status=302, kind="http", phase="headers", location=location)
        assert len(calls) == 2 and final_http is not None
        assert 0 < kwargs["max_total"] <= z.VPN_CONTROL_SECONDS
        return DownloadResult(
            final_http == 206, status=final_http, phase="body" if final_http == 206 else "headers",
            downloaded=z.PROBE_BYTES if final_http == 206 else 0, location="?third=private",
        )

    h.controller._request = request
    control = h.controller._fallback_vpn_control(
        h.cfg, h.current, 20011, None, gate_closed=True, routed_back=True,
        stopped=True, target="cdn",
    )
    h.controller._record_vpn_control("cdn", control)
    row, = h.controller.view["vpn_control_attempts"]
    assert len(calls) == (1 if final_http is None else 2)
    assert row["verdict"] == verdict and row["http"] == (final_http or 302)
    assert row["redirect"]["http"] == 302 and row["redirect"]["state"] == redirect_state
    if redirect_state == "followed":
        assert row["redirect"]["host_changed"] == location.startswith("https://r2.")
    assert "private" not in json.dumps(row)
    assert h.controller._read_budget(h.cfg).spent_bytes == len(calls) * z.PROBE_CHARGE
