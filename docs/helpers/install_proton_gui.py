#!/usr/bin/python3
"""Установка только GUI: stage → activate; rollback возвращает один app.py."""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

CODE = "7c20f59023ec39e5c5ce4606767ea915c3b91f64"
RELEASE = Path("/opt/xgw/gui/releases") / CODE
BACKUP = Path("/var/lib/xgw/gui-install") / CODE
MARKER = "# XGW_PROTON_GUI " + CODE


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def trusted(path: Path) -> None:
    require(path.is_absolute(), "absolute path required")
    for node in [*reversed(path.parents), path]:
        require(not node.is_symlink(), f"symlink not allowed: {node}")
        if node.exists():
            info = node.stat()
            require(info.st_uid == 0 and not info.st_mode & 0o022,
                    f"not root-owned or writable by others: {node}")
            require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode),
                    f"not a regular file/directory: {node}")


def atomic(path: Path, data: bytes, mode: int, uid: int = 0, gid: int = 0) -> None:
    trusted(path.parent)
    fd, name = tempfile.mkstemp(prefix=".xgw-gui-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            os.fchown(stream.fileno(), uid, gid)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def app_path(value: str) -> Path:
    path = Path(value)
    require(path.is_absolute() and ".." not in path.parts, "invalid app path")
    # Caller resolves the installed package first; never follow a changing symlink here.
    require(path.is_relative_to("/opt/xgw") and path.parts[-2:] == ("gui", "app.py"),
            "expected installed /opt/xgw/.../gui/app.py")
    trusted(path)
    require(path.is_file(), "installed GUI entry is absent")
    return path


def patch(original: bytes) -> bytes:
    text = original.decode("utf-8")
    require("XGW_PROTON_GUI" not in text, "entry already has a GUI dispatcher")
    tree = ast.parse(text)
    mains = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name == "main"]
    require(len(mains) == 1, "one main() function required")
    guard = mains[0].body[0]
    require(isinstance(guard, ast.If) and ast.unparse(guard.test) ==
            "hasattr(os, 'geteuid') and os.geteuid() == 0", "root guard differs; inspect entry")
    require(isinstance(guard.body[-1], ast.Return) and
            isinstance(guard.body[-1].value, ast.Constant) and guard.body[-1].value.value == 2,
            "root guard must return 2")
    lines = text.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in text else "\n"
    call = ["    " + MARKER, "    os.execv(sys.executable, [",
            f"        sys.executable, '-I', {str(RELEASE / 'vpn_ui/main_xgw.py')!r},",
            "        '--theme', 'light', '--native-titlebar',", "    ])", ""]
    lines.insert(guard.end_lineno, newline.join(call) + newline)
    result = "".join(lines).encode("utf-8")
    compile(result, "installed-gui-app.py", "exec")
    return result


def payload(source: Path) -> dict[str, bytes]:
    require(source.is_dir(), "source checkout is absent")
    cmd = ["git", "-c", f"safe.directory={source}", "-C", str(source)]
    archive = subprocess.run([*cmd, "archive", "--format=tar", CODE, "vpn_ui", "src/xgw"],
                             check=True, capture_output=True).stdout
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for item in tar:
            path = Path(item.name)
            require(not path.is_absolute() and ".." not in path.parts, "unsafe archive path")
            require(path.parts[0] == "vpn_ui" or path.parts[:2] == ("src", "xgw") or
                    (item.isdir() and path.parts == ("src",)),
                    "unexpected archive entry")
            if item.isdir():
                continue
            require(item.isfile(), "links and special archive entries are forbidden")
            with tar.extractfile(item) as stream:
                files[path.as_posix()] = stream.read()
    require("vpn_ui/main_xgw.py" in files and "src/xgw/gui/app.py" in files, "incomplete GUI")
    require("vpn_ui/assets/NOTICE.md" in files, "asset notice absent")
    return files


def manifest(files: dict[str, bytes]) -> bytes:
    return (json.dumps({key: sha(value) for key, value in sorted(files.items())},
                       indent=2) + "\n").encode()


def verify_release(expected: dict) -> None:
    trusted(RELEASE)
    require(RELEASE.is_dir(), "release absent")
    for directory in [*RELEASE.parents, RELEASE]:
        require(directory.stat().st_mode & 0o005 == 0o005,
                f"GUI directory is not readable/traversable by desktop user: {directory}")
    actual = set()
    for path in RELEASE.rglob("*"):
        trusted(path)
        if path.is_dir():
            require(stat.S_IMODE(path.stat().st_mode) == 0o755,
                    f"GUI directory mode differs: {path}")
        else:
            actual.add(path.relative_to(RELEASE).as_posix())
    require(actual == set(expected), "unexpected or missing GUI files; inspect release")
    for name, digest in expected.items():
        path = RELEASE / name
        require(path.is_relative_to(RELEASE) and ".." not in path.parts, "invalid manifest path")
        trusted(path)
        require(path.is_file() and sha(path.read_bytes()) == digest, f"release changed: {name}")
        require(stat.S_IMODE(path.stat().st_mode) == 0o644, f"file mode differs: {name}")


def stage(args) -> None:
    app = app_path(args.app)
    original = app.read_bytes()
    require(sha(original) == args.expected, "installed app SHA differs; take a fresh baseline")
    patched = patch(original)
    files = payload(Path(args.source).resolve())
    sums = manifest(files)
    trusted(RELEASE)
    trusted(BACKUP)
    require(not BACKUP.exists(), f"backup exists: {BACKUP}; inspect/status, do not overwrite")
    RELEASE.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    if RELEASE.exists():
        verify_release(json.loads(sums))
    else:
        staging = Path(tempfile.mkdtemp(prefix=".stage-", dir=RELEASE.parent))
        os.chmod(staging, 0o755)
        for name, data in files.items():
            dest = staging / name
            dest.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            atomic(dest, data, 0o644)
        os.replace(staging, RELEASE)
        verify_release(json.loads(sums))
    BACKUP.mkdir(parents=True, mode=0o700)
    os.chmod(BACKUP, 0o700)
    info = app.stat()
    record = {"code": CODE, "app": str(app), "original": sha(original), "patched": sha(patched),
              "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "gid": info.st_gid,
              "manifest": sha(sums), "release": str(RELEASE)}
    atomic(BACKUP / "original.py", original, 0o600)
    atomic(BACKUP / "patched.py", patched, 0o600)
    atomic(BACKUP / "manifest.json", sums, 0o600)
    atomic(BACKUP / "record.json", (json.dumps(record, indent=2) + "\n").encode(), 0o600)
    print("STAGED", RELEASE, "installed entry unchanged", sep="\n")


def record():
    for name in ("record.json", "original.py", "patched.py", "manifest.json"):
        trusted(BACKUP / name)
    saved = json.loads((BACKUP / "record.json").read_bytes())
    require(saved["code"] == CODE and saved["release"] == str(RELEASE), "wrong deployment record")
    app = app_path(saved["app"])
    original, patched = ((BACKUP / name).read_bytes() for name in ("original.py", "patched.py"))
    sums = (BACKUP / "manifest.json").read_bytes()
    require(sha(original) == saved["original"] and sha(patched) == saved["patched"]
            and sha(sums) == saved["manifest"], "backup hash mismatch")
    return saved, app, original, patched, json.loads(sums)


def switch(activate: bool) -> None:
    saved, app, original, patched, sums = record()
    expected = saved["original"] if activate else saved["patched"]
    target = patched if activate else original
    current = sha(app.read_bytes())
    require(current in (expected, sha(target)), "entry changed by someone else; stop and inspect")
    if activate:
        verify_release(sums)
    if current != sha(target):
        atomic(app, target, saved["mode"], saved["uid"], saved["gid"])
    require(sha(app.read_bytes()) == sha(target), "entry verification failed")
    print("ACTIVE" if activate else "ROLLED_BACK", app)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "activate", "rollback", "status"))
    parser.add_argument("--source")
    parser.add_argument("--app")
    parser.add_argument("--expected", help="SHA-256 of the installed GUI app.py before staging")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("root is needed for GUI files; never run the GUI itself as root")
    os.umask(0o022)
    try:
        if args.action == "stage":
            require(bool(args.source and args.app and args.expected),
                    "stage needs source/app/expected")
            stage(args)
        elif args.action == "status":
            saved, app, _original, _patched, sums = record()
            verify_release(sums)
            current = sha(app.read_bytes())
            state = "ACTIVE" if current == saved["patched"] else (
                "ORIGINAL" if current == saved["original"] else "CHANGED_EXTERNALLY")
            print(state, app, "release=" + CODE)
        else:
            switch(args.action == "activate")
    except (OSError, ValueError, KeyError, SyntaxError, subprocess.SubprocessError) as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
