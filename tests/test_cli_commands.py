"""Команды этапа 2: apply, status, servers, probe, pin/unpin, run — на подменённом ядре."""

import json
import time

import links
import pytest

from xgw import cli, engine
from xgw.apply.applier import ApplyOutcome
from xgw.cli import main
from xgw.paths import Paths
from xgw.store import Store
from xgw.watch.scan import ScanResult
from xgw.xraycore.api import ApiError, BalancerInfo


class FakeApi:
    def __init__(self):
        self.calls: list[tuple] = []
        self.fail = False
        self.state = BalancerInfo(override=None, selects=())

    def pin(self, balancer, tag):
        if self.fail:
            raise ApiError("нет связи с ядром")
        self.calls.append(("pin", balancer, tag))

    def unpin(self, balancer):
        self.calls.append(("unpin", balancer))

    def balancer_state(self, balancer):
        return self.state


class FakeApplier:
    def __init__(self, api, mode="api"):
        self.api = api
        self.mode = mode
        self.calls: list[tuple[dict, bool]] = []

    def apply(self, config, *, urgent=False, force_now=False):
        self.calls.append((config, force_now))
        return ApplyOutcome(self.mode, ops=["ado: spare-xx-0000"] if self.mode == "api" else [])


@pytest.fixture()
def gateway(tmp_path, monkeypatch):
    """Шлюз с применённым конфигом; Xray, API и метрики подменены."""
    monkeypatch.setenv("XGW_ROOT", str(tmp_path / "root"))
    monkeypatch.delenv("XGW_XRAY_BIN", raising=False)
    config = tmp_path / "config.toml"
    config.write_text(
        "[manual]\nlinks = [" + ", ".join(f'"{link}"' for link in links.FULL_LINKS) + "]\n"
        '[filters]\nexclude_regex = ""\nmax_members = 2\n[dns]\nbootstrap = []\n',
        encoding="utf-8",
    )
    paths = Paths.from_env()
    assert main(["generate", "--config", str(config), "--no-validate",
                 "--out", str(paths.xray_config_file)]) == 0

    api = FakeApi()
    applier = FakeApplier(api)
    monkeypatch.setattr(cli.validate, "find_xray", lambda *_args: tmp_path / "xray")
    monkeypatch.setattr(cli.validate, "validate_config", lambda *_args: (True, "OK"))
    monkeypatch.setattr(cli.engine, "make_api", lambda *_args: api)
    monkeypatch.setattr(cli.engine, "make_applier", lambda *_args: applier)
    monkeypatch.setattr(cli.binary, "installed_version", lambda *_args: (26, 3, 27))

    def no_metrics(_port, **_kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(cli.metrics, "fetch_metrics", no_metrics)

    class Gateway:
        pass

    gw = Gateway()
    gw.config, gw.paths, gw.api, gw.applier, gw.tmp = config, paths, api, applier, tmp_path
    gw.run = lambda *args: main([*args, "--config", str(config)])
    gw.applied = lambda: json.loads(paths.xray_config_file.read_text(encoding="utf-8"))
    gw.tags = lambda role: [o["tag"] for o in gw.applied()["outbounds"]
                            if o["tag"].startswith(role + "-")]
    return gw


def _alive(gateway, monkeypatch, dead=()):
    observatory = {
        tag: ({"outbound_tag": tag} if tag in dead else {"alive": True, "delay": 42})
        for tag in gateway.tags("proxy")
    }
    payload = {"observatory": observatory}
    monkeypatch.setattr(cli.metrics, "fetch_metrics", lambda *_args, **_kwargs: payload)


# --- apply ---------------------------------------------------------------------


def test_apply_reports_api_path(gateway, capsys):
    assert gateway.run("apply") == 0
    assert "применено через API без перезапуска" in capsys.readouterr().out
    assert len(gateway.applier.calls) == 1 and gateway.applier.calls[0][1] is False
    store = Store(gateway.paths.db_file)
    assert any(event["kind"] == "apply" for event in store.recent_events())
    store.close()


def test_apply_now_forces_restart(gateway):
    assert gateway.run("apply", "--now") == 0
    assert gateway.applier.calls[0][1] is True


def test_apply_deferred_explains_how_to_force(gateway, capsys):
    gateway.applier.mode = "restart_deferred"
    assert gateway.run("apply") == 0
    out = capsys.readouterr().out
    assert "отложен" in out and "xgw apply --now" in out


@pytest.mark.parametrize("mode", ["rejected", "rollback", "failed"])
def test_apply_failure_exit_code(gateway, mode):
    gateway.applier.mode = mode
    assert gateway.run("apply") == 1


def test_apply_without_xray(gateway, monkeypatch, capsys):
    monkeypatch.setattr(cli.validate, "find_xray", lambda *_args: None)
    assert gateway.run("apply") == 1
    assert "xray не найден" in capsys.readouterr().err
    assert gateway.applier.calls == []


def test_apply_refuses_incomplete_subscriptions(gateway, capsys):
    """Подписка недоступна и кэша нет — её серверы из работающего ядра не убираем."""
    gateway.config.write_text(
        gateway.config.read_text(encoding="utf-8")
        + f'[[subscriptions]]\nname = "gone"\nurl = "{(gateway.tmp / "missing.txt").as_uri()}"\n',
        encoding="utf-8",
    )
    assert gateway.run("apply") == 1
    assert "не все подписки получены" in capsys.readouterr().err
    assert gateway.applier.calls == []


def test_apply_restores_active_pin(gateway):
    target = gateway.tags("proxy")[0]
    store = Store(gateway.paths.db_file)
    store.set_meta("pin", json.dumps({"tag": target, "until": time.time() + 600}))
    store.close()
    assert gateway.run("apply") == 0
    assert gateway.api.calls == [("pin", "auto", target)]  # adrules сбросил закрепление в ядре


def test_lock_timeout_is_reported(gateway, monkeypatch, capsys):
    from xgw.paths import LockTimeout

    def busy(*_args, **_kwargs):
        raise LockTimeout("блокировка занята дольше 60 с")

    gateway.applier.apply = busy
    assert gateway.run("apply") == 1
    assert "идёт другое применение" in capsys.readouterr().err


# --- status / servers ----------------------------------------------------------


def test_status_without_applied_config(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path / "root"))
    config = tmp_path / "config.toml"
    config.write_text("[manual]\nlinks = []\n", encoding="utf-8")
    assert main(["status", "--config", str(config)]) == 1
    assert "xgw apply" in capsys.readouterr().err


def test_status_one_shot_when_daemon_is_not_running(gateway, monkeypatch, capsys):
    members = gateway.tags("proxy")
    _alive(gateway, monkeypatch, dead=members[1:])
    gateway.api.state = BalancerInfo(override=None, selects=(members[0],))
    assert gateway.run("status") == 0
    out = capsys.readouterr().out
    assert "демон XGW не запущен" in out
    assert "Xray 26.3.27: отвечает" in out
    assert "жив, 42 мс" in out and "МЁРТВ" in out
    assert "← выбран" in out and "Трафик проверок" in out
    assert "NL-1" in out  # имена узлов — из хранилища


def test_status_xray_down(gateway, capsys):
    assert gateway.run("status") == 0
    out = capsys.readouterr().out
    assert "НЕ ОТВЕЧАЕТ" in out and "нет данных" in out


def test_status_prefers_fresh_daemon_snapshot(gateway, capsys):
    snapshot = {
        "updated": time.time(), "daemon": True, "state": "DEGRADED",
        "action": "часть серверов недоступна — замена на запасные", "since": time.time() - 120,
        "xray": {"ok": True, "version": "26.3.27"}, "members": [], "spares": [],
        "selecting": [], "pin": None, "quota": {}, "budget": {}, "pending_restart": True,
        "events": [{"ts": time.time(), "kind": "rotation", "detail": "замена участников"}],
    }
    gateway.paths.status_file.parent.mkdir(parents=True, exist_ok=True)
    gateway.paths.status_file.write_text(json.dumps(snapshot), encoding="utf-8")
    assert gateway.run("status") == 0
    out = capsys.readouterr().out
    assert "Состояние: DEGRADED" in out and "замена на запасные" in out
    assert "Ожидает окна перезапуска" in out and "rotation: замена участников" in out

    snapshot["updated"] = time.time() - 3600  # демон давно не писал статус — он не запущен
    gateway.paths.status_file.write_text(json.dumps(snapshot), encoding="utf-8")
    assert gateway.run("status") == 0
    assert "демон XGW не запущен" in capsys.readouterr().out


def test_status_json_and_quota(gateway, monkeypatch, capsys):
    _alive(gateway, monkeypatch)
    store = Store(gateway.paths.db_file)
    store.set_meta("quota", json.dumps(
        {"main": {"upload": 10**9, "download": 39 * 10**9, "total": 100 * 10**9,
                  "expire": 1798761600}}))
    store.close()
    assert gateway.run("status", "--json") == 0
    status = json.loads(capsys.readouterr().out)
    assert status["daemon"] is False and status["xray"]["ok"] is True
    assert [member["alive"] for member in status["members"]] == [True, True]
    assert status["budget"]["limit_mb"] == 1024
    assert gateway.run("status") == 0
    assert "израсходовано 40.0 ГБ из 100.0 ГБ" in capsys.readouterr().out


def test_servers_lists_members_and_spares(gateway, monkeypatch, capsys):
    _alive(gateway, monkeypatch)
    assert gateway.run("servers") == 0
    out = capsys.readouterr().out
    assert "Участники балансировщика (2)" in out and "Запасные (2)" in out
    assert all(tag in out for tag in gateway.tags("proxy") + gateway.tags("spare"))
    assert "не проверялся" in out and "Состояние" not in out


# --- probe ---------------------------------------------------------------------


def _fake_scans(monkeypatch, verdicts: dict[str, str]):
    seen: list[tuple[str, str]] = []

    def scan_node(info, _cfg, *, probe_pass, **_kwargs):
        seen.append((info.tag, probe_pass))
        verdict = verdicts.get(info.tag, "OK")
        size = 65536 if verdict == "OK" else 16384
        return ScanResult(info.tag, verdict, size, 0.4, "" if verdict == "OK" else "тишина 5 с")

    monkeypatch.setattr(cli.scan, "scan_node", scan_node)
    return seen


def test_probe_all_saves_results(gateway, monkeypatch, capsys):
    spare = gateway.tags("spare")[0]
    seen = _fake_scans(monkeypatch, {spare: "FROZEN"})
    assert gateway.run("probe", "--all") == 0
    out = capsys.readouterr().out
    assert len(seen) == 4  # два участника и два запасных
    # пароль проб — из применённого конфига: у работающего Xray действует именно он
    password = gateway.applied()["inbounds"][3]["settings"]["accounts"][0]["pass"]
    assert {used for _tag, used in seen} == {password}
    assert "FROZEN" in out and "16384 Б" in out and out.count("OK") == 3
    store = Store(gateway.paths.db_file)
    scans = store.scans()
    store.close()
    assert scans[spare.replace("spare-", "probe-")]["verdict"] == "FROZEN"
    assert len(scans) == 4
    capsys.readouterr()
    assert gateway.run("servers") == 0
    assert "FROZEN, 16384 Б" in capsys.readouterr().out  # результат виден в списке запасных


def test_probe_single_tag_exit_code(gateway, monkeypatch, capsys):
    member, spare = gateway.tags("proxy")[0], gateway.tags("spare")[0]
    seen = _fake_scans(monkeypatch, {spare: "STALL_BEFORE_BODY"})
    assert gateway.run("probe", member) == 0
    assert gateway.run("probe", spare) == 1  # узел не прошёл проверку
    assert [tag for tag, _password in seen] == [member, spare]
    capsys.readouterr()
    assert gateway.run("probe", "proxy-zz-0000") == 2
    assert "нет в рабочем конфиге" in capsys.readouterr().err


# --- pin / unpin ---------------------------------------------------------------


def test_pin_and_unpin(gateway, capsys):
    target = gateway.tags("proxy")[0]
    assert gateway.run("pin", target, "--ttl", "5m") == 0
    out = capsys.readouterr().out
    assert "Автопереключение на это время отключено" in out
    assert "демон XGW не запущен" in out  # срок некому отслеживать — предупреждаем
    assert gateway.api.calls == [("pin", "auto", target)]
    store = Store(gateway.paths.db_file)
    pin = json.loads(store.get_meta("pin"))
    store.close()
    assert pin["tag"] == target and 290 < pin["until"] - time.time() <= 300

    assert gateway.run("status") == 0
    assert f"Закреплён вручную: {target}" in capsys.readouterr().out

    assert gateway.run("unpin") == 0
    assert gateway.api.calls[-1] == ("unpin", "auto")
    store = Store(gateway.paths.db_file)
    assert store.get_meta("pin") == ""
    store.close()


def test_pin_validates_arguments(gateway, capsys):
    target, spare = gateway.tags("proxy")[0], gateway.tags("spare")[0]
    assert gateway.run("pin", target, "--ttl", "вечно") == 2
    assert gateway.run("pin", target, "--ttl", "48h") == 2  # дольше суток закреплять нельзя
    assert gateway.run("pin", spare) == 2  # запасной не в балансировщике
    assert "не участник балансировщика" in capsys.readouterr().err
    assert gateway.api.calls == []


def test_pin_api_error(gateway, capsys):
    gateway.api.fail = True
    assert gateway.run("pin", gateway.tags("proxy")[0]) == 1
    assert "нет связи с ядром" in capsys.readouterr().err
    store = Store(gateway.paths.db_file)
    assert not store.get_meta("pin")
    store.close()


# --- run -----------------------------------------------------------------------


def test_run_once(gateway, monkeypatch, capsys):
    import xgw.daemon

    created: list = []

    class FakeDaemon:
        def __init__(self, cfg, paths, *, xray_bin):
            self.store = Store(paths.db_file)
            self.ticks = 0
            created.append(self)

        def tick(self):
            self.ticks += 1
            return "HEALTHY"

    monkeypatch.setattr(xgw.daemon, "Daemon", FakeDaemon)
    assert gateway.run("run", "--once") == 0
    assert created[0].ticks == 1 and "HEALTHY" in capsys.readouterr().out


def test_describe_outcomes():
    assert engine.describe(ApplyOutcome("unchanged")) == "изменений нет"
    text = engine.describe(ApplyOutcome("restart_deferred", ops=["секция dns"], detail="окно"))
    assert text == "нужен перезапуск Xray — отложен: секция dns (окно)"
