import copy
import importlib.util
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from xgw.generator import builder, singbox

NODE = builder.NodeInfo("fixture", "proxy-test", "probe-test", 12345, "proxy")
PASSWORD = "PRIVATE"
PAGE = "https://www.youtube.com/watch?v=fixture"


@pytest.fixture
def helper(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "docs/helpers/video_probe_browser_check.py"
    spec = importlib.util.spec_from_file_location("video_probe_browser_fixture", path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    monkeypatch.setattr(sys, "path", sys.path[:])
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def before(helper):
    applied = {
        "inbounds": [{
            "tag": NODE.probe_tag, "listen": "127.0.0.1",
            "port": NODE.probe_port, "protocol": "http",
            "settings": {"accounts": [{"user": builder.PROBE_USER, "pass": PASSWORD}]},
        }],
        "routing": {"rules": [
            {"type": "field", "inboundTag": [NODE.probe_tag], "outboundTag": NODE.tag},
        ]},
        "outbounds": [
            {"tag": NODE.tag, "protocol": "vless"},
            {"tag": "another", "protocol": "vmess"},
        ],
    }
    state = {"members": [{"tag": NODE.tag, "alive": True, "cost": 0}]}
    return helper.Checkpoint(state, ("cfg", "panel"), b"pids", "before", applied, {})


def test_unrelated_rotation_is_accepted_but_selected_route_must_match(helper, before):
    path = helper.selected_path(before, NODE, PASSWORD)
    after = copy.deepcopy(before)
    after.xray["outbounds"][-1] = {"tag": "rotated", "protocol": "trojan"}
    after.xray["routing"]["rules"].insert(
        0, {"type": "field", "inboundTag": ["probe-other"], "outboundTag": "rotated"})
    assert helper.compare(before, after, path, NODE, PASSWORD) == "ok"
    after.xray["routing"]["rules"][1]["outboundTag"] = "rotated"
    assert helper.compare(before, after, path, NODE, PASSWORD) == "selected_path_changed"


def test_selected_singbox_bridge_follows_detour_but_ignores_other_outbounds(helper, before):
    before.xray["outbounds"][0] = singbox.bridge_outbound(23456, "d", "BRIDGE") | {"tag": NODE.tag}
    before.singbox = {
        "inbounds": [{"tag": "bridge", "listen": "127.0.0.1", "listen_port": 23456}],
        "route": {"rules": [{"inbound": ["bridge"], "action": "route", "outbound": "selected"}]},
        "outbounds": [{"tag": "selected", "detour": "parent"}, {"tag": "unrelated"}],
        "endpoints": [{"tag": "parent", "type": "wireguard"}],
    }
    path = helper.selected_path(before, NODE, PASSWORD)
    after = copy.deepcopy(before)
    after.singbox["outbounds"].pop()
    assert helper.compare(before, after, path, NODE, PASSWORD) == "ok"
    after.singbox["endpoints"][0]["server"] = "changed"
    assert helper.compare(before, after, path, NODE, PASSWORD) == "selected_path_changed"


@pytest.mark.parametrize(
    "change", ["unrelated", "before_replay", "after_replay", "process", "browser_error"],
)
def test_receipt_and_replay_follow_selected_path(
    helper, before, monkeypatch, tmp_path, capsys, change,
):
    receipt = tmp_path / "result.json"
    after_browser, after_replay = copy.deepcopy(before), copy.deepcopy(before)
    after_browser.xray_digest = after_replay.xray_digest = "rotated"
    if change == "before_replay":
        after_browser.xray["inbounds"][0]["port"] += 1
    if change == "after_replay":
        after_replay.xray["outbounds"][0]["protocol"] = "trojan"
    if change == "process":
        after_browser.units = b"changed"
    checkpoints = iter([before, after_browser, after_replay])

    def capture(_paths):
        point = next(checkpoints)
        if point is not before:
            saved = json.loads(receipt.read_bytes())
            assert saved["playback"] and saved["verification"] == "pending"
            assert ("video" in saved) == (point is after_replay)
        return point

    class Relay:
        def __init__(self, *_args):
            self.stopped = threading.Event()
            self.spent = 1000

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def serve_forever(self):
            pass

        def shutdown(self):
            pass

    cfg = SimpleNamespace(
        zapret2=SimpleNamespace(mode="off", probe_urls=[PAGE], domains=["domain:youtube.com"]),
        media=SimpleNamespace(youtube_sign_url=""),
    )
    monkeypatch.setattr(sys, "argv", ["helper", "--state", str(receipt)])
    monkeypatch.setattr(helper.pwd, "getpwnam", lambda _name: SimpleNamespace(pw_uid=1000))
    monkeypatch.setattr(helper.shutil, "which", lambda *_a, **_kw: "firefox")
    monkeypatch.setattr(helper.config, "load", lambda _path: (cfg, []))
    monkeypatch.setattr(helper, "checkpoint", capture)
    monkeypatch.setattr(helper.builder, "applied_nodes", lambda _applied: [NODE])
    monkeypatch.setattr(helper.video_browser, "Relay", Relay)
    expected_stages = [
        "relay_ready", "marionette_port_reserved", "firefox_started", "marionette_ready",
    ]

    def observe(_firefox, _user, _page, _domains, _relay, progress):
        for index, stage in enumerate(expected_stages[1:], 2):
            progress(stage)
            saved = json.loads(receipt.read_bytes())
            assert saved["stages"] == expected_stages[:index]
            assert saved["verification"] == "pending"
        if change == "browser_error":
            raise OSError("PRIVATE")
        return "PRIVATE", "Firefox", "played", True

    monkeypatch.setattr(helper.video_browser, "browser", observe)
    calls = []

    def replay(*args):
        calls.append(args)
        return {"result": "browser_video_verified", "expires_in": 900, "video": {
            "http": 206, "bytes": 16384, "video_mime": True, "verdict": "ok",
        }}

    monkeypatch.setattr(helper.video_probe, "replay", replay)
    if change == "browser_error":
        with pytest.raises(OSError):
            helper.main()
        assert json.loads(receipt.read_bytes())["stages"] == expected_stages
        assert not calls and "PRIVATE" not in receipt.read_text() + capsys.readouterr().out
        return
    expected = "ok" if change == "unrelated" else "selected_path_changed"
    if change == "process":
        expected = "gateway_settings_or_processes_changed"
    assert helper.main() == (0 if expected == "ok" else 2)
    saved = json.loads(receipt.read_bytes())
    assert saved["verification"] == expected and saved["xray_config_changed"]
    assert saved["stages"] == expected_stages
    assert bool(calls) == (change in ("unrelated", "after_replay"))
    assert receipt.stat().st_mode & 0o077 == 0
    output = capsys.readouterr().out
    assert ("RESULT browser_video_verified" in output) == (expected == "ok")
    assert "PRIVATE" not in output + receipt.read_text()
