"""`xgw update-xray` — обновление Xray-core с проверкой SHA-256 и `xray run -test`.

Новая версия скачивается в соседний каталог и проверяется рабочим конфигом ещё
до замены; прежняя остаётся рядом, пока новая не поднимется. Если Xray после
замены не отвечает — возвращается прежний бинарник.

Ставит только проверенную версию (config.XRAY_VERSION) — в том числе поверх более
новой, принятой шлюзом после обновления из панели (cores.py): после этого принятая и
прежняя версии забываются.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import time
from collections.abc import Callable

from .. import cores, engine, fetch, log
from ..config import XRAY_VERSION, Config
from ..generator import validate
from ..generator.builder import BALANCER_TAG
from ..paths import Paths, file_lock
from . import binary
from .api import ApiError
from .service import XrayServiceError

WAIT_SECONDS = 15.0


def _version_text(version: tuple[int, int, int] | None) -> str:
    return ".".join(map(str, version)) if version else "не установлен"


def update_xray(
    cfg: Config,
    paths: Paths,
    *,
    out: Callable[[str], None] = print,
    logger=None,
    get_release=None,
    download=None,
    wait: float = WAIT_SECONDS,
) -> int:
    logger = logger or log.get_logger("update")
    get_release = get_release or binary.get_release
    download = download or binary.download_release
    target = paths.xray_dir
    current = binary.installed_version(paths.xray_bin) if paths.xray_bin.exists() else None
    mark = engine.bypass_mark(cfg, logger)
    route = {"mark": mark, "bootstrap": cfg.dns.resolvers if mark is not None else None}
    try:
        release = get_release(XRAY_VERSION, **route)  # другую версию XGW не ставит
        wanted = binary.parse_version(release.tag)
    except (binary.BinaryError, fetch.FetchError) as exc:
        out(f"ошибка: не удалось узнать версию Xray на GitHub: {exc}")
        return 1
    if current == wanted:
        out(f"Xray {_version_text(current)} — уже нужная версия")
        return 0

    staging = target.with_name(target.name + ".new")
    previous = target.with_name(target.name + ".prev")
    shutil.rmtree(staging, ignore_errors=True)
    try:
        tag, new_bin = download(staging, XRAY_VERSION, release=release, **route)
    except (binary.BinaryError, fetch.FetchError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        out(f"ошибка: Xray {release.tag} не загружен: {exc}")
        return 1

    problem = check_new(new_bin, engine.read_json(paths.xray_config_file))
    if problem:
        shutil.rmtree(staging, ignore_errors=True)
        out(f"ошибка: Xray {tag} не подходит — {problem}. Установленная версия не тронута.")
        return 1

    with file_lock(paths.lock_file):
        service = engine.make_service(paths, paths.xray_bin)
        api = engine.make_api(cfg, paths.xray_bin)
        configured = paths.xray_config_file.exists()
        shutil.rmtree(previous, ignore_errors=True)
        try:
            # Работающее ядро продолжает работать на прежнем файле до перезапуска.
            if target.exists():
                os.replace(target, previous)
            os.replace(staging, target)
        except (OSError, XrayServiceError) as exc:
            if not target.exists() and previous.exists():
                os.replace(previous, target)
            shutil.rmtree(staging, ignore_errors=True)
            out(f"ошибка: файлы Xray не заменены ({exc}). Установленная версия не тронута")
            return 1
        with contextlib.suppress(OSError):
            os.chmod(target, 0o755)
        if not configured:
            shutil.rmtree(previous, ignore_errors=True)
            cores.forget(paths, "xray")
            out(f"Xray обновлён: {_version_text(current)} → {tag.lstrip('v')}")
            return 0
        error = restart_and_wait(service, api, wait)
        if error is None:
            shutil.rmtree(previous, ignore_errors=True)
            cores.forget(paths, "xray")
            out(f"Xray обновлён и перезапущен: {_version_text(current)} → {tag.lstrip('v')}")
            return 0
        # Новая версия не поднялась — возвращаем прежнюю.
        logger.error("Xray %s после обновления не поднялся: %s", tag, error)
        if previous.exists():
            shutil.rmtree(staging, ignore_errors=True)
            os.replace(target, staging)
            os.replace(previous, target)
            shutil.rmtree(staging, ignore_errors=True)
            again = restart_and_wait(service, api, wait)
            out(
                f"ошибка: Xray {tag} не поднялся ({error}) — возвращена версия "
                f"{_version_text(current)}"
                + ("" if again is None else f", но и она не отвечает: {again}")
            )
        else:
            out(f"ошибка: Xray {tag} не поднялся: {error}")
        return 1


def check_new(new_bin, applied: dict | None) -> str:
    """Почему новый бинарник нельзя ставить; пусто — можно."""
    version = binary.installed_version(new_bin)
    if version is None:
        return "бинарник не запускается"
    if version < binary.MIN_VERSION:
        return f"версия ниже {binary.min_version_text()}"
    if not binary.has_string(new_bin, b"httpMethod"):
        return "в нём нет поля httpMethod (GET-проверки)"
    if applied is not None:
        verdict, output = validate.validate_config(applied, new_bin)
        if verdict is False:
            return f"рабочий конфиг не проходит xray run -test: {output}"
    return ""


def restart_and_wait(service, api, wait: float) -> str | None:
    try:
        service.restart()
    except XrayServiceError as exc:
        return str(exc)
    deadline = time.monotonic() + wait
    while True:
        try:
            api.balancer_info(BALANCER_TAG)
            return None
        except ApiError as exc:
            if time.monotonic() >= deadline:
                return f"API не отвечает {wait:.0f} с ({exc})"
            time.sleep(0.5)
