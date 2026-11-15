"""Check nfqws2 files and Lua before either XGW worker takes the queue."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import stat
from pathlib import Path

from ..net import cmd
from ..zapret2_bundle import COMMIT, VERSION

MANAGED_ROOT = Path("/opt/xgw/zapret2")
# Pinned v1.0.7 inputs from third_party/zapret2/UPSTREAM.json.
LUA_HASHES = {
    "zapret-lib.lua": "6bf528fef1f0fc3c65e189216fc8a06bb873f6e25d1c29d2bfa4695a09b73440",
    "zapret-antidpi.lua": "6d1fa9168e5de1682fef91fd174f68b58c50f6739ef00f42ca7db2b940b6246d",
}
_VERSION = re.compile(r"^github version v?([^ ]+) \(([a-f0-9]{7,40})\) lua_compat_ver \d+$",
                      re.MULTILINE)


def trusted_file(name: Path) -> Path:
    # Use the checked absolute path in argv, including for CLI preflight. An alias in
    # an untrusted directory must never remain in the command after it is resolved.
    path = name.resolve(strict=True)
    for parent in reversed(path.parents):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("unsafe_directory")
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022
            or info.st_size > 64 * 1024 * 1024):
        raise ValueError("unsafe_files")
    return path


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _managed(name: Path, path: Path) -> bool:
    return name.is_relative_to(MANAGED_ROOT) or path.is_relative_to(MANAGED_ROOT)


def _verify_managed_binary(path: Path, runner: cmd.Runner) -> None:
    if path != MANAGED_ROOT / VERSION / "nfqws2":
        raise ValueError("bundle_mismatch")
    manifest = path.with_name("bundle.json")
    try:
        manifest.lstat()
    except FileNotFoundError:
        # A manually installed upstream binary has no XGW build manifest.
        try:
            text = runner([str(path), "--version"], timeout=5)
        except cmd.CommandError:
            raise ValueError("bundle_mismatch") from None
        match = _VERSION.search(text)
        if not match or match[1] != VERSION or not COMMIT.startswith(match[2]):
            raise ValueError("bundle_mismatch") from None
        return
    try:
        with trusted_file(manifest).open(encoding="utf-8") as stream:
            data = json.loads(stream.read(65536))
        if (data["version"] != VERSION or data["commit"] != COMMIT or data["system"] != "Linux"
                or data["machine"] != platform.machine()
                or data["files"]["nfqws2"] != _digest(path)):
            raise ValueError
    except (OSError, ValueError, TypeError, KeyError):
        raise ValueError("bundle_mismatch") from None


def prepare(args: list[str], runner: cmd.Runner) -> list[str]:
    """Return the exact checked argv. args comes from XGW's profile builder."""
    name = Path(args[0])
    binary = trusted_file(name)
    prepared = [str(binary)]
    for arg in args[1:]:
        if arg.startswith("--lua-init=@"):
            prefix, file = "--lua-init=@", arg.removeprefix("--lua-init=@")
        elif arg.startswith("--blob=") and ":@" in arg:
            key, file = arg.split(":@", 1)
            prefix = key + ":@"
        else:
            prepared.append(arg)
            continue
        source = Path(file)
        path = trusted_file(source)
        if prefix == "--lua-init=@" and _managed(source, path):
            expected = LUA_HASHES.get(source.name)
            if (not expected or path != MANAGED_ROOT / VERSION / "lua" / source.name
                    or _digest(path) != expected):
                raise ValueError("bundle_mismatch")
        prepared.append(prefix + str(path))
    if _managed(name, binary):
        _verify_managed_binary(binary, runner)
    return prepared


def check(args: list[str], runner: cmd.Runner) -> list[str]:
    prepared = prepare(args, runner)
    stages = (("--dry-run", "bad_worker_options"), ("--intercept=0", "lua_init_failed"))
    for option, reason in stages:
        try:
            runner([*prepared, option], timeout=10)
        except cmd.CommandError:
            raise ValueError(reason) from None
    return prepared
