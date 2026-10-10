"""Сеть шлюза без ядра: ip rule, sysctl, dnsmasq и управление перехватом (Capture)."""

import json
import shutil
import subprocess

import pytest
from fakenet import FakeKernel

from xgw.config import Config
from xgw.net import cmd, dnsmasq, iprule, lan, sysctl
from xgw.net.capture import Capture, CaptureError
from xgw.paths import Paths

# --- ip rule / ip route --------------------------------------------------------


def test_iprule_ensure_is_idempotent():
    kernel = FakeKernel()
    assert not iprule.present(1, 100, kernel)
    for _ in range(3):
        iprule.ensure(1, 100, kernel)
    assert kernel.rules == [{"priority": 100, "src": "all", "fwmark": "0x1", "table": "100"}]
    assert kernel.route and iprule.present(1, 100, kernel)
    assert len(kernel.commands("ip", "rule", "add")) == 1  # дубликатов нет


def test_iprule_ensure_removes_duplicates_and_ignores_foreign_rules():
    kernel = FakeKernel()
    ours = {"priority": 100, "src": "all", "fwmark": "0x1", "table": "100"}
    foreign = {"priority": 200, "src": "all", "fwmark": "0x1", "table": "200"}
    kernel.rules = [dict(ours), dict(foreign), dict(ours)]
    iprule.ensure(1, 100, kernel)
    assert kernel.rules.count(ours) == 1 and foreign in kernel.rules


def test_iprule_remove():
    kernel = FakeKernel()
    iprule.remove(1, 100, kernel)  # нечего убирать — не ошибка
    assert kernel.commands("ip", "rule", "del") == []
    iprule.ensure(1, 100, kernel)
    iprule.remove(1, 100, kernel)
    assert kernel.rules == [] and not kernel.route


def test_cmd_run_reports_missing_program_and_failure():
    with pytest.raises(cmd.CommandError, match="программа не найдена"):
        cmd.run(["xgw-no-such-program"])
    import sys

    with pytest.raises(cmd.CommandError, match="boom"):
        cmd.run([sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"])
    assert cmd.run([sys.executable, "-c", "print(input())"], input="ok\n").strip() == "ok"


# --- sysctl --------------------------------------------------------------------


def test_sysctl_file_and_proc(tmp_path):
    text = sysctl.file_text()
    assert "net.ipv4.ip_forward = 1" in text and "net.ipv6.conf.all.forwarding = 0" in text
    assert sysctl.read(sysctl.IP_FORWARD, tmp_path) is None
    (tmp_path / "net/ipv4").mkdir(parents=True)
    (tmp_path / sysctl.IP_FORWARD).write_text("0\n")
    sysctl.write(sysctl.IP_FORWARD, "1", tmp_path)
    assert sysctl.read(sysctl.IP_FORWARD, tmp_path) == "1"


# --- LAN и dnsmasq -------------------------------------------------------------


def _lan_cfg() -> Config:
    cfg = Config()
    cfg.network.lan_if = "enp3s0"
    return cfg


def test_static_leases_are_validated():
    cfg = _lan_cfg()
    cfg.network.static_leases = [
        "AA:BB:CC:DD:EE:FF,192.168.50.20,tv",
        "aa:bb:cc:dd:ee:01, 192.168.50.21",
        "не mac,192.168.50.22",
        "aa:bb:cc:dd:ee:02,не адрес",
        "aa:bb:cc:dd:ee:ff,192.168.50.23",  # MAC уже был
        "aa:bb:cc:dd:ee:03,192.168.50.24,имя с пробелом\ndhcp-option=3",
    ]
    leases, warnings = lan.parse_leases(cfg)
    assert leases == [
        lan.Lease("aa:bb:cc:dd:ee:ff", "192.168.50.20", "tv"),
        lan.Lease("aa:bb:cc:dd:ee:01", "192.168.50.21"),
        lan.Lease("aa:bb:cc:dd:ee:03", "192.168.50.24"),  # имя отброшено, аренда осталась
    ]
    assert len(warnings) == 4


def test_dnsmasq_config():
    cfg = _lan_cfg()
    cfg.network.static_leases = ["aa:bb:cc:dd:ee:ff,192.168.50.20,tv"]
    text, warnings = dnsmasq.render(cfg)
    assert warnings == []
    lines = text.splitlines()
    assert "port=0" in lines  # DNS обслуживает Xray, конфликта с systemd-resolved нет
    assert "interface=enp3s0" in lines and "bind-interfaces" in lines
    assert "dhcp-range=192.168.50.100,192.168.50.200,12h" in lines
    assert "dhcp-option=option:router,192.168.50.1" in lines
    assert "dhcp-option=option:dns-server,192.168.50.1" in lines
    assert "dhcp-authoritative" in lines
    assert "dhcp-host=aa:bb:cc:dd:ee:ff,192.168.50.20,tv" in lines


def test_dnsmasq_router_mode_serves_single_lease():
    cfg = _lan_cfg()
    cfg.network.router_mode = "router"
    cfg.network.router_mac = "11-22-33-44-55-66"
    text, warnings = dnsmasq.render(cfg)
    assert warnings == []
    assert "dhcp-range=192.168.50.100,static,12h" in text
    assert "dhcp-host=11:22:33:44:55:66,192.168.50.100,router" in text
    cfg.network.router_mac = ""
    text, warnings = dnsmasq.render(cfg)
    assert "dhcp-range=192.168.50.100,192.168.50.200,12h" in text
    assert any("router_mac" in warning for warning in warnings)


def test_dnsmasq_not_needed_or_misconfigured():
    assert dnsmasq.render(Config()) == ("", [])  # только эта машина
    cfg = _lan_cfg()
    cfg.network.dhcp_range = "192.168.60.100,192.168.60.200,12h"  # не та сеть
    text, warnings = dnsmasq.render(cfg)
    assert text == "" and "dhcp_range" in warnings[0]
    cfg = _lan_cfg()
    cfg.network.lan_address = "шлюз"
    text, warnings = dnsmasq.render(cfg)
    assert text == "" and "lan_address" in warnings[0]


@pytest.mark.skipif(shutil.which("dnsmasq") is None, reason="dnsmasq не установлен")
def test_real_dnsmasq_accepts_config(tmp_path):
    cfg = _lan_cfg()
    cfg.network.static_leases = ["aa:bb:cc:dd:ee:ff,192.168.50.20,tv"]
    for mode in ("ap", "router"):
        cfg.network.router_mode, cfg.network.router_mac = mode, "11:22:33:44:55:66"
        conf = tmp_path / f"{mode}.conf"
        conf.write_text(dnsmasq.render(cfg)[0], encoding="utf-8")
        done = subprocess.run(
            ["dnsmasq", "--test", f"--conf-file={conf}"], capture_output=True, text=True
        )
        assert done.returncode == 0, done.stderr


# --- Capture -------------------------------------------------------------------


@pytest.fixture()
def gateway(tmp_path, monkeypatch):
    """Шлюз с LAN на подменённом ядре; ip_forward до XGW был выключен."""
    monkeypatch.setenv("XGW_ROOT", str(tmp_path / "root"))
    paths = Paths.from_env()
    paths.ensure()
    proc = tmp_path / "proc"
    (proc / "net/ipv4").mkdir(parents=True)
    (proc / sysctl.IP_FORWARD).write_text("0\n")
    cfg = Config()
    cfg.network.lan_if = "lan0"
    kernel = FakeKernel()
    capture = Capture(cfg, paths, runner=kernel, proc_sys=proc, time_uids=())
    capture.kernel, capture.proc = kernel, proc
    return capture


def test_enable_loads_rules_route_and_forwarding(gateway):
    assert gateway.mode() == "on" and gateway.loaded() is False  # ещё ничего не загружено
    assert gateway.enable() == "on"
    kernel = gateway.kernel
    assert "tproxy to 127.0.0.1:12345" in kernel.table and ("ip6", "xgw6") in kernel.tables
    assert kernel.rules[0]["fwmark"] == "0x1" and kernel.route
    assert sysctl.read(sysctl.IP_FORWARD, gateway.proc) == "1"
    assert gateway.loaded() is True
    # Сначала маршрут для помеченных пакетов, потом правила, которые их метят.
    assert kernel.index("ip", "rule", "add") < kernel.index("nft", "-f")
    assert json.loads(gateway.state_file.read_text())["enabled"] is True


def test_disable_keeps_router_and_survives_restart(gateway):
    gateway.enable()
    gateway.kernel.calls.clear()
    assert gateway.disable() == "off"
    kernel = gateway.kernel
    assert "tproxy" not in kernel.table and "masquerade" in kernel.table
    assert kernel.rules == [] and not kernel.route
    assert gateway.loaded() is True  # ядро соответствует режиму «снят»
    # Сначала перестаём метить пакеты, потом убираем их маршрут.
    assert kernel.index("nft", "-f") < kernel.index("ip", "rule", "del")
    # Выбор пользователя переживает перезагрузку: xgw-net.service загрузит режим «снят».
    again = Capture(gateway.cfg, gateway.paths, runner=FakeKernel(), proc_sys=gateway.proc)
    assert again.mode() == "off" and again.up() == "off"
    assert "tproxy" not in again.runner.table
    assert gateway.enable() == "on" and "tproxy" in kernel.table


def test_fail_open_is_temporary(gateway):
    gateway.enable()
    assert gateway.open() == "open"
    assert "tproxy" not in gateway.kernel.table and gateway.loaded() is True
    assert gateway.wanted() is True  # выбор пользователя не тронут
    assert gateway.up() == "open"  # повторная загрузка режима не меняет
    assert gateway.close() == "on" and "tproxy" in gateway.kernel.table
    gateway.open()
    assert gateway.enable() == "on"  # явное включение снимает и временную метку


def test_loaded_detects_missing_and_stale_rules(gateway):
    gateway.enable()
    del gateway.kernel.tables[("ip", "xgw")]  # чужой flush ruleset
    assert gateway.loaded() is False
    assert gateway.up() == "on" and gateway.loaded() is True
    gateway.kernel.rules.clear()  # правило ip rule пропало
    assert gateway.loaded() is False
    gateway.up()
    gateway.disable()
    gateway.kernel.tables[("ip", "xgw")] += "    chain prerouting {\n    }\n"  # остаток перехвата
    assert gateway.loaded() is False
    gateway.kernel.forbidden = True
    assert gateway.loaded() is None  # без root узнать нельзя
    assert gateway.describe()["loaded"] is None


def test_down_removes_everything_and_restores_forwarding(gateway):
    gateway.enable()
    gateway.open()
    gateway.down()
    assert gateway.kernel.tables == {} and gateway.kernel.rules == [] and not gateway.kernel.route
    assert sysctl.read(sysctl.IP_FORWARD, gateway.proc) == "0"  # как было до XGW
    assert not gateway.open_marker.exists()
    gateway.down()  # повторно — не ошибка
    # Форвардинг, включённый до XGW, XGW не выключает.
    (gateway.proc / sysctl.IP_FORWARD).write_text("1\n")
    gateway.enable()
    gateway.down()
    assert sysctl.read(sysctl.IP_FORWARD, gateway.proc) == "1"


def test_only_this_machine_has_no_router_part(gateway):
    gateway.cfg.network.lan_if = ""
    assert gateway.capturing and gateway.enable() == "on"
    assert "chain output" in gateway.kernel.table and "forward" not in gateway.kernel.table
    assert sysctl.read(sysctl.IP_FORWARD, gateway.proc) == "0"  # форвардинг не нужен
    assert gateway.disable() == "off"
    assert gateway.kernel.tables == {}  # без LAN и без перехвата таблица не нужна
    assert gateway.loaded() is True


def test_capture_switched_off_in_config(gateway):
    gateway.cfg.capture.lan = gateway.cfg.capture.local = False
    assert gateway.mode() == "none" and not gateway.capturing and gateway.configured
    assert gateway.up() == "none"  # LAN есть — шлюз работает обычным роутером
    assert "tproxy" not in gateway.kernel.table and "masquerade" in gateway.kernel.table
    gateway.cfg.network.lan_if = ""
    assert not gateway.configured


def test_failure_is_reported_and_keeps_previous_rules(gateway):
    gateway.enable()
    before = gateway.kernel.table
    gateway.kernel.refuse = "nft -c"
    with pytest.raises(CaptureError, match="отказано"):
        gateway.disable()
    assert gateway.kernel.table == before  # правила не тронуты: проверка была до загрузки
    assert gateway.wanted() is True and gateway.mode() == "on"  # выбор не запомнен


def test_describe(gateway):
    gateway.cfg.network.static_leases = ["aa:bb:cc:dd:ee:ff,192.168.50.20"]
    gateway.cfg.network.bypass_hosts = ["aa:bb:cc:dd:ee:ff"]
    gateway.enable()
    assert gateway.describe() == {
        "mode": "on", "lan_if": "lan0", "lan": True, "local": True,
        "bypass": ["192.168.50.20"], "fail_mode": "closed", "loaded": True,
    }
