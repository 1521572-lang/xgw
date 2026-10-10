"""Пути файловой системы XGW, атомарная запись и файловая блокировка.

Корень по умолчанию «/» (реальная система). В тестах и разработке корень
переопределяется переменной окружения XGW_ROOT, чтобы не трогать хост.
"""

from __future__ import annotations

import contextlib
import json
import os
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
    def api_dirty_file(self) -> Path:
        """Метка «ядро изменено через API лишь частично» — живёт до перезапуска Xray
        (каталог /run очищается при перезагрузке вместе с состоянием ядра)."""
        return self.run / "api-dirty"

    @property
    def xray_dir(self) -> Path:
        return self.opt / "xray"

    @property
    def xray_bin(self) -> Path:
        return self.xray_dir / ("xray.exe" if os.name == "nt" else "xray")

    def ensure(self) -> None:
        for directory in (
            self.etc,
            self.xray_config_dir,
            self.var,
            self.cache_dir,
            self.backup_dir,
            self.run,
        ):
            directory.mkdir(parents=True, exist_ok=True)


def atomic_write_bytes(path: Path, data: bytes, *, mode: int = 0o640) -> None:
    """Атомарная запись: временный файл рядом, fsync, os.replace.

    Файл сразу создаётся с нужными правами — содержимое с секретами ни на
    мгновение не оказывается доступным на чтение остальным.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
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


def atomic_write_text(path: Path, text: str, *, mode: int = 0o640) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), mode=mode)


def atomic_write_json(path: Path, payload: object, *, mode: int = 0o640) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n", mode=mode)


if os.name == "nt":  # разработка и юнит-тесты; целевая платформа — Linux
    import msvcrt

    def _try_lock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def file_lock(path: Path, *, timeout: float = 60.0, poll: float = 0.1) -> Iterator[None]:
    """Межпроцессная блокировка: применение конфига и вызовы API не пересекаются."""
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    with open(path, "a+b") as handle:
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
