import hashlib
import json
import runpy
import sys
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


def test_catalog_sections_preserve_order_exclusions_split_positions_and_ip_id(tmp_path):
    source, translation = flowseal.load_catalog(CATALOG)
    cutoff = 0
    for config in source["configurations"]:
        options = {row["profile"]: row["options"] for row in config["all_profiles_in_source_order"]}
        profile = translation["configurations"][config["file"].removesuffix(".bat")]
        assert profile["file"] == config["file"]
        assert list(dict.fromkeys(row["profile"] for row in profile["profiles"])) == list(options)
        for row in profile["profiles"]:
            if "dpi-desync-cutoff" in dict(options[row["profile"]]):
                assert row["status"] == "EXCLUDED_COVERAGE"
                cutoff += 1
        for scope in ("source", "youtube"):
            blocks, included, _, _ = flowseal._profile_plan(profile, scope, tmp_path)
            assert [row["worker_profile"] for row in included] == list(range(1, len(blocks) + 1))
            for row, block in zip(included, blocks, strict=True):
                original = options[row["profile"]]
                for key in ("hostlist-exclude", "hostlist-exclude-domains", "ipset-exclude"):
                    prefix = f"--{key}="
                    assert [arg for arg in block if arg.startswith(prefix)] == [
                        prefix + (str(tmp_path / value.removeprefix("%LISTS%"))
                                  if value.startswith("%LISTS%") else value)
                        for option, value in original if option == key
                    ]
                flags = dict(original)
                assert "dpi-desync-cutoff" not in flags
                stages = [arg.removeprefix("--lua-desync=").split(":")
                          for arg in block if arg.startswith("--lua-desync=")]
                for stage, *params in stages:
                    assert ("ip_id=zero" in params) == (flags.get("ip-id") == "zero")
                    if (stage in {"multisplit", "multidisorder", "fakedsplit"}
                            and "dpi-desync-split-pos" in flags):
                        assert f"pos={flags['dpi-desync-split-pos']}" in params
    assert cutoff == 45


def test_alt9_branch_order_and_tls_auto_literals_are_stable(tmp_path):
    source, translation = flowseal.load_catalog(CATALOG)
    configs = translation["configurations"]
    blocks, included, _, _ = flowseal._profile_plan(configs[flowseal.LIVE_PROFILE], "youtube",
                                                  tmp_path)
    assert [item["profile"] for item in included] == [1, 4, 5, 6, 7]
    first_tls = next(i for i, block in enumerate(blocks) if "--filter-l7=tls" in block)
    assert included[first_tls]["worker_profile"] == 2 and included[first_tls]["kind"] == "G"
    assert "--filter-tcp=443" in blocks[first_tls]

    name = "general (FAKE TLS AUTO)"
    original = next(row for row in source["configurations"] if row["file"] == name + ".bat")
    google = original["all_profiles_in_source_order"][3]
    assert google["profile"] == 4
    assert [value for key, value in google["options"] if key == "dpi-desync-fake-tls"] == [
        "0x00000000", "!",
    ]
    blocks, included, _, _ = flowseal._profile_plan(configs[name], "youtube", tmp_path)
    block = next(block for row, block in zip(included, blocks, strict=True) if row["profile"] == 4)
    assert "--blob=fl_hex_00000000:0x00000000" in block
    assert [arg.split(":", 2)[1] for arg in block if arg.startswith("--lua-desync=fake:")] == [
        "blob=fl_hex_00000000", "blob=fake_default_tls",
    ]
    paired = [(row, block) for row, block in zip(included, blocks, strict=True)
              if row["profile"] == 5]
    assert [row["kind"] for row, _ in paired] == ["H", "H-HTTP"]
    assert "--filter-l7=tls" in paired[0][1]
    assert {"--filter-l7=http", "--payload=http_req"} <= set(paired[1][1])


def _run_generator(monkeypatch, capsys, source, directory, *options):
    script = str(CATALOG / "make_flowseal.py")
    rc = 0
    with monkeypatch.context() as patch:
        patch.setattr(sys, "argv", [script, str(source), str(directory), *options])
        try:
            runpy.run_path(script, run_name="__main__")
        except SystemExit as exc:
            rc = exc.code
    output = capsys.readouterr()
    return rc, output.out, output.err


def test_generator_checks_frozen_files_and_rejects_unverified_bat(tmp_path, monkeypatch, capsys):
    source = CATALOG / "flowseal-youtube-source.json"
    artifacts = ["flowseal-translation.json", "flowseal_lab.py"]
    original = {name: (CATALOG / name).read_bytes() for name in artifacts}
    for name, data in original.items():
        (tmp_path / name).write_bytes(data)
    rc, out, err = _run_generator(monkeypatch, capsys, source, tmp_path, "--check")
    assert rc == 0, err
    assert "FLOWSEAL_CHECK_OK configurations=22 source_bat=0" in out

    bat = tmp_path / "general (ALT).bat"
    bat.write_bytes(b"changed source")
    rc, _, err = _run_generator(monkeypatch, capsys, source, tmp_path,
                                "--check", "--source-tree", str(tmp_path))
    assert rc == 2 and "BAT size or SHA-256 differs" in err
    assert {name: (tmp_path / name).read_bytes() for name in artifacts} == original

    changed = original["flowseal_lab.py"] + b"# changed\n"
    (tmp_path / "flowseal_lab.py").write_bytes(changed)
    rc, _, err = _run_generator(monkeypatch, capsys, source, tmp_path, "--check")
    assert rc == 2 and "flowseal_lab.py: generated content differs" in err
    assert (tmp_path / "flowseal_lab.py").read_bytes() == changed


def test_generator_rejects_cutoff_in_a_translated_section(tmp_path, monkeypatch, capsys):
    source, _ = flowseal.load_catalog(CATALOG)
    config = next(row for row in source["configurations"] if row["file"] == "general.bat")
    config["all_profiles_in_source_order"][3]["options"].append(["dpi-desync-cutoff", "n3"])
    modified = tmp_path / "input.json"
    modified.write_text(json.dumps(source), encoding="utf-8")
    rc, _, err = _run_generator(monkeypatch, capsys, modified, tmp_path)
    assert rc != 0
    assert "UNACCOUNTED OPTIONS" in err and "dpi-desync-cutoff" in err
    assert not (tmp_path / "translation.json").exists()
    assert not (tmp_path / "flowseal_lab.py").exists()


def test_generator_propagates_ip_id_to_an_http_sibling(tmp_path, monkeypatch, capsys):
    source, _ = flowseal.load_catalog(CATALOG)
    config = next(row for row in source["configurations"]
                  if row["file"] == "general (FAKE TLS AUTO).bat")
    config["all_profiles_in_source_order"][4]["options"].append(["ip-id", "zero"])
    modified = tmp_path / "input.json"
    modified.write_text(json.dumps(source), encoding="utf-8")
    rc, _, err = _run_generator(monkeypatch, capsys, modified, tmp_path)
    assert rc == 0, err
    rendered = json.loads((tmp_path / "translation.json").read_bytes())
    profile = rendered["configurations"]["general (FAKE TLS AUTO)"]
    included = [row for row in profile["profiles"] if row["status"] == "INCLUDED"]
    http = next(block for row, block in zip(included, profile["blocks"], strict=True)
                if row["profile"] == 5 and row["kind"] == "H-HTTP")
    assert ":ip_id=zero" in next(arg for arg in http if arg.startswith("--lua-desync=fake:"))


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
    _, _, refs, _ = flowseal._profile_plan(profile, "youtube", assets)
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
    cfg.zapret2.domains = ["domain:googlevideo.com", "domain:youtube.com"]
    cfg.zapret2.flowseal_exclude_domains = ["example.googlevideo.com", "example.googlevideo.com"]
    blocks, _, _, _ = flowseal._profile_plan(profile, "youtube", assets, hosts="youtube.com,googlevideo.com",
                                            exclusions="example.googlevideo.com")
    args = zapret2.arguments(cfg)
    assert args[1] == f"--qnum={cfg.zapret2.queue_num}"
    assert args[5:] == flowseal._arguments(blocks) and "--qnum=42" not in args
    assert args.count("--hostlist-domains=youtube.com,googlevideo.com") == len(blocks)
    assert args.count("--hostlist-exclude-domains=example.googlevideo.com") == len(blocks)
    assert (assets / "list-exclude-user.txt").read_bytes() == b""
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


@pytest.mark.parametrize("bad", ["evilgooglevideo.com", "googlevideo.com.example", "*.googlevideo.com",
                                 "-bad.googlevideo.com", "sub..youtube.com", "a.youtube.com,b.youtube.com"])
def test_alt9_validates_each_local_hostname(bad):
    with pytest.raises(schema.PolicyError, match="flowseal_exclude_domains"):
        schema.validate_patch({"flowseal_exclude_domains": [bad]})


def test_alt9_refuses_an_entirely_excluded_scope_without_changing_legacy_revisions():
    assert schema.migrate({"flowseal_exclude_domains": []}) == schema.migrate({})
    patch = {"strategy": flowseal.LIVE_STRATEGY, "domains": list(flowseal.YOUTUBE_DOMAINS[:2]),
             "flowseal_exclude_domains": ["youtube.com", "googlevideo.com"]}
    assert schema.project(schema.migrate(patch | {"mode": "off"}))["mode"] == "off"
    with pytest.raises(schema.PolicyError, match="nonempty"):
        schema.project(schema.migrate(patch | {"mode": "standalone"}))
