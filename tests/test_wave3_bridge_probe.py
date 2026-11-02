"""Bridge selector/privacy/limits only; no real requests or gateway operations."""

import copy
import importlib.util
import json
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


def probe():
    path = Path(__file__).parent / "stand/wave3_bridge_probe.py"
    spec = importlib.util.spec_from_file_location("bridge_probe", path)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    return tool


def config():
    return {
        "inbounds": [
            {
                "type": "socks",
                "tag": "sb-in-1234abcd-d",
                "listen": "127.0.0.1",
                "listen_port": 24000,
                "users": [{"username": "xgw-d", "password": "PRIVATE"}],
            }
        ],
        "outbounds": [{"tag": "sb-out-1234abcd-d", "type": "hysteria2"}],
        "route": {
            "rules": [
                {
                    "inbound": ["sb-in-1234abcd-d"],
                    "action": "route",
                    "outbound": "sb-out-1234abcd-d",
                },
                {"action": "reject"},
            ]
        },
    }


def test_only_existing_default_profile_selected():
    tool = probe()
    value = config()
    extra = copy.deepcopy(value["inbounds"][0])
    extra.update(tag="sb-in-1234abcd-f", listen_port=24001)
    value["inbounds"].append(extra)
    assert [(x["port"], x["protocol"]) for x in tool.bridges(value)] == [(24000, "hysteria2")]


@pytest.mark.parametrize("change", ["public_listener", "direct_outbound", "broad_route"])
def test_ambiguous_or_direct_route_cannot_be_counted_as_proxy_success(change):
    tool = probe()
    value = config()
    if change == "public_listener":
        value["inbounds"][0]["listen"] = "0.0.0.0"
    elif change == "direct_outbound":
        value["outbounds"][0]["type"] = "direct"
    else:
        value["route"]["rules"].insert(0, {"action": "route", "outbound": "direct"})
    with pytest.raises(ValueError):
        tool.bridges(value)


def test_stdin_config_rejects_injected_options():
    tool = probe()
    with pytest.raises(ValueError):
        tool.quoted('pass\nurl = "https://elsewhere.invalid"')
    assert tool.quoted('a"\\b') == '"a\\"\\\\b"'


@pytest.mark.parametrize(
    "size,verify,good", [(32769, 0, True), (32768, 0, False), (32769, 1, False)]
)
def test_curl_metadata_privacy_and_required_body_tls(size, verify, good, monkeypatch):
    tool = probe()
    seen = {}

    def fake(argv, **kwargs):
        seen.update(argv=argv, **kwargs)
        raw = {
            "http_code": 206,
            "size_download": size,
            "time_total": 0.5,
            "ssl_verify_result": verify,
            "num_redirects": 0,
            "url_effective": "PRIVATE_URL",
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(raw).encode() + b"\nidentity")

    monkeypatch.setattr(tool.subprocess, "run", fake)
    result = tool.request(
        "/curl",
        {"port": 24000, "user": "xgw-d", "password": "PRIVATE_PASS"},
        "https://example.invalid/PRIVATE_URL",
    )
    assert result["body_ok"] is good
    assert "PRIVATE" not in json.dumps(result) and "PRIVATE" not in " ".join(seen["argv"])
    assert b"PRIVATE_PASS" in seen["input"]
    assert seen["argv"][1] == "-q" and seen["timeout"] == 8
    assert "--insecure" not in seen["argv"] and "--location" not in seen["argv"]
    assert seen["argv"][seen["argv"].index("--max-filesize") + 1] == "131072"
    assert seen["env"] == {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "LANG": "C"}


def test_request_timeout_is_unknown_not_a_body_success(monkeypatch):
    tool = probe()

    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("private", 8)

    monkeypatch.setattr(tool.subprocess, "run", fail)
    assert tool.request(
        "/curl", {"port": 24000, "user": "xgw-d", "password": "secret"}, "https://example.invalid/"
    ) == {"outcome": "WORKER_TIMEOUT", "body_ok": False}


def test_listener_must_belong_to_process_not_only_network_namespace(tmp_path):
    tool = probe()
    process = tmp_path / "99"
    for path in [process / "fd", process / "net", process / "ns", tmp_path / "self/ns"]:
        path.mkdir(parents=True, exist_ok=True)
    (process / "ns/net").symlink_to("net:[11]")
    (tmp_path / "self/ns/net").symlink_to("net:[11]")
    (process / "fd/7").symlink_to("socket:[123]")
    tcp = process / "net/tcp"
    tcp.write_text("header\n0: 0100007F:5DC0 00000000:0000 0A 0:0 00:0 0 1000 0 123\n")
    assert tool.owns_listener(99, 24000, tmp_path) is True
    tcp.write_text("header\n0: 0100007F:5DC0 00000000:0000 0A 0:0 00:0 0 1000 0 999\n")
    assert tool.owns_listener(99, 24000, tmp_path) is False


def test_pin_read_is_private_and_cannot_create_missing_database(tmp_path, monkeypatch):
    tool = probe()
    database = tmp_path / "state.db"
    monkeypatch.setattr(tool.reader, "PATHS", SimpleNamespace(db_file=database))
    assert tool.pin_token() is None and not database.exists()
    conn = sqlite3.connect(database)
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO meta VALUES (?, ?)", ("pin", "PRIVATE_SELECTION"))
    conn.commit()
    conn.close()
    before = database.read_bytes()
    token = tool.pin_token()
    assert isinstance(token, bytes) and b"PRIVATE_SELECTION" not in token
    assert database.read_bytes() == before
