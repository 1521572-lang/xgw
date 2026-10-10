"""Запуск внешних программ (nft, ip) с таймаутом и понятной ошибкой.

Модули сети получают функцию запуска параметром: в тестах она подменяется, на
стенде команды выполняются внутри пространства имён шлюза.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence

Runner = Callable[..., str]


class CommandError(Exception):
    """Программа не найдена, не уложилась в таймаут или завершилась с ошибкой."""


def run(argv: Sequence[str], *, input: str | None = None, timeout: float = 15.0) -> str:
    """Выполняет команду и возвращает её stdout; ненулевой код — CommandError."""
    command = " ".join(argv)
    try:
        proc = subprocess.run(
            list(argv), input=input, capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError as exc:
        raise CommandError(f"{argv[0]}: программа не найдена") from exc
    except subprocess.TimeoutExpired as exc:
        raise CommandError(f"{command}: таймаут {timeout:.0f} с") from exc
    except OSError as exc:
        raise CommandError(f"{command}: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip() or f"код {proc.returncode}"
        raise CommandError(f"{command}: {detail}")
    return proc.stdout
