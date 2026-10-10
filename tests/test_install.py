"""Установка и удаление на подставной системе: что меняется, что запоминается в
журнале и возвращается ли всё на место. На настоящих systemd и NetworkManager то
же самое проверяет tests/stand/test_machine.py."""

import os
from pathlib import Path

import pytest
from fakesys import FakeSystem

from xgw import config
from xgw.install import UNITS, Installer, Journal
from xgw.net import nm, sleep, sysctl, ufw
from xgw.net.cmd import CommandError
from xgw.paths import Paths
from xgw.uninstall import Uninstaller

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
        self.out: list[str] = []
        self.answers: list[bool] = []
        self.questions: list[str] = []
        self.xray_ok = True
        self.old_lan = self.system.add_profile("Wired connection 2", "lan0", active=True)

    def ask(self, question: str) -> bool:
        self.questions.append(question)
        return self.answers.pop(0)

    def download(self, dest_dir: Path, version: str, **_route) -> tuple[str, Path]:
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / self.paths.xray_bin.name).write_bytes(b"xray")
        return "v26.3.27", dest_dir / self.paths.xray_bin.name

    def installer(self) -> Installer:
        return Installer(
            self.cfg, self.paths, runner=self.system, out=self.out.append, ask=self.ask,
            source_root=REPO, proc_sys=self.proc, download=self.download,
            first_apply=lambda: self.xray_ok, which=lambda name: f"/usr/bin/{name}",
            chown=lambda *args: None,
        )

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
    for expected in ("План установки XGW", "пакеты из apt: dnsmasq", "пользователь xray",
                     "профиль xgw-lan на lan0 — 192.168.50.1/24", "«Wired connection 2»",
                     "IPv6 в профиле WAN (wan0)", "fail-closed", "sudo xgw uninstall",
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
    conf_before_apt: list[bool] = []
    original = system._apt_get

    def apt(args, command, check):
        conf_before_apt.append((paths.root / "etc/dnsmasq.d/xgw.conf").exists())
        return original(args, command, check)

    system._apt_get = apt
    assert box.install() == 0, box.text()
    assert "XGW установлен." in box.text()
    # Конфиг dnsmasq (port=0) лежит до установки пакета: иначе его служба заняла бы порт 53.
    assert conf_before_apt == [True]
    assert "dnsmasq" in system.packages and "xray" in system.users

    lan_profile = system.profile(nm.PROFILE)
    assert lan_profile["device"] == "lan0" and lan_profile["ipv4.method"] == "manual"
    assert lan_profile["ipv4.addresses"] == "192.168.50.1/24"
    assert lan_profile["ipv4.never-default"] == "yes" and lan_profile["ipv6.method"] == "disabled"
    assert system.profile("Wired connection 2")["connection.autoconnect"] == "no"
    assert system.profile("wan")["ipv6.method"] == "disabled"
    assert ("nmcli", "device", "reapply", "wan0") in system.calls

    assert box.forward() == "1"
    assert "net.ipv4.ip_forward = 1" in paths.sysctl_file.read_text(encoding="utf-8")
    for unit in ("xgw-net.service", "xgw.service", "dnsmasq.service"):
        assert system.units[unit] == {"active": True, "enabled": True}, unit
    # Xray запускает первая генерация конфига (в тесте подменена).
    assert system.units["xgw-xray.service"]["enabled"]
    for unit in UNITS:
        assert (paths.systemd_dir / unit).read_text(encoding="utf-8") == (
            REPO / "packaging" / unit).read_text(encoding="utf-8")
    assert "tproxy to 127.0.0.1:12345" in system.kernel.table and system.kernel.rules
    assert (paths.lib_dir / "xgw" / "cli.py").exists()
    assert not list((paths.lib_dir / "xgw").rglob("__pycache__"))
    assert "/opt/xgw/lib" in paths.launcher.read_text(encoding="utf-8")
    assert paths.xray_bin.exists()

    journal = Journal(paths.journal_file)
    assert journal.get("packages") == ["dnsmasq"] and journal.get("user_created") is True
    assert journal.get("dnsmasq") == {"package": True, "enabled": False, "active": False}
    assert journal.get("sysctl") == {
        "net.ipv4.ip_forward": "0", "net.ipv6.conf.all.forwarding": "0"}
    assert journal.get("nm_lan")["disabled"] == [{
        "uuid": box.old_lan, "name": "Wired connection 2", "autoconnect": "yes", "active": True}]
    assert journal.get("nm_wan")["ipv6_method"] == "auto"
    assert journal.get("sleep") == list(sleep.TARGETS)
    assert journal.get("capture") == {"mark_proxy": 1, "route_table": 100}
    assert journal.get("finished")
    if os.name != "nt":
        assert paths.journal_file.stat().st_mode & 0o777 == 0o600
        assert paths.launcher.stat().st_mode & 0o777 == 0o755


def test_second_install_keeps_the_original_state_in_the_journal(box):
    assert box.install() == 0
    first = Journal(box.paths.journal_file).data
    assert box.install() == 0, box.text()
    second = Journal(box.paths.journal_file).data
    for key in ("sysctl", "nm_lan", "nm_wan", "dnsmasq", "packages", "user_created", "sleep"):
        assert second[key] == first[key], key
    # Профиль один, а не по одному на каждый запуск.
    assert sum(1 for item in box.system.profiles.values()
               if item["connection.id"] == nm.PROFILE) == 1
    assert len(box.system.commands("useradd")) == 1


def test_machine_only_mode_does_not_touch_lan_things(box):
    box.cfg.network.lan_if = ""
    assert box.install() == 0, box.text()
    assert "dnsmasq" not in box.system.packages
    assert not box.paths.sysctl_file.exists() and box.forward() == "0"
    assert nm.PROFILE not in [item["connection.id"] for item in box.system.profiles.values()]
    assert box.system.profile("Wired connection 2")["connection.autoconnect"] == "yes"
    assert "chain output" in box.system.kernel.table  # перехват трафика самой машины
    assert "Роутер:" not in box.text()


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
    box.system.refuse["systemctl restart dnsmasq.service"] = "нет"  # лишь предупреждение
    box.system.refuse["systemctl daemon-reload"] = "Failed to reload daemon"
    assert box.install() == 1
    text = box.text()
    assert "настройка сети не удалась" in text and "Возвращаю сеть" in text
    assert "dnsmasq не запустился" in text
    assert "Сеть возвращена в состояние до установки." in text
    system = box.system
    assert nm.PROFILE not in [item["connection.id"] for item in system.profiles.values()]
    assert system.profile("Wired connection 2")["connection.autoconnect"] == "yes"
    assert system.profile("Wired connection 2")["device"] == "lan0"
    assert system.profile("wan")["ipv6.method"] == "auto"
    assert box.forward() == "0" and not box.paths.sysctl_file.exists()
    assert not any((box.paths.systemd_dir / unit).exists() for unit in UNITS)
    assert not system.kernel.tables and not system.kernel.rules
    # Код и то, что установка не откатывает, остаются — повторный запуск о них помнит.
    assert box.paths.launcher.exists() and "xray" in system.users
    assert set(Journal(box.paths.journal_file).data) == {"packages", "user_created", "dnsmasq"}


def test_system_failure_stops_before_the_network_is_touched(box):
    box.system.refuse["apt-get install"] = "E: Unable to locate package dnsmasq"
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
    for unit in UNITS:
        assert system.units[unit] == {"active": False, "enabled": False}
        assert not (paths.systemd_dir / unit).exists()
    # Пакет dnsmasq остаётся, но служба выключена: с конфигом по умолчанию она
    # спорила бы с systemd-resolved за порт 53.
    assert system.units["dnsmasq.service"] == {"active": False, "enabled": False}
    assert not (paths.root / "etc/dnsmasq.d/xgw.conf").exists()
    assert "xray" not in system.users
    assert ("systemctl", "unmask", *sleep.TARGETS) in system.calls
    assert not paths.opt.exists() and not paths.var.exists() and not paths.launcher.exists()
    assert not paths.xray_config_dir.exists()
    assert paths.config_file.exists() and "Конфиг оставлен" in box.text()
    assert "sudo apt remove dnsmasq" in box.text()
    # Демон останавливается раньше, чем снимаются правила: иначе он вернул бы их.
    calls = system.calls
    assert calls.index(("systemctl", "disable", "--now", "xgw.service")) < calls.index(
        ("nft", "-f", "-"), calls.index(("systemctl", "disable", "--now", "xgw.service")))


def test_uninstall_purge_removes_the_config_too(box):
    assert box.install() == 0
    assert box.uninstall(purge=True) == 0
    assert not box.paths.etc.exists()


def test_uninstall_keeps_things_that_existed_before(box):
    system = box.system
    system.packages.add("dnsmasq")
    system.users.add("xray")
    system.unit("dnsmasq.service").update(active=True, enabled=True)
    assert box.install() == 0
    assert box.uninstall() == 0
    assert "xray" in system.users  # пользователь был и до XGW
    assert system.units["dnsmasq.service"] == {"active": True, "enabled": True}
    assert "sudo apt remove" not in box.text()


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


@pytest.mark.skipif(os.name == "nt", reason="символические ссылки в Windows требуют прав")
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
    assert f"Icon={(box.paths.lib_dir / 'xgw' / 'ui' / 'icon.svg').as_posix()}\n" in entry
    for name in ("index.html", "login.html", "app.js", "app.css", "icon.svg"):
        assert (box.paths.lib_dir / "xgw" / "ui" / name).is_file(), name
    text = box.text()
    assert "панель управления — http://127.0.0.1:8781/" in text  # в плане
    assert f"Панель управления: http://127.0.0.1:8781/?token={token}" in text  # в итоге
    assert "sudo xgw panel" in text and "Вставьте в панели" not in text
    journal = Journal(box.paths.journal_file)
    assert journal.get("launcher") == str(desktop) and journal.get("launcher_dir") is True
    if os.name != "nt":
        assert panel.token_file(box.paths).stat().st_mode & 0o777 == 0o600
        assert desktop.stat().st_mode & 0o777 == 0o644

    assert box.install() == 0  # повторная установка токен не меняет
    assert panel.read_token(box.paths) == token
    assert Journal(box.paths.journal_file).get("launcher_dir") is True
    assert box.uninstall() == 0, box.text()
    assert "ярлык панели удалён" in box.text()
    assert not desktop.exists() and not desktop.parent.exists()


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
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
    before = path.read_text(encoding="utf-8")
    assert set_lan_if(path, "enp5s0") is False  # строки lan_if = "" уже нет — не трогаем
    assert set_lan_if(path, 'x"; rm') is False
    assert path.read_text(encoding="utf-8") == before
