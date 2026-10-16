"""Рабочий стол Ubuntu: кто запустил команду от root, браузер в его сеансе, окно пароля."""

import subprocess
import types

import pytest

from xgw import desktop
from xgw.net.cmd import CommandError

ALICE = desktop.User("alice", 1000)
GNOME_ENV = "HOME=/home/alice\nWAYLAND_DISPLAY=wayland-0\nXDG_SESSION_TYPE=wayland\n"


class Runner:
    def __init__(self, replies=None, fail=None):
        self.calls: list[list[str]] = []
        self.replies = replies or {}
        self.fail = fail

    def __call__(self, argv, *, input=None, timeout=15.0, check=True):
        self.calls.append(list(argv))
        if self.fail and self.fail in " ".join(argv):
            raise CommandError(f"{' '.join(argv)}: Failed to connect to user bus")
        return next((text for key, text in self.replies.items() if key in argv), "")


def test_invoking_user_comes_from_pkexec_first_then_sudo(monkeypatch):
    names = {1000: "alice", 1001: "bob"}

    def getpwuid(uid):
        if uid not in names:
            raise KeyError(uid)
        return types.SimpleNamespace(pw_name=names[uid], pw_uid=uid)

    monkeypatch.setattr(desktop.pwd, "getpwuid", getpwuid)
    assert desktop.invoking_user({"PKEXEC_UID": "1000", "SUDO_UID": "1001"}) == ALICE
    assert desktop.invoking_user({"SUDO_UID": "1001"}) == desktop.User("bob", 1001)
    assert desktop.invoking_user({"SUDO_UID": "4242"}) is None  # такого пользователя нет


def test_invoking_user_is_unknown_for_root_and_plain_runs():
    assert desktop.invoking_user({}) is None
    assert desktop.invoking_user({"SUDO_UID": "0", "PKEXEC_UID": "x"}) is None


def test_graphical_session_is_seen_in_the_user_manager():
    runner = Runner({"show-environment": GNOME_ENV})
    assert desktop.graphical(ALICE, runner)
    assert runner.calls == [["systemctl", "--user", "--machine=alice@", "show-environment"]]
    # Пользователь вошёл только по SSH: переменных графического сеанса нет.
    assert not desktop.graphical(ALICE, Runner({"show-environment": "HOME=/home/alice\n"}))
    assert not desktop.graphical(ALICE, Runner(fail="show-environment"))


def test_browser_opens_in_the_users_session_and_the_code_stays_out_of_errors():
    runner = Runner()
    url = "http://127.0.0.1:8781/?login=SECRETCODE"
    desktop.open_url(ALICE, url, runner)
    (argv,) = runner.calls
    assert argv[:5] == ["systemd-run", "--user", "--machine=alice@", "--quiet", "--collect"]
    assert argv[-3:] == ["--", "xdg-open", url]
    # Описание службы (оно попадает в журнал) — без адреса.
    assert all("SECRETCODE" not in part for part in argv[:-1])
    with pytest.raises(desktop.DesktopError) as caught:
        desktop.open_url(ALICE, url, Runner(fail="xdg-open"))
    assert "SECRETCODE" not in str(caught.value) and "alice" in str(caught.value)


def test_notify_goes_to_the_users_session_from_root(monkeypatch):
    runner = Runner()
    monkeypatch.setattr(desktop, "is_root", lambda: True)
    desktop.notify(ALICE, "панель не отвечает", runner)
    assert runner.calls[0][:3] == ["systemd-run", "--user", "--machine=alice@"]
    assert runner.calls[0][-2:] == ["XGW", "панель не отвечает"]
    desktop.notify(ALICE, "ещё раз", Runner(fail="notify-send"))  # сбой не мешает


def test_admin_password_window_is_pkexec(monkeypatch):
    seen: list[list[str]] = []

    def run(argv, timeout):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, desktop.PKEXEC_DISMISSED)

    monkeypatch.setattr(desktop.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert desktop.as_admin(["/usr/local/bin/xgw", "panel", "--login"], run=run) == 126
    assert seen == [["/usr/bin/pkexec", "/usr/local/bin/xgw", "panel", "--login"]]
    monkeypatch.setattr(desktop.shutil, "which", lambda name: None)
    with pytest.raises(desktop.DesktopError, match="sudo xgw panel"):
        desktop.as_admin(["/usr/local/bin/xgw"], run=run)
