"""Загрузка официального sing-box с GitHub (SagerNet/sing-box) со сверкой SHA-256.

XGW работает с одной проверенной версией — config.SINGBOX_VERSION (1.14.3): поля конфига,
которые строит generator/singbox.py, проверены именно на ней, а у другой выпуск мог что-то
переименовать. Для linux/amd64 хеш архива зашит в код (PINNED_SHA256) и сверяется независимо от
того, что скажет GitHub; для остальных платформ берётся хеш (`digest`) из ответа API GitHub для
этого же файла. Из архива извлекается только сам бинарник `sing-box`.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import tarfile
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .. import fetch
from ..xraycore.binary import BinaryError, platform_pair

RELEASES_API = "https://api.github.com/repos/SagerNet/sing-box/releases"
PINNED_SHA256 = {
    ("linux", "x86_64"): "e2bdf179c15a3652955dc44867e33ca0965c9c9b91b34267dcc5a5d639a5feee",
}
_ARCH = {("linux", "x86_64"): "amd64", ("linux", "aarch64"): "arm64"}
MAX_BINARY_BYTES = 200 * 1024 * 1024


@dataclass
class Release:
    tag: str
    assets: dict[str, tuple[str, str]]  # имя файла → (адрес, sha256 из API; пусто, если нет)


def parse_version(text: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"\s*v?(\d+)\.(\d+)\.(\d+)\s*", text)
    if not match:
        raise BinaryError(f"не разобрать версию sing-box: {text}")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def asset_name(version: str, goos: str, machine: str) -> str | None:
    arch = _ARCH.get((goos, machine))
    return f"sing-box-{version.lstrip('vV')}-{goos}-{arch}.tar.gz" if arch else None


def get_release(
    version: str,
    *,
    timeout: float = 20.0,
    mark: int | None = None,
    bootstrap: Sequence[str] | None = None,
) -> Release:
    """Релиз этой версии (config.SINGBOX_VERSION); «последнего» нет — см. docstring модуля."""
    if not re.fullmatch(r"[vV]?\d+\.\d+\.\d+", version.strip()):
        raise BinaryError(f"версия sing-box — цифрами, например 1.14.3, а не «{version}»")
    url = f"{RELEASES_API}/tags/v{version.strip().lstrip('vV')}"
    result = fetch.fetch_url(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "xgw-updater"},
        timeout=timeout, retries=1, mark=mark, bootstrap=bootstrap,
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
    assets: dict[str, tuple[str, str]] = {}
    for asset in data.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        digest = str(asset.get("digest") or "")
        sha = digest.partition(":")[2].lower() if digest.startswith("sha256:") else ""
        assets[str(asset.get("name"))] = (str(asset.get("browser_download_url")), sha)
    if not tag or not assets:
        raise BinaryError("в релизе нет тега или файлов")
    return Release(tag=tag, assets=assets)


def expected_sha256(release: Release, name: str, goos: str, machine: str) -> str:
    """Хеш архива, с которым сверяется загрузка: зашитый в код, а для прочих платформ — из API.
    Если зашитый и тот, что сообщает GitHub, расходятся, загрузка отвергается."""
    pinned = PINNED_SHA256.get((goos, machine), "")
    published = release.assets.get(name, ("", ""))[1]
    if pinned and published and pinned != published:
        raise BinaryError(
            "хеш архива на GitHub не совпадает с проверенным XGW — загрузка отвергнута"
        )
    wanted = pinned or published
    if not wanted:
        raise BinaryError(f"для {name} нет ни зашитого хеша, ни хеша в ответе GitHub")
    return wanted


def download_release(
    dest_dir: Path,
    version: str,
    *,
    mark: int | None = None,
    bootstrap: Sequence[str] | None = None,
    release: Release | None = None,
) -> tuple[str, Path]:
    """Скачивает архив, сверяет SHA-256 и кладёт бинарник в dest_dir/sing-box.

    Возвращает (тег релиза, путь к бинарнику). Файл заменяется переименованием в пределах одной
    файловой системы: работающий sing-box при этом не мешает (запись поверх исполняемого файла
    дала бы ETXTBSY)."""
    if release is None:
        release = get_release(version, mark=mark, bootstrap=bootstrap)
    goos, machine = platform_pair()
    name = asset_name(release.tag, goos, machine)
    if name is None or name not in release.assets:
        raise BinaryError(f"для {goos}/{machine} нет подходящего файла в релизе {release.tag}")
    wanted = expected_sha256(release, name, goos, machine)
    result = fetch.fetch_url(
        release.assets[name][0], mark=mark, bootstrap=bootstrap, timeout=300, retries=1,
    )
    if result.status != 200:
        raise BinaryError(f"GitHub не отдал файл релиза (HTTP {result.status})")
    if hashlib.sha256(result.body).hexdigest() != wanted:
        raise BinaryError("SHA-256 архива не совпал с ожидаемым")
    binary_data = _extract_binary(result.body)
    dest_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".xgw-sing-box-", dir=dest_dir)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(binary_data)
        os.chmod(tmp_name, 0o755 | stat.S_IRUSR)
        os.replace(tmp_name, dest_dir / "sing-box")
    except OSError:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return release.tag, dest_dir / "sing-box"


def _extract_binary(archive: bytes) -> bytes:
    """Содержимое файла sing-box из tar.gz. Остальное (библиотеки, лицензия) не извлекается, а
    пути из архива на диск не попадают: читается только один регулярный файл."""
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            for member in tar:
                if member.isfile() and Path(member.name).name == "sing-box":
                    if member.size <= 0 or member.size > MAX_BINARY_BYTES:
                        raise BinaryError("размер бинарника sing-box в архиве неправдоподобен")
                    extracted = tar.extractfile(member)
                    if extracted is None:
                        break
                    return extracted.read()
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise BinaryError(f"архив sing-box не читается: {exc}") from exc
    raise BinaryError("в архиве релиза нет бинарника sing-box")
