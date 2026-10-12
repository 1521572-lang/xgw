"""Системный прокси Windows — то, чем на Windows заменён перехват трафика.

На Windows XGW не шлюз, а клиент для самой машины: «включить VPN» значит записать в
настройки пользователя прокси 127.0.0.1:<http_port>. Им пользуются браузеры и
программы, которые смотрят на системный прокси; остальные ходят напрямую.

Настройки лежат в реестре пользователя, прав администратора не нужно:

    HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings
        ProxyEnable    REG_DWORD  0 | 1
        ProxyServer    REG_SZ     127.0.0.1:10819
        ProxyOverride  REG_SZ     localhost;127.*;10.*;…;<local> — что идёт мимо прокси
        AutoConfigURL  REG_SZ     адрес PAC-файла; он сильнее ручного прокси

Чтобы уже запущенные программы узнали об изменении сразу, им рассылается уведомление
WinINET (InternetSetOption: SETTINGS_CHANGED и REFRESH).

Реестр — за интерфейсом Registry: в тестах он подменяется, а проверка на настоящем
winreg идёт на отдельном ключе (переменная XGW_WINPROXY_KEY), не на настройках машины.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Protocol

KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
# Адреса, которые в VPN не нужны: сама машина, домашняя сеть, имена без точки.
OVERRIDE = ";".join([
    "localhost", "127.*", "10.*", "192.168.*",
    *(f"172.{second}.*" for second in range(16, 32)),
    "<local>",
])
INTERNET_OPTION_REFRESH = 37
INTERNET_OPTION_SETTINGS_CHANGED = 39


class ProxyError(Exception):
    """Настройки прокси не прочитаны или не записаны."""


@dataclass(frozen=True)
class Settings:
    enable: bool = False
    server: str = ""
    override: str = ""
    autoconfig: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: object) -> Settings:
        """Сохранённые настройки; чужие или битые данные — «прокси выключен»."""
        if not isinstance(data, dict):
            return cls()
        return cls(
            enable=data.get("enable") is True,
            server=data["server"] if isinstance(data.get("server"), str) else "",
            override=data["override"] if isinstance(data.get("override"), str) else "",
            autoconfig=data["autoconfig"] if isinstance(data.get("autoconfig"), str) else "",
        )


class Registry(Protocol):
    def get(self, name: str) -> object | None: ...

    def set(self, name: str, value: int | str) -> None: ...

    def delete(self, name: str) -> None: ...


class WinRegistry:
    """Значения одного ключа в HKEY_CURRENT_USER (winreg)."""

    def __init__(self, path: str = KEY) -> None:
        self.path = path

    def _open(self, write: bool):
        import winreg

        try:
            if write:
                return winreg.CreateKeyEx(
                    winreg.HKEY_CURRENT_USER, self.path, 0,
                    winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
                )
            return winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.path, 0, winreg.KEY_QUERY_VALUE)
        except OSError as exc:
            raise ProxyError(f"реестр HKCU\\{self.path}: {exc}") from exc

    def get(self, name: str) -> object | None:
        import winreg

        try:
            with self._open(False) as key:
                return winreg.QueryValueEx(key, name)[0]
        except FileNotFoundError:
            return None
        except ProxyError as exc:
            if isinstance(exc.__cause__, FileNotFoundError):
                return None  # ключа ещё нет — значит, и значения нет
            raise
        except OSError as exc:
            raise ProxyError(f"реестр, чтение {name}: {exc}") from exc

    def set(self, name: str, value: int | str) -> None:
        import winreg

        kind = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
        try:
            with self._open(True) as key:
                winreg.SetValueEx(key, name, 0, kind, value)
        except OSError as exc:
            raise ProxyError(f"реестр, запись {name}: {exc}") from exc

    def delete(self, name: str) -> None:
        import winreg

        try:
            with self._open(True) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise ProxyError(f"реестр, удаление {name}: {exc}") from exc


def read(registry: Registry) -> Settings:
    def text(name: str) -> str:
        value = registry.get(name)
        return value if isinstance(value, str) else ""

    return Settings(
        enable=registry.get("ProxyEnable") == 1,
        server=text("ProxyServer"),
        override=text("ProxyOverride"),
        autoconfig=text("AutoConfigURL"),
    )


def write(registry: Registry, settings: Settings) -> None:
    """Записывает настройки целиком. Сначала адрес, потом включение: в промежутке
    программы не должны увидеть «прокси включён» с чужим или пустым адресом."""
    for name, value in (
        ("ProxyServer", settings.server),
        ("ProxyOverride", settings.override),
        ("AutoConfigURL", settings.autoconfig),
    ):
        if value:
            registry.set(name, value)
        else:
            registry.delete(name)
    registry.set("ProxyEnable", 1 if settings.enable else 0)


def target(port: int) -> Settings:
    """Настройки «всё через Xray»: его http-in на этой машине, без PAC."""
    return Settings(enable=True, server=f"127.0.0.1:{port}", override=OVERRIDE, autoconfig="")


def is_ours(settings: Settings, port: int) -> bool:
    """Включён ли сейчас именно прокси XGW. PAC сильнее ручного прокси, поэтому с
    заданным AutoConfigURL наш адрес не действует."""
    return settings.enable and settings.server == f"127.0.0.1:{port}" and not settings.autoconfig


def notify() -> None:
    """Сообщает работающим программам, что настройки прокси изменились."""
    import ctypes

    wininet = ctypes.WinDLL("wininet", use_last_error=True)
    for option in (INTERNET_OPTION_SETTINGS_CHANGED, INTERNET_OPTION_REFRESH):
        if not wininet.InternetSetOptionW(None, option, None, 0):
            raise ProxyError(f"InternetSetOption({option}): ошибка {ctypes.get_last_error()}")


def scratch_key(variable: str) -> str | None:
    """Ключ реестра для тестов и стенда из переменной окружения; None — настоящий.

    С заданным XGW_ROOT (корень для тестов) настоящие настройки пользователя не
    трогаются никогда: без отдельного ключа это ошибка, а не молчаливая запись в них.
    """
    value = os.environ.get(variable, "").strip()
    if value:
        return value
    if os.environ.get("XGW_ROOT"):
        raise ProxyError(
            f"задан XGW_ROOT (тесты, стенд): настройки этой машины не трогаются — "
            f"задайте {variable} (отдельный ключ в HKCU)"
        )
    return None


def default_registry() -> tuple[Registry, Callable[[], None]]:
    """Реестр и уведомление для этой машины. XGW_WINPROXY_KEY — другой ключ в HKCU
    (тесты и стенд): настройки машины тогда не трогаются и уведомлять некого."""
    scratch = scratch_key("XGW_WINPROXY_KEY")
    if scratch:
        return WinRegistry(scratch), lambda: None
    return WinRegistry(), notify
