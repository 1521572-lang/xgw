"""Загрузка официального Xray-core с GitHub и проверка установленной версии.

Версия не ниже 25.7.23 (поле httpMethod и дочитывание тела при GET);
SHA-256 сверяется с файлом .dgst того же релиза.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .. import fetch

RELEASES_API = "https://api.github.com/repos/XTLS/Xray-core/releases"
MIN_VERSION = (25, 7, 23)

_ASSETS = {
    ("linux", "x86_64"): ("xray-linux-64.zip", "x-ray-linux-64.zip"),
    ("linux", "aarch64"): ("xray-linux-arm64-v8a.zip",),
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


def min_version_text() -> str:
    return ".".join(map(str, MIN_VERSION))


def installed_version(
    bin_path: Path | str, *, timeout: float = 15.0
) -> tuple[int, int, int] | None:
    """Версия установленного бинарника по `xray version`; None — узнать не удалось.

    Нужна до любой проверки конфига: Xray старше 25.7.23 не знает поля
    httpMethod, молча его игнорирует и проверяет серверы HEAD-запросом —
    `xray run -test` при этом проходит, а «заморозку» шлюз перестаёт видеть.
    """
    try:
        proc = subprocess.run(
            [str(bin_path), "version"], capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"\bXray\s+v?(\d+\.\d+(?:\.\d+)?)", proc.stdout or "")
    if not match:
        return None
    try:
        return parse_version(match.group(1))
    except BinaryError:
        return None


def has_string(bin_path: Path | str, needle: bytes, *, chunk: int = 1 << 20) -> bool:
    """Есть ли в бинарнике строка — например, имя поля конфига.

    Xray молча игнорирует незнакомые поля, и `xray run -test` такой конфиг
    принимает; имена полей при этом лежат в бинарнике открытым текстом.
    """
    tail = b""
    try:
        with open(bin_path, "rb") as handle:
            while block := handle.read(chunk):
                window = tail + block
                if needle in window:
                    return True
                # Хвост — на случай, если строка легла на границу двух блоков.
                tail = window[-(len(needle) - 1):] if len(needle) > 1 else b""
    except OSError:
        return False
    return False


def platform_pair() -> tuple[str, str]:
    if sys.platform == "darwin":
        goos = "darwin"
    else:
        goos = "linux"
    machine = platform.machine().lower() or "x86_64"
    if machine in ("amd64", "x64"):
        machine = "x86_64"
    elif machine == "arm64":
        machine = "aarch64"
    return goos, machine


def pick_asset(release: Release, goos: str, machine: str) -> str | None:
    wanted = _ASSETS.get((goos, machine), ())
    lowered = {name.lower(): name for name in release.assets}
    for candidate in wanted:
        if candidate in lowered:
            return lowered[candidate]
    return None


def get_release(
    version: str,
    *,
    timeout: float = 20.0,
    mark: int | None = None,
    bootstrap: Sequence[str] | None = None,
) -> Release:
    """Релиз этой версии (config.XRAY_VERSION). «Последнего» нет: на GitHub это старый
    стабильный выпуск, а XGW работает только с одной версией."""
    if not re.fullmatch(r"[vV]?\d+(\.\d+){0,2}", version.strip()):
        raise BinaryError(f"версия Xray — цифрами, например 26.10.10, а не «{version}»")
    url = f"{RELEASES_API}/tags/v{version.strip().lstrip('vV')}"
    result = fetch.fetch_url(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "xgw-updater"},
        timeout=timeout,
        retries=1,
        mark=mark,
        bootstrap=bootstrap,
    )
    if result.status != 200:
        raise BinaryError(f"GitHub API вернул HTTP {result.status}")
    try:
        data = json.loads(result.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BinaryError("GitHub API вернул не JSON") from exc
    if not isinstance(data, dict):
        raise BinaryError("GitHub API вернул неожиданный ответ")
    tag = str(data.get("tag_name") or "")
    assets = {
        str(asset.get("name")): str(asset.get("browser_download_url"))
        for asset in data.get("assets") or []
        if isinstance(asset, dict)
    }
    if not tag or not assets:
        raise BinaryError("в релизе нет тега или файлов")
    return Release(tag=tag, assets=assets)


def verify_sha256(data: bytes, dgst_text: str) -> bool:
    """Сверяет SHA-256 со строкой «SHA2-256= …» файла .dgst.

    Берётся именно эта строка: в .dgst есть и SHA2-512, а любые 64 hex-символа
    подряд совпали бы и с половиной чужого хеша.
    """
    digest = hashlib.sha256(data).hexdigest()
    declared = re.findall(
        r"(?im)^\s*SHA(?:2-)?256\s*=\s*([0-9a-f]{64})\s*$", dgst_text
    )
    return any(value.lower() == digest for value in declared)


def download_release(
    dest_dir: Path,
    version: str,
    *,
    mark: int | None = None,
    bootstrap: Sequence[str] | None = None,
    enforce_min: bool = True,
    release: Release | None = None,
) -> tuple[str, Path]:
    """Скачивает zip + .dgst, проверяет SHA-256, распаковывает в dest_dir.

    Возвращает (тег релиза, путь к бинарнику). Файлы заменяются переименованием
    в пределах одной файловой системы: работающий xray при этом не мешает
    (запись поверх исполняемого файла дала бы ETXTBSY), а недокачанный
    бинарник на месте рабочего не окажется.
    """
    if release is None:
        release = get_release(version, mark=mark, bootstrap=bootstrap)
    if enforce_min and not version_ok(release.tag):
        raise BinaryError(f"версия {release.tag} ниже требуемой v{min_version_text()}")
    goos, machine = platform_pair()
    asset = pick_asset(release, goos, machine)
    if asset is None:
        raise BinaryError(f"для {goos}/{machine} нет подходящего файла в релизе {release.tag}")
    dgst_url = release.assets.get(asset + ".dgst") or release.assets[asset] + ".dgst"

    zip_result = fetch.fetch_url(
        release.assets[asset], mark=mark, bootstrap=bootstrap, timeout=180, retries=1
    )
    dgst_result = fetch.fetch_url(dgst_url, mark=mark, bootstrap=bootstrap, timeout=30, retries=1)
    if zip_result.status != 200 or dgst_result.status != 200:
        raise BinaryError(
            f"GitHub не отдал файлы релиза (HTTP {zip_result.status}/{dgst_result.status})"
        )
    if not verify_sha256(zip_result.body, dgst_result.body.decode("utf-8", "replace")):
        raise BinaryError("SHA-256 архива не совпал с .dgst релиза")

    dest_dir.mkdir(parents=True, exist_ok=True)
    binary_name = "xray"
    with tempfile.TemporaryDirectory(prefix=".xgw-xray-", dir=dest_dir) as tmp_dir:
        tmp_zip = Path(tmp_dir) / asset
        tmp_zip.write_bytes(zip_result.body)
        with zipfile.ZipFile(tmp_zip) as archive:
            archive.extractall(tmp_dir)
        tmp_zip.unlink()
        files = [item for item in Path(tmp_dir).iterdir() if item.is_file()]
        if not any(item.name == binary_name for item in files):
            raise BinaryError("в архиве релиза нет бинарника xray")
        # Бинарник переносится последним: geo-файлы к этому моменту уже на месте.
        for item in sorted(files, key=lambda item: item.name == binary_name):
            if item.name == binary_name:
                item.chmod(item.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            try:
                os.replace(item, dest_dir / item.name)
            except OSError:
                shutil.move(str(item), dest_dir / item.name)
    return release.tag, dest_dir / binary_name
