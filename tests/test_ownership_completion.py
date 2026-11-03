import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

from xgw.ownership_completion import CompletionContract, CompletionRefused, FileCompletion
from xgw.ownership_files import FileExpectation, PrivateFiles


@pytest.fixture
def context(tmp_path):
    tmp_path.chmod(0o700)
    path = tmp_path / "result.txt"
    path.write_bytes(b"BASELINE\n")
    path.chmod(0o600)
    observer = PrivateFiles(
        tmp_path,
        expected_uid=os.getuid(),
        expectations=(
            FileExpectation("result.txt", hashlib.sha256(path.read_bytes()).hexdigest()),
        ),
    )
    contract = CompletionContract(frozenset({"PANEL"}), ("FILES",), "COMMITTED")
    return path, observer, contract


def test_fresh_observation_does_not_reuse_previous_success(context):
    path, observer, contract = context
    v = FileCompletion(contract, observer, accept=lambda value: value is True)
    assert v(contract.roles, True).accepted()
    path.write_bytes(b"CHANGED\n")
    assert not v(contract.roles, True).accepted()
    assert v.last.reason == "FILES_NOT_VERIFIED" and v.last.checked == 0


def test_unsupported_domain_refuses_before_checker_or_files(context):
    _, observer, contract = context
    called = []
    observer.root /= "absent"
    v = FileCompletion(
        CompletionContract(contract.roles, ("FILES", "KERNEL"), "COMMITTED"),
        observer,
        accept=lambda value: called.append(1) or True,
    )
    assert not v(contract.roles, True).accepted() and called == []
    assert v.last.reason == "DOMAIN_NOT_IMPLEMENTED" and not v.last.observation_entered


def test_swallowed_reentry_taints_outer_check(context):
    _, observer, contract = context

    def check(value):
        with pytest.raises(CompletionRefused):
            v(contract.roles, value)
        return True

    v = FileCompletion(contract, observer, accept=check)
    assert not v(contract.roles, True).accepted()
    assert v.last.reason == "VERIFIER_TAINTED" and not v.last.observation_entered


def test_internal_observer_shadow_is_refused(context):
    _, observer, contract = context
    v = FileCompletion(contract, observer, accept=lambda value: True)
    observer.observe_one = lambda *args: None
    assert not v(contract.roles, True).accepted()
    assert v.last.reason == "OBSERVER_DRIFT" and not v.last.accept_entered


def test_partial_checked_prefix_is_not_full_verification(context):
    _, observer, contract = context
    observer.expectations += (FileExpectation("absent.txt", "0" * 64),)
    v = FileCompletion(contract, observer, accept=lambda value: True)
    assert not v(contract.roles, True).accepted()
    assert v.last.checked == 1 and v.last.matched is False


def test_constructor_and_nontrue_result_do_not_read_files(context, monkeypatch):
    _, observer, contract = context

    def no_io(*args, **kwargs):
        raise AssertionError("unexpected I/O")

    monkeypatch.setattr(Path, "lstat", no_io)
    v = FileCompletion(contract, observer, accept=lambda value: 1)
    assert not v(contract.roles, True).accepted()
    assert v.last.reason == "RESULT_NOT_ACCEPTED" and not v.last.observation_entered


@pytest.mark.parametrize("field,value", [("expectations", ()), ("expected_uid", True)])
def test_observer_policy_is_validated_again_at_composition(context, field, value):
    _, observer, contract = context
    setattr(observer, field, value)
    with pytest.raises(CompletionRefused, match="OBSERVER_POLICY"):
        FileCompletion(contract, observer, accept=lambda result: True)


@pytest.mark.parametrize("case", ["I_COMMITTED", "I_NOOP", "I_ROLLBACK", "I_FILES_MISMATCH"])
def test_real_panel_composite_final_files_gate_receipt(tmp_path, case):
    stand = Path(__file__).parents[1] / "tests/stand"

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    h = load("ai_narrow_helper", stand / "wave3_file_completion.py")
    s = load("ai_narrow_support", stand / "wave3_source_hooks.py")
    names = (
        "ownership",
        "ownership_adapters",
        "ownership_hooks",
        "paths",
        "managed",
        "ownership_binding",
        "ownership_files",
        "ownership_completion",
    )
    s.MODULES = {n: importlib.import_module("xgw." + n) for n in names}
    h.SUPPORT, h.M = s, s.MODULES
    h.DETAILS = dict.fromkeys(h.DETAIL_KEYS)
    f = s.Fixture(tmp_path)
    h.integration_case(f, case)
    assert f.registry.summary()["receipts"] == (0 if case == "I_FILES_MISMATCH" else 1)


def test_report_freezes_partial_actuals_and_refuses_private_fields(tmp_path, monkeypatch):
    stand = Path(__file__).parents[1] / "tests/stand"
    modules = []
    for name in ("wave3_file_completion", "wave3_source_hooks"):
        spec = importlib.util.spec_from_file_location(
            "report_narrow_" + name, stand / (name + ".py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    h, support = modules
    tmp_path.chmod(0o700)
    monkeypatch.setattr(h, "NOTES", tmp_path)
    h.SUPPORT = support
    support.create(tmp_path / "source-current.json", {"head": "a" * 40, "tree": "b" * 40})
    support.create(tmp_path / "manifest.json", {})
    row = {
        "case": h.EXPECTED[0],
        "passed": False,
        "elapsed_ms": 17,
        "details": dict.fromkeys(h.DETAIL_KEYS),
        "reason": "PRIVATE_EXCEPTION_TEXT",
    }
    data = {"final": False, "completed": 1, "cases": [row]}
    support.create(tmp_path / "progress.json", data)
    h.report()
    preview = (tmp_path / "report-data.md").read_bytes()
    assert b"PRIVATE_EXCEPTION_TEXT" not in preview and b'"file_checked":null' in preview
    # An advancing collector must not force a partial-report rewrite or rerun.
    (tmp_path / "progress.json").write_text(json.dumps({"invalid": "NEW_PRIVATE"}))
    h.report()
    assert (tmp_path / "report-data.md").read_bytes() == preview
    record = json.loads((tmp_path / "report-record.json").read_bytes())
    record["data"]["cases"][0]["details"]["private_config"] = "SECRET"
    (tmp_path / "report-record.json").write_text(json.dumps(record))
    with pytest.raises(ValueError, match="DETAIL_FIELDS"):
        h.report()
