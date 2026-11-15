"""Windows-safe policy tests; local files only, Linux locks explicitly mocked."""

import copy
import importlib.util
import json
from contextlib import nullcontext
from dataclasses import asdict
from pathlib import Path

import pytest

from xgw import config, managed, zapret2
from xgw.desync import schema
from xgw.watch.zapret2_control import card


@pytest.mark.parametrize("source", ["freepool", "gui-light"])
def test_lossless_idempotent_branch_roundtrip(source):
    raw = {"mode": "selective", "strategy": "multisplit",
           "probe_urls": ["https://youtube.com/watch?v=private", "https://googlevideo.com/v?sig=x"]}
    if source == "gui-light":
        raw.update(engine="auto", engine_profile="hostfakesplit-md5")
    before = copy.deepcopy(raw)
    policy = schema.migrate(raw, source=source)
    assert raw == before
    assert schema.migrate(policy) == policy
    exported = schema.project(policy, target=source)
    assert schema.migrate(exported, source=source) == policy
    assert all(exported[k] == value for k, value in raw.items())
    expected = schema.FREEPOOL_DOMAINS if source == "freepool" else schema.GUI_DOMAINS
    assert policy["selected"]["domains"] == expected


def test_config_defaults_match_legacy_defaults():
    assert asdict(config.Zapret2()) == schema.DEFAULTS


def test_legacy_compare_strategy_preserved_but_requires_supported_trace():
    policy = schema.migrate({"mode": "compare", "strategy": "hostfakesplit_md5"},
                            source="freepool")
    assert schema.migrate(schema.project(policy, target="freepool"), source="freepool") == policy
    with pytest.raises(schema.PolicyError, match="compare tracing"):
        schema.project(policy, target="gui-light")


@pytest.mark.parametrize("strategy", schema.SELECTED_PROFILES)
@pytest.mark.parametrize("representation", ["zapret2", "desync"])
def test_dormant_strategy_loads_losslessly_and_confirms_off(tmp_path, strategy, representation):
    file = tmp_path / "config.toml"
    file.write_text("", encoding="utf-8")
    raw = {"mode": "off", "strategy": strategy, "domains": schema.FREEPOOL_DOMAINS,
           "probe_urls": ["https://www.youtube.com/watch?v=fixture",
                          "https://cdn.googlevideo.com/video?sig=fixture"]}
    policy = schema.migrate(raw)
    panel = tmp_path / "panel.json"
    panel.write_text(json.dumps({representation: raw if representation == "zapret2"
                                else policy}), encoding="utf-8")
    before = (file.read_bytes(), panel.read_bytes())
    cfg, warnings = config.load(file)
    assert cfg.desync == policy == schema.migrate(asdict(cfg.zapret2))
    assert cfg.zapret2.mode == cfg.zapret2.engine == "off"
    assert not cfg.zapret2.probe_enabled
    assert not any("zapret2" in warning for warning in warnings)
    assert config.load(file)[0].desync == policy
    assert (file.read_bytes(), panel.read_bytes()) == before
    # Same effective-policy fingerprint as the daemon: no perpetual pending after load.
    snapshot = {"updated": 1000, "daemon": True, "zapret2": {"state": "off"},
                "capture": {"nfqws2": {"state": "off"}},
                "zapret2_policy_key": schema.fingerprint(schema.migrate(asdict(cfg.zapret2)))}
    view = card(cfg, snapshot, {"mode": "on"}, True, now=1000)
    assert view["state"] == "off" and view["fresh"] and view["policy_matched"]
    assert view["strategy"] is None and not view["without_vpn"]


def test_dormant_strategy_with_no_trace_cannot_be_enabled_in_compare(tmp_path, monkeypatch):
    file = tmp_path / "config.toml"
    file.write_text('[zapret2]\nengine="auto"\n', encoding="utf-8")
    panel = tmp_path / "panel.json"
    policy = schema.migrate({"mode": "off", "strategy": "hostfakesplit_md5",
                             "engine": "auto"})
    panel.write_text(json.dumps({"desync": policy}), encoding="utf-8")
    cfg, _ = config.load(file)
    assert cfg.zapret2.engine == "auto"  # Existing engine setting is preserved, not enabled here.
    assert cfg.zapret2.strategy == "hostfakesplit_md5"
    original = panel.read_bytes()
    monkeypatch.setattr(managed, "file_lock", lambda *a, **kw: nullcontext())
    assert not managed.set_desync(panel, policy)
    requested = copy.deepcopy(policy)
    requested["selected"]["mode"] = "compare"
    with pytest.raises(managed.ManagedError, match="compare tracing"):
        managed.set_desync(panel, requested)
    assert panel.read_bytes() == original
    panel.write_text(json.dumps({"desync": requested}), encoding="utf-8")
    with pytest.raises(config.ConfigError, match="compare tracing"):
        config.load(file)


def test_unknown_dormant_strategy_is_still_rejected():
    with pytest.raises(schema.PolicyError, match="strategy"):
        schema.migrate({"mode": "off", "strategy": "unknown"})
    cfg = config.Config()
    cfg.zapret2.strategy = "unknown"
    assert any("strategy" in warning for warning in zapret2.validate(cfg))


def test_engine_cannot_be_silently_lost_exporting_to_freepool():
    with pytest.raises(schema.PolicyError, match="cannot be represented"):
        schema.project(schema.migrate({"engine": "auto"}), target="freepool")


@pytest.mark.parametrize("bad", [
    {"engine_queue": True}, {"queue_num": 0}, {"mode": "magic"},
    {"binary": "C:\\nfqws2.exe"}, {"lua_dir": "/opt/../tmp/lua"},
    {"binary": "//server/nfqws2"}, {"domains": [123]}, {"probe_urls": [False]},
    {"probe_urls": ["http://youtube.com/"]}, {"extra": "ignored?"},
    {"probe_urls": ["https://u:secret@youtube.com/"]},
])
def test_invalid_inputs_fail_without_private_values(bad):
    with pytest.raises(schema.PolicyError) as exc:
        schema.migrate(bad)
    assert "secret" not in str(exc.value)


def test_canonical_is_strict_and_detached():
    original = schema.migrate({})
    policy = schema.migrate(original)
    policy["selected"]["domains"].append("domain:example.com")
    assert policy != original
    for bad in ({**original, "schema_version": 2}, {**original, "schema_version": True},
                {**original, "extra": {}}, {**original, "runtime": {}}):
        with pytest.raises(schema.PolicyError):
            schema.migrate(bad)


def test_dual_representation_must_agree():
    policy = schema.migrate({"engine": "auto"})
    assert schema.resolve({"engine": "auto"}, policy) == policy
    with pytest.raises(schema.PolicyError, match="conflicting"):
        schema.resolve({"engine": "off"}, policy)


def test_config_load_merges_legacy_panel_and_keeps_files_unchanged(tmp_path):
    file = tmp_path / "config.toml"
    file.write_text('[zapret2]\nengine = "auto"\n', encoding="utf-8")
    panel = tmp_path / "panel.json"
    panel.write_text(json.dumps({"zapret2": {"engine_profile": "hostfakesplit-md5"}}))
    before = (file.read_bytes(), panel.read_bytes())
    first, _ = config.load(file)
    second, _ = config.load(file)
    assert first.desync == second.desync
    assert first.zapret2.engine == "auto"
    assert first.zapret2.engine_profile == "hostfakesplit-md5"
    assert (file.read_bytes(), panel.read_bytes()) == before


def test_canonical_config_and_conflict(tmp_path):
    file = tmp_path / "config.toml"
    policy = schema.migrate({"engine": "auto"})
    # TOML inline tables accept JSON string syntax, but use TOML boolean spelling.
    sections = [f"[desync]\nschema_version = {schema.VERSION}"]
    for group in schema.GROUPS:
        sections.append(f"[desync.{group}]")
        sections.extend(f"{k} = {json.dumps(v)}" for k, v in policy[group].items())
    text = "\n".join(sections) + "\n"
    file.write_text(text, encoding="utf-8")
    cfg, _ = config.load(file)
    assert cfg.desync == policy and cfg.zapret2.engine == "auto"
    file.write_text(text + '\n[zapret2]\nengine="off"\n', encoding="utf-8")
    with pytest.raises(config.ConfigError, match="conflicting"):
        config.load(file)


def test_complete_panel_policy_overrides_toml_and_unrelated_writes_preserve_it(tmp_path):
    file = tmp_path / "config.toml"
    file.write_text('[zapret2]\nengine="auto"\n', encoding="utf-8")
    panel = tmp_path / "panel.json"
    desired = schema.migrate({"engine": "off"})
    panel.write_text(json.dumps({"desync": desired, "sticky": True}), encoding="utf-8")
    cfg, _ = config.load(file)
    assert cfg.desync == desired and cfg.zapret2.engine == "off"
    data, error = managed.load(panel)
    assert not error
    data["sticky"] = False
    panel.write_text(json.dumps(data), encoding="utf-8")
    cfg, _ = config.load(file)
    assert cfg.desync == desired and cfg.zapret2.engine == "off"


@pytest.mark.parametrize("raw", [
    {"zapret2": {"mode": "compare", "strategy": "hostfakesplit_md5"}},
    {"desync": {"schema_version": 999}},
    {"desync": {"engine": "auto"}},
    {"zapret2": {"engine_queue": False}},
])
def test_bad_or_unsupported_panel_policy_does_not_turn_into_defaults(tmp_path, raw):
    file = tmp_path / "config.toml"
    file.write_text("", encoding="utf-8")
    panel = tmp_path / "panel.json"
    panel.write_text(json.dumps(raw), encoding="utf-8")
    original = panel.read_bytes()
    with pytest.raises(config.ConfigError):
        config.load(file)
    assert panel.read_bytes() == original


@pytest.mark.parametrize("content", ["{broken", "[]"])
def test_unreadable_panel_never_enables_toml_fallback(tmp_path, content):
    file = tmp_path / "config.toml"
    file.write_text('[zapret2]\nengine="auto"\n', encoding="utf-8")
    panel = tmp_path / "panel.json"
    panel.write_text(content, encoding="utf-8")
    with pytest.raises(config.ConfigError):
        config.load(file)
    assert panel.read_text(encoding="utf-8") == content


def test_rejected_selected_mode_cannot_implicitly_enable_engine(tmp_path):
    file = tmp_path / "config.toml"
    file.write_text('[network]\nquic_mode="proxy"\n'
                    '[zapret2]\nmode="selective"\nengine="auto"\n', encoding="utf-8")
    with pytest.raises(config.ConfigError, match="network prerequisites"):
        config.load(file)


def test_persist_once_and_preserve_unrelated_panel_settings(tmp_path, monkeypatch):
    file = tmp_path / "panel.json"
    file.write_text(json.dumps({"sticky": True, "zapret2": {"engine": "off"}}))
    monkeypatch.setattr(managed, "file_lock", lambda *a, **kw: nullcontext())
    writes = []

    def write(path, data, **kwargs):
        writes.append(data)
        path.write_text(json.dumps(data), encoding="utf-8")

    monkeypatch.setattr(managed, "atomic_write_json", write)
    policy = schema.migrate({"mode": "off", "strategy": "hostfakesplit_md5"})
    assert managed.set_desync(file, policy)
    assert not managed.set_desync(file, policy)
    assert len(writes) == 1
    data, error = managed.load(file)
    assert not error and data["sticky"] is True and data["desync"] == policy
    assert data["zapret2"] == {}
    # The actual file locking/ownership remains an Ubuntu acceptance check.


def test_observe_synack_is_optional_and_can_round_trip_without_changing_old_policy(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[zapret2]\nobserve_synack = true\n', encoding="utf-8")
    cfg, _ = config.load(path)
    assert cfg.zapret2.observe_synack is True
    assert cfg.desync["selected"]["observe_synack"] is True
    before = schema.migrate({})
    disabled = schema.migrate({"observe_synack": False})
    assert disabled == before
    assert schema.fingerprint(disabled) == schema.fingerprint(before)
    with pytest.raises(schema.PolicyError, match="cannot be represented"):
        schema.project(cfg.desync, target="freepool")


@pytest.fixture(params=["desync_batch1_install.py", "gui_catalog_install.py"])
def installer(monkeypatch, request):
    file = Path(__file__).parents[1] / "docs/helpers" / request.param
    spec = importlib.util.spec_from_file_location("batch1_install", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    monkeypatch.setattr(module, "service", lambda *args: calls.append(args) or "active")
    monkeypatch.setattr(module, "trusted", lambda path: None)
    # Model the file transaction only. POSIX ownership and systemd are tested on Ubuntu.
    monkeypatch.setattr(module, "atomic", lambda path, data, *args: path.write_bytes(data))
    return module, calls


def test_deploy_refuses_drift_before_stopping_service(tmp_path, installer):
    module, calls = installer
    target = tmp_path / "code.py"
    target.write_bytes(b"changed after prepare")
    row = {"target": str(target), "old_sha": module.sha(b"baseline")}
    with pytest.raises(ValueError, match="changed after prepare"):
        module.apply(tmp_path, [row])
    assert not any(call[0] == "stop" for call in calls)
    assert target.read_bytes() == b"changed after prepare"


def test_partial_deploy_failure_restores_old_files_and_restarts(tmp_path, installer, monkeypatch):
    module, calls = installer
    original = tmp_path / "old.py"
    added = tmp_path / "new.py"
    original.write_bytes(b"old")
    (tmp_path / "0.old").write_bytes(b"old")
    (tmp_path / "0.new").write_bytes(b"updated")
    (tmp_path / "1.new").write_bytes(b"added")
    rows = [
        {"target": str(original), "old_sha": module.sha(b"old"), "old": "0.old",
         "new": "0.new", "mode": 0o644, "gid": 0},
        {"target": str(added), "old_sha": None, "new": "1.new", "mode": 0o644, "gid": 0},
    ]

    def fail_second_write(path, data, *args):
        if path == added:
            raise OSError("injected partial deployment failure")
        path.write_bytes(data)

    monkeypatch.setattr(module, "atomic", fail_second_write)
    with pytest.raises(OSError, match="injected"):
        module.apply(tmp_path, rows)
    assert original.read_bytes() == b"old" and not added.exists()
    assert calls[-1] == ("start", "xgw.service") or calls[-1] == ("start",)
