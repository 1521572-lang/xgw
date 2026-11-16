import hashlib
import json
from pathlib import Path

import pytest

from xgw import zapret2
from xgw.config import Config
from xgw.desync import flowseal, preflight, schema

CATALOG = Path(__file__).resolve().parents[1] / "docs" / "helpers"


def test_reviewed_profiles_reference_pinned_files_and_keep_http_tls_separate(tmp_path):
    source, translation = flowseal.load_catalog(CATALOG)
    assert len(translation["configurations"]) == 22
    for profile in translation["configurations"].values():
        for scope in ("source", "youtube"):
            blocks, included, assets, _ = flowseal._profile_plan(profile, scope, tmp_path)
            assert all(path in source["files"] for path in assets.values() if path is not None)
            for entry, block in zip(included, blocks, strict=True):
                if entry["kind"].endswith("-HTTP"):
                    assert "--filter-l7=http" in block
                    assert "--payload=http_req" in block
                if "--payload=tls_client_hello" in block:
                    assert "--filter-l7=tls" in block
                if scope == "youtube":
                    assert "--hostlist-domains=" + flowseal.YOUTUBE in block
                    assert not any(arg.startswith(("--hostlist=", "--ipset=")) for arg in block)
                for arg in block:
                    if arg.startswith("--blob=") and ":0x" not in arg:
                        assert ":@" in arg
    alt5 = translation["configurations"]["general (ALT5)"]
    source_blocks, _, _, _ = flowseal._profile_plan(alt5, "source", tmp_path)
    assert any("--filter-l3=ipv4" in block and "--lua-desync=syndata" in block
               for block in source_blocks)
    yt_blocks, _, _, excluded = flowseal._profile_plan(alt5, "youtube", tmp_path)
    assert not any("--lua-desync=syndata" in block for block in yt_blocks)
    assert any(row["kind"] == "S09" and row["status"] == "EXCLUDED_SCOPE" for row in excluded)


def test_import_is_atomic_and_requires_matching_bytes(tmp_path):
    source, translation = flowseal.load_catalog(CATALOG)
    name = "general (ALT)"
    profile = translation["configurations"][name]
    output = tmp_path / "snapshot"
    blocks, _, refs, _ = flowseal._profile_plan(profile, "youtube", output / "assets")
    root = tmp_path / "source"
    files = {}
    source_paths = {profile["file"], "service.bat", "LICENSE.txt"}
    source_paths.update(path for path in refs.values() if path is not None)
    for name_in_source in source_paths:
        path = root / name_in_source
        path.parent.mkdir(parents=True, exist_ok=True)
        content = name_in_source.encode()
        path.write_bytes(content)
        files[name_in_source] = {
            "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
        }
    catalog = (source | {"files": files}, translation)
    broken = root / "lists/list-exclude.txt"
    before = broken.read_bytes()
    broken.write_bytes(b"x" * len(before))
    with pytest.raises(ValueError, match="source_digest"):
        flowseal.prepare(catalog, root, output, name, "youtube")
    assert not output.exists()
    broken.write_bytes(before)

    result = flowseal.prepare(catalog, root, output, name, "youtube")
    assert result["apply"] is False and result["scope"] == "ADAPTED_YOUTUBE"
    assert result["arguments"][:len(blocks[0])] == blocks[0]
    assert result["arguments"].count("--new") == len(blocks) - 1
    assert json.loads((output / "plan.json").read_bytes()) == result
    assert (output / "assets/list-exclude.txt").read_bytes() == before
    assert (output / "assets/list-exclude-user.txt").read_bytes() == b""
    assert not list(output.rglob("*.bat"))
    with pytest.raises(ValueError, match="output_exists"):
        flowseal.prepare(catalog, root, output, name, "youtube")


def test_catalog_does_not_trust_options_from_imported_input(tmp_path):
    for name in flowseal.CATALOG_HASHES:
        (tmp_path / name).write_bytes((CATALOG / name).read_bytes())
    path = tmp_path / "flowseal-translation.json"
    doc = json.loads(path.read_bytes())
    doc["configurations"]["general"]["blocks"][0].append("--qnum=42")
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="catalog_digest"):
        flowseal.load_catalog(tmp_path)


def test_live_uses_verified_assets_and_not_a_stored_command(tmp_path, monkeypatch):
    catalog = flowseal.load_catalog(CATALOG)
    source, translation = catalog
    profile = translation["configurations"][flowseal.LIVE_PROFILE]
    assets = tmp_path / "alt9" / "assets"
    assets.mkdir(parents=True)
    blocks, _, refs, _ = flowseal._profile_plan(profile, "youtube", assets)
    files = {}
    for name, path in refs.items():
        data = path.encode() if path else b""
        (assets / name).write_bytes(data)
        if path:
            files[path] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    (assets.parent / "plan.json").write_text('{"arguments":["--qnum=42"]}', encoding="utf-8")

    monkeypatch.setattr(flowseal, "LIVE_ROOT", tmp_path)
    monkeypatch.setattr(preflight, "trusted_file", lambda path: path)
    pinned = (source | {"files": files}, translation)
    monkeypatch.setattr(flowseal, "load_catalog", lambda _path: pinned)
    cfg = Config()
    cfg.zapret2.mode = "standalone"
    cfg.zapret2.strategy = flowseal.LIVE_STRATEGY
    args = zapret2.arguments(cfg)
    assert args[1] == f"--qnum={cfg.zapret2.queue_num}"
    assert args[5:] == flowseal._arguments(blocks) and "--qnum=42" not in args
    (assets / "list-exclude-user.txt").write_bytes(b"youtube.com")
    with pytest.raises(ValueError, match="source_digest"):
        zapret2.arguments(cfg)


def test_alt9_policy_rejects_selective_extra_domains_and_old_runtime():
    base = {"strategy": flowseal.LIVE_STRATEGY}
    assert schema.project(schema.migrate(base))["mode"] == "off"
    with pytest.raises(schema.PolicyError, match="Flowseal"):
        schema.project(schema.migrate(base), target="freepool")
    incompatible = ({"mode": "selective"},
                    {"mode": "standalone", "domains": ["domain:example.com"]})
    for changes in incompatible:
        with pytest.raises(schema.PolicyError, match="requires Standalone"):
            schema.project(schema.migrate(base | changes))
