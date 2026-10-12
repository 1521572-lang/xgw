"""Сон машины (раздел 6.2): уснувший шлюз оставляет без интернета весь дом.

При disable_sleep = true и заданном lan_if цели сна маскируются; при удалении (и при
повторной установке уже без роутера) снимается маска только с тех, что замаскировал
XGW. В режиме «только эта машина» сон не трогается: оставлять без сети некого.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..config import Config
from . import cmd, lan

TARGETS = ("sleep.target", "suspend.target", "hibernate.target", "hybrid-sleep.target")
# Маска не мешает GNOME пытаться усыпить машину по простою — он лишь получит отказ.
GNOME_HINT = (
    "gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing'"
)


def wanted(cfg: Config) -> bool:
    """Маскировать ли сон: только шлюзу, за которым есть сеть. Без роутера уснувшая
    машина никого без интернета не оставляет, а ноутбук должен засыпать."""
    return cfg.network.disable_sleep and bool(lan.lan_interface(cfg))


def is_masked(target: str, systemd_dir: Path) -> bool:
    """Маска — ссылка /etc/systemd/system/<цель> → /dev/null."""
    link = systemd_dir / target
    try:
        return link.is_symlink() and os.readlink(link) == "/dev/null"
    except OSError:
        return False


def unmasked(systemd_dir: Path) -> list[str]:
    return [target for target in TARGETS if not is_masked(target, systemd_dir)]


def mask(systemd_dir: Path, runner: cmd.Runner = cmd.run) -> list[str]:
    """Маскирует цели сна; возвращает те, что не были замаскированы до нас."""
    targets = unmasked(systemd_dir)
    if targets:
        runner(["systemctl", "mask", *targets], timeout=30.0)
    return targets


def unmask(targets: list[str], runner: cmd.Runner = cmd.run) -> None:
    targets = [target for target in targets if target in TARGETS]
    if targets:
        runner(["systemctl", "unmask", *targets], timeout=30.0)
