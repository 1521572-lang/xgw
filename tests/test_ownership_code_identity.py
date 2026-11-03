import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

from xgw.ownership import Refused, Registry
from xgw.ownership_identity import CodeIdentity, canonical
from xgw.ownership_seal import CodeFile, CodeSeal
from xgw.ownership_surface import SURFACES, CodePreflight, SurfaceCatalog, surface_record

BOOT = "11111111-1111-1111-1111-111111111111"


def identity(source="a" * 64):
    return CodeIdentity(source, "b" * 64, "c" * 64)


def registry(path, code=None):
    r = Registry(
        path, boot_id=BOOT, expected_uid=os.getuid(), clock_ns=lambda: 10, code_identity=code
    )
    r.initialize()
    return r


@pytest.mark.parametrize("code", [None, identity()])
def test_constructor_does_no_io(tmp_path, monkeypatch, code):
    def forbidden(*args, **kwargs):
        raise AssertionError("constructor I/O")

    monkeypatch.setattr(os, "open", forbidden)
    Registry(
        tmp_path / "absent",
        boot_id=BOOT,
        expected_uid=os.getuid(),
        clock_ns=forbidden,
        code_identity=code,
    )
    assert not (tmp_path / "absent").exists()


def test_legacy_serialized_shapes_are_unchanged(tmp_path):
    r = registry(tmp_path / "legacy")
    data = json.loads((r.directory / "state.json").read_bytes())
    assert data["schema"] == 1 and set(data) == {
        "schema",
        "registry_id",
        "boot_id",
        "lock_device",
        "lock_inode",
        "revision",
        "generation",
        "serial",
        "epoch",
        "writers",
        "lease",
        "receipts",
    }
    token = r.admit("CORE")
    assert set(token) == {"registry_id", "boot_id", "id", "role"}
    r.complete(token, outcome="COMMITTED", verified=True)
    assert set(r.summary()) == {"writers", "unknown", "generation", "receipts", "phase"}
    lease = r.acquire(run_id="a" * 32, expected_generation=1, duration_ns=100)
    assert set(lease) == {"registry_id", "boot_id", "run_id", "epoch", "generation"}


def test_wrong_code_cannot_complete_and_state_does_not_change(tmp_path):
    r = registry(tmp_path / "v2", identity())
    token = r.admit("CORE")
    before = (r.directory / "state.json").read_bytes()
    peer = Registry(
        r.directory, boot_id=BOOT, expected_uid=os.getuid(), code_identity=identity("d" * 64)
    )
    with pytest.raises(Refused, match="CODE_IDENTITY_MISMATCH"):
        peer.complete(token, outcome="COMMITTED", verified=True)
    assert (r.directory / "state.json").read_bytes() == before
    r.complete(token, outcome="COMMITTED", verified=True)
    assert r.summary()["code_bound"] is True and r.receipt(token)["generation"] == 1


@pytest.mark.parametrize("store_code,peer_code", [(identity(), None), (None, identity())])
def test_no_implicit_schema_upgrade_or_downgrade(tmp_path, store_code, peer_code):
    r = registry(tmp_path / "registry", store_code)
    before = (r.directory / "state.json").read_bytes()
    peer = Registry(r.directory, boot_id=BOOT, expected_uid=os.getuid(), code_identity=peer_code)
    with pytest.raises(Refused, match="STATE_SCHEMA"):
        peer.admit("CORE")
    assert (r.directory / "state.json").read_bytes() == before


def test_recovery_token_is_bound_to_code_identity(tmp_path):
    r = registry(tmp_path / "v2", identity())
    lease = r.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
    with pytest.raises(Refused, match="RECOVERY_TOKEN"):
        r.begin({**lease, "code_identity_sha256": "0" * 64})
    r.begin(lease)
    r.retire(lease, outcome="RESTORED_ON", verified=True)
    assert r.summary()["generation"] == 1
    assert (
        json.loads((r.directory / "state.json").read_bytes())["code_identity"]
        == identity().record()
    )


def seal(root, content=b"public fixture\n"):
    root.mkdir(mode=0o700)
    path = root / "code.py"
    path.write_bytes(content)
    path.chmod(0o600)
    return CodeSeal(
        root,
        expected_uid=os.getuid(),
        expectations=(CodeFile("code.py", hashlib.sha256(content).hexdigest()),),
    )


def test_code_seal_rejects_unlisted_file_and_is_readonly(tmp_path):
    observer = seal(tmp_path / "code")
    assert observer.observe().matched
    original = (observer.root / "code.py").read_bytes()
    (observer.root / "unexpected").write_text("private fixture")
    result = observer.observe()
    assert not result.matched and result.reason == "INVENTORY_MISMATCH"
    assert (observer.root / "code.py").read_bytes() == original


def test_surface_catalog_rejects_same_function_with_changed_code(tmp_path, monkeypatch):
    digest = hashlib.sha256(canonical(surface_record())).hexdigest()
    catalog = SurfaceCatalog(digest)
    assert catalog.observe().matched
    owner, name, _ = SURFACES["engine.apply_all"]
    fn = getattr(owner, name)
    monkeypatch.setattr(
        fn, "__code__", fn.__code__.replace(co_firstlineno=fn.__code__.co_firstlineno + 1)
    )
    assert not catalog.observe().matched


def test_preflight_preserves_independent_partial_observations(tmp_path):
    source, units = seal(tmp_path / "source"), seal(tmp_path / "units")
    digest = hashlib.sha256(canonical(surface_record())).hexdigest()
    catalog = SurfaceCatalog(digest)
    code = CodeIdentity(source.manifest_digest(), units.manifest_digest(), digest)
    preflight = CodePreflight(code, source, units, catalog)
    assert preflight.observe().matched
    (source.root / "code.py").write_bytes(b"changed")
    result = preflight.observe()
    assert not result.matched and result.source_matched is False
    assert result.units_matched is result.surface_matched is True
    assert result.source_checked == 0 and result.surface_checked == 65


@pytest.mark.parametrize(
    "case",
    [
        "R_DIAGNOSTIC__SOURCE",
        "T_RECEIPT__DIGEST",
        "J_SAME",
        "H_CODE",
        "I_PREFIX",
        "I_WRITER_FENCE",
        "BRIDGE_OLD_V2_COMPLETE",
        "BRIDGE_OLD_V1_READ_NEW",
    ],
)
def test_new_helper_representative_contracts(tmp_path, monkeypatch, case):
    stand = Path(__file__).parent / "stand"

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    support = load("ak_narrow_support", stand / "wave3_source_hooks.py")
    helper = load("ak_narrow_helper", stand / "wave3_code_handshake.py")
    names = (
        "ownership",
        "ownership_hooks",
        "ownership_adapters",
        "paths",
        "ownership_identity",
        "ownership_seal",
        "ownership_surface",
        "ownership_diagnostics",
        "ownership_files",
        "ownership_completion",
    )
    modules = {n: importlib.import_module("xgw." + n) for n in names}
    modules["legacy"] = load("ak_narrow_legacy", stand / "wave3_schema1_reference.py")
    monkeypatch.setattr(support, "MODULES", modules)
    monkeypatch.setattr(helper, "M", modules)
    monkeypatch.setattr(helper, "SUPPORT", support)
    monkeypatch.setattr(helper, "DETAILS", dict.fromkeys(helper.DETAIL_KEYS))
    helper.run_case(support.Fixture(tmp_path), case)


def test_new_reader_accepts_full_size_record_and_refuses_ambiguous_keys(tmp_path):
    path = Path(__file__).parent / "stand/wave3_code_handshake.py"
    spec = importlib.util.spec_from_file_location("ak_record_reader", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    record = tmp_path / "snapshot.json"
    value = {"data": "x" * 350000, "nullable": None}
    record.write_text(json.dumps(value))
    record.chmod(0o600)
    assert helper.read_record(record) == value
    record.write_text('{"passed":false,"passed":true}')
    with pytest.raises(ValueError, match=r"^DUPLICATE_RECORD_KEY$"):
        helper.read_record(record)
