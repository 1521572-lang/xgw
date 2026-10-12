"""XGW в Windows: клиент для самой машины (без шлюза для Wi-Fi).

Здесь то, что в Linux делают systemd и `xgw install`: автозапуск демона при входе
пользователя, единственный его экземпляр, остановка и первый запуск после установки.
Прав администратора не нужно ни для чего: программа живёт в профиле пользователя
(%LOCALAPPDATA%\\XGW), автозапуск и системный прокси — настройки самого пользователя.

Файлы на место кладёт установщик (packaging/windows); он же вызывает `xgw winsetup
install` после копирования и `xgw winsetup uninstall` перед удалением.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from . import config, engine, log
from .generator import validate
from .net import winproxy
from .net.capture import CaptureError
from .net.wincapture import WinCapture
from .paths import InstanceLock, Paths, atomic_write_text
from .watch import panel
from .xraycore.service import XrayServiceError, pid_alive

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "XGW"
LOCK_NAME = "daemon.lock"
PID_NAME = "daemon.pid"
STOP_NAME = "stop-request"
STOP_POLL = 1.0
START_WAIT = 20.0

CONFIG_TEMPLATE = """\
# Конфигурация XGW для Windows. Править её не обязательно: подписки добавляются в
# панели управления (ярлык «XGW» в меню «Пуск») и лежат рядом, в panel.json.
# Остальные параметры и их описания — в config.example.toml проекта; раздел [network]
# и правила перехвата Linux в Windows не действуют.

[capture]
# Системный прокси Windows вместо перехвата трафика: через VPN идут браузеры и
# программы, которые смотрят на системный прокси; остальные ходят напрямую.
method = "sysproxy"
lan = false
# closed — пока Xray не отвечает, прокси остаётся включённым: программы без интернета,
# но не мимо VPN; open — через минуту прежние настройки прокси временно возвращаются.
fail_mode = "closed"

[xray]
# Порты на 127.0.0.1. Не 10808 и 10809, как в Linux: их часто занимают другие
# VPN-клиенты для Windows.
socks_port = 10818
http_port = 10819

[notify]
# Уведомлений на рабочий стол в Windows пока нет; Telegram подключается в панели.
desktop = false
"""


class WinAppError(Exception):
    """Действие не выполнено; текст — что случилось и что делать."""


def windowless() -> bool:
    """Процесс без окна консоли — так XGW запускают ярлык и автозапуск: печатать ему
    некуда. pythonw.exe всегда без окна, даже когда запустившая программа передала
    ему свои потоки вывода (тогда sys.stderr есть, но читать его некому)."""
    return sys.stderr is None or Path(sys.executable).stem.lower() == "pythonw"


def alert(text: str) -> None:
    """Окно с сообщением об ошибке — для запуска без консоли (ярлык в меню «Пуск»),
    где печатать некуда."""
    import ctypes

    ctypes.windll.user32.MessageBoxW(None, text, "XGW", 0x10)  # MB_ICONERROR


# --- автозапуск ------------------------------------------------------------------


def run_registry() -> winproxy.Registry:
    """Ключ автозапуска пользователя. XGW_WINRUN_KEY — другой ключ в HKCU (тесты)."""
    return winproxy.WinRegistry(winproxy.scratch_key("XGW_WINRUN_KEY") or RUN_KEY)


def daemon_command(python: Path | None = None) -> list[str]:
    """Демон без окна консоли: pythonw.exe рядом с тем Python, которым запущен XGW.
    Журнал такой процесс может вести только в файл."""
    interpreter = Path(python or sys.executable)
    windowless = interpreter.with_name("pythonw.exe")
    program = windowless if windowless.exists() else interpreter
    return [str(program), "-m", "xgw", "run", "--log-file"]


def autostart(registry: winproxy.Registry | None = None) -> str:
    """Команда автозапуска, записанная сейчас; пусто — автозапуска нет."""
    value = (registry or run_registry()).get(RUN_NAME)
    return value if isinstance(value, str) else ""


def set_autostart(
    registry: winproxy.Registry | None = None, command: list[str] | None = None
) -> None:
    line = subprocess.list2cmdline(command or daemon_command())
    (registry or run_registry()).set(RUN_NAME, line)


def remove_autostart(registry: winproxy.Registry | None = None) -> None:
    (registry or run_registry()).delete(RUN_NAME)


# --- единственный экземпляр демона ------------------------------------------------


class DaemonGuard:
    """Держит блокировку, пока демон работает, и слушает просьбу остановиться.

    Жив ли демон, решает блокировка, а не pid-файл: систему не обманет ни файл,
    переживший перезагрузку, ни чужой процесс с тем же номером.
    """

    def __init__(self, paths: Paths) -> None:
        self.paths = paths
        self.lock = InstanceLock(paths.run / LOCK_NAME)
        self.pid_file = paths.run / PID_NAME
        self.stop_file = paths.run / STOP_NAME
        self._watcher: threading.Thread | None = None

    def acquire(self) -> bool:
        """False — демон уже работает в другом процессе."""
        if not self.lock.acquire():
            return False
        self.stop_file.unlink(missing_ok=True)  # просьба относилась к прежнему демону
        atomic_write_text(self.pid_file, f"{os.getpid()}\n", mode=0o644)
        return True

    def watch(self, stop: threading.Event) -> None:
        """Файл stop-request (его кладёт `xgw stop`) завершает демон так же, как сигнал:
        в Windows послать сигнал процессу без консоли нечем."""

        def loop() -> None:
            while not stop.wait(STOP_POLL):
                if self.stop_file.exists():
                    stop.set()

        self._watcher = threading.Thread(target=loop, name="xgw-stop", daemon=True)
        self._watcher.start()

    def release(self) -> None:
        self.pid_file.unlink(missing_ok=True)
        self.stop_file.unlink(missing_ok=True)
        self.lock.release()


def daemon_running(paths: Paths) -> bool:
    probe = InstanceLock(paths.run / LOCK_NAME)
    if probe.acquire():
        probe.release()
        return False
    return True


def _daemon_pid(paths: Paths) -> int:
    try:
        return int((paths.run / PID_NAME).read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return 0


def start_daemon(
    paths: Paths, *, command: list[str] | None = None, wait: float = START_WAIT
) -> bool:
    """Запускает демон отдельным процессом без окна. True — он работает (в том числе
    если уже работал); False — за отведённое время не появился."""
    if daemon_running(paths):
        return True
    paths.ensure()
    flags = (
        subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        if os.name == "nt" else 0
    )
    try:
        subprocess.Popen(
            command or daemon_command(),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags, close_fds=True, cwd=str(paths.root),
        )
    except OSError as exc:
        raise WinAppError(f"демон XGW не запущен: {exc}") from exc
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if daemon_running(paths):
            return True
        time.sleep(0.2)
    return False


def stop_daemon(paths: Paths, *, timeout: float = 20.0) -> str:
    """Останавливает демон: просит завершиться, а не дождавшись — снимает процесс."""
    if not daemon_running(paths):
        (paths.run / STOP_NAME).unlink(missing_ok=True)
        return "демон XGW не запущен"
    paths.run.mkdir(parents=True, exist_ok=True)
    (paths.run / STOP_NAME).write_text("stop\n", encoding="ascii")
    deadline = time.monotonic() + timeout
    while daemon_running(paths) and time.monotonic() < deadline:
        time.sleep(0.2)
    if not daemon_running(paths):
        return "демон XGW остановлен"
    # Блокировку держит именно демон, значит, pid-файл написан им и номер — его.
    pid = _daemon_pid(paths)
    if pid and pid != os.getpid() and pid_alive(pid):
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)  # в Windows это TerminateProcess
        deadline = time.monotonic() + 5.0
        while daemon_running(paths) and time.monotonic() < deadline:
            time.sleep(0.2)
    (paths.run / STOP_NAME).unlink(missing_ok=True)
    if daemon_running(paths):
        raise WinAppError("демон XGW не остановился — завершите pythonw.exe в диспетчере задач")
    return "демон XGW не отвечал на просьбу и был завершён"


def stop_xray(paths: Paths) -> str:
    """Останавливает Xray, запущенный демоном (по pid-файлу)."""
    service = engine.make_service(paths, validate.find_xray(None, paths))
    if not service.is_active():
        service.stop()  # убирает pid-файл, оставшийся от прежнего запуска
        return "Xray не запущен"
    service.stop()
    if service.is_active():
        raise WinAppError("Xray не остановился — завершите xray.exe в диспетчере задач")
    return "Xray остановлен"


def prepare_xray(paths: Paths, logger) -> None:
    """При запуске демона. В Linux Xray после загрузки поднимает systemd; здесь это
    делает сам демон, и сразу: watchdog заметил бы остановленное ядро лишь через
    несколько шагов, а с включённым VPN всё это время программы были бы без интернета.

    Каталог run в Windows переживает перезагрузку (в Linux /run очищается сам): метка
    «ядро изменено через API частично» относится к уже не работающему Xray.
    """
    service = engine.make_service(paths, validate.find_xray(None, paths))
    if service.is_active():
        return
    paths.api_dirty_file.unlink(missing_ok=True)
    if not paths.xray_config_file.exists():
        return  # первый запуск: конфиг соберёт демон, когда появится подписка
    try:
        service.start()
        logger.info("Xray запущен")
    except XrayServiceError as exc:
        logger.error("Xray не запустился: %s — демон попробует снова", exc)


# --- установка и удаление ---------------------------------------------------------


def _load_config(paths: Paths) -> config.Config:
    """Настройки для действий, которым нужен только режим и порт: если config.toml не
    читается, прокси всё равно надо уметь вернуть."""
    try:
        cfg, _warnings = config.load(paths.config_file)
    except config.ConfigError:
        cfg = config.Config()
        cfg.capture.method = "sysproxy"
    return cfg


def install(
    paths: Paths,
    *,
    out: Callable[[str], None] = print,
    start: bool = True,
    with_autostart: bool = True,
    registry: winproxy.Registry | None = None,
    command: list[str] | None = None,
) -> int:
    """Первый запуск после установки (и после обновления): конфиг, токен панели,
    автозапуск, демон. Уже существующие настройки и подписки не трогает."""
    logger = log.get_logger("winsetup")
    paths.ensure()
    if not paths.config_file.exists():
        atomic_write_text(paths.config_file, CONFIG_TEMPLATE, mode=0o600)
        out(f"Создан {paths.config_file}")
    try:
        cfg, warnings = config.load(paths.config_file)
    except config.ConfigError as exc:
        out(f"ошибка: {exc}")
        return 2
    for warning in warnings:
        logger.warning("%s", warning)
    if not cfg.capture.sysproxy:
        out(
            f"внимание: в {paths.config_file} не задан capture.method = \"sysproxy\" — "
            "кнопка включения VPN в Windows работать не будет"
        )
    token = panel.ensure_token(paths)
    if with_autostart:
        try:
            set_autostart(registry, command)
            out("Автозапуск при входе в Windows включён")
        except winproxy.ProxyError as exc:
            out(f"внимание: автозапуск не включён: {exc}")
    if start:
        try:
            running = start_daemon(paths, command=command)
        except WinAppError as exc:
            out(f"ошибка: {exc}")
            return 1
        if not running:
            out(f"ошибка: демон XGW не запустился — см. журнал {paths.log_file}")
            return 1
        out("XGW запущен")
    if cfg.panel.enabled:
        out(f"Панель управления: {panel.address(cfg)}?token={token}")
    return 0


def uninstall(
    paths: Paths,
    *,
    out: Callable[[str], None] = print,
    purge: bool = False,
    registry: winproxy.Registry | None = None,
) -> int:
    """Перед удалением файлов: остановить демон и Xray, вернуть системный прокси,
    убрать автозапуск. Каждый шаг выполняется независимо от остальных."""
    failed = False
    for step in (lambda: stop_daemon(paths), lambda: stop_xray(paths)):
        try:
            out(step())
        except (WinAppError, OSError) as exc:
            out(f"ошибка: {exc}")
            failed = True
    try:
        # Именно системный прокси, что бы ни стояло в config.toml: возвращается то,
        # что XGW записал в настройки пользователя.
        WinCapture(_load_config(paths), paths).down()
        out("системный прокси возвращён к настройкам до XGW")
    except (CaptureError, OSError) as exc:
        out(f"ошибка: системный прокси не возвращён: {exc} — проверьте его в «Параметры → "
            "Сеть и Интернет → Прокси-сервер»")
        failed = True
    try:
        remove_autostart(registry)
        out("автозапуск убран")
    except winproxy.ProxyError as exc:
        out(f"ошибка: автозапуск не убран: {exc}")
        failed = True
    if purge and not failed:
        for directory in (paths.etc, paths.var, paths.run):
            try:
                shutil.rmtree(directory)
            except FileNotFoundError:
                pass
            except OSError as exc:
                out(f"ошибка: {directory} не удалён: {exc}")
                failed = True
        if not failed:
            out("настройки, подписки и журналы удалены")
    return 1 if failed else 0
