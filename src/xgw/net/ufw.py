"""ufw (раздел 6.3): его политика по умолчанию запрещает входящие и форвардинг.

Шлюзу за включённым ufw нужны три вещи:

  * `ufw allow in on <lan>` — DHCP и DNS-запросы устройств к самому шлюзу;
  * `ufw route allow in on <lan> out on <wan>` — форвардинг для устройств в
    обход VPN, ICMP и режима «перехват снят»;
  * строка в /etc/ufw/before.rules для перехваченного трафика. Пакеты, которые
    TPROXY отдаёт Xray, проходят цепочку INPUT с чужим адресом назначения, и
    ufw отбрасывает такие в ufw-not-local — раньше, чем доходит до правил из
    `ufw allow`. Командой ufw это правило не добавить: пользовательские правила
    стоят после ufw-not-local.

Всё это добавляется только с подтверждения и убирается при удалении; других
правил ufw XGW не касается.
"""

from __future__ import annotations

import contextlib
import os
import shutil
from pathlib import Path

from ..paths import atomic_write_text
from . import cmd

MARKER = "# XGW: перехваченный трафик устройств (TPROXY); строку убирает xgw uninstall"
ANCHOR = "-A ufw-before-input -j ufw-not-local"


def before_rules(root: Path) -> Path:
    return root / "etc" / "ufw" / "before.rules"


def active(runner: cmd.Runner = cmd.run) -> bool:
    """Включён ли ufw. Нет программы или прав — считаем, что выключен."""
    try:
        text = runner(["ufw", "status"], timeout=20.0)
    except cmd.CommandError:
        return False
    return text.strip().lower().startswith("status: active")


def wanted(lan_if: str, wan_if: str) -> list[list[str]]:
    """Правила для шлюза: аргументы `ufw` без самой команды."""
    forward = ["route", "allow", "in", "on", lan_if]
    if wan_if:
        forward += ["out", "on", wan_if]
    return [["allow", "in", "on", lan_if], forward]


def add(rules: list[list[str]], runner: cmd.Runner = cmd.run) -> list[list[str]]:
    """Добавляет правила; возвращает те, которых до нас не было."""
    added: list[list[str]] = []
    for rule in rules:
        text = runner(["ufw", *rule], timeout=30.0)
        if "skipping" not in text.lower():
            added.append(rule)
    return added


def _delete_args(rule: list[str]) -> list[str]:
    """`ufw allow …` → `ufw delete allow …`; `ufw route allow …` → `ufw route delete allow …`."""
    if rule[:1] == ["route"]:
        return ["route", "delete", *rule[1:]]
    return ["delete", *rule]


def remove(rules: list[list[str]], runner: cmd.Runner = cmd.run) -> list[str]:
    """Убирает добавленные XGW правила; возвращает предупреждения."""
    warnings: list[str] = []
    for rule in rules:
        try:
            runner(["ufw", *_delete_args(rule)], timeout=30.0)
        except cmd.CommandError as exc:
            warnings.append(f"правило ufw «{' '.join(rule)}» не удалено: {exc}")
    return warnings


# --- перехваченный трафик: строка в before.rules --------------------------------


def tproxy_rule(lan_if: str, mark: int) -> str:
    """Пропустить пакеты с LAN, помеченные правилом перехвата (mark_proxy)."""
    return f"-A ufw-before-input -i {lan_if} -m mark --mark {mark:#x} -j ACCEPT"


def _without_block(lines: list[str]) -> list[str]:
    """Строки before.rules без блока XGW (комментарий-метка и правило за ним)."""
    result: list[str] = []
    skip_rule = False
    for line in lines:
        if line.strip() == MARKER:
            skip_rule = True
            continue
        if skip_rule and line.startswith("-A ufw-before-input ") and "--mark" in line:
            skip_rule = False
            continue
        skip_rule = False
        result.append(line)
    return result


def has_tproxy_rule(path: Path, lan_if: str, mark: int) -> bool:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False
    return MARKER in (line.strip() for line in lines) and tproxy_rule(lan_if, mark) in lines


def add_tproxy_rule(
    path: Path, lan_if: str, mark: int, backup_dir: Path, runner: cmd.Runner = cmd.run
) -> None:
    """Вписывает правило перед переходом в ufw-not-local и перечитывает ufw."""
    try:
        original = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise cmd.CommandError(f"{path} не читается: {exc}") from exc
    lines = _without_block(original.splitlines())
    if ANCHOR not in lines:
        raise cmd.CommandError(
            f"в {path} нет строки «{ANCHOR}» — файл изменён; добавьте перед переходом в "
            f"ufw-not-local правило «{tproxy_rule(lan_if, mark)}» сами и выполните ufw reload"
        )
    backup = backup_dir / "ufw-before.rules"
    if not backup.exists():
        with contextlib.suppress(OSError):
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, backup)
            os.chmod(backup, 0o600)
    position = lines.index(ANCHOR)
    lines[position:position] = [MARKER, tproxy_rule(lan_if, mark)]
    text = "\n".join(lines) + "\n"
    if text != original:
        atomic_write_text(path, text, mode=_mode(path))
    runner(["ufw", "reload"], timeout=60.0)


def remove_tproxy_rule(path: Path, runner: cmd.Runner = cmd.run) -> bool:
    """Убирает блок XGW из before.rules; True — он там был."""
    try:
        original = path.read_text(encoding="utf-8")
    except OSError:
        return False
    lines = original.splitlines()
    kept = _without_block(lines)
    if kept == lines:
        return False
    atomic_write_text(path, "\n".join(kept) + "\n", mode=_mode(path))
    runner(["ufw", "reload"], timeout=60.0, check=False)
    return True


def _mode(path: Path) -> int:
    try:
        return path.stat().st_mode & 0o777
    except OSError:
        return 0o640
