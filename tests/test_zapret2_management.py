"""Policy commands. Windows mocks only flock; Ubuntu exercises the real lock."""

import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest

from xgw import config, managed
from xgw.desync import schema
from xgw.watch import zapret2_management as management


@pytest.fixture
def store(tmp_path, monkeypatch):
    if sys.platform == "win32":
        lock = threading.Lock()

        @contextmanager
        def locked(*args, **kwargs):
            with lock:
                yield

        monkeypatch.setattr(managed, "file_lock", locked)
    cfg = tmp_path / "config.toml"
    cfg.write_text('[capture]\nlocal=true\nfail_mode="closed"\nhold="block"\n'
                   '[network]\nquic_mode="reject"\n', encoding="utf-8")
    panel = managed.path_for(cfg)
    panel.write_text(json.dumps({"links": [], "extension": {"keep": [1, 2]},
                                "zapret2": {"engine": "auto"}}), encoding="utf-8")
    return cfg, panel


def key(cfg):
    return schema.fingerprint(config.load(cfg)[0].desync)


def send(cfg, patch, *, expected=None, action="settings", **kwargs):
    return management.command(cfg, action, {
        "expected": key(cfg) if expected is None else expected,
        "mode" if action == "mode" else "settings": patch,
    }, ready=kwargs.get("ready", True), capture={"mode": kwargs.get("capture", "on")},
       budget_reader=kwargs.get("budget_reader", lambda proposed:
           management.zapret2.read_probe_budget(None, proposed.zapret2.daily_probe_mb, now=0)))


def test_atomic_edit_preserves_unrelated_engine_and_toml(store):
    cfg, panel = store
    original = cfg.read_bytes()
    result = send(cfg, {"retry_seconds": 120})
    assert result["ok"] and result["changed"]
    assert result["config_key"] == key(cfg)
    actual = json.loads(panel.read_text())
    assert actual["extension"] == {"keep": [1, 2]}
    assert actual["desync"]["engine"]["engine"] == "auto"
    assert cfg.read_bytes() == original


def test_noop_and_stale_never_rewrite(store):
    cfg, panel = store
    old = key(cfg)
    before = panel.read_bytes(), panel.stat().st_mtime_ns
    assert send(cfg, {"retry_seconds": 300})["code"] == "unchanged"
    assert (panel.read_bytes(), panel.stat().st_mtime_ns) == before
    assert send(cfg, {"retry_seconds": 120})["ok"]
    before = panel.read_bytes(), panel.stat().st_mtime_ns
    assert send(cfg, {"retry_seconds": 120}, expected=old)["code"] == "conflict"
    assert (panel.read_bytes(), panel.stat().st_mtime_ns) == before


@pytest.mark.parametrize("patch", [
    {"engine": "off"}, {"mode": "standalone"}, {"binary": "/tmp/tool"},
    {"queue_num": 201}, {"strategy": schema.LIVE_STRATEGY},
    {"retry_seconds": True}, {"daily_probe_mb": 0}, {"domains": []},
    {"probe_urls": ["https://elsewhere.test/?private-token"]},
    {"probe_urls": ["https://youtube.com/?bad\nprivate-token"]},
])
def test_invalid_edit_is_private_and_never_writes(store, patch):
    cfg, panel = store
    before = panel.read_bytes()
    result = send(cfg, patch)
    assert not result["ok"]
    assert "private-token" not in json.dumps(result)
    assert panel.read_bytes() == before

def test_probes_are_write_only_preserved_when_omitted_and_explicitly_cleared(store):
    cfg, panel = store
    urls = ["https://www.youtube.com/watch?v=private-token",
            "https://r1.googlevideo.com/videoplayback?sig=private-token"]
    result = send(cfg, {"probe_urls": urls, "youtube_transport_probe": True})
    assert result["ok"] and "private-token" not in json.dumps(result)
    assert send(cfg, {"retry_seconds": 120})["ok"]
    assert config.load(cfg)[0].zapret2.probe_urls == urls
    assert send(cfg, {"probe_urls": []})["ok"]
    cleared = config.load(cfg)[0].zapret2
    assert cleared.probe_urls == [] and cleared.youtube_transport_probe and cleared.mode == "off"
    before = panel.read_bytes()
    assert b"private-token" not in before
    assert send(cfg, {"probe_urls": [], "youtube_transport_probe": True})["code"] == "unchanged"
    assert send(cfg, "selective", action="mode")["code"] == "invalid"
    assert panel.read_bytes() == before
    assert send(cfg, {"retry_seconds": 180})["ok"]
    assert send(cfg, {"probe_urls": urls})["ok"]
    assert send(cfg, "selective", action="mode")["ok"]


def test_modes_require_prerequisites_and_do_not_change_engine(store):
    cfg, panel = store
    before = panel.read_bytes()
    assert send(cfg, "selective", action="mode")["code"] == "blocked"
    assert send(cfg, "compare", action="mode")["code"] == "invalid"
    assert send(cfg, "standalone", action="mode", ready=False)["code"] == "blocked"
    assert send(cfg, "standalone", action="mode", capture="off")["code"] == "blocked"
    assert panel.read_bytes() == before
    assert send(cfg, "standalone", action="mode")["ok"]
    assert config.load(cfg)[0].zapret2.engine == "auto"
    assert send(cfg, "off", action="mode", ready=False, capture="off")["ok"]
    assert config.load(cfg)[0].zapret2.engine == "auto"


def test_replacing_only_the_cdn_retains_the_page_and_checks_the_revision(store, monkeypatch):
    cfg, panel = store
    page = "https://www.youtube.com/t/terms"
    old_cdn = "https://r1.googlevideo.com/videoplayback?expire=1&sig=previous"
    assert send(cfg, {"youtube_transport_probe": True, "probe_urls": [page, old_cdn]})["ok"]
    old_key = key(cfg)
    cdn = "https://r2.googlevideo.com/videoplayback?expire=2000000000&sig=secret"
    result = send(cfg, {"cdn_probe_url": cdn})
    assert result["ok"] and result["config_key"] != old_key and "secret" not in str(result)
    assert config.load(cfg)[0].zapret2.probe_urls == [page, cdn]
    assert "cdn_probe_url" not in panel.read_text()
    before = panel.read_bytes(), panel.stat().st_mtime_ns
    assert send(cfg, {"cdn_probe_url": old_cdn}, expected=old_key)["code"] == "conflict"
    assert send(cfg, {"cdn_probe_url": cdn})["code"] == "unchanged"
    assert (panel.read_bytes(), panel.stat().st_mtime_ns) == before
    assert send(cfg, "selective", action="mode")["ok"]
    assert send(cfg, {"cdn_probe_url": old_cdn})["code"] == "blocked"
    assert config.load(cfg)[0].zapret2.probe_urls == [page, cdn]
    monkeypatch.setattr(management.time, "time", lambda: 2000000001)
    refreshed = "https://r3.googlevideo.com/videoplayback?expire=2000000600&sig=new"
    assert send(cfg, {"cdn_probe_url": refreshed})["code"] == "saved"
    active = config.load(cfg)[0].zapret2
    assert active.mode == "selective" and active.probe_urls == [page, refreshed]


def test_cdn_only_requires_saved_pair_and_rejects_conflicting_or_invalid_inputs(store):
    cfg, panel = store
    cdn = "https://r1.googlevideo.com/generate_204"
    before = panel.read_bytes()
    assert send(cfg, {"cdn_probe_url": cdn})["code"] == "blocked"
    assert panel.read_bytes() == before
    assert send(cfg, {"youtube_transport_probe": True, "probe_urls": [
        "https://www.youtube.com/t/terms", cdn,
    ]})["ok"]
    before = panel.read_bytes()
    for patch in (
        {"cdn_probe_url": None},
        {"cdn_probe_url": cdn, "probe_urls": []},
        {"cdn_probe_url": cdn, "youtube_transport_probe": False},
        {"cdn_probe_url": "https://other.test/videoplayback?secret"},
    ):
        result = send(cfg, patch)
        assert not result["ok"] and "secret" not in str(result)
        assert panel.read_bytes() == before


def test_can_enable_transport_and_replace_cdn_of_saved_pair_in_one_edit(store):
    cfg, panel = store
    page = "https://www.youtube.com/t/terms"
    cdn = "https://r1.googlevideo.com/generate_204"
    assert send(cfg, {"youtube_transport_probe": False, "probe_urls": [page, cdn]})["ok"]
    old_key = key(cfg)
    before = panel.read_bytes()
    replacement = "https://r2.googlevideo.com/videoplayback?expire=2000000000&sig=private"
    assert send(cfg, {"cdn_probe_url": replacement})["code"] == "blocked"
    assert panel.read_bytes() == before

    payload = {"youtube_transport_probe": True, "cdn_probe_url": replacement}
    assert send(cfg, payload, expected="old")["code"] == "conflict"
    assert panel.read_bytes() == before
    result = send(cfg, payload, expected=old_key)
    assert result["ok"] and result["config_key"] != old_key
    assert "sig=private" not in str(result)
    actual = config.load(cfg)[0].zapret2
    assert actual.youtube_transport_probe and actual.probe_urls == [page, replacement]
    assert actual.mode == "off"


def test_youtube_gate_validates_merged_mode_domains_and_urls(store):
    cfg, panel = store
    before = panel.read_bytes()
    missing = send(cfg, {"youtube_transport_probe": True})
    assert missing["code"] == "invalid" and "/videoplayback" in missing["text"]
    assert not send(cfg, "selective", action="mode")["ok"]
    assert panel.read_bytes() == before
    valid = {"youtube_transport_probe": True, "probe_urls": [
        "https://www.youtube.com/t/terms", "https://r1.googlevideo.com/videoplayback?sig=fixture"]}
    domains = [*schema.YOUTUBE_DOMAINS, "domain:other.example"]
    rejected = send(cfg, {**valid, "domains": domains})
    assert rejected["code"] == "invalid" and "domain:googlevideo.com" in rejected["text"]
    assert "fixture" not in json.dumps(rejected) and panel.read_bytes() == before
    assert send(cfg, {**valid, "domains": list(schema.YOUTUBE_DOMAINS[:2])})["ok"]
    assert config.load(cfg)[0].zapret2.mode == "off"
    assert not send(cfg, "standalone", action="mode")["ok"]
    assert send(cfg, "selective", action="mode")["ok"]
    before = panel.read_bytes()
    assert not send(cfg, {"probe_urls": []})["ok"]
    assert not send(cfg, {"domains": ["domain:example.org"]})["ok"]
    assert panel.read_bytes() == before
    assert config.load(cfg)[0].zapret2.mode == "selective"
    assert send(cfg, "off", action="mode", ready=False)["ok"]
    assert send(cfg, {"youtube_transport_probe": False, "domains": domains, "probe_urls": []})["ok"]


def test_legacy_off_settings_can_be_corrected_without_activating(store):
    cfg, panel = store
    raw = json.loads(panel.read_text(encoding="utf-8"))
    raw["zapret2"].update(youtube_transport_probe=True, domains=schema.FREEPOOL_DOMAINS,
                         probe_urls=["https://www.youtube.com/t/terms",
                                     "https://r1.googlevideo.com/videoplayback?sig=fixture"])
    panel.write_text(json.dumps(raw), encoding="utf-8")
    before = panel.read_bytes()
    rejected = send(cfg, "selective", action="mode")
    assert "подставьте список" in rejected["text"] and panel.read_bytes() == before
    assert send(cfg, {"probe_urls": [], "domains": schema.FREEPOOL_DOMAINS,
                      "youtube_transport_probe": True})["code"] == "saved"
    assert not send(cfg, {"domains": [*schema.FREEPOOL_DOMAINS, "domain:other.example"]})["ok"]
    assert not send(cfg, "selective", action="mode")["ok"]
    assert send(cfg, {"youtube_transport_probe": False})["ok"]
    actual = config.load(cfg)[0].zapret2
    assert actual.mode == "off" and actual.domains == schema.FREEPOOL_DOMAINS


def test_two_writers_with_same_expected_have_one_winner(store):
    cfg, _panel = store
    expected = key(cfg)
    barrier = threading.Barrier(2)

    def write(seconds):
        barrier.wait(timeout=5)
        return send(cfg, {"retry_seconds": seconds}, expected=expected)["code"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, [120, 180]))
    assert sorted(results) == ["conflict", "saved"]


def test_parallel_managed_writer_is_not_lost(store):
    cfg, panel = store
    expected = key(cfg)
    barrier = threading.Barrier(2)

    def ordinary():
        barrier.wait(timeout=5)

        def change(data):
            data["sticky"] = True
            return True

        managed._update(panel, change)

    def selected():
        barrier.wait(timeout=5)
        assert send(cfg, {"retry_seconds": 120}, expected=expected)["ok"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(ordinary), pool.submit(selected)]
        for future in futures:
            future.result(timeout=10)
    actual = config.load(cfg)[0]
    assert actual.speed.sticky is True
    assert actual.zapret2.retry_seconds == 120


def test_error_does_not_save_or_leak_config(store, monkeypatch):
    cfg, panel = store
    before = panel.read_bytes()

    def failed(*args, **kwargs):
        raise OSError("private-token")

    monkeypatch.setattr(managed, "save", failed)
    result = send(cfg, {"retry_seconds": 120})
    assert result["code"] == "storage_error" and "private-token" not in json.dumps(result)
    assert panel.read_bytes() == before

@pytest.mark.parametrize("assets_ready", [False, True])
def test_alt9_entry_requires_import_even_when_assets_are_present(store, monkeypatch, assets_ready):
    from unittest.mock import Mock

    from xgw.desync import flowseal

    cfg, panel = store
    verify = Mock(return_value=[], side_effect=None if assets_ready else OSError("private-token"))
    monkeypatch.setattr(flowseal, "live_arguments", verify)
    before = panel.read_bytes(), panel.stat().st_mtime_ns
    result = send(cfg, {"strategy": schema.LIVE_STRATEGY})
    assert result["code"] == "invalid" and "Flowseal" in result["text"]
    assert "private-token" not in json.dumps(result)
    assert (panel.read_bytes(), panel.stat().st_mtime_ns) == before
    verify.assert_not_called()


def import_alt9(cfg, *, expected=None):
    return management.command(cfg, "import", {
        "expected": key(cfg) if expected is None else expected, "import": schema.LIVE_STRATEGY,
    }, ready=True, capture={"mode": "on"})


def test_alt9_import_echo_switch_away_and_reimport(store, monkeypatch):
    from unittest.mock import Mock

    from xgw.desync import flowseal

    cfg, panel = store
    verify = Mock(return_value=[])
    monkeypatch.setattr(flowseal, "live_arguments", verify)
    old = key(cfg)
    assert import_alt9(cfg)["code"] == "saved"
    verify.assert_called_once()
    imported = config.load(cfg)[0]
    assert imported.zapret2.mode == "off" and imported.zapret2.engine == "auto"
    assert imported.zapret2.strategy == schema.LIVE_STRATEGY
    assert json.loads(panel.read_text())["extension"] == {"keep": [1, 2]}
    assert import_alt9(cfg, expected=old)["code"] == "conflict"
    verify.assert_called_once()
    assert not management.reasons(imported, "standalone", ready=True, capture={"mode": "on"})
    # Both forms echo the selected strategy when editing an unrelated setting.
    assert send(cfg, {"strategy": schema.LIVE_STRATEGY, "retry_seconds": 120})["ok"]
    verify.assert_called_once()
    before = panel.read_bytes(), panel.stat().st_mtime_ns
    assert send(cfg, {"strategy": schema.LIVE_STRATEGY})["code"] == "unchanged"
    assert (panel.read_bytes(), panel.stat().st_mtime_ns) == before
    assert send(cfg, {"strategy": "multisplit"})["ok"]
    assert not send(cfg, {"strategy": schema.LIVE_STRATEGY})["ok"]
    assert import_alt9(cfg)["ok"]
    assert verify.call_count == 2


def test_alt9_missing_assets_prevent_import_and_activation_but_allow_off(store, monkeypatch):
    from unittest.mock import Mock

    from xgw.desync import flowseal

    cfg, panel = store
    verify = Mock(side_effect=OSError("private-token"))
    monkeypatch.setattr(flowseal, "live_arguments", verify)
    before = panel.read_bytes()
    missing = import_alt9(cfg)
    assert missing["code"] == "blocked" and "private-token" not in json.dumps(missing)
    assert panel.read_bytes() == before
    verify.side_effect = None
    verify.return_value = []
    assert import_alt9(cfg)["ok"]
    assert send(cfg, "standalone", action="mode")["ok"]
    verify.side_effect = ValueError("private-token")
    # Off must work even when the files disappear after a successful start.
    assert send(cfg, "off", action="mode", ready=False, capture="off")["ok"]
    assert send(cfg, {"strategy": schema.LIVE_STRATEGY, "retry_seconds": 120})["ok"]
    before = panel.read_bytes()
    blocked = send(cfg, "standalone", action="mode")
    assert blocked["code"] == "blocked" and "private-token" not in json.dumps(blocked)
    assert panel.read_bytes() == before

@pytest.mark.parametrize("remaining", [None, 0, 262144, 786431, 786432])
def test_selective_admission_is_checked_before_saving(store, remaining):
    cfg, panel = store
    assert send(cfg, {"youtube_transport_probe": True, "domains": list(schema.YOUTUBE_DOMAINS),
                      "probe_urls": ["https://www.youtube.com/t/terms",
                                     "https://r1.googlevideo.com/generate_204"]})["ok"]
    before = panel.read_bytes()
    def budget(proposed):
        return (None if remaining is None else
                management.zapret2.ProbeBudget(0, 1024 ** 2 - remaining, 1024 ** 2))
    result = send(cfg, "selective", action="mode", budget_reader=budget)
    assert result["ok"] is (remaining == 786432)
    if not result["ok"]:
        assert result["code"] in ("probe_budget", "budget_unavailable")
        assert panel.read_bytes() == before
