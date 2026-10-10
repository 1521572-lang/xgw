"""Логирование в stderr (journald подхватывает само). Каждая строка проходит
через masking.mask_text — секреты не попадают в журнал.

Маскирует форматтер обработчика, а не фильтр логгера: фильтры логгера не
применяются к записям дочерних логгеров (xgw.generate, xgw.apply, …), а
форматтер видит каждую запись целиком, включая текст исключения.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable

from . import masking

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# Точные значения секретов (пароли серверов, токены), известные процессу.
_secrets: set[str] = set()


class MaskingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return masking.mask_text(super().format(record), _secrets)


def setup(level: str = "INFO", secrets: Iterable[str] | None = None) -> None:
    add_secrets(secrets or ())
    root = logging.getLogger("xgw")
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(MaskingFormatter(_FORMAT))
    root.addHandler(handler)
    root.setLevel(level.upper())
    root.propagate = False


def add_secrets(values: Iterable[str]) -> None:
    """Регистрирует секреты, которые регулярками не распознать (короткие пароли)."""
    _secrets.update(value for value in values if value and len(value) >= 4)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"xgw.{name}")
