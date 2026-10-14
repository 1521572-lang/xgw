"""Сам установщик XGW для Windows: тихая установка в отдельный каталог, работа
установленной программы на встроенном Python, удаление с сохранением настроек,
повторная установка поверх них и удаление начисто.

Запускается только по явной просьбе — нужны собранный установщик и настоящий Xray:

    python packaging/windows/build.py
    set XGW_WINDOWS_SETUP=build\\windows\\XGW-Setup-0.1.3.exe
    set XGW_XRAY_BIN=tools\\xray\\xray.exe
    pytest tests/stand/test_windows_installer.py

Что тест меняет на машине и возвращает обратно: ярлык «XGW» в меню «Пуск» и запись
об установленной программе (HKCU\\…\\Uninstall\\XGW). Системный прокси и автозапуск
этой машины не трогаются: установленная программа получает отдельные ключи реестра
(XGW_WINPROXY_KEY, XGW_WINRUN_KEY). Если XGW на этой машине уже установлен
по-настоящему, тест не запускается.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from panel_client import login, request
from ports import free_port
from stand import Stand, wait_for

from xgw.net import winproxy
from xgw.paths import InstanceLock
from xgw.watch import checks

SETUP = os.environ.get("XGW_WINDOWS_SETUP", "")
XRAY_BIN = os.environ.get("XGW_XRAY_BIN", "")
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\XGW"
REAL_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
PREVIOUS = winproxy.Settings(True, "proxy.corp.example:3128", "*.corp.example;<local>", "")

pytestmark = [
    pytest.mark.skipif(os.name != "nt", reason="установщик — только для Windows"),
    pytest.mark.skipif(
        not SETUP or not Path(SETUP).is_file(),
        reason="нет XGW_WINDOWS_SETUP — проверка установщика запускается по просьбе",
    ),
    pytest.mark.skipif(
        not XRAY_BIN or not Path(XRAY_BIN).exists(), reason="нет XGW_XRAY_BIN — стенд пропущен"
    ),
]


def _value(path: str, name: str):
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except FileNotFoundError:
        return None


class Installed:
    def __init__(self, tmp_path: Path) -> None:
        self.home = tmp_path / "XGW"
        base = rf"Software\XGW-Test\{uuid.uuid4().hex}"
        self.base = base
        self.proxy = winproxy.WinRegistry(base + r"\Internet Settings")
        self.run = winproxy.WinRegistry(base + r"\Run")
        # Окружение пользователя после установки — без переменных разработки, но с
        # отдельными ключами реестра вместо настроек машины.
        self.env = {key: value for key, value in os.environ.items()
                    if not key.upper().startswith(("XGW_", "PYTHON"))}
        self.env.update(XGW_WINPROXY_KEY=self.proxy.path, XGW_WINRUN_KEY=self.run.path)
        self.stand = Stand(tmp_path / "stand", Path(XRAY_BIN), mode="loopback")
        self.stand.config_file = self.home / "config" / "config.toml"
        self.panel_port = free_port()
        self.shortcut = Path(os.environ["APPDATA"]) / (
            r"Microsoft\Windows\Start Menu\Programs\XGW.lnk")

    def setup(self, *switches: str) -> subprocess.CompletedProcess:
        # /D= — последним и без кавычек: так его разбирает NSIS.
        return subprocess.run(
            [SETUP, "/S", *switches, f"/D={self.home}"], env=self.env, timeout=600,
            capture_output=True,
        )

    def remove(self, *switches: str) -> subprocess.CompletedProcess:
        # «_?=» — выполнить удаление в этом же процессе и дождаться его конца.
        return subprocess.run(
            [str(self.home / "uninstall.exe"), "/S", *switches, f"_?={self.home}"],
            env=self.env, timeout=600, capture_output=True,
        )

    def xgw(self, *args: str, timeout: float = 120) -> subprocess.CompletedProcess:
        python = self.home / "app" / "python" / "python.exe"
        return subprocess.run(
            [str(python), "-m", "xgw", *args], env=self.env, timeout=timeout,
            capture_output=True, text=True, encoding="cp1251", errors="replace",
        )

    def state(self) -> str:
        result = self.xgw("status", "--json")
        if result.returncode != 0:
            return ""
        try:
            return json.loads(result.stdout).get("state") or ""
        except ValueError:
            return ""

    def daemon_running(self) -> bool:
        probe = InstanceLock(self.home / "run" / "daemon.lock")
        if probe.acquire():
            probe.release()
            return False
        return True

    def through_proxy(self) -> bool:
        port = self.stand.ports["http"]
        url = self.stand.origin_url("/64k")
        return checks.http_get_via_proxy("127.0.0.1", port, url, silence=5.0, max_total=20.0).ok

    def log(self) -> str:
        try:
            return (self.home / "data" / "logs" / "xgw.log").read_text("utf-8", "replace")
        except OSError:
            return ""

    def cleanup(self) -> None:
        import winreg

        if (self.home / "uninstall.exe").exists():
            self.remove("/PURGE")
        for key in (self.proxy.path, self.run.path, self.base, r"Software\XGW-Test"):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
            except FileNotFoundError:
                pass
            except PermissionError:
                break
        shutil.rmtree(self.home, ignore_errors=True)


@pytest.fixture()
def installed(tmp_path):
    if _value(UNINSTALL_KEY, "DisplayName") is not None:
        pytest.skip("XGW уже установлен на этой машине — проверка установщика его бы задела")
    instance = Installed(tmp_path)
    try:
        instance.stand.start()
        yield instance
    finally:
        try:
            instance.cleanup()
        finally:
            instance.stand.stop()


def test_installer_installs_runs_and_removes(installed):
    stand, home = installed.stand, installed.home
    target = winproxy.target(stand.ports["http"])
    run_before = _value(REAL_RUN_KEY, "XGW")

    # Настройки остались от прошлой установки (здесь — конфиг стенда): ставимся поверх.
    home.joinpath("config").mkdir(parents=True)
    stand.set_subscription(stand.names)
    stand.write_config(
        sysproxy=True, panel=True,
        extra=f"\n[panel]\nenabled = true\nport = {installed.panel_port}\n",
    )
    kept = stand.config_file.read_text(encoding="utf-8")
    winproxy.write(installed.proxy, PREVIOUS)

    # --- установка -----------------------------------------------------------------
    result = installed.setup()
    assert result.returncode == 0, result
    for name in ("app/python/python.exe", "app/python/pythonw.exe", "app/lib/xgw/cli.py",
                 "app/lib/xgw/ui/index.html", "app/xray/xray.exe", "app/xray/geoip.dat",
                 "uninstall.exe", "xgw.cmd", "xgw.ico", "licenses/Python-LICENSE.txt"):
        assert (home / name).is_file(), name
    assert stand.config_file.read_text(encoding="utf-8") == kept  # настройки не затёрты
    assert installed.shortcut.is_file()
    assert _value(UNINSTALL_KEY, "DisplayName") == "XGW — VPN-клиент на Xray"
    assert _value(UNINSTALL_KEY, "InstallLocation") == str(home)
    assert _value(UNINSTALL_KEY, "DisplayVersion")
    pythonw = str(home / "app" / "python" / "pythonw.exe")
    assert installed.run.get("XGW") == subprocess.list2cmdline(
        [pythonw, "-m", "xgw", "run", "--log-file"])
    assert _value(REAL_RUN_KEY, "XGW") == run_before  # автозапуск машины не тронут

    # --- установленная программа работает на встроенном Python ---------------------
    assert installed.daemon_running()
    assert wait_for(lambda: installed.state() == "HEALTHY", 120, step=2), (
        installed.xgw("status").stdout + installed.log()[-2500:]
    )
    assert "xgw 0." in installed.xgw("--version").stdout
    launcher = subprocess.run(
        ["cmd", "/c", str(home / "xgw.cmd"), "--version"], env=installed.env,
        capture_output=True, text=True, timeout=60,
    )
    assert launcher.returncode == 0 and "xgw 0." in launcher.stdout
    assert installed.through_proxy()
    assert winproxy.read(installed.proxy) == PREVIOUS  # до включения прокси не тронут

    # Панель: страницы лежат в установленном каталоге, вход по токену.
    token = (home / "data" / "panel-token").read_text(encoding="ascii").strip()
    cookie = login(installed.panel_port, token)
    response, page = request(installed.panel_port, "GET", "/", cookie=cookie)
    assert response.status == 200 and 'id="power"' in page
    response, script = request(installed.panel_port, "GET", "/app.js")
    assert response.status == 200 and "sysproxy" in script
    response, text = request(installed.panel_port, "GET", "/api/state", cookie=cookie)
    state = json.loads(text)
    assert state["capture"]["sysproxy"] is True and state["power"]["can_on"] is True

    on = installed.xgw("enable")
    assert on.returncode == 0, on.stdout + on.stderr
    assert winproxy.read(installed.proxy) == target
    diag = installed.xgw("diag", "--no-net")
    assert "FAIL — 0" in diag.stdout, diag.stdout
    assert "VPN включён: прокси Windows" in diag.stdout
    assert str(home / "config" / "config.toml") in diag.stdout
    logs = installed.xgw("logs", "-n", "50")
    assert logs.returncode == 0 and "демон XGW запущен" in logs.stdout

    # --- обновление поверх работающей программы -------------------------------------
    # Установщик сам останавливает демон и Xray, меняет файлы и запускает всё снова;
    # VPN остаётся включённым, настройки и подписки — на месте.
    first_pid = int((home / "run" / "xray.pid").read_text(encoding="ascii").strip())
    (home / "app" / "lib" / "xgw" / "удалённый_модуль.py").write_text("x = 1\n", "utf-8")
    upgraded = installed.setup()
    assert upgraded.returncode == 0, upgraded
    assert not (home / "app" / "lib" / "xgw" / "удалённый_модуль.py").exists()
    assert installed.daemon_running()
    assert wait_for(installed.through_proxy, 20, step=0.5), installed.log()[-2000:]
    assert int((home / "run" / "xray.pid").read_text(encoding="ascii").strip()) != first_pid
    assert winproxy.read(installed.proxy) == target
    assert stand.config_file.read_text(encoding="utf-8") == kept
    assert wait_for(lambda: installed.state() == "HEALTHY", 90, step=2)

    # --- удаление с сохранением настроек -------------------------------------------
    xray_pid = int((home / "run" / "xray.pid").read_text(encoding="ascii").strip())
    removed = installed.remove()
    assert removed.returncode == 0, removed
    assert not (home / "app").exists() and not (home / "run").exists()
    assert not installed.shortcut.exists()
    assert _value(UNINSTALL_KEY, "DisplayName") is None
    assert installed.run.get("XGW") is None
    assert winproxy.read(installed.proxy) == PREVIOUS  # прокси возвращён
    assert not installed.daemon_running()
    from xgw.xraycore.service import runs_program

    assert not runs_program(xray_pid, "xray.exe")
    assert stand.config_file.read_text(encoding="utf-8") == kept
    assert (home / "data" / "state.db").is_file()  # подписки и состояние остались

    # --- повторная установка поверх настроек и удаление начисто ---------------------
    again = installed.setup("/NOSTART")
    assert again.returncode == 0, again
    assert (home / "app" / "lib" / "xgw" / "cli.py").is_file()
    assert not installed.daemon_running() and installed.run.get("XGW") is None
    assert stand.config_file.read_text(encoding="utf-8") == kept

    purged = installed.remove("/PURGE")
    assert purged.returncode == 0, purged
    left = sorted(item.name for item in home.iterdir()) if home.exists() else []
    assert left in ([], ["uninstall.exe"]), left  # сам uninstall.exe при «_?=» остаётся
    assert _value(UNINSTALL_KEY, "DisplayName") is None and not installed.shortcut.exists()
    assert _value(REAL_RUN_KEY, "XGW") == run_before


def test_first_install_creates_settings_for_windows(installed):
    """Первая установка в пустой каталог: настройки создаёт сама программа — сразу
    для системного прокси и на портах, которые не делит с другими VPN-клиентами."""
    home = installed.home
    result = installed.setup("/NOSTART")
    assert result.returncode == 0, result
    text = (home / "config" / "config.toml").read_text(encoding="utf-8")
    assert 'method = "sysproxy"' in text and "http_port = 10819" in text
    assert (home / "data" / "panel-token").read_text(encoding="ascii").strip()
    assert not installed.daemon_running() and installed.run.get("XGW") is None
    # Команда для терминала не смотрит на переменные PYTHON* пользователя.
    assert " -I -m xgw " in (home / "xgw.cmd").read_text(encoding="ascii")
    status = installed.xgw("status")
    assert status.returncode != 0 and "рабочего конфига нет" in status.stderr
    diag = installed.xgw("diag", "--no-net")
    assert "режим — системный прокси" in diag.stdout and "systemctl" not in diag.stdout
    assert "XGW не запущен" in diag.stdout  # с /NOSTART демон не запускался

    # Испорченный файл настроек: установка поверх него сообщает о сбое кодом, но
    # файлы ставит, и удалить программу после этого можно.
    (home / "config" / "config.toml").write_text("[capture\n", encoding="utf-8")
    broken = installed.setup()
    assert broken.returncode == 2, broken
    assert not installed.daemon_running()
    purged = installed.remove("/PURGE")
    assert purged.returncode == 0, purged
    left = sorted(item.name for item in home.iterdir()) if home.exists() else []
    assert left in ([], ["uninstall.exe"]), left
    assert _value(UNINSTALL_KEY, "DisplayName") is None and not installed.shortcut.exists()


def test_installer_refuses_a_folder_with_other_files(installed):
    home = installed.home
    home.mkdir()
    (home / "app").mkdir()
    (home / "app" / "важный-файл.txt").write_text("не трогать", encoding="utf-8")
    result = installed.setup("/NOSTART")
    assert result.returncode != 0
    assert (home / "app" / "важный-файл.txt").read_text(encoding="utf-8") == "не трогать"
    assert not (home / "uninstall.exe").exists() and not (home / "xgw.cmd").exists()
    assert _value(UNINSTALL_KEY, "DisplayName") is None and not installed.shortcut.exists()
