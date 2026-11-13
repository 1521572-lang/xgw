"""Волна 2 (ASSUMPTIONS п. 336): память профилей — удачный профиль первым, не помогший
последним, сроки, несовместимые параметры, скачок часов, перезапуск."""

import copy
import json

import pytest
from test_daemon import Harness, _started

from xgw.config import Config
from xgw.daemon import TRIALS_META, ProfileTrial
from xgw.generator import profiles
from xgw.paths import Paths

LADDER = profiles.ladder("FROZEN", profiles.XRAY_DEFAULT, profiles.XRAY_DEFAULT,
                         list(profiles.ALL))


@pytest.fixture()
def daemon(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    cfg = Config()
    cfg.filters.max_members = 2
    cfg.filters.exclude_regex = ""
    cfg.dns.bootstrap = []
    cfg.speed.sticky = False
    cfg.speed.unlimited_hours = cfg.speed.limited_hours = 0
    instance = Harness(cfg, paths)
    yield instance
    instance.store.close()


def test_success_first_and_failure_last_cut_the_attempts():
    worked = {"profile": profiles.SB_FRAGMENT, "ts": 1000.0, "key": "k"}
    failed = {"key": "k", "steps": {profiles.XRAY_FRAGMENT: 1000.0}}
    order = profiles.remembered(LADDER, key="k", now=2000.0, worked=worked, failed=failed)
    # Помогает только sing-box с дроблением: до запоминания — семь попыток, после — одна.
    assert LADDER.index(profiles.SB_FRAGMENT) + 1 == 7
    assert order.index(profiles.SB_FRAGMENT) + 1 == 1
    assert order[-1] == profiles.XRAY_FRAGMENT and sorted(order) == sorted(LADDER)


def test_new_params_expiry_and_clock_jump_do_not_bind():
    worked = {"profile": profiles.SB_FRAGMENT, "ts": 1000.0, "key": "k"}
    failed = {"key": "k", "steps": {profiles.XRAY_FRAGMENT: 1000.0}}
    # Сменились параметры (ключ) — ни ложного успеха, ни запрета.
    assert profiles.remembered(LADDER, key="new", now=2000.0, worked=worked,
                               failed=failed) == LADDER
    # Истёкшая неудача снова на своём месте; истёкшая удача не первая.
    late = 1000.0 + profiles.WORKED_KEEP + 1
    assert profiles.remembered(LADDER, key="k", now=late, worked=worked, failed=failed) == LADDER
    # Отметка «из будущего» (часы ушли назад) — не действует.
    assert profiles.remembered(LADDER, key="k", now=500.0, worked=worked,
                               failed=failed) == LADDER
    assert not profiles.fresh(True, 1.0, 10.0) and not profiles.fresh("1", 1.0, 10.0)


def test_daemon_records_success_and_failure_per_params(daemon):
    _started(daemon)
    node = daemon.inventory.nodes[0]
    failed = ProfileTrial(profiles.XRAY_FRAGMENT, [], profiles.XRAY_DEFAULT, "probe-x",
                          daemon.wall(), False, "FROZEN", False)
    daemon._trial_failed(node, failed)
    assert daemon._remembered(node, LADDER)[-1] == profiles.XRAY_FRAGMENT
    good = ProfileTrial(profiles.SB_FRAGMENT, [], profiles.XRAY_DEFAULT, "probe-x",
                        daemon.wall(), False, "FROZEN", False)
    daemon._learned(node.fingerprint, good)
    assert daemon._remembered(node, LADDER)[0] == profiles.SB_FRAGMENT
    saved = json.loads(daemon.store.get_meta(TRIALS_META))
    assert saved["worked"][node.fingerprint]["profile"] == profiles.SB_FRAGMENT
    assert saved["failed"][node.fingerprint]["verdict"] == "FROZEN"
    # Тот же отпечаток с другим SNI или путём — записи несовместимы; имя не важно.
    renamed = copy.deepcopy(node)
    renamed.name = "другое имя"
    assert daemon._remembered(renamed, LADDER)[0] == profiles.SB_FRAGMENT
    changed = copy.deepcopy(node)
    stream = changed.outbound.setdefault("streamSettings", {})
    stream.setdefault("tlsSettings", {})["serverName"] = "other.example.org"
    assert profiles.params_key(changed) != profiles.params_key(node)
    assert daemon._remembered(changed, LADDER) == LADDER


def test_restart_keeps_memory_and_drops_bad_or_future_records(daemon):
    now = daemon.wall()
    window = daemon.cfg.fragment.escalation_hours * 3600.0
    daemon.store.set_meta(TRIALS_META, json.dumps({
        "worked": {"fp1": {"profile": profiles.XRAY_SPLIT, "ts": now - 60, "key": "k"},
                   "fp2": {"profile": "bogus", "ts": now, "key": "k"}},
        "failed": {"fp1": {"key": "k", "steps": {profiles.SB_DEFAULT: now - 60}},
                   "fp3": {"key": "k", "steps": {profiles.SB_DEFAULT: "nan"}}},
        "closed": {"fp4": now + 10 * 86400.0},
        "unstable": {"fp5": now + 10 * window},
        "escalations": {"fp6": [now + 86400.0]},
    }))
    daemon._load_profiles()
    assert set(daemon._worked) == {"fp1"} and set(daemon._failed_steps) == {"fp1"}
    assert not daemon._is_unstable("fp5")  # часы ушли назад — не вечный запрет
    assert daemon._may_escalate("fp6", "«x» (y)")  # перевод «из будущего» не считается
    daemon._save_profiles()
    saved = json.loads(daemon.store.get_meta(TRIALS_META))
    assert saved["worked"]["fp1"]["profile"] == profiles.XRAY_SPLIT
    assert saved["failed"]["fp1"]["steps"] == {profiles.SB_DEFAULT: now - 60}
    assert "fp4" not in saved["closed"] and "fp5" not in saved["unstable"]
