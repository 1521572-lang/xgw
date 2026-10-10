"""Загрузка официального Xray-core с GitHub.

Версия не ниже 25.7.23 (поле httpMethod и дочитывание тела при GET);
SHA-256 сверяется с файлом .dgst того же релиза. Для разработки
минимальную версию можно снять переменной XGW_SKIP_VERSION_MIN=1
(фиксируется в ASSUMPTIONS.md, на целевую машину не переносится).
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .. import fetch

RELEASES_API = "https://api.github.com/repos/XTLS/Xray-core/releases"
MIN_VERSION = (25, 7, 23)

_ASSETS = {
    ("linux", "x86_64"): ("xray-linux-64.zip", "x-ray-linux-64.zip"),
    ("linux", "aarch64"): ("xray-linux-arm64-v8a.zip",),
    ("windows", "x86_64"): ("xray-windows-64.zip", "x-ray-windows-64.zip"),
    ("windows", "aarch64"): ("xray-windows-arm64-v8a.zip",),
}


class BinaryError(Exception):
    pass


@dataclass
class Release:
    tag: str
    assets: dict[str, str]


def parse_version(text: str) -> tuple[int, int, int]:
    clean = text.strip().lstrip("vV")
    numbers: list[int] = []
    for part in clean.split(".")[:3]:
        match = re.match(r"\d+", part)
        if not match:
            raise BinaryError(f"не разобрать версию: {text}")
        numbers.append(int(match.group(0)))
    while len(numbers) < 3:
        numbers.append(0)
    return (numbers[0], numbers[1], numbers[2])


def version_ok(text: str) -> bool:
    try:
        return parse_version(text) >= MIN_VERSION
    except BinaryError:
        return False


def platform_pair() -> tuple[str, str]:
    if sys.platform.startswith("win"):
        goos = "windows"
    elif sys.platform == "darwin":
        goos = "darwin"
    else:
        goos = "linux"
    machine = platform.machine().lower() or "x86_64"
    if machine in ("amd64", "x64"):
        machine = "x86_64"
    return goos, machine


def pick_asset(release: Release, goos: str, machine: str) -> str | None:
    wanted = _ASSETS.get((goos, machine), ())
    lowered = {name.lower(): name for name in release.assets}
    for candidate in wanted:
        if candidate in lowered:
            return lowered[candidate]
    return None


def get_release(version: str = "latest", *, timeout: float = 20.0) -> Release:
    if version in ("", "latest"):
        url = f"{RELEASES_API}/latest"
    else:
        url = f"{RELEASES_API}/tags/v{version.lstrip('vV')}"
    result = fetch.fetch_url(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "xgw-updater"},
        timeout=timeout,
        retries=2,
    )
    if result.status != 200:
        raise BinaryError(f"GitHub API вернул HTTP {result.status}")
    data = json.loads(result.body.decode("utf-8"))
    tag = str(data.get("tag_name") or "")
    assets = {
        str(asset.get("name")): str(asset.get("browser_download_url"))
        for asset in data.get("assets", [])
    }
    if not tag or not assets:
        raise BinaryError("в релизе нет тега или файлов")
    return Release(tag=tag, assets=assets)


def verify_sha256(data: bytes, dgst_text: str) -> bool:
    digest = hashlib.sha256(data).hexdigest()
    return any(token.lower() == digest for token in re.findall(r"[0-9a-fA-F]{64}", dgst_text))


def download_release(
    dest_dir: Path,
    version: str = "latest",
    *,
    mark: int | None = None,
    enforce_min: bool | None = None,
) -> tuple[str, Path]:
    """Скачивает zip + .dgst, проверяет SHA-256, распаковывает в dest_dir.

    Возвращает (тег релиза, путь к бинарнику). Существующие файлы заменяет.
    """
    release = get_release(version)
    if enforce_min is None:
        enforce_min = os.environ.get("XGW_SKIP_VERSION_MIN") != "1"
    if enforce_min and not version_ok(release.tag):
        raise BinaryError(
            f"версия {release.tag} ниже требуемой v{'.'.join(map(str, MIN_VERSION))}"
        )
    goos, machine = platform_pair()
    asset = pick_asset(release, goos, machine)
    if asset is None:
        raise BinaryError(f"для {goos}/{machine} нет подходящего файла в релизе {release.tag}")

    zip_result = fetch.fetch_url(release.assets[asset], mark=mark, timeout=180, retries=2)
    dgst_result = fetch.fetch_url(
        release.assets[asset] + ".dgst", mark=mark, timeout=30, retries=2
    )
    if not verify_sha256(zip_result.body, dgst_result.body.decode("utf-8", "replace")):
        raise BinaryError("SHA-256 архива не совпал с .dgst релиза")

    dest_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="xgw-xray-") as tmp_dir:
        tmp_zip = Path(tmp_dir) / asset
        tmp_zip.write_bytes(zip_result.body)
        with zipfile.ZipFile(tmp_zip) as archive:
            archive.extractall(tmp_dir)
        for item in Path(tmp_dir).iterdir():
            if item.is_file() and item != tmp_zip:
                target = dest_dir / item.name
                shutil.move(str(item), target)
                if target.stem == "xray":
                    target.chmod(
                        target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                    )
    binary = dest_dir / ("xray.exe" if goos == "windows" else "xray")
    if not binary.exists():
        raise BinaryError("в архиве релиза нет бинарника xray")
    return release.tag, binary
