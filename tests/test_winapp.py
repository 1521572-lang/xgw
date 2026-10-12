"""XGW в Windows: раскладка каталогов, автозапуск, единственный экземпляр демона,
шаги установщика и проверки `xgw diag`. Реестр подменён; настоящие настройки машины
тесты не читают и не меняют."""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from test_winproxy import FakeRegistry

from xgw import config, winapp
from xgw.diag import FAIL, OK, WARN
from xgw.generator import builder
from xgw.model import ServerNode
from xgw.net import winproxy
from xgw.net.capture import Capture, capture_for
from xgw.net.wincapture import WinCapture
from xgw.paths import InstanceLock, Paths, windows_home
from xgw.watch import status
from xgw.windiag import WinDiag, parse_listeners

WINDOWS = os.name == "nt"


def _cfg() -> config.Config:
    cfg = config.Config()
    cfg.capture.method = "sysproxy"
    cfg.capture.lan = False
    cfg.xray.socks_port, cfg.xray.http_port = 10818, 10819
    return cfg


# --- раскладка каталогов ----------------------------------------------------------


def test_windows_layout_keeps_everything_in_one_folder(tmp_path):
    paths = Paths(root=tmp_path / "XGW", windows=True)
    assert paths.config_file == tmp_path / "XGW" / "config" / "config.toml"
    assert paths.db_file == tmp_path / "XGW" / "data" / "state.db"
    assert paths.status_file == tmp_path / "XGW" / "run" / "status.json"
    assert paths.xray_dir == tmp_path / "XGW" / "app" / "xray"
    assert paths.lib_dir == tmp_path / "XGW" / "app" / "lib"
    assert paths.log_file == tmp_path / "XGW" / "data" / "logs" / "xgw.log"
    posix = Paths(root=tmp_path)  # прежняя раскладка не изменилась
    assert posix.config_file == tmp_path / "etc" / "xgw" / "config.toml"
    assert posix.run == tmp_path / "run" / "xgw" and not posix.windows


def test_installed_program_finds_its_home_by_its_own_place(tmp_path):
    module = tmp_path / "Programs" / "XGW" / "app" / "lib" / "xgw" / "paths.py"
    assert windows_home({"LOCALAPPDATA": "C:/x"}, module) == tmp_path / "Programs" / "XGW"
    source = tmp_path / "checkout" / "src" / "xgw" / "paths.py"  # запуск из исходников
    assert windows_home({"LOCALAPPDATA": str(tmp_path / "Local")}, source) == (
        tmp_path / "Local" / "XGW"
    )


def test_xgw_root_always_wins(tmp_path):
    paths = Paths.from_env({"XGW_ROOT": str(tmp_path), "LOCALAPPDATA": "C:/x"})
    assert paths.root == tmp_path and not paths.windows
    if WINDOWS:
        home = Paths.from_env({"LOCALAPPDATA": str(tmp_path)})
        assert home.windows and home.root == tmp_path / "XGW"


# --- конфиг и сборка --------------------------------------------------------------


def test_template_config_is_valid_and_selects_the_system_proxy(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(winapp.CONFIG_TEMPLATE, encoding="utf-8")
    cfg, warnings = config.load(path)
    if WINDOWS:
        assert cfg.capture.sysproxy and warnings == []
    else:  # на другой системе слово sysproxy не действует — и об этом сказано
        assert not cfg.capture.sysproxy and any("sysproxy" in text for text in warnings)
    assert cfg.capture.lan is False and cfg.capture.fail_mode == "closed"
    assert (cfg.xray.socks_port, cfg.xray.http_port) == (10818, 10819)
    assert cfg.notify.desktop is False and cfg.panel.enabled


def test_sysproxy_config_has_no_transparent_inbounds():
    node = ServerNode(
        fingerprint="ab" * 16, name="NL", source="s", protocol="vless", address="1.2.3.4",
        port=443, country="nl",
        outbound={"protocol": "vless", "settings": {"vnext": [{
            "address": "1.2.3.4", "port": 443,
            "users": [{"id": "11111111-2222-3333-4455-666666666661", "encryption": "none"}],
        }]}},
    )
    selection = builder.Selection(members=[node], spares=[], chains=[], warnings=[])
    built = builder.build(_cfg(), selection, hosts={}).config
    protocols = {item["tag"]: item["protocol"] for item in built["inbounds"]}
    assert "tproxy-in" not in protocols and "tun-in" not in protocols
    assert protocols["http-in"] == "http" and protocols["socks-in"] == "socks"
    ports = {item["tag"]: item["port"] for item in built["inbounds"]}
    assert ports["http-in"] == 10819 and ports["socks-in"] == 10818
    # Правило «порт 53 — в dns-out» относится к перехвату; маршрутизация остаётся общей.
    assert not [rule for rule in built["routing"]["rules"] if rule.get("port") == "53"]
    assert built["routing"]["rules"][-1]["balancerTag"] == builder.BALANCER_TAG
    linux = builder.build(config.Config(), selection, hosts={}).config
    assert "tproxy-in" in [item["tag"] for item in linux["inbounds"]]  # прежнее — как было


def test_capture_for_picks_the_backend(tmp_path):
    paths = Paths(root=tmp_path)
    assert type(capture_for(config.Config(), paths)) is Capture
    win = capture_for(_cfg(), paths, registry=FakeRegistry(), logger=None)
    assert type(win) is WinCapture and win.transparent is False
    assert Capture.transparent is True


def test_root_is_not_needed_for_the_system_proxy(monkeypatch):
    from xgw import actions

    if WINDOWS:
        assert actions.root_problem(_cfg()) is None
        assert "только в Linux" in actions.root_problem(config.Config())
        assert "только в Linux" in actions.root_problem()
    else:
        assert "только в Windows" in actions.root_problem(_cfg())


def test_status_line_for_the_system_proxy():
    base = {"sysproxy": True, "proxy": "127.0.0.1:10819", "loaded": True}
    assert status.render_capture({**base, "mode": "on"}) == (
        "VPN: включён — системный прокси Windows 127.0.0.1:10819"
    )
    assert "ВЫКЛЮЧЕН" in status.render_capture({**base, "mode": "off"})
    assert "ВРЕМЕННО" in status.render_capture({**base, "mode": "open"})
    assert "capture.local" in status.render_capture({**base, "mode": "none"})
    changed = status.render_capture({**base, "mode": "on", "loaded": False})
    assert "ИЗМЕНЁН НЕ XGW" in changed


# --- автозапуск -------------------------------------------------------------------


def test_autostart_is_one_value_in_the_run_key():
    registry = FakeRegistry()
    assert winapp.autostart(registry) == ""
    winapp.set_autostart(registry, [r"C:\Users\u\AppData\Local\XGW\app\python\pythonw.exe",
                                    "-m", "xgw", "run"])
    assert registry.values == {
        "XGW": r"C:\Users\u\AppData\Local\XGW\app\python\pythonw.exe -m xgw run"
    }
    winapp.set_autostart(registry, [r"C:\Program Files\X\pythonw.exe", "-m", "xgw", "run"])
    assert winapp.autostart(registry) == r'"C:\Program Files\X\pythonw.exe" -m xgw run'
    winapp.remove_autostart(registry)
    winapp.remove_autostart(registry)  # повторно — не ошибка
    assert registry.values == {}


def test_daemon_command_prefers_the_windowless_python(tmp_path):
    python = tmp_path / "python.exe"
    python.write_bytes(b"")
    assert winapp.daemon_command(python) == [str(python), "-m", "xgw", "run", "--log-file"]
    (tmp_path / "pythonw.exe").write_bytes(b"")
    assert winapp.daemon_command(python)[0] == str(tmp_path / "pythonw.exe")


def test_real_settings_are_never_touched_under_a_test_root(monkeypatch, tmp_path):
    monkeypatch.setenv("XGW_ROOT", str(tmp_path))
    monkeypatch.delenv("XGW_WINPROXY_KEY", raising=False)
    monkeypatch.delenv("XGW_WINRUN_KEY", raising=False)
    with pytest.raises(winproxy.ProxyError, match="XGW_WINPROXY_KEY"):
        winproxy.default_registry()
    with pytest.raises(winproxy.ProxyError, match="XGW_WINRUN_KEY"):
        winapp.run_registry()
    paths = Paths(root=tmp_path)
    paths.ensure()
    capture = WinCapture(_cfg(), paths)  # создать можно: режим читается без реестра
    assert capture.mode() == "off" and capture.loaded() is None
    from xgw.net.capture import CaptureError

    with pytest.raises(CaptureError, match="XGW_WINPROXY_KEY"):
        capture.enable()
    monkeypatch.setenv("XGW_WINPROXY_KEY", r"Software\XGW-Test\x\Internet Settings")
    registry, notify = winproxy.default_registry()
    assert registry.path == r"Software\XGW-Test\x\Internet Settings" and notify() is None


# --- единственный экземпляр демона -------------------------------------------------


def test_instance_lock_is_exclusive_and_reusable(tmp_path):
    first, second = InstanceLock(tmp_path / "run" / "daemon.lock"), InstanceLock(
        tmp_path / "run" / "daemon.lock")
    assert first.acquire() and first.acquire()  # повторно тем же — можно
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()
    second.release()


def test_guard_reports_a_running_daemon_and_hears_the_stop_request(tmp_path, monkeypatch):
    monkeypatch.setattr(winapp, "STOP_POLL", 0.05)
    paths = Paths(root=tmp_path)
    paths.ensure()
    assert not winapp.daemon_running(paths)
    (paths.run / winapp.STOP_NAME).write_text("stop", encoding="ascii")  # от прежнего запуска
    guard = winapp.DaemonGuard(paths)
    assert guard.acquire()
    try:
        assert winapp.daemon_running(paths) and not winapp.DaemonGuard(paths).acquire()
        assert int((paths.run / winapp.PID_NAME).read_text()) == os.getpid()
        assert not (paths.run / winapp.STOP_NAME).exists()  # старая просьба не действует
        stop = threading.Event()
        guard.watch(stop)
        time.sleep(0.2)
        assert not stop.is_set()
        (paths.run / winapp.STOP_NAME).write_text("stop", encoding="ascii")
        assert stop.wait(3)
    finally:
        guard.release()
    assert not winapp.daemon_running(paths)
    assert not (paths.run / winapp.PID_NAME).exists()
    assert winapp.stop_daemon(paths) == "демон XGW не запущен"


_DAEMON = """
import sys, threading, time
sys.path.insert(0, {src!r})
from pathlib import Path
from xgw import winapp
from xgw.paths import Paths
paths = Paths(root=Path({root!r}))
guard = winapp.DaemonGuard(paths)
assert guard.acquire()
stop = threading.Event()
if {polite!r}:
    guard.watch(stop)
stop.wait(60)
guard.release()
"""


@pytest.mark.parametrize("polite", [True, False])
def test_stop_daemon_asks_first_and_then_terminates(tmp_path, monkeypatch, polite):
    """Демон в другом процессе: вежливый завершается по просьбе, глухой — снимается."""
    monkeypatch.setattr(winapp, "STOP_POLL", 0.05)
    paths = Paths(root=tmp_path)
    paths.ensure()
    src = str(Path(winapp.__file__).resolve().parents[1])
    script = _DAEMON.format(src=src, root=str(tmp_path), polite=polite)
    daemon = subprocess.Popen([sys.executable, "-c", script])
    try:
        deadline = time.monotonic() + 15
        while not winapp.daemon_running(paths) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert winapp.daemon_running(paths)
        assert winapp.start_daemon(paths, command=["не", "запустится"])  # уже работает
        text = winapp.stop_daemon(paths, timeout=5.0 if polite else 1.0)
        assert text == ("демон XGW остановлен" if polite else
                        "демон XGW не отвечал на просьбу и был завершён")
        assert daemon.wait(timeout=10) == (0 if polite else daemon.returncode)
        assert not winapp.daemon_running(paths)
    finally:
        if daemon.poll() is None:
            daemon.kill()
            daemon.wait(timeout=5)


def test_start_daemon_says_when_it_did_not_come_up(tmp_path):
    paths = Paths(root=tmp_path)
    quiet = [sys.executable, "-c", "pass"]  # запускается и сразу выходит, демоном не став
    assert winapp.start_daemon(paths, command=quiet, wait=1.0) is False
    with pytest.raises(winapp.WinAppError, match="не запущен"):
        winapp.start_daemon(paths, command=[str(tmp_path / "нет-такой-программы.exe")])


# --- шаги установщика -------------------------------------------------------------


class Setup:
    def __init__(self, tmp_path, monkeypatch) -> None:
        self.paths = Paths(root=tmp_path / "XGW", windows=True)
        self.run_key = FakeRegistry()
        self.proxy_key = FakeRegistry()
        self.out: list[str] = []
        monkeypatch.setattr(
            winproxy, "default_registry", lambda: (self.proxy_key, lambda: None)
        )
        self.started: list[list[str]] = []
        monkeypatch.setattr(
            winapp, "start_daemon",
            lambda paths, command=None, **kw: self.started.append(command or ["demon"]) or True,
        )
        monkeypatch.setattr(winapp, "stop_daemon", lambda paths, **kw: "демон XGW остановлен")
        monkeypatch.setattr(winapp, "stop_xray", lambda paths: "Xray остановлен")

    def install(self, **kwargs) -> int:
        return winapp.install(
            self.paths, out=self.out.append, registry=self.run_key,
            command=["pythonw.exe", "-m", "xgw", "run"], **kwargs,
        )

    def uninstall(self, **kwargs) -> int:
        return winapp.uninstall(self.paths, out=self.out.append, registry=self.run_key, **kwargs)

    def text(self) -> str:
        return "\n".join(self.out)


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    return Setup(tmp_path, monkeypatch)


@pytest.mark.skipif(not WINDOWS, reason="режим sysproxy в конфиге действует только в Windows")
def test_first_install_creates_config_token_autostart_and_starts(setup):
    assert setup.install() == 0, setup.text()
    paths = setup.paths
    assert paths.config_file.read_text(encoding="utf-8") == winapp.CONFIG_TEMPLATE
    token = paths.panel_token_file.read_text(encoding="ascii").strip()
    assert len(token) >= 24 and f"http://127.0.0.1:8781/?token={token}" in setup.text()
    assert setup.run_key.values == {"XGW": "pythonw.exe -m xgw run"}
    assert setup.started == [["pythonw.exe", "-m", "xgw", "run"]]
    assert "XGW запущен" in setup.text() and "внимание" not in setup.text()
    assert setup.proxy_key.writes == []  # прокси до нажатия кнопки не трогается

    # Повторный запуск (обновление) не затирает настройки и токен.
    paths.config_file.write_text(winapp.CONFIG_TEMPLATE + "\n# моя правка\n", encoding="utf-8")
    setup.out.clear()
    assert setup.install() == 0
    assert "# моя правка" in paths.config_file.read_text(encoding="utf-8")
    assert paths.panel_token_file.read_text(encoding="ascii").strip() == token
    assert "Создан" not in setup.text()


def test_install_options_and_a_broken_config(setup):
    assert setup.install(start=False, with_autostart=False) == 0
    assert setup.started == [] and setup.run_key.values == {}
    assert "XGW запущен" not in setup.text()
    setup.paths.config_file.write_text("[capture\nэто не TOML", encoding="utf-8")
    setup.out.clear()
    assert setup.install() == 2 and "ошибка" in setup.text()
    assert setup.started == []


def test_install_warns_when_the_config_is_not_for_windows(setup):
    setup.paths.ensure()
    setup.paths.config_file.write_text("[capture]\nlocal = true\n", encoding="utf-8")
    assert setup.install() == 0
    assert "capture.method" in setup.text() and "работать не будет" in setup.text()


def test_install_reports_a_daemon_that_did_not_start(setup, monkeypatch):
    monkeypatch.setattr(winapp, "start_daemon", lambda paths, **kw: False)
    assert setup.install() == 1 and "не запустился" in setup.text()


@pytest.mark.skipif(not WINDOWS, reason="режим sysproxy в конфиге действует только в Windows")
def test_uninstall_returns_the_proxy_and_removes_autostart(setup):
    assert setup.install() == 0
    before = winproxy.Settings(True, "proxy.corp:3128", "*.corp", "")
    winproxy.write(setup.proxy_key, before)
    cfg, _warnings = config.load(setup.paths.config_file)
    WinCapture(cfg, setup.paths, registry=setup.proxy_key).enable()
    assert winproxy.read(setup.proxy_key) == winproxy.target(10819)

    setup.out.clear()
    assert setup.uninstall() == 0, setup.text()
    assert winproxy.read(setup.proxy_key) == before
    assert setup.run_key.values == {}
    for expected in ("демон XGW остановлен", "Xray остановлен", "прокси возвращён",
                     "автозапуск убран"):
        assert expected in setup.text(), expected
    assert setup.paths.config_file.exists()  # настройки остаются, пока не попросили стереть

    assert setup.uninstall(purge=True) == 0
    assert not setup.paths.etc.exists() and not setup.paths.var.exists()
    assert "настройки, подписки и журналы удалены" in setup.text()


def test_uninstall_restores_the_proxy_even_without_a_readable_config(setup):
    setup.paths.ensure()
    cfg = _cfg()
    WinCapture(cfg, setup.paths, registry=setup.proxy_key).enable()
    setup.paths.config_file.write_text("это не TOML [", encoding="utf-8")
    assert setup.uninstall() == 0, setup.text()
    assert winproxy.read(setup.proxy_key) == winproxy.Settings()


def test_uninstall_goes_on_after_a_failed_step_and_keeps_the_data(setup, monkeypatch):
    setup.paths.ensure()
    setup.paths.config_file.write_text(winapp.CONFIG_TEMPLATE, encoding="utf-8")

    def stuck(paths, **kwargs):
        raise winapp.WinAppError("демон XGW не остановился")

    monkeypatch.setattr(winapp, "stop_daemon", stuck)
    winapp.set_autostart(setup.run_key, ["pythonw.exe"])
    assert setup.uninstall(purge=True) == 1
    assert "ошибка: демон XGW не остановился" in setup.text()
    assert "Xray остановлен" in setup.text() and setup.run_key.values == {}
    assert setup.paths.config_file.exists()  # после сбоя данные не стираются


# --- журнал -----------------------------------------------------------------------


def test_log_tail_and_export_without_journald(tmp_path, monkeypatch):
    import tarfile

    from xgw import logs

    paths = Paths(root=tmp_path / "XGW", windows=True)
    paths.ensure()
    paths.config_file.write_text(winapp.CONFIG_TEMPLATE, encoding="utf-8")
    assert logs.tail(paths.log_file, 10) == ""  # журнала ещё нет — не ошибка
    paths.log_file.parent.mkdir(parents=True)
    lines = [f"2026-10-12 12:00:{second:02d} INFO xgw.daemon: шаг {second}" for second in range(30)]
    paths.log_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert logs.tail(paths.log_file, 3) == "\n".join(lines[-3:]) + "\n"
    monkeypatch.setattr(logs, "TAIL_BYTES", 200)  # большой файл читается только с конца
    cut = logs.tail(paths.log_file, 100).splitlines()
    assert cut == lines[-len(cut):] and 0 < len(cut) < 30

    (paths.run / "xray.log").write_text("[Warning] тест\n", encoding="utf-8")
    proxy_key = FakeRegistry(ProxyEnable=1, ProxyServer="proxy.corp:3128")
    monkeypatch.setattr(winproxy, "default_registry", lambda: (proxy_key, lambda: None))
    cfg = _cfg()

    def no_commands(argv, **kwargs):
        raise AssertionError(f"в Windows команды Linux не запускаются: {argv}")

    out = tmp_path / "logs.tar.gz"
    names = logs.export(cfg, paths, out, runner=no_commands, diag_text=lambda: "Итог: OK — 1")
    assert {"journal.txt", "xray.log", "network.txt", "config.toml", "versions.txt",
            "diag.txt"} <= set(names)
    with tarfile.open(out) as archive:
        network = archive.extractfile("xgw-logs/network.txt").read().decode("utf-8")
        journal = archive.extractfile("xgw-logs/journal.txt").read().decode("utf-8")
    assert "адрес: proxy.corp:3128" in network and "XGW: режим off" in network
    assert "шаг 29" in journal
    assert proxy_key.writes == []  # экспорт только читает


# --- xgw diag ---------------------------------------------------------------------


NETSTAT = """
Активные подключения

  Имя    Локальный адрес        Внешний адрес          Состояние       PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1368
  TCP    127.0.0.1:10809        0.0.0.0:0              LISTENING       16320
  TCP    127.0.0.1:10819        0.0.0.0:0              LISTENING       4242
  TCP    127.0.0.1:54321        127.0.0.1:10809        ESTABLISHED     7000
  TCP    [::1]:8781             [::]:0                 LISTENING       5151
"""


def test_netstat_listing_is_parsed():
    assert parse_listeners(NETSTAT) == {135: 1368, 10809: 16320, 10819: 4242, 8781: 5151}
    assert parse_listeners("") == {}


class DiagBox:
    def __init__(self, tmp_path) -> None:
        self.paths = Paths(root=tmp_path / "XGW", windows=True)
        self.paths.ensure()
        self.paths.config_file.write_text(winapp.CONFIG_TEMPLATE, encoding="utf-8")
        self.cfg = _cfg()
        self.proxy_key = FakeRegistry()
        self.run_key = FakeRegistry(XGW="pythonw.exe -m xgw run")
        self.busy: set[int] = set()
        self.pids: dict[int, int] = {}
        self.images: dict[int, str] = {}
        self.running = True

    def diag(self, **kwargs) -> WinDiag:
        options = {
            "net": False, "registry": self.proxy_key, "run_registry": self.run_key,
            "port_free": lambda port: port not in self.busy,
            "listening": lambda: self.pids, "image": lambda pid: self.images.get(pid, ""),
            "daemon_running": lambda: self.running,
        }
        options.update(kwargs)
        return WinDiag(self.cfg, self.paths, **options)


@pytest.fixture()
def dbox(tmp_path, monkeypatch):
    monkeypatch.delenv("XGW_XRAY_BIN", raising=False)
    return DiagBox(tmp_path)


def _named(checks) -> dict[str, list]:
    result: dict[str, list] = {}
    for check in checks:
        result.setdefault(check.name, []).append(check)
    return result


def test_diag_names_the_program_that_holds_a_port(dbox):
    dbox.busy = {10819, 10818}
    dbox.pids = {10819: 16320, 10818: 16320}
    dbox.images = {16320: r"C:\Program Files\INCY\incy.exe"}
    check = dbox.diag()._ports()[0]
    assert check.level == FAIL and "socks 10818 — incy.exe" in check.text
    assert "http 10819 — incy.exe" in check.text and "другой VPN-клиент" in check.advice
    dbox.images = {}  # узнать программу не удалось — порт всё равно назван
    assert "http 10819" in dbox.diag()._ports()[0].text
    dbox.busy = set()
    assert dbox.diag()._ports()[0].level == OK


def test_diag_accepts_ports_held_by_our_own_xray(dbox, monkeypatch):
    dbox.busy = {10819, 10818, 10085, 10086}
    dbox.pids = dict.fromkeys(dbox.busy, 900)
    dbox.images = {900: r"C:\Users\u\AppData\Local\XGW\app\xray\xray.exe"}
    instance = dbox.diag()
    monkeypatch.setattr(instance, "xray_up", lambda: True)
    check = instance._ports()[0]
    assert check.level == OK and "работающим Xray" in check.text
    # Панель у работающего демона занята им самим и в проверку не входит.
    dbox.busy.add(8781)
    assert instance._ports()[0].level == OK
    dbox.running = False
    stopped = dbox.diag()
    monkeypatch.setattr(stopped, "xray_up", lambda: True)
    assert "панель 8781" in stopped._ports()[0].text


def test_diag_before_the_first_server_and_when_xray_is_down(dbox, monkeypatch):
    """Сразу после установки серверов нет и Xray не запускался — это не сбой. А когда
    он должен работать и молчит, совет — про журналы в файлах, а не про systemd."""
    from xgw import diag

    def refused(port):
        raise OSError("подключение отвергнуто")

    monkeypatch.setattr(diag.metrics, "fetch_metrics", refused)
    instance = dbox.diag()
    instance.xray_bin = dbox.paths.xray_bin
    check = instance._xray_api()[0]
    assert check.level == WARN and "ещё не запускался" in check.text
    assert "панели управления" in check.advice and "systemctl" not in check.advice
    assert "ещё не запускался" in status.render_xray({"ok": False, "configured": False})

    dbox.paths.xray_config_file.parent.mkdir(parents=True, exist_ok=True)
    dbox.paths.xray_config_file.write_text("{}", encoding="utf-8")
    check = dbox.diag()._xray_api()
    assert check == []  # без Xray в папке программы проверять нечего
    again = dbox.diag()
    again.xray_bin = dbox.paths.xray_bin
    check = again._xray_api()[0]
    assert check.level == FAIL and "метрики не отвечают" in check.text
    assert "xgw logs" in check.advice and "xray.log" in check.advice
    assert "systemctl" not in check.advice and "journalctl" not in check.advice
    assert "НЕ ОТВЕЧАЕТ" in status.render_xray({"ok": False, "configured": True})
    assert "НЕ ОТВЕЧАЕТ" in status.render_xray({"ok": False})  # статус прежнего вида


def test_diag_daemon_autostart_and_proxy(dbox):
    by_name = _named(dbox.diag()._daemon())
    assert by_name["Демон"][0].level == OK and by_name["Автозапуск"][0].level == OK
    proxy = dbox.diag()._proxy()[0]
    assert proxy.level == OK and "VPN выключен; прокси в Windows не задан" in proxy.text

    dbox.running = False
    dbox.run_key.values.clear()
    by_name = _named(dbox.diag()._daemon())
    assert by_name["Демон"][0].level == WARN and "xgw start" in by_name["Демон"][0].advice
    assert by_name["Автозапуск"][0].level == WARN

    capture = WinCapture(dbox.cfg, dbox.paths, registry=dbox.proxy_key)
    capture.enable()
    assert "VPN включён: прокси Windows — 127.0.0.1:10819" in dbox.diag()._proxy()[0].text
    dbox.proxy_key.values["ProxyEnable"] = 0
    changed = dbox.diag()._proxy()[0]
    assert changed.level == WARN and "xgw enable" in changed.advice
    capture.disable()
    winproxy.write(dbox.proxy_key, winproxy.Settings(True, "proxy.corp:3128", "", ""))
    assert "сейчас стоит прокси proxy.corp:3128" in dbox.diag()._proxy()[0].text
    winproxy.write(dbox.proxy_key, winproxy.Settings(False, "", "", "http://wpad/p.pac"))
    assert "PAC-файл http://wpad/p.pac" in dbox.diag()._proxy()[0].text


def test_diag_config_and_missing_xray(dbox, monkeypatch):
    from xgw import diag as diag_module

    monkeypatch.setattr(diag_module.validate.shutil, "which", lambda name: None)
    assert dbox.diag()._config()[0].level == OK
    dbox.cfg.capture.method = "tproxy"
    wrong = dbox.diag()._config()[0]
    assert wrong.level == FAIL and 'method = "sysproxy"' in wrong.advice
    assert dbox.diag()._proxy() == []
    broken = dbox.diag(config_error="config.toml: битый TOML")._config()[0]
    assert broken.level == FAIL and "установщик XGW" in broken.advice
    missing = dbox.diag()._xray()[0]
    assert missing.level == FAIL and "xgw update-xray" in missing.advice


@pytest.mark.skipif(not WINDOWS, reason="проверка системы — для Windows")
def test_diag_run_has_no_linux_checks_and_no_sudo(dbox, monkeypatch):
    from xgw import diag as diag_module

    monkeypatch.setattr(diag_module.validate.shutil, "which", lambda name: None)
    checks = dbox.diag().run()
    names = {check.name for check in checks}
    assert {"Система", "Конфиг", "Xray", "Порты", "Демон", "Автозапуск",
            "Системный прокси", "Трафик проверок"} <= names
    assert not names & {"Ядро", "Файрвол", "NetworkManager", "Сон", "IPv6", "Службы", "Время"}
    assert "Windows" in _named(checks)["Система"][0].text
    assert not [check for check in checks if "sudo" in check.advice]
