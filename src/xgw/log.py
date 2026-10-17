"""Логирование в stderr (journald подхватывает само).
Каждая строка проходит через masking.mask_text — секреты не попадают в журнал.

Маскирует форматтер обработчика, а не фильтр логгера: фильтры логгера не
применяются к записям дочерних логгеров (xgw.generate, xgw.apply, …), а
форматтер видит каждую запись целиком, включая текст исключения.

Уровень записи journald берёт из префикса «<N>» в начале строки (SyslogLevelPrefix=,
по умолчанию включён); строки без него — info (6), и `journalctl -p warning` не нашёл
бы ни одного предупреждения. Поэтому, когда stderr подключён к журналу, каждая строка
записи получает такой префикс (journald его снимает).
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterable
from typing import TextIO

from . import masking

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# Точные значения секретов (пароли серверов, токены), известные процессу.
_secrets: set[str] = set()


def syslog_priority(levelno: int) -> int:
    """Уровень logging → приоритет syslog/journald: 2 crit, 3 err, 4 warning, 6 info, 7 debug."""
    if levelno >= logging.CRITICAL:
        return 2
    if levelno >= logging.ERROR:
        return 3
    if levelno >= logging.WARNING:
        return 4
    if levelno >= logging.INFO:
        return 6
    return 7


def journal_stream(stream: TextIO | None) -> bool:
    """Подключён ли поток к journald. systemd кладёт в JOURNAL_STREAM «устройство:inode»
    потока журнала (systemd.exec(5)); сверка с fstat отличает сам этот поток от
    переменной, унаследованной процессом, чей stderr перенаправлен в другое место."""
    expected = os.environ.get("JOURNAL_STREAM", "")
    if stream is None or ":" not in expected:
        return False
    try:
        info = os.fstat(stream.fileno())
    except (OSError, ValueError):  # io.UnsupportedOperation — подкласс обоих
        return False
    return f"{info.st_dev}:{info.st_ino}" == expected


class MaskingFormatter(logging.Formatter):
    def __init__(self, fmt: str | None = None, *, journal: bool = False) -> None:
        super().__init__(fmt)
        self.journal = journal  # ставить ли префикс уровня journald «<N>»

    def format(self, record: logging.LogRecord) -> str:
        text = masking.mask_text(super().format(record), _secrets)
        if not self.journal:
            return text
        # Префикс — каждой строке: journald делит запись по строкам, и продолжение
        # (текст исключения) без него ушло бы с уровнем info.
        prefix = f"<{syslog_priority(record.levelno)}>"
        return "\n".join(prefix + line for line in text.split("\n"))


def setup(level: str = "INFO", secrets: Iterable[str] | None = None) -> None:
    add_secrets(secrets or ())
    root = logging.getLogger("xgw")
    if root.handlers:
        return
    handler: logging.Handler = (
        logging.StreamHandler(sys.stderr) if sys.stderr is not None else logging.NullHandler()
    )
    handler.setFormatter(MaskingFormatter(_FORMAT, journal=journal_stream(sys.stderr)))
    root.addHandler(handler)
    root.setLevel(level.upper())
    root.propagate = False


def add_secrets(values: Iterable[str]) -> None:
    """Регистрирует секреты, которые регулярками не распознать (короткие пароли)."""
    _secrets.update(value for value in values if value and len(value) >= 4)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"xgw.{name}")
