import importlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

STAND = Path(__file__).parent / "stand"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, STAND / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def helper(monkeypatch):
    h = load("al_narrow_helper", "wave3_defaults_closure.py")
    ak = load("al_narrow_ak", "wave3_code_handshake.py")
    modules = {
        n: importlib.import_module("xgw." + n)
        for n in ("ownership_surface", "ownership_seal", "ownership_identity")
    }
    monkeypatch.setattr(ak, "M", modules)
    monkeypatch.setattr(h, "M", modules)
    monkeypatch.setattr(h, "AK", ak)
    monkeypatch.setattr(h, "DETAILS", dict.fromkeys(h.DETAIL_KEYS))
    return h


@pytest.mark.parametrize("name", ["H_DEFAULT", "H_DEFAULT_CODE"])
def test_original_failure_is_helper_wrapper_selection(helper, name):
    helper.AK.DETAILS = {}
    with pytest.raises(TypeError):
        helper.AK.surface_extra(None, name)


@pytest.mark.parametrize(
    "selector,route",
    [
        ("REPAIR_H_DEFAULT", "CATALOG"),
        ("REPAIR_H_DEFAULT", "PREFLIGHT"),
        ("REPAIR_H_DEFAULT_CODE", "CATALOG"),
        ("REPAIR_H_DEFAULT_CODE", "PREFLIGHT"),
        ("POS:LITERAL", "CATALOG"),
        ("POS:REMOVE", "PREFLIGHT"),
        ("KW:REMOVE", "CATALOG"),
        ("KW:OPAQUE", "PREFLIGHT"),
        ("CODE:DRIFT", "PREFLIGHT"),
        ("CELL:DRIFT", "PREFLIGHT"),
    ],
)
def test_repair_and_representative_slot_contracts(helper, tmp_path, selector, route):
    if ":" in selector:
        kind, mode = selector.split(":")
        index = next(i for i, row in enumerate(helper.SLOTS) if row[2] == kind)
        selector = f"SLOT_{index:03d}_{mode}"
    helper.run_case(SimpleNamespace(work=tmp_path), selector + "__" + route)
    details = helper.DETAILS
    assert details["target_resolved"] is details["mutation_entered"] is True
    assert details["mutated_matched"] is False and details["mutated_checked"] == 0
    assert details["restored_matched"] is details["fresh_catalog_matched"] is True
    assert details["restored_checked"] == details["fresh_checked"] == 65
    assert details["target_restored"] is True
    if route == "PREFLIGHT":
        assert details["source_matched"] is details["units_matched"] is True


def test_catalog_uses_complete_bounded_public_chain(helper):
    actual = helper.catalog(helper.M["ownership_surface"])
    assert actual == helper.SLOTS and len(actual) == 306
    assert len(helper.EXPECTED) == len(set(helper.EXPECTED)) == 756
    for surface, parameter in (
        ("engine.apply_all", "force_now"),
        ("actions.apply_network", "runner"),
    ):
        depth, fn = helper.default_target(surface, parameter)
        assert depth == 2 and parameter in fn.__kwdefaults__


def test_chain_cycle_and_excess_depth_are_refused(helper):
    def fn():
        raise AssertionError("must never execute")

    fn.__wrapped__ = fn
    with pytest.raises(ValueError, match=r"^CHAIN_REFUSED$"):
        helper.chain(fn)


def test_mutation_observer_error_restores_before_rethrow(helper, monkeypatch, tmp_path):
    catalog = helper.M["ownership_surface"].SurfaceCatalog
    original = catalog.observe
    calls = 0

    def observe(self):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("fixture error")
        return original(self)

    monkeypatch.setattr(catalog, "observe", observe)
    with pytest.raises(RuntimeError, match=r"^fixture error$"):
        helper.run_case(SimpleNamespace(work=tmp_path), "REPAIR_H_DEFAULT__CATALOG")
    assert helper.DETAILS["target_restored"] is True
    assert helper.DETAILS["restored_matched"] is helper.DETAILS["fresh_catalog_matched"] is True
    assert helper.DETAILS["mutated_matched"] is None


def test_bad_initial_surface_is_global_stop(helper, monkeypatch, tmp_path):
    module = helper.M["ownership_surface"]
    monkeypatch.setattr(
        module.SurfaceCatalog,
        "observe",
        lambda self: module.SurfaceEvidence(False, 0, "SURFACE_REFUSED"),
    )
    with pytest.raises(helper.TargetRestoreStop):
        helper.run_case(SimpleNamespace(work=tmp_path), "REPAIR_H_DEFAULT__CATALOG")
    assert helper.DETAILS["mutation_entered"] is None


def test_large_record_and_duplicate_key_policy(helper, tmp_path):
    path = tmp_path / "record.json"
    value = {"payload": "x" * 650000, "nullable": None}
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    assert helper.read_record(path) == value
    path.write_text('{"passed":false,"passed":true}')
    with pytest.raises(ValueError, match=r"^DUPLICATE_RECORD_KEY$"):
        helper.read_record(path)
