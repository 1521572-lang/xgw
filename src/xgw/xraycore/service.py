"""Управление процессом/службой Xray.

На хосте — systemd-юнит xgw-xray.service (этап 4). Там, где юнита нет (стенд,
интеграционные тесты), — обычный процесс: ProcessXrayService живёт внутри
одного процесса Python, PidfileXrayService виден всем командам XGW через
pid-файл. Единый интерфейс: start/stop/restart/is_active.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path


class XrayServiceError(Exception):
    pass


class XrayService(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def restart(self) -> None: ...

    @abstractmethod
    def is_active(self) -> bool: ...


class SystemdXrayService(XrayService):
    """systemctl для юнита xgw-xray.service (устанавливается на этапе 4)."""

    def __init__(self, unit: str = "xgw-xray.service") -> None:
        self.unit = unit

    def _systemctl(self, *args: str) -> str:
        command = " ".join(args)
        try:
            proc = subprocess.run(
                ["systemctl", *args, self.unit], capture_output=True, text=True, timeout=30
            )
        except subprocess.TimeoutExpired as exc:
            raise XrayServiceError(f"systemctl {command}: таймаут 30 с") from exc
        except OSError as exc:
            raise XrayServiceError(f"systemctl {command}: {exc}") from exc
        if proc.returncode != 0:
            raise XrayServiceError(f"systemctl {command}: {proc.stderr.strip()}")
        return proc.stdout.strip()

    def start(self) -> None:
        self._systemctl("start")

    def stop(self) -> None:
        self._systemctl("stop")

    def restart(self) -> None:
        self._systemctl("restart")

    def is_active(self) -> bool:
        try:
            proc = subprocess.run(
                ["systemctl", "is-active", "--quiet", self.unit], timeout=30
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return proc.returncode == 0


class ProcessXrayService(XrayService):
    """Прямой subprocess — стенд и интеграционные тесты."""

    def __init__(self, bin_path, config_path, *, grace: float = 5.0) -> None:
        self.bin_path = str(bin_path)
        self.config_path = str(config_path)
        self.grace = grace
        self._proc: subprocess.Popen | None = None

    def start(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        try:
            self._proc = subprocess.Popen(
                [self.bin_path, "run", "-c", self.config_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise XrayServiceError(f"xray не запустился: {exc}") from exc
        # Ловим только мгновенное падение (битый конфиг, занятый порт); готовность
        # API вызывающий код проверяет сам, ждать здесь весь grace незачем.
        deadline = time.monotonic() + min(self.grace, 1.0)
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise XrayServiceError("xray завершился сразу после запуска")
            time.sleep(0.1)

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=self.grace)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=self.grace)

    def restart(self) -> None:
        self.stop()
        self.start()

    def is_active(self) -> bool:
        return self._proc is not None and self._proc.poll() is None


def pid_alive(pid: int) -> bool:
    """Жив ли процесс с таким pid (не обязательно наш дочерний)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and (
                code.value == 259  # STILL_ACTIVE
            )
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class PidfileXrayService(XrayService):
    """Xray как обычный процесс с pid-файлом — там, где нет systemd-юнита.

    `xgw apply` и демон — разные процессы: запущенный одним Xray другой находит
    по pid-файлу. Вывод ядра пишется в файл рядом: без journald иначе не узнать,
    почему оно не поднялось.
    """

    def __init__(self, bin_path, config_path, pid_file: Path, *, grace: float = 5.0) -> None:
        self.bin_path = str(bin_path)
        self.config_path = str(config_path)
        self.pid_file = Path(pid_file)
        self.log_file = self.pid_file.with_suffix(".log")
        self.grace = grace
        self._proc: subprocess.Popen | None = None  # если запускали сами — чтобы не оставить зомби

    def _pid(self) -> int:
        try:
            return int(self.pid_file.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return 0

    def is_active(self) -> bool:
        pid = self._pid()
        if self._proc is not None and self._proc.pid == pid:
            return self._proc.poll() is None
        return pid_alive(pid)

    def start(self) -> None:
        if self.is_active():
            return
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.log_file, "ab") as log:
                self._proc = subprocess.Popen(
                    [self.bin_path, "run", "-c", self.config_path],
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=os.name != "nt",
                )
        except OSError as exc:
            raise XrayServiceError(f"xray не запустился: {exc}") from exc
        self.pid_file.write_text(f"{self._proc.pid}\n", encoding="ascii")
        deadline = time.monotonic() + min(self.grace, 1.0)
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise XrayServiceError(
                    f"xray завершился сразу после запуска (см. {self.log_file})"
                )
            time.sleep(0.1)

    def stop(self) -> None:
        pid = self._pid()
        if pid and self.is_active():
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGTERM)  # в Windows это TerminateProcess
            deadline = time.monotonic() + self.grace
            while self.is_active() and time.monotonic() < deadline:
                time.sleep(0.1)
            if self.is_active() and os.name != "nt":
                with contextlib.suppress(OSError):
                    os.kill(pid, signal.SIGKILL)
                time.sleep(0.2)
        if self._proc is not None:
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._proc.wait(timeout=1)
            self._proc = None
        self.pid_file.unlink(missing_ok=True)

    def restart(self) -> None:
        self.stop()
        self.start()
