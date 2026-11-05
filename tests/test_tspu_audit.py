"""Аудит противодействия ТСПУ 05.11.2026: отпечаток TLS у Xray, браузерные UA проб, разброс
сроков плановых замеров скорости."""

from xgw.config import DEFAULT_PROBE_UA
from xgw.generator import builder
from xgw.watch import checks, speed


def _outbound(**stream):
    return {"tag": "proxy-x", "protocol": "vless", "streamSettings": stream}


def test_xray_tls_gets_a_stable_browser_fingerprint_unless_the_link_has_one():
    plain = _outbound(network="ws", security="tls", tlsSettings={"serverName": "a.example"})
    builder._modernize(plain)
    assert plain["streamSettings"]["tlsSettings"] == {
        "serverName": "a.example", "fingerprint": "chrome"}
    given = _outbound(network="tcp", security="tls", tlsSettings={"fingerprint": "firefox"})
    builder._modernize(given)
    assert given["streamSettings"]["tlsSettings"]["fingerprint"] == "firefox"
    reality = _outbound(network="tcp", security="reality", realitySettings={"fingerprint": "ios"})
    builder._modernize(reality)
    assert "tlsSettings" not in reality["streamSettings"]
    quic = _outbound(network="xhttp", security="tls", tlsSettings={"alpn": ["h3"]})
    builder._modernize(quic)
    assert "fingerprint" not in quic["streamSettings"]["tlsSettings"]
    none = _outbound(network="tcp", security="none")
    builder._modernize(none)
    assert "tlsSettings" not in none["streamSettings"]
    split = _outbound(network="xhttp", security="reality", xhttpSettings={
        "downloadSettings": {"address": "d.example", "security": "tls"}})
    builder._modernize(split)
    leg = split["streamSettings"]["xhttpSettings"]["downloadSettings"]
    assert leg["tlsSettings"] == {"fingerprint": "chrome"}


def test_probe_user_agent_comes_from_a_browser_pool_unless_set():
    seen = {checks.pick_agent(DEFAULT_PROBE_UA) for _ in range(200)}
    assert seen <= set(checks.BROWSER_AGENTS) and len(seen) > 3
    assert all("xgw" not in agent.lower() for agent in checks.BROWSER_AGENTS)
    assert checks.pick_agent("") in checks.BROWSER_AGENTS
    assert checks.pick_agent("MyAgent/1.0") == "MyAgent/1.0"
    request = checks._request("GET", "/", {"Host": "h"}, "").decode()
    assert "xgw/" not in request and "User-Agent: Mozilla/5.0" in request


def test_speed_due_factor_spreads_servers_and_is_stable_per_measurement():
    factors = [speed.due_factor(f"server-{index}", 1_700_000_000) for index in range(400)]
    assert min(factors) >= 0.8 and max(factors) <= 1.2
    assert max(factors) - min(factors) > 0.3
    assert speed.due_factor("a", 1_700_000_000.4) == speed.due_factor("a", 1_700_000_000.9)
    assert speed.due_factor("a", 1_700_000_000) != speed.due_factor("a", 1_700_021_600)
