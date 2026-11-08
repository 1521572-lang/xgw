"""Управление процессом/службой Xray.

На хосте — systemd-юнит xgw-xray.service (его ставит `xgw install`). Там, где юнита нет (стенд,
интеграционные тесты), — обычный процесс: ProcessXrayService живёт внутри
одного процесса Python, PidfileXrayService виден всем командам XGW через
pid-файл. Единый интерфейс: start/stop/restart/is_active.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path

from .. import log, masking
from ..paths import atomic_write_json
from .api import applied_listen

MAX_LOG_BYTES = 2 * 1024 * 1024


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

    def restart_pending(self) -> bool:
        """Служба упала, и её вот-вот поднимет сам systemd (Restart=always). Без systemd —
        некому."""
        return False


class SystemdXrayService(XrayService):
    """systemctl для юнита xgw-xray.service."""

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

    def restart_pending(self) -> bool:
        """systemd ждёт RestartSec, чтобы поднять упавший Xray сам. `systemctl start` в это
        время только добавил бы запуск к StartLimitBurst (5 за 10 с): при падении сразу после
        старта systemd перестал бы поднимать службу раньше времени (третий аудит 0.2.0)."""
        try:
            proc = subprocess.run(
                ["systemctl", "show", "-p", "SubState", "--value", self.unit],
                capture_output=True, text=True, timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return proc.stdout.strip() == "auto-restart"


class ProcessXrayService(XrayService):
    """Прямой subprocess — стенд и интеграционные тесты."""

    def __init__(self, bin_path, config_path, *, grace: float = 5.0) -> None:
        self.bin_path = str(bin_path)
        self.config_path = str(config_path)
        self.grace = grace
        self._proc: subprocess.Popen | None = None
        self._err = None  # stderr процесса: нужен, чтобы сказать, почему он упал

    def _error_tail(self) -> str:
        if self._err is None:
            return ""
        self._err.seek(0)
        text = self._err.read().decode("utf-8", errors="replace").strip()
        return masking.mask_text(" ".join(text[-300:].split()))

    def start(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        if self._err is not None:
            self._err.close()
        self._err = tempfile.TemporaryFile()  # noqa: SIM115 — живёт, пока жив процесс
        try:
            self._proc = subprocess.Popen(
                [self.bin_path, "run", "-c", self.config_path],
                stdout=subprocess.DEVNULL,
                stderr=self._err,
            )
        except OSError as exc:
            raise XrayServiceError(f"xray не запустился: {exc}") from exc
        # Ловим только мгновенное падение (битый конфиг, занятый порт); готовность
        # API вызывающий код проверяет сам, ждать здесь весь grace незачем.
        deadline = time.monotonic() + min(self.grace, 1.0)
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                tail = self._error_tail()
                raise XrayServiceError(
                    "xray завершился сразу после запуска" + (f": {tail}" if tail else "")
                )
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
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return not _is_zombie(pid)


def _is_zombie(pid: int) -> bool:
    """Процесс завершился, но родитель его ещё не снял: kill(pid, 0) для такого проходит.

    Так выглядит Xray, запущенный демоном и остановленный командой `xgw apply`:
    без этой проверки остановка ждала бы весь grace, считая процесс живым.
    """
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii", errors="replace")
    except OSError:
        return False
    # Состояние идёт сразу за именем в скобках; в самом имени могут быть скобки и пробелы.
    return stat.rpartition(")")[2].split()[:1] == ["Z"]


@dataclass(frozen=True)
class ProcessIdentity:
    """Чем процесс отличается от другого с тем же номером: время запуска и его программа."""

    pid: int
    start_ticks: int
    exe_dev: int
    exe_ino: int


class IdentityUnknown(Exception):
    """Процесс есть, а кто он — /proc не говорит (нет прав, непонятный ответ)."""


def process_identity(pid: int) -> ProcessIdentity | None:
    """Отпечаток живого процесса; None — такого нет или это зомби. Программа сверяется по
    устройству и inode: путь в /proc показал бы и текст, и «(deleted)» после обновления ядра."""
    if pid <= 0:
        return None
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii", errors="replace")
        # За именем в скобках (в нём могут быть скобки и пробелы): поле N — индекс N - 3.
        fields = stat.rpartition(")")[2].split()
        if fields[0] in ("Z", "X"):
            return None
        exe = os.stat(f"/proc/{pid}/exe")
        return ProcessIdentity(pid, int(fields[19]), exe.st_dev, exe.st_ino)
    except (FileNotFoundError, ProcessLookupError):
        return None
    except (OSError, IndexError, ValueError) as exc:
        raise IdentityUnknown(str(exc)) from exc


def send_signal(expected: ProcessIdentity, number: int) -> bool:
    """Сигнал именно этому процессу; False — его уже нет или номер занял другой. pidfd держит
    сам процесс: после проверки номер не может перейти к другому. Без pidfd проверка стоит
    прямо перед kill."""
    descriptor = None
    with contextlib.suppress(AttributeError, OSError):
        descriptor = os.pidfd_open(expected.pid)
    try:
        if process_identity(expected.pid) != expected:
            return False
        if descriptor is not None:
            signal.pidfd_send_signal(descriptor, number)
        else:
            os.kill(expected.pid, number)
    except (OSError, IdentityUnknown):
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return True


class PidfileXrayService(XrayService):
    """Xray как обычный процесс с pid-файлом — там, где нет systemd-юнита.

    `xgw apply` и демон — разные процессы: запущенный одним Xray другой находит
    по pid-файлу. Вывод ядра пишется в файл рядом: без journald иначе не узнать,
    почему оно не поднялось. Рядом с pid-файлом — отпечаток процесса (.identity): номер после
    аварии может достаться чужому процессу, и сигнал ушёл бы ему (п. 347, A-02).
    """

    def __init__(self, bin_path, config_path, pid_file: Path, *, grace: float = 5.0) -> None:
        self.bin_path = str(bin_path)
        self.config_path = str(config_path)
        self.pid_file = Path(pid_file)
        self.log_file = self.pid_file.with_suffix(".log")
        self.identity_file = self.pid_file.with_suffix(".identity")
        self.grace = grace
        self._proc: subprocess.Popen | None = None  # если запускали сами — чтобы не оставить зомби

    def _pid(self) -> int:
        try:
            return int(self.pid_file.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return 0

    def _recorded(self, pid: int) -> ProcessIdentity | None:
        try:
            data = json.loads(self.identity_file.read_text(encoding="ascii"))
            recorded = ProcessIdentity(**data)
        except (OSError, ValueError, TypeError):
            return None
        return recorded if recorded.pid == pid else None

    def _owner(self) -> ProcessIdentity | None:
        """Ядро из pid-файла, подтверждённое отпечатком; None — его нет: процесс завершился или
        номер теперь у другого. IdentityUnknown — выяснить нельзя, и сигнал не посылается."""
        pid = self._pid()
        actual = process_identity(pid)
        if actual is None:
            return None
        recorded = self._recorded(pid)
        if recorded is not None:
            return actual if actual == recorded else None
        # Pid-файл прежней версии, без отпечатка: сверяем хотя бы программу.
        try:
            binary = os.stat(self.bin_path)
        except OSError as exc:
            raise IdentityUnknown(str(exc)) from exc
        same = (actual.exe_dev, actual.exe_ino) == (binary.st_dev, binary.st_ino)
        return actual if same else None

    def _running(self) -> bool:
        pid = self._pid()
        if self._proc is not None and self._proc.poll() is not None:
            # Наш процесс завершён — возможно, другой командой XGW. poll() его снял.
            self._proc = None
        if self._proc is not None and self._proc.pid == pid:
            return True
        return self._owner() is not None

    def is_active(self) -> bool:
        try:
            return self._running()
        except IdentityUnknown:
            return False

    def deliver(self, number: int) -> bool:
        """Сигнал ядру из pid-файла — только подтверждённому."""
        try:
            expected = self._owner()
        except IdentityUnknown:
            return False
        return expected is not None and send_signal(expected, number)

    def _trim_log(self) -> None:
        """Журнал ядра дописывается при каждом запуске: большой уходит в .log.1."""
        try:
            if self.log_file.stat().st_size > MAX_LOG_BYTES:
                os.replace(self.log_file, self.log_file.with_suffix(".log.1"))
        except FileNotFoundError:
            pass
        except OSError as exc:
            # Файл держит ещё не завершившийся Xray: обрежется при следующем запуске.
            log.get_logger("xray").debug("журнал %s не перенесён: %s", self.log_file, exc)

    def start(self) -> None:
        try:
            if self._running():
                return
        except IdentityUnknown as exc:
            raise XrayServiceError(
                f"процесс из {self.pid_file} не удалось проверить ({exc}) — второй экземпляр "
                "не запускаю"
            ) from exc
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        # Каталог сокета API: у службы его создаёт (и убирает при любой остановке) systemd —
        # RuntimeDirectory, здесь — сами. Ядро не работает (is_active выше), а сокет остался —
        # процесс убили без уборки: новый Xray с ним не запустится (address already in use).
        listen = applied_listen(Path(self.config_path))
        if listen.startswith("/"):
            socket_path = Path(listen)
            socket_path.parent.mkdir(parents=True, exist_ok=True)
            if socket_path.is_socket():
                socket_path.unlink(missing_ok=True)
        self._trim_log()
        try:
            with open(self.log_file, "ab") as output:
                self._proc = subprocess.Popen(
                    [self.bin_path, "run", "-c", self.config_path],
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
        except OSError as exc:
            raise XrayServiceError(f"xray не запустился: {exc}") from exc
        # Отпечаток — раньше номера: иначе номер без отпечатка выглядел бы файлом прежней версии.
        with contextlib.suppress(OSError, IdentityUnknown):
            identity = process_identity(self._proc.pid)
            if identity is not None:
                atomic_write_json(self.identity_file, asdict(identity), mode=0o644)
        self.pid_file.write_text(f"{self._proc.pid}\n", encoding="ascii")
        deadline = time.monotonic() + min(self.grace, 1.0)
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise XrayServiceError(
                    f"xray завершился сразу после запуска (см. {self.log_file})"
                )
            time.sleep(0.1)

    def _stop_child(self, child: subprocess.Popen) -> None:
        """Свой процесс — по его Popen: номер занят, пока он не снят, и ошибиться нельзя."""
        child.terminate()
        try:
            child.wait(timeout=self.grace)
        except subprocess.TimeoutExpired:
            child.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                child.wait(timeout=self.grace)

    def _stop_confirmed(self, expected: ProcessIdentity) -> None:
        send_signal(expected, signal.SIGTERM)
        deadline = time.monotonic() + self.grace
        while self.is_active() and time.monotonic() < deadline:
            time.sleep(0.1)
        if self.is_active() and send_signal(expected, signal.SIGKILL):
            time.sleep(0.2)
        # Завершающийся процесс уже без программы в /proc, но ещё не зомби: дождаться и этого.
        settle = time.monotonic() + 1.0
        while pid_alive(expected.pid) and time.monotonic() < settle:
            time.sleep(0.02)

    def stop(self) -> None:
        """Сигнал — только процессу, подтверждённому отпечатком. Номер занят другим (отпечаток
        иной): нашего ядра нет, сигнала нет, а устаревший файл убирается. Выяснить нельзя —
        ошибка, и файл остаётся."""
        pid = self._pid()
        child = self._proc
        if child is not None and child.pid == pid and child.poll() is None:
            self._stop_child(child)
        elif pid:
            try:
                expected = self._owner()
            except IdentityUnknown as exc:
                raise XrayServiceError(
                    f"процесс из {self.pid_file} не удалось проверить ({exc}) — сигнал не послан"
                ) from exc
            if expected is not None:
                self._stop_confirmed(expected)
        if self._proc is not None:
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._proc.wait(timeout=1)
            self._proc = None
        self.pid_file.unlink(missing_ok=True)
        self.identity_file.unlink(missing_ok=True)

    def restart(self) -> None:
        self.stop()
        self.start()
