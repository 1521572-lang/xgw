import importlib
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def helper(monkeypatch):
    stand = Path(__file__).parent / "stand"

    def load(name, filename):
        spec = importlib.util.spec_from_file_location(name, stand / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    h = load("am_narrow_helper", "wave3_bound_composition.py")
    ak = load("am_narrow_ak", "wave3_code_handshake.py")
    names = (
        "ownership",
        "ownership_hooks",
        "ownership_binding",
        "ownership_files",
        "ownership_completion",
        "ownership_composition",
        "ownership_identity",
        "ownership_seal",
        "ownership_surface",
    )
    modules = {n: importlib.import_module("xgw." + n) for n in names}
    monkeypatch.setattr(h, "M", modules)
    monkeypatch.setattr(ak, "M", modules)
    monkeypatch.setattr(h, "AK", ak)
    monkeypatch.setattr(h, "SUPPORT", SimpleNamespace(BOOT="11111111-1111-1111-1111-111111111111"))
    monkeypatch.setattr(h, "HOOKS", tuple(modules["ownership_binding"].FUNCTIONS))
    monkeypatch.setattr(h, "DETAILS", dict.fromkeys(h.DETAIL_KEYS))
    return h


@pytest.mark.parametrize(
    "case",
    [
        "I_ONE",
        "I_NOOP",
        "I_EARLY_LEASE",
        "I_REPLAY",
        "I_FENCED",
        "H_00_ROLE_PREPARE",
        "H_00_SHADOW_BODY",
        "H_00_ROLE_FINAL",
        "A_pool_NONE_CHECKER",
        "R_STORE_NONE_BODY",
        "B_SOURCE_HASH_RUN",
        "C_GATE_CODE",
        "C_CHECKER_DEFAULT",
        "P_EQUAL_IDENTITY",
        "P_UNSEALED",
        "F_CHECKER_FALSE",
        "F_FINAL_TERMINAL",
        "F_SWAP_BOUNDARY_FINAL",
        "T_02_BODY",
        "T_19_FINAL",
    ],
)
def test_explicit_composition_contracts(helper, tmp_path, case):
    work = tmp_path / "private"
    work.mkdir(mode=0o700)
    helper.run_case(SimpleNamespace(root=tmp_path, work=work), case)


def test_gate_and_seal_constructor_have_no_io(helper, tmp_path, monkeypatch):
    work = tmp_path / "private"
    work.mkdir(mode=0o700)
    f = SimpleNamespace(root=tmp_path, work=work)
    helper.fixture(f, "I_ONE")
    cm = helper.M["ownership_composition"]

    def forbidden(*a, **kw):
        raise AssertionError("unexpected constructor IO")

    monkeypatch.setattr(os, "open", forbidden)
    gate = cm.BuildCompletion(f.registry, f.preflight, f.files)
    c = helper.M["ownership_hooks"].Coordinator(f.registry, gate)
    for actor in f.actors.values():
        object.__setattr__(actor, "ownership", c)
    binding = helper.M["ownership_binding"].BoundWriters(c, f.actors)
    composition = cm.Composition(binding)
    assert composition.gate is gate
    assert gate.observations == 0


def test_partial_details_survive_operation_exception(helper, tmp_path, monkeypatch):
    original = helper.fixture

    def fixture(f, name):
        original(f, name)

        def trigger(when):
            if when == "BODY":
                raise ValueError("private fixture failure")

        f.trigger = trigger

    monkeypatch.setattr(helper, "fixture", fixture)
    work = tmp_path / "private"
    work.mkdir(mode=0o700)
    with pytest.raises(ValueError, match=r"^private fixture failure$"):
        helper.run_case(SimpleNamespace(root=tmp_path, work=work), "I_ONE")
    assert helper.DETAILS["body_calls"] == 1
    assert helper.DETAILS["unknown_writers"] == 1
    assert helper.DETAILS["registry_receipts"] == 0
    assert helper.DETAILS["target_restored"] is True
