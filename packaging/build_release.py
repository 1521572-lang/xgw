#!/usr/bin/env python3
"""Собрать Linux-дистрибутив XGW с nfqws2 из закреплённых исходников. Без скачиваний."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from xgw import zapret2_bundle as bundle  # noqa: E402


def run(args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def build(output: Path) -> Path:
    if platform.system() != "Linux":
        raise SystemExit("Сборка требует Linux и системные библиотеки; см. packaging/README.md")
    upstream = ROOT / "third_party/zapret2"
    manifest = json.loads((upstream / "UPSTREAM.json").read_text())
    if manifest["commit"] != bundle.COMMIT or manifest["version"] != bundle.VERSION:
        raise SystemExit("Неожиданная версия upstream")
    actual = {p.relative_to(upstream).as_posix() for p in upstream.rglob("*") if p.is_file()}
    if actual != set(manifest["files"]) | {"UPSTREAM.json", "README.xgw.md"}:
        raise SystemExit("Состав исходников upstream изменён")
    for name, digest in manifest["files"].items():
        if (upstream / name).is_symlink():
            raise SystemExit("Ссылка вместо исходника upstream")
        if hashlib.sha256((upstream / name).read_bytes()).hexdigest() != digest:
            raise SystemExit("Исходник upstream изменён: " + name)
    # Дистрибутив включает исходники: можно пересобрать без обращения к upstream.
    if (ROOT / ".git").exists():
        names = run(["git", "-c", "safe.directory=" + str(ROOT), "-C", str(ROOT),
                     "ls-files", "--cached", "--others",
                     "--exclude-standard", "-z"]).split("\0")
    else:
        names = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()]
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="xgw-release-") as temp:
        workspace = Path(temp)
        workspace.chmod(0o755)
        tree = workspace / "xgw"
        for name in filter(None, names):
            if (Path(name).parts[0] in ("dist", "build", "zapret2")
                    or "__pycache__" in Path(name).parts):
                continue
            source = ROOT / name
            if source.is_symlink() or not source.is_file():
                raise SystemExit("Недопустимый файл дистрибутива: " + name)
            destination = tree / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        build_dir = workspace / "build"
        shutil.copytree(upstream / "nfq2", build_dir)
        subprocess.run(["make", "-C", str(build_dir), "LUA_JIT=0", "LUA_VER=5.4",
                        "LUA_PKG=lua5.4"], check=True)
        dest = tree / bundle.RELATIVE
        (dest / "lua").mkdir(parents=True)
        shutil.copyfile(build_dir / "nfqws2", dest / "nfqws2")
        (dest / "nfqws2").chmod(0o755)
        for name in ("zapret-lib.lua", "zapret-antidpi.lua"):
            shutil.copyfile(upstream / "lua" / name, dest / "lua" / name)
        shutil.copyfile(upstream / "docs/LICENSE.txt", dest / "LICENSE.txt")
        licenses = dest / "licenses"
        licenses.mkdir()
        packages = {}
        for package in (*bundle.RUNTIME_PACKAGES, "libc6"):
            packages[package] = run(["dpkg-query", "-W", "-f=${Version}", package])
            shutil.copyfile(Path("/usr/share/doc") / package / "copyright",
                            licenses / (package + ".copyright"))
        for name in ("GPL-2", "LGPL-2.1", "GPL-3", "LGPL-3"):
            shutil.copyfile(Path("/usr/share/common-licenses") / name, licenses / name)
        version = run([str(dest / "nfqws2"), "--version"])
        # Сборка не требует root/CAP_NET_RAW. Проверка исполнения Lua — отдельным helper.
        subprocess.run([str(dest / "nfqws2"), "--dry-run", "--intercept=0",
                        "--lua-init=@" + str(dest / "lua/zapret-lib.lua"),
                        "--lua-init=@" + str(dest / "lua/zapret-antidpi.lua")], check=True)
        data = {"version": bundle.VERSION, "commit": bundle.COMMIT,
                "machine": platform.machine(), "system": "Linux", "packages": packages,
                "compiler": run(["cc", "--version"]).splitlines()[0],
                "build_system": platform.freedesktop_os_release(), "binary_version": version,
                "files": {p.relative_to(dest).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(dest.rglob("*")) if p.is_file()}}
        (dest / "bundle.json").write_text(json.dumps(data, indent=2) + "\n")
        bundle.validate(dest)
        version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
        archive = output / f"xgw-{version}-linux-{platform.machine()}-zapret2.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(tree, arcname="xgw")
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_suffix(archive.suffix + ".sha256").write_text(
            digest + "  " + archive.name + "\n")
        return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    print(build(args.output.resolve()))
