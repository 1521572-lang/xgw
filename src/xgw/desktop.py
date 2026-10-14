"""Рабочий стол Ubuntu: браузер и уведомления в сеансе человека, когда XGW работает
от root, и окно пароля администратора для входа в панель.

Установку запускают через sudo, вход в панель с ярлыка «XGW» — через pkexec: оба
работают от root, без окружения графического сеанса. Браузер же нужно открыть у
того, кто их запустил, и от его имени — поэтому команда уходит в его пользовательский
менеджер systemd (`systemd-run --user --machine=<имя>@`). Графический сеанс GNOME
передаёт этому менеджеру свои переменные (WAYLAND_DISPLAY, DISPLAY); если их там нет,
сеанса нет, и открывать браузер негде.

Пароль администратора спрашивает pkexec — окном самой Ubuntu (агент polkit сеанса).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from . import log
from .net import cmd

PKEXEC_DISMISSED = 126  # окно пароля закрыли (man pkexec)
PKEXEC_REFUSED = 127  # пароль не подошёл либо прав нет
GRAPHICAL_VARS = ("WAYLAND_DISPLAY", "DISPLAY")
PASSWORD_WAIT = 600.0  # сколько ждать, пока человек введёт пароль


class DesktopError(Exception):
    """Открыть браузер или спросить пароль не удалось; текст — для человека."""


@dataclass(frozen=True)
class User:
    name: str
    uid: int


def is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def invoking_user(environ: Mapping[str, str] | None = None) -> User | None:
    """Кто запустил процесс root: pkexec (PKEXEC_UID) или sudo (SUDO_UID). None — сам
    root, неизвестный номер или запуск не через них."""
    environ = os.environ if environ is None else environ
    for key in ("PKEXEC_UID", "SUDO_UID"):
        value = (environ.get(key) or "").strip()
        if not value.isdigit() or int(value) == 0:
            continue
        import pwd  # только в Linux; в Windows этих переменных и не бывает

        try:
            return User(pwd.getpwuid(int(value)).pw_name, int(value))
        except KeyError:
            return None
    return None


def _target(user: User) -> str:
    return f"--machine={user.name}@"


def session_vars(user: User, runner: cmd.Runner = cmd.run) -> dict[str, str]:
    """Окружение пользовательского менеджера systemd; пусто — менеджер не запущен."""
    try:
        text = runner(["systemctl", "--user", _target(user), "show-environment"], timeout=10.0)
    except cmd.CommandError:
        return {}
    found: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            found[key] = value
    return found


def graphical(user: User, runner: cmd.Runner = cmd.run) -> bool:
    """Есть ли у человека графический сеанс, где можно открыть браузер."""
    found = session_vars(user, runner)
    return any(found.get(key) for key in GRAPHICAL_VARS)


def _run_as(user: User, argv: list[str], description: str, runner: cmd.Runner) -> None:
    runner(
        ["systemd-run", "--user", _target(user), "--quiet", "--collect",
         f"--description={description}", "--", *argv],
        timeout=20.0,
    )


def open_url(user: User, url: str, runner: cmd.Runner = cmd.run) -> None:
    """Открывает адрес в браузере человека (xdg-open в его сеансе, от его имени).

    В адресе может быть одноразовый код входа: в текст ошибки адрес не попадает."""
    try:
        _run_as(user, ["xdg-open", url], "XGW: панель управления", runner)
    except cmd.CommandError as exc:
        reason = str(exc).replace(url, "<адрес панели>")
        raise DesktopError(f"браузер пользователя {user.name} не открылся: {reason}") from exc


def notify(user: User | None, text: str, runner: cmd.Runner = cmd.run) -> None:
    """Уведомление на рабочем столе: о сбое ярлыка, у которого нет терминала. От root —
    в сеанс человека, иначе — прямо в свой. Не вышло — не беда: текст уже в stderr."""
    argv = ["notify-send", "--app-name=XGW", "XGW", text]
    try:
        if user is not None and is_root():
            _run_as(user, argv, "XGW: уведомление", runner)
        elif shutil.which("notify-send"):
            runner(argv, timeout=10.0)
    except cmd.CommandError as exc:
        # Текст уже напечатан в stderr; уведомление — только дубль для ярлыка.
        log.get_logger("desktop").debug("уведомление не показано: %s", exc)


def as_admin(
    argv: list[str], *, run: Callable[..., subprocess.CompletedProcess] = subprocess.run
) -> int:
    """Запускает команду от root через pkexec — Ubuntu спрашивает пароль своим окном.
    Возвращает код завершения (PKEXEC_DISMISSED — окно закрыли)."""
    pkexec = shutil.which("pkexec")
    if pkexec is None:
        raise DesktopError(
            "нет программы pkexec (пакет pkexec), которая спрашивает пароль администратора — "
            "откройте панель из терминала: sudo xgw panel"
        )
    try:
        return run([pkexec, *argv], timeout=PASSWORD_WAIT).returncode
    except subprocess.TimeoutExpired as exc:
        raise DesktopError("пароль администратора так и не ввели") from exc
    except OSError as exc:
        raise DesktopError(f"pkexec не запустился: {exc}") from exc
