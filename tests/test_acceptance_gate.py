
"""Acceptance must not classify a different assertion as an old failure."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "acceptance_test_gate", Path(__file__).resolve().parents[1] /
    "docs/helpers/acceptance_test_gate.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def junit(tmp_path, name, message="", *, skipped=False):
    from xml.etree.ElementTree import Element, SubElement, tostring

    root = Element("testsuite", errors="0", failures="1" if message else "0")
    case = SubElement(root, "testcase", classname="tests.test_example", name="case")
    if message:
        SubElement(case, "failure", message=message)
    if skipped:
        SubElement(case, "skipped")
    path = tmp_path / name
    path.write_bytes(tostring(root))
    return path


def test_identical_failure_accepts_only_checkout_prefix_difference(tmp_path):
    a, b = tmp_path / "new", tmp_path / "old"
    new = gate.read(junit(tmp_path, "new.xml", f"assert {a}/config == expected"), a)
    old = gate.read(junit(tmp_path, "old.xml", f"assert {b}/config == expected"), b)
    result = gate.compare(new, old)
    assert result["ok"] and len(result["matching_baseline_failures"]) == 1


@pytest.mark.parametrize("old_message", ["", "assert 1 == 2"])
def test_new_or_changed_failure_blocks(tmp_path, old_message):
    new = gate.read(junit(tmp_path, "new.xml", "assert 3 == 4"), tmp_path)
    old = gate.read(junit(tmp_path, "old.xml", old_message), tmp_path)
    assert not gate.compare(new, old)["ok"]


def test_missing_case_or_new_skip_cannot_waive_a_test(tmp_path):
    old = gate.read(junit(tmp_path, "old.xml"), tmp_path)
    new = gate.read(junit(tmp_path, "new.xml", skipped=True), tmp_path)
    assert not gate.compare(new, old)["ok"]
    assert not gate.compare({}, old)["ok"]


def test_empty_or_ambiguous_junit_is_rejected(tmp_path):
    path = tmp_path / "empty.xml"
    path.write_text("<testsuite/>")
    with pytest.raises(ValueError, match="junit_empty"):
        gate.read(path, tmp_path)
    path.write_text('<testsuite><testcase classname="a" name="b"/>'
                    '<testcase classname="a" name="b"/></testsuite>')
    with pytest.raises(ValueError, match="junit_duplicate"):
        gate.read(path, tmp_path)

