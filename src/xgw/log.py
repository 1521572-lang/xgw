"""Логирование в stderr (journald подхватывает само), а в Windows — ещё и в файл.
Каждая строка проходит через masking.mask_text — секреты не попадают в журнал.

Маскирует форматтер обработчика, а не фильтр логгера: фильтры логгера не
применяются к записям дочерних логгеров (xgw.generate, xgw.apply, …), а
форматтер видит каждую запись целиком, включая текст исключения.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import masking

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
MAX_BYTES = 1_000_000
BACKUPS = 3

# Точные значения секретов (пароли серверов, токены), известные процессу.
_secrets: set[str] = set()


class MaskingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return masking.mask_text(super().format(record), _secrets)


def setup(
    level: str = "INFO", secrets: Iterable[str] | None = None, *, file: Path | None = None
) -> None:
    """file — журнал в файл с ротацией: для демона там, где нет journald (Windows).
    Под pythonw.exe потока stderr нет вовсе, и файл остаётся единственным журналом."""
    add_secrets(secrets or ())
    root = logging.getLogger("xgw")
    if root.handlers:
        return
    handlers: list[logging.Handler] = []
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    problem = ""
    if file is not None:
        try:
            file.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(
                RotatingFileHandler(file, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
            )
        except OSError as exc:
            problem = f"журнал {file} не открыт: {exc}"
    for handler in handlers or [logging.NullHandler()]:
        handler.setFormatter(MaskingFormatter(_FORMAT))
        root.addHandler(handler)
    root.setLevel(level.upper())
    root.propagate = False
    if problem:
        root.error("%s", problem)


def add_secrets(values: Iterable[str]) -> None:
    """Регистрирует секреты, которые регулярками не распознать (короткие пароли)."""
    _secrets.update(value for value in values if value and len(value) >= 4)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"xgw.{name}")
