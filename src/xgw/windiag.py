"""`xgw diag` в Windows: те же вердикты OK, WARN и FAIL, но о другом — ядра, файрвола
и NetworkManager здесь нет, зато есть системный прокси, автозапуск и занятые порты
(другие VPN-клиенты часто держат те же номера). Ничего не меняет в системе.
"""

from __future__ import annotations

import dataclasses
import os
import platform
import subprocess
import sys
from collections.abc import Callable
from pathlib import PureWindowsPath

from . import winapp
from .diag import FAIL, OK, WARN, Check, Diag
from .net import cmd, winproxy
from .net.wincapture import WinCapture
from .xraycore import binary
from .xraycore.service import process_image

# Программы самого XGW: порт, занятый ими, чужим не считается.
OURS = ("xray", "python", "pythonw")

def parse_listeners(text: str) -> dict[int, int]:
    """Вывод `netstat -ano -p TCP` → порт: номер процесса, который его слушает."""
    found: dict[int, int] = {}
    for line in text.splitlines():
        words = line.split()
        if len(words) < 5 or words[0] != "TCP" or words[3] != "LISTENING":
            continue
        port, pid = words[1].rpartition(":")[2], words[4]
        if port.isdigit() and pid.isdigit():
            found.setdefault(int(port), int(pid))
    return found


def listeners() -> dict[int, int]:
    """Кто слушает порты TCP на этой машине. Заголовки netstat печатает в кодировке
    консоли — нужны только строки с цифрами и латиницей, остальное не разбирается."""
    try:
        proc = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"], capture_output=True, timeout=20, **cmd.HIDDEN
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise cmd.CommandError(f"netstat: {exc}") from exc
    return parse_listeners(proc.stdout.decode("ascii", errors="replace"))


class WinDiag(Diag):
    def __init__(
        self,
        *args,
        registry: winproxy.Registry | None = None,
        run_registry: winproxy.Registry | None = None,
        image: Callable[[int], str] = process_image,
        listening: Callable[[], dict[int, int]] = listeners,
        daemon_running: Callable[[], bool] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.registry = registry
        self.run_registry = run_registry
        self.image = image
        self.listening = listening
        self.daemon_running = daemon_running or (lambda: winapp.daemon_running(self.paths))
        # Для общей проверки «Xray API»: «установлен» здесь значит «демон работает».
        self.installed = self.daemon_running()

    def run(self) -> list[Check]:
        groups: list[tuple[str, Callable[[], list[Check]]]] = [
            ("Система", self._system),
            ("Конфиг", self._config),
            ("Xray", self._xray),
            ("Порты", self._ports),
            ("Демон", self._daemon),
            ("Системный прокси", self._proxy),
            ("Xray API", self._xray_api),
            ("Трафик проверок", self._budget),
        ]
        if self.net:
            groups += [("probe.url", self._probe), ("bootstrap DNS", self._bootstrap)]
        result: list[Check] = []
        for name, group in groups:
            try:
                result.extend(group())
            except Exception as exc:  # одна проверка не должна ронять остальные
                self.log.error("diag, проверка «%s»: %s", name, exc)
                result.append(Check(name, WARN, f"проверка не выполнена: {exc}"))
        # Общие проверки советуют команды с sudo; в Windows оно не нужно.
        return [
            dataclasses.replace(check, advice=check.advice.replace("sudo ", ""))
            for check in result
        ]

    # --- система, конфиг, Xray ---------------------------------------------------

    def _system(self) -> list[Check]:
        python = f"Python {sys.version_info.major}.{sys.version_info.minor}"
        if os.name != "nt":
            return [Check("Система", FAIL, "эта проверка — для XGW в Windows")]
        return [Check("Система", OK, f"{platform.system()} {platform.release()} "
                                     f"(сборка {platform.version()}), {python}")]

    def _config(self) -> list[Check]:
        path = self.paths.config_file
        if self.config_error:
            return [Check(
                "Конфиг", FAIL, self.config_error,
                f"исправьте {path} либо удалите его и запустите установщик XGW ещё раз — "
                "файл будет создан заново; подписки (panel.json) при этом сохранятся",
            )]
        result: list[Check] = []
        if self.config_warnings:
            result.append(Check("Конфиг", WARN, "; ".join(self.config_warnings)))
        if not self.cfg.capture.sysproxy:
            result.append(Check(
                "Конфиг", FAIL,
                f"capture.method = {self.cfg.capture.method!r}: в Windows XGW включает VPN "
                "только через системный прокси",
                f'впишите в {path} в раздел [capture]: method = "sysproxy"',
            ))
        if not result:
            result.append(Check("Конфиг", OK, f"{path} читается; режим — системный прокси"))
        return result

    def _xray(self) -> list[Check]:
        if self.xray_bin is None:
            return [Check(
                "Xray", FAIL, f"не найден ({self.paths.xray_bin})",
                "запустите установщик XGW ещё раз либо xgw update-xray",
            )]
        version = binary.installed_version(self.xray_bin)
        if version is None:
            return [Check("Xray", FAIL, f"{self.xray_bin} не запускается", "xgw update-xray")]
        text = ".".join(map(str, version))
        if version < binary.MIN_VERSION:
            return [Check(
                "Xray", FAIL,
                f"версия {text} ниже {binary.min_version_text()}: поля httpMethod в ней нет, "
                "серверы проверялись бы HEAD-запросом и «заморозка» осталась бы незамеченной",
                "xgw update-xray",
            )]
        if not binary.has_string(self.xray_bin, b"httpMethod"):
            return [Check("Xray", FAIL, f"версия {text}, но поля httpMethod в бинарнике нет",
                          "xgw update-xray")]
        return [Check("Xray", OK, f"версия {text}, GET-проверка (httpMethod) поддерживается")]

    def _xray_api(self) -> list[Check]:
        if (
            self.installed and self.xray_bin is not None
            and not self.paths.xray_config_file.exists() and not self.xray_up()
        ):
            # Сразу после установки: конфиг Xray собирается, когда появляется первый сервер.
            return [Check(
                "Xray API", WARN,
                "Xray ещё не запускался: рабочего конфига пока нет — он собирается с "
                "первым сервером из подписки",
                "добавьте подписку в панели управления (ярлык «XGW» в меню «Пуск»); если "
                "она уже добавлена — причина в xgw logs",
            )]
        # У общей проверки советы — про systemd и journald; здесь журналы лежат в файлах.
        journal = f"xgw logs; журнал Xray — {self.paths.run / 'xray.log'}"
        return [
            dataclasses.replace(check, advice=journal) if "journalctl" in check.advice else check
            for check in super()._xray_api()
        ]

    # --- порты --------------------------------------------------------------------

    def _ports(self) -> list[Check]:
        ports = {
            "api": self.cfg.xray.api_port, "metrics": self.cfg.xray.metrics_port,
            "socks": self.cfg.xray.socks_port, "http": self.cfg.xray.http_port,
        }
        if self.cfg.panel.enabled and not self.installed:
            ports["панель"] = self.cfg.panel.port  # у работающего демона она и должна быть занята
        busy = {name: port for name, port in ports.items() if not self.port_free(port)}
        if not busy:
            return [Check("Порты", OK, "служебные порты свободны")]
        owners = self._owners(busy)
        foreign = {
            name: port for name, port in busy.items()
            if PureWindowsPath(owners.get(port, "")).stem.lower() not in OURS
        }
        if not foreign and self.xray_up():
            return [Check("Порты", OK, "служебные порты заняты работающим Xray")]
        shown = foreign or busy
        # Пути программ — пути Windows, на какой бы системе их ни разбирали.
        text = ", ".join(
            f"{name} {port}"
            + (f" — {PureWindowsPath(owners[port]).name}" if owners.get(port) else "")
            for name, port in shown.items()
        )
        return [Check(
            "Порты", FAIL, "заняты другой программой: " + text,
            "закройте эту программу (часто это другой VPN-клиент) либо смените порт в "
            f"разделе [xray] файла {self.paths.config_file}",
        )]

    def _owners(self, busy: dict[str, int]) -> dict[int, str]:
        """Порт → программа, которая его заняла; чего узнать не удалось, того нет."""
        try:
            pids = self.listening()
        except cmd.CommandError as exc:
            self.log.debug("netstat: %s", exc)
            return {}
        owners: dict[int, str] = {}
        for port in busy.values():
            image = self.image(pids[port]) if port in pids else ""
            if image:
                owners[port] = image
        return owners

    # --- демон, автозапуск, системный прокси ----------------------------------------

    def _daemon(self) -> list[Check]:
        result: list[Check] = []
        if self.installed:
            result.append(Check("Демон", OK, "XGW запущен"))
        else:
            result.append(Check(
                "Демон", WARN, "XGW не запущен: серверы не проверяются, панель не открывается",
                "xgw start (или выйдите из Windows и войдите снова)",
            ))
        try:
            line = winapp.autostart(self.run_registry)
        except winproxy.ProxyError as exc:
            return [*result, Check("Автозапуск", WARN, f"не проверен: {exc}")]
        if line:
            result.append(Check("Автозапуск", OK, "XGW запускается при входе в Windows"))
        else:
            result.append(Check(
                "Автозапуск", WARN, "XGW не запустится сам при входе в Windows",
                "запустите установщик XGW ещё раз",
            ))
        return result

    def _proxy(self) -> list[Check]:
        if not self.cfg.capture.sysproxy:
            return []
        capture = WinCapture(self.cfg, self.paths, registry=self.registry, logger=self.log)
        try:
            current = winproxy.read(capture.registry)
        except winproxy.ProxyError as exc:
            return [Check("Системный прокси", WARN, f"не прочитан: {exc}")]
        info = capture.describe()
        mode, ours = info["mode"], info["proxy"]
        if mode == "none":
            return [Check("Системный прокси", OK, "VPN выключен в конфиге (capture.local = false)")]
        if mode == "on":
            if info["loaded"]:
                return [Check("Системный прокси", OK, f"VPN включён: прокси Windows — {ours}")]
            return [Check(
                "Системный прокси", WARN,
                f"VPN включён, но прокси Windows сейчас не {ours} — его изменили не в XGW",
                "демон вернёт его на ближайшем шаге; сразу — xgw enable",
            )]
        note = "VPN выключен" if mode == "off" else "VPN временно выключен (fail_mode = open)"
        if current.autoconfig:
            return [Check("Системный прокси", OK, f"{note}; задан PAC-файл {current.autoconfig} — "
                                                  "на время работы VPN XGW его убирает")]
        if current.enable and current.server:
            return [Check("Системный прокси", OK, f"{note}; сейчас стоит прокси {current.server} — "
                                                  "XGW вернёт его при выключении VPN")]
        return [Check("Системный прокси", OK, f"{note}; прокси в Windows не задан")]
