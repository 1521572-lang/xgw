import importlib
import importlib.util
import os
from pathlib import Path

import pytest


@pytest.fixture
def flow(tmp_path):
    stand = Path(__file__).parents[1] / "tests/stand"

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, stand / path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    support = load("af_support_narrow", "wave3_source_hooks.py")
    helper = load("af_helper_narrow", "wave3_source_flow.py")
    names = (
        "ownership",
        "ownership_hooks",
        "ownership_adapters",
        "ownership_binding",
        "paths",
        "net.capture",
        "net.nft",
        "net.tun",
        "freepool.backend",
        "apply.applier",
        "apply.singbox",
        "xraycore.api",
        "managed",
        "cores",
        "engine",
    )
    support.MODULES = {name: importlib.import_module("xgw." + name) for name in names}
    helper.SUPPORT, helper.M = support, support.MODULES
    created = []

    def fixture():
        path = tmp_path / f"fixture-{len(created)}"
        path.mkdir(mode=0o700)
        created.append(path)
        helper.DETAILS = {}
        return support.Fixture(path)

    previous = os.umask(0o077)
    try:
        yield helper, fixture
    finally:
        os.umask(previous)


@pytest.mark.parametrize("name", ("SET_STICKY", "DROP_TELEGRAM"))
def test_public_panel_nested_save_keeps_legacy_bytes_and_one_receipt(flow, name):
    helper, make = flow
    helper.matrix(make(), "P", name, "LEGACY")
    owned = make()
    helper.matrix(owned, "P", name, "OWNED")
    assert helper.DETAILS["legacy_equivalent"] is True
    assert owned.registry.summary()["receipts"] == 1


def test_job_run_is_fenced_before_state_write_and_request_unlink(flow):
    helper, make = flow
    fixture = make()
    helper.matrix(fixture, "K", "JOB_RUN", "FENCED")
    assert fixture.paths.cores_request_file.exists()
    assert not fixture.paths.cores_state_file.exists()


@pytest.mark.parametrize("name", ("K_REQUEST_FOREIGN", "K_REQUEST_NO_JOB", "K_SWALLOWED_SAVE"))
def test_job_factory_binding_and_swallowed_nested_error(flow, name):
    helper, make = flow
    fixture = make()
    helper.extras(fixture, name)
    assert fixture.registry.summary()["receipts"] == (1 if name == "K_REQUEST_NO_JOB" else 0)


@pytest.mark.parametrize("name", ("API", "APPLIER", "SINGBOX"))
def test_factory_propagates_fence_to_real_product_object(flow, name):
    helper, make = flow
    fixture = make()
    helper.factory(fixture, name, "FENCED")
    assert fixture.registry.summary()["writers"] == 0


def test_free_function_hook_rejects_ambiguous_signature_and_generator(flow):
    helper, make = flow
    helper.extras(make(), "H_SIGNATURE")
    helper.extras(make(), "H_DEFERRED")


def test_free_function_hook_caught_error_taints_outer(flow):
    helper, make = flow
    fixture = make()
    helper.extras(fixture, "H_NESTED_ERROR")
    assert fixture.registry.summary()["unknown"] == 1
