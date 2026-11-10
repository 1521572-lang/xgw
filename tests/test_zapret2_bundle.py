import hashlib
import json
import platform

import pytest
from test_install import Box

from xgw import zapret2_bundle as bundle
from xgw.config import load


def make_bundle(root):
    root.mkdir(parents=True)
    for name in ("nfqws2", "lua/zapret-lib.lua", "lua/zapret-antidpi.lua", "LICENSE.txt"):
        path = root / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("fixture " + name)
    manifest = {"version": bundle.VERSION, "commit": bundle.COMMIT,
                "machine": platform.machine(), "system": "Linux",
                "files": {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in root.rglob("*") if p.is_file()}}
    (root / "bundle.json").write_text(json.dumps(manifest))
    return root


def test_install_is_idempotent_and_wont_replace_different_bundle(tmp_path):
    source = make_bundle(tmp_path / "source")
    target = bundle.install(source, tmp_path / "opt")
    assert (target / "nfqws2").stat().st_mode & 0o777 == 0o755
    assert (target / "lua/zapret-lib.lua").stat().st_mode & 0o777 == 0o644
    assert bundle.install(source, tmp_path / "opt") == target
    original = (target / "nfqws2").read_bytes()
    (source / "nfqws2").write_text("replacement")
    manifest = json.loads((source / "bundle.json").read_text())
    manifest["files"]["nfqws2"] = hashlib.sha256(b"replacement").hexdigest()
    (source / "bundle.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="другой комплект"):
        bundle.install(source, tmp_path / "opt")
    assert (target / "nfqws2").read_bytes() == original


@pytest.mark.parametrize("failure", ["hash", "extra", "architecture", "symlink", "missing"])
def test_bad_bundle_does_not_create_target(tmp_path, failure):
    source = make_bundle(tmp_path / "source")
    if failure == "hash":
        (source / "nfqws2").write_text("changed")
    elif failure == "extra":
        (source / "extra").write_text("unexpected")
    elif failure == "architecture":
        manifest = json.loads((source / "bundle.json").read_text())
        manifest["machine"] = "wrong"
        (source / "bundle.json").write_text(json.dumps(manifest))
    elif failure == "symlink":
        (source / "extra").symlink_to(source / "nfqws2")
    else:
        (source / "lua/zapret-lib.lua").unlink()
    with pytest.raises(ValueError):
        bundle.install(source, tmp_path / "opt")
    assert not (tmp_path / "opt").exists()


def test_external_parent_is_never_used(tmp_path):
    source = make_bundle(tmp_path / "source")
    (tmp_path / "opt").mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (tmp_path / "opt/zapret2").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="ссылкой"):
        bundle.install(source, tmp_path / "opt")
    assert not list(external.iterdir())


def test_installer_checks_bundle_before_any_system_changes_even_force(tmp_path):
    box = Box(tmp_path / "machine")
    installer = box.installer()
    installer.source_root = tmp_path / "release"
    source = make_bundle(installer.source_root / bundle.RELATIVE)
    (source / "nfqws2").write_text("corrupt")
    assert installer.run(assume_yes=True, force=True) == 1
    assert not box.paths.journal_file.exists()
    assert "повреждён комплект" in box.text()


def test_installer_copies_bundle_and_preserves_config(tmp_path):
    box = Box(tmp_path / "machine")
    installer = box.installer()
    installer.source_root = tmp_path / "release"
    make_bundle(installer.source_root / bundle.RELATIVE)
    before = box.paths.config_file.read_bytes()
    facts = installer.facts()
    assert set(bundle.RUNTIME_PACKAGES) <= set(facts.packages)
    # Проверяем системную часть, без запуска сети/служб nfqws2.
    box.paths.singbox_config_dir.mkdir(parents=True, exist_ok=True)
    installer._system(facts)
    bundle.validate(box.paths.opt / bundle.RELATIVE)
    assert box.paths.config_file.read_bytes() == before
    assert not box.system.commands("systemctl", "start", "xgw-zapret2.service")


def test_explicit_external_paths_survive_config_loading(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[zapret2]\nbinary="/opt/zapret2/nfqws2"\nlua_dir="/opt/zapret2/lua"\n')
    cfg, _ = load(path)
    assert cfg.zapret2.binary == "/opt/zapret2/nfqws2"
    assert cfg.zapret2.lua_dir == "/opt/zapret2/lua"
    path.write_text("")
    cfg, _ = load(path)
    assert cfg.zapret2.binary == "/opt/xgw/zapret2/1.0.7/nfqws2"
