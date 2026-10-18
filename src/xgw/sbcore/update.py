"""`xgw update-singbox` — установка/обновление sing-box до проверенной версии.

По образцу `xgw update-xray`: новая версия скачивается в соседний каталог и проверяется рабочим
конфигом до замены; если после замены sing-box не отвечает — возвращается прежний бинарник.
Версия одна — config.SINGBOX_VERSION: другую XGW не ставит.
"""

from __future__ import annotations

import contextlib
import os
import shutil
from collections.abc import Callable

from .. import engine, fetch, log
from ..apply import singbox as singbox_apply
from ..config import SINGBOX_VERSION, Config
from ..generator import singbox as singboxing
from ..paths import Paths, file_lock
from ..xraycore.binary import BinaryError
from ..xraycore.service import XrayServiceError
from . import binary


def _version_text(version: tuple[int, int, int] | None) -> str:
    return ".".join(map(str, version)) if version else "не установлен"


def update_singbox(
    cfg: Config,
    paths: Paths,
    *,
    out: Callable[[str], None] = print,
    logger=None,
    get_release=None,
    download=None,
) -> int:
    logger = logger or log.get_logger("update")
    get_release = get_release or binary.get_release
    download = download or binary.download_release
    target = paths.singbox_dir
    current = None
    if paths.singbox_bin.exists():
        current = singboxing.installed_version(paths.singbox_bin)
    wanted = binary.parse_version(SINGBOX_VERSION)
    if current == wanted:
        out(f"sing-box {_version_text(current)} — уже нужная версия")
        return 0
    mark = engine.bypass_mark(cfg, logger)
    route = {"mark": mark, "bootstrap": cfg.dns.bootstrap if mark is not None else None}
    try:
        release = get_release(SINGBOX_VERSION, **route)
    except (BinaryError, fetch.FetchError) as exc:
        out(f"ошибка: не удалось узнать версию sing-box на GitHub: {exc}")
        return 1
    staging = target.with_name(target.name + ".new")
    previous = target.with_name(target.name + ".prev")
    shutil.rmtree(staging, ignore_errors=True)
    try:
        tag, new_bin = download(staging, SINGBOX_VERSION, release=release, **route)
    except (BinaryError, fetch.FetchError, OSError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        out(f"ошибка: sing-box {release.tag} не загружен: {exc}")
        return 1
    found = singboxing.installed_version(new_bin)
    if found != wanted:
        shutil.rmtree(staging, ignore_errors=True)
        out(f"ошибка: скачан sing-box {_version_text(found)}, а нужен {SINGBOX_VERSION}. "
            "Установленная версия не тронута.")
        return 1
    applied = engine.read_json(paths.singbox_config_file)
    if applied is not None:
        ok, output = singboxing.validate_config(applied, new_bin)
        if ok is False:
            shutil.rmtree(staging, ignore_errors=True)
            out(f"ошибка: sing-box {tag} не принимает рабочий конфиг: {output}. "
                "Установленная версия не тронута.")
            return 1

    with file_lock(paths.lock_file):
        core = engine.make_singbox(cfg, paths)
        shutil.rmtree(previous, ignore_errors=True)
        try:
            if target.exists():
                os.replace(target, previous)
            os.replace(staging, target)
        except OSError as exc:
            if not target.exists() and previous.exists():
                os.replace(previous, target)
            shutil.rmtree(staging, ignore_errors=True)
            out(f"ошибка: файлы sing-box не заменены ({exc}). Установленная версия не тронута")
            return 1
        with contextlib.suppress(OSError):
            os.chmod(paths.singbox_bin, 0o755)
        if applied is None:
            shutil.rmtree(previous, ignore_errors=True)
            out(f"sing-box установлен: {_version_text(current)} → {tag.lstrip('v')}")
            return 0
        error = _restart(core)
        if error is None:
            shutil.rmtree(previous, ignore_errors=True)
            out(f"sing-box обновлён и перезапущен: {_version_text(current)} → {tag.lstrip('v')}")
            return 0
        logger.error("sing-box %s после обновления не поднялся: %s", tag, error)
        if previous.exists():
            shutil.rmtree(staging, ignore_errors=True)
            os.replace(target, staging)
            os.replace(previous, target)
            shutil.rmtree(staging, ignore_errors=True)
            again = _restart(core)
            out(
                f"ошибка: sing-box {tag} не поднялся ({error}) — возвращена версия "
                f"{_version_text(current)}"
                + ("" if again is None else f", но и она не отвечает: {again}")
            )
        else:
            out(f"ошибка: sing-box {tag} не поднялся: {error}")
        return 1


def _restart(core: singbox_apply.SingboxCore) -> str | None:
    try:
        error = core.restart()
    except XrayServiceError as exc:
        return str(exc)
    if error is not None:
        return error
    return None if core.alive() else "sing-box не отвечает на Clash API"
