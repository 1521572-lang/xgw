import json
from types import SimpleNamespace

import pytest

from docs.helpers import lan_https_sample
from xgw.desync import lan_control

BOOT = "12345678123412341234123456789abc"
GATEWAY = "192.168.100.1"
CLIENT = {"local_ip": "192.168.100.6", "remote_ip": "1.1.1.1", "local_port": 16000,
          "next_hop": GATEWAY, "http": 200, "bytes": 330, "curl_rc": 0}
TAG = "proxy-de-aabc"
BEFORE = {"unix": 100.0, "monotonic_ns": 10**9, "xray_epoch": f"{BOOT}:41:1",
          "config_sha256": "same", "client_zapret2_rule": False,
          "tags": {TAG: {"group": "xray", "uplink": 0, "downlink": 0}}}
AFTER = BEFORE | {"unix": 102.0, "monotonic_ns": 3 * 10**9}


def log_entry(target, *, source="192.168.100.6:16000", inbound="tproxy-in"):
    return {"_SYSTEMD_UNIT": "xgw-xray.service", "_BOOT_ID": BOOT, "_PID": "41",
            "__REALTIME_TIMESTAMP": "101000000",
            "MESSAGE": f"from {source} accepted tcp:{target} [{inbound} -> {TAG}]"}


@pytest.mark.parametrize("target", ["www.cloudflare.com:443", "1.1.1.1:443"])
def test_lan_https_matches_original_peer_or_sniffed_hostname(target):
    unrelated = [log_entry(target, inbound="http-in"), log_entry(target, source="192.168.100.5:16000"),
                 log_entry("other.example.com:443")]
    result = lan_control.analyze(CLIENT, GATEWAY, [*unrelated, log_entry(target)], BEFORE, AFTER)
    assert result["https_complete"] is True
    assert result["accepted_route"]["state"] == "observed"
    assert result["accepted_route"]["group"] == "xray"
    public = json.dumps(result)
    assert not any(value in public for value in (CLIENT["local_ip"], CLIENT["remote_ip"], TAG, BOOT))


@pytest.mark.parametrize("changes,reason", [
    ({"local_ip": GATEWAY}, "invalid_socket"), ({"local_ip": "127.0.0.1"}, "invalid_socket"),
    ({"next_hop": None}, "client_next_hop_missing"),
    ({"next_hop": "192.168.100.8"}, "client_gateway_mismatch"),
    ({"local_port": True}, "invalid_socket"), ({"remote_ip": "192.168.100.100"}, "invalid_socket"),
])
def test_lan_https_requires_client_next_hop_and_usable_socket(changes, reason):
    result = lan_control.analyze(CLIENT | changes, GATEWAY, [], BEFORE, AFTER)
    assert result["https_complete"] is True
    assert result["accepted_route"] == {"state": "client_route_unconfirmed", "reason": reason}


def test_lan_https_can_report_route_with_incomplete_http_and_rejects_ambiguous_logs():
    rows = [log_entry("1.1.1.1:443"), log_entry("www.cloudflare.com:443")]
    result = lan_control.analyze(CLIENT, GATEWAY, rows, BEFORE, AFTER)
    assert result["accepted_route"] == {"state": "ambiguous"}
    incomplete = lan_control.analyze(CLIENT | {"curl_rc": 28}, GATEWAY, rows[:1], BEFORE, AFTER)
    assert incomplete["https_complete"] is False
    assert incomplete["accepted_route"]["state"] == "observed"


def test_lan_https_sample_uses_one_bounded_unproxied_request_and_checks_next_hop(monkeypatch):
    calls = []

    def run(argv, **options):
        calls.append(argv)
        assert options["timeout"] > 0 and options["capture_output"] is True
        if argv[0] == "curl":
            row = {key: val for key, val in CLIENT.items() if key not in ("curl_rc", "next_hop")}
            row["http"] = str(row["http"])
            return SimpleNamespace(stdout=json.dumps(row), returncode=0)
        return SimpleNamespace(stdout=json.dumps([{"gateway": GATEWAY}]), returncode=0)

    monkeypatch.setattr(lan_https_sample.subprocess, "run", run)
    assert lan_https_sample.sample() == CLIENT
    assert calls[0][:7] == ["curl", "-q", "--noproxy", "*", "--ipv4", "--http1.1", "--connect-timeout"]
    assert calls[1] == ["ip", "-j", "-4", "route", "get", CLIENT["remote_ip"],
                        "from", CLIENT["local_ip"]]
