"""Логирование в stderr (journald подхватывает само). Каждое сообщение
проходит через masking.mask_text — секреты не попадают в журнал."""

from __future__ import annotations

import logging
import sys

from . import masking

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class MaskingFilter(logging.Filter):
    def __init__(self, secrets: list[str] | None = None) -> None:
        super().__init__()
        self.secrets: list[str] = secrets if secrets is not None else []

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # лог не должен падать даже при битых аргументах
            return True
        record.msg = masking.mask_text(message, self.secrets)
        record.args = ()
        return True


def setup(level: str = "INFO", secrets: list[str] | None = None) -> None:
    root = logging.getLogger("xgw")
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)
    root.addFilter(MaskingFilter(secrets))
    root.setLevel(level.upper())
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"xgw.{name}")
