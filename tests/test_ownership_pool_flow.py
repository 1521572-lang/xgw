import importlib
import importlib.util
import os
from pathlib import Path

import pytest


@pytest.fixture
def flow(tmp_path):
    stand = Path(__file__).parents[1] / "tests/stand"

    def load(name, filename):
        spec = importlib.util.spec_from_file_location(name, stand / filename)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    support = load("ag_support_narrow", "wave3_source_hooks.py")
    helper = load("ag_helper_narrow", "wave3_pool_flow.py")
    names = (
        "ownership",
        "ownership_hooks",
        "ownership_adapters",
        "ownership_binding",
        "paths",
        "config",
        "net.capture",
        "net.nft",
        "net.tun",
        "freepool.backend",
        "freepool.models",
        "freepool.store",
        "freepool.pool",
        "apply.applier",
        "apply.singbox",
        "xraycore.api",
        "managed",
        "cores",
    )
    support.MODULES = {name: importlib.import_module("xgw." + name) for name in names}
    helper.SUPPORT, helper.M = support, support.MODULES
    created = []

    def make():
        path = tmp_path / f"fixture-{len(created)}"
        path.mkdir(mode=0o700)
        created.append(path)
        helper.DETAILS = {}
        return support.Fixture(path)

    previous = os.umask(0o077)
    try:
        yield helper, make
    finally:
        os.umask(previous)


def test_constructor_cleanup_legacy_owned_and_before_effect_refusal(flow):
    helper, make = flow
    for mode in ("LEGACY", "OWNED", "FENCED"):
        helper.constructor(make(), "RETIRED", mode)


def test_store_rotation_has_one_outer_receipt_and_legacy_bytes(flow):
    helper, make = flow
    helper.matrix(make(), "S", "ROTATE", "LEGACY")
    owned = make()
    helper.matrix(owned, "S", "ROTATE", "OWNED")
    assert helper.DETAILS["legacy_equivalent"] is True
    assert owned.registry.summary()["receipts"] == 1


def test_source_tunnel_flow_uses_fake_runner_and_one_receipt(flow):
    helper, make = flow
    helper.matrix(make(), "P", "CHECK_TUNNEL", "LEGACY")
    owned = make()
    helper.matrix(owned, "P", "CHECK_TUNNEL", "OWNED")
    assert helper.DETAILS["legacy_equivalent"] is True
    assert owned.registry.summary()["receipts"] == 1
    assert len(owned.trace) > 1


def test_caught_nested_prune_error_does_not_publish_completion(flow):
    helper, make = flow
    fixture = make()
    helper.extras(fixture, "E_PRUNE_ERROR")
    assert fixture.registry.summary()["unknown"] == 1


@pytest.mark.parametrize(
    "name", ("E_POOL_STORE_ALIAS", "E_POOL_RUNTIME_ALIAS", "E_APPLIER_API_ALIAS")
)
def test_nine_actor_binding_rejects_foreign_dependency_reference(flow, name):
    helper, make = flow
    fixture = make()
    helper.extras(fixture, name)
    assert fixture.registry.summary()["writers"] == 0


@pytest.mark.parametrize("name", ("I_REFRESH_CHECK", "I_SECOND_FAIL"))
def test_composite_refresh_probe_scope_and_partial_failure(flow, name):
    helper, make = flow
    fixture = make()
    helper.extras(fixture, name)
    assert fixture.registry.summary()["receipts"] == (1 if name == "I_REFRESH_CHECK" else 0)


def test_foreign_runtime_refused_before_constructor_file_cleanup(flow):
    helper, make = flow
    helper.extras(make(), "E_FOREIGN_NONE")


def test_store_constructor_is_explicit_and_has_no_io(flow):
    helper, make = flow
    helper.extras(make(), "E_STORE_NOIO")
