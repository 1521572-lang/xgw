"""Тесты Applier: путь API, отложенный перезапуск, срочный, откат last-good."""

import datetime
import json

import pytest
from test_generator import _build

from xgw.apply.applier import Applier, in_restart_window
from xgw.config import Config
from xgw.paths import Paths
from xgw.xraycore.api import ApiError


class StubApi:
    def __init__(self, fail: bool = False, healthy: bool = True):
        self.fail = fail
        self.healthy = healthy
        self.calls: list[str] = []

    def add_inbounds(self, inbounds):
        self.calls.append("adi")
        if self.fail:
            raise ApiError("нет связи")

    def add_outbounds(self, outbounds):
        self.calls.append("ado")
        if self.fail:
            raise ApiError("нет связи")

    def replace_routing(self, routing, *, append=False):
        self.calls.append("adrules")
        if self.fail:
            raise ApiError("нет связи")

    def remove_outbound(self, tag):
        self.calls.append("rmo")

    def remove_inbound(self, tag):
        self.calls.append("rmi")

    def balancer_info(self, *balancers):
        if not self.healthy:
            raise ApiError("API не отвечает")
        return "{}"


class StubService:
    def __init__(self, healthy_after_restart: bool = True):
        self.healthy = healthy_after_restart
        self.restarts = 0

    def start(self):
        pass

    def stop(self):
        pass

    def restart(self):
        self.restarts += 1

    def is_active(self):
        return self.healthy


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    result, _cfg, _sel = _build()
    paths.xray_config_file.write_text(
        json.dumps(result.config, ensure_ascii=False), encoding="utf-8"
    )
    return paths, result.config


def _with_extra_outbound(config: dict) -> dict:
    import copy

    new = copy.deepcopy(config)
    extra = copy.deepcopy(new["outbounds"][0])
    extra["tag"] = "proxy-zz-ffffffff"
    new["outbounds"].append(extra)
    probe = copy.deepcopy(new["inbounds"][3])
    probe["tag"] = "probe-zz-ffffffff"
    probe["port"] = 20999
    new["inbounds"].append(probe)
    new["routing"]["rules"].insert(
        0,
        {"type": "field", "inboundTag": ["probe-zz-ffffffff"], "outboundTag": "proxy-zz-ffffffff"},
    )
    return new


def test_api_path_promotes_files(env):
    paths, current = env
    api = StubApi()
    applier = Applier(Config(), paths, api, StubService())
    outcome = applier.apply(_with_extra_outbound(current))
    assert outcome.mode == "api"
    assert api.calls == ["adi", "ado", "adrules"]
    on_disk = json.loads(paths.xray_config_file.read_text(encoding="utf-8"))
    assert "proxy-zz-ffffffff" in [o["tag"] for o in on_disk["outbounds"]]
    assert paths.last_good_file.exists()  # старый конфиг стал last-good


def test_unchanged(env):
    paths, current = env
    applier = Applier(Config(), paths, StubApi(), StubService())
    assert applier.apply(current).mode == "unchanged"


def test_restart_deferred_outside_window(env, monkeypatch):
    paths, current = env
    cfg = Config()
    cfg.apply.restart_window = "03:00-03:30"
    fixed = datetime.time(12, 0)
    applier = Applier(cfg, paths, StubApi(), StubService(), now_fn=lambda: fixed)
    new = _with_extra_outbound(current)
    new["dns"]["hosts"]["new.example.com"] = ["203.0.113.98"]  # требует перезапуска
    outcome = applier.apply(new)
    assert outcome.mode == "restart_deferred"
    assert (paths.xray_config_dir / "config.pending.json").exists()
    assert "proxy-zz-ffffffff" not in paths.xray_config_file.read_text(encoding="utf-8")


def test_force_now_restarts_inside_any_time(env):
    paths, current = env
    cfg = Config()
    cfg.apply.restart_window = "03:00-03:30"
    service = StubService()
    applier = Applier(cfg, paths, StubApi(), service, now_fn=lambda: datetime.time(12, 0))
    new = _with_extra_outbound(current)
    new["dns"]["hosts"]["new.example.com"] = ["203.0.113.98"]
    outcome = applier.apply(new, force_now=True)
    assert outcome.mode == "restart"
    assert service.restarts == 1


def test_api_error_falls_back_to_restart(env):
    paths, current = env
    service = StubService()
    applier = Applier(Config(), paths, StubApi(fail=True), service)
    outcome = applier.apply(_with_extra_outbound(current))
    assert outcome.mode == "restart"
    assert service.restarts == 1


def test_window_wrap_around_midnight():
    assert in_restart_window("23:00-01:00", datetime.time(0, 30))
    assert in_restart_window("23:00-01:00", datetime.time(23, 30))
    assert not in_restart_window("23:00-01:00", datetime.time(12, 0))
    assert in_restart_window("04:00-05:00", datetime.time(4, 30))
    assert not in_restart_window("04:00-05:00", datetime.time(6, 0))


def test_rollback_to_last_good_when_xray_never_up(env):
    paths, current = env
    # первый успешный apply создаёт last-good
    applier = Applier(Config(), paths, StubApi(), StubService())
    applier.apply(_with_extra_outbound(current))
    good = json.loads(paths.last_good_file.read_text(encoding="utf-8"))
    # перезапуск, после которого API так и не отвечает → откат
    cfg = Config()
    cfg.apply.restart_window = "00:00-23:59"
    service = StubService()
    new = json.loads(paths.xray_config_file.read_text(encoding="utf-8"))
    new["policy"]["levels"]["0"]["connIdle"] = 999
    applier = Applier(cfg, paths, StubApi(healthy=False), service, wait_seconds=0.2)
    outcome = applier.apply(new, force_now=True)
    assert outcome.mode == "rollback"
    restored = json.loads(paths.xray_config_file.read_text(encoding="utf-8"))
    assert "proxy-zz-ffffffff" in [o["tag"] for o in restored["outbounds"]]
    assert good["policy"] == restored["policy"]
