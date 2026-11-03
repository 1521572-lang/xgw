import hashlib
import os

import pytest

from xgw.ownership import Registry
from xgw.ownership_adapters import Verification
from xgw.ownership_binding import SPECS, BoundWriters, PanelWriter, Step
from xgw.ownership_files import FileExpectation, PrivateFiles
from xgw.ownership_hooks import Coordinator, MutationBlocked


@pytest.fixture
def context(tmp_path):
    registry = Registry(
        tmp_path / "registry",
        boot_id="11111111-1111-1111-1111-111111111111",
        expected_uid=os.getuid(),
        clock_ns=lambda: 10,
    )
    registry.initialize()
    coordinator = Coordinator(
        registry, lambda roles, values: Verification("COMMITTED", (("FILES", True),))
    )
    actors = {}
    for name, (cls, _, _) in SPECS.items():
        actor = cls.__new__(cls)
        object.__setattr__(actor, "ownership", coordinator)
        actors[name] = actor
    actors["panel"] = PanelWriter(tmp_path / "panel.json", coordinator)
    object.__setattr__(actors["api"], "_run", lambda *args, **kwargs: "")
    return registry, coordinator, actors


def test_missing_actor_and_shadowed_hook_refuse_before_admission(context):
    registry, c, actors = context
    missing = dict(actors)
    missing.pop("api")
    with pytest.raises(MutationBlocked):
        BoundWriters(c, missing)
    actors["capture"].down = lambda: None
    with pytest.raises(MutationBlocked):
        BoundWriters(c, actors)
    assert registry.summary()["writers"] == 0


def test_composite_real_api_and_panel_have_one_final_receipt(context, tmp_path):
    registry, c, actors = context
    seen = []
    c.verifier = lambda roles, values: (
        seen.append((roles, values)) or Verification("COMMITTED", (("FILES", True),))
    )
    batch = BoundWriters(c, actors).prepare(
        (
            Step("api", "pin", ("fixture", "fixture")),
            Step("panel", "update", (lambda data: False,)),
        ),
        accept=lambda step, value: value == "" if step.writer == "api" else value is False,
    )
    assert batch.run() == ("", False)
    assert seen == [(frozenset({"LIFECYCLE", "API", "PANEL"}), ("", False))]
    assert registry.summary()["receipts"] == 1
    with pytest.raises(MutationBlocked, match="BATCH_ALREADY_USED"):
        batch.run()


def test_drift_after_first_body_stops_next_and_keeps_unknown(context):
    registry, c, actors = context
    called = []

    def first(*args, **kwargs):
        called.append(1)
        actors["peers"].ownership = None
        return ""

    object.__setattr__(actors["api"], "_run", first)
    batch = BoundWriters(c, actors).prepare(
        (
            Step("api", "pin", ("fixture", "fixture")),
            Step("api", "unpin", ("fixture",)),
        ),
        accept=lambda step, value: True,
    )
    with pytest.raises(MutationBlocked, match="ACTOR_UNBOUND"):
        batch.run()
    assert called == [1] and registry.summary()["unknown"] == 1
    assert registry.summary()["receipts"] == 0


def test_false_step_checker_stops_before_next_body(context):
    registry, c, actors = context
    trace = []
    object.__setattr__(actors["api"], "_run", lambda *args, **kwargs: trace.append(1) or "")
    plan = BoundWriters(c, actors).prepare(
        (
            Step("api", "pin", ("fixture", "fixture")),
            Step("api", "unpin", ("fixture",)),
        ),
        accept=lambda step, value: 1,
    )
    with pytest.raises(MutationBlocked, match="STEP_RESULT_REFUSED"):
        plan.run()
    assert trace == [1] and registry.summary()["unknown"] == 1


def test_admission_refusal_consumes_plan_and_mutates_no_files(context, tmp_path):
    registry, c, actors = context
    plan = BoundWriters(c, actors).prepare(
        (Step("panel", "update", (lambda data: True,)),), accept=lambda step, value: True
    )
    registry.acquire(run_id="a" * 32, expected_generation=0, duration_ns=100)
    with pytest.raises(MutationBlocked):
        plan.run()
    with pytest.raises(MutationBlocked, match="BATCH_ALREADY_USED"):
        plan.run()
    assert not (tmp_path / ".panel.json.lock").exists()
    assert registry.summary()["receipts"] == 0


def observer(root, relative="file", **kwargs):
    return PrivateFiles(
        root,
        expected_uid=os.getuid(),
        expectations=(
            FileExpectation(
                relative,
                digest=hashlib.sha256(b"fixture").hexdigest(),
                **kwargs,
            ),
        ),
    )


def test_exact_file_reader_is_readonly_and_checks_mode(tmp_path):
    tmp_path.chmod(0o700)
    path = tmp_path / "file"
    path.write_bytes(b"fixture")
    path.chmod(0o600)
    before = path.stat()
    assert observer(tmp_path).observe().matched is True
    after = path.stat()
    assert (before.st_mtime_ns, before.st_ctime_ns) == (after.st_mtime_ns, after.st_ctime_ns)
    path.chmod(0o640)
    assert observer(tmp_path).observe().reason == "FILE_METADATA"


def test_file_reader_refuses_symlink_ancestor_and_hardlink(tmp_path):
    tmp_path.chmod(0o700)
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    (target / "file").write_bytes(b"fixture")
    (target / "file").chmod(0o600)
    (tmp_path / "alias").symlink_to(target, target_is_directory=True)
    assert observer(tmp_path, "alias/file").observe().matched is False
    os.link(target / "file", tmp_path / "file")
    assert observer(tmp_path).observe().reason == "FILE_METADATA"


def test_absence_does_not_treat_missing_parent_or_symlink_as_absent(tmp_path):
    tmp_path.chmod(0o700)

    def absent(relative):
        return PrivateFiles(
            tmp_path,
            expected_uid=os.getuid(),
            expectations=(FileExpectation(relative, absent=True),),
        ).observe()

    assert absent("missing").matched is True
    assert absent("missing/file").matched is False
    (tmp_path / "link").symlink_to(tmp_path / "absent-target")
    assert absent("link").reason == "EXPECTED_ABSENCE"


@pytest.mark.parametrize("case", ("C_SB_XRAY", "C_SECOND_REJECT"))
def test_new_helper_two_core_fixture_and_exact_file_contract(tmp_path, case):
    import importlib
    import importlib.util
    from pathlib import Path

    stand = Path(__file__).parents[1] / "tests/stand"

    def load(name, file):
        spec = importlib.util.spec_from_file_location(name, stand / file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    support = load("ae_support_contract", "wave3_source_hooks.py")
    helper = load("ae_helper_contract", "wave3_bound_batch.py")
    names = (
        "ownership",
        "ownership_hooks",
        "ownership_adapters",
        "ownership_binding",
        "ownership_files",
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
    )
    support.MODULES = {name: importlib.import_module("xgw." + name) for name in names}
    helper.SUPPORT, helper.M = support, support.MODULES
    helper.DETAILS = {}
    previous = os.umask(0o077)
    try:
        fixture = support.Fixture(tmp_path)
        helper.composite_case(fixture, case)
    finally:
        os.umask(previous)
    if case == "C_SB_XRAY":
        assert helper.DETAILS["file_checked"] == 2
        assert helper.DETAILS["file_matched"] is True
        assert fixture.registry.summary()["generation"] == 1
    else:
        assert helper.DETAILS["rejection_observed"] is True
        assert fixture.registry.summary()["unknown"] == 1


def test_observer_refuses_replacement_after_open(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    path = tmp_path / "file"
    path.write_bytes(b"fixture")
    path.chmod(0o600)
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"fixture")
    replacement.chmod(0o600)
    original = os.stat

    def replacing(name, *args, **kwargs):
        if name == "file" and "dir_fd" in kwargs:
            os.replace(replacement, path)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(os, "stat", replacing)
    assert observer(tmp_path).observe().reason == "FILE_CHANGED"
