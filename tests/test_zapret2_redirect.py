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
    assert len(calls) == (1 if loop else 3)
    assert hops == (0 if loop else 2) and reason == ("loop" if loop else "limit")
    assert url == calls[-1]


def test_redirects_share_one_time_budget(monkeypatch):
    h = Harness()
    times = iter([10, 10, 17, 19])
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
    assert url.endswith("/next1") and hops == 1 and reason == "limit"
