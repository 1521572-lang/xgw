"""Системный прокси Windows: чтение и запись настроек, режимы WinCapture. Реестр
подменён словарём; настоящий winreg проверяется на отдельном ключе, не на настройках
машины (их тесты не читают и не меняют)."""

import os
import uuid

import pytest

from xgw import config
from xgw.net import winproxy
from xgw.net.capture import CaptureError
from xgw.net.wincapture import WinCapture
from xgw.net.winproxy import Settings
from xgw.paths import Paths

PORT = 10819
OURS = f"127.0.0.1:{PORT}"


class FakeRegistry:
    def __init__(self, **values) -> None:
        self.values: dict[str, object] = dict(values)
        self.writes: list[tuple[str, object]] = []
        self.broken = False

    def get(self, name):
        if self.broken:
            raise winproxy.ProxyError("реестр недоступен")
        return self.values.get(name)

    def set(self, name, value) -> None:
        if self.broken:
            raise winproxy.ProxyError("реестр недоступен")
        self.values[name] = value
        self.writes.append((name, value))

    def delete(self, name) -> None:
        if self.values.pop(name, None) is not None:
            self.writes.append((name, None))


class Rig:
    def __init__(self, tmp_path, **registry) -> None:
        self.paths = Paths(root=tmp_path)
        self.paths.ensure()
        self.cfg = config.Config()
        self.cfg.capture.method = "sysproxy"
        self.cfg.xray.http_port = PORT
        self.registry = FakeRegistry(**registry)
        self.notified = 0

    def _notify(self) -> None:
        self.notified += 1

    def capture(self) -> WinCapture:
        return WinCapture(self.cfg, self.paths, registry=self.registry, notify=self._notify)

    def now(self) -> Settings:
        return winproxy.read(self.registry)


@pytest.fixture()
def rig(tmp_path):
    return Rig(tmp_path)


# --- настройки ---------------------------------------------------------------------------------


def test_read_and_write_roundtrip():
    registry = FakeRegistry(ProxyEnable=1, ProxyServer="proxy.corp:3128", AutoConfigURL="")
    assert winproxy.read(registry) == Settings(True, "proxy.corp:3128", "", "")
    winproxy.write(registry, Settings(False, "", "", "http://wpad/proxy.pac"))
    assert registry.values == {"ProxyEnable": 0, "AutoConfigURL": "http://wpad/proxy.pac"}
    # Сначала адрес, потом включение: «включён» с прежним адресом никто не увидит.
    winproxy.write(registry, winproxy.target(PORT))
    assert [name for name, _value in registry.writes][-1] == "ProxyEnable"
    assert winproxy.read(registry) == Settings(True, OURS, winproxy.OVERRIDE, "")


def test_override_keeps_local_addresses_out_of_the_vpn():
    parts = winproxy.OVERRIDE.split(";")
    for expected in ("localhost", "127.*", "10.*", "192.168.*", "172.16.*", "172.31.*", "<local>"):
        assert expected in parts
    assert "172.15.*" not in parts and "172.32.*" not in parts


def test_foreign_types_and_missing_values_read_as_off():
    assert winproxy.read(FakeRegistry()) == Settings()
    assert winproxy.read(FakeRegistry(ProxyEnable="1", ProxyServer=7)) == Settings()
    assert Settings.from_dict(None) == Settings()
    assert Settings.from_dict({"enable": "yes", "server": 5}) == Settings()
    saved = Settings(True, "a:1", "x", "http://p/pac")
    assert Settings.from_dict(saved.to_dict()) == saved


def test_pac_file_means_the_proxy_is_not_ours():
    assert winproxy.is_ours(Settings(True, OURS, "", ""), PORT)
    assert not winproxy.is_ours(Settings(True, OURS, "", "http://wpad/proxy.pac"), PORT)
    assert not winproxy.is_ours(Settings(False, OURS, "", ""), PORT)
    assert not winproxy.is_ours(Settings(True, "127.0.0.1:10809", "", ""), PORT)


# --- режимы ------------------------------------------------------------------------------------


def test_vpn_is_off_until_the_user_turns_it_on(rig):
    capture = rig.capture()
    assert capture.mode() == "off" and capture.choice() is None
    assert capture.loaded() is True and rig.registry.writes == []
    assert capture.up() == "off" and rig.registry.writes == []  # демон ничего не трогает
    info = capture.describe()
    assert info["sysproxy"] is True and info["proxy"] == OURS and info["lan_if"] == ""
    assert info["local"] is True and info["lan"] is False and info["loaded"] is True
    assert capture.transparent is False and capture.configured and capture.capturing


def test_enable_sets_the_proxy_and_disable_returns_what_was_before(tmp_path):
    rig = Rig(tmp_path, ProxyEnable=1, ProxyServer="proxy.corp:3128", ProxyOverride="*.corp")
    before = rig.now()
    capture = rig.capture()
    assert capture.enable() == "on"
    assert rig.now() == winproxy.target(PORT) and rig.notified == 1
    assert capture.mode() == "on" and capture.loaded() is True and capture.choice() is True
    assert capture.enable() == "on" and rig.notified == 1  # повторно — ничего не пишет

    assert rig.capture().disable() == "off"  # другой процесс: состояние — в файле
    assert rig.now() == before and rig.notified == 2
    assert capture.mode() == "off" and capture.loaded() is True
    assert "proxy_before" not in capture._state() and "proxy_server" not in capture._state()


def test_pac_is_removed_while_on_and_comes_back(tmp_path):
    rig = Rig(tmp_path, ProxyEnable=0, AutoConfigURL="http://wpad.corp/proxy.pac")
    capture = rig.capture()
    capture.enable()
    assert rig.now() == winproxy.target(PORT) and "AutoConfigURL" not in rig.registry.values
    capture.disable()
    assert rig.now() == Settings(False, "", "", "http://wpad.corp/proxy.pac")


def test_switching_the_proxy_off_in_windows_does_not_lose_what_was_before(tmp_path):
    rig = Rig(tmp_path, ProxyEnable=1, ProxyServer="proxy.corp:3128", ProxyOverride="*.corp")
    before = rig.now()
    capture = rig.capture()
    capture.enable()
    rig.registry.values["ProxyEnable"] = 0  # выключили в настройках Windows
    assert capture.loaded() is False
    assert capture.up() == "on" and capture.loaded() is True  # демон вернул
    rig.registry.values["ProxyOverride"] = "example.org"  # поправили исключения
    capture.up()
    assert rig.now() == winproxy.target(PORT)
    capture.disable()
    assert rig.now() == before  # а не «наш адрес, выключенный»

    # Выключили в Windows и следом в панели: прежние настройки всё равно возвращаются.
    capture.enable()
    rig.registry.values["ProxyEnable"] = 0
    capture.disable()
    assert rig.now() == before and capture.loaded() is True


def test_a_disabled_leftover_with_our_address_is_left_alone(tmp_path):
    """XGW этот прокси не ставил (состояния нет): выключенный адрес — чужое дело."""
    rig = Rig(tmp_path, ProxyEnable=0, ProxyServer=OURS)
    capture = rig.capture()
    assert capture.loaded() is True
    capture.disable()
    assert rig.registry.writes == [] and rig.now() == Settings(False, OURS, "", "")


def test_proxy_changed_by_someone_else_is_put_back_while_on(rig):
    capture = rig.capture()
    capture.enable()
    rig.registry.values["ProxyEnable"] = 0  # выключили в настройках Windows
    assert capture.loaded() is False
    assert capture.up() == "on" and capture.loaded() is True
    # Чужой прокси, поставленный поверх нашего, запоминается как «было до XGW».
    winproxy.write(rig.registry, Settings(True, "other:8080", "", ""))
    assert capture.loaded() is False
    capture.up()
    assert rig.now() == winproxy.target(PORT)
    capture.disable()
    assert rig.now() == Settings(True, "other:8080", "", "")


def test_disable_does_not_touch_a_proxy_that_is_no_longer_ours(rig):
    capture = rig.capture()
    capture.enable()
    foreign = Settings(True, "other:8080", "", "")
    winproxy.write(rig.registry, foreign)
    writes = len(rig.registry.writes)
    capture.disable()
    assert rig.now() == foreign and len(rig.registry.writes) == writes
    assert capture.loaded() is True and "proxy_before" not in capture._state()


def test_changed_port_is_still_recognised_as_ours(rig):
    capture = rig.capture()
    capture.enable()
    rig.cfg.xray.http_port = 10900
    moved = rig.capture()
    assert moved.loaded() is False  # включён, а прокси указывает на прежний порт
    moved.up()
    assert rig.now() == winproxy.target(10900)
    rig.cfg.xray.http_port = 10901
    rig.capture().disable()  # выключили уже с третьим портом — прокси всё равно наш
    assert rig.now() == Settings()


def test_fail_open_returns_previous_settings_for_a_while(tmp_path):
    rig = Rig(tmp_path, ProxyEnable=1, ProxyServer="proxy.corp:3128")
    before = rig.now()
    capture = rig.capture()
    capture.enable()
    assert capture.open() == "open" and rig.now() == before and capture.loaded() is True
    assert capture.choice() is True  # выбор пользователя не изменился
    assert capture.close() == "on" and rig.now() == winproxy.target(PORT)
    capture.disable()
    assert rig.now() == before


def test_down_restores_the_proxy_and_keeps_the_choice(rig):
    capture = rig.capture()
    capture.enable()
    capture.down()
    assert rig.now() == Settings() and capture.choice() is True
    assert capture.loaded() is False  # включён по выбору, а прокси снят — демон вернёт


def test_capture_off_in_config_means_none(rig):
    rig.cfg.capture.local = False
    capture = rig.capture()
    assert capture.mode() == "none" and not capture.configured
    assert capture.enable() == "none" and rig.registry.writes == []


def test_registry_failure_is_a_capture_error_and_unknown_state(rig):
    capture = rig.capture()
    rig.registry.broken = True
    assert capture.loaded() is None
    with pytest.raises(CaptureError, match="реестр недоступен"):
        capture.enable()
    assert capture.choice() is None  # выбор запоминается, только когда прокси записан


def test_failed_notification_is_not_an_error(rig, caplog):
    def notify():
        raise winproxy.ProxyError("InternetSetOption(39): ошибка 5")

    capture = WinCapture(rig.cfg, rig.paths, registry=rig.registry, notify=notify)
    capture.log.propagate = True
    assert capture.enable() == "on" and rig.now() == winproxy.target(PORT)
    assert "не уведомлены" in caplog.text


# --- настоящий реестр --------------------------------------------------------------------------


@pytest.fixture()
def scratch_key():
    import winreg

    path = rf"Software\XGW-Test\{uuid.uuid4().hex}\Internet Settings"
    yield path
    parent = path.rsplit("\\", 1)[0]
    for key in (path, parent, r"Software\XGW-Test"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except FileNotFoundError:
            pass
        except PermissionError:
            break  # общий ключ не пуст: им пользуется другой тест


@pytest.mark.skipif(os.name != "nt", reason="реестр есть только в Windows")
def test_real_registry_on_a_scratch_key(tmp_path, scratch_key, monkeypatch):
    import winreg

    registry = winproxy.WinRegistry(scratch_key)
    assert winproxy.read(registry) == Settings()  # ключа ещё нет
    registry.delete("ProxyServer")  # отсутствующее значение — не ошибка
    previous = Settings(True, "proxy.corp:3128", "*.corp;<local>", "")
    winproxy.write(registry, previous)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, scratch_key) as key:
        assert winreg.QueryValueEx(key, "ProxyEnable") == (1, winreg.REG_DWORD)
        assert winreg.QueryValueEx(key, "ProxyServer") == ("proxy.corp:3128", winreg.REG_SZ)

    # Через переменную окружения тот же ключ получает и WinCapture — без уведомлений.
    monkeypatch.setenv("XGW_WINPROXY_KEY", scratch_key)
    rig = Rig(tmp_path)
    capture = WinCapture(rig.cfg, rig.paths)
    assert capture.registry.path == scratch_key
    capture.enable()
    assert winproxy.read(registry) == winproxy.target(PORT)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, scratch_key) as key:
        assert winreg.QueryValueEx(key, "ProxyOverride")[0] == winproxy.OVERRIDE
    capture.disable()
    assert winproxy.read(registry) == previous
