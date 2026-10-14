"""Тесты Applier: путь API, отложенный перезапуск, срочный, откат last-good."""

import copy
import datetime
import json

import pytest
from test_generator import _build

from xgw.apply.applier import Applier, in_restart_window
from xgw.config import Config
from xgw.paths import Paths, file_lock
from xgw.xraycore.api import ApiError

NOON = datetime.time(12, 0)


def _valid(_config):
    return True, ""


class StubService:
    def __init__(self):
        self.restarts = 0

    def start(self):
        pass

    def stop(self):
        pass

    def restart(self):
        self.restarts += 1

    def is_active(self):
        return True


class StubApi:
    """fail — имя вызова, на котором API отвечает ошибкой; healthy_after — с какого
    по счёту перезапуска службы ядро начинает отвечать (None — никогда)."""

    def __init__(self, fail: str = "", service: StubService | None = None,
                 healthy_after: int | None = 0):
        self.fail = fail
        self.service = service
        self.healthy_after = healthy_after
        self.calls: list[str] = []
        self.bi_args: list[tuple] = []

    def _call(self, name: str):
        self.calls.append(name)
        if self.fail == name:
            raise ApiError("нет связи")

    def add_inbounds(self, inbounds):
        self._call("adi")

    def add_outbounds(self, outbounds):
        self._call("ado")

    def replace_routing(self, routing, *, append=False):
        self._call("adrules")

    def remove_outbound(self, tag):
        self._call("rmo")

    def remove_inbound(self, tag):
        self._call("rmi")

    def balancer_info(self, *balancers):
        self.bi_args.append(balancers)
        restarts = self.service.restarts if self.service else 0
        if self.healthy_after is None or restarts < self.healthy_after:
            raise ApiError("API не отвечает")
        return "{}"


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


def _applier(paths, api, service=None, *, window="03:00-03:30", now=NOON, **kwargs):
    cfg = Config()
    cfg.apply.restart_window = window
    return Applier(
        cfg, paths, api, service or StubService(), now_fn=lambda: now, validator=_valid, **kwargs
    )


def _on_disk(paths) -> dict:
    return json.loads(paths.xray_config_file.read_text(encoding="utf-8"))


def _with_extra_outbound(config: dict) -> dict:
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


def _needs_restart(config: dict) -> dict:
    new = _with_extra_outbound(config)
    new["policy"]["levels"]["0"]["connIdle"] = 999
    return new


def test_api_path_promotes_files(env):
    paths, current = env
    api = StubApi()
    outcome = _applier(paths, api).apply(_with_extra_outbound(current))
    assert outcome.mode == "api"
    assert api.calls == ["adi", "ado", "adrules"]
    assert "proxy-zz-ffffffff" in [o["tag"] for o in _on_disk(paths)["outbounds"]]
    # старый конфиг стал last-good
    assert json.loads(paths.last_good_file.read_text(encoding="utf-8")) == current


def test_unchanged(env):
    paths, current = env
    assert _applier(paths, StubApi()).apply(current).mode == "unchanged"


def test_changed_outbound_with_same_tag_is_replaced(env):
    """В подписке сменили параметр сервера: тег тот же, но ядро обязано получить новый."""
    paths, current = env
    new = copy.deepcopy(current)
    new["outbounds"][0]["streamSettings"]["tlsSettings"] = {"serverName": "changed.example.org"}
    api = StubApi()
    outcome = _applier(paths, api).apply(new)
    assert outcome.mode == "api"
    assert api.calls == ["rmo", "ado"]
    assert _on_disk(paths) == new


def test_new_server_with_domain_goes_through_api(env):
    """Новый сервер с доменным адресом меняет dns.hosts — это не повод для перезапуска."""
    paths, current = env
    new = _with_extra_outbound(current)
    new["dns"]["hosts"]["new.example.com"] = ["203.0.113.98"]
    api, service = StubApi(), StubService()
    outcome = _applier(paths, api, service).apply(new)
    assert outcome.mode == "api"
    assert service.restarts == 0
    assert any("dns.hosts" in op for op in outcome.ops)
    assert _on_disk(paths)["dns"]["hosts"]["new.example.com"] == ["203.0.113.98"]


def test_invalid_config_is_rejected(env):
    paths, current = env
    applier = _applier(paths, StubApi())
    applier.validator = lambda _config: (False, "failed to parse")
    outcome = applier.apply(_with_extra_outbound(current))
    assert outcome.mode == "rejected" and "failed to parse" in outcome.detail
    assert _on_disk(paths) == current


def test_unverified_config_is_rejected(env):
    """Xray не найден — конфиг проверить нечем, значит и применять нельзя."""
    paths, current = env
    applier = _applier(paths, StubApi())
    applier.validator = lambda _config: (None, "xray не найден")
    assert applier.apply(_with_extra_outbound(current)).mode == "rejected"
    assert _on_disk(paths) == current


def test_restart_deferred_outside_window(env):
    paths, current = env
    service = StubService()
    outcome = _applier(paths, StubApi(), service).apply(_needs_restart(current))
    assert outcome.mode == "restart_deferred"
    assert "секция policy" in outcome.ops
    assert service.restarts == 0
    assert paths.pending_config_file.exists()
    assert _on_disk(paths) == current


def test_restart_inside_window_clears_pending(env):
    paths, current = env
    new = _needs_restart(current)
    _applier(paths, StubApi()).apply(new)
    service = StubService()
    api = StubApi(service=service, healthy_after=1)
    outcome = _applier(paths, api, service, now=datetime.time(3, 15)).apply(new)
    assert outcome.mode == "restart"
    assert service.restarts == 1
    assert _on_disk(paths) == new
    assert not paths.pending_config_file.exists()
    # готовность проверяется по конкретному балансировщику: `bi` без тега — ошибка
    assert api.bi_args and all(args == ("auto",) for args in api.bi_args)


def test_force_now_restarts_at_any_time(env):
    paths, current = env
    service = StubService()
    outcome = _applier(paths, StubApi(), service).apply(_needs_restart(current), force_now=True)
    assert outcome.mode == "restart"
    assert service.restarts == 1


def _without_tproxy_inbounds(config: dict) -> dict:
    new = copy.deepcopy(config)
    new["inbounds"] = [
        inbound
        for inbound in new["inbounds"]
        if not str(inbound.get("tag", "")).startswith("tproxy-in")
    ]
    return new


def test_tproxy_inbound_change_is_not_deferred(env):
    """Inbound перехвата меняется — перезапуск сразу, даже вне окна.

    Правила nftables грузятся по новому конфигу в тот же шаг watchdog; если ядро
    оставить на старом конфиге до 04:00, перехваченный трафик уйдёт на порт,
    который никто не слушает, и при fail_mode = closed машина останется без
    интернета.
    """
    paths, current = env
    service = StubService()
    outcome = _applier(paths, StubApi(service=service, healthy_after=1), service).apply(
        _without_tproxy_inbounds(current)
    )
    assert outcome.mode == "restart"
    assert "изменение inbound перехвата" in " ".join(outcome.ops)
    assert service.restarts == 1
    assert not paths.pending_config_file.exists()

    # Обратно: появление inbound'а перехвата тоже применяется сразу.
    service = StubService()
    outcome = _applier(paths, StubApi(service=service, healthy_after=1), service).apply(current)
    assert outcome.mode == "restart"
    assert "изменение inbound перехвата" in " ".join(outcome.ops)


def test_tun_inbound_change_is_not_deferred(env):
    """То же для capture.method = "tun": inbound tun-in появился, сменил интерфейс или
    исчез — Xray перезапускается сразу, а не в окне: маршрут уже ведёт трафик машины в
    интерфейс, из которого прежний Xray не читает."""
    paths, current = env
    tun_in = {"tag": "tun-in", "protocol": "tun", "settings": {"name": "xgwtun0", "mtu": 1500}}
    with_tun = copy.deepcopy(current)
    with_tun["inbounds"].insert(0, tun_in)
    renamed = copy.deepcopy(current)
    renamed["inbounds"].insert(0, {**tun_in, "settings": {"name": "vpn7", "mtu": 1500}})
    for step in (with_tun, renamed, current):  # появился → изменился → исчез
        service = StubService()
        outcome = _applier(paths, StubApi(service=service, healthy_after=1), service).apply(step)
        assert outcome.mode == "restart", outcome
        assert "изменение inbound перехвата" in " ".join(outcome.ops)
        assert service.restarts == 1 and not paths.pending_config_file.exists()
        assert _on_disk(paths) == step


def test_other_inbounds_still_wait_for_the_window(env):
    """Немедленный перезапуск — только для inbound'ов перехвата: смена порта socks-in
    по-прежнему ждёт окна (в Linux на него не ссылается ни одно правило сети)."""
    paths, current = env
    new = copy.deepcopy(current)
    next(item for item in new["inbounds"] if item["tag"] == "socks-in")["port"] = 11808
    service = StubService()
    outcome = _applier(paths, StubApi(service=service), service).apply(new)
    assert outcome.mode == "restart_deferred" and service.restarts == 0
    assert paths.pending_config_file.exists()


def _with_tun_inbound(config: dict) -> dict:
    new = _needs_restart(config)
    new["inbounds"].insert(
        0, {"tag": "tun-in", "protocol": "tun", "settings": {"name": "xgwtun0", "mtu": 1500}}
    )
    return new


def test_tun_interface_is_created_before_xray_starts(env):
    """Интерфейс, созданный самим Xray, исчез бы вместе с ним (и с маршрутом в него);
    постоянный создаёт XGW — и до запуска ядра."""
    from fakenet import FakeKernel

    paths, current = env
    kernel = FakeKernel()
    order: list[str] = []

    class Service(StubService):
        def restart(self):
            order.append("restart")
            order.append("link" if "xgwtun0" in kernel.links else "no link")
            super().restart()

    outcome = _applier(paths, StubApi(), Service(), runner=kernel).apply(
        _with_tun_inbound(current), force_now=True
    )
    assert outcome.mode == "restart"
    assert order == ["restart", "link"]
    assert kernel.links == {"xgwtun0": "tun"}


def test_failed_tun_preparation_does_not_block_the_restart(env):
    from fakenet import FakeKernel

    paths, current = env
    kernel = FakeKernel()
    kernel.refuse = "tuntap add"
    service = StubService()
    outcome = _applier(paths, StubApi(), service, runner=kernel).apply(
        _with_tun_inbound(current), force_now=True
    )
    assert outcome.mode == "restart" and service.restarts == 1  # Xray создаст свой интерфейс


def test_no_tun_inbound_means_no_ip_commands(env):
    from fakenet import FakeKernel

    paths, current = env
    kernel = FakeKernel()
    _applier(paths, StubApi(), runner=kernel).apply(_needs_restart(current), force_now=True)
    assert kernel.calls == []


def test_api_error_defers_restart_and_blocks_api_path(env):
    """Ошибка API — перезапуск по общим правилам (окно/срочно), а до него
    частично изменённое ядро через API больше не трогаем."""
    paths, current = env
    new = _with_extra_outbound(current)
    service = StubService()
    outcome = _applier(paths, StubApi(fail="ado"), service).apply(new)
    assert outcome.mode == "restart_deferred"
    assert "ошибка API" in outcome.ops
    assert service.restarts == 0
    assert _on_disk(paths) == current
    assert paths.api_dirty_file.exists()

    healthy = StubApi()
    again = _applier(paths, healthy, service).apply(new)
    assert again.mode == "restart_deferred"
    assert healthy.calls == []  # повторного adi/ado поверх половины изменений нет

    final = _applier(paths, StubApi(), service).apply(new, urgent=True)
    assert final.mode == "restart"
    assert service.restarts == 1
    assert _on_disk(paths) == new
    assert not paths.api_dirty_file.exists()


def test_api_error_restarts_immediately_when_urgent(env):
    paths, current = env
    service = StubService()
    outcome = _applier(paths, StubApi(fail="adrules"), service).apply(
        _with_extra_outbound(current), urgent=True
    )
    assert outcome.mode == "restart"
    assert service.restarts == 1


def test_window_wrap_around_midnight():
    assert in_restart_window("23:00-01:00", datetime.time(0, 30))
    assert in_restart_window("23:00-01:00", datetime.time(23, 30))
    assert not in_restart_window("23:00-01:00", datetime.time(12, 0))
    assert in_restart_window("04:00-05:00", datetime.time(4, 30))
    assert not in_restart_window("04:00-05:00", datetime.time(6, 0))


def test_rollback_to_last_good_when_new_config_does_not_start(env):
    paths, current = env
    service = StubService()
    # с новым конфигом ядро не отвечает, после отката (второй перезапуск) — отвечает
    api = StubApi(service=service, healthy_after=2)
    outcome = _applier(paths, api, service, wait_seconds=0.2).apply(
        _needs_restart(current), force_now=True
    )
    assert outcome.mode == "rollback"
    assert service.restarts == 2
    assert _on_disk(paths) == current


def test_failed_when_rollback_does_not_help(env):
    paths, current = env
    service = StubService()
    api = StubApi(service=service, healthy_after=None)
    outcome = _applier(paths, api, service, wait_seconds=0.2).apply(
        _needs_restart(current), force_now=True
    )
    assert outcome.mode == "failed"
    assert service.restarts == 2
    assert _on_disk(paths) == current  # на диске — last-good, не неработающий конфиг


def test_first_start_without_last_good_reports_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    paths = Paths.from_env()
    paths.ensure()
    config = _build()[0].config
    service = StubService()
    ok = _applier(paths, StubApi(service=service, healthy_after=1), service).apply(config)
    assert ok.mode == "restart" and _on_disk(paths) == config

    other = tmp_path / "second"
    monkeypatch.setenv("XGW_ROOT", str(other))
    paths = Paths.from_env()
    paths.ensure()
    failed = _applier(paths, StubApi(healthy_after=None), wait_seconds=0.2).apply(config)
    assert failed.mode == "failed"


def test_apply_waits_for_file_lock(env):
    """Два применения одновременно не идут: второе ждёт блокировку и сдаётся по таймауту."""
    import xgw.apply.applier as applier_module
    from xgw.paths import LockTimeout

    paths, current = env
    original = applier_module.file_lock
    applier_module.file_lock = lambda path: original(path, timeout=0.3, poll=0.05)
    try:
        with file_lock(paths.lock_file), pytest.raises(LockTimeout):
            _applier(paths, StubApi()).apply(_with_extra_outbound(current))
    finally:
        applier_module.file_lock = original
    assert _on_disk(paths) == current
