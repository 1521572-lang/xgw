"""Сборка установщика XGW для Windows: XGW-Setup-<версия>.exe.

    python packaging/windows/build.py [--python-embed <zip>] [--xray-dir <каталог>]
                                      [--makensis <makensis.exe>] [--out <каталог>]

Что кладётся в установщик (каталог stage, раскладка — как после установки):

    app\\python\\   официальный встраиваемый Python (python-3.x.y-embed-amd64.zip с
                  python.org); его файл ._pth переписывается, чтобы был виден app\\lib
    app\\lib\\xgw\\ код XGW (src/xgw) — только стандартная библиотека, зависимостей нет
    app\\xray\\     официальный Xray-core для Windows: xray.exe, geoip.dat, geosite.dat
    xgw.cmd       команда `xgw` для терминала
    xgw.ico       значок (packaging/windows/make_icon.py)
    licenses\\     лицензии XGW, Python и Xray-core

Сам скрипт ничего не скачивает: Python и Xray берутся из готовых файлов (по умолчанию
— tools/pyembed и tools/xray в корне проекта, оба каталога вне git). Перед упаковкой
собранное дерево проверяется: встроенный Python должен запустить `xgw --version` и
импортировать всё, что нужно XGW, а Xray — быть не ниже минимальной версии.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "src"))

import make_icon  # noqa: E402

from xgw.xraycore import binary  # noqa: E402

XRAY_FILES = ("xray.exe", "geoip.dat", "geosite.dat")
# -I — встроенный Python не смотрит на переменные PYTHON* из окружения пользователя.
LAUNCHER = '@echo off\r\n"%~dp0app\\python\\python.exe" -I -m xgw %*\r\n'
# Что должен уметь встроенный Python: модули с расширениями (.pyd), без которых XGW
# не работает, и сам XGW целиком.
SMOKE = (
    "import ctypes, json, sqlite3, ssl, tomllib, winreg, zipfile, tarfile, logging.handlers;"
    "import xgw.cli, xgw.daemon, xgw.winapp, xgw.windiag, xgw.net.wincapture, xgw.watch.panel;"
    "from xgw.paths import Paths; p = Paths.from_env({});"
    "assert p.windows, p; print(p.root)"
)


class BuildError(Exception):
    pass


def version() -> str:
    text = (REPO / "src" / "xgw" / "__init__.py").read_text(encoding="utf-8")
    found = re.search(r'__version__\s*=\s*"(\d+\.\d+\.\d+)"', text)
    if not found:
        raise BuildError("в src/xgw/__init__.py нет __version__ вида 1.2.3")
    return found.group(1)


def find_makensis(explicit: str | None) -> Path:
    candidates = [explicit] if explicit else [
        shutil.which("makensis"),
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "tauri" / "NSIS" / "makensis.exe"),
        r"C:\Program Files (x86)\NSIS\makensis.exe",
        r"C:\Program Files\NSIS\makensis.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise BuildError("makensis.exe не найден — установите NSIS 3 или укажите --makensis")


def stage_python(embed: Path, target: Path) -> None:
    if not embed.is_file():
        raise BuildError(
            f"нет {embed}: скачайте python-3.x.y-embed-amd64.zip с python.org и укажите "
            "--python-embed"
        )
    target.mkdir(parents=True)
    with zipfile.ZipFile(embed) as archive:
        archive.extractall(target)
    for name in ("python.exe", "pythonw.exe"):
        if not (target / name).is_file():
            raise BuildError(f"в {embed.name} нет {name} — это не встраиваемый Python")
    pth = list(target.glob("python3*._pth"))
    if len(pth) != 1:
        raise BuildError(f"в {embed.name} ожидался один файл python3*._pth, найдено {len(pth)}")
    stdlib = pth[0].with_suffix(".zip").name
    # Только стандартная библиотека и код XGW; переменные PYTHON* и каталоги
    # пользователя с таким файлом не учитываются вовсе.
    pth[0].write_text(f"{stdlib}\n.\n..\\lib\n", encoding="ascii")


def stage_code(target: Path) -> None:
    shutil.copytree(
        REPO / "src" / "xgw", target / "xgw",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def stage_xray(source: Path, target: Path) -> str:
    target.mkdir(parents=True)
    for name in XRAY_FILES:
        if not (source / name).is_file():
            raise BuildError(f"нет {source / name}: нужен распакованный Xray-core для Windows")
        shutil.copy2(source / name, target / name)
    found = binary.installed_version(target / "xray.exe")
    if found is None or found < binary.MIN_VERSION:
        raise BuildError(
            f"{source / 'xray.exe'}: версия {found}, нужна не ниже {binary.min_version_text()}"
        )
    return ".".join(map(str, found))


def stage_licenses(stage: Path, xray_dir: Path) -> None:
    target = stage / "licenses"
    target.mkdir()
    if (REPO / "LICENSE").is_file():
        shutil.copy2(REPO / "LICENSE", target / "XGW-LICENSE.txt")
    shutil.move(str(stage / "app" / "python" / "LICENSE.txt"), target / "Python-LICENSE.txt")
    if (xray_dir / "LICENSE").is_file():
        shutil.copy2(xray_dir / "LICENSE", target / "Xray-core-LICENSE.txt")


def smoke(stage: Path) -> None:
    python = stage / "app" / "python" / "python.exe"
    # Окружение без XGW_ROOT и PYTHONPATH: как у пользователя после установки.
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("XGW_", "PYTHON"))}
    for argv in (["-m", "xgw", "--version"], ["-c", SMOKE]):
        proc = subprocess.run(
            [str(python), *argv], capture_output=True, text=True, timeout=120, env=env,
            cwd=str(stage),
        )
        if proc.returncode != 0:
            raise BuildError(
                f"встроенный Python не выполнил {' '.join(argv[:3])}:\n{proc.stdout}{proc.stderr}"
            )
        print("  проверка:", proc.stdout.strip())
    # Проверка не должна оставить следов в том, что пойдёт в установщик.
    for cache in (stage / "app" / "lib").rglob("__pycache__"):
        shutil.rmtree(cache)


def build(args: argparse.Namespace) -> Path:
    if os.name != "nt":
        raise BuildError("установщик собирается в Windows: нужны makensis и запуск xray.exe")
    makensis = find_makensis(args.makensis)
    out_dir = Path(args.out).resolve()
    stage = out_dir / "stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    print("Готовлю файлы…")
    stage_python(Path(args.python_embed), stage / "app" / "python")
    stage_code(stage / "app" / "lib")
    xray = stage_xray(Path(args.xray_dir), stage / "app" / "xray")
    stage_licenses(stage, Path(args.xray_dir))
    (stage / "xgw.cmd").write_bytes(LAUNCHER.encode("ascii"))
    make_icon.build(stage / "xgw.ico")
    side = out_dir / "side.bmp"  # нужна только самому установщику, в программу не идёт
    make_icon.build_side(side)
    smoke(stage)

    release = version()
    outfile = out_dir / f"XGW-Setup-{release}.exe"
    outfile.unlink(missing_ok=True)
    print(f"Упаковываю (XGW {release}, Xray {xray})…")
    proc = subprocess.run(
        [str(makensis), "/V2", "/INPUTCHARSET", "UTF8", f"/DVERSION={release}",
         f"/DSTAGE={stage}", f"/DSIDE={side}", f"/DOUTFILE={outfile}", str(HERE / "xgw.nsi")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
    )
    if proc.returncode != 0 or not outfile.is_file():
        raise BuildError(f"makensis завершился с ошибкой:\n{proc.stdout}{proc.stderr}")
    digest = hashlib.sha256(outfile.read_bytes()).hexdigest()
    print(f"Готово: {outfile}")
    print(f"  размер {outfile.stat().st_size / 1e6:.1f} МБ, SHA-256 {digest}")
    return outfile


def main() -> int:
    parser = argparse.ArgumentParser(description="Сборка установщика XGW для Windows")
    parser.add_argument(
        "--python-embed",
        default=str(REPO / "tools" / "pyembed" / "python-3.12.10-embed-amd64.zip"),
        help="встраиваемый Python с python.org (zip)",
    )
    parser.add_argument(
        "--xray-dir", default=str(REPO / "tools" / "xray"),
        help="каталог с распакованным Xray-core для Windows",
    )
    parser.add_argument("--makensis", default=None, help="путь к makensis.exe (NSIS 3)")
    parser.add_argument("--out", default=str(REPO / "build" / "windows"), help="куда собирать")
    try:
        build(parser.parse_args())
    except BuildError as exc:
        print(f"ошибка: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
