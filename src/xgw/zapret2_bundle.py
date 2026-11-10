"""Проверка и установка готового nfqws2 из дистрибутива, без загрузок и запуска служб."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import tempfile
from pathlib import Path, PurePosixPath

VERSION = "1.0.7"
COMMIT = "038c97e5819df10f8e8c22a2f1fffe57f2f7379b"
RELATIVE = Path("zapret2") / VERSION
RUNTIME_PACKAGES = ("liblua5.4-0", "libnetfilter-queue1", "libnfnetlink0", "libmnl0", "zlib1g")


def validate(directory: Path) -> dict:
    """Манифест проверяет целостность комплекта; доверие к издателю — доверие дистрибутиву."""
    if directory.is_symlink() or (directory / "bundle.json").is_symlink():
        raise ValueError("zapret2: ссылка вместо комплекта")
    data = json.loads((directory / "bundle.json").read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("version") != VERSION or data.get("commit") != COMMIT
            or data.get("machine") != platform.machine()
            or data.get("system") != "Linux"):
        raise ValueError("zapret2: версия или архитектура комплекта не подходит")
    files = data.get("files", {})
    required = {"nfqws2", "lua/zapret-lib.lua", "lua/zapret-antidpi.lua", "LICENSE.txt"}
    if not isinstance(files, dict) or not required <= files.keys():
        raise ValueError("zapret2: неполный комплект")
    actual = set()
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ValueError("zapret2: ссылки в комплекте запрещены")
        if path.is_file() and path != directory / "bundle.json":
            actual.add(path.relative_to(directory).as_posix())
    if actual != set(files):
        raise ValueError("zapret2: состав комплекта изменён")
    for name, digest in files.items():
        rel = PurePosixPath(name)
        if rel.is_absolute() or ".." in rel.parts or "\\" in name:
            raise ValueError("zapret2: недопустимый путь")
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise ValueError("zapret2: контрольная сумма не совпала")
    return data


def install(source: Path, opt: Path) -> Path:
    """Новая версия ставится атомарно; существующий отличный комплект не перезаписывается."""
    manifest = validate(source)
    target = opt / RELATIVE
    if opt.is_symlink() or target.parent.is_symlink():
        raise ValueError("zapret2: каталог установки является ссылкой")
    if target.exists() or target.is_symlink():
        if validate(target) != manifest:
            raise ValueError("zapret2: установлен другой комплект этой версии")
        return target
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=parent))
    try:
        shutil.copytree(source, stage, dirs_exist_ok=True)
        validate(stage)
        for path in [stage, *stage.rglob("*")]:
            path.chmod(0o755 if path.is_dir() or path.name == "nfqws2" else 0o644)
        os.replace(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return target
