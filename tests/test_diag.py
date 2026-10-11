"""`xgw diag` на подставной системе: вердикты и советы."""

import json
import sys
from pathlib import Path

import pytest
from fakesys import FakeSystem

from xgw import config, diag
from xgw.diag import FAIL, OK, WARN, Diag
from xgw.net import nm, ufw
from xgw.paths import Paths

LINUX = sys.platform.startswith("linux")


class Box:
    def __init__(self, tmp_path: Path) -> None:
        self.paths = Paths(root=tmp_path)
        self.paths.ensure()
        self.paths.config_file.write_text("# конфиг\n", encoding="utf-8")
        self.paths.config_file.chmod(0o600)
        self.system = FakeSystem()
        self.cfg = config.Config()
        self.cfg.network.lan_if = "lan0"
        self.release = tmp_path / "os-release"
        self.release.write_text(
            'PRETTY_NAME="Ubuntu 26.04.1 LTS"\nID=ubuntu\nVERSION_ID="26.04"\n', encoding="utf-8"
        )
        self.kwargs: dict = {}

    def diag(self, **kwargs) -> Diag:
        options = {
            "runner": self.system, "net": False, "which": lambda name: f"/usr/bin/{name}",
            "is_root": True, "os_release": self.release, "port_free": lambda port: True,
        }
        options.update(self.kwargs)
        options.update(kwargs)
        return Diag(self.cfg, self.paths, **options)

    def installed(self) -> None:
        self.paths.systemd_dir.mkdir(parents=True, exist_ok=True)
        (self.paths.systemd_dir / "xgw.service").write_text("[Service]\n", encoding="utf-8")


@pytest.fixture()
def box(tmp_path, monkeypatch):
    monkeypatch.delenv("XGW_XRAY_BIN", raising=False)
    monkeypatch.setattr(diag.validate.shutil, "which", lambda name: None)
    return Box(tmp_path)


def _by_name(checks) -> dict[str, list]:
    result: dict[str, list] = {}
    for check in checks:
        result.setdefault(check.name, []).append(check)
    return result


def test_render_counts_levels_and_shows_advice():
    text = diag.render([
        diag.Check("Xray", OK, "версия 26.3.27"),
        diag.Check("Сон", WARN, "не замаскирован", "sudo xgw install"),
        diag.Check("Порты", FAIL, "заняты"),
    ])
    assert "OK    Xray: версия 26.3.27" in text
    assert "WARN  Сон: не замаскирован\n      → sudo xgw install" in text
    assert text.endswith("Итог: OK — 1, WARN — 1, FAIL — 0".replace("FAIL — 0", "FAIL — 1"))


@pytest.mark.skipif(not LINUX, reason="остальные проверки идут только в Linux")
def test_clean_machine_before_install_has_no_failures(box):
    checks = box.diag().run()
    assert not [check for check in checks if check.level == FAIL], diag.render(checks)
    by_name = _by_name(checks)
    assert by_name["Система"][0].level == OK and "Ubuntu 26.04.1" in by_name["Система"][0].text
    assert "сеть lan0 и эта машина" in by_name["Конфиг"][0].text
    assert by_name["Xray"][0].level == WARN and "xgw install загрузит" in by_name["Xray"][0].advice
    assert by_name["Ядро"][0].level == OK
    assert by_name["Файрвол"][0].level == OK
    assert "создаст установка" in by_name["LAN"][0].text
    assert by_name["Порты"][0].level == OK
    assert "Xray API" not in by_name and "Службы" not in by_name  # до установки нечего
    # Правила проверяются в отдельном пространстве имён, а не в сети машины.
    assert ("unshare", "-n", "nft", "-f", "-") in box.system.calls
    assert not box.system.kernel.tables


def test_not_linux_is_a_failure(box, monkeypatch):
    monkeypatch.setattr(diag.sys, "platform", "win32")
    checks = box.diag()._system()
    assert checks[0].level == FAIL and "только в Linux" in checks[0].text


def test_other_system_and_no_root_are_warnings(box, monkeypatch):
    monkeypatch.setattr(diag.sys, "platform", "linux")
    box.release.write_text('PRETTY_NAME="Debian 13"\nID=debian\nVERSION_ID="13"\n')
    checks = box.diag(is_root=False)._system()
    assert [check.level for check in checks] == [WARN, WARN]
    assert "проверялся только на Ubuntu 26.04" in checks[0].text
    assert checks[1].advice == "sudo xgw diag"
    assert box.diag(is_root=False)._kernel() == []


def test_config_problems(box):
    missing = box.diag(config_error="конфиг не найден: /etc/xgw/config.toml")._config()[0]
    assert missing.level == FAIL and "xgw install создаст" in missing.advice
    checks = box.diag(config_warnings=["неизвестный ключ xray.foo проигнорирован"])._config()
    assert checks[0].level == WARN and "xray.foo" in checks[0].text
    if LINUX:
        box.paths.config_file.chmod(0o644)
        check = box.diag()._config()[0]
        assert check.level == WARN and "chmod 600" in check.advice


def test_missing_programs(box):
    missing = box.diag(which=lambda name: None if name == "nmcli" else "/usr/bin/x")._programs()
    assert missing[0].level == FAIL and "nmcli" in missing[0].text
    later = box.diag(which=lambda name: None if name == "nft" else "/x")._programs()
    assert later[0].level == WARN and "nftables, dnsmasq" in later[0].text
    # Программа dnsmasq из dnsmasq-base — ещё не служба: нужен пакет dnsmasq.
    unit = box.paths.root / "usr/lib/systemd/system/dnsmasq.service"
    unit.parent.mkdir(parents=True)
    unit.write_text("[Service]\n", encoding="utf-8")
    assert box.diag()._programs()[0].level == OK
    unit.unlink()
    box.cfg.network.lan_if = ""
    solo = box.diag(which=lambda name: None if name == "nmcli" else "/x")
    assert solo._programs()[0].level == OK  # для одной машины они не нужны


def test_xray_version_and_get_probe_support(box, monkeypatch):
    box.paths.xray_dir.mkdir(parents=True)
    box.paths.xray_bin.write_bytes(b"...httpMethod...")
    instance = box.diag()
    monkeypatch.setattr(diag.binary, "installed_version", lambda path: (26, 3, 27))
    assert instance._xray()[0].level == OK
    monkeypatch.setattr(diag.binary, "installed_version", lambda path: (25, 6, 8))
    old = instance._xray()[0]
    assert old.level == FAIL and "ниже 25.7.23" in old.text and "update-xray" in old.advice
    monkeypatch.setattr(diag.binary, "installed_version", lambda path: None)
    assert "не запускается" in instance._xray()[0].text
    monkeypatch.setattr(diag.binary, "installed_version", lambda path: (26, 3, 27))
    box.paths.xray_bin.write_bytes(b"xray without the field")
    assert "httpMethod в бинарнике нет" in instance._xray()[0].text


def test_kernel_refusing_the_rules_is_a_failure(box):
    box.system.refuse["unshare -n nft"] = "Error: Could not process rule: No such file or directory"
    check = box.diag()._kernel()[0]
    assert check.level == FAIL and "Could not process rule" in check.text
    assert "nft_tproxy" in check.advice


def test_kernel_check_without_unshare_checks_syntax_only(box):
    check = box.diag(which=lambda name: None if name == "unshare" else "/x")._kernel()[0]
    assert check.level == WARN and "синтаксис" in check.text
    assert box.system.kernel.commands("nft", "-c", "-f", "-")


def test_ufw_needs_rules_for_lan(box):
    box.system.ufw_active = True
    before = ufw.before_rules(box.paths.root)
    before.parent.mkdir(parents=True)
    before.write_text(f"*filter\n{ufw.ANCHOR}\nCOMMIT\n", encoding="utf-8")
    check = _by_name(box.diag()._firewall())["ufw"][0]
    assert check.level == WARN and "ufw-not-local" in check.text
    assert "sudo ufw allow in on lan0" in check.advice
    assert "-i lan0 -m mark --mark 0x1 -j ACCEPT" in check.advice
    box.installed()
    assert _by_name(box.diag()._firewall())["ufw"][0].level == FAIL  # устройства уже без сети
    box.system.ufw_rules.append(("allow", "in", "on", "lan0"))
    ufw.add_tproxy_rule(before, "lan0", 1, box.paths.backup_dir, box.system)
    assert _by_name(box.diag()._firewall())["ufw"][0].level == OK
    # Без LAN ufw трафику самой машины не мешает.
    box.cfg.network.lan_if = ""
    assert "не мешает" in _by_name(box.diag()._firewall())["ufw"][0].text


def test_docker_forward_drop_and_nftables_service_are_reported(box):
    box.system.nft_chains = [
        {"family": "ip", "table": "filter", "name": "FORWARD", "hook": "forward",
         "policy": "drop"},
        {"family": "ip", "table": "filter", "name": "DOCKER-USER"},
        {"family": "ip", "table": "xgw", "name": "forward", "hook": "forward", "policy": "drop"},
    ]
    box.system.unit("nftables.service")["enabled"] = True
    by_name = _by_name(box.diag()._firewall())
    docker = by_name["Docker"][0]
    assert docker.level == WARN and "DOCKER-USER -i lan0" in docker.advice
    assert "flush ruleset" in by_name["nftables.service"][0].text
    # Своя цепочка forward с политикой drop — не «чужой файрвол».
    box.system.nft_chains = box.system.nft_chains[2:]
    box.system.unit("nftables.service")["enabled"] = False
    assert [check.level for check in box.diag()._firewall()] == [OK]


def test_foreign_input_drop_is_reported(box):
    box.system.nft_chains = [
        {"family": "inet", "table": "firewalld", "name": "filter_INPUT", "hook": "input",
         "policy": "drop"},
    ]
    check = box.diag()._firewall()[0]
    assert check.level == WARN and "inet firewalld" in check.text and "lan0" in check.advice


def test_network_manager_checks(box):
    system = box.system
    system.devices["lan0"]["state"] = "unmanaged"
    check = box.diag()._nm()[0]
    assert check.level == FAIL and "renderer: NetworkManager" in check.advice
    system.devices["lan0"]["state"] = "disconnected"
    del system.devices["lan0"]
    assert "интерфейса lan0 нет; есть: wan0" in box.diag()._nm()[0].text
    system.devices["lan0"] = {"type": "ethernet", "state": "connected"}
    box.cfg.network.lan_if = "wan0"
    assert box.diag()._nm()[0].level == FAIL
    box.cfg.network.lan_if = "lan0"
    system.add_profile("hotspot", "lan0", **{"ipv4.method": "shared"})
    shared = box.diag()._nm()
    assert shared[0].level == WARN and "shared" in shared[0].text
    system.add_profile(nm.PROFILE, "lan0", active=True)
    assert f"профиль {nm.PROFILE} активен" in box.diag()._nm()[-1].text
    system.nm_running = False
    assert box.diag()._nm()[0].level == FAIL
    box.cfg.network.lan_if = ""
    assert box.diag()._nm()[0].level == WARN  # без LAN это лишь предупреждение


def test_ports_busy_by_another_program(box, monkeypatch):
    monkeypatch.setattr(diag.sys, "platform", "linux")
    instance = box.diag(port_free=lambda port: port != 10085)
    instance._xray_up = False
    check = instance._ports()[0]
    assert check.level == FAIL and "api 10085" in check.text and "ss -ltnp" in check.advice
    instance._xray_up = True
    assert instance._ports()[0].level == OK  # заняты самим Xray


def test_can_bind_detects_a_listening_socket():
    import socket

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        assert not diag.can_bind(port)
    assert diag.can_bind(port)


def test_time_sleep_and_ipv6(box, monkeypatch):
    monkeypatch.setattr(diag, "_user_exists", lambda name: name == "_chrony")
    monkeypatch.setattr(diag, "_chrony_uses_nts", lambda: True)
    synced = box.diag()._time()
    assert synced[0].level == OK and "_chrony" in synced[0].text and "NTS" in synced[0].text
    box.system.time_synced = False
    assert box.diag()._time()[0].level == WARN
    monkeypatch.setattr(diag, "_user_exists", lambda name: False)
    assert "не найден пользователь службы времени" in box.diag()._time()[-1].text

    sleepy = box.diag()._sleep()[0]
    assert sleepy.level == WARN and "gsettings" in sleepy.advice
    box.cfg.network.disable_sleep = False
    assert box.diag()._sleep()[0].level == OK

    assert box.diag()._ipv6()[0].level == OK
    box.system.ipv6_global = ["wan0"]
    assert box.diag()._ipv6()[0].level == WARN
    box.installed()
    after = box.diag()._ipv6()[0]
    assert after.level == FAIL and "ipv6.method disabled" in after.advice


def test_tun_needs_the_device_and_a_loose_reverse_path_filter(box, tmp_path):
    box.cfg.capture.method = "tun"
    proc = tmp_path / "proc"
    for where, value in (("all", "2"), ("xgwtun0", "0"), ("default", "2")):
        (proc / "net/ipv4/conf" / where).mkdir(parents=True)
        (proc / "net/ipv4/conf" / where / "rp_filter").write_text(value + "\n")
    device = tmp_path / "tun"
    box.kwargs.update(proc_sys=proc, dev_tun=device)

    missing = box.diag()._tun()
    assert [c.level for c in missing] == [FAIL] and "modprobe tun" in missing[0].advice
    device.write_text("")
    ok = box.diag()._tun()
    assert [c.level for c in ok] == [OK] and "xgwtun0" in ok[0].text

    (proc / "net/ipv4/conf/all/rp_filter").write_text("1\n")
    strict = box.diag()._tun()
    assert [c.level for c in strict] == [OK, WARN]
    assert "rp_filter" in strict[1].text and "rp_filter=2" in strict[1].advice
    (proc / "net/ipv4/conf/all/rp_filter").write_text("2\n")
    (proc / "net/ipv4/conf/xgwtun0/rp_filter").write_text("1\n")  # строгий и на самом интерфейсе
    assert [c.level for c in box.diag()._tun()] == [OK, WARN]

    box.cfg.capture.method = "tproxy"  # не TUN — проверок нет
    assert box.diag()._tun() == []
    box.cfg.capture.method = "tun"
    box.cfg.capture.local = False
    assert box.diag()._tun() == []


def test_proxied_ipv6_is_checked_through_the_capture_state(box, monkeypatch):
    box.cfg.network.ipv6 = "proxy"
    box.system.ipv6_global = ["wan0"]  # при ipv6 = proxy это не повод для тревоги
    monkeypatch.setattr(diag.sysctl, "ipv6_usable", lambda *_a: True)
    assert box.diag()._ipv6()[0].level == OK  # до установки: просто сказано, что будет
    box.cfg.capture.local = False
    assert box.diag()._ipv6()[0].level == WARN
    box.cfg.capture.local = True

    state = {"mode": "on", "loaded": True, "ipv6": True}

    class FakeCapture:
        def __init__(self, *_a, **_k):
            pass

        def describe(self):
            return dict(state)

    monkeypatch.setattr(diag, "Capture", FakeCapture)
    box.installed()
    assert box.diag()._ipv6()[0].level == OK
    state["loaded"] = False
    check = box.diag()._ipv6()[0]
    assert check.level == FAIL and "xgw net up" in check.advice
    state.update(loaded=True, ipv6=False)  # правила для IPv6 не собраны
    assert box.diag()._ipv6()[0].level == FAIL
    state.update(mode="off")
    assert box.diag()._ipv6()[0].level == WARN and "xgw enable" in box.diag()._ipv6()[0].advice
    monkeypatch.setattr(diag.sysctl, "ipv6_usable", lambda *_a: False)
    assert "ядре выключен" in box.diag()._ipv6()[0].text


def test_chrony_nts_detection(tmp_path):
    (tmp_path / "sources.d").mkdir()
    (tmp_path / "chrony.conf").write_text("pool ntp.ubuntu.com iburst\n# server x nts\n")
    assert not diag._chrony_uses_nts(tmp_path)
    (tmp_path / "sources.d" / "ubuntu.sources").write_text("pool 1.ntp.ubuntu.com iburst nts\n")
    assert diag._chrony_uses_nts(tmp_path)
    assert not diag._chrony_uses_nts(tmp_path / "нет")


def test_services_and_capture_after_install(box):
    box.installed()
    down = box.diag()._services()
    assert down[0].level == FAIL and "xgw-net.service" in down[0].text
    for unit in ("xgw-net.service", "xgw-xray.service", "xgw.service", "dnsmasq.service"):
        box.system.unit(unit)["active"] = True
    checks = box.diag()._services()
    assert checks[0].level == OK and "dnsmasq работают" in checks[0].text
    assert checks[1].level == FAIL and checks[1].advice == "sudo xgw net up"  # правил нет
    from xgw.net.capture import Capture

    proc = box.paths.root / "proc" / "sys"  # не настоящий /proc/sys: тест сеть не трогает
    (proc / "net/ipv4").mkdir(parents=True)
    (proc / "net/ipv4/ip_forward").write_text("0\n", encoding="ascii")
    capture = Capture(box.cfg, box.paths, runner=box.system, proc_sys=proc)
    capture.enable()
    assert box.diag()._services()[1].level == OK
    capture.disable()
    off = box.diag()._services()[1]
    assert off.level == WARN and off.advice == "sudo xgw enable"


def test_budget_uses_known_nodes(box):
    assert box.diag()._budget()[0].level == OK  # 5 участников по умолчанию — ~944 МБ
    box.cfg.filters.max_members = 8
    over = box.diag()._budget()[0]
    assert over.level == WARN and "больше лимита" in over.text
    from xgw.store import Store

    store = Store(box.paths.db_file)
    store.replace_nodes([
        {"fingerprint": "a", "tag": "proxy-a", "role": "proxy", "name": "A", "source": "s",
         "address": "a.example.com", "port": 443, "updated": 1},
    ])
    store.set_meta("quota", json.dumps({"main": {"total": 10**9, "upload": 0, "download": 0}}))
    store.close()
    quota = box.diag()._budget()[0]
    assert quota.level == WARN and "10 % остатка квоты" in quota.text


def test_network_probes(box, monkeypatch):
    replies: dict = {}

    def fetch_url(url, **kwargs):
        if isinstance(replies.get("probe"), Exception):
            raise replies["probe"]
        return diag.fetch.FetchResult(200, {}, b"x" * replies.get("size", 65536), url)

    monkeypatch.setattr(diag.fetch, "fetch_url", fetch_url)
    monkeypatch.setattr(diag.engine, "healthy_http_in", lambda cfg: None)
    monkeypatch.setattr(diag.engine, "bypass_mark", lambda cfg, logger: None)
    assert box.diag()._probe()[0].level == OK
    replies["size"] = 100
    short = box.diag()._probe()[0]
    assert short.level == WARN and "100 Б из 65536" in short.text
    replies["probe"] = diag.fetch.FetchError("не удалось получить speed.cloudflare.com: timeout")
    assert "напрямую не скачивается" in box.diag()._probe()[0].text

    answers = {"https://1.1.1.1/dns-query": True, "https://8.8.8.8/dns-query": True,
               "udp://77.88.8.8": True}

    def resolve(name, resolvers, mark=None):
        assert name == "speed.cloudflare.com"
        if not answers[resolvers[0]]:
            raise diag.fetch.ResolveError("таймаут")
        return ["203.0.113.5"]

    monkeypatch.setattr(diag.fetch, "resolve_domain", resolve)
    assert box.diag()._bootstrap()[0].level == OK
    answers["https://8.8.8.8/dns-query"] = False
    some = box.diag()._bootstrap()[0]
    assert some.level == WARN and "отвечают 2 из 3" in some.text
    answers.update(dict.fromkeys(answers, False))
    assert box.diag()._bootstrap()[0].level == FAIL
    box.cfg.probe.url = "http://203.0.113.9/64k"
    assert box.diag()._bootstrap() == []  # имён в конфиге нет — разрешать нечего


def test_a_crashing_check_does_not_stop_the_rest(box, monkeypatch):
    instance = box.diag()
    monkeypatch.setattr(instance, "_sleep", lambda: 1 / 0)
    checks = instance.run()
    broken = [check for check in checks if "проверка не выполнена" in check.text]
    assert len(broken) == 1 and broken[0].name == "Сон" and broken[0].level == WARN
    assert any(check.name == "Трафик проверок" for check in checks)
