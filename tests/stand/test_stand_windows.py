"""XGW в Windows на настоящем Xray: шаги установщика, демон без окна, включение VPN
кнопкой панели, системный прокси, fail-closed, остановка и удаление.

Нужны Windows и настоящий Xray: XGW_XRAY_BIN=<путь к xray.exe>. Настройки прокси и
автозапуска этой машины не трогаются: вместо них — отдельные ключи реестра
(XGW_WINPROXY_KEY, XGW_WINRUN_KEY), которые тест создаёт и удаляет. Трафик идёт через
VLESS-серверы стенда на 127.0.0.1.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from panel_client import login, request
from ports import free_port
from stand import Stand, wait_for

from xgw.net import winproxy
from xgw.paths import Paths
from xgw.watch import checks
from xgw.xraycore.service import pid_alive

XRAY_BIN = os.environ.get("XGW_XRAY_BIN", "")

pytestmark = [
    pytest.mark.skipif(os.name != "nt", reason="системный прокси и автозапуск — только Windows"),
    pytest.mark.skipif(
        not XRAY_BIN or not Path(XRAY_BIN).exists(), reason="нет XGW_XRAY_BIN — стенд пропущен"
    ),
]

PREVIOUS = winproxy.Settings(True, "proxy.corp.example:3128", "*.corp.example;<local>", "")


class Machine:
    """Стенд и то, что на настоящей машине лежит в реестре пользователя."""

    def __init__(self, tmp_path: Path) -> None:
        import winreg

        self.winreg = winreg
        self.base = rf"Software\XGW-Test\{uuid.uuid4().hex}"
        self.proxy_key = self.base + r"\Internet Settings"
        self.run_key = self.base + r"\Run"
        self.stand = Stand(
            tmp_path, Path(XRAY_BIN), mode="loopback",
            extra_env={"XGW_WINPROXY_KEY": self.proxy_key, "XGW_WINRUN_KEY": self.run_key},
        )
        # Демон, запущенный установщиком, читает конфиг со своего обычного места.
        self.stand.config_file = self.stand.root / "etc" / "xgw" / "config.toml"
        self.stand.config_file.parent.mkdir(parents=True)
        self.paths = Paths(root=self.stand.root)
        self.proxy = winproxy.WinRegistry(self.proxy_key)
        self.run = winproxy.WinRegistry(self.run_key)
        self.panel_port = free_port()

    def xgw(self, *args: str, timeout: float = 120) -> subprocess.CompletedProcess:
        return self.stand.xgw(*args, timeout=timeout)

    def winsetup(self, *args: str) -> subprocess.CompletedProcess:
        """Шаг установщика. Его вывод читает установщик — в кодировке ANSI системы,
        что бы ни стояло в PYTHONIOENCODING."""
        return self.stand.xgw("winsetup", *args, encoding="mbcs")

    def state(self) -> str:
        result = self.xgw("status", "--json")
        return json.loads(result.stdout).get("state") or "" if result.returncode == 0 else ""

    def token(self) -> str:
        return self.paths.panel_token_file.read_text(encoding="ascii").strip()

    def panel(self) -> dict:
        cookie = login(self.panel_port, self.token())
        response, text = request(self.panel_port, "GET", "/api/state", cookie=cookie)
        assert response.status == 200, text
        return json.loads(text)

    def press(self, action: str, **body) -> dict:
        cookie = login(self.panel_port, self.token())
        response, text = request(
            self.panel_port, "POST", f"/api/{action}", cookie=cookie,
            body=json.dumps(body).encode("utf-8"),
        )
        assert response.status == 200, text
        return json.loads(text)

    def through_proxy(self) -> bool:
        """Загрузка через http-in шлюза — то, что делает программа с системным прокси."""
        port = self.stand.ports["http"]
        url = self.stand.origin_url("/64k")
        return checks.http_get_via_proxy("127.0.0.1", port, url, silence=5.0, max_total=20.0).ok

    def daemon_log(self) -> str:
        try:
            return self.paths.log_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def cleanup(self) -> None:
        for key in (self.proxy_key, self.run_key, self.base, r"Software\XGW-Test"):
            try:
                self.winreg.DeleteKey(self.winreg.HKEY_CURRENT_USER, key)
            except FileNotFoundError:
                pass
            except PermissionError:
                break  # общий ключ не пуст: им пользуется другой тест


@pytest.fixture()
def machine(tmp_path):
    instance = Machine(tmp_path)
    try:
        instance.stand.start()
        yield instance
    finally:
        try:
            instance.xgw("stop", timeout=60)
        finally:
            instance.stand.stop()
            instance.cleanup()


def test_windows_client_from_install_to_uninstall(machine):
    stand, target = machine.stand, winproxy.target(machine.stand.ports["http"])
    stand.set_subscription(stand.names)
    stand.write_config(
        sysproxy=True, panel=True,
        extra=f"\n[panel]\nenabled = true\nport = {machine.panel_port}\n",
    )
    winproxy.write(machine.proxy, PREVIOUS)  # у пользователя уже был свой прокси

    # --- установщик: `xgw winsetup install` ---------------------------------------
    result = machine.winsetup("install")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "XGW запущен" in result.stdout and "Автозапуск при входе в Windows включён" in (
        result.stdout)
    assert f"http://127.0.0.1:{machine.panel_port}/?token={machine.token()}" in result.stdout
    pythonw = str(Path(sys.executable).with_name("pythonw.exe"))
    assert machine.run.get("XGW") == subprocess.list2cmdline(
        [pythonw, "-m", "xgw", "run", "--log-file"])

    # Демон сам получает подписку, собирает конфиг и запускает Xray.
    assert wait_for(lambda: machine.state() == "HEALTHY", 90, step=2), (
        machine.xgw("status").stdout + machine.daemon_log()[-2000:] + stand.xray_log()
    )
    tags = {item["tag"] for item in stand.applied()["inbounds"]}
    assert {"http-in", "socks-in"} <= tags and not tags & {"tproxy-in", "tproxy-in6", "tun-in"}
    assert machine.through_proxy()
    assert pid_alive(stand.xray_pid())

    # Второй демон рядом не запускается.
    second = machine.xgw("run", timeout=30)
    assert second.returncode == 0 and "уже запущен" in second.stdout

    # До нажатия кнопки прокси пользователя не тронут.
    assert winproxy.read(machine.proxy) == PREVIOUS
    assert "VPN: ВЫКЛЮЧЕН" in machine.xgw("status").stdout
    diag = machine.xgw("diag", "--no-net")
    assert "FAIL — 0" in diag.stdout, diag.stdout
    for expected in ("Демон: XGW запущен", "Автозапуск: XGW запускается при входе",
                     "VPN выключен; сейчас стоит прокси proxy.corp.example:3128",
                     "Порты: служебные порты заняты работающим Xray"):
        assert expected in diag.stdout, diag.stdout

    # --- кнопка в панели ----------------------------------------------------------
    state = machine.panel()
    assert state["capture"]["sysproxy"] is True and state["capture"]["mode"] == "off"
    assert state["power"] == {"can_on": True, "can_off": False, "why": ""}
    pressed = machine.press("power", on=True)
    assert pressed["ok"], pressed
    assert "системный прокси Windows" in pressed["text"]
    assert winproxy.read(machine.proxy) == target
    assert machine.panel()["capture"]["mode"] == "on"
    assert f"VPN: включён — системный прокси Windows {target.server}" in (
        machine.xgw("status").stdout)

    # Прокси выключили в настройках Windows — демон возвращает его сам.
    machine.proxy.set("ProxyEnable", 0)
    assert wait_for(lambda: winproxy.read(machine.proxy) == target, 30)
    assert "возвращён" in machine.xgw("status").stdout

    # --- fail-closed: Xray упал ----------------------------------------------------
    old_pid = stand.xray_pid()
    os.kill(old_pid, 15)
    assert wait_for(lambda: not pid_alive(old_pid), 10)
    assert winproxy.read(machine.proxy) == target  # прокси не снят: программы не идут мимо
    assert not machine.through_proxy()
    # Демон поднимает Xray снова, VPN возвращается без действий пользователя.
    assert wait_for(lambda: machine.state() == "HEALTHY" and machine.through_proxy(), 90, step=2), (
        machine.xgw("status").stdout + machine.daemon_log()[-2000:]
    )
    assert stand.xray_pid() != old_pid and winproxy.read(machine.proxy) == target

    # --- выключение возвращает прежние настройки -----------------------------------
    off = machine.xgw("disable")
    assert off.returncode == 0 and "VPN выключен" in off.stdout
    assert winproxy.read(machine.proxy) == PREVIOUS
    on = machine.xgw("enable")
    assert on.returncode == 0, on.stderr
    assert winproxy.read(machine.proxy) == target

    # --- остановка и запуск --------------------------------------------------------
    stopped = machine.xgw("stop")
    assert stopped.returncode == 0, stopped.stdout + stopped.stderr
    assert "демон XGW остановлен" in stopped.stdout and "Xray остановлен" in stopped.stdout
    assert "системный прокси по-прежнему указывает на XGW" in stopped.stdout
    assert not pid_alive(stand.xray_pid() if (stand.root / "run/xgw/xray.pid").exists() else 0)
    assert winproxy.read(machine.proxy) == target  # выбор пользователя не изменился
    log = machine.daemon_log()
    assert "демон XGW запущен" in log and "демон XGW остановлен" in log  # завершился сам
    assert machine.token() not in log

    # Запуск (как после входа в Windows): VPN включён, поэтому Xray нужен сразу — демон
    # поднимает его при старте, не дожидаясь, пока watchdog заметит остановленное ядро.
    started = machine.xgw("start")
    assert started.returncode == 0 and "XGW запущен" in started.stdout
    assert wait_for(machine.through_proxy, 8, step=0.5), machine.daemon_log()[-1500:]
    # Запись появляется чуть позже самого ядра: запуск ещё секунду следит, не упало ли оно.
    assert wait_for(lambda: "Xray запущен" in machine.daemon_log(), 5)
    assert wait_for(lambda: machine.state() == "HEALTHY", 60, step=2)

    # --- удаление: `xgw winsetup uninstall` ----------------------------------------
    removed = machine.winsetup("uninstall")
    assert removed.returncode == 0, removed.stdout + removed.stderr
    for expected in ("демон XGW остановлен", "Xray остановлен",
                     "системный прокси возвращён к настройкам до XGW", "автозапуск убран"):
        assert expected in removed.stdout, removed.stdout
    assert winproxy.read(machine.proxy) == PREVIOUS
    assert machine.run.get("XGW") is None
    assert not (stand.root / "run/xgw/xray.pid").exists()
    assert not machine.through_proxy()


def test_fail_open_returns_the_previous_proxy_while_xray_is_down(machine, monkeypatch):
    """fail_mode = "open": Xray недоступен дольше минуты — прежние настройки прокси
    возвращаются на время, а с Xray возвращается и прокси XGW."""
    stand, target = machine.stand, winproxy.target(machine.stand.ports["http"])
    stand.set_subscription(stand.names)
    # Подписка обновляется редко: обновление пересобрало бы испорченный ниже конфиг и
    # подняло Xray раньше, чем пройдёт минута, после которой прокси возвращается.
    stand.write_config(sysproxy=True, fail_mode="open", refresh_minutes=30)
    winproxy.write(machine.proxy, PREVIOUS)
    assert machine.winsetup("install", "--no-autostart").returncode == 0
    assert wait_for(lambda: machine.state() == "HEALTHY", 90, step=2), machine.daemon_log()[-2000:]
    assert machine.xgw("enable").returncode == 0
    assert winproxy.read(machine.proxy) == target

    # Xray «сломан»: его конфиг на диске подменён нерабочим, демон поднять его не может.
    config = stand.root / "etc/xgw/xray/config.json"
    good = config.read_text(encoding="utf-8")
    last_good = stand.root / "var/lib/xgw/last-good.json"
    config.write_text('{"inbounds": "сломано"}', encoding="utf-8")
    last_good.write_text('{"inbounds": "сломано"}', encoding="utf-8")
    os.kill(stand.xray_pid(), 15)
    assert wait_for(lambda: winproxy.read(machine.proxy) == PREVIOUS, 120, step=2), (
        machine.xgw("status").stdout + machine.daemon_log()[-2000:]
    )
    assert "VPN: ВРЕМЕННО ВЫКЛЮЧЕН" in machine.xgw("status").stdout

    config.write_text(good, encoding="utf-8")
    assert wait_for(lambda: winproxy.read(machine.proxy) == target, 90, step=2), (
        machine.xgw("status").stdout + machine.daemon_log()[-2000:]
    )
    assert machine.through_proxy()
