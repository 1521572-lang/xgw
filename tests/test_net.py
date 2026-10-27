"""Сеть шлюза без ядра: ip rule, sysctl, dnsmasq и управление перехватом (Capture)."""

import dataclasses
import json
import shutil
import subprocess

import fakexray
import pytest
from fakenet import FakeKernel

from xgw.config import Config
from xgw.net import cmd, dnsmasq, iprule, lan, nft, sysctl, tun
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


def test_iprule_ipv6_uses_its_own_rule_and_route():
    kernel = FakeKernel()
    assert not iprule.present(1, 100, kernel, 6)
    for _ in range(2):
        iprule.ensure(1, 100, kernel, 6)
    assert kernel.rules6 == [{"priority": 100, "src": "all", "fwmark": "0x1", "table": "100"}]
    assert kernel.route6 and iprule.present(1, 100, kernel, 6)
    assert len(kernel.commands("ip", "-6", "rule", "add")) == 1
    assert set(kernel.commands("ip", "-6", "route", "replace")) == {
        ("ip", "-6", "route", "replace", "local", "::/0", "dev", "lo", "table", "100")
    }  # replace идемпотентен, поэтому вызывается при каждом ensure
    # IPv4 не затронут: у семейств правила и маршруты отдельные.
    assert kernel.rules == [] and not kernel.route and not iprule.present(1, 100, kernel)
    iprule.remove(1, 100, kernel, 6)
    assert kernel.rules6 == [] and not kernel.route6
    iprule.remove(1, 100, kernel, 6)  # повторно — не ошибка


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
    assert "interface=enp3s0" in lines and "bind-dynamic" in lines
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
    """Шлюз с LAN на подменённом ядре; ip_forward до XGW был выключен.
    IPv6 в «ядре» нет: каталога net/ipv6 в подменённом /proc/sys не создано."""
    monkeypatch.setenv("XGW_ROOT", str(tmp_path / "root"))
    paths = Paths.from_env()
    paths.ensure()
    proc = tmp_path / "proc"
    (proc / "net/ipv4").mkdir(parents=True)
    (proc / sysctl.IP_FORWARD).write_text("0\n")
    cfg = Config()
    cfg.network.lan_if = "lan0"
    fakexray.write(paths)  # Xray запущен с inbound'ом перехвата
    kernel = FakeKernel()
    capture = Capture(cfg, paths, runner=kernel, proc_sys=proc, time_uids=())
    capture.kernel, capture.proc = kernel, proc
    capture.sys_net = tmp_path / "sys-class-net"  # мостов Docker нет
    # Контейнеры — в своих проверках ниже: здесь маршруты и правила только LAN и машины.
    cfg.capture.containers = False
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


def test_lan_subnet_throw_keeps_lan_alive_with_src_valid_mark(gateway):
    """Issue #1: при net.ipv4.conf.all.src_valid_mark = 1 (его ставит tailscaled) ядро
    проверяет источник пакета LAN с меткой по таблице TPROXY, видит там local и молча
    отбрасывает пакет. Маршрут throw для подсети LAN отправляет проверку в main."""
    kernel, proc = gateway.kernel, gateway.proc
    (proc / "net/ipv4/conf/all").mkdir(parents=True)
    (proc / sysctl.SRC_VALID_MARK).write_text("1\n")
    kernel.src_valid_mark = True
    kernel.lan_links["lan0"] = True
    gateway.enable()
    assert {"type": "throw", "dst": "192.168.50.0/24"} in kernel.routes(100)
    assert gateway.loaded() is True and gateway.lan_path() == ""
    # Маршрут пропал (чужой flush): пакеты LAN гибнут, правила «не те» — демон загрузит.
    kernel.routes(100).remove({"type": "throw", "dst": "192.168.50.0/24"})
    problem = gateway.lan_path()
    assert "не доходят до Xray" in problem and "src_valid_mark = 1" in problem
    assert gateway.loaded() is False
    gateway.up()
    assert gateway.lan_path() == "" and gateway.loaded() is True
    # Подсеть LAN сменили: старый throw уходит, новый появляется.
    gateway.cfg.network.lan_address = "10.9.0.1/24"
    assert gateway.loaded() is False
    gateway.up()
    throws = [route for route in kernel.routes(100) if route.get("type") == "throw"]
    assert throws == [{"type": "throw", "dst": "10.9.0.0/24"}] and gateway.lan_path() == ""
    # Интерфейс LAN выключен — проверять нечего, это не сбой перехвата.
    kernel.lan_links["lan0"] = False
    assert gateway.lan_path() == ""
    # Перехват снят: таблица TPROXY не нужна вовсе, throw уходит вместе с ней.
    gateway.disable()
    assert kernel.routes(100) == [] and gateway.lan_path() == ""


def test_iprule_throw_routes():
    kernel = FakeKernel()
    iprule.ensure(1, 100, kernel, throws=("192.168.60.0/24",))
    assert iprule.present(1, 100, kernel, throws=("192.168.60.0/24",))
    assert not iprule.present(1, 100, kernel)  # лишний throw — правила «не те»
    iprule.ensure(1, 100, kernel, throws=("192.168.60.0/24",))
    assert len(kernel.commands("ip", "route", "replace", "throw")) == 1  # уже есть
    iprule.ensure(1, 100, kernel)
    assert not [route for route in kernel.routes(100) if route.get("type") == "throw"]
    iprule.ensure(1, 100, kernel, throws=("192.168.60.0/24",))
    iprule.remove(1, 100, kernel)
    assert kernel.routes(100) == [] and kernel.rules == []


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


def _state(capture) -> dict:
    return json.loads(capture.state_file.read_text())


def test_bbr_is_switched_on_and_the_previous_algorithm_comes_back(gateway):
    """network.tcp_bbr (0.1.11): xgw-net ставит BBR и помнит прежний алгоритм; повторная
    загрузка правил его не перетирает, `xgw net down` возвращает."""
    proc = gateway.proc
    (proc / sysctl.TCP_CONGESTION).write_text("cubic\n")
    gateway.enable()
    assert sysctl.read(sysctl.TCP_CONGESTION, proc) == "bbr"
    assert _state(gateway)["tcp_congestion_before"] == "cubic"
    gateway.up()
    assert _state(gateway)["tcp_congestion_before"] == "cubic"
    gateway.down()
    assert sysctl.read(sysctl.TCP_CONGESTION, proc) == "cubic"
    assert "tcp_congestion_before" not in _state(gateway)


def test_bbr_switched_off_in_the_config_gives_the_previous_algorithm_back(gateway):
    proc = gateway.proc
    (proc / sysctl.TCP_CONGESTION).write_text("cubic\n")
    gateway.enable()
    gateway.cfg.network.tcp_bbr = False
    gateway.up()
    assert sysctl.read(sysctl.TCP_CONGESTION, proc) == "cubic"
    assert "tcp_congestion_before" not in _state(gateway)


def test_bbr_set_before_xgw_is_left_alone(gateway):
    proc = gateway.proc
    (proc / sysctl.TCP_CONGESTION).write_text("bbr\n")
    gateway.enable()
    gateway.down()
    assert sysctl.read(sysctl.TCP_CONGESTION, proc) == "bbr"
    assert "tcp_congestion_before" not in _state(gateway)


def test_kernel_without_bbr_keeps_its_algorithm(gateway, monkeypatch):
    proc = gateway.proc
    (proc / sysctl.TCP_CONGESTION).write_text("cubic\n")
    write = sysctl.write

    def refuse(key, value, root=sysctl.PROC_SYS):
        if key == sysctl.TCP_CONGESTION and value == "bbr":
            raise OSError(2, "No such file or directory")  # так отвечает ядро без tcp_bbr
        write(key, value, root)

    monkeypatch.setattr(sysctl, "write", refuse)
    assert gateway.enable() == "on"  # перехват включается как обычно
    assert sysctl.read(sysctl.TCP_CONGESTION, proc) == "cubic"
    assert "tcp_congestion_before" not in _state(gateway)


def test_enable_refuses_without_applied_tproxy_inbound(gateway):
    """Пока применённый конфиг Xray без inbound'а перехвата, включать его нельзя:
    правила отправили бы весь трафик на порт, который никто не слушает, и при
    fail_mode = "closed" машина осталась бы без интернета (так и случилось на
    настоящей машине, когда правка настроек ждала окна перезапуска).
    capture.hold = "direct" — прежнее поведение: до перезапуска Xray сеть идёт напрямую."""
    gateway.cfg.capture.hold = "direct"
    fakexray.write(gateway.paths, {"inbounds": [{"tag": "socks-in"}]})
    assert gateway.enable() == "off"
    assert "нет inbound tproxy-in на порту 12345" in gateway.held
    assert gateway.describe()["inbound_missing"] == gateway.held
    assert gateway.mode() == "on" and gateway.effective_mode() == "off"
    # Загружено ровно то, что должно быть в этом положении: демон не станет
    # перезагружать правила на каждом шаге.
    assert gateway.loaded() is True
    kernel = gateway.kernel
    assert "tproxy" not in kernel.table  # трафик не перехвачен
    assert kernel.rules == [] and not kernel.route  # маршрут по метке тоже не нужен
    assert "masquerade" in kernel.table  # шлюз остаётся роутером
    # Желание человека запомнено: перехват включится, когда применится конфиг.
    assert json.loads(gateway.state_file.read_text())["enabled"] is True
    fakexray.write(gateway.paths)
    assert gateway.loaded() is False  # конфиг применён — пора загружать перехват
    assert gateway.up() == "on"
    assert gateway.held == "" and gateway.describe()["inbound_missing"] == ""
    assert "tproxy to 127.0.0.1:12345" in gateway.kernel.table


def test_capture_refuses_when_applied_config_is_missing_or_broken(gateway):
    """Файла нет или он битый — это тоже «Xray ещё не с inbound'ом перехвата». Рабочего
    конфига нет вовсе (первая установка, подписки ещё нет) — VPN ещё нечем включать, и сеть
    идёт напрямую даже при hold = "block"; конфиг есть, но без inbound'а — blocked."""
    for text, mode in ((None, "off"), ("{не json", "off"), ('{"inbounds": "нет"}', "blocked")):
        if text is None:
            gateway.paths.xray_config_file.unlink()
        else:
            gateway.paths.xray_config_file.write_text(text, encoding="utf-8")
        assert gateway.inbound_problem()
        assert gateway.up() == mode and gateway.held
        assert gateway.effective_mode() == mode
    # Другой порт перехвата — это уже не наш inbound.
    fakexray.write(
        gateway.paths, {"inbounds": [{"tag": "tproxy-in", "protocol": "tunnel", "port": 1234}]}
    )
    assert "на порту 12345" in gateway.inbound_problem()
    # Перехват в конфиге выключен — и проверять нечего.
    gateway.cfg.capture.lan = gateway.cfg.capture.local = False
    assert gateway.inbound_problem() == ""


def test_missing_inbound_blocks_when_hold_is_block(gateway):
    """capture.hold = "block" (по умолчанию): Xray запущен с конфигом без inbound'а
    перехвата — мимо VPN не уходит ничего; включится сам, когда конфиг применится."""
    assert gateway.cfg.capture.hold == "block"
    fakexray.write(gateway.paths, {"inbounds": [{"tag": "socks-in"}]})
    assert gateway.enable() == "blocked"
    assert gateway.mode() == "on" and gateway.effective_mode() == "blocked"
    info = gateway.describe()
    assert info["blocked"] is True and "tproxy-in" in info["inbound_missing"]
    kernel = gateway.kernel
    assert "tproxy" not in kernel.table and "chain block_output" in kernel.table
    assert "chain v6_guard" not in kernel.table6  # IPv6 в «ядре» фикстуры нет
    assert kernel.rules == [] and not kernel.route
    assert gateway.loaded() is True  # демон не станет перезагружать правила каждый шаг
    fakexray.write(gateway.paths)
    assert gateway.loaded() is False and gateway.up() == "on"
    assert gateway.describe()["blocked"] is False
    assert "tproxy to 127.0.0.1:12345" in gateway.kernel.table


def test_fail_mode_open_never_blocks(gateway):
    """fail_mode = "open" — человек выбрал связь важнее VPN: hold не действует."""
    gateway.cfg.capture.fail_mode = "open"
    fakexray.write(gateway.paths, {"inbounds": [{"tag": "socks-in"}]})
    assert gateway.enable() == "off" and gateway.describe()["blocked"] is False


def test_blocked_rules_are_reloaded_when_missing(gateway):
    fakexray.write(gateway.paths, {"inbounds": [{"tag": "socks-in"}]})
    gateway.enable()
    del gateway.kernel.tables[("ip", "xgw")]  # чужой flush ruleset
    assert gateway.loaded() is False
    assert gateway.up() == "blocked" and gateway.loaded() is True
    gateway.kernel.tables[("ip", "xgw")] = nft.render(gateway.rules("off"))  # «не тот» режим
    assert gateway.loaded() is False


def test_v6_guard_is_loaded_and_checked_when_ipv6_works(gateway):
    (gateway.proc / "net/ipv6/conf/all").mkdir(parents=True)  # IPv6 в ядре есть
    (gateway.proc / "net/ipv6/conf/all/disable_ipv6").write_text("0\n")
    assert gateway.ipv6_usable()
    assert gateway.enable() == "on"
    assert "chain v6_guard" in gateway.kernel.table6 and gateway.loaded() is True
    gateway.kernel.tables[("ip6", "xgw6")] = nft.render6(
        dataclasses.replace(gateway.rules("on"), v6_guard=False)
    )
    assert gateway.loaded() is False  # IPv6 машины без защиты — правила загружаются заново
    assert gateway.disable() == "off" and "chain v6_guard" in gateway.kernel.table6


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


def test_quic_rule_as_nft_prints_it_counts_as_loaded(gateway):
    """Отчёт 0.1.18 (25.10.2026), дефект 1: nft печатает «reject with icmp type
    port-unreachable» просто как «reject», а проверка искала «port-unreachable» — правила
    считались незагруженными, и демон загружал их заново каждые 30–40 с."""
    assert gateway.enable() == "on"
    printed = gateway.kernel(["nft", "list", "table", "ip", "xgw"])
    assert "udp dport 443" in printed and "port-unreachable" not in printed
    assert gateway.loaded() is True
    gateway.cfg.network.block_quic = False  # ключ выключили — правило лишнее
    assert gateway.loaded() is False
    assert gateway.up() == "on" and gateway.loaded() is True
    assert "udp dport 443" not in gateway.kernel.table


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
        "bypass": ["192.168.50.20"], "ipv6": False, "tun": False, "containers": False,
        "direct4": 0, "docker": False, "fail_mode": "closed", "hold": "block", "loaded": True,
        "tun_problem": "", "inbound_missing": "", "blocked": False,
    }
    # Docker создал мост — о контейнерах говорится и в статусе (если их перехват включён).
    gateway.cfg.capture.containers = True
    assert gateway.describe(check=False)["docker"] is False
    gateway.sys_net.mkdir()
    (gateway.sys_net / "docker0").mkdir()
    assert gateway.describe(check=False)["docker"] is True


def test_russian_addresses_set_is_reloaded_only_when_it_changes(gateway):
    """Ф6: набор direct4 сверяется по отпечатку. Правила загружаются заново, когда разгрузку
    включили или выключили, сменились geoip.dat или direct_ips, — а не на каждом шаге
    (испытание 25.10.2026 с QUIC: неверная сверка — перезагрузка каждые 30–40 с)."""
    from test_geodat import write_geoip

    gateway.paths.xray_dir.mkdir(parents=True, exist_ok=True)
    write_geoip(gateway.paths.xray_dir / "geoip.dat", {"RU": [("5.8.0.0", 13)]})
    gateway.enable()
    assert gateway.loaded() is True
    gateway.cfg.routing.kernel_direct = True
    assert gateway.loaded() is False  # включили — набора ещё нет
    gateway.up()
    assert gateway.loaded() is True and "5.8.0.0/13" in gateway.kernel.table
    assert gateway.describe(check=False)["direct4"] == 1
    gateway.cfg.routing.direct_ips = ["geoip:ru", "203.0.113.0/24"]
    assert gateway.loaded() is False  # набор другой
    gateway.up()
    assert gateway.loaded() is True
    gateway.cfg.routing.kernel_direct = False
    assert gateway.loaded() is False
    gateway.up()
    assert gateway.loaded() is True and "direct4" not in gateway.kernel.table
    # По устройству (пожелание заказчика): набор их адресов сверяется по элементам.
    gateway.cfg.managed.kernel_devices = ["192.168.50.20"]
    assert gateway.loaded() is False
    gateway.up()
    assert gateway.loaded() is True and "direct_lan4" in gateway.kernel.table
    gateway.cfg.managed.kernel_devices = ["192.168.50.21"]
    assert gateway.loaded() is False  # другое устройство
    gateway.up()
    gateway.cfg.routing.kernel_direct = True
    assert gateway.loaded() is False  # и машине: отпечаток другой, хотя набор сетей тот же
    gateway.up()
    assert gateway.loaded() is True


# --- TUN (capture.method = tun) -----------------------------------------------------


@pytest.fixture()
def gateway_tun(gateway):
    gateway.cfg.capture.method = "tun"
    return gateway


def test_tun_is_created_before_the_rules_and_traffic_goes_into_it(gateway_tun):
    gateway = gateway_tun
    assert gateway.enable() == "on"
    kernel = gateway.kernel
    assert kernel.links == {"xgwtun0": "tun"}
    # Машина — в TUN (iif lo, table 101), сеть LAN — локальная доставка TPROXY (table 100).
    assert {(r["table"], r.get("iif")) for r in kernel.rules} == {("101", "lo"), ("100", None)}
    assert kernel.routes(101)[0] == {"dst": "default", "dev": "xgwtun0", "scope": "link"}
    assert kernel.route and "iifname \"lo\"" not in kernel.table
    assert kernel.index("ip", "tuntap", "add") < kernel.index("ip", "rule", "add")
    assert kernel.index("ip", "route", "replace") < kernel.index("nft", "-f")
    assert gateway.loaded() is True
    assert gateway.describe()["tun"] is True


def test_tun_capture_waits_for_the_tun_inbound_in_xray(gateway_tun):
    """Тот же предохранитель для capture.method = "tun": маршрут ведёт трафик машины в
    интерфейс, и если Xray запущен без inbound'а tun-in (настройки ещё не применены),
    читать из интерфейса некому — пакеты пропадают. Перехват не загружается."""
    gateway = gateway_tun
    kernel = gateway.kernel
    fakexray.write(gateway.paths, fakexray.applied_config(tun=None))  # только tproxy-in
    assert gateway.enable() == "blocked"  # capture.hold = "block": мимо VPN ничего
    assert gateway.held == "в применённом конфиге Xray нет inbound tun-in для интерфейса xgwtun0"
    assert kernel.rules == [] and not kernel.routes(101) and "tproxy" not in kernel.table
    assert gateway.loaded() is True and gateway.effective_mode() == "blocked"

    # Xray слушает другой интерфейс (имя в настройках сменили, конфиг ещё прежний).
    fakexray.write(gateway.paths, fakexray.applied_config(tun="oldtun0"))
    assert gateway.up() == "blocked" and "xgwtun0" in gateway.held

    fakexray.write(gateway.paths)  # конфиг с tun-in применён
    assert gateway.loaded() is False
    assert gateway.up() == "on" and gateway.held == ""
    assert kernel.routes(101)[0]["dev"] == "xgwtun0" and gateway.loaded() is True


def test_tun_needs_both_inbounds_when_the_lan_is_captured_too(gateway_tun):
    """Сеть LAN и в режиме TUN идёт через TPROXY: без tproxy-in её трафик пропал бы."""
    gateway = gateway_tun
    fakexray.write(gateway.paths, {"inbounds": [
        {"tag": "tun-in", "protocol": "tun", "settings": {"name": "xgwtun0"}},
    ]})
    assert gateway.enable() == "blocked" and "tproxy-in" in gateway.held


def test_pure_tun_does_not_ask_for_a_tproxy_inbound(gateway_tun):
    """Только эта машина, capture.lan = false: генератор не пишет tproxy-in вовсе, и
    предохранитель не должен его требовать (иначе TUN не включился бы никогда)."""
    gateway = gateway_tun
    gateway.cfg.network.lan_if = ""
    gateway.cfg.capture.lan = False
    fakexray.write(gateway.paths, {"inbounds": [
        {"tag": "tun-in", "protocol": "tun", "settings": {"name": "xgwtun0"}},
    ]})
    assert gateway.inbound_problem() == ""
    assert gateway.enable() == "on" and gateway.loaded() is True
    # Контейнеры идут в тот же TUN по метке: TPROXY им не нужен, tproxy-in — тоже.
    gateway.cfg.capture.containers = True
    assert gateway.inbound_problem() == ""


def test_capture_is_not_loaded_when_the_tun_interface_did_not_appear(gateway_tun, monkeypatch):
    """Команда создания прошла, а интерфейса в системе нет: маршрут в него вёл бы в
    никуда — перехват не загружается, причина остаётся в held."""
    from xgw.net import tun

    gateway = gateway_tun
    monkeypatch.setattr(tun, "present", lambda name, runner: False)
    assert gateway.enable() == "blocked"
    assert gateway.held == "TUN-интерфейса xgwtun0 нет в системе"
    assert gateway.kernel.rules == [] and "tproxy" not in gateway.kernel.table
    # Причина видна и в статусе — той же строкой, что и отсутствие inbound'а.
    assert gateway.describe(check=False)["inbound_missing"] == gateway.held


def test_tun_and_its_route_come_back_after_xray_starts_again(gateway_tun):
    """Xray новее 26.3.27 при остановке выключает интерфейс, и ядро удаляет маршрут через
    него. `xgw net tun` (его вызывает xgw-xray.service после запуска) возвращает и то и
    другое, а правил nftables не трогает."""
    gateway = gateway_tun
    kernel = gateway.kernel
    assert gateway.restore_tun() == ""  # перехват ещё не загружен — делать нечего
    assert gateway.enable() == "on"
    kernel.up.discard("xgwtun0")  # Xray остановился: интерфейс выключен,
    kernel.routes(101)[:] = [r for r in kernel.routes(101) if r.get("dev") != "xgwtun0"]
    assert gateway.loaded() is False  # маршрута в него нет
    tables = dict(kernel.tables)
    assert gateway.restore_tun() == "интерфейс xgwtun0 поднят, маршруты в него на месте"
    assert "xgwtun0" in kernel.up
    assert {route.get("dev") for route in kernel.routes(101)} >= {"xgwtun0"}
    assert kernel.tables == tables and gateway.loaded() is True
    # Перехват снят — маршруты в интерфейс не нужны.
    assert gateway.disable() == "off"
    assert gateway.restore_tun() == ""
    assert "xgwtun0" not in {route.get("dev") for route in kernel.routes(101)}


def test_tun_interface_goes_away_after_switching_back_to_tproxy(gateway_tun):
    """capture.method вернули на tproxy: интерфейс xgwtun0 больше не нужен. Пока Xray ещё
    работает с inbound'ом TUN, интерфейс остаётся (иначе Xray остался бы с оборванным
    интерфейсом); после перезапуска Xray без него — убирается сам."""
    gateway = gateway_tun
    kernel = gateway.kernel
    assert gateway.enable() == "on" and kernel.links == {"xgwtun0": "tun"}
    gateway.cfg.capture.method = "tproxy"
    assert gateway.up() == "on"
    assert kernel.links == {"xgwtun0": "tun"}  # применённый конфиг Xray ещё с tun-in
    assert gateway.tidy() == ""
    fakexray.write(gateway.paths, fakexray.applied_config(tun=None))  # Xray перезапущен
    assert gateway.tidy() == (
        "интерфейс xgwtun0 убран: он больше не нужен ни этой машине, ни контейнерам"
    )
    assert kernel.links == {} and gateway.tidy() == ""
    assert gateway.loaded() is True
    # Чужой интерфейс с тем же именем (не TUN) не трогается.
    kernel.links["xgwtun0"] = "dummy"
    assert gateway.tidy() == "" and kernel.links == {"xgwtun0": "dummy"}


# --- контейнеры Docker ----------------------------------------------------------------


def test_containers_are_marked_and_routed_into_the_tun(gateway):
    """Контейнеры Docker: метка mark_containers в цепочке containers и маршрут по ней в
    таблицу TUN. Пока интерфейса TUN нет (Xray ещё без inbound'а TUN), маршрут ведёт в
    чёрную дыру: контейнеры закрыты, а не выходят мимо VPN."""
    gateway.cfg.capture.containers = True
    fakexray.write(gateway.paths, fakexray.applied_config(tun=None))  # Docker ещё нет
    kernel = gateway.kernel
    assert gateway.enable() == "on"
    assert "meta mark set 0x3" in kernel.table and 'iifname "docker0" goto containers' in (
        kernel.table)
    rule = next(r for r in kernel.rules if r["fwmark"] == "0x3")
    assert rule["table"] == "101" and rule.get("iif") is None
    routes = kernel.routes(101)
    assert [route.get("type") for route in routes] == ["blackhole"]  # интерфейса ещё нет
    assert gateway.loaded() is True
    # Docker появился, Xray перезапущен с inbound'ом TUN — Applier создал интерфейс.
    fakexray.write(gateway.paths)
    tun.ensure("xgwtun0", kernel, gateway.proc)
    assert gateway.loaded() is False  # в интерфейс маршрута ещё нет
    gateway.up()
    assert {route.get("dev") for route in kernel.routes(101)} >= {"xgwtun0"}
    assert gateway.loaded() is True
    # Перехват снят — ни метки, ни маршрута.
    assert gateway.disable() == "off"
    assert "0x3" not in [r["fwmark"] for r in kernel.rules] and not kernel.routes(101)
    assert gateway.loaded() is True
    # Выключили в конфиге — лишний маршрут заметен.
    assert gateway.enable() == "on"
    gateway.cfg.capture.containers = False
    assert gateway.loaded() is False
    gateway.up()
    assert "0x3" not in [r["fwmark"] for r in kernel.rules] and gateway.loaded() is True


def test_containers_tun_is_prepared_by_xgw_after_a_reboot(gateway):
    """После перезагрузки правила загружает xgw-net.service, раньше Xray. Интерфейс TUN
    для контейнеров создаёт XGW — с адресом: иначе его создал бы сам Xray, без адреса, и
    ядро отбрасывало бы ответы Xray (контейнеры без интернета, отчёт 0.1.4, G7). Интерфейс
    без адреса loaded() видит — демон загружает правила заново, и up() его чинит."""
    gateway.cfg.capture.containers = True  # применённый конфиг — с inbound'ом TUN: Docker есть
    kernel = gateway.kernel
    assert gateway.up() == "on"
    assert kernel.links == {"xgwtun0": "tun"} and "xgwtun0" in kernel.up
    assert kernel.addresses["xgwtun0"] == {tun.ADDRESS}
    assert {route.get("dev") for route in kernel.routes(101)} >= {"xgwtun0"}
    assert gateway.loaded() is True and gateway.tun_problem() == ""
    assert gateway.tidy() == ""  # интерфейс нужен контейнерам — остаётся

    # Xray пересоздал интерфейс сам: адреса нет, ответы Xray не дойдут.
    kernel("ip link del dev xgwtun0".split())
    kernel.links["xgwtun0"] = "tun"
    assert gateway.loaded() is False
    assert "нет адреса 169.254.10.1/32" in gateway.tun_problem()
    gateway.up()
    assert kernel.addresses["xgwtun0"] == {tun.ADDRESS} and gateway.loaded() is True

    # Снят один адрес, маршруты и правила на месте: статус называет интерфейс, а не
    # «правила не загружены».
    kernel.addresses.pop("xgwtun0")
    assert gateway.loaded() is False and gateway.loaded(tun=False) is True
    info = gateway.describe()
    assert info["loaded"] is False and info["tun_problem"] == gateway.tun_problem() != ""
    gateway.up()
    assert gateway.describe()["tun_problem"] == "" and gateway.loaded() is True

    # Интерфейс не создаётся (нет /dev/net/tun) — перехват не держится: машина и LAN идут
    # через TPROXY, контейнеры закрыты чёрной дырой.
    kernel("ip link del dev xgwtun0".split())
    kernel.refuse = "tuntap add"
    assert gateway.up() == "on" and gateway.held == ""
    assert [route.get("type") for route in kernel.routes(101)] == ["blackhole"]
    assert gateway.loaded() is True


def test_containers_share_the_tun_table_with_the_machine(gateway_tun):
    """capture.method = "tun": машина и контейнеры — в одной таблице TUN. Возврат машины на
    TPROXY не убирает маршруты таблицы, пока они нужны контейнерам."""
    gateway = gateway_tun
    gateway.cfg.capture.containers = True
    kernel = gateway.kernel
    assert gateway.enable() == "on"
    assert {(r["table"], r.get("iif"), r["fwmark"]) for r in kernel.rules} == {
        ("101", "lo", "0x1"), ("100", None, "0x1"), ("101", None, "0x3")}
    gateway.cfg.capture.method = "tproxy"
    gateway.up()
    assert {(r["table"], r.get("iif"), r["fwmark"]) for r in kernel.rules} == {
        ("100", None, "0x1"), ("101", None, "0x3")}
    types = {route.get("type") for route in kernel.routes(101)}
    assert "blackhole" in types  # контейнерам таблица ещё нужна
    assert gateway.loaded() is True


def test_capture_inbounds_lists_everything_the_rules_depend_on():
    from xgw.net.capture import capture_inbounds

    tproxy = {"tag": "tproxy-in", "listen": "127.0.0.1", "port": 12345, "protocol": "tunnel"}
    tun_in = {"tag": "tun-in", "protocol": "tun", "settings": {"name": "xgwtun0", "mtu": 1500}}
    http = {"tag": "http-in", "protocol": "http", "port": 10809}
    probe = {"tag": "probe-nl-1243", "protocol": "http", "port": 20001}
    config = {"inbounds": [tproxy, tun_in, http, probe]}
    assert len(capture_inbounds(config)) == 2  # http-in и пробы правил сети не касаются
    assert capture_inbounds({}) == [] and capture_inbounds(None) == []
    assert capture_inbounds({"inbounds": "нет"}) == []
    # Любой параметр inbound'а перехвата — уже другой набор.
    renamed = {"inbounds": [tproxy, {**tun_in, "settings": {"name": "vpn7", "mtu": 1500}}]}
    assert capture_inbounds(renamed) != capture_inbounds(config)
    moved = {"inbounds": [{**tproxy, "port": 12346}, tun_in]}
    assert capture_inbounds(moved) != capture_inbounds(config)
    assert capture_inbounds({"inbounds": [tun_in, tproxy]}) == capture_inbounds(config)


def test_tun_machine_only_has_no_tproxy_rule_or_table(gateway_tun):
    gateway = gateway_tun
    gateway.cfg.network.lan_if = ""
    assert gateway.enable() == "on"
    kernel = gateway.kernel
    assert [r["table"] for r in kernel.rules] == ["101"] and not kernel.routes(100)
    assert "chain prerouting" not in kernel.table
    assert gateway.loaded() is True


def test_disable_keeps_the_interface_but_removes_rules_and_routes(gateway_tun):
    gateway = gateway_tun
    gateway.enable()
    assert gateway.disable() == "off"
    kernel = gateway.kernel
    assert kernel.rules == [] and not kernel.routes(101) and not kernel.routes(100)
    assert kernel.links == {"xgwtun0": "tun"}  # его держит открытым Xray
    assert gateway.loaded() is True
    assert gateway.enable() == "on" and gateway.loaded() is True
    assert gateway.open() == "open"  # fail_mode = open: тоже без интерфейса не обходится
    assert kernel.rules == [] and kernel.links
    assert gateway.close() == "on"


def test_down_keeps_the_interface_unless_asked(gateway_tun):
    gateway = gateway_tun
    gateway.enable()
    gateway.down()
    kernel = gateway.kernel
    assert kernel.tables == {} and kernel.rules == [] and not kernel.routes(101)
    assert kernel.links == {"xgwtun0": "tun"}
    gateway.down(remove_tun=True)
    assert kernel.links == {}
    gateway.down(remove_tun=True)  # повторно — не ошибка


def test_loaded_notices_a_lost_interface_route_or_tproxy(gateway_tun):
    gateway = gateway_tun
    gateway.enable()
    kernel = gateway.kernel
    kernel("ip link del dev xgwtun0".split())  # интерфейс пропал
    assert gateway.loaded() is False
    assert gateway.up() == "on" and gateway.loaded() is True  # демон возвращает его
    kernel.rules[:] = [r for r in kernel.rules if r.get("iif") != "lo"]
    assert gateway.loaded() is False
    gateway.up()
    kernel.tables[("ip", "xgw")] += "    chain prerouting {\n    }\n"
    assert gateway.loaded() is True  # prerouting для LAN в TUN-режиме нужен
    gateway.cfg.network.lan_if = ""
    assert gateway.loaded() is False  # без LAN TPROXY остался бы лишним


def test_switching_the_method_moves_the_routes(gateway):
    gateway.enable()
    kernel = gateway.kernel
    assert kernel.links == {} and [r["table"] for r in kernel.rules] == ["100"]
    gateway.cfg.capture.method = "tun"
    assert gateway.loaded() is False  # TPROXY самой машины лишний, TUN ещё нет
    gateway.up()
    assert gateway.loaded() is True and kernel.links
    assert {(r["table"], r.get("iif")) for r in kernel.rules} == {("101", "lo"), ("100", None)}
    gateway.cfg.capture.method = "tproxy"
    assert gateway.loaded() is False
    gateway.up()
    assert gateway.loaded() is True
    assert [r["table"] for r in kernel.rules] == ["100"] and not kernel.routes(101)
    assert kernel.links  # интерфейс не удаляется: Xray мог его уже открыть


def test_tun_carries_ipv6_of_the_machine_without_a_tproxy_chain(gateway_tun):
    (gateway_tun.proc / "net/ipv6/conf/all").mkdir(parents=True)
    (gateway_tun.proc / "net/ipv6/conf/lo").mkdir(parents=True)
    gateway_tun.cfg.network.ipv6 = "proxy"
    assert gateway_tun.enable() == "on"
    kernel = gateway_tun.kernel
    assert {(r["table"], r.get("iif")) for r in kernel.rules6} == {("101", "lo")}
    assert kernel.routes(101, 6)[0]["dev"] == "xgwtun0"
    assert "chain output" in kernel.table6 and "chain prerouting" not in kernel.table6
    assert gateway_tun.loaded() is True and gateway_tun.describe()["ipv6"] is True
    gateway_tun.cfg.network.ipv6 = "off"
    assert gateway_tun.loaded() is False
    gateway_tun.up()
    assert kernel.rules6 == [] and not kernel.routes(101, 6) and gateway_tun.loaded() is True


def test_failure_to_create_the_interface_is_reported(gateway_tun):
    gateway_tun.kernel.refuse = "tuntap add"
    with pytest.raises(CaptureError, match="отказано"):
        gateway_tun.enable()
    assert gateway_tun.kernel.tables == {}  # правила не загружены без интерфейса


# --- IPv6 самой машины (network.ipv6 = proxy) ---------------------------------------


@pytest.fixture()
def gateway6(gateway):
    """Шлюз, у которого IPv6 в ядре есть и проксируется."""
    (gateway.proc / "net/ipv6/conf/all").mkdir(parents=True)
    (gateway.proc / "net/ipv6/conf/lo").mkdir(parents=True)
    for where in ("all", "lo"):
        (gateway.proc / f"net/ipv6/conf/{where}/disable_ipv6").write_text("0\n")
    gateway.cfg.network.ipv6 = "proxy"
    return gateway


def test_ipv6_is_loaded_with_its_own_route_before_the_marking_rules(gateway6):
    assert gateway6.enable() == "on"
    kernel = gateway6.kernel
    assert "tproxy ip6 to [::1]:12345" in kernel.table6 and "chain output" in kernel.table6
    assert kernel.rules6[0]["fwmark"] == "0x1" and kernel.route6
    assert kernel.index("ip", "-6", "rule", "add") < kernel.index("nft", "-f")
    assert gateway6.loaded() is True and gateway6.describe()["ipv6"] is True


def test_ipv6_rules_are_checked_by_loaded(gateway6):
    gateway6.enable()
    kernel = gateway6.kernel
    kernel.rules6.clear()  # пропало правило ip -6 rule
    assert gateway6.loaded() is False
    gateway6.up()
    assert gateway6.loaded() is True
    del kernel.tables[("ip6", "xgw6")]  # чужой flush ruleset
    assert gateway6.loaded() is False
    assert gateway6.up() == "on" and gateway6.loaded() is True


def test_ipv6_rules_are_removed_when_proxying_stops(gateway6):
    gateway6.enable()
    kernel = gateway6.kernel
    gateway6.cfg.network.ipv6 = "off"  # настройку убрали, демон перечитал конфиг
    assert gateway6.loaded() is False  # от ipv6 = proxy остались правила
    gateway6.up()
    assert "tproxy" not in kernel.table6 and kernel.rules6 == [] and not kernel.route6
    assert kernel.rules and gateway6.loaded() is True  # IPv4 перехват на месте
    gateway6.cfg.network.ipv6 = "proxy"
    gateway6.up()
    assert gateway6.disable() == "off"  # xgw disable: IPv6 тоже идёт напрямую
    assert "tproxy" not in kernel.table6 and kernel.rules6 == [] and gateway6.loaded() is True


def test_ipv6_is_proxied_only_while_capturing(gateway6):
    gateway6.enable()
    gateway6.open()  # fail_mode = open: перехват снят временно
    assert gateway6.kernel.rules6 == [] and "tproxy" not in gateway6.kernel.table6
    gateway6.close()
    assert gateway6.kernel.rules6 and "tproxy" in gateway6.kernel.table6


def test_down_removes_the_ipv6_parts_too(gateway6):
    gateway6.enable()
    gateway6.down()
    kernel = gateway6.kernel
    assert kernel.tables == {} and kernel.rules6 == [] and not kernel.route6


def test_ipv6_is_skipped_when_the_kernel_has_none(gateway):
    """ipv6.disable=1: нет ни команд ip -6, ни таблицы ip6 — IPv4 при этом работает."""
    gateway.cfg.network.ipv6 = "proxy"
    gateway.kernel.refuse_ip6 = True
    gateway.kernel.refuse = "ip -6"
    assert not gateway.ipv6_usable()
    assert gateway.enable() == "on" and gateway.loaded() is True
    assert gateway.kernel.commands("ip", "-6") == []
    assert gateway.describe()["ipv6"] is False
    gateway.disable()
    gateway.down()


def test_ipv6_disabled_by_sysctl_counts_as_absent(gateway6):
    """С disable_ipv6=1 на lo нет ::1: Xray не открыл бы на нём TPROXY-inbound."""
    (gateway6.proc / "net/ipv6/conf/lo/disable_ipv6").write_text("1\n")
    assert not gateway6.ipv6_usable() and gateway6.enable() == "on"
    assert gateway6.kernel.table6.count("tproxy") == 0


def test_ipv6_failure_to_load_is_an_error(gateway6):
    gateway6.kernel.refuse_ip6 = True
    with pytest.raises(CaptureError):
        gateway6.enable()
    assert gateway6.mode() == "on"


# --- подсеть LAN и сети других интерфейсов ---------------------------------------------


def _ip_runner(addresses: dict[str, list[str]], gateway: str = "", dev: str = "",
               routes: list[dict] | None = None):
    """Подмена `ip -j -4 addr show` и `ip -j -4 route show`."""
    import ipaddress

    def run(argv, **_kwargs) -> str:
        if list(argv) == ["ip", "-j", "-4", "addr", "show"]:
            return json.dumps([
                {"ifname": name, "addr_info": [
                    {"family": "inet", "local": item.split("/")[0],
                     "prefixlen": int(item.split("/")[1])} for item in items]}
                for name, items in addresses.items()
            ])
        assert list(argv) == ["ip", "-j", "-4", "route", "show"], argv
        found = [{"dst": "default", "gateway": gateway, "dev": dev}] if gateway else []
        found += [
            {"dst": str(ipaddress.IPv4Interface(item).network), "dev": name, "scope": "link"}
            for name, items in addresses.items() for item in items
        ]
        return json.dumps([*found, *(routes or [])])

    return run


def _subnet_cfg(address: str = "192.168.50.1/24", lan_if: str = "enp4s0") -> Config:
    cfg = Config()
    cfg.network.lan_if = lan_if
    cfg.network.lan_address = address
    return cfg


def test_lan_subnet_must_not_overlap_the_wan_network():
    """Так было на живой машине: провайдерский роутер раздаёт 192.168.50.0/24 и сам
    стоит на 192.168.50.1 — ровно то, что XGW по умолчанию назначил бы карте LAN."""
    runner = _ip_runner(
        {"lo": ["127.0.0.1/8"], "enp3s0f0": ["192.168.50.37/24"]},
        gateway="192.168.50.1", dev="enp3s0f0",
    )
    cfg = _subnet_cfg()
    conflicts = lan.subnet_conflicts(cfg, runner)
    assert conflicts == [lan.Conflict("enp3s0f0", "192.168.50.0/24")]  # шлюз — в той же сети
    assert lan.free_lan_address(cfg, runner) == "192.168.60.1/24"
    text = lan.conflict_text(cfg, conflicts, "/etc/xgw/config.toml", "192.168.60.1/24")
    assert text == (
        "Конфликт подсетей: lan_address (192.168.50.1/24) пересекается с интерфейсом "
        "enp3s0f0 (192.168.50.0/24). Измените lan_address и dhcp_range в "
        "/etc/xgw/config.toml (например, на 192.168.60.1/24)."
    )
    assert lan.subnet_conflicts(_subnet_cfg("192.168.60.1/24"), runner) == []


def test_lan_subnet_check_ignores_the_lan_card_itself_and_local_addresses():
    """Повторная установка: на карте LAN уже стоит её собственный адрес — это не
    конфликт. Loopback и link-local (в том числе адрес TUN-интерфейса XGW) не в счёт."""
    runner = _ip_runner({
        "lo": ["127.0.0.1/8"], "enp4s0": ["192.168.50.1/24"], "wan0": ["203.0.113.5/24"],
        "xgwtun0": ["169.254.10.1/32"],
    }, gateway="203.0.113.1", dev="wan0")
    assert lan.subnet_conflicts(_subnet_cfg(), runner) == []
    assert lan.subnet_conflicts(_subnet_cfg(lan_if=""), runner) == []  # LAN не настроен
    assert lan.subnet_conflicts(_subnet_cfg("не адрес"), runner) == []


def test_lan_subnet_conflict_with_other_networks_and_the_default_gateway():
    # Мост Docker, сеть шире нашей: пересечение считается и так.
    docker = _ip_runner({"wan0": ["203.0.113.5/24"], "docker0": ["172.17.0.1/16"]},
                        gateway="203.0.113.1", dev="wan0")
    assert lan.subnet_conflicts(_subnet_cfg("172.17.5.1/24"), docker) == [
        lan.Conflict("docker0", "172.17.0.0/16")]
    # PPPoE: у интерфейса адрес /32, а шлюз провайдера — внутри нашей подсети.
    pppoe = _ip_runner({"ppp0": ["100.70.1.2/32"]}, gateway="192.168.50.1", dev="ppp0")
    found = lan.subnet_conflicts(_subnet_cfg(), pppoe)
    assert found == [lan.Conflict("ppp0", "192.168.50.1/32", gateway=True)]
    assert "со шлюзом по умолчанию на интерфейсе ppp0 (192.168.50.1/32)" in lan.conflict_text(
        _subnet_cfg(), found, "config.toml")
    # Маршрут в сеть через другой интерфейс (VPN на работу) — тоже занятая сеть.
    routed = _ip_runner({"wan0": ["203.0.113.5/24"]}, gateway="203.0.113.1", dev="wan0",
                        routes=[{"dst": "192.168.48.0/21", "dev": "wg0", "gateway": "10.9.0.1"}])
    assert lan.subnet_conflicts(_subnet_cfg(), routed) == [lan.Conflict("wg0", "192.168.48.0/21")]


def test_free_lan_address_skips_occupied_networks():
    runner = _ip_runner({"wan0": ["192.168.50.37/24"], "br0": ["192.168.60.1/24"],
                         "vm0": ["192.168.64.0/20"]})
    assert lan.free_lan_address(_subnet_cfg(), runner) == "192.168.80.1/24"
    everything = _ip_runner({"wan0": ["192.168.0.5/16"]})
    assert lan.free_lan_address(_subnet_cfg(), everything) == ""  # совет без примера


def test_lan_subnet_check_survives_a_missing_ip_tool():
    def broken(argv, **_kwargs):
        raise cmd.CommandError("ip: программа не найдена")

    assert lan.occupied_networks(broken) == []
    assert lan.subnet_conflicts(_subnet_cfg(), broken) == []


def _flush_table(text: str) -> str:
    """Таблица после чужого `nft flush table`: цепочки и их заголовки остались, правил нет."""
    kept, chain = [], False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("chain "):
            chain = True
        elif chain and stripped == "}":
            chain = False
        elif chain and not stripped.startswith("type "):
            continue
        kept.append(line)
    return "\n".join(kept) + "\n"


def test_flushed_table_is_not_taken_for_loaded(gateway):
    """`nft flush table ip xgw` оставляет цепочки пустыми: имена на месте, а перехвата и
    маскарадинга нет. Раньше loaded() смотрел только на имена и считал правила на месте."""
    gateway.enable()
    key = ("ip", "xgw")
    gateway.kernel.tables[key] = _flush_table(gateway.kernel.tables[key])
    assert "chain output {" in gateway.kernel.tables[key]
    assert gateway.loaded() is False
    assert gateway.up() == "on" and gateway.loaded() is True


def test_own_rule_loads_open_the_quiet_window(gateway, monkeypatch):
    """Свои загрузки правил демон по событиям nft monitor не будит: окно открыто, пока идёт
    nft -f, и ещё секунду после (события netlink приходят асинхронно)."""
    from xgw.net import capture as capture_module

    clock = [1000.0]
    monkeypatch.setattr(capture_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(Capture, "ignore_rules_until", 0.0)
    seen: list[bool] = []
    kernel = gateway.kernel
    original = kernel.__call__

    def watching(argv, **kwargs):
        if list(argv[:2]) == ["nft", "-f"]:
            seen.append(Capture.rules_quiet())
        return original(argv, **kwargs)

    gateway.runner = watching
    assert not Capture.rules_quiet()
    gateway.enable()
    assert seen and all(seen)  # во время самой загрузки
    assert Capture.rules_quiet()
    clock[0] += 1.1
    assert not Capture.rules_quiet()


# --- проверка правил по поколению nft (отчёт 0.2.0: 3,5 с на каждом шаге с nft 1.0.9) ---------


def test_loaded_reads_tables_again_only_after_a_rule_change(gateway, monkeypatch):
    """Пока поколение правил ядра то же, loaded() nft не запускает; правка (своя загрузка или
    чужой flush) меняет поколение, и правила перечитываются — пропажа замечается сразу."""
    kernel = gateway.kernel
    gen = [1]
    checked = Capture(gateway.cfg, gateway.paths, runner=kernel, proc_sys=gateway.proc,
                      time_uids=(), generation=lambda: gen[0])
    checked.sys_net = gateway.sys_net
    assert Capture(gateway.cfg, gateway.paths, runner=kernel).lister is kernel  # без кэша

    def listings() -> int:
        return sum(1 for call in kernel.calls if call[:1] == ("nft",) and "list" in call[1:3])

    gateway.enable()
    gen[0] += 1  # nft -f загрузил правила
    assert checked.loaded() is True
    before = listings()
    assert checked.loaded() is True and checked.loaded() is True
    assert listings() == before  # ничего не менялось — nft не запускался
    key = ("ip", "xgw")
    kernel.tables[key] = _flush_table(kernel.tables[key])
    assert checked.loaded() is True  # поколение то же — правка ядру неизвестна (не бывает)
    gen[0] += 1  # чужой flush table меняет поколение
    assert checked.loaded() is False and listings() > before
