"""Установка и удаление на подставной системе: что меняется, что запоминается в
журнале и возвращается ли всё на место. На настоящих systemd и NetworkManager то
же самое проверяет tests/stand/test_machine.py."""

import os
from pathlib import Path

import fakexray
import pytest
from fakesys import FakeSystem

from xgw import config, managed
from xgw.install import UNIT_FILES, Installer, Journal
from xgw.net import nm, sleep, sysctl, ufw
from xgw.net.cmd import CommandError
from xgw.paths import Paths
from xgw.uninstall import Uninstaller
from xgw.xraycore.binary import BinaryError

REPO = Path(__file__).resolve().parents[1]
BEFORE_RULES = """*filter
:ufw-before-input - [0:0]
-A ufw-before-input -i lo -j ACCEPT
-A ufw-before-input -j ufw-not-local
-A ufw-not-local -j DROP
COMMIT
"""


class Box:
    """Подставная машина: система, пути в tmp, конфиг шлюза с LAN."""

    def __init__(self, tmp_path: Path) -> None:
        self.paths = Paths(root=tmp_path)
        self.system = FakeSystem()
        self.proc = tmp_path / "proc" / "sys"
        for key in ("net/ipv4/ip_forward", "net/ipv6/conf/all/forwarding"):
            (self.proc / key).parent.mkdir(parents=True, exist_ok=True)
            (self.proc / key).write_text("0\n", encoding="ascii")
        self.cfg = config.Config()
        self.cfg.network.lan_if = "lan0"
        self.cfg.subscriptions = [config.Subscription(url="https://sub.example.net/abc")]
        self.paths.etc.mkdir(parents=True)
        self.paths.config_file.write_text("# конфиг\n", encoding="utf-8")
        fakexray.write(self.paths)  # конфиг Xray: установка его пишет до включения перехвата
        self.out: list[str] = []
        self.answers: list[bool] = []
        self.questions: list[str] = []
        self.xray_ok = True
        self.singbox_error = ""  # не пусто — загрузка sing-box не удаётся
        self.old_lan = self.system.add_profile("Wired connection 2", "lan0", active=True)
        # Чей браузер открыла установка (open_panel): пусто — открывать негде.
        self.opened_for: str | Exception = ""

    def ask(self, question: str) -> bool:
        self.questions.append(question)
        return self.answers.pop(0)

    def download(self, dest_dir: Path, version: str, **_route) -> tuple[str, Path]:
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / self.paths.xray_bin.name).write_bytes(b"xray")
        return "v26.3.27", dest_dir / self.paths.xray_bin.name

    def download_singbox(self, dest_dir: Path, version: str, **_route) -> tuple[str, Path]:
        if self.singbox_error:
            raise BinaryError(self.singbox_error)
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "sing-box").write_bytes(b"sing-box")
        return "v1.14.3", dest_dir / "sing-box"

    def installer(self) -> Installer:
        return Installer(
            self.cfg, self.paths, runner=self.system, out=self.out.append, ask=self.ask,
            source_root=REPO, proc_sys=self.proc, download=self.download,
            download_singbox=self.download_singbox,
            first_apply=lambda: self.xray_ok, which=self.system.which,
            chown=lambda *args: None, open_panel=self.open_panel,
        )

    def open_panel(self) -> str:
        if isinstance(self.opened_for, Exception):
            raise self.opened_for
        return self.opened_for

    def install(self, **kwargs) -> int:
        return self.installer().run(assume_yes=True, **kwargs)

    def uninstall(self, **kwargs) -> int:
        return Uninstaller(
            self.cfg, self.paths, runner=self.system, out=self.out.append, proc_sys=self.proc
        ).run(**kwargs)

    def text(self) -> str:
        return "\n".join(self.out)

    def forward(self) -> str:
        return (self.proc / "net/ipv4/ip_forward").read_text(encoding="ascii").strip()


@pytest.fixture()
def box(tmp_path):
    return Box(tmp_path)


# --- журнал ---------------------------------------------------------------------


def test_journal_keeps_the_original_state(tmp_path):
    journal = Journal(tmp_path / "backup" / "install.json")
    assert journal.setdefault("sysctl", {"ip_forward": "0"}) == {"ip_forward": "0"}
    assert journal.setdefault("sysctl", {"ip_forward": "1"}) == {"ip_forward": "0"}
    journal.extend("sleep", ["sleep.target"])
    journal.extend("sleep", ["sleep.target", "suspend.target"])
    reloaded = Journal(tmp_path / "backup" / "install.json")
    assert reloaded.get("sleep") == ["sleep.target", "suspend.target"]
    assert "sysctl" in reloaded and "ufw" not in reloaded


# --- план и отказ -----------------------------------------------------------------


def test_plan_is_shown_and_nothing_changes_when_declined(box):
    box.answers = [False]
    assert box.installer().run() == 1
    text = box.text()
    for expected in ("План установки XGW", "пакеты из apt: dnsmasq-base", "пользователь xray",
                     "своя служба xgw-dhcp",
                     "профиль xgw-lan на lan0 — 192.168.50.1/24", "«Wired connection 2»",
                     "IPv6 на WAN (wan0)", "fail-closed", "sudo xgw uninstall",
                     "Отменено, в системе ничего не изменено"):
        assert expected in text, expected
    assert box.questions == ["Продолжить?"]
    assert not box.paths.journal_file.exists() and not box.paths.launcher.exists()
    assert not box.system.commands("nmcli", "connection") and not box.system.kernel.tables
    assert box.system.profile("Wired connection 2")["connection.autoconnect"] == "yes"


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda b: setattr(b.cfg.network, "lan_if", "wan0"), "интерфейс выхода в интернет"),
        (lambda b: (setattr(b.cfg, "subscriptions", []),
                    setattr(b.cfg.panel, "enabled", False)), "нет ни подписки"),
        (lambda b: b.cfg.subscriptions.__setitem__(
            0, config.Subscription(url="https://example.com/sub/TOKEN")), "подписка-пример"),
        (lambda b: b.system.devices["lan0"].update(state="unmanaged"), "unmanaged"),
        (lambda b: b.system.devices.pop("lan0"), "интерфейса lan0"),
        (lambda b: setattr(b.system, "nm_running", False), "NetworkManager не запущен"),
        (lambda b: setattr(b.cfg.network, "dhcp_range", "10.0.0.1,10.0.0.9"), "dhcp_range"),
    ],
)
def test_install_does_not_start_on_a_blocking_problem(box, change, expected):
    change(box)
    assert box.install() == 1
    assert expected in box.text() and "Установка не начата" in box.text()
    assert not box.paths.journal_file.exists()


def test_failed_diag_check_blocks_install_unless_forced(box):
    from xgw.diag import FAIL, Check

    installer = box.installer()
    installer.checks = lambda: [Check("Ядро", FAIL, "ядро не принимает правила перехвата")]
    assert installer.run(assume_yes=True) == 1
    assert "✗ Ядро: ядро не принимает правила перехвата" in box.text()
    assert installer.run(assume_yes=True, force=True) == 0


# --- установка --------------------------------------------------------------------


def test_install_configures_the_system_and_records_what_was_before(box):
    system, paths = box.system, box.paths
    assert box.install() == 0, box.text()
    assert "XGW установлен." in box.text()
    # Программа dnsmasq — из dnsmasq-base: пакет dnsmasq со штатной службой не нужен.
    assert "dnsmasq-base" in system.packages and "dnsmasq" not in system.packages
    assert "xray" in system.users
    # DHCP — своя служба со своим конфигом: в /etc/dnsmasq.d XGW больше ничего не кладёт.
    conf = (paths.etc / "dnsmasq.conf").read_text(encoding="utf-8")
    assert "interface=lan0" in conf and "port=0" in conf and "user=dnsmasq" in conf
    assert f"dhcp-leasefile={paths.var / 'dhcp.leases'}" in conf
    assert not (paths.root / "etc/dnsmasq.d/xgw.conf").exists()
    assert "dnsmasq.service" not in system.units

    lan_profile = system.profile(nm.PROFILE)
    assert lan_profile["device"] == "lan0" and lan_profile["ipv4.method"] == "manual"
    assert lan_profile["ipv4.addresses"] == "192.168.50.1/24"
    assert lan_profile["ipv4.never-default"] == "yes" and lan_profile["ipv6.method"] == "disabled"
    assert system.profile("Wired connection 2")["connection.autoconnect"] == "no"
    assert system.profile("wan")["ipv6.method"] == "disabled"
    assert ("nmcli", "device", "reapply", "wan0") in system.calls

    assert box.forward() == "1"
    assert "net.ipv4.ip_forward = 1" in paths.sysctl_file.read_text(encoding="utf-8")
    for unit in ("xgw-net.service", "xgw.service", "xgw-dhcp.service"):
        assert system.units[unit] == {"active": True, "enabled": True}, unit
    # Xray запускает первая генерация конфига (в тесте подменена).
    assert system.units["xgw-xray.service"]["enabled"]
    for unit in UNIT_FILES:
        assert (paths.systemd_dir / unit).read_text(encoding="utf-8") == (
            REPO / "packaging" / unit).read_text(encoding="utf-8")
    assert "tproxy to 127.0.0.1:12345" in system.kernel.table and system.kernel.rules
    assert (paths.lib_dir / "xgw" / "cli.py").exists()
    assert not list((paths.lib_dir / "xgw").rglob("__pycache__"))
    assert "/opt/xgw/lib" in paths.launcher.read_text(encoding="utf-8")
    assert paths.xray_bin.exists()

    journal = Journal(paths.journal_file)
    assert journal.get("packages") == ["dnsmasq-base"] and journal.get("user_created") is True
    assert "dnsmasq" not in journal.data  # штатную службу dnsmasq XGW не трогает
    assert journal.get("sysctl") == {
        "net.ipv4.ip_forward": "0", "net.ipv6.conf.all.forwarding": "0"}
    assert journal.get("nm_lan")["disabled"] == [{
        "uuid": box.old_lan, "name": "Wired connection 2", "autoconnect": "yes", "active": True}]
    assert journal.get("nm_wan")["ipv6_method"] == "auto"
    assert journal.get("sleep") == list(sleep.TARGETS)
    assert journal.get("capture") == {
        "mark_proxy": 1, "route_table": 100, "tun_route_table": 101, "tun_name": "xgwtun0",
    }
    assert journal.get("finished")
    assert paths.journal_file.stat().st_mode & 0o777 == 0o600
    assert paths.launcher.stat().st_mode & 0o777 == 0o755


def test_ipv6_proxy_leaves_ipv6_on_wan_and_loads_its_rules(box):
    box.cfg.network.ipv6 = "proxy"
    box.answers = [False]
    assert box.installer().run() == 1
    plan = box.text()
    assert "IPv6 самой машины пойдёт через Xray" in plan and "будет отключён" not in plan

    assert box.install() == 0, box.text()
    system = box.system
    assert system.profile("wan")["ipv6.method"] == "auto"  # чужой профиль не тронут
    assert ("nmcli", "device", "reapply", "wan0") not in system.calls
    assert "nm_wan" not in Journal(box.paths.journal_file).data
    # Перехват IPv6 машины загружен: отдельные правило и маршрут и своя таблица.
    assert "tproxy ip6 to [::1]:12345" in system.kernel.table6
    assert system.kernel.rules6 and system.kernel.route6

    assert box.uninstall() == 0, box.text()
    assert system.kernel.tables == {} and system.kernel.rules6 == [] and not system.kernel.route6


def test_ipv6_off_to_proxy_gives_ipv6_back_to_wan_and_back_again(box):
    assert box.install() == 0
    assert box.system.profile("wan")["ipv6.method"] == "disabled"
    box.cfg.network.ipv6 = "proxy"
    assert box.install() == 0, box.text()
    assert box.system.profile("wan")["ipv6.method"] == "auto"  # как было до XGW
    assert "nm_wan" not in Journal(box.paths.journal_file).data
    assert "IPv6 в профиле WAN (wan0) возвращён" in box.text()
    box.cfg.network.ipv6 = "off"
    assert box.install() == 0
    assert box.system.profile("wan")["ipv6.method"] == "disabled"
    assert Journal(box.paths.journal_file).get("nm_wan")["ipv6_method"] == "auto"
    assert box.system.kernel.rules6 == [] and "tproxy" not in box.system.kernel.table6


def _netplan_wan(box: "Box") -> Path:
    """Профиль WAN описан в /etc/netplan (как у серверов и cloud-init): ipv6.method ignore."""
    box.system.profile("wan").update({
        "filename": "/run/NetworkManager/system-connections/netplan-wan0.nmconnection",
        "ipv6.method": "ignore",
    })
    key = box.proc / "net/ipv6/conf/wan0/disable_ipv6"
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_text("0\n", encoding="ascii")
    return key


@pytest.mark.parametrize("lan_if", ["lan0", ""])
def test_netplan_wan_gets_ipv6_off_by_sysctl_and_back(box, lan_if):
    """WIN-03: после nmcli modify NetworkManager 1.46 переписал профиль WAN из netplan с
    `match: {}`, и после удаления XGW и перезагрузки он встал на карту LAN. Теперь такой
    профиль не меняется: IPv6 на карте выключает sysctl, удаление его возвращает."""
    box.cfg.network.lan_if = lan_if
    key = _netplan_wan(box)
    assert box.install() == 0, box.text()
    system = box.system
    assert system.profile("wan")["ipv6.method"] == "ignore"
    assert not [call for call in system.commands("nmcli", "connection", "modify")
                if system.uuid_of("wan") in call]
    assert key.read_text(encoding="ascii").strip() == "1"
    text = box.paths.sysctl_file.read_text(encoding="utf-8")
    assert "net/ipv6/conf/wan0/disable_ipv6 = 1" in text
    assert ("net.ipv4.ip_forward = 1" in text) == bool(lan_if)  # форвардинг — только с LAN
    assert "IPv6 на wan0 отключён" in box.text() and "описан в netplan" in box.text()
    journal = Journal(box.paths.journal_file)
    assert journal.get("nm_wan")["sysctl"] is True
    assert journal.get("sysctl")["net/ipv6/conf/wan0/disable_ipv6"] == "0"

    assert box.install() == 0, box.text()  # повторная установка ничего не портит
    assert key.read_text(encoding="ascii").strip() == "1"
    assert Journal(box.paths.journal_file).get("sysctl")["net/ipv6/conf/wan0/disable_ipv6"] == "0"

    box.out.clear()
    assert box.uninstall() == 0, box.text()
    assert key.read_text(encoding="ascii").strip() == "0"
    assert not box.paths.sysctl_file.exists()
    assert system.profile("wan")["ipv6.method"] == "ignore"
    assert "IPv6 на wan0 — как до установки" in box.text() and "✗" not in box.text()


def test_netplan_wan_ipv6_comes_back_when_ipv6_goes_through_xray(box):
    key = _netplan_wan(box)
    assert box.install() == 0
    box.cfg.network.ipv6 = "proxy"
    assert box.install() == 0, box.text()
    assert key.read_text(encoding="ascii").strip() == "0"
    assert "disable_ipv6" not in box.paths.sysctl_file.read_text(encoding="utf-8")
    assert "nm_wan" not in Journal(box.paths.journal_file).data
    assert "IPv6 на wan0 возвращён" in box.text()


def test_second_install_keeps_the_original_state_in_the_journal(box):
    assert box.install() == 0
    first = Journal(box.paths.journal_file).data
    assert box.install() == 0, box.text()
    second = Journal(box.paths.journal_file).data
    for key in ("sysctl", "nm_lan", "nm_wan", "packages", "user_created", "sleep"):
        assert second[key] == first[key], key
    # Профиль один, а не по одному на каждый запуск.
    assert sum(1 for item in box.system.profiles.values()
               if item["connection.id"] == nm.PROFILE) == 1
    assert len(box.system.commands("useradd")) == 1


def test_machine_only_mode_does_not_touch_lan_things(box):
    box.cfg.network.lan_if = ""
    assert box.install() == 0, box.text()
    assert "dnsmasq-base" not in box.system.packages
    assert not (box.paths.etc / "dnsmasq.conf").exists()
    assert not box.system.units.get("xgw-dhcp.service", {}).get("enabled")
    assert not box.paths.sysctl_file.exists() and box.forward() == "0"
    assert nm.PROFILE not in [item["connection.id"] for item in box.system.profiles.values()]
    assert box.system.profile("Wired connection 2")["connection.autoconnect"] == "yes"
    assert "chain output" in box.system.kernel.table  # перехват трафика самой машины
    assert "Роутер:" not in box.text()
    # Сон не трогается: без роутера уснувшая машина никого без интернета не оставляет.
    assert not box.system.commands("systemctl", "mask")
    assert "sleep" not in Journal(box.paths.journal_file).data
    assert "сон не трогается" in box.text() and "замаскирован" not in box.text()
    assert "gsettings" not in box.text()
    box.out.clear()
    assert box.uninstall() == 0, box.text()
    assert not box.system.commands("systemctl", "unmask") and "размаскирован" not in box.text()


def test_sleep_mask_follows_the_router(box):
    """Маску со сна снимает и повторная установка уже без роутера (или с
    disable_sleep = false), а не только удаление; с роутером она возвращается."""
    assert box.install() == 0
    assert "сон замаскирован" in box.text() and "gsettings" in box.text()
    assert Journal(box.paths.journal_file).get("sleep") == list(sleep.TARGETS)

    box.cfg.network.lan_if = ""
    box.out.clear()
    box.answers = [False]
    assert box.installer().run() == 1
    assert "маска, поставленная прошлой установкой, будет снята" in box.text()
    assert not box.system.commands("systemctl", "unmask")  # план показан, система не тронута

    box.out.clear()
    assert box.install() == 0, box.text()
    assert box.system.calls.count(("systemctl", "unmask", *sleep.TARGETS)) == 1
    assert "сон размаскирован" in box.text() and "gsettings" not in box.text()
    assert "sleep" not in Journal(box.paths.journal_file).data
    assert box.install() == 0  # повторно снимать нечего
    assert box.system.calls.count(("systemctl", "unmask", *sleep.TARGETS)) == 1

    box.cfg.network.lan_if = "lan0"
    assert box.install() == 0
    assert Journal(box.paths.journal_file).get("sleep") == list(sleep.TARGETS)
    box.cfg.network.disable_sleep = False
    assert box.install() == 0
    assert box.system.calls.count(("systemctl", "unmask", *sleep.TARGETS)) == 2
    assert "sleep" not in Journal(box.paths.journal_file).data


def test_capture_stays_off_when_xray_did_not_start(box):
    box.xray_ok = False
    assert box.install() == 0
    assert "Xray не запущен, поэтому перехват не включён" in box.text()
    assert "XGW установлен, но Xray пока не запущен." in box.text()
    # Шлюз остаётся роутером, но ничего не перехватывает: интернет работает напрямую.
    assert "tproxy" not in box.system.kernel.table and "masquerade" in box.system.kernel.table
    assert not box.system.kernel.rules
    assert box.installer().capture.mode() == "off"


def test_reinstall_keeps_capture_enabled_even_if_xray_is_down(box):
    assert box.install() == 0
    box.xray_ok = False
    assert box.install() == 0
    assert "tproxy" in box.system.kernel.table  # выбор пользователя не меняется


def test_ufw_rules_are_added_only_after_confirmation(box):
    box.system.ufw_active = True
    before = ufw.before_rules(box.paths.root)
    before.parent.mkdir(parents=True)
    before.write_text(BEFORE_RULES, encoding="utf-8")

    box.answers = [True, False]
    assert box.installer().run() == 0
    assert "ufw включён. Добавить правила" in box.questions[1]
    assert box.system.ufw_rules == [] and before.read_text(encoding="utf-8") == BEFORE_RULES
    assert "правила ufw не добавлены" in box.text()

    assert box.install() == 0
    assert box.system.ufw_rules == [
        ("allow", "in", "on", "lan0"),
        ("route", "allow", "in", "on", "lan0", "out", "on", "wan0"),
    ]
    lines = before.read_text(encoding="utf-8").splitlines()
    rule = "-A ufw-before-input -i lan0 -m mark --mark 0x1 -j ACCEPT"
    assert lines.index(rule) == lines.index(ufw.ANCHOR) - 1  # до перехода в ufw-not-local
    assert box.system.ufw_reloads == 1
    assert (box.paths.backup_dir / "ufw-before.rules").read_text(encoding="utf-8") == BEFORE_RULES

    assert box.install() == 0  # повтор не плодит строки
    assert before.read_text(encoding="utf-8").count(rule) == 1
    assert box.uninstall() == 0
    assert box.system.ufw_rules == [] and before.read_text(encoding="utf-8") == BEFORE_RULES


def test_network_failure_rolls_everything_back(box):
    box.system.refuse["systemctl daemon-reload"] = "Failed to reload daemon"
    assert box.install() == 1
    text = box.text()
    assert "настройка сети не удалась" in text and "Возвращаю сеть" in text
    assert "Сеть возвращена в состояние до установки." in text
    system = box.system
    assert nm.PROFILE not in [item["connection.id"] for item in system.profiles.values()]
    assert system.profile("Wired connection 2")["connection.autoconnect"] == "yes"
    assert system.profile("Wired connection 2")["device"] == "lan0"
    assert system.profile("wan")["ipv6.method"] == "auto"
    assert box.forward() == "0" and not box.paths.sysctl_file.exists()
    assert not any((box.paths.systemd_dir / unit).exists() for unit in UNIT_FILES)
    assert not system.kernel.tables and not system.kernel.rules
    assert not (box.paths.etc / "dnsmasq.conf").exists()
    # Код и то, что установка не откатывает, остаются — повторный запуск о них помнит.
    assert box.paths.launcher.exists() and "xray" in system.users
    assert set(Journal(box.paths.journal_file).data) == {"packages", "user_created"}


def test_system_failure_stops_before_the_network_is_touched(box):
    box.system.refuse["apt-get install"] = "E: Unable to locate package dnsmasq-base"
    assert box.install() == 1
    assert "установка остановлена" in box.text() and "Сеть не менялась" in box.text()
    assert not box.system.commands("nmcli", "connection", "add")
    assert not box.system.kernel.tables and box.forward() == "0"


# --- удаление ---------------------------------------------------------------------


def test_uninstall_returns_everything(box):
    assert box.install() == 0
    box.out.clear()
    assert box.uninstall() == 0, box.text()
    system, paths = box.system, box.paths
    assert "XGW удалён" in box.text() and "✗" not in box.text()
    assert [item["connection.id"] for item in system.profiles.values()] == [
        "wan", "Wired connection 2"]
    old = system.profile("Wired connection 2")
    assert old["connection.autoconnect"] == "yes" and old["device"] == "lan0"
    assert system.profile("wan")["ipv6.method"] == "auto"
    assert box.forward() == "0" and not paths.sysctl_file.exists()
    assert not system.kernel.tables and not system.kernel.rules and not system.kernel.route
    for unit in UNIT_FILES:
        assert system.units[unit] == {"active": False, "enabled": False}
        assert not (paths.systemd_dir / unit).exists()
    assert not (paths.etc / "dnsmasq.conf").exists()
    assert "dnsmasq.service" not in system.units  # штатную службу XGW не трогал
    assert "xray" not in system.users
    assert ("systemctl", "unmask", *sleep.TARGETS) in system.calls
    assert not paths.opt.exists() and not paths.var.exists() and not paths.launcher.exists()
    assert not paths.xray_config_dir.exists()
    assert paths.config_file.exists() and "Конфиг оставлен" in box.text()
    assert "sudo apt remove dnsmasq-base" in box.text()
    # Демон останавливается раньше, чем снимаются правила: иначе он вернул бы их.
    calls = system.calls
    assert calls.index(("systemctl", "disable", "--now", "xgw.service")) < calls.index(
        ("nft", "-f", "-"), calls.index(("systemctl", "disable", "--now", "xgw.service")))


def test_uninstall_keeps_panel_settings_but_not_their_lock_file(box):
    assert box.install() == 0
    store = managed.path_for(box.paths.config_file)
    assert managed.set_sticky(store, False)
    assert managed.lock_path(store).exists()
    assert box.uninstall() == 0, box.text()
    assert store.exists() and not managed.lock_path(store).exists()


def test_uninstall_purge_removes_the_config_too(box):
    assert box.install() == 0
    assert box.uninstall(purge=True) == 0
    assert not box.paths.etc.exists()


def test_uninstall_keeps_things_that_existed_before(box):
    system = box.system
    system.packages.update({"dnsmasq", "dnsmasq-base"})
    system.missing.discard("dnsmasq")
    system.users.add("xray")
    system.unit("dnsmasq.service").update(active=True, enabled=True)
    assert box.install() == 0
    # Своя служба DHCP не мешает штатной: та как работала, так и работает.
    assert system.units["dnsmasq.service"] == {"active": True, "enabled": True}
    assert box.uninstall() == 0
    assert "xray" in system.users  # пользователь был и до XGW
    assert system.units["dnsmasq.service"] == {"active": True, "enabled": True}
    assert "sudo apt remove" not in box.text()


@pytest.mark.parametrize("before", [
    {"package": True, "enabled": False, "active": False},  # пакет dnsmasq поставил XGW
    {"package": False, "enabled": True, "active": True},  # dnsmasq работал и до XGW
])
def test_install_moves_an_old_setup_off_the_system_dnsmasq(box, before):
    """Установка до 0.1.4 раздавала DHCP штатной службой dnsmasq.service по файлу
    /etc/dnsmasq.d/xgw.conf (живая машина 14.10: пакет ubuntu-fan положил рядом
    bind-interfaces, и после перезагрузки dnsmasq не запустился). Повторная установка
    убирает файл, возвращает штатную службу в состояние до XGW, переносит аренды и
    включает свою службу xgw-dhcp."""
    system, paths = box.system, box.paths
    system.packages.update({"dnsmasq", "dnsmasq-base"})
    system.missing.discard("dnsmasq")
    system.unit("dnsmasq.service").update(active=True, enabled=True)  # её включил пакет
    legacy = paths.root / "etc/dnsmasq.d/xgw.conf"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("port=0\nbind-dynamic\n", encoding="utf-8")
    leases = paths.root / "var/lib/misc/dnsmasq.leases"
    leases.parent.mkdir(parents=True)
    leases.write_text("1760000000 aa:bb:cc:dd:ee:ff 192.168.50.120 phone *\n", "utf-8")
    paths.journal_file.parent.mkdir(parents=True)
    paths.journal_file.write_text(
        __import__("json").dumps({"dnsmasq": before, "packages": ["dnsmasq"]}), "utf-8")

    assert box.install() == 0, box.text()
    assert not legacy.exists()
    if before["active"]:
        assert system.units["dnsmasq.service"] == {"active": True, "enabled": True}
        assert ("systemctl", "restart", "dnsmasq.service") in system.calls
    else:
        assert system.units["dnsmasq.service"] == {"active": False, "enabled": False}
    assert "DHCP теперь раздаёт своя служба xgw-dhcp" in box.text()
    assert system.units["xgw-dhcp.service"] == {"active": True, "enabled": True}
    assert (paths.var / "dhcp.leases").read_text(encoding="utf-8") == leases.read_text("utf-8")
    journal = Journal(paths.journal_file)
    assert "dnsmasq" not in journal.data and journal.get("packages") == ["dnsmasq"]
    # Повтор — штатная служба больше не трогается.
    calls = len(system.commands("systemctl", "restart", "dnsmasq.service"))
    assert box.install() == 0
    assert len(system.commands("systemctl", "restart", "dnsmasq.service")) == calls


def test_uninstall_reports_a_failed_step_and_keeps_the_journal(box):
    assert box.install() == 0
    box.out.clear()
    box.system.nm_running = False
    assert box.uninstall() == 1
    assert "✗ NetworkManager" in box.text() and "Не всё удалось вернуть" in box.text()
    # Остальное возвращено, журнал цел — удаление можно повторить.
    assert box.forward() == "0" and not box.system.kernel.tables
    assert box.paths.journal_file.exists() and box.paths.opt.exists()
    box.system.nm_running = True
    assert box.uninstall() == 0
    assert box.system.profile("Wired connection 2")["connection.autoconnect"] == "yes"


def test_uninstall_without_readable_config_uses_marks_from_the_journal(box):
    box.cfg.capture.mark_proxy = 7
    box.cfg.capture.route_table = 107
    assert box.install() == 0
    assert box.system.kernel.rules[0]["fwmark"] == "0x7"
    code = Uninstaller(
        None, box.paths, runner=box.system, out=box.out.append, proc_sys=box.proc
    ).run()
    assert code == 0 and not box.system.kernel.rules and not box.system.kernel.tables


def test_tun_method_is_announced_installed_and_removed(box):
    box.cfg.capture.method = "tun"
    box.answers = [False]
    assert box.installer().run() == 1
    assert "TUN: постоянный интерфейс xgwtun0" in box.text()
    assert not box.system.kernel.links  # план показан, система не тронута

    assert box.install() == 0, box.text()
    kernel = box.system.kernel
    assert kernel.links == {"xgwtun0": "tun"}
    # Машина — в TUN (iif lo), LAN — TPROXY (таблица 100), контейнеры — в ту же таблицу TUN
    # по своей метке.
    assert {(r["table"], r.get("iif"), r["fwmark"]) for r in kernel.rules} == {
        ("101", "lo", "0x1"), ("100", None, "0x1"), ("101", None, "0x3")}
    assert "tproxy to 127.0.0.1:12345" in kernel.table  # сеть LAN — по-прежнему TPROXY

    assert box.uninstall() == 0, box.text()
    assert "интерфейс TUN убраны" in box.text()
    assert kernel.links == {} and kernel.rules == [] and kernel.tables == {}


def test_uninstall_without_config_finds_the_tun_interface_in_the_journal(box):
    box.cfg.capture.method = "tun"
    box.cfg.capture.tun_name = "vpn7"
    box.cfg.capture.tun_route_table = 177
    fakexray.write(box.paths, fakexray.applied_config(tun="vpn7"))  # Xray слушает vpn7
    assert box.install() == 0
    kernel = box.system.kernel
    assert kernel.links == {"vpn7": "tun"} and "177" in {r["table"] for r in kernel.rules}
    code = Uninstaller(
        None, box.paths, runner=box.system, out=box.out.append, proc_sys=box.proc
    ).run()
    assert code == 0 and kernel.links == {} and not kernel.rules and not kernel.tables


def test_uninstall_on_a_clean_system_is_harmless(box):
    assert box.uninstall() == 0
    assert "XGW удалён" in box.text()
    assert box.system.profile("Wired connection 2")["connection.autoconnect"] == "yes"


# --- части: sysctl, сон, ufw --------------------------------------------------------


def test_sysctl_install_and_restore(box):
    previous = sysctl.install(box.paths, box.proc)
    assert previous == {"net.ipv4.ip_forward": "0", "net.ipv6.conf.all.forwarding": "0"}
    assert box.forward() == "1"
    sysctl.restore(previous, box.paths, box.proc)
    assert box.forward() == "0" and not box.paths.sysctl_file.exists()


def test_sleep_masks_only_what_was_not_masked(box):
    directory = box.paths.systemd_dir
    directory.mkdir(parents=True)
    os.symlink("/dev/null", directory / "sleep.target")
    assert sleep.is_masked("sleep.target", directory)
    assert not sleep.is_masked("suspend.target", directory)
    masked = sleep.mask(directory, box.system)
    assert masked == ["suspend.target", "hibernate.target", "hybrid-sleep.target"]
    assert box.system.calls[-1] == ("systemctl", "mask", *masked)
    box.system.calls.clear()
    sleep.unmask([*masked, "чужое.target"], box.system)
    assert box.system.calls == [("systemctl", "unmask", *masked)]


def test_ufw_before_rules_needs_the_anchor(tmp_path):
    system = FakeSystem()
    path = tmp_path / "before.rules"
    path.write_text("*filter\nCOMMIT\n", encoding="utf-8")
    with pytest.raises(CommandError, match="ufw-not-local"):
        ufw.add_tproxy_rule(path, "lan0", 1, tmp_path / "backup", system)
    assert system.ufw_reloads == 0 and path.read_text(encoding="utf-8") == "*filter\nCOMMIT\n"
    assert not ufw.remove_tproxy_rule(path, system)


def test_ufw_before_rules_follow_interface_and_mark(tmp_path):
    system = FakeSystem()
    path = tmp_path / "before.rules"
    path.write_text(BEFORE_RULES, encoding="utf-8")
    ufw.add_tproxy_rule(path, "lan0", 1, tmp_path / "backup", system)
    assert ufw.has_tproxy_rule(path, "lan0", 1) and not ufw.has_tproxy_rule(path, "lan0", 5)
    ufw.add_tproxy_rule(path, "enp3s0", 5, tmp_path / "backup", system)  # конфиг изменили
    text = path.read_text(encoding="utf-8")
    assert "-i enp3s0 -m mark --mark 0x5" in text and "lan0" not in text
    assert text.count(ufw.MARKER) == 1
    assert ufw.remove_tproxy_rule(path, system)
    assert path.read_text(encoding="utf-8") == BEFORE_RULES


def test_ufw_rules_without_known_wan():
    assert ufw.wanted("lan0", "") == [
        ["allow", "in", "on", "lan0"], ["route", "allow", "in", "on", "lan0"]]


# --- панель: ярлык, токен, установка без подписки ------------------------------------


def test_install_sets_up_the_panel_and_uninstall_removes_the_launcher(box):
    from xgw.watch import panel

    assert box.install() == 0, box.text()
    desktop = box.paths.desktop_file
    entry = desktop.read_text(encoding="utf-8")
    token = panel.read_token(box.paths)
    assert "Exec=xdg-open http://127.0.0.1:8781/\n" in entry and token not in entry
    # Браузер забыл вход — правая кнопка по ярлыку: окно пароля вместо терминала.
    assert "Actions=login;\n" in entry and "[Desktop Action login]\n" in entry
    assert "Name[ru]=Войти заново\n" in entry
    assert f"Exec={box.paths.launcher.as_posix()} panel --login\n" in entry
    assert f"Icon={(box.paths.lib_dir / 'xgw' / 'ui' / 'icon.svg').as_posix()}\n" in entry
    for name in ("index.html", "login.html", "app.js", "app.css", "icon.svg"):
        assert (box.paths.lib_dir / "xgw" / "ui" / name).is_file(), name
    text = box.text()
    assert "панель управления — http://127.0.0.1:8781/" in text  # в плане
    assert f"Панель управления: http://127.0.0.1:8781/?token={token}" in text  # в итоге
    assert "sudo xgw panel" in text and "Вставьте в панели" not in text
    journal = Journal(box.paths.journal_file)
    assert journal.get("launcher") == str(desktop) and journal.get("launcher_dir") is True
    assert panel.token_file(box.paths).stat().st_mode & 0o777 == 0o600
    assert desktop.stat().st_mode & 0o777 == 0o644

    assert box.install() == 0  # повторная установка токен не меняет
    assert panel.read_token(box.paths) == token
    assert Journal(box.paths.journal_file).get("launcher_dir") is True
    assert box.uninstall() == 0, box.text()
    assert "ярлык панели удалён" in box.text()
    assert not desktop.exists() and not desktop.parent.exists()


def test_install_opens_the_panel_in_the_browser_of_whoever_ran_sudo(box):
    from xgw.desktop import DesktopError

    box.opened_for = "alice"
    assert box.install() == 0, box.text()
    text = box.text()
    assert "Панель уже открыта в браузере пользователя alice, вход выполнен" in text
    assert "Откройте эту ссылку в браузере" not in text
    assert "«Войти заново»" in text

    box.out.clear()
    box.opened_for = DesktopError("браузер пользователя alice не открылся: нет xdg-open")
    assert box.install() == 0  # браузер — не повод считать установку неудачной
    text = box.text()
    assert "! панель в браузере не открылась: браузер пользователя alice" in text
    assert "Откройте эту ссылку в браузере" in text


def test_foreign_launchers_survive_uninstall(box):
    other = box.paths.desktop_file.with_name("other-app.desktop")
    other.parent.mkdir(parents=True)
    other.write_text("[Desktop Entry]\n", encoding="utf-8")
    assert box.install() == 0 and box.uninstall() == 0
    assert other.exists() and not box.paths.desktop_file.exists()


def test_install_with_the_panel_switched_off(box):
    box.cfg.panel.enabled = False
    assert box.install() == 0
    assert not box.paths.desktop_file.exists() and "Панель управления" not in box.text()
    assert "launcher" not in Journal(box.paths.journal_file)


def test_install_without_a_subscription_leaves_vpn_off_and_points_to_the_panel(box):
    from xgw.net.capture import Capture

    box.cfg.subscriptions = []
    applied: list[bool] = []
    installer = box.installer()
    installer.first_apply = lambda: applied.append(True) or True
    assert installer.run(assume_yes=True) == 0, box.text()
    text = box.text()
    assert applied == []  # собирать конфиг Xray пока не из чего
    assert "подписок пока нет: VPN не включится" in text  # предупреждено ещё в плане
    assert "XGW установлен. Подписок пока нет — VPN выключен" in text
    assert "Вставьте в панели адрес подписки и нажмите кнопку включения" in text
    assert "Предупреждений" not in text  # это ожидаемое состояние, а не сбой
    capture = Capture(box.cfg, box.paths, runner=box.system, proc_sys=box.proc)
    assert capture.choice() is False and capture.mode() == "off"
    assert "tproxy" not in box.system.kernel.table and "masquerade" in box.system.kernel.table
    assert box.system.units["xgw.service"]["active"]


# --- вопрос о сетевой карте к роутеру -------------------------------------------------


def _ask_lan(system, *answers):
    from xgw.install import choose_lan

    out: list[str] = []
    replies = iter(answers)

    def read(prompt: str) -> str:
        out.append(prompt)
        try:
            return next(replies)
        except StopIteration:
            raise EOFError from None

    return choose_lan(system, read=read, out=out.append), "\n".join(out)


def test_lan_question_offers_wired_cards_except_the_internet_one(box):
    box.system.devices["wlan0"] = {"type": "wifi", "state": "connected"}
    box.system.devices["lan1"] = {"type": "ethernet", "state": "unavailable"}
    chosen, text = _ask_lan(box.system, "9", "мимо", "2")
    assert chosen == "lan1"
    assert "1) lan0 — подключена" in text and "2) lan1 — кабель не подключён" in text
    assert "интернет идёт через wan0" in text and "wlan0" not in text and "wan0 —" not in text
    assert text.count("Введите номер из списка") == 2
    assert _ask_lan(box.system, "lan0")[0] == "lan0"  # можно и именем
    assert _ask_lan(box.system, "")[0] == ""  # Enter — роутера нет
    assert _ask_lan(box.system)[0] == ""  # ввод закрыт


def test_lan_question_is_skipped_when_there_is_no_second_card(box):
    del box.system.devices["lan0"]
    chosen, text = _ask_lan(box.system, "1")
    assert chosen == "" and "только эту машину" in text and "Номер" not in text
    box.system.nm_running = False
    assert _ask_lan(box.system, "1")[0] == ""


def test_chosen_card_is_written_into_a_fresh_config(tmp_path):
    from xgw.install import set_lan_if

    path = tmp_path / "config.toml"
    path.write_text((REPO / "config.example.toml").read_text(encoding="utf-8"), encoding="utf-8")
    assert set_lan_if(path, "enp4s0") is True
    cfg, warnings = config.load(path)
    assert cfg.network.lan_if == "enp4s0" and warnings == []
    assert path.read_text(encoding="utf-8").count("\n# ") > 20  # комментарии примера на месте
    assert path.stat().st_mode & 0o777 == 0o600
    before = path.read_text(encoding="utf-8")
    assert set_lan_if(path, "enp5s0") is False  # строки lan_if = "" уже нет — не трогаем
    assert set_lan_if(path, 'x"; rm') is False
    assert path.read_text(encoding="utf-8") == before


def test_install_is_refused_when_the_lan_subnet_overlaps_the_wan_network(box):
    """Сеть провайдера — 192.168.50.0/24, как и lan_address по умолчанию: профиль
    xgw-lan дал бы второй карте адрес роутера провайдера. Установка не начинается —
    ни с --yes, ни с --force, — и в системе ничего не меняется."""
    box.system.addresses["wan0"] = ["192.168.50.37/24"]
    box.system.gateway = "192.168.50.1"
    profiles = dict(box.system.profiles)
    for force in (False, True):
        box.out.clear()
        assert box.install(force=force) == 1
        text = box.text()
        assert "✗ Конфликт подсетей: lan_address (192.168.50.1/24) пересекается с " \
               "интерфейсом wan0 (192.168.50.0/24)" in text
        assert "(например, на 192.168.60.1/24)" in text
        assert "сначала исправьте подсеть LAN" in text and "План установки" not in text
    assert box.system.profiles == profiles and box.system.units == {}
    assert not box.paths.journal_file.exists() and box.system.kernel.tables == {}

    box.cfg.network.lan_address = "192.168.60.1/24"
    box.cfg.network.dhcp_range = "192.168.60.100,192.168.60.200,12h"
    box.out.clear()
    assert box.install() == 0, box.text()
    assert box.system.profile("xgw-lan")["ipv4.addresses"] == "192.168.60.1/24"


def test_conflict_reported_by_diag_is_not_printed_twice(box):
    from xgw.diag import FAIL, Check

    box.system.addresses["wan0"] = ["192.168.50.37/24"]
    installer = box.installer()
    installer.checks = lambda: [
        Check("Подсеть LAN", FAIL, installer.subnet_conflict()),
        Check("Порты", FAIL, "заняты другой программой"),
    ]
    assert installer.run(assume_yes=True) == 1
    assert box.text().count("Конфликт подсетей") == 1 and "Порты: заняты" in box.text()


def test_lan_profile_is_not_created_if_the_conflict_appears_during_install(box):
    """Пока ставились пакеты, у машины появился адрес из подсети LAN (поднялся другой
    интерфейс): сеть не трогается, сделанное откатывается."""
    installer = box.installer()
    seen = {"count": 0}
    original = installer.subnet_conflict

    def conflict() -> str:
        seen["count"] += 1
        if seen["count"] > 1:
            box.system.addresses["usb0"] = ["192.168.50.9/24"]
        return original()

    installer.subnet_conflict = conflict
    assert installer.run(assume_yes=True) == 1
    assert "настройка сети не удалась: Конфликт подсетей" in box.text()
    assert "xgw-lan" not in [item["connection.id"] for item in box.system.profiles.values()]


def test_install_says_so_when_capture_waits_for_the_xray_inbound(box):
    """Xray отвечает, но в его конфиге нет inbound'а перехвата (собран при выключенном
    перехвате, а настройки с тех пор сменили): установка не рапортует «включён».
    capture.hold = "block" (по умолчанию): до перезапуска Xray мимо VPN ничего не уходит."""
    fakexray.write(box.paths, {"inbounds": [{"tag": "socks-in"}]})
    assert box.install() == 0
    text = box.text()
    assert "правила nftables загружены, трафик заблокирован до перезапуска Xray" in text
    assert "! перехват пока не включён: в применённом конфиге Xray нет inbound tproxy-in" in text
    assert "Интернет закрыт, мимо VPN ничего не уходит" in text
    table = box.system.kernel.table
    assert "tproxy" not in table and "chain block_output" in table and "masquerade" in table
    assert "Предупреждений: 1" in text


# --- второе ядро (sing-box) --------------------------------------------------------------


def test_install_puts_sing_box_next_to_xray_with_its_own_service(box):
    box.answers = [False]
    assert box.installer().run() == 1
    assert "sing-box 1.14.3 с GitHub" in box.text() and "xgw-singbox" in box.text()
    box.out.clear()
    assert box.install() == 0, box.text()
    paths = box.paths
    assert paths.singbox_bin.read_bytes() == b"sing-box"
    assert box.system.units["xgw-singbox.service"]["enabled"]
    assert (paths.systemd_dir / "xgw-singbox.service").read_text(encoding="utf-8") == (
        REPO / "packaging" / "xgw-singbox.service").read_text(encoding="utf-8")
    assert "sing-box v1.14.3" in box.text()
    assert paths.singbox_config_dir.exists()


def test_install_goes_on_when_sing_box_cannot_be_downloaded(box):
    box.singbox_error = "нет сети"
    assert box.install() == 0, box.text()
    assert not box.paths.singbox_bin.exists()
    assert "sing-box не загружен: нет сети" in box.text() and "xgw update-singbox" in box.text()


def test_install_skips_sing_box_when_the_core_is_switched_off(box):
    box.cfg.core.mode = "xray"
    box.answers = [False]
    box.installer().run()
    assert "sing-box 1.14.3 с GitHub" not in box.text()
    box.singbox_error = "не должен вызываться"
    assert box.install() == 0, box.text()
    assert not box.paths.singbox_bin.exists() and "sing-box не загружен" not in box.text()


def test_uninstall_removes_sing_box_files_and_service(box):
    assert box.install() == 0, box.text()
    box.paths.singbox_config_file.write_text("{}", encoding="utf-8")
    assert box.uninstall() == 0, box.text()
    assert not box.paths.singbox_bin.exists() and not box.paths.singbox_config_dir.exists()
    assert not (box.paths.systemd_dir / "xgw-singbox.service").exists()
    assert "xgw-singbox.service" not in box.system.units or not box.system.units[
        "xgw-singbox.service"].get("enabled")
