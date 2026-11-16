"""Import a reviewed Flowseal configuration into a private nfqws2 test plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path

from .experiment import digest, private_path

COMMIT = "2401b7a13837139b0265632464ba563dddbf80d8"
LIVE_STRATEGY = "flowseal_alt9"
LIVE_PROFILE = "general (ALT9)"
LIVE_ROOT = Path("/opt/xgw/flowseal") / COMMIT
CATALOG_HASHES = {
    "flowseal-youtube-source.json":
        "3ffe3cf7950c4dfb697ded500fca4df00e7abe7b614ef4512eef832885152eac",
    "flowseal-translation.json":
        "8d7027b1d765da1f32502713b36576993939fa6b9a16c309df838615db4805fb",
}
YOUTUBE = ("youtube.com,googlevideo.com,youtubei.googleapis.com,"
           "youtube-nocookie.com,ytimg.com,ggpht.com")
YOUTUBE_DOMAINS = tuple(f"domain:{name}" for name in YOUTUBE.split(","))
USER_LISTS = {"list-general-user.txt", "list-exclude-user.txt", "ipset-exclude-user.txt"}
POSITIVE = ("--hostlist=", "--hostlist-domains=", "--ipset=")
PLACEHOLDER = "%LISTS%"


def load_catalog(directory: Path) -> tuple[dict, dict]:
    tables = []
    for name, expected in CATALOG_HASHES.items():
        path = directory / name
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError("catalog_path")
        with path.open("rb") as stream:
            raw = stream.read(512 * 1024 + 1)
        if len(raw) > 512 * 1024:
            raise ValueError("catalog_size")
        item = json.loads(raw)
        if digest(item) != expected:
            raise ValueError("catalog_digest")
        tables.append(item)
    return tables[0], tables[1]


def _verified_asset(root: Path, name: str, metadata: dict) -> bytes:
    path = root / name
    # Names are from the checked-in catalog. Reject links and special files even
    # inside the upstream snapshot, so reading stops at the selected directory.
    for parent in path.parents:
        if parent == root:
            break
        if not stat.S_ISDIR(parent.lstat().st_mode):
            raise ValueError("source_path")
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("source_path")
    size = metadata["bytes"]
    with path.open("rb") as stream:
        data = stream.read(size + 1)
    if len(data) != size or hashlib.sha256(data).hexdigest() != metadata["sha256"]:
        raise ValueError("source_digest")
    return data


def valid_live_scope(mode: str, domains: list[str]) -> bool:
    return mode == "off" or (
        mode == "standalone"
        and set(YOUTUBE_DOMAINS[:2]) <= set(domains) <= set(YOUTUBE_DOMAINS)
    )


def _profile_plan(profile: dict, scope: str, assets_dir: Path) -> tuple[list, list, dict, list]:
    blocks, included, sources = [], [], {}
    excluded = [entry for entry in profile["profiles"] if entry["status"] != "INCLUDED"]
    runnable = (entry for entry in profile["profiles"] if entry["status"] == "INCLUDED")
    for entry, block in zip(runnable, profile["blocks"], strict=True):
        if scope == "youtube" and entry["kind"] == "S09":
            excluded.append(entry | {"status": "EXCLUDED_SCOPE", "note": "ipv4_syn_requires_lab"})
            continue
        arguments = []
        if scope == "youtube":
            arguments.append("--hostlist-domains=" + YOUTUBE)
        for arg in block:
            if scope == "youtube" and arg.startswith(POSITIVE):
                continue
            if PLACEHOLDER in arg:
                prefix, filename = arg.split(PLACEHOLDER, 1)
                if prefix.startswith("--blob="):
                    blob = profile["blob_decls"][filename].removeprefix("%BIN%")
                    sources[filename] = "bin/" + blob
                else:
                    sources[filename] = None if filename in USER_LISTS else "lists/" + filename
                arg = prefix + str(assets_dir / filename)
            arguments.append(arg)
        blocks.append(arguments)
        included.append(entry | {"worker_profile": len(blocks)})
    return blocks, included, sources, excluded


def _arguments(blocks: list[list[str]]) -> list[str]:
    arguments = []
    for block in blocks:
        if arguments:
            arguments.append("--new")
        arguments.extend(block)
    return arguments


def live_arguments() -> list[str]:
    """Compile the approved YouTube adaptation from immutable local input."""
    from .preflight import trusted_file

    for name in CATALOG_HASHES:
        path = LIVE_ROOT / name
        if trusted_file(path) != path:
            raise ValueError("flowseal_catalog_path")
    source, translation = load_catalog(LIVE_ROOT)
    assets_dir = LIVE_ROOT / "alt9" / "assets"
    blocks, _, sources, _ = _profile_plan(
        translation["configurations"][LIVE_PROFILE], "youtube", assets_dir,
    )
    empty = {"bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}
    for name, upstream in sources.items():
        path = assets_dir / name
        if trusted_file(path) != path:
            raise ValueError("flowseal_asset_path")
        _verified_asset(assets_dir, name, source["files"][upstream] if upstream else empty)
    return _arguments(blocks)


def prepare(catalog: tuple[dict, dict], root: Path, output: Path, name: str, scope: str) -> dict:
    source, translation = catalog
    if scope not in ("source", "youtube"):
        raise ValueError("scope")
    profile = translation["configurations"].get(name)
    if profile is None:
        raise ValueError("unknown_profile")
    output = output.absolute()
    if os.path.lexists(output):
        raise ValueError("output_exists")
    if any(c in str(output) for c in "\r\n\x00"):
        raise ValueError("output_path")
    blocks, included, sources, excluded = _profile_plan(profile, scope, output / "assets")
    files = source["files"]
    verified = {path: _verified_asset(root, path, files[path]) for path in sorted({
        profile["file"], "service.bat", "LICENSE.txt", *(p for p in sources.values() if p),
    })}
    plan = {
        "schema": 1, "state": "prepared", "apply": False, "playback": "NOT_RUN",
        "source_commit": COMMIT, "profile": name,
        "scope": "FLOWSEAL_LISTS" if scope == "source" else "ADAPTED_YOUTUBE",
        "translation": "ADAPTED_NFQWS2",
        "catalog_sha256": CATALOG_HASHES["flowseal-translation.json"],
        "source_files": {p: files[p]["sha256"] for p in verified},
        "assets": {name: {"source": path, "sha256": hashlib.sha256(
            verified[path] if path else b"").hexdigest()} for name, path in sources.items()},
        "profiles": included, "excluded_profiles": excluded, "notes": profile["notes"],
        "arguments": _arguments(blocks),
    }
    with tempfile.TemporaryDirectory(prefix=".flowseal-", dir=output.parent) as staging:
        dest = Path(staging) / "import"
        assets = dest / "assets"
        dest.mkdir(mode=0o700)
        assets.mkdir(mode=0o700)
        for filename, path in sources.items():
            (assets / filename).write_bytes(verified[path] if path else b"")
            (assets / filename).chmod(0o600)
        (dest / "LICENSE.txt").write_bytes(verified["LICENSE.txt"])
        (dest / "LICENSE.txt").chmod(0o600)
        plan_file = dest / "plan.json"
        rendered = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
        plan_file.write_text(rendered, encoding="utf-8")
        plan_file.chmod(0o600)
        os.rename(dest, output)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-dir", type=Path, required=True)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("list")
    command = actions.add_parser("prepare")
    command.add_argument("--source-dir", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--profile", required=True)
    command.add_argument("--scope", choices=("source", "youtube"), required=True)
    args = parser.parse_args()
    try:
        catalog = load_catalog(args.catalog_dir)
        if args.action == "list":
            result = {"source_commit": COMMIT, "profiles": sorted(catalog[1]["configurations"])}
        else:
            if os.name != "posix":
                raise ValueError("linux_required")
            private_path(args.source_dir, directory=True)
            private_path(args.output.parent, directory=True)
            plan = prepare(catalog, args.source_dir, args.output, args.profile, args.scope)
            result = {key: plan[key] for key in ("state", "apply", "profile", "scope", "playback")}
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, RecursionError):
        print('{"state":"invalid_flowseal_input","apply":false}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
