"""Управление процессом/службой Xray.

На хосте — systemd-юнит xgw-xray.service (этап 4), на стенде и в интеграционных
тестах — прямой subprocess. Единый интерфейс: start/stop/restart/is_active.
"""

from __future__ import annotations

import subprocess
import time
from abc import ABC, abstractmethod


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
