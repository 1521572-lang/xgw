"""Пути файловой системы XGW, атомарная запись и файловая блокировка.

Корень по умолчанию «/» (реальная система). В тестах и разработке корень
переопределяется переменной окружения XGW_ROOT, чтобы не трогать хост.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


class LockTimeout(Exception):
    """Блокировку держит другой процесс XGW дольше допустимого."""


@dataclass(frozen=True)
class Paths:
    root: Path

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Paths:
        """XGW_ROOT — корень вместо «/» (тесты, стенд)."""
        source = dict(os.environ) if env is None else env
        return cls(root=Path(source.get("XGW_ROOT", "/")))

    @property
    def etc(self) -> Path:
        return self.root / "etc" / "xgw"

    @property
    def var(self) -> Path:
        return self.root / "var" / "lib" / "xgw"

    @property
    def run(self) -> Path:
        return self.root / "run" / "xgw"

    @property
    def opt(self) -> Path:
        return self.root / "opt" / "xgw"

    @property
    def config_file(self) -> Path:
        return self.etc / "config.toml"

    @property
    def xray_config_dir(self) -> Path:
        return self.etc / "xray"

    @property
    def xray_config_file(self) -> Path:
        return self.xray_config_dir / "config.json"

    @property
    def generated_config_file(self) -> Path:
        """Результат `xgw generate`: рядом с применённым конфигом, но не вместо него."""
        return self.xray_config_dir / "config.generated.json"

    @property
    def pending_config_file(self) -> Path:
        """Конфиг, ожидающий окна перезапуска."""
        return self.xray_config_dir / "config.pending.json"

    @property
    def last_good_file(self) -> Path:
        return self.var / "last-good.json"

    @property
    def cache_dir(self) -> Path:
        return self.var / "cache"

    @property
    def backup_dir(self) -> Path:
        return self.var / "backup"

    @property
    def db_file(self) -> Path:
        return self.var / "state.db"

    @property
    def lock_file(self) -> Path:
        return self.run / "apply.lock"

    @property
    def status_file(self) -> Path:
        return self.run / "status.json"

    @property
    def api_dirty_file(self) -> Path:
        """Метка «ядро изменено через API лишь частично» — живёт до перезапуска Xray
        (каталог /run очищается при перезагрузке вместе с состоянием ядра)."""
        return self.run / "api-dirty"

    @property
    def xray_dir(self) -> Path:
        return self.opt / "xray"

    @property
    def xray_bin(self) -> Path:
        return self.xray_dir / "xray"

    # --- второе ядро: sing-box (generator/singbox.py) ----------------------------

    @property
    def singbox_dir(self) -> Path:
        return self.opt / "sing-box"

    @property
    def singbox_bin(self) -> Path:
        return self.singbox_dir / "sing-box"

    @property
    def singbox_config_dir(self) -> Path:
        return self.etc / "sing-box"

    @property
    def singbox_config_file(self) -> Path:
        return self.singbox_config_dir / "config.json"

    @property
    def singbox_pending_file(self) -> Path:
        """Конфиг sing-box, ждущий окна перезапуска: перечитывание рвёт его соединения."""
        return self.singbox_config_dir / "config.pending.json"

    @property
    def singbox_last_good_file(self) -> Path:
        return self.var / "sing-box.last-good.json"

    # --- установка (этап 4) -------------------------------------------------------

    @property
    def lib_dir(self) -> Path:
        """Код XGW: /opt/xgw/lib/xgw."""
        return self.opt / "lib"

    @property
    def launcher(self) -> Path:
        return self.root / "usr" / "local" / "bin" / "xgw"

    @property
    def systemd_dir(self) -> Path:
        return self.root / "etc" / "systemd" / "system"

    @property
    def sysctl_file(self) -> Path:
        return self.root / "etc" / "sysctl.d" / "90-xgw.conf"

    @property
    def journal_file(self) -> Path:
        """Что установка изменила в системе и что было до неё — по нему работает uninstall."""
        return self.backup_dir / "install.json"

    @property
    def status_token_file(self) -> Path:
        """Токен страницы статуса, если он не задан в config.toml."""
        return self.var / "status-token"

    @property
    def panel_token_file(self) -> Path:
        """Токен панели управления."""
        return self.var / "panel-token"

    @property
    def records_dir(self) -> Path:
        """Записи трафика устройств (watch/record.py), 0700."""
        return self.var / "records"

    @property
    def desktop_file(self) -> Path:
        """Ярлык панели в меню приложений (каталог локально установленных программ)."""
        return self.root / "usr" / "local" / "share" / "applications" / "xgw-panel.desktop"

    def ensure(self) -> None:
        for directory in (
            self.etc,
            self.xray_config_dir,
            self.singbox_config_dir,
            self.var,
            self.cache_dir,
            self.backup_dir,
            self.run,
        ):
            directory.mkdir(parents=True, exist_ok=True)


def atomic_write_bytes(path: Path, data: bytes, *, mode: int = 0o640) -> None:
    """Атомарная запись: временный файл рядом, fsync, os.replace, fsync каталога.

    Файл сразу создаётся с нужными правами — содержимое с секретами ни на
    мгновение не оказывается доступным на чтение остальным. Временный файл у каждого
    потока свой: два потока демона, пишущие один файл, иначе писали бы в общий
    временный и могли оставить смесь обеих записей. fsync каталога — чтобы после
    сбоя питания на месте файла не оказалось прежнего содержимого.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), mode)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        with contextlib.suppress(OSError):
            os.chmod(tmp, mode)  # файл мог остаться от прошлого запуска с другими правами
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    _fsync_dir(path.parent)


def _fsync_dir(directory: Path) -> None:
    """Запись о переименовании — на диск; где каталог так не открыть, обходимся без этого."""
    with contextlib.suppress(OSError):
        fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def atomic_write_text(path: Path, text: str, *, mode: int = 0o640) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), mode=mode)


def atomic_write_json(path: Path, payload: object, *, mode: int = 0o640) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n", mode=mode)


def _try_lock(handle) -> None:
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(handle) -> None:
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class InstanceLock:
    """Блокировка на всё время жизни процесса: второй демон рядом не запустится.
    Система снимает её сама, когда процесс завершается — как бы он ни завершился."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    def acquire(self) -> bool:
        """False — блокировку держит другой процесс."""
        if self._handle is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")  # noqa: SIM115 — живёт, пока жив процесс
        try:
            _try_lock(handle)
        except OSError:
            handle.close()
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        with contextlib.suppress(OSError):
            _unlock(self._handle)
        self._handle.close()
        self._handle = None


@contextlib.contextmanager
def file_lock(
    path: Path, *, timeout: float = 60.0, poll: float = 0.1, mode: int = 0o666,
) -> Iterator[None]:
    """Межпроцессная блокировка: применение конфига и вызовы API не пересекаются.
    Потоки одного процесса она тоже разводит: каждый вызов открывает файл заново.
    mode — права файла блокировки, если его ещё нет (минус umask)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, mode)
    with os.fdopen(fd, "a+b") as handle:
        while True:
            try:
                _try_lock(handle)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise LockTimeout(f"блокировка {path} занята дольше {timeout:.0f} с") from exc
                time.sleep(poll)
        try:
            yield
        finally:
            with contextlib.suppress(OSError):
                _unlock(handle)
